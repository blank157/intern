"""Supabase JWT verification for API requests.

Supabase issues HS256 tokens (legacy projects, signed with the project's JWT
secret) or RS256 tokens (asymmetric keys published via JWKS). This verifier
supports both: it tries the project JWKS first and falls back to the shared
secret. Identity is ALWAYS derived from a verified token - never from request
payloads.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
import jwt
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

logger = logging.getLogger(__name__)

_JWKS_CACHE_TTL_SECONDS = 3600

# alg header -> allowed verification algorithms
_ALGORITHMS = {
    "RS256": ["RS256"],
    "RS384": ["RS384"],
    "RS512": ["RS512"],
    "ES256": ["ES256"],
    "HS256": ["HS256"],
}


class AuthError(Exception):
    """Raised when a bearer token cannot be trusted."""


class SupabaseJWTVerifier:
    def __init__(
        self,
        supabase_url: str = "",
        jwt_secret: str = "",
        *,
        jwks_url: str | None = None,
        jwks_ttl_seconds: int = _JWKS_CACHE_TTL_SECONDS,
        leeway_seconds: int = 30,
    ) -> None:
        self._supabase_url = (supabase_url or "").rstrip("/")
        self._jwt_secret = jwt_secret
        self._jwks_url = (
            jwks_url
            or (f"{self._supabase_url}/auth/v1/.well-known/jwks.json" if self._supabase_url else "")
        )
        self._jwks_ttl = jwks_ttl_seconds
        self._leeway = leeway_seconds
        self._jwks_keys: dict[str, Any] = {}
        self._jwks_fetched_at: float = 0.0

    # -- public ------------------------------------------------------------

    def verify(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:  # noqa: BLE001 - normalize library errors
            raise AuthError(f"Malformed token header: {exc}") from exc

        algorithm = header.get("alg", "")
        if algorithm in ("RS256", "RS384", "RS512", "ES256"):
            key = self._asymmetric_key(header.get("kid"))
            claims = self._decode(token, key=key, algorithms=_ALGORITHMS[algorithm], leeway=self._leeway)
        elif algorithm == "HS256":
            if not self._jwt_secret:
                raise AuthError("HS256 token rejected: SUPABASE_JWT_SECRET not configured")
            claims = self._decode(token, key=self._jwt_secret, algorithms=["HS256"], leeway=self._leeway)
        else:
            raise AuthError(f"Unsupported token algorithm '{algorithm}'")

        subject = claims.get("sub")
        if not subject:
            raise AuthError("Token has no 'sub' claim")
        return claims

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _decode(token: str, *, key: Any, algorithms: list[str], leeway: int = 0) -> dict[str, Any]:
        try:
            return jwt.decode(
                token,
                key=key,
                algorithms=algorithms,
                options={"verify_aud": False},
                leeway=leeway,
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("Token expired") from exc
        except jwt.PyJWTError as exc:  # noqa: BLE001
            raise AuthError(f"Invalid token: {exc}") from exc

    def _asymmetric_key(self, kid: str | None) -> Any:
        if not self._jwks_url:
            raise AuthError("Asymmetric token rejected: SUPABASE_URL not configured")
        keys = self._get_jwks()
        if kid is None or kid not in keys:
            raise AuthError("No JWKS signing key matches token 'kid'")
        return keys[kid]

    def _get_jwks(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._jwks_keys and now - self._jwks_fetched_at < self._jwks_ttl:
            return self._jwks_keys
        try:
            raw = self._fetch_jwks(self._jwks_url)
            try:
                documents = raw.get("keys", [])
            except AttributeError as exc:
                raise AuthError("JWKS endpoint returned invalid payload") from exc
            parsed: dict[str, Any] = {}
            for document in documents:
                kid = document.get("kid")
                if not kid:
                    continue
                key_type = document.get("kty")
                if key_type == "RSA":
                    parsed[kid] = RSAAlgorithm.from_jwk(json.dumps(document))
                elif key_type == "EC":
                    parsed[kid] = ECAlgorithm.from_jwk(json.dumps(document))
                else:
                    logger.warning("Skipping JWKS key %s with unsupported kty=%s", kid, key_type)
            self._jwks_keys = parsed
            self._jwks_fetched_at = now
            return parsed
        except AuthError:
            # Transient network problems should not hard-fail auth while a
            # previously fetched key set is available (keys rotate rarely).
            if self._jwks_keys:
                logger.warning("Using stale JWKS cache after fetch failure")
                return self._jwks_keys
            raise

    def _fetch_jwks(self, url: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = httpx.get(url, timeout=15.0)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                logger.warning("JWKS fetch attempt %d failed for %s: %s", attempt + 1, url, exc)
        raise AuthError("Unable to fetch Supabase JWKS") from last_error
