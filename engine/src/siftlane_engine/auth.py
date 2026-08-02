from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from .models import UserRecord, UserRole


PASSWORD_ITERATIONS = 310_000
LOCAL_USER_ID = "local-operator"


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.urlsafe_b64decode(salt.encode("ascii")),
            int(iterations),
        )
        expected_bytes = base64.urlsafe_b64decode(expected.encode("ascii"))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected_bytes)


def issue_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


DUMMY_PASSWORD_HASH = hash_password("siftlane-invalid-password")


@dataclass(frozen=True, slots=True)
class Principal:
    user: UserRecord
    auth_mode: str
    session_id: str | None = None

    @property
    def id(self) -> str:
        return self.user.id

    @property
    def username(self) -> str:
        return self.user.username

    @property
    def role(self) -> UserRole:
        return self.user.role


class LoginLimiter:
    def __init__(self, *, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def retry_after(self, key: str) -> int:
        async with self._lock:
            attempts = self._active_attempts(key)
            if len(attempts) < self.max_attempts:
                return 0
            return max(1, int(self.window_seconds - (time.monotonic() - attempts[0])))

    async def record_failure(self, key: str) -> None:
        async with self._lock:
            attempts = self._active_attempts(key)
            attempts.append(time.monotonic())

    async def reset(self, key: str) -> None:
        async with self._lock:
            self._attempts.pop(key, None)

    def _active_attempts(self, key: str) -> deque[float]:
        attempts = self._attempts[key]
        cutoff = time.monotonic() - self.window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        return attempts
