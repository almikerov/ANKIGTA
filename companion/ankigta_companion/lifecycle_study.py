"""Study lifecycle: pausing, and never stranding a card.

Every way study can end — the user pausing, an AnkiWeb sync, a lost connection,
a shutdown, the add-on being removed — converges on the same requirement: the
owned filtered deck must be emptied and every card returned to its home deck.
A card left in a deleted or abandoned `ANKIGTA Session` is invisible to the user
and hard to find, so cleanup is the one step that runs in all of them.

Two things deliberately do *not* happen:

- ANKIGTA never starts, waits for, or configures an AnkiWeb sync. Sync is
  Anki's, and reaching into it would be reaching into the user's account.
- Nothing resumes study by itself. Reconnecting, finishing a sync or reopening
  a profile all land in connected-paused, and the user presses the button.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock


class StudyPhase(StrEnum):
    #: Nothing is running; the user has not started study.
    IDLE = "idle"
    #: Study is running.
    ACTIVE = "active"
    #: Study stopped for a stated reason, and links are untouched.
    PAUSED = "paused"


#: Reasons study was paused. All of them are terminal until the user restarts.
PAUSE_USER = "paused"
PAUSE_SYNC = "anki_sync"
PAUSE_DISCONNECTED = "connection_lost"
PAUSE_COLLECTION_CLOSING = "collection_closing"
PAUSE_REVIEWER = "reviewer_active"
PAUSE_SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class LifecycleResult:
    phase: StudyPhase
    reason: str | None
    cleaned: bool
    #: True when cleanup was deliberately deferred pending reconciliation.
    awaiting_reconciliation: bool = False


class StudyLifecycle:
    """Drives every transition that ends a study session."""

    def __init__(
        self,
        *,
        pause_session: Callable[[], bool],
        close_unrated_review: Callable[[], None],
        unresolved_transaction: Callable[[], bool],
        reconcile: Callable[[], None] | None = None,
    ) -> None:
        self._pause_session = pause_session
        self._close_unrated_review = close_unrated_review
        self._unresolved_transaction = unresolved_transaction
        self._reconcile = reconcile or (lambda: None)
        self._lock = Lock()
        self._phase = StudyPhase.IDLE
        self._reason: str | None = None

    @property
    def phase(self) -> StudyPhase:
        with self._lock:
            return self._phase

    @property
    def reason(self) -> str | None:
        with self._lock:
            return self._reason

    @property
    def activation_enabled(self) -> bool:
        """Activation zones and the next-card indicator follow study, not links."""
        return self.phase is StudyPhase.ACTIVE

    def started(self) -> None:
        with self._lock:
            self._phase = StudyPhase.ACTIVE
            self._reason = None

    # -------------------------------------------------------------- pausing

    def pause(self, reason: str = PAUSE_USER) -> LifecycleResult:
        """Stop study for a stated reason. Spatial Links are never touched."""
        return self._settle(reason, close_review=True)

    def on_anki_sync_starting(self) -> LifecycleResult:
        """The user started a sync in Anki; stand down and stay down.

        ANKIGTA neither triggers nor awaits the sync itself.
        """
        return self._settle(PAUSE_SYNC, close_review=True)

    def on_collection_closing(self) -> LifecycleResult:
        return self._settle(PAUSE_COLLECTION_CLOSING, close_review=True)

    def on_connection_lost(self) -> LifecycleResult:
        """The MTA link dropped. The pending transaction survives untouched."""
        return self._settle(PAUSE_DISCONNECTED, close_review=False)

    def on_reviewer_opened(self) -> LifecycleResult:
        return self._settle(PAUSE_REVIEWER, close_review=True)

    def on_shutdown(self) -> LifecycleResult:
        """Normal stop, exit, or add-on removal: clean up, close nothing else."""
        return self._settle(PAUSE_SHUTDOWN, close_review=True)

    def on_reconnected(self) -> LifecycleResult:
        """Reconnecting reconciles first and then waits for the user.

        It never reopens a card or rebuilds the session: the player did not ask
        for study to resume just because the socket came back.
        """
        self._reconcile()
        with self._lock:
            reason = self._reason or PAUSE_DISCONNECTED
            self._phase = StudyPhase.PAUSED
            self._reason = reason
        return LifecycleResult(phase=StudyPhase.PAUSED, reason=reason, cleaned=False)

    def _settle(self, reason: str, *, close_review: bool) -> LifecycleResult:
        if close_review:
            # An unrated open card is closed without touching its schedule;
            # a submitted one is left to the journal to reconcile.
            self._close_unrated_review()

        if self._unresolved_transaction():
            # Emptying the deck now would hide the very card whose outcome is
            # still unproven. Stop studying, but leave the deck alone.
            with self._lock:
                self._phase = StudyPhase.PAUSED
                self._reason = reason
            return LifecycleResult(
                phase=StudyPhase.PAUSED,
                reason=reason,
                cleaned=False,
                awaiting_reconciliation=True,
            )

        cleaned = bool(self._pause_session())
        with self._lock:
            self._phase = StudyPhase.PAUSED
            self._reason = reason
        return LifecycleResult(phase=StudyPhase.PAUSED, reason=reason, cleaned=cleaned)
