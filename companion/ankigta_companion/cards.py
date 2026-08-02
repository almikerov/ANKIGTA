from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from time import time
from typing import Protocol

from .collection_identity import (
    AnkiCardIdentity,
    CollectionIdentityObservation,
    CollectionIdentityState,
)


# Anki 26.05 `anki.consts` queue values, restated so the mapping below reads as
# the source does rather than as bare numbers.
QUEUE_TYPE_MANUALLY_BURIED = -3
QUEUE_TYPE_SIBLING_BURIED = -2
QUEUE_TYPE_SUSPENDED = -1
QUEUE_TYPE_NEW = 0
QUEUE_TYPE_LRN = 1
QUEUE_TYPE_REV = 2
QUEUE_TYPE_DAY_LEARN_RELEARN = 3
QUEUE_TYPE_PREVIEW = 4


def card_state(queue: int, due: int, today: int) -> CardState:
    """Map an Anki queue value to the state ANKIGTA reasons about.

    Both buried queues must be recognised. A manually buried card once fell
    through to REVIEW here, which would have let it into a session and been
    rated -- exactly what burying is meant to prevent.
    """
    if queue == QUEUE_TYPE_SUSPENDED:
        return CardState.SUSPENDED
    if queue in {QUEUE_TYPE_SIBLING_BURIED, QUEUE_TYPE_MANUALLY_BURIED}:
        return CardState.BURIED
    if queue == QUEUE_TYPE_NEW:
        return CardState.NEW
    if queue in {QUEUE_TYPE_LRN, QUEUE_TYPE_DAY_LEARN_RELEARN}:
        return CardState.LEARNING
    if queue == QUEUE_TYPE_REV:
        return CardState.NOT_DUE if due > today else CardState.REVIEW
    # Anki's own preview queue, and anything this build does not recognise:
    # not a due review, and never assumed rateable.
    return CardState.NOT_DUE


class CardPickerError(ValueError):
    """A safe, user-visible Card Picker failure."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


class CardState(StrEnum):
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    NOT_DUE = "not_due"
    SUSPENDED = "suspended"
    BURIED = "buried"


class NoteLike(Protocol):
    id: int
    tags: Sequence[str]

    def keys(self) -> Sequence[str]: ...

    def items(self) -> Sequence[tuple[str, str]]: ...


class CardLike(Protocol):
    id: int
    did: int
    queue: int
    due: int

    def note(self) -> NoteLike: ...


class DecksLike(Protocol):
    def all_names_and_ids(self) -> object: ...


class CollectionLike(Protocol):
    decks: DecksLike

    def find_cards(self, query: str) -> Sequence[int]: ...

    def get_card(self, card_id: int) -> CardLike | None: ...


@dataclass(frozen=True)
class CardView:
    identity: AnkiCardIdentity
    deck_id: int
    deck_name: str | None
    state: CardState
    due: int
    tags: tuple[str, ...]
    #: The note behind the card, for the one card being inspected. Empty on a
    #: search page: reading every field of every card to draw a list would pay
    #: for a whole page what only one card is ever looked at.
    note_id: int = 0
    fields: tuple[NoteField, ...] = ()


@dataclass(frozen=True)
class NoteField:
    name: str
    value: str


@dataclass(frozen=True)
class DeckView:
    deck_id: int
    name: str


@dataclass(frozen=True)
class CardSearchPage:
    cards: tuple[CardView, ...]
    page: int
    page_size: int
    total: int
    query: str
    deck_filter: str | None
    #: Every deck in the collection, so the filter can be chosen from a list
    #: rather than typed. Carried with the page because the search already read
    #: them all to name its cards.
    decks: tuple[DeckView, ...] = ()


IdentityProvider = Callable[[], CollectionIdentityObservation | None]
CollectionProvider = Callable[[], CollectionLike | None]


class CardPickerService:
    """Read-only card search/read operations scoped to the bound collection."""

    def __init__(
        self,
        identity_provider: IdentityProvider,
        collection_provider: CollectionProvider,
        *,
        today: Callable[[], int] | None = None,
    ) -> None:
        self._identity_provider = identity_provider
        self._collection_provider = collection_provider
        self._today = today or (lambda: int(time() // 86400))

    def search(
        self,
        *,
        query: str = "",
        deck_filter: str | None = None,
        page: int = 0,
        page_size: int = 50,
    ) -> CardSearchPage:
        if page < 0 or page_size < 1 or page_size > 200:
            raise CardPickerError(
                "invalid_pagination",
                "page must be non-negative and pageSize must be between 1 and 200",
            )
        collection_uuid, collection = self._bound_collection()
        normalized_query = self._normalize_query(query)
        normalized_deck = self._normalize_deck_filter(deck_filter)
        anki_query = self._build_query(normalized_query, normalized_deck)
        try:
            raw_ids = collection.find_cards(anki_query)
        except Exception as error:
            raise CardPickerError(
                "card_search_failed",
                "Anki rejected the card search",
            ) from error

        matched = self._matched_card_ids(raw_ids)
        start = page * page_size
        # Read once for the whole answer: the page's names and the deck list
        # are the same list, and asking twice made a page cost two reads.
        names = self._deck_names(collection)
        return CardSearchPage(
            cards=self._read_page(
                collection,
                collection_uuid,
                matched[start : start + page_size],
                names,
            ),
            page=page,
            page_size=page_size,
            total=len(matched),
            query=normalized_query,
            deck_filter=normalized_deck,
            decks=tuple(
                DeckView(deck_id=deck_id, name=name)
                # By name, not by id: the name is what is read, and Anki's `::`
                # nesting sorts into a tree correctly as plain text.
                for deck_id, name in sorted(names.items(), key=lambda p: p[1])
            ),
        )

    def read(self, card_id: int) -> CardView:
        if isinstance(card_id, bool) or not isinstance(card_id, int) or card_id <= 0:
            raise CardPickerError("invalid_card_id", "cardId must be a positive integer")
        collection_uuid, collection = self._bound_collection()
        try:
            card = collection.get_card(card_id)
        except Exception as error:
            raise CardPickerError(
                "card_read_failed",
                "Anki rejected the card read",
            ) from error
        if card is None:
            raise CardPickerError("card_missing", "card is missing from the bound collection")
        # Reading one card is where the note is worth the read: this is the
        # card being inspected, not one of fifty being listed.
        return self._view(collection, collection_uuid, card, with_note=True)

    def refresh_card_state(self, identity: AnkiCardIdentity) -> bool:
        """Refresh one persisted link without ever matching a new card heuristically."""
        if not isinstance(identity, AnkiCardIdentity):
            raise CardPickerError(
                "invalid_anki_card_identity",
                "card identity must include collectionUuid and cardId",
            )
        self.read_identity(identity)
        return True

    def read_identity(self, identity: AnkiCardIdentity) -> CardView:
        if not isinstance(identity, AnkiCardIdentity):
            raise CardPickerError(
                "invalid_anki_card_identity",
                "card identity must include collectionUuid and cardId",
            )
        collection_uuid, collection = self._bound_collection()
        if identity.collection_uuid != collection_uuid:
            raise CardPickerError(
                "wrong_collection",
                "card identity belongs to a different collection",
            )
        try:
            card = collection.get_card(identity.card_id)
        except Exception as error:
            raise CardPickerError(
                "card_read_failed",
                "Anki rejected the card state refresh",
            ) from error
        if card is None:
            raise CardPickerError(
                "card_missing",
                "card is missing from the bound collection",
            )
        return self._view(collection, collection_uuid, card)

    def _bound_collection(self) -> tuple[str, CollectionLike]:
        observation = self._identity_provider()
        if (
            observation is None
            or observation.state is not CollectionIdentityState.BOUND
            or not observation.collection_uuid
        ):
            raise CardPickerError(
                "collection_not_bound",
                "Card Picker requires the current Bound Anki Collection",
            )
        collection = self._collection_provider()
        if collection is None:
            raise CardPickerError(
                "collection_unavailable",
                "the Bound Anki Collection is not open",
            )
        return observation.collection_uuid, collection

    @staticmethod
    def _normalize_query(query: str) -> str:
        if not isinstance(query, str):
            raise CardPickerError("invalid_query", "query must be a string")
        return query.strip()

    @staticmethod
    def _normalize_deck_filter(deck_filter: str | None) -> str | None:
        if deck_filter is None:
            return None
        if not isinstance(deck_filter, str):
            raise CardPickerError("invalid_deck_filter", "deckFilter must be a string")
        normalized = deck_filter.strip()
        return normalized or None

    @staticmethod
    def _build_query(query: str, deck_filter: str | None) -> str:
        if deck_filter is None:
            return query
        escaped = deck_filter.replace("\\", "\\\\").replace('"', '\\"')
        return f'deck:"{escaped}"' + (f" {query}" if query else "")

    @staticmethod
    def _matched_card_ids(raw_ids: Sequence[int]) -> list[int]:
        """What the search matched, as ids: deduplicated and in a stable order.

        Ids only, because reading a card is what costs. A page of fifty is
        fifty cards however many the search matched, and shaping every match to
        serve one page read a hundred thousand cards for the reference
        collection's first page — the whole of that threshold's budget spent on
        cards nobody asked to see.
        """
        return sorted(
            {
                card_id
                for card_id in raw_ids
                if isinstance(card_id, int)
                and not isinstance(card_id, bool)
                and card_id > 0
            }
        )

    def _read_page(
        self,
        collection: CollectionLike,
        collection_uuid: str,
        card_ids: Sequence[int],
        deck_names: dict[int, str],
    ) -> tuple[CardView, ...]:
        """Read exactly these cards.

        A card the search matched and that is gone by the time it is read
        leaves a gap on its own page rather than pulling the next page's first
        card forward: the collection changed under the search, and hiding that
        by silently reflowing would make the page disagree with `total`.
        """
        result: list[CardView] = []
        for card_id in card_ids:
            try:
                card = collection.get_card(card_id)
            except Exception as error:
                raise CardPickerError(
                    "card_read_failed",
                    "Anki rejected a card state refresh",
                ) from error
            if card is not None:
                result.append(
                    self._view(collection, collection_uuid, card, deck_names)
                )
        return tuple(result)

    @staticmethod
    def _note_fields(note: NoteLike) -> tuple[int, tuple[NoteField, ...]]:
        """The note's own fields, in the order its note type declares them.

        Anki has spelt a note's fields more than one way. `items()` gives name
        and value together where it exists; otherwise `keys()` names them and
        the note indexes by name. A build that answers to neither leaves the
        fields empty rather than guessing -- an inspector showing nothing is
        recoverable, one showing the wrong field under the right name is not.
        """
        try:
            note_id = int(note.id)
        except Exception:
            note_id = 0
        try:
            pairs = note.items()
        except Exception:
            pairs = None
        if pairs is not None:
            try:
                return note_id, tuple(
                    NoteField(name=str(name), value=str(value))
                    for name, value in pairs
                )
            except Exception:
                return note_id, ()
        try:
            return note_id, tuple(
                NoteField(name=str(name), value=str(note[name]))  # type: ignore[index]
                for name in note.keys()
            )
        except Exception:
            return note_id, ()

    def _view(
        self,
        collection: CollectionLike,
        collection_uuid: str,
        card: CardLike,
        deck_names: dict[int, str] | None = None,
        *,
        with_note: bool = False,
    ) -> CardView:
        try:
            card_id = int(card.id)
            deck_id = int(card.did)
            due = int(card.due)
            queue = int(card.queue)
            note = card.note()
            tags = tuple(str(tag) for tag in note.tags)
        except Exception as error:
            raise CardPickerError(
                "card_state_invalid",
                "Anki returned an invalid card state",
            ) from error
        if deck_names is None:
            deck_names = self._deck_names(collection)
        note_id, fields = self._note_fields(note) if with_note else (0, ())
        return CardView(
            identity=AnkiCardIdentity(collection_uuid, card_id),
            deck_id=deck_id,
            deck_name=deck_names.get(deck_id),
            state=self._state(queue, due),
            due=due,
            tags=tags,
            note_id=note_id,
            fields=fields,
        )

    def _state(self, queue: int, due: int) -> CardState:
        return card_state(queue, due, self._today())

    @staticmethod
    def _deck_names(collection: CollectionLike) -> dict[int, str]:
        """Every deck's name by id, read once.

        Once per search rather than once per card: the deck list is one answer
        for the whole page, and asking Anki for all of it per card made naming
        a page of cards cost the deck list times the page.

        Anki has spelt this list three ways across builds, so all three are
        read: a mapping either way round, and a sequence of pairs or records.
        A shape this build does not recognise leaves the names empty rather
        than guessing, and a card with no name still carries its deck id.
        """
        try:
            raw_decks = collection.decks.all_names_and_ids()
        except Exception:
            return {}
        names: dict[int, str] = {}
        if isinstance(raw_decks, dict):
            for first, second in raw_decks.items():
                for raw_id, raw_name in ((first, second), (second, first)):
                    if isinstance(raw_name, str):
                        try:
                            names.setdefault(int(raw_id), raw_name)
                        except (TypeError, ValueError):
                            continue
            return names
        if isinstance(raw_decks, Sequence) and not isinstance(raw_decks, (str, bytes)):
            for raw in raw_decks:
                if isinstance(raw, tuple) and len(raw) == 2:
                    name, raw_id = raw
                    try:
                        names.setdefault(int(raw_id), str(name))
                    except (TypeError, ValueError):
                        continue
                elif isinstance(raw, dict):
                    name = raw.get("name")
                    try:
                        identifier = int(raw.get("id", -1))
                    except (TypeError, ValueError):
                        continue
                    if isinstance(name, str):
                        names.setdefault(identifier, name)
        return names
