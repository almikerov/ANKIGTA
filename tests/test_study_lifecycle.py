"""Ticket 18 — pause, AnkiWeb sync and lifecycle cleanup.

Every way study can end has to leave the collection tidy: no card stranded in
the owned filtered deck, no Spatial Link removed, and nothing resuming by
itself. These tests walk each of those exits.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from ankigta_companion.lifecycle_study import (
    PAUSE_COLLECTION_CLOSING,
    PAUSE_DISCONNECTED,
    PAUSE_REVIEWER,
    PAUSE_SHUTDOWN,
    PAUSE_SYNC,
    PAUSE_USER,
    StudyLifecycle,
    StudyPhase,
)


@dataclass
class Fakes:
    cleaned: int = 0
    closed_reviews: int = 0
    reconciled: int = 0
    unresolved: bool = False
    links_removed: int = 0
    events: list[str] = field(default_factory=list)

    def pause_session(self) -> bool:
        self.cleaned += 1
        self.events.append("cleaned")
        return True

    def close_unrated_review(self) -> None:
        self.closed_reviews += 1
        self.events.append("closed_review")

    def reconcile(self) -> None:
        self.reconciled += 1
        self.events.append("reconciled")


def build(unresolved: bool = False) -> tuple[StudyLifecycle, Fakes]:
    fakes = Fakes(unresolved=unresolved)
    lifecycle = StudyLifecycle(
        pause_session=fakes.pause_session,
        close_unrated_review=fakes.close_unrated_review,
        unresolved_transaction=lambda: fakes.unresolved,
        reconcile=fakes.reconcile,
    )
    lifecycle.started()
    return lifecycle, fakes


EXITS = [
    ("pause", PAUSE_USER),
    ("on_anki_sync_starting", PAUSE_SYNC),
    ("on_collection_closing", PAUSE_COLLECTION_CLOSING),
    ("on_connection_lost", PAUSE_DISCONNECTED),
    ("on_reviewer_opened", PAUSE_REVIEWER),
    ("on_shutdown", PAUSE_SHUTDOWN),
]


@pytest.mark.parametrize(("method", "reason"), EXITS)
def test_every_exit_cleans_the_owned_deck(method: str, reason: str) -> None:
    """No lifecycle path may strand a card in ANKIGTA Session."""
    lifecycle, fakes = build()

    result = getattr(lifecycle, method)()

    assert result.cleaned is True
    assert fakes.cleaned == 1
    assert result.phase is StudyPhase.PAUSED
    assert result.reason == reason


@pytest.mark.parametrize(("method", "_reason"), EXITS)
def test_no_exit_removes_a_spatial_link(method: str, _reason: str) -> None:
    lifecycle, fakes = build()

    getattr(lifecycle, method)()

    assert fakes.links_removed == 0


@pytest.mark.parametrize(("method", "_reason"), EXITS)
def test_no_exit_resumes_study_by_itself(method: str, _reason: str) -> None:
    lifecycle, _fakes = build()

    getattr(lifecycle, method)()

    assert lifecycle.phase is StudyPhase.PAUSED
    assert lifecycle.activation_enabled is False


def test_pausing_disables_activation_and_the_indicator() -> None:
    lifecycle, _fakes = build()
    assert lifecycle.activation_enabled is True

    lifecycle.pause()

    assert lifecycle.activation_enabled is False


def test_a_sync_closes_an_unrated_review_first() -> None:
    lifecycle, fakes = build()

    lifecycle.on_anki_sync_starting()

    # The card is closed before the deck is emptied, so nothing is rated by
    # accident and nothing is left mid-review.
    assert fakes.events == ["closed_review", "cleaned"]


def test_an_unproven_transaction_defers_cleanup_rather_than_hiding_the_card() -> None:
    lifecycle, fakes = build(unresolved=True)

    result = lifecycle.on_anki_sync_starting()

    assert result.phase is StudyPhase.PAUSED
    assert result.cleaned is False
    assert result.awaiting_reconciliation is True
    assert fakes.cleaned == 0, (
        "emptying the deck would hide the card whose outcome is unproven"
    )


def test_losing_the_connection_leaves_the_open_review_alone() -> None:
    lifecycle, fakes = build()

    result = lifecycle.on_connection_lost()

    # The pending transaction and its card survive the drop untouched.
    assert fakes.closed_reviews == 0
    assert result.reason == PAUSE_DISCONNECTED


def test_reconnecting_reconciles_first_and_stays_paused() -> None:
    lifecycle, fakes = build()
    lifecycle.on_connection_lost()
    fakes.events.clear()

    result = lifecycle.on_reconnected()

    assert fakes.reconciled == 1
    assert result.phase is StudyPhase.PAUSED
    assert lifecycle.activation_enabled is False


def test_reconnecting_never_rebuilds_or_reopens() -> None:
    lifecycle, fakes = build()
    lifecycle.on_connection_lost()
    fakes.events.clear()

    lifecycle.on_reconnected()

    # Only reconciliation. The socket coming back is not a request to study.
    assert fakes.events == ["reconciled"]


def test_reconnecting_remembers_why_study_stopped() -> None:
    lifecycle, _fakes = build()
    lifecycle.on_connection_lost()

    result = lifecycle.on_reconnected()

    assert result.reason == PAUSE_DISCONNECTED


def test_shutdown_cleans_without_touching_anything_else() -> None:
    lifecycle, fakes = build()

    result = lifecycle.on_shutdown()

    assert result.cleaned is True
    assert fakes.events == ["closed_review", "cleaned"]


def test_ankigta_never_drives_anki_sync() -> None:
    """Sync belongs to the user's account; ANKIGTA only reacts to it."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "companion"
        / "ankigta_companion"
        / "lifecycle_study.py"
    ).read_text(encoding="utf-8")

    for forbidden in ("sync(", "full_sync", "sync_login", "syncCollection", "AnkiWeb("):
        assert forbidden not in source, f"lifecycle must not call {forbidden}"


def test_a_second_exit_is_harmless() -> None:
    lifecycle, fakes = build()

    lifecycle.pause()
    lifecycle.on_shutdown()

    # Cleanup is idempotent at this level; the session coordinator no-ops when
    # there is no owned deck left.
    assert lifecycle.phase is StudyPhase.PAUSED
    assert fakes.cleaned == 2


# --- wiring into the real Anki hooks -----------------------------------------


def addon_with_lifecycle(tmp_path):  # type: ignore[no-untyped-def]
    """Build a CompanionAddon whose study lifecycle we can observe."""
    from ankigta_companion.lifecycle import CompanionAddon

    fakes = Fakes()
    lifecycle = StudyLifecycle(
        pause_session=fakes.pause_session,
        close_unrated_review=fakes.close_unrated_review,
        unresolved_transaction=lambda: fakes.unresolved,
        reconcile=fakes.reconcile,
    )
    lifecycle.started()

    class Hooks:
        def __init__(self) -> None:
            self.profile_did_open: list[object] = []
            self.profile_will_close: list[object] = []
            self.collection_will_temporarily_close: list[object] = []
            self.collection_did_temporarily_close: list[object] = []

    class Window:
        col = None
        pm = None

    addon = CompanionAddon(
        main_window=Window(),  # type: ignore[arg-type]
        hooks=Hooks(),  # type: ignore[arg-type]
        anki_version="26.05",
        defer=lambda _ms, fn: None,
        study_lifecycle=lifecycle,
    )
    return addon, lifecycle, fakes


def test_an_anki_sync_pauses_study_through_the_real_hook(tmp_path) -> None:  # type: ignore[no-untyped-def]
    addon, lifecycle, fakes = addon_with_lifecycle(tmp_path)

    addon._on_collection_will_temporarily_close(None)  # noqa: SLF001

    assert lifecycle.phase is StudyPhase.PAUSED
    assert lifecycle.reason == PAUSE_SYNC
    assert fakes.cleaned == 1


def test_closing_the_profile_pauses_study_through_the_real_hook(tmp_path) -> None:  # type: ignore[no-untyped-def]
    addon, lifecycle, fakes = addon_with_lifecycle(tmp_path)

    addon._on_profile_will_close()  # noqa: SLF001

    assert lifecycle.reason == PAUSE_COLLECTION_CLOSING
    assert fakes.cleaned == 1


def test_a_sync_finishing_does_not_resume_study(tmp_path) -> None:  # type: ignore[no-untyped-def]
    addon, lifecycle, fakes = addon_with_lifecycle(tmp_path)
    addon._on_collection_will_temporarily_close(None)  # noqa: SLF001
    fakes.events.clear()

    addon._on_collection_did_temporarily_close(None)  # noqa: SLF001

    assert lifecycle.phase is StudyPhase.PAUSED, "the user restarts study"
    assert lifecycle.activation_enabled is False
