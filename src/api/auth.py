"""
Logowanie przez Google OAuth2 / OIDC.

Flow:
  1. GET  /api/v1/auth/google            → redirect do Google consent
  2. GET  /api/v1/auth/google/callback   → wymiana kodu → JWT sesji
  3. GET  /api/v1/auth/me                → zwraca profil z JWT (Bearer token)
  4. POST /api/v1/auth/logout            → informacja o wylogowaniu (klient usuwa token)

JWT jest podpisywany kluczem JWT_SECRET (HS256).
Profil użytkownika zawiera: sub, email, name, picture.

Wymagania:
  - GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI
  - JWT_SECRET (min 32 znaków)

Zależności:
  - httpx (już w requirements)
  - PyJWT (dodane do requirements)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_SCOPES = "openid email profile"


# ---------------------------------------------------------------------------
# JWT helpers (używamy PyJWT; fallback na HMAC ręczny)
# ---------------------------------------------------------------------------

def _encode_jwt(payload: dict[str, Any], secret: str, algorithm: str = "HS256") -> str:
    try:
        import jwt as pyjwt
        return pyjwt.encode(payload, secret, algorithm=algorithm)
    except ImportError:
        # Fallback: base64url HS256 bez biblioteki (uproszczone – nie prod!)
        import base64
        import hashlib
        import hmac
        import json as _json

        def _b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        header = _b64url(_json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        body   = _b64url(_json.dumps(payload).encode())
        sig_input = f"{header}.{body}".encode()
        sig = _b64url(
            hmac.new(secret.encode(), sig_input, hashlib.sha256).digest()
        )
        return f"{header}.{body}.{sig}"


def _decode_jwt(token: str, secret: str, algorithm: str = "HS256") -> dict[str, Any]:
    try:
        import jwt as pyjwt
        return pyjwt.decode(token, secret, algorithms=[algorithm])
    except ImportError:
        import base64
        import hashlib
        import hmac
        import json as _json

        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Nieprawidłowy format JWT.")
        header_b64, body_b64, sig_b64 = parts
        sig_input = f"{header_b64}.{body_b64}".encode()
        expected = (
            base64.urlsafe_b64encode(
                hmac.new(secret.encode(), sig_input, __import__("hashlib").sha256).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        if sig_b64 != expected:
            raise ValueError("Nieprawidłowy podpis JWT.")
        padding = 4 - len(body_b64) % 4
        body_bytes = base64.urlsafe_b64decode(body_b64 + "=" * padding)
        return _json.loads(body_bytes)


# ---------------------------------------------------------------------------
# GoogleAuthService
# ---------------------------------------------------------------------------

class GoogleAuthService:
    """
    Obsługuje Google OAuth2 OIDC.

    Może działać bez GOOGLE_CLIENT_ID (tryb demo – zwraca mock profil),
    co pozwala testować bez prawdziwych poświadczeń.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        jwt_secret: str,
        jwt_algorithm: str = "HS256",
        jwt_expire_minutes: int = 60,
    ) -> None:
        self.client_id          = client_id
        self.client_secret      = client_secret
        self.redirect_uri       = redirect_uri
        self.jwt_secret         = jwt_secret
        self.jwt_algorithm      = jwt_algorithm
        self.jwt_expire_minutes = jwt_expire_minutes

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # ── Krok 1: generuj URL do Google ──────────────────────────────────────

    def get_authorization_url(self, state: str = "") -> str:
        params: dict[str, str] = {
            "client_id":     self.client_id,
            "redirect_uri":  self.redirect_uri,
            "response_type": "code",
            "scope":         _SCOPES,
            "access_type":   "online",
        }
        if state:
            params["state"] = state
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    # ── Krok 2: wymień kod na token ─────────────────────────────────────────

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Wymienia authorization_code na access_token + id_token."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code":          code,
                    "client_id":     self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri":  self.redirect_uri,
                    "grant_type":    "authorization_code",
                },
                timeout=10.0,
            )
        resp.raise_for_status()
        return resp.json()

    # ── Krok 3: pobierz profil ──────────────────────────────────────────────

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Pobiera profil użytkownika z Google UserInfo endpoint."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
        resp.raise_for_status()
        return resp.json()

    # ── Krok 4: generuj JWT sesji ───────────────────────────────────────────

    def create_session_jwt(self, user_info: dict[str, Any]) -> str:
        """Tworzy podpisany JWT z danymi użytkownika."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub":     user_info.get("sub", ""),
            "email":   user_info.get("email", ""),
            "name":    user_info.get("name", ""),
            "picture": user_info.get("picture", ""),
            "iat":     int(now.timestamp()),
            "exp":     int((now + timedelta(minutes=self.jwt_expire_minutes)).timestamp()),
        }
        return _encode_jwt(payload, self.jwt_secret, self.jwt_algorithm)

    # ── Weryfikacja JWT ─────────────────────────────────────────────────────

    def verify_session_jwt(self, token: str) -> dict[str, Any]:
        """Weryfikuje i dekoduje JWT. Rzuca ValueError przy błędzie."""
        try:
            payload = _decode_jwt(token, self.jwt_secret, self.jwt_algorithm)
        except Exception as exc:
            raise ValueError(f"Nieprawidłowy JWT: {exc}") from exc
        # Sprawdź wygaśnięcie (dla fallback bez PyJWT)
        exp = payload.get("exp", 0)
        now = int(datetime.now(timezone.utc).timestamp())
        if exp and now > exp:
            raise ValueError("JWT wygasł.")
        return payload

    # ── Demo (brak konfiguracji) ────────────────────────────────────────────

    def get_demo_token(self, email: str = "demo@czlowiek-roku.local") -> str:
        """Zwraca token demo dla środowisk bez prawdziwych poświadczeń Google."""
        user_info = {
            "sub":     "demo-user-001",
            "email":   email,
            "name":    "Demo User",
            "picture": "",
        }
        return self.create_session_jwt(user_info)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

def get_google_auth_service() -> GoogleAuthService:
    from src.config.settings import settings
    return GoogleAuthService(
        client_id          = settings.google_client_id,
        client_secret      = settings.google_client_secret,
        redirect_uri       = settings.google_redirect_uri,
        jwt_secret         = settings.jwt_secret,
        jwt_algorithm      = settings.jwt_algorithm,
        jwt_expire_minutes = settings.jwt_expire_minutes,
    )
