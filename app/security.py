"""Password hashing and JWT creation/verification.

Two separate jobs live here:

  * turning a password into a hash that cannot be reversed
  * issuing and reading signed tokens that prove who a request belongs to
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from app import config


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a password with bcrypt.

    bcrypt is used rather than a plain hash like SHA-256 for two reasons:

      * it is deliberately slow, so guessing billions of candidates is
        impractical
      * it salts every hash automatically, so two users with the same password
        get different stored values and one cracked hash reveals nothing about
        the other

    The 72-byte truncation is bcrypt's own limit: anything past 72 bytes is
    ignored. Passwords are cut here explicitly so the behaviour is visible
    rather than silent, and PASSWORD_MAX keeps requests near that boundary.
    """
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Check a password against a stored hash.

    bcrypt.checkpw compares in constant time, so the comparison itself does not
    leak how much of the hash matched.

    A malformed or truncated hash makes bcrypt raise, which would surface as a
    500 during login; returning False instead treats an unreadable hash as a
    failed attempt.
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def create_access_token(user_id: int, email: str) -> str:
    """Create a signed JWT identifying one user.

    The payload holds:

        sub    the user id, as a string (the JWT spec expects a string subject)
        email  convenience for logging and debugging
        exp    expiry, so a stolen token stops working
        iat    issued-at

    Nothing secret goes in here. A JWT is signed, not encrypted — anyone holding
    it can read the payload. The signature only proves it has not been altered.
    """
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES),
    }

    return jwt.encode(payload, config.SECRET_KEY, algorithm=config.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Verify a token and return its payload, or None if it is not usable.

    jwt.decode checks the signature and the expiry, raising on failure. Every
    failure is treated the same way — an invalid signature, an expired token and
    a malformed string all return None — so the caller cannot accidentally leak
    which one it was in an error message.
    """
    try:
        return jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
    except jwt.PyJWTError:
        return None
