"""Ticket 13 — early, unavailable and daily-limit behaviour.

Three permissions, deliberately separate: showing a card, rating it, and letting
it drive automatic study. Most of these tests exist to pin the cases where they
differ.
"""

from __future__ import annotations

import pytest

from ankigta_companion.cards import (
    QUEUE_TYPE_DAY_LEARN_RELEARN,
    QUEUE_TYPE_LRN,
    QUEUE_TYPE_MANUALLY_BURIED,
    QUEUE_TYPE_NEW,
    QUEUE_TYPE_PREVIEW,
    QUEUE_TYPE_REV,
    QUEUE_TYPE_SIBLING_BURIED,
    QUEUE_TYPE_SUSPENDED,
    CardState,
    CardView,
    card_state,
)
from ankigta_companion.collection_identity import AnkiCardIdentity
from ankigta_companion.eligibility import (
    WARNING_BEYOND_DAILY_LIMIT,
    WARNING_EARLY_REVIEW,
    WARNING_EARLY_REVIEW_UNSUPPORTED,
    WARNING_NOT_DUE,
    WARNING_UNAVAILABLE,
    EligibilitySettings,
    classify,
)


UUID = "11111111-1111-4111-8111-111111111111"


def card(state: CardState, card_id: int = 7) -> CardView:
    return CardView(
        identity=AnkiCardIdentity(UUID, card_id),
        deck_id=10,
        deck_name="Source",
        state=state,
        due=0,
        tags=(),
    )


@pytest.mark.parametrize("state", [CardState.SUSPENDED, CardState.BURIED])
def test_unavailable_cards_are_viewable_but_never_rateable(
    state: CardState,
) -> None:
    result = classify(card(state))

    assert result.rateable is False
    assert result.preview_only is True
    assert result.automatic is False
    assert result.warnings == (WARNING_UNAVAILABLE,)


@pytest.mark.parametrize("state", [CardState.SUSPENDED, CardState.BURIED])
def test_early_review_never_overrides_suspend_or_bury(state: CardState) -> None:
    """The setting governs *when* a card may be rated, not the user's own hold."""
    result = classify(
        card(state),
        EligibilitySettings(allow_early_review=True),
    )

    assert result.rateable is False
    assert result.automatic is False


def test_a_not_due_card_is_preview_only_by_default() -> None:
    result = classify(card(CardState.NOT_DUE))

    assert result.preview_only is True
    assert result.automatic is False, "must not interrupt the player unasked"
    assert result.warnings == (WARNING_NOT_DUE,)


def test_enabling_early_review_makes_a_not_due_card_rateable_with_a_warning() -> None:
    result = classify(
        card(CardState.NOT_DUE),
        EligibilitySettings(allow_early_review=True),
    )

    assert result.rateable is True
    assert result.automatic is True
    assert WARNING_EARLY_REVIEW in result.warnings


def test_early_review_degrades_to_preview_on_an_unverified_build() -> None:
    result = classify(
        card(CardState.NOT_DUE),
        EligibilitySettings(allow_early_review=True, early_review_supported=False),
    )

    assert result.preview_only is True
    assert WARNING_EARLY_REVIEW_UNSUPPORTED in result.warnings


@pytest.mark.parametrize(
    "state",
    [CardState.NEW, CardState.LEARNING, CardState.REVIEW],
)
def test_ordinary_cards_are_rateable_and_drive_automatic_study(
    state: CardState,
) -> None:
    result = classify(card(state))

    assert result.rateable is True
    assert result.automatic is True
    assert result.warnings == ()


def test_a_new_card_beyond_the_daily_limit_stays_rateable_and_warns() -> None:
    result = classify(
        card(CardState.NEW),
        beyond_daily_limit=lambda _identity: True,
    )

    # ADR 0020: the limit becomes a warning, not a gate.
    assert result.rateable is True
    assert result.automatic is True
    assert result.warnings == (WARNING_BEYOND_DAILY_LIMIT,)


def test_the_daily_limit_is_asked_about_only_for_new_cards() -> None:
    asked: list[AnkiCardIdentity] = []

    def query(identity: AnkiCardIdentity) -> bool:
        asked.append(identity)
        return True

    for state in (CardState.REVIEW, CardState.LEARNING, CardState.NOT_DUE):
        classify(card(state), beyond_daily_limit=query)
    assert asked == []

    classify(card(CardState.NEW), beyond_daily_limit=query)
    assert len(asked) == 1


def test_the_policy_never_computes_a_limit_itself() -> None:
    """Anki stays the only scheduler (ADR 0017)."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "companion"
        / "ankigta_companion"
        / "eligibility.py"
    ).read_text(encoding="utf-8")

    for forbidden in ("perDay", "per_day", "newCount", "find_cards", "col.db"):
        assert forbidden not in source, f"policy must not compute {forbidden}"


# --- queue classification ----------------------------------------------------


def state_for(queue: int, due: int = 0, today: int = 0) -> CardState:
    return card_state(queue, due, today)


@pytest.mark.parametrize(
    ("queue", "expected"),
    [
        (QUEUE_TYPE_SUSPENDED, CardState.SUSPENDED),
        (QUEUE_TYPE_SIBLING_BURIED, CardState.BURIED),
        (QUEUE_TYPE_MANUALLY_BURIED, CardState.BURIED),
        (QUEUE_TYPE_NEW, CardState.NEW),
        (QUEUE_TYPE_LRN, CardState.LEARNING),
        (QUEUE_TYPE_DAY_LEARN_RELEARN, CardState.LEARNING),
        (QUEUE_TYPE_REV, CardState.REVIEW),
    ],
)
def test_every_anki_queue_maps_to_the_right_state(
    queue: int,
    expected: CardState,
) -> None:
    assert state_for(queue) is expected


def test_a_manually_buried_card_is_buried_not_review() -> None:
    """It used to fall through to REVIEW and would then have been rated."""
    assert state_for(QUEUE_TYPE_MANUALLY_BURIED) is CardState.BURIED
    assert classify(card(state_for(QUEUE_TYPE_MANUALLY_BURIED))).rateable is False


def test_a_card_in_ankis_own_preview_queue_is_not_a_due_review() -> None:
    assert state_for(QUEUE_TYPE_PREVIEW) is CardState.NOT_DUE
    assert classify(card(state_for(QUEUE_TYPE_PREVIEW))).automatic is False


def test_an_unknown_queue_is_not_assumed_rateable() -> None:
    # A queue this build does not know about must not become a due review.
    assert state_for(99) is CardState.NOT_DUE
