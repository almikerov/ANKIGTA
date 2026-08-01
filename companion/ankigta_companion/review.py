"""The Review Transaction coordinator.

Anki owns scheduling; this module owns the promise that one user rating reaches
Anki exactly once. Two failure modes drive its shape:

- The same rating can arrive twice — a double click, or the transport retrying a
  request whose response was lost. Both carry the same `reviewTransactionId`, so
  a repeat replays the recorded result instead of rating again.
- An answer can fail without proving anything. A transport error or an
  exception mid-call leaves the outcome genuinely unknown; guessing either way
  risks a double review or a silently lost one. Such a transaction becomes
  `outcome_unknown`, is never retried blindly, and blocks further ratings until
  a later reconciliation pass resolves it (ticket 16).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

from .collection_identity import AnkiCardIdentity
from .journal import COMPLETED, JournalError, ReviewJournal
from .session import SessionCoordinator


# Anki's rating ordinals for the four answer buttons.
RATINGS: dict[str, int] = {
    "again": 1,
    "hard": 2,
    "good": 3,
    "easy": 4,
}

APPLIED = "applied"
OUTCOME_UNKNOWN = "outcome_unknown"


class ReviewError(RuntimeError):
    """A categorized, user-visible rating failure."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


@dataclass(frozen=True)
class RatingOutcome:
    review_transaction_id: str
    identity: AnkiCardIdentity
    rating: str
    state: str
    replayed: bool = False
    reason: str | None = None

    @property
    def applied(self) -> bool:
        return self.state == APPLIED


AnswerCard = Callable[[int, int], None]


class ReviewCoordinator:
    """Applies one rating per Review Transaction, and never more."""

    def __init__(
        self,
        *,
        session: SessionCoordinator,
        answer_card: AnswerCard,
        journal: ReviewJournal | None = None,
        snapshot_card: Callable[[int], dict[str, object]] | None = None,
    ) -> None:
        self._session = session
        self._answer_card = answer_card
        self._journal = journal
        self._snapshot_card = snapshot_card or (lambda _card_id: {})
        self._lock = Lock()
        self._outcomes: dict[str, RatingOutcome] = {}

    def outcome(self, review_transaction_id: str) -> RatingOutcome | None:
        with self._lock:
            remembered = self._outcomes.get(review_transaction_id)
        if remembered is not None:
            return remembered
        if self._journal is None:
            return None
        # After a restart the memory is empty but the journal is not, and a
        # replayed rating must still find its recorded result.
        for record in self._journal.find(review_transaction_id):
            if record.state == COMPLETED:
                return RatingOutcome(
                    review_transaction_id=record.review_transaction_id,
                    identity=record.identity,
                    rating=record.rating,
                    state=APPLIED,
                )
            if record.state == OUTCOME_UNKNOWN:
                return RatingOutcome(
                    review_transaction_id=record.review_transaction_id,
                    identity=record.identity,
                    rating=record.rating,
                    state=OUTCOME_UNKNOWN,
                    reason=record.reason,
                )
        return None

    def unresolved(self) -> bool:
        """True while any transaction's outcome is still unproven."""
        if self._journal is not None and self._journal.blocking():
            return True
        with self._lock:
            return any(
                outcome.state == OUTCOME_UNKNOWN
                for outcome in self._outcomes.values()
            )

    def rate(
        self,
        review_transaction_id: str,
        identity: AnkiCardIdentity,
        rating: str,
    ) -> RatingOutcome:
        if not isinstance(review_transaction_id, str) or not review_transaction_id:
            raise ReviewError(
                "invalid_transaction",
                "reviewTransactionId must be a non-empty string",
            )

        recorded = self.outcome(review_transaction_id)
        if recorded is not None:
            # The same transaction arriving again is a repeat, not a new
            # review — but only if it is asking for the same thing.
            if recorded.identity != identity or recorded.rating != rating:
                raise ReviewError(
                    "transaction_conflict",
                    "reviewTransactionId was already used for a different rating",
                )
            return RatingOutcome(
                review_transaction_id=recorded.review_transaction_id,
                identity=recorded.identity,
                rating=recorded.rating,
                state=recorded.state,
                replayed=True,
                reason=recorded.reason,
            )

        if rating not in RATINGS:
            raise ReviewError("invalid_rating", f"unknown rating: {rating}")
        if self.unresolved():
            raise ReviewError(
                "outcome_unknown",
                "an unresolved Review Transaction must be reconciled first",
            )

        admitted = self._session.admitted_identity()
        if admitted is None or admitted != identity:
            raise ReviewError(
                "card_not_admitted",
                "only the admitted scheduler-top card can be rated",
            )
        # Anki enforces this too, but checking first keeps a stale click from
        # becoming a scheduler error the user has to interpret.
        if self._session.scheduler_top() != identity:
            raise ReviewError(
                "not_scheduler_top",
                "card is no longer scheduler-top; reopen it before rating",
            )

        record = None
        if self._journal is not None:
            try:
                record = self._journal.record_intent(
                    identity,
                    review_transaction_id,
                    rating,
                    self._snapshot_card(identity.card_id),
                )
            except JournalError as error:
                raise ReviewError(error.category, error.message) from error
            # The scheduler call is counted before it is made, so a crash in
            # between looks like a call that may have happened.
            record = self._journal.mark_rating_started(record)

        outcome = self._apply(review_transaction_id, identity, rating)

        if self._journal is not None and record is not None:
            if outcome.applied:
                self._journal.mark_completed(record, {"state": APPLIED})
            else:
                self._journal.mark_outcome_unknown(
                    record,
                    outcome.reason or "indeterminate",
                )

        with self._lock:
            self._outcomes[review_transaction_id] = outcome
        if outcome.applied:
            # Only a confirmed terminal result may restore the full session.
            self._session.restore()
        return outcome

    def reconcile(self, verify: object) -> tuple[object, ...]:
        """Resolve unfinished transactions after a restart.

        Delegates the evidence question to the journal, which decides only from
        what can be proved about the collection.
        """
        if self._journal is None:
            return ()
        results = self._journal.reconcile(verify)  # type: ignore[arg-type]
        with self._lock:
            for item in results:
                record = item.record
                self._outcomes[record.review_transaction_id] = RatingOutcome(
                    review_transaction_id=record.review_transaction_id,
                    identity=record.identity,
                    rating=record.rating,
                    state=(
                        APPLIED
                        if record.state == "completed"
                        else OUTCOME_UNKNOWN
                    ),
                    reason=record.reason,
                )
        return results

    def _apply(
        self,
        review_transaction_id: str,
        identity: AnkiCardIdentity,
        rating: str,
    ) -> RatingOutcome:
        try:
            self._answer_card(identity.card_id, RATINGS[rating])
        except Exception as error:  # noqa: BLE001 - any failure is unproven
            return RatingOutcome(
                review_transaction_id=review_transaction_id,
                identity=identity,
                rating=rating,
                state=OUTCOME_UNKNOWN,
                reason=str(error) or error.__class__.__name__,
            )
        return RatingOutcome(
            review_transaction_id=review_transaction_id,
            identity=identity,
            rating=rating,
            state=APPLIED,
        )
