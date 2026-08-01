"""The reference world ticket 30 states its thresholds against.

10,000 Map Entity, 5,000 Spatial Link and 100,000 Anki cards. It is generated
rather than checked in: a 100,000-card collection is not a file to keep in a
repository, and a generated one can be rebuilt identically on another machine,
which is what "reproducible" has to mean.

Nothing here loads CEF. The cards are card *records* — the thing the Card
Picker searches and the session is built from. A card is rendered only when one
is opened, which is a separate measurement with exactly one card in it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Iterator, Sequence

from ankigta_companion.cards import (
    QUEUE_TYPE_LRN,
    QUEUE_TYPE_NEW,
    QUEUE_TYPE_REV,
)
from ankigta_companion.collection_identity import AnkiCardIdentity


REFERENCE_MAP_ENTITIES = 10_000
REFERENCE_SPATIAL_LINKS = 5_000
REFERENCE_ANKI_CARDS = 100_000

#: The collection every generated card and link belongs to. Fixed rather than
#: random, so two runs on two machines produce the same identities.
REFERENCE_COLLECTION_UUID = "30000000-3000-4000-8000-300000000030"

MAP_ID = "ticket30-reference"
DECK_COUNT = 20
FIRST_CARD_ID = 1_000_000


def entity_id(index: int) -> str:
    """A Map Entity id, wide enough that ordering by id is ordering by index."""
    return f"ref-{index:06d}"


def card_id(index: int) -> int:
    return FIRST_CARD_ID + index


def deck_name(deck_index: int) -> str:
    return f"Reference::deck-{deck_index:02d}"


@dataclass(frozen=True)
class GeneratedCard:
    """One Anki card record, as the Card Picker's collection protocol sees it."""

    id: int
    did: int
    queue: int
    due: int
    tags: tuple[str, ...]

    def note(self) -> GeneratedCard:
        # `CardLike.note()` only has to answer `tags`.
        return self


class _Decks:
    def __init__(self, names: Sequence[tuple[str, int]]) -> None:
        self._names = list(names)

    def all_names_and_ids(self) -> list[tuple[str, int]]:
        return list(self._names)


class GeneratedCollection:
    """A collection of card records, answering only what ANKIGTA asks of one.

    It is not a stand-in for Anki's scheduler and never pretends to be: the
    session and admission measurements go through the real `SessionCoordinator`
    with a backend that records what it was asked to build.
    """

    def __init__(self, cards: dict[int, GeneratedCard], decks: _Decks) -> None:
        self._cards = cards
        self.decks = decks

    def find_cards(self, query: str) -> list[int]:
        """Anki's own search, reduced to what the Card Picker actually sends.

        The Card Picker sends an empty query or `deck:"<name>"`. Anything else
        is not something this generator can honestly answer, so it says so
        rather than returning a plausible subset.
        """
        stripped = query.strip()
        if not stripped:
            return list(self._cards)
        if stripped.startswith('deck:"') and stripped.endswith('"'):
            wanted = stripped[len('deck:"') : -1].replace('\\"', '"')
            wanted_id = _deck_id_for_name(wanted)
            if wanted_id is None:
                return []
            return [
                identifier
                for identifier, card in self._cards.items()
                if card.did == wanted_id
            ]
        raise NotImplementedError(f"reference collection cannot answer {query!r}")

    def get_card(self, identifier: int) -> GeneratedCard | None:
        return self._cards.get(int(identifier))


def _deck_id_for_name(name: str) -> int | None:
    for index in range(DECK_COUNT):
        if deck_name(index) == name:
            return 100 + index
    return None


@dataclass(frozen=True)
class ReferenceDataset:
    """The generated world, and the identities that join its two halves."""

    collection: GeneratedCollection
    collection_uuid: str
    map_entities: int
    spatial_links: int
    anki_cards: int
    #: The Anki Card Identity of every active Spatial Link, deduplicated the way
    #: the server deduplicates them before a session is built.
    linked_identities: tuple[AnkiCardIdentity, ...]

    def sql(self) -> Iterator[tuple[str, Sequence[Any]]]:
        yield from _rows(self.map_entities, self.spatial_links)


def _card_shape(index: int) -> GeneratedCard:
    """Spread the cards over the states a real collection is in.

    A collection of 100,000 new cards would make every eligibility check take
    the same branch, which is not the collection the thresholds are about.
    """
    bucket = index % 10
    if bucket < 4:
        queue, due = QUEUE_TYPE_NEW, index
    elif bucket < 6:
        queue, due = QUEUE_TYPE_LRN, index
    elif bucket < 9:
        # Due today or earlier: `card_state` compares `due` against today.
        queue, due = QUEUE_TYPE_REV, 0
    else:
        # Not due until well past any plausible "today".
        queue, due = QUEUE_TYPE_REV, 10_000_000
    return GeneratedCard(
        id=card_id(index),
        did=100 + (index % DECK_COUNT),
        queue=queue,
        due=due,
        tags=("reference", f"bucket-{bucket}"),
    )


def _rows(
    map_entities: int,
    spatial_links: int,
) -> Iterator[tuple[str, Sequence[Any]]]:
    yield (
        "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
        " VALUES (?, ?, ?)",
        [(MAP_ID, "ankigta", "Ticket 30 reference map")],
    )
    yield (
        "INSERT OR IGNORE INTO map_entities (map_id, entity_id, entity_type,"
        " model, authored_x, authored_y, authored_z, rotation_x, rotation_y,"
        " rotation_z, interior, dimension)"
        " VALUES (?, ?, 'object', 1337, ?, ?, ?, 0, 0, 0, 0, 0)",
        [
            (
                MAP_ID,
                entity_id(index),
                # Spread over a plausible stretch of world rather than stacked
                # on one point: a nearest-candidate scan over ten thousand
                # identical positions is not the scan the game does.
                float(index % 500) * 4.0,
                float(index // 500) * 4.0,
                float(index % 7),
            )
            for index in range(map_entities)
        ],
    )
    yield (
        "INSERT OR IGNORE INTO spatial_links (map_id, entity_id,"
        " collection_uuid, card_id, state, verified_map_sha256)"
        " VALUES (?, ?, ?, ?, 'active', ?)",
        [
            (
                MAP_ID,
                entity_id(index),
                REFERENCE_COLLECTION_UUID,
                card_id(_linked_card_index(index)),
                "a" * 64,
            )
            for index in range(spatial_links)
        ],
    )


def _linked_card_index(link_index: int) -> int:
    """Which card a link points at.

    Every twentieth link reuses the previous card, because one Anki Card linked
    to several Map Entity is the case the counts and the session membership
    have to deduplicate — and a fixture where it never happens would let a
    duplicate-counting bug pass.
    """
    if link_index % 20 == 0 and link_index > 0:
        return link_index - 1
    return link_index


def fill_store(
    sandbox: Any,
    *,
    map_entities: int,
    spatial_links: int,
) -> None:
    """Write the world straight into the store's open database.

    Through SQL rather than through `Store.linkCardToEntity`: ten thousand
    entities arrive from a Map Editor save, not from ten thousand user actions,
    and recording ten thousand Change History entries would generate a fixture
    ANKIGTA never produces. One explicit transaction, because the sandbox's
    connection is in autocommit and committing each row separately spends a
    minute of disk sync on setup.
    """
    connection: sqlite3.Connection = sandbox.connection.raw
    connection.execute("BEGIN")
    try:
        for statement, parameters in _rows(map_entities, spatial_links):
            connection.executemany(statement, parameters)
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")


def reference_dataset(
    *,
    map_entities: int = REFERENCE_MAP_ENTITIES,
    spatial_links: int = REFERENCE_SPATIAL_LINKS,
    anki_cards: int = REFERENCE_ANKI_CARDS,
) -> ReferenceDataset:
    cards = {
        card_id(index): _card_shape(index) for index in range(anki_cards)
    }
    decks = _Decks([(deck_name(index), 100 + index) for index in range(DECK_COUNT)])
    seen: dict[int, None] = {}
    for index in range(spatial_links):
        seen.setdefault(card_id(_linked_card_index(index)), None)
    return ReferenceDataset(
        collection=GeneratedCollection(cards, decks),
        collection_uuid=REFERENCE_COLLECTION_UUID,
        map_entities=map_entities,
        spatial_links=spatial_links,
        anki_cards=anki_cards,
        linked_identities=tuple(
            AnkiCardIdentity(REFERENCE_COLLECTION_UUID, identifier)
            for identifier in seen
        ),
    )
