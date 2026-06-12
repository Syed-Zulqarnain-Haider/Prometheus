"""Authentication primitives: Firebase token verification.

The verifier is exposed as a FastAPI dependency so it can be swapped for a fake
in tests (no network, no real Firebase project needed).
"""

from __future__ import annotations

from typing import Any, Protocol

import firebase_admin
from fastapi.security import HTTPBearer
from firebase_admin import auth as firebase_auth


class InvalidTokenError(Exception):
    """Raised when a bearer token cannot be verified."""


class TokenVerifier(Protocol):
    """Verifies a bearer token and returns its decoded claims."""

    def verify(self, token: str) -> dict[str, Any]: ...


class FirebaseTokenVerifier:
    """Verifies Firebase ID tokens via firebase-admin."""

    def verify(self, token: str) -> dict[str, Any]:
        # Initialize the default app lazily using Application Default Credentials
        # (GOOGLE_APPLICATION_CREDENTIALS / Workload Identity in production).
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        try:
            claims: dict[str, Any] = firebase_auth.verify_id_token(token)
        except Exception as exc:  # noqa: BLE001 — any verification failure → 401
            raise InvalidTokenError(str(exc)) from exc
        return claims


# auto_error=False so we return our own 401 envelope for missing credentials.
bearer_scheme = HTTPBearer(auto_error=False)


def get_token_verifier() -> TokenVerifier:
    """FastAPI dependency returning the active token verifier."""
    return FirebaseTokenVerifier()
