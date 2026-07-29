from __future__ import annotations

import json
from http.client import HTTPConnection

import pytest

from ankigta_companion.contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)
from ankigta_companion.http_server import HealthServer


def post_health(server: HealthServer, body: object) -> tuple[int, dict[str, object]]:
    connection = HTTPConnection(server.host, server.port, timeout=2)
    connection.request(
        "POST",
        "/v1/health",
        body=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    payload = json.loads(response.read())
    connection.close()
    return response.status, payload


def post_raw_health(
    server: HealthServer,
    body: bytes,
) -> tuple[int, dict[str, object]]:
    connection = HTTPConnection(server.host, server.port, timeout=2)
    connection.request(
        "POST",
        "/v1/health",
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
