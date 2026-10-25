"""Automated Anti-No-Show SMS Engine (Twilio Native Integration + Dual-Mode Sandbox).

Supports:
1. Instant SMS notifications (`estimate_ready`, `booking_confirmed`, `rescheduled`).
2. Scheduled Anti-No-Show Reminders (`reminder_24h` at T-24h and `reminder_2h` at T-2h).
3. Dual-Mode execution:
   - Live Twilio REST API when `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` are configured.
   - Sandbox Outbox Mode when keys are omitted, persisting every SMS with a realistic SID
     so founders and angel investors can inspect and trigger 24h/2h reminders live in the UI.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from . import config, observability
from .core import new_id, now_ts

HOUR = 3600


def normalize_phone_e164(raw: str | None) -> str:
    """Normalize Romanian phone numbers to E.164 format (+407xxxxxxxx)."""
    if not raw:
        return "+40700000000"
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("40") and len(digits) == 11:
        return "+" + digits
    if digits.startswith("07") and len(digits) == 10:
        return "+4" + digits
    if len(digits) == 9 and digits.startswith("7"):
        return "+40" + digits
    return "+" + digits if digits else "+40700000000"


def _send_via_twilio(to_e164: str, body: str) -> tuple[str, str]:
    """Send SMS via Twilio REST API if credentials are configured, else Sandbox Outbox."""
    sid = config.TWILIO_ACCOUNT_SID.strip()
    token = config.TWILIO_AUTH_TOKEN.strip()
    sender = config.TWILIO_PHONE_NUMBER.strip() or "REZOLV"
    if not (sid and token):
        return "delivered", "SM_sandbox_" + new_id("")[:16]

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    payload = urllib.parse.urlencode({
        "To": to_e164,
        "From": sender,
        "Body": body,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    auth = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {auth}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return "sent", data.get("sid") or ("SM_" + new_id("")[:16])
    except (urllib.error.URLError, ValueError, KeyError):
        return "failed", "SM_err_" + new_id("")[:12]


def format_ro_slot(start_ts: int | None, end_ts: int | None = None, fallback: str | None = None) -> str:
    if not start_ts:
        return fallback or "În curând"
    dt = datetime.fromtimestamp(start_ts)
    months = ["Ian", "Feb", "Mar", "Apr", "Mai", "Iun", "Iul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    days = ["Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică"]
    day_label = f"{days[dt.weekday()]}, {dt.day} {months[dt.month - 1]}"
    start_hhmm = dt.strftime("%H:%M")
    if end_ts and end_ts > start_ts:
        end_hhmm = datetime.fromtimestamp(end_ts).strftime("%H:%M")
        return f"{day_label}, {start_hhmm}–{end_hhmm}"
    return f"{day_label}, {start_hhmm}"


def send_instant_sms(
    conn,
    booking_id: str,
    recipient_phone: str | None,
    reminder_type: str,
    message_body: str,
    recipient_role: str = "client",
) -> dict:
    """Send an immediate SMS and record it in `sms_reminders`."""
    t = now_ts()
    observability.check_and_record_spend(conn, "sms", enforce=True)
    e164 = normalize_phone_e164(recipient_phone)
    status, provider_sid = _send_via_twilio(e164, message_body)
    provider = "twilio_live" if (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN) else "twilio_sandbox"
    rid = new_id("sms_")
    conn.execute(
        "INSERT INTO sms_reminders (id,booking_id,recipient_phone,recipient_role,reminder_type,"
        "message_body,send_at,status,provider,provider_sid,sent_at,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, booking_id, e164, recipient_role, reminder_type, message_body, t, status, provider, provider_sid, t, t),
    )
    return {
        "id": rid,
        "booking_id": booking_id,
        "recipient_phone": e164,
        "reminder_type": reminder_type,
        "message_body": message_body,
        "status": status,
        "provider": provider,
        "provider_sid": provider_sid,
        "send_at": t,
        "sent_at": t,
    }


def schedule_anti_noshow_reminders(
    conn,
    booking_id: str,
    client_phone: str | None,
    pro_name: str,
    company_name: str,
    service_name: str,
    price_ron: int,
    start_ts: int,
    end_ts: int | None = None,
    is_reschedule: bool = False,
) -> list[dict]:
    """Cancel any previously scheduled reminders for this booking, send instant confirmation,
    and schedule the T-24h and T-2h anti-no-show reminders."""
    t = now_ts()
    e164 = normalize_phone_e164(client_phone)
    slot_str = format_ro_slot(start_ts, end_ts)

    # Cancel any pending future reminders from previous schedule
    conn.execute(
        "UPDATE sms_reminders SET status='cancelled' WHERE booking_id=? AND status='scheduled'",
        (booking_id,),
    )

    created = []
    # 1. Instant confirmation / reschedule SMS
    instant_type = "rescheduled" if is_reschedule else "booking_confirmed"
    if is_reschedule:
        instant_msg = (
            f"REZOLV Sibiu: Lucrarea „{service_name}” cu {pro_name} ({company_name}) a fost "
            f"reprogramată pentru {slot_str}. Cost estimat: {price_ron} RON."
        )
    else:
        instant_msg = (
            f"REZOLV Sibiu: Programare CONFIRMATĂ! {pro_name} ({company_name}) vine pe {slot_str} "
            f"pentru „{service_name}”. Estimare acceptată: {price_ron} RON. Primești reminder la 24h și 2h înainte."
        )
    created.append(send_instant_sms(conn, booking_id, e164, instant_type, instant_msg))

    provider = "twilio_live" if (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN) else "twilio_sandbox"

    # 2. T-24h Anti No-Show Reminder
    send_24h = max(t + 60, start_ts - 24 * HOUR)
    msg_24h = (
        f"REZOLV Reminder (24h): Mâine ({slot_str}) are loc intervenția „{service_name}” cu "
        f"{pro_name} ({price_ron} RON). Dacă a intervenit ceva, deschide aplicația REZOLV pentru reprogramare."
    )
    rid_24 = new_id("sms_")
    conn.execute(
        "INSERT INTO sms_reminders (id,booking_id,recipient_phone,recipient_role,reminder_type,"
        "message_body,send_at,status,provider,provider_sid,sent_at,created_at) "
        "VALUES (?,?,?,?,?,?,?,'scheduled',?,NULL,NULL,?)",
        (rid_24, booking_id, e164, "client", "reminder_24h", msg_24h, send_24h, provider, t),
    )
    created.append({
        "id": rid_24,
        "booking_id": booking_id,
        "recipient_phone": e164,
        "reminder_type": "reminder_24h",
        "message_body": msg_24h,
        "status": "scheduled",
        "provider": provider,
        "send_at": send_24h,
        "sent_at": None,
    })

    # 3. T-2h Anti No-Show Reminder
    send_2h = max(t + 120, start_ts - 2 * HOUR)
    msg_2h = (
        f"REZOLV Reminder (2h): Peste 2 ore ({slot_str}), meșterul {pro_name} ajunge la locația ta din Sibiu "
        f"pentru „{service_name}”. Te rugăm să fii disponibil la telefon!"
    )
    rid_2 = new_id("sms_")
    conn.execute(
        "INSERT INTO sms_reminders (id,booking_id,recipient_phone,recipient_role,reminder_type,"
        "message_body,send_at,status,provider,provider_sid,sent_at,created_at) "
        "VALUES (?,?,?,?,?,?,?,'scheduled',?,NULL,NULL,?)",
        (rid_2, booking_id, e164, "client", "reminder_2h", msg_2h, send_2h, provider, t),
    )
    created.append({
        "id": rid_2,
        "booking_id": booking_id,
        "recipient_phone": e164,
        "reminder_type": "reminder_2h",
        "message_body": msg_2h,
        "status": "scheduled",
        "provider": provider,
        "send_at": send_2h,
        "sent_at": None,
    })
    return created


def process_due_reminders(conn, force_booking_id: str | None = None, force_all_scheduled: bool = False) -> list[dict]:
    """Dispatch due `scheduled` SMS reminders (or force-dispatch for live investor demo)."""
    t = now_ts()
    if force_booking_id:
        rows = conn.execute(
            "SELECT * FROM sms_reminders WHERE booking_id=? AND status='scheduled' ORDER BY send_at",
            (force_booking_id,),
        ).fetchall()
    elif force_all_scheduled:
        rows = conn.execute(
            "SELECT * FROM sms_reminders WHERE status='scheduled' ORDER BY send_at LIMIT 50"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sms_reminders WHERE status='scheduled' AND send_at<=? ORDER BY send_at LIMIT 50",
            (t,),
        ).fetchall()

    dispatched = []
    for r in rows:
        try:
            observability.check_and_record_spend(conn, "sms", enforce=True)
        except Exception:
            break
        status, sid = _send_via_twilio(r["recipient_phone"], r["message_body"])
        conn.execute(
            "UPDATE sms_reminders SET status=?, provider_sid=?, sent_at=? WHERE id=?",
            (status, sid, t, r["id"]),
        )
        dispatched.append({
            "id": r["id"],
            "booking_id": r["booking_id"],
            "recipient_phone": r["recipient_phone"],
            "reminder_type": r["reminder_type"],
            "message_body": r["message_body"],
            "status": status,
            "provider_sid": sid,
            "send_at": r["send_at"],
            "sent_at": t,
        })
    if dispatched:
        conn.commit()
    return dispatched


def list_booking_sms(conn, booking_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM sms_reminders WHERE booking_id=? ORDER BY created_at ASC, send_at ASC",
        (booking_id,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "booking_id": r["booking_id"],
            "recipient_phone": r["recipient_phone"],
            "reminder_type": r["reminder_type"],
            "message_body": r["message_body"],
            "status": r["status"],
            "provider": r["provider"],
            "provider_sid": r["provider_sid"],
            "send_at": r["send_at"],
            "sent_at": r["sent_at"],
        }
        for r in rows
    ]
