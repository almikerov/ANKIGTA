from __future__ import annotations

from pathlib import Path

from tests.lua.constants import string_constants
import re
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
RESOURCE = ROOT / "mta" / "ankigta"


def source(relative: str) -> str:
    return (RESOURCE / relative).read_text(encoding="utf-8")


def test_session_gateway_is_server_side_bounded_and_uses_explicit_paths() -> None:
    companion = source("server/companion.lua")
    assert 'local SESSION_START_PATH = "/v1/session/start"' in companion
    assert 'local SESSION_REBUILD_PATH = "/v1/session/rebuild"' in companion
    assert 'local SESSION_PAUSE_PATH = "/v1/session/pause"' in companion
    assert 'local SESSION_STOP_PATH = "/v1/session/stop"' in companion
    assert "SESSION_TIMEOUT_MS = 30000" in companion
    assert "requestSessionStart" in companion
    assert "requestSessionPause" in companion
    assert 'http://127.0.0.1:%d%s' in companion
    assert "sessionActive) ~= false" not in companion


def test_server_study_start_is_acl_bound_and_deduplicates_active_links() -> None:
    main = source("server/main.lua")
    assert 'local START_STUDY_REQUEST_EVENT = "ankigta:startStudy"' in main
    assert "playerAuthorization(player)" in main
    assert "activeCardIdentities" in main
    assert "local seen = {}" in main
    assert "requestSessionStart" in main
    assert "requestSessionPause" in main
    assert "requestSessionStop" in main


def test_study_ui_exposes_only_explicit_start_and_safe_cleanup_actions() -> None:
    manifest = ET.parse(RESOURCE / "meta.xml").getroot()
    scripts = [script.get("src") for script in manifest.findall("script")]
    assert "client/study.lua" in scripts
    study = source("client/study.lua")
    study_keys = string_constants(RESOURCE / "client" / "study.lua")
    assert "study.start" in study_keys
    assert "study.session" in study_keys
    assert "study.pause" in study_keys
    assert "study.stop" in study_keys
    assert 'triggerServerEvent(\n            START_STUDY_REQUEST_EVENT' in study
    assert "PAUSE_STUDY_REQUEST_EVENT" in study
    assert "STOP_STUDY_REQUEST_EVENT" in study
