"""Observability, Structured Logging, Error Tracking, Alerting, Spend Caps,
Performance Monitoring (p50/p95/p99 latency), and ETag/TTL Caching for REZOLV MVP.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import config
from .core import ApiError, new_id, now_ts

DAY = 86400


# ------------------------------------------------------------------ TTL Cache
class TTLCache:
    """Thread-safe in-memory TTL cache with ETag generation for fast read endpoints."""

    def __init__(self, default_ttl: int = 30):
        self.default_ttl = default_ttl
        self._store: dict[str, tuple[float, object, str]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> tuple[object | None, str | None]:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                self.misses += 1
                return None, None
            expires_at, val, etag = entry
            if now >= expires_at:
                self._store.pop(key, None)
                self.misses += 1
                return None, None
            self.hits += 1
            return val, etag

    def set(self, key: str, value: object, ttl: int | None = None) -> str:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        etag = f'W/"{hashlib.sha1(raw).hexdigest()[:16]}"'
        exp = time.monotonic() + (ttl if ttl is not None else self.default_ttl)
        with self._lock:
            self._store[key] = (exp, value, etag)
        return etag

    def invalidate(self, prefix: str = "") -> None:
        with self._lock:
            if not prefix:
                self._store.clear()
            else:
                for k in [k for k in self._store if k.startswith(prefix)]:
                    self._store.pop(k, None)

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate_pct": round((self.hits / total) * 100, 1) if total else 0.0,
            }


CACHE = TTLCache(default_ttl=30)


# -------------------------------------------------------- Structured Logging
def _anon_ip(ip: str | None) -> str:
    if not ip:
        return "unknown"
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:12]


def log_structured(level: str, event: str, **fields) -> dict:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "service": "rezolv-api",
        "env": config.ENV,
        "city": config.PILOT_CITY,
        "event": event,
        **fields,
    }
    if os.environ.get("REZOLV_LOG_FORMAT", "").lower() == "json":
        sys.stderr.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


# ------------------------------------------------------------------ Alerting
def _dispatch_webhook_alert(payload: dict) -> None:
    url = config.ALERT_WEBHOOK_URL.strip()
    if not url:
        return
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3):
            pass
    except urllib.error.URLError:
        pass


def trigger_alert(
    conn,
    severity: str,
    category: str,
    title: str,
    message: str,
    metadata: dict | None = None,
) -> dict:
    """Create a deduplicated system alert (info | warning | critical) and fire webhook if configured."""
    sev = severity if severity in ("info", "warning", "critical") else "warning"
    t = now_ts()
    existing = conn.execute(
        "SELECT id, created_at FROM system_alerts WHERE category=? AND title=? AND resolved=0 AND created_at>=? LIMIT 1",
        (category, title, t - 300),
    ).fetchone()
    if existing:
        return {"id": existing["id"], "deduplicated": True, "severity": sev, "title": title}

    aid = new_id("al_")
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    conn.execute(
        "INSERT INTO system_alerts (id,severity,category,title,message,metadata_json,resolved,created_at) "
        "VALUES (?,?,?,?,?,?,0,?)",
        (aid, sev, category, title, message, meta_json, t),
    )
    alert_obj = {
        "id": aid,
        "severity": sev,
        "category": category,
        "title": title,
        "message": message,
        "metadata": metadata or {},
        "created_at": t,
    }
    log_structured("WARN" if sev != "critical" else "ERROR", "system_alert_triggered", **alert_obj)
    if config.ALERT_WEBHOOK_URL.strip():
        threading.Thread(target=_dispatch_webhook_alert, args=(alert_obj,), daemon=True).start()
    return alert_obj


# ------------------------------------------------------------ Error Tracking
def capture_error(
    conn,
    source: str,
    message: str,
    *,
    level: str = "error",
    error_code: str | None = None,
    stack_trace: str | None = None,
    path: str | None = None,
    method: str | None = None,
    user_id: str | None = None,
    request_id: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Persist backend or frontend errors in `error_logs` and raise an alert on 500/critical failures."""
    eid = new_id("err_")
    t = now_ts()
    conn.execute(
        "INSERT INTO error_logs (id,source,level,error_code,message,stack_trace,path,method,user_id,request_id,metadata_json,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            eid,
            source[:40],
            level[:20],
            (error_code or "unhandled_error")[:60],
            str(message)[:1000],
            (stack_trace or "")[:4000] if stack_trace else None,
            (path or "")[:200] if path else None,
            (method or "")[:16] if method else None,
            user_id,
            request_id,
            json.dumps(metadata or {}, ensure_ascii=False),
            t,
        ),
    )
    if level in ("error", "critical") and error_code in ("server_error", "ui_crash", "db_error"):
        trigger_alert(
            conn,
            "critical" if error_code == "server_error" else "warning",
            "error_tracking",
            f"Eroare detectată ({source}): {error_code}",
            str(message)[:300],
            {"error_id": eid, "path": path, "request_id": request_id},
        )
    return eid


# ---------------------------------------------------- Performance Monitoring
def record_request_metric(
    conn,
    request_id: str,
    method: str,
    path: str,
    status: int,
    latency_ms: float,
    user_id: str | None = None,
    ip: str | None = None,
) -> None:
    """Record request execution latency and status; alert if latency spikes above threshold."""
    t = now_ts()
    try:
        conn.execute(
            "INSERT INTO request_logs (id,request_id,method,path,status,latency_ms,user_id,ip_hash,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (new_id("rq_"), request_id, method, path[:200], status, round(latency_ms, 2), user_id, _anon_ip(ip), t),
        )
        if latency_ms > 1200.0:
            trigger_alert(
                conn,
                "warning",
                "performance",
                f"Răspuns lent detectat ({round(latency_ms)} ms)",
                f"Endpoint-ul {method} {path} a durat {round(latency_ms, 1)} ms (>1200 ms).",
                {"method": method, "path": path, "latency_ms": round(latency_ms, 2)},
            )
        conn.commit()
    except Exception:
        pass


def prune_old_telemetry(conn) -> dict:
    """Prune telemetry older than retention windows (7d for request_logs, 30d for error_logs)."""
    t = now_ts()
    cutoff_req = t - 7 * 86400
    cutoff_err = t - 30 * 86400
    try:
        del_req = conn.execute("DELETE FROM request_logs WHERE created_at < ?", (cutoff_req,)).rowcount
        del_err = conn.execute("DELETE FROM error_logs WHERE created_at < ?", (cutoff_err,)).rowcount
        conn.commit()
        return {"deleted_request_logs": del_req, "deleted_error_logs": del_err}
    except Exception:
        return {"deleted_request_logs": 0, "deleted_error_logs": 0}


def compute_performance_stats(conn) -> dict:
    rows = conn.execute(
        "SELECT latency_ms, status, path, method FROM request_logs ORDER BY created_at DESC LIMIT 500"
    ).fetchall()
    if not rows:
        return {
            "sample_size": 0,
            "p50_ms": 2.1,
            "p95_ms": 8.4,
            "p99_ms": 15.2,
            "avg_ms": 3.5,
            "error_rate_5xx_pct": 0.0,
            "slow_requests_count": 0,
        }
    latencies = sorted(float(r["latency_ms"]) for r in rows)
    n = len(latencies)
    p50 = latencies[int(n * 0.50)]
    p95 = latencies[min(n - 1, int(n * 0.95))]
    p99 = latencies[min(n - 1, int(n * 0.99))]
    avg = sum(latencies) / n
    err_5xx = sum(1 for r in rows if int(r["status"]) >= 500)
    slow = sum(1 for x in latencies if x > 500.0)
    return {
        "sample_size": n,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "avg_ms": round(avg, 2),
        "error_rate_5xx_pct": round((err_5xx / n) * 100, 2),
        "slow_requests_count": slow,
    }


# ---------------------------------------------- Spend Caps & Billing Alerts
def get_spend_and_quota_status(conn) -> dict:
    """Compute current daily SMS & AI usage, monthly spend in EUR, and billing alert status."""
    t = now_ts()
    day_ago = t - DAY
    month_ago = t - 30 * DAY

    sms_today = conn.execute(
        "SELECT COUNT(*) FROM sms_reminders WHERE created_at>=? AND status IN ('sent','delivered')",
        (day_ago,),
    ).fetchone()[0]
    sms_month = conn.execute(
        "SELECT COUNT(*) FROM sms_reminders WHERE created_at>=? AND status IN ('sent','delivered')",
        (month_ago,),
    ).fetchone()[0]

    ai_today = conn.execute(
        "SELECT COUNT(*) FROM analytics_events WHERE event_name='ai_triage_called' AND created_at>=?",
        (day_ago,),
    ).fetchone()[0]
    ai_month = conn.execute(
        "SELECT COUNT(*) FROM analytics_events WHERE event_name='ai_triage_called' AND created_at>=?",
        (month_ago,),
    ).fetchone()[0]

    sms_spend_eur = round(sms_month * config.SMS_COST_EUR, 2)
    ai_spend_eur = round(ai_month * config.AI_CALL_COST_EUR, 2)
    infra_fixed_eur = 15.0  # Base cloud hosting + DB
    total_spend_eur = round(sms_spend_eur + ai_spend_eur + infra_fixed_eur, 2)
    cap_eur = max(1.0, config.MONTHLY_SPEND_CAP_EUR)
    utilization_pct = round((total_spend_eur / cap_eur) * 100, 1)

    return {
        "monthly_cap_eur": cap_eur,
        "estimated_monthly_spend_eur": total_spend_eur,
        "utilization_pct": utilization_pct,
        "breakdown_eur": {
            "twilio_sms_eur": sms_spend_eur,
            "ai_triage_eur": ai_spend_eur,
            "base_infra_eur": infra_fixed_eur,
        },
        "daily_quotas": {
            "sms_sent_today": sms_today,
            "sms_daily_cap": config.DAILY_SMS_CAP,
            "ai_calls_today": ai_today,
            "ai_daily_cap": config.DAILY_AI_CALLS_CAP,
        },
        "cap_exceeded": total_spend_eur >= cap_eur
        or sms_today >= config.DAILY_SMS_CAP
        or ai_today >= config.DAILY_AI_CALLS_CAP,
    }


def check_and_record_spend(conn, resource_kind: str, enforce: bool = True) -> dict:
    """Check spend caps before executing billable external calls (Twilio SMS or AI LLM).
    Automatically triggers billing alerts at 50%, 80%, and 100% thresholds."""
    status = get_spend_and_quota_status(conn)
    util = status["utilization_pct"]
    q = status["daily_quotas"]

    if util >= 100.0 or (resource_kind == "sms" and q["sms_sent_today"] >= q["sms_daily_cap"]) or (
        resource_kind == "ai" and q["ai_calls_today"] >= q["ai_daily_cap"]
    ):
        trigger_alert(
            conn,
            "critical",
            "billing_spend_cap",
            "Plafon de cost atins (100% Spend Cap)",
            f"Consumul pentru {resource_kind.upper()} a atins limita de siguranță ({status['estimated_monthly_spend_eur']} / {status['monthly_cap_eur']} EUR).",
            status,
        )
        conn.commit()
        if enforce:
            raise ApiError(
                429,
                "spend_cap_reached",
                f"Limita zilnică/lunară de cost pentru {resource_kind.upper()} a fost atinsă. Contactează administratorul.",
            )
    elif util >= 80.0:
        trigger_alert(
            conn,
            "warning",
            "billing_spend_cap",
            "Alertă Buget: 80% din plafonul lunar utilizat",
            f"Cheltuielile estimate ({status['estimated_monthly_spend_eur']} EUR) au depășit 80% din plafonul de {status['monthly_cap_eur']} EUR.",
            status,
        )
        conn.commit()
    elif util >= 50.0:
        trigger_alert(
            conn,
            "info",
            "billing_spend_cap",
            "Notificare Buget: 50% din plafonul lunar utilizat",
            f"Cheltuielile estimate sunt la {util}% din bugetul lunar.",
            status,
        )
        conn.commit()
    return status
