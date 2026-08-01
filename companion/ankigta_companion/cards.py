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
    tags: Sequence[str]


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


@dataclass(frozen=True)
class CardSearchPage:
    cards: tuple[CardView, ...]
    page: int
    page_size: int
    total: int
    query: str
    deck_filter: str | None


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

        cards = self._read_existing_cards(
            collection,
            collection_uuid,
            raw_ids,
        )
        start = page * page_size
        return CardSearchPage(
            cards=tuple(cards[start : start + page_size]),
            page=page,
            page_size=page_size,
            total=len(cards),
            query=normalized_query,
            deck_filter=normalized_deck,
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
        return self._view(collection, collection_uuid, card)

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

    def _read_existing_cards(
        self,
        collection: CollectionLike,
        collection_uuid: str,
        raw_ids: Sequence[int],
    ) -> list[CardView]:
        result: list[CardView] = []
        for raw_id in sorted(
            {
                card_id
                for card_id in raw_ids
                if isinstance(card_id, int)
                and not isinstance(card_id, bool)
                and card_id > 0
            }
        ):
            try:
                card = collection.get_card(raw_id)
            except Exception as error:
                raise CardPickerError(
                    "card_read_failed",
                    "Anki rejected a card state refresh",
                ) from error
            if card is not None:
                result.append(self._view(collection, collection_uuid, card))
        return result

    def _view(
        self,
        collection: CollectionLike,
        collection_uuid: str,
        card: CardLike,
    ) -> CardView:
        try:
            card_id = int(card.id)
            deck_id = int(card.did)
            due = int(card.due)
            queue = int(card.queue)
            tags = tuple(str(tag) for tag in card.note().tags)
        except Exception as error:
            raise CardPickerError(
                "card_state_invalid",
                "Anki returned an invalid card state",
            ) from error
        return CardView(
            identity=AnkiCardIdentity(collection_uuid, card_id),
            deck_id=deck_id,
            deck_name=self._deck_name(collection, deck_id),
            state=self._state(queue, due),
            due=due,
            tags=tags,
        )

    def _state(self, queue: int, due: int) -> CardState:
        if queue == -1:
            return CardState.SUSPENDED
        if queue == -2:
            return CardState.BURIED
        if queue == 0:
            return CardState.NEW
        if queue == 1:
            return CardState.LEARNING
        if queue == 2 and due > self._today():
            return CardState.NOT_DUE
        return CardState.REVIEW

    def _deck_name(self, collection: CollectionLike, deck_id: int) -> str | None:
        try:
            raw_decks = collection.decks.all_names_and_ids()
        except Exception:
            return None
        if isinstance(raw_decks, dict):
            value = raw_decks.get(deck_id)
            if isinstance(value, str):
                return value
            for raw_name, raw_id in raw_decks.items():
                try:
                    if int(raw_id) == deck_id:
                        return str(raw_name)
                except (TypeError, ValueError):
                    continue
            return None
        if isinstance(raw_decks, Sequence) and not isinstance(raw_decks, (str, bytes)):
            for raw in raw_decks:
                if isinstance(raw, tuple) and len(raw) == 2:
                    name, raw_id = raw
                    if int(raw_id) == deck_id:
                        return str(name)
                elif isinstance(raw, dict) and int(raw.get("id", -1)) == deck_id:
                    name = raw.get("name")
                    return str(name) if isinstance(name, str) else None
        return None
