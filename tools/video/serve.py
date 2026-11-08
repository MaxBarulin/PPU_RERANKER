"""Статика сцены + /api/info для настоящей страницы сервиса внутри ролика."""
import json, sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
INFO = {"index": True, "records": 11000, "built": "2026-11-08T09:00:00", "llm": True, "llm_local": True,
        "llm_host": "127.0.0.1", "rebuild": "idle"}
class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/api/info"):
            b = json.dumps(INFO).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if self.path == "/logo.png": self.path = "/logo.png"
        return super().do_GET()
ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), partial(H, directory=sys.argv[2])).serve_forever()
