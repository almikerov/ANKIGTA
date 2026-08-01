"""Ticket 16 — durable Review Transaction recovery.

Every test here is about the same question: after a crash, can the companion
tell whether Anki applied a rating? It may only answer from evidence. Where
evidence is absent the honest answer is `outcome_unknown`, and these tests are
mostly about making sure the code says that instead of guessing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from ankigta_companion.collection_identity import AnkiCardIdentity
from ankigta_companion.journal import (
    COMPLETED,
    OUTCOME_UNKNOWN,
    RATING_STARTED,
    RECEIVED,
    JournalError,
    JournalRecord,
    ReviewJournal,
)


UUID = "11111111-1111-4111-8111-111111111111"
OTHER_UUID = "22222222-2222-4222-8222-222222222222"
TRANSACTION = "review-0001"
BEFORE = {"type": 0, "queue": 0, "due": 1, "reps": 0, "revlog": []}


@pytest.fixture
def journal(tmp_path: Path) -> Iterator[ReviewJournal]:
    instance = ReviewJournal(tmp_path / "review.sqlite")
    try:
        yield instance
    finally:
        instance.close()


def intent(
    journal: ReviewJournal,
    *,
    card_id: int = 7,
    rating: str = "good",
    transaction: str = TRANSACTION,
    collection_uuid: str = UUID,
) -> JournalRecord:
    return journal.record_intent(
        AnkiCardIdentity(collection_uuid, card_id),
        transaction,
        rating,
        BEFORE,
    )


def always(value: bool | None):  # type: ignore[no-untyped-def]
    def verify(_record: JournalRecord) -> bool | None:
        return value

    return verify


def test_intent_is_durable_before_the_scheduler_is_invoked(
    journal: ReviewJournal,
) -> None:
    record = intent(journal)

    assert record.state == RECEIVED
    assert record.scheduler_calls == 0
    assert record.before == BEFORE


def test_the_journal_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "review.sqlite"
    first = ReviewJournal(path)
    started = first.mark_rating_started(intent(first))
    first.close()

    second = ReviewJournal(path)
    try:
        recovered = second.get(UUID, TRANSACTION)
        assert recovered is not None
        assert recovered.state == RATING_STARTED
        assert recovered.scheduler_calls == started.scheduler_calls == 1
        assert recovered.before == BEFORE
    finally:
        second.close()


def test_an_identical_replay_returns_the_existing_record(
    journal: ReviewJournal,
) -> None:
    first = intent(journal)
    second = intent(journal)

    assert second == first


@pytest.mark.parametrize(
    ("card_id", "rating"),
    [(8, "good"), (7, "again")],
)
def test_a_conflicting_replay_is_rejected_without_mutation(
    journal: ReviewJournal,
    card_id: int,
    rating: str,
) -> None:
    original = intent(journal)

    with pytest.raises(JournalError) as error:
        intent(journal, card_id=card_id, rating=rating)

    assert error.value.category == "transaction_conflict"
    assert journal.get(UUID, TRANSACTION) == original


def test_the_same_transaction_id_in_another_collection_is_a_different_record(
    journal: ReviewJournal,
) -> None:
    intent(journal)
    other = intent(journal, collection_uuid=OTHER_UUID, rating="easy")

    assert other.state == RECEIVED
    assert other.rating == "easy"
    assert journal.get(UUID, TRANSACTION) is not None
    assert journal.get(OTHER_UUID, TRANSACTION) is not None


def test_the_scheduler_call_is_counted_before_it_happens(
    journal: ReviewJournal,
) -> None:
    """A crash between the count and the call must look like a possible call."""
    started = journal.mark_rating_started(intent(journal))

    assert started.scheduler_calls == 1
    assert started.state == RATING_STARTED


def test_evidence_of_application_completes_without_a_second_call(
    journal: ReviewJournal,
) -> None:
    journal.mark_rating_started(intent(journal))

    results = journal.reconcile(always(True))

    assert [item.action for item in results] == ["confirmed"]
    record = journal.get(UUID, TRANSACTION)
    assert record is not None
    assert record.state == COMPLETED
    assert record.scheduler_calls == 1, "no second scheduler invocation"


def test_proven_non_application_is_resent_once_under_the_same_id(
    journal: ReviewJournal,
) -> None:
    journal.mark_rating_started(intent(journal))

    results = journal.reconcile(always(False))
    assert [item.action for item in results] == ["resend"]
    resent = journal.get(UUID, TRANSACTION)
    assert resent is not None
    assert resent.state == RECEIVED
    assert resent.resends == 1
    assert resent.review_transaction_id == TRANSACTION, "the id must not change"


def test_a_resend_is_never_repeated_indefinitely(journal: ReviewJournal) -> None:
    journal.mark_rating_started(intent(journal))
    journal.reconcile(always(False))

    # The resent attempt reaches the scheduler and is again unproven.
    record = journal.get(UUID, TRANSACTION)
    assert record is not None
    journal.mark_rating_started(record)
    results = journal.reconcile(always(False))

    assert [item.action for item in results] == ["quarantined"]
    final = journal.get(UUID, TRANSACTION)
    assert final is not None
    assert final.state == OUTCOME_UNKNOWN
    assert final.reason == "resend_limit"


def test_an_untouched_transaction_is_safe_to_resend(journal: ReviewJournal) -> None:
    intent(journal)

    results = journal.reconcile(always(None))

    # The scheduler was never invoked, so nothing needs proving.
    assert [item.action for item in results] == ["resend"]
    record = journal.get(UUID, TRANSACTION)
    assert record is not None
    assert record.state == RECEIVED


def test_an_indeterminate_outcome_becomes_a_durable_quarantine(
    journal: ReviewJournal,
) -> None:
    journal.mark_rating_started(intent(journal))

    results = journal.reconcile(always(None))

    assert [item.action for item in results] == ["quarantined"]
    record = journal.get(UUID, TRANSACTION)
    assert record is not None
    assert record.state == OUTCOME_UNKNOWN
    assert record.reason == "indeterminate"
    assert record.scheduler_calls == 1, "a quarantine must not retry"


def test_a_quarantine_survives_a_restart_and_still_blocks(tmp_path: Path) -> None:
    path = tmp_path / "review.sqlite"
    first = ReviewJournal(path)
    first.mark_rating_started(intent(first))
    first.reconcile(always(None))
    first.close()

    second = ReviewJournal(path)
    try:
        blocking = second.blocking()
        assert [record.state for record in blocking] == [OUTCOME_UNKNOWN]
        # Reconciling again must not gamble a scheduler call.
        second.reconcile(always(None))
        record = second.get(UUID, TRANSACTION)
        assert record is not None
        assert record.scheduler_calls == 1
    finally:
        second.close()


def test_only_the_affected_card_is_blocked(journal: ReviewJournal) -> None:
    journal.mark_rating_started(intent(journal, card_id=7))
    journal.reconcile(always(None))
    journal.mark_completed(
        journal.mark_rating_started(
            intent(journal, card_id=9, transaction="review-0002")
        ),
        {"state": "applied"},
    )

    blocked = {record.card_id for record in journal.blocking()}
    assert blocked == {7}


def test_a_completed_transaction_no_longer_blocks(journal: ReviewJournal) -> None:
    journal.mark_completed(
        journal.mark_rating_started(intent(journal)),
        {"state": "applied"},
    )

    assert journal.blocking() == ()


def test_garbage_collection_removes_only_acknowledged_terminal_records(
    journal: ReviewJournal,
) -> None:
    journal.mark_completed(
        journal.mark_rating_started(intent(journal)),
        {"state": "applied"},
    )
    journal.mark_completed(
        journal.mark_rating_started(intent(journal, transaction="review-0002")),
        {"state": "applied"},
    )

    removed = journal.collect_garbage({TRANSACTION})

    assert removed == 1
    assert journal.get(UUID, TRANSACTION) is None
    assert journal.get(UUID, "review-0002") is not None


def test_garbage_collection_never_removes_an_unresolved_outcome(
    journal: ReviewJournal,
) -> None:
    journal.mark_rating_started(intent(journal))
    journal.reconcile(always(None))

    removed = journal.collect_garbage({TRANSACTION})

    assert removed == 0
    record = journal.get(UUID, TRANSACTION)
    assert record is not None
    assert record.state == OUTCOME_UNKNOWN


def test_garbage_collection_never_removes_an_unacknowledged_record(
    journal: ReviewJournal,
) -> None:
    journal.mark_completed(
        journal.mark_rating_started(intent(journal)),
        {"state": "applied"},
    )

    assert journal.collect_garbage(set()) == 0
    assert journal.get(UUID, TRANSACTION) is not None


def test_reconciliation_sees_evidence_including_the_before_snapshot(
    journal: ReviewJournal,
) -> None:
    journal.mark_rating_started(intent(journal))
    seen: list[JournalRecord] = []

    def verify(record: JournalRecord) -> bool | None:
        seen.append(record)
        return True

    journal.reconcile(verify)

    assert len(seen) == 1
    assert seen[0].before == BEFORE
    assert seen[0].card_id == 7
    assert seen[0].rating == "good"


def test_a_rating_survives_a_companion_restart_without_a_second_call(
    tmp_path: Path,
) -> None:
    """The end-to-end promise: restart, replay, still exactly one call."""
    from tests.test_review_transaction import (
        Answers,
        FakeBackend,
        admitted_session,
        card,
        observation,
    )
    from ankigta_companion.review import ReviewCoordinator

    path = tmp_path / "review.sqlite"
    cards = {1: card(1), 2: card(2)}
    answers = Answers()

    first_journal = ReviewJournal(path)
    session = admitted_session(FakeBackend(), cards, 2)
    review = ReviewCoordinator(
        session=session,
        answer_card=answers,
        journal=first_journal,
    )
    outcome = review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")
    assert outcome.state == "applied"
    first_journal.close()

    # A fresh process: new coordinator, new in-memory state, same journal.
    second_journal = ReviewJournal(path)
    try:
        restarted_session = admitted_session(FakeBackend(), cards, 2)
        restarted = ReviewCoordinator(
            session=restarted_session,
            answer_card=answers,
            journal=second_journal,
        )
        replay = restarted.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")

        assert replay.state == "applied"
        assert replay.replayed is True
        assert len(answers.calls) == 1, "the restart must not re-rate the card"
    finally:
        second_journal.close()


def test_an_unknown_outcome_survives_a_restart_and_still_blocks(
    tmp_path: Path,
) -> None:
    from tests.test_review_transaction import (
        Answers,
        FakeBackend,
        admitted_session,
        card,
        observation,
    )
    from ankigta_companion.review import ReviewCoordinator, ReviewError

    path = tmp_path / "review.sqlite"
    cards = {1: card(1), 2: card(2)}
    answers = Answers()
    answers.error = RuntimeError("lost mid-answer")

    first_journal = ReviewJournal(path)
    review = ReviewCoordinator(
        session=admitted_session(FakeBackend(), cards, 2),
        answer_card=answers,
        journal=first_journal,
    )
    assert review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good").state == (
        "outcome_unknown"
    )
    first_journal.close()

    second_journal = ReviewJournal(path)
    try:
        answers.error = None
        restarted = ReviewCoordinator(
            session=admitted_session(FakeBackend(), cards, 2),
            answer_card=answers,
            journal=second_journal,
        )
        assert restarted.unresolved() is True

        with pytest.raises(ReviewError) as error:
            restarted.rate("review-0002", AnkiCardIdentity(UUID, 2), "good")
        assert error.value.category == "outcome_unknown"
        assert len(answers.calls) == 1, "the quarantine must not be gambled on"
    finally:
        second_journal.close()
