"""Errors, validation helpers, password hashing, signed tokens, rate limiting."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque

from . import config


class ApiError(Exception):
    def __init__(self, status, code, message, fields=None, headers=None):
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields or {}
        self.headers = headers or {}

    def payload(self):
        out = {"error": {"code": self.code, "message": self.message}}
        if self.fields:
            out["error"]["fields"] = self.fields
        return out


def bad(message, field=None, code="validation_error"):
    return ApiError(422, code, message, {field: message} if field else None)


def new_id(prefix=""):
    return prefix + uuid.uuid4().hex[:16]


def now_ts() -> int:
    return int(time.time())


# ---------------------------------------------------------------- validation
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9 .\-]{9,18}$")


class Validator:
    """Tiny schema helper: collects every field error, then raises once."""

    def __init__(self, data):
        if not isinstance(data, dict):
            raise ApiError(400, "bad_request", "Corpul cererii trebuie să fie un obiect JSON.")
        self.data, self.errors, self.clean = data, {}, {}

    def _fail(self, field, msg):
        self.errors.setdefault(field, msg)

    def text(self, field, *, min=0, max=500, required=True, label=None):
        label = label or field
        val = self.data.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            if required:
                self._fail(field, f"{label} este obligatoriu.")
            self.clean[field] = None
            return None
        if not isinstance(val, str):
            self._fail(field, f"{label} trebuie să fie text.")
            return None
        val = " ".join(val.split()) if max <= 200 else val.strip()
        if len(val) < min:
            self._fail(field, f"{label} trebuie să aibă minim {min} caractere.")
        elif len(val) > max:
            self._fail(field, f"{label} trebuie să aibă maxim {max} caractere.")
        self.clean[field] = val
        return val

    def email(self, field="email"):
        val = self.text(field, max=254, label="Emailul")
        if val and not EMAIL_RE.match(val):
            self._fail(field, "Adresa de email nu este validă.")
        if val:
            self.clean[field] = val.lower()
        return self.clean.get(field)

    def phone(self, field="phone", required=False, label="Telefonul"):
        val = self.text(field, max=20, required=required, label=label)
        if val and not PHONE_RE.match(val):
            self._fail(field, "Numărul de telefon nu este valid.")
        return val

    def password(self, field="password", enforce=True):
        val = self.data.get(field)
        if not isinstance(val, str) or not val:
            self._fail(field, "Parola este obligatorie.")
            return None
        if enforce:
            if len(val) < 8 or len(val) > 128:
                self._fail(field, "Parola trebuie să aibă între 8 și 128 de caractere.")
            elif not (re.search(r"[A-Za-z]", val) and re.search(r"\d", val)):
                self._fail(field, "Parola trebuie să conțină litere și cifre.")
        self.clean[field] = val
        return val

    def integer(self, field, *, min=None, max=None, required=True, label=None):
        label = label or field
        val = self.data.get(field)
        if val is None or val == "":
            if required:
                self._fail(field, f"{label} este obligatoriu.")
            return None
        try:
            if isinstance(val, bool):
                raise ValueError
            num = int(float(val)) if not isinstance(val, int) else val
        except (TypeError, ValueError):
            self._fail(field, f"{label} trebuie să fie un număr.")
            return None
        if min is not None and num < min:
            self._fail(field, f"{label} trebuie să fie cel puțin {min}.")
        if max is not None and num > max:
            self._fail(field, f"{label} trebuie să fie cel mult {max}.")
        self.clean[field] = num
        return num

    def choice(self, field, options, required=True, label=None):
        val = self.data.get(field)
        if val is None and not required:
            return None
        if val not in options:
            self._fail(field, f"{label or field} are o valoare nepermisă.")
            return None
        self.clean[field] = val
        return val

    def done(self):
        if self.errors:
            raise ApiError(422, "validation_error", "Datele introduse nu sunt valide.", self.errors)
        return self.clean


# ------------------------------------------------------------------ passwords
_ITER = 210_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


# --------------------------------------------------------------------- tokens
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(user_id: str, role: str, token_version: int, secret: bytes) -> str:
    payload = {"sub": user_id, "role": role, "tv": token_version,
               "iat": now_ts(), "exp": now_ts() + config.TOKEN_TTL_SECONDS}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str, secret: bytes, previous_secret: bytes | None = None) -> dict:
    try:
        body, sig = token.split(".")
        expected = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
        valid = hmac.compare_digest(sig, expected)
        if not valid and previous_secret:
            expected_prev = _b64(hmac.new(previous_secret, body.encode(), hashlib.sha256).digest())
            valid = hmac.compare_digest(sig, expected_prev)
        if not valid:
            raise ValueError
        payload = json.loads(_unb64(body))
    except Exception:
        raise ApiError(401, "invalid_token", "Sesiune invalidă. Conectează-te din nou.")
    if payload.get("exp", 0) < now_ts():
        raise ApiError(401, "token_expired", "Sesiunea a expirat. Conectează-te din nou.")
    return payload


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --------------------------------------------------------------- rate limiting
class RateLimiter:
    """Sliding-window limiter (in-memory; swap for Redis when scaling out)."""

    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str, limit: int, window: int, message=None) -> int:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                retry = int(window - (now - q[0])) + 1
                raise ApiError(
                    429,
                    "rate_limited",
                    message or f"Prea multe încercări. Reîncearcă în {retry} secunde.",
                    headers={"Retry-After": str(retry), "X-RateLimit-Remaining": "0"},
                )
            q.append(now)
            return max(0, limit - len(q))

    def reset(self, key: str):
        with self.lock:
            self.hits.pop(key, None)
