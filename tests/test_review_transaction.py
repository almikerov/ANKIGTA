"""Ticket 15 — one rating through MTA, applied exactly once.

The hard part is not applying a rating; it is never applying a second one and
never guessing. A lost response proves nothing about whether Anki committed the
review, so the coordinator reports `outcome_unknown` rather than picking an
answer, and refuses to rebuild the session until the outcome is terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from ankigta_companion.cards import CardState, CardView
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
from ankigta_companion.review import (
    RATINGS,
    ReviewCoordinator,
    ReviewError,
)
from ankigta_companion.session import (
    FILTERED_DECK_NAME,
    FilteredDeckInfo,
    SessionCoordinator,
)


UUID = "11111111-1111-4111-8111-111111111111"
OTHER_UUID = "22222222-2222-4222-8222-222222222222"
TRANSACTION = "review-0001"


@dataclass
class FakeBackend:
    existing: FilteredDeckInfo | None = None
    top: AnkiCardIdentity | None = None
    built: list[tuple[str, tuple[int, ...]]] = field(default_factory=list)
    cleaned: list[str] = field(default_factory=list)

    def inspect(self, name: str) -> FilteredDeckInfo | None:
        return self.existing

    def build(self, name: str, card_ids: tuple[int, ...], **_kwargs: object) -> None:
        self.built.append((name, card_ids))

    def cleanup(self, name: str) -> None:
        self.cleaned.append(name)

    def scheduler_top(self) -> AnkiCardIdentity | None:
        return self.top


def observation() -> RuntimeObservation:
    return RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(
            state=CollectionState.OPEN,
            identity=CollectionIdentityObservation(
                CollectionIdentityState.BOUND,
                UUID,
            ),
        ),
    )


def card(card_id: int, state: CardState = CardState.NEW) -> CardView:
    return CardView(
        identity=AnkiCardIdentity(UUID, card_id),
        deck_id=10,
        deck_name="Source",
        state=state,
        due=0,
        tags=(),
    )


@dataclass
class Answers:
    """Stands in for Anki's scheduler answer call."""

    calls: list[tuple[int, int]] = field(default_factory=list)
    error: Exception | None = None

    def __call__(self, card_id: int, ordinal: int) -> None:
        self.calls.append((card_id, ordinal))
        if self.error is not None:
            raise self.error


def admitted_session(
    backend: FakeBackend,
    cards: dict[int, CardView],
    target: int,
) -> SessionCoordinator:
    session = SessionCoordinator(
        observe=observation,
        read_card=cards.get,
        backend=backend,
    )
    session.start(AnkiCardIdentity(UUID, card_id) for card_id in cards)
    backend.top = AnkiCardIdentity(UUID, target)
    session.admit(AnkiCardIdentity(UUID, target))
    backend.built.clear()
    return session


def build(target: int = 2) -> tuple[SessionCoordinator, FakeBackend, Answers, ReviewCoordinator]:
    cards = {1: card(1), 2: card(2)}
    backend = FakeBackend()
    session = admitted_session(backend, cards, target)
    answers = Answers()
    review = ReviewCoordinator(session=session, answer_card=answers)
    return session, backend, answers, review


@pytest.mark.parametrize("rating", sorted(RATINGS))
def test_each_rating_reaches_anki_exactly_once(rating: str) -> None:
    _session, _backend, answers, review = build()

    outcome = review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), rating)

    assert outcome.state == "applied"
    assert outcome.replayed is False
    assert answers.calls == [(2, RATINGS[rating])]


def test_a_repeated_click_replays_the_recorded_result_without_rating_again() -> None:
    _session, _backend, answers, review = build()

    first = review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")
    second = review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")

    assert first.state == "applied"
    assert second.state == "applied"
    assert second.replayed is True
    assert answers.calls == [(2, RATINGS["good"])], "Anki must be called once"


def test_a_replay_with_a_conflicting_rating_is_refused() -> None:
    _session, _backend, answers, review = build()

    review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")
    with pytest.raises(ReviewError) as error:
        review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "again")

    assert error.value.category == "transaction_conflict"
    assert len(answers.calls) == 1


def test_only_the_admitted_card_can_be_rated() -> None:
    _session, _backend, answers, review = build(target=2)

    with pytest.raises(ReviewError) as error:
        review.rate(TRANSACTION, AnkiCardIdentity(UUID, 1), "good")

    assert error.value.category == "card_not_admitted"
    assert answers.calls == []


def test_a_card_id_from_another_collection_is_not_the_admitted_card() -> None:
    _session, _backend, answers, review = build(target=2)

    with pytest.raises(ReviewError) as error:
        review.rate(TRANSACTION, AnkiCardIdentity(OTHER_UUID, 2), "good")

    assert error.value.category == "card_not_admitted"
    assert answers.calls == []


def test_rating_without_an_admission_is_refused() -> None:
    cards = {1: card(1)}
    backend = FakeBackend(top=AnkiCardIdentity(UUID, 1))
    session = SessionCoordinator(
        observe=observation,
        read_card=cards.get,
        backend=backend,
    )
    session.start([AnkiCardIdentity(UUID, 1)])
    answers = Answers()
    review = ReviewCoordinator(session=session, answer_card=answers)

    with pytest.raises(ReviewError) as error:
        review.rate(TRANSACTION, AnkiCardIdentity(UUID, 1), "good")

    assert error.value.category == "card_not_admitted"
    assert answers.calls == []


def test_an_unknown_rating_is_refused() -> None:
    _session, _backend, answers, review = build()

    with pytest.raises(ReviewError) as error:
        review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "perfect")

    assert error.value.category == "invalid_rating"
    assert answers.calls == []


def test_the_card_must_still_be_scheduler_top_when_the_rating_arrives() -> None:
    _session, backend, answers, review = build()
    # Something changed between admission and the click.
    backend.top = AnkiCardIdentity(UUID, 1)

    with pytest.raises(ReviewError) as error:
        review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")

    assert error.value.category == "not_scheduler_top"
    assert answers.calls == []


def test_a_failed_answer_is_outcome_unknown_and_is_never_retried_blindly() -> None:
    _session, _backend, answers, review = build()
    answers.error = RuntimeError("connection lost mid-answer")

    outcome = review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")

    assert outcome.state == "outcome_unknown"
    assert len(answers.calls) == 1

    # Replaying must not gamble a second scheduler call.
    replay = review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")
    assert replay.state == "outcome_unknown"
    assert replay.replayed is True
    assert len(answers.calls) == 1


def test_an_unknown_outcome_blocks_further_ratings() -> None:
    _session, _backend, answers, review = build()
    answers.error = RuntimeError("lost")
    review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")

    assert review.unresolved() is True
    with pytest.raises(ReviewError) as error:
        review.rate("review-0002", AnkiCardIdentity(UUID, 2), "good")
    assert error.value.category == "outcome_unknown"


def test_the_session_is_rebuilt_only_after_a_confirmed_result() -> None:
    session, backend, answers, review = build()

    review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")

    assert backend.built[-1] == (FILTERED_DECK_NAME, (1, 2))
    assert session.status().card_ids == (1, 2)


def test_an_unknown_outcome_does_not_rebuild_the_session() -> None:
    session, backend, answers, review = build()
    answers.error = RuntimeError("lost")

    review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")

    assert backend.built == [], "an unproven rating must not restore the session"
    assert session.status().card_ids == (2,)


def test_transaction_ids_are_independent_of_transport_request_ids() -> None:
    """A retried transport request must reuse the same reviewTransactionId."""
    _session, _backend, answers, review = build()

    # The same transaction arriving twice is the transport retrying, not the
    # user rating twice; only a different transaction id is a new review.
    review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")
    review.rate(TRANSACTION, AnkiCardIdentity(UUID, 2), "good")

    assert len(answers.calls) == 1
    assert review.outcome(TRANSACTION) is not None
    assert review.outcome("review-0002") is None


def post_rating(server: object, body: dict[str, object]) -> tuple[int, dict[str, object]]:
    import json
    from http.client import HTTPConnection

    connection = HTTPConnection(server.host, server.port, timeout=2)  # type: ignore[attr-defined]
    connection.request(
        "POST",
        "/v1/review/rate",
        body=json.dumps(
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": "transport-1",
                **body,
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    value = json.loads(response.read())
    connection.close()
    return response.status, value


def test_rating_is_reachable_as_a_versioned_control_operation() -> None:
    from ankigta_companion.http_server import HealthServer

    session, _backend, answers, review = build()

    with HealthServer(
        observation,
        session_coordinator=session,
        review_coordinator=review,
    ) as server:
        status, applied = post_rating(
            server,
            {
                "reviewTransactionId": TRANSACTION,
                "cardIdentity": {"collectionUuid": UUID, "cardId": 2},
                "rating": "good",
            },
        )
        assert status == 200
        assert applied["payload"]["review"]["state"] == "applied"
        assert applied["payload"]["review"]["replayed"] is False

        # The transport retrying the same transaction must not rate twice.
        status, replayed = post_rating(
            server,
            {
                "reviewTransactionId": TRANSACTION,
                "cardIdentity": {"collectionUuid": UUID, "cardId": 2},
                "rating": "good",
            },
        )
        assert status == 200
        assert replayed["payload"]["review"]["replayed"] is True

    assert answers.calls == [(2, RATINGS["good"])]


def test_a_malformed_rating_request_is_rejected_without_touching_anki() -> None:
    from ankigta_companion.http_server import HealthServer

    session, _backend, answers, review = build()

    with HealthServer(
        observation,
        session_coordinator=session,
        review_coordinator=review,
    ) as server:
        status, missing_id = post_rating(
            server,
            {
                "cardIdentity": {"collectionUuid": UUID, "cardId": 2},
                "rating": "good",
            },
        )
        assert status == 400
        assert missing_id["error"]["category"] == "invalid_session_request"

        status, bad_rating = post_rating(
            server,
            {
                "reviewTransactionId": TRANSACTION,
                "cardIdentity": {"collectionUuid": UUID, "cardId": 2},
                "rating": "perfect",
            },
        )
        assert status == 400
        assert bad_rating["error"]["category"] == "invalid_rating"

    assert answers.calls == []
