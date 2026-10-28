"""End-to-end API tests against the REZOLV MVP backend (stdlib only).
Run:  python3 -m unittest discover -s backend/tests -v
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["REZOLV_DATA_DIR"] = tempfile.mkdtemp()
os.environ["REZOLV_BACKUP_DIR"] = tempfile.mkdtemp()

from rezolv import server  # noqa: E402
from rezolv import verification as ver  # noqa: E402


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.ctx = server.create_server("127.0.0.1", 0, os.path.join(os.environ["REZOLV_DATA_DIR"], "t.db"))
        if cls.srv is not None:
            cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
            threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        else:
            cls.base = "http://127.0.0.1:8787"

    @classmethod
    def tearDownClass(cls):
        if cls.srv is not None:
            cls.srv.shutdown()
            cls.srv.server_close()

    def call(self, method, path, body=None, token=None, raw=None, ctype="application/json"):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        headers = {}
        if data is not None:
            headers["Content-Type"] = ctype
        if token:
            headers["Authorization"] = "Bearer " + token

        if self.srv is not None:
            req = urllib.request.Request(self.base + path, data=data, method=method)
            for k, v in headers.items():
                req.add_header(k, v)
            try:
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
            except urllib.error.URLError as e:
                if not isinstance(e.reason, PermissionError):
                    raise

        status, parsed, _ = server.dispatch_test_request(self.ctx, method, path, raw=data, headers=headers)
        return status, parsed

    def login(self, email, role=None, pw="Demo1234"):
        s, b = self.call("POST", "/api/auth/login", {"email": email, "password": pw, "role": role})
        self.assertEqual(s, 200, b)
        return b["token"]


class TestAuth(Api):
    def test_login_ok_and_me(self):
        t = self.login("client@rezolv.ro", "client")
        s, b = self.call("GET", "/api/me", token=t)
        self.assertEqual((s, b["user"]["role"], b["user"]["city"]), (200, "client", "Sibiu"))

    def test_bad_password_and_unknown_user_same_error(self):
        s1, b1 = self.call("POST", "/api/auth/login", {"email": "client@rezolv.ro", "password": "Nope12345"})
        s2, b2 = self.call("POST", "/api/auth/login", {"email": "ghost@rezolv.ro", "password": "Nope12345"})
        self.assertEqual((s1, s2), (401, 401))
        self.assertEqual(b1["error"]["message"], b2["error"]["message"])

    def test_wrong_role_rejected(self):
        s, b = self.call("POST", "/api/auth/login", {"email": "client@rezolv.ro", "password": "Demo1234", "role": "pro"})
        self.assertEqual((s, b["error"]["code"]), (403, "wrong_role"))

    def test_protected_requires_token_and_rejects_tampering(self):
        self.assertEqual(self.call("GET", "/api/me")[0], 401)
        t = self.login("client@rezolv.ro")
        self.assertEqual(self.call("GET", "/api/me", token=t[:-3] + "abc")[0], 401)

    def test_register_validation_and_duplicate(self):
        s, b = self.call("POST", "/api/auth/register", {"email": "bad", "password": "short", "name": "A", "role": "client"})
        self.assertEqual(s, 422)
        self.assertEqual(set(b["error"]["fields"]), {"email", "password", "name"})
        ok = {"email": "nou@test.ro", "password": "Parola123", "name": "Test User", "role": "client"}
        self.assertEqual(self.call("POST", "/api/auth/register", ok)[0], 200)
        self.assertEqual(self.call("POST", "/api/auth/register", ok)[0], 409)

    def test_login_rate_limit(self):
        codes = [self.call("POST", "/api/auth/login", {"email": "rl@rezolv.ro", "password": "x1234567"})[0] for _ in range(10)]
        self.assertIn(429, codes)

    def test_password_reset_invalidates_old_tokens(self):
        email = "reset@test.ro"
        self.call("POST", "/api/auth/register", {"email": email, "password": "Parola123", "name": "Reset Me", "role": "client"})
        old = self.login(email, pw="Parola123")
        s, b = self.call("POST", "/api/auth/password-reset", {"email": email})
        self.assertEqual(s, 200)
        s, _ = self.call("POST", "/api/auth/password-reset/confirm", {"token": b["dev_token"], "password": "NouaParola9"})
        self.assertEqual(s, 200)
        self.assertEqual(self.call("GET", "/api/me", token=old)[0], 401)
        self.assertEqual(self.call("POST", "/api/auth/password-reset/confirm", {"token": b["dev_token"], "password": "AltaParola9"})[0], 400)
        self.login(email, pw="NouaParola9")

    def test_reset_unknown_email_does_not_leak(self):
        s, b = self.call("POST", "/api/auth/password-reset", {"email": "nobody@x.ro"})
        self.assertEqual(s, 200)
        self.assertNotIn("dev_token", b)

    def test_json_content_type_enforced(self):
        s, _ = self.call("POST", "/api/auth/login", raw=b"a=b", ctype="text/plain")
        self.assertEqual(s, 415)
        self.assertEqual(self.call("POST", "/api/auth/login", raw=b"{oops", ctype="application/json")[0], 400)


class TestCatalog(Api):
    def test_categories_and_professionals(self):
        s, b = self.call("GET", "/api/categories")
        self.assertEqual(len(b["categories"]), 12)
        for c in b["categories"]:
            s, p = self.call("GET", "/api/professionals?category=" + urllib.request.quote(c["name"]))
            self.assertGreaterEqual(len(p["professionals"]), 2, c["name"])
        s, p = self.call("GET", "/api/professionals?category=Instala%C8%9Bii%20Sanitare")
        self.assertTrue(p["professionals"][0]["promoted"])

    def test_search_by_name_and_service(self):
        s, p = self.call("GET", "/api/professionals?q=binder")
        self.assertEqual([x["name"] for x in p["professionals"]], ["Binder Lukas"])
        s, p = self.call("GET", "/api/professionals?q=anvelope")
        self.assertTrue(p["professionals"])

    def test_unknown_professional_404(self):
        self.assertEqual(self.call("GET", "/api/professionals/nope")[0], 404)


class TestBookingFlow(Api):
    def _service(self):
        pros = self.call("GET", "/api/professionals?q=binder")[1]["professionals"]
        return pros[0]["id"], pros[0]["services"][0]["id"]

    def test_full_lifecycle_with_rating(self):
        client, pro = self.login("client@rezolv.ro", "client"), self.login("mester@rezolv.ro", "pro")
        pro_id, sid = self._service()
        before = self.call("GET", "/api/professionals/" + pro_id)[1]["professional"]
        s, b = self.call("POST", "/api/bookings", {"service_id": sid, "description": "Robinet defect în bucătărie"}, client)
        self.assertEqual((s, b["booking"]["status"]), (200, "pending"))
        bid = b["booking"]["id"]
        self.assertEqual(self.call("POST", f"/api/bookings/{bid}/quote", {"price": 100, "duration": "1 oră"}, client)[0], 403)
        self.assertEqual(self.call("POST", f"/api/bookings/{bid}/quote", {"price": -5, "duration": ""}, pro)[0], 422)
        self.assertEqual(self.call("POST", f"/api/bookings/{bid}/complete", {}, pro)[0], 409)
        s, b = self.call("POST", f"/api/bookings/{bid}/quote", {"price": 180, "duration": "2 ore"}, pro)
        self.assertEqual((s, b["booking"]["status"], b["booking"]["quote_price"]), (200, "accepted", 180))
        self.assertEqual(self.call("POST", f"/api/bookings/{bid}/review", {"rating": 5}, client)[0], 409)
        s, b = self.call("POST", f"/api/bookings/{bid}/complete", {}, pro)
        self.assertEqual(b["booking"]["status"], "completed")
        self.assertTrue(b["booking"]["client"]["phone"])
        s, b = self.call("POST", f"/api/bookings/{bid}/review", {"rating": 3, "comment": "OK"}, client)
        self.assertEqual((s, b["booking"]["review"]["rating"]), (200, 3))
        self.assertEqual(self.call("POST", f"/api/bookings/{bid}/review", {"rating": 5}, client)[0], 409)
        after = self.call("GET", "/api/professionals/" + pro_id)[1]["professional"]
        self.assertEqual(after["reviews"], before["reviews"] + 1)
        self.assertLess(after["rating_value"], before["rating_value"])
        events = self.call("GET", f"/api/bookings/{bid}", token=client)[1]["booking"]["events"]
        self.assertEqual([e["to_status"] for e in events], ["pending", "accepted", "completed"])
        notes = self.call("GET", "/api/notifications", token=client)[1]
        self.assertTrue(any(n["kind"] == "booking_completed" for n in notes["notifications"]))

    def test_three_step_estimate_flow_and_sms_reminders(self):
        """Tests the Phase 2B Estimate Handshake: Request -> Pro Estimate -> Client Accept -> Slot Lock + 24h/2h SMS."""
        client, pro = self.login("dan@rezolv.ro", "client"), self.login("mester@rezolv.ro", "pro")
        _, sid = self._service()
        s, b = self.call(
            "POST",
            "/api/bookings",
            {
                "service_id": sid,
                "description": "Pierdere presiune centrală termică în Șelimbăr, am atașat detalii.",
                "neighborhood": "Șelimbăr",
                "urgency_level": "urgent_today",
                "preferred_window": "Mâine, 10:00–13:00",
            },
            client,
        )
        self.assertEqual(s, 200)
        bid = b["booking"]["id"]

        # Step 2: Pro sends flexible Estimate (price + duration + proposed slot)
        s, est_res = self.call(
            "POST",
            f"/api/bookings/{bid}/estimate",
            {
                "price": 240,
                "price_max": 290,
                "duration_minutes": 90,
                "pro_notes": "Include curățare chimică și deplasarea în Șelimbăr.",
            },
            pro,
        )
        self.assertEqual(s, 200, est_res)
        self.assertEqual(est_res["booking"]["status"], "estimated")
        self.assertIsNotNone(est_res["booking"]["estimate"])
        self.assertEqual(est_res["booking"]["estimate"]["price_ron"], 240)
        self.assertEqual(est_res["booking"]["estimate"]["status"], "sent")

        # Step 3: Client accepts the Estimate -> locks calendar slot + queues T-24h and T-2h SMS reminders
        s, acc_res = self.call("POST", f"/api/bookings/{bid}/accept-estimate", {}, client)
        self.assertEqual(s, 200, acc_res)
        self.assertEqual(acc_res["booking"]["status"], "accepted")
        self.assertEqual(acc_res["booking"]["estimate"]["status"], "accepted")
        sms_types = [x["reminder_type"] for x in acc_res["booking"]["sms_reminders"]]
        self.assertIn("booking_confirmed", sms_types)
        self.assertIn("reminder_24h", sms_types)
        self.assertIn("reminder_2h", sms_types)

        # Trigger scheduled 24h & 2h SMS reminders on demand
        s, trig = self.call("POST", f"/api/bookings/{bid}/sms-trigger", {}, pro)
        self.assertEqual(s, 200)
        self.assertEqual(len(trig["dispatched"]), 2)

    def test_two_click_calendar_reschedule_and_double_booking_conflict(self):
        """Tests 2-Click B2B Calendar Reschedule and atomic double-booking prevention."""
        client, pro = self.login("elena@rezolv.ro", "client"), self.login("mester@rezolv.ro", "pro")
        _, sid = self._service()
        cal = self.call("GET", "/api/pro/calendar", token=pro)[1]
        self.assertGreaterEqual(len(cal["days"]), 5)
        free_slots = cal["quick_free_slots"]
        self.assertGreaterEqual(len(free_slots), 2)

        bid1 = self.call(
            "POST",
            "/api/bookings",
            {"service_id": sid, "description": "Lucrare test slot 1 în Turnișor"},
            client,
        )[1]["booking"]["id"]
        slot_a = free_slots[0]["start_at"]
        slot_b = free_slots[1]["start_at"]

        # Pro estimates & Client accepts on slot_a
        self.call("POST", f"/api/bookings/{bid1}/estimate", {"price": 200, "duration_minutes": 60, "proposed_start_at": slot_a}, pro)
        self.assertEqual(self.call("POST", f"/api/bookings/{bid1}/accept-estimate", {}, client)[0], 200)

        # Second booking attempting to use the exact same locked slot_a must be rejected with 409 slot_conflict
        bid2 = self.call(
            "POST",
            "/api/bookings",
            {"service_id": sid, "description": "Lucrare test suprapunere în Turnișor"},
            client,
        )[1]["booking"]["id"]
        s_conf, b_conf = self.call(
            "POST",
            f"/api/bookings/{bid2}/estimate",
            {"price": 180, "duration_minutes": 60, "proposed_start_at": slot_a},
            pro,
        )
        self.assertEqual((s_conf, b_conf["error"]["code"]), (409, "slot_conflict"))

        # Rescheduling bid1 to free slot_b in 2 clicks succeeds and frees slot_a
        s_res, b_res = self.call(
            "POST",
            f"/api/bookings/{bid1}/reschedule",
            {"start_at": slot_b, "duration_minutes": 60},
            pro,
        )
        self.assertEqual(s_res, 200, b_res)
        self.assertEqual(b_res["booking"]["scheduled_start_at"], slot_b)

    def test_pro_sees_request_and_refusal(self):
        client, pro = self.login("elena@rezolv.ro", "client"), self.login("mester@rezolv.ro", "pro")
        _, sid = self._service()
        bid = self.call("POST", "/api/bookings", {"service_id": sid, "description": "Verificare instalație veche"}, client)[1]["booking"]["id"]
        dash = self.call("GET", "/api/pro/dashboard", token=pro)[1]
        self.assertIn(bid, [x["id"] for x in dash["pending"]])
        self.assertEqual(self.call("POST", f"/api/bookings/{bid}/refuse", {}, pro)[1]["booking"]["status"], "refused")
        self.assertEqual(self.call("POST", f"/api/bookings/{bid}/cancel", {}, client)[0], 409)

    def test_isolation_between_users(self):
        a, b_ = self.login("dan@rezolv.ro", "client"), self.login("mihai@rezolv.ro", "client")
        _, sid = self._service()
        bid = self.call("POST", "/api/bookings", {"service_id": sid, "description": "Problemă privată cu apa"}, a)[1]["booking"]["id"]
        self.assertEqual(self.call("GET", f"/api/bookings/{bid}", token=b_)[0], 404)
        self.assertEqual(self.call("POST", f"/api/bookings/{bid}/cancel", {}, b_)[0], 404)
        other_pro = self.login("marian@rezolv.ro", "pro")
        self.assertEqual(self.call("POST", f"/api/bookings/{bid}/quote", {"price": 50, "duration": "1h"}, other_pro)[0], 404)
        self.assertNotIn(bid, [x["id"] for x in self.call("GET", "/api/bookings", token=b_)[1]["bookings"]])

    def test_booking_validation_and_photos(self):
        client = self.login("client@rezolv.ro", "client")
        _, sid = self._service()
        self.assertEqual(self.call("POST", "/api/bookings", {"service_id": sid, "description": "scurt"}, client)[0], 422)
        self.assertEqual(self.call("POST", "/api/bookings", {"service_id": "x", "description": "o descriere suficientă"}, client)[0], 404)
        bad_photo = {"service_id": sid, "description": "o descriere suficientă", "photos": ["javascript:alert(1)"]}
        self.assertEqual(self.call("POST", "/api/bookings", bad_photo, client)[0], 422)
        png = "data:image/png;base64,iVBORw0KGgo="
        good = {"service_id": sid, "description": "o descriere suficientă", "photos": [png]}
        s, b = self.call("POST", "/api/bookings", good, client)
        self.assertEqual((s, b["booking"]["photos"]), (200, [png]))
        self.assertEqual(self.call("POST", "/api/bookings", {**good, "photos": [png] * 5}, client)[0], 422)

    def test_booking_address_phone_mutual_reveal_and_no_show(self):
        client = self.login("elena@rezolv.ro", "client")
        pro = self.login("mester@rezolv.ro", "pro")
        _, sid = self._service()
        body = {
            "service_id": sid,
            "description": "Reparație boiler de urgență la adresa specificată",
            "address": "Str. Nicolae Bălcescu nr. 12, Sibiu",
            "phone": "+40 740 123 456",
        }
        s, b = self.call("POST", "/api/bookings", body, client)
        self.assertEqual(s, 200)
        bid = b["booking"]["id"]
        self.assertEqual(b["booking"]["client_address"], "Str. Nicolae Bălcescu nr. 12, Sibiu")
        self.assertEqual(b["booking"]["client_phone"], "+40 740 123 456")
        # While pending, mutual pro phone is not exposed
        self.assertIsNone(b["booking"]["professional"].get("phone"))

        # Pro sends estimate and client accepts
        now = int(time.time())
        slot_start = ((now // 3600) + 24) * 3600
        self.call(
            "POST",
            f"/api/bookings/{bid}/estimate",
            {"price": 180, "duration_minutes": 60, "proposed_start_at": slot_start},
            pro,
        )
        s_acc, b_acc = self.call("POST", f"/api/bookings/{bid}/accept-estimate", {}, client)
        self.assertEqual(s_acc, 200)
        self.assertEqual(b_acc["booking"]["status"], "accepted")
        # Once accepted, mutual pro phone is exposed to client
        self.assertIsNotNone(b_acc["booking"]["professional"].get("phone"))

        # Pro can mark no-show if client does not answer
        s_ns, b_ns = self.call("POST", f"/api/bookings/{bid}/no-show", {"notes": "Client absent"}, pro)
        self.assertEqual(s_ns, 200)
        self.assertEqual(b_ns["booking"]["status"], "no_show")

    def test_pro_cannot_book_and_anon_cannot(self):
        _, sid = self._service()
        body = {"service_id": sid, "description": "o descriere suficientă"}
        self.assertEqual(self.call("POST", "/api/bookings", body, self.login("mester@rezolv.ro", "pro"))[0], 403)
        self.assertEqual(self.call("POST", "/api/bookings", body)[0], 401)


class TestProWorkspace(Api):
    def test_category_toggle_hides_pro_from_search(self):
        t = self.login("vlad@rezolv.ro", "pro")
        q = urllib.request.quote
        cat = "Zidărie & Faianțare"
        count = lambda: len(self.call("GET", "/api/professionals?category=" + q(cat))[1]["professionals"])
        before = count()
        self.assertEqual(self.call("PUT", "/api/pro/categories/" + q(cat), {"enabled": False}, t)[0], 200)
        self.assertEqual(count(), before - 1)
        self.call("PUT", "/api/pro/categories/" + q(cat), {"enabled": True}, t)
        self.assertEqual(count(), before)
        self.assertEqual(self.call("PUT", "/api/pro/categories/" + q(cat), {"enabled": "yes"}, t)[0], 422)

    def test_add_service_and_clients_blocked(self):
        t = self.login("andrei@rezolv.ro", "pro")
        s, b = self.call("POST", "/api/pro/services", {"name": "Montaj boiler", "price_from": 250, "duration": "2 ore"}, t)
        self.assertEqual(s, 200)
        self.assertEqual(self.call("POST", "/api/pro/services", {"name": "x", "price_from": 0}, t)[0], 422)
        self.assertEqual(self.call("POST", "/api/pro/services", {"name": "Montaj boiler", "price_from": 5}, self.login("client@rezolv.ro"))[0], 403)

    def test_profile_update(self):
        t = self.login("radu@rezolv.ro", "pro")
        s, b = self.call(
            "PATCH",
            "/api/pro/profile",
            {"zones": ["Hipodrom", "Șelimbăr"], "hours": {"Luni–Vineri": "09:00–17:00"}, "bio": "Descriere nouă"},
            t,
        )
        self.assertEqual((s, b["user"]["pro"]["zones"]), (200, ["Hipodrom", "Șelimbăr"]))
        self.assertEqual(self.call("PATCH", "/api/pro/profile", {"zones": "nope"}, t)[0], 422)


class TestVerification(Api):
    def test_cui_checksum(self):
        self.assertTrue(ver.validate_cui("RO" + ver.make_cui("4561230")))
        self.assertFalse(ver.validate_cui("RO4561231" if ver.make_cui("456123")[-1] != "1" else "RO4561232"))
        self.assertFalse(ver.validate_cui("abc"))

    def _reg(self, email, cui, company="Firma Test S.R.L."):
        return self.call(
            "POST",
            "/api/auth/register",
            {"email": email, "password": "Parola123", "name": "Pro Nou", "role": "pro", "company_name": company, "cui": cui},
        )

    def test_invalid_cui_rejected_and_known_company_autoverified(self):
        s, b = self._reg("p1@test.ro", "RO1234567")
        self.assertEqual(s, 422) if not ver.validate_cui("RO1234567") else None
        s, b = self._reg("p2@test.ro", "RO" + ver.make_cui("4561230"))
        self.assertEqual((s, b["user"]["pro"]["verification_status"]), (200, "verified"))

    def test_unknown_company_stays_hidden_until_admin_approves(self):
        s, b = self._reg("p3@test.ro", "RO" + ver.make_cui("5012345"), "Necunoscuta S.R.L.")
        self.assertEqual((s, b["user"]["pro"]["verification_status"]), (200, "pending"))
        tok, uid = b["token"], b["user"]["id"]
        self.assertEqual(self.call("POST", "/api/pro/services", {"name": "Test serviciu", "price_from": 99}, tok)[0], 403)
        self.assertEqual(self.call("GET", "/api/professionals/" + uid)[0], 404)
        admin = self.login("admin@rezolv.ro")
        self.assertIn(uid, [p["id"] for p in self.call("GET", "/api/admin/pros/pending", token=admin)[1]["pros"]])
        self.assertEqual(self.call("GET", "/api/admin/pros/pending", token=tok)[0], 403)
        self.assertEqual(self.call("POST", f"/api/admin/pros/{uid}/review", {"approve": True}, admin)[0], 200)
        self.assertEqual(self.call("GET", "/api/me", token=tok)[1]["user"]["pro"]["verification_status"], "verified")

    def test_duplicate_cui(self):
        cui = "RO" + ver.make_cui("5099001")
        self.assertEqual(self._reg("p4@test.ro", cui)[0], 200)
        self.assertEqual(self._reg("p5@test.ro", cui)[0], 409)


class TestPayments(Api):
    def card(self, number="4242 4242 4242 4242", exp="12/99", cvc="123"):
        return {"number": number, "exp": exp, "cvc": cvc}

    def test_upgrade_with_saved_card_and_invoice(self):
        t = self.login("mester@rezolv.ro", "pro")
        s, b = self.call("POST", "/api/subscription/checkout", {"plan": "pro"}, t)
        self.assertEqual((s, b["plan"], b["status"]), (200, "pro", "active"))
        self.assertEqual(b["payments"][0]["amount_ron"], 195)
        self.assertTrue(b["payments"][0]["invoice_no"].startswith("RZV-"))
        self.assertEqual(self.call("POST", "/api/subscription/checkout", {"plan": "pro"}, t)[0], 409)
        self.assertTrue(self.call("GET", "/api/professionals?q=binder")[1]["professionals"][0]["promoted"])

        # Test ANAF e-Factura UBL 2.1 CIUS-RO XML generation
        payment_id = b["payments"][0]["id"]
        s_xml, b_xml = self.call("GET", f"/api/payments/{payment_id}/invoice-xml", token=t)
        self.assertEqual(s_xml, 200)
        self.assertIn("urn:oasis:names:specification:ubl:schema:xsd:Invoice-2", b_xml["xml"])
        self.assertIn("CIUS-RO", b_xml["xml"])
        self.assertTrue(b_xml["filename"].endswith(".xml"))

    def test_declined_and_invalid_cards(self):
        t = self.login("andrei@rezolv.ro", "pro")
        s, b = self.call("POST", "/api/subscription/checkout", {"plan": "pro", "card": self.card("4000000000000002")}, t)
        self.assertEqual((s, b["error"]["code"]), (402, "card_declined"))
        s, b = self.call("POST", "/api/subscription/checkout", {"plan": "pro", "card": self.card("1234567812345678")}, t)
        self.assertEqual((s, "number" in b["error"]["fields"]), (422, True))
        s, b = self.call("POST", "/api/subscription/checkout", {"plan": "pro", "card": self.card(exp="01/20")}, t)
        self.assertEqual(s, 422)
        sub = self.call("GET", "/api/subscription", token=t)[1]
        self.assertEqual(sub["plan"], "essential")
        self.assertEqual(sub["payments"][0]["status"], "failed")
        self.assertNotIn("4242424242424242", json.dumps(sub))

    def test_card_payment_succeeds_and_clients_blocked(self):
        t = self.login("radu@rezolv.ro", "pro")
        s, b = self.call("POST", "/api/subscription/checkout", {"plan": "pro", "card": self.card(), "save_card": True}, t)
        self.assertEqual(s, 200)
        self.assertEqual(b["payment_method"]["last4"], "4242")
        self.assertEqual(self.call("POST", "/api/subscription/checkout", {"plan": "pro"}, self.login("client@rezolv.ro"))[0], 403)
        self.assertEqual(self.call("POST", "/api/subscription/checkout", {"plan": "gold"}, t)[0], 422)


class TestAdmin(Api):
    def test_cors_allowlist(self):
        _, _, hdrs_ok = server.dispatch_test_request(
            self.ctx, "OPTIONS", "/api/bookings", headers={"Origin": "http://localhost:5173"}
        )
        _, _, hdrs_bad = server.dispatch_test_request(
            self.ctx, "OPTIONS", "/api/bookings", headers={"Origin": "https://evil.example"}
        )
        self.assertEqual(hdrs_ok.get("Access-Control-Allow-Origin"), "http://localhost:5173")
        self.assertIsNone(hdrs_bad.get("Access-Control-Allow-Origin"))

    def test_ai_recommend(self):
        s, b = self.call("POST", "/api/ai/recommend", {"problem": "Curge apă sub chiuvetă și robinetul nu se închide"})
        self.assertEqual((s, b["category"]), (200, "Instalații Sanitare"))
        self.assertTrue(b["professional"]["verified"])
        self.assertEqual(self.call("POST", "/api/ai/recommend", {"problem": "scurt"})[0], 422)

    def test_metrics_admin_only(self):
        self.assertEqual(self.call("GET", "/api/admin/metrics", token=self.login("client@rezolv.ro"))[0], 403)
        s, b = self.call("GET", "/api/admin/metrics", token=self.login("admin@rezolv.ro"))
        self.assertEqual(s, 200)
        self.assertGreaterEqual(b["users"]["pros_verified"], 9)

    def test_super_admin_white_glove_onboarding_and_investor_analytics(self):
        admin = self.login("admin@rezolv.ro")
        cui_valid = "RO" + ver.make_cui("6123450")

        # 1. CUI Lookup via ANAF / Sibiu Registry
        s_cui, b_cui = self.call("POST", "/api/admin/cui-lookup", {"cui": cui_valid}, admin)
        self.assertEqual((s_cui, b_cui["valid"]), (200, True))

        # 2. White-Glove Onboarding of a new Sibiu Auto Service
        s_onb, b_onb = self.call(
            "POST",
            "/api/admin/pros/onboard",
            {
                "name": "Mircea Vulcanizare",
                "email": "mircea.sibiu@rezolv.ro",
                "phone": "+40 744 111 222",
                "company_name": "MIRCEA AUTO SIBIU S.R.L.",
                "cui": cui_valid,
                "category": "Mecanică Auto",
                "zones": ["Șelimbăr", "Hipodrom", "Vasile Aaron"],
                "plan_status": "active",
            },
            admin,
        )
        self.assertEqual(s_onb, 200, b_onb)
        self.assertEqual(b_onb["onboarded"]["company_name"], "MIRCEA AUTO SIBIU S.R.L.")
        self.assertTrue(b_onb["onboarded"]["verified"])

        # 3. Verify Investor Analytics & Unit Economics (39 EUR/month, CAC < 80 EUR, LTV ~ 800 EUR)
        s_ov, b_ov = self.call("GET", "/api/admin/overview", token=admin)
        self.assertEqual(s_ov, 200)
        ue = b_ov["analytics"]["unit_economics"]
        self.assertEqual(ue["subscription_eur"], 39)
        self.assertEqual(ue["commission_pct"], 0)
        self.assertLess(ue["cac_eur"], 80)
        self.assertGreaterEqual(ue["ltv_eur"], 750)

    def test_unknown_route_and_method(self):
        self.assertEqual(self.call("GET", "/api/nope")[0], 404)
        self.assertEqual(self.call("DELETE", "/api/categories")[0], 405)

    def test_tester_feedback_flow(self):
        # 1. Validation failure (short message)
        s, b = self.call("POST", "/api/feedback", {"rating": 5, "message": "x"})
        self.assertEqual(s, 422)

        # 2. Validation failure (invalid rating)
        s, b = self.call("POST", "/api/feedback", {"rating": 9, "message": "Arată excelent pe telefon!"})
        self.assertEqual(s, 422)

        # 3. Successful guest feedback
        s, b = self.call("POST", "/api/feedback", {
            "name": "Prieten Tester",
            "email": "prieten@test.ro",
            "rating": 5,
            "category": "idea",
            "message": "Arată super pe iPhone! Adaugă și opțiunea de chat direct.",
            "device_info": "iPhone 15 Pro • Safari"
        })
        self.assertEqual(s, 200)
        self.assertEqual(b["status"], "ok")
        self.assertTrue(b["id"].startswith("fb_"))

        # 4. Successful authenticated feedback
        client_tok = self.login("client@rezolv.ro")
        s, b = self.call("POST", "/api/feedback", {
            "rating": 4,
            "category": "bug",
            "message": "La pasul de adresă ar fi utilă completarea automată a străzii.",
        }, token=client_tok)
        self.assertEqual(s, 200)

        # 5. Non-admin cannot list feedback
        self.assertEqual(self.call("GET", "/api/admin/feedback", token=client_tok)[0], 403)

        # 6. Admin lists feedback
        admin_tok = self.login("admin@rezolv.ro")
        s_adm, b_adm = self.call("GET", "/api/admin/feedback", token=admin_tok)
        self.assertEqual(s_adm, 200)
        self.assertGreaterEqual(b_adm["stats"]["total"], 2)
        self.assertGreaterEqual(b_adm["stats"]["avg_rating"], 4.0)
        self.assertIn("idea", b_adm["stats"]["by_category"])
        self.assertIn("bug", b_adm["stats"]["by_category"])


if __name__ == "__main__":
    unittest.main()
