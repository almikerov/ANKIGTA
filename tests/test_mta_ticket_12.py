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


def test_study_needs_no_menu_and_still_cleans_up_safely() -> None:
    """Ticket 32 deleted the study window; the session lifts itself.

    What ticket 12 actually asked for was that a session starts explicitly
    rather than by accident and is cleaned up safely. Starting is now the
    server's, on the one paused reason that means nobody has decided anything;
    the panel offers a way back from a decision and nothing else.
    """
    manifest = ET.parse(RESOURCE / "meta.xml").getroot()
    scripts = [script.get("src") for script in manifest.findall("script")]
    assert "client/study.lua" not in scripts
    assert "client/panel.lua" in scripts

    main = source("server/main.lua")
    # The trigger is narrow on purpose: paused and stopped are decisions, and
    # opening Anki's own Reviewer is one of them.
    assert 'local UNDECIDED_SESSION = "not_started"' in main
    assert "maybeAutoStartStudy(player, study)" in main
    # Cleanup is unchanged and still server-side.
    assert "requestStudyCleanup" in main
    assert "requestSessionStop" in main

    panel_keys = string_constants(RESOURCE / "client" / "panel.lua")
    assert "ankigta:startStudy" in panel_keys
    # No pause, rebuild or stop button reaches the server from the panel.
    for gone in ("ankigta:pauseStudy", "ankigta:stopStudy", "ankigta:rebuildStudy"):
        assert gone not in panel_keys


