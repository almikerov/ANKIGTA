"""Ticket 14 — Exact Card Admission.

Prototype 0001 established that `Scheduler.answerCard(X)` fails when X is not
scheduler-top. Prototype 0002 established the supported way to make it top:
rebuild the owned filtered deck to an X-only membership, then let Anki decide.
These tests pin that sequence and, above all, the refusal to rate when Anki did
not actually put X on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event

import pytest

from ankigta_companion.cards import CardState, CardView
from ankigta_companion.collection_identity import (
    AnkiCardIdentity,
    CollectionIdentityObservation,
    CollectionIdentityState,
)
from ankigta_companion.contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)
from ankigta_companion.session import (
    FILTERED_DECK_NAME,
    FilteredDeckInfo,
    SessionCoordinator,
    SessionError,
)


UUID = "11111111-1111-4111-8111-111111111111"
OTHER_UUID = "22222222-2222-4222-8222-222222222222"


@dataclass
class FakeBackend:
    """Records builds and reports whatever scheduler-top the test dictates."""

    existing: FilteredDeckInfo | None = None
    top: AnkiCardIdentity | None = None
    built: list[tuple[str, tuple[int, ...]]] = field(default_factory=list)
    cleaned: list[str] = field(default_factory=list)

    def inspect(self, name: str) -> FilteredDeckInfo | None:
        return self.existing

    def build(
        self,
        name: str,
        card_ids: tuple[int, ...],
        *,
        progress: object,
        cancel: Event,
    ) -> None:
        self.built.append((name, card_ids))

    def cleanup(self, name: str) -> None:
        self.cleaned.append(name)

    def scheduler_top(self) -> AnkiCardIdentity | None:
        return self.top


def observation() -> RuntimeObservation:
    return RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(
            state=CollectionState.OPEN,
            identity=CollectionIdentityObservation(
                CollectionIdentityState.BOUND,
                UUID,
            ),
        ),
    )


def card(card_id: int, state: CardState) -> CardView:
    return CardView(
        identity=AnkiCardIdentity(UUID, card_id),
        deck_id=10,
        deck_name="Source",
        state=state,
        due=0,
        tags=(),
    )


def coordinator(
    backend: FakeBackend,
    cards: dict[int, CardView],
    **kwargs: object,
) -> SessionCoordinator:
    return SessionCoordinator(
        observe=observation,
        read_card=cards.get,
        backend=backend,
        **kwargs,  # type: ignore[arg-type]
    )


def started(
    backend: FakeBackend,
    cards: dict[int, CardView],
    **kwargs: object,
) -> SessionCoordinator:
    session = coordinator(backend, cards, **kwargs)
    session.start(AnkiCardIdentity(UUID, card_id) for card_id in cards)
    backend.built.clear()
    return session


def test_admission_rebuilds_the_owned_deck_to_exactly_one_card() -> None:
    cards = {1: card(1, CardState.NEW), 2: card(2, CardState.NEW)}
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 2))
    session = started(backend, cards)

    result = session.admit(AnkiCardIdentity(UUID, 2))

    assert backend.built == [(FILTERED_DECK_NAME, (2,))]
    assert result.admitted is True
    assert result.preview_only is False
    assert result.identity == AnkiCardIdentity(UUID, 2)


def test_a_non_top_result_is_preview_only_and_never_rates() -> None:
    cards = {1: card(1, CardState.NEW), 2: card(2, CardState.NEW)}
    # Anki put something else on top despite the X-only rebuild.
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 1))
    session = started(backend, cards)

    result = session.admit(AnkiCardIdentity(UUID, 2))

    assert result.admitted is False
    assert result.preview_only is True
    assert result.reason == "not_scheduler_top"


def test_an_empty_scheduler_top_is_preview_only() -> None:
    cards = {2: card(2, CardState.NEW)}
    backend = FakeBackend(top=None)
    session = started(backend, cards)

    result = session.admit(AnkiCardIdentity(UUID, 2))

    assert result.admitted is False
    assert result.preview_only is True
    assert result.reason == "no_scheduler_top"


def test_a_matching_card_id_from_another_collection_is_not_the_same_card() -> None:
    cards = {2: card(2, CardState.NEW)}
    # Same numeric card id, different collection: not X.
    backend = FakeBackend(top=AnkiCardIdentity(OTHER_UUID, 2))
    session = started(backend, cards)

    result = session.admit(AnkiCardIdentity(UUID, 2))

    assert result.admitted is False
    assert result.reason == "not_scheduler_top"


@pytest.mark.parametrize("state", [CardState.SUSPENDED, CardState.BURIED])
def test_unavailable_cards_are_refused_even_when_asked_for_explicitly(
    state: CardState,
) -> None:
    cards = {1: card(1, CardState.NEW), 2: card(2, state)}
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 2))
    session = started(backend, cards)

    with pytest.raises(SessionError) as error:
        session.admit(AnkiCardIdentity(UUID, 2))

    assert error.value.category == "card_unavailable"
    assert backend.built == [], "an ineligible card must not touch the deck"


def test_a_not_due_card_needs_explicit_early_review() -> None:
    cards = {1: card(1, CardState.NEW), 2: card(2, CardState.NOT_DUE)}
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 2))
    session = started(backend, cards)

    with pytest.raises(SessionError) as error:
        session.admit(AnkiCardIdentity(UUID, 2))
    assert error.value.category == "early_review_disabled"

    result = session.admit(AnkiCardIdentity(UUID, 2), allow_early_review=True)
    assert result.admitted is True


def test_a_card_from_another_collection_is_refused() -> None:
    cards = {1: card(1, CardState.NEW)}
    backend = FakeBackend(top=AnkiCardIdentity(OTHER_UUID, 1))
    session = started(backend, cards)

    with pytest.raises(SessionError) as error:
        session.admit(AnkiCardIdentity(OTHER_UUID, 1))

    assert error.value.category == "wrong_collection"
    assert backend.built == []


def test_a_stale_card_id_is_refused() -> None:
    cards = {1: card(1, CardState.NEW)}
    backend = FakeBackend(top=None)
    session = started(backend, cards)

    with pytest.raises(SessionError) as error:
        session.admit(AnkiCardIdentity(UUID, 999))

    assert error.value.category == "card_missing"
    assert backend.built == []


def test_admission_requires_an_active_session() -> None:
    cards = {1: card(1, CardState.NEW)}
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 1))
    session = coordinator(backend, cards)

    with pytest.raises(SessionError) as error:
        session.admit(AnkiCardIdentity(UUID, 1))

    assert error.value.category == "session_inactive"
    assert backend.built == []


def test_an_unresolved_transaction_blocks_admission() -> None:
    cards = {1: card(1, CardState.NEW)}
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 1))
    blocked = {"value": False}
    session = started(
        backend,
        cards,
        unresolved_transaction=lambda: blocked["value"],
    )

    blocked["value"] = True
    with pytest.raises(SessionError) as error:
        session.admit(AnkiCardIdentity(UUID, 1))

    assert error.value.category == "outcome_unknown"
    assert backend.built == []


def test_a_second_admission_while_one_is_open_is_refused() -> None:
    cards = {1: card(1, CardState.NEW), 2: card(2, CardState.NEW)}
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 1))
    session = started(backend, cards)

    session.admit(AnkiCardIdentity(UUID, 1))
    backend.top = AnkiCardIdentity(UUID, 2)
    with pytest.raises(SessionError) as error:
        session.admit(AnkiCardIdentity(UUID, 2))

    assert error.value.category == "admission_open"


def test_restoring_rebuilds_the_full_membership_without_duplicates() -> None:
    cards = {
        1: card(1, CardState.NEW),
        2: card(2, CardState.NEW),
        3: card(3, CardState.LEARNING),
    }
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 2))
    session = started(backend, cards)

    session.admit(AnkiCardIdentity(UUID, 2))
    session.restore()

    assert backend.built[-1] == (FILTERED_DECK_NAME, (1, 2, 3))
    assert session.status().card_ids == (1, 2, 3)
    assert session.status().session_active is True


def test_a_preview_only_admission_restores_the_full_membership_itself() -> None:
    cards = {1: card(1, CardState.NEW), 2: card(2, CardState.NEW)}
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 1))
    session = started(backend, cards)

    result = session.admit(AnkiCardIdentity(UUID, 2))

    assert result.preview_only is True
    # A refused admission must not strand the session on an X-only deck.
    assert backend.built[-1] == (FILTERED_DECK_NAME, (1, 2))
    assert session.status().card_ids == (1, 2)


def test_restore_is_idempotent_when_no_admission_is_open() -> None:
    cards = {1: card(1, CardState.NEW)}
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 1))
    session = started(backend, cards)

    assert session.restore() is False
    assert backend.built == []


def test_the_session_never_answers_or_writes_scheduling_state() -> None:
    """Anki stays authoritative: no direct answers, no queue or SQL writes."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "companion"
        / "ankigta_companion"
        / "session.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "answerCard",
        "answer_card",
        # Private scheduler queues, as attribute access -- the supported
        # observer `get_queued_cards` is deliberately not matched here.
        "._queue",
        "._lrnQueue",
        "._revQueue",
        "._newQueue",
        "col.db",
        "collection.db",
        "UPDATE cards",
        "UPDATE revlog",
        "INSERT INTO revlog",
    ):
        assert forbidden not in source, f"session must not use {forbidden}"


def test_admission_is_reachable_as_a_versioned_control_operation() -> None:
    """The MTA gateway (ticket 15) reaches admission over the control API."""
    import json
    from http.client import HTTPConnection

    from ankigta_companion.http_server import HealthServer

    cards = {1: card(1, CardState.NEW), 2: card(2, CardState.NEW)}
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 2))
    session = coordinator(backend, cards)

    with HealthServer(observation, session_coordinator=session) as server:

        def post(path: str, body: dict[str, object]) -> tuple[int, dict[str, object]]:
            connection = HTTPConnection(server.host, server.port, timeout=2)
            connection.request(
                "POST",
                path,
                body=json.dumps(
                    {
                        "protocol": "ankigta-control",
                        "protocolVersion": 1,
                        "requestId": "admit-1",
                        **body,
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            value = json.loads(response.read())
            connection.close()
            return response.status, value

        status, _ = post(
            "/v1/session/start",
            {
                "cardIdentities": [
                    {"collectionUuid": UUID, "cardId": 1},
                    {"collectionUuid": UUID, "cardId": 2},
                ]
            },
        )
        assert status == 200

        status, admitted = post(
            "/v1/session/admit",
            {"cardIdentity": {"collectionUuid": UUID, "cardId": 2}},
        )
        assert status == 200
        assert admitted["payload"]["admission"]["admitted"] is True
        assert admitted["payload"]["session"]["ratingEnabled"] is True

        status, restored = post("/v1/session/restore", {})
        assert status == 200
        assert restored["payload"]["restored"] is True
        assert restored["payload"]["session"]["ratingEnabled"] is False

        # A card Anki refuses to put on top must not look ratable.
        backend.top = AnkiCardIdentity(UUID, 1)
        status, refused = post(
            "/v1/session/admit",
            {"cardIdentity": {"collectionUuid": UUID, "cardId": 2}},
        )
        assert status == 200
        assert refused["payload"]["admission"]["previewOnly"] is True
        assert refused["payload"]["admission"]["reason"] == "not_scheduler_top"
        assert refused["payload"]["session"]["ratingEnabled"] is False


def test_a_malformed_admission_request_is_rejected() -> None:
    import json
    from http.client import HTTPConnection

    from ankigta_companion.http_server import HealthServer

    cards = {1: card(1, CardState.NEW)}
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 1))
    session = coordinator(backend, cards)

    with HealthServer(observation, session_coordinator=session) as server:
        connection = HTTPConnection(server.host, server.port, timeout=2)
        connection.request(
            "POST",
            "/v1/session/admit",
            body=json.dumps(
                {
                    "protocol": "ankigta-control",
                    "protocolVersion": 1,
                    "requestId": "admit-bad",
                    "cardIdentity": {"collectionUuid": UUID},
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        value = json.loads(response.read())
        connection.close()

    assert response.status == 400
    assert value["error"]["category"] == "invalid_session_request"
    assert backend.built == []
