"""Milestone 1 Test Suite: Public Pro Slugs, Dynamic Ratings & Pricing Alignment."""
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rezolv import core, db, payments, seed, server, services  # noqa: E402


class TestM1SlugsAndRatings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.data_dir, "test_m1.db")
        cls.srv, cls.ctx = server.create_server("127.0.0.1", 0, cls.db_path)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        if cls.srv is not None:
            cls.srv.shutdown()
            cls.srv.server_close()

    def call(self, method, path, body=None, token=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = "Bearer " + token

        req = urllib.request.Request(self.base + path, data=data, method=method)
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw.decode()) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read()
            return e.code, json.loads(raw.decode()) if raw else {}

    def login(self, email, role="pro"):
        status, body = self.call("POST", "/api/auth/login", {"email": email, "password": seed.DEMO_PASSWORD})
        self.assertEqual(status, 200)
        return body["token"]

    def test_slug_present_in_public_pro_list_and_detail(self):
        # 1. Check list_professionals exposes slug
        status, body = self.call("GET", "/api/professionals?category=Instala%C8%9Bii%20Sanitare")
        self.assertEqual(status, 200)
        pros = body["professionals"]
        self.assertTrue(len(pros) > 0)
        for p in pros:
            self.assertIn("slug", p)
            self.assertTrue(p["slug"] is None or isinstance(p["slug"], str))

        # Check seeded pro has exact canonical slug
        binder = next((p for p in pros if p["name"] == "Binder Lukas"), None)
        self.assertIsNotNone(binder)
        self.assertEqual(binder["slug"], "binder-lukas-instalator")

        # 2. Check get_professional detail exposes slug
        status_det, body_det = self.call("GET", f"/api/professionals/{binder['id']}")
        self.assertEqual(status_det, 200)
        self.assertEqual(body_det["professional"]["slug"], "binder-lukas-instalator")

    def test_lookup_by_slug_and_case_insensitivity(self):
        # 1. Lookup by canonical slug
        status, body = self.call("GET", "/api/professionals/binder-lukas-instalator")
        self.assertEqual(status, 200)
        pro = body["professional"]
        self.assertEqual(pro["name"], "Binder Lukas")
        self.assertEqual(pro["slug"], "binder-lukas-instalator")

        # 2. Lookup with uppercase/mixed case
        status_upper, body_upper = self.call("GET", "/api/professionals/BINDER-LUKAS-INSTALATOR")
        self.assertEqual(status_upper, 200)
        self.assertEqual(body_upper["professional"]["id"], pro["id"])

        status_mixed, body_mixed = self.call("GET", "/api/professionals/Binder-Lukas-Instalator")
        self.assertEqual(status_mixed, 200)
        self.assertEqual(body_mixed["professional"]["id"], pro["id"])

        # 3. Lookup other demo pros by slug
        demo_slugs = [
            "marian-popescu-instalator",
            "andrei-munteanu-electrician",
            "radu-petrescu-instalatii",
            "ionut-dragomir-mecanic",
            "catalin-stoica-vulcanizare",
            "sorin-toma-finisaje",
            "mirela-ene-curatenie",
            "vlad-lacatusu-lacatus",
        ]
        for s in demo_slugs:
            st, res = self.call("GET", f"/api/professionals/{s}")
            self.assertEqual(st, 200, f"Slug {s} failed to resolve")
            self.assertEqual(res["professional"]["slug"], s)

    def test_lookup_unknown_slug_returns_404(self):
        status, body = self.call("GET", "/api/professionals/slug-care-nu-exista-404")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "not_found")

    def test_pro_dashboard_dynamic_ratings_and_speed(self):
        token = self.login("mester@rezolv.ro", "pro")
        status, body = self.call("GET", "/api/pro/dashboard", token=token)
        self.assertEqual(status, 200)
        self.assertIn("rating_avg", body)
        self.assertIn("rating_count", body)
        self.assertIn("response_speed", body)
        self.assertIsInstance(body["rating_avg"], (int, float))
        self.assertIsInstance(body["rating_count"], int)
        self.assertIsInstance(body["response_speed"], str)
        self.assertIn("min", body["response_speed"])

    def test_response_speed_formatting_unit(self):
        # Known timestamp offsets
        self.assertEqual(services.format_response_speed(None), "~15 min")
        self.assertEqual(services.format_response_speed(-10), "~15 min")
        self.assertEqual(services.format_response_speed(30), "1 min")
        self.assertEqual(services.format_response_speed(720), "12 min")  # 12 min
        self.assertEqual(services.format_response_speed(3600), "1 oră")
        self.assertEqual(services.format_response_speed(5400), "1.5 ore")
        self.assertEqual(services.format_response_speed(7200), "2 ore")

    def test_essential_plan_checkout_price_eur_10(self):
        # Marian is seeded with 'pro' plan; downgrade/switch to 'essential'
        token = self.login("marian@rezolv.ro", "pro")
        status, body = self.call(
            "POST",
            "/api/subscription/checkout",
            {"plan": "essential", "card": {"number": "4242424242424242", "exp": "12/28", "cvc": "123"}},
            token=token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["plan"], "essential")
        self.assertEqual(body["price_eur"], 10)

        # Check DB directly to ensure subscription_price_eur is 10
        conn = db.connect(self.db_path)
        row = conn.execute(
            "SELECT subscription_price_eur, plan FROM pro_profiles WHERE user_id=(SELECT id FROM users WHERE email='marian@rezolv.ro')"
        ).fetchone()
        self.assertEqual(row["subscription_price_eur"], 10)
        self.assertEqual(row["plan"], "essential")

    def test_safe_migration_and_idempotency_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_db = os.path.join(tmp, "legacy.db")
            conn = db.connect(tmp_db)
            # Create a legacy pro_profiles table without slug
            conn.executescript("""
            CREATE TABLE users (
              id TEXT PRIMARY KEY,
              email TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL,
              name TEXT NOT NULL,
              phone TEXT,
              city TEXT NOT NULL DEFAULT 'Sibiu',
              neighborhood TEXT NOT NULL DEFAULT 'Centru',
              address TEXT,
              email_verified INTEGER NOT NULL DEFAULT 0,
              cookie_consent_json TEXT,
              created_at INTEGER NOT NULL,
              last_login_at INTEGER NOT NULL,
              is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE pro_profiles (
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
              verification_status TEXT NOT NULL DEFAULT 'pending',
              verification_note TEXT,
              verified_at INTEGER,
              onboarded_by_admin INTEGER NOT NULL DEFAULT 0,
              rating_avg REAL NOT NULL DEFAULT 0,
              rating_count INTEGER NOT NULL DEFAULT 0,
              jobs_completed INTEGER NOT NULL DEFAULT 0,
              availability TEXT NOT NULL DEFAULT 'Disponibil astăzi',
              distance_km REAL NOT NULL DEFAULT 2.5,
              plan TEXT NOT NULL DEFAULT 'essential',
              plan_status TEXT NOT NULL DEFAULT 'trial',
              subscription_price_eur INTEGER NOT NULL DEFAULT 39,
              plan_renews_at INTEGER
            );
            INSERT INTO users (id,email,password_hash,role,name,phone,city,neighborhood,address,created_at,last_login_at)
            VALUES ('u_marian', 'marian@rezolv.ro', 'hash', 'pro', 'Marian Popescu', '0700', 'Sibiu', 'Centru', 'Str 1', 1000, 1000);
            INSERT INTO pro_profiles (user_id,company_name,cui)
            VALUES ('u_marian', 'SIBIU TERMO SERV', 'RO3918225');
            """)
            conn.commit()
            conn.close()

            # First run: safe migration adds column, unique index, and backfills
            db.init_db(tmp_db)
            conn = db.connect(tmp_db)
            row = conn.execute("SELECT slug FROM pro_profiles WHERE user_id='u_marian'").fetchone()
            self.assertEqual(row["slug"], "marian-popescu-instalator")

            # Verify unique index exists
            idx = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pro_profiles_slug'").fetchone()
            self.assertIsNotNone(idx)
            conn.close()

            # Second run: must be completely idempotent
            db.init_db(tmp_db)
            conn = db.connect(tmp_db)
            row2 = conn.execute("SELECT slug FROM pro_profiles WHERE user_id='u_marian'").fetchone()
            self.assertEqual(row2["slug"], "marian-popescu-instalator")

            # Unique constraint violation check
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO pro_profiles (user_id,slug,company_name,cui) VALUES ('u_dup','marian-popescu-instalator','Other','RO99999')"
                )
            conn.close()

    def test_pro_slug_generation_and_uniqueness(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_db = os.path.join(tmp, "slug_test.db")
            db.init_db(tmp_db)
            conn = db.connect(tmp_db)

            # Romanian diacritics normalization
            slug1 = services.generate_pro_slug(conn, "CIBIN INSTALAȚII S.R.L.")
            self.assertEqual(slug1, "cibin-instalatii-s-r-l")

            # Collision avoidance
            conn.execute(
                "INSERT INTO users (id,email,password_hash,role,name,city,neighborhood,created_at,last_login_at) "
                "VALUES ('u_1','p1@r.ro','h','pro','P1','Sibiu','Centru',1,1)"
            )
            conn.execute("INSERT INTO pro_profiles (user_id,slug,company_name,cui) VALUES ('u_1','cibin-instalatii-s-r-l','Cibin','RO111')")

            slug2 = services.generate_pro_slug(conn, "CIBIN INSTALAȚII S.R.L.")
            self.assertEqual(slug2, "cibin-instalatii-s-r-l-2")

            slug3 = services.generate_pro_slug(conn, "CIBIN INSTALAȚII S.R.L.", user_id="u_1")
            # Same user can keep its own slug
            self.assertEqual(slug3, "cibin-instalatii-s-r-l")
            conn.close()


if __name__ == "__main__":
    unittest.main()
