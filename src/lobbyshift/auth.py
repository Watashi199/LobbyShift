"""Authentication: one admin password (scrypt) + signed session cookie,
and a bearer token for the local CLI.

The cookie is HttpOnly and SameSite=Strict, and unsafe requests must come
from the same origin, which closes the CSRF hole of v1 (any web page could
POST to the gateway from a LAN browser).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from .store import Store

log = logging.getLogger(__name__)

COOKIE_NAME = "lobbyshift_session"
SESSION_TTL = 30 * 86400
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
_MAX_FAILURES = 5
_LOCKOUT_SECONDS = 60


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    b64 = base64.b64encode
    return f"scrypt${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    salt, expected = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=len(expected), **_SCRYPT)
    return hmac.compare_digest(digest, expected)


@dataclass
class _Throttle:
    failures: dict[str, list[float]] = field(default_factory=dict)

    def blocked(self, client: str) -> bool:
        recent = [t for t in self.failures.get(client, []) if time.monotonic() - t < _LOCKOUT_SECONDS]
        self.failures[client] = recent
        return len(recent) >= _MAX_FAILURES

    def fail(self, client: str) -> None:
        self.failures.setdefault(client, []).append(time.monotonic())

    def reset(self, client: str) -> None:
        self.failures.pop(client, None)


class Auth:
    def __init__(self, store: Store, token_file: Path):
        self.store = store
        self.token_file = token_file
        self.throttle = _Throttle()

    # -- bootstrap ---------------------------------------------------------

    def ensure_initialized(self, seed_password: str = "") -> str | None:
        """Create secrets on first start. Returns a generated password, if any."""
        if not self.store.get("session_secret"):
            self.store.set("session_secret", secrets.token_hex(32))
        if not self.store.get("api_token"):
            self.store.set("api_token", secrets.token_urlsafe(32))
        self._write_token_file()

        generated = None
        if not self.store.get("password_hash"):
            password = seed_password or secrets.token_urlsafe(9)
            self.store.set("password_hash", hash_password(password))
            if not seed_password:
                generated = password
        return generated

    def _write_token_file(self) -> None:
        try:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.token_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(self.store.get("api_token"))
        except OSError as e:
            log.warning("Cannot write CLI token file %s: %s", self.token_file, e)

    def set_password(self, password: str) -> None:
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        self.store.set("password_hash", hash_password(password))
        # Rotating the secret signs everyone out.
        self.store.set("session_secret", secrets.token_hex(32))

    # -- login / sessions --------------------------------------------------

    def login(self, password: str, client: str) -> str | None:
        if self.throttle.blocked(client):
            raise PermissionError("Too many attempts, retry in a minute")
        stored = self.store.get("password_hash", "")
        if not verify_password(password, stored):
            self.throttle.fail(client)
            return None
        self.throttle.reset(client)
        return self._sign(int(time.time()) + SESSION_TTL)

    def _sign(self, expires: int) -> str:
        secret = self.store.get("session_secret", "").encode()
        mac = hmac.new(secret, str(expires).encode(), hashlib.sha256).hexdigest()
        return f"{expires}.{mac}"

    def valid_session(self, cookie: str | None) -> bool:
        if not cookie or "." not in cookie:
            return False
        expires_s, _ = cookie.split(".", 1)
        if not expires_s.isdigit() or int(expires_s) < time.time():
            return False
        return hmac.compare_digest(self._sign(int(expires_s)), cookie)

    def valid_token(self, header: str | None) -> bool:
        if not header or not header.lower().startswith("bearer "):
            return False
        token = self.store.get("api_token", "")
        return bool(token) and hmac.compare_digest(header[7:].strip(), token)
