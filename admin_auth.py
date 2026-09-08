"""
admin_auth.py

JWT protection for admin.

Credentials from .env
ADMIN_USERNAME, ADMIN_PASSWORD - Admin login
JWT_SECRET                     - Signs token

"""

import hmac
import os
import time

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

TOKEN_TTL_SECONDS = 60 * 60
ALGORITHM = "HS256"

_bearer = HTTPBearer(auto_error=False)


def _secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="Admin auth not set up")
    return secret


def check_credentials(username: str, password: str) -> bool:
    expected_user = os.environ.get("ADMIN_USERNAME", "")
    expected_pass = os.environ.get("ADMIN_PASSWORD", "")

    if not expected_user or not expected_pass:
        return False

    return hmac.compare_digest(username, expected_user) and hmac.compare_digest(
        password, expected_pass
    )


def issue_token(username: str) -> tuple[str, int]:
    """Return (token, expires_in_seconds)"""
    now = int(time.time())
    payload = {"sub": username, "iat": now, "exp": now + TOKEN_TTL_SECONDS}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM), TOKEN_TTL_SECONDS


def require_admin(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    """FastAPI dependency: returns admin username or 401"""
    if creds is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        payload = jwt.decode(creds.credentials, _secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload["sub"]
