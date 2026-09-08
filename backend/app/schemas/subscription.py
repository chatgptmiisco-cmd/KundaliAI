from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SubscriptionOut(BaseModel):
    tier: Literal["free", "insight", "strategy"]
    status: str
    billing_cycle: str | None
    current_period_end: datetime | None


class CheckoutRequest(BaseModel):
    tier: Literal["insight", "strategy"]
    billing_cycle: Literal["monthly", "yearly"] = "monthly"


class CheckoutResponse(BaseModel):
    simulated: bool
    checkout_url: str | None
    provider: str
    tier: str
    note: str


class RazorpayWebhookEvent(BaseModel):
    """Loosely typed on purpose — Razorpay's webhook payload varies by event
    type; the handler only reads `event` and `payload.subscription.entity`."""

    event: str
    payload: dict
