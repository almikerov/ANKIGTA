from __future__ import annotations

import json
import socket
from http.client import HTTPConnection
from pathlib import Path
from urllib.error import URLError

from ankigta_companion.connection import CompanionConnectionManager
from ankigta_companion.connection_settings_ui import connection_summary
from tests.lua import MtaSandbox
from ankigta_companion.contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MTA_RESOURCE = REPO_ROOT / "mta" / "ankigta"
TICKET_02_INTEGRATION = REPO_ROOT / "tests" / "integration" / "mta_ticket_02"


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
        '<script src="client/panel.lua" type="client" cache="false" />'
        in manifest
    )


def test_blocking_ticket_02_harness_uses_configured_gateway_seam() -> None:
    runner = (TICKET_02_INTEGRATION / "runner.py").read_text(
        encoding="utf-8"
    )
    driver = (TICKET_02_INTEGRATION / "driver" / "server.lua").read_text(
        encoding="utf-8"
    )

    # The harness must reach the gateway through the published connection file,
    # never by injecting a port or request id of its own. It observes the
    # resource's configured auto-connect rather than initiating a competing one.
    assert '"connection.json"' in runner
    assert "getCompanionConnectionStatus()" in driver
    assert "requestCompanionHealth(" not in driver
    assert "case.port" not in driver
    assert "case.requestId" not in driver


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
    gateway = (MTA_RESOURCE / "server" / "companion.lua").read_text(
        encoding="utf-8"
    )
    exported_request = gateway[gateway.index("function requestCompanionHealth") :]
    exported_request = exported_request[: exported_request.index("\nend") + 4]
    assert "Gateway.connectConfigured" in exported_request
    assert "Gateway.requestHealth" not in exported_request
    assert "legacyManualGatewayUsed" not in gateway


def test_mta_connection_ui_masks_replacement_token_and_offers_connect() -> None:
    """Ticket 32 moved this into the panel, so the panel is what is driven.

    The gate is read off the page's own markup rather than a source search: a
    field that stopped being rendered would still satisfy a grep.
    """
    page = (MTA_RESOURCE / "client" / "panel" / "index.html").read_text(
        encoding="utf-8"
    )
    # The replacement token is typed into a masked field, never echoed back.
    assert 'id="token"' in page
    assert 'type="password"' in page
    assert 'data-i18n="connection.connect"' in page
    assert 'data-i18n="connection.manualPort"' in page

    app = (MTA_RESOURCE / "client" / "panel" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "keepToken" in app

    sandbox = MtaSandbox()
    try:
        for script in (
            "shared/settings.lua",
            "shared/locale.lua",
            "client/layout.lua",
            "client/panel.lua",
        ):
            sandbox.load(script)
        sandbox.eval(
            'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
        )()
        for handler in sandbox.bound_keys.get(("F7", "down"), []):
            handler()
        sandbox.eval(
            """
            function()
                triggerEvent("ankigta:panelAction", resourceRoot, "ready", "{}")
                triggerEvent(
                    "ankigta:panelAction",
                    resourceRoot,
                    "updateConnection",
                    '{"mode":"manual","port":40007,"token":"s","keepToken":false}'
                )
            end
            """
        )()

        updates = [
            event
            for event in sandbox.recorder.server_events
            if event.name == "ankigta:updateConnectionSettings"
        ]
        assert updates, sandbox.recorder.server_events
        assert sandbox.to_python(updates[-1].args[0])["port"] == 40007
    finally:
        sandbox.close()


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


def test_secret_scan_excludes_tokens_from_ui_logs_and_config_diagnostics(
    tmp_path: Path,
    capsys: object,
) -> None:
    secret = "ticket03-generated-disposable-token"
    resource_folder = tmp_path / "ankigta"
    resource_folder.mkdir()
    (resource_folder / "meta.xml").write_text("<meta />", encoding="utf-8")
    manager = CompanionConnectionManager(
        observe=supported_observation,
        settings_path=tmp_path / "user_files" / "connection-settings.json",
        generate_token=lambda: secret,
    )
    manager.start()
    manager.select_resource_folder(resource_folder)
    status = manager.status()
    summary = connection_summary(status)
    wrong_token_status = health_status(
        manager.server.port,
        "ticket03-wrong-disposable-token",
    )
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    manager.stop()

    diagnostics = json.dumps(
        {
            "status": status,
            "summary": summary,
            "wrongTokenStatus": wrong_token_status,
            "stdout": captured.out,
            "stderr": captured.err,
        },
        ensure_ascii=False,
    )
    ui_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            MTA_RESOURCE / "client" / "connection_status.lua",
            MTA_RESOURCE / "client" / "panel.lua",
            MTA_RESOURCE / "client" / "panel" / "app.js",
            MTA_RESOURCE / "client" / "panel" / "index.html",
        )
    )

    gateway_source = (
        MTA_RESOURCE / "server" / "companion.lua"
    ).read_text(encoding="utf-8")
    sanitized_block = gateway_source[
        gateway_source.index("local function sanitizedConfig") :
        gateway_source.index("local function syntheticConfigFailure")
    ]
    config_source = (
        MTA_RESOURCE / "server" / "connection_config.lua"
    ).read_text(encoding="utf-8")
    sanitized_status_block = config_source[
        config_source.index("function ConnectionConfig.getSanitizedStatus") :
        config_source.index("ANKIGTA.ConnectionConfig = ConnectionConfig")
    ]

    for secret in (secret, "ticket03-wrong-disposable-token"):
        assert secret not in diagnostics
        assert secret not in ui_sources
    assert "token = " not in sanitized_block
    assert "token = " not in sanitized_status_block
