from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pytest

from ankigta_companion.collection_identity import CollectionIdentityService
from ankigta_companion.lifecycle import CompanionAddon
from test_health_contract import post_health, post_raw_health


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
    config: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.decks = FakeDecks(self.fsrs)

    def v3_scheduler(self) -> bool:
        return True

    def get_config(self, key: str, default: object | None = None) -> object:
        return self.config.get(key, default)

    def set_config(
        self,
        key: str,
        value: object,
        *,
        undoable: bool = False,
    ) -> object:
        assert undoable is False
        self.config[key] = value
        return object()


@dataclass
class FakeProfileManager:
    name: str = "Lifecycle Profile"
    collection_path: str = "collection.anki2"

    def collectionPath(self) -> str:
        return self.collection_path


@dataclass
class FakeMainWindow:
    col: FakeCollection | None = None
    pm: FakeProfileManager = field(default_factory=FakeProfileManager)


@dataclass
class FakeHooks:
    profile_did_open: list[Callable[[], None]] = field(default_factory=list)
    profile_will_close: list[Callable[[], None]] = field(default_factory=list)
    collection_will_temporarily_close: list[
        Callable[[FakeCollection], None]
    ] = field(default_factory=list)
    collection_did_temporarily_close: list[
        Callable[[FakeCollection], None]
    ] = field(default_factory=list)


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
    deferred: list[Callable[[], None]] = []
    addon = CompanionAddon(
        main_window=main_window,
        hooks=hooks,
        anki_version="26.05",
        defer=lambda _delay_ms, action: deferred.append(action),
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

    main_window.col = None
    deferred.pop(0)()
    status, response = request_health(addon, "after-close")
    assert status == 503
    assert response["payload"]["collection"]["state"] == "absent"

    addon.stop()
    assert hooks.profile_did_open == []
    assert hooks.profile_will_close == []
    assert hooks.collection_will_temporarily_close == []
    assert hooks.collection_did_temporarily_close == []
    with pytest.raises(OSError):
        request_health(addon, "after-unload")


def test_bound_collection_selection_pauses_a_different_open_collection(
    tmp_path: Path,
) -> None:
    first_locator = tmp_path / "Profile A" / "collection.anki2"
    second_locator = tmp_path / "Profile B" / "collection.anki2"
    first_locator.parent.mkdir()
    second_locator.parent.mkdir()
    first_locator.touch()
    second_locator.touch()
    main_window = FakeMainWindow(
        col=FakeCollection(fsrs=True),
        pm=FakeProfileManager(
            name="Profile A",
            collection_path=str(first_locator),
        ),
    )
    hooks = FakeHooks()
    deferred: list[Callable[[], None]] = []
    addon = CompanionAddon(
        main_window=main_window,
        hooks=hooks,
        anki_version="26.05",
        defer=lambda _delay_ms, action: deferred.append(action),
        identity_service=CollectionIdentityService(
            tmp_path / "collection-registry.json"
        ),
    )
    addon.start()

    _, first_health = request_health(addon, "first-unbound")
    first_uuid = first_health["payload"]["collection"]["collectionUuid"]
    addon.bind_current_collection(first_uuid)
    _, bound_health = request_health(addon, "first-bound")
    assert bound_health["payload"]["collection"]["identityState"] == "bound"

    hooks.profile_will_close[0]()
    main_window.col = FakeCollection(fsrs=True)
    main_window.pm = FakeProfileManager(
        name="Profile B",
        collection_path=str(second_locator),
    )
    hooks.profile_did_open[0]()
    _, second_health = request_health(addon, "second-open")

    assert second_health["payload"]["collection"]["collectionUuid"] != first_uuid
    assert (
        second_health["payload"]["collection"]["identityState"]
        == "wrong_collection"
    )
    assert second_health["payload"]["study"] == {
        "sessionActive": False,
        "ratingEnabled": False,
        "paused": True,
        "pausedReason": "wrong_collection",
    }
    addon.stop()


def test_timed_out_bind_is_cancelled_before_a_late_main_thread_callback(
    tmp_path: Path,
) -> None:
    locator = tmp_path / "Profile" / "collection.anki2"
    locator.parent.mkdir()
    locator.touch()
    main_window = FakeMainWindow(
        col=FakeCollection(fsrs=True),
        pm=FakeProfileManager(collection_path=str(locator)),
    )
    queued_main_actions: list[Callable[[], None]] = []
    addon = CompanionAddon(
        main_window=main_window,
        hooks=FakeHooks(),
        anki_version="26.05",
        defer=lambda _delay_ms, action: action(),
        identity_service=CollectionIdentityService(
            tmp_path / "collection-registry.json"
        ),
        run_on_main=queued_main_actions.append,
    )
    addon.start()
    _, initial = request_health(addon, "before-timeout")
    collection_uuid = initial["payload"]["collection"]["collectionUuid"]

    status, response = post_raw_health(
        addon.server,
        json.dumps(
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": "timed-out-bind",
                "collectionUuid": collection_uuid,
            }
        ).encode("utf-8"),
        path="/v1/collection/bind",
        timeout=7,
    )
    queued_main_actions.pop()()
    _, after_late_callback = request_health(addon, "after-late-callback")

    assert status == 409
    assert response["error"]["category"] == "collection_identity_timeout"
    assert (
        after_late_callback["payload"]["collection"]["identityState"]
        == "unbound"
    )
    addon.stop()
