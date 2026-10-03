"""Target/parameter admission is independent of any browser success simulation."""

import uuid

import pytest
from pydantic import SecretStr

from backend.app.config import settings
from fixture_contract.registry import load_contract
from runner.contracts import RunnerViolation, validate_job


def job():
    contract = load_contract()
    artifact = contract.artifact("checkout_mobile_fixed")
    return {"job_id": str(uuid.uuid4()), "lease_token": str(uuid.uuid4()), "lease_until": "2030-01-01T00:00:00Z",
        "task_id": str(uuid.uuid4()), "delivery_id": str(uuid.uuid4()), "mandate_version_id": str(uuid.uuid4()),
        "mandate_digest": "a"*64, "artifact_version_id": str(uuid.uuid4()), "artifact_digest": artifact.digest,
        "fixture_url": "http://fixture:8080"+artifact.relative_path,
        "checks": [{"check_id": f"C0{i}", "template_type": t.template_type, "params": t.params,
                    "compiled_by": "ai", "approved": True} for i, t in enumerate(contract.family(artifact.family).templates, 1)]}


@pytest.mark.parametrize("change", ["host", "traversal", "query", "digest", "code", "width", "unapproved"])
def test_untrusted_targets_and_templates_are_rejected(change):
    request = job()
    if change=="host": request["fixture_url"] = request["fixture_url"].replace("fixture", "attacker", 1)
    elif change=="traversal": request["fixture_url"] += "/../admin"
    elif change=="query": request["fixture_url"] += "?target=https://attacker.invalid"
    elif change=="digest": request["artifact_digest"] = "a"*64
    elif change=="code": request["checks"][0]["template_type"] = "execute_code"
    elif change=="width": request["checks"][0]["params"]["width"] = 480
    else: request["checks"][0]["approved"] = False
    with pytest.raises(RunnerViolation):
        validate_job(request, "http://fixture:8080")


def test_runner_request_limits_and_duplicate_json(client, monkeypatch):
    monkeypatch.setattr(settings, "RUNNER_SERVICE_TOKEN", SecretStr("test-only-runner-service-token-length-32"))
    headers = {"Authorization": "Bearer test-only-runner-service-token-length-32", "Content-Type": "application/json"}
    path = f"/internal/runner/jobs/{uuid.uuid4()}/complete"
    assert client.post(path, content=b"x"*3145729, headers=headers).status_code==413
    assert client.post(path, content=b'{"lease_token":"one","lease_token":"two"}', headers=headers).status_code==422
