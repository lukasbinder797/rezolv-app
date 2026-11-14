"""Adversarial Empirical Test Suite: Milestone 1 Challenger 1

Stress-testing:
1. Migration idempotency (5x runs on fresh and legacy databases)
2. Slug uniqueness enforcement and sqlite3.IntegrityError
3. Romanian diacritics, special characters, and collision handling
4. Legacy demo pros queryability in rezolv.db
"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rezolv import core, db, services  # noqa: E402


class TestAdversarialM1Challenger1(unittest.TestCase):
    def test_migration_idempotency_fresh_database(self):
        """Run init_db() 5 times consecutively on a fresh database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "fresh_idempotent.db")
            for i in range(5):
                db.init_db(db_path)
            
            conn = db.connect(db_path)
            # Verify table and unique index exist
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(pro_profiles)").fetchall()}
            self.assertIn("slug", cols)
            idx = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pro_profiles_slug'"
            ).fetchone()
            self.assertIsNotNone(idx)
            conn.close()

    def test_migration_idempotency_legacy_database(self):
        """Run init_db() 5 times consecutively on a legacy database lacking slug column."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "legacy_idempotent.db")
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'client',
                    name TEXT NOT NULL,
                    phone TEXT,
                    city TEXT NOT NULL DEFAULT 'Sibiu',
                    neighborhood TEXT NOT NULL DEFAULT 'Centru',
                    address TEXT,
                    avatar_url TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    last_login_at INTEGER
                );
            """)
            conn.execute("""
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
            """)
            conn.execute(
                "INSERT INTO users (id, email, password_hash, role, name, created_at) "
                "VALUES ('u_marian', 'marian@rezolv.ro', 'pw', 'pro', 'Marian Popescu', 1000)"
            )
            conn.execute(
                "INSERT INTO pro_profiles (user_id, company_name, cui, verification_status, plan_status) "
                "VALUES ('u_marian', 'Instal Prest SRL', 'RO12345678', 'verified', 'active')"
            )
            conn.commit()
            conn.close()

            # Execute init_db 5 times consecutively
            for i in range(5):
                db.init_db(db_path)

            conn = db.connect(db_path)
            row = conn.execute("SELECT slug FROM pro_profiles WHERE user_id='u_marian'").fetchone()
            self.assertEqual(row["slug"], "marian-popescu-instalator")
            conn.close()

    def test_slug_uniqueness_enforcement(self):
        """Inserting two pros with identical slugs must raise sqlite3.IntegrityError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "slug_unique.db")
            db.init_db(db_path)
            conn = db.connect(db_path)

            conn.execute(
                "INSERT INTO users (id, email, password_hash, role, name, created_at) "
                "VALUES ('u1', 'pro1@test.ro', 'pw', 'pro', 'Pro 1', 100)"
            )
            conn.execute(
                "INSERT INTO pro_profiles (user_id, slug, company_name, cui) "
                "VALUES ('u1', 'duplicate-slug', 'Firm 1', 'RO111')"
            )
            conn.commit()

            conn.execute(
                "INSERT INTO users (id, email, password_hash, role, name, created_at) "
                "VALUES ('u2', 'pro2@test.ro', 'pw', 'pro', 'Pro 2', 100)"
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO pro_profiles (user_id, slug, company_name, cui) "
                    "VALUES ('u2', 'duplicate-slug', 'Firm 2', 'RO222')"
                )
            conn.close()

    def test_romanian_diacritics_and_special_characters(self):
        """Test Romanian characters (ă, î, ș, ț, â, and legacy cedillas ş, ţ) and symbols."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "slug_gen.db")
            db.init_db(db_path)
            conn = db.connect(db_path)

            test_cases = [
                ("Curățenie Șic & Zugrăveli Țintești", "curatenie-sic-zugraveli-tintesti"),
                ("Lăcătușerie & Tâmplărie Fier", "lacatuserie-tamplarie-fier"),
                ("Ștefan cel Mare & Țiriac Auto", "stefan-cel-mare-tiriac-auto"),
                ("Şerban Ţurcanu Împreună", "serban-turcanu-impreuna"),
                ("ĂÂÎȘȚ-ăâîșț-ŞŢşţ", "aaist-aaist-stst"),
                ("Instalații S.R.L. / P.F.A. & Fii!", "instalatii-s-r-l-p-f-a-fii"),
                ("  ---  Electrician Pro --- ", "electrician-pro"),
                ("🔧 Mesterul priceput 😊 (Sibiu) #1", "mesterul-priceput-sibiu-1"),
                ("", "pro"),
                ("   ", "pro"),
                ("---", "pro"),
                ("!@#$%^&*()", "pro"),
            ]
            for raw, expected in test_cases:
                slug = services.generate_pro_slug(conn, raw)
                self.assertEqual(slug, expected, f"Failed for raw input {raw!r}")
            conn.close()

    def test_collision_handling_sequence(self):
        """Verify collision handling with repeated company names producing -2, -3, etc."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "slug_coll.db")
            db.init_db(db_path)
            conn = db.connect(db_path)

            slugs = []
            for i in range(1, 11):
                uid = f"u_c_{i}"
                slug = services.generate_pro_slug(conn, "Instalator Sibiu")
                slugs.append(slug)
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, role, name, created_at) "
                    "VALUES (?, ?, 'pw', 'pro', 'Name', 100)",
                    (uid, f"c{i}@test.ro"),
                )
                conn.execute(
                    "INSERT INTO pro_profiles (user_id, slug, company_name, cui) "
                    "VALUES (?, ?, 'Instalator Sibiu', ?)",
                    (uid, slug, f"RO{i:05d}"),
                )
                conn.commit()

            self.assertEqual(slugs[0], "instalator-sibiu")
            self.assertEqual(slugs[1], "instalator-sibiu-2")
            self.assertEqual(slugs[2], "instalator-sibiu-3")
            self.assertEqual(slugs[9], "instalator-sibiu-10")

            # Same user updating profile keeps their existing slug
            self.assertEqual(
                services.generate_pro_slug(conn, "Instalator Sibiu", user_id="u_c_1"),
                "instalator-sibiu",
            )
            self.assertEqual(
                services.generate_pro_slug(conn, "Instalator Sibiu", user_id="u_c_2"),
                "instalator-sibiu-2",
            )
            conn.close()

    def test_legacy_data_backfill_rezolv_db(self):
        """Verify that existing demo pros in rezolv.db can all be queried by slug."""
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "rezolv.db")
        conn = db.connect(db_path)
        demo_slugs = [
            "binder-lukas-instalator",
            "marian-popescu-instalator",
            "andrei-munteanu-electrician",
            "radu-petrescu-instalatii",
            "ionut-dragomir-mecanic",
            "catalin-stoica-vulcanizare",
            "sorin-toma-finisaje",
            "mirela-ene-curatenie",
            "vlad-lacatusu-lacatus",
        ]
        for slug in demo_slugs:
            res = services.get_professional(conn, slug)
            self.assertIn("professional", res)
            prof = res["professional"]
            self.assertEqual(prof["slug"], slug)
            self.assertTrue(prof["company_name"])
            self.assertTrue(prof["cui"])
            self.assertIsInstance(prof["zones"], list)
            self.assertIsInstance(prof["hours"], dict)
            self.assertIsInstance(prof["recent_reviews"], list)
        conn.close()

    def test_get_professional_access_control(self):
        """Unverified and past_due pros must not be accessible via slug."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "access.db")
            db.init_db(db_path)
            conn = db.connect(db_path)

            conn.execute(
                "INSERT INTO users (id, email, password_hash, role, name, created_at) "
                "VALUES ('u_pen', 'pen@test.ro', 'pw', 'pro', 'Pen', 100)"
            )
            conn.execute(
                "INSERT INTO pro_profiles (user_id, slug, company_name, cui, verification_status, plan_status) "
                "VALUES ('u_pen', 'pending-pro', 'Pen SRL', 'RO777', 'pending', 'trial')"
            )
            conn.commit()

            with self.assertRaises(core.ApiError) as ctx:
                services.get_professional(conn, "pending-pro")
            self.assertEqual(ctx.exception.status, 404)
            conn.close()


if __name__ == "__main__":
    unittest.main()
