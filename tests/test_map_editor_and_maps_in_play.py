"""Panel rebuild 02 — the Map Editor, and which maps are in play.

Four things ANKIGTA got wrong about the stock Map Editor, which are one
misunderstanding: the editor keeps a world beside the world, and ANKIGTA read
it as if it were the only one.

The world these tests build is the one the running server actually holds — the
editor's copy of a map in its own working dimension, a play-test of the same
map in the ordinary one, and EDF's representation elements standing beside the
elements they draw.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox


REPO_ROOT = Path(__file__).resolve().parents[1]
UUID = "11111111-1111-4111-8111-111111111111"
PORT = 51_600


def manifest_scripts(*kinds: str) -> list[str]:
    manifest = ElementTree.parse(REPO_ROOT / "mta" / "ankigta" / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


@pytest.fixture
def server(tmp_path: Path) -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
    try:
        for script in manifest_scripts("shared", "server"):
            sandbox.load(script)
        # A published connection file is ticket 03's subject; these tests are
        # about what the server does once it has one.
        sandbox.execute(
            f"""
            ANKIGTA.ConnectionConfig.loadEffective = function()
                return {{port = {PORT}, token = "t"}}, false, false
            end
            """
        )
        sandbox.trigger("onResourceStart")
        yield sandbox
    finally:
        sandbox.close()


# --- the world the editor actually builds ------------------------------------


def open_map_in_editor(
    sandbox: MtaSandbox,
    *,
    map_name: str = "mymap",
    working_dimension: int = 200,
) -> Any:
    """The stock editor running with one map open, and that map's files.

    The editor loads a map's elements into its own working dimension without
    starting the map's resource, which is why `getCurrentMapName` is the only
    thing that says the map is there at all.
    """
    editor_root = sandbox.add_resource("editor_main")
    sandbox.editor_map_name = map_name
    sandbox.editor_working_dimension = working_dimension
    sandbox.write_file(
        f":{map_name}/meta.xml",
        f'<meta><map src="{map_name}.map" /></meta>',
    )
    sandbox.write_file(f":{map_name}/{map_name}.map", "<map>\n</map>\n")
    return editor_root


def editor_element(
    sandbox: MtaSandbox,
    editor_root: Any,
    *,
    entity_id: str,
    kind: str = "object",
    dimension: int = 200,
    x: float = 0.0,
    stamped: bool = True,
) -> Any:
    """One element the editor has open, with EDF's drawing of it beside it.

    `me:ID` is deliberately absent: `assignID` only writes it when it has to
    invent an id, so an element whose `.map` already named it uniquely never
    carries one (editor_main/server/IDhandler.lua).
    """
    element = sandbox.add_world_element(
        kind,
        map_id=entity_id,
        dimension=dimension,
        x=x,
        **({"ankigtaEntityId": entity_id} if stamped else {}),
    )
    element["__parent"] = editor_root
    sandbox.add_edf_representation(element)
    return element


def seed_entity(
    sandbox: MtaSandbox,
    *,
    map_id: str,
    entity_id: str,
    resource_name: str | None = None,
    entity_type: str = "object",
    dimension: int = 0,
    x: float = 0.0,
) -> None:
    connection: sqlite3.Connection = sandbox.connection.raw
    connection.execute(
        "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
        " VALUES (?, ?, ?)",
        (map_id, resource_name or map_id, map_id),
    )
    connection.execute(
        "INSERT OR REPLACE INTO map_entities (map_id, entity_id, entity_type,"
        " model, authored_x, authored_y, authored_z, rotation_x, rotation_y,"
        " rotation_z, interior, dimension)"
        " VALUES (?, ?, ?, 1337, ?, 0, 0, 0, 0, 0, 0, ?)",
        (map_id, entity_id, entity_type, x, dimension),
    )
    connection.commit()


def link_card(
    sandbox: MtaSandbox,
    player: Any,
    map_id: str,
    entity_id: str,
    *,
    card_id: int = 42,
) -> tuple[Any, Any]:
    """`linkCardToEntity`, as the panel's Link button reaches it."""
    result = sandbox.eval(
        """
        function(player, mapId, entityId, identity)
            local ok, reason = linkCardToEntity(player, mapId, entityId, identity)
            if not ok then
                return false, tostring(reason)
            end
            return ok, false
        end
        """
    )(
        player,
        map_id,
        entity_id,
        sandbox.lua.table_from({"collectionUuid": UUID, "cardId": card_id}),
    )
    linked, reason = result
    return linked, reason


def study_player(sandbox: MtaSandbox, *, dimension: int = 200) -> Any:
    player = sandbox.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0
    player["dimension"] = dimension
    player["interior"] = 0
    return player


# --- nothing can be linked ---------------------------------------------------


def test_a_card_links_to_an_object_while_the_map_editor_is_open(
    server: MtaSandbox,
) -> None:
    editor_root = open_map_in_editor(server)
    seed_entity(server, map_id="mymap", entity_id="object (bin) (1)")
    editor_element(server, editor_root, entity_id="object (bin) (1)")
    player = study_player(server)

    linked, reason = link_card(server, player, "mymap", "object (bin) (1)")

    assert reason is False, reason
    assert linked["state"] == "Pending Map Save"


def test_an_editor_representation_is_not_counted_as_a_second_copy(
    server: MtaSandbox,
) -> None:
    """EDF parents its drawing to the element and stamps it `edf:rep`.

    Both carry the identity the `.map` file gave the element, so a check that
    counts elements by identity sees two inside the editor and never one.
    """
    editor_root = open_map_in_editor(server)
    seed_entity(server, map_id="mymap", entity_id="object (bin) (1)")
    element = editor_element(server, editor_root, entity_id="object (bin) (1)")
    player = study_player(server)

    copies = server.eval(
        "function() return #ANKIGTA.World.runtimeInstances("
        '"mymap", "object (bin) (1)") end'
    )()

    assert copies == 1
    resolved, count = server.eval(
        "function(p) return ANKIGTA.World.runtimeInstance("
        '"mymap", "object (bin) (1)", p) end'
    )(player)
    assert count == 1
    assert resolved["__handle"] == element["__handle"]


def test_a_genuine_duplicate_is_still_refused_and_the_refusal_says_which(
    server: MtaSandbox,
) -> None:
    editor_root = open_map_in_editor(server)
    seed_entity(server, map_id="mymap", entity_id="object (bin) (1)")
    editor_element(server, editor_root, entity_id="object (bin) (1)")
    # A second element in the player's own world carrying the same identity.
    editor_element(server, editor_root, entity_id="object (bin) (1)", x=50)
    player = study_player(server)

    linked, reason = link_card(server, player, "mymap", "object (bin) (1)")

    assert linked is False
    assert "entity_runtime_not_unique" in reason
    assert "object (bin) (1)" in reason, "the refusal has to name the entity"


def test_the_play_test_copy_does_not_block_linking_in_the_editor(
    server: MtaSandbox,
) -> None:
    """The editor edits in its own dimension while the map runs in the world.

    Two copies of one authored entity, and the player is standing next to one
    of them.
    """
    editor_root = open_map_in_editor(server)
    play_test_root = server.add_resource("editor_test", resource_type="map")
    seed_entity(server, map_id="mymap", entity_id="object (bin) (1)")
    editable = editor_element(
        server, editor_root, entity_id="object (bin) (1)", x=99
    )
    play_test = editor_element(
        server, play_test_root, entity_id="object (bin) (1)", dimension=0, x=10
    )
    player = study_player(server, dimension=200)

    linked, reason = link_card(server, player, "mymap", "object (bin) (1)")

    assert reason is False, reason
    assert linked["state"] == "Pending Map Save"
    resolved, count = server.eval(
        "function(p) return ANKIGTA.World.runtimeInstance("
        '"mymap", "object (bin) (1)", p) end'
    )(player)
    assert count == 2, "both copies are really there"
    assert resolved["__handle"] == editable["__handle"]
    assert play_test["__handle"] != editable["__handle"]


@pytest.mark.parametrize("kind", ["object", "vehicle", "ped", "marker"])
def test_every_map_entity_type_can_be_linked(
    server: MtaSandbox, kind: str
) -> None:
    """All four are Map Entity types; the check only ever looked at objects."""
    editor_root = open_map_in_editor(server)
    entity_id = f"{kind} (1)"
    seed_entity(
        server, map_id="mymap", entity_id=entity_id, entity_type=kind
    )
    editor_element(server, editor_root, entity_id=entity_id, kind=kind)
    player = study_player(server)

    linked, reason = link_card(server, player, "mymap", entity_id)

    assert reason is False, reason
    assert linked["state"] == "Pending Map Save"


def test_an_entity_the_editor_reloaded_is_still_found_by_its_map_id(
    server: MtaSandbox,
) -> None:
    """A restart takes the stamp with it; the `.map` file keeps the id."""
    editor_root = open_map_in_editor(server)
    seed_entity(server, map_id="mymap", entity_id="object (bin) (1)")
    editor_element(
        server, editor_root, entity_id="object (bin) (1)", stamped=False
    )
    player = study_player(server)

    linked, reason = link_card(server, player, "mymap", "object (bin) (1)")

    assert reason is False, reason
    assert linked["state"] == "Pending Map Save"


# --- teleport ----------------------------------------------------------------


def teleport(
    sandbox: MtaSandbox, player: Any, map_id: str, entity_id: str
) -> tuple[Any, Any]:
    return sandbox.eval(
        "function(p, m, e) return teleportPlayerToMapEntity(p, m, e) end"
    )(player, map_id, entity_id)


def test_teleport_moves_the_player_to_the_entity_while_the_editor_is_open(
    server: MtaSandbox,
) -> None:
    """The record carries the authored dimension; the copy in front of the
    player is in the editor's working one."""
    editor_root = open_map_in_editor(server)
    seed_entity(
        server, map_id="mymap", entity_id="object (bin) (1)", dimension=0, x=5
    )
    editor_element(
        server, editor_root, entity_id="object (bin) (1)", dimension=200, x=99
    )
    player = study_player(server, dimension=200)

    moved, source = teleport(server, player, "mymap", "object (bin) (1)")

    assert moved is True
    assert source == "runtime"
    last = server.moved[-1]
    assert last["position"][0] == 99
    assert last["dimension"] == 200


def test_teleport_outside_the_editor_lands_in_the_right_dimension(
    server: MtaSandbox,
) -> None:
    map_root = server.add_resource("mymap", resource_type="map")
    seed_entity(
        server, map_id="mymap", entity_id="object (bin) (1)", dimension=7, x=5
    )
    element = server.add_world_element(
        "object", map_id="object (bin) (1)", dimension=7, x=42
    )
    element["__parent"] = map_root
    player = study_player(server, dimension=7)

    moved, source = teleport(server, player, "mymap", "object (bin) (1)")

    assert moved is True
    assert source == "runtime"
    assert server.moved[-1]["dimension"] == 7
    assert server.moved[-1]["position"][0] == 42


def test_teleport_uses_the_authored_snapshot_when_nothing_is_loaded(
    server: MtaSandbox,
) -> None:
    seed_entity(
        server, map_id="mymap", entity_id="object (bin) (1)", dimension=7, x=5
    )
    player = study_player(server, dimension=0)

    moved, source = teleport(server, player, "mymap", "object (bin) (1)")

    assert moved is True
    assert source == "authored"
    assert server.moved[-1]["dimension"] == 7
    assert server.moved[-1]["position"][0] == 5


# --- the editor's scratch resources ------------------------------------------


def adopt(sandbox: MtaSandbox, player: Any, name: str) -> None:
    sandbox.trigger(
        "ankigta:adoptEntity",
        sandbox.lua.globals().resourceRoot,
        name,
        sandbox.lua.table_from({"collectionUuid": UUID, "cardId": 42}),
        client=player,
    )


def notices(sandbox: MtaSandbox) -> list[Any]:
    return [
        event
        for event in sandbox.recorder.client_events
        if event.name == "ankigta:pendingMapSaveNotice"
    ]


def test_an_entity_is_not_adopted_while_a_scratch_resource_owns_it(
    server: MtaSandbox,
) -> None:
    """`editor_test` is the copy the editor play-tests from.

    An entity adopted out of one is a Spatial Link pointing at a copy that
    stops existing when the test does.
    """
    scratch_root = server.add_resource("editor_test", resource_type="map")
    element = server.add_world_element("object", map_id="object (bin) (1)")
    element["__parent"] = scratch_root
    player = study_player(server, dimension=0)

    adopt(server, player, "object (bin) (1)")

    stored = server.connection.raw.execute(
        "SELECT COUNT(*) FROM map_entities"
    ).fetchone()[0]
    assert stored == 0
    assert notices(server)[-1].args[1] == "editor_scratch_resource"


def test_working_in_the_map_editor_normally_still_adopts(
    server: MtaSandbox,
) -> None:
    editor_root = open_map_in_editor(server)
    element = editor_element(
        server, editor_root, entity_id="object (bin) (1)", stamped=False, x=99
    )
    player = study_player(server, dimension=200)

    adopt(server, player, "object (bin) (1)")

    row = server.connection.raw.execute(
        "SELECT map_id, authored_x FROM map_entities"
    ).fetchone()
    assert row == ("mymap", 99)


def test_an_entity_stored_against_a_scratch_map_is_reported_as_missing(
    server: MtaSandbox,
) -> None:
    """Not deleted. The link may have been made against an object the player
    still has, so the row says what it is and the player decides."""
    seed_entity(
        server,
        map_id="editor_dump",
        entity_id="object (bin) (1)",
        resource_name="editor_dump",
    )
    player = study_player(server, dimension=0)

    server.trigger(
        "ankigta:requestF7", server.lua.globals().resourceRoot, client=player
    )
    snapshot = server.to_python(server.recorder.client_events[-1].args[0])
    rows = {
        entry["mapEntity"]["entityId"]: entry
        for entry in snapshot["entities"]
    }

    assert "object (bin) (1)" in rows, "a scratch row is never hidden"
    link = rows["object (bin) (1)"]["link"]
    assert link["state"] == "Entity missing"
    assert link["editorScratchMap"] is True
    # Told, in words the panel can show, rather than left to be guessed at.
    assert link["guidanceKey"] == "guidance.editorScratchMap"
    # And still there afterwards: reporting a row is not deleting it.
    assert server.connection.raw.execute(
        "SELECT COUNT(*) FROM map_entities"
    ).fetchone()[0] == 1


def test_a_spatial_link_on_a_scratch_map_can_be_removed(
    server: MtaSandbox,
) -> None:
    """The other half of the decision: keep the entity, drop the link."""
    seed_link(
        server,
        map_id="editor_dump",
        entity_id="object (bin) (1)",
        card_id=42,
        resource_name="editor_dump",
    )
    player = study_player(server, dimension=0)

    server.eval(
        """
        function(player)
            return unlinkCardFromEntity(player, "editor_dump",
                "object (bin) (1)",
                {collectionUuid = "%s", cardId = 42})
        end
        """
        % UUID
    )(player)

    assert server.connection.raw.execute(
        "SELECT COUNT(*) FROM spatial_links"
    ).fetchone()[0] == 0
    # The Map Entity itself is kept, so nothing the player named is lost.
    assert server.connection.raw.execute(
        "SELECT COUNT(*) FROM map_entities"
    ).fetchone()[0] == 1


def test_a_spatial_link_on_a_scratch_map_can_be_relinked(
    server: MtaSandbox,
) -> None:
    seed_entity(
        server,
        map_id="editor_dump",
        entity_id="object (bin) (1)",
        resource_name="editor_dump",
    )
    seed_entity(server, map_id="mymap", entity_id="object (crate) (1)")
    server.connection.raw.execute(
        "INSERT INTO spatial_links (map_id, entity_id, collection_uuid,"
        " card_id, state, verified_map_sha256)"
        " VALUES ('editor_dump', 'object (bin) (1)', ?, 42, 'active', ?)",
        (UUID, "a" * 64),
    )
    server.connection.raw.commit()
    player = study_player(server, dimension=0)
    # The presence refresh is what marks a scratch row missing.
    server.trigger(
        "ankigta:requestF7", server.lua.globals().resourceRoot, client=player
    )

    relinked = server.eval(
        """
        function(player)
            local ok, reason = relinkEntity(player, "editor_dump",
                "object (bin) (1)", "mymap", "object (crate) (1)")
            return ok ~= false and ok ~= nil, tostring(reason)
        end
        """
    )(player)

    assert relinked[0] is True, relinked[1]
    moved = server.connection.raw.execute(
        "SELECT map_id, entity_id FROM spatial_links"
    ).fetchall()
    assert moved == [("mymap", "object (crate) (1)")]


def test_nothing_is_written_into_an_editor_resource(server: MtaSandbox) -> None:
    """ADR 0025: the editor is used as it ships.

    Knowing which of its resources are scratch is reading it, not changing it.
    """
    editor_root = open_map_in_editor(server)
    server.add_resource("editor_test", resource_type="map")
    seed_entity(server, map_id="mymap", entity_id="object (bin) (1)")
    seed_entity(
        server,
        map_id="editor_dump",
        entity_id="object (old) (1)",
        resource_name="editor_dump",
    )
    editor_element(server, editor_root, entity_id="object (bin) (1)")
    player = study_player(server)
    server.files.writes.clear()

    server.trigger(
        "ankigta:requestF7", server.lua.globals().resourceRoot, client=player
    )
    link_card(server, player, "mymap", "object (bin) (1)")
    teleport(server, player, "editor_dump", "object (old) (1)")

    assert [
        path
        for path in server.files.writes
        if path.startswith((":editor_dump/", ":editor_test/", ":editor"))
    ] == []
    surviving = {
        path
        for path in server.files.keys()
        if path.startswith((":editor_dump/", ":editor_test/", ":editor"))
    }
    assert surviving == set()


# --- loaded is what decides ---------------------------------------------------


def settings_rows(sandbox: MtaSandbox, player: Any) -> list[dict[str, Any]]:
    sandbox.trigger(
        "ankigta:requestSettings",
        sandbox.lua.globals().resourceRoot,
        client=player,
    )
    return sandbox.to_python(sandbox.recorder.client_events[-1].args[0])


def test_settings_offer_no_per_map_row_and_no_way_to_exclude_a_map(
    server: MtaSandbox,
) -> None:
    seed_entity(server, map_id="mymap", entity_id="object (bin) (1)")
    player = study_player(server, dimension=0)

    snapshot = settings_rows(server, player)

    assert "maps" not in snapshot
    assert "includeInStudy" not in snapshot["values"]
    assert server.eval(
        'function() return ANKIGTA.Settings.schema.includeInStudy == nil end'
    )() is True


def refresh_study(sandbox: MtaSandbox, player: Any) -> None:
    sandbox.eval(
        """
        function(player)
            triggerEvent("ankigta:studyStateChanged", resourceRoot, player,
                {study = {sessionActive = true}})
        end
        """
    )(player)


def answer_card_states(sandbox: MtaSandbox, states: dict[str, str]) -> None:
    fetch = sandbox.recorder.remote_fetches[-1]
    request_id = json.loads(fetch["options"]["postData"])["requestId"]
    sandbox.complete_fetch(
        len(sandbox.recorder.remote_fetches) - 1,
        body=json.dumps(
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": request_id,
                "ok": True,
                "error": None,
                "payload": {"cardStates": states, "nextCard": None},
            }
        ),
    )


def seed_link(
    sandbox: MtaSandbox,
    *,
    map_id: str,
    entity_id: str,
    card_id: int,
    resource_name: str | None = None,
) -> None:
    seed_entity(
        sandbox,
        map_id=map_id,
        entity_id=entity_id,
        resource_name=resource_name,
    )
    sandbox.connection.raw.execute(
        "INSERT OR REPLACE INTO spatial_links (map_id, entity_id,"
        " collection_uuid, card_id, state, verified_map_sha256)"
        " VALUES (?, ?, ?, ?, 'active', ?)",
        (map_id, entity_id, UUID, card_id, "a" * 64),
    )
    sandbox.connection.raw.commit()


def last_payload(sandbox: MtaSandbox, name: str, argument: int = 0) -> Any:
    events = [
        event for event in sandbox.recorder.client_events if event.name == name
    ]
    assert events, f"no {name} was sent"
    return sandbox.to_python(events[-1].args[argument])


def as_list(value: Any) -> list[Any]:
    return list(value.values()) if isinstance(value, dict) else list(value)


def test_a_map_entity_on_a_loaded_map_is_in_play_and_an_unloaded_one_is_not(
    server: MtaSandbox,
) -> None:
    server.add_resource("loaded-map", resource_type="map")
    seed_link(server, map_id="loaded-map", entity_id="here", card_id=11)
    seed_link(server, map_id="stowed-map", entity_id="elsewhere", card_id=12)
    player = study_player(server, dimension=0)

    refresh_study(server, player)
    body = json.loads(server.recorder.remote_fetches[-1]["options"]["postData"])
    assert [
        identity["cardId"] for identity in body["cardIdentities"]
    ] == [11], "the session's card set narrows by the same answer"

    answer_card_states(server, {f"{UUID}/11": "new", f"{UUID}/12": "new"})

    assert last_payload(server, "ankigta:statistics")["total"] == 1
    candidates = as_list(last_payload(server, "ankigta:spatialCandidates"))
    assert [candidate["entityId"] for candidate in candidates] == ["here"]


def test_loading_the_map_again_brings_its_links_back_untouched(
    server: MtaSandbox,
) -> None:
    server.add_resource("mymap", resource_type="map")
    seed_link(server, map_id="mymap", entity_id="here", card_id=11)
    player = study_player(server, dimension=0)

    server.set_resource_state("mymap", "loaded")
    refresh_study(server, player)
    assert server.recorder.remote_fetches == []
    assert as_list(last_payload(server, "ankigta:spatialCandidates")) == []
    # Nothing was removed while it was away.
    assert server.connection.raw.execute(
        "SELECT COUNT(*) FROM spatial_links"
    ).fetchone()[0] == 1

    server.set_resource_state("mymap", "running")
    refresh_study(server, player)
    answer_card_states(server, {f"{UUID}/11": "new"})

    candidates = as_list(last_payload(server, "ankigta:spatialCandidates"))
    assert [candidate["entityId"] for candidate in candidates] == ["here"]


def test_the_editors_open_map_counts_as_loaded(server: MtaSandbox) -> None:
    """The editor loads a map's elements without starting its resource."""
    open_map_in_editor(server)
    seed_link(server, map_id="mymap", entity_id="here", card_id=11)
    player = study_player(server, dimension=200)

    refresh_study(server, player)
    answer_card_states(server, {f"{UUID}/11": "new"})

    candidates = as_list(last_payload(server, "ankigta:spatialCandidates"))
    assert [candidate["entityId"] for candidate in candidates] == ["here"]


def test_a_database_holding_map_preferences_opens_and_stops_carrying_them(
    tmp_path: Path,
) -> None:
    """A stored per-map switch is a setting nothing offers any more."""
    database = str(tmp_path / "ankigta.sqlite")
    first = MtaSandbox(database_path=database)
    try:
        for script in manifest_scripts("shared", "server"):
            first.load(script)
        first.trigger("onResourceStart")
        raw = first.connection.raw
        raw.execute(
            "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
            " VALUES ('mymap', 'mymap', 'mymap')"
        )
        raw.execute(
            "CREATE TABLE IF NOT EXISTS map_preferences ("
            " map_id TEXT PRIMARY KEY, include_in_study INTEGER NOT NULL"
            " DEFAULT 1)"
        )
        raw.execute(
            "INSERT OR REPLACE INTO map_preferences (map_id, include_in_study)"
            " VALUES ('mymap', 0)"
        )
        raw.execute(
            "INSERT OR REPLACE INTO map_entities (map_id, entity_id,"
            " entity_type, model, authored_x, authored_y, authored_z,"
            " rotation_x, rotation_y, rotation_z, interior, dimension)"
            " VALUES ('mymap', 'here', 'object', 1337, 0, 0, 0, 0, 0, 0, 0, 0)"
        )
        raw.execute(
            "INSERT INTO spatial_links (map_id, entity_id, collection_uuid,"
            " card_id, state, verified_map_sha256)"
            " VALUES ('mymap', 'here', ?, 7, 'active', ?)",
            (UUID, "a" * 64),
        )
        # A Change History entry that replayed into the table, with the cursor
        # sitting on it: the shape a database carrying the switch really has.
        raw.execute(
            "INSERT INTO change_history (operation, target, before_json,"
            " after_json, created_at) VALUES ('map_preference', ?, ?, ?, 1)",
            (
                '{"mapId":"mymap"}',
                '{"exists":false}',
                '{"exists":true,"includeInStudy":false}',
            ),
        )
        raw.execute(
            "UPDATE change_history_state SET cursor_id ="
            " (SELECT MAX(history_id) FROM change_history) WHERE singleton = 1"
        )
        raw.execute("UPDATE schema_meta SET version = 6 WHERE singleton = 1")
        raw.commit()
    finally:
        first.close()

    second = MtaSandbox(database_path=database)
    try:
        for script in manifest_scripts("shared", "server"):
            second.load(script)
        second.trigger("onResourceStart")
        status = second.to_python(
            second.eval("function() return ANKIGTA.Store.status() end")()
        )
        assert status["ready"] is True, status
        tables = {
            name
            for (name,) in second.connection.raw.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "map_preferences" not in tables
        # A Spatial Link is not the map, and the switch is not the link. The
        # one that was switched off is exactly where it was.
        assert second.connection.raw.execute(
            "SELECT map_id, entity_id, state FROM spatial_links"
        ).fetchall() == [("mymap", "here", "active")]
        # Undo is not left pointing at an entry that no longer exists.
        assert second.connection.raw.execute(
            "SELECT COUNT(*) FROM change_history WHERE operation ="
            " 'map_preference'"
        ).fetchone()[0] == 0
        history = second.to_python(
            second.eval("function() return ANKIGTA.Store.historyStatus() end")()
        )
        assert history["canUndo"] is False
    finally:
        second.close()


# --- the panel, on the client's half of the editor -----------------------------


@pytest.fixture
def panel_client() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        sandbox.load("shared/locale.lua")
        sandbox.load("shared/entity_types.lua")
        sandbox.load("client/layout.lua")
        sandbox.load("client/panel.lua")
        sandbox.eval(
            """
            function()
                triggerEvent("ankigta:setAuthorized", resourceRoot, true)
                togglePanel()
                triggerEvent("ankigta:panelAction", resourceRoot, "ready", "{}")
            end
            """
        )()
        yield sandbox
    finally:
        sandbox.close()


def to_lua(sandbox: MtaSandbox, value: Any) -> Any:
    if isinstance(value, dict):
        return sandbox.lua.table_from(
            {key: to_lua(sandbox, item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return sandbox.lua.table_from([to_lua(sandbox, item) for item in value])
    return value


def test_the_panel_skips_a_representation_without_asking_a_server_export(
    panel_client: MtaSandbox,
) -> None:
    """`edf/meta.xml` exports `edfIsRepresentation` server-side only.

    Calling it from the client fails, and the client half of ANKIGTA swallowed
    the failure into "nothing is ever a representation" -- so the list resolved
    rows to EDF's drawing of an element as readily as to the element, and wrote
    a line into `clientscript.log` on every refresh.
    """
    panel_client.eval(
        """
        function()
            exports.edf.edfIsRepresentation = function()
                error("client-side edf has no such export")
            end
        end
        """
    )()
    representation = panel_client.add_world_element(
        "object", map_id="gate-17", x=999, y=999, z=999
    )
    representation["edf:rep"] = True
    representation["ankigtaEntityId"] = "gate-17"
    real = panel_client.add_world_element(
        "object", map_id="gate-17", x=10.25, y=-20.5, z=3
    )
    real["ankigtaEntityId"] = "gate-17"
    panel_client.eval(
        """
        function(snapshot)
            triggerEvent("ankigta:f7Snapshot", resourceRoot, snapshot)
        end
        """
    )(
        to_lua(
            panel_client,
            {
                "visible": True,
                "cardPicker": {"enabled": True},
                "history": {"canUndo": False, "canRedo": False},
                "currentMap": {
                    "resourceName": "current-map",
                    "mapIds": ["current-map-id"],
                },
                "cardLinks": [],
                "entities": [
                    {
                        "mapEntity": {
                            "mapId": "current-map-id",
                            "entityId": "gate-17",
                            "type": "object",
                            "model": 1337,
                            "map": {
                                "resourceName": "current-map",
                                "mapName": "Current Map",
                            },
                            "authored": {
                                "position": {"x": 0, "y": 0, "z": 0},
                                "rotation": {"x": 0, "y": 0, "z": 0},
                                "world": {"interior": 0, "dimension": 0},
                            },
                        },
                        "runtimeInstance": {
                            "available": True,
                            "referenceId": "gate-17",
                        },
                        "metadata": {
                            "name": "",
                            "entityTag": "",
                            "radius": 3,
                            "showRadius": False,
                        },
                        "link": {"state": "Unlinked"},
                    }
                ],
            },
        )
    )

    panel_client.eval(
        """
        function()
            triggerEvent("ankigta:panelAction", resourceRoot, "focusEntity",
                '{"mapId":"current-map-id","entityId":"gate-17"}')
        end
        """
    )()

    assert panel_client.camera_matrix[3:6] == (10.25, -20.5, 3.0)
