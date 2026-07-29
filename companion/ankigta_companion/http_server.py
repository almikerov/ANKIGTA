from __future__ import annotations

import json
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from .contract import (
    ContractError,
    RuntimeObservation,
    error_response,
    health_response,
    validate_request,
)


class HealthServer:
    host = "127.0.0.1"

    def __init__(self, observe: Callable[[], RuntimeObservation], port: int = 0) -> None:
        self._observe = observe
        self._server = ThreadingHTTPServer(
            (self.host, port),
            self._handler_type(),
        )
        self._thread = Thread(
            target=self._server.serve_forever,
            name="ankigta-health",
            daemon=True,
        )

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def _handler_type(self) -> type[BaseHTTPRequestHandler]:
        observe = self._observe

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    request = json.loads(self.rfile.read(length))
                except json.JSONDecodeError:
                    error = ContractError(
                        "invalid_envelope",
                        "request body must be valid JSON",
                        None,
                    )
                    self._write_json(400, error_response(error))
                    return
                try:
                    request_id = validate_request(request)
                except ContractError as error:
                    self._write_json(400, error_response(error))
                    return
                status, response = health_response(request_id, observe())
                self._write_json(status, response)

            def _write_json(self, status: int, response: object) -> None:
                encoded = json.dumps(response).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def __enter__(self) -> HealthServer:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()
