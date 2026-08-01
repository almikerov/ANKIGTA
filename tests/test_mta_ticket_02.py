from __future__ import annotations

import re
import socket
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import pytest

from integration.mta_ticket_02.runner import (
    configured_mta_server_root,
    run_health_case,
)
from ankigta_companion.contract import (
    CollectionObservation,
    CollectionState,
    RuntimeObservation,
)
from ankigta_companion.http_server import HealthServer


REPO_ROOT = Path(__file__).resolve().parents[1]
MTA_RESOURCE = REPO_ROOT / "mta" / "ankigta"


def mta_server_root_or_skip() -> Path:
    try:
        return configured_mta_server_root()
    except RuntimeError as error:
        pytest.skip(str(error))


@lru_cache(maxsize=1)
def successful_health_evidence() -> dict[str, object]:
    return run_health_case(mta_server_root_or_skip(), "success")


def test_companion_control_gateway_is_server_side_only() -> None:
    manifest = ET.parse(MTA_RESOURCE / "meta.xml").getroot()
    scripts = manifest.findall("script")
    gateway_scripts = [
        script
        for script in scripts
        if script.get("src") == "server/companion.lua"
    ]

    assert [script.get("type") for script in gateway_scripts] == ["server"]

    forbidden_client_fragments = (
        "fetchRemote(",
        "127.0.0.1",
        "::1",
        '["Authorization"]',
        "connectionToken",
        "reviewTransactionId",
        "/v1/",
    )
    for script in scripts:
        if script.get("type") != "client":
            continue
        source = (MTA_RESOURCE / str(script.get("src"))).read_text(encoding="utf-8")
        assert all(fragment not in source for fragment in forbidden_client_fragments)

    gateway_source = (MTA_RESOURCE / "server" / "companion.lua").read_text(
        encoding="utf-8"
    )
    assert '"http://127.0.0.1:%d%s"' in gateway_source
    assert all(
        fragment not in gateway_source
        for fragment in ('"localhost"', '"::1"', '"0.0.0.0"')
    )


def test_client_presents_only_the_sanitized_connection_status() -> None:
    manifest = ET.parse(MTA_RESOURCE / "meta.xml").getroot()
    scripts = manifest.findall("script")
    status_scripts = [
        script
        for script in scripts
        if script.get("src") == "client/connection_status.lua"
    ]

    assert [script.get("type") for script in status_scripts] == ["client"]
    source = (MTA_RESOURCE / "client" / "connection_status.lua").read_text(
        encoding="utf-8"
    )
    assert '"ankigta:companionStatus"' in source
    assert "addEvent(STATUS_EVENT, true)" in source
    assert "outputChatBox" in source
    for category in (
        "protocol_error",
        "timeout",
        "transport_error",
        "collection_unavailable",
        "compatibility_failure",
    ):
        assert category in source
    assert "getLocalization()" in source


def test_companion_listener_is_unreachable_through_ipv6_or_lan() -> None:
    observation = RuntimeObservation(
        anki_version="26.05",
        v3_scheduler=True,
        fsrs_enabled=True,
        collection=CollectionObservation(state=CollectionState.OPEN),
    )

    with HealthServer(lambda: observation) as server:
        ipv6_probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        ipv6_probe.settimeout(0.5)
        try:
            assert ipv6_probe.connect_ex(("::1", server.port)) != 0
        finally:
            ipv6_probe.close()

        lan_addresses = {
            entry[4][0]
            for entry in socket.getaddrinfo(
                socket.gethostname(),
                None,
                socket.AF_INET,
                socket.SOCK_STREAM,
            )
            if not entry[4][0].startswith("127.")
        }
        for address in lan_addresses:
            lan_probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            lan_probe.settimeout(0.5)
            try:
                assert lan_probe.connect_ex((address, server.port)) != 0
            finally:
                lan_probe.close()


def test_real_mta_server_fetches_companion_health_over_ipv4_loopback() -> None:
    evidence = successful_health_evidence()
    status = evidence["status"]

    assert status["state"] == "connected"
    assert status["category"] is False
    # The gateway owns the correlator now, so assert that it is a stable health
    # request id rather than a prefix the harness used to inject.
    assert isinstance(status["requestId"], str)
    assert re.fullmatch(r"health-\d+-\d+", status["requestId"])
    assert status["httpStatus"] == 200
    # A successful connection must start nothing: no session, no filtered deck,
    # no Review Mode, no rating capability.
    assert status["study"] == {
        "sessionActive": False,
        "ratingEnabled": False,
        "filteredDeckCreated": False,
        "reviewModeOpened": False,
    }
    assert evidence["elapsedMs"] < 5000
    assert evidence["timerTicks"] > 0


@pytest.mark.parametrize(
    ("case_name", "category", "http_status"),
    [
        ("collection_unavailable", "collection_unavailable", 503),
        ("compatibility_failure", "compatibility_failure", 409),
    ],
)
def test_valid_health_failures_keep_the_companion_category(
    case_name: str,
    category: str,
    http_status: int,
) -> None:
    evidence = run_health_case(mta_server_root_or_skip(), case_name)

    assert evidence["status"]["state"] == "disconnected"
    assert evidence["status"]["category"] == category
    assert evidence["status"]["httpStatus"] == http_status


@pytest.mark.parametrize(
    "case_name",
    [
        "wrong_content_type",
        "json_prefix_content_type",
        "malformed_json",
        "missing_health_fields",
        "success_with_error",
        "error_missing_message",
        "compatibility_contradiction",
        "protocol_version_string",
        "wrong_protocol_version",
        "wrong_request_id",
    ],
)
def test_http_200_with_an_invalid_envelope_is_a_protocol_error(
    case_name: str,
) -> None:
    evidence = run_health_case(mta_server_root_or_skip(), case_name)

    assert evidence["status"]["state"] == "disconnected"
    assert evidence["status"]["category"] == "protocol_error"
    assert evidence["status"]["httpStatus"] == 200


def test_timeout_is_bounded_non_blocking_and_quarantines_a_late_callback() -> None:
    evidence = run_health_case(mta_server_root_or_skip(), "late_callback")

    assert evidence["status"]["state"] == "disconnected"
    assert evidence["status"]["category"] == "timeout"
    assert evidence["status"]["elapsedMs"] <= 5000
    assert evidence["timerTicks"] >= 100
    assert evidence["finalStatus"]["state"] == "disconnected"
    assert evidence["finalStatus"]["category"] == "timeout"
    assert (
        evidence["finalStatus"]["requestId"]
        == evidence["status"]["requestId"]
    )
    assert evidence["finalStatus"]["quarantinedCallbacks"] >= 1
