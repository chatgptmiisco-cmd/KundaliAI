from pydantic import BaseModel, EmailStr, Field


class SignupEmailRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str
    preferred_language: str = "en"


class LoginEmailRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr
    new_password: str = Field(min_length=8)


class RequestOtpRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=20)


class RequestOtpResponse(BaseModel):
    phone: str
    expires_in_seconds: int
    dev_code: str | None = Field(
        default=None,
        description="Only populated when STT/SMS provider is a stub — never present once a real SMS provider is wired up.",
    )


class VerifyOtpRequest(BaseModel):
    phone: str
    code: str


class OAuthLoginRequest(BaseModel):
    provider: str  # "google" | "apple"
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
