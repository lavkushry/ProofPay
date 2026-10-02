import httpx
import pytest
from pydantic import ValidationError

from backend.app.config import PayPalSettings, Settings
from backend.app.services.payment_executor import PaymentUnavailable, PayPalExecutor


@pytest.mark.parametrize("config", [
    {"PAYPAL_MODE": "live"},
    {"PAYPAL_BASE_URL": "https://api-m.paypal.com"},
    {"PAYPAL_BASE_URL": "https://api-m.sandbox.paypal.com.evil.example"},
])
def test_live_or_untrusted_payment_configuration_is_rejected(config):
    with pytest.raises(ValidationError):
        PayPalSettings(_env_file=None, **config)


def test_api_settings_do_not_load_financial_credentials(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "test-only-secret")
    api_settings = Settings(_env_file=None)
    assert not hasattr(api_settings, "PAYPAL_CLIENT_SECRET")
    assert not hasattr(api_settings, "ENCRYPTION_KEY")


@pytest.mark.parametrize("operation", ["token", "create", "batch", "item", "verify", "cancel"])
async def test_missing_credentials_never_simulate_or_send(operation):
    def unexpected_request(request):
        pytest.fail("Unconfigured executor performed network I/O")

    executor = PayPalExecutor(
        PayPalSettings(_env_file=None), httpx.MockTransport(unexpected_request)
    )
    calls = {
        "token": lambda: executor.get_access_token(),
        "create": lambda: executor.create_payout("batch", "item", "1.00", "test@example.invalid"),
        "batch": lambda: executor.get_payout_batch("batch"),
        "item": lambda: executor.get_payout_item("item"),
        "verify": lambda: executor.verify_webhook_signature(
            "id", "time", "webhook", {}, "cert", "sig", "SHA256withRSA"
        ),
        "cancel": lambda: executor.cancel_unclaimed_item("item"),
    }
    with pytest.raises(PaymentUnavailable):
        await calls[operation]()


async def test_transport_allowlist_denies_custom_endpoint_without_io():
    executor = PayPalExecutor(PayPalSettings(
        _env_file=None, PAYPAL_CLIENT_ID="test-id", PAYPAL_CLIENT_SECRET="test-secret"
    ))
    with pytest.raises(ValueError, match="allowlist"):
        await executor._send("POST", "/v1/customer/disputes")
    with pytest.raises(ValueError, match="allowlist"):
        await executor._send("GET", "/v1/payments/payouts-item/item/../../oauth2/token")


async def test_provider_error_is_not_converted_to_success():
    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "test-token", "expires_in": 3600})
        return httpx.Response(503, json={"name": "TEST_PROVIDER_UNAVAILABLE"})

    executor = PayPalExecutor(PayPalSettings(
        _env_file=None, PAYPAL_CLIENT_ID="test-id", PAYPAL_CLIENT_SECRET="test-secret"
    ), httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await executor.get_payout_item("item")
