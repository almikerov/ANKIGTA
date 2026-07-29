from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from threading import Event, Lock

import pytest

from ankigta_companion.contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)
from ankigta_companion.http_server import HealthServer


def post_health(server: HealthServer, body: object) -> tuple[int, dict[str, object]]:
    return post_raw_health(server, json.dumps(body).encode("utf-8"))


def post_raw_health(
    server: HealthServer,
    body: bytes,
    path: str = "/v1/health",
    timeout: float = 2,
) -> tuple[int, dict[str, object]]:
    connection = HTTPConnection(server.host, server.port, timeout=timeout)
    connection.request(
        "POST",
        path,
        body=body,
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    payload = json.loads(response.read())
    connection.close()
    return response.status, payload


def test_supported_open_collection_is_observable_without_enabling_study() -> None:
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(
            state=CollectionState.OPEN,
            profile_name="Test Profile",
        ),
    )

    with HealthServer(lambda: observation) as server:
        status, response = post_health(
            server,
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": "health-001",
            },
        )

    assert status == 200
    assert response == {
        "protocol": "ankigta-control",
        "protocolVersion": 1,
        "requestId": "health-001",
        "ok": True,
        "error": None,
        "payload": {
            "anki": {
                "version": "26.05",
                "v3Scheduler": True,
                "fsrsEnabled": True,
            },
            "collection": {
                "state": "open",
                "profileName": "Test Profile",
            },
            "compatibility": {
                "status": "supported",
                "previewReadOnlyCompatible": True,
                "sessionCompatible": True,
                "ratingCompatible": True,
            },
            "study": {
                "sessionActive": False,
                "ratingEnabled": False,
            },
        },
    }


def test_protected_listener_checks_token_before_health_dispatch() -> None:
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )
    observe_calls = 0

    def observe() -> RuntimeObservation:
        nonlocal observe_calls
        observe_calls += 1
        return observation

    with HealthServer(observe, token="correct-secret") as server:
        connection = HTTPConnection(server.host, server.port, timeout=2)
        body = json.dumps(
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": "protected-health",
            }
        )
        connection.request(
            "POST",
            "/v1/health",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer wrong-secret",
            },
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()

    assert response.status == 401
    assert payload["requestId"] == "protected-health"
    assert payload["error"] == {
        "category": "authorization_failure",
        "message": "connection token was rejected",
    }
    assert "correct-secret" not in json.dumps(payload)
    assert observe_calls == 0


def test_explicit_empty_token_allows_health_in_unprotected_mode() -> None:
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )

    with HealthServer(lambda: observation, token="") as server:
        status, response = post_health(
            server,
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": "unprotected-health",
            },
        )

    assert status == 200
    assert response["ok"] is True


@pytest.mark.parametrize(
    ("request_body", "category"),
    [
        (
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
            },
            "invalid_request_id",
        ),
        (
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": 42,
            },
            "invalid_request_id",
        ),
        (
            {
                "protocol": "different-control",
                "protocolVersion": 1,
                "requestId": "health-002",
            },
            "protocol_mismatch",
        ),
        (
            {
                "protocol": "ankigta-control",
                "protocolVersion": 2,
                "requestId": "health-003",
            },
            "protocol_mismatch",
        ),
    ],
)
def test_invalid_request_envelope_returns_a_stable_error(
    request_body: dict[str, object],
    category: str,
) -> None:
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.ABSENT),
    )

    with HealthServer(lambda: observation) as server:
        status, response = post_health(server, request_body)

    expected_request_id = request_body.get("requestId")
    if not isinstance(expected_request_id, str):
        expected_request_id = None
    assert status == 400
    assert response == {
        "protocol": "ankigta-control",
        "protocolVersion": 1,
        "requestId": expected_request_id,
        "ok": False,
        "error": {
            "category": category,
            "message": (
                "requestId must be a non-empty string"
                if category == "invalid_request_id"
                else "unsupported protocol identity or version"
            ),
        },
        "payload": None,
    }


def test_malformed_json_returns_a_versioned_error_envelope() -> None:
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.ABSENT),
    )

    with HealthServer(lambda: observation) as server:
        status, response = post_raw_health(server, b'{"requestId":')

    assert status == 400
    assert response == {
        "protocol": "ankigta-control",
        "protocolVersion": 1,
        "requestId": None,
        "ok": False,
        "error": {
            "category": "invalid_envelope",
            "message": "request body must be valid JSON",
        },
        "payload": None,
    }


def test_only_the_health_operation_path_is_exposed() -> None:
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )
    request = json.dumps(
        {
            "protocol": "ankigta-control",
            "protocolVersion": 1,
            "requestId": "wrong-path",
        }
    ).encode("utf-8")

    with HealthServer(lambda: observation) as server:
        status, response = post_raw_health(server, request, path="/v1/rating")

    assert status == 404
    assert response == {
        "protocol": "ankigta-control",
        "protocolVersion": 1,
        "requestId": "wrong-path",
        "ok": False,
        "error": {
            "category": "operation_not_found",
            "message": "control operation does not exist",
        },
        "payload": None,
    }


def test_identity_mutations_are_not_exposed_before_the_token_gate() -> None:
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )

    collection_uuid = "d384e4c5-a509-43a8-b801-e50bff4f90e8"
    with HealthServer(lambda: observation) as server:
        status, response = post_raw_health(
            server,
            json.dumps(
                {
                    "protocol": "ankigta-control",
                    "protocolVersion": 1,
                    "requestId": "bind-001",
                    "collectionUuid": collection_uuid,
                }
            ).encode("utf-8"),
            path="/v1/collection/bind",
        )

    assert status == 404
    assert response["error"]["category"] == "operation_not_found"


def test_control_request_larger_than_two_mib_is_rejected() -> None:
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )

    with HealthServer(lambda: observation) as server:
        status, response = post_raw_health(
            server,
            b"{" + (b" " * (2 * 1024 * 1024)),
        )

    assert status == 413
    assert response["error"] == {
        "category": "request_too_large",
        "message": "control request exceeds 2 MiB",
    }


def test_control_response_larger_than_two_mib_is_replaced_by_an_error() -> None:
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(
            state=CollectionState.OPEN,
            profile_name="x" * (2 * 1024 * 1024),
        ),
    )

    with HealthServer(lambda: observation) as server:
        status, response = post_health(
            server,
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": "large-response",
            },
        )

    assert status == 500
    assert response["requestId"] == "large-response"
    assert response["error"] == {
        "category": "response_too_large",
        "message": "control response exceeds 2 MiB",
    }


def test_health_reads_use_a_bounded_worker_queue() -> None:
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )
    release_workers = Event()
    four_workers_active = Event()
    eight_workers_active = Event()
    counter_lock = Lock()
    active_workers = 0
    maximum_active_workers = 0

    def observe() -> RuntimeObservation:
        nonlocal active_workers, maximum_active_workers
        with counter_lock:
            active_workers += 1
            maximum_active_workers = max(maximum_active_workers, active_workers)
            if active_workers == 4:
                four_workers_active.set()
            if active_workers == 8:
                eight_workers_active.set()
        release_workers.wait(timeout=2)
        with counter_lock:
            active_workers -= 1
        return observation

    with HealthServer(observe) as server:
        with ThreadPoolExecutor(max_workers=8) as clients:
            requests = [
                clients.submit(
                    post_health,
                    server,
                    {
                        "protocol": "ankigta-control",
                        "protocolVersion": 1,
                        "requestId": f"concurrent-{index}",
                    },
                )
                for index in range(8)
            ]
            assert four_workers_active.wait(timeout=2)
            eight_workers_active.wait(timeout=0.5)
            assert maximum_active_workers == 4
            release_workers.set()
            assert [request.result(timeout=2)[0] for request in requests] == [200] * 8


@pytest.mark.parametrize(
    "collection_state",
    [CollectionState.ABSENT, CollectionState.CLOSING],
)
def test_unavailable_collection_is_not_reported_as_success(
    collection_state: CollectionState,
) -> None:
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=collection_state),
    )

    with HealthServer(lambda: observation) as server:
        status, response = post_health(
            server,
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": "health-unavailable",
            },
        )

    assert status == 503
    assert response["ok"] is False
    assert response["error"] == {
        "category": "collection_unavailable",
        "message": f"collection is {collection_state.value}",
    }
    assert response["payload"]["collection"] == {
        "state": collection_state.value,
        "profileName": None,
    }


@pytest.mark.parametrize(
    ("anki_version", "v3_scheduler", "fsrs_enabled", "reasons"),
    [
        ("25.07.3", True, True, ["unsupported_anki_version"]),
        ("26.05", False, True, ["v3_scheduler_disabled"]),
        ("26.05", True, False, ["fsrs_disabled"]),
    ],
)
def test_incompatible_anki_configuration_is_an_explicit_failure(
    anki_version: str,
    v3_scheduler: bool,
    fsrs_enabled: bool,
    reasons: list[str],
) -> None:
    observation = RuntimeObservation(
        anki_version=anki_version,
        v3_scheduler=v3_scheduler,
        fsrs_enabled=fsrs_enabled,
        collection=CollectionObservation(
            state=CollectionState.OPEN,
            profile_name="Test Profile",
        ),
    )

    with HealthServer(lambda: observation) as server:
        status, response = post_health(
            server,
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": "health-incompatible",
            },
        )

    assert status == 409
    assert response["ok"] is False
    assert response["error"] == {
        "category": "compatibility_failure",
        "message": "Anki configuration is not supported for session or rating",
    }
    compatibility = response["payload"]["compatibility"]
    assert compatibility == {
        "status": "unsupported",
        "reasons": reasons,
        "previewReadOnlyCompatible": True,
        "sessionCompatible": False,
        "ratingCompatible": False,
    }
    assert response["payload"]["study"] == {
        "sessionActive": False,
        "ratingEnabled": False,
    }
