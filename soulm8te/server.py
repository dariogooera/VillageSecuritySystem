"""HTTP API server for the companion, exposing it as a backend for the PWA.

Uses only the Python standard library so it runs anywhere with no extra
dependencies. Companion state is isolated per wallet address (or "guest"),
so each Web3 identity owns its own memory and relationship.

Endpoints:
  GET  /                     -> PWA index
  GET  /<static files>       -> frontend assets
  POST /api/chat             {text, wallet?} -> {reply, status, relationship}
  GET  /api/status?wallet=   -> relationship & feeling state
  POST /api/proactive        {wallet?}        -> {message|null}
  GET  /api/offline?wallet=  -> offline readiness report
  GET  /api/self?wallet=     -> last self-improvement patch
"""
from __future__ import annotations

import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from core.conversation import Companion
from core.offline import prepare_offline, offline_ready_report

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")
STATE_ROOT = os.path.join(ROOT, "state")

_lock = threading.Lock()
_companions: dict[str, Companion] = {}


def get_companion(wallet: str | None) -> Companion:
    key = (wallet or "guest").lower()
    with _lock:
        if key not in _companions:
            state_dir = os.path.join(STATE_ROOT, re.sub(r"[^a-z0-9]", "", key) or "guest")
            _companions[key] = Companion(state_dir=state_dir)
        return _companions[key]


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            return self._api_get(path, parse_qs(parsed.query))
        if path in ("/", "/index.html"):
            return self._static("index.html")
        # prevent path traversal
        safe = os.path.normpath(path).lstrip("/")
        return self._static(safe)

    def do_POST(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            return self._send(404, b"not found")
        data = self._read_json()
        wallet = data.get("wallet")
        comp = get_companion(wallet)

        if parsed.path == "/api/chat":
            text = (data.get("text") or "").strip()
            if not text:
                return self._json(400, {"error": "empty text"})
            reply = comp.respond(text)
            return self._json(200, {
                "reply": reply,
                "status": comp.status(),
                "relationship": comp.relationship.stage_label(),
                "intimacy": round(comp.relationship.intimacy, 3),
            })
        if parsed.path == "/api/proactive":
            msg = comp.maybe_proactive()
            return self._json(200, {"message": msg})
        return self._json(404, {"error": "unknown endpoint"})

    def _api_get(self, path: str, qs: dict):
        wallet = (qs.get("wallet") or [None])[0]
        comp = get_companion(wallet)
        if path == "/api/status":
            return self._json(200, {"status": comp.status()})
        if path == "/api/offline":
            out_dir = os.path.join(os.path.dirname(comp.memory.path), "offline")
            snap = prepare_offline(comp.memory, out_dir)
            return self._json(200, {"report": offline_ready_report(snap)})
        if path == "/api/self":
            hist = comp.self_improver.history
            return self._json(200, {"last": hist[-1] if hist else {}})
        return self._json(404, {"error": "unknown endpoint"})

    def _static(self, rel: str):
        full = os.path.join(WEB_DIR, rel)
        if not os.path.isfile(full):
            return self._send(404, b"not found")
        ext = os.path.splitext(full)[1]
        with open(full, "rb") as f:
            body = f.read()
        self._send(200, body, CONTENT_TYPES.get(ext, "application/octet-stream"))

    def log_message(self, fmt, *args):  # quieter logs
        return


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"ULTI companion server running at http://localhost:{port}")
    print("Open the PWA at the root URL. Supports wallet-based identity.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
