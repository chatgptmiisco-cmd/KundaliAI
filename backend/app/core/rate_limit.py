"""Rate limiting for expensive endpoints (astrology calculations, LLM calls,
voice synthesis/transcription). Keyed by authenticated user id when available,
falling back to client IP for unauthenticated endpoints.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _rate_limit_key(request: Request) -> str:
    user = getattr(request.state, "user_id", None)
    return f"user:{user}" if user else f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_rate_limit_key)
