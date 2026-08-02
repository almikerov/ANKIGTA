from __future__ import annotations

import json
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

from .connection_config import (
    AutomaticConnection,
    CompanionConnection,
    ConnectionConfig,
    ConnectionConfigPublisher,
    ConnectionMode,
    ConnectionConfigError,
)
from .contract import RuntimeObservation
from .cards import CardPickerService
from .notes import NoteEditorService
from .http_server import HealthServer
from .session import SessionCoordinator


@dataclass
class _ConnectionSettings:
    resource_folder: Path | None
    automatic_port: int
    automatic_token: str
    mode: ConnectionMode = ConnectionMode.AUTOMATIC
    manual_port: int | None = None
    manual_token: str | None = None
    revision: int = 1
    unprotected_warning_dismissed: bool = False


class CompanionConnectionManager:
    def __init__(
        self,
        *,
        observe: Callable[[], RuntimeObservation],
        settings_path: Path,
        generate_token: Callable[[], str] | None = None,
        card_picker: CardPickerService | None = None,
        note_editor: NoteEditorService | None = None,
        session_coordinator: SessionCoordinator | None = None,
    ) -> None:
        self._observe = observe
        self._settings_path = settings_path
        self._generate_token = generate_token or (
            lambda: secrets.token_urlsafe(32)
        )
        self._card_picker = card_picker
        self._note_editor = note_editor
        self._session_coordinator = session_coordinator
        self._settings: _ConnectionSettings | None = None
        self._server: HealthServer | None = None
        self._started = False

    @property
    def server(self) -> HealthServer:
        if self._server is None:
            raise RuntimeError("companion connection manager is not started")
        return self._server

    def start(self) -> None:
        if self._started:
            return
        settings = self._load_settings()
        if settings is None:
            token = self._generate_token()
            if not token:
                raise ValueError("generated connection token must not be empty")
            settings = _ConnectionSettings(
                resource_folder=None,
                automatic_port=0,
                automatic_token=token,
            )
        self._settings = settings
        port, token = self._effective_connection(settings)
        port_changed = False
        try:
            self._server = self._new_server(port, token)
        except OSError:
            if settings.mode is ConnectionMode.MANUAL:
                raise
            self._server = self._new_server(0, token)
            settings.automatic_port = self._server.port
            settings.revision += 1
            port_changed = True
        try:
            self._server.start()
            if settings.automatic_port == 0:
                settings.automatic_port = self._server.port
            if port_changed and settings.resource_folder is not None:
                self._publish(
                    ConnectionConfigPublisher(settings.resource_folder),
                    settings,
                )
                self._persist(settings)
            self._started = True
        except BaseException:
            self._server.stop()
            self._server = None
            self._settings = None
            raise

    def stop(self) -> None:
        if not self._started:
            return
        self.server.stop()
        self._started = False

    def select_resource_folder(self, resource_folder: Path) -> None:
        settings = self._required_settings()
        publisher = ConnectionConfigPublisher(resource_folder)
        proposed = replace(
            settings,
            resource_folder=resource_folder.resolve(),
        )
        self._publish(publisher, proposed)
        self._persist(proposed)
        self._settings = proposed

    def set_manual_connection(self, port: int, token: str | None) -> None:
        if port < 1 or port > 65535:
            raise ValueError("manual port must be from 1 to 65535")
        settings = self._required_settings()
        if settings.resource_folder is None:
            raise ConnectionConfigError(
                "select the MTA resource folder before manual configuration"
            )
        if token is None:
            token = self._effective_connection(settings)[1]
        previous = replace(settings)
        self._switch_listener(port, token)
        try:
            settings.mode = ConnectionMode.MANUAL
            settings.manual_port = port
            settings.manual_token = token
            settings.revision += 1
            settings.unprotected_warning_dismissed = False
            self._publish(
                ConnectionConfigPublisher(settings.resource_folder),
                settings,
            )
            self._persist(settings)
        except BaseException:
            self._restore_connection(previous)
            raise

    def use_automatic_connection(self) -> None:
        settings = self._required_settings()
        if settings.resource_folder is None:
            raise ConnectionConfigError(
                "select the MTA resource folder before automatic configuration"
            )
        previous = replace(settings)
        try:
            try:
                self._switch_listener(
                    settings.automatic_port,
                    settings.automatic_token,
                )
            except OSError:
                self._switch_listener(0, settings.automatic_token)
                settings.automatic_port = self.server.port
            settings.mode = ConnectionMode.AUTOMATIC
            settings.manual_port = None
            settings.manual_token = None
            settings.revision += 1
            settings.unprotected_warning_dismissed = False
            self._publish(
                ConnectionConfigPublisher(settings.resource_folder),
                settings,
            )
            self._persist(settings)
        except BaseException:
            self._restore_connection(previous)
            raise

    def dismiss_unprotected_warning(self) -> None:
        settings = self._required_settings()
        if self._effective_connection(settings)[1] != "":
            return
        settings.unprotected_warning_dismissed = True
        self._persist(settings)

    def status(self) -> dict[str, object]:
        settings = self._required_settings()
        token = (
            settings.automatic_token
            if settings.mode is ConnectionMode.AUTOMATIC
            else settings.manual_token
        )
        return {
            "configured": settings.resource_folder is not None,
            "mode": settings.mode.value,
            "port": self.server.port,
            "tokenProtected": bool(token),
            "unprotectedWarning": token == "",
            "unprotectedWarningDismissed": (
                settings.unprotected_warning_dismissed
            ),
        }

    def _publish(
        self,
        publisher: ConnectionConfigPublisher,
        settings: _ConnectionSettings,
    ) -> None:
        publisher.publish(
            ConnectionConfig(
                revision=settings.revision,
                automatic=AutomaticConnection(
                    port=settings.automatic_port,
                    token=settings.automatic_token,
                ),
                companion=(
                    CompanionConnection(mode=ConnectionMode.AUTOMATIC)
                    if settings.mode is ConnectionMode.AUTOMATIC
                    else CompanionConnection(
                        mode=ConnectionMode.MANUAL,
                        port=settings.manual_port,
                        token_digest=sha256(
                            (settings.manual_token or "").encode("utf-8")
                        ).hexdigest(),
                    )
                ),
            )
        )

    def _persist(self, settings: _ConnectionSettings) -> None:
        value: dict[str, object] = {
            "format": "ankigta-companion-connection-settings",
            "formatVersion": 1,
            "resourceFolder": str(settings.resource_folder),
            "revision": settings.revision,
            "automatic": {
                "port": settings.automatic_port,
                "token": settings.automatic_token,
            },
            "companion": (
                {"mode": settings.mode.value}
                if settings.mode is ConnectionMode.AUTOMATIC
                else {
                    "mode": settings.mode.value,
                    "port": settings.manual_port,
                    "token": settings.manual_token,
                }
            ),
            "unprotectedWarningDismissed": (
                settings.unprotected_warning_dismissed
            ),
        }
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        candidate = self._settings_path.with_suffix(
            f"{self._settings_path.suffix}.tmp"
        )
        candidate.write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(candidate, self._settings_path)

    def _required_settings(self) -> _ConnectionSettings:
        if self._settings is None:
            raise RuntimeError("companion connection manager is not started")
        return self._settings

    def _switch_listener(self, port: int, token: str) -> None:
        old_server = self.server
        if port != old_server.port:
            new_server = self._new_server(port, token)
            new_server.start()
            self._server = new_server
            old_server.stop()
            return

        old_server.stop()
        try:
            new_server = self._new_server(port, token)
        except BaseException:
            restored = self._new_server(
                port,
                self._effective_connection(self._required_settings())[1],
            )
            restored.start()
            self._server = restored
            raise
        new_server.start()
        self._server = new_server

    def _new_server(self, port: int, token: str) -> HealthServer:
        return HealthServer(
            self._observe,
            port=port,
            token=token,
            card_picker=self._card_picker,
            note_editor=self._note_editor,
            session_coordinator=self._session_coordinator,
        )

    def _restore_connection(self, settings: _ConnectionSettings) -> None:
        self._settings = settings
        port, token = self._effective_connection(settings)
        self._switch_listener(port, token)

    def _effective_connection(
        self,
        settings: _ConnectionSettings,
    ) -> tuple[int, str]:
        if settings.mode is ConnectionMode.AUTOMATIC:
            return settings.automatic_port, settings.automatic_token
        if settings.manual_port is None or settings.manual_token is None:
            raise ConnectionConfigError(
                "manual companion settings are incomplete"
            )
        return settings.manual_port, settings.manual_token

    def _load_settings(self) -> _ConnectionSettings | None:
        if not self._settings_path.exists():
            return None
        value = json.loads(self._settings_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ConnectionConfigError(
                "companion connection settings must be a JSON object"
            )
        if (
            value.get("format")
            != "ankigta-companion-connection-settings"
            or value.get("formatVersion") != 1
        ):
            raise ConnectionConfigError(
                "unsupported companion connection settings"
            )
        resource_folder_value = value.get("resourceFolder")
        resource_folder = (
            Path(resource_folder_value)
            if isinstance(resource_folder_value, str)
            and resource_folder_value
            and resource_folder_value != "None"
            else None
        )
        revision = value.get("revision")
        if (
            not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 1
        ):
            raise ConnectionConfigError("invalid connection settings revision")
        automatic = value.get("automatic")
        if not isinstance(automatic, dict):
            raise ConnectionConfigError("automatic connection is missing")
        automatic_port = automatic.get("port")
        automatic_token = automatic.get("token")
        if (
            not isinstance(automatic_port, int)
            or isinstance(automatic_port, bool)
            or automatic_port < 1
            or automatic_port > 65535
            or not isinstance(automatic_token, str)
        ):
            raise ConnectionConfigError("invalid automatic connection")
        companion = value.get("companion")
        if not isinstance(companion, dict):
            raise ConnectionConfigError("companion connection is missing")
        raw_mode = companion.get("mode")
        if not isinstance(raw_mode, str):
            raise ConnectionConfigError("invalid companion connection mode")
        try:
            mode = ConnectionMode(raw_mode)
        except ValueError as error:
            raise ConnectionConfigError(
                "invalid companion connection mode"
            ) from error
        dismissed = value.get("unprotectedWarningDismissed", False)
        if not isinstance(dismissed, bool):
            raise ConnectionConfigError("invalid warning preference")
        manual_port: int | None = None
        manual_token: str | None = None
        if mode is ConnectionMode.MANUAL:
            raw_manual_port = companion.get("port")
            raw_manual_token = companion.get("token")
            if (
                not isinstance(raw_manual_port, int)
                or isinstance(raw_manual_port, bool)
                or raw_manual_port < 1
                or raw_manual_port > 65535
                or not isinstance(raw_manual_token, str)
            ):
                raise ConnectionConfigError(
                    "invalid manual companion connection"
                )
            manual_port = raw_manual_port
            manual_token = raw_manual_token
        return _ConnectionSettings(
            resource_folder=resource_folder,
            automatic_port=automatic_port,
            automatic_token=automatic_token,
            mode=mode,
            manual_port=manual_port,
            manual_token=manual_token,
            revision=revision,
            unprotected_warning_dismissed=dismissed,
        )
