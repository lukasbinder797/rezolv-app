"""Smoke Test Suite for REZOLV Sibiu MVP.
Rapidly verifies critical paths: liveness/readiness probes, SEO/AEO endpoints
(robots.txt, sitemap.xml, llms.txt, JSON-LD structured data), legal endpoints,
catalog, auth, and AI triage fallback.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("REZOLV_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("REZOLV_BACKUP_DIR", tempfile.mkdtemp())

from rezolv import server


class TestSmokeSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = os.path.join(tempfile.mkdtemp(), "smoke.db")
        _, cls.ctx = server.create_server("127.0.0.1", 0, cls.db_path, bind_socket=False)

    def req(self, method: str, path: str, body: dict | None = None, headers: dict | None = None):
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        hdrs = {"Content-Type": "application/json"} if raw is not None else {}
        if headers:
            hdrs.update(headers)
        return server.dispatch_test_request(self.ctx, method, path, raw=raw, headers=hdrs)

    def test_01_health_live_and_ready_probes(self):
        s1, b1, h1 = self.req("GET", "/api/health")
        self.assertEqual(s1, 200)
        self.assertEqual(b1["status"], "ok")
        self.assertTrue(b1["db_ok"])
        self.assertIn("X-Request-Id", h1)
        self.assertIn("X-Response-Time-Ms", h1)
        self.assertIn("Strict-Transport-Security", h1)

        s2, b2, _ = self.req("GET", "/api/health/live")
        self.assertEqual((s2, b2["status"]), (200, "alive"))

        s3, b3, _ = self.req("GET", "/api/health/ready")
        self.assertEqual((s3, b3["status"], b3["db_connected"]), (200, "ready", True))

    def test_02_seo_and_aeo_endpoints(self):
        s_rob, b_rob, _ = self.req("GET", "/robots.txt")
        self.assertEqual(s_rob, 200)
        self.assertIn("Sitemap:", b_rob["raw_text"])
        self.assertIn("GPTBot", b_rob["raw_text"])

        s_map, b_map, _ = self.req("GET", "/sitemap.xml")
        self.assertEqual(s_map, 200)
        self.assertIn("<urlset", b_map["raw_text"])
        self.assertIn("Instala%C8%9Bii%20Sanitare", b_map["raw_text"])

        s_llm, b_llm, _ = self.req("GET", "/llms.txt")
        self.assertEqual(s_llm, 200)
        self.assertIn("REZOLV Sibiu", b_llm["raw_text"])

        s_sd, b_sd, _ = self.req("GET", "/api/seo/structured-data")
        self.assertEqual(s_sd, 200)
        self.assertEqual(b_sd["@context"], "https://schema.org")
        types = {node["@type"] for node in b_sd["@graph"]}
        self.assertEqual(types, {"LocalBusiness", "WebApplication", "FAQPage"})

    def test_03_legal_privacy_terms_and_cookie_consent(self):
        s_p, b_p, _ = self.req("GET", "/api/legal/privacy")
        self.assertEqual((s_p, b_p["kind"]), (200, "privacy_policy"))

        s_t, b_t, _ = self.req("GET", "/api/legal/terms")
        self.assertEqual((s_t, b_t["kind"]), (200, "terms_and_conditions"))

        s_c, b_c, _ = self.req("POST", "/api/legal/cookie-consent", {"analytics": True})
        self.assertEqual((s_c, b_c["ok"], b_c["consent"]["analytics"]), (200, True, True))

    def test_04_critical_business_smoke(self):
        s_cat, b_cat, _ = self.req("GET", "/api/categories")
        self.assertEqual((s_cat, len(b_cat["categories"])), (200, 12))

        s_log, b_log, _ = self.req("POST", "/api/auth/login", {"email": "client@rezolv.ro", "password": "Demo1234", "role": "client"})
        self.assertEqual(s_log, 200)
        self.assertTrue(b_log["token"])

        s_ai, b_ai, _ = self.req("POST", "/api/ai/recommend", {"problem": "Am pană la roată în Sibiu pe Calea Dumbrăvii"})
        self.assertEqual((s_ai, b_ai["category"]), (200, "Vulcanizare Mobilă"))


if __name__ == "__main__":
    unittest.main()
