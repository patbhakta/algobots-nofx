"""Opt-in real-browser regression against an isolated migrated API database.

NOFX_WEB_DIST and NOFX_BROWSER_RUNNER point to a built frontend and a Node
Playwright script. No production user, invite, or credentials are needed.
"""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest


@pytest.mark.skipif(not os.getenv("NOFX_BROWSER_RUNNER"), reason="opt-in browser regression")
def test_browser_strategy_roundtrip(client, founder):
    root = Path(os.environ["NOFX_WEB_DIST"])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def do_PUT(self):
            self.respond()

        def respond(self):
            if self.path.startswith("/api/"):
                path = self.path
                if not path.startswith("/api/nofx/"):
                    path = path.replace("/api/", "/api/nofx/", 1)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                response = client.request(
                    self.command, path, content=body, headers=dict(self.headers)
                )
                self.send_response(response.status_code)
                self.send_header(
                    "Content-Type", response.headers.get("content-type", "application/json")
                )
                self.end_headers()
                self.wfile.write(response.content)
                return
            path = root / self.path.split("?")[0].lstrip("/")
            if not path.is_file():
                path = root / "index.html"
            self.send_response(200)
            self.send_header(
                "Content-Type",
                {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}.get(
                    path.suffix, "text/html"
                ),
            )
            self.end_headers()
            self.wfile.write(path.read_bytes())

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            ["node", os.environ["NOFX_BROWSER_RUNNER"]],
            input=json.dumps(
                {"url": f"http://127.0.0.1:{server.server_port}", "email": founder["email"]}
            ),
            text=True,
            capture_output=True,
            timeout=90,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
