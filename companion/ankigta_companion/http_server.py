from __future__ import annotations

import json
from hmac import compare_digest
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from socket import socket
from threading import BoundedSemaphore, Thread

from .contract import (
    ContractError,
    RuntimeObservation,
    error_response,
    card_read_response,
    card_search_response,
    health_response,
    session_response,
    validate_request,
)
from .cards import CardPickerError, CardPickerService
from .collection_identity import AnkiCardIdentity
from .session import SessionCoordinator, SessionError

HEALTH_PATH = "/v1/health"
CARD_SEARCH_PATH = "/v1/cards/search"
CARD_READ_PATH = "/v1/cards/read"
SESSION_START_PATH = "/v1/session/start"
SESSION_REBUILD_PATH = "/v1/session/rebuild"
SESSION_PAUSE_PATH = "/v1/session/pause"
SESSION_STOP_PATH = "/v1/session/stop"
SESSION_CANCEL_PATH = "/v1/session/cancel"
SESSION_ADMIT_PATH = "/v1/session/admit"
SESSION_RESTORE_PATH = "/v1/session/restore"
MAX_CONTROL_BYTES = 2 * 1024 * 1024
MAX_READ_WORKERS = 4
MAX_PENDING_READS = 4
MAX_IN_FLIGHT_READS = MAX_READ_WORKERS + MAX_PENDING_READS
LISTEN_BACKLOG = MAX_IN_FLIGHT_READS

ServerRequest = socket | tuple[bytes, socket]


def _parse_identities(request: object) -> list[AnkiCardIdentity]:
    if not isinstance(request, dict):
        raise SessionError("invalid_session_request", "request body must be an object")
    raw_identities = request.get("cardIdentities")
    if not isinstance(raw_identities, list):
        raise SessionError(
            "invalid_session_request",
            "cardIdentities must be an array",
        )
    identities: list[AnkiCardIdentity] = []
    for raw in raw_identities:
        if not isinstance(raw, dict):
            raise SessionError(
                "invalid_session_request",
                "cardIdentities entries must be objects",
            )
        collection_uuid = raw.get("collectionUuid")
        card_id = raw.get("cardId")
        if (
            not isinstance(collection_uuid, str)
            or not collection_uuid
            or not isinstance(card_id, int)
            or isinstance(card_id, bool)
            or card_id <= 0
        ):
            raise SessionError(
                "invalid_session_request",
                "cardIdentities entries must contain collectionUuid and positive cardId",
            )
        identities.append(AnkiCardIdentity(collection_uuid, card_id))
    return identities


def _parse_identity(request: object) -> AnkiCardIdentity:
    """Read the single `cardIdentity` an admission request targets."""
    if not isinstance(request, dict):
        raise SessionError("invalid_session_request", "request body must be an object")
    raw = request.get("cardIdentity")
    if not isinstance(raw, dict):
        raise SessionError(
            "invalid_session_request",
            "cardIdentity must be an object",
        )
    collection_uuid = raw.get("collectionUuid")
    card_id = raw.get("cardId")
    if (
        not isinstance(collection_uuid, str)
        or not collection_uuid
        or not isinstance(card_id, int)
        or isinstance(card_id, bool)
        or card_id <= 0
    ):
        raise SessionError(
            "invalid_session_request",
            "cardIdentity must contain collectionUuid and positive cardId",
        )
    return AnkiCardIdentity(collection_uuid, card_id)


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
        token: str | None = None,
        card_picker: CardPickerService | None = None,
        session_coordinator: SessionCoordinator | None = None,
    ) -> None:
        self._observe = observe
        self._token = token or None
        self._card_picker = card_picker
        self._session = session_coordinator
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
        token = self._token
        card_picker = self._card_picker
        session = self._session

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
                if token is not None:
                    expected = f"Bearer {token}"
                    provided = self.headers.get("Authorization", "")
                    if not compare_digest(provided, expected):
                        authorization_error = ContractError(
                            "authorization_failure",
                            "connection token was rejected",
                            request_id,
                        )
                        self._write_json(
                            401,
                            error_response(authorization_error),
                        )
                        return
                if self.path == HEALTH_PATH:
                    study = session.status().payload() if session is not None else None
                    if study is not None:
                        study["ratingEnabled"] = False
                        study["reviewModeOpened"] = False
                    status, response = health_response(
                        request_id,
                        observe(),
                        study,
                    )
                    self._write_json(status, response)
                    return
                if self.path in {CARD_SEARCH_PATH, CARD_READ_PATH}:
                    if card_picker is None:
                        unavailable = ContractError(
                            "card_picker_unavailable",
                            "Card Picker is unavailable",
                            request_id,
                        )
                        self._write_json(503, error_response(unavailable))
                        return
                    try:
                        if self.path == CARD_SEARCH_PATH:
                            raw_query = request.get("query", "")
                            raw_deck_filter = request.get("deckFilter")
                            raw_page = request.get("page", 0)
                            raw_page_size = request.get("pageSize", 50)
                            if not isinstance(raw_query, str):
                                raise CardPickerError(
                                    "invalid_query",
                                    "query must be a string",
                                )
                            if raw_deck_filter is False:
                                raw_deck_filter = None
                            if raw_deck_filter is not None and not isinstance(
                                raw_deck_filter, str
                            ):
                                raise CardPickerError(
                                    "invalid_deck_filter",
                                    "deckFilter must be a string",
                                )
                            if (
                                not isinstance(raw_page, int)
                                or isinstance(raw_page, bool)
                            ):
                                raise CardPickerError(
                                    "invalid_pagination",
                                    "page must be an integer",
                                )
                            if (
                                not isinstance(raw_page_size, int)
                                or isinstance(raw_page_size, bool)
                            ):
                                raise CardPickerError(
                                    "invalid_pagination",
                                    "pageSize must be an integer",
                                )
                            query = raw_query
                            deck_filter = raw_deck_filter
                            page = raw_page
                            page_size = raw_page_size
                            search_page = card_picker.search(
                                query=query,
                                deck_filter=deck_filter,
                                page=page,
                                page_size=page_size,
                            )
                            status, response = card_search_response(
                                request_id,
                                search_page,
                            )
                        else:
                            raw_card_id = request.get("cardId")
                            raw_collection_uuid = request.get("collectionUuid")
                            if raw_collection_uuid is not None:
                                if not isinstance(raw_collection_uuid, str):
                                    raise CardPickerError(
                                        "invalid_anki_card_identity",
                                        "collectionUuid must be a string",
                                    )
                                card = card_picker.read_identity(
                                    AnkiCardIdentity(
                                        raw_collection_uuid,
                                        raw_card_id
                                        if isinstance(raw_card_id, int)
                                        and not isinstance(raw_card_id, bool)
                                        else 0,
                                    )
                                )
                            else:
                                card = card_picker.read(
                                    raw_card_id
                                    if isinstance(raw_card_id, int)
                                    and not isinstance(raw_card_id, bool)
                                    else 0
                                )
                            status, response = card_read_response(
                                request_id,
                                card,
                            )
                    except CardPickerError as error:
                        category_status = {
                            "invalid_card_id": 400,
                            "invalid_pagination": 400,
                            "invalid_query": 400,
                            "invalid_deck_filter": 400,
                            "collection_not_bound": 409,
                            "collection_unavailable": 503,
                            "card_missing": 404,
                            "wrong_collection": 409,
                            "invalid_anki_card_identity": 400,
                        }.get(error.category, 409)
                        self._write_json(
                            category_status,
                            error_response(
                                ContractError(
                                    error.category,
                                    error.message,
                                    request_id,
                                )
                            ),
                        )
                        return
                    self._write_json(status, response)
                    return
                if self.path in {
                    SESSION_START_PATH,
                    SESSION_REBUILD_PATH,
                    SESSION_PAUSE_PATH,
                    SESSION_STOP_PATH,
                    SESSION_CANCEL_PATH,
                    SESSION_ADMIT_PATH,
                    SESSION_RESTORE_PATH,
                }:
                    if session is None:
                        unavailable = ContractError(
                            "session_unavailable",
                            "ANKIGTA Session is unavailable",
                            request_id,
                        )
                        self._write_json(503, error_response(unavailable))
                        return
                    try:
                        if self.path in {
                            SESSION_START_PATH,
                            SESSION_REBUILD_PATH,
                        }:
                            identities = _parse_identities(request)
                            allow_early = request.get("allowEarlyReview", False)
                            if not isinstance(allow_early, bool):
                                raise SessionError(
                                    "invalid_session_request",
                                    "allowEarlyReview must be a boolean",
                                )
                            session_result = (
                                session.start
                                if self.path == SESSION_START_PATH
                                else session.rebuild
                            )(
                                identities,
                                allow_early_review=allow_early,
                            )
                            study_payload = session.status().payload()
                            study_payload["ratingEnabled"] = False
                            study_payload["reviewModeOpened"] = False
                            status, response = session_response(
                                request_id,
                                {
                                    "session": study_payload,
                                    "cardIds": list(session_result.card_ids),
                                    "skipped": [
                                        {
                                            "collectionUuid": item.collection_uuid,
                                            "cardId": item.card_id,
                                        }
                                        for item in session_result.skipped
                                    ],
                                },
                            )
                        elif self.path == SESSION_ADMIT_PATH:
                            allow_early = request.get("allowEarlyReview", False)
                            if not isinstance(allow_early, bool):
                                raise SessionError(
                                    "invalid_session_request",
                                    "allowEarlyReview must be a boolean",
                                )
                            admission = session.admit(
                                _parse_identity(request),
                                allow_early_review=allow_early,
                            )
                            study_payload = session.status().payload()
                            # Rating is authorized by admission alone; a
                            # Preview-only card must never look ratable.
                            study_payload["ratingEnabled"] = admission.admitted
                            study_payload["reviewModeOpened"] = False
                            status, response = session_response(
                                request_id,
                                {
                                    "session": study_payload,
                                    "admission": {
                                        "collectionUuid": (
                                            admission.identity.collection_uuid
                                        ),
                                        "cardId": admission.identity.card_id,
                                        "admitted": admission.admitted,
                                        "previewOnly": admission.preview_only,
                                        "reason": admission.reason,
                                    },
                                },
                            )
                        elif self.path == SESSION_RESTORE_PATH:
                            restored = session.restore()
                            study_payload = session.status().payload()
                            study_payload["ratingEnabled"] = False
                            study_payload["reviewModeOpened"] = False
                            status, response = session_response(
                                request_id,
                                {
                                    "session": study_payload,
                                    "restored": restored,
                                },
                            )
                        elif self.path == SESSION_CANCEL_PATH:
                            cancelled = session.cancel_rebuild()
                            if not cancelled:
                                raise SessionError(
                                    "session_not_rebuilding",
                                    "ANKIGTA Session is not rebuilding",
                                )
                            study_payload = session.status().payload()
                            study_payload["ratingEnabled"] = False
                            study_payload["reviewModeOpened"] = False
                            status, response = session_response(
                                request_id,
                                {"session": study_payload, "cancelled": True},
                            )
                        else:
                            cleanup_result = (
                                session.pause()
                                if self.path == SESSION_PAUSE_PATH
                                else session.stop()
                            )
                            study_payload = session.status().payload()
                            study_payload["ratingEnabled"] = False
                            study_payload["reviewModeOpened"] = False
                            status, response = session_response(
                                request_id,
                                {
                                    "session": study_payload,
                                    "cleaned": cleanup_result.cleaned,
                                },
                            )
                    except SessionError as error:
                        category_status = {
                            "invalid_session_request": 400,
                            "collection_unavailable": 503,
                            "collection_not_bound": 409,
                            "compatibility_failure": 409,
                            "deck_name_collision": 409,
                            "reviewer_active": 409,
                            "outcome_unknown": 409,
                            "session_inactive": 409,
                            "rebuild_timeout": 408,
                            "rebuild_cancelled": 409,
                            "session_not_rebuilding": 409,
                            "wrong_collection": 409,
                            "card_missing": 404,
                            "card_unavailable": 409,
                            "early_review_disabled": 409,
                            "admission_open": 409,
                        }.get(error.category, 409)
                        self._write_json(
                            category_status,
                            error_response(
                                ContractError(
                                    error.category,
                                    error.message,
                                    request_id,
                                )
                            ),
                        )
                        return
                    self._write_json(status, response)
                    return
                operation_error = ContractError(
                    "operation_not_found",
                    "control operation does not exist",
                    request_id,
                )
                self._write_json(404, error_response(operation_error))

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
