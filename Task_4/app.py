"""
app.py - Standalone Python Web Server & REST API for Task 4: Mini AI Agent Development.
Serves the interactive Web UI (`index.html`) and exposes REST endpoints:
  - GET  /               -> Interactive Support Ticket Triage Agent Web UI
  - POST /api/triage     -> Runs SupportTicketTriageAgent.triage_ticket()
  - GET  /api/tickets    -> Lists all stored tickets from TicketStore (High->Medium->Low)
  - POST /api/resolve    -> Marks a ticket as Resolved (Requirement 3)
  - GET  /api/stats      -> Returns live metrics (done, pending, resolved, high, med, low)
  - POST /api/clear      -> Clears stored tickets
  - GET  /api/policies   -> Returns predefined SUPPORT_POLICIES
  - GET  /api/samples    -> Returns sample_tickets.json
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from agent import SupportTicketTriageAgent
from tools import SUPPORT_POLICIES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT = SupportTicketTriageAgent()


class TriageRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            index_path = os.path.join(BASE_DIR, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self._send_json(404, {"error": "index.html not found"})
        elif parsed.path == "/api/tickets":
            self._send_json(200, {"tickets": AGENT.store.list_tickets()})
        elif parsed.path == "/api/stats":
            self._send_json(200, AGENT.store.get_stats())
        elif parsed.path == "/api/policies":
            self._send_json(200, {"policies": SUPPORT_POLICIES})
        elif parsed.path == "/api/samples":
            sample_path = os.path.join(BASE_DIR, "sample_tickets.json")
            with open(sample_path, "r", encoding="utf-8") as f:
                samples = json.load(f)
            self._send_json(200, {"samples": samples})
        else:
            self._send_json(404, {"error": f"Unknown endpoint: {parsed.path}"})

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON request body"})
            return

        if parsed.path == "/api/triage":
            # Dynamically update LLM config if provided in request
            api_key_override = data.get("api_key") or data.get("xkiro_api_key")
            model_override = data.get("model") or data.get("xkiro_model")
            base_url_override = data.get("base_url") or data.get("xkiro_base_url")

            if api_key_override:
                AGENT.api_key = api_key_override.strip()
            if model_override:
                AGENT.model = model_override.strip()
            if base_url_override:
                AGENT.base_url = base_url_override.strip()

            result = AGENT.triage_ticket(
                request_text=data.get("request_text", ""),
                customer_id=data.get("customer_id", "CUST-1042"),
                created_at=data.get("created_at"),
                simulate_malformed_llm=bool(data.get("simulate_malformed_llm", False)),
                simulate_policy_tool_failure=bool(data.get("simulate_policy_tool_failure", False)),
                simulate_storage_tool_failure=bool(data.get("simulate_storage_tool_failure", False)),
            )
            self._send_json(200, result)
        elif parsed.path == "/api/resolve":
            ticket_id = data.get("ticket_id")
            if not ticket_id:
                self._send_json(400, {"error": "ticket_id is required"})
                return
            updated = AGENT.store.resolve_ticket(ticket_id)
            if updated:
                self._send_json(200, {"status": "resolved", "ticket": updated, "stats": AGENT.store.get_stats()})
            else:
                self._send_json(404, {"error": f"Ticket {ticket_id} not found"})
        elif parsed.path == "/api/clear":
            AGENT.store.clear()
            self._send_json(200, {"status": "cleared", "stats": AGENT.store.get_stats()})
        else:
            self._send_json(404, {"error": f"Unknown POST endpoint: {parsed.path}"})


def run_server(port: int = 8000):
    server = HTTPServer(("0.0.0.0", port), TriageRequestHandler)
    print(f"🚀 AI Support Ticket Triage Agent Server running at http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    run_server()