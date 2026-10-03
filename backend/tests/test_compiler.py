from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from backend.app.config import settings
from backend.app.services.compiler import CompilerError, compile_revision, provider_config
from fixture_contract.registry import load_contract


def revision(family="responsive_css"):
    return SimpleNamespace(family=family, title="Keep checkout usable", body="Fit the checkout at 320px and keep the total unchanged.")


def proposal(contract, family="responsive_css"):
    return {
        "checks": [
            {"check_id": f"C0{number}", "template_type": item.template_type,
             "params": item.params, "compiled_by": "ai", "approved": False}
            for number, item in enumerate(contract.family(family).templates, start=1)
        ],
        "ambiguities": [], "clarifying_questions": [],
    }


@pytest.mark.asyncio
async def test_openai_structured_output_is_validated(monkeypatch):
    contract = load_contract()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("test-openai-key"))
    seen = {}

    async def handler(request):
        seen["payload"] = request.read()
        return httpx.Response(200, json={"choices": [{"message": {"content": __import__("json").dumps(proposal(contract))}}], "usage": {"total_tokens": 7}})

    result = await compile_revision(contract, revision(), transport=httpx.MockTransport(handler))
    assert result.status == "ready"
    assert result.provider == "openai"
    assert result.proposal.checks[0].params == {"width": 320, "target_ref": "checkout"}
    assert b"response_format" in seen["payload"]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gemini", "openrouter"])
async def test_provider_adapters_use_json_contract(monkeypatch, provider):
    contract = load_contract()
    monkeypatch.setattr(settings, "LLM_PROVIDER", provider)
    if provider == "gemini":
        monkeypatch.setattr(settings, "GEMINI_API_KEY", SecretStr("test-gemini-key"))
    else:
        monkeypatch.setattr(settings, "OPENROUTER_API_KEY", SecretStr("test-openrouter-key"))

    async def handler(request):
        if provider == "gemini":
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": __import__("json").dumps(proposal(contract))}]}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": __import__("json").dumps(proposal(contract))}}]})

    result = await compile_revision(contract, revision(), transport=httpx.MockTransport(handler))
    assert result.status == "ready"
    assert result.provider == provider


def test_missing_provider_credentials_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", SecretStr(""))
    with pytest.raises(CompilerError) as error:
        provider_config()
    assert error.value.code == "MODEL_UNAVAILABLE"


@pytest.mark.asyncio
async def test_semantic_parameter_drift_becomes_ambiguous(monkeypatch):
    contract = load_contract()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("test-openai-key"))
    invalid = deepcopy(proposal(contract))
    invalid["checks"][0]["params"]["width"] = 375

    async def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": __import__("json").dumps(invalid)}}]})

    result = await compile_revision(contract, revision(), transport=httpx.MockTransport(handler))
    assert result.status == "ambiguous"
    assert result.reasons


@pytest.mark.asyncio
async def test_unresolved_questions_block_a_complete_looking_proposal(monkeypatch):
    contract = load_contract()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("test-openai-key"))
    unresolved = proposal(contract)
    unresolved["ambiguities"] = ["The requested browser target is unclear."]
    unresolved["clarifying_questions"] = ["Should this apply to the reviewed checkout?"]

    async def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": __import__("json").dumps(unresolved)}}]})

    result = await compile_revision(contract, revision(), transport=httpx.MockTransport(handler))
    assert result.status == "ambiguous"
