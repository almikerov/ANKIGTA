from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


PROTOCOL_NAME = "ankigta-control"
PROTOCOL_VERSION = 1
SUPPORTED_ANKI_VERSION = "26.05"


class CollectionState(StrEnum):
    OPEN = "open"
    ABSENT = "absent"
    CLOSING = "closing"


@dataclass(frozen=True)
class CollectionObservation:
    state: CollectionState
    profile_name: str | None = None


@dataclass(frozen=True)
class RuntimeObservation:
    anki_version: str
    v3_scheduler: bool
    fsrs_enabled: bool
    collection: CollectionObservation


class ContractError(ValueError):
    def __init__(
        self,
        category: str,
        message: str,
        request_id: str | None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.request_id = request_id


def validate_request(request: object) -> str:
    if not isinstance(request, dict):
        raise ContractError(
            "invalid_envelope",
            "request body must be a JSON object",
            None,
        )
    request_id = request.get("requestId")
    if not isinstance(request_id, str) or not request_id:
        raise ContractError(
            "invalid_request_id",
            "requestId must be a non-empty string",
            None,
        )
    if (
        request.get("protocol") != PROTOCOL_NAME
        or request.get("protocolVersion") != PROTOCOL_VERSION
    ):
        raise ContractError(
            "protocol_mismatch",
            "unsupported protocol identity or version",
            request_id,
        )
    return request_id


def error_response(error: ContractError) -> dict[str, object]:
    return {
        "protocol": PROTOCOL_NAME,
        "protocolVersion": PROTOCOL_VERSION,
        "requestId": error.request_id,
        "ok": False,
        "error": {
            "category": error.category,
            "message": error.message,
        },
        "payload": None,
    }


def health_response(
    request_id: str,
    observation: RuntimeObservation,
) -> tuple[int, dict[str, object]]:
    compatibility_reasons: list[str] = []
    if observation.anki_version != SUPPORTED_ANKI_VERSION:
        compatibility_reasons.append("unsupported_anki_version")
    if not observation.v3_scheduler:
        compatibility_reasons.append("v3_scheduler_disabled")
    if not observation.fsrs_enabled:
        compatibility_reasons.append("fsrs_disabled")
    supported = not compatibility_reasons
    collection = {
        "state": observation.collection.state.value,
        "profileName": observation.collection.profile_name,
    }
    compatibility: dict[str, object] = {
        "status": "supported" if supported else "unsupported",
        "previewReadOnlyCompatible": True,
        "sessionCompatible": supported,
        "ratingCompatible": supported,
    }
    if compatibility_reasons:
        compatibility["reasons"] = compatibility_reasons

    error: dict[str, str] | None = None
    if observation.collection.state is not CollectionState.OPEN:
        error = {
            "category": "collection_unavailable",
            "message": f"collection is {observation.collection.state.value}",
        }
    elif not supported:
        error = {
            "category": "compatibility_failure",
            "message": "Anki configuration is not supported for session or rating",
        }

    if error is None:
        status = 200
    elif error["category"] == "collection_unavailable":
        status = 503
    else:
        status = 409

    return status, {
        "protocol": PROTOCOL_NAME,
        "protocolVersion": PROTOCOL_VERSION,
        "requestId": request_id,
        "ok": error is None,
        "error": error,
        "payload": {
            "anki": {
                "version": observation.anki_version,
                "v3Scheduler": observation.v3_scheduler,
                "fsrsEnabled": observation.fsrs_enabled,
            },
            "collection": collection,
            "compatibility": compatibility,
            "study": {
                "sessionActive": False,
                "ratingEnabled": False,
            },
        },
    }
