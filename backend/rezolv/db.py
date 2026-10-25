"""Relational DB access + schema (Users, Providers, Services, Bookings/Appointments,
Estimates, SMS Reminders, Analytics Events, Email Verification, Error Tracking,
System Alerts, Request Performance Logs). Foreign keys enforced."""
from __future__ import annotations

import os
import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('client','pro','admin')),
  name TEXT NOT NULL,
  phone TEXT,
  city TEXT NOT NULL DEFAULT 'Sibiu',
  neighborhood TEXT DEFAULT 'Centru',
  address TEXT,
  locale TEXT NOT NULL DEFAULT 'ro',
  token_version INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  email_verified INTEGER NOT NULL DEFAULT 0,
  cookie_consent_json TEXT,
  created_at INTEGER NOT NULL,
  last_login_at INTEGER
);

CREATE TABLE IF NOT EXISTS pro_profiles (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  company_name TEXT NOT NULL,
  cui TEXT NOT NULL UNIQUE,
  headline TEXT,
  bio TEXT,
  experience_years INTEGER NOT NULL DEFAULT 1,
  city TEXT NOT NULL DEFAULT 'Sibiu',
  zones_json TEXT NOT NULL DEFAULT '[]',
  hours_json TEXT NOT NULL DEFAULT '{}',
  slot_step_minutes INTEGER NOT NULL DEFAULT 30,
  verification_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (verification_status IN ('pending','verified','rejected')),
  verification_note TEXT,
  verified_at INTEGER,
  onboarded_by_admin INTEGER NOT NULL DEFAULT 0,
  rating_avg REAL NOT NULL DEFAULT 0,
  rating_count INTEGER NOT NULL DEFAULT 0,
  jobs_completed INTEGER NOT NULL DEFAULT 0,
  availability TEXT NOT NULL DEFAULT 'Disponibil astăzi',
  distance_km REAL NOT NULL DEFAULT 2.5,
  plan TEXT NOT NULL DEFAULT 'essential' CHECK (plan IN ('essential','pro')),
  plan_status TEXT NOT NULL DEFAULT 'trial' CHECK (plan_status IN ('trial','active','past_due')),
  subscription_price_eur INTEGER NOT NULL DEFAULT 39,
  plan_renews_at INTEGER
);

CREATE TABLE IF NOT EXISTS categories (
  name TEXT PRIMARY KEY,
  price_label TEXT NOT NULL,
  icon TEXT NOT NULL,
  tone TEXT NOT NULL,
  sort INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS pro_services (
  id TEXT PRIMARY KEY,
  pro_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category TEXT NOT NULL REFERENCES categories(name),
  name TEXT NOT NULL,
  price_from INTEGER NOT NULL CHECK (price_from > 0),
  price_unit TEXT NOT NULL DEFAULT 'RON',
  duration TEXT NOT NULL,
  est_duration_min INTEGER NOT NULL DEFAULT 60,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_services_pro ON pro_services(pro_id);
CREATE INDEX IF NOT EXISTS idx_services_cat ON pro_services(category, active);

CREATE TABLE IF NOT EXISTS bookings (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  pro_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  service_id TEXT REFERENCES pro_services(id) ON DELETE SET NULL,
  category TEXT NOT NULL,
  service_name TEXT NOT NULL,
  price_label TEXT NOT NULL,
  description TEXT NOT NULL,
  neighborhood TEXT DEFAULT 'Sibiu',
  client_address TEXT,
  client_phone TEXT,
  urgency_level TEXT NOT NULL DEFAULT 'normal',
  preferred_window TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','estimated','accepted','refused','cancelled','completed','no_show')),
  quote_price INTEGER,
  quote_price_max INTEGER,
  quote_duration TEXT,
  duration_minutes INTEGER NOT NULL DEFAULT 60,
  pro_notes TEXT,
  scheduled_for TEXT,
  scheduled_start_at INTEGER,
  scheduled_end_at INTEGER,
  accepted_estimate_id TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  completed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_bookings_client ON bookings(client_id, created_at);
CREATE INDEX IF NOT EXISTS idx_bookings_pro ON bookings(pro_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_bookings_cal ON bookings(pro_id, status, scheduled_start_at);

CREATE TABLE IF NOT EXISTS estimates (
  id TEXT PRIMARY KEY,
  booking_id TEXT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  pro_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  price_ron INTEGER NOT NULL CHECK (price_ron > 0),
  price_max_ron INTEGER,
  duration_minutes INTEGER NOT NULL DEFAULT 60,
  duration_label TEXT NOT NULL DEFAULT '1 oră',
  proposed_start_at INTEGER NOT NULL,
  proposed_end_at INTEGER NOT NULL,
  slot_label TEXT NOT NULL,
  pro_notes TEXT,
  status TEXT NOT NULL DEFAULT 'sent'
    CHECK (status IN ('sent','accepted','declined','expired','superseded')),
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  responded_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_estimates_booking ON estimates(booking_id, status);

CREATE TABLE IF NOT EXISTS sms_reminders (
  id TEXT PRIMARY KEY,
  booking_id TEXT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  recipient_phone TEXT NOT NULL,
  recipient_role TEXT NOT NULL DEFAULT 'client',
  reminder_type TEXT NOT NULL
    CHECK (reminder_type IN ('estimate_ready','booking_confirmed','reminder_24h','reminder_2h','rescheduled')),
  message_body TEXT NOT NULL,
  send_at INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled'
    CHECK (status IN ('scheduled','sent','delivered','failed','cancelled')),
  provider TEXT NOT NULL DEFAULT 'twilio',
  provider_sid TEXT,
  sent_at INTEGER,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sms_booking ON sms_reminders(booking_id, reminder_type);
CREATE INDEX IF NOT EXISTS idx_sms_due ON sms_reminders(status, send_at);

CREATE TABLE IF NOT EXISTS analytics_events (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  role TEXT,
  event_name TEXT NOT NULL,
  properties_json TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analytics_name ON analytics_events(event_name, created_at);

CREATE TABLE IF NOT EXISTS booking_photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  booking_id TEXT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  data_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS booking_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  booking_id TEXT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  actor_id TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY,
  booking_id TEXT NOT NULL UNIQUE REFERENCES bookings(id) ON DELETE CASCADE,
  client_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  pro_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  comment TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  plan TEXT,
  amount_ron INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('succeeded','failed')),
  provider TEXT NOT NULL,
  provider_ref TEXT,
  card_brand TEXT,
  card_last4 TEXT,
  invoice_no TEXT,
  failure_reason TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id, created_at);

CREATE TABLE IF NOT EXISTS payment_methods (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  brand TEXT NOT NULL,
  last4 TEXT NOT NULL,
  exp TEXT NOT NULL,
  is_default INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  booking_id TEXT,
  is_read INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read, created_at);

CREATE TABLE IF NOT EXISTS reset_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS email_outbox (
  id TEXT PRIMARY KEY,
  recipient_email TEXT NOT NULL,
  subject TEXT NOT NULL,
  body_text TEXT NOT NULL,
  template_kind TEXT NOT NULL,
  headers_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'sent',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_email_outbox_recipient ON email_outbox(recipient_email, created_at);

CREATE TABLE IF NOT EXISTS error_logs (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  level TEXT NOT NULL,
  error_code TEXT,
  message TEXT NOT NULL,
  stack_trace TEXT,
  path TEXT,
  method TEXT,
  user_id TEXT,
  request_id TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_error_logs_created ON error_logs(created_at DESC);

CREATE TABLE IF NOT EXISTS system_alerts (
  id TEXT PRIMARY KEY,
  severity TEXT NOT NULL CHECK (severity IN ('info','warning','critical')),
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  resolved INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON system_alerts(resolved, created_at DESC);

CREATE TABLE IF NOT EXISTS request_logs (
  id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  method TEXT NOT NULL,
  path TEXT NOT NULL,
  status INTEGER NOT NULL,
  latency_ms REAL NOT NULL,
  user_id TEXT,
  ip_hash TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_req_logs_created ON request_logs(created_at DESC);
"""


_RO_MAP = str.maketrans("ăâîșşțţĂÂÎȘŞȚŢ", "aaissttAAISSTT")


def ro_norm(val: object) -> str:
    """Case-insensitive and Romanian-diacritic-insensitive normalizer for SQLite queries."""
    if val is None:
        return ""
    return str(val).translate(_RO_MAP).lower()


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.create_function("ro_norm", 1, ro_norm)
    return conn


def init_db(db_path: str | None = None) -> None:
    path = db_path or config.DB_PATH
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        cols_u = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "email_verified" not in cols_u:
            conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
        if "cookie_consent_json" not in cols_u:
            conn.execute("ALTER TABLE users ADD COLUMN cookie_consent_json TEXT")

        cols_b = {r["name"] for r in conn.execute("PRAGMA table_info(bookings)").fetchall()}
        if "client_address" not in cols_b:
            conn.execute("ALTER TABLE bookings ADD COLUMN client_address TEXT")
        if "client_phone" not in cols_b:
            conn.execute("ALTER TABLE bookings ADD COLUMN client_phone TEXT")

        icon_updates = {
            "Instalații Sanitare": "cat-instalatii-sanitare.svg",
            "Instalații Electrice": "cat-instalatii-electrice.svg",
            "Mecanică Auto": "cat-mecanica-auto.svg",
            "Vulcanizare Mobilă": "cat-vulcanizare-mobila.svg",
            "Climatizare & Termice": "cat-climatizare-termice.svg",
            "Reparații Electrocasnice": "cat-reparatii-electrocasnice.svg",
            "Zugrăveli & Finisaje": "cat-zugraveli-finisaje.svg",
            "Zidărie & Faianțare": "cat-zidarie-faiantare.svg",
            "Montaj Mobilă": "cat-montaj-mobila.svg",
            "Lăcătuș": "cat-lacatus.svg",
            "Acoperișuri & Exterioare": "cat-acoperisuri-exterioare.svg",
            "Curățenie": "cat-curatenie.svg",
        }
        for cat_name, icon_name in icon_updates.items():
            conn.execute("UPDATE categories SET icon=? WHERE name=?", (icon_name, cat_name))
        conn.commit()
    finally:
        conn.close()
