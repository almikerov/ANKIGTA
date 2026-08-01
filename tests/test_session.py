from __future__ import annotations

from dataclasses import dataclass
import json
from http.client import HTTPConnection
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
    AnkiFilteredDeckBackend,
    FILTERED_DECK_NAME,
    FilteredDeckInfo,
    SessionCoordinator,
    SessionError,
)
from ankigta_companion.http_server import HealthServer


UUID = "11111111-1111-4111-8111-111111111111"


@dataclass
class FakeBackend:
    existing: FilteredDeckInfo | None = None

    def __post_init__(self) -> None:
        self.built: list[tuple[str, tuple[int, ...]]] = []
        self.cleaned: list[str] = []

    def inspect(self, name: str) -> FilteredDeckInfo | None:
        assert name == FILTERED_DECK_NAME
        return self.existing

    def build(
        self,
        name: str,
        card_ids: tuple[int, ...],
        *,
        progress: object,
        cancel: Event,
    ) -> None:
        assert name == FILTERED_DECK_NAME
        self.built.append((name, card_ids))

    def cleanup(self, name: str) -> None:
        self.cleaned.append(name)


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


def test_start_deduplicates_identities_and_excludes_unavailable_cards() -> None:
    cards = {
        1: card(1, CardState.NEW),
        2: card(2, CardState.LEARNING),
        3: card(3, CardState.REVIEW),
        4: card(4, CardState.SUSPENDED),
        5: card(5, CardState.BURIED),
        6: card(6, CardState.NOT_DUE),
    }
    backend = FakeBackend()
    coordinator = SessionCoordinator(
        observe=observation,
        read_card=lambda card_id: cards.get(card_id),
        backend=backend,
    )

    result = coordinator.start(
        [
            AnkiCardIdentity(UUID, 3),
            AnkiCardIdentity(UUID, 1),
            AnkiCardIdentity(UUID, 3),
            AnkiCardIdentity(UUID, 2),
            AnkiCardIdentity(UUID, 4),
            AnkiCardIdentity(UUID, 5),
            AnkiCardIdentity(UUID, 6),
        ]
    )

    assert result.card_ids == (1, 2, 3)
    assert backend.built == [(FILTERED_DECK_NAME, (1, 2, 3))]
    assert coordinator.status().session_active is True


def test_start_requires_explicitly_enabled_early_review() -> None:
    backend = FakeBackend()
    coordinator = SessionCoordinator(
        observe=observation,
        read_card=lambda _card_id: card(6, CardState.NOT_DUE),
        backend=backend,
    )

    assert coordinator.start(
        [AnkiCardIdentity(UUID, 6)],
    ).card_ids == ()
    assert coordinator.pause().cleaned is False

    coordinator.start(
        [AnkiCardIdentity(UUID, 6)],
        allow_early_review=True,
    )
    assert backend.built[-1] == (FILTERED_DECK_NAME, (6,))


def test_empty_rebuild_cleans_an_owned_stale_deck() -> None:
    backend = FakeBackend(existing=FilteredDeckInfo(deck_id=7, owned=True))
    coordinator = SessionCoordinator(
        observe=observation,
        read_card=lambda _card_id: card(6, CardState.NOT_DUE),
        backend=backend,
    )

    result = coordinator.start([AnkiCardIdentity(UUID, 6)])

    assert result.card_ids == ()
    assert backend.cleaned == [FILTERED_DECK_NAME]


def test_owned_deck_collision_does_not_touch_foreign_filtered_deck() -> None:
    backend = FakeBackend(
        existing=FilteredDeckInfo(deck_id=99, owned=False),
    )
    coordinator = SessionCoordinator(
        observe=observation,
        read_card=lambda _card_id: card(1, CardState.NEW),
        backend=backend,
    )

    with pytest.raises(SessionError, match="collision"):
        coordinator.start([AnkiCardIdentity(UUID, 1)])
    assert backend.built == []
    assert backend.cleaned == []


def test_pause_cleans_owned_deck_and_returns_to_paused() -> None:
    backend = FakeBackend()
    coordinator = SessionCoordinator(
        observe=observation,
        read_card=lambda _card_id: card(1, CardState.NEW),
        backend=backend,
    )
    coordinator.start([AnkiCardIdentity(UUID, 1)])

    result = coordinator.pause()

    assert result.cleaned is True
    assert backend.cleaned == [FILTERED_DECK_NAME]
    assert coordinator.status().session_active is False


def test_rebuild_timeout_cleans_without_stranding_cards() -> None:
    backend = FakeBackend()

    def slow_build(
        _name: str,
        _card_ids: tuple[int, ...],
        *,
        progress: object,
        cancel: Event,
    ) -> None:
        cancel.set()

    backend.build = slow_build  # type: ignore[method-assign]
    coordinator = SessionCoordinator(
        observe=observation,
        read_card=lambda _card_id: card(1, CardState.NEW),
        backend=backend,
    )

    with pytest.raises(SessionError, match="cancelled"):
        coordinator.start([AnkiCardIdentity(UUID, 1)])
    assert backend.cleaned == [FILTERED_DECK_NAME]
    assert coordinator.status().session_active is False


def test_anki_backend_uses_owner_marker_and_scheduler_operations() -> None:
    class Decks:
        def __init__(self) -> None:
            self.names = [("Source", 1)]
            self.created: list[str] = []

        def all_names_and_ids(self) -> list[tuple[str, int]]:
            return self.names

        def create_filtered(self, name: str) -> int:
            self.created.append(name)
            self.names.append((name, 7))
            return 7

        def remove(self, deck_id: int) -> None:
            self.names = [item for item in self.names if item[1] != deck_id]

    class Collection:
        def __init__(self) -> None:
            self.decks = Decks()
            self.config: dict[str, object] = {}
            self.rebuilt: list[tuple[int, tuple[int, ...]]] = []
            self.emptied: list[int] = []
            self.deleted: list[int] = []

        def get_config(self, key: str, default: object | None = None) -> object:
            return self.config.get(key, default)

        def set_config(
            self,
            key: str,
            value: object,
            *,
            undoable: bool = False,
        ) -> object:
            self.config[key] = value
            return value

        def rebuild(self, deck_id: int, card_ids: tuple[int, ...]) -> None:
            self.rebuilt.append((deck_id, card_ids))

        def delete_deck(self, deck_id: int) -> None:
            # A real delete removes the deck, so the fake must too; otherwise
            # post-cleanup lookups pass for the wrong reason.
            self.deleted.append(deck_id)
            self.decks.remove(deck_id)

    collection = Collection()
    backend = AnkiFilteredDeckBackend(
        collection,
        create_filtered_deck=collection.decks.create_filtered,
        rebuild_filtered_deck=collection.rebuild,
        empty_filtered_deck=collection.emptied.append,
        delete_filtered_deck=collection.delete_deck,
    )

    assert backend.inspect(FILTERED_DECK_NAME) is None
    backend.build(
        FILTERED_DECK_NAME,
        (9, 2),
        progress=lambda *_: None,
        cancel=Event(),
    )
    assert collection.rebuilt == [(7, (9, 2))]
    assert backend.inspect(FILTERED_DECK_NAME) == FilteredDeckInfo(7, True)
    backend.cleanup(FILTERED_DECK_NAME)
    assert collection.emptied == [7]
    assert collection.deleted == [7]
    # The ownership marker must go with the deck; a stale one would make
    # ANKIGTA claim a future deck that reused this id.
    assert collection.config[AnkiFilteredDeckBackend.OWNER_CONFIG_KEY] is None
    assert backend.inspect(FILTERED_DECK_NAME) is None


def test_session_control_requires_explicit_start_and_reports_health_state() -> None:
    backend = FakeBackend()
    coordinator = SessionCoordinator(
        observe=observation,
        read_card=lambda _card_id: card(1, CardState.NEW),
        backend=backend,
    )
    with HealthServer(lambda: observation(), session_coordinator=coordinator) as server:
        def post(path: str, body: dict[str, object]) -> tuple[int, dict[str, object]]:
            connection = HTTPConnection(server.host, server.port, timeout=2)
            connection.request(
                "POST",
                path,
                body=json.dumps(
                    {
                        "protocol": "ankigta-control",
                        "protocolVersion": 1,
                        "requestId": "session-1",
                        **body,
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            value = json.loads(response.read())
            connection.close()
            return response.status, value

        status, before = post("/v1/health", {})
        assert status == 200
        assert before["payload"]["study"]["sessionActive"] is False
        status, started = post(
            "/v1/session/start",
            {
                "cardIdentities": [
                    {"collectionUuid": UUID, "cardId": 1},
                ],
            },
        )
        assert status == 200
        assert started["payload"]["cardIds"] == [1]
        status, after = post("/v1/health", {})
        assert status == 200
        assert after["payload"]["study"]["sessionActive"] is True
        status, paused = post("/v1/session/pause", {})
        assert status == 200
        assert paused["payload"]["cleaned"] is True
