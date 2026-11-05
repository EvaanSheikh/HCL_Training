"""Fail-closed Auth0 API token validation and caller identity helpers."""
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

# Ensure environment variables from root .env and frontend .env.local are loaded
_BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(_BASE_DIR / ".env")
load_dotenv(_BASE_DIR / "autonomous-data-analyst-web" / ".env.local")

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_jwk_set=True, lifespan=300, timeout=5)


# Cache verified opaque tokens for 60 seconds to avoid IdP rate limits and latency
_USERINFO_CACHE: dict[str, tuple[str, float]] = {}


def _fetch_userinfo(url: str, token: str) -> dict:
    """Fetch user profile from OIDC /userinfo to introspect opaque tokens."""
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "User-Agent": "NOHA-Backend/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status != 200:
                raise HTTPException(status_code=401, detail="Invalid authentication credentials.")
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials.") from None


def validate_access_token(token: str) -> Principal:
    issuer = os.getenv("AUTH0_ISSUER", "").rstrip("/") + "/"
    audience = os.getenv("AUTH0_AUDIENCE", "")
    required_scope = os.getenv("AUTH0_REQUIRED_SCOPE", "noha:access")
    jwks_url = os.getenv("AUTH0_JWKS_URL", "")
    allowed_client = os.getenv("AUTH0_ALLOWED_CLIENT_ID", "")
    if not issuer.strip("/") or not audience or not jwks_url or not allowed_client:
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    if not issuer.startswith("https://") or not jwks_url.startswith(issuer) or not jwks_url.startswith("https://"):
        raise HTTPException(status_code=503, detail="Authentication is not configured.")

    # 1. Standard 3-part JWT access token (RS256 signed with audience and scopes)
    parts = token.split(".")
    if len(parts) == 3:
        try:
            key = _jwks_client(jwks_url).get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=["RS256"], issuer=issuer,
                audience=audience, options={"require": ["iss", "sub", "aud", "exp", "iat"]},
                leeway=30,
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials.") from None
        except jwt.PyJWKClientConnectionError:
            raise HTTPException(status_code=503, detail="Authentication provider is unavailable.") from None
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials.") from None

        if required_scope not in str(claims.get("scope", "")).split():
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        if claims.get("azp") != allowed_client:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials.")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials.")
        return Principal(issuer=issuer, subject=subject)

    # 2. Opaque access token introspection via OIDC /userinfo
    # As specified in AUTH_IMPLEMENTATION_PLAN.md:
    # "For opaque access tokens use authenticated introspection instead of JWT parsing."
    now = time.time()
    cached = _USERINFO_CACHE.get(token)
    if cached and cached[1] > now:
        return Principal(issuer=issuer, subject=cached[0])

    userinfo_url = f"{issuer.rstrip('/')}/userinfo"
    userinfo = _fetch_userinfo(userinfo_url, token)
    subject = userinfo.get("sub")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials.")

    _USERINFO_CACHE[token] = (subject, now + 60.0)
    return Principal(issuer=issuer, subject=subject)


def require_principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required.", headers={"WWW-Authenticate": "Bearer"})
    return validate_access_token(credentials.credentials)


def get_user_id(principal: Principal) -> str:
    from app.storage.database import get_or_create_user
    return get_or_create_user(principal.issuer, principal.subject)
