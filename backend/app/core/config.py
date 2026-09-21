"""Application settings, loaded from environment variables / .env file.

Nothing here should be imported for its side effects — `get_settings()` is
cached so the environment is only read once per process.
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "KundaliAI Backend"
    environment: Literal["dev", "test", "prod"] = "dev"
    api_v1_prefix: str = "/api/v1"

    # Database. Defaults to a local SQLite file so the backend runs with zero
    # setup; point DATABASE_URL at Postgres (asyncpg) in any real deployment —
    # the SQLAlchemy models make no SQLite-specific assumptions.
    database_url: str = "sqlite+aiosqlite:///./kundaliai.db"
    sql_echo: bool = False

    # Auth
    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Field-level encryption for PII (birth data). Must be a valid Fernet key
    # (32 url-safe base64-encoded bytes). Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # This default is a valid Fernet key so the app runs out of the box in
    # dev, but it is PUBLIC (checked into source) — never use it in any real
    # deployment. Override via env var, generated with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    pii_encryption_key: str = "2llRqH9W5eM8KcuMH4PLPoaF945mietzNdVHwbDothE="

    # LLM (Anthropic Claude). Astrology itself is fixed, deterministic
    # calculation (Swiss Ephemeris + classical rules) — every chart, dasha,
    # Manglik, and Guna Milan number in this app is computed, never guessed
    # by a model. The only thing an LLM could ever contribute is turning
    # those numbers into prose, and even that stays OFF by default: setting
    # ANTHROPIC_API_KEY alone is not enough, use_ai_interpretation must also
    # be explicitly set to true. Until then, app.services.interpretation
    # .templates.TemplateInterpreter (pure Python, no network call) is what
    # renders every explanation, and it's what get_interpreter() returns.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    # OpenAI is preferred over Claude when both keys are set (see
    # app.services.interpretation.factory.get_interpreter) — gpt-4o-mini is
    # the default for cost, since chat now makes two small calls per message
    # (understand the question, then explain the real computed answer)
    # rather than one big one.
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    use_ai_interpretation: bool = False

    # Birth-place search (Google Places API) — proxied through this backend
    # (see app.services.geocoding_service) rather than called directly from
    # the app, so the key never ships inside the mobile bundle where it
    # could be extracted and reused to run up billing on this project's
    # Google account. Leave unset and the frontend falls back to its own
    # offline city table + OpenStreetMap Nominatim (see src/data/geocoding.ts).
    google_places_api_key: str | None = None

    # Every subscription-gated feature (D9/D10 charts, unlimited period
    # analyses, real AI chat, voice narration) is unlocked for every tier
    # while pricing isn't live yet — see app.api.deps.require_tier and
    # app.services.analysis_service's free-quota check, both of which read
    # this flag. The subscription/tier machinery itself is untouched (still
    # tracked, still switchable in the UI) so flipping this back to false is
    # the only change needed to turn paywalls back on later.
    all_features_free: bool = True

    # Payments (Razorpay). If unset, the payments layer runs in simulate mode:
    # "checkout" always succeeds locally without calling Razorpay at all.
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None

    # Voice (STT/TTS). Stub providers ship by default; see app/services/voice.
    # "openai" reuses openai_api_key above — no separate key needed. The
    # whisper-1 is the default since it's available on every OpenAI project
    # without extra enablement — gpt-4o-mini-transcribe is cheaper/newer but
    # gated behind per-project access, so it's opt-in via STT_MODEL instead.
    stt_provider: Literal["stub", "openai", "google", "azure", "aws"] = "stub"
    stt_model: str = "whisper-1"
    tts_provider: Literal["stub", "google", "azure", "aws"] = "stub"

    # Free-tier quotas
    free_monthly_period_analyses: int = 3

    # CORS
    cors_allow_origins: list[str] = ["*"]

    # Rate limiting (requests per minute per client) for expensive endpoints
    rate_limit_calc: str = "30/minute"
    rate_limit_llm: str = "10/minute"
    rate_limit_voice: str = "10/minute"


@lru_cache
def get_settings() -> Settings:
    return Settings()
