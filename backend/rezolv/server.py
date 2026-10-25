"""HTTP layer: routing, JSON, SEO/AEO (robots.txt, sitemap.xml, llms.txt),
CORS allow-list, HSTS/CSP security headers, ETag caching, performance monitoring,
and structured error tracking."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

FRONTEND_DIST = Path(
    os.environ.get(
        "REZOLV_FRONTEND_DIST",
        str(Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"),
    )
)

from . import ai_evals, analytics, config, db, observability, payments, seed, services as svc
from . import verification as ver
from .core import ApiError, RateLimiter, new_id, now_ts


class Context:
    def __init__(self, db_path=None):
        self.db_path = db_path or config.DB_PATH
        self.secret = config.get_secret()
        self.limiter = RateLimiter()
        self.provider = payments.get_provider()


def bootstrap(ctx, with_seed=True):
    db.init_db(ctx.db_path)
    conn = db.connect(ctx.db_path)
    try:
        if with_seed:
            seed.seed(conn)
        for r in conn.execute("SELECT cui, company_name FROM pro_profiles WHERE verification_status='verified'"):
            ver.register(r["cui"], r["company_name"])
        for cui, name in DEMO_REGISTRY:
            ver.register(ver.make_cui(cui), name)
    finally:
        conn.close()


# Companies the ONRC/ANAF registry knows out-of-the-box — new pro sign-ups with these CUIs auto-verify.
DEMO_REGISTRY = [
    ("4561230", "INSTAL PRO SERVICE SIBIU S.R.L."),
    ("4780019", "CASA BUNA RENOVARI SIBIU S.R.L."),
    ("3920417", "ELECTRO TOTAL HERMANNSTADT S.R.L."),
]

# (method, regex, handler(ctx, conn, user, params, body, query), auth) -- auth: None=public, True=required
R = []


def route(method, pattern, auth=True):
    def deco(fn):
        R.append((method, re.compile("^" + pattern + "$"), fn, auth))
        return fn

    return deco


@route("GET", "/api/health", auth=None)
def _health(ctx, conn, user, p, b, q):
    db_ok = bool(conn.execute("SELECT 1").fetchone()[0] == 1)
    spend = observability.get_spend_and_quota_status(conn)
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "rezolv-api",
        "version": "2.1-production-ready",
        "environment": config.ENV,
        "pilot_city": config.PILOT_CITY,
        "uptime_seconds": max(1, now_ts() - config.BOOT_TIMESTAMP),
        "db_ok": db_ok,
        "spend_cap_ok": not spend["cap_exceeded"],
    }


@route("GET", "/api/health/live", auth=None)
def _health_live(ctx, conn, user, p, b, q):
    return {"status": "alive", "uptime_seconds": max(1, now_ts() - config.BOOT_TIMESTAMP)}


@route("GET", "/api/health/ready", auth=None)
def _health_ready(ctx, conn, user, p, b, q):
    users_cnt = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return {"status": "ready", "db_connected": True, "seeded_users": users_cnt}


@route("POST", "/api/auth/register", auth=None)
def _register(ctx, conn, user, p, b, q):
    ctx.limiter.check("register:" + ctx.ip, 20, 3600)
    return svc.register(conn, ctx, b)


@route("POST", "/api/auth/login", auth=None)
def _login(ctx, conn, user, p, b, q):
    return svc.login(conn, ctx, b, ctx.ip)


@route("POST", "/api/auth/password-reset", auth=None)
def _reset(ctx, conn, user, p, b, q):
    return svc.request_password_reset(conn, ctx, b, ctx.ip)


@route("POST", "/api/auth/password-reset/confirm", auth=None)
def _reset_confirm(ctx, conn, user, p, b, q):
    return svc.confirm_password_reset(conn, ctx, b)


@route("POST", "/api/auth/verify-email/send")
def _verify_email_send(ctx, conn, user, p, b, q):
    return svc.send_email_verification(conn, ctx, user)


@route("POST", "/api/auth/verify-email/confirm", auth=None)
def _verify_email_confirm(ctx, conn, user, p, b, q):
    return svc.confirm_email_verification(conn, b)


@route("GET", "/api/me")
def _me(ctx, conn, user, p, b, q):
    return svc.me(conn, user)


@route("PATCH", "/api/me")
def _me_update(ctx, conn, user, p, b, q):
    return svc.update_me(conn, user, b)


@route("GET", "/api/me/export")
def _me_export(ctx, conn, user, p, b, q):
    return svc.export_user_data(conn, user)


@route("DELETE", "/api/me")
def _me_delete(ctx, conn, user, p, b, q):
    return svc.delete_user_account(conn, user, b)


@route("POST", "/api/me/delete")
def _me_delete_post(ctx, conn, user, p, b, q):
    return svc.delete_user_account(conn, user, b)


@route("POST", "/api/legal/cookie-consent", auth=None)
def _cookie_consent(ctx, conn, user, p, b, q):
    return svc.save_cookie_consent(conn, user, b)


@route("GET", "/api/legal/privacy", auth=None)
def _legal_privacy(ctx, conn, user, p, b, q):
    return svc.get_legal_document("privacy")


@route("GET", "/api/legal/terms", auth=None)
def _legal_terms(ctx, conn, user, p, b, q):
    return svc.get_legal_document("terms")


@route("GET", "/api/seo/structured-data", auth=None)
def _seo_structured(ctx, conn, user, p, b, q):
    return svc.get_seo_structured_data(conn)


@route("POST", "/api/errors/report", auth=None)
def _error_report(ctx, conn, user, p, b, q):
    ctx.limiter.check("err_report:" + ctx.ip, 30, 600)
    data = b if isinstance(b, dict) else {}
    msg = str(data.get("message") or "Client UI Error")[:500]
    stack = str(data.get("stack") or "")[:3000]
    code = str(data.get("code") or "ui_crash")[:60]
    eid = observability.capture_error(
        conn,
        "frontend",
        msg,
        level="error",
        error_code=code,
        stack_trace=stack,
        path=str(data.get("url") or "/"),
        metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
    )
    conn.commit()
    return {"ok": True, "error_id": eid}


@route("GET", "/api/categories", auth=None)
def _cats(ctx, conn, user, p, b, q):
    return svc.list_categories(conn)


@route("GET", "/api/professionals", auth=None)
def _pros(ctx, conn, user, p, b, q):
    return svc.list_professionals(conn, q.get("category"), q.get("q"), q.get("zone"))


@route("GET", "/api/professionals/(?P<id>[\\w-]+)", auth=None)
def _pro(ctx, conn, user, p, b, q):
    return svc.get_professional(conn, p["id"])


@route("GET", "/api/bookings")
def _bookings(ctx, conn, user, p, b, q):
    return svc.list_bookings(conn, user, q.get("status"))


@route("POST", "/api/bookings")
def _booking_new(ctx, conn, user, p, b, q):
    return svc.create_booking(conn, ctx, user, b)


@route("GET", "/api/bookings/(?P<id>\\w+)")
def _booking(ctx, conn, user, p, b, q):
    return svc.get_booking(conn, user, p["id"])


@route("POST", "/api/bookings/(?P<id>\\w+)/quote")
def _quote(ctx, conn, user, p, b, q):
    return svc.quote_booking(conn, user, p["id"], b)


@route("POST", "/api/bookings/(?P<id>\\w+)/estimate")
def _estimate(ctx, conn, user, p, b, q):
    return svc.send_estimate(conn, user, p["id"], b)


@route("POST", "/api/bookings/(?P<id>\\w+)/accept-estimate")
def _accept_estimate(ctx, conn, user, p, b, q):
    return svc.accept_estimate(conn, user, p["id"], b)


@route("POST", "/api/bookings/(?P<id>\\w+)/decline-estimate")
def _decline_estimate(ctx, conn, user, p, b, q):
    return svc.decline_estimate(conn, user, p["id"], b)


@route("POST", "/api/bookings/(?P<id>\\w+)/reschedule")
def _reschedule(ctx, conn, user, p, b, q):
    return svc.reschedule_booking(conn, user, p["id"], b)


@route("POST", "/api/bookings/(?P<id>\\w+)/sms-trigger")
def _sms_trigger(ctx, conn, user, p, b, q):
    return svc.trigger_booking_sms_now(conn, user, p["id"])


@route("POST", "/api/bookings/(?P<id>\\w+)/refuse")
def _refuse(ctx, conn, user, p, b, q):
    return svc.refuse_booking(conn, user, p["id"])


@route("POST", "/api/bookings/(?P<id>\\w+)/cancel")
def _cancel(ctx, conn, user, p, b, q):
    return svc.cancel_booking(conn, user, p["id"])


@route("POST", "/api/bookings/(?P<id>\\w+)/complete")
def _complete(ctx, conn, user, p, b, q):
    return svc.complete_booking(conn, user, p["id"])


@route("POST", "/api/bookings/(?P<id>\\w+)/no-show")
def _no_show(ctx, conn, user, p, b, q):
    return svc.mark_no_show(conn, user, p["id"])


@route("POST", "/api/bookings/(?P<id>\\w+)/review")
def _review(ctx, conn, user, p, b, q):
    return svc.review_booking(conn, user, p["id"], b)


@route("GET", "/api/pro/dashboard")
def _dash(ctx, conn, user, p, b, q):
    return svc.pro_dashboard(conn, user)


@route("GET", "/api/pro/calendar")
def _pro_cal(ctx, conn, user, p, b, q):
    return svc.pro_calendar(conn, user)


@route("GET", "/api/pro/categories")
def _pro_cats(ctx, conn, user, p, b, q):
    return svc.pro_categories(conn, user)


@route("PUT", "/api/pro/categories/(?P<name>[^/]+)")
def _pro_cat_toggle(ctx, conn, user, p, b, q):
    from urllib.parse import unquote

    return svc.set_category_enabled(conn, user, unquote(p["name"]), b)


@route("POST", "/api/pro/services")
def _pro_service_add(ctx, conn, user, p, b, q):
    return svc.add_service(conn, user, b)


@route("PATCH", "/api/pro/profile")
def _pro_profile(ctx, conn, user, p, b, q):
    return svc.update_pro_profile(conn, user, b)


@route("POST", "/api/pro/verification")
def _pro_verify(ctx, conn, user, p, b, q):
    return svc.submit_verification(conn, user, b)


@route("GET", "/api/subscription")
def _sub(ctx, conn, user, p, b, q):
    return svc.subscription(conn, user)


@route("POST", "/api/subscription/checkout")
def _checkout(ctx, conn, user, p, b, q):
    return svc.checkout(conn, ctx, user, b)


@route("POST", "/api/payment-methods")
def _pm(ctx, conn, user, p, b, q):
    return svc.save_payment_method(conn, user, b)


@route("GET", "/api/payments/(?P<id>\\w+)/invoice-xml")
def _payment_invoice_xml(ctx, conn, user, p, b, q):
    return svc.get_payment_invoice_xml(conn, user, p["id"])


@route("POST", "/api/ai/recommend", auth=None)
def _ai(ctx, conn, user, p, b, q):
    ctx.limiter.check("ai:" + ctx.ip, 30, 600)
    return svc.ai_recommend(conn, b)


@route("POST", "/api/analytics/track", auth=None)
def _track_event(ctx, conn, user, p, b, q):
    ev_name = str((b or {}).get("event") or "ui_interaction")[:80]
    props = (b or {}).get("properties") if isinstance((b or {}).get("properties"), dict) else {}
    uid = (b or {}).get("user_id")
    role = (b or {}).get("role")
    eid = analytics.track(conn, uid, role, ev_name, props)
    conn.commit()
    return {"ok": True, "event_id": eid}


@route("GET", "/api/notifications")
def _notifs(ctx, conn, user, p, b, q):
    return svc.list_notifications(conn, user)


@route("POST", "/api/notifications/read")
def _notifs_read(ctx, conn, user, p, b, q):
    return svc.mark_notifications_read(conn, user)


@route("GET", "/api/admin/metrics")
def _metrics(ctx, conn, user, p, b, q):
    return svc.admin_metrics(conn, user)


@route("GET", "/api/admin/overview")
def _admin_overview(ctx, conn, user, p, b, q):
    return svc.admin_overview(conn, user)


@route("GET", "/api/admin/observability")
def _admin_obs(ctx, conn, user, p, b, q):
    return svc.admin_observability_report(conn, user)


@route("POST", "/api/admin/db/backup")
def _admin_backup(ctx, conn, user, p, b, q):
    return svc.admin_run_backup(conn, user, db_path=ctx.db_path)


@route("POST", "/api/admin/db/verify-restore")
def _admin_verify_restore(ctx, conn, user, p, b, q):
    return svc.admin_verify_restore(conn, user, db_path=ctx.db_path)


@route("GET", "/api/admin/ai-evals")
def _admin_ai_evals(ctx, conn, user, p, b, q):
    svc.require_role(user, "admin")
    return ai_evals.run_eval_suite(conn)


@route("POST", "/api/admin/cui-lookup")
def _admin_cui(ctx, conn, user, p, b, q):
    return svc.admin_cui_lookup(conn, user, b)


@route("POST", "/api/admin/pros/onboard")
def _admin_onboard(ctx, conn, user, p, b, q):
    return svc.admin_white_glove_onboard(conn, user, b)


@route("PATCH", "/api/admin/pros/(?P<id>\\w+)/subscription")
def _admin_sub(ctx, conn, user, p, b, q):
    return svc.admin_update_pro_subscription(conn, user, p["id"], b)


@route("POST", "/api/admin/sms/trigger-due")
def _admin_sms_trigger(ctx, conn, user, p, b, q):
    return svc.admin_trigger_due_sms(conn, user)


@route("GET", "/api/admin/pros/pending")
def _pending(ctx, conn, user, p, b, q):
    return svc.admin_pending_pros(conn, user)


@route("POST", "/api/admin/pros/(?P<id>\\w+)/review")
def _admin_review(ctx, conn, user, p, b, q):
    return svc.admin_review_pro(conn, user, p["id"], b)


# ------------------------------------------- SEO & AEO Generators (robots, sitemap, llms.txt)
def build_robots_txt() -> str:
    domain = f"https://{config.CUSTOM_DOMAIN}"
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /api/categories\n"
        "Allow: /api/professionals\n"
        "Disallow: /api/admin/\n"
        "Disallow: /api/me\n\n"
        "# Answer Engine Optimization (AEO) — AI Crawlers Welcome\n"
        "User-agent: GPTBot\n"
        "Allow: /\n"
        "Allow: /llms.txt\n\n"
        "User-agent: PerplexityBot\n"
        "Allow: /\n"
        "Allow: /llms.txt\n\n"
        "User-agent: ClaudeBot\n"
        "Allow: /\n"
        "Allow: /llms.txt\n\n"
        "User-agent: Google-Extended\n"
        "Allow: /\n\n"
        f"Sitemap: {domain}/sitemap.xml\n"
    )


def build_sitemap_xml(conn) -> str:
    domain = f"https://{config.CUSTOM_DOMAIN}"
    urls = [
        (f"{domain}/", "daily", "1.0"),
        (f"{domain}/llms.txt", "weekly", "0.8"),
        (f"{domain}/api/legal/privacy", "monthly", "0.5"),
        (f"{domain}/api/legal/terms", "monthly", "0.5"),
    ]
    for r in conn.execute("SELECT name FROM categories ORDER BY sort").fetchall():
        urls.append((f"{domain}/?category={quote(r['name'])}", "daily", "0.9"))
    for r in conn.execute("SELECT user_id FROM pro_profiles WHERE verification_status='verified'").fetchall():
        urls.append((f"{domain}/?pro={r['user_id']}", "weekly", "0.8"))

    items = "\n".join(
        f"  <url>\n    <loc>{loc}</loc>\n    <changefreq>{freq}</changefreq>\n    <priority>{prio}</priority>\n  </url>"
        for loc, freq, prio in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}\n"
        "</urlset>\n"
    )


def build_llms_txt(conn) -> str:
    cats = [r["name"] for r in conn.execute("SELECT name FROM categories ORDER BY sort").fetchall()]
    return (
        "# REZOLV Sibiu — B2B SaaS-Enabled Home & Auto Services Marketplace\n\n"
        "> Marketplace pentru meșteri și servicii auto verificate CUI în Sibiu, România.\n"
        "> Rezervare 100% gratuită pentru clienți (0% comision). Abonament SaaS 39 EUR/lună pentru profesioniști.\n\n"
        "## Categorii principale în Sibiu\n"
        + "\n".join(f"- {c}" for c in cats)
        + "\n\n## Cum funcționează (3-Step Estimate + Atomic Calendar Lock)\n"
        "1. Clientul descrie problema (sau folosește triajul AI în limba română).\n"
        "2. Meșterul verificat CUI (ONRC/ANAF) trimite din 2 click-uri o estimare de preț, durată și oră.\n"
        "3. Clientul acceptă estimarea -> slotul se blochează atomic în calendar și se programează remindere SMS la 24h și 2h înainte.\n"
    )


PUBLIC_CACHEABLE_GETS = {"/api/categories", "/api/seo/structured-data", "/api/legal/privacy", "/api/legal/terms"}


def make_handler(ctx):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Rezolv"
        sys_version = ""

        def log_message(self, fmt, *args):
            if "--quiet" not in sys.argv:
                sys.stderr.write("%s %s\n" % (self.command, fmt % args))

        def _cors(self):
            origin = self.headers.get("Origin")
            is_allowed = origin and (
                origin in config.ALLOWED_ORIGINS
                or bool(re.match(r"^https?://(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|localhost|127\.0\.0\.1)(:\d+)?$", origin))
            )
            if is_allowed:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, If-None-Match")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")

        def _security_headers(self, req_id: str, latency_ms: float):
            self.send_header("X-Request-Id", req_id)
            self.send_header("X-Response-Time-Ms", f"{latency_ms:.2f}")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            self.send_header("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
            self.send_header("Permissions-Policy", "camera=(self), geolocation=(self), microphone=()")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; connect-src 'self' http://localhost:* http://127.0.0.1:* https://*.posthog.com",
            )

        def _send(self, status, payload, *, req_id="req_0", latency_ms=0.0, cache_policy="no-store", etag=None, extra_headers=None):
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", cache_policy)
            if etag:
                self.send_header("ETag", etag)
            if extra_headers:
                for hk, hv in extra_headers.items():
                    self.send_header(hk, hv)
            self._security_headers(req_id, latency_ms)
            self._cors()
            self.end_headers()
            if raw:
                self.wfile.write(raw)

        def _send_text(self, status: int, content: str, content_type: str, req_id: str, latency_ms: float, cache_policy: str = "public, max-age=3600"):
            raw = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", cache_policy)
            self._security_headers(req_id, latency_ms)
            self._cors()
            self.end_headers()
            self.wfile.write(raw)

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def _handle(self, method):
            t0 = time.perf_counter()
            req_id = new_id("req_")
            ip = self.client_address[0]
            if ip in ("127.0.0.1", "::1", "localhost"):
                fwd = self.headers.get("X-Forwarded-For") or self.headers.get("X-Real-IP") or self.headers.get("CF-Connecting-IP")
                if fwd:
                    ip = fwd.split(",")[0].strip()
            conn = None
            user = None
            url = urlparse(self.path)
            try:
                ctx.limiter.check("global:" + ip, 600, 60)

                # SEO & AEO static/dynamic endpoints
                if method == "GET" and url.path in ("/robots.txt", "/sitemap.xml", "/llms.txt"):
                    conn = db.connect(ctx.db_path)
                    latency_ms = (time.perf_counter() - t0) * 1000
                    if url.path == "/robots.txt":
                        self._send_text(200, build_robots_txt(), "text/plain", req_id, latency_ms)
                    elif url.path == "/sitemap.xml":
                        self._send_text(200, build_sitemap_xml(conn), "application/xml", req_id, latency_ms)
                    else:
                        self._send_text(200, build_llms_txt(conn), "text/plain", req_id, latency_ms)
                    return

                body = {}
                if method in ("POST", "PUT", "PATCH", "DELETE"):
                    length = int(self.headers.get("Content-Length") or 0)
                    if length > config.MAX_BODY_BYTES:
                        raise ApiError(413, "too_large", "Cererea este prea mare.")
                    ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
                    raw = self.rfile.read(length) if length else b""
                    if raw:
                        if ctype != "application/json":
                            raise ApiError(415, "unsupported_media_type", "Se acceptă doar application/json.")
                        try:
                            body = json.loads(raw)
                        except ValueError:
                            raise ApiError(400, "bad_json", "JSON invalid.")
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                matched_path = False
                for m, rx, fn, auth in R:
                    hit = rx.match(url.path)
                    if not hit:
                        continue
                    matched_path = True
                    if m != method:
                        continue
                    conn = db.connect(ctx.db_path)
                    user = svc.authenticate(conn, ctx, self.headers.get("Authorization")) if auth else None
                    c = Context.__new__(Context)
                    c.__dict__.update(ctx.__dict__)
                    c.ip = ip
                    res_payload = fn(c, conn, user, hit.groupdict(), body, query)
                    latency_ms = (time.perf_counter() - t0) * 1000

                    cache_policy = "no-store"
                    etag = None
                    if method == "GET" and url.path in PUBLIC_CACHEABLE_GETS:
                        cache_policy = "public, max-age=60, stale-while-revalidate=300"
                        raw_hash = hashlib.sha1(
                            json.dumps(res_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
                        ).hexdigest()[:16]
                        etag = f'W/"{raw_hash}"'
                        inm = self.headers.get("If-None-Match")
                        if inm and inm.strip() == etag:
                            observability.record_request_metric(
                                conn, req_id, method, url.path, 304, latency_ms, None, ip
                            )
                            self._send(304, None, req_id=req_id, latency_ms=latency_ms, cache_policy=cache_policy, etag=etag)
                            return

                    observability.record_request_metric(
                        conn, req_id, method, url.path, 200, latency_ms, user["id"] if user else None, ip
                    )
                    self._send(200, res_payload, req_id=req_id, latency_ms=latency_ms, cache_policy=cache_policy, etag=etag)
                    return
                if matched_path:
                    raise ApiError(405, "method_not_allowed", "Metodă nepermisă.")
                if method == "GET" and not url.path.startswith("/api") and FRONTEND_DIST.exists():
                    rel = url.path.lstrip("/") or "index.html"
                    target = (FRONTEND_DIST / rel).resolve()
                    if not str(target).startswith(str(FRONTEND_DIST.resolve())) or not target.is_file():
                        target = FRONTEND_DIST / "index.html"
                    if target.is_file():
                        data = target.read_bytes()
                        ctype_guess, _ = mimetypes.guess_type(str(target))
                        latency_ms = (time.perf_counter() - t0) * 1000
                        is_asset = "/assets/" in url.path
                        self.send_response(200)
                        self.send_header("Content-Type", (ctype_guess or "text/html") + "; charset=utf-8")
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header(
                            "Cache-Control",
                            "public, max-age=31536000, immutable" if is_asset else "public, max-age=60",
                        )
                        self._security_headers(req_id, latency_ms)
                        self.end_headers()
                        self.wfile.write(data)
                        return
                raise ApiError(404, "not_found", "Resursa nu există.")
            except ApiError as e:
                latency_ms = (time.perf_counter() - t0) * 1000
                if conn:
                    observability.record_request_metric(
                        conn, req_id, method, url.path, e.status, latency_ms, user["id"] if user else None, ip
                    )
                self._send(e.status, e.payload(), req_id=req_id, latency_ms=latency_ms, extra_headers=e.headers)
            except Exception as exc:
                latency_ms = (time.perf_counter() - t0) * 1000
                tb_str = traceback.format_exc()
                if "--quiet" not in sys.argv:
                    traceback.print_exc()
                try:
                    err_conn = conn or db.connect(ctx.db_path)
                    observability.capture_error(
                        err_conn,
                        "backend",
                        str(exc),
                        level="critical",
                        error_code="server_error",
                        stack_trace=tb_str,
                        path=url.path,
                        method=method,
                        user_id=user["id"] if user else None,
                        request_id=req_id,
                    )
                    observability.record_request_metric(
                        err_conn, req_id, method, url.path, 500, latency_ms, user["id"] if user else None, ip
                    )
                    err_conn.commit()
                    if not conn:
                        err_conn.close()
                except Exception:
                    pass
                self._send(
                    500,
                    {"error": {"code": "server_error", "message": "Eroare internă. Încearcă din nou.", "request_id": req_id}},
                    req_id=req_id,
                    latency_ms=latency_ms,
                )
            finally:
                if conn:
                    conn.close()

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def do_PUT(self):
            self._handle("PUT")

        def do_PATCH(self):
            self._handle("PATCH")

        def do_DELETE(self):
            self._handle("DELETE")

    return Handler


def _start_background_scheduler(ctx):
    import threading

    def _worker():
        while True:
            time.sleep(60)
            try:
                conn = db.connect(ctx.db_path)
                try:
                    sms.process_due_reminders(conn, force_all_scheduled=False)
                    observability.prune_old_telemetry(conn)
                finally:
                    conn.close()
            except Exception:
                pass

    t = threading.Thread(target=_worker, daemon=True, name="rezolv_scheduler")
    t.start()


def create_server(host=None, port=None, db_path=None, with_seed=True, bind_socket=True):
    ctx = Context(db_path)
    bootstrap(ctx, with_seed)
    srv = None
    if bind_socket:
        try:
            srv = ThreadingHTTPServer((host or config.HOST, port if port is not None else config.PORT), make_handler(ctx))
            _start_background_scheduler(ctx)
        except (PermissionError, OSError):
            srv = None
    return srv, ctx


def dispatch_test_request(ctx, method: str, path: str, raw: bytes | None = None, headers: dict | None = None):
    """In-process HTTP request dispatcher (identical pipeline to BaseHTTPRequestHandler) for sandboxed tests."""
    import io

    hdrs = {k: v for k, v in (headers or {}).items()}
    if raw is not None and "Content-Length" not in hdrs:
        hdrs["Content-Length"] = str(len(raw))

    HandlerCls = make_handler(ctx)
    h = HandlerCls.__new__(HandlerCls)
    h.client_address = ("127.0.0.1", 55000)
    h.command = method
    h.path = path
    h.headers = hdrs
    h.rfile = io.BytesIO(raw or b"")
    h.wfile = io.BytesIO()
    h._resp_status = 200
    h._resp_headers = {}

    def _send_response(code, message=None):
        h._resp_status = code

    def _send_header(k, v):
        h._resp_headers[k] = v

    def _end_headers():
        pass

    h.send_response = _send_response
    h.send_header = _send_header
    h.end_headers = _end_headers

    if method == "OPTIONS":
        h.do_OPTIONS()
    else:
        h._handle(method)
    body_bytes = h.wfile.getvalue()
    text_body = body_bytes.decode("utf-8") if body_bytes else ""
    ctype = h._resp_headers.get("Content-Type", "")
    if "application/json" in ctype:
        parsed = json.loads(text_body) if text_body else {}
    else:
        parsed = {"raw_text": text_body} if text_body else {}
    return h._resp_status, parsed, h._resp_headers


def main():
    server, _ = create_server()
    host, port = server.server_address
    print(f"REZOLV API listening on http://{host}:{port}  (env={config.ENV}, city={config.PILOT_CITY})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
