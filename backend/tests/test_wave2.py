"""End-to-end tests for REZOLV Wave 2 ("Valul 2 — Diferențiatori Core"):
- 2.1: Live Calendar Slots, Optional Instant Book, Smart Fallback Cascade
- 2.2: Before/After Photo Portfolio, Verified External Reviews, CAEN Rev.2 Specialization Badges
- 2.3: WhatsApp Business API Primary Channel + 1-Tap "Sunt pe drum (ETA)"
- 2.4: Configurable Stripe / Netopia (Web2App) Payment Providers + Anti-No-Show Slot Deposit
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["REZOLV_DATA_DIR"] = tempfile.mkdtemp()
os.environ["REZOLV_BACKUP_DIR"] = tempfile.mkdtemp()

from rezolv import payments, server, verification as ver  # noqa: E402


class TestWave2CoreDifferentiators(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.ctx = server.create_server(
            "127.0.0.1", 0, os.path.join(os.environ["REZOLV_DATA_DIR"], "wave2.db"), bind_socket=False
        )

    @classmethod
    def tearDownClass(cls):
        pass

    def call(self, method, path, body=None, token=None):
        raw = json.dumps(body).encode() if body is not None else None
        headers = {}
        if raw is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = "Bearer " + token
        status, parsed, _ = server.dispatch_test_request(self.ctx, method, path, raw=raw, headers=headers)
        return status, parsed

    def login(self, email, role=None, pw="Demo1234"):
        s, b = self.call("POST", "/api/auth/login", {"email": email, "password": pw, "role": role})
        self.assertEqual(s, 200, b)
        return b["token"]

    def test_2_1_live_calendar_slots_by_id_and_slug(self):
        """Public GET /api/professionals/{id}/slots returns live calendar windows and Instant Book eligibility."""
        s, b = self.call("GET", "/api/professionals/binder-lukas-instalator/slots")
        self.assertEqual(s, 200, b)
        pro_id = b["pro_id"]
        self.assertTrue(pro_id.startswith("u_"))
        self.assertTrue(b["instant_book_enabled"])
        self.assertGreaterEqual(len(b["slots"]), 3)
        first_slot = b["slots"][0]
        self.assertIn("start_at", first_slot)
        self.assertIn("end_at", first_slot)
        self.assertIn("label", first_slot)

        # Also works by user_id
        s2, b2 = self.call("GET", f"/api/professionals/{pro_id}/slots")
        self.assertEqual(s2, 200)
        self.assertEqual(b2["pro_id"], pro_id)

    def test_2_1_instant_book_locks_slot_and_schedules_reminders(self):
        """Instant Book creates an accepted booking immediately, locks the calendar slot, and rejects overlapping slots."""
        client_tok = self.login("client@rezolv.ro", "client")

        # Fetch pro services and live slots
        _, pro_res = self.call("GET", "/api/professionals/binder-lukas-instalator")
        pro = pro_res["professional"]
        ib_services = [sv for sv in pro["services"] if sv.get("instant_book")]
        self.assertTrue(len(ib_services) >= 1, "Expected at least one Instant Book standardized service")
        ib_svc = ib_services[0]

        _, slots_res = self.call("GET", "/api/professionals/binder-lukas-instalator/slots")
        chosen_slot = slots_res["slots"][-1]

        s, created = self.call(
            "POST",
            "/api/bookings",
            {
                "service_id": ib_svc["id"],
                "description": "Înlocuire baterie chiuvetă bucătărie cu tarif fix și rezervare instantă.",
                "neighborhood": "Hipodrom",
                "instant_book": True,
                "slot_start_at": chosen_slot["start_at"],
            },
            token=client_tok,
        )
        self.assertEqual(s, 200, created)
        bk = created["booking"]
        self.assertEqual(bk["status"], "accepted")
        self.assertTrue(bk["is_instant_book"])
        self.assertEqual(bk["quote_price"], ib_svc["price_from"])
        self.assertGreaterEqual(len(bk.get("sms_reminders", [])), 3)

        # Attempting another Instant Book on the exact same slot must return 409 slot_conflict
        s_conf, conf_body = self.call(
            "POST",
            "/api/bookings",
            {
                "service_id": ib_svc["id"],
                "description": "A doua rezervare pe același interval orar blocat.",
                "neighborhood": "Hipodrom",
                "instant_book": True,
                "slot_start_at": chosen_slot["start_at"],
            },
            token=client_tok,
        )
        self.assertEqual(s_conf, 409, conf_body)
        self.assertEqual(conf_body["error"]["code"], "slot_conflict")

    def test_2_1_smart_fallback_cascade(self):
        """POST /api/bookings/{id}/cascade forwards a pending or refused booking to up to 2 other verified pros."""
        client_tok = self.login("client@rezolv.ro", "client")
        _, pro_res = self.call("GET", "/api/professionals/binder-lukas-instalator")
        pro = pro_res["professional"]
        svc_id = pro["services"][0]["id"]

        s, created = self.call(
            "POST",
            "/api/bookings",
            {
                "service_id": svc_id,
                "description": "Scurgere sub chiuvetă în Turnișor, am nevoie de ofertă.",
                "neighborhood": "Turnișor",
            },
            token=client_tok,
        )
        self.assertEqual(s, 200, created)
        orig_id = created["booking"]["id"]

        s_cas, cas = self.call("POST", f"/api/bookings/{orig_id}/cascade", {}, token=client_tok)
        self.assertEqual(s_cas, 200, cas)
        self.assertEqual(cas["original_booking_id"], orig_id)
        self.assertGreaterEqual(cas["cascaded_count"], 1)
        self.assertLessEqual(cas["cascaded_count"], 2)
        for cb in cas["cascaded_bookings"]:
            self.assertEqual(cb["cascaded_from_booking_id"], orig_id)
            self.assertNotEqual(cb["professional"]["id"], pro["id"])

    def test_2_2_caen_portfolio_and_external_reviews(self):
        """Verify CAEN Rev.2 badge, Before/After photo portfolio CRUD, and Verified External Reviews."""
        # 1. Verify CAEN validation helper
        self.assertTrue(ver.validate_caen_for_category("4322", "Instalații Sanitare"))
        caen_info = ver.get_caen_info("Instalații Sanitare", "4322")
        self.assertIn("CAEN 4322", caen_info["caen_label"])

        # 2. Check seeded public profile has CAEN badge, portfolio photos, and external reviews
        s_pub, pub = self.call("GET", "/api/professionals/binder-lukas-instalator")
        self.assertEqual(s_pub, 200, pub)
        pro_detail = pub["professional"]
        self.assertEqual(pro_detail["caen_code"], "4322")
        self.assertIn("CAEN 4322", pro_detail["caen_label"])
        self.assertGreaterEqual(len(pro_detail["portfolio_photos"]), 1)
        self.assertGreaterEqual(len(pro_detail["external_reviews"]), 1)

        # 3. Authenticated pro can add and delete Before/After portfolio photos
        pro_tok = self.login("mester@rezolv.ro", "pro")
        valid_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        s_add, added = self.call(
            "POST",
            "/api/pro/portfolio",
            {
                "title": "Montaj distribuitor încălzire în pardoseală Șelimbăr",
                "category": "Instalații Sanitare",
                "before_caption": "Conducte vechi oxidate",
                "after_caption": "Distribuitor inox cu debitmetre reglate",
                "before_url": valid_png,
                "after_url": valid_png,
            },
            token=pro_tok,
        )
        self.assertEqual(s_add, 200, added)
        new_pf_id = added["portfolio"][0]["id"]

        s_del, after_del = self.call("DELETE", f"/api/pro/portfolio/{new_pf_id}", token=pro_tok)
        self.assertEqual(s_del, 200, after_del)
        self.assertFalse(any(p["id"] == new_pf_id for p in after_del["portfolio"]))

        # 4. Authenticated pro can import a verified external review
        s_ext, ext_res = self.call(
            "POST",
            "/api/pro/external-reviews",
            {
                "author_name": "Mircea Popa (Șelimbăr)",
                "client_phone": "+40 744 900 800",
                "rating": 5,
                "comment": "Lucrare impecabilă la centrala termică, recomand cu încredere!",
                "source_label": "Client verificat telefonic (Google Business)",
            },
            token=pro_tok,
        )
        self.assertEqual(s_ext, 200, ext_res)
        self.assertTrue(
            any("Mircea Popa" in r["author"] for r in ext_res["professional"]["external_reviews"])
        )

    def test_2_3_whatsapp_on_my_way_notification(self):
        """POST /api/bookings/{id}/on-my-way sends WhatsApp Business notification (0.14 RON) and updates ETA."""
        client_tok = self.login("client@rezolv.ro", "client")
        pro_tok = self.login("mester@rezolv.ro", "pro")

        # Create an Instant Book accepted booking so pro can immediately mark on-my-way
        _, pro_res = self.call("GET", "/api/professionals/binder-lukas-instalator")
        ib_svc = [sv for sv in pro_res["professional"]["services"] if sv.get("instant_book")][0]
        _, slots_res = self.call("GET", "/api/professionals/binder-lukas-instalator/slots")
        slot = slots_res["slots"][1]
        s_c, created = self.call(
            "POST",
            "/api/bookings",
            {
                "service_id": ib_svc["id"],
                "description": "Urgență robineți trecere apă rece.",
                "neighborhood": "Centru Istoric",
                "instant_book": True,
                "slot_start_at": slot["start_at"],
            },
            token=client_tok,
        )
        self.assertEqual(s_c, 200, created)
        bid = created["booking"]["id"]

        s_omw, omw = self.call(
            "POST",
            f"/api/bookings/{bid}/on-my-way",
            {"eta_minutes": 18, "channel": "whatsapp"},
            token=pro_tok,
        )
        self.assertEqual(s_omw, 200, omw)
        self.assertEqual(omw["booking"]["eta_minutes"], 18)
        self.assertIsNotNone(omw["booking"]["on_my_way_at"])
        self.assertEqual(omw["dispatch"]["provider"], "whatsapp_sandbox")
        self.assertEqual(omw["dispatch"]["estimated_cost_ron"], 0.14)
        self.assertIn("~18 min", omw["dispatch"]["message_body"])

    def test_2_4_deposit_and_web2app_stripe_netopia_providers(self):
        """Verify optional anti-no-show deposit (50 RON), Web2App checkout session, and Stripe/Netopia providers."""
        client_tok = self.login("client@rezolv.ro", "client")
        pro_tok = self.login("mester@rezolv.ro", "pro")
        _, pro_res = self.call("GET", "/api/professionals/binder-lukas-instalator")
        svc_id = pro_res["professional"]["services"][0]["id"]

        # Create booking and pay 50 RON anti-no-show deposit
        s_c, created = self.call(
            "POST",
            "/api/bookings",
            {
                "service_id": svc_id,
                "description": "Montaj obiecte sanitare baie nouă.",
                "neighborhood": "Valea Aurie",
            },
            token=client_tok,
        )
        self.assertEqual(s_c, 200, created)
        bid = created["booking"]["id"]

        s_dep, dep_res = self.call(
            "POST",
            f"/api/bookings/{bid}/deposit",
            {"amount_ron": 50},
            token=client_tok,
        )
        self.assertEqual(s_dep, 200, dep_res)
        self.assertEqual(dep_res["deposit"]["amount_ron"], 50)
        self.assertEqual(dep_res["booking"]["deposit_paid_ron"], 50)

        # Declined card (...0002) returns 402
        s_fail, fail_res = self.call(
            "POST",
            f"/api/bookings/{bid}/deposit",
            {"amount_ron": 50, "card": {"number": "4000000000000002", "exp": "12/29", "cvc": "123"}},
            token=client_tok,
        )
        self.assertEqual(s_fail, 402, fail_res)

        # Web2App session for pro subscription (0% Apple/Google IAP tax)
        s_w2a, w2a = self.call(
            "POST",
            "/api/subscription/web2app-session",
            {"kind": "subscription", "plan": "pro"},
            token=pro_tok,
        )
        self.assertEqual(s_w2a, 200, w2a)
        self.assertTrue(w2a["zero_apple_commission"])
        self.assertEqual(w2a["amount_ron"], 195)
        self.assertIn("cs_web2app_", w2a["web2app_url"])

        # Provider factory supports stripe and netopia
        os.environ["REZOLV_PAYMENT_PROVIDER"] = "stripe"
        self.assertEqual(payments.get_provider().name, "stripe")
        os.environ["REZOLV_PAYMENT_PROVIDER"] = "netopia"
        self.assertEqual(payments.get_provider().name, "netopia")
        os.environ["REZOLV_PAYMENT_PROVIDER"] = "mock"
        self.assertEqual(payments.get_provider().name, "mock")


if __name__ == "__main__":
    unittest.main()
