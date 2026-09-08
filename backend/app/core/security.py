"""Password hashing, JWT issuance/verification, and field-level PII encryption.

Kept separate from business logic so auth/crypto primitives have one obvious
home and can be audited in one place.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

from app.core.config import get_settings

# Using the `bcrypt` package directly rather than passlib's CryptContext:
# passlib 1.7.4 (unmaintained since 2020) has a known incompatibility with
# bcrypt>=4 where its internal self-test raises ValueError on import. bcrypt
# truncates the input to 72 bytes itself; there is no need to pre-truncate.
_BCRYPT_MAX_BYTES = 72


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


class PiiCipher:
    """Symmetric field-level encryption for PII (birth data) at rest.

    Uses Fernet (AES-128-CBC + HMAC) — appropriate for encrypting individual
    small fields rather than whole-database encryption, which is a deployment
    concern (e.g. Postgres TDE / disk encryption) handled outside the app.
    """

    def __init__(self, key: str):
        self._fernet = Fernet(key.encode("utf-8"))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Could not decrypt PII field — wrong key or corrupted data") from exc


_cipher: PiiCipher | None = None


def get_pii_cipher() -> PiiCipher:
    global _cipher
    if _cipher is None:
        _cipher = PiiCipher(get_settings().pii_encryption_key)
    return _cipher
