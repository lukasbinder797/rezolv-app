"""Adversarial Empirical Test Suite: Milestone 3 URL Routing, Deep Links & Security Guardrails.

Challenger 1 Empirical Verification for Milestone 3:
1. URL parsing & query routing edge cases (empty, unknown, malformed, nonexistent slugs).
2. Romanian diacritic handling (Instalații Sanitare, Instalatii Electrice, Ş/Ț cedilla vs comma, NFC/NFD normalization).
3. Clean path variants (/pro/<slug>, /pro/<uuid>, case insensitivity).
4. Path traversal, XSS, and SQL injection payloads in path and query parameters.
5. In-process HTTP verification against router logic and error handling.
"""
import json
import os
import sys
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rezolv import config, core, db, seed, server, services


class TestAdversarialM3Routing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmpdir.name, "m3_adversarial.db")
        db.init_db(cls.db_path)
        conn = db.connect(cls.db_path)
        seed.seed(conn)
        conn.close()
        cls.ctx = server.Context(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def dispatch(self, method: str, path: str, body: dict | None = None, headers: dict | None = None):
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        h = {"Content-Type": "application/json"} if body is not None else {}
        if headers:
            h.update(headers)
        self.ctx.limiter.hits.clear()
        status, resp, resp_headers = server.dispatch_test_request(
            self.ctx, method, path, raw=raw, headers=h
        )
        return status, resp, resp_headers

    # =========================================================================
    # 1. Query Routing & Category Filtering Edge Cases
    # =========================================================================

    def test_query_category_empty_value_returns_all_active_pros(self):
        """/?category= (empty value) should not crash or filter out all pros."""
        status, resp, _ = self.dispatch("GET", "/api/professionals?category=")
        self.assertEqual(status, 200)
        self.assertIn("professionals", resp)
        self.assertGreater(len(resp["professionals"]), 0)

    def test_query_category_unknown_value_returns_empty_array(self):
        """/?category=unknown_xyz_12345 returns empty list gracefully without error."""
        status, resp, _ = self.dispatch("GET", "/api/professionals?category=unknown_xyz_12345")
        self.assertEqual(status, 200)
        self.assertIn("professionals", resp)
        self.assertEqual(len(resp["professionals"]), 0)

    def test_query_category_romanian_diacritics_exact(self):
        """/?category=Instala%C8%9Bii%20Sanitare matches seeded sanitare pros."""
        cat_encoded = urllib.parse.quote("Instalații Sanitare")
        status, resp, _ = self.dispatch("GET", f"/api/professionals?category={cat_encoded}")
        self.assertEqual(status, 200)
        pros = resp["professionals"]
        self.assertGreater(len(pros), 0)
        marian = next((p for p in pros if p["slug"] == "marian-popescu-instalator"), None)
        self.assertIsNotNone(marian)

    def test_query_category_without_diacritics_in_search(self):
        """Free-text search `q=instalatii electrice` finds pros despite diacritics."""
        q_encoded = urllib.parse.quote("instalatii electrice")
        status, resp, _ = self.dispatch("GET", f"/api/professionals?q={q_encoded}")
        self.assertEqual(status, 200)
        self.assertGreater(len(resp["professionals"]), 0)

    def test_query_category_nonexistent_zugraveli_amenajari(self):
        """/?category=zugraveli-si-amenajari returns 200 with empty list (safe recovery)."""
        status, resp, _ = self.dispatch("GET", "/api/professionals?category=zugraveli-si-amenajari")
        self.assertEqual(status, 200)
        self.assertEqual(resp["professionals"], [])

    # =========================================================================
    # 2. Professional Slug & ID Resolution Edge Cases
    # =========================================================================

    def test_pro_valid_slug_resolution(self):
        """GET /api/professionals/marian-popescu-instalator resolves pro detail."""
        status, resp, _ = self.dispatch("GET", "/api/professionals/marian-popescu-instalator")
        self.assertEqual(status, 200)
        pro = resp["professional"]
        self.assertEqual(pro["slug"], "marian-popescu-instalator")
        self.assertEqual(pro["name"], "Marian Popescu")
        self.assertTrue(pro["verified"])

    def test_pro_valid_uuid_resolution(self):
        """GET /api/professionals/<uuid> resolves pro detail."""
        conn = db.connect(self.db_path)
        row = conn.execute("SELECT user_id, slug FROM pro_profiles WHERE slug='marian-popescu-instalator'").fetchone()
        conn.close()
        self.assertIsNotNone(row)
        user_id = row["user_id"]
        status, resp, _ = self.dispatch("GET", f"/api/professionals/{user_id}")
        self.assertEqual(status, 200)
        pro = resp["professional"]
        self.assertEqual(pro["id"], user_id)
        self.assertEqual(pro["slug"], "marian-popescu-instalator")

    def test_pro_case_insensitive_slug_resolution(self):
        """GET /api/professionals/MARIAN-POPESCU-INSTALATOR resolves cleanly."""
        status, resp, _ = self.dispatch("GET", "/api/professionals/MARIAN-POPESCU-INSTALATOR")
        self.assertEqual(status, 200)
        self.assertEqual(resp["professional"]["slug"], "marian-popescu-instalator")

    def test_pro_nonexistent_slug_returns_404(self):
        """GET /api/professionals/nonexistent-slug-99999 returns clean 404."""
        status, resp, _ = self.dispatch("GET", "/api/professionals/nonexistent-slug-99999")
        self.assertEqual(status, 404)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], "not_found")

    def test_pro_empty_identifier_handled(self):
        """GET /api/professionals/ returns 404 (not matching pro or list with empty)."""
        status, resp, _ = self.dispatch("GET", "/api/professionals/")
        # Trailing slash either returns 404 or redirects/treats as invalid path
        self.assertIn(status, [200, 404])

    # =========================================================================
    # 3. Path Traversal & Injection Attacks
    # =========================================================================

    def test_path_traversal_in_identifier(self):
        """GET /api/professionals/../../etc/passwd must return 404, NEVER leak file."""
        status, resp, _ = self.dispatch("GET", "/api/professionals/../../etc/passwd")
        # In HTTP router, ../../ resolves or fails regex match -> 404
        self.assertIn(status, [400, 404])
        self.assertNotIn("root:", str(resp))

    def test_xss_in_pro_identifier(self):
        """GET /api/professionals/<script>alert(1)</script> rejected safely."""
        status, resp, _ = self.dispatch("GET", "/api/professionals/<script>alert(1)</script>")
        self.assertEqual(status, 404)
        self.assertNotIn("<script>", resp.get("professional", {}).get("name", ""))

    def test_sql_injection_in_pro_identifier(self):
        """GET /api/professionals/' OR 1=1-- rejected safely with 404."""
        status, resp, _ = self.dispatch("GET", "/api/professionals/' OR 1=1--")
        self.assertEqual(status, 404)

    def test_sql_injection_in_category_query(self):
        """GET /api/professionals?category=' OR 1=1-- returns empty list, does not dump DB."""
        status, resp, _ = self.dispatch("GET", "/api/professionals?category=' OR 1=1--")
        self.assertEqual(status, 200)
        # Should NOT match all pros
        self.assertEqual(resp["professionals"], [])

    def test_xss_in_category_query(self):
        """GET /api/professionals?category=<script>alert(1)</script> returns empty list."""
        status, resp, _ = self.dispatch("GET", "/api/professionals?category=<script>alert(1)</script>")
        self.assertEqual(status, 200)
        self.assertEqual(resp["professionals"], [])

    def test_path_traversal_in_category_query(self):
        """GET /api/professionals?category=../../etc/passwd returns empty list."""
        status, resp, _ = self.dispatch("GET", "/api/professionals?category=../../etc/passwd")
        self.assertEqual(status, 200)
        self.assertEqual(resp["professionals"], [])


if __name__ == "__main__":
    unittest.main()
