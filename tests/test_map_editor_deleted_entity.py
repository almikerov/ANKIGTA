"""An object deleted in the Map Editor stops being a Map Entity.

The stock editor's Delete does not destroy anything: `setElementDimension` parks
the element in `workingDimension + 1` so Undo can bring it back. Nothing in
ANKIGTA looked at that, so a deleted object kept its row, kept its Activation
Zone drawn at coordinates nothing stands at, and offered a copy decision about
something that was in the bin.

Deleted from the map means gone from the list. The saved link was made
deliberately, so removing *that* is asked rather than assumed.
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
        sandbox.trigger("onResourceStart")
        yield sandbox
    finally:
        sandbox.close()


MAP_DOCUMENT = (
    "<map>\n"
    '  <ankigta_map_identity ankigtaMapId="mymap" />\n'
    '  <object id="object (bin) (1)" ankigtaEntityId="object (bin) (1)" />\n'
    "</map>\n"
)


def editor_with_map(sandbox: MtaSandbox) -> Any:
    editor_root = sandbox.add_resource("editor_main")
    sandbox.editor_map_name = "mymap"
    sandbox.editor_working_dimension = 200
    sandbox.write_file(
        ":mymap/meta.xml", '<meta><map src="mymap.map" /></meta>'
    )
    sandbox.write_file(":mymap/mymap.map", MAP_DOCUMENT)
    identity = sandbox.add_world_element(
        "ankigta_map_identity", map_id="ankigta_map_identity (1)", dimension=200
    )
    identity["__parent"] = editor_root
    identity["ankigtaMapId"] = "mymap"
    return editor_root


def seed_linked_entity(
    sandbox: MtaSandbox, entity_id: str = "object (bin) (1)"
) -> None:
    connection: sqlite3.Connection = sandbox.connection.raw
    connection.execute(
        "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
        " VALUES ('mymap', 'mymap', 'mymap.map')"
    )
    connection.execute(
        "INSERT OR REPLACE INTO map_entities (map_id, entity_id, entity_type,"
        " model, authored_x, authored_y, authored_z, rotation_x, rotation_y,"
        " rotation_z, interior, dimension)"
        " VALUES ('mymap', ?, 'object', 1337, 1, 2, 3, 0, 0, 0, 0, 200)",
        (entity_id,),
    )
    connection.execute(
        # `radius_override` is the one anything reads; `radius` is the NOT NULL
        # column it was split out of. Seeding only the second would describe an
        # entity that follows the global, which is not what this fixture means.
        "INSERT OR REPLACE INTO map_entity_metadata (map_id, entity_id, name,"
        " entity_tag, radius, radius_override, show_radius, presence_state)"
        " VALUES ('mymap', ?, 'North bin', 'yard', 7.5, 7.5, 1, 'identified')",
        (entity_id,),
    )
    connection.execute(
        "INSERT OR REPLACE INTO spatial_links (map_id, entity_id,"
        " collection_uuid, card_id, state, verified_map_sha256)"
        " VALUES ('mymap', ?, ?, 42, 'active', ?)",
        (entity_id, UUID, "a" * 64),
    )
    connection.commit()


def element_in(
    sandbox: MtaSandbox, editor_root: Any, *, dimension: int, entity_id: str
) -> Any:
    element = sandbox.add_world_element(
        "object", map_id=entity_id, dimension=dimension, x=10
    )
    element["__parent"] = editor_root
    element["ankigtaEntityId"] = entity_id
    return element


def as_list(value: Any) -> list[Any]:
    """A Lua array, as a list.

    An empty Lua table carries no shape, so it crosses as an empty mapping
    rather than as an empty list; both mean "nothing to ask about".
    """
    return list(value.values()) if isinstance(value, dict) else list(value)


def study_player(sandbox: MtaSandbox) -> Any:
    player = sandbox.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0
    player["dimension"] = 200
    player["interior"] = 0
    return player


def snapshot_of(sandbox: MtaSandbox, player: Any) -> dict[str, Any]:
    sandbox.trigger(
        "ankigta:requestF7", sandbox.lua.globals().resourceRoot, client=player
    )
    event = sandbox.recorder.client_events[-1]
    assert event.name == "ankigta:f7Snapshot"
    return sandbox.to_python(event.args[0])


# --- the row ------------------------------------------------------------------


def test_a_deleted_object_leaves_the_list(server: MtaSandbox) -> None:
    editor_root = editor_with_map(server)
    seed_linked_entity(server)
    # The editor's Delete: parked one dimension above the working one.
    element_in(server, editor_root, dimension=201, entity_id="object (bin) (1)")
    player = study_player(server)

    snapshot = snapshot_of(server, player)

    listed = [
        entry["mapEntity"]["entityId"] for entry in snapshot["entities"]
    ]
    assert "object (bin) (1)" not in listed


def test_an_object_that_is_merely_standing_there_keeps_its_row(
    server: MtaSandbox,
) -> None:
    """The parked dimension is the whole signal, so nothing else may trip it."""
    editor_root = editor_with_map(server)
    seed_linked_entity(server)
    element_in(server, editor_root, dimension=200, entity_id="object (bin) (1)")
    player = study_player(server)

    snapshot = snapshot_of(server, player)

    listed = [
        entry["mapEntity"]["entityId"] for entry in snapshot["entities"]
    ]
    assert "object (bin) (1)" in listed
    assert as_list(snapshot["deletedFromMap"]) == []


def test_a_deleted_object_has_no_runtime_instance(server: MtaSandbox) -> None:
    """Which is what stops its Activation Zone being drawn at nothing."""
    editor_root = editor_with_map(server)
    element_in(server, editor_root, dimension=201, entity_id="object (bin) (1)")

    found = server.eval(
        "function() return #ANKIGTA.World.runtimeInstances("
        '"mymap", "object (bin) (1)") end'
    )()

    assert found == 0


# --- the question -------------------------------------------------------------


def test_the_player_is_told_which_object_and_which_map(
    server: MtaSandbox,
) -> None:
    editor_root = editor_with_map(server)
    seed_linked_entity(server)
    element_in(server, editor_root, dimension=201, entity_id="object (bin) (1)")
    player = study_player(server)

    deleted = as_list(snapshot_of(server, player)["deletedFromMap"])

    assert len(deleted) == 1
    # Named the way the player named it, not by its editor id.
    assert deleted[0]["name"] == "North bin"
    assert deleted[0]["mapName"] == "mymap.map"
    assert deleted[0]["linked"] is True


def test_removing_takes_the_entity_its_metadata_and_its_link(
    server: MtaSandbox,
) -> None:
    editor_with_map(server)
    seed_linked_entity(server)
    player = study_player(server)

    removed = server.eval(
        """
        function(player)
            local ok, reason = forgetMapEntity(
                player, "mymap", "object (bin) (1)"
            )
            return ok ~= false and ok ~= nil, tostring(reason)
        end
        """
    )(player)

    assert removed[0] is True, removed[1]
    raw = server.connection.raw
    assert raw.execute("SELECT COUNT(*) FROM map_entities").fetchone()[0] == 0
    assert raw.execute("SELECT COUNT(*) FROM spatial_links").fetchone()[0] == 0
    assert raw.execute(
        "SELECT COUNT(*) FROM map_entity_metadata"
    ).fetchone()[0] == 0


def test_removing_is_one_undo_away(server: MtaSandbox) -> None:
    """An answer given too quickly is not a deletion the player cannot take
    back."""
    editor_with_map(server)
    seed_linked_entity(server)
    player = study_player(server)

    server.eval(
        'function(p) return forgetMapEntity(p, "mymap", "object (bin) (1)") end'
    )(player)
    server.eval("function() return ANKIGTA.Store.undo() end")()

    raw = server.connection.raw
    assert raw.execute(
        "SELECT entity_type, authored_x FROM map_entities"
    ).fetchall() == [("object", 1)]
    assert raw.execute(
        "SELECT card_id, state FROM spatial_links"
    ).fetchall() == [(42, "active")]
    assert raw.execute(
        "SELECT name FROM map_entity_metadata"
    ).fetchall() == [("North bin",)]
    # `radius_override`, not `radius`: the second is the inert column nothing
    # reads, kept only because SQLite cannot drop it from a table other tables
    # cascade from.
    assert raw.execute(
        "SELECT radius_override FROM map_entity_metadata"
    ).fetchall() == [(7.5,)]


def test_undoing_a_removal_puts_back_following_the_global(
    server: MtaSandbox,
) -> None:
    """An entity that had no radius of its own must not come back pinned to
    whatever the global said at the moment it was removed."""
    editor_with_map(server)
    seed_linked_entity(server)
    raw = server.connection.raw
    raw.execute("UPDATE map_entity_metadata SET radius_override = NULL")
    player = study_player(server)

    server.eval(
        'function(p) return forgetMapEntity(p, "mymap", "object (bin) (1)") end'
    )(player)
    server.eval("function() return ANKIGTA.Store.undo() end")()

    assert raw.execute(
        "SELECT radius_override FROM map_entity_metadata"
    ).fetchall() == [(None,)]


# --- the panel's half ---------------------------------------------------------


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


def push_snapshot(sandbox: MtaSandbox, deleted: list[dict[str, Any]]) -> None:
    sandbox.eval(
        """
        function(snapshot)
            triggerEvent("ankigta:f7Snapshot", resourceRoot, snapshot)
        end
        """
    )(
        to_lua(
            sandbox,
            {
                "visible": True,
                "cardPicker": {"enabled": True},
                "history": {"canUndo": False, "canRedo": False},
                "currentMap": {"resourceName": "mymap", "mapIds": ["mymap"]},
                "cardLinks": [],
                "entities": [],
                "deletedFromMap": deleted,
            },
        )
    )


def panel_action(
    sandbox: MtaSandbox, action: str, payload: dict[str, Any] | None = None
) -> None:
    sandbox.eval(
        """
        function(action, payload)
            triggerEvent("ankigta:panelAction", resourceRoot, action, payload)
        end
        """
    )(action, json.dumps(payload or {}))


DELETED = [
    {
        "mapId": "mymap",
        "entityId": "object (bin) (1)",
        "name": "North bin",
        "mapName": "mymap.map",
        "linked": True,
    }
]


def test_the_question_reaches_the_page(panel_client: MtaSandbox) -> None:
    push_snapshot(panel_client, DELETED)

    state = panel_client.pushed_panel_state()

    assert as_list(state["deletedFromMap"])[0]["name"] == "North bin"


def test_remove_asks_the_server_to_forget_that_entity(
    panel_client: MtaSandbox,
) -> None:
    push_snapshot(panel_client, DELETED)

    panel_action(panel_client, "forgetEntity")

    sent = [
        event for event in panel_client.recorder.server_events
        if event.name == "ankigta:forgetMapEntity"
    ]
    assert len(sent) == 1
    assert sent[0].args[0] == "mymap"
    assert sent[0].args[1] == "object (bin) (1)"


def test_keep_is_an_answer_and_is_not_asked_again(
    panel_client: MtaSandbox,
) -> None:
    """Keeping the link is a decision. Re-asking on the next snapshot would
    look like it had not been heard."""
    push_snapshot(panel_client, DELETED)

    panel_action(panel_client, "keepDeletedEntity")

    assert as_list(panel_client.pushed_panel_state()["deletedFromMap"]) == []
    assert [
        event for event in panel_client.recorder.server_events
        if event.name == "ankigta:forgetMapEntity"
    ] == []

    # And it stays answered when the server says the same thing again.
    push_snapshot(panel_client, DELETED)
    assert as_list(panel_client.pushed_panel_state()["deletedFromMap"]) == []
