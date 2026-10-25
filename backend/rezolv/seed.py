"""Demo data for Pilot City: Sibiu, România.
Includes categories, verified Sibiu professionals, demo accounts, calendar slots,
flexible estimates, and scheduled Twilio 24h/2h anti-no-show SMS reminders.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from . import analytics, sms
from . import verification as ver
from .core import hash_password, new_id, now_ts

DAY = 86400
HOUR = 3600

CATEGORIES = [
    ("Instalații Sanitare", "80 – 350 RON", "cat-instalatii-sanitare.svg", "blue"),
    ("Instalații Electrice", "100 – 450 RON", "cat-instalatii-electrice.svg", "gold"),
    ("Mecanică Auto", "120 – 700 RON", "cat-mecanica-auto.svg", "blue"),
    ("Vulcanizare Mobilă", "80 – 250 RON", "cat-vulcanizare-mobila.svg", "green"),
    ("Climatizare & Termice", "150 – 600 RON", "cat-climatizare-termice.svg", "blue"),
    ("Reparații Electrocasnice", "90 – 300 RON", "cat-reparatii-electrocasnice.svg", "green"),
    ("Zugrăveli & Finisaje", "25 – 60 RON/mp", "cat-zugraveli-finisaje.svg", "coral"),
    ("Zidărie & Faianțare", "50 – 120 RON/mp", "cat-zidarie-faiantare.svg", "gold"),
    ("Montaj Mobilă", "100 – 400 RON", "cat-montaj-mobila.svg", "blue"),
    ("Lăcătuș", "100 – 280 RON", "cat-lacatus.svg", "green"),
    ("Acoperișuri & Exterioare", "200 – 1500 RON", "cat-acoperisuri-exterioare.svg", "coral"),
    ("Curățenie", "150 – 450 RON", "cat-curatenie.svg", "gold"),
]

# (name, price_from, unit, duration_label, est_duration_min)
CATALOG = {
    "Instalații Sanitare": [
        ("Reparație robinet sau baterie", 120, "RON", "1 oră", 60),
        ("Desfundare și reparație scurgere", 160, "RON", "1.5 ore", 90),
        ("Montaj obiecte sanitare", 220, "RON", "2 ore", 120),
    ],
    "Instalații Electrice": [
        ("Reparație priză sau întrerupător", 100, "RON", "1 oră", 60),
        ("Verificare și reparație tablou siguranțe", 180, "RON", "1.5 ore", 90),
        ("Montaj corpuri de iluminat", 140, "RON", "1 oră", 60),
    ],
    "Mecanică Auto": [
        ("Diagnoză auto computerizată (Sibiu)", 150, "RON", "1 oră", 60),
        ("Înlocuire baterie / pornire pe teren", 120, "RON", "45 min", 45),
        ("Revizie frâne și mecanică rapidă", 250, "RON", "2 ore", 120),
    ],
    "Vulcanizare Mobilă": [
        ("Reparație pană la locație (Sibiu & A1)", 100, "RON", "45 min", 45),
        ("Schimb roată și echilibrare mobilă", 80, "RON", "30 min", 30),
        ("Schimb sezonier set 4 anvelope", 220, "RON", "1 oră", 60),
    ],
    "Climatizare & Termice": [
        ("Revizie și verificare centrală termică", 250, "RON", "1.5 ore", 90),
        ("Igienizare și încărcare freon AC", 180, "RON", "1 oră", 60),
        ("Reparație instalație încălzire / calorifere", 300, "RON", "2 ore", 120),
    ],
    "Reparații Electrocasnice": [
        ("Diagnoză electrocasnic la domiciliu", 100, "RON", "1 oră", 60),
        ("Reparație mașină de spălat / uscător", 180, "RON", "1.5 ore", 90),
        ("Reparație frigider sau cuptor electric", 220, "RON", "2 ore", 120),
    ],
    "Zugrăveli & Finisaje": [
        ("Zugrăvire cameră lavabilă", 30, "RON/mp", "3 ore", 180),
        ("Reparații fisuri și gletuire", 35, "RON/mp", "3 ore", 180),
        ("Finisaje decorative interior", 50, "RON/mp", "4 ore", 240),
    ],
    "Zidărie & Faianțare": [
        ("Montaj gresie și faianță baie/bucătărie", 70, "RON/mp", "4 ore", 240),
        ("Reparații zidărie și tencuieli", 250, "RON", "3 ore", 180),
        ("Înlocuire plăci sparte și chituire", 60, "RON/mp", "2 ore", 120),
    ],
    "Montaj Mobilă": [
        ("Asamblare mobilier dormitor/living", 150, "RON", "2 ore", 120),
        ("Montaj și decupaje mobilă bucătărie", 400, "RON", "4 ore", 240),
        ("Fixare corpuri suspendate și galerii", 120, "RON", "1 oră", 60),
    ],
    "Lăcătuș": [
        ("Deblocare ușă fără distrugere (Urgent)", 140, "RON", "45 min", 45),
        ("Înlocuire cilindru / yală securitate", 180, "RON", "1 oră", 60),
        ("Reglaj și reparație mecanism multipunct", 160, "RON", "1 oră", 60),
    ],
    "Acoperișuri & Exterioare": [
        ("Inspecție și reparație țiglă acoperiș", 300, "RON", "3 ore", 180),
        ("Curățare și lipire jgheaburi pluviale", 250, "RON", "2 ore", 120),
        ("Hidroizolație terasă / infiltrări", 450, "RON", "4 ore", 240),
    ],
    "Curățenie": [
        ("Curățenie generală apartament/casă", 250, "RON", "3 ore", 180),
        ("Curățenie după constructor / renovare", 400, "RON", "4 ore", 240),
        ("Curățenie de întreținere", 180, "RON", "2 ore", 120),
    ],
}

SIBIU_ZONES = [
    "Hipodrom",
    "Șelimbăr",
    "Turnișor",
    "Ștrand",
    "Vasile Aaron",
    "Centru Istoric",
    "Valea Aurie",
    "Gușterița",
    "Lazaret",
    "Cisnădie",
]
HOURS = {"Luni–Vineri": "08:00–18:00", "Sâmbătă": "09:00–14:00", "Duminică": "Închis"}

# email, name, company, cui body, rating, reviews, jobs, km, availability, years, plan, categories
PROS = [
    ("mester@rezolv.ro", "Binder Lukas", "BINDER INSTAL SIBIU S.R.L.", "4123984", 4.9, 41, 63, 1.6,
     "Disponibil astăzi", 9, "essential", ["Instalații Sanitare", "Climatizare & Termice"]),
    ("marian@rezolv.ro", "Marian Popescu", "SIBIU TERMO SERV S.R.L.", "3918225", 4.9, 127, 214,
     1.8, "Disponibil astăzi", 8, "pro", ["Instalații Sanitare", "Climatizare & Termice", "Lăcătuș"]),
    ("andrei@rezolv.ro", "Andrei Munteanu", "TRANSILVANIA ELECTRO S.R.L.", "4417766", 4.8, 89, 156, 2.4,
     "Disponibil în 2 ore", 6, "essential", ["Instalații Sanitare", "Instalații Electrice", "Reparații Electrocasnice"]),
    ("radu@rezolv.ro", "Radu Petrescu", "CIBIN INSTALAȚII S.R.L.", "3604519", 4.7, 64, 118, 3.1,
     "Disponibil mâine", 10, "essential", ["Instalații Sanitare", "Instalații Electrice", "Montaj Mobilă", "Zugrăveli & Finisaje"]),
    ("ionut@rezolv.ro", "Ionuț Dragomir", "HERMANNSTADT AUTO GARAGE S.R.L.", "4290177", 4.9, 73, 190, 2.9,
     "Disponibil astăzi", 12, "pro", ["Mecanică Auto", "Vulcanizare Mobilă"]),
    ("catalin@rezolv.ro", "Cătălin Stoica", "AUTO MOBIL ȘELIMBĂR S.R.L.", "3815203", 4.6, 38, 77, 4.2,
     "Disponibil mâine", 7, "essential", ["Mecanică Auto", "Vulcanizare Mobilă", "Acoperișuri & Exterioare"]),
    ("sorin@rezolv.ro", "Sorin Toma", "TOMA FINISAJE SIBIU S.R.L.", "4501238", 4.8, 52, 101, 2.7,
     "Disponibil în 2 zile", 11, "essential", ["Zugrăveli & Finisaje", "Zidărie & Faianțare", "Montaj Mobilă", "Acoperișuri & Exterioare", "Curățenie"]),
    ("mirela@rezolv.ro", "Mirela Ene", "SIBIU PRO CLEAN S.R.L.", "4377012", 4.9, 95, 240, 2.1,
     "Disponibil astăzi", 5, "pro", ["Curățenie", "Reparații Electrocasnice"]),
    ("vlad@rezolv.ro", "Vlad Lăcătușu", "SIBIU LOCK & SAFE S.R.L.", "4112893", 4.7, 46, 88, 1.9,
     "Disponibil în 2 ore", 9, "essential", ["Lăcătuș", "Zidărie & Faianțare"]),
]

CLIENTS = [
    ("client@rezolv.ro", "Lukas Binder", "+40 721 555 010", "Hipodrom", "Bd. Mihai Viteazu nr. 24, Hipodrom, Sibiu"),
    ("dan@rezolv.ro", "Dan Georgescu", "+40 722 555 011", "Șelimbăr", "Str. Pictor Brana nr. 14, Șelimbăr, Sibiu"),
    ("elena@rezolv.ro", "Elena Radu", "+40 723 555 012", "Turnișor", "Șos. Alba Iulia nr. 58, Turnișor, Sibiu"),
    ("mihai@rezolv.ro", "Mihai Ionescu", "+40 724 555 013", "Ștrand", "Str. Maramureșului nr. 19, Ștrand, Sibiu"),
    ("andreea@rezolv.ro", "Andreea Popa", "+40 725 555 014", "Vasile Aaron", "Str. Semaforului nr. 31, Vasile Aaron, Sibiu"),
]

DEMO_PASSWORD = "Demo1234"


def _day_slot_ts(days_offset: int, hour: int, minute: int = 0) -> int:
    now = datetime.now()
    base = datetime(now.year, now.month, now.day, hour, minute, 0) + timedelta(days=days_offset)
    return int(base.timestamp())


def seed(conn):
    if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        return False
    t = now_ts()
    pw = hash_password(DEMO_PASSWORD)

    for i, (name, label, icon, tone) in enumerate(CATEGORIES):
        conn.execute("INSERT INTO categories VALUES (?,?,?,?,?)", (name, label, icon, tone, i))

    def add_user(email, role, name, phone=None, neighborhood="Centru", address=None):
        uid = new_id("u_")
        conn.execute(
            "INSERT INTO users (id,email,password_hash,role,name,phone,city,neighborhood,address,email_verified,created_at,last_login_at) "
            "VALUES (?,?,?,?,?,?,'Sibiu',?,?,1,?,?)",
            (uid, email, pw, role, name, phone, neighborhood, address, t - 30 * DAY, t),
        )
        return uid

    add_user("admin@rezolv.ro", "admin", "Fondator REZOLV Sibiu", "+40 720 000 001", "Centru Istoric", "Piața Mare nr. 1, Sibiu")
    clients = {c[0]: add_user(c[0], "client", c[1], c[2], c[3], c[4]) for c in CLIENTS}

    pro_ids = {}
    for idx, (email, name, company, body, rating, reviews, jobs, km, avail, years, plan, cats) in enumerate(PROS):
        cui = ver.make_cui(body)
        zones_slice = SIBIU_ZONES[:5] if idx % 2 == 0 else SIBIU_ZONES[1:6]
        uid = add_user(email, "pro", name, "+40 740 555 0" + body[-2:], zones_slice[0], f"{zones_slice[0]}, Sibiu")
        ver.register(cui, company, True, f"{zones_slice[0]}, Mun. Sibiu", cats[0])
        conn.execute(
            "INSERT INTO pro_profiles (user_id,company_name,cui,headline,bio,experience_years,city,zones_json,"
            "hours_json,slot_step_minutes,verification_status,verified_at,onboarded_by_admin,rating_avg,rating_count,"
            "jobs_completed,availability,distance_km,plan,plan_status,subscription_price_eur,plan_renews_at) "
            "VALUES (?,?,?,?,?,?,'Sibiu',?,?,30,'verified',?,1,?,?,?,?,?,?, 'active', 39, ?)",
            (
                uid,
                company,
                "RO" + cui,
                " & ".join(c.split(" &")[0] for c in cats[:2]),
                f"{company} (Sibiu) — meșteri verificați personal, estimare rapidă de preț și durată direct în aplicație "
                f"și garanție pentru lucrările efectuate în Sibiu și Șelimbăr. Specializări: {', '.join(c.lower() for c in cats)}.",
                years,
                json.dumps(zones_slice, ensure_ascii=False),
                json.dumps(HOURS, ensure_ascii=False),
                t - 40 * DAY,
                rating,
                reviews,
                jobs,
                avail,
                km,
                plan,
                t + (12 if email == "mester@rezolv.ro" else 24) * DAY,
            ),
        )
        for cat in cats:
            for (sname, price, unit, dur, est_min) in CATALOG[cat]:
                conn.execute(
                    "INSERT INTO pro_services (id,pro_id,category,name,price_from,price_unit,duration,est_duration_min,active)"
                    " VALUES (?,?,?,?,?,?,?,?,1)",
                    (new_id("s_"), uid, cat, sname, price, unit, dur, est_min),
                )
        pro_ids[email] = uid

    binder = pro_ids["mester@rezolv.ro"]
    ionut_auto = pro_ids["ionut@rezolv.ro"]
    conn.execute(
        "INSERT INTO payment_methods VALUES (?,?,?,?,?,1,?)",
        (new_id("pm_"), binder, "visa", "4242", "12/30", t),
    )

    def svc(pro, category, idx=0):
        return conn.execute(
            "SELECT * FROM pro_services WHERE pro_id=? AND category=? ORDER BY rowid LIMIT 1 OFFSET ?",
            (pro, category, idx),
        ).fetchone()

    def booking(
        client_email,
        pro,
        category,
        idx,
        desc,
        status,
        ago_min,
        quote=None,
        dur=None,
        dur_min=60,
        scheduled=None,
        start_ts=None,
        end_ts=None,
        neighborhood="Hipodrom",
        urgency="normal",
        window="Azi, 10:00–14:00",
        notes=None,
        review=None,
    ):
        s = svc(pro, category, idx)
        bid = new_id("b_")
        created = t - ago_min * 60
        conn.execute(
            "INSERT INTO bookings (id,client_id,pro_id,service_id,category,service_name,price_label,description,"
            "neighborhood,urgency_level,preferred_window,status,quote_price,quote_duration,duration_minutes,"
            "pro_notes,scheduled_for,scheduled_start_at,scheduled_end_at,created_at,updated_at,completed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                bid,
                clients[client_email],
                pro,
                s["id"],
                category,
                s["name"],
                f"de la {s['price_from']} {s['price_unit']}",
                desc,
                neighborhood,
                urgency,
                window,
                status,
                quote,
                dur,
                dur_min,
                notes,
                scheduled,
                start_ts,
                end_ts,
                created,
                created,
                created if status == "completed" else None,
            ),
        )
        conn.execute(
            "INSERT INTO booking_events (booking_id,actor_id,from_status,to_status,at) VALUES (?,?,NULL,'pending',?)",
            (bid, clients[client_email], created),
        )
        if status != "pending":
            conn.execute(
                "INSERT INTO booking_events (booking_id,actor_id,from_status,to_status,at) VALUES (?,?,'pending',?,?)",
                (bid, pro, status, created + 300),
            )
        if review:
            conn.execute(
                "INSERT INTO reviews VALUES (?,?,?,?,?,?,?)",
                (new_id("r_"), bid, clients[client_email], pro, review[0], review[1], created + 600),
            )
        return bid

    # 1. Pending requests in Sibiu for Binder Lukas (ready for 2-click Estimate on the Pro Calendar)
    booking(
        "dan@rezolv.ro",
        binder,
        "Instalații Sanitare",
        0,
        "Picură sub mască la chiuveta din bucătărie (Șelimbăr, str. Pictor Brana). Am bateria Grohe cumpărată, "
        "trebuie înlocuită și verificate robineții colțari.",
        "pending",
        12,
        neighborhood="Șelimbăr",
        urgency="urgent_today",
        window="Azi, 11:00–14:00",
    )
    booking(
        "elena@rezolv.ro",
        binder,
        "Climatizare & Termice",
        0,
        "Revizie centrală Vaillant + verificare presiune în calorifere înainte de sezonul rece (Turnișor). Apare intermitent F28.",
        "pending",
        45,
        scheduled="Mâine, 10:00",
        neighborhood="Turnișor",
        urgency="normal",
        window="Mâine, 09:00–12:00",
    )

    # 2. Estimated booking waiting for Client ("client@rezolv.ro") to click "Acceptă Estimarea și Blochează Slotul"
    est_start = _day_slot_ts(1, 11, 0)
    est_end = est_start + 90 * 60
    est_slot_label = sms.format_ro_slot(est_start, est_end)
    b_est = booking(
        "client@rezolv.ro",
        binder,
        "Instalații Sanitare",
        1,
        "Scurgere înfundată la baie și garnitură sifon uzată (Bd. Mihai Viteazu, Hipodrom).",
        "estimated",
        25,
        quote=190,
        dur="1.5 ore",
        dur_min=90,
        scheduled=est_slot_label,
        start_ts=est_start,
        end_ts=est_end,
        neighborhood="Hipodrom",
        urgency="normal",
        window="Mâine dimineață",
        notes="Include desfundare mecanică, înlocuire garnitură sifon și deplasarea în Hipodrom.",
    )
    est_id = new_id("est_")
    conn.execute(
        "INSERT INTO estimates (id,booking_id,pro_id,price_ron,price_max_ron,duration_minutes,duration_label,"
        "proposed_start_at,proposed_end_at,slot_label,pro_notes,status,expires_at,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,'sent',?,?)",
        (
            est_id,
            b_est,
            binder,
            190,
            230,
            90,
            "1.5 ore",
            est_start,
            est_end,
            est_slot_label,
            "Include desfundare mecanică, înlocuire garnitură sifon și deplasarea în Hipodrom.",
            t + 6 * HOUR,
            t - 900,
        ),
    )
    sms.send_instant_sms(
        conn,
        b_est,
        "+40 721 555 010",
        "estimate_ready",
        f"REZOLV Sibiu: Binder Lukas (BINDER INSTAL SIBIU S.R.L.) ți-a trimis o estimare: 190 RON (1.5 ore) "
        f"pentru {est_slot_label}. Intră în aplicație și apasă ACCEPTĂ pentru a bloca ora în calendar!",
    )

    # 3. Today's & Tomorrow's Confirmed Calendar Appointments (with active 24h & 2h SMS Reminders!)
    slot1_start = _day_slot_ts(0, 14, 0)
    slot1_end = slot1_start + 120 * 60
    b_conf1 = booking(
        "andreea@rezolv.ro",
        binder,
        "Climatizare & Termice",
        2,
        "Echilibrare hidraulică distribuitor încălzire în pardoseală și schimbare actuatoare (Vasile Aaron).",
        "accepted",
        180,
        quote=380,
        dur="2 ore",
        dur_min=120,
        scheduled=f"Azi, 14:00–16:00",
        start_ts=slot1_start,
        end_ts=slot1_end,
        neighborhood="Vasile Aaron",
        window="Azi după-amiază",
        notes="Piese incluse în deviz.",
    )
    sms.schedule_anti_noshow_reminders(
        conn,
        b_conf1,
        "+40 725 555 014",
        "Binder Lukas",
        "BINDER INSTAL SIBIU S.R.L.",
        "Reparație instalație încălzire / calorifere",
        380,
        slot1_start,
        slot1_end,
    )

    slot2_start = _day_slot_ts(1, 9, 0)
    slot2_end = slot2_start + 60 * 60
    b_conf2 = booking(
        "client@rezolv.ro",
        ionut_auto,
        "Mecanică Auto",
        0,
        "Martor Check Engine aprins la rece pe VW Golf 7, necesită diagnoză VCDS în parcarea din Hipodrom.",
        "accepted",
        240,
        quote=150,
        dur="1 oră",
        dur_min=60,
        scheduled=sms.format_ro_slot(slot2_start, slot2_end),
        start_ts=slot2_start,
        end_ts=slot2_end,
        neighborhood="Hipodrom",
        window="Mâine, 09:00",
        notes="Vin cu testerul mobil direct la mașină.",
    )
    sms.schedule_anti_noshow_reminders(
        conn,
        b_conf2,
        "+40 721 555 010",
        "Ionuț Dragomir",
        "HERMANNSTADT AUTO GARAGE S.R.L.",
        "Diagnoză auto computerizată (Sibiu)",
        150,
        slot2_start,
        slot2_end,
    )

    # 4. Completed today & historical jobs for revenue / retention analytics
    slot_done_start = _day_slot_ts(0, 9, 30)
    booking(
        "mihai@rezolv.ro",
        binder,
        "Instalații Sanitare",
        1,
        "Scurgere bucătărie înfundată în cartierul Ștrand.",
        "completed",
        300,
        quote=160,
        dur="1 oră",
        dur_min=60,
        scheduled="Azi, 09:30–10:30",
        start_ts=slot_done_start,
        end_ts=slot_done_start + 3600,
        neighborhood="Ștrand",
        review=(5, "A ajuns la fix în Ștrand, a rezolvat în 45 minute. Recomand!"),
    )

    for i in range(7):
        hist_start = _day_slot_ts(-(i + 1), 11, 0)
        booking(
            "client@rezolv.ro",
            binder,
            "Instalații Sanitare",
            i % 3,
            f"Intervenție tehnică finalizată în Sibiu ({SIBIU_ZONES[i % len(SIBIU_ZONES)]}).",
            "completed",
            1440 * (i + 2),
            quote=180 + 25 * i,
            dur="1.5 ore",
            dur_min=90,
            scheduled=sms.format_ro_slot(hist_start, hist_start + 5400),
            start_ts=hist_start,
            end_ts=hist_start + 5400,
            neighborhood=SIBIU_ZONES[i % len(SIBIU_ZONES)],
        )

    # Seed sample analytics telemetry for PostHog / Investor Dashboard
    for uid in pro_ids.values():
        analytics.track(conn, uid, "pro", "calendar_opened", {"city": "Sibiu", "source": "mobile_b2b"})
    analytics.track(conn, binder, "pro", "estimate_sent", {"booking_id": b_est, "price_ron": 190, "duration_min": 90})
    analytics.track(conn, clients["andreea@rezolv.ro"], "client", "estimate_accepted", {"booking_id": b_conf1, "price_ron": 380})
    analytics.track(conn, clients["client@rezolv.ro"], "client", "booking_requested", {"booking_id": b_est, "neighborhood": "Hipodrom"})

    conn.commit()
    return True
