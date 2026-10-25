"""Regression & Security Audit Test Suite for REZOLV Sibiu MVP.
Covers:
- Exhaustive endpoint authentication & RBAC check across every registered route
- Email verification end-to-end lifecycle
- GDPR Article 20 Data Export & Article 17 Account/Data Deletion
- ETag & 304 Not Modified HTTP caching
- Spend caps & billing alert thresholds
- Error tracking & alerting pipeline
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

from rezolv import config, db, observability, server


class TestRegressionSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = os.path.join(tempfile.mkdtemp(), "regression.db")
        _, cls.ctx = server.create_server("127.0.0.1", 0, cls.db_path, bind_socket=False)

    def req(self, method: str, path: str, body: dict | None = None, token: str | None = None, headers: dict | None = None):
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        hdrs = {}
        if raw is not None:
            hdrs["Content-Type"] = "application/json"
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        if headers:
            hdrs.update(headers)
        return server.dispatch_test_request(self.ctx, method, path, raw=raw, headers=hdrs)

    def login(self, email: str, role: str | None = None, pw: str = "Demo1234") -> str:
        s, b, _ = self.req("POST", "/api/auth/login", {"email": email, "password": pw, "role": role})
        self.assertEqual(s, 200, b)
        return b["token"]

    def test_exhaustive_auth_on_every_endpoint(self):
        """Audit every route in `server.R`: protected routes must return 401 without a token,
        admin routes must return 403 for clients/pros, and pro routes must return 403 for clients."""
        client_token = self.login("client@rezolv.ro", "client")
        pro_token = self.login("mester@rezolv.ro", "pro")

        sample_path_for = lambda pattern: (
            pattern.lstrip("^")
            .rstrip("$")
            .replace("(?P<id>[\\w-]+)", "u_test123")
            .replace("(?P<id>\\w+)", "b_test123")
            .replace("(?P<name>[^/]+)", "Cur%C4%83%C8%9Benie")
        )

        protected_checked = 0
        admin_checked = 0
        pro_checked = 0
        for method, rx, _, auth in server.R:
            path = sample_path_for(rx.pattern)
            body = {} if method in ("POST", "PUT", "PATCH", "DELETE") else None
            if auth:
                s_anon, _, _ = self.req(method, path, body=body)
                self.assertEqual(s_anon, 401, f"Protected route {method} {path} did not reject anonymous request!")
                protected_checked += 1

            if path.startswith("/api/admin/"):
                s_cli, _, _ = self.req(method, path, body=body, token=client_token)
                s_pro, _, _ = self.req(method, path, body=body, token=pro_token)
                self.assertEqual(s_cli, 403, f"Admin route {method} {path} allowed client!")
                self.assertEqual(s_pro, 403, f"Admin route {method} {path} allowed pro!")
                admin_checked += 1

            if path.startswith("/api/pro/"):
                s_cli, _, _ = self.req(method, path, body=body, token=client_token)
                self.assertEqual(s_cli, 403, f"Pro route {method} {path} allowed client!")
                pro_checked += 1

        self.assertGreaterEqual(protected_checked, 25)
        self.assertGreaterEqual(admin_checked, 9)
        self.assertGreaterEqual(pro_checked, 6)

    def test_email_verification_and_gdpr_export_and_account_deletion(self):
        # 1. Register a brand new user -> starts with email_verified=False and receives dev_verification_token
        s_reg, b_reg, _ = self.req(
            "POST",
            "/api/auth/register",
            {"email": "gdpr.user@test.ro", "password": "Parola123", "name": "Elena GDPR", "role": "client"},
        )
        self.assertEqual(s_reg, 200)
        tok = b_reg["token"]
        self.assertFalse(b_reg["user"]["email_verified"])
        ver_tok = b_reg.get("dev_verification_token")
        self.assertTrue(ver_tok)

        # 2. Confirm email verification
        s_ver, b_ver, _ = self.req("POST", "/api/auth/verify-email/confirm", {"token": ver_tok})
        self.assertEqual(s_ver, 200)
        self.assertTrue(b_ver["user"]["email_verified"])

        # Re-using the same verification token must fail with 400
        self.assertEqual(self.req("POST", "/api/auth/verify-email/confirm", {"token": ver_tok})[0], 400)

        # 3. Export GDPR data (Article 20)
        s_exp, b_exp, _ = self.req("GET", "/api/me/export", token=tok)
        self.assertEqual(s_exp, 200)
        self.assertEqual(b_exp["user"]["email"], "gdpr.user@test.ro")
        self.assertIn("bookings", b_exp)

        # 4. Delete account & data (Article 17 Right to Erasure)
        s_del, b_del, _ = self.req("DELETE", "/api/me", body={"password": "Parola123"}, token=tok)
        self.assertEqual((s_del, b_del["deleted"]), (200, True))

        # 5. Old token must immediately fail with 401 and login must fail with 401
        self.assertEqual(self.req("GET", "/api/me", token=tok)[0], 401)
        self.assertEqual(
            self.req("POST", "/api/auth/login", {"email": "gdpr.user@test.ro", "password": "Parola123"})[0], 401
        )

    def test_etag_caching_and_304_not_modified(self):
        s1, b1, h1 = self.req("GET", "/api/categories")
        self.assertEqual(s1, 200)
        etag = h1.get("ETag")
        self.assertTrue(etag)
        self.assertIn("max-age=60", h1.get("Cache-Control", ""))

        s2, _, _ = self.req("GET", "/api/categories", headers={"If-None-Match": etag})
        self.assertEqual(s2, 304)

    def test_error_tracking_observability_and_spend_caps(self):
        # 1. Report a client error
        s_err, b_err, _ = self.req(
            "POST",
            "/api/errors/report",
            {"message": "Simulated UI Render Error", "code": "ui_crash", "stack": "at App.tsx:100"},
        )
        self.assertEqual((s_err, b_err["ok"]), (200, True))

        # 2. Check Admin Observability & Backup endpoints
        admin = self.login("admin@rezolv.ro")
        s_obs, b_obs, _ = self.req("GET", "/api/admin/observability", token=admin)
        self.assertEqual(s_obs, 200)
        self.assertIn("performance", b_obs)
        self.assertIn("spend_caps", b_obs)
        self.assertIn("email_auth", b_obs)
        self.assertTrue(any(e["message"] == "Simulated UI Render Error" for e in b_obs["recent_errors"]))

        # 3. Trigger Spend Cap Enforcement
        conn = db.connect(self.db_path)
        old_cap = config.MONTHLY_SPEND_CAP_EUR
        try:
            config.MONTHLY_SPEND_CAP_EUR = 1.0  # Lower below base 15 EUR so cap is exceeded
            with self.assertRaises(core_err := Exception):
                observability.check_and_record_spend(conn, "ai", enforce=True)
        finally:
            config.MONTHLY_SPEND_CAP_EUR = old_cap
            conn.close()


if __name__ == "__main__":
    unittest.main()
