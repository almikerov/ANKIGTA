"""Ticket 32 — the session lifts itself, so the study menu can go.

ANKIGTA Session exists because of Exact Card Admission: a filtered deck the
add-on owns has to be built before a card can be legitimately rated. That is a
consequence of the rating path, not a thing to ask a player about, and it ended
up as four buttons only because someone had to press something.

The trigger is deliberately narrow. `not_started` is the one paused reason that
means nobody has decided anything yet; `paused` and `stopped` are decisions, and
CONTEXT.md is explicit that opening Anki's own Reviewer pauses ANKIGTA with no
automatic return. Auto-start must never argue with that.
"""

from __future__ import annotations

import json
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox
from tests.lua.sandbox import RESOURCE_ROOT


PORT = 51234
UUID = "11111111-1111-4111-8111-111111111111"


def manifest_scripts(*kinds: str) -> list[str]:
    manifest = ElementTree.parse(RESOURCE_ROOT / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


@pytest.fixture
def server(tmp_path: Any) -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
    for script in manifest_scripts("shared", "server"):
        sandbox.load(script)
    sandbox.execute(
        f"""
        ANKIGTA.ConnectionConfig.loadEffective = function()
            return {{port = {PORT}, token = "t"}}, false, false
        end
        """
    )
    sandbox.trigger("onResourceStart")
    try:
        yield sandbox
    finally:
        sandbox.close()


def seed_link(sandbox: MtaSandbox) -> None:
    """One Active Spatial Link, so there is something to study."""
    raw = sandbox.connection.raw
    raw.execute(
        "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
        " VALUES ('m1', 'ankigta', 'Ticket 32')"
    )
    raw.execute(
        "INSERT OR REPLACE INTO map_preferences (map_id, include_in_study)"
        " VALUES ('m1', 1)"
    )
    raw.execute(
        "INSERT OR IGNORE INTO map_entities (map_id, entity_id, entity_type,"
        " model, authored_x, authored_y, authored_z, rotation_x, rotation_y,"
        " rotation_z, interior, dimension)"
        " VALUES ('m1', 'e1', 'object', 1337, 0, 0, 0, 0, 0, 0, 0, 0)"
    )
    raw.execute(
        "INSERT OR IGNORE INTO spatial_links (map_id, entity_id,"
        " collection_uuid, card_id, state, verified_map_sha256)"
        " VALUES ('m1', 'e1', ?, 7, 'active', ?)",
        (UUID, "a" * 64),
    )
    raw.commit()


def announce_study(sandbox: MtaSandbox, player: Any, **study: Any) -> None:
    """The gateway reporting what the companion says about the session."""
    sandbox.eval(
        """
        function(player, payload)
            triggerEvent(
                "ankigta:studyStateChanged",
                resourceRoot,
                player,
                {state = "connected", study = fromJSON(payload)}
            )
        end
        """
    )(player, json.dumps(study))


def session_starts(sandbox: MtaSandbox) -> list[dict[str, Any]]:
    return [
        json.loads(fetch["options"]["postData"])
        for fetch in sandbox.recorder.remote_fetches
        if "session/start" in str(fetch.get("url", ""))
    ]


def test_a_connected_companion_with_links_starts_studying_by_itself(
    server: MtaSandbox,
) -> None:
    player = server.add_study_player()
    seed_link(server)

    announce_study(server, player, sessionActive=False, pausedReason="not_started")

    assert session_starts(server), [
        fetch.get("url") for fetch in server.recorder.remote_fetches
    ]


@pytest.mark.parametrize("reason", ["paused", "stopped", "rebuilding"])
def test_a_session_someone_decided_to_stop_is_left_alone(
    server: MtaSandbox, reason: str
) -> None:
    """Opening Anki's own Reviewer pauses ANKIGTA and there is no automatic
    return (CONTEXT.md). Restarting here would be arguing with the arbiter."""
    player = server.add_study_player()
    seed_link(server)

    announce_study(server, player, sessionActive=False, pausedReason=reason)

    assert session_starts(server) == []


def test_nothing_starts_when_there_is_nothing_linked(server: MtaSandbox) -> None:
    player = server.add_study_player()

    announce_study(server, player, sessionActive=False, pausedReason="not_started")

    assert session_starts(server) == []


def test_an_active_session_is_not_started_again(server: MtaSandbox) -> None:
    player = server.add_study_player()
    seed_link(server)

    announce_study(server, player, sessionActive=True, pausedReason=False)

    assert session_starts(server) == []


def test_a_wrong_collection_is_not_studied_around(server: MtaSandbox) -> None:
    """The identity states arrive as paused reasons too, and each of them is a
    reason a person has to resolve rather than one to retry through."""
    player = server.add_study_player()
    seed_link(server)

    announce_study(
        server, player, sessionActive=False, pausedReason="wrong_collection"
    )

    assert session_starts(server) == []
