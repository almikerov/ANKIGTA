"""Ticket 17 — arbitration between Anki's Reviewer and an ANKIGTA Session.

Most of these tests are about what the arbiter refuses to do. Prototype 0003
disproved the appealing shortcut — close the Reviewer and let an in-flight
rating finish in the background — because the stock callback still depends on
state the cleanup would have cleared.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from ankigta_companion.arbitration import (
    DECK_BROWSER,
    REVIEW_ANSWER,
    REVIEW_QUESTION,
    REVIEW_TRANSITION,
    WAITING_MESSAGE,
    ReviewerArbiter,
)


@dataclass
class FakeReviewer:
    current: str = DECK_BROWSER
    moves: int = 0
    #: Set when the reviewer refuses to leave, as a stuck one would.
    stuck: bool = False

    def state(self) -> str:
        return self.current

    def move_to_deck_browser(self) -> None:
        self.moves += 1
        if not self.stuck:
            self.current = DECK_BROWSER


@dataclass
class Session:
    paused: int = 0
    unresolved: bool = False
    events: list[str] = field(default_factory=list)

    def pause(self) -> None:
        self.paused += 1
        self.events.append("paused")


def build(
    state: str = DECK_BROWSER,
    *,
    unresolved: bool = False,
    supported: bool = True,
) -> tuple[ReviewerArbiter, FakeReviewer, Session]:
    reviewer = FakeReviewer(current=state)
    session = Session(unresolved=unresolved)
    arbiter = ReviewerArbiter(
        reviewer=reviewer,
        pause_session=session.pause,
        unresolved_transaction=lambda: session.unresolved,
        supported=supported,
    )
    return arbiter, reviewer, session


def test_opening_the_reviewer_pauses_ankigta() -> None:
    arbiter, _reviewer, session = build()

    decision = arbiter.on_reviewer_opened()

    assert decision.allowed is True
    assert session.paused == 1


def test_the_reviewer_does_not_take_over_before_reconciliation() -> None:
    arbiter, _reviewer, session = build(unresolved=True)

    decision = arbiter.on_reviewer_opened()

    assert decision.allowed is False
    assert decision.reason == "outcome_unknown"
    assert session.paused == 0, (
        "handing over the queue with an unproven rating would let the two "
        "modes disagree about what happened"
    )


def test_a_session_may_start_from_the_deck_browser() -> None:
    arbiter, reviewer, _session = build(DECK_BROWSER)

    decision = arbiter.request_session_start()

    assert decision.allowed is True
    assert reviewer.moves == 0, "nothing to close"


@pytest.mark.parametrize("state", [REVIEW_QUESTION, REVIEW_ANSWER])
def test_an_unrated_card_is_left_without_mutating_anki(state: str) -> None:
    arbiter, reviewer, _session = build(state)

    decision = arbiter.request_session_start()

    assert decision.allowed is True
    assert reviewer.moves == 1
    assert reviewer.current == DECK_BROWSER


def test_an_in_flight_rating_is_waited_for_not_closed() -> None:
    arbiter, reviewer, _session = build(REVIEW_TRANSITION)

    decision = arbiter.request_session_start()

    assert decision.allowed is False
    assert decision.reason == "rating_in_flight"
    assert decision.waiting is True
    assert decision.message == WAITING_MESSAGE
    assert reviewer.moves == 0, (
        "prototype 0003: the stock callback still owns Reviewer.card"
    )


def test_a_rating_marked_in_flight_blocks_even_from_a_quiet_state() -> None:
    arbiter, reviewer, _session = build(REVIEW_ANSWER)
    arbiter.on_rating_started()

    decision = arbiter.request_session_start()

    assert decision.waiting is True
    assert reviewer.moves == 0


def test_the_session_may_start_once_the_callback_completes() -> None:
    arbiter, reviewer, _session = build(REVIEW_TRANSITION)
    arbiter.on_rating_started()
    assert arbiter.request_session_start().allowed is False

    arbiter.on_rating_completed()
    reviewer.current = REVIEW_ANSWER

    decision = arbiter.request_session_start()
    assert decision.allowed is True
    assert reviewer.current == DECK_BROWSER


def test_repeated_requests_while_waiting_never_force_anything() -> None:
    arbiter, reviewer, session = build(REVIEW_TRANSITION)

    for _ in range(10):
        decision = arbiter.request_session_start()
        assert decision.allowed is False
        assert decision.waiting is True

    # A timeout is not permission: nothing was closed, cleaned or started.
    assert reviewer.moves == 0
    assert session.paused == 0


def test_a_reviewer_that_refuses_to_close_is_reported_not_forced() -> None:
    arbiter, reviewer, _session = build(REVIEW_QUESTION)
    reviewer.stuck = True

    decision = arbiter.request_session_start()

    assert decision.allowed is False
    assert decision.reason == "reviewer_did_not_close"
    assert reviewer.moves == 1, "asked once, politely, and then gave up"


def test_closing_the_reviewer_never_resumes_ankigta() -> None:
    arbiter, _reviewer, session = build()
    arbiter.on_reviewer_opened()
    session.events.clear()

    arbiter.on_reviewer_closed()

    # ADR 0022: the user restarts study explicitly.
    assert session.events == []


def test_an_unsupported_build_blocks_rather_than_guesses() -> None:
    arbiter, reviewer, session = build(REVIEW_QUESTION, supported=False)

    start = arbiter.request_session_start()
    opened = arbiter.on_reviewer_opened()

    assert start.allowed is False
    assert start.reason == "unsupported_anki"
    assert opened.allowed is False
    assert reviewer.moves == 0
    assert session.paused == 0


def test_an_unresolved_transaction_blocks_session_start() -> None:
    arbiter, _reviewer, _session = build(DECK_BROWSER, unresolved=True)

    decision = arbiter.request_session_start()

    assert decision.allowed is False
    assert decision.reason == "outcome_unknown"


def test_an_unrecognised_reviewer_state_is_refused() -> None:
    arbiter, reviewer, _session = build("review/somethingNew")

    decision = arbiter.request_session_start()

    assert decision.allowed is False
    assert decision.reason == "reviewer_state_unknown"
    assert reviewer.moves == 0


def test_arbitration_never_patches_or_cancels_anki() -> None:
    """ADR 0022 forbids all three of these outright."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "companion"
        / "ankigta_companion"
        / "arbitration.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "setattr(",
        "monkeypatch",
        "__dict__",
        ".cancel(",
        "_card",
        "col.db",
    ):
        assert forbidden not in source, f"arbitration must not use {forbidden}"
