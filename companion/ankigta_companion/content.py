"""The read-only card content endpoint.

Card HTML is arbitrary markup, CSS and JavaScript out of the user's own notes.
Prototype 0006 found that stock MTA injects a `window.mta` stub into every
browser context, so the card cannot be promised a bridge-free page. What can be
promised is that the endpoint it talks to is incapable of anything interesting:
it serves bytes for exactly one render and dispatches no control operation.

The contract comes from prototype 0006:

- 256-bit capabilities bound to collection, card, side and generation;
- a 15-second lifetime, revoked by close or by a newer generation;
- per-render budgets on requests, unique bytes, HTML size and media size;
- one uniform denial for every failure, so probing distinguishes nothing.

Deliberately absent: any import of the session or review coordinators, any
connection token, any control path. The negative test in
`tests/test_content_endpoint.py` enforces that absence.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import BoundedSemaphore, Lock, Thread
from time import monotonic

from .collection_identity import AnkiCardIdentity


CAPABILITY_BYTES = 32  # 256 bits
CAPABILITY_LIFETIME_SECONDS = 15.0
MAX_REQUESTS_PER_RENDER = 64
MAX_UNIQUE_BYTES = 32 * 1024 * 1024
MAX_HTML_BYTES = 4 * 1024 * 1024
MAX_MEDIA_BYTES = 16 * 1024 * 1024
MAX_CONCURRENT_REQUESTS = 4

SIDES = frozenset({"question", "answer"})

#: Shown in place of a medium the note refers to but the collection lacks.
MISSING_MEDIA_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
    b'<rect width="64" height="64" fill="#eee"/>'
    b'<text x="32" y="36" font-size="10" text-anchor="middle">?</text>'
    b"</svg>"
)


@dataclass(frozen=True)
class RenderedCard:
    html: str
    media: dict[str, bytes] = field(default_factory=dict)


Renderer = Callable[[AnkiCardIdentity, str], "RenderedCard | None"]


@dataclass(frozen=True)
class RenderCapability:
    token: str
    identity: AnkiCardIdentity
    side: str
    generation: int
    issued_at: float
    lifetime_seconds: float = CAPABILITY_LIFETIME_SECONDS

    @property
    def document_path(self) -> str:
        return f"/render/{self.token}/index.html"

    def media_path(self, name: str) -> str:
        return f"/render/{self.token}/media/{name}"

    def expired(self, now: float) -> bool:
        return now >= self.issued_at + self.lifetime_seconds


@dataclass
class RenderUsage:
    requests: int = 0
    unique_bytes: int = 0
    served: set[str] = field(default_factory=set)


class ContentServer:
    """Serves one render at a time, over loopback, and nothing else."""

    host = "127.0.0.1"

    def __init__(self, render: Renderer, port: int = 0) -> None:
        self._render = render
        self._lock = Lock()
        self._generation = 0
        self._capability: RenderCapability | None = None
        self._card: RenderedCard | None = None
        self._usage = RenderUsage()
        self._capacity = BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
        # Threading, so the concurrency guard below is real rather than
        # decorative: a serialised server could never exceed one in flight.
        self._server = ThreadingHTTPServer((self.host, port), self._handler_type())
        self._server.daemon_threads = True
        self._thread = Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.02),
            name="ankigta-content",
            daemon=True,
        )

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    # ------------------------------------------------------------ capability

    def issue(self, identity: AnkiCardIdentity, side: str) -> RenderCapability:
        """Mint a capability for one render, revoking any previous one."""
        if side not in SIDES:
            raise ValueError(f"unknown card side: {side}")
        card = self._render(identity, side)
        if card is None:
            raise LookupError("card cannot be rendered")
        with self._lock:
            self._generation += 1
            capability = RenderCapability(
                token=secrets.token_urlsafe(CAPABILITY_BYTES),
                identity=identity,
                side=side,
                generation=self._generation,
                issued_at=monotonic(),
            )
            self._capability = capability
            self._card = card
            self._usage = RenderUsage()
        return capability

    def close(self, token: str | None = None) -> None:
        with self._lock:
            if token is not None and (
                self._capability is None or self._capability.token != token
            ):
                return
            self._capability = None
            self._card = None
            self._usage = RenderUsage()

    def expire_now(self, token: str) -> None:
        """Force expiry, so tests need not wait out the lifetime."""
        with self._lock:
            if self._capability is None or self._capability.token != token:
                return
            self._capability = RenderCapability(
                token=self._capability.token,
                identity=self._capability.identity,
                side=self._capability.side,
                generation=self._capability.generation,
                issued_at=monotonic() - CAPABILITY_LIFETIME_SECONDS - 1,
            )

    def usage(self, token: str) -> RenderUsage:
        with self._lock:
            if self._capability is not None and self._capability.token == token:
                return RenderUsage(
                    requests=self._usage.requests,
                    unique_bytes=self._usage.unique_bytes,
                    served=set(self._usage.served),
                )
        return RenderUsage()

    # -------------------------------------------------------------- serving

    def _resolve(self, token: str) -> tuple[RenderCapability, RenderedCard] | None:
        with self._lock:
            capability = self._capability
            card = self._card
            if capability is None or card is None:
                return None
            if capability.token != token or capability.expired(monotonic()):
                return None
            return capability, card

    def _charge(self, key: str, size: int) -> str:
        """Account one request against the render budgets.

        Returns "ok", "requests" or "bytes". An identical retry costs a request
        but not the bytes again, so a client re-fetching the same medium after
        a dropped connection is not punished for it.
        """
        with self._lock:
            if self._usage.requests >= MAX_REQUESTS_PER_RENDER:
                return "requests"
            self._usage.requests += 1
            if key in self._usage.served:
                return "ok"
            if self._usage.unique_bytes + size > MAX_UNIQUE_BYTES:
                return "bytes"
            self._usage.served.add(key)
            self._usage.unique_bytes += size
            return "ok"

    def _handler_type(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                self._serve(with_body=True)

            def do_HEAD(self) -> None:
                self._serve(with_body=False)

            def _reject_method(self) -> None:
                self._send(405, b"", "text/plain")

            do_POST = _reject_method
            do_PUT = _reject_method
            do_DELETE = _reject_method
            do_PATCH = _reject_method
            do_OPTIONS = _reject_method

            def _serve(self, *, with_body: bool) -> None:
                if not server._capacity.acquire(blocking=False):
                    # Bounded backpressure rather than an unbounded queue.
                    self._send(503, b"", "text/plain", extra={"Retry-After": "1"})
                    return
                try:
                    self._dispatch(with_body=with_body)
                finally:
                    server._capacity.release()

            def _dispatch(self, *, with_body: bool) -> None:
                parts = self.path.split("?", 1)[0].strip("/").split("/")
                if len(parts) < 3 or parts[0] != "render":
                    self._deny()
                    return
                token = parts[1]
                resolved = server._resolve(token)
                if resolved is None:
                    self._deny()
                    return
                _capability, card = resolved

                if parts[2] == "index.html" and len(parts) == 3:
                    self._serve_document(card, with_body=with_body)
                    return
                if parts[2] == "media" and len(parts) == 4:
                    self._serve_medium(card, parts[3], with_body=with_body)
                    return
                self._deny()

            def _serve_document(
                self,
                card: RenderedCard,
                *,
                with_body: bool,
            ) -> None:
                body = card.html.encode("utf-8")
                if len(body) > MAX_HTML_BYTES:
                    self._send(413, b"", "text/plain")
                    return
                charged = server._charge("index.html", len(body))
                if charged == "requests":
                    self._send(429, b"", "text/plain")
                    return
                if charged == "bytes":
                    self._send(413, b"", "text/plain")
                    return
                self._send(
                    200,
                    body if with_body else b"",
                    "text/html; charset=utf-8",
                    content_length=len(body),
                )

            def _serve_medium(
                self,
                card: RenderedCard,
                name: str,
                *,
                with_body: bool,
            ) -> None:
                from urllib.parse import unquote

                resolved_name = unquote(name)
                data = card.media.get(resolved_name)
                warning = None
                if data is None:
                    data = MISSING_MEDIA_SVG
                    warning = "missing-media"
                if len(data) > MAX_MEDIA_BYTES:
                    self._send(413, b"", "text/plain")
                    return

                charged = server._charge(f"media/{resolved_name}", len(data))
                if charged == "requests":
                    self._send(429, b"", "text/plain")
                    return
                if charged == "bytes":
                    self._send(413, b"", "text/plain")
                    return

                extra = {"X-ANKIGTA-Warning": warning} if warning else None
                content_type = (
                    "image/svg+xml" if warning else "application/octet-stream"
                )
                span = self._requested_range(len(data))
                if span is None:
                    self._send(
                        200,
                        data if with_body else b"",
                        content_type,
                        content_length=len(data),
                        extra=extra,
                    )
                    return
                start, end = span
                chunk = data[start : end + 1]
                headers = dict(extra or {})
                headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
                self._send(
                    206,
                    chunk if with_body else b"",
                    content_type,
                    content_length=len(chunk),
                    extra=headers,
                )

            def _requested_range(self, size: int) -> tuple[int, int] | None:
                header = self.headers.get("Range")
                if not header or not header.startswith("bytes="):
                    return None
                span = header[len("bytes=") :].split(",")[0].strip()
                start_text, _, end_text = span.partition("-")
                try:
                    start = int(start_text) if start_text else 0
                    end = int(end_text) if end_text else size - 1
                except ValueError:
                    return None
                if start < 0 or end < start or start >= size:
                    return None
                return start, min(end, size - 1)

            def _deny(self) -> None:
                # One shape for every failure: an expired, closed, mistyped,
                # cross-card or cross-side request must be indistinguishable.
                self._send(404, b"", "text/plain")

            def _send(
                self,
                status: int,
                body: bytes,
                content_type: str,
                *,
                content_length: int | None = None,
                extra: dict[str, str] | None = None,
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header(
                    "Content-Length",
                    str(content_length if content_length is not None else len(body)),
                )
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler
