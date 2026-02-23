#!/usr/bin/env python3
"""
FLOW Intelligence - Cost Dashboard Server
Sirve el dashboard HTML y provee API REST para feedback persistente.

Uso:
    python3 server.py              # Inicia en http://localhost:4200
    python3 server.py --port 8080  # Puerto custom
    python3 server.py --scan       # Escanear primero, luego servir
"""

import json
import os
import subprocess
import sys
import webbrowser
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).parent
FEEDBACK_PATH = SCRIPT_DIR / "feedback.json"
HISTORY_PATH = SCRIPT_DIR / "cost_history.json"
AUDIT_HTML = SCRIPT_DIR / "audit.html"
SCAN_SCRIPT = SCRIPT_DIR / "scan.py"

DEFAULT_PORT = 4200


def load_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def record_monthly_snapshot(client_snapshot=None):
    """Save snapshot. Uses client-computed billing data if provided."""
    history = load_json(HISTORY_PATH, {"snapshots": []})

    if client_snapshot and isinstance(client_snapshot, dict) and "total" in client_snapshot:
        snapshot = dict(client_snapshot)
        if "date" not in snapshot:
            snapshot["date"] = datetime.now().strftime("%Y-%m")
        if "timestamp" not in snapshot:
            snapshot["timestamp"] = datetime.now().isoformat()
    else:
        feedback = load_json(FEEDBACK_PATH)
        services = feedback.get("services", {})
        total = 0.0
        by_category = {}
        for svc_id, svc_data in services.items():
            cost = svc_data.get("actual_cost", 0)
            if not isinstance(cost, (int, float)):
                try:
                    cost = float(str(cost).replace("$", "").replace(",", "").strip() or "0")
                except ValueError:
                    cost = 0
            total += cost
            cat = svc_data.get("category", "other")
            by_category[cat] = by_category.get(cat, 0) + cost
        snapshot = {
            "date": datetime.now().strftime("%Y-%m"),
            "timestamp": datetime.now().isoformat(),
            "total": round(total, 2),
            "by_project": {},
            "by_category": {k: round(v, 2) for k, v in by_category.items()},
            "service_count": len(services),
        }

    existing_months = {s["date"] for s in history["snapshots"]}
    if snapshot["date"] in existing_months:
        history["snapshots"] = [s for s in history["snapshots"] if s["date"] != snapshot["date"]]

    history["snapshots"].append(snapshot)
    history["snapshots"].sort(key=lambda s: s["date"])
    save_json(HISTORY_PATH, history)
    return snapshot


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.serve_file(AUDIT_HTML, "text/html")
        elif path == "/api/feedback":
            self.send_json(load_json(FEEDBACK_PATH))
        elif path == "/api/history":
            self.send_json(load_json(HISTORY_PATH, {"snapshots": []}))
        elif path == "/api/scan":
            self.run_scan()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_error_json(400, "Invalid JSON")
            return

        if path == "/api/feedback":
            self.save_feedback(data)
        elif path == "/api/feedback/service":
            self.update_service_feedback(data)
        elif path == "/api/snapshot":
            snapshot = record_monthly_snapshot(data if data else None)
            self.send_json({"ok": True, "snapshot": snapshot})
        else:
            self.send_error_json(404, "Not found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def save_feedback(self, data):
        save_json(FEEDBACK_PATH, data)
        self.send_json({"ok": True})

    def update_service_feedback(self, data):
        svc_id = data.get("service_id")
        if not svc_id:
            self.send_error_json(400, "Missing service_id")
            return

        feedback = load_json(FEEDBACK_PATH)
        if "services" not in feedback:
            feedback["services"] = {}
        if "updated_at" not in feedback:
            feedback["updated_at"] = {}

        if svc_id not in feedback["services"]:
            feedback["services"][svc_id] = {}

        for key in ("actual_cost", "status", "user_notes", "action_taken", "plan", "projects", "category"):
            if key in data:
                feedback["services"][svc_id][key] = data[key]

        feedback["updated_at"][svc_id] = datetime.now().isoformat()
        feedback["last_modified"] = datetime.now().isoformat()

        save_json(FEEDBACK_PATH, feedback)
        self.send_json({"ok": True, "service_id": svc_id})

    def run_scan(self):
        try:
            result = subprocess.run(
                [sys.executable, str(SCAN_SCRIPT)],
                capture_output=True, text=True, timeout=30,
                cwd=str(SCRIPT_DIR),
            )
            self.send_json({
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            })
        except subprocess.TimeoutExpired:
            self.send_error_json(500, "Scan timed out")
        except Exception as e:
            self.send_error_json(500, str(e))

    def serve_file(self, filepath, content_type):
        try:
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", len(content))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404)

    def send_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, code, message):
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            print(f"  API: {args[0]}")


def main():
    port = DEFAULT_PORT
    do_scan = False

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--port" and i < len(sys.argv) - 1:
            port = int(sys.argv[i + 1])
        elif arg == "--scan":
            do_scan = True

    if do_scan:
        print("Ejecutando scan previo...")
        subprocess.run([sys.executable, str(SCAN_SCRIPT)], cwd=str(SCRIPT_DIR))
        print()

    if not AUDIT_HTML.exists():
        print("audit.html no existe. Ejecutando scan...")
        subprocess.run([sys.executable, str(SCAN_SCRIPT)], cwd=str(SCRIPT_DIR))

    if not FEEDBACK_PATH.exists():
        save_json(FEEDBACK_PATH, {"services": {}, "last_modified": datetime.now().isoformat()})

    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    url = f"http://localhost:{port}"
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  FLOW Intelligence - Cost Dashboard          ║")
    print(f"║  {url:<43s} ║")
    print(f"╚══════════════════════════════════════════════╝")
    print(f"\n  API endpoints:")
    print(f"    GET  /api/feedback   - Obtener feedback guardado")
    print(f"    POST /api/feedback/service - Actualizar un servicio")
    print(f"    GET  /api/history    - Historial de costos")
    print(f"    POST /api/snapshot   - Guardar snapshot mensual")
    print(f"    GET  /api/scan       - Re-escanear proyectos")
    print(f"\n  Ctrl+C para detener\n")

    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDetenido.")
        server.server_close()


if __name__ == "__main__":
    main()
