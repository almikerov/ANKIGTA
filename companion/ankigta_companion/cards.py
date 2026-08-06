from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from html import unescape
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


#: The class Anki raises when the search expression itself is what it cannot
#: accept: `anki.errors.SearchError`. Recognised by name rather than by
#: importing it, because this module deliberately holds no Anki import -- that
#: is what lets the Card Picker be exercised without a collection at all -- and
#: the name is the whole of what telling a bad expression from a bad collection
#: needs.
SEARCH_REJECTED_ERROR = "SearchError"

#: How much of Anki's own words about a refused expression is passed on. Anki
#: writes a sentence; anything much longer than one is not an explanation.
MAX_SEARCH_REJECTION_LENGTH = 240


#: Anki creates this deck in every collection and hides it from its own deck
#: list once it is empty. Offering it as a filter that matches nothing is
#: offering a choice that cannot work.
DEFAULT_DECK_NAME = "Default"

#: How much of the sort field a row carries. A row in a game panel is one line;
#: a field holding an essay is not a label.
MAX_SORT_FIELD_LENGTH = 120

_MEDIA_TAG = re.compile(r"\[(?:sound|anki)(?::[^\]]*)?\]")
_MARKUP = re.compile(r"<[^>]*>")


def _one_line(value: str) -> str:
    """A note field as a line of a list, rather than as the HTML it is stored
    as.

    Anki stores a field as markup, and a row that reads `<div>hello</div>` or
    `[sound:hello.mp3]` is showing storage rather than the card.
    """
    text = _MEDIA_TAG.sub(" ", value)
    text = _MARKUP.sub(" ", text)
    text = unescape(text).replace(" ", " ")
    return " ".join(text.split())[:MAX_SORT_FIELD_LENGTH]


def _is_row_id(value: object) -> bool:
    """Is this an Anki row id, rather than something that merely looks like one?

    `bool` is a subclass of `int`, so `True` passes an `isinstance(x, int)`
    check and then reads as card 1.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class CardPickerError(ValueError):
    """A safe, user-visible Card Picker failure."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


class SearchScope(StrEnum):
    """What one result row stands for: a card, or the note behind it.

    Anki's browser offers the same switch, and it changes the rows rather than
    the search. A note whose three cards all match is one row here and three
    there; the row a note stands for is still one of its cards, so linking has
    an Anki Card Identity either way.
    """

    CARDS = "cards"
    NOTES = "notes"


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
    #: The note's field values, in the order its note type declares them.
    fields: Sequence[str]

    def note_type(self) -> dict[str, object] | None: ...

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

    def find_notes(self, query: str) -> Sequence[int]: ...

    def card_ids_of_note(self, note_id: int) -> Sequence[int]: ...

    def get_card(self, card_id: int) -> CardLike | None: ...


@dataclass(frozen=True)
class CardView:
    identity: AnkiCardIdentity
    deck_id: int
    deck_name: str | None
    state: CardState
    due: int
    tags: tuple[str, ...]
    #: What Anki lists this note by -- the field its note type nominates as the
    #: sort field. Carried on every row, because the note it comes from is
    #: already loaded for the tags beside it.
    sort_field: str = ""
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
class NoteView:
    """One card's note, with nothing about the card attached.

    What a Text Label needs and no more: the fields in the order the note type
    declares them, because "the first field with words" is a question about
    that order.
    """

    identity: AnkiCardIdentity
    note_id: int
    fields: tuple[NoteField, ...]


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
    #: What a row on this page stands for. Echoed back so the switch on screen
    #: and the rows under it cannot come to disagree.
    scope: SearchScope = SearchScope.CARDS


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
        scope: str = SearchScope.CARDS,
        page: int = 0,
        page_size: int = 50,
    ) -> CardSearchPage:
        if page < 0 or page_size < 1 or page_size > 200:
            raise CardPickerError(
                "invalid_pagination",
                "page must be non-negative and pageSize must be between 1 and 200",
            )
        normalized_scope = self._normalize_scope(scope)
        collection_uuid, collection = self._bound_collection()
        normalized_query = self._normalize_query(query)
        normalized_deck = self._normalize_deck_filter(deck_filter)
        anki_query = self._build_query(normalized_query, normalized_deck)
        try:
            if normalized_scope is SearchScope.NOTES:
                raw_ids = collection.find_notes(anki_query)
            else:
                raw_ids = collection.find_cards(anki_query)
        except Exception as error:
            raise self._search_failure(error) from error

        matched = self._matched_ids(raw_ids)
        start = page * page_size
        page_ids = matched[start : start + page_size]
        if normalized_scope is SearchScope.NOTES:
            page_ids = self._first_card_of_each(collection, page_ids)
        # Read once for the whole answer: the page's names and the deck list
        # are the same list, and asking twice made a page cost two reads.
        names = self._deck_names(collection)
        return CardSearchPage(
            cards=self._read_page(
                collection,
                collection_uuid,
                page_ids,
                names,
            ),
            page=page,
            page_size=page_size,
            total=len(matched),
            query=normalized_query,
            deck_filter=normalized_deck,
            decks=self._offered_decks(collection, names),
            scope=normalized_scope,
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

    def read_identity(
        self,
        identity: AnkiCardIdentity,
        *,
        with_note: bool = False,
    ) -> CardView:
        """One card named by its full identity, optionally with its note.

        The note is off by default because the caller that reads every stored
        link asks this same question of every card it holds, and reading the
        fields of all of them to refresh a state nobody is looking at is what
        the page-sized reads elsewhere in this file exist to avoid. The
        inspector, which is looking at exactly one card, asks for it.
        """
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
        return self._view(collection, collection_uuid, card, with_note=with_note)

    def read_notes(
        self,
        identities: Sequence[AnkiCardIdentity],
    ) -> tuple[NoteView, ...]:
        """The words behind each of these cards, for the Text Label cache.

        A batch rather than one read per card: ANKIGTA refreshes the whole
        cache on connecting, and a reference world holds thousands of Spatial
        Links -- a request each would be thousands of round trips before the
        first label could be drawn.

        A card that cannot be read is left out rather than guessed at. The
        caller keeps whatever it already had for that card, which is a stale
        label rather than a wrong one; a card that has genuinely gone is a
        `card_missing` the link state already reports.

        Nothing here is a deck read. The deck a card sits in has no bearing on
        what its note says, and paying for one per card is what makes a batch
        of five thousand slow.
        """
        collection_uuid, collection = self._bound_collection()
        views: list[NoteView] = []
        for identity in identities:
            if not isinstance(identity, AnkiCardIdentity):
                raise CardPickerError(
                    "invalid_anki_card_identity",
                    "card identity must include collectionUuid and cardId",
                )
            if identity.collection_uuid != collection_uuid:
                # Another collection's card is not this collection's to read,
                # and quietly reading it by id would be exactly the confusion
                # Anki Card Identity exists to prevent.
                continue
            try:
                card = collection.get_card(identity.card_id)
            except Exception:
                continue
            if card is None:
                continue
            try:
                note = card.note()
            except Exception:
                continue
            note_id, fields = self._note_fields(note)
            views.append(
                NoteView(identity=identity, note_id=note_id, fields=fields)
            )
        return tuple(views)

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
    def _normalize_scope(scope: str) -> SearchScope:
        try:
            return SearchScope(scope)
        except ValueError as error:
            raise CardPickerError(
                "invalid_scope",
                "scope must be either cards or notes",
            ) from error

    @staticmethod
    def _search_failure(error: Exception) -> CardPickerError:
        """Was the expression refused, or did the read of the collection fail?

        Told apart because they send the player to different places. A refused
        expression is a bracket they left open, and reporting it as a failed
        read -- or, worse, as an empty collection -- sends them looking for
        cards that were never searched for.
        """
        # The whole ancestry, not just the class: a build that raises a
        # subclass of `SearchError` is still Anki refusing the expression.
        if not any(
            ancestor.__name__ == SEARCH_REJECTED_ERROR
            for ancestor in type(error).__mro__
        ):
            return CardPickerError(
                "card_search_failed",
                "Anki rejected the card search",
            )
        # Anki's own sentence, whitespace-collapsed: it is already written for
        # the person who typed the expression, and rewriting it here would
        # trade a specific complaint for a vague one.
        said = " ".join(str(error).split())[:MAX_SEARCH_REJECTION_LENGTH]
        return CardPickerError(
            "search_rejected",
            said or "Anki did not accept this search expression",
        )

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
        """The deck filter and the written expression, as one Anki search.

        The expression is bracketed. Anki binds an implicit `and` tighter than
        `or`, so `deck:"Spanish" tag:verb or tag:noun` reads as
        `(deck:Spanish and tag:verb) or tag:noun` -- the deck filter applies to
        the left half only, and the search returns cards from every deck while
        the picker still says which deck it was filtered to.
        """
        if deck_filter is None:
            return query
        escaped = deck_filter.replace("\\", "\\\\").replace('"', '\\"')
        return f'deck:"{escaped}"' + (f" ({query})" if query else "")

    @staticmethod
    def _matched_ids(raw_ids: Sequence[int]) -> list[int]:
        """What the search matched, as ids: deduplicated and in a stable order.

        Cards or notes, depending on what was asked for; ids only either way,
        because reading one is what costs. A page of fifty is fifty reads
        however many the search matched, and shaping every match to serve one
        page read a hundred thousand cards for the reference collection's first
        page — the whole of that threshold's budget spent on rows nobody asked
        to see.
        """
        return sorted({m for m in raw_ids if _is_row_id(m)})

    @staticmethod
    def _first_card_of_each(
        collection: CollectionLike,
        note_ids: Sequence[int],
    ) -> list[int]:
        """The card that stands for each note on this page.

        Anki's browser shows a note by its first card, and so does this: the
        order `card_ids_of_note` returns is template order, so the first of
        them is the note's first card rather than whichever card happens to
        have the lowest id.

        Asked for the page's notes only, never for every note the search
        matched — the same rule that keeps a page of fifty cards fifty reads.
        A note whose cards have all gone leaves a gap, as a deleted card does.
        """
        first_cards: list[int] = []
        for note_id in note_ids:
            try:
                card_ids = collection.card_ids_of_note(note_id)
            except Exception as error:
                raise CardPickerError(
                    "card_read_failed",
                    "Anki rejected a note's card list",
                ) from error
            for card_id in card_ids:
                if _is_row_id(card_id):
                    first_cards.append(card_id)
                    break
        return first_cards

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

    def _offered_decks(
        self,
        collection: CollectionLike,
        names: dict[int, str],
    ) -> tuple[DeckView, ...]:
        """The decks worth offering as a filter.

        Sorted by name, not by id: the name is what is read, and Anki's `::`
        nesting sorts into a tree correctly as plain text.

        Anki creates a deck called `Default` in every collection and hides it
        from its own deck list once it holds nothing and nothing lives under
        it. Offering it here is offering a filter that returns an empty list --
        a choice that can only disappoint, and one nobody made.
        """
        offered = sorted(names.items(), key=lambda pair: pair[1])
        if not self._default_deck_is_used(collection, names):
            offered = [pair for pair in offered if pair[1] != DEFAULT_DECK_NAME]
        return tuple(
            DeckView(deck_id=deck_id, name=name) for deck_id, name in offered
        )

    @staticmethod
    def _default_deck_is_used(
        collection: CollectionLike,
        names: dict[int, str],
    ) -> bool:
        """Does Anki's own `Default` deck hold anything, or carry anything?

        Kept rather than hidden whenever the answer cannot be had: hiding a
        deck that has cards in it loses the player a filter they need, while
        showing an empty one merely wastes a line.
        """
        prefix = DEFAULT_DECK_NAME + "::"
        if any(name.startswith(prefix) for name in names.values()):
            return True
        try:
            return bool(collection.find_cards(f'deck:"{DEFAULT_DECK_NAME}"'))
        except Exception:
            return True

    @staticmethod
    def _sort_field(note: NoteLike) -> str:
        """What Anki lists this note by.

        Which field that is belongs to the note type, as `sortf`, so a
        collection that sorts by Reading rather than by Expression lists the
        same way here as it does in Anki's own browser.

        Free, unlike the full field read beside it: the note was already loaded
        to name the card's tags, so this is one more value off an object that
        is already in hand. A build that spells a note differently leaves the
        row without a label rather than guessing at one -- a row showing its
        card id is recoverable, one showing the wrong field is not.
        """
        try:
            fields = list(note.fields)
        except Exception:
            return ""
        if not fields:
            return ""
        index = 0
        try:
            note_type = note.note_type()
            if isinstance(note_type, dict):
                nominated = note_type.get("sortf", 0)
                if isinstance(nominated, (int, str)):
                    index = int(nominated)
        except Exception:
            index = 0
        if not 0 <= index < len(fields):
            index = 0
        # The nominated field first, then the first one that has words in it.
        # A note whose sort field is empty -- or holds only an image or a
        # `[sound:]` tag -- would otherwise be labelled by its card id, which
        # names nothing anybody chose the card for. ADR 0029 settled the same
        # question the same way for the Text Label.
        order = [index] + [other for other in range(len(fields)) if other != index]
        for candidate in order:
            try:
                text = _one_line(str(fields[candidate]))
            except Exception:
                return ""
            if text:
                return text
        return ""

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
            sort_field=self._sort_field(note),
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

        def remember(raw_id: object, raw_name: object) -> None:
            if not isinstance(raw_name, str):
                return
            try:
                identifier = int(raw_id)  # type: ignore[call-overload]
            except (TypeError, ValueError):
                return
            names.setdefault(identifier, raw_name)

        if isinstance(raw_decks, dict):
            for first, second in raw_decks.items():
                remember(first, second)
                remember(second, first)
            return names
        if isinstance(raw_decks, Sequence) and not isinstance(raw_decks, (str, bytes)):
            for raw in raw_decks:
                if isinstance(raw, tuple) and len(raw) == 2:
                    name, raw_id = raw
                    remember(raw_id, name)
                elif isinstance(raw, dict):
                    remember(raw.get("id"), raw.get("name"))
                else:
                    remember(
                        getattr(raw, "id", None),
                        getattr(raw, "name", None),
                    )
        return names
