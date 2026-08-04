from __future__ import annotations

from dataclasses import dataclass
import json
from http.client import HTTPConnection

import pytest

from ankigta_companion.cards import (
    CardPickerError,
    CardPickerService,
    CardState,
)
from ankigta_companion.contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)
from ankigta_companion.http_server import HealthServer
from ankigta_companion.collection_identity import (
    CollectionIdentityObservation,
    CollectionIdentityState,
)
from ankigta_companion.collection_identity import AnkiCardIdentity


BOUND_UUID = "11111111-1111-4111-8111-111111111111"
OTHER_UUID = "22222222-2222-4222-8222-222222222222"


@dataclass
class FakeNote:
    tags: list[str]
    id: int = 0


@dataclass
class FakeCard:
    id: int
    did: int
    queue: int
    due: int
    note_tags: list[str]
    #: Which note this card belongs to. Defaulted to the card's own id so a
    #: card written without one is still a note of its own, the way a
    #: single-template note type behaves.
    note_id: int = 0

    def note(self) -> FakeNote:
        return FakeNote(self.note_tags, self.note_id or self.id)


class FakeDecks:
    def all_names_and_ids(self) -> list[tuple[str, int]]:
        return [("Languages", 10), ("Archive", 20)]


@dataclass(frozen=True)
class AnkiDeckNameId:
    """The record shape returned by Anki 26.05's deck manager."""

    id: int
    name: str


class AnkiDecks:
    def all_names_and_ids(self) -> list[AnkiDeckNameId]:
        return [
            AnkiDeckNameId(id=10, name="Languages"),
            AnkiDeckNameId(id=20, name="Archive"),
        ]


class FakeCollection:
    decks = FakeDecks()

    def __init__(self) -> None:
        self.cards = {
            2: FakeCard(2, 10, 0, 0, ["anki"]),
            4: FakeCard(4, 20, 2, 12, ["review"]),
            6: FakeCard(6, 10, -1, 0, ["suspended"]),
        }
        self.queries: list[str] = []

    def find_cards(self, query: str) -> list[int]:
        self.queries.append(query)
        return sorted(self.cards)

    def find_notes(self, query: str) -> list[int]:
        self.queries.append(query)
        return sorted({card.note_id or card.id for card in self.cards.values()})

    def card_ids_of_note(self, note_id: int) -> list[int]:
        return [
            card.id
            for card in sorted(self.cards.values(), key=lambda card: card.id)
            if (card.note_id or card.id) == note_id
        ]

    def get_card(self, card_id: int) -> FakeCard | None:
        return self.cards.get(card_id)


def bound_identity(uuid: str = BOUND_UUID) -> CollectionIdentityObservation:
    return CollectionIdentityObservation(CollectionIdentityState.BOUND, uuid)


def test_search_uses_only_bound_collection_and_preserves_initial_deck_filter() -> None:
    collection = FakeCollection()
    service = CardPickerService(lambda: bound_identity(), lambda: collection)

    result = service.search(query="front:hello", deck_filter="Languages", page=0, page_size=2)

    assert collection.queries == ['deck:"Languages" front:hello']
    assert result.total == 3
    assert [card.identity.card_id for card in result.cards] == [2, 4]
    assert result.cards[0].identity.collection_uuid == BOUND_UUID
    assert result.cards[0].state is CardState.NEW
    assert result.cards[1].deck_name == "Archive"


def test_search_pagination_and_stale_state_are_explicit() -> None:
    collection = FakeCollection()
    service = CardPickerService(lambda: bound_identity(), lambda: collection)
    collection.cards.pop(4)

    result = service.search(page=0, page_size=2)

    assert result.total == 2
    assert [card.identity.card_id for card in result.cards] == [2, 6]
    assert result.cards[1].state is CardState.SUSPENDED

    with pytest.raises(CardPickerError, match="card is missing"):
        service.read(4)


def test_a_written_anki_expression_reaches_anki_unchanged() -> None:
    """What the player typed is the search, not a phrase to be reinterpreted.

    `-is:suspended` means "not suspended" to Anki and nothing at all to a
    substring match, so anything this side did to the text -- quoting it,
    escaping it, splitting it into words -- would silently answer a different
    question from the one that was asked.
    """
    collection = FakeCollection()
    service = CardPickerService(lambda: bound_identity(), lambda: collection)

    service.search(query="deck:Spanish tag:verb -is:suspended")

    assert collection.queries == ["deck:Spanish tag:verb -is:suspended"]


class SearchError(Exception):
    """What Anki raises when the expression itself is what it cannot accept.

    Named for `anki.errors.SearchError`, which is what `find_cards` raises on
    an expression it cannot parse. There is no Anki in this suite, and the
    companion recognises that class by name, so a double of the same name is
    the honest stand-in.
    """


def test_an_expression_anki_rejects_is_reported_as_rejected() -> None:
    """A refused expression is not an empty collection.

    Reporting it as no results tells the player their search ran and matched
    nothing, which sends them looking for the missing cards instead of at the
    bracket they left open.
    """
    collection = FakeCollection()

    def refuse(query: str) -> list[int]:
        raise SearchError("Invalid search - please check for typing mistakes.")

    collection.find_cards = refuse  # type: ignore[method-assign]
    service = CardPickerService(lambda: bound_identity(), lambda: collection)

    with pytest.raises(CardPickerError) as rejected:
        service.search(query="deck:(Spanish")

    assert rejected.value.category == "search_rejected"
    assert "typing mistakes" in rejected.value.message


def test_a_collection_failure_that_is_not_the_expression_stays_a_read_failure() -> None:
    collection = FakeCollection()

    def fail(query: str) -> list[int]:
        raise RuntimeError("the collection is closed")

    collection.find_cards = fail  # type: ignore[method-assign]
    service = CardPickerService(lambda: bound_identity(), lambda: collection)

    with pytest.raises(CardPickerError) as failure:
        service.search()

    assert failure.value.category == "card_search_failed"


def test_the_note_card_switch_changes_what_a_result_row_is() -> None:
    """Notes mode lists notes; cards mode lists cards, as Anki's browser does.

    A note with two cards is two rows in one mode and one in the other, and the
    row a note stands for is its first card, so linking still names a card.
    """
    collection = FakeCollection()
    collection.cards[3] = FakeCard(3, 10, 0, 0, ["anki"], note_id=2)
    service = CardPickerService(lambda: bound_identity(), lambda: collection)

    cards = service.search(scope="cards")
    notes = service.search(scope="notes")

    assert [card.identity.card_id for card in cards.cards] == [2, 3, 4, 6]
    assert cards.total == 4
    assert [card.identity.card_id for card in notes.cards] == [2, 4, 6]
    assert notes.total == 3
    assert notes.scope == "notes"


def test_a_scope_the_picker_does_not_have_is_refused() -> None:
    collection = FakeCollection()
    service = CardPickerService(lambda: bound_identity(), lambda: collection)

    with pytest.raises(CardPickerError) as refused:
        service.search(scope="decks")

    assert refused.value.category == "invalid_scope"
    assert collection.queries == []


def test_card_search_is_blocked_when_collection_is_not_bound() -> None:
    collection = FakeCollection()
    service = CardPickerService(
        lambda: CollectionIdentityObservation(CollectionIdentityState.WRONG_COLLECTION, OTHER_UUID),
        lambda: collection,
    )

    with pytest.raises(CardPickerError, match="Bound"):
        service.search()
    assert collection.queries == []


def _post(
    server: HealthServer,
    path: str,
    body: dict[str, object],
) -> tuple[int, dict[str, object]]:
    connection = HTTPConnection(server.host, server.port, timeout=2)
    connection.request(
        "POST",
        path,
        body=json.dumps(
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": "cards-001",
                **body,
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    payload = json.loads(response.read())
    connection.close()
    return response.status, payload


def test_card_search_and_read_use_versioned_control_envelopes() -> None:
    collection = FakeCollection()
    service = CardPickerService(lambda: bound_identity(), lambda: collection)
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )

    with HealthServer(lambda: observation, card_picker=service) as server:
        status, search = _post(
            server,
            "/v1/cards/search",
            {"query": "front:hello", "deckFilter": "Languages"},
        )
        read_status, read = _post(
            server,
            "/v1/cards/read",
            {"cardId": 2},
        )

    assert status == 200
    assert search["ok"] is True
    assert search["payload"]["cards"][0]["identity"] == {
        "collectionUuid": BOUND_UUID,
        "cardId": 2,
    }
    assert read_status == 200
    assert read["payload"]["card"]["state"] == "new"


def test_card_search_accepts_anki_deck_records_at_the_http_boundary() -> None:
    collection = FakeCollection()
    collection.decks = AnkiDecks()
    service = CardPickerService(lambda: bound_identity(), lambda: collection)
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )

    with HealthServer(lambda: observation, card_picker=service) as server:
        status, search = _post(server, "/v1/cards/search", {"query": ""})

    assert status == 200
    assert search["payload"]["decks"] == [
        {"deckId": 20, "name": "Archive"},
        {"deckId": 10, "name": "Languages"},
    ]
    assert search["payload"]["cards"][0]["deck"] == {
        "id": 10,
        "name": "Languages",
    }


def test_card_identity_survives_deck_move_and_can_be_reused() -> None:
    collection = FakeCollection()
    service = CardPickerService(lambda: bound_identity(), lambda: collection)

    first = service.read(2)
    collection.cards[2].did = 20
    second = service.read(2)

    assert first.identity == second.identity
    assert second.deck_name == "Archive"
    assert second.identity.card_id == 2


def test_refresh_card_state_is_exact_and_rejects_missing_or_other_collection() -> None:
    collection = FakeCollection()
    service = CardPickerService(lambda: bound_identity(), lambda: collection)

    assert service.refresh_card_state(AnkiCardIdentity(BOUND_UUID, 2)) is True
    collection.cards.pop(2)
    with pytest.raises(CardPickerError, match="card is missing"):
        service.refresh_card_state(AnkiCardIdentity(BOUND_UUID, 2))
    with pytest.raises(CardPickerError, match="different collection"):
        service.refresh_card_state(AnkiCardIdentity(OTHER_UUID, 2))


def test_card_control_rejects_malformed_search_parameters() -> None:
    collection = FakeCollection()
    service = CardPickerService(lambda: bound_identity(), lambda: collection)
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )

    with HealthServer(lambda: observation, card_picker=service) as server:
        status, response = _post(
            server,
            "/v1/cards/search",
            {"query": 42},
        )

    assert status == 400
    assert response["error"]["category"] == "invalid_query"


def test_a_rejected_expression_and_the_chosen_scope_cross_the_http_boundary() -> None:
    """The gateway can only tell the two apart if the answer does.

    A rejected expression has to arrive as a refusal the panel can name, and
    the scope has to come back with the page so the switch and the rows on
    screen cannot drift apart.
    """
    collection = FakeCollection()
    collection.cards[3] = FakeCard(3, 10, 0, 0, ["anki"], note_id=2)
    service = CardPickerService(lambda: bound_identity(), lambda: collection)
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )

    with HealthServer(lambda: observation, card_picker=service) as server:
        scoped_status, scoped = _post(
            server,
            "/v1/cards/search",
            {"query": "", "scope": "notes"},
        )

        def refuse(query: str) -> list[int]:
            raise SearchError("Invalid search - please check for typing mistakes.")

        collection.find_cards = refuse  # type: ignore[method-assign]
        rejected_status, rejected = _post(
            server,
            "/v1/cards/search",
            {"query": "deck:(Spanish"},
        )

    assert scoped_status == 200
    assert scoped["payload"]["scope"] == "notes"
    assert [card["identity"]["cardId"] for card in scoped["payload"]["cards"]] == [
        2,
        4,
        6,
    ]
    assert rejected_status == 400
    assert rejected["error"]["category"] == "search_rejected"
    assert "typing mistakes" in rejected["error"]["message"]


class CountingCollection:
    """A collection that records how much of itself was read.

    The point of a page is that it costs a page. Nothing about the returned
    cards distinguishes "read fifty" from "read a hundred thousand and threw
    away all but fifty", so the counts are the only place that shows.
    """

    def __init__(self, card_count: int) -> None:
        self.decks = FakeDecks()
        self.card_count = card_count
        self.card_reads = 0
        self.deck_reads = 0
        self.note_card_reads = 0

        class CountingDecks:
            def all_names_and_ids(inner) -> list[tuple[str, int]]:
                self.deck_reads += 1
                return [("Languages", 10), ("Archive", 20)]

        self.decks = CountingDecks()

    def find_cards(self, query: str) -> list[int]:
        return list(range(1, self.card_count + 1))

    def find_notes(self, query: str) -> list[int]:
        return list(range(1, self.card_count + 1))

    def card_ids_of_note(self, note_id: int) -> list[int]:
        self.note_card_reads += 1
        return [note_id]

    def get_card(self, card_id: int) -> FakeCard | None:
        if not 1 <= card_id <= self.card_count:
            return None
        self.card_reads += 1
        return FakeCard(card_id, 10, 0, 0, ["reference"])


def test_a_page_of_fifty_reads_fifty_cards_however_many_the_search_matched() -> None:
    collection = CountingCollection(100_000)
    service = CardPickerService(lambda: bound_identity(), lambda: collection)

    result = service.search(page=0, page_size=50)

    assert result.total == 100_000
    assert [card.identity.card_id for card in result.cards] == list(range(1, 51))
    assert collection.card_reads == 50
    # And the deck list once for the page, not once per card.
    assert collection.deck_reads == 1


def test_a_page_of_notes_costs_a_page_of_notes() -> None:
    """Notes mode pays the same way cards mode does.

    Standing a note up as a row means finding its first card, and doing that
    for every note the search matched -- rather than for the fifty on screen --
    would spend the whole of the page's budget on notes nobody asked to see.
    """
    collection = CountingCollection(100_000)
    service = CardPickerService(lambda: bound_identity(), lambda: collection)

    result = service.search(scope="notes", page=0, page_size=50)

    assert result.total == 100_000
    assert collection.note_card_reads == 50
    assert collection.card_reads == 50


def test_a_later_page_reads_its_own_cards_and_no_earlier_ones() -> None:
    collection = CountingCollection(100_000)
    service = CardPickerService(lambda: bound_identity(), lambda: collection)

    result = service.search(page=10, page_size=50)

    assert [card.identity.card_id for card in result.cards] == list(range(501, 551))
    assert collection.card_reads == 50


def test_a_card_that_vanished_between_the_search_and_the_read_leaves_a_gap() -> None:
    """The collection changed under the search, and the page says so.

    Pulling the next page's first card forward to fill the hole would make a
    page of forty-nine look like a page of fifty and disagree with `total`,
    which is the count the search actually returned.
    """
    collection = CountingCollection(100)
    service = CardPickerService(lambda: bound_identity(), lambda: collection)
    original = collection.get_card

    def vanishing(card_id: int) -> FakeCard | None:
        return None if card_id == 3 else original(card_id)

    collection.get_card = vanishing  # type: ignore[method-assign]

    result = service.search(page=0, page_size=5)

    assert result.total == 100
    assert [card.identity.card_id for card in result.cards] == [1, 2, 4, 5]
