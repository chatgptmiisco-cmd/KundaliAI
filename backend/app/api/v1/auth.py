from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import limiter
from app.db.base import get_db
from app.schemas.auth import (
    LoginEmailRequest,
    OAuthLoginRequest,
    PasswordResetRequest,
    RequestOtpRequest,
    RequestOtpResponse,
    SignupEmailRequest,
    TokenResponse,
    VerifyOtpRequest,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse)
async def signup(body: SignupEmailRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await auth_service.signup_with_email(db, body.email, body.password, body.name, body.preferred_language)
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return TokenResponse(access_token=auth_service.issue_token(user), user_id=user.id)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginEmailRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await auth_service.login_with_email(db, body.email, body.password)
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return TokenResponse(access_token=auth_service.issue_token(user), user_id=user.id)


@router.post("/reset-password", response_model=TokenResponse)
async def reset_password(body: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    """Resets the password for the given email with no verification step
    (no OTP, no reset link/token) — anyone who knows the email can reset it."""
    try:
        user = await auth_service.reset_password(db, body.email, body.new_password)
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return TokenResponse(access_token=auth_service.issue_token(user), user_id=user.id)


@router.post("/otp/request", response_model=RequestOtpResponse)
@limiter.limit("5/minute")
async def request_otp(request: Request, body: RequestOtpRequest, db: AsyncSession = Depends(get_db)):
    code, ttl = await auth_service.request_otp(db, body.phone)
    return RequestOtpResponse(phone=body.phone, expires_in_seconds=ttl, dev_code=code)


@router.post("/otp/verify", response_model=TokenResponse)
async def verify_otp(body: VerifyOtpRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await auth_service.verify_otp(db, body.phone, body.code)
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return TokenResponse(access_token=auth_service.issue_token(user), user_id=user.id)


@router.post("/oauth", response_model=TokenResponse)
async def oauth_login(body: OAuthLoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await auth_service.oauth_login(db, body.provider, body.id_token)
    except NotImplementedError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(exc)) from exc
    return TokenResponse(access_token=auth_service.issue_token(user), user_id=user.id)
