"""Runtime configuration (environment driven, Dual-Mode Live + Sandbox defaults).
Includes secret key rotation, spend caps & billing alert thresholds, custom domain/SSL,
email authentication (SPF/DKIM/DMARC), and staging/production environment isolation.
"""
from __future__ import annotations

import os
import secrets
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("REZOLV_DATA_DIR", os.path.join(BASE_DIR, "data"))
BACKUP_DIR = os.environ.get("REZOLV_BACKUP_DIR", os.path.join(BASE_DIR, "backups"))
DB_PATH = os.environ.get("REZOLV_DB", os.path.join(DATA_DIR, "rezolv.db"))
HOST = os.environ.get("REZOLV_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", os.environ.get("REZOLV_PORT", "8787")))
ENV = os.environ.get("REZOLV_ENV", "dev")  # "dev" | "staging" | "production"
TOKEN_TTL_SECONDS = int(os.environ.get("REZOLV_TOKEN_TTL", str(60 * 60 * 12)))
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_PHOTO_CHARS = 1_500_000

CUSTOM_DOMAIN = os.environ.get("REZOLV_CUSTOM_DOMAIN", "rezolv.ro")
STAGING_DOMAIN = os.environ.get("REZOLV_STAGING_DOMAIN", "staging.rezolv.ro")

ALLOWED_ORIGINS = {
    o.strip()
    for o in os.environ.get(
        "REZOLV_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,"
        "http://127.0.0.1:4173,http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:3000,https://rezolv.ro,https://www.rezolv.ro,https://staging.rezolv.ro",
    ).split(",")
    if o.strip()
}

# Pilot City & SaaS Unit Economics Configuration
PILOT_CITY = os.environ.get("REZOLV_PILOT_CITY", "Sibiu")
B2B_MONTHLY_EUR = int(os.environ.get("REZOLV_B2B_EUR", "39"))
B2B_MONTHLY_RON = int(os.environ.get("REZOLV_B2B_RON", "195"))  # 39 EUR * ~5.0 RON

# Spend Caps & Billing Alert Thresholds
MONTHLY_SPEND_CAP_EUR = float(os.environ.get("REZOLV_MONTHLY_SPEND_CAP_EUR", "250.0"))
DAILY_SMS_CAP = int(os.environ.get("REZOLV_DAILY_SMS_CAP", "500"))
DAILY_AI_CALLS_CAP = int(os.environ.get("REZOLV_DAILY_AI_CALLS_CAP", "2000"))
SMS_COST_EUR = float(os.environ.get("REZOLV_SMS_COST_EUR", "0.045"))
AI_CALL_COST_EUR = float(os.environ.get("REZOLV_AI_CALL_COST_EUR", "0.002"))

# External API Keys (Dual-Mode: Live when configured, Sandbox Inspector when empty)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "REZOLV")

POSTHOG_API_KEY = os.environ.get("POSTHOG_API_KEY", "")
POSTHOG_HOST = os.environ.get("POSTHOG_HOST", "https://eu.i.posthog.com")

# Email & DNS Authentication (SPF / DKIM / DMARC)
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", f"noreply@{CUSTOM_DOMAIN}")
DKIM_SELECTOR = os.environ.get("DKIM_SELECTOR", "rezolv1")

# AI Model & Token Budget Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
AI_MODEL_TIMEOUT_SEC = float(os.environ.get("REZOLV_AI_TIMEOUT", "2.5"))
AI_MAX_INPUT_TOKENS = int(os.environ.get("REZOLV_AI_MAX_INPUT_TOKENS", "250"))
AI_SIMULATE_OUTAGE = os.environ.get("REZOLV_AI_SIMULATE_OUTAGE", "0") == "1"

# Observability & Alerting
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "")
BOOT_TIMESTAMP = int(time.time())


def get_secret() -> bytes:
    """Signing secret: env var, else a persisted random key (never hard-coded)."""
    env = os.environ.get("REZOLV_SECRET")
    if env:
        return env.encode()
    data_dir = os.environ.get("REZOLV_DATA_DIR", DATA_DIR)
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "secret.key")
    if not os.path.exists(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip().encode()


def get_previous_secret() -> bytes | None:
    """Optional previous signing secret for zero-downtime key rotation."""
    env_prev = os.environ.get("REZOLV_SECRET_PREVIOUS")
    if env_prev:
        return env_prev.encode()
    data_dir = os.environ.get("REZOLV_DATA_DIR", DATA_DIR)
    prev_path = os.path.join(data_dir, "secret.prev.key")
    if os.path.exists(prev_path):
        with open(prev_path) as f:
            raw = f.read().strip()
            return raw.encode() if raw else None
    return None


def rotate_secret(keep_previous: bool = False) -> bytes:
    """Rotate the signing key on disk, optionally retaining previous key or invalidating all old tokens."""
    data_dir = os.environ.get("REZOLV_DATA_DIR", DATA_DIR)
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "secret.key")
    prev_path = os.path.join(data_dir, "secret.prev.key")
    if keep_previous and os.path.exists(path):
        with open(path) as src:
            old_val = src.read().strip()
        fd_prev = os.open(prev_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd_prev, "w") as dst:
            dst.write(old_val)
    elif not keep_previous and os.path.exists(prev_path):
        try:
            os.remove(prev_path)
        except OSError:
            pass
    new_val = secrets.token_hex(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(new_val)
    return new_val.encode()
