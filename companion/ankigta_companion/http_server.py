from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from socket import socket
from threading import BoundedSemaphore, Thread

from .contract import (
    ContractError,
    RuntimeObservation,
    error_response,
    health_response,
    identity_response,
    validate_collection_uuid,
    validate_copy_decision,
    validate_request,
)
from .collection_identity import (
    CollectionCopyDecision,
    CollectionIdentityCommand,
    CollectionIdentityObservation,
)

HEALTH_PATH = "/v1/health"
MAX_CONTROL_BYTES = 2 * 1024 * 1024
MAX_READ_WORKERS = 4
MAX_PENDING_READS = 4
MAX_IN_FLIGHT_READS = MAX_READ_WORKERS + MAX_PENDING_READS
LISTEN_BACKLOG = MAX_IN_FLIGHT_READS
BIND_COLLECTION_PATH = "/v1/collection/bind"
COPY_DECISION_PATH = "/v1/collection/copy-decision"

ServerRequest = socket | tuple[bytes, socket]
IdentityCommand = Callable[
    [CollectionIdentityCommand, str, CollectionCopyDecision | None],
    CollectionIdentityObservation,
]


class BoundedHTTPServer(HTTPServer):
    request_queue_size = LISTEN_BACKLOG

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_type: type[BaseHTTPRequestHandler],
    ) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=MAX_READ_WORKERS,
            thread_name_prefix="ankigta-health-worker",
        )
        self._capacity = BoundedSemaphore(MAX_IN_FLIGHT_READS)
        super().__init__(server_address, handler_type)

    def process_request(
        self,
        request: ServerRequest,
        client_address: tuple[str, int],
    ) -> None:
        self._capacity.acquire()
        try:
            self._executor.submit(
                self._finish_bounded_request,
                request,
                client_address,
            )
        except BaseException:
            self._capacity.release()
            self.shutdown_request(request)
            raise

    def _finish_bounded_request(
        self,
        request: ServerRequest,
        client_address: tuple[str, int],
    ) -> None:
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)
            self._capacity.release()

    def server_close(self) -> None:
        super().server_close()
        self._executor.shutdown(wait=True, cancel_futures=True)


class HealthServer:
    host = "127.0.0.1"

    def __init__(
        self,
        observe: Callable[[], RuntimeObservation],
        port: int = 0,
        *,
        identity_command: IdentityCommand | None = None,
    ) -> None:
        self._observe = observe
        self._identity_command = identity_command
        self._server = BoundedHTTPServer(
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
        identity_command = self._identity_command

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
                if self.path == HEALTH_PATH:
                    status, response = health_response(request_id, observe())
                    self._write_json(status, response)
                    return
                if self.path not in {BIND_COLLECTION_PATH, COPY_DECISION_PATH}:
                    operation_error = ContractError(
                        "operation_not_found",
                        "control operation does not exist",
                        request_id,
                    )
                    self._write_json(404, error_response(operation_error))
                    return
                if identity_command is None:
                    unavailable_error = ContractError(
                        "operation_not_found",
                        "control operation does not exist",
                        request_id,
                    )
                    self._write_json(404, error_response(unavailable_error))
                    return
                try:
                    collection_uuid = validate_collection_uuid(request, request_id)
                    decision = (
                        validate_copy_decision(request, request_id)
                        if self.path == COPY_DECISION_PATH
                        else None
                    )
                except ContractError as error:
                    self._write_json(400, error_response(error))
                    return
                command = (
                    CollectionIdentityCommand.BIND
                    if self.path == BIND_COLLECTION_PATH
                    else CollectionIdentityCommand.COPY_DECISION
                )
                identity = identity_command(command, collection_uuid, decision)
                response = identity_response(request_id, identity)
                self._write_json(200 if response["ok"] else 409, response)

            def _write_json(self, status: int, response: object) -> None:
                encoded = json.dumps(response).encode("utf-8")
                if len(encoded) > MAX_CONTROL_BYTES:
                    request_id = (
                        response.get("requestId")
                        if isinstance(response, dict)
                        and isinstance(response.get("requestId"), str)
                        else None
                    )
                    size_error = ContractError(
                        "response_too_large",
                        "control response exceeds 2 MiB",
                        request_id,
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
