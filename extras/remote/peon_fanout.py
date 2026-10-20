#!/usr/bin/env python3
"""Fan Peon relay requests out to every reachable client relay.

peon-remote talks to this on 127.0.0.1:$PEON_FANOUT_PORT (default 19996).
PEON_FANOUT_BACKENDS is a comma-separated host:port list, for example
"127.0.0.1:19998,100.64.0.12:19998": a reverse-tunnelled desktop plus a laptop
relay bound to its private (e.g. Tailscale) address.
"""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import urllib.request

BACKENDS = [b for b in os.environ.get("PEON_FANOUT_BACKENDS", "127.0.0.1:19998").split(",") if b]
PORT = int(os.environ.get("PEON_FANOUT_PORT", "19996"))
FORWARD_HEADERS = ("Content-Type", "X-Volume")
POOL = ThreadPoolExecutor(max_workers=8)


def forward(backend, method, path, headers, body):
    request = urllib.request.Request(f"http://{backend}{path}", data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=0.8) as response:
            return response.status, response.read()
    except Exception:
        return None


class Handler(BaseHTTPRequestHandler):
    def relay(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {name: self.headers[name] for name in FORWARD_HEADERS if self.headers.get(name)}
        results = [r for r in POOL.map(lambda b: forward(b, method, self.path, headers, body), BACKENDS) if r]
        ok = [r for r in results if 200 <= r[0] < 300]
        status, payload = (ok[0] if ok else (results[0] if results else (503, b"no relay reachable\n")))
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.relay("GET")

    def do_POST(self):
        self.relay("POST")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
