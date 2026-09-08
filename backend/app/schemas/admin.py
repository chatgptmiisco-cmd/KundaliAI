from datetime import datetime

from pydantic import BaseModel


class AdminUserListItem(BaseModel):
    id: str
    email_masked: str | None
    phone_masked: str | None
    tier: str
    is_active: bool
    created_at: datetime


class AdminUserDetail(BaseModel):
    id: str
    email_masked: str | None
    phone_masked: str | None
    preferred_language: str
    tier: str
    subscription_status: str
    has_birth_profile: bool
    is_active: bool
    is_admin: bool
    created_at: datetime


class AdminRegenerateRequest(BaseModel):
    user_id: str
    targets: list[str] = ["chart", "dasha", "horoscope"]
