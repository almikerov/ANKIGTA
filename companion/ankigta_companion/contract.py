from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .collection_identity import (
    CollectionIdentityObservation,
    CollectionIdentityState,
)
from .cards import CardSearchPage, CardView
from .notes import NoteUpdate


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
    identity: CollectionIdentityObservation | None = None


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
    study: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    compatibility_reasons: list[str] = []
    if observation.anki_version != SUPPORTED_ANKI_VERSION:
        compatibility_reasons.append("unsupported_anki_version")
    if not observation.v3_scheduler:
        compatibility_reasons.append("v3_scheduler_disabled")
    # FSRS is reported and not judged. Nothing ANKIGTA does depends on the
    # scheduling algorithm: Exact Card Admission asks the V3 scheduler for its
    # top card and hands the rating to Anki, which computes the interval. The
    # setting still travels in the payload, because a diagnostic that says which
    # scheduler produced an interval is worth having.
    supported = not compatibility_reasons
    collection: dict[str, object] = {
        "state": observation.collection.state.value,
        "profileName": observation.collection.profile_name,
    }
    identity = observation.collection.identity
    if identity is not None:
        collection.update(
            {
                "collectionUuid": identity.collection_uuid,
                "identityState": identity.state.value,
            }
        )
        if identity.copy_decision_options:
            collection["copyDecision"] = {
                "options": [
                    option.value
                    for option in identity.copy_decision_options
                ],
                "default": (
                    identity.default_copy_decision.value
                    if identity.default_copy_decision is not None
                    else None
                ),
            }
        if identity.error_category is not None:
            collection["identityErrorCategory"] = identity.error_category
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

    study_payload: dict[str, object] = (
        dict(study)
        if study is not None
        else {
            "sessionActive": False,
            "ratingEnabled": False,
            "filteredDeckCreated": False,
            "reviewModeOpened": False,
        }
    )
    if (
        identity is not None
        and identity.state is not CollectionIdentityState.BOUND
    ):
        study_payload.update(
            {
                "paused": True,
                "pausedReason": identity.state.value,
            }
        )

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
            "study": study_payload,
        },
    }


def card_view_payload(card: CardView) -> dict[str, object]:
    return {
        "identity": {
            "collectionUuid": card.identity.collection_uuid,
            "cardId": card.identity.card_id,
        },
        "deck": {
            "id": card.deck_id,
            "name": card.deck_name,
        },
        "state": card.state.value,
        "due": card.due,
        "tags": list(card.tags),
        # Present only where the note was read, which is the single card being
        # inspected rather than any card on a list.
        "note": {
            "noteId": card.note_id,
            "fields": [
                {"name": field.name, "value": field.value}
                for field in card.fields
            ],
        },
    }


def card_search_response(
    request_id: str,
    page: CardSearchPage,
) -> tuple[int, dict[str, object]]:
    return 200, {
        "protocol": PROTOCOL_NAME,
        "protocolVersion": PROTOCOL_VERSION,
        "requestId": request_id,
        "ok": True,
        "error": None,
        "payload": {
            "cards": [card_view_payload(card) for card in page.cards],
            "page": page.page,
            "pageSize": page.page_size,
            "total": page.total,
            "query": page.query,
            "deckFilter": page.deck_filter,
            # Every deck, with the page rather than behind a second request.
            # The search already had to read them all to name one page of
            # cards, so this costs nothing and cannot disagree with what the
            # page says a card's deck is.
            "decks": [
                {"deckId": deck.deck_id, "name": deck.name}
                for deck in page.decks
            ],
        },
    }


def note_update_response(
    request_id: str,
    update: NoteUpdate,
) -> tuple[int, dict[str, object]]:
    return 200, {
        "protocol": PROTOCOL_NAME,
        "protocolVersion": PROTOCOL_VERSION,
        "requestId": request_id,
        "ok": True,
        "error": None,
        "payload": {
            # What the note says now, read back after the write: Anki
            # normalises tags and may rewrite a field on save, so echoing the
            # request would report a change the collection did not make.
            "note": {
                "noteId": update.note_id,
                "fields": [
                    {"name": field.name, "value": field.value}
                    for field in update.fields
                ],
                "tags": list(update.tags),
            },
        },
    }


def card_read_response(
    request_id: str,
    card: CardView,
) -> tuple[int, dict[str, object]]:
    return 200, {
        "protocol": PROTOCOL_NAME,
        "protocolVersion": PROTOCOL_VERSION,
        "requestId": request_id,
        "ok": True,
        "error": None,
        "payload": {"card": card_view_payload(card)},
    }


def session_response(
    request_id: str,
    payload: dict[str, object],
) -> tuple[int, dict[str, object]]:
    return 200, {
        "protocol": PROTOCOL_NAME,
        "protocolVersion": PROTOCOL_VERSION,
        "requestId": request_id,
        "ok": True,
        "error": None,
        "payload": payload,
    }
