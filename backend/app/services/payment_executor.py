import re
import time
from typing import Any

import httpx

from backend.app.config import PayPalSettings


class PaymentUnavailable(RuntimeError):
    pass


class PayPalExecutor:
    """Sandbox transport; application dispatch guards are a separate milestone."""

    _operations = (
        ("POST", r"/v1/oauth2/token"),
        ("POST", r"/v1/payments/payouts"),
        ("GET", r"/v1/payments/payouts/[A-Za-z0-9_-]+"),
        ("GET", r"/v1/payments/payouts-item/[A-Za-z0-9_-]+"),
        ("POST", r"/v1/notifications/verify-webhook-signature"),
        ("POST", r"/v1/payments/payouts-item/[A-Za-z0-9_-]+/cancel"),
    )

    def __init__(
        self,
        config: PayPalSettings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.config = config or PayPalSettings()
        self.transport = transport
        self._cached_token: str | None = None
        self._token_expiry = 0.0

    def _require_configuration(self):
        if (
            self.config.PAYPAL_MODE != "sandbox"
            or self.config.PAYPAL_BASE_URL != "https://api-m.sandbox.paypal.com"
        ):
            raise PaymentUnavailable("Only the PayPal sandbox host is permitted")
        credentials = (
            self.config.PAYPAL_CLIENT_ID.get_secret_value(),
            self.config.PAYPAL_CLIENT_SECRET.get_secret_value(),
        )
        if any(not value or value.startswith(("demo_", "your_")) for value in credentials):
            raise PaymentUnavailable("PayPal executor credentials are not configured")

    async def _send(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self._require_configuration()
        if not any(method == verb and re.fullmatch(pattern, path) for verb, pattern in self._operations):
            raise ValueError("PayPal operation is outside the six-endpoint allowlist")
        async with httpx.AsyncClient(
            timeout=20.0, follow_redirects=False, transport=self.transport
        ) as client:
            response = await client.request(
                method, f"{self.config.PAYPAL_BASE_URL}{path}", **kwargs
            )
            response.raise_for_status()
            return response.json()

    async def get_access_token(self) -> str:
        self._require_configuration()
        if self._cached_token and time.monotonic() < self._token_expiry - 60:
            return self._cached_token
        data = await self._send(
            "POST",
            "/v1/oauth2/token",
            auth=(
                self.config.PAYPAL_CLIENT_ID.get_secret_value(),
                self.config.PAYPAL_CLIENT_SECRET.get_secret_value(),
            ),
            data={"grant_type": "client_credentials"},
        )
        self._cached_token = data["access_token"]
        self._token_expiry = time.monotonic() + int(data["expires_in"])
        return self._cached_token

    async def _authorized(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        token = await self.get_access_token()
        return await self._send(
            method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs
        )

    async def create_payout(
        self,
        sender_batch_id: str,
        sender_item_id: str,
        amount_usd: str,
        receiver_email: str,
        note: str = "ProofPay acceptance-verified milestone payment",
    ) -> dict[str, Any]:
        return await self._authorized(
            "POST",
            "/v1/payments/payouts",
            json={
                "sender_batch_header": {
                    "sender_batch_id": sender_batch_id,
                    "email_subject": "You have a payment from ProofPay",
                    "email_message": note,
                },
                "items": [{
                    "recipient_type": "EMAIL",
                    "recipient_wallet": "PAYPAL",
                    "amount": {"value": amount_usd, "currency": "USD"},
                    "note": note,
                    "sender_item_id": sender_item_id,
                    "receiver": receiver_email,
                }],
            },
        )

    async def get_payout_batch(self, batch_id: str) -> dict[str, Any]:
        return await self._authorized("GET", f"/v1/payments/payouts/{batch_id}")

    async def get_payout_item(self, item_id: str) -> dict[str, Any]:
        return await self._authorized("GET", f"/v1/payments/payouts-item/{item_id}")

    async def verify_webhook_signature(
        self,
        transmission_id: str,
        timestamp: str,
        webhook_id: str,
        event_body: dict[str, Any],
        cert_url: str,
        actual_signature: str,
        auth_algo: str,
    ) -> bool:
        if not webhook_id or not all((transmission_id, timestamp, cert_url, actual_signature, auth_algo)):
            return False
        data = await self._authorized(
            "POST",
            "/v1/notifications/verify-webhook-signature",
            json={
                "transmission_id": transmission_id,
                "transmission_time": timestamp,
                "cert_url": cert_url,
                "auth_algo": auth_algo,
                "transmission_sig": actual_signature,
                "webhook_id": webhook_id,
                "webhook_event": event_body,
            },
        )
        return data.get("verification_status") == "SUCCESS"

    async def cancel_unclaimed_item(self, item_id: str) -> dict[str, Any]:
        return await self._authorized("POST", f"/v1/payments/payouts-item/{item_id}/cancel")
