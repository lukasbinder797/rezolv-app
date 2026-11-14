"""End-to-end tests for REZOLV Wave 3 ("Valul 3 — Moats pe Termen Mediu" + 3-Tier B2B Subscription Architecture):
- 3.0: 3-Tier B2B Subscription Architecture (`essential` 49 RON, `pro` 195 RON, `business` 349 RON)
- 3.1: REZOLV Recepționer AI 24/7 (Missed-Call & WhatsApp Auto-Responder)
- 3.2: Good–Better–Best 3-Option Estimates (Standard / Recomandat / Premium) + 1-Tap B2C Invoice & RO e-Factura ANAF SPV (OUG 69/2024 UBL 2.1 XML)
(Note: 3.3 "Garanția REZOLV Sibiu" is intentionally excluded until post-launch per founder instruction.)
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["REZOLV_DATA_DIR"] = tempfile.mkdtemp()
os.environ["REZOLV_BACKUP_DIR"] = tempfile.mkdtemp()

from rezolv import payments, server  # noqa: E402


class TestWave3MediumTermMoatsAndPricing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.ctx = server.create_server(
            "127.0.0.1", 0, os.path.join(os.environ["REZOLV_DATA_DIR"], "wave3.db"), bind_socket=False
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

    def test_3_0_three_tier_b2b_subscription_architecture(self):
        """Verify 3-tier B2B subscription pricing (`essential` 49 RON, `pro` 195 RON, `business` 349 RON) and checkout."""
        self.assertEqual(payments.PLANS["essential"]["price_ron"], 49)
        self.assertEqual(payments.PLANS["pro"]["price_ron"], 195)
        self.assertEqual(payments.PLANS["business"]["price_ron"], 349)
        self.assertEqual(payments.PLANS["business"]["price_eur"], 69)

        pro_tok = self.login("mester@rezolv.ro", "pro")

        # Web2App session supports 'business' tier (349 RON, 0% Apple commission)
        s_w2a, w2a = self.call(
            "POST",
            "/api/subscription/web2app-session",
            {"kind": "subscription", "plan": "business"},
            token=pro_tok,
        )
        self.assertEqual(s_w2a, 200, w2a)
        self.assertEqual(w2a["amount_ron"], 349)
        self.assertTrue(w2a["zero_apple_commission"])

        # Checkout into 'business' plan
        s_chk, chk = self.call("POST", "/api/subscription/checkout", {"plan": "business"}, token=pro_tok)
        self.assertEqual(s_chk, 200, chk)
        self.assertEqual(chk["plan"], "business")
        self.assertEqual(chk["status"], "active")
        self.assertEqual(chk["payments"][0]["amount_ron"], 349)

    def test_3_1_ai_receptionist_missed_call_auto_responder(self):
        """Wave 3.1: REZOLV Recepționer AI captures missed calls/WhatsApp, matches service, proposes slot, and creates booking."""
        pro_tok = self.login("mester@rezolv.ro", "pro")
        # Ensure pro is on business plan
        self.call("POST", "/api/subscription/checkout", {"plan": "business"}, token=pro_tok)

        # 1. Enable AI Receptionist
        s_patch, st = self.call(
            "PATCH",
            "/api/pro/ai-receptionist",
            {"enabled": True, "auto_quote": True},
            token=pro_tok,
        )
        self.assertEqual(s_patch, 200, st)
        self.assertTrue(st["enabled"])
        self.assertTrue(st["eligible"])

        # 2. Simulate a missed call from a Sibiu client
        s_sim, sim = self.call(
            "POST",
            "/api/pro/ai-receptionist/simulate",
            {
                "channel": "missed_call",
                "caller_name": "Andrei Munteanu",
                "caller_phone": "+40745112233",
                "message": "Bună! Am sunat dar nu ați putut răspunde — picură bateria sub chiuvetă în Hipodrom, când aveți loc?",
                "neighborhood": "Hipodrom",
            },
            token=pro_tok,
        )
        self.assertEqual(s_sim, 200, sim)
        self.assertTrue(sim["handled"])
        self.assertGreater(sim["estimated_price_ron"], 0)
        self.assertIn("RON", sim["ai_reply"])
        self.assertEqual(sim["booking"]["status"], "estimated")
        self.assertGreaterEqual(len(sim["receptionist"]["logs"]), 1)

    def test_3_2_good_better_best_options_and_b2c_efactura_spv(self):
        """Wave 3.2: 3-Option Good–Better–Best Estimate + 1-Tap B2C Invoice & OUG 69/2024 RO e-Factura UBL 2.1 XML."""
        client_tok = self.login("client@rezolv.ro", "client")
        pro_tok = self.login("mester@rezolv.ro", "pro")

        _, pro_res = self.call("GET", "/api/professionals/binder-lukas-instalator")
        svc_id = pro_res["professional"]["services"][0]["id"]

        # 1. Client creates booking request
        s_bk, bk_res = self.call(
            "POST",
            "/api/bookings",
            {
                "service_id": svc_id,
                "description": "Înlocuire robinet colțar și verificare racorduri mașină de spălat în Șelimbăr.",
                "neighborhood": "Șelimbăr",
            },
            token=client_tok,
        )
        self.assertEqual(s_bk, 200, bk_res)
        bid = bk_res["booking"]["id"]

        # 2. Pro sends Good-Better-Best 3-Option Estimate
        options_payload = [
            {
                "tier": "standard",
                "title": "Varianta Standard (Reparație punctuală)",
                "price_ron": 160,
                "description": "Înlocuire robinet colțar standard.",
            },
            {
                "tier": "recomandat",
                "title": "Varianta Recomandată (Revizie completă)",
                "price_ron": 210,
                "description": "Robinet + racorduri flexibile inox + verificare presiune.",
            },
            {
                "tier": "premium",
                "title": "Varianta Premium (Piese Grohe + Garanție extinsă)",
                "price_ron": 290,
                "description": "Robineți colțari cu filtru ceramic + racorduri Aquastop.",
            },
        ]
        s_est, est_res = self.call(
            "POST",
            f"/api/bookings/{bid}/estimate",
            {
                "price": 210,
                "duration_minutes": 60,
                "duration": "1 oră",
                "pro_notes": "Puteți alege oricare din cele 3 pachete de mai jos.",
                "options": options_payload,
            },
            token=pro_tok,
        )
        self.assertEqual(s_est, 200, est_res)
        self.assertEqual(len(est_res["booking"]["estimate"]["options"]), 3)

        # 3. Client accepts the "premium" tier (290 RON)
        s_acc, acc_res = self.call(
            "POST",
            f"/api/bookings/{bid}/accept-estimate",
            {"selected_tier": "premium"},
            token=client_tok,
        )
        self.assertEqual(s_acc, 200, acc_res)
        self.assertEqual(acc_res["booking"]["status"], "accepted")
        self.assertEqual(acc_res["booking"]["selected_tier"], "premium")
        self.assertEqual(acc_res["booking"]["quote_price"], 290)

        # 4. Pro issues 1-Tap B2C Fiscal Invoice & RO e-Factura ANAF SPV
        s_inv, inv_res = self.call(
            "POST",
            f"/api/bookings/{bid}/invoice",
            {},
            token=pro_tok,
        )
        self.assertEqual(s_inv, 200, inv_res)
        inv = inv_res["invoice"]
        self.assertTrue(inv["invoice_no"].startswith("SB-"))
        self.assertEqual(inv["total_ron"], 290)
        self.assertEqual(inv["efactura_status"], "transmitted_spv")
        self.assertTrue(len(inv["spv_index"]) >= 8)

        # 5. Download OUG 69/2024 B2C RO e-Factura UBL 2.1 XML
        s_xml, xml_res = self.call(
            "GET",
            f"/api/bookings/{bid}/invoice/xml",
            token=pro_tok,
        )
        self.assertEqual(s_xml, 200, xml_res)
        self.assertIn("urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1", xml_res["xml"])
        self.assertIn(inv["invoice_no"], xml_res["xml"])
        self.assertIn("0000000000000", xml_res["xml"])

    def test_3_4_audit_fixes_and_live_twilio_webhooks(self):
        """Verify audit fixes: Instant Book on add_service, Twilio Voice (TwiML XML) & WhatsApp webhooks, and Admin plan selection."""
        pro_tok = self.login("mester@rezolv.ro", "pro")
        admin_tok = self.login("admin@rezolv.ro", "admin")

        # 1. Pro adds a new service with instant_book=True
        s_svc, _ = self.call(
            "POST",
            "/api/pro/services",
            {
                "name": "Desfundare rapidă cu hidrojet",
                "price_from": 240,
                "duration": "1 oră",
                "instant_book": True,
            },
            token=pro_tok,
        )
        self.assertEqual(s_svc, 200)
        _, pro_pub = self.call("GET", "/api/professionals/binder-lukas-instalator")
        added_svc = [s for s in pro_pub["professional"]["services"] if s["name"] == "Desfundare rapidă cu hidrojet"][0]
        self.assertTrue(added_svc["instant_book"])

        # 2. Live Twilio Voice Webhook via x-www-form-urlencoded returns Romanian TwiML XML and creates booking
        form_raw = (
            b"From=%2B40745998877&CallerName=Elena+Sibiu&SpeechResult=Scurgere+teava+in+Hipodrom"
        )
        st_voice, voice_parsed, voice_hdrs = server.dispatch_test_request(
            self.ctx,
            "POST",
            "/api/webhooks/twilio-voice",
            raw=form_raw,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(st_voice, 200, voice_parsed)
        self.assertIn("application/xml", voice_hdrs.get("Content-Type", ""))
        self.assertIn('<Say voice="Polly.Carmen" language="ro-RO">', voice_parsed["raw_text"])
        self.assertIn("lei", voice_parsed["raw_text"])

        # 3. Live Twilio WhatsApp Webhook via JSON
        st_wa, wa_res = self.call(
            "POST",
            "/api/webhooks/twilio-whatsapp",
            {
                "From": "whatsapp:+40745334455",
                "ProfileName": "Radu Popescu",
                "Body": "Bună! Cât costă desfundarea în Turnișor și când aveți loc?",
            },
        )
        self.assertEqual(st_wa, 200, wa_res)
        self.assertTrue(wa_res["handled"])
        self.assertIn("twiml", wa_res)
        self.assertEqual(wa_res["booking"]["status"], "estimated")

        # 4. Admin White-Glove Onboarding with 'business' plan
        s_onb, onb_res = self.call(
            "POST",
            "/api/admin/pros/onboard",
            {
                "name": "Sorin Munteanu",
                "email": "sorin.business@rezolv.ro",
                "phone": "+40 745 777 888",
                "company_name": "SORIN TERMO BUSINESS S.R.L.",
                "cui": "RO14399840",
                "category": "Instalații Sanitare",
                "plan": "business",
                "plan_status": "active",
            },
            token=admin_tok,
        )
        self.assertEqual(s_onb, 200, onb_res)
        onb_pro = [p for p in onb_res["overview"]["professionals"] if p["email"] == "sorin.business@rezolv.ro"][0]
        self.assertEqual(onb_pro["plan"], "business")
        self.assertEqual(onb_pro["subscription_price_eur"], 69)


if __name__ == "__main__":
    unittest.main()
