from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pytest

from ankigta_companion.lifecycle import CompanionAddon
from test_health_contract import post_health


@dataclass
class FakeDeckConfiguration:
    fsrs: bool


@dataclass
class FakeDecks:
    fsrs: bool

    def get_current_id(self) -> int:
        return 1

    def get_deck_configs_for_update(self, deck_id: int) -> FakeDeckConfiguration:
        assert deck_id == 1
        return FakeDeckConfiguration(fsrs=self.fsrs)


@dataclass
class FakeCollection:
    fsrs: bool
    decks: FakeDecks = field(init=False)

    def __post_init__(self) -> None:
        self.decks = FakeDecks(self.fsrs)

    def v3_scheduler(self) -> bool:
        return True


@dataclass
class FakeProfileManager:
    name: str = "Lifecycle Profile"


@dataclass
class FakeMainWindow:
    col: FakeCollection | None = None
    pm: FakeProfileManager = field(default_factory=FakeProfileManager)


@dataclass
class FakeHooks:
    profile_did_open: list[Callable[[], None]] = field(default_factory=list)
    profile_will_close: list[Callable[[], None]] = field(default_factory=list)


def request_health(addon: CompanionAddon, request_id: str) -> tuple[int, dict[str, object]]:
    return post_health(
        addon.server,
        {
            "protocol": "ankigta-control",
            "protocolVersion": 1,
            "requestId": request_id,
        },
    )


def test_addon_observes_profile_lifecycle_and_releases_listener() -> None:
    main_window = FakeMainWindow()
    hooks = FakeHooks()
    addon = CompanionAddon(
        main_window=main_window,
        hooks=hooks,
        anki_version="26.05",
    )
    addon.start()

    status, response = request_health(addon, "before-open")
    assert status == 503
    assert response["payload"]["collection"]["state"] == "absent"

    main_window.col = FakeCollection(fsrs=True)
    hooks.profile_did_open[0]()
    status, response = request_health(addon, "after-open")
    assert status == 200
    assert response["payload"]["collection"] == {
        "state": "open",
        "profileName": "Lifecycle Profile",
    }

    hooks.profile_will_close[0]()
    status, response = request_health(addon, "while-closing")
    assert status == 503
    assert response["payload"]["collection"]["state"] == "closing"

    addon.stop()
    assert hooks.profile_did_open == []
    assert hooks.profile_will_close == []
    with pytest.raises(OSError):
        request_health(addon, "after-unload")
