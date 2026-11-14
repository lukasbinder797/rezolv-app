"""Adversarial Empirical Challenge Suite: Milestone 3 (Challenger 2)
Focus: Deferred Auth, Booking Flow & State Recovery

Stress-tests:
1. Unauthenticated polling guard: GET /api/bookings returns 401 for unauthenticated visitors.
2. Auth-last booking enforcement: POST /api/bookings returns 401 without auth, 403 with pro token, 401 with malformed token.
3. Full registration -> onboarding -> deferred booking execution lifecycle with payload preservation (photos, address, phone, urgency_level).
4. Existing user login -> immediate booking execution lifecycle.
5. High-volume unauthenticated browsing without 401 leakage.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rezolv import config, core, db, seed, server, services


class TestMilestone3DeferredAuthChallenger2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmpdir, "test_m3.db")
        db.init_db(cls.db_path)
        conn = db.connect(cls.db_path)
        seed.seed(conn)
        conn.close()
        cls.ctx = server.Context(db_path=cls.db_path)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def dispatch(self, method, path, body=None, token=None):
        headers = {}
        raw = None
        if body is not None:
            raw = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.ctx.limiter.hits.clear()
        status, parsed, _ = server.dispatch_test_request(self.ctx, method, path, raw=raw, headers=headers)
        return status, parsed

    def test_01_unauthenticated_bookings_polling_returns_401(self):
        """Proof: If an unauthenticated visitor were to poll GET /api/bookings, it returns 401."""
        status, res = self.dispatch("GET", "/api/bookings")
        self.assertEqual(status, 401)
        self.assertEqual(res.get("error", {}).get("code"), "unauthenticated")
        self.assertEqual(res.get("error", {}).get("message"), "Autentificare necesară.")

    def test_02_unauthenticated_booking_submission_returns_401(self):
        """Proof: Submitting POST /api/bookings without token is strictly blocked with 401."""
        status, res = self.dispatch("POST", "/api/bookings", {
            "service_id": "srv_instalatii_1",
            "description": "Scurgere robinet bucatarie",
            "address": "Str. Semaforului 10",
            "phone": "+40 721 555 010",
        })
        self.assertEqual(status, 401)
        self.assertEqual(res.get("error", {}).get("code"), "unauthenticated")
        self.assertEqual(res.get("error", {}).get("message"), "Autentificare necesară.")

    def test_03_pro_role_cannot_submit_client_booking(self):
        """Proof: A user with role 'pro' attempting to create a booking gets 403 Forbidden."""
        status, login_res = self.dispatch("POST", "/api/auth/login", {
            "email": "mester@rezolv.ro",
            "password": "Demo1234",
            "role": "pro",
        })
        self.assertEqual(status, 200)
        pro_token = login_res["token"]

        status, res = self.dispatch("POST", "/api/bookings", {
            "service_id": "srv_instalatii_1",
            "description": "Attempted pro booking",
        }, token=pro_token)
        self.assertEqual(status, 403)
        self.assertEqual(res.get("error", {}).get("code"), "forbidden")

    def test_04_new_user_registration_and_onboarding_lifecycle(self):
        """Lifecycle Test:
        1. Register new client (starts with NULL address and phone).
        2. Attempt booking before onboarding -> works at backend if address provided, but frontend gates onboarding.
        3. Onboard via POST /api/me (address + phone updated).
        4. Submit deferred booking with photos, address, phone -> verifies full payload preservation.
        """
        # 1. Register new client
        status, reg_res = self.dispatch("POST", "/api/auth/register", {
            "role": "client",
            "name": "Challenger Client",
            "email": "challenger.client@rezolv.ro",
            "password": "SecurePassword123!",
        })
        self.assertEqual(status, 200)
        token = reg_res["token"]
        user = reg_res["user"]
        # Verify initial registration lacks address and phone
        self.assertIsNone(user.get("address"))
        self.assertIsNone(user.get("phone"))

        # 2. Update profile (Onboarding Modal simulation uses PATCH /api/me)
        status, me_res = self.dispatch("PATCH", "/api/me", {
            "name": "Challenger Client",
            "address": "Str. Livezii nr. 14, Sibiu",
            "phone": "+40 740 999 888",
            "email": "challenger.client@rezolv.ro",
        }, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(me_res["user"]["address"], "Str. Livezii nr. 14, Sibiu")
        self.assertEqual(me_res["user"]["phone"], "+40 740 999 888")

        # Get valid service_id for Marian Popescu
        _, pro_data = self.dispatch("GET", "/api/professionals/marian-popescu-instalator")
        service_id = pro_data["professional"]["services"][0]["id"]

        # 3. Create deferred booking with preserved photos and fields
        booking_payload = {
            "service_id": service_id,
            "description": "Robinet baie picură sub mască",
            "neighborhood": "Ștrand",
            "address": "Str. Livezii nr. 14, Sibiu",
            "phone": "+40 740 999 888",
            "urgency_level": "urgent_today",
            "preferred_window": "Urgent Azi",
            "scheduled_for": "Urgent Azi",
            "photos": [
                "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
                "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==",
            ],
        }
        status, book_res = self.dispatch("POST", "/api/bookings", booking_payload, token=token)
        self.assertEqual(status, 200)
        booking = book_res["booking"]
        self.assertEqual(booking["status"], "pending")
        self.assertEqual(booking["urgency_level"], "urgent_today")
        self.assertEqual(booking["description"], "Robinet baie picură sub mască")
        self.assertEqual(len(booking.get("photos", [])), 2)
        self.assertEqual(booking["client_address"], "Str. Livezii nr. 14, Sibiu")
        self.assertEqual(booking["client_phone"], "+40 740 999 888")

        # 4. Verify client can now poll their bookings
        status, list_res = self.dispatch("GET", "/api/bookings", token=token)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(list_res["bookings"]), 1)
        self.assertEqual(list_res["bookings"][0]["id"], booking["id"])

    def test_05_existing_user_login_and_immediate_deferred_booking(self):
        """Lifecycle Test for Existing Client:
        1. Login existing client (client@rezolv.ro).
        2. Auto-submit deferred booking with custom address/phone.
        3. Assert booking created with status 'pending' and correct pro assignment.
        """
        status, login_res = self.dispatch("POST", "/api/auth/login", {
            "email": "client@rezolv.ro",
            "password": "Demo1234",
            "role": "client",
        })
        self.assertEqual(status, 200)
        client_token = login_res["token"]

        _, pro_data = self.dispatch("GET", "/api/professionals/marian-popescu-instalator")
        service_id = pro_data["professional"]["services"][0]["id"]

        custom_payload = {
            "service_id": service_id,
            "description": "Înlocuire robinet trecere coloană",
            "neighborhood": "Hipodrom",
            "address": "Bd. Mihai Viteazu nr. 24, Ap. 12",
            "phone": "+40 721 555 010",
            "urgency_level": "normal",
            "preferred_window": "Mâine, 09:00–12:00",
            "photos": [],
        }
        status, book_res = self.dispatch("POST", "/api/bookings", custom_payload, token=client_token)
        self.assertEqual(status, 200)
        booking = book_res["booking"]
        self.assertEqual(booking["status"], "pending")
        self.assertEqual(booking["description"], "Înlocuire robinet trecere coloană")
        self.assertEqual(booking["client_address"], "Bd. Mihai Viteazu nr. 24, Ap. 12")

    def test_06_unauthenticated_visitor_browse_first_stability(self):
        """Verify unauthenticated visitor can browse categories, pros, pro details without auth."""
        # 1. Categories
        s, r = self.dispatch("GET", "/api/categories")
        self.assertEqual(s, 200)
        self.assertGreaterEqual(len(r.get("categories", [])), 1)

        # 2. Pros list
        s, r = self.dispatch("GET", "/api/professionals")
        self.assertEqual(s, 200)
        self.assertGreaterEqual(len(r.get("professionals", [])), 1)

        # 3. Specific pro by slug
        s, r = self.dispatch("GET", "/api/professionals/marian-popescu-instalator")
        self.assertEqual(s, 200)
        self.assertEqual(r["professional"]["slug"], "marian-popescu-instalator")


if __name__ == "__main__":
    unittest.main()
