from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import Protocol

from .contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)
from .http_server import HealthServer


class DeckConfiguration(Protocol):
    fsrs: bool


class DeckManager(Protocol):
    def get_current_id(self) -> int: ...

    def get_deck_configs_for_update(
        self,
        deck_id: int,
    ) -> DeckConfiguration: ...


class Collection(Protocol):
    decks: DeckManager

    def v3_scheduler(self) -> bool: ...


class ProfileManager(Protocol):
    name: str


class MainWindow(Protocol):
    col: Collection | None
    pm: ProfileManager


class GuiHooks(Protocol):
    profile_did_open: list[Callable[[], None]]
    profile_will_close: list[Callable[[], None]]


class ObservationStore:
    def __init__(self, observation: RuntimeObservation) -> None:
        self._observation = observation
        self._lock = Lock()

    def get(self) -> RuntimeObservation:
        with self._lock:
            return self._observation

    def set(self, observation: RuntimeObservation) -> None:
        with self._lock:
            self._observation = observation


class CompanionAddon:
    def __init__(
        self,
        *,
        main_window: MainWindow,
        hooks: GuiHooks,
        anki_version: str,
        defer: Callable[[int, Callable[[], None]], None],
        port: int = 0,
    ) -> None:
        self._main_window = main_window
        self._hooks = hooks
        self._anki_version = anki_version
        self._defer = defer
        self._observations = ObservationStore(
            RuntimeObservation(
                anki_version=anki_version,
                v3_scheduler=False,
                fsrs_enabled=False,
                collection=CollectionObservation(state=CollectionState.ABSENT),
            )
        )
        self.server = HealthServer(self._observations.get, port=port)
        self._started = False
        self._collection_generation = 0

    def start(self) -> None:
        if self._started:
            return
        self._hooks.profile_did_open.append(self._on_profile_did_open)
        self._hooks.profile_will_close.append(self._on_profile_will_close)
        if self._main_window.col is not None:
            self._on_profile_did_open()
        self.server.start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self.server.stop()
        self._hooks.profile_did_open.remove(self._on_profile_did_open)
        self._hooks.profile_will_close.remove(self._on_profile_will_close)
        self._started = False

    def _on_profile_did_open(self) -> None:
        self._collection_generation += 1
        collection = self._main_window.col
        if collection is None:
            return
        deck_id = collection.decks.get_current_id()
        deck_configuration = collection.decks.get_deck_configs_for_update(deck_id)
        self._observations.set(
            RuntimeObservation(
                anki_version=self._anki_version,
                v3_scheduler=bool(collection.v3_scheduler()),
                fsrs_enabled=bool(deck_configuration.fsrs),
                collection=CollectionObservation(
                    state=CollectionState.OPEN,
                    profile_name=self._main_window.pm.name,
                ),
            )
        )

    def _on_profile_will_close(self) -> None:
        self._collection_generation += 1
        closing_generation = self._collection_generation
        current = self._observations.get()
        self._observations.set(
            RuntimeObservation(
                anki_version=current.anki_version,
                v3_scheduler=current.v3_scheduler,
                fsrs_enabled=current.fsrs_enabled,
                collection=CollectionObservation(
                    state=CollectionState.CLOSING,
                    profile_name=current.collection.profile_name,
                ),
            )
        )
        self._defer(
            0,
            lambda: self._mark_absent_after_close(closing_generation),
        )

    def _mark_absent_after_close(self, closing_generation: int) -> None:
        if not self._started or closing_generation != self._collection_generation:
            return
        if self._main_window.col is not None:
            self._defer(
                10,
                lambda: self._mark_absent_after_close(closing_generation),
            )
            return
        current = self._observations.get()
        self._observations.set(
            RuntimeObservation(
                anki_version=current.anki_version,
                v3_scheduler=current.v3_scheduler,
                fsrs_enabled=current.fsrs_enabled,
                collection=CollectionObservation(state=CollectionState.ABSENT),
            )
        )
