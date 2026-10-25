import sqlite3
import json
import os
import uuid
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rezolv.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Profiles Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id TEXT PRIMARY KEY,
        role TEXT NOT NULL DEFAULT 'client',
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone TEXT,
        city TEXT NOT NULL DEFAULT 'Sibiu',
        address TEXT,
        avatar TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # 2. Professionals Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS professionals (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        company_name TEXT NOT NULL,
        cui TEXT NOT NULL UNIQUE,
        reg_com TEXT,
        headquarters TEXT,
        is_verified INTEGER NOT NULL DEFAULT 1,
        verification_status TEXT NOT NULL DEFAULT 'verified',
        rating REAL NOT NULL DEFAULT 0.0,
        reviews_count INTEGER NOT NULL DEFAULT 0,
        category TEXT NOT NULL,
        response_time TEXT NOT NULL DEFAULT '~15 min',
        location TEXT NOT NULL DEFAULT 'Sibiu',
        service_radius_km INTEGER NOT NULL DEFAULT 25,
        price_range TEXT NOT NULL,
        avatar TEXT,
        bio TEXT,
        is_available INTEGER NOT NULL DEFAULT 1,
        completed_jobs INTEGER NOT NULL DEFAULT 0,
        working_hours_json TEXT,
        covered_neighborhoods_json TEXT,
        accepted_payment_methods_json TEXT,
        subscription_tier TEXT NOT NULL DEFAULT 'pro_partner',
        subscription_expires_at TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # 3. Services Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS services (
        id TEXT PRIMARY KEY,
        professional_id TEXT NOT NULL,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        price_min REAL NOT NULL,
        price_max REAL NOT NULL,
        unit TEXT DEFAULT 'lucrare',
        duration TEXT NOT NULL,
        FOREIGN KEY (professional_id) REFERENCES professionals (id)
    );
    """)

    # 4. Bookings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id TEXT PRIMARY KEY,
        pro_id TEXT NOT NULL,
        pro_name TEXT NOT NULL,
        company TEXT NOT NULL,
        client_name TEXT NOT NULL,
        client_phone TEXT,
        service_name TEXT NOT NULL,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        address TEXT NOT NULL,
        neighborhood TEXT,
        price_est TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        notes TEXT,
        has_reviewed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (pro_id) REFERENCES professionals (id)
    );
    """)

    # 5. Reviews Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id TEXT PRIMARY KEY,
        booking_id TEXT,
        pro_id TEXT NOT NULL,
        client_name TEXT NOT NULL,
        rating INTEGER NOT NULL,
        date TEXT NOT NULL,
        comment TEXT NOT NULL,
        service TEXT NOT NULL,
        tag_punctual INTEGER DEFAULT 1,
        tag_fair_price INTEGER DEFAULT 1,
        tag_invoice INTEGER DEFAULT 1,
        tag_quality INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (pro_id) REFERENCES professionals (id)
    );
    """)

    # Seed initial data if empty
    cursor.execute("SELECT count(*) FROM professionals;")
    if cursor.fetchone()[0] == 0:
        seed_data(cursor)

    conn.commit()
    conn.close()

def seed_data(cursor):
    now = datetime.utcnow().isoformat()

    # Seed Client Profile
    cursor.execute("""
    INSERT INTO profiles (id, role, name, email, phone, city, address, avatar, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        'usr-client-1', 'client', 'Alexandru Popa', 'alexandru.popa@email.ro',
        '0745 123 456', 'Sibiu', 'Str. Mitropoliei 14, Ap. 3',
        'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=160&auto=format&fit=crop&q=80',
        now
    ))

    # Seed Pros
    pros_data = [
        (
            'pro-1', 'Radu Munteanu', 'S.C. INSTAL EXPERT S.R.L.', 'RO41928310',
            'J32/450/2019', 'Str. Turnului nr. 12, Sibiu', 1, 'verified', 4.94, 52,
            'Instalații Sanitare & Termice', '~15 min', 'Sibiu & Șelimbăr', 25,
            '80 – 450 RON',
            'https://images.unsplash.com/photo-1560250097-0b93528c311a?w=160&auto=format&fit=crop&q=80',
            'Instalator autorizat cu peste 11 ani de experiență în Sibiu. Intervenții rapide la avarii, montaj centrale, instalații sanitare și încălzire în pardoseală. Ofer factură, chitanță și garanție scrisă pentru fiecare lucrare.',
            1, 184,
            json.dumps({"monday": "08:00 - 18:00", "saturday": "09:00 - 14:00", "emergency": True}),
            json.dumps(['Centru', 'Trei Stejari', 'Hipodrom', 'Vasile Aaron', 'Șelimbăr', 'Turnișor', 'Valea Aurie']),
            json.dumps(['cash', 'pos_card', 'bank_transfer', 'revolut']),
            'pro_partner', '2026-11-15T00:00:00Z', now
        ),
        (
            'pro-2', 'Cristi Avram', 'ELECTRO SIB SOLUTIONS S.R.L.', 'RO38902144',
            'J32/112/2018', 'Str. Stefan cel Mare 45, Sibiu', 1, 'verified', 4.88, 39,
            'Instalații Electrice & Tablouri', '~20 min', 'Sibiu și împrejurimi', 30,
            '100 – 450 RON',
            'https://images.unsplash.com/photo-1540569014015-19a7be504e3a?w=160&auto=format&fit=crop&q=80',
            'Electrician autorizat ANRE. Execut instalații electrice complete, înlocuire tablouri siguranțe automate, prize, întrerupătoare și iluminat LED.',
            1, 112,
            json.dumps({"monday": "08:00 - 19:00", "saturday": "09:00 - 15:00", "emergency": True}),
            json.dumps(['Centru', 'Terezian', 'Valea Aurie', 'Șelimbăr', 'Cisnădie']),
            json.dumps(['cash', 'pos_card', 'bank_transfer']),
            'pro_partner', '2026-11-15T00:00:00Z', now
        ),
        (
            'pro-3', 'Andrei Mihai', 'AUTO MOBIL SIB SERVICE S.R.L.', 'RO44102931',
            'J32/890/2021', 'Calea Șurii Mici nr. 2, Sibiu', 1, 'verified', 4.91, 28,
            'Auto & Diagnoză Mobilă', '~30 min', 'Sibiu și autostrada A1', 40,
            '120 – 600 RON',
            'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=160&auto=format&fit=crop&q=80',
            'Diagnoză auto computerizată la domiciliu sau pe traseu, pornire cabluri robot, vulcanizare mobilă și remediere avarii rapide.',
            1, 94,
            json.dumps({"monday": "07:00 - 22:00", "saturday": "08:00 - 20:00", "emergency": True}),
            json.dumps(['Toate cartierele din Sibiu', 'Autostrada A1 Sibiu-Sebeș']),
            json.dumps(['cash', 'pos_card', 'revolut']),
            'pro_partner', '2026-11-15T00:00:00Z', now
        )
    ]

    for p in pros_data:
        cursor.execute("""
        INSERT INTO professionals (
            id, name, company_name, cui, reg_com, headquarters, is_verified,
            verification_status, rating, reviews_count, category, response_time,
            location, service_radius_km, price_range, avatar, bio, is_available,
            completed_jobs, working_hours_json, covered_neighborhoods_json,
            accepted_payment_methods_json, subscription_tier, subscription_expires_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, p)

    # Seed Services for pro-1, pro-2, pro-3
    services_all = [
        ('s1', 'pro-1', 'Sanitare', 'Înlocuire baterie chiuvetă / cadă', 90, 140, 'lucrare', '30-45 min'),
        ('s2', 'pro-1', 'Urgențe', 'Desfundare canalizare / scurgere baie', 120, 260, 'lucrare', '45-90 min'),
        ('s3', 'pro-1', 'Sanitare', 'Înlocuire sau reparare vas WC / rezervor', 110, 200, 'lucrare', '1 oră'),
        ('s4', 'pro-1', 'Termice', 'Montaj centrală termică murală + probe ISCIR', 650, 1100, 'lucrare', '4-6 ore'),
        ('se1', 'pro-2', 'Tablouri', 'Înlocuire tablou electric siguranțe automate', 250, 450, 'lucrare', '2-3 ore'),
        ('se2', 'pro-2', 'Reparații', 'Schimbare prize / întrerupătoare (până la 5 buc)', 100, 180, 'lucrare', '1 oră'),
        ('se3', 'pro-2', 'Urgențe', 'Diagnosticare scurtcircuit & remediere', 120, 250, 'lucrare', '1-2 ore'),
        ('sa1', 'pro-3', 'Diagnoză', 'Diagnoză computerizată OBD la domiciliu', 120, 180, 'lucrare', '30 min'),
        ('sa2', 'pro-3', 'Urgențe', 'Asistență pornire baterie descărcată (Robot)', 100, 150, 'lucrare', '20 min'),
        ('sa3', 'pro-3', 'Mecanică', 'Schimb plăcuțe frână față/spate', 150, 250, 'lucrare', '1-2 ore')
    ]
    for s in services_all:
        cursor.execute("INSERT INTO services VALUES (?, ?, ?, ?, ?, ?, ?, ?)", s)

    # Seed initial Bookings
    bookings_data = [
        ('b-101', 'pro-1', 'Radu Munteanu', 'S.C. INSTAL EXPERT S.R.L.', 'Alexandru Popa', '0745 123 456', 'Înlocuire baterie lavoar & racorduri', '2026-10-21', '14:30', 'Str. Mitropoliei 14, Ap. 3', 'Centru', '90 – 140 RON', 'pending', 'Picură racordul flexibil cu apă caldă.', 0, now),
        ('b-102', 'pro-1', 'Radu Munteanu', 'S.C. INSTAL EXPERT S.R.L.', 'Ioana Cristea', '0740 987 654', 'Desfundare scurgere duș', '2026-10-22', '10:00', 'Bd. Mihai Viteazu 22, Ap. 12', 'Hipodrom', '120 – 260 RON', 'confirmed', 'Apa se scurge foarte greu din cădiță.', 0, now),
        ('b-103', 'pro-1', 'Radu Munteanu', 'S.C. INSTAL EXPERT S.R.L.', 'Marius Stan', '0722 334 455', 'Montaj centrală termică', '2026-10-18', '09:00', 'Str. Livezii nr. 4, Șelimbăr', 'Șelimbăr', '850 RON', 'completed', 'Lucrare finalizată cu succes. Factură emisă.', 0, now)
    ]
    for b in bookings_data:
        cursor.execute("INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", b)

    # Seed Reviews for pro-1
    reviews_data = [
        ('r1', 'b-103', 'pro-1', 'Mihai D. (Sibiu, Trei Stejari)', 5, 'Ieri', 'A ajuns în 25 de minute pentru o țeavă spartă sub chiuvetă. Foarte curat, profesionist, factură pe loc. Recomand cu încredere!', 'Urgență instalație sanitară', 1, 1, 1, 1, now),
        ('r2', 'b-102', 'pro-1', 'Elena V. (Sibiu, Hipodrom)', 5, '14 Octombrie', 'A montat centrala și 4 calorifere. Prețul a fost exact în plaja discutată inițial, fără costuri ascunse.', 'Montaj centrală termică', 1, 1, 1, 1, now)
    ]
    for r in reviews_data:
        cursor.execute("INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", r)

# API Helpers
def list_professionals(query=None, category=None):
    conn = get_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM professionals WHERE 1=1"
    params = []
    if category:
        sql += " AND category LIKE ?"
        params.append(f"%{category}%")
    if query:
        sql += " AND (name LIKE ? OR company_name LIKE ? OR category LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])
    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]

    for r in rows:
        cursor.execute("SELECT * FROM services WHERE professional_id = ?", (r['id'],))
        r['services'] = [dict(s) for s in cursor.fetchall()]
        cursor.execute("SELECT * FROM reviews WHERE pro_id = ?", (r['id'],))
        r['reviews'] = [dict(rev) for rev in cursor.fetchall()]
        if r.get('covered_neighborhoods_json'):
            r['covered_neighborhoods'] = json.loads(r['covered_neighborhoods_json'])
        if r.get('working_hours_json'):
            r['working_hours'] = json.loads(r['working_hours_json'])
        if r.get('accepted_payment_methods_json'):
            r['accepted_payment_methods'] = json.loads(r['accepted_payment_methods_json'])

    conn.close()
    return rows

def create_booking(data):
    conn = get_connection()
    cursor = conn.cursor()
    booking_id = f"b-{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO bookings (id, pro_id, pro_name, company, client_name, client_phone, service_name, date, time, address, neighborhood, price_est, status, notes, has_reviewed, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, 0, ?)
    """, (
        booking_id, data.get('pro_id'), data.get('pro_name'), data.get('company'),
        data.get('client_name'), data.get('client_phone'), data.get('service_name'),
        data.get('date'), data.get('time'), data.get('address'), data.get('neighborhood', 'Centru'),
        data.get('price_est'), data.get('notes'), now
    ))
    conn.commit()
    conn.close()
    return {"id": booking_id, "status": "pending"}

def update_booking_status(booking_id, new_status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE bookings SET status = ? WHERE id = ?", (new_status, booking_id))
    conn.commit()
    conn.close()
    return {"id": booking_id, "status": new_status}

def add_review(data):
    conn = get_connection()
    cursor = conn.cursor()
    rev_id = f"r-{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow().isoformat()
    pro_id = data.get('pro_id')
    rating = int(data.get('rating', 5))

    cursor.execute("""
    INSERT INTO reviews (id, booking_id, pro_id, client_name, rating, date, comment, service, tag_punctual, tag_fair_price, tag_invoice, tag_quality, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        rev_id, data.get('booking_id'), pro_id, data.get('client_name'), rating,
        'Astăzi', data.get('comment'), data.get('service'),
        data.get('tag_punctual', 1), data.get('tag_fair_price', 1),
        data.get('tag_invoice', 1), data.get('tag_quality', 1), now
    ))

    # Mark booking has_reviewed
    if data.get('booking_id'):
        cursor.execute("UPDATE bookings SET has_reviewed = 1 WHERE id = ?", (data.get('booking_id'),))

    # Recalculate Pro rating
    cursor.execute("SELECT avg(rating), count(*) FROM reviews WHERE pro_id = ?", (pro_id,))
    avg_rating, total_revs = cursor.fetchone()
    if avg_rating is not None:
        cursor.execute("UPDATE professionals SET rating = ?, reviews_count = ? WHERE id = ?", (round(avg_rating, 2), total_revs, pro_id))

    conn.commit()
    conn.close()
    return {"id": rev_id, "new_rating": round(avg_rating, 2) if avg_rating else rating}

def verify_cui(cui):
    # Simulated ANAF validation check
    cui_clean = cui.upper().replace('RO', '').strip()
    is_valid_format = len(cui_clean) >= 6 and len(cui_clean) <= 10 and cui_clean.isdigit()
    return {
        "cui": cui,
        "is_valid": is_valid_format,
        "status": "ACTIV FISCAL" if is_valid_format else "INVALID",
        "company_name": "S.C. INSTAL EXPERT S.R.L." if cui_clean == "41928310" else "FIRMĂ VERIFICATĂ ANAF",
        "tva_payer": True,
        "city": "Sibiu"
    }

if __name__ == "__main__":
    init_db()
    print("✓ SQLite Database initialized at", DB_PATH)
