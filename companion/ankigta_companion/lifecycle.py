from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from threading import Lock
from typing import Protocol, cast

from .collection_identity import (
    CollectionCopyDecision,
    CollectionIdentityObservation,
    CollectionIdentityService,
)
from .cards import CardPickerService, CollectionLike
from .connection import CompanionConnectionManager
from .contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)
from .http_server import HealthServer
from .session import SessionCoordinator


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

    def get_config(self, key: str, default: object | None = None) -> object: ...

    def set_config(
        self,
        key: str,
        value: object,
        *,
        undoable: bool = False,
    ) -> object: ...


class ProfileManager(Protocol):
    name: str

    def collectionPath(self) -> str: ...


class MainWindow(Protocol):
    col: Collection | None
    pm: ProfileManager


class GuiHooks(Protocol):
    profile_did_open: list[Callable[[], None]]
    profile_will_close: list[Callable[[], None]]
    collection_will_temporarily_close: list[Callable[[Collection], None]]
    collection_did_temporarily_close: list[Callable[[Collection], None]]


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
        identity_service: CollectionIdentityService | None = None,
        connection_settings_path: Path | None = None,
        generate_connection_token: Callable[[], str] | None = None,
        card_picker: CardPickerService | None = None,
        session_coordinator: SessionCoordinator | None = None,
    ) -> None:
        self._main_window = main_window
        self._hooks = hooks
        self._anki_version = anki_version
        self._defer = defer
        self._identity_service = identity_service
        effective_card_picker = card_picker
        if effective_card_picker is None and identity_service is not None:
            effective_card_picker = CardPickerService(
                self.current_collection_identity,
                lambda: cast(CollectionLike | None, self._main_window.col),
            )
        self._observations = ObservationStore(
            RuntimeObservation(
                anki_version=anki_version,
                v3_scheduler=False,
                fsrs_enabled=False,
                collection=CollectionObservation(state=CollectionState.ABSENT),
            )
        )
        self._connection_manager = (
            CompanionConnectionManager(
                observe=self._observations.get,
                settings_path=connection_settings_path,
                generate_token=generate_connection_token,
                card_picker=effective_card_picker,
                session_coordinator=session_coordinator,
            )
            if connection_settings_path is not None
            else None
        )
        self._legacy_server = (
            None
            if self._connection_manager is not None
            else HealthServer(
                self._observations.get,
                port=port,
                card_picker=effective_card_picker,
                session_coordinator=session_coordinator,
            )
        )
        self._started = False
        self._collection_generation = 0

    def start(self) -> None:
        if self._started:
            return
        self._hooks.profile_did_open.append(self._on_profile_did_open)
        self._hooks.profile_will_close.append(self._on_profile_will_close)
        self._hooks.collection_will_temporarily_close.append(
            self._on_collection_will_temporarily_close
        )
        self._hooks.collection_did_temporarily_close.append(
            self._on_collection_did_temporarily_close
        )
        if self._main_window.col is not None:
            self._on_profile_did_open()
        if self._connection_manager is not None:
            self._connection_manager.start()
        else:
            self.server.start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        if self._connection_manager is not None:
            self._connection_manager.stop()
        else:
            self.server.stop()
        self._hooks.profile_did_open.remove(self._on_profile_did_open)
        self._hooks.profile_will_close.remove(self._on_profile_will_close)
        self._hooks.collection_will_temporarily_close.remove(
            self._on_collection_will_temporarily_close
        )
        self._hooks.collection_did_temporarily_close.remove(
            self._on_collection_did_temporarily_close
        )
        self._started = False

    def _on_profile_did_open(self) -> None:
        self._collection_generation += 1
        collection = self._main_window.col
        if collection is None:
            return
        deck_id = collection.decks.get_current_id()
        deck_configuration = collection.decks.get_deck_configs_for_update(deck_id)
        identity = (
            self._identity_service.observe_open_collection(
                collection,
                Path(self._main_window.pm.collectionPath()),
            )
            if self._identity_service is not None
            else None
        )
        self._observations.set(
            RuntimeObservation(
                anki_version=self._anki_version,
                v3_scheduler=bool(collection.v3_scheduler()),
                fsrs_enabled=bool(deck_configuration.fsrs),
                collection=CollectionObservation(
                    state=CollectionState.OPEN,
                    profile_name=self._main_window.pm.name,
                    identity=identity,
                ),
            )
        )

    def _on_profile_will_close(self) -> None:
        closing_generation = self._mark_collection_closing()
        self._defer(
            0,
            lambda: self._mark_absent_after_close(closing_generation),
        )

    def _on_collection_will_temporarily_close(
        self,
        _collection: Collection,
    ) -> None:
        self._mark_collection_closing()

    def _mark_collection_closing(self) -> int:
        self._collection_generation += 1
        if self._identity_service is not None:
            self._identity_service.clear_current()
        current = self._observations.get()
        self._observations.set(
            replace(
                current,
                collection=CollectionObservation(
                    state=CollectionState.CLOSING,
                    profile_name=current.collection.profile_name,
                ),
            )
        )
        return self._collection_generation

    def _on_collection_did_temporarily_close(
        self,
        _collection: Collection,
    ) -> None:
        self._on_profile_did_open()

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
            replace(
                current,
                collection=CollectionObservation(state=CollectionState.ABSENT),
            )
        )

    def bind_current_collection(
        self,
        expected_collection_uuid: str | None,
    ) -> CollectionIdentityObservation:
        if self._identity_service is None:
            raise RuntimeError("collection identity service is unavailable")
        identity = self._identity_service.bind_current(expected_collection_uuid)
        self._publish_identity(identity)
        return identity

    def decide_current_collection_copy(
        self,
        expected_collection_uuid: str | None,
        decision: CollectionCopyDecision,
    ) -> CollectionIdentityObservation:
        if self._identity_service is None:
            raise RuntimeError("collection identity service is unavailable")
        collection = self._main_window.col
        if collection is None:
            raise ValueError("no collection is open")
        identity = self._identity_service.decide_copy(
            collection,
            Path(self._main_window.pm.collectionPath()),
            expected_collection_uuid,
            decision,
        )
        self._publish_identity(identity)
        return identity

    def _publish_identity(self, identity: CollectionIdentityObservation) -> None:
        current = self._observations.get()
        self._observations.set(
            replace(
                current,
                collection=replace(
                    current.collection,
                    identity=identity,
                ),
            )
        )

    def current_collection_identity(self) -> CollectionIdentityObservation | None:
        return self._observations.get().collection.identity

    @property
    def server(self) -> HealthServer:
        if self._connection_manager is not None:
            return self._connection_manager.server
        if self._legacy_server is None:
            raise RuntimeError("companion server is unavailable")
        return self._legacy_server

    def select_mta_resource_folder(self, resource_folder: Path) -> None:
        self._required_connection_manager().select_resource_folder(
            resource_folder
        )

    def set_manual_connection(self, port: int, token: str | None) -> None:
        self._required_connection_manager().set_manual_connection(port, token)

    def use_automatic_connection(self) -> None:
        self._required_connection_manager().use_automatic_connection()

    def dismiss_unprotected_warning(self) -> None:
        self._required_connection_manager().dismiss_unprotected_warning()

    def connection_status(self) -> dict[str, object]:
        return self._required_connection_manager().status()

    def _required_connection_manager(self) -> CompanionConnectionManager:
        if self._connection_manager is None:
            raise RuntimeError("connection settings are unavailable")
        return self._connection_manager
