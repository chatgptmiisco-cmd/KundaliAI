"""Subscription tier state + Razorpay checkout/webhook orchestration."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.subscription import Subscription
from app.schemas.subscription import CheckoutRequest, CheckoutResponse, SubscriptionOut
from app.services.payments.razorpay_client import RazorpayClient

_PRICING_INR_PAISE = {
    ("insight", "monthly"): 19900,
    ("insight", "yearly"): 199900,
    ("strategy", "monthly"): 49900,
    ("strategy", "yearly"): 499900,
}

_PERIOD_DAYS = {"monthly": 30, "yearly": 365}


async def get_or_create_subscription(db: AsyncSession, user_id: str) -> Subscription:
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    sub = result.scalar_one_or_none()
    if sub is None:
        sub = Subscription(user_id=user_id, tier="free", status="active")
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
    return sub


def to_subscription_out(sub: Subscription) -> SubscriptionOut:
    return SubscriptionOut(
        tier=sub.tier, status=sub.status, billing_cycle=sub.billing_cycle,
        current_period_end=sub.current_period_end,
    )


async def start_checkout(db: AsyncSession, user_id: str, request: CheckoutRequest) -> CheckoutResponse:
    client = RazorpayClient()
    amount = _PRICING_INR_PAISE[(request.tier, request.billing_cycle)]
    order = await client.create_order(amount_paise=amount, currency="INR", receipt=f"{user_id}:{request.tier}")

    sub = await get_or_create_subscription(db, user_id)

    if order.simulated:
        # No real payment gateway configured — activate immediately so the
        # rest of the product is fully testable end-to-end.
        sub.tier = request.tier
        sub.status = "active"
        sub.billing_cycle = request.billing_cycle
        sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=_PERIOD_DAYS[request.billing_cycle])
        await db.commit()

    return CheckoutResponse(
        simulated=order.simulated,
        checkout_url=order.checkout_url,
        provider="razorpay",
        tier=request.tier,
        note=order.note,
    )


async def apply_webhook_event(db: AsyncSession, event: str, payload: dict) -> None:
    """Handles the subset of Razorpay subscription webhook events relevant
    to tier state. Unknown events are ignored (logged by the caller)."""
    entity = payload.get("subscription", {}).get("entity", {})
    razorpay_subscription_id = entity.get("id")
    notes = entity.get("notes", {})
    user_id = notes.get("user_id")
    if not user_id:
        return

    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    sub = result.scalar_one_or_none()
    if sub is None:
        return

    if event in ("subscription.activated", "subscription.charged"):
        sub.status = "active"
    elif event in ("subscription.cancelled", "subscription.completed"):
        sub.status = "cancelled"
        sub.tier = "free"
    elif event == "subscription.pending":
        sub.status = "past_due"

    if razorpay_subscription_id:
        sub.razorpay_subscription_id = razorpay_subscription_id

    await db.commit()
