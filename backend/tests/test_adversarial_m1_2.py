"""Adversarial Empirical Verification Suite for Milestone 1 (Challenger 2).

Targets:
1. Pro lookup boundary cases (case-insensitivity, unverified/inactive pros, malformed/SQLi IDs).
2. Dynamic ratings & response speed calculations (0 reviews, 10 varying reviews, 0 estimates, multiple/superseded estimates).
3. Subscription checkout (Essential 10 EUR / 49 RON, Pro 39 EUR / 195 RON, decline handling).
"""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rezolv import core, db, payments, seed, server, services  # noqa: E402


class TestAdversarialM1Challenger2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.data_dir, "test_adversarial_m1.db")
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

    # =========================================================================
    # Group 1: Pro Lookup Boundary Cases
    # =========================================================================

    def test_slug_case_insensitivity_matrix(self):
        """Verify case insensitivity across variations for seeded pros."""
        variations = [
            "BINDER-LUKAS-INSTALATOR",
            "Binder-Lukas-Instalator",
            "bInDeR-lUkAs-InStAlAtOr",
            "binder-lukas-INSTALATOR",
        ]
        for var in variations:
            status, body = self.call("GET", f"/api/professionals/{var}")
            self.assertEqual(status, 200, f"Failed resolving case variant: {var}")
            self.assertEqual(body["professional"]["slug"], "binder-lukas-instalator")
            self.assertEqual(body["professional"]["name"], "Binder Lukas")

        # Test case insensitivity via direct service invocation
        conn = db.connect(self.db_path)
        for var in variations:
            res = services.get_professional(conn, var)
            self.assertEqual(res["professional"]["slug"], "binder-lukas-instalator")

    def test_unverified_or_inactive_pro_cannot_be_accessed_by_slug(self):
        """Unverified, rejected, inactive, or cancelled pros MUST return 404."""
        conn = db.connect(self.db_path)
        # 1. Create a test user with a slug but verification_status='pending'
        uid_pending = "adv_user_pending"
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, name, phone, created_at, last_login_at, is_active) "
            "VALUES (?, ?, 'hash', 'pro', 'Pending Pro', '+40700000001', 1700000000, 1700000000, 1)",
            (uid_pending, "pending@test.ro"),
        )
        conn.execute(
            "INSERT INTO pro_profiles (user_id, company_name, cui, slug, verification_status, plan, plan_status, "
            "zones_json, hours_json) VALUES (?, 'Pending SRL', 'RO999001', 'pending-pro-slug', 'pending', 'essential', 'trial', '[]', '{}')",
            (uid_pending,),
        )
        conn.commit()

        # Query pending pro via HTTP and direct service -> 404
        status, body = self.call("GET", "/api/professionals/pending-pro-slug")
        self.assertEqual(status, 404)
        with self.assertRaises(core.ApiError) as cm:
            services.get_professional(conn, "pending-pro-slug")
        self.assertEqual(cm.exception.status, 404)

        # 2. Update to verification_status='rejected' -> 404
        conn.execute("UPDATE pro_profiles SET verification_status='rejected' WHERE user_id=?", (uid_pending,))
        conn.commit()
        status, _ = self.call("GET", "/api/professionals/pending-pro-slug")
        self.assertEqual(status, 404)

        # 3. Verified, but user is_active=0 -> 404
        conn.execute("UPDATE pro_profiles SET verification_status='verified' WHERE user_id=?", (uid_pending,))
        conn.execute("UPDATE users SET is_active=0 WHERE id=?", (uid_pending,))
        conn.commit()
        status, _ = self.call("GET", "/api/professionals/pending-pro-slug")
        self.assertEqual(status, 404)

        # 4. Verified and active, but plan_status='past_due' -> 404
        conn.execute("UPDATE users SET is_active=1 WHERE id=?", (uid_pending,))
        conn.execute("UPDATE pro_profiles SET plan_status='past_due' WHERE user_id=?", (uid_pending,))
        conn.commit()
        status, _ = self.call("GET", "/api/professionals/pending-pro-slug")
        self.assertEqual(status, 404)

        # 5. Restore to plan_status='active' -> now 200!
        conn.execute("UPDATE pro_profiles SET plan_status='active' WHERE user_id=?", (uid_pending,))
        conn.commit()
        status, body = self.call("GET", "/api/professionals/pending-pro-slug")
        self.assertEqual(status, 200)
        self.assertEqual(body["professional"]["company_name"], "Pending SRL")

    def test_malformed_identifiers_and_sqli_attempts(self):
        """Malformed IDs, spaces, symbols, and SQLi attempts must return 404 or be safely handled."""
        conn = db.connect(self.db_path)

        adversarial_inputs = [
            "",
            "   ",
            None,
            12345,
            [],
            {},
            "non-existent-pro-99999",
            "' OR 1=1 --",
            "binder-lukas-instalator' OR '1'='1",
            "\" OR \"1\"=\"1",
            "binder-lukas-instalator; DROP TABLE users; --",
            "UNION SELECT * FROM users --",
            "<script>alert('xss')</script>",
            "../../etc/passwd",
            "%20",
            "slug with space",
            "slug@with#symbols$!%",
        ]

        for bad_id in adversarial_inputs:
            with self.assertRaises(core.ApiError) as cm:
                services.get_professional(conn, bad_id)
            self.assertEqual(cm.exception.status, 404, f"Input {bad_id!r} did not produce 404")

        # Test over HTTP wire
        wire_adversarial = [
            "non-existent-pro-99999",
            "slug-with-nonexistent",
            "BINDER-LUKAS-INSTALATOR-EXTRA",
        ]
        for bad_slug in wire_adversarial:
            status, _ = self.call("GET", f"/api/professionals/{bad_slug}")
            self.assertEqual(status, 404)

    # =========================================================================
    # Group 2: Dynamic Ratings & Response Speed
    # =========================================================================

    def test_dynamic_ratings_zero_reviews_fallback(self):
        """New pro with 0 reviews in reviews table falls back to profile defaults."""
        conn = db.connect(self.db_path)
        uid_zero = "adv_user_zero_rev"
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, name, phone, created_at, last_login_at, is_active) "
            "VALUES (?, 'zero@test.ro', 'hash', 'pro', 'Zero Reviews Pro', '+40700000002', 1700000000, 1700000000, 1)",
            (uid_zero,),
        )
        conn.execute(
            "INSERT INTO pro_profiles (user_id, company_name, cui, slug, verification_status, plan, plan_status, "
            "rating_avg, rating_count, zones_json, hours_json) "
            "VALUES (?, 'Zero SRL', 'RO999002', 'zero-reviews-pro', 'verified', 'essential', 'active', 4.8, 5, '[]', '{}')",
            (uid_zero,),
        )
        conn.commit()

        user = conn.execute("SELECT * FROM users WHERE id=?", (uid_zero,)).fetchone()
        dash = services.pro_dashboard(conn, user)
        # Should fallback to profile rating_avg and rating_count
        self.assertEqual(dash["rating_avg"], 4.8)
        self.assertEqual(dash["rating_count"], 5)

        # Pro with 0 profile ratings and 0 reviews falls back to 5.0 and 0
        conn.execute("UPDATE pro_profiles SET rating_avg=0, rating_count=0 WHERE user_id=?", (uid_zero,))
        conn.commit()
        dash2 = services.pro_dashboard(conn, user)
        self.assertEqual(dash2["rating_avg"], 5.0)
        self.assertEqual(dash2["rating_count"], 0)

    def test_dynamic_ratings_exact_average_calculation_10_reviews(self):
        """Pro with 10 reviews with varying scores (1-5): exact arithmetic average."""
        conn = db.connect(self.db_path)
        uid_calc = "adv_user_calc_rev"
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, name, phone, created_at, last_login_at, is_active) "
            "VALUES (?, 'calc@test.ro', 'hash', 'pro', 'Calc Pro', '+40700000003', 1700000000, 1700000000, 1)",
            (uid_calc,),
        )
        conn.execute(
            "INSERT INTO pro_profiles (user_id, company_name, cui, slug, verification_status, plan, plan_status, "
            "rating_avg, rating_count, zones_json, hours_json) "
            "VALUES (?, 'Calc SRL', 'RO999003', 'calc-pro-slug', 'verified', 'pro', 'active', 2.0, 1, '[]', '{}')",
            (uid_calc,),
        )

        client_user = conn.execute("SELECT id FROM users WHERE role='client' LIMIT 1").fetchone()
        client_id = client_user["id"]

        scores = [1, 2, 3, 4, 5, 2, 3, 4, 5, 5]
        # Sum = 1+2+3+4+5+2+3+4+5+5 = 34. Avg = 3.4. Count = 10.
        for idx, s in enumerate(scores):
            bid = f"adv_book_calc_{idx}"
            conn.execute(
                "INSERT INTO bookings (id, client_id, pro_id, category, service_name, price_label, description, status, created_at, updated_at) "
                "VALUES (?, ?, ?, 'Sanitare', 'Reparatie', '100 RON', 'Desc', 'completed', ?, ?)",
                (bid, client_id, uid_calc, 1700000000 + idx * 10, 1700000000 + idx * 10),
            )
            conn.execute(
                "INSERT INTO reviews (id, booking_id, client_id, pro_id, rating, comment, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"adv_rev_{idx}", bid, client_id, uid_calc, s, f"Review {idx}", 1700000000 + idx * 100),
            )
        conn.commit()

        user = conn.execute("SELECT * FROM users WHERE id=?", (uid_calc,)).fetchone()
        dash = services.pro_dashboard(conn, user)
        self.assertEqual(dash["rating_count"], 10)
        self.assertEqual(dash["rating_avg"], 3.4)

        # Add 11th review with score 1: (34 + 1) / 11 = 35 / 11 = 3.1818... -> round(..., 1) = 3.2
        bid_11 = "adv_book_calc_11"
        conn.execute(
            "INSERT INTO bookings (id, client_id, pro_id, category, service_name, price_label, description, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'Sanitare', 'Reparatie', '100 RON', 'Desc', 'completed', 1700002000, 1700002000)",
            (bid_11, client_id, uid_calc),
        )
        conn.execute(
            "INSERT INTO reviews (id, booking_id, client_id, pro_id, rating, comment, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("adv_rev_11", bid_11, client_id, uid_calc, 1, "Review 11", 1700002000),
        )
        conn.commit()
        dash_11 = services.pro_dashboard(conn, user)
        self.assertEqual(dash_11["rating_count"], 11)
        self.assertEqual(dash_11["rating_avg"], 3.2)

    def test_response_speed_zero_estimates_fallback(self):
        """Pro with 0 estimates must return '~15 min' fallback."""
        conn = db.connect(self.db_path)
        uid_no_est = "adv_user_no_est"
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, name, phone, created_at, last_login_at, is_active) "
            "VALUES (?, 'noest@test.ro', 'hash', 'pro', 'No Estimates Pro', '+40700000004', 1700000000, 1700000000, 1)",
            (uid_no_est,),
        )
        conn.execute(
            "INSERT INTO pro_profiles (user_id, company_name, cui, slug, verification_status, plan, plan_status, "
            "zones_json, hours_json) VALUES (?, 'NoEst SRL', 'RO999004', 'no-est-slug', 'verified', 'pro', 'active', '[]', '{}')",
            (uid_no_est,),
        )
        conn.commit()

        user = conn.execute("SELECT * FROM users WHERE id=?", (uid_no_est,)).fetchone()
        dash = services.pro_dashboard(conn, user)
        self.assertEqual(dash["response_speed"], "~15 min")

    def test_response_speed_multiple_and_superseded_estimates(self):
        """Multiple estimates, superseded estimates, and edge case timestamps do not crash."""
        conn = db.connect(self.db_path)
        uid_est = "adv_user_multi_est"
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, name, phone, created_at, last_login_at, is_active) "
            "VALUES (?, 'multiest@test.ro', 'hash', 'pro', 'Multi Est Pro', '+40700000005', 1700000000, 1700000000, 1)",
            (uid_est,),
        )
        conn.execute(
            "INSERT INTO pro_profiles (user_id, company_name, cui, slug, verification_status, plan, plan_status, "
            "zones_json, hours_json) VALUES (?, 'MultiEst SRL', 'RO999005', 'multi-est-slug', 'verified', 'pro', 'active', '[]', '{}')",
            (uid_est,),
        )

        client_id = conn.execute("SELECT id FROM users WHERE role='client' LIMIT 1").fetchone()["id"]
        t0 = 1700000000

        # Booking 1
        b1_id = "adv_b1"
        conn.execute(
            "INSERT INTO bookings (id, client_id, pro_id, category, service_name, price_label, description, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'Sanitare', 'S1', '100 RON', 'Desc 1', 'pending', ?, ?)",
            (b1_id, client_id, uid_est, t0, t0),
        )
        # Estimate 1 for B1: latency 600s (10 min), superseded
        conn.execute(
            "INSERT INTO estimates (id, booking_id, pro_id, price_ron, duration_minutes, duration_label, "
            "proposed_start_at, proposed_end_at, slot_label, status, expires_at, created_at) "
            "VALUES ('adv_e1_1', ?, ?, 100, 60, '1 oră', ?, ?, 'Luni 10:00', 'superseded', ?, ?)",
            (b1_id, uid_est, t0 + 10000, t0 + 13600, t0 + 86400, t0 + 600),
        )
        # Estimate 2 for B1: latency 1200s (20 min), sent
        conn.execute(
            "INSERT INTO estimates (id, booking_id, pro_id, price_ron, duration_minutes, duration_label, "
            "proposed_start_at, proposed_end_at, slot_label, status, expires_at, created_at) "
            "VALUES ('adv_e1_2', ?, ?, 120, 60, '1 oră', ?, ?, 'Luni 11:00', 'sent', ?, ?)",
            (b1_id, uid_est, t0 + 10000, t0 + 13600, t0 + 86400, t0 + 1200),
        )

        # Booking 2
        b2_id = "adv_b2"
        conn.execute(
            "INSERT INTO bookings (id, client_id, pro_id, category, service_name, price_label, description, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'Sanitare', 'S2', '200 RON', 'Desc 2', 'pending', ?, ?)",
            (b2_id, client_id, uid_est, t0 + 2000, t0 + 2000),
        )
        # Estimate 3 for B2: latency 3600s (60 min)
        conn.execute(
            "INSERT INTO estimates (id, booking_id, pro_id, price_ron, duration_minutes, duration_label, "
            "proposed_start_at, proposed_end_at, slot_label, status, expires_at, created_at) "
            "VALUES ('adv_e2_1', ?, ?, 200, 90, '1.5 ore', ?, ?, 'Luni 14:00', 'accepted', ?, ?)",
            (b2_id, uid_est, t0 + 10000, t0 + 15400, t0 + 86400, t0 + 2000 + 3600),
        )

        # Booking 3 with anomalous estimate created before booking (clock drift edge case)
        b3_id = "adv_b3"
        conn.execute(
            "INSERT INTO bookings (id, client_id, pro_id, category, service_name, price_label, description, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'Sanitare', 'S3', '150 RON', 'Desc 3', 'pending', ?, ?)",
            (b3_id, client_id, uid_est, t0 + 5000, t0 + 5000),
        )
        conn.execute(
            "INSERT INTO estimates (id, booking_id, pro_id, price_ron, duration_minutes, duration_label, "
            "proposed_start_at, proposed_end_at, slot_label, status, expires_at, created_at) "
            "VALUES ('adv_e3_1', ?, ?, 150, 45, '45 min', ?, ?, 'Luni 16:00', 'sent', ?, ?)",
            (b3_id, uid_est, t0 + 10000, t0 + 12700, t0 + 86400, t0 + 4900),  # before booking
        )
        conn.commit()

        user = conn.execute("SELECT * FROM users WHERE id=?", (uid_est,)).fetchone()
        dash = services.pro_dashboard(conn, user)
        # Calculation:
        # Latencies matching created_at >= b.created_at:
        # e1_1: 600s
        # e1_2: 1200s
        # e2_1: 3600s
        # e3_1 is excluded by WHERE est.created_at >= b.created_at
        # Avg = (600 + 1200 + 3600) / 3 = 5400 / 3 = 1800s = 30 min.
        # format_response_speed(1800) -> 30 min
        self.assertEqual(dash["response_speed"], "30 min")

    # =========================================================================
    # Group 3: Subscription Checkout (Essential 10 EUR / Pro 39 EUR)
    # =========================================================================

    def test_subscription_checkout_essential_and_pro_pricing(self):
        """Checkout preserves 10 EUR / 49 RON for Essential and 39 EUR / 195 RON for Pro."""
        # 1. Marian switches to Essential plan
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

        conn = db.connect(self.db_path)
        marian_uid = conn.execute("SELECT id FROM users WHERE email='marian@rezolv.ro'").fetchone()["id"]

        pro_prof = conn.execute("SELECT * FROM pro_profiles WHERE user_id=?", (marian_uid,)).fetchone()
        self.assertEqual(pro_prof["plan"], "essential")
        self.assertEqual(pro_prof["subscription_price_eur"], 10)

        # Check payments audit table
        last_pay = conn.execute(
            "SELECT * FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
            (marian_uid,),
        ).fetchone()
        self.assertEqual(last_pay["plan"], "essential")
        self.assertEqual(last_pay["amount_ron"], 49)
        self.assertEqual(last_pay["status"], "succeeded")

        # 2. Marian upgrades to Pro plan
        status_pro, body_pro = self.call(
            "POST",
            "/api/subscription/checkout",
            {"plan": "pro", "card": {"number": "4242424242424242", "exp": "12/28", "cvc": "123"}},
            token=token,
        )
        self.assertEqual(status_pro, 200)
        self.assertEqual(body_pro["plan"], "pro")
        self.assertEqual(body_pro["price_eur"], 39)

        pro_prof_up = conn.execute("SELECT * FROM pro_profiles WHERE user_id=?", (marian_uid,)).fetchone()
        self.assertEqual(pro_prof_up["plan"], "pro")
        self.assertEqual(pro_prof_up["subscription_price_eur"], 39)

        last_pay_pro = conn.execute(
            "SELECT * FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
            (marian_uid,),
        ).fetchone()
        self.assertEqual(last_pay_pro["plan"], "pro")
        self.assertEqual(last_pay_pro["amount_ron"], 195)
        self.assertEqual(last_pay_pro["status"], "succeeded")

    def test_subscription_checkout_adversarial_failures(self):
        """Card declined and invalid plan adversarial handling."""
        token = self.login("andrei@rezolv.ro", "pro")

        # 1. Invalid plan name
        status_bad, body_bad = self.call(
            "POST",
            "/api/subscription/checkout",
            {"plan": "enterprise_gold", "card": {"number": "4242424242424242", "exp": "12/28", "cvc": "123"}},
            token=token,
        )
        self.assertEqual(status_bad, 422)
        self.assertEqual(body_bad["error"]["code"], "validation_error")

        # 2. Declined test card (upgrading to 'pro' with bad card)
        status_dec, body_dec = self.call(
            "POST",
            "/api/subscription/checkout",
            {"plan": "pro", "card": {"number": "4000000000000002", "exp": "12/28", "cvc": "123"}},
            token=token,
        )
        self.assertEqual(status_dec, 402)
        self.assertEqual(body_dec["error"]["code"], "card_declined")

        # Verify failed payment recorded with proper RON amount (195 RON for Pro)
        conn = db.connect(self.db_path)
        andrei_uid = conn.execute("SELECT id FROM users WHERE email='andrei@rezolv.ro'").fetchone()["id"]
        last_pay = conn.execute(
            "SELECT * FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
            (andrei_uid,),
        ).fetchone()
        self.assertEqual(last_pay["status"], "failed")
        self.assertEqual(last_pay["amount_ron"], 195)


if __name__ == "__main__":
    unittest.main()
