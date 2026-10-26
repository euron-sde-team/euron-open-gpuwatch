"""A tiny receiver for GPUWatch alert webhooks that verifies the signature.

    GPUWATCH_WEBHOOK_SECRET=... python webhook_receiver.py [--port 8787]

GPUWatch sends X-GPUWatch-Timestamp (Unix seconds) and, when the channel has a secret,
X-GPUWatch-Signature = "sha256=" + hex HMAC-SHA256(secret, "<timestamp>.<raw body>").
This server recomputes it over the raw bytes, compares in constant time, refuses
timestamps more than 5 minutes away (replays), then prints the alert. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_AGE_S = 300


def verify(secret: str, timestamp: str, body: bytes, signature: str) -> str | None:
    """None when the request is authentic and fresh, else the reason it is not."""
    if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > MAX_AGE_S:
        return "timestamp missing or older than 5 minutes"
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    if not hmac.compare_digest(f"sha256={mac.hexdigest()}", signature):
        return "signature does not match"
    return None


class Handler(BaseHTTPRequestHandler):
    secret = ""

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        problem = verify(
            self.secret,
            self.headers.get("X-GPUWatch-Timestamp", ""),
            body,
            self.headers.get("X-GPUWatch-Signature", ""),
        )
        if problem:
            print(f"refused: {problem}")
            self.send_response(401)
            self.end_headers()
            return
        event = json.loads(body)
        print(f"\n{event.get('type')}: {event.get('title')}")
        print(f"  {event.get('message')}")
        for field in ("severity", "value", "started_at", "resolved_at", "dashboard_url"):
            if event.get(field) is not None:
                print(f"  {field}: {event[field]}")
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_: object) -> None:  # keep the output to the alerts
        return


def main() -> None:
    p = argparse.ArgumentParser(description="Verify and print GPUWatch alert webhooks")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--secret", default=os.environ.get("GPUWATCH_WEBHOOK_SECRET"))
    args = p.parse_args()
    if not args.secret:
        p.error("set GPUWATCH_WEBHOOK_SECRET or pass --secret (the channel's signing secret)")
    Handler.secret = args.secret
    print(f"listening on http://0.0.0.0:{args.port}/ (Ctrl+C to stop)")
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()  # noqa: S104


if __name__ == "__main__":
    main()
