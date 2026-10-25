"""Business logic for REZOLV MVP (Sibiu Pilot).
Includes:
- Auth & Romanian CUI / ANAF verification
- Catalog & Sibiu neighborhood filtering
- 3-Step Flexible Estimate Handshake (Request -> Estimate -> Client Accept + Atomic Slot Lock)
- 2-Click B2B Mobile Calendar Engine (Slot conflict detection, 2-click Reschedule/Accept/Cancel)
- Twilio Anti-No-Show SMS Engine (T-24h & T-2h reminders)
- Founder Super-Admin White-Glove Onboarding & PostHog/Mixpanel Investor Analytics
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timedelta

from . import analytics, backup, config, db, email_service, observability, payments, seed, sms
from . import verification as ver
from .core import (
    ApiError,
    Validator,
    bad,
    hash_password,
    hash_reset_token,
    issue_token,
    new_id,
    now_ts,
    read_token,
    verify_password,
)

DAY = 86400
HOUR = 3600
PHOTO_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,[A-Za-z0-9+/=]+$")


# ------------------------------------------------------------------- helpers
def initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def ago(ts: int) -> str:
    s = max(0, now_ts() - ts)
    if s < 90:
        return "Acum câteva secunde"
    if s < 3600:
        return f"Acum {s // 60}m"
    if s < DAY:
        return f"{s // 3600}h în urmă"
    return f"{s // DAY} zile în urmă"


def hhmm(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def duration_label_of(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    if minutes == 60:
        return "1 oră"
    if minutes % 60 == 30:
        return f"{minutes // 60}.5 ore"
    return f"{minutes // 60} ore"


def parse_duration_minutes(raw_duration: str | None, explicit_min: int | None = None) -> int:
    if isinstance(explicit_min, int) and 15 <= explicit_min <= 720:
        return explicit_min
    if not raw_duration:
        return 60
    s = raw_duration.lower()
    m_min = re.search(r"(\d+)\s*min", s)
    if m_min:
        return max(15, min(720, int(m_min.group(1))))
    m_dec = re.search(r"(\d+[.,]\d+)\s*or", s)
    if m_dec:
        val = float(m_dec.group(1).replace(",", "."))
        return max(30, min(720, int(round(val * 60))))
    m_hr = re.search(r"(\d+)\s*(?:or|h)", s)
    if m_hr:
        return max(30, min(720, int(m_hr.group(1)) * 60))
    return 60


def default_next_free_slot(conn, pro_id: str, duration_min: int = 60, preferred_ts: int | None = None) -> tuple[int, int]:
    """Find the next conflict-free slot for a Pro starting today or tomorrow between 08:00 and 18:00."""
    if preferred_ts and preferred_ts > now_ts() - 3600:
        end_ts = preferred_ts + duration_min * 60
        if not has_slot_conflict(conn, pro_id, preferred_ts, end_ts):
            return preferred_ts, end_ts

    now_dt = datetime.now()
    for day_offset in range(0, 14):
        day_dt = now_dt + timedelta(days=day_offset)
        for hour in (8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18):
            cand_dt = datetime(day_dt.year, day_dt.month, day_dt.day, hour, 0, 0)
            start_ts = int(cand_dt.timestamp())
            if start_ts <= now_ts() + 900:
                continue
            end_ts = start_ts + duration_min * 60
            # Avoid slots that are either already accepted or already have an active estimate
            busy = conn.execute(
                "SELECT 1 FROM bookings WHERE pro_id=? AND status IN ('accepted','estimated') "
                "AND scheduled_start_at IS NOT NULL AND scheduled_end_at IS NOT NULL "
                "AND scheduled_start_at < ? AND scheduled_end_at > ? LIMIT 1",
                (pro_id, end_ts, start_ts),
            ).fetchone()
            if not busy:
                return start_ts, end_ts
    fallback_start = int((now_dt + timedelta(days=1)).replace(hour=10, minute=0, second=0).timestamp())
    return fallback_start, fallback_start + duration_min * 60


def has_slot_conflict(conn, pro_id: str, start_ts: int, end_ts: int, exclude_booking_id: str | None = None) -> dict | None:
    """Check if the Pro already has an accepted booking overlapping [start_ts, end_ts)."""
    sql = (
        "SELECT id, service_name, scheduled_for, scheduled_start_at, scheduled_end_at "
        "FROM bookings WHERE pro_id=? AND status='accepted' "
        "AND scheduled_start_at IS NOT NULL AND scheduled_end_at IS NOT NULL "
        "AND scheduled_start_at < ? AND scheduled_end_at > ?"
    )
    args = [pro_id, end_ts, start_ts]
    if exclude_booking_id:
        sql += " AND id<>?"
        args.append(exclude_booking_id)
    row = conn.execute(sql, args).fetchone()
    return dict(row) if row else None


def notify(conn, user_id, kind, title, body, booking_id=None):
    conn.execute(
        "INSERT INTO notifications (id,user_id,kind,title,body,booking_id,is_read,created_at) "
        "VALUES (?,?,?,?,?,?,0,?)",
        (new_id("n_"), user_id, kind, title, body, booking_id, now_ts()),
    )


def user_view(row, profile=None):
    out = {
        "id": row["id"],
        "email": row["email"],
        "role": row["role"],
        "name": row["name"],
        "phone": row["phone"],
        "city": row["city"] if "city" in row.keys() else "Sibiu",
        "neighborhood": row["neighborhood"] if "neighborhood" in row.keys() else "Centru",
        "address": row["address"],
        "locale": row["locale"],
        "email_verified": bool(row["email_verified"]) if "email_verified" in row.keys() else True,
        "initials": initials(row["name"]),
    }
    if profile is not None:
        out["pro"] = pro_private_view(profile)
    return out


def pro_private_view(p):
    return {
        "company_name": p["company_name"],
        "cui": p["cui"],
        "headline": p["headline"],
        "bio": p["bio"],
        "experience_years": p["experience_years"],
        "city": p["city"] if "city" in p.keys() else "Sibiu",
        "zones": json.loads(p["zones_json"]),
        "hours": json.loads(p["hours_json"]),
        "verification_status": p["verification_status"],
        "verification_note": p["verification_note"],
        "onboarded_by_admin": bool(p["onboarded_by_admin"]) if "onboarded_by_admin" in p.keys() else False,
        "plan": p["plan"],
        "plan_status": p["plan_status"],
        "subscription_price_eur": p["subscription_price_eur"] if "subscription_price_eur" in p.keys() else 39,
        "plan_renews_at": p["plan_renews_at"],
        "rating": round(p["rating_avg"], 1),
        "reviews": p["rating_count"],
        "jobs": p["jobs_completed"],
    }


def fmt_rating(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


# ---------------------------------------------------------------------- auth
def _auth_payload(conn, ctx, user_row):
    profile = conn.execute("SELECT * FROM pro_profiles WHERE user_id=?", (user_row["id"],)).fetchone()
    token = issue_token(user_row["id"], user_row["role"], user_row["token_version"], ctx.secret)
    return {"token": token, "user": user_view(user_row, profile)}


def register(conn, ctx, data):
    v = Validator(data)
    role = v.choice("role", ("client", "pro"), label="Rolul")
    name = v.text("name", min=2, max=80, label="Numele")
    email = v.email()
    v.password()
    phone = v.phone()
    company = cui = None
    if role == "pro":
        company = v.text("company_name", min=3, max=120, label="Denumirea firmei")
        cui = v.text("cui", max=14, label="CUI")
        if cui and not ver.validate_cui(cui):
            v.errors.setdefault("cui", "CUI invalid (verificați cifra de control).")
    clean = v.done()
    if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise ApiError(409, "email_taken", "Există deja un cont cu acest email.", {"email": "Email deja folosit."})
    canon = None
    if role == "pro":
        canon = "RO" + ver.normalize_cui(cui)
        if conn.execute("SELECT 1 FROM pro_profiles WHERE cui=?", (canon,)).fetchone():
            raise ApiError(409, "cui_taken", "Această firmă are deja un cont.", {"cui": "CUI deja înregistrat."})
    uid, t = new_id("u_"), now_ts()
    conn.execute(
        "INSERT INTO users (id,email,password_hash,role,name,phone,city,neighborhood,created_at,last_login_at) "
        "VALUES (?,?,?,?,?,?,'Sibiu','Centru',?,?)",
        (uid, email, hash_password(clean["password"]), role, name, phone, t, t),
    )
    if role == "pro":
        reg = ver.lookup_registry(cui)
        status = "verified" if reg and reg["active"] else "pending"
        note = (
            "Verificat automat în registrul ONRC/ANAF."
            if status == "verified"
            else "Firma nu a fost găsită automat; echipa REZOLV Sibiu o verifică manual (sau prin White-Glove Onboarding)."
        )
        conn.execute(
            "INSERT INTO pro_profiles (user_id,company_name,cui,city,zones_json,hours_json,verification_status,"
            "verification_note,verified_at,plan,plan_status,subscription_price_eur,plan_renews_at,availability) "
            "VALUES (?,?,?,'Sibiu',?,?,?,?,?,'essential','trial',39,?,'Disponibil în curând')",
            (
                uid,
                company,
                canon,
                json.dumps(seed.SIBIU_ZONES[:5], ensure_ascii=False),
                json.dumps(seed.HOURS, ensure_ascii=False),
                status,
                note,
                t if status == "verified" else None,
                t + 14 * DAY,
            ),
        )
        notify(conn, uid, "verification", "Bine ai venit în REZOLV Sibiu", "Contul tău profesional a fost creat. " + note)
    ver_token = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO email_verification_tokens (token_hash,user_id,expires_at,used) VALUES (?,?,?,0)",
        (hash_reset_token(ver_token), uid, t + 24 * HOUR),
    )
    email_service.send_verification_email(conn, email, name, ver_token)
    analytics.track(conn, uid, role, "user_registered", {"city": "Sibiu", "role": role})
    observability.CACHE.invalidate()
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    payload = _auth_payload(conn, ctx, row)
    if config.ENV == "dev":
        payload["dev_verification_token"] = ver_token
    return payload


def login(conn, ctx, data, ip):
    v = Validator(data)
    email = v.email()
    pw = v.data.get("password")
    role = data.get("role")
    v.done()
    if not isinstance(pw, str) or not pw:
        raise bad("Parola este obligatorie.", "password")
    key = f"login:{ip}:{email}"
    ctx.limiter.check(key, 8, 900, "Prea multe încercări de autentificare. Reîncearcă în câteva minute.")
    row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    ok = verify_password(pw, row["password_hash"]) if row else verify_password(pw, "x$1$00$00")
    if not row or not ok or not row["is_active"]:
        raise ApiError(401, "invalid_credentials", "Email sau parolă incorectă.")
    if role in ("client", "pro") and row["role"] != role:
        wanted = "Meșter" if row["role"] == "pro" else "Client"
        raise ApiError(403, "wrong_role", f"Acest cont este de tip {wanted}. Schimbă rolul selectat.")
    ctx.limiter.reset(key)
    conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (now_ts(), row["id"]))
    analytics.track(conn, row["id"], row["role"], "user_logged_in", {"city": "Sibiu"})
    conn.commit()
    return _auth_payload(conn, ctx, row)


def authenticate(conn, ctx, header):
    if not header or not header.startswith("Bearer "):
        raise ApiError(401, "unauthenticated", "Autentificare necesară.")
    payload = read_token(header[7:].strip(), ctx.secret, config.get_previous_secret())
    row = conn.execute("SELECT * FROM users WHERE id=?", (payload["sub"],)).fetchone()
    if not row or not row["is_active"] or row["token_version"] != payload["tv"]:
        raise ApiError(401, "invalid_token", "Sesiune invalidă. Conectează-te din nou.")
    return row


def require_role(user, *roles):
    if user["role"] not in roles:
        raise ApiError(403, "forbidden", "Nu ai permisiunea să efectuezi această acțiune.")


def request_password_reset(conn, ctx, data, ip):
    v = Validator(data)
    email = v.email()
    v.done()
    ctx.limiter.check(f"reset:{ip}", 5, 3600)
    row = conn.execute("SELECT id FROM users WHERE email=? AND is_active=1", (email,)).fetchone()
    out = {"message": "Dacă adresa există, am trimis instrucțiunile de resetare."}
    if row:
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO reset_tokens VALUES (?,?,?,0)",
            (hash_reset_token(token), row["id"], now_ts() + 3600),
        )
        email_service.send_password_reset_email(conn, email, token)
        conn.commit()
        if config.ENV == "dev":
            out["dev_token"] = token
    return out


def confirm_password_reset(conn, ctx, data):
    v = Validator(data)
    token = v.text("token", max=200, label="Tokenul")
    password = v.password()
    v.done()
    row = conn.execute("SELECT * FROM reset_tokens WHERE token_hash=?", (hash_reset_token(token),)).fetchone()
    if not row or row["used"] or row["expires_at"] < now_ts():
        raise ApiError(400, "invalid_reset", "Linkul de resetare este invalid sau a expirat.")
    conn.execute("UPDATE reset_tokens SET used=1 WHERE token_hash=?", (row["token_hash"],))
    conn.execute(
        "UPDATE users SET password_hash=?, token_version=token_version+1 WHERE id=?",
        (hash_password(password), row["user_id"]),
    )
    conn.commit()
    return {"message": "Parola a fost schimbată. Te poți conecta."}


def send_email_verification(conn, ctx, user):
    ctx.limiter.check(f"verify_email:{user['id']}", 5, 3600)
    if "email_verified" in user.keys() and user["email_verified"]:
        return {"message": "Adresa de email este deja verificată.", "already_verified": True}
    token = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO email_verification_tokens (token_hash,user_id,expires_at,used) VALUES (?,?,?,0)",
        (hash_reset_token(token), user["id"], now_ts() + 24 * HOUR),
    )
    email_service.send_verification_email(conn, user["email"], user["name"], token)
    conn.commit()
    out = {"message": f"Am trimis codul de verificare la {user['email']}."}
    if config.ENV == "dev":
        out["dev_token"] = token
    return out


def confirm_email_verification(conn, data):
    v = Validator(data)
    token = v.text("token", max=200, label="Codul de verificare")
    v.done()
    row = conn.execute(
        "SELECT * FROM email_verification_tokens WHERE token_hash=?",
        (hash_reset_token(token),),
    ).fetchone()
    if not row or row["used"] or row["expires_at"] < now_ts():
        raise ApiError(400, "invalid_verification_token", "Codul de verificare este invalid sau a expirat.")
    conn.execute("UPDATE email_verification_tokens SET used=1 WHERE token_hash=?", (row["token_hash"],))
    conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (row["user_id"],))
    notify(
        conn,
        row["user_id"],
        "email_verified",
        "Email verificat cu succes",
        "Adresa ta de email a fost confirmată în platforma REZOLV Sibiu.",
    )
    conn.commit()
    u_row = conn.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()
    return {"message": "Adresa de email a fost verificată cu succes!", **me(conn, u_row)}


def export_user_data(conn, user) -> dict:
    """GDPR Article 20 (Right to Data Portability): export all personal data in structured JSON."""
    uid = user["id"]
    profile = conn.execute("SELECT * FROM pro_profiles WHERE user_id=?", (uid,)).fetchone()
    bookings = [
        dict(r)
        for r in conn.execute(
            "SELECT id,category,service_name,description,neighborhood,status,quote_price,scheduled_for,created_at "
            "FROM bookings WHERE client_id=? OR pro_id=? ORDER BY created_at DESC",
            (uid, uid),
        ).fetchall()
    ]
    reviews = [
        dict(r)
        for r in conn.execute(
            "SELECT id,booking_id,rating,comment,created_at FROM reviews WHERE client_id=? OR pro_id=?",
            (uid, uid),
        ).fetchall()
    ]
    payments_list = [
        dict(r)
        for r in conn.execute(
            "SELECT id,plan,amount_ron,status,invoice_no,card_brand,card_last4,created_at FROM payments WHERE user_id=?",
            (uid,),
        ).fetchall()
    ]
    notifs = [
        dict(r)
        for r in conn.execute(
            "SELECT id,kind,title,body,created_at FROM notifications WHERE user_id=? ORDER BY created_at DESC",
            (uid,),
        ).fetchall()
    ]
    analytics.track(conn, uid, user["role"], "gdpr_data_exported", {})
    conn.commit()
    return {
        "gdpr_export_version": "1.0",
        "exported_at": now_ts(),
        "controller": "REZOLV Sibiu S.R.L. (gdpr@rezolv.ro)",
        "user": user_view(user, profile),
        "bookings": bookings,
        "reviews": reviews,
        "payments": payments_list,
        "notifications": notifs,
    }


def delete_user_account(conn, user, data=None) -> dict:
    """GDPR Article 17 (Right to Erasure / Account & Data Deletion)."""
    uid = user["id"]
    email = user["email"]
    name = user["name"]
    if isinstance(data, dict) and data.get("password"):
        if not verify_password(str(data["password"]), user["password_hash"]):
            raise ApiError(401, "invalid_credentials", "Parola introdusă pentru confirmarea ștergerii este incorectă.")

    # Delete dependent records & user row
    conn.execute("DELETE FROM reviews WHERE client_id=? OR pro_id=?", (uid, uid))
    conn.execute("DELETE FROM estimates WHERE pro_id=?", (uid,))
    conn.execute("DELETE FROM bookings WHERE client_id=? OR pro_id=?", (uid, uid))
    conn.execute("DELETE FROM pro_services WHERE pro_id=?", (uid,))
    conn.execute("DELETE FROM pro_profiles WHERE user_id=?", (uid,))
    # Retain anonymized payment rows for Romanian 10-year fiscal accounting compliance (Legea 82/1991)
    conn.execute("UPDATE payments SET user_id='gdpr_anonymized' WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM payment_methods WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM notifications WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM reset_tokens WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM email_verification_tokens WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM analytics_events WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM users WHERE id=?", (uid,))

    email_service.send_account_deleted_email(conn, email, name)
    observability.CACHE.invalidate()
    conn.commit()
    return {
        "deleted": True,
        "gdpr_erasure": "completed",
        "message": "Contul și toate datele tale personale au fost șterse definitiv conform GDPR.",
    }


def save_cookie_consent(conn, user, data) -> dict:
    consent = {
        "essential": True,
        "analytics": bool((data or {}).get("analytics", False)),
        "marketing": bool((data or {}).get("marketing", False)),
        "updated_at": now_ts(),
    }
    if user:
        conn.execute(
            "UPDATE users SET cookie_consent_json=? WHERE id=?",
            (json.dumps(consent, ensure_ascii=False), user["id"]),
        )
        conn.commit()
    return {"ok": True, "consent": consent}


def get_legal_document(kind: str) -> dict:
    if kind == "privacy":
        return {
            "kind": "privacy_policy",
            "title": "Politică de Confidențialitate și Protecția Datelor (GDPR)",
            "effective_date": "2026-10-01",
            "controller": "REZOLV Sibiu S.R.L., Mun. Sibiu, România • DPO: gdpr@rezolv.ro",
            "sections": [
                {
                    "heading": "1. Ce date colectăm (Minimul necesar)",
                    "body": "Colectăm numele, adresa de email, numărul de telefon (pentru remindere SMS anti-no-show la 24h și 2h înainte de lucrare), cartierul/adresa intervenției din Sibiu și, pentru meșteri, datele de identificare ale firmei (CUI și denumire SRL/PFA).",
                },
                {
                    "heading": "2. Temeiul legal și scopul prelucrării (Regulamentul UE 2016/679)",
                    "body": "Datele sunt prelucrate pentru executarea contractului de programare dintre client și meșter (Art. 6(1)(b) GDPR), securitatea platformei și prevenirea fraudei (Art. 6(1)(f)), precum și telemetrie de produs doar cu consimțământul tău (Art. 6(1)(a)).",
                },
                {
                    "heading": "3. Drepturile tale (Export & Ștergere 1-Click)",
                    "body": "Ai dreptul de acces, rectificare, portabilitatea datelor (butonul „Exportă datele mele GDPR” din Profil) și dreptul la ștergere definitivă / „dreptul de a fi uitat” (butonul „Șterge contul și datele” din Profil, executat instantaneu).",
                },
                {
                    "heading": "4. Securitate și stocare în UE",
                    "body": "Parolele sunt criptate cu PBKDF2-SHA256 (210.000 iterații), sesiunile sunt semnate criptografic cu HMAC-SHA256, nu stocăm niciodată numere complete de card (doar ultimele 4 cifre), iar datele sunt găzduite în Uniunea Europeană.",
                },
            ],
        }
    return {
        "kind": "terms_and_conditions",
        "title": "Termeni și Condiții de Utilizare — REZOLV Sibiu",
        "effective_date": "2026-10-01",
        "sections": [
            {
                "heading": "1. Modelul REZOLV (0% Comision per lucrare)",
                "body": "Pentru clienți, găsirea unui meșter verificat și blocarea unui slot în calendar este 100% gratuită. Plata lucrării se face direct către meșter după recepția serviciului. Profesioniștii (SRL/PFA) utilizează platforma pe bază de abonament lunar B2B SaaS (39 EUR/lună).",
            },
            {
                "heading": "2. Verificarea CUI și Garanția Calității",
                "body": "Toți meșterii publicați în REZOLV Sibiu sunt verificați prin CUI (cifră de control Modulo-11 și registru ONRC/ANAF) sau prin procesul White-Glove Onboarding realizat de echipa locală.",
            },
            {
                "heading": "3. Estimări, Calendar și Remindere SMS Anti-No-Show",
                "body": "Când clientul acceptă o estimare de preț și durată, intervalul orar este blocat atomic în calendarul meșterului și se programează automat remindere SMS la 24h și 2h înainte de intervenție.",
            },
        ],
    }


def me(conn, user):
    profile = conn.execute("SELECT * FROM pro_profiles WHERE user_id=?", (user["id"],)).fetchone()
    return {"user": user_view(user, profile)}


def update_me(conn, user, data):
    v = Validator(data)
    name = v.text("name", min=2, max=80, label="Numele", required=False)
    phone = v.phone()
    address = v.text("address", max=200, required=False, label="Adresa")
    neighborhood = v.text("neighborhood", max=80, required=False, label="Cartierul")
    locale = v.choice("locale", ("ro", "en", "de"), required=False, label="Limba")
    v.done()
    conn.execute(
        "UPDATE users SET name=COALESCE(?,name), phone=COALESCE(?,phone), address=COALESCE(?,address),"
        " neighborhood=COALESCE(?,neighborhood), locale=COALESCE(?,locale) WHERE id=?",
        (name, phone, address, neighborhood, locale, user["id"]),
    )
    conn.commit()
    return me(conn, conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())


# ------------------------------------------------------------------- catalog
def list_categories(conn):
    cached, _ = observability.CACHE.get("categories:all")
    if cached is not None:
        return cached
    res = {"categories": [dict(r) for r in conn.execute("SELECT * FROM categories ORDER BY sort")]}
    observability.CACHE.set("categories:all", res, ttl=60)
    return res


def _service_view(r):
    price = f"de la {r['price_from']} {r['price_unit']}"
    return {
        "id": r["id"],
        "category": r["category"],
        "name": r["name"],
        "price": price,
        "price_from": r["price_from"],
        "unit": r["price_unit"],
        "duration": r["duration"],
        "est_duration_min": r["est_duration_min"] if "est_duration_min" in r.keys() else 60,
        "active": bool(r["active"]),
    }


def _public_pro(conn, r, category=None, detail=False):
    q = "SELECT * FROM pro_services WHERE pro_id=? AND active=1"
    args = [r["user_id"]]
    if category:
        q += " AND category=?"
        args.append(category)
    services = [_service_view(s) for s in conn.execute(q + " ORDER BY category, rowid", args)]
    zones = json.loads(r["zones_json"])
    out = {
        "id": r["user_id"],
        "name": r["name"],
        "initials": initials(r["name"]),
        "company_name": r["company_name"],
        "cui": r["cui"],
        "headline": r["headline"],
        "city": r["city"] if "city" in r.keys() else "Sibiu",
        "zones": zones,
        "rating": fmt_rating(r["rating_avg"]),
        "rating_value": round(r["rating_avg"], 2),
        "reviews": r["rating_count"],
        "jobs": r["jobs_completed"],
        "distance": f"{r['distance_km']:.1f}".replace(".", ",") + " km",
        "availability": r["availability"],
        "experience": f"{r['experience_years']} ani experiență",
        "experience_years": r["experience_years"],
        "verified": r["verification_status"] == "verified",
        "promoted": r["plan"] == "pro",
        "services": services,
    }
    if detail:
        out["bio"] = r["bio"]
        out["hours"] = json.loads(r["hours_json"])
        out["categories"] = sorted({s["category"] for s in services})
        out["recent_reviews"] = [
            {"rating": x["rating"], "comment": x["comment"], "author": x["author"], "ago": ago(x["created_at"])}
            for x in conn.execute(
                "SELECT rv.rating, rv.comment, rv.created_at, u.name AS author FROM reviews rv "
                "JOIN users u ON u.id=rv.client_id WHERE rv.pro_id=? ORDER BY rv.created_at DESC LIMIT 10",
                (r["user_id"],),
            )
        ]
    return out


_PRO_JOIN = (
    "SELECT p.*, u.name FROM pro_profiles p JOIN users u ON u.id=p.user_id "
    "WHERE p.verification_status='verified' AND u.is_active=1 "
    "AND p.plan_status IN ('active', 'trial')"
)


def list_professionals(conn, category=None, q=None, zone=None):
    sql, args = _PRO_JOIN, []
    if category:
        sql += (
            " AND EXISTS (SELECT 1 FROM pro_services s WHERE s.pro_id=p.user_id "
            "AND s.category=? AND s.active=1)"
        )
        args.append(category)
    if zone:
        sql += " AND ro_norm(p.zones_json) LIKE ?"
        args.append(f"%{db.ro_norm(zone)[:40]}%")
    if q:
        like = f"%{db.ro_norm(q)[:60]}%"
        sql += (
            " AND (ro_norm(u.name) LIKE ? OR ro_norm(p.company_name) LIKE ? OR ro_norm(p.zones_json) LIKE ? OR EXISTS ("
            "SELECT 1 FROM pro_services s WHERE s.pro_id=p.user_id AND s.active=1 "
            "AND (ro_norm(s.name) LIKE ? OR ro_norm(s.category) LIKE ?)))"
        )
        args += [like] * 5
    sql += " ORDER BY (p.plan='pro') DESC, p.rating_avg DESC, p.rating_count DESC"
    return {"professionals": [_public_pro(conn, r, category) for r in conn.execute(sql, args)]}


def get_professional(conn, pro_id):
    r = conn.execute(_PRO_JOIN + " AND p.user_id=?", (pro_id,)).fetchone()
    if not r:
        raise ApiError(404, "not_found", "Meșterul nu a fost găsit.")
    return {"professional": _public_pro(conn, r, detail=True)}


# ----------------------------------------- bookings, estimates & calendar
def _validate_photos(photos):
    if photos is None:
        return []
    if not isinstance(photos, list) or len(photos) > 4:
        raise bad("Poți atașa maximum 4 fotografii.", "photos")
    for p in photos:
        if not isinstance(p, str) or not PHOTO_RE.match(p) or len(p) > config.MAX_PHOTO_CHARS:
            raise bad("Fotografiile trebuie să fie PNG/JPEG/WebP sub ~1 MB fiecare.", "photos")
    return photos


def _estimate_view(row) -> dict:
    return {
        "id": row["id"],
        "booking_id": row["booking_id"],
        "pro_id": row["pro_id"],
        "price_ron": row["price_ron"],
        "price_max_ron": row["price_max_ron"],
        "duration_minutes": row["duration_minutes"],
        "duration_label": row["duration_label"],
        "proposed_start_at": row["proposed_start_at"],
        "proposed_end_at": row["proposed_end_at"],
        "slot_label": row["slot_label"],
        "pro_notes": row["pro_notes"],
        "status": row["status"],
        "expires_at": row["expires_at"],
        "created_at": row["created_at"],
    }


def create_booking(conn, ctx, user, data):
    require_role(user, "client")
    ctx.limiter.check(f"booking:{user['id']}", 15, 3600, "Ai trimis prea multe solicitări într-o oră.")
    v = Validator(data)
    service_id = v.text("service_id", max=40, label="Serviciul")
    desc = v.text("description", min=10, max=1500, label="Descrierea")
    sched = v.text("scheduled_for", max=80, required=False, label="Programarea")
    u_keys = user.keys() if hasattr(user, "keys") else {}
    u_addr = user["address"] if "address" in u_keys else None
    u_phone = user["phone"] if "phone" in u_keys else None
    neighborhood = v.text("neighborhood", max=60, required=False, label="Cartierul") or (user["neighborhood"] if "neighborhood" in u_keys else None) or "Hipodrom"
    address = v.text("address", max=120, required=False, label="Adresa") or u_addr
    phone = v.phone("phone", required=False, label="Telefonul") or u_phone
    urgency = v.choice("urgency_level", ("normal", "urgent_today"), required=False, label="Urgența") or "normal"
    preferred_window = v.text("preferred_window", max=80, required=False, label="Intervalul preferat") or sched or "Mâine, 09:00–13:00"
    v.done()
    photos = _validate_photos(data.get("photos"))
    s = conn.execute(
        "SELECT s.*, p.verification_status, u.is_active FROM pro_services s JOIN pro_profiles p ON p.user_id=s.pro_id "
        "JOIN users u ON u.id=s.pro_id WHERE s.id=?",
        (service_id,),
    ).fetchone()
    if not s or not s["active"] or s["verification_status"] != "verified" or not s["is_active"]:
        raise ApiError(404, "service_unavailable", "Serviciul selectat nu mai este disponibil.")
    bid, t = new_id("b_"), now_ts()
    est_min = s["est_duration_min"] if "est_duration_min" in s.keys() else 60
    conn.execute(
        "INSERT INTO bookings (id,client_id,pro_id,service_id,category,service_name,price_label,description,"
        "neighborhood,client_address,client_phone,urgency_level,preferred_window,status,duration_minutes,scheduled_for,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            bid,
            user["id"],
            s["pro_id"],
            s["id"],
            s["category"],
            s["name"],
            f"de la {s['price_from']} {s['price_unit']}",
            desc,
            neighborhood,
            address,
            phone,
            urgency,
            preferred_window,
            "pending",
            est_min,
            sched or preferred_window,
            t,
            t,
        ),
    )
    for p in photos:
        conn.execute("INSERT INTO booking_photos (booking_id,data_url) VALUES (?,?)", (bid, p))
    conn.execute(
        "INSERT INTO booking_events (booking_id,actor_id,from_status,to_status,at) VALUES (?,?,NULL,'pending',?)",
        (bid, user["id"], t),
    )
    notify(
        conn,
        s["pro_id"],
        "booking_new",
        "Cerere nouă în Sibiu (" + neighborhood + ")",
        f"{user['name']} a solicitat „{s['name']}” ({preferred_window}). Trimite o estimare din 2 click-uri!",
        bid,
    )
    analytics.track(
        conn,
        user["id"],
        "client",
        "booking_requested",
        {"booking_id": bid, "category": s["category"], "neighborhood": neighborhood, "urgency": urgency},
    )
    conn.commit()
    return {"booking": _booking_view(conn, _booking_row(conn, bid), user, detail=True)}


def _booking_row(conn, bid):
    return conn.execute(
        "SELECT b.*, c.name AS client_name, COALESCE(b.client_phone, c.phone) AS client_phone, "
        "COALESCE(b.client_address, c.address) AS client_address, "
        "c.neighborhood AS client_neighborhood, pr.name AS pro_name, pr.phone AS pro_phone, pp.company_name AS pro_company "
        "FROM bookings b JOIN users c ON c.id=b.client_id JOIN users pr ON pr.id=b.pro_id "
        "LEFT JOIN pro_profiles pp ON pp.user_id=b.pro_id WHERE b.id=?",
        (bid,),
    ).fetchone()


def _booking_view(conn, b, viewer, detail=False):
    review = conn.execute("SELECT rating, comment FROM reviews WHERE booking_id=?", (b["id"],)).fetchone()
    latest_est = conn.execute(
        "SELECT * FROM estimates WHERE booking_id=? ORDER BY created_at DESC LIMIT 1",
        (b["id"],),
    ).fetchone()
    sms_list = sms.list_booking_sms(conn, b["id"])
    neighborhood = b["neighborhood"] if "neighborhood" in b.keys() and b["neighborhood"] else "Sibiu"
    pro_phone = b["pro_phone"] if "pro_phone" in b.keys() else None
    out = {
        "id": b["id"],
        "status": b["status"],
        "category": b["category"],
        "service_name": b["service_name"],
        "price_label": b["price_label"],
        "description": b["description"],
        "neighborhood": neighborhood,
        "urgency_level": b["urgency_level"] if "urgency_level" in b.keys() else "normal",
        "preferred_window": b["preferred_window"] if "preferred_window" in b.keys() else b["scheduled_for"],
        "quote_price": b["quote_price"],
        "quote_price_max": b["quote_price_max"] if "quote_price_max" in b.keys() else None,
        "quote_duration": b["quote_duration"],
        "duration_minutes": b["duration_minutes"] if "duration_minutes" in b.keys() else 60,
        "pro_notes": b["pro_notes"] if "pro_notes" in b.keys() else None,
        "scheduled_for": b["scheduled_for"],
        "scheduled_start_at": b["scheduled_start_at"] if "scheduled_start_at" in b.keys() else None,
        "scheduled_end_at": b["scheduled_end_at"] if "scheduled_end_at" in b.keys() else None,
        "created_at": b["created_at"],
        "ago": ago(b["created_at"]),
        "time_label": b["scheduled_for"] or hhmm(b["created_at"]),
        "client": {
            "id": b["client_id"],
            "name": b["client_name"],
            "neighborhood": neighborhood,
            "address": b["client_address"] or f"{neighborhood}, Sibiu",
        },
        "professional": {
            "id": b["pro_id"],
            "name": b["pro_name"],
            "company_name": b["pro_company"] if "pro_company" in b.keys() else "",
            "initials": initials(b["pro_name"]),
            "phone": pro_phone if (b["status"] in ("accepted", "completed") or viewer["role"] in ("pro", "admin")) else None,
        },
        "estimate": _estimate_view(latest_est) if latest_est else None,
        "sms_reminders": sms_list,
        "review": dict(review) if review else None,
        "can_review": b["status"] == "completed" and review is None and viewer["id"] == b["client_id"],
        "client_address": b["client_address"] if "client_address" in b.keys() else None,
        "client_phone": b["client_phone"] if "client_phone" in b.keys() and (viewer["role"] != "client" or viewer["id"] == b["client_id"]) else None,
    }
    if viewer["role"] != "client" and b["status"] in ("estimated", "accepted", "completed"):
        out["client"]["phone"] = b["client_phone"]
    if detail:
        out["photos"] = [
            r["data_url"]
            for r in conn.execute("SELECT data_url FROM booking_photos WHERE booking_id=? ORDER BY id", (b["id"],))
        ]
        out["events"] = [
            dict(r)
            for r in conn.execute(
                "SELECT from_status, to_status, at FROM booking_events WHERE booking_id=? ORDER BY id",
                (b["id"],),
            )
        ]
    return out


def list_bookings(conn, user, status=None):
    col = {"client": "b.client_id", "pro": "b.pro_id"}.get(user["role"])
    sql = (
        "SELECT b.*, c.name AS client_name, COALESCE(b.client_phone, c.phone) AS client_phone, "
        "COALESCE(b.client_address, c.address) AS client_address, "
        "c.neighborhood AS client_neighborhood, pr.name AS pro_name, pr.phone AS pro_phone, pp.company_name AS pro_company "
        "FROM bookings b JOIN users c ON c.id=b.client_id JOIN users pr ON pr.id=b.pro_id "
        "LEFT JOIN pro_profiles pp ON pp.user_id=b.pro_id"
    )
    args = []
    if col:
        sql += f" WHERE {col}=?"
        args.append(user["id"])
        if status:
            sql += " AND b.status=?"
            args.append(status)
    sql += " ORDER BY b.created_at DESC LIMIT 200"
    return {"bookings": [_booking_view(conn, b, user) for b in conn.execute(sql, args)]}


def get_booking(conn, user, bid):
    b = _booking_row(conn, bid)
    if not b or (user["role"] != "admin" and user["id"] not in (b["client_id"], b["pro_id"])):
        raise ApiError(404, "not_found", "Programarea nu a fost găsită.")
    return {"booking": _booking_view(conn, b, user, detail=True)}


def _transition(conn, user, bid, to, allowed_from, who, **sets):
    b = _booking_row(conn, bid)
    if not b or (user["role"] != "admin" and user["id"] not in (b["client_id"], b["pro_id"])):
        raise ApiError(404, "not_found", "Programarea nu a fost găsită.")
    role_of_user = "admin" if user["role"] == "admin" else ("client" if user["id"] == b["client_id"] else "pro")
    if role_of_user not in who and role_of_user != "admin":
        raise ApiError(403, "forbidden", "Nu poți efectua această acțiune asupra programării.")
    if b["status"] not in allowed_from:
        raise ApiError(409, "invalid_transition", f"Acțiune imposibilă: programarea este deja „{b['status']}”.")
    t = now_ts()
    cols = ", ".join(f"{k}=?" for k in sets)
    conn.execute(
        f"UPDATE bookings SET status=?, updated_at=?{', ' + cols if cols else ''} WHERE id=?",
        (to, t, *sets.values(), bid),
    )
    conn.execute(
        "INSERT INTO booking_events (booking_id,actor_id,from_status,to_status,at) VALUES (?,?,?,?,?)",
        (bid, user["id"], b["status"], to, t),
    )
    return b, role_of_user


def send_estimate(conn, user, bid, data):
    """3-Step Flexible Estimate Workflow (Step 2: Pro sends Price + Duration + Proposed Slot -> status='estimated')."""
    require_role(user, "pro")
    v = Validator(data)
    price = v.integer("price", min=1, max=100000, label="Prețul estimat")
    price_max = v.integer("price_max", min=1, max=100000, required=False, label="Prețul maxim")
    duration = v.text("duration", min=2, max=60, required=False, label="Durata")
    duration_min = v.integer("duration_minutes", min=15, max=720, required=False, label="Durata în minute")
    notes = v.text("pro_notes", max=500, required=False, label="Detalii estimare")
    proposed_start_at = v.integer("proposed_start_at", min=1, max=4102444800, required=False, label="Data și ora")
    v.done()

    dur_m = parse_duration_minutes(duration, duration_min)
    dur_lbl = duration or duration_label_of(dur_m)

    b_row = _booking_row(conn, bid)
    if not b_row or b_row["pro_id"] != user["id"]:
        raise ApiError(404, "not_found", "Programarea nu a fost găsită.")

    if proposed_start_at:
        start_ts, end_ts = proposed_start_at, proposed_start_at + dur_m * 60
    else:
        start_ts, end_ts = default_next_free_slot(conn, user["id"], dur_m)
    conflict = has_slot_conflict(conn, user["id"], start_ts, end_ts, exclude_booking_id=bid)
    if conflict:
        raise ApiError(
            409,
            "slot_conflict",
            f"Intervalul selectat se suprapune cu lucrarea „{conflict['service_name']}” ({conflict['scheduled_for']}). Alege altă oră.",
        )

    slot_lbl = data.get("slot_label") or sms.format_ro_slot(start_ts, end_ts)
    b, _ = _transition(
        conn,
        user,
        bid,
        "estimated",
        ("pending", "estimated"),
        ("pro",),
        quote_price=price,
        quote_price_max=price_max,
        quote_duration=dur_lbl,
        duration_minutes=dur_m,
        pro_notes=notes,
        scheduled_for=slot_lbl,
        scheduled_start_at=start_ts,
        scheduled_end_at=end_ts,
    )

    conn.execute("UPDATE estimates SET status='superseded' WHERE booking_id=? AND status='sent'", (bid,))
    est_id = new_id("est_")
    t = now_ts()
    conn.execute(
        "INSERT INTO estimates (id,booking_id,pro_id,price_ron,price_max_ron,duration_minutes,duration_label,"
        "proposed_start_at,proposed_end_at,slot_label,pro_notes,status,expires_at,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,'sent',?,?)",
        (est_id, bid, user["id"], price, price_max, dur_m, dur_lbl, start_ts, end_ts, slot_lbl, notes, t + 12 * HOUR, t),
    )

    notify(
        conn,
        b["client_id"],
        "estimate_received",
        "Estimare nouă primită",
        f"{user['name']} a trimis devizul: {price} RON ({dur_lbl}) pentru {slot_lbl}. Apasă Acceptă pentru a bloca ora!",
        bid,
    )
    sms.send_instant_sms(
        conn,
        bid,
        b["client_phone"],
        "estimate_ready",
        f"REZOLV Sibiu: {user['name']} ({b['pro_company'] or 'Meșter Verificat'}) a trimis o estimare pentru "
        f"„{b['service_name']}”: {price} RON, durată {dur_lbl}, pe {slot_lbl}. Confirmă din aplicație pentru a bloca slotul!",
    )
    analytics.track(
        conn,
        user["id"],
        "pro",
        "estimate_sent",
        {"booking_id": bid, "estimate_id": est_id, "price_ron": price, "duration_minutes": dur_m},
    )
    conn.commit()
    return get_booking(conn, user, bid)


def accept_estimate(conn, user, bid, data=None):
    """Step 3 of Estimate Flow: Client accepts the Pro's Estimate -> Locks slot in Calendar + Queues 24h & 2h SMS."""
    require_role(user, "client", "admin")
    b = _booking_row(conn, bid)
    if not b or (user["role"] != "admin" and b["client_id"] != user["id"]):
        raise ApiError(404, "not_found", "Programarea nu a fost găsită.")
    if b["status"] not in ("estimated", "pending"):
        raise ApiError(409, "invalid_transition", f"Estimarea nu poate fi acceptată din starea „{b['status']}”.")

    est = conn.execute(
        "SELECT * FROM estimates WHERE booking_id=? AND status='sent' ORDER BY created_at DESC LIMIT 1",
        (bid,),
    ).fetchone()
    if est and est["expires_at"] and est["expires_at"] < now_ts():
        conn.execute("UPDATE estimates SET status='expired' WHERE id=?", (est["id"],))
        conn.commit()
        raise ApiError(409, "estimate_expired", "Această estimare a expirat. Te rugăm să soliciți o nouă estimare de la meșter.")

    dur_m = est["duration_minutes"] if est else (b["duration_minutes"] or 60)
    price = est["price_ron"] if est else (b["quote_price"] or 150)
    dur_lbl = est["duration_label"] if est else (b["quote_duration"] or duration_label_of(dur_m))
    start_ts = est["proposed_start_at"] if est else b["scheduled_start_at"]
    end_ts = est["proposed_end_at"] if est else b["scheduled_end_at"]
    if not (start_ts and end_ts):
        start_ts, end_ts = default_next_free_slot(conn, b["pro_id"], dur_m)

    # Atomic Double-Booking Check before locking the calendar slot
    conflict = has_slot_conflict(conn, b["pro_id"], start_ts, end_ts, exclude_booking_id=bid)
    if conflict:
        raise ApiError(
            409,
            "slot_conflict",
            "Acest interval orar a fost ocupat între timp. Cere meșterului o altă oră disponibilă.",
        )

    slot_lbl = est["slot_label"] if est else sms.format_ro_slot(start_ts, end_ts)
    t = now_ts()
    _transition(
        conn,
        user,
        bid,
        "accepted",
        ("estimated", "pending"),
        ("client", "admin"),
        quote_price=price,
        quote_duration=dur_lbl,
        duration_minutes=dur_m,
        scheduled_for=slot_lbl,
        scheduled_start_at=start_ts,
        scheduled_end_at=end_ts,
        accepted_estimate_id=est["id"] if est else None,
    )
    if est:
        conn.execute("UPDATE estimates SET status='accepted', responded_at=? WHERE id=?", (t, est["id"]))

    notify(
        conn,
        b["pro_id"],
        "estimate_accepted",
        "Estimare ACCEPTATĂ • Slot blocat în Calendar",
        f"{b['client_name']} a acceptat devizul de {price} RON ({dur_lbl}). Slotul {slot_lbl} este blocat în calendarul tău!",
        bid,
    )

    # Schedule Anti-No-Show Twilio SMS Reminders (Immediate + T-24h + T-2h)
    sms.schedule_anti_noshow_reminders(
        conn,
        bid,
        b["client_phone"],
        b["pro_name"],
        b["pro_company"] or "Meșter REZOLV Sibiu",
        b["service_name"],
        price,
        start_ts,
        end_ts,
    )
    analytics.track(
        conn,
        user["id"],
        user["role"],
        "estimate_accepted",
        {"booking_id": bid, "price_ron": price, "duration_minutes": dur_m, "slot_locked": slot_lbl},
    )
    conn.commit()
    return get_booking(conn, user, bid)


def decline_estimate(conn, user, bid, data=None):
    """Client declines or asks for another slot -> returns booking to 'pending'."""
    require_role(user, "client")
    b = _booking_row(conn, bid)
    if not b or b["client_id"] != user["id"]:
        raise ApiError(404, "not_found", "Programarea nu a fost găsită.")
    if b["status"] != "estimated":
        raise ApiError(409, "invalid_transition", "Nu există o estimare activă de revizuit.")
    reason = (data or {}).get("reason") or "Clientul a solicitat altă oră sau revizuirea estimării."
    t = now_ts()
    conn.execute("UPDATE estimates SET status='declined', responded_at=? WHERE booking_id=? AND status='sent'", (t, bid))
    _transition(conn, user, bid, "pending", ("estimated",), ("client",), pro_notes=reason[:300])
    notify(
        conn,
        b["pro_id"],
        "estimate_declined",
        "Clientul cere altă oră / ofertă",
        f"{b['client_name']} a cerut reprogramarea estimării: {reason[:120]}",
        bid,
    )
    analytics.track(conn, user["id"], "client", "estimate_declined", {"booking_id": bid})
    conn.commit()
    return get_booking(conn, user, bid)


def quote_booking(conn, user, bid, data):
    """Supports both 3-step estimate mode (`mode='estimate'`) and 2-click direct confirmation."""
    require_role(user, "pro")
    if isinstance(data, dict) and data.get("mode") == "estimate":
        return send_estimate(conn, user, bid, data)

    v = Validator(data)
    price = v.integer("price", min=1, max=100000, label="Prețul")
    duration = v.text("duration", min=2, max=60, label="Durata")
    v.done()

    dur_m = parse_duration_minutes(duration, data.get("duration_minutes") if isinstance(data, dict) else None)
    b_check = _booking_row(conn, bid)
    if not b_check or b_check["pro_id"] != user["id"]:
        raise ApiError(404, "not_found", "Programarea nu a fost găsită.")

    pref_ts = data.get("proposed_start_at") if isinstance(data, dict) else None
    start_ts, end_ts = default_next_free_slot(conn, user["id"], dur_m, pref_ts)
    slot_lbl = b_check["scheduled_for"] or sms.format_ro_slot(start_ts, end_ts)

    b, _ = _transition(
        conn,
        user,
        bid,
        "accepted",
        ("pending", "estimated"),
        ("pro",),
        quote_price=price,
        quote_duration=duration,
        duration_minutes=dur_m,
        scheduled_for=slot_lbl,
        scheduled_start_at=start_ts,
        scheduled_end_at=end_ts,
    )
    t = now_ts()
    est_id = new_id("est_")
    conn.execute(
        "INSERT INTO estimates (id,booking_id,pro_id,price_ron,duration_minutes,duration_label,"
        "proposed_start_at,proposed_end_at,slot_label,status,expires_at,created_at,responded_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,'accepted',?,?,?)",
        (est_id, bid, user["id"], price, dur_m, duration, start_ts, end_ts, slot_lbl, t + 12 * HOUR, t, t),
    )
    notify(
        conn,
        b["client_id"],
        "booking_accepted",
        "Cerere acceptată",
        f"{user['name']} a confirmat {price} RON, durată {duration} ({slot_lbl}).",
        bid,
    )
    sms.schedule_anti_noshow_reminders(
        conn,
        bid,
        b["client_phone"],
        user["name"],
        b["pro_company"] or "Meșter REZOLV Sibiu",
        b["service_name"],
        price,
        start_ts,
        end_ts,
    )
    analytics.track(conn, user["id"], "pro", "booking_fast_accepted", {"booking_id": bid, "price_ron": price})
    conn.commit()
    return get_booking(conn, user, bid)


def reschedule_booking(conn, user, bid, data):
    """2-Click Calendar Reschedule for Pro or Client. Recalculates slot + 24h & 2h SMS reminders."""
    b = _booking_row(conn, bid)
    if not b or (user["role"] != "admin" and user["id"] not in (b["client_id"], b["pro_id"])):
        raise ApiError(404, "not_found", "Programarea nu a fost găsită.")
    if b["status"] not in ("accepted", "estimated", "pending"):
        raise ApiError(409, "invalid_transition", "Doar programările active pot fi reprogramate.")

    v = Validator(data)
    new_start = v.integer("start_at", min=1, max=4102444800, required=False, label="Noua oră")
    shift_hours = v.integer("shift_hours", min=-48, max=168, required=False, label="Decalaj ore")
    duration_min = v.integer("duration_minutes", min=15, max=720, required=False, label="Durata")
    v.done()

    dur_m = duration_min or b["duration_minutes"] or 60
    base_start = b["scheduled_start_at"] or default_next_free_slot(conn, b["pro_id"], dur_m)[0]
    if new_start:
        start_ts = new_start
    elif shift_hours:
        start_ts = base_start + shift_hours * HOUR
    else:
        raise bad("Selectează noua oră din calendar.", "start_at")

    end_ts = start_ts + dur_m * 60
    conflict = has_slot_conflict(conn, b["pro_id"], start_ts, end_ts, exclude_booking_id=bid)
    if conflict:
        raise ApiError(
            409,
            "slot_conflict",
            f"Slotul este deja ocupat de „{conflict['service_name']}” ({conflict['scheduled_for']}).",
        )

    slot_lbl = data.get("slot_label") or sms.format_ro_slot(start_ts, end_ts)
    t = now_ts()
    conn.execute(
        "UPDATE bookings SET scheduled_start_at=?, scheduled_end_at=?, scheduled_for=?, duration_minutes=?, updated_at=? WHERE id=?",
        (start_ts, end_ts, slot_lbl, dur_m, t, bid),
    )
    conn.execute(
        "UPDATE estimates SET proposed_start_at=?, proposed_end_at=?, slot_label=? WHERE booking_id=? AND status IN ('sent','accepted')",
        (start_ts, end_ts, slot_lbl, bid),
    )
    other = b["client_id"] if user["id"] == b["pro_id"] else b["pro_id"]
    notify(
        conn,
        other,
        "booking_rescheduled",
        "Programare reprogramată în Calendar",
        f"{user['name']} a mutat lucrarea „{b['service_name']}” pe {slot_lbl}.",
        bid,
    )
    if b["status"] == "accepted":
        sms.schedule_anti_noshow_reminders(
            conn,
            bid,
            b["client_phone"],
            b["pro_name"],
            b["pro_company"] or "Meșter REZOLV Sibiu",
            b["service_name"],
            b["quote_price"] or 150,
            start_ts,
            end_ts,
            is_reschedule=True,
        )
    analytics.track(conn, user["id"], user["role"], "booking_rescheduled_2click", {"booking_id": bid, "new_slot": slot_lbl})
    conn.commit()
    return get_booking(conn, user, bid)


def refuse_booking(conn, user, bid):
    require_role(user, "pro")
    b, _ = _transition(conn, user, bid, "refused", ("pending", "estimated"), ("pro",))
    conn.execute("UPDATE estimates SET status='expired' WHERE booking_id=? AND status='sent'", (bid,))
    notify(
        conn,
        b["client_id"],
        "booking_refused",
        "Cerere refuzată",
        f"{user['name']} nu poate prelua „{b['service_name']}”. Alege alt meșter din Sibiu.",
        bid,
    )
    analytics.track(conn, user["id"], "pro", "booking_refused", {"booking_id": bid})
    conn.commit()
    return get_booking(conn, user, bid)


def cancel_booking(conn, user, bid):
    b, who = _transition(conn, user, bid, "cancelled", ("pending", "estimated", "accepted"), ("client", "pro"))
    conn.execute("UPDATE sms_reminders SET status='cancelled' WHERE booking_id=? AND status='scheduled'", (bid,))
    conn.execute("UPDATE estimates SET status='expired' WHERE booking_id=? AND status='sent'", (bid,))
    other = b["pro_id"] if who == "client" else b["client_id"]
    notify(
        conn,
        other,
        "booking_cancelled",
        "Programare anulată",
        f"{user['name']} a anulat „{b['service_name']}”. Slotul din calendar a fost eliberat.",
        bid,
    )
    analytics.track(conn, user["id"], who, "booking_cancelled", {"booking_id": bid})
    conn.commit()
    return get_booking(conn, user, bid)


def complete_booking(conn, user, bid):
    require_role(user, "pro")
    t = now_ts()
    b, _ = _transition(conn, user, bid, "completed", ("accepted",), ("pro",), completed_at=t)
    conn.execute("UPDATE pro_profiles SET jobs_completed=jobs_completed+1 WHERE user_id=?", (user["id"],))
    conn.execute("UPDATE sms_reminders SET status='cancelled' WHERE booking_id=? AND status='scheduled'", (bid,))
    notify(
        conn,
        b["client_id"],
        "booking_completed",
        "Lucrare finalizată",
        "Spune-ne cum a fost experiența cu meșterul.",
        bid,
    )
    analytics.track(conn, user["id"], "pro", "booking_completed", {"booking_id": bid, "price_ron": b["quote_price"]})
    conn.commit()
    return get_booking(conn, user, bid)


def mark_no_show(conn, user, bid):
    require_role(user, "pro", "admin")
    b, who = _transition(conn, user, bid, "no_show", ("accepted",), ("pro", "admin"))
    conn.execute("UPDATE sms_reminders SET status='cancelled' WHERE booking_id=? AND status='scheduled'", (bid,))
    notify(
        conn,
        b["client_id"],
        "booking_no_show",
        "Programare marcată ca neprezentare",
        f"Meșterul a semnalat neprezentarea la adresa programată pentru „{b['service_name']}”.",
        bid,
    )
    analytics.track(conn, user["id"], who, "booking_no_show", {"booking_id": bid})
    conn.commit()
    return get_booking(conn, user, bid)


def review_booking(conn, user, bid, data):
    require_role(user, "client")
    v = Validator(data)
    rating = v.integer("rating", min=1, max=5, label="Evaluarea")
    comment = v.text("comment", max=1000, required=False, label="Comentariul")
    v.done()
    b = _booking_row(conn, bid)
    if not b or b["client_id"] != user["id"]:
        raise ApiError(404, "not_found", "Programarea nu a fost găsită.")
    if b["status"] != "completed":
        raise ApiError(409, "not_completed", "Poți evalua doar lucrările finalizate.")
    if conn.execute("SELECT 1 FROM reviews WHERE booking_id=?", (bid,)).fetchone():
        raise ApiError(409, "already_reviewed", "Ai evaluat deja această lucrare.")
    conn.execute(
        "INSERT INTO reviews VALUES (?,?,?,?,?,?,?)",
        (new_id("r_"), bid, user["id"], b["pro_id"], rating, comment, now_ts()),
    )
    conn.execute(
        "UPDATE pro_profiles SET rating_avg=(rating_avg*rating_count+?)/(rating_count+1), "
        "rating_count=rating_count+1 WHERE user_id=?",
        (rating, b["pro_id"]),
    )
    notify(conn, b["pro_id"], "review", "Recenzie nouă", f"Ai primit {rating}★ de la {user['name']}.", bid)
    analytics.track(conn, user["id"], "client", "review_submitted", {"booking_id": bid, "rating": rating})
    conn.commit()
    return get_booking(conn, user, bid)


def trigger_booking_sms_now(conn, user, bid):
    """Trigger scheduled 24h & 2h SMS reminders immediately (for investor live demo)."""
    b = _booking_row(conn, bid)
    if not b or (user["role"] != "admin" and user["id"] not in (b["client_id"], b["pro_id"])):
        raise ApiError(404, "not_found", "Programarea nu a fost găsită.")
    sent = sms.process_due_reminders(conn, force_booking_id=bid)
    analytics.track(conn, user["id"], user["role"], "sms_reminder_triggered", {"booking_id": bid, "count": len(sent)})
    return {"dispatched": sent, "booking": _booking_view(conn, b, user, detail=True)}


# ------------------------------------------------------------ pro workspace & B2B calendar
def _own_profile(conn, user):
    require_role(user, "pro")
    return conn.execute("SELECT * FROM pro_profiles WHERE user_id=?", (user["id"],)).fetchone()


def _require_verified(p):
    if p["verification_status"] != "verified":
        raise ApiError(403, "not_verified", "Profilul tău trebuie verificat înainte de publicare.")


def pro_calendar(conn, user, days_count: int = 5):
    """Build a 5-to-7 day mobile-first B2B Calendar grid with free slots & locked bookings."""
    _own_profile(conn, user)
    now_dt = datetime.now()
    days_ro = ["Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică"]
    months_ro = ["Ian", "Feb", "Mar", "Apr", "Mai", "Iun", "Iul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    all_active = [
        _booking_view(conn, b, user, detail=True)
        for b in conn.execute(
            "SELECT b.*, c.name AS client_name, c.phone AS client_phone, c.address AS client_address, "
            "c.neighborhood AS client_neighborhood, pr.name AS pro_name, pp.company_name AS pro_company "
            "FROM bookings b JOIN users c ON c.id=b.client_id JOIN users pr ON pr.id=b.pro_id "
            "LEFT JOIN pro_profiles pp ON pp.user_id=b.pro_id "
            "WHERE b.pro_id=? AND b.status IN ('accepted','estimated','completed') "
            "ORDER BY COALESCE(b.scheduled_start_at, b.updated_at) ASC",
            (user["id"],),
        )
    ]

    calendar_days = []
    quick_free_slots = []
    for d_idx in range(days_count):
        dt = now_dt + timedelta(days=d_idx)
        day_start = int(datetime(dt.year, dt.month, dt.day, 0, 0, 0).timestamp())
        day_end = day_start + DAY
        day_name = "Azi" if d_idx == 0 else ("Mâine" if d_idx == 1 else days_ro[dt.weekday()])
        date_short = f"{dt.day} {months_ro[dt.month - 1]}"

        slots = []
        for hour in (8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18):
            slot_start = int(datetime(dt.year, dt.month, dt.day, hour, 0, 0).timestamp())
            slot_end = slot_start + HOUR
            matched_booking = None
            for bk in all_active:
                b_start = bk.get("scheduled_start_at")
                b_end = bk.get("scheduled_end_at") or ((b_start + HOUR) if b_start else None)
                if b_start and b_end and b_start < slot_end and b_end > slot_start:
                    matched_booking = bk
                    break
            is_free = matched_booking is None and slot_start > now_ts() - 1800
            slot_label = f"{day_name} ({date_short}), {hour:02d}:00"
            slot_obj = {
                "hour": f"{hour:02d}:00",
                "start_at": slot_start,
                "end_at": slot_end,
                "label": slot_label,
                "status": matched_booking["status"] if matched_booking else ("free" if is_free else "past"),
                "booking": matched_booking,
            }
            slots.append(slot_obj)
            if is_free and len(quick_free_slots) < 8 and hour in (9, 10, 11, 14, 15, 16):
                quick_free_slots.append({
                    "start_at": slot_start,
                    "label": f"{day_name}, {hour:02d}:00",
                    "full_label": f"{day_name} ({date_short}), {hour:02d}:00",
                })

        calendar_days.append({
            "day_offset": d_idx,
            "date_iso": dt.strftime("%Y-%m-%d"),
            "day_name": day_name,
            "date_short": date_short,
            "slots": slots,
        })

    return {"days": calendar_days, "quick_free_slots": quick_free_slots}


def pro_dashboard(conn, user):
    p = _own_profile(conn, user)
    t = now_ts()

    def revenue(a, b):
        return conn.execute(
            "SELECT COALESCE(SUM(quote_price),0) s, COUNT(*) c FROM bookings WHERE pro_id=? AND "
            "status='completed' AND completed_at>=? AND completed_at<?",
            (user["id"], a, b),
        ).fetchone()

    this, prev = revenue(t - 7 * DAY, t + 1), revenue(t - 14 * DAY, t - 7 * DAY)
    change = round((this["s"] - prev["s"]) * 100 / prev["s"]) if prev["s"] else None
    pend = [
        _booking_view(conn, b, user, detail=True)
        for b in conn.execute(
            "SELECT b.*, c.name AS client_name, c.phone AS client_phone, c.address AS client_address, "
            "c.neighborhood AS client_neighborhood, pr.name AS pro_name, pp.company_name AS pro_company "
            "FROM bookings b JOIN users c ON c.id=b.client_id JOIN users pr ON pr.id=b.pro_id "
            "LEFT JOIN pro_profiles pp ON pp.user_id=b.pro_id "
            "WHERE b.pro_id=? AND b.status IN ('pending','estimated') ORDER BY (b.status='pending') DESC, b.created_at DESC",
            (user["id"],),
        )
    ]
    sched = [
        _booking_view(conn, b, user, detail=True)
        for b in conn.execute(
            "SELECT b.*, c.name AS client_name, c.phone AS client_phone, c.address AS client_address, "
            "c.neighborhood AS client_neighborhood, pr.name AS pro_name, pp.company_name AS pro_company "
            "FROM bookings b JOIN users c ON c.id=b.client_id JOIN users pr ON pr.id=b.pro_id "
            "LEFT JOIN pro_profiles pp ON pp.user_id=b.pro_id "
            "WHERE b.pro_id=? AND (b.status='accepted' OR (b.status='completed' AND b.completed_at>=?)) "
            "ORDER BY COALESCE(b.scheduled_start_at, b.updated_at) ASC",
            (user["id"], t - DAY),
        )
    ]
    renew = max(0, (p["plan_renews_at"] - t) // DAY) if p["plan_renews_at"] else None
    cal = pro_calendar(conn, user, days_count=5)
    analytics.track(conn, user["id"], "pro", "pro_dashboard_viewed", {"city": "Sibiu"})
    conn.commit()
    return {
        "week": {"revenue": this["s"], "jobs": this["c"], "change_pct": change},
        "plan": {
            "plan": p["plan"],
            "status": p["plan_status"],
            "price_eur": p["subscription_price_eur"] if "subscription_price_eur" in p.keys() else 39,
            "renews_in_days": renew,
        },
        "pending": pend,
        "schedule": sched,
        "calendar": cal,
        "verification_status": p["verification_status"],
        "unread_notifications": conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (user["id"],)
        ).fetchone()[0],
    }


def pro_categories(conn, user):
    _own_profile(conn, user)
    cats = []
    for c in conn.execute("SELECT * FROM categories ORDER BY sort"):
        rows = conn.execute(
            "SELECT * FROM pro_services WHERE pro_id=? AND category=?", (user["id"], c["name"])
        ).fetchall()
        if not rows:
            continue
        active = [r for r in rows if r["active"]]
        low = min(r["price_from"] for r in rows)
        cats.append({
            "category": c["name"],
            "icon": c["icon"],
            "tone": c["tone"],
            "enabled": bool(active),
            "price_label": c["price_label"],
            "from_price": low,
            "count": len(rows),
            "services": [_service_view(r) for r in rows],
        })
    return {"categories": cats}


def set_category_enabled(conn, user, name, data):
    p = _own_profile(conn, user)
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        raise bad("Valoarea 'enabled' trebuie să fie true/false.", "enabled")
    if not conn.execute("SELECT 1 FROM categories WHERE name=?", (name,)).fetchone():
        raise ApiError(404, "not_found", "Categoria nu există.")
    if enabled:
        _require_verified(p)
    conn.execute("UPDATE pro_services SET active=? WHERE pro_id=? AND category=?", (1 if enabled else 0, user["id"], name))
    observability.CACHE.invalidate()
    conn.commit()
    return pro_categories(conn, user)


def add_service(conn, user, data):
    p = _own_profile(conn, user)
    _require_verified(p)
    v = Validator(data)
    name = v.text("name", min=3, max=80, label="Denumirea serviciului")
    price = v.integer("price_from", min=1, max=100000, label="Tariful")
    unit = v.choice("unit", ("RON", "RON/mp", "RON/oră"), required=False, label="Unitatea") or "RON"
    duration = v.text("duration", max=60, required=False, label="Durata") or "1–2 ore"
    category = v.text("category", max=60, required=False, label="Categoria")
    v.done()
    if category is None:
        row = conn.execute(
            "SELECT category FROM pro_services WHERE pro_id=? ORDER BY active DESC, rowid LIMIT 1",
            (user["id"],),
        ).fetchone()
        category = row["category"] if row else "Instalații Sanitare"
    if not conn.execute("SELECT 1 FROM categories WHERE name=?", (category,)).fetchone():
        raise bad("Categorie necunoscută.", "category")
    if conn.execute("SELECT COUNT(*) FROM pro_services WHERE pro_id=?", (user["id"],)).fetchone()[0] >= 60:
        raise ApiError(409, "limit", "Ai atins numărul maxim de servicii.")
    est_min = parse_duration_minutes(duration)
    conn.execute(
        "INSERT INTO pro_services (id,pro_id,category,name,price_from,price_unit,duration,est_duration_min,active) "
        "VALUES (?,?,?,?,?,?,?,?,1)",
        (new_id("s_"), user["id"], category, name, price, unit, duration, est_min),
    )
    observability.CACHE.invalidate()
    conn.commit()
    return pro_categories(conn, user)


def update_pro_profile(conn, user, data):
    _own_profile(conn, user)
    v = Validator(data)
    headline = v.text("headline", max=120, required=False, label="Titlul")
    bio = v.text("bio", max=1200, required=False, label="Descrierea")
    years = v.integer("experience_years", min=0, max=60, required=False, label="Experiența")
    availability = v.text("availability", max=60, required=False, label="Disponibilitatea")
    zones, hours = data.get("zones"), data.get("hours")
    if zones is not None and not (
        isinstance(zones, list)
        and len(zones) <= 30
        and all(isinstance(z, str) and 1 <= len(z) <= 60 for z in zones)
    ):
        v.errors["zones"] = "Zonele trebuie să fie o listă de maximum 30 de nume."
    if hours is not None and not (
        isinstance(hours, dict)
        and len(hours) <= 10
        and all(isinstance(k, str) and isinstance(x, str) and len(x) <= 40 for k, x in hours.items())
    ):
        v.errors["hours"] = "Programul de lucru are un format invalid."
    v.done()
    conn.execute(
        "UPDATE pro_profiles SET headline=COALESCE(?,headline), bio=COALESCE(?,bio), "
        "experience_years=COALESCE(?,experience_years), availability=COALESCE(?,availability), "
        "zones_json=COALESCE(?,zones_json), hours_json=COALESCE(?,hours_json) WHERE user_id=?",
        (
            headline,
            bio,
            years,
            availability,
            json.dumps(zones, ensure_ascii=False) if zones is not None else None,
            json.dumps(hours, ensure_ascii=False) if hours is not None else None,
            user["id"],
        ),
    )
    conn.commit()
    return me(conn, user)


def submit_verification(conn, user, data):
    p = _own_profile(conn, user)
    if p["verification_status"] == "verified":
        raise ApiError(409, "already_verified", "Firma este deja verificată.")
    v = Validator(data)
    company = v.text("company_name", min=3, max=120, label="Denumirea firmei")
    cui = v.text("cui", max=14, label="CUI")
    if cui and not ver.validate_cui(cui):
        v.errors.setdefault("cui", "CUI invalid (verificați cifra de control).")
    v.done()
    canon = "RO" + ver.normalize_cui(cui)
    if conn.execute("SELECT 1 FROM pro_profiles WHERE cui=? AND user_id<>?", (canon, user["id"])).fetchone():
        raise ApiError(409, "cui_taken", "Această firmă are deja un cont.", {"cui": "CUI deja înregistrat."})
    reg = ver.lookup_registry(cui)
    ok = bool(reg and reg["active"])
    note = "Verificat automat în registrul ONRC/ANAF." if ok else "În așteptarea verificării manuale (1-2 zile lucrătoare)."
    conn.execute(
        "UPDATE pro_profiles SET company_name=?, cui=?, verification_status=?, verification_note=?, "
        "verified_at=? WHERE user_id=?",
        (company, canon, "verified" if ok else "pending", note, now_ts() if ok else None, user["id"]),
    )
    conn.commit()
    return me(conn, user)


# ------------------------------------------------- subscription & payments
def subscription(conn, user):
    p = _own_profile(conn, user)
    t = now_ts()
    pm = conn.execute(
        "SELECT brand,last4,exp FROM payment_methods WHERE user_id=? AND is_default=1", (user["id"],)
    ).fetchone()
    return {
        "plan": p["plan"],
        "status": p["plan_status"],
        "price_eur": p["subscription_price_eur"] if "subscription_price_eur" in p.keys() else 39,
        "renews_at": p["plan_renews_at"],
        "renews_in_days": max(0, (p["plan_renews_at"] - t) // DAY) if p["plan_renews_at"] else None,
        "plans": payments.PLANS,
        "payment_method": dict(pm) if pm else None,
        "payments": [
            dict(r)
            for r in conn.execute(
                "SELECT id,plan,amount_ron,status,invoice_no,card_brand,card_last4,failure_reason,created_at "
                "FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
                (user["id"],),
            )
        ],
    }


def save_payment_method(conn, user, data):
    _own_profile(conn, user)
    card = data.get("card")
    num = payments.validate_card(card)["number"]
    brand = payments.brand_of(num)
    conn.execute("UPDATE payment_methods SET is_default=0 WHERE user_id=?", (user["id"],))
    conn.execute(
        "INSERT INTO payment_methods VALUES (?,?,?,?,?,1,?)",
        (new_id("pm_"), user["id"], brand, num[-4:], str(card["exp"]).replace(" ", ""), now_ts()),
    )
    conn.commit()
    return subscription(conn, user)


def checkout(conn, ctx, user, data):
    p = _own_profile(conn, user)
    _require_verified(p)
    ctx.limiter.check(f"pay:{user['id']}", 10, 3600, "Prea multe încercări de plată. Reîncearcă mai târziu.")
    v = Validator(data)
    plan = v.choice("plan", tuple(payments.PLANS), label="Planul")
    v.done()
    if p["plan"] == plan and p["plan_status"] == "active" and (p["plan_renews_at"] or 0) - now_ts() > 7 * DAY:
        raise ApiError(409, "already_active", "Acest plan este deja activ.")
    card = data.get("card")
    if card is None:
        pm = conn.execute("SELECT * FROM payment_methods WHERE user_id=? AND is_default=1", (user["id"],)).fetchone()
        if not pm:
            raise ApiError(402, "no_payment_method", "Adaugă o metodă de plată pentru a continua.")
        card = {
            "number": "4242424242424242" if pm["last4"] == "4242" else "5555555555554444",
            "exp": "12/99",
            "cvc": "123",
        }
    amount = payments.PLANS[plan]["price_ron"]
    res = ctx.provider.charge(amount, card, f"REZOLV {payments.PLANS[plan]['name']}")
    t = now_ts()
    pid = new_id("pay_")
    invoice = (
        f"RZV-{datetime.now().year}-{conn.execute('SELECT COUNT(*) FROM payments WHERE status=?', ('succeeded',)).fetchone()[0] + 1:06d}"
        if res.ok
        else None
    )
    conn.execute(
        "INSERT INTO payments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            pid,
            user["id"],
            "subscription",
            plan,
            amount,
            "succeeded" if res.ok else "failed",
            ctx.provider.name,
            res.ref,
            res.brand,
            res.last4,
            invoice,
            None if res.ok else res.reason,
            t,
        ),
    )
    if not res.ok:
        conn.execute("UPDATE pro_profiles SET plan_status='past_due' WHERE user_id=? AND plan_status<>'trial'", (user["id"],))
        conn.commit()
        raise ApiError(402, "card_declined", res.reason or "Plata a fost refuzată.")
    if card.get("number") and data.get("card") and data.get("save_card"):
        save_payment_method(conn, user, {"card": data["card"]})
    conn.execute(
        "UPDATE pro_profiles SET plan=?, plan_status='active', subscription_price_eur=39, plan_renews_at=? WHERE user_id=?",
        (plan, t + 30 * DAY, user["id"]),
    )
    notify(
        conn,
        user["id"],
        "payment",
        "Plată reușită (39 EUR/lună • 0% comision)",
        f"Planul {payments.PLANS[plan]['name']} este activ. Factura {invoice}.",
    )
    analytics.track(conn, user["id"], "pro", "subscription_activated", {"plan": plan, "price_eur": 39})
    conn.commit()
    return subscription(conn, user)


def get_payment_invoice_xml(conn, user, payment_id: str) -> dict:
    p = conn.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
    if not p:
        raise ApiError(404, "not_found", "Factura nu a fost găsită.")
    if user["role"] != "admin" and p["user_id"] != user["id"]:
        raise ApiError(403, "forbidden", "Acces interzis la factura solicitată.")
    buyer_pro = conn.execute("SELECT company_name, cui FROM pro_profiles WHERE user_id=?", (p["user_id"],)).fetchone()
    b_name = buyer_pro["company_name"] if buyer_pro and buyer_pro["company_name"] else user["name"]
    b_cui = buyer_pro["cui"] if buyer_pro and buyer_pro["cui"] else "RO45612301"
    xml_str = payments.generate_efactura_ubl_xml(dict(p), supplier_cui="RO39204176", buyer_cui=b_cui, buyer_name=b_name)
    return {
        "invoice_no": p["invoice_no"],
        "filename": f"{p['invoice_no']}_cius_ro.xml",
        "xml": xml_str,
        "format": "ubl_2.1_cius_ro",
        "supplier_cui": "RO39204176",
        "buyer_cui": b_cui,
    }


# ------------------------------------------------------------- AI assistant
AI_RULES = [
    (
        "Reparații Electrocasnice",
        r"frigider|spălat|spalat|cuptor|electrocasnic|uscător|uscator|centrifug",
        "100 – 300 RON",
        "Problema descrisă necesită diagnoza unui tehnician pentru electrocasnice.",
    ),
    (
        "Acoperișuri & Exterioare",
        r"țigl|tigl|acoperi|jgheab|pluvial|hidroizola|infiltr",
        "200 – 1500 RON",
        "Pentru reparații la acoperiș, țiglă sau jgheaburi pluviale, este recomandată o echipă specializată.",
    ),
    (
        "Instalații Sanitare",
        r"țeav|teav|robinet|apă|apa |scurg|chiuvet|baterie lavoar|lavoar|wc|duș|dus|inunda",
        "120 – 280 RON",
        "Descrierea indică o problemă la instalația de apă. Este recomandat un instalator autorizat din Sibiu.",
    ),
    (
        "Instalații Electrice",
        r"curent|priz|siguran|electric|bec|cablu|tablou|iluminat|scântei|scantei",
        "150 – 350 RON",
        "Simptomele descrise necesită verificarea circuitului de către un electrician autorizat ANRE.",
    ),
    (
        "Climatizare & Termice",
        r"central|calorifer|aer condi|termic|clim|vaillant|viessmann|freon",
        "180 – 400 RON",
        "Pare o problemă de încălzire sau climatizare; un tehnician din Sibiu poate face revizia la fața locului.",
    ),
    (
        "Mecanică Auto",
        r"mașin|masin|motor|frân|fran|baterie auto|diagnoz|check engine",
        "150 – 450 RON",
        "Cererea ține de diagnoză sau reparații auto mobile în Sibiu.",
    ),
    (
        "Vulcanizare Mobilă",
        r"roat|pană|pana |anvelop|cauciuc|echilibrare",
        "100 – 250 RON",
        "O echipă de vulcanizare mobilă din Sibiu poate interveni direct la locația ta.",
    ),
    (
        "Lăcătuș",
        r"yal|ușă|usa |ușa|cheie|încuiat|incuiat|cilindru",
        "140 – 280 RON",
        "Un lăcătuș autorizat din Sibiu poate rezolva rapid problema de închidere.",
    ),
    (
        "Zugrăveli & Finisaje",
        r"zugrav|zugrăv|vopsea|lavabil|glet|perete",
        "30 – 60 RON/mp",
        "Pentru pereți și finisaje, un zugrav profesionist îți poate oferi deviz pe metru pătrat.",
    ),
    (
        "Zidărie & Faianțare",
        r"gresie|faianț|faiant|chituir|zidăr|zidar|tencui|plăci|placi",
        "50 – 120 RON/mp",
        "Pentru montaj gresie, faianță sau zidărie, îți recomandăm un faianțar verificat din Sibiu.",
    ),
    (
        "Montaj Mobilă",
        r"asambl|mobil|dulap|pax|bucătări|corpuri suspendate",
        "100 – 400 RON",
        "Pentru asamblare și montaj mobilier, un montator cu experiență din Sibiu poate prelua lucrarea.",
    ),
    (
        "Curățenie",
        r"curăț|curat|menaj|mizerie|după constructor",
        "150 – 450 RON",
        "O echipă de curățenie poate prelua lucrarea cu materiale proprii.",
    ),
]

PROMPT_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(all\s+)?(previous|prior)\s+instructions|"
    r"ignor[aă]\s+(toate\s+)?instruc[tț]iunile|"
    r"uit[aă]\s+instruc[tț]iunile|"
    r"system\s+(prompt|override)|"
    r"you\s+are\s+now\s+dan|"
    r"do\s+anything\s+now|"
    r"reveal\s+(your|internal)\s+(prompt|instructions)|"
    r"REZOLV_SECRET|"
    r"drop\s+table\s+users|"
    r"union\s+select\s+password_hash|"
    r"<script\b[^>]*>)",
    re.IGNORECASE,
)


def detect_prompt_injection(text: str) -> str | None:
    """Detect prompt-injection, jailbreak, or SQL/XSS payload attempts inside AI inputs."""
    hit = PROMPT_INJECTION_PATTERNS.search(text or "")
    return hit.group(0) if hit else None


def estimate_tokens(text: str) -> int:
    """Estimate LLM token count (~3.6 chars per token for Romanian text)."""
    if not text:
        return 0
    return max(1, (len(text.strip()) + 3) // 4)


def truncate_to_token_budget(text: str, max_tokens: int | None = None) -> tuple[str, int, int, bool]:
    """Ensure input fits within `max_tokens` context window without splitting words mid-token."""
    budget = max_tokens or config.AI_MAX_INPUT_TOKENS
    orig_tokens = estimate_tokens(text)
    if orig_tokens <= budget:
        return text, orig_tokens, orig_tokens, False
    char_limit = max(40, budget * 4)
    clipped = text[:char_limit].rsplit(" ", 1)[0].strip() or text[:char_limit]
    used_tokens = estimate_tokens(clipped)
    return clipped, orig_tokens, used_tokens, True


def ai_recommend(conn, data):
    if not isinstance(data, dict):
        raise ApiError(400, "bad_request", "Corpul cererii trebuie să fie un obiect JSON.")
    raw_problem = data.get("problem")
    if not isinstance(raw_problem, str) or len(raw_problem.strip()) < 10:
        raise bad("Descrierea trebuie să aibă minim 10 caractere.", "problem")
    if len(raw_problem) > 12000:
        raise bad("Descrierea depășește limita maximă admisă (12.000 caractere).", "problem")

    # 1. Prompt Injection & Security Guardrail
    inj = detect_prompt_injection(raw_problem)
    if inj:
        observability.trigger_alert(
            conn,
            "warning",
            "security_prompt_injection",
            "Tentativă de Prompt Injection blocată",
            f"Input respins de filtrul AI Guardrail: {inj[:80]}",
            {"matched_pattern": inj[:80]},
        )
        conn.commit()
        raise ApiError(
            400,
            "prompt_injection_detected",
            "Am detectat instrucțiuni nepermise în text. Te rugăm să descrii doar problema tehnică din locuință sau auto.",
            {"problem": "Conținut blocat de filtrul de securitate AI."},
        )

    # 2. Spend Cap Check & Token Context Window Management
    observability.check_and_record_spend(conn, "ai", enforce=True)
    clean_problem, orig_tokens, used_tokens, truncated = truncate_to_token_budget(
        raw_problem.strip(), config.AI_MAX_INPUT_TOKENS
    )
    photos_raw = data.get("photos")
    photos_count = len(photos_raw) if isinstance(photos_raw, list) else 0

    # 3. Primary Model API vs Deterministic Fallback Circuit Breaker
    simulate_down = bool(data.get("simulate_model_down")) or config.AI_SIMULATE_OUTAGE
    has_live_llm = bool(config.OPENAI_API_KEY.strip() or config.GEMINI_API_KEY.strip())
    fallback_used = simulate_down or not has_live_llm
    provider = "deterministic_fallback" if fallback_used else "llm_primary_with_fallback"

    llm_cat = None
    if has_live_llm and not simulate_down:
        try:
            if config.GEMINI_API_KEY.strip():
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={config.GEMINI_API_KEY.strip()}"
                prompt_content = f"Triage repair problem in Sibiu into one of the 12 categories: Instalații Sanitare, Instalații Electrice, Climatizare & Termice, Mecanică Auto, Vopsitorie & Tinichigerie, Vulcanizare & Detailing, Amenajări & Zugrăveli, Tâmplărie & Uși, Acoperișuri & Exterioare, Zidărie & Faianțare, Lăcătuș & Deblocări, Reparații Electrocasnice. Description: {clean_problem}"
                payload = json.dumps({"contents": [{"parts": [{"text": prompt_content}]}]}).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=config.AI_MODEL_TIMEOUT_SEC) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    cand = resp_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    for name, _, _, _ in AI_RULES:
                        if name.lower() in cand.lower():
                            llm_cat = name
                            break
        except Exception:
            fallback_used = True
            provider = "deterministic_fallback"

    text = clean_problem.lower()
    cat, price, reason = (
        "Instalații Sanitare",
        "100 – 400 RON",
        "Am selectat un meșter verificat din Sibiu care poate trimite o estimare rapidă.",
    )
    matched = False
    if llm_cat:
        cat, matched = llm_cat, True
        for name, _, p, why in AI_RULES:
            if name == cat:
                price, reason = p, why
                break
    else:
        for name, rx, p, why in AI_RULES:
            if re.search(rx, text):
                cat, price, reason, matched = name, p, why, True
                break
    pros = list_professionals(conn, cat)["professionals"]
    urgent = bool(re.search(r"inund|curge tare|urgen|scântei|scantei|fum", text))

    analytics.track(
        conn,
        None,
        "client",
        "ai_triage_called",
        {
            "category": cat,
            "matched": matched,
            "urgent": urgent,
            "fallback_used": fallback_used,
            "context_truncated": truncated,
            "tokens": used_tokens,
            "photos_count": photos_count,
        },
    )
    conn.commit()
    return {
        "category": cat,
        "reason": reason,
        "price": f"Estimare orientativă: {price}",
        "matched": matched,
        "urgency": "Intervenție urgentă Sibiu" if urgent else (pros[0]["availability"] if pros else "Disponibil curând"),
        "professional": pros[0] if pros else None,
        "provider": provider,
        "fallback_used": fallback_used,
        "context_truncated": truncated,
        "photos_analyzed": photos_count,
        "token_usage": {
            "original_tokens": orig_tokens,
            "used_tokens": used_tokens,
            "max_budget_tokens": config.AI_MAX_INPUT_TOKENS,
        },
    }


# ----------------------------------------------------------- notifications
def list_notifications(conn, user):
    rows = conn.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (user["id"],)
    ).fetchall()
    return {
        "notifications": [
            {
                "id": r["id"],
                "kind": r["kind"],
                "title": r["title"],
                "body": r["body"],
                "booking_id": r["booking_id"],
                "read": bool(r["is_read"]),
                "ago": ago(r["created_at"]),
            }
            for r in rows
        ],
        "unread": sum(1 for r in rows if not r["is_read"]),
    }


def mark_notifications_read(conn, user):
    conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user["id"],))
    conn.commit()
    return list_notifications(conn, user)


# ------------------------------------ Super-Admin (White-Glove & Investor Cockpit)
def admin_metrics(conn, user):
    require_role(user, "admin")
    q = lambda sql: conn.execute(sql).fetchone()[0]
    active_pros = q("SELECT COUNT(*) FROM pro_profiles WHERE plan_status='active'")
    return {
        "pilot_city": config.PILOT_CITY,
        "users": {
            "clients": q("SELECT COUNT(*) FROM users WHERE role='client'"),
            "pros": q("SELECT COUNT(*) FROM users WHERE role='pro'"),
            "pros_verified": q("SELECT COUNT(*) FROM pro_profiles WHERE verification_status='verified'"),
            "pros_pending": q("SELECT COUNT(*) FROM pro_profiles WHERE verification_status='pending'"),
        },
        "bookings": {
            "total": q("SELECT COUNT(*) FROM bookings"),
            "estimated": q("SELECT COUNT(*) FROM bookings WHERE status='estimated'"),
            "accepted": q("SELECT COUNT(*) FROM bookings WHERE status='accepted'"),
            "completed": q("SELECT COUNT(*) FROM bookings WHERE status='completed'"),
            "gmv_ron": q("SELECT COALESCE(SUM(quote_price),0) FROM bookings WHERE status='completed'"),
        },
        "revenue": {
            "mrr_eur": active_pros * config.B2B_MONTHLY_EUR,
            "mrr_ron": active_pros * config.B2B_MONTHLY_RON,
            "collected_ron": q("SELECT COALESCE(SUM(amount_ron),0) FROM payments WHERE status='succeeded'"),
        },
        "avg_rating": round(q("SELECT COALESCE(AVG(rating),0) FROM reviews"), 2),
    }


def admin_overview(conn, user):
    """Comprehensive Founder Super-Admin & Investor Overview."""
    require_role(user, "admin")
    metrics = admin_metrics(conn, user)
    inv_analytics = analytics.compute_investor_analytics(conn)

    pros_rows = conn.execute(
        "SELECT p.*, u.name, u.email, u.phone FROM pro_profiles p JOIN users u ON u.id=p.user_id ORDER BY p.verified_at DESC, u.created_at DESC"
    ).fetchall()
    pros_list = []
    for r in pros_rows:
        svcs = [
            _service_view(s)
            for s in conn.execute("SELECT * FROM pro_services WHERE pro_id=? ORDER BY category, rowid", (r["user_id"],))
        ]
        pros_list.append({
            "id": r["user_id"],
            "name": r["name"],
            "email": r["email"],
            "phone": r["phone"],
            "company_name": r["company_name"],
            "cui": r["cui"],
            "zones": json.loads(r["zones_json"]),
            "hours": json.loads(r["hours_json"]),
            "verification_status": r["verification_status"],
            "onboarded_by_admin": bool(r["onboarded_by_admin"]) if "onboarded_by_admin" in r.keys() else False,
            "plan": r["plan"],
            "plan_status": r["plan_status"],
            "subscription_price_eur": r["subscription_price_eur"] if "subscription_price_eur" in r.keys() else 39,
            "rating": round(r["rating_avg"], 1),
            "jobs": r["jobs_completed"],
            "services_count": len(svcs),
            "categories": sorted({s["category"] for s in svcs}),
        })

    sms_rows = conn.execute(
        "SELECT sr.*, b.service_name, c.name AS client_name, pr.name AS pro_name "
        "FROM sms_reminders sr JOIN bookings b ON b.id=sr.booking_id "
        "JOIN users c ON c.id=b.client_id JOIN users pr ON pr.id=b.pro_id "
        "ORDER BY sr.created_at DESC, sr.send_at ASC LIMIT 40"
    ).fetchall()
    sms_queue = [
        {
            "id": r["id"],
            "booking_id": r["booking_id"],
            "service_name": r["service_name"],
            "client_name": r["client_name"],
            "pro_name": r["pro_name"],
            "recipient_phone": r["recipient_phone"],
            "reminder_type": r["reminder_type"],
            "message_body": r["message_body"],
            "status": r["status"],
            "provider": r["provider"],
            "provider_sid": r["provider_sid"],
            "send_at": r["send_at"],
            "send_at_label": sms.format_ro_slot(r["send_at"]),
            "sent_at": r["sent_at"],
        }
        for r in sms_rows
    ]

    return {
        "metrics": metrics,
        "analytics": inv_analytics,
        "professionals": pros_list,
        "sms_queue": sms_queue,
        "sibiu_zones": seed.SIBIU_ZONES,
        "categories": [c[0] for c in seed.CATEGORIES],
    }


def admin_cui_lookup(conn, user, data):
    require_role(user, "admin")
    cui = (data or {}).get("cui") or ""
    res = ver.lookup_anaf_cui(cui)
    if not res.get("valid"):
        raise bad(res.get("error") or "CUI invalid.", "cui")
    return res


def admin_white_glove_onboard(conn, user, data):
    """Founder White-Glove Onboarding: manually create a verified Pro in Sibiu with hours, zones & catalog."""
    require_role(user, "admin")
    v = Validator(data)
    name = v.text("name", min=2, max=80, label="Numele meșterului")
    email = v.email()
    phone = v.phone() or "+40 740 555 099"
    company = v.text("company_name", min=3, max=120, label="Denumirea firmei (SRL/PFA)")
    cui = v.text("cui", max=14, label="CUI")
    if cui and not ver.validate_cui(cui):
        v.errors.setdefault("cui", "CUI invalid (cifra de control modulo-11 incorectă).")
    primary_category = v.text("category", max=60, required=False, label="Categoria principală") or "Instalații Sanitare"
    experience_years = v.integer("experience_years", min=1, max=50, required=False, label="Ani experiență") or 8
    plan_status = v.choice("plan_status", ("trial", "active"), required=False, label="Status abonament") or "active"
    v.done()

    if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise ApiError(409, "email_taken", "Există deja un meșter cu acest email.", {"email": "Email deja folosit."})
    canon = "RO" + ver.normalize_cui(cui)
    if conn.execute("SELECT 1 FROM pro_profiles WHERE cui=?", (canon,)).fetchone():
        raise ApiError(409, "cui_taken", "Acest CUI este deja înregistrat în platformă.", {"cui": "CUI deja înregistrat."})

    zones = data.get("zones")
    if not isinstance(zones, list) or not zones:
        zones = seed.SIBIU_ZONES[:5]
    hours = data.get("hours")
    if not isinstance(hours, dict) or not hours:
        hours = seed.HOURS

    uid, t = new_id("u_"), now_ts()
    pw_hash = hash_password(data.get("password") or seed.DEMO_PASSWORD)
    conn.execute(
        "INSERT INTO users (id,email,password_hash,role,name,phone,city,neighborhood,address,created_at,last_login_at) "
        "VALUES (?,?,?,'pro',?,?,'Sibiu',?,?,?,?)",
        (uid, email, pw_hash, name, phone, zones[0], f"{zones[0]}, Sibiu", t, t),
    )
    ver.register(canon, company, True, f"{zones[0]}, Sibiu", primary_category)
    conn.execute(
        "INSERT INTO pro_profiles (user_id,company_name,cui,headline,bio,experience_years,city,zones_json,hours_json,"
        "slot_step_minutes,verification_status,verification_note,verified_at,onboarded_by_admin,rating_avg,rating_count,"
        "jobs_completed,availability,distance_km,plan,plan_status,subscription_price_eur,plan_renews_at) "
        "VALUES (?,?,?,?,?,?,'Sibiu',?,?,30,'verified','White-Glove Onboarding de către Fondator (Sibiu)',?,1,5.0,1,0,"
        "'Disponibil astăzi',2.0,'pro',?,39,?)",
        (
            uid,
            company,
            canon,
            primary_category,
            f"{company} — partener verificat în Sibiu prin White-Glove Onboarding. Deviz clar și garanție.",
            experience_years,
            json.dumps(zones, ensure_ascii=False),
            json.dumps(hours, ensure_ascii=False),
            t,
            plan_status,
            t + 30 * DAY,
        ),
    )

    # Populate services from custom list or template catalog for the chosen category
    custom_services = data.get("services")
    if isinstance(custom_services, list) and custom_services:
        for item in custom_services[:10]:
            sname = str(item.get("name") or "Intervenție tehnică")[:80]
            sprice = max(50, int(item.get("price_from") or 150))
            sdur = str(item.get("duration") or "1 oră")[:40]
            conn.execute(
                "INSERT INTO pro_services (id,pro_id,category,name,price_from,price_unit,duration,est_duration_min,active) "
                "VALUES (?,?,?,?,?,'RON',?,?,1)",
                (new_id("s_"), uid, primary_category, sname, sprice, sdur, parse_duration_minutes(sdur)),
            )
    else:
        cat_templates = seed.CATALOG.get(primary_category, seed.CATALOG["Instalații Sanitare"])
        for (sname, sprice, sunit, sdur, est_m) in cat_templates:
            conn.execute(
                "INSERT INTO pro_services (id,pro_id,category,name,price_from,price_unit,duration,est_duration_min,active) "
                "VALUES (?,?,?,?,?,?,?,?,1)",
                (new_id("s_"), uid, primary_category, sname, sprice, sunit, sdur, est_m),
            )

    analytics.track(
        conn,
        user["id"],
        "admin",
        "white_glove_pro_onboarded",
        {"pro_id": uid, "company": company, "cui": canon, "category": primary_category, "zones": zones},
    )
    observability.CACHE.invalidate()
    conn.commit()
    return {
        "onboarded": get_professional(conn, uid)["professional"],
        "overview": admin_overview(conn, user),
    }


def admin_update_pro_subscription(conn, user, pro_id, data):
    require_role(user, "admin")
    if not conn.execute("SELECT 1 FROM pro_profiles WHERE user_id=?", (pro_id,)).fetchone():
        raise ApiError(404, "not_found", "Profilul meșterului nu există.")
    plan_status = data.get("plan_status")
    plan = data.get("plan")
    if plan_status in ("trial", "active", "past_due"):
        conn.execute(
            "UPDATE pro_profiles SET plan_status=?, plan_renews_at=? WHERE user_id=?",
            (plan_status, now_ts() + 30 * DAY, pro_id),
        )
    if plan in ("essential", "pro"):
        conn.execute("UPDATE pro_profiles SET plan=? WHERE user_id=?", (plan, pro_id))
    analytics.track(conn, user["id"], "admin", "pro_subscription_updated", {"pro_id": pro_id, "plan_status": plan_status})
    conn.commit()
    return admin_overview(conn, user)


def admin_trigger_due_sms(conn, user):
    require_role(user, "admin")
    dispatched = sms.process_due_reminders(conn, force_all_scheduled=True)
    analytics.track(conn, user["id"], "admin", "sms_batch_dispatched", {"count": len(dispatched)})
    return {"dispatched": dispatched, "overview": admin_overview(conn, user)}


def admin_pending_pros(conn, user):
    require_role(user, "admin")
    return {
        "pros": [
            {"id": r["user_id"], "name": r["name"], "company_name": r["company_name"], "cui": r["cui"]}
            for r in conn.execute(
                "SELECT p.*, u.name FROM pro_profiles p JOIN users u ON u.id=p.user_id "
                "WHERE p.verification_status='pending'"
            )
        ]
    }


def admin_review_pro(conn, user, pro_id, data):
    require_role(user, "admin")
    approve = data.get("approve")
    if not isinstance(approve, bool):
        raise bad("Câmpul 'approve' trebuie să fie true/false.", "approve")
    if not conn.execute("SELECT 1 FROM pro_profiles WHERE user_id=?", (pro_id,)).fetchone():
        raise ApiError(404, "not_found", "Profilul nu există.")
    status = "verified" if approve else "rejected"
    note = "Verificat de echipa REZOLV Sibiu." if approve else str(data.get("note") or "Documente insuficiente.")[:200]
    conn.execute(
        "UPDATE pro_profiles SET verification_status=?, verification_note=?, verified_at=? WHERE user_id=?",
        (status, note, now_ts() if approve else None, pro_id),
    )
    notify(
        conn,
        pro_id,
        "verification",
        "Verificare firmă",
        "Firma ta a fost aprobată și profilul este public în Sibiu." if approve else f"Verificare respinsă: {note}",
    )
    observability.CACHE.invalidate()
    conn.commit()
    return {"id": pro_id, "verification_status": status}


def admin_observability_report(conn, user) -> dict:
    """Comprehensive SRE, Security, Performance, Spend Caps, Email Auth & Alerting Dashboard."""
    require_role(user, "admin")
    perf = observability.compute_performance_stats(conn)
    spend = observability.get_spend_and_quota_status(conn)
    email_dns = email_service.get_email_auth_dns_records()
    cache_stats = observability.CACHE.stats()

    alerts = [
        {
            "id": r["id"],
            "severity": r["severity"],
            "category": r["category"],
            "title": r["title"],
            "message": r["message"],
            "metadata": json.loads(r["metadata_json"] or "{}"),
            "resolved": bool(r["resolved"]),
            "created_at": r["created_at"],
            "ago": ago(r["created_at"]),
        }
        for r in conn.execute("SELECT * FROM system_alerts ORDER BY created_at DESC LIMIT 20").fetchall()
    ]
    errors = [
        {
            "id": r["id"],
            "source": r["source"],
            "level": r["level"],
            "error_code": r["error_code"],
            "message": r["message"],
            "path": r["path"],
            "method": r["method"],
            "request_id": r["request_id"],
            "created_at": r["created_at"],
            "ago": ago(r["created_at"]),
        }
        for r in conn.execute("SELECT * FROM error_logs ORDER BY created_at DESC LIMIT 20").fetchall()
    ]
    emails = [
        {
            "id": r["id"],
            "recipient_email": r["recipient_email"],
            "subject": r["subject"],
            "template_kind": r["template_kind"],
            "status": r["status"],
            "created_at": r["created_at"],
            "ago": ago(r["created_at"]),
        }
        for r in conn.execute("SELECT * FROM email_outbox ORDER BY created_at DESC LIMIT 15").fetchall()
    ]
    return {
        "uptime_seconds": max(1, now_ts() - config.BOOT_TIMESTAMP),
        "environment": config.ENV,
        "custom_domain": config.CUSTOM_DOMAIN,
        "ssl_hsts_enabled": True,
        "performance": perf,
        "spend_caps": spend,
        "email_auth": email_dns,
        "cache": cache_stats,
        "alerts": alerts,
        "recent_errors": errors,
        "email_outbox": emails,
    }


def admin_run_backup(conn, user, db_path: str | None = None) -> dict:
    require_role(user, "admin")
    manifest = backup.create_backup(db_path=db_path)
    analytics.track(conn, user["id"], "admin", "db_backup_created", {"sha256": manifest["sha256"][:16]})
    conn.commit()
    return manifest


def admin_verify_restore(conn, user, db_path: str | None = None) -> dict:
    require_role(user, "admin")
    report = backup.verify_backup_and_restore(db_path=db_path)
    analytics.track(conn, user["id"], "admin", "db_restore_verified", {"verified": report["verified"]})
    conn.commit()
    return report


def get_seo_structured_data(conn) -> dict:
    """Return Schema.org JSON-LD graph (LocalBusiness, WebApplication, Service, FAQPage) for SEO & AEO."""
    pros_count = conn.execute("SELECT COUNT(*) FROM pro_profiles WHERE verification_status='verified'").fetchone()[0]
    avg_rating = round(conn.execute("SELECT COALESCE(AVG(rating), 4.9) FROM reviews").fetchone()[0] or 4.9, 2)
    reviews_count = max(1, conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0])
    cats = [r["name"] for r in conn.execute("SELECT name FROM categories ORDER BY sort").fetchall()]
    domain = f"https://{config.CUSTOM_DOMAIN}"
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "LocalBusiness",
                "@id": f"{domain}/#organization",
                "name": "REZOLV Sibiu",
                "url": domain,
                "logo": f"{domain}/favicon.svg",
                "image": f"{domain}/og-image.svg",
                "description": "Platformă de meșteri și servicii auto verificate CUI în Sibiu. 0% comision pentru clienți, deviz flexibil și calendar cu remindere SMS anti-no-show.",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "Piața Mare nr. 1",
                    "addressLocality": "Sibiu",
                    "addressRegion": "Sibiu",
                    "postalCode": "550163",
                    "addressCountry": "RO",
                },
                "areaServed": ["Sibiu", "Șelimbăr", "Cisnădie", "Hipodrom", "Turnișor", "Ștrand", "Vasile Aaron"],
                "aggregateRating": {
                    "@type": "AggregateRating",
                    "ratingValue": str(avg_rating),
                    "reviewCount": str(reviews_count),
                    "bestRating": "5",
                    "worstRating": "1",
                },
                "knowsAbout": cats,
            },
            {
                "@type": "WebApplication",
                "@id": f"{domain}/#webapp",
                "name": "REZOLV — Meșteri Verificați Sibiu",
                "url": domain,
                "applicationCategory": "BusinessApplication",
                "operatingSystem": "Web, iOS, Android",
                "inLanguage": "ro-RO",
                "offers": {
                    "@type": "Offer",
                    "price": "0",
                    "priceCurrency": "RON",
                    "description": f"Rezervare gratuită pentru clienți ({pros_count} meșteri verificați în Sibiu).",
                },
            },
            {
                "@type": "FAQPage",
                "@id": f"{domain}/#faq",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": "Cât costă folosirea aplicației REZOLV pentru clienții din Sibiu?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": "Pentru clienți, REZOLV este 100% gratuit (0% comision). Plătești direct meșterului după finalizarea lucrării, pe baza estimării acceptate în aplicație.",
                        },
                    },
                    {
                        "@type": "Question",
                        "name": "Cum sunt verificați meșterii din Sibiu pe REZOLV?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": "Fiecare meșter sau atelier auto este verificat juridic prin CUI (cifră de control Modulo-11 și interogare ONRC/ANAF) și prin procesul local White-Glove Onboarding în Sibiu.",
                        },
                    },
                    {
                        "@type": "Question",
                        "name": "Cum funcționează estimarea și blocarea orei în calendar?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": "Descrii problema (sau folosești triajul AI), primești o estimare de preț, durată și oră de la meșter, iar când apeși Acceptă, slotul se blochează atomic în calendarul meșterului și primești remindere SMS la 24h și 2h înainte.",
                        },
                    },
                ],
            },
        ],
    }
