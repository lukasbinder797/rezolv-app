#!/usr/bin/env python3
"""Uptime & Performance Monitor for REZOLV Sibiu MVP.
Checks /api/health, /api/health/live, /api/health/ready, and /robots.txt,
verifying response status == 200, DB connectivity, and latency < 500ms.
"""
import argparse
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from rezolv import server  # noqa: E402


def run_check(live_url: str | None = None) -> dict:
    endpoints = ["/api/health", "/api/health/live", "/api/health/ready", "/robots.txt", "/sitemap.xml"]
    results = []
    all_ok = True

    if live_url:
        import urllib.request
        base = live_url.rstrip("/")
        for ep in endpoints:
            t0 = time.perf_counter()
            try:
                req = urllib.request.Request(f"{base}{ep}")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    status = resp.status
                ms = round((time.perf_counter() - t0) * 1000, 2)
                ok = status == 200 and ms < 500.0
            except Exception as e:
                ms = round((time.perf_counter() - t0) * 1000, 2)
                status = getattr(e, "code", 500)
                ok = False
            if not ok:
                all_ok = False
            results.append({"endpoint": ep, "status": status, "latency_ms": ms, "ok": ok})
        return {"all_ok": all_ok, "checked_at": int(time.time()), "mode": "live_http", "probes": results}

    db_path = os.path.join(tempfile.mkdtemp(), "uptime_check.db")
    _, ctx = server.create_server("127.0.0.1", 0, db_path, bind_socket=False)
    for ep in endpoints:
        t0 = time.perf_counter()
        status, body, hdrs = server.dispatch_test_request(ctx, "GET", ep)
        ms = round((time.perf_counter() - t0) * 1000, 2)
        ok = status == 200 and ms < 500.0
        if not ok:
            all_ok = False
        results.append({"endpoint": ep, "status": status, "latency_ms": ms, "ok": ok})
    return {"all_ok": all_ok, "checked_at": int(time.time()), "mode": "in_process", "probes": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run a single uptime probe check")
    parser.add_argument("--url", type=str, default=None, help="Base URL of live server to probe over HTTP")
    args = parser.parse_args()
    report = run_check(live_url=args.url)
    print(json.dumps(report, indent=2))
    if not report["all_ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
