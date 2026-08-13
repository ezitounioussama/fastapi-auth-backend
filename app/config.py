"""Settings, read from the environment with sensible defaults for local work."""

import os
import secrets
import sys

from dotenv import load_dotenv

load_dotenv()

APP_NAME = "AI Study Assistant API"
APP_VERSION = "2.0.0"

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# The signing key. Anyone holding it can mint tokens for any account, so it must
# come from the environment in production and never be committed.
#
# For local development a random key is generated at startup when none is set.
# That is deliberately inconvenient: it changes on every restart, which
# invalidates old tokens and makes the missing setting obvious, rather than
# quietly shipping a hard-coded secret that ends up in production.
SECRET_KEY = os.getenv("SECRET_KEY", "")

if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(32)
    # Printed to stderr so it shows up when running the server but does not
    # pollute JSON output from scripts.
    print(
        "WARNING: SECRET_KEY is not set, so a random one was generated for this "
        "run.\n         Tokens will stop working when the server restarts. Set "
        "SECRET_KEY in .env\n         for anything beyond local experiments.",
        file=sys.stderr,
    )

# --------------------------------------------------------------------------
# Validation limits
# --------------------------------------------------------------------------
PASSWORD_MIN = 8
PASSWORD_MAX = 128  # bcrypt only reads the first 72 bytes; see security.py

TITLE_MIN = 1
TITLE_MAX = 120

MESSAGE_MIN = 1
MESSAGE_MAX = 2000

# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))
