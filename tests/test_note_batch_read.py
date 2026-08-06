"""Panel rebuild 06 — reading the words behind many cards at once.

ANKIGTA caches a note's fields so a Text Label can be drawn with Anki shut
(ADR 0017, ADR 0029). Refreshing that cache is one question about every Spatial
Link there is, so it is one request rather than one per card: a reference world
holds thousands of links, and a round trip each would be thousands of them
before the first label could be drawn.

What it answers with is the note's fields **in the order its note type declares
them**, because "the first field with words" is a question about that order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from http.client import HTTPConnection

import pytest

from ankigta_companion.cards import CardPickerError, CardPickerService
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
from ankigta_companion.http_server import HealthServer


BOUND_UUID = "11111111-1111-4111-8111-111111111111"
OTHER_UUID = "22222222-2222-4222-8222-222222222222"


@dataclass
class FakeNote:
    id: int = 0
    tags: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=lambda: ["Front", "Back"])
    values: list[str] = field(
        default_factory=lambda: ["<div>hola</div>", "hello"]
    )

    def items(self) -> list[tuple[str, str]]:
        return list(zip(self.names, self.values))

    def keys(self) -> list[str]:
        return list(self.names)


class FakeCard:
    """A card as Anki hands one over: `note()` is a call, not an attribute."""

    def __init__(self, card_id: int, note: FakeNote | None = None) -> None:
        self.id = card_id
        self.did = 10
        self.queue = 0
        self.due = 0
        self.stored_note = note or FakeNote(id=card_id * 10)

    def note(self) -> FakeNote:
        return self.stored_note


class FakeCollection:
    def __init__(self) -> None:
        self.cards = {
            2: FakeCard(2),
            4: FakeCard(4),
        }
        self.reads: list[int] = []

    def get_card(self, card_id: int) -> FakeCard | None:
        self.reads.append(card_id)
        return self.cards.get(card_id)


def bound_identity(uuid: str = BOUND_UUID) -> CollectionIdentityObservation:
    return CollectionIdentityObservation(CollectionIdentityState.BOUND, uuid)


def service(collection: FakeCollection) -> CardPickerService:
    return CardPickerService(lambda: bound_identity(), lambda: collection)


def identity(card_id: int, uuid: str = BOUND_UUID) -> AnkiCardIdentity:
    return AnkiCardIdentity(uuid, card_id)


def test_a_batch_answers_with_every_note_it_could_read() -> None:
    collection = FakeCollection()

    notes = service(collection).read_notes([identity(2), identity(4)])

    assert [note.identity.card_id for note in notes] == [2, 4]
    assert [field.name for field in notes[0].fields] == ["Front", "Back"]


def test_the_fields_arrive_in_the_order_the_note_type_declares() -> None:
    """"The first field with words" is a question about that order, and a
    mapping with the order lost cannot answer it."""
    collection = FakeCollection()
    collection.cards[2].stored_note = FakeNote(
        id=20, names=["Reading", "Expression"], values=["", "hola"]
    )

    notes = service(collection).read_notes([identity(2)])

    assert [field.name for field in notes[0].fields] == ["Reading", "Expression"]


def test_the_markup_anki_stores_is_carried_across_untouched() -> None:
    """Stripping it is `shared/text_label.lua`'s, on the side that draws. What
    is cached is what the note says, so the rules can change without the cache
    having to be read again."""
    collection = FakeCollection()

    notes = service(collection).read_notes([identity(2)])

    assert notes[0].fields[0].value == "<div>hola</div>"


def test_a_card_that_cannot_be_read_is_left_out_rather_than_guessed_at() -> None:
    """The caller keeps whatever it already had for it, which is a stale label
    rather than a wrong one; a card that has genuinely gone is a `card_missing`
    the link state already reports."""
    collection = FakeCollection()

    notes = service(collection).read_notes([identity(2), identity(99)])

    assert [note.identity.card_id for note in notes] == [2]


def test_another_collections_card_is_never_read_by_its_id() -> None:
    """Quietly reading it would be exactly the confusion Anki Card Identity
    exists to prevent."""
    collection = FakeCollection()

    notes = service(collection).read_notes(
        [identity(2), identity(4, OTHER_UUID)]
    )

    assert [note.identity.card_id for note in notes] == [2]
    assert 4 not in collection.reads


def test_a_batch_costs_one_read_per_card_and_no_deck_lookups() -> None:
    """The deck a card sits in has no bearing on what its note says, and paying
    for one per card is what makes a batch of five thousand slow."""
    collection = FakeCollection()

    service(collection).read_notes([identity(2), identity(4)])

    assert collection.reads == [2, 4]


def test_something_that_is_not_a_card_identity_is_refused_outright() -> None:
    collection = FakeCollection()

    with pytest.raises(CardPickerError, match="card identity"):
        service(collection).read_notes(["2"])  # type: ignore[list-item]


def test_an_empty_batch_answers_with_nothing_rather_than_failing() -> None:
    assert service(FakeCollection()).read_notes([]) == ()


# --- over the wire -----------------------------------------------------------


def post(
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
                "requestId": "notes-001",
                **body,
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    payload = json.loads(response.read())
    connection.close()
    return response.status, payload


def observation() -> RuntimeObservation:
    return RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )


def test_the_endpoint_answers_in_the_versioned_control_envelope() -> None:
    picker = service(FakeCollection())

    with HealthServer(lambda: observation(), card_picker=picker) as server:
        status, answer = post(
            server,
            "/v1/notes/read",
            {
                "cardIdentities": [
                    {"collectionUuid": BOUND_UUID, "cardId": 2},
                    {"collectionUuid": BOUND_UUID, "cardId": 4},
                ]
            },
        )

    assert status == 200
    assert answer["ok"] is True
    notes = answer["payload"]["notes"]
    assert [note["identity"]["cardId"] for note in notes] == [2, 4]
    assert notes[0]["fields"] == [
        {"name": "Front", "value": "<div>hola</div>"},
        {"name": "Back", "value": "hello"},
    ]


def test_a_malformed_batch_is_refused_rather_than_partly_answered() -> None:
    picker = service(FakeCollection())

    with HealthServer(lambda: observation(), card_picker=picker) as server:
        status, answer = post(server, "/v1/notes/read", {"cardIdentities": {}})

    assert status == 400
    assert answer["ok"] is False


def test_a_card_the_batch_asked_for_and_could_not_read_is_simply_absent() -> None:
    """Rather than handed back empty, which would draw a linked object as
    having nothing to say."""
    picker = service(FakeCollection())

    with HealthServer(lambda: observation(), card_picker=picker) as server:
        _, answer = post(
            server,
            "/v1/notes/read",
            {
                "cardIdentities": [
                    {"collectionUuid": BOUND_UUID, "cardId": 2},
                    {"collectionUuid": BOUND_UUID, "cardId": 99},
                ]
            },
        )

    assert [note["identity"]["cardId"] for note in answer["payload"]["notes"]] == [2]
