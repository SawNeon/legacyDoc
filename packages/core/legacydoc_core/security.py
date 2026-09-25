"""Passwords, JWT tokens and API keys."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from legacydoc_core.errors import AuthenticationError, ValidationError
from legacydoc_core.settings import Settings

_password_hash = PasswordHash.recommended()

API_KEY_PREFIX = "ldk_"
_API_KEY_LOOKUP_LEN = 12


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> str:
    normalized = normalize_email(email)
    local, _, domain = normalized.partition("@")

    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValidationError("E-mail invalido.")

    return normalized


def validate_password_strength(password: str, min_length: int) -> None:
    if len(password) < min_length:
        raise ValidationError(f"A senha deve ter pelo menos {min_length} caracteres.")

    if password.isdigit() or password.isalpha():
        raise ValidationError("A senha deve misturar letras e numeros.")


@dataclass(frozen=True)
class TokenPayload:
    user_id: str
    email: str


def create_access_token(user_id: str, email: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
        "typ": "access",
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: Settings) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token expirado.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Token invalido.") from exc

    user_id = payload.get("sub")
    email = payload.get("email")

    if not user_id or not email:
        raise AuthenticationError("Token incompleto.")

    return TokenPayload(user_id=user_id, email=email)


@dataclass(frozen=True)
class GeneratedApiKey:
    plaintext: str
    prefix: str
    key_hash: str


def generate_api_key() -> GeneratedApiKey:
    secret = secrets.token_urlsafe(32)
    plaintext = f"{API_KEY_PREFIX}{secret}"

    return GeneratedApiKey(
        plaintext=plaintext,
        prefix=plaintext[:_API_KEY_LOOKUP_LEN],
        key_hash=hash_api_key(plaintext),
    )


def hash_api_key(plaintext: str) -> str:
    """SHA-256 rather than argon2."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def api_key_lookup_prefix(plaintext: str) -> str:
    return plaintext[:_API_KEY_LOOKUP_LEN]


def api_key_matches(plaintext: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(plaintext), stored_hash)


def looks_like_api_key(credential: str) -> bool:
    return credential.startswith(API_KEY_PREFIX)


MAX_FAILED_LOGINS = 5

LOCKOUT_MINUTES = 15


def lockout_until(failed_attempts: int) -> datetime | None:
    """How long the account stays locked, given consecutive failures."""
    if failed_attempts < MAX_FAILED_LOGINS:
        return None

    excedentes = failed_attempts - MAX_FAILED_LOGINS
    minutos = min(LOCKOUT_MINUTES * (2**excedentes), 24 * 60)

    return datetime.now(UTC) + timedelta(minutes=minutos)


def is_locked(locked_until_value: datetime | None) -> bool:
    if locked_until_value is None:
        return False

    referencia = (
        locked_until_value if locked_until_value.tzinfo else locked_until_value.replace(tzinfo=UTC)
    )

    return referencia > datetime.now(UTC)


RESET_TOKEN_TTL_MINUTES = 30


@dataclass(frozen=True)
class GeneratedResetToken:
    plaintext: str
    token_hash: str
    expires_at: datetime


def generate_reset_token() -> GeneratedResetToken:
    plaintext = secrets.token_urlsafe(32)

    return GeneratedResetToken(
        plaintext=plaintext,
        token_hash=hash_reset_token(plaintext),
        expires_at=datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),
    )


def hash_reset_token(plaintext: str) -> str:
    """SHA-256, as with API keys: 256 bits of entropy do not need argon2."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def reset_token_matches(plaintext: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_reset_token(plaintext), stored_hash)
