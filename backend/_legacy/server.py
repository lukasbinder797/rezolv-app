#!/usr/bin/env python3
import http.server
import socketserver
import json
import urllib.parse
import os
import sys

from database import (
    init_db,
    list_professionals,
    create_booking,
    update_booking_status,
    add_review,
    verify_cui,
    get_connection
)

PORT = 8000

class RezolvAPIHandler(http.server.SimpleHTTPRequestHandler):
    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Health check
        if path == "/api/health":
            self.send_json({"status": "healthy", "service": "Rezolv API", "city": "Sibiu"})
            return

        # 2. List Professionals
        if path == "/api/professionals":
            q = query.get('q', [None])[0]
            cat = query.get('category', [None])[0]
            pros = list_professionals(query=q, category=cat)
            self.send_json(pros)
            return

        # 3. Get Single Professional
        if path.startswith("/api/professionals/"):
            pro_id = path.replace("/api/professionals/", "")
            pros = list_professionals()
            found = next((p for p in pros if p['id'] == pro_id), None)
            if found:
                self.send_json(found)
            else:
                self.send_json({"error": "Professional not found"}, 404)
            return

        # 4. Get Bookings
        if path == "/api/bookings":
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bookings ORDER BY created_at DESC")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            self.send_json(rows)
            return

        # 5. Get User Profile
        if path == "/api/user/profile":
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM profiles WHERE id = 'usr-client-1'")
            row = cursor.fetchone()
            conn.close()
            if row:
                self.send_json(dict(row))
            else:
                self.send_json({"error": "Profile not found"}, 404)
            return

        # Fallback to static files in workspace
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(body) if body else {}

        # 1. Create Booking
        if path == "/api/bookings":
            res = create_booking(data)
            self.send_json(res, 201)
            return

        # 2. Add Review
        if path == "/api/reviews":
            res = add_review(data)
            self.send_json(res, 201)
            return

        # 3. Verify CUI
        if path == "/api/cui/verify":
            cui = data.get('cui', '')
            res = verify_cui(cui)
            self.send_json(res)
            return

        # 4. Update Availability
        if path.startswith("/api/professionals/") and path.endswith("/availability"):
            pro_id = path.split("/")[3]
            is_avail = 1 if data.get('is_available', True) else 0
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE professionals SET is_available = ? WHERE id = ?", (is_avail, pro_id))
            conn.commit()
            conn.close()
            self.send_json({"id": pro_id, "is_available": bool(is_avail)})
            return

        # 5. Update Profile
        if path == "/api/user/profile":
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE profiles SET name = ?, phone = ?, email = ?, address = ?, avatar = ?
            WHERE id = 'usr-client-1'
            """, (
                data.get('name', 'Alexandru Popa'),
                data.get('phone', '0745 123 456'),
                data.get('email', 'alexandru.popa@email.ro'),
                data.get('address', 'Str. Mitropoliei 14, Ap. 3'),
                data.get('avatar', '')
            ))
            conn.commit()
            conn.close()
            self.send_json({"status": "updated"})
            return

        self.send_json({"error": "Endpoint not found"}, 404)

    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(body) if body else {}

        if path.startswith("/api/bookings/") and path.endswith("/status"):
            booking_id = path.split("/")[3]
            new_status = data.get('status', 'confirmed')
            res = update_booking_status(booking_id, new_status)
            self.send_json(res)
            return

        self.send_json({"error": "Endpoint not found"}, 404)

def run_server():
    init_db()
    with socketserver.TCPServer(("", PORT), RezolvAPIHandler) as httpd:
        print(f"🚀 Rezolv Backend Server running on http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer shutting down.")

if __name__ == "__main__":
    run_server()
