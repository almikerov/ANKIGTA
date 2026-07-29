from __future__ import annotations

import json
from pathlib import Path

import pytest

import ankigta_companion.connection_config as connection_config_module
from ankigta_companion.connection_config import (
    AutomaticConnection,
    CompanionConnection,
    ConnectionConfig,
    ConnectionConfigPublisher,
    ConnectionMode,
    load_connection_config,
)


def automatic_config(port: int, token: str, revision: int) -> ConnectionConfig:
    return ConnectionConfig(
        revision=revision,
        automatic=AutomaticConnection(port=port, token=token),
        companion=CompanionConnection(mode=ConnectionMode.AUTOMATIC),
    )


def test_first_setup_publishes_one_valid_versioned_connection_config(
    tmp_path: Path,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    publisher = ConnectionConfigPublisher(resource_folder)

    publisher.publish(automatic_config(32145, "generated-token", revision=1))

    assert json.loads(publisher.current_path.read_text(encoding="utf-8")) == {
        "format": "ankigta-connection",
        "formatVersion": 1,
        "protocol": "ankigta-control",
        "protocolVersion": 1,
        "revision": 1,
        "host": "127.0.0.1",
        "automatic": {
            "port": 32145,
            "token": "generated-token",
        },
        "companion": {
            "mode": "automatic",
        },
    }
    assert not publisher.last_known_good_path.exists()
    assert list(resource_folder.glob("*.tmp")) == []


def test_temporary_write_failure_preserves_current_and_previous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    publisher = ConnectionConfigPublisher(resource_folder)
    publisher.publish(automatic_config(32145, "first-token", revision=1))
    current_before = publisher.current_path.read_bytes()

    original_write_bytes = Path.write_bytes

    def fail_candidate_write(path: Path, data: bytes) -> int:
        if path.name == "connection.json.tmp":
            raise OSError("injected temporary write failure")
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_candidate_write)

    with pytest.raises(OSError, match="temporary write failure"):
        publisher.publish(automatic_config(32146, "second-token", revision=2))

    assert publisher.current_path.read_bytes() == current_before
    assert not publisher.last_known_good_path.exists()
    assert list(resource_folder.glob("*.tmp")) == []


def test_candidate_validation_failure_never_replaces_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    publisher = ConnectionConfigPublisher(resource_folder)
    publisher.publish(automatic_config(32145, "first-token", revision=1))
    current_before = publisher.current_path.read_bytes()
    original_write_bytes = Path.write_bytes

    def corrupt_candidate(path: Path, data: bytes) -> int:
        if path.name == "connection.json.tmp":
            return original_write_bytes(path, b'{"format":"corrupt"}')
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", corrupt_candidate)

    with pytest.raises(
        connection_config_module.ConnectionConfigError,
        match="unsupported connection",
    ):
        publisher.publish(automatic_config(32146, "second-token", revision=2))

    assert publisher.current_path.read_bytes() == current_before
    assert not publisher.last_known_good_path.exists()
    assert list(resource_folder.glob("*.tmp")) == []


def test_replace_failure_leaves_a_valid_current_and_rollback_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    publisher = ConnectionConfigPublisher(resource_folder)
    publisher.publish(automatic_config(32145, "first-token", revision=1))
    current_before = publisher.current_path.read_bytes()
    original_replace = connection_config_module.os.replace

    def fail_current_replace(source: Path, destination: Path) -> None:
        if destination == publisher.current_path:
            raise OSError("injected replace failure")
        original_replace(source, destination)

    monkeypatch.setattr(
        connection_config_module.os,
        "replace",
        fail_current_replace,
    )

    with pytest.raises(OSError, match="replace failure"):
        publisher.publish(automatic_config(32146, "second-token", revision=2))

    assert publisher.current_path.read_bytes() == current_before
    assert publisher.last_known_good_path.read_bytes() == current_before
    assert list(resource_folder.glob("*.tmp")) == []


def test_invalid_current_rolls_back_to_one_last_known_good_with_warning(
    tmp_path: Path,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    publisher = ConnectionConfigPublisher(resource_folder)
    publisher.publish(automatic_config(32145, "first-token", revision=1))
    publisher.publish(automatic_config(32146, "second-token", revision=2))
    publisher.current_path.write_text('{"format":"corrupt"}', encoding="utf-8")

    loaded = load_connection_config(
        publisher.current_path,
        publisher.last_known_good_path,
    )

    assert loaded.config.revision == 1
    assert loaded.used_last_known_good is True
    assert loaded.warning_category == "connection_config_rollback"


def test_manual_candidate_requires_a_lowercase_sha256_token_digest(
    tmp_path: Path,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    publisher = ConnectionConfigPublisher(resource_folder)
    candidate = ConnectionConfig(
        revision=1,
        automatic=AutomaticConnection(port=32145, token="automatic-token"),
        companion=CompanionConnection(
            mode=ConnectionMode.MANUAL,
            port=32146,
            token_digest="z" * 64,
        ),
    )

    with pytest.raises(
        connection_config_module.ConnectionConfigError,
        match="SHA-256",
    ):
        publisher.publish(candidate)

    assert not publisher.current_path.exists()


def test_publish_retains_exactly_one_previous_validated_config(
    tmp_path: Path,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    publisher = ConnectionConfigPublisher(resource_folder)

    publisher.publish(automatic_config(32145, "first-token", revision=1))
    publisher.publish(automatic_config(32146, "second-token", revision=2))
    publisher.publish(automatic_config(32147, "third-token", revision=3))

    current = json.loads(publisher.current_path.read_text(encoding="utf-8"))
    previous = json.loads(
        publisher.last_known_good_path.read_text(encoding="utf-8")
    )
    assert current["revision"] == 3
    assert previous["revision"] == 2
    assert sorted(path.name for path in resource_folder.glob("connection*.json")) == [
        "connection.json",
        "connection.last-known-good.json",
    ]
    assert list(resource_folder.glob("*.tmp")) == []


def test_publish_recovers_from_invalid_current_using_confirmed_previous(
    tmp_path: Path,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    publisher = ConnectionConfigPublisher(resource_folder)
    publisher.publish(automatic_config(32145, "first-token", revision=1))
    publisher.publish(automatic_config(32146, "second-token", revision=2))
    publisher.current_path.write_text('{"format":"corrupt"}', encoding="utf-8")

    publisher.publish(automatic_config(32147, "third-token", revision=3))

    current = json.loads(publisher.current_path.read_text(encoding="utf-8"))
    previous = json.loads(
        publisher.last_known_good_path.read_text(encoding="utf-8")
    )
    assert current["revision"] == 3
    assert previous["revision"] == 1
    assert list(resource_folder.glob("*.tmp")) == []
