import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.db.base import get_db
from app.db.models.user import User
from app.schemas.subscription import CheckoutRequest, CheckoutResponse, SubscriptionOut
from app.services.payments.razorpay_client import RazorpayClient
from app.services.payments.subscription_service import (
    apply_webhook_event,
    get_or_create_subscription,
    start_checkout,
    to_subscription_out,
)

router = APIRouter(prefix="/subscription", tags=["subscription"])
logger = get_logger(__name__)


@router.get("", response_model=SubscriptionOut)
async def get_subscription(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    sub = await get_or_create_subscription(db, user.id)
    return to_subscription_out(sub)


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    body: CheckoutRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await start_checkout(db, user.id, body)


@router.post("/webhook/razorpay", status_code=status.HTTP_204_NO_CONTENT)
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_razorpay_signature: str | None = Header(default=None),
):
    raw_body = await request.body()
    client = RazorpayClient()

    if client.is_configured:
        if not x_razorpay_signature or not client.verify_webhook_signature(raw_body, x_razorpay_signature):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature")

    payload = json.loads(raw_body)
    event = payload.get("event", "")
    logger.info("razorpay_webhook_received", extra={"event": event})
    await apply_webhook_event(db, event, payload.get("payload", {}))
