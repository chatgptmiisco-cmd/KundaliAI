"""Razorpay integration.

Runs in one of two modes based on whether real credentials are configured:

- Stub mode (no RAZORPAY_KEY_ID/SECRET set): `create_order` returns a
  simulated order immediately, no network call — subscription_service treats
  it as an instant, always-successful checkout. This is what's active by
  default in this pass.
- Real mode (credentials set): calls Razorpay's REST API directly over
  https using the documented Orders endpoint. No official SDK dependency —
  it's a thin, well-documented HTTP call, so this stays easy to audit.

Webhook signature verification (`verify_webhook_signature`) follows
Razorpay's documented scheme (HMAC-SHA256 of the raw body with the webhook
secret) and works identically in both modes once a real webhook secret is
set — the difference only affects order creation.
"""
import hashlib
import hmac
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

_RAZORPAY_API_BASE = "https://api.razorpay.com/v1"


@dataclass(frozen=True)
class OrderResult:
    simulated: bool
    order_id: str | None
    checkout_url: str | None
    note: str


class RazorpayClient:
    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.razorpay_key_id and self._settings.razorpay_key_secret)

    async def create_order(self, amount_paise: int, currency: str, receipt: str) -> OrderResult:
        if not self.is_configured:
            return OrderResult(
                simulated=True,
                order_id=f"sim_{receipt}",
                checkout_url=None,
                note="Razorpay is not configured — this checkout was simulated locally and the "
                "subscription was activated immediately without any real payment.",
            )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_RAZORPAY_API_BASE}/orders",
                auth=(self._settings.razorpay_key_id, self._settings.razorpay_key_secret),
                json={"amount": amount_paise, "currency": currency, "receipt": receipt},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
        return OrderResult(
            simulated=False,
            order_id=data["id"],
            checkout_url=None,  # Razorpay Checkout is a client-side widget keyed by order_id
            note="Real Razorpay order created — complete payment client-side with Razorpay Checkout.",
        )

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        if not self._settings.razorpay_webhook_secret:
            return False
        expected = hmac.new(
            self._settings.razorpay_webhook_secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
