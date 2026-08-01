"""What ANKIGTA may do with a card, and why.

Three questions get confused easily and are kept apart here:

- may the card be **shown**? Almost always yes, including suspended ones.
- may it be **rated**? Only when Anki's own scheduler would accept the rating.
- may it drive **automatic study** — the queue, activation zones, markers?
  A card the user must opt into does not get to interrupt them unasked.

The policy decides from an already-classified `CardView` plus settings. It asks
Anki nothing itself: the one genuinely scheduler-shaped question, whether a new
card sits beyond today's limit, arrives through an injected query, because
reimplementing that count would be writing a second scheduler (ADR 0017).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .cards import CardState, CardView
from .collection_identity import AnkiCardIdentity


#: Suspended and Buried. Existing, linked, viewable — but never rateable.
UNAVAILABLE_STATES = frozenset({CardState.SUSPENDED, CardState.BURIED})

WARNING_UNAVAILABLE = "card_unavailable"
WARNING_NOT_DUE = "card_not_due"
WARNING_EARLY_REVIEW = "early_review"
WARNING_BEYOND_DAILY_LIMIT = "beyond_daily_limit"
WARNING_EARLY_REVIEW_UNSUPPORTED = "early_review_unsupported"


@dataclass(frozen=True)
class EligibilitySettings:
    """The user's choices that change what a card is allowed to do."""

    allow_early_review: bool = False
    #: False on an Anki build whose early-review behaviour was never verified.
    early_review_supported: bool = True


@dataclass(frozen=True)
class Eligibility:
    identity: AnkiCardIdentity
    state: CardState
    #: May Anki be asked to rate this card at all.
    rateable: bool
    #: May it enter the session, the queue, activation zones and markers.
    automatic: bool
    warnings: tuple[str, ...] = ()

    @property
    def preview_only(self) -> bool:
        return not self.rateable


#: Answers "is this new card beyond the source deck's limit for today?".
DailyLimitQuery = Callable[[AnkiCardIdentity], bool]


def classify(
    card: CardView,
    settings: EligibilitySettings | None = None,
    beyond_daily_limit: DailyLimitQuery | None = None,
) -> Eligibility:
    """Decide what may be done with one card."""
    settings = settings or EligibilitySettings()
    warnings: list[str] = []

    if card.state in UNAVAILABLE_STATES:
        # No setting reaches this branch. Early review is about *when* a card
        # may be rated, never about overriding the user's own suspend or bury.
        return Eligibility(
            identity=card.identity,
            state=card.state,
            rateable=False,
            automatic=False,
            warnings=(WARNING_UNAVAILABLE,),
        )

    if card.state is CardState.NOT_DUE:
        if not settings.allow_early_review:
            return Eligibility(
                identity=card.identity,
                state=card.state,
                rateable=False,
                automatic=False,
                warnings=(WARNING_NOT_DUE,),
            )
        if not settings.early_review_supported:
            # The setting is on but this Anki build's early-review behaviour is
            # unverified, so degrade to Preview rather than guess.
            return Eligibility(
                identity=card.identity,
                state=card.state,
                rateable=False,
                automatic=False,
                warnings=(WARNING_NOT_DUE, WARNING_EARLY_REVIEW_UNSUPPORTED),
            )
        warnings.append(WARNING_EARLY_REVIEW)

    if (
        card.state is CardState.NEW
        and beyond_daily_limit is not None
        and beyond_daily_limit(card.identity)
    ):
        # ADR 0020: every linked new card enters regardless of the source
        # deck's daily limit; the limit becomes a warning, not a gate.
        warnings.append(WARNING_BEYOND_DAILY_LIMIT)

    return Eligibility(
        identity=card.identity,
        state=card.state,
        rateable=True,
        automatic=True,
        warnings=tuple(warnings),
    )
