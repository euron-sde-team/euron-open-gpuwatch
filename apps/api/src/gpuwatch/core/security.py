"""Password hashing, dashboard sessions and bearer tokens (API keys, agent host tokens,
enrolment tokens)."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
# A real hash of a random password so unknown emails cost the same time as known ones.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

# Bearer token kinds. Each is ``<kind>_<12 hex prefix>_<secret>``; only a peppered HMAC of
# the secret is stored, the prefix is the lookup key.
API_KEY_PREFIX = "gwk"  # read-only REST API keys
HOST_TOKEN_PREFIX = "gwh"  # noqa: S105 a prefix, not a secret; one per enrolled agent host
ENROLMENT_PREFIX = "gwe"  # exchanged by an agent for a host token
SESSION_AUDIENCE = "gpuwatch-dashboard"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("at least 10 characters")
    if password.lower() == password or password.upper() == password:
        problems.append("upper and lower case letters")
    if not any(c.isdigit() for c in password):
        problems.append("a digit")
    return problems


@dataclass(frozen=True, slots=True)
class SessionClaims:
    user_id: uuid.UUID
    role: str
    session_version: int
    jti: str = ""
    expires_at: datetime | None = None


def issue_session(
    user_id: uuid.UUID, role: str, session_version: int, secret: str, ttl_hours: int
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "sv": session_version,
        "aud": SESSION_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(hours=ttl_hours),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_session(token: str, secret: str) -> SessionClaims | None:
    try:
        data = jwt.decode(token, secret, algorithms=["HS256"], audience=SESSION_AUDIENCE)
        return SessionClaims(
            uuid.UUID(data["sub"]),
            str(data["role"]),
            int(data.get("sv", 0)),
            str(data.get("jti", "")),
            datetime.fromtimestamp(int(data["exp"]), UTC),
        )
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class GeneratedKey:
    plaintext: str
    prefix: str
    secret_hash: str


def hash_key_secret(secret: str, pepper: str) -> str:
    """Peppered HMAC: a leaked database alone cannot be brute forced into usable keys."""
    return hmac.new(pepper.encode(), secret.encode(), hashlib.sha256).hexdigest()


def generate_api_key(pepper: str, kind: str = API_KEY_PREFIX) -> GeneratedKey:
    prefix = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    return GeneratedKey(
        plaintext=f"{kind}_{prefix}_{secret}",
        prefix=prefix,
        secret_hash=hash_key_secret(secret, pepper),
    )


_PREFIX_RE = re.compile(r"[0-9a-f]{12}")


def parse_api_key(raw: str, kind: str = API_KEY_PREFIX) -> tuple[str, str] | None:
    """Split ``<kind>_<prefix>_<secret>`` into (prefix, secret); None if malformed."""
    parts = raw.split("_", 2)
    if len(parts) != 3 or parts[0] != kind or not parts[2]:
        return None
    if not _PREFIX_RE.fullmatch(parts[1]):
        return None  # prefixes are 12 hex chars; anything else never reaches the cache or DB
    return parts[1], parts[2]


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
