"""Arbitration between Anki's own Reviewer and an ANKIGTA Session.

The two are mutually exclusive over one collection (ADR 0022). Opening Anki's
Reviewer pauses ANKIGTA; ending it never resumes ANKIGTA, because resuming a
game session behind the user's back is worse than making them press a button.

The delicate case is a standard rating already in flight. Prototype 0003
measured that Anki's backend had created exactly one `revlog` row, and that
moving to the deck browser at that moment still returned in about 1.7 ms — but
the stock completion callback continued to depend on `Reviewer.card`, which the
cleanup had cleared. So "close it and let the rating finish in the background"
is disproved. Instead ANKIGTA waits, visibly, and if the callback never
completes it simply does not start: a timeout is not permission to force
anything.

Three things are therefore never done here, and a source test enforces it:
monkey-patching the callback, mutating private Reviewer state, and cancelling an
in-flight operation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Protocol


#: AQT reviewer states this arbiter understands.
DECK_BROWSER = "deckBrowser"
REVIEW_QUESTION = "review/question"
REVIEW_ANSWER = "review/answer"
REVIEW_TRANSITION = "review/transition"

#: States in which no rating has been submitted, so leaving mutates nothing.
UNRATED_STATES = frozenset({REVIEW_QUESTION, REVIEW_ANSWER})

WAITING_MESSAGE = "Завершаем оценку Anki…"


class ArbitrationError(RuntimeError):
    """A categorized, user-visible arbitration failure."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


class ReviewerSurface(Protocol):
    """The small, version-sensitive slice of AQT this needs.

    Kept behind a protocol because `moveToState` is not a documented add-on API
    (prototype 0003); pinning it here keeps the version risk in one place.
    """

    def state(self) -> str: ...

    def move_to_deck_browser(self) -> None: ...


@dataclass(frozen=True)
class ArbitrationDecision:
    allowed: bool
    reason: str | None = None
    message: str | None = None
    #: True while a stock rating callback is still outstanding.
    waiting: bool = False


class ReviewerArbiter:
    """Decides which study mode may hold the collection."""

    def __init__(
        self,
        *,
        reviewer: ReviewerSurface,
        pause_session: Callable[[], None],
        unresolved_transaction: Callable[[], bool],
        supported: bool = True,
    ) -> None:
        self._reviewer = reviewer
        self._pause_session = pause_session
        self._unresolved_transaction = unresolved_transaction
        self._supported = supported
        self._lock = Lock()
        self._rating_in_flight = False
        self._paused_by_reviewer = False

    # ------------------------------------------------------------ observation

    def on_reviewer_opened(self) -> ArbitrationDecision:
        """Anki's Reviewer took the collection; stand down.

        Cleanup waits on reconciliation: handing the queue to the standard
        Reviewer while a submitted ANKIGTA transaction is still unproven would
        make the two disagree about what happened.
        """
        if not self._supported:
            return ArbitrationDecision(
                allowed=False,
                reason="unsupported_anki",
                message="Anki build is not supported for arbitration",
            )
        if self._unresolved_transaction():
            return ArbitrationDecision(
                allowed=False,
                reason="outcome_unknown",
                message="Unresolved Review Transaction must be reconciled first",
            )
        self._pause_session()
        with self._lock:
            self._paused_by_reviewer = True
        return ArbitrationDecision(allowed=True)

    def on_rating_started(self) -> None:
        with self._lock:
            self._rating_in_flight = True

    def on_rating_completed(self) -> None:
        with self._lock:
            self._rating_in_flight = False

    def on_reviewer_closed(self) -> None:
        """Ending ordinary review never resumes ANKIGTA (ADR 0022)."""
        with self._lock:
            self._rating_in_flight = False
            self._paused_by_reviewer = False

    @property
    def waiting_for_rating(self) -> bool:
        with self._lock:
            return self._rating_in_flight

    # ------------------------------------------------------------- transition

    def request_session_start(self) -> ArbitrationDecision:
        """May an ANKIGTA Session take the collection now?"""
        if not self._supported:
            return ArbitrationDecision(
                allowed=False,
                reason="unsupported_anki",
                message="Anki build is not supported for arbitration",
            )
        if self._unresolved_transaction():
            return ArbitrationDecision(
                allowed=False,
                reason="outcome_unknown",
                message="Unresolved Review Transaction must be reconciled first",
            )

        state = self._reviewer.state()
        if state == DECK_BROWSER:
            return ArbitrationDecision(allowed=True)

        if self.waiting_for_rating or state == REVIEW_TRANSITION:
            # The stock callback still owns Reviewer.card. Touching anything
            # here is what prototype 0003 proved unsafe.
            return ArbitrationDecision(
                allowed=False,
                reason="rating_in_flight",
                message=WAITING_MESSAGE,
                waiting=True,
            )

        if state in UNRATED_STATES:
            # Nothing was submitted, so leaving mutates nothing.
            self._reviewer.move_to_deck_browser()
            if self._reviewer.state() != DECK_BROWSER:
                return ArbitrationDecision(
                    allowed=False,
                    reason="reviewer_did_not_close",
                    message="Anki Reviewer did not close; close it manually",
                )
            return ArbitrationDecision(allowed=True)

        return ArbitrationDecision(
            allowed=False,
            reason="reviewer_state_unknown",
            message=f"unrecognised Anki Reviewer state: {state}",
        )
