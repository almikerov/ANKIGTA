from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from threading import Event, Lock
from typing import Protocol

from .cards import CardState, CardView
from .collection_identity import AnkiCardIdentity, CollectionIdentityState
from .contract import RuntimeObservation


FILTERED_DECK_NAME = "ANKIGTA Session"
REBUILD_TIMEOUT_SECONDS = 30.0


class SessionError(RuntimeError):
    """A categorized, user-visible session failure."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


@dataclass(frozen=True)
class FilteredDeckInfo:
    deck_id: int
    owned: bool


class FilteredDeckBackend(Protocol):
    def inspect(self, name: str) -> FilteredDeckInfo | None: ...

    def build(
        self,
        name: str,
        card_ids: tuple[int, ...],
        *,
        progress: Callable[[int, int], None],
        cancel: Event,
    ) -> None: ...

    def cleanup(self, name: str) -> None: ...

    def scheduler_top(self) -> AnkiCardIdentity | None:
        """The card Anki currently considers next, without advancing it."""
        ...


class AnkiFilteredDeckBackend:
    """Small adapter around Anki's supported filtered-deck operations.

    The scheduler and filtered-deck implementation stay in Anki.  The adapter
    only supplies exact card IDs and owns a durable marker in collection
    configuration; it never writes Anki's scheduling tables.
    """

    OWNER_CONFIG_KEY = "ankigta.session.filtered_deck"

    def __init__(
        self,
        collection: object,
        *,
        create_filtered_deck: Callable[[str], int],
        rebuild_filtered_deck: Callable[[int, tuple[int, ...]], None],
        empty_filtered_deck: Callable[[int], None],
        delete_filtered_deck: Callable[[int], None],
        top_card_id: Callable[[], int | None] | None = None,
        collection_uuid: Callable[[], str | None] | None = None,
    ) -> None:
        self._collection = collection
        self._create = create_filtered_deck
        self._rebuild = rebuild_filtered_deck
        self._empty = empty_filtered_deck
        self._delete = delete_filtered_deck
        self._top_card_id = top_card_id or (lambda: None)
        self._collection_uuid = collection_uuid or (lambda: None)

    @classmethod
    def from_collection(
        cls,
        collection: object,
        *,
        collection_uuid: Callable[[], str | None] | None = None,
    ) -> AnkiFilteredDeckBackend:
        """Create the pinned Anki 26.05 adapter using non-private scheduler APIs."""

        def create(name: str) -> int:
            from anki.decks import DeckId

            scheduler = getattr(collection, "sched")
            deck = scheduler.get_or_create_filtered_deck(deck_id=DeckId(0))
            deck.name = name
            deck.config.reschedule = True
            deck.allow_empty = True
            return int(deck.id)

        def rebuild(deck_id: int, card_ids: tuple[int, ...]) -> None:
            from anki.decks import DeckId, FilteredDeckConfig

            scheduler = getattr(collection, "sched")
            deck = scheduler.get_or_create_filtered_deck(deck_id=DeckId(deck_id))
            deck.config.reschedule = True
            deck.allow_empty = True
            terms = deck.config.search_terms
            del terms[:]
            search = "cid:" + ",".join(str(card_id) for card_id in card_ids)
            terms.append(
                FilteredDeckConfig.SearchTerm(
                    search=search,
                    limit=len(card_ids),
                    order=0,
                )
            )
            scheduler.add_or_update_filtered_deck(deck)

        def empty(deck_id: int) -> None:
            from anki.decks import DeckId

            getattr(collection, "sched").empty_filtered_deck(DeckId(deck_id))

        def delete(deck_id: int) -> None:
            from anki.decks import DeckId

            getattr(collection, "decks").remove([DeckId(deck_id)])

        def top_card_id() -> int | None:
            # get_queued_cards observes the next card without advancing the
            # scheduler, which is what makes the check safe to repeat.
            scheduler = getattr(collection, "sched")
            queued = scheduler.get_queued_cards(fetch_limit=1)
            entries = getattr(queued, "cards", ())
            if not entries:
                return None
            return int(entries[0].card.id)

        return cls(
            collection,
            create_filtered_deck=create,
            rebuild_filtered_deck=rebuild,
            empty_filtered_deck=empty,
            delete_filtered_deck=delete,
            top_card_id=top_card_id,
            collection_uuid=collection_uuid,
        )

    def inspect(self, name: str) -> FilteredDeckInfo | None:
        deck_id = self._find_deck_id(name)
        if deck_id is None:
            return None
        marker = self._get_config()
        return FilteredDeckInfo(
            deck_id=deck_id,
            owned=marker == deck_id,
        )

    def build(
        self,
        name: str,
        card_ids: tuple[int, ...],
        *,
        progress: Callable[[int, int], None],
        cancel: Event,
    ) -> None:
        if cancel.is_set():
            raise SessionError("rebuild_cancelled", "ANKIGTA Session rebuild cancelled")
        deck_id = self._find_deck_id(name)
        if deck_id is None:
            deck_id = int(self._create(name))
            self._set_config(deck_id)
        elif self._get_config() != deck_id:
            raise SessionError(
                "deck_name_collision",
                "filtered deck name collision: deck is not owned by ANKIGTA",
            )
        self._rebuild(deck_id, card_ids)
        progress(len(card_ids), len(card_ids))

    def cleanup(self, name: str) -> None:
        deck_id = self._find_deck_id(name)
        if deck_id is None or self._get_config() != deck_id:
            return
        self._empty(deck_id)
        self._delete(deck_id)

    def scheduler_top(self) -> AnkiCardIdentity | None:
        card_id = self._top_card_id()
        collection_uuid = self._collection_uuid()
        if card_id is None or not collection_uuid or card_id <= 0:
            return None
        return AnkiCardIdentity(collection_uuid, card_id)
        self._set_config(None)

    def _find_deck_id(self, name: str) -> int | None:
        decks = getattr(self._collection, "decks", None)
        if decks is None:
            raise SessionError("deck_api_unavailable", "Anki deck API is unavailable")
        raw = decks.all_names_and_ids()
        for item in raw if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)) else ():
            if str(getattr(item, "name", "")) == name:
                return int(getattr(item, "id"))
        if isinstance(raw, dict):
            for raw_name, raw_id in raw.items():
                if str(raw_name) == name:
                    return int(raw_id)
        if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
            for item in raw:
                if isinstance(item, tuple) and len(item) >= 2:
                    if str(item[0]) == name:
                        return int(item[1])
                elif isinstance(item, dict) and str(item.get("name")) == name:
                    return int(item["id"])
        return None

    def _get_config(self) -> int | None:
        getter = getattr(self._collection, "get_config", None)
        if getter is None:
            return None
        value = getter(self.OWNER_CONFIG_KEY, None)
        return int(value) if isinstance(value, int) and not isinstance(value, bool) else None

    def _set_config(self, deck_id: int | None) -> None:
        setter = getattr(self._collection, "set_config", None)
        if setter is not None:
            setter(self.OWNER_CONFIG_KEY, deck_id, undoable=False)


@dataclass(frozen=True)
class SessionStatus:
    session_active: bool
    paused: bool
    paused_reason: str | None
    filtered_deck_created: bool
    card_ids: tuple[int, ...]
    progress: int
    total: int

    def payload(self) -> dict[str, object]:
        return {
            "sessionActive": self.session_active,
            "paused": self.paused,
            "pausedReason": self.paused_reason,
            "filteredDeckCreated": self.filtered_deck_created,
            "cardCount": len(self.card_ids),
            "progress": self.progress,
            "total": self.total,
        }


@dataclass(frozen=True)
class SessionResult:
    card_ids: tuple[int, ...]
    skipped: tuple[AnkiCardIdentity, ...]


@dataclass(frozen=True)
class PauseResult:
    cleaned: bool


@dataclass(frozen=True)
class AdmissionResult:
    """The outcome of trying to make one exact card scheduler-top.

    `admitted` is the only thing that authorizes a rating. When it is false the
    card may still be shown, but strictly as Preview: Anki did not put it on
    top, so answering it would fail the scheduler's own check anyway.
    """

    identity: AnkiCardIdentity
    admitted: bool
    reason: str | None = None

    @property
    def preview_only(self) -> bool:
        return not self.admitted


CardReader = Callable[[int], CardView | None]
Observer = Callable[[], RuntimeObservation]


class SessionCoordinator:
    """Owns one rescheduling filtered deck without owning Anki scheduling."""

    def __init__(
        self,
        *,
        observe: Observer,
        read_card: CardReader,
        backend: FilteredDeckBackend,
        timeout_seconds: float = REBUILD_TIMEOUT_SECONDS,
        reviewer_guard: Callable[[], bool] | None = None,
        unresolved_transaction: Callable[[], bool] | None = None,
    ) -> None:
        self._observe = observe
        self._read_card = read_card
        self._backend = backend
        self._timeout_seconds = timeout_seconds
        self._reviewer_guard = reviewer_guard or (lambda: False)
        self._unresolved_transaction = unresolved_transaction or (lambda: False)
        self._lock = Lock()
        self._status = SessionStatus(
            session_active=False,
            paused=True,
            paused_reason="not_started",
            filtered_deck_created=False,
            card_ids=(),
            progress=0,
            total=0,
        )
        self._cancel = Event()
        self._admitted: AnkiCardIdentity | None = None
        self._full_membership: tuple[int, ...] = ()

    def status(self) -> SessionStatus:
        with self._lock:
            return self._status

    def start(
        self,
        identities: Iterable[AnkiCardIdentity],
        *,
        allow_early_review: bool = False,
        cancel: Event | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> SessionResult:
        self._validate_start()
        deck = self._backend.inspect(FILTERED_DECK_NAME)
        if deck is not None and not deck.owned:
            raise SessionError(
                "deck_name_collision",
                "filtered deck name collision: ANKIGTA Session is owned by another deck",
            )

        unique = self._unique_identities(identities)
        eligible: list[AnkiCardIdentity] = []
        skipped: list[AnkiCardIdentity] = []
        for identity in unique:
            if not self._identity_matches_bound_collection(identity):
                skipped.append(identity)
                continue
            card = self._read_card(identity.card_id)
            if card is None:
                skipped.append(identity)
                continue
            if card.state in {CardState.SUSPENDED, CardState.BURIED}:
                skipped.append(identity)
                continue
            if card.state is CardState.NOT_DUE and not allow_early_review:
                skipped.append(identity)
                continue
            eligible.append(identity)

        card_ids = tuple(identity.card_id for identity in eligible)
        self._cancel = cancel or Event()
        if card_ids:
            try:
                self._run_build(card_ids, progress)
            except SessionError:
                self._safe_cleanup()
                raise
        elif deck is not None and deck.owned:
            # A previous run may have left the owned deck behind while all
            # current links became ineligible; never strand that deck.
            self._safe_cleanup()
        with self._lock:
            self._status = SessionStatus(
                session_active=True,
                paused=False,
                paused_reason=None,
                filtered_deck_created=bool(card_ids),
                card_ids=card_ids,
                progress=len(card_ids),
                total=len(card_ids),
            )
        return SessionResult(card_ids=card_ids, skipped=tuple(skipped))

    def rebuild(
        self,
        identities: Iterable[AnkiCardIdentity],
        *,
        allow_early_review: bool = False,
        cancel: Event | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> SessionResult:
        if not self.status().session_active:
            raise SessionError("session_inactive", "ANKIGTA Session is not active")
        return self.start(
            identities,
            allow_early_review=allow_early_review,
            cancel=cancel,
            progress=progress,
        )

    def admit(
        self,
        identity: AnkiCardIdentity,
        *,
        allow_early_review: bool = False,
    ) -> AdmissionResult:
        """Try to make one exact card scheduler-top through an X-only rebuild.

        Prototype 0001 proved that answering a non-top card fails in Anki, and
        prototype 0002 proved this rebuild is the supported way to change which
        card is top. Anki still decides: this only asks, then checks.
        """
        self._validate_admission(identity, allow_early_review=allow_early_review)

        full_membership = self.status().card_ids
        self._run_build((identity.card_id,), None)
        with self._lock:
            self._status = SessionStatus(
                session_active=True,
                paused=False,
                paused_reason=None,
                filtered_deck_created=True,
                card_ids=(identity.card_id,),
                progress=0,
                total=1,
            )
            self._full_membership = full_membership

        top = self._backend.scheduler_top()
        if top is None:
            return self._refuse(identity, "no_scheduler_top")
        # Comparing the full identity, not just the number: the same card id in
        # another collection is a different card (ADR 0009).
        if top != identity:
            return self._refuse(identity, "not_scheduler_top")

        with self._lock:
            self._admitted = identity
        return AdmissionResult(identity=identity, admitted=True)

    def admitted_identity(self) -> AnkiCardIdentity | None:
        """The card currently admitted as scheduler-top, if any."""
        with self._lock:
            return self._admitted

    def scheduler_top(self) -> AnkiCardIdentity | None:
        return self._backend.scheduler_top()

    def restore(self) -> bool:
        """Rebuild the full session membership after an admission finishes."""
        with self._lock:
            admitted = self._admitted
            membership = self._full_membership
        if admitted is None:
            return False
        self._restore_membership(membership)
        return True

    def _refuse(self, identity: AnkiCardIdentity, reason: str) -> AdmissionResult:
        """Return to the full session rather than stranding an X-only deck."""
        with self._lock:
            membership = self._full_membership
        self._restore_membership(membership)
        return AdmissionResult(identity=identity, admitted=False, reason=reason)

    def _restore_membership(self, membership: tuple[int, ...]) -> None:
        if membership:
            self._run_build(membership, None)
        with self._lock:
            self._admitted = None
            self._full_membership = ()
            self._status = SessionStatus(
                session_active=True,
                paused=False,
                paused_reason=None,
                filtered_deck_created=bool(membership),
                card_ids=membership,
                progress=len(membership),
                total=len(membership),
            )

    def _validate_admission(
        self,
        identity: AnkiCardIdentity,
        *,
        allow_early_review: bool,
    ) -> None:
        if not self.status().session_active:
            raise SessionError("session_inactive", "ANKIGTA Session is not active")
        with self._lock:
            open_admission = self._admitted
        if open_admission is not None:
            raise SessionError(
                "admission_open",
                "another card is already admitted; finish it first",
            )
        if self._unresolved_transaction():
            raise SessionError(
                "outcome_unknown",
                "Unresolved Review Transaction blocks admission",
            )
        if self._reviewer_guard():
            raise SessionError("reviewer_active", "Anki Reviewer must be closed first")
        if not self._identity_matches_bound_collection(identity):
            raise SessionError(
                "wrong_collection",
                "card belongs to a different Anki collection",
            )
        card = self._read_card(identity.card_id)
        if card is None:
            raise SessionError("card_missing", "card no longer exists in Anki")
        if card.state in {CardState.SUSPENDED, CardState.BURIED}:
            # Prototype 0002 S7: Anki refuses these even for an exact request,
            # so refuse before touching the deck rather than after.
            raise SessionError(
                "card_unavailable",
                f"card is {card.state.value} and cannot be rated",
            )
        if card.state is CardState.NOT_DUE and not allow_early_review:
            raise SessionError(
                "early_review_disabled",
                "card is not due; enable early review to rate it",
            )

    def pause(self) -> PauseResult:
        current = self.status()
        cleaned = current.filtered_deck_created
        if cleaned:
            self._safe_cleanup()
        with self._lock:
            self._status = SessionStatus(
                session_active=False,
                paused=True,
                paused_reason="paused",
                filtered_deck_created=False,
                card_ids=(),
                progress=0,
                total=0,
            )
        return PauseResult(cleaned=cleaned)

    def cancel_rebuild(self) -> bool:
        with self._lock:
            rebuilding = self._status.paused_reason == "rebuilding"
        if not rebuilding:
            return False
        self._cancel.set()
        return True

    def stop(self) -> PauseResult:
        result = self.pause()
        with self._lock:
            self._status = SessionStatus(
                session_active=False,
                paused=True,
                paused_reason="stopped",
                filtered_deck_created=False,
                card_ids=(),
                progress=0,
                total=0,
            )
        return result

    def on_connection_lost(self, reason: str = "connection_lost") -> PauseResult:
        result = self.pause()
        with self._lock:
            self._status = SessionStatus(
                session_active=False,
                paused=True,
                paused_reason=reason,
                filtered_deck_created=False,
                card_ids=(),
                progress=0,
                total=0,
            )
        return result

    def _validate_start(self) -> None:
        observation = self._observe()
        if observation.anki_version != "26.05" or not observation.v3_scheduler:
            raise SessionError(
                "compatibility_failure",
                "Anki configuration is not supported for session",
            )
        if not observation.fsrs_enabled:
            raise SessionError("compatibility_failure", "FSRS must be enabled")
        if observation.collection.state.value != "open":
            raise SessionError("collection_unavailable", "Bound collection is not open")
        identity = observation.collection.identity
        if identity is None or identity.state is not CollectionIdentityState.BOUND:
            raise SessionError("collection_not_bound", "Bound Anki Collection is required")
        if self._reviewer_guard():
            raise SessionError("reviewer_active", "Anki Reviewer must be closed first")
        if self._unresolved_transaction():
            raise SessionError(
                "outcome_unknown",
                "Unresolved Review Transaction blocks session startup",
            )

    @staticmethod
    def _unique_identities(
        identities: Iterable[AnkiCardIdentity],
    ) -> tuple[AnkiCardIdentity, ...]:
        return tuple(
            sorted(
                {
                    identity
                    for identity in identities
                    if isinstance(identity, AnkiCardIdentity)
                    and identity.card_id > 0
                },
                key=lambda value: (value.collection_uuid, value.card_id),
            )
        )

    def _identity_matches_bound_collection(self, identity: AnkiCardIdentity) -> bool:
        bound = self._observe().collection.identity
        return (
            bound is not None
            and bound.state is CollectionIdentityState.BOUND
            and bound.collection_uuid == identity.collection_uuid
        )

    def _run_build(
        self,
        card_ids: tuple[int, ...],
        progress: Callable[[int, int], None] | None,
    ) -> None:
        total = len(card_ids)
        with self._lock:
            self._status = SessionStatus(
                session_active=False,
                paused=True,
                paused_reason="rebuilding",
                filtered_deck_created=False,
                card_ids=card_ids,
                progress=0,
                total=total,
            )

        def report(done: int, reported_total: int) -> None:
            with self._lock:
                self._status = SessionStatus(
                    session_active=False,
                    paused=True,
                    paused_reason="rebuilding",
                    filtered_deck_created=False,
                    card_ids=card_ids,
                    progress=max(0, min(int(done), total)),
                    total=max(total, int(reported_total)),
                )
            if progress is not None:
                progress(done, reported_total)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ankigta-session")
        future: Future[None] = executor.submit(
            self._backend.build,
            FILTERED_DECK_NAME,
            card_ids,
            progress=report,
            cancel=self._cancel,
        )
        try:
            future.result(timeout=self._timeout_seconds)
        except FutureTimeout as error:
            self._cancel.set()
            future.cancel()
            raise SessionError(
                "rebuild_timeout",
                "ANKIGTA Session rebuild exceeded 30 seconds",
            ) from error
        except Exception as error:
            if self._cancel.is_set():
                raise SessionError("rebuild_cancelled", "ANKIGTA Session rebuild cancelled") from error
            raise SessionError("rebuild_failed", "ANKIGTA Session rebuild failed") from error
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        if self._cancel.is_set():
            raise SessionError("rebuild_cancelled", "ANKIGTA Session rebuild cancelled")

    def _safe_cleanup(self) -> None:
        try:
            self._backend.cleanup(FILTERED_DECK_NAME)
        except Exception as error:
            raise SessionError(
                "cleanup_failed",
                "ANKIGTA Session cleanup failed; retry before continuing",
            ) from error
