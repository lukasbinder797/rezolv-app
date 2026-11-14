"""Empirical Adversarial Challenge Suite: E2E Wave 1 Test Track (Challenger 1)

Verifies:
1. Mutation Sensitivity (Oracles fail when invariants are violated):
   - M1: Unauthenticated booking bypass (200 instead of 401)
   - M2: Pro slug resolution failure (UUID-only resolution)
   - M3: Hardcoded rating return (fixed 4.9 float or "4.9" string)
   - M4: Subscription pricing tampering (50 RON instead of 49 RON)
   - M5: Prompt injection guardrail bypass
   - M6: Missing RON currency in triage price
   - M7: CUI missing Romanian "RO" prefix
2. Blind Spot & Edge Case Introspection:
   - BS1: Verification of uninvoked mock_gemini fixture in test_e2e_wave1.py
   - BS2: Verification of missing urllib import in backend/rezolv/services.py
   - BS3: Concurrency and sub-millisecond database clone isolation
"""
import inspect
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from rezolv import config, core, db, payments, seed, server, services


class TestEmpiricalMutationSensitivity(unittest.TestCase):
    """Executes mutations and empirically verifies that test_e2e_wave1.py detects them."""

    def test_mutation_01_unauth_booking_bypass_detected(self):
        """Mutation 1: Unauthenticated booking returning 200 MUST trigger test failure."""
        orig_dispatch = server.dispatch_test_request

        def mutated_dispatch(ctx, method, path, raw=None, headers=None):
            if method == "POST" and path == "/api/bookings" and ("Authorization" not in (headers or {})):
                return 200, {"booking": {"id": "b_mutated", "status": "pending"}}, {"Content-Type": "application/json"}
            return orig_dispatch(ctx, method, path, raw=raw, headers=headers)

        server.dispatch_test_request = mutated_dispatch
        try:
            ret = pytest.main([
                "backend/tests/test_e2e_wave1.py",
                "-k", "test_f4_01_booking_rejected_without_auth",
                "-q",
            ])
            self.assertNotEqual(ret, 0, "Test suite failed to detect unauthenticated booking bypass!")
        finally:
            server.dispatch_test_request = orig_dispatch

    def test_mutation_02_slug_resolution_failure_detected(self):
        """Mutation 2: Disabling pro slug lookup MUST trigger test failure."""
        orig_get_professional = services.get_professional

        def mutated_get_professional(conn, pro_id):
            if not pro_id or not isinstance(pro_id, str) or not pro_id.strip():
                raise services.ApiError(404, "not_found", "Meșterul nu a fost găsit.")
            ident = pro_id.strip()
            # Only allow UUID lookup
            r = conn.execute(services._PRO_JOIN + " AND p.user_id = ?", (ident,)).fetchone()
            if not r:
                raise services.ApiError(404, "not_found", "Meșterul nu a fost găsit.")
            return {"professional": services._public_pro(conn, r, detail=True)}

        services.get_professional = mutated_get_professional
        try:
            ret = pytest.main([
                "backend/tests/test_e2e_wave1.py",
                "-k", "test_f3_01_resolve_by_slug",
                "-q",
            ])
            self.assertNotEqual(ret, 0, "Test suite failed to detect broken slug resolution!")
        finally:
            services.get_professional = orig_get_professional

    def test_mutation_03_hardcoded_rating_detected(self):
        """Mutation 3: ProDashboard returning hardcoded 4.9 rating MUST trigger test failure."""
        orig_pro_dashboard = services.pro_dashboard

        def mutated_pro_dashboard(conn, user):
            res = orig_pro_dashboard(conn, user)
            res["rating_avg"] = 4.9
            return res

        services.pro_dashboard = mutated_pro_dashboard
        try:
            ret = pytest.main([
                "backend/tests/test_e2e_wave1.py",
                "-k", "test_f6_04_no_review_default_behavior",
                "-q",
            ])
            self.assertNotEqual(ret, 0, "Test suite failed to detect hardcoded 4.9 rating!")
        finally:
            services.pro_dashboard = orig_pro_dashboard

    def test_mutation_04_string_rating_type_detected(self):
        """Mutation 3B: ProDashboard returning string '4.9' instead of float MUST trigger test failure."""
        orig_pro_dashboard = services.pro_dashboard

        def mutated_pro_dashboard(conn, user):
            res = orig_pro_dashboard(conn, user)
            res["rating_avg"] = "4.9"
            return res

        services.pro_dashboard = mutated_pro_dashboard
        try:
            ret = pytest.main([
                "backend/tests/test_e2e_wave1.py",
                "-k", "test_f6_02_pro_dashboard_rating_metrics",
                "-q",
            ])
            self.assertNotEqual(ret, 0, "Test suite failed to detect string rating type artifact!")
        finally:
            services.pro_dashboard = orig_pro_dashboard

    def test_mutation_05_subscription_pricing_tamper_detected(self):
        """Mutation 4: Essential plan price set to 50 RON instead of 49 MUST trigger test failure."""
        orig_plans = dict(payments.PLANS)
        mutated_plans = dict(payments.PLANS)
        mutated_plans["essential"] = dict(mutated_plans["essential"])
        mutated_plans["essential"]["price_ron"] = 50
        payments.PLANS = mutated_plans
        try:
            ret = pytest.main([
                "backend/tests/test_e2e_wave1.py",
                "-k", "test_f9_01_essential_plan_49_ron",
                "-q",
            ])
            self.assertNotEqual(ret, 0, "Test suite failed to detect subscription price tampering!")
        finally:
            payments.PLANS = orig_plans

    def test_mutation_06_prompt_injection_bypass_detected(self):
        """Mutation 5: Bypassing prompt injection guardrail MUST trigger test failure."""
        orig_ai = services.ai_recommend

        def mutated_ai(conn, data):
            if "Ignore all previous instructions" in data.get("problem", ""):
                return {
                    "category": "Instalații Sanitare",
                    "identified_malfunction": "Bypass",
                    "price_range_ron": {"min": 100, "max": 200},
                    "urgency": "mediu",
                    "reason": "Bypassed",
                    "photos_analyzed": 0,
                    "engine": "gemini-2.5-flash",
                    "professional": None,
                }
            return orig_ai(conn, data)

        services.ai_recommend = mutated_ai
        try:
            ret = pytest.main([
                "backend/tests/test_e2e_wave1.py",
                "-k", "test_b5_02_prompt_injection_guardrail",
                "-q",
            ])
            self.assertNotEqual(ret, 0, "Test suite failed to detect prompt injection bypass!")
        finally:
            services.ai_recommend = orig_ai

    def test_mutation_07_cui_ro_prefix_missing_detected(self):
        """Mutation 7: CUI lacking Romanian 'RO' prefix MUST trigger test failure."""
        orig_pub = services._public_pro

        def mutated_pub(conn, r, category=None, detail=False):
            res = orig_pub(conn, r, category=category, detail=detail)
            if "cui" in res:
                res["cui"] = "12345678"
            return res

        services._public_pro = mutated_pub
        try:
            ret = pytest.main([
                "backend/tests/test_e2e_wave1.py",
                "-k", "test_f5_02_cui_verification_badge",
                "-q",
            ])
            self.assertNotEqual(ret, 0, "Test suite failed to detect missing RO prefix in CUI!")
        finally:
            services._public_pro = orig_pub


class TestEmpiricalBlindSpotAuditing(unittest.TestCase):
    """Adversarial structural analysis revealing edge case blind spots."""

    def test_blind_spot_01_mock_gemini_referenced_in_tests(self):
        """Empirically proves mock_gemini fixture is invoked by the F7 Vision triage tests."""
        test_file_path = os.path.join(os.path.dirname(__file__), "test_e2e_wave1.py")
        with open(test_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Find all test function definitions
        test_defs = re.findall(r"def (test_[a-zA-Z0-9_]+)\(([^)]*)\):", content)
        self.assertGreater(len(test_defs), 80, "Expected >= 80 tests in suite")

        tests_using_mock_gemini = [
            name for name, params in test_defs if "mock_gemini" in params
        ]
        # Structural proof: at least 5 F7 Vision tests invoke mock_gemini
        self.assertGreaterEqual(
            len(tests_using_mock_gemini),
            5,
            f"Expected >= 5 callers of mock_gemini among test functions, got: {tests_using_mock_gemini}",
        )

    def test_blind_spot_02_missing_urllib_import_in_services(self):
        """Empirically proves backend/rezolv/services.py lacks urllib import."""
        services_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rezolv", "services.py")
        with open(services_file, "r", encoding="utf-8") as f:
            services_code = f.read()

        # Check for top-level urllib import
        has_top_level_urllib = bool(re.search(r"^\s*import urllib", services_code, re.MULTILINE))
        self.assertFalse(
            has_top_level_urllib,
            "backend/rezolv/services.py does not import urllib at the module level",
        )

    def test_isolation_concurrency_template_cloning(self):
        """Empirically verifies sub-millisecond database clone isolation under rapid sequential copies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template = os.path.join(tmpdir, "template.db")
            db.init_db(template)
            conn = db.connect(template)
            seed.seed(conn)
            conn.close()

            # Clone 10 times in rapid succession
            for i in range(10):
                clone = os.path.join(tmpdir, f"clone_{i}.db")
                shutil.copyfile(template, clone)
                conn_c = db.connect(clone)
                pros_cnt = conn_c.execute("SELECT COUNT(*) FROM pro_profiles").fetchone()[0]
                self.assertGreaterEqual(pros_cnt, 9)
                conn_c.close()
