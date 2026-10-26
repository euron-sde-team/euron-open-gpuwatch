"""Pure ASGI middleware (no BaseHTTPMiddleware: it buffers streams and adds latency)."""

from __future__ import annotations

import json
import logging
import secrets
import time

import orjson
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gpuwatch.core.config import Settings
from gpuwatch.core.logs import request_id_var

log = logging.getLogger("gpuwatch.http")

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]
# Probes, scrapes and agent batches (every few seconds per host) are logged only on failure.
_QUIET = {"/healthz", "/readyz", "/metrics", "/ingest/v1/batches"}


class RequestContextMiddleware:
    """Assigns a request id, adds security headers, logs one line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode()[:64]
        rid = incoming if incoming.replace("-", "").replace("_", "").isalnum() else ""
        rid = rid or secrets.token_hex(8)
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", rid.encode()))
                headers.extend(SECURITY_HEADERS)
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            if path not in _QUIET or status >= 400:
                log.info(
                    "request",
                    extra={
                        "method": scope.get("method"),
                        "path": path,
                        "status": status,
                        "ms": round((time.perf_counter() - started) * 1000, 1),
                    },
                )
            request_id_var.reset(token)


_BODY_METHODS = {"POST", "PUT", "PATCH"}


class BodySizeLimitMiddleware:
    """Refuses request bodies over ``limit`` bytes with 413, whatever their framing, and JSON
    bodies that are not valid UTF-8 text with 422.

    ``Content-Length`` is checked up front; chunked bodies (no length) are counted as they
    arrive and refused the moment they pass the limit, before any route parses them. JSON
    may escape a lone UTF-16 surrogate ("\\ud800"), which the standard parser accepts but no
    database column can store; orjson refuses it, so such a body never reaches a route. The
    accepted body is then replayed to the app unchanged.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return
        limit = self.settings.max_body_bytes
        length = dict(scope.get("headers") or []).get(b"content-length", b"")
        if length.isdigit() and int(length) > limit:
            await self._refuse(send, limit)
            return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > limit:
                await self._refuse(send, limit)
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break
        content_type = dict(scope.get("headers") or []).get(b"content-type", b"")
        if b"json" in content_type and size:
            try:
                orjson.loads(b"".join(chunks))
            except orjson.JSONDecodeError as exc:
                await self._invalid_json(send, str(exc))
                return
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()  # after the body: wait for a disconnect

        await self.app(scope, replay, send)

    async def _invalid_json(self, send: Send, reason: str) -> None:
        body = json.dumps(
            {
                "error": {
                    "code": "invalid_json",
                    "type": "invalid_request_error",
                    "message": "The request body is not valid JSON text (UTF-8, no unpaired "
                    "surrogates)",
                    "details": {"reason": reason[:200]},
                }
            }
        ).encode()
        await self._respond(send, 422, body)

    async def _respond(self, send: Send, status: int, body: bytes) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def _refuse(self, send: Send, limit: int) -> None:
        body = json.dumps(
            {
                "error": {
                    "code": "payload_too_large",
                    "type": "invalid_request_error",
                    "message": f"The request body is larger than {limit:,} bytes. Split "
                    "it into smaller batches, or raise MAX_BODY_BYTES",
                    "details": {"limit_bytes": limit},
                }
            }
        ).encode()
        await self._respond(send, 413, body)
