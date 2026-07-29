from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .contract import PROTOCOL_NAME, PROTOCOL_VERSION


CONNECTION_FORMAT = "ankigta-connection"
CONNECTION_FORMAT_VERSION = 1
CONNECTION_FILE_NAME = "connection.json"
LAST_KNOWN_GOOD_FILE_NAME = "connection.last-known-good.json"


class ConnectionConfigError(ValueError):
    pass


class ConnectionMode(StrEnum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"


@dataclass(frozen=True)
class AutomaticConnection:
    port: int
    token: str


@dataclass(frozen=True)
class CompanionConnection:
    mode: ConnectionMode
    port: int | None = None
    token_digest: str | None = None


@dataclass(frozen=True)
class ConnectionConfig:
    revision: int
    automatic: AutomaticConnection
    companion: CompanionConnection

    def as_dict(self) -> dict[str, object]:
        companion: dict[str, object] = {
            "mode": self.companion.mode.value,
        }
        if self.companion.mode is ConnectionMode.MANUAL:
            companion.update(
                {
                    "port": self.companion.port,
                    "tokenDigest": self.companion.token_digest,
                }
            )
        return {
            "format": CONNECTION_FORMAT,
            "formatVersion": CONNECTION_FORMAT_VERSION,
            "protocol": PROTOCOL_NAME,
            "protocolVersion": PROTOCOL_VERSION,
            "revision": self.revision,
            "host": "127.0.0.1",
            "automatic": {
                "port": self.automatic.port,
                "token": self.automatic.token,
            },
            "companion": companion,
        }


@dataclass(frozen=True)
class LoadedConnectionConfig:
    config: ConnectionConfig
    used_last_known_good: bool
    warning_category: str | None


def validate_connection_config(value: object) -> ConnectionConfig:
    if not isinstance(value, dict):
        raise ConnectionConfigError("connection config must be a JSON object")
    if (
        value.get("format") != CONNECTION_FORMAT
        or value.get("formatVersion") != CONNECTION_FORMAT_VERSION
        or value.get("protocol") != PROTOCOL_NAME
        or value.get("protocolVersion") != PROTOCOL_VERSION
        or value.get("host") != "127.0.0.1"
    ):
        raise ConnectionConfigError(
            "unsupported connection format, protocol, or host"
        )
    revision = value.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ConnectionConfigError("revision must be a positive integer")
    automatic_value = value.get("automatic")
    if not isinstance(automatic_value, dict):
        raise ConnectionConfigError("automatic connection is required")
    raw_port = automatic_value.get("port")
    token = automatic_value.get("token")
    port = _validated_port(raw_port)
    if not isinstance(token, str):
        raise ConnectionConfigError("token must be a string")
    companion_value = value.get("companion")
    if not isinstance(companion_value, dict):
        raise ConnectionConfigError("companion connection is required")
    raw_mode = companion_value.get("mode")
    if not isinstance(raw_mode, str):
        raise ConnectionConfigError("invalid companion connection mode")
    try:
        mode = ConnectionMode(raw_mode)
    except ValueError as error:
        raise ConnectionConfigError("invalid companion connection mode") from error
    companion_port: int | None = None
    token_digest: str | None = None
    if mode is ConnectionMode.MANUAL:
        raw_companion_port = companion_value.get("port")
        companion_port = _validated_port(raw_companion_port)
        raw_digest = companion_value.get("tokenDigest")
        if (
            not isinstance(raw_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", raw_digest) is None
        ):
            raise ConnectionConfigError(
                "manual companion token digest must be SHA-256"
            )
        token_digest = raw_digest
    return ConnectionConfig(
        revision=revision,
        automatic=AutomaticConnection(port=port, token=token),
        companion=CompanionConnection(
            mode=mode,
            port=companion_port,
            token_digest=token_digest,
        ),
    )


def _validated_port(port: object) -> int:
    if (
        not isinstance(port, int)
        or isinstance(port, bool)
        or port < 1
        or port > 65535
    ):
        raise ConnectionConfigError("port must be an integer from 1 to 65535")
    return port


def load_connection_config(
    current_path: Path,
    last_known_good_path: Path,
) -> LoadedConnectionConfig:
    try:
        current = _read_connection_config(current_path)
    except (OSError, json.JSONDecodeError, ConnectionConfigError):
        try:
            previous = _read_connection_config(last_known_good_path)
        except (
            OSError,
            json.JSONDecodeError,
            ConnectionConfigError,
        ) as previous_error:
            raise ConnectionConfigError(
                "current and last-known-good connection configs are invalid"
            ) from previous_error
        return LoadedConnectionConfig(
            config=previous,
            used_last_known_good=True,
            warning_category="connection_config_rollback",
        )
    return LoadedConnectionConfig(
        config=current,
        used_last_known_good=False,
        warning_category=None,
    )


def _read_connection_config(path: Path) -> ConnectionConfig:
    return validate_connection_config(
        json.loads(path.read_text(encoding="utf-8"))
    )


class ConnectionConfigPublisher:
    def __init__(self, resource_folder: Path) -> None:
        if not (resource_folder / "meta.xml").is_file():
            raise ConnectionConfigError(
                "selected folder is not an MTA resource folder"
            )
        self.resource_folder = resource_folder
        self.current_path = resource_folder / CONNECTION_FILE_NAME
        self.last_known_good_path = (
            resource_folder / LAST_KNOWN_GOOD_FILE_NAME
        )
        self._candidate_path = resource_folder / f"{CONNECTION_FILE_NAME}.tmp"
        self._previous_candidate_path = resource_folder / (
            f"{LAST_KNOWN_GOOD_FILE_NAME}.tmp"
        )

    def publish(self, config: ConnectionConfig) -> None:
        encoded = json.dumps(
            config.as_dict(),
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        self._candidate_path.write_bytes(encoded)
        try:
            validate_connection_config(
                json.loads(self._candidate_path.read_text(encoding="utf-8"))
            )
            confirmed_previous: bytes | None = None
            if self.current_path.exists():
                current_bytes = self.current_path.read_bytes()
                try:
                    validate_connection_config(json.loads(current_bytes))
                except (json.JSONDecodeError, ConnectionConfigError):
                    pass
                else:
                    confirmed_previous = current_bytes
            if (
                confirmed_previous is None
                and self.last_known_good_path.exists()
            ):
                previous_bytes = self.last_known_good_path.read_bytes()
                try:
                    validate_connection_config(json.loads(previous_bytes))
                except (json.JSONDecodeError, ConnectionConfigError):
                    pass
                else:
                    confirmed_previous = previous_bytes
            if confirmed_previous is not None:
                self._previous_candidate_path.write_bytes(
                    confirmed_previous
                )
                validate_connection_config(
                    json.loads(
                        self._previous_candidate_path.read_text(encoding="utf-8")
                    )
                )
                os.replace(
                    self._previous_candidate_path,
                    self.last_known_good_path,
                )
            os.replace(self._candidate_path, self.current_path)
            if confirmed_previous is None:
                self.last_known_good_path.unlink(missing_ok=True)
        finally:
            self._candidate_path.unlink(missing_ok=True)
            self._previous_candidate_path.unlink(missing_ok=True)
