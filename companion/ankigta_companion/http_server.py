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

HEALTH_PATH = "/v1/health"
MAX_CONTROL_BYTES = 2 * 1024 * 1024


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
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length_error = ContractError(
                        "invalid_envelope",
                        "Content-Length must be an integer",
                        None,
                    )
                    self._write_json(400, error_response(length_error))
                    return
                if length < 0:
                    length_error = ContractError(
                        "invalid_envelope",
                        "Content-Length must not be negative",
                        None,
                    )
                    self._write_json(400, error_response(length_error))
                    return
                if length > MAX_CONTROL_BYTES:
                    size_error = ContractError(
                        "request_too_large",
                        "control request exceeds 2 MiB",
                        None,
                    )
                    self._write_json(413, error_response(size_error))
                    return
                try:
                    request = json.loads(self.rfile.read(length))
                except json.JSONDecodeError:
                    json_error = ContractError(
                        "invalid_envelope",
                        "request body must be valid JSON",
                        None,
                    )
                    self._write_json(400, error_response(json_error))
                    return
                try:
                    request_id = validate_request(request)
                except ContractError as error:
                    self._write_json(400, error_response(error))
                    return
                if self.path != HEALTH_PATH:
                    operation_error = ContractError(
                        "operation_not_found",
                        "control operation does not exist",
                        request_id,
                    )
                    self._write_json(404, error_response(operation_error))
                    return
                status, response = health_response(request_id, observe())
                self._write_json(status, response)

            def _write_json(self, status: int, response: object) -> None:
                encoded = json.dumps(response).encode("utf-8")
                if len(encoded) > MAX_CONTROL_BYTES:
                    size_error = ContractError(
                        "response_too_large",
                        "control response exceeds 2 MiB",
                        None,
                    )
                    status = 500
                    encoded = json.dumps(error_response(size_error)).encode("utf-8")
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
