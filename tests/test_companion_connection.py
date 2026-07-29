from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

import ankigta_companion.connection as connection_module
from ankigta_companion.connection import CompanionConnectionManager
from ankigta_companion.contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)


def supported_observation() -> RuntimeObservation:
    return RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )


def test_first_folder_selection_generates_and_publishes_automatic_connection(
    tmp_path: Path,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    manager = CompanionConnectionManager(
        observe=supported_observation,
        settings_path=tmp_path / "user_files" / "connection-settings.json",
        generate_token=lambda: "generated-disposable-token",
    )

    manager.start()
    manager.select_resource_folder(resource_folder)
    published = json.loads(
        (resource_folder / "connection.json").read_text(encoding="utf-8")
    )
    status = manager.status()

    assert published["automatic"] == {
        "port": manager.server.port,
        "token": "generated-disposable-token",
    }
    assert published["companion"] == {"mode": "automatic"}
    assert status == {
        "configured": True,
        "mode": "automatic",
        "port": manager.server.port,
        "tokenProtected": True,
        "unprotectedWarning": False,
        "unprotectedWarningDismissed": False,
    }
    assert "generated-disposable-token" not in json.dumps(status)
    manager.stop()


def test_restart_chooses_another_free_port_when_saved_port_is_occupied(
    tmp_path: Path,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    settings_path = tmp_path / "user_files" / "connection-settings.json"
    first = CompanionConnectionManager(
        observe=supported_observation,
        settings_path=settings_path,
        generate_token=lambda: "stable-generated-token",
    )
    first.start()
    first.select_resource_folder(resource_folder)
    occupied_port = first.server.port
    first.stop()

    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", occupied_port))
    occupied.listen(1)
    try:
        restarted = CompanionConnectionManager(
            observe=supported_observation,
            settings_path=settings_path,
            generate_token=lambda: (_ for _ in ()).throw(
                AssertionError("restart must reuse the generated token")
            ),
        )
        restarted.start()
        published = json.loads(
            (resource_folder / "connection.json").read_text(encoding="utf-8")
        )

        assert restarted.server.port != occupied_port
        assert published["revision"] == 2
        assert published["automatic"] == {
            "port": restarted.server.port,
            "token": "stable-generated-token",
        }
        restarted.stop()
    finally:
        occupied.close()


def test_manual_override_changes_only_companion_effective_config_and_can_return_auto(
    tmp_path: Path,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    manager = CompanionConnectionManager(
        observe=supported_observation,
        settings_path=tmp_path / "user_files" / "connection-settings.json",
        generate_token=lambda: "automatic-token",
    )
    manager.start()
    manager.select_resource_folder(resource_folder)
    automatic_port = manager.server.port
    free_port_probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    free_port_probe.bind(("127.0.0.1", 0))
    manual_port = int(free_port_probe.getsockname()[1])
    free_port_probe.close()

    manager.set_manual_connection(manual_port, "")
    manual_config = json.loads(
        (resource_folder / "connection.json").read_text(encoding="utf-8")
    )

    assert manager.server.port == manual_port
    assert manual_config["automatic"] == {
        "port": automatic_port,
        "token": "automatic-token",
    }
    assert manual_config["companion"] == {
        "mode": "manual",
        "port": manual_port,
        "tokenDigest": (
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        ),
    }
    assert manager.status()["unprotectedWarning"] is True
    manager.select_resource_folder(resource_folder)
    assert manager.server.port == manual_port
    assert manager.status()["mode"] == "manual"
    manager.dismiss_unprotected_warning()
    assert manager.status()["unprotectedWarningDismissed"] is True

    manager.use_automatic_connection()
    automatic_config_after = json.loads(
        (resource_folder / "connection.json").read_text(encoding="utf-8")
    )

    assert manager.server.port == automatic_port
    assert automatic_config_after["companion"] == {"mode": "automatic"}
    assert manager.status()["unprotectedWarning"] is False
    manager.stop()


def test_failed_manual_publication_restores_previous_working_listener(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    manager = CompanionConnectionManager(
        observe=supported_observation,
        settings_path=tmp_path / "user_files" / "connection-settings.json",
        generate_token=lambda: "automatic-token",
    )
    manager.start()
    manager.select_resource_folder(resource_folder)
    automatic_port = manager.server.port
    free_port_probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    free_port_probe.bind(("127.0.0.1", 0))
    manual_port = int(free_port_probe.getsockname()[1])
    free_port_probe.close()

    def fail_publish(_publisher: object, _config: object) -> None:
        raise OSError("injected publication failure")

    monkeypatch.setattr(
        connection_module.ConnectionConfigPublisher,
        "publish",
        fail_publish,
    )

    with pytest.raises(OSError, match="publication failure"):
        manager.set_manual_connection(manual_port, "manual-token")

    assert manager.server.port == automatic_port
    assert manager.status()["mode"] == "automatic"
    assert manager.status()["tokenProtected"] is True
    manager.stop()


def test_editing_only_manual_port_preserves_the_hidden_effective_token(
    tmp_path: Path,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    manager = CompanionConnectionManager(
        observe=supported_observation,
        settings_path=tmp_path / "user_files" / "connection-settings.json",
        generate_token=lambda: "hidden-automatic-token",
    )
    manager.start()
    manager.select_resource_folder(resource_folder)
    free_port_probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    free_port_probe.bind(("127.0.0.1", 0))
    manual_port = int(free_port_probe.getsockname()[1])
    free_port_probe.close()

    manager.set_manual_connection(manual_port, None)
    published = json.loads(
        (resource_folder / "connection.json").read_text(encoding="utf-8")
    )

    assert manager.status()["tokenProtected"] is True
    assert published["companion"]["tokenDigest"] == (
        "3e93d47d5d78e8e834a7c0109317113d"
        "be90fb407f003f9ac13a6eb1aa7977b6"
    )
    manager.stop()


def test_restart_publication_failure_does_not_leave_listener_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    settings_path = tmp_path / "user_files" / "connection-settings.json"
    first = CompanionConnectionManager(
        observe=supported_observation,
        settings_path=settings_path,
        generate_token=lambda: "stable-token",
    )
    first.start()
    first.select_resource_folder(resource_folder)
    occupied_port = first.server.port
    first.stop()

    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", occupied_port))
    occupied.listen(1)
    try:
        def fail_publish(
            _manager: object,
            _publisher: object,
            _settings: object,
        ) -> None:
            raise OSError("injected restart publication failure")

        monkeypatch.setattr(
            connection_module.CompanionConnectionManager,
            "_publish",
            fail_publish,
        )
        restarted = CompanionConnectionManager(
            observe=supported_observation,
            settings_path=settings_path,
            generate_token=lambda: "unused",
        )

        with pytest.raises(OSError, match="restart publication failure"):
            restarted.start()

        with pytest.raises(RuntimeError, match="not started"):
            _ = restarted.server
    finally:
        occupied.close()
