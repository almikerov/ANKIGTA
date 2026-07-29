from __future__ import annotations

import json
import socket
from http.client import HTTPConnection
from pathlib import Path
from urllib.error import URLError

from ankigta_companion.connection import CompanionConnectionManager
from ankigta_companion.contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MTA_RESOURCE = REPO_ROOT / "mta" / "ankigta"


def supported_observation() -> RuntimeObservation:
    return RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )


def health_status(port: int, token: str | None) -> int:
    connection = HTTPConnection("127.0.0.1", port, timeout=0.5)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    try:
        connection.request(
            "POST",
            "/v1/health",
            body=json.dumps(
                {
                    "protocol": "ankigta-control",
                    "protocolVersion": 1,
                    "requestId": "ticket-03-local-transport",
                }
            ),
            headers=headers,
        )
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def test_mta_manifest_keeps_config_and_control_on_server_side() -> None:
    manifest = (MTA_RESOURCE / "meta.xml").read_text(encoding="utf-8")

    assert manifest.index('src="server/connection_config.lua"') < manifest.index(
        'src="server/companion.lua"'
    )
    assert (
        '<script src="server/connection_config.lua" type="server" />'
        in manifest
    )
    assert (
        '<script src="client/connection_settings.lua" '
        'type="client" cache="false" />'
        in manifest
    )


def test_mta_config_reader_validates_current_and_last_known_good() -> None:
    source = (MTA_RESOURCE / "server" / "connection_config.lua").read_text(
        encoding="utf-8"
    )

    for fragment in (
        '"connection.json"',
        '"connection.last-known-good.json"',
        '"ankigta-connection"',
        '"ankigta-control"',
        "connection_config_rollback",
        "effective_config_mismatch",
        'hash("sha256"',
        '"automatic"',
        '"manual"',
        "keepExistingToken",
    ):
        assert fragment in source
    assert "127.0.0.1" in source
    assert all(
        fragment not in source
        for fragment in ('"localhost"', '"::1"', '"0.0.0.0"')
    )


def test_mta_connection_ui_masks_replacement_token_and_offers_connect() -> None:
    source = (MTA_RESOURCE / "client" / "connection_settings.lua").read_text(
        encoding="utf-8"
    )

    assert "Подключиться" in source
    assert "Automatic Connection Mode" in source
    assert "Manual Connection Mode" in source
    assert "guiEditSetMasked" in source
    assert "keepToken" in source
    assert "Disable token explicitly" in source
    assert "ankigta:connectCompanion" in source
    assert "ankigta:updateConnectionSettings" in source
    assert all(
        fragment not in source
        for fragment in ("Authorization", "Bearer ", "/v1/", "127.0.0.1")
    )


def test_repository_local_transport_wrong_empty_token_port_change_and_reconnect(
    tmp_path: Path,
) -> None:
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    manager = CompanionConnectionManager(
        observe=supported_observation,
        settings_path=tmp_path / "user_files" / "connection-settings.json",
        generate_token=lambda: "ticket03-generated-disposable-token",
    )
    manager.start()
    manager.select_resource_folder(resource_folder)
    automatic_port = manager.server.port

    assert health_status(
        automatic_port,
        "ticket03-generated-disposable-token",
    ) == 200
    assert health_status(automatic_port, "ticket03-wrong-disposable-token") == 401

    free_port_probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    free_port_probe.bind(("127.0.0.1", 0))
    empty_token_port = int(free_port_probe.getsockname()[1])
    free_port_probe.close()
    manager.set_manual_connection(empty_token_port, "")

    assert empty_token_port != automatic_port
    assert health_status(empty_token_port, None) == 200
    manager.stop()
    try:
        health_status(empty_token_port, None)
    except (ConnectionError, OSError, URLError):
        pass
    else:
        raise AssertionError("stopped companion transport stayed reachable")

    manager.start()
    assert manager.server.port == empty_token_port
    assert health_status(empty_token_port, None) == 200
    manager.stop()


def test_secret_scan_excludes_tokens_from_ui_logs_and_config_diagnostics() -> None:
    ui_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            MTA_RESOURCE / "client" / "connection_status.lua",
            MTA_RESOURCE / "client" / "connection_settings.lua",
        )
    )

    for secret in (
        "ticket03-generated-disposable-token",
        "ticket03-wrong-disposable-token",
    ):
        assert secret not in ui_sources
