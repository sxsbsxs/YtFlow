from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any


COOKIE_NAME = "ytflow_session"


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class AuthConfig:
    admin_username: str
    admin_password: str
    secret_key: str
    session_ttl_seconds: int = 86400
    cookie_secure: bool = True

    @classmethod
    def from_env(cls) -> "AuthConfig":
        username = os.getenv("YTFLOW_ADMIN_USERNAME", "").strip()
        password = os.getenv("YTFLOW_ADMIN_PASSWORD", "")
        secret = os.getenv("YTFLOW_SECRET_KEY", "")
        if not username:
            raise RuntimeError("YTFLOW_ADMIN_USERNAME is required. Copy .env.example to .env and configure it.")
        if len(password) < 12 or password.startswith("CHANGE_THIS"):
            raise RuntimeError("Set a unique YTFLOW_ADMIN_PASSWORD of at least 12 characters in .env; the example placeholder is not accepted.")
        if len(secret) < 32 or secret.startswith("REPLACE_WITH"):
            raise RuntimeError("Set YTFLOW_SECRET_KEY to a random value of at least 32 characters. Generate one with: openssl rand -hex 32")
        try:
            ttl = int(os.getenv("YTFLOW_SESSION_TTL_SECONDS", "86400"))
        except ValueError as exc:
            raise RuntimeError("YTFLOW_SESSION_TTL_SECONDS must be an integer.") from exc
        if not 300 <= ttl <= 604800:
            raise RuntimeError("YTFLOW_SESSION_TTL_SECONDS must be between 300 and 604800.")
        cookie_secure = os.getenv("YTFLOW_COOKIE_SECURE", "true").strip().lower() not in {"0", "false", "no", "off"}
        return cls(
            admin_username=username,
            admin_password=password,
            secret_key=secret,
            session_ttl_seconds=ttl,
            cookie_secure=cookie_secure,
        )


class SessionAuth:
    """Small signed-cookie session manager; no session state is stored in the browser."""

    def __init__(self, config: AuthConfig) -> None:
        self.config = config
        self._key = config.secret_key.encode("utf-8")

    def verify_credentials(self, username: str, password: str) -> bool:
        username_ok = secrets.compare_digest(username.encode("utf-8"), self.config.admin_username.encode("utf-8"))
        password_ok = secrets.compare_digest(password.encode("utf-8"), self.config.admin_password.encode("utf-8"))
        return username_ok and password_ok

    def issue(self, username: str | None = None, now: int | None = None) -> tuple[str, str]:
        issued_at = int(time.time() if now is None else now)
        csrf_token = secrets.token_urlsafe(32)
        payload = {
            "sub": username or self.config.admin_username,
            "iat": issued_at,
            "exp": issued_at + self.config.session_ttl_seconds,
            "csrf": csrf_token,
        }
        encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signature = _b64encode(hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).digest())
        return f"{encoded}.{signature}", csrf_token

    def read(self, token: str | None, now: int | None = None) -> dict[str, Any] | None:
        if not token or "." not in token:
            return None
        encoded, supplied_signature = token.rsplit(".", 1)
        expected_signature = _b64encode(hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).digest())
        if not secrets.compare_digest(supplied_signature, expected_signature):
            return None
        try:
            payload = json.loads(_b64decode(encoded))
            current = int(time.time() if now is None else now)
            if payload.get("sub") != self.config.admin_username:
                return None
            if not isinstance(payload.get("exp"), int) or payload["exp"] <= current:
                return None
            if not isinstance(payload.get("csrf"), str) or len(payload["csrf"]) < 32:
                return None
            return payload
        except (ValueError, TypeError, json.JSONDecodeError):
            return None

    @classmethod
    def from_env(cls) -> "SessionAuth":
        return cls(AuthConfig.from_env())
