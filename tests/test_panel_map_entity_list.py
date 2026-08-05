"""Panel usability 02 — the Map Entity list's public behaviour."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox


REPO_ROOT = Path(__file__).resolve().parents[1]


def manifest_scripts(*kinds: str) -> list[str]:
    manifest = ElementTree.parse(REPO_ROOT / "mta" / "ankigta" / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


def test_f7_survives_an_incremental_client_reload_before_entity_types_arrive() -> None:
    """A changed panel can reach an already connected client before a new script."""
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        sandbox.load("shared/locale.lua")
        sandbox.load("client/layout.lua")
        sandbox.load("client/panel.lua")
        sandbox.trigger("onClientResourceStart")
        sandbox.eval(
            'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
        )()

        for handler in sandbox.bound_keys.get(("F7", "down"), []):
            handler()

        assert len(sandbox.browsers) == 1
    finally:
        sandbox.close()


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


def push_client_snapshot(
    sandbox: MtaSandbox,
    *,
    entities: list[dict[str, Any]],
    current_map_ids: list[str] | None = None,
    card_links: list[dict[str, Any]] | None = None,
) -> None:
    snapshot = {
        "visible": True,
        "cardPicker": {"enabled": True},
        "history": {"canUndo": False, "canRedo": False},
        "entities": entities,
        "currentMap": {
            "resourceName": "current-map",
            "mapIds": current_map_ids or ["current-map-id"],
        },
        "cardLinks": card_links or [],
    }
    sandbox.eval(
        """
        function(snapshot)
            triggerEvent("ankigta:f7Snapshot", resourceRoot, snapshot)
        end
        """
    )(to_lua(sandbox, snapshot))


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


def panel_entry(
    *,
    entity_id: str = "gate-17",
    name: str = "North gate",
    available: bool = False,
) -> dict[str, Any]:
    return {
        "mapEntity": {
            "mapId": "current-map-id",
            "entityId": entity_id,
            "type": "object",
            "model": 1337,
            "map": {"resourceName": "current-map", "mapName": "Current Map"},
            "authored": {
                "position": {"x": 10.25, "y": -20.5, "z": 3},
                "rotation": {"x": 0, "y": 0, "z": 0},
                "world": {"interior": 0, "dimension": 0},
            },
        },
        "runtimeInstance": {"available": available, "referenceId": entity_id},
        "metadata": {
            "name": name,
            "entityTag": "",
            "radius": 3,
            "showCorona": False,
        },
        "link": {"state": "Unlinked"},
    }


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


def seed_entity(
    sandbox: MtaSandbox,
    *,
    map_id: str,
    resource_name: str,
    entity_id: str,
    map_name: str | None = None,
) -> None:
    connection: sqlite3.Connection = sandbox.connection.raw
    connection.execute(
        "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
        " VALUES (?, ?, ?)",
        (map_id, resource_name, map_name or resource_name),
    )
    connection.execute(
        "INSERT OR REPLACE INTO map_entities (map_id, entity_id, entity_type,"
        " model, authored_x, authored_y, authored_z, rotation_x, rotation_y,"
        " rotation_z, interior, dimension)"
        " VALUES (?, ?, 'object', 1337, 10, 20, 30, 0, 0, 0, 0, 0)",
        (map_id, entity_id),
    )


def install_resource_world(
    sandbox: MtaSandbox,
    *,
    current_resource: str,
    duplicate_entity_id: str,
) -> Any:
    """One running map plus the editor's live copy of the same element."""
    current = sandbox.lua.table_from({"name": current_resource})
    editor = sandbox.lua.table_from({"name": "editor_main"})
    current_root = sandbox.lua.table_from(
        {"__element": True, "type": "resourceRoot", "name": current_resource}
    )
    editor_root = sandbox.lua.table_from(
        {"__element": True, "type": "resourceRoot", "name": "editor_main"}
    )
    sandbox.eval(
        """
        function(current, editor, currentRoot, editorRoot)
            getResources = function() return {current, editor} end
            getResourceName = function(value) return value.name end
            getResourceRootElement = function(value)
                if value == current then return currentRoot end
                return editorRoot
            end
            getResourceState = function(value) return "running" end
            getResourceInfo = function(value, key)
                if key == "type" and value == current then return "map" end
                return false
            end
            getResourceFromName = function(name)
                if name == current.name then return current end
                if name == editor.name then return editor end
                return false
            end
        end
        """
    )(current, editor, current_root, editor_root)

    original = sandbox.add_world_element(
        entity_id=duplicate_entity_id,
        map_id=duplicate_entity_id,
        ankigtaEntityId=duplicate_entity_id,
    )
    original["__parent"] = current_root
    editor_copy = sandbox.add_world_element(
        entity_id=duplicate_entity_id,
        map_id=duplicate_entity_id,
        dimension=200,
        ankigtaEntityId=duplicate_entity_id,
    )
    editor_copy["__parent"] = editor_root
    return original


def request_snapshot(
    sandbox: MtaSandbox, *, player_dimension: int | None = None
) -> dict[str, Any]:
    player = sandbox.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0
    if player_dimension is not None:
        player["dimension"] = player_dimension
    sandbox.trigger(
        "ankigta:requestF7",
        sandbox.lua.globals().resourceRoot,
        client=player,
    )
    event = sandbox.recorder.client_events[-1]
    assert event.name == "ankigta:f7Snapshot"
    return sandbox.to_python(event.args[0])


def test_the_list_contains_each_entity_of_the_current_map_once(
    server: MtaSandbox,
) -> None:
    seed_entity(
        server,
        map_id="current-map-id",
        resource_name="current-map",
        entity_id="shared-object",
    )
    seed_entity(
        server,
        map_id="other-map-id",
        resource_name="other-map",
        entity_id="elsewhere",
    )
    runtime = install_resource_world(
        server,
        current_resource="current-map",
        duplicate_entity_id="shared-object",
    )
    runtime["__id"] = "different-mta-id"

    snapshot = request_snapshot(server)

    assert [
        (entry["mapEntity"]["mapId"], entry["mapEntity"]["entityId"])
        for entry in snapshot["entities"]
    ] == [("current-map-id", "shared-object")]


def test_a_live_marker_is_not_reported_as_destroyed(server: MtaSandbox) -> None:
    seed_entity(
        server,
        map_id="current-map-id",
        resource_name="current-map",
        entity_id="marker-1",
    )
    server.connection.raw.execute(
        "UPDATE map_entities SET entity_type = 'marker'"
        " WHERE map_id = ? AND entity_id = ?",
        ("current-map-id", "marker-1"),
    )
    runtime = install_resource_world(
        server,
        current_resource="current-map",
        duplicate_entity_id="marker-1",
    )
    runtime["type"] = "marker"
    for element in server.world_elements:
        if element["dimension"] == 200:
            element["ankigtaEntityId"] = "editor-copy"

    snapshot = request_snapshot(server)

    assert snapshot["entities"][0]["runtimeInstance"]["available"] is True


def test_a_runtime_map_identity_excludes_old_maps_from_the_same_resource(
    server: MtaSandbox,
) -> None:
    seed_entity(
        server,
        map_id="current-map-id",
        resource_name="current-map",
        entity_id="here",
    )
    seed_entity(
        server,
        map_id="old-map-id",
        resource_name="current-map",
        entity_id="old-copy",
    )
    current = install_resource_world(
        server,
        current_resource="current-map",
        duplicate_entity_id="here",
    )
    current["ankigtaMapId"] = "current-map-id"

    snapshot = request_snapshot(server)

    assert [
        entry["mapEntity"]["mapId"] for entry in snapshot["entities"]
    ] == ["current-map-id"]


def test_multiple_running_maps_are_resolved_from_the_players_world(
    server: MtaSandbox,
) -> None:
    seed_entity(
        server, map_id="map-a-id", resource_name="map-a", entity_id="far"
    )
    seed_entity(
        server, map_id="map-z-id", resource_name="map-z", entity_id="here"
    )
    map_a = server.lua.table_from({"name": "map-a"})
    map_z = server.lua.table_from({"name": "map-z"})
    root_a = server.lua.table_from(
        {"__element": True, "type": "resourceRoot", "name": "map-a"}
    )
    root_z = server.lua.table_from(
        {"__element": True, "type": "resourceRoot", "name": "map-z"}
    )
    server.eval(
        """
        function(mapA, mapZ, rootA, rootZ)
            getResources = function() return {mapA, mapZ} end
            getResourceName = function(value) return value.name end
            getResourceRootElement = function(value)
                if value == mapA then return rootA end
                return rootZ
            end
            getResourceState = function() return "running" end
            getResourceInfo = function(_, key)
                if key == "type" then return "map" end
                return false
            end
            getResourceFromName = function() return false end
        end
        """
    )(map_a, map_z, root_a, root_z)
    far = server.add_world_element(
        entity_id="far",
        map_id="far",
        dimension=1,
        ankigtaEntityId="far",
        ankigtaMapId="map-a-id",
    )
    far["__parent"] = root_a
    here = server.add_world_element(
        entity_id="here",
        map_id="here",
        dimension=9,
        ankigtaEntityId="here",
        ankigtaMapId="map-z-id",
    )
    here["__parent"] = root_z

    snapshot = request_snapshot(server, player_dimension=9)

    assert snapshot["currentMap"]["resourceName"] == "map-z"
    assert [
        entry["mapEntity"]["entityId"] for entry in snapshot["entities"]
    ] == ["here"]


def test_the_editor_list_skips_representations_and_its_deleted_dimension(
    server: MtaSandbox,
) -> None:
    server.editor_map_name = "current-map"
    server.editor_working_dimension = 200
    editor = server.lua.table_from({"name": "editor_main"})
    editor_root = server.lua.table_from(
        {"__element": True, "type": "resourceRoot", "name": "editor_main"}
    )
    server.eval(
        """
        function(editor, editorRoot)
            getResources = function() return {editor} end
            getResourceName = function(value) return value.name end
            getResourceRootElement = function(value) return editorRoot end
            getResourceState = function(value) return "running" end
            getResourceInfo = function(value, key) return false end
            getResourceFromName = function(name)
                if name == "editor_main" then return editor end
                return false
            end
        end
        """
    )(editor, editor_root)

    kept = server.add_world_element(
        entity_id="kept", map_id="kept", dimension=200
    )
    kept["__parent"] = editor_root
    representation = server.add_world_element(
        entity_id="representation", map_id="representation", dimension=200
    )
    representation["__parent"] = editor_root
    # What EDF stamps on every element it parents to the one it draws.
    representation["edf:rep"] = True
    deleted = server.add_world_element(
        entity_id="deleted", map_id="deleted", dimension=201
    )
    deleted["__parent"] = editor_root

    snapshot = request_snapshot(server, player_dimension=200)

    assert [
        (entry["mapEntity"]["mapId"], entry["mapEntity"]["entityId"])
        for entry in snapshot["entities"]
    ] == [("current-map", "kept")]


def test_the_snapshot_reports_the_runtime_instance_for_each_saved_entity(
    server: MtaSandbox,
) -> None:
    seed_entity(
        server,
        map_id="current-map-id",
        resource_name="current-map",
        entity_id="present",
    )
    seed_entity(
        server,
        map_id="current-map-id",
        resource_name="current-map",
        entity_id="gone",
    )
    install_resource_world(
        server,
        current_resource="current-map",
        duplicate_entity_id="present",
    )

    snapshot = request_snapshot(server)
    by_id = {
        entry["mapEntity"]["entityId"]: entry["runtimeInstance"]
        for entry in snapshot["entities"]
    }

    assert by_id["present"]["available"] is True
    assert by_id["present"]["referenceId"] == "present"
    assert by_id["gone"]["available"] is False


def test_the_snapshot_keeps_other_map_links_for_the_card_picker(
    server: MtaSandbox,
) -> None:
    seed_entity(
        server,
        map_id="current-map-id",
        resource_name="current-map",
        entity_id="here",
    )
    seed_entity(
        server,
        map_id="other-map-id",
        resource_name="other-map",
        map_name="Other Map",
        entity_id="elsewhere",
    )
    server.connection.raw.execute(
        "INSERT INTO spatial_links (map_id, entity_id, collection_uuid, card_id,"
        " state, verified_map_sha256) VALUES (?, ?, ?, ?, 'active', ?)",
        ("other-map-id", "elsewhere", "collection-a", 42, "a" * 64),
    )
    install_resource_world(
        server,
        current_resource="current-map",
        duplicate_entity_id="here",
    )

    snapshot = request_snapshot(server)

    assert snapshot["currentMap"]["mapIds"] == ["current-map-id"]
    assert snapshot["cardLinks"] == [
        {
            "mapId": "other-map-id",
            "entityId": "elsewhere",
            "mapName": "Other Map",
            "collectionUuid": "collection-a",
            "cardId": 42,
        }
    ]


def test_a_cosmetic_name_survives_the_store_reopening(server: MtaSandbox) -> None:
    seed_entity(
        server,
        map_id="current-map-id",
        resource_name="current-map",
        entity_id="gate-17",
    )
    player = server.add_study_player()
    server.trigger(
        "ankigta:updateEntityMetadata",
        server.lua.globals().resourceRoot,
        "current-map-id",
        "gate-17",
        server.lua.table_from({"name": "North gate"}),
        client=player,
    )

    reopened = server.eval(
        """
        function()
            ANKIGTA.Store.close()
            assert(ANKIGTA.Store.open())
            return ANKIGTA.Store.getMapEntity("current-map-id", "gate-17")
        end
        """
    )()
    row = server.to_python(reopened)

    assert row["entity_name"] == "North gate"
    assert row["entity_id"] == "gate-17"


def test_adopting_an_editor_row_uses_the_editable_copy_not_the_play_test_copy(
    server: MtaSandbox,
) -> None:
    server.editor_map_name = "current-map"
    server.editor_working_dimension = 200
    current = server.lua.table_from({"name": "current-map"})
    editor = server.lua.table_from({"name": "editor_main"})
    current_root = server.lua.table_from(
        {"__element": True, "type": "resourceRoot", "name": "current-map"}
    )
    editor_root = server.lua.table_from(
        {"__element": True, "type": "resourceRoot", "name": "editor_main"}
    )
    server.eval(
        """
        function(current, editor, currentRoot, editorRoot)
            getResources = function() return {current, editor} end
            getResourceName = function(value) return value.name end
            getResourceRootElement = function(value)
                if value == current then return currentRoot end
                return editorRoot
            end
            getResourceState = function(value) return "running" end
            getResourceInfo = function(value, key)
                if value == current and key == "type" then return "map" end
                return false
            end
            getResourceFromName = function(name)
                if name == current.name then return current end
                if name == editor.name then return editor end
                return false
            end
            linkCardToEntity = function() return true end
        end
        """
    )(current, editor, current_root, editor_root)
    play_test_copy = server.add_world_element(
        entity_id="shared-object", map_id="shared-object", x=10, dimension=0
    )
    play_test_copy["__parent"] = current_root
    editable_copy = server.add_world_element(
        entity_id="shared-object", map_id="shared-object", x=99, dimension=200
    )
    editable_copy["__parent"] = editor_root
    player = server.add_study_player()
    player["dimension"] = 200
    player["x"], player["y"], player["z"] = 0, 0, 0

    server.trigger(
        "ankigta:adoptEntity",
        server.lua.globals().resourceRoot,
        "shared-object",
        server.lua.table_from({"collectionUuid": "collection-a", "cardId": 42}),
        client=player,
    )

    row = server.connection.raw.execute(
        "SELECT authored_x FROM map_entities WHERE map_id = ? AND entity_id = ?",
        ("current-map", "shared-object"),
    ).fetchone()
    assert row is not None
    assert row[0] == 99


def test_naming_something_the_list_only_offered_takes_it_in(
    server: MtaSandbox,
) -> None:
    """A Map Entity does not need a card in order to exist.

    Adoption used to happen only on the way to a link, so naming an object --
    or saying how close you must stand to it -- could not be done until a card
    had been chosen. The glossary has always had it the other way round: a
    Spatial Link is a link *between* a Map Entity and one card, so the entity
    is what the link is made of.
    """
    # A running map, plus one thing standing in it that carries no ANKIGTA
    # identity at all -- which is what an offer is.
    known = install_resource_world(
        server, current_resource="current-map", duplicate_entity_id="already-here"
    )
    offered = server.add_world_element(entity_id="lamp-3", map_id="lamp-3")
    offered["__parent"] = known["__parent"]
    player = server.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0

    server.trigger(
        "ankigta:updateEntityMetadata",
        server.lua.globals().resourceRoot,
        "current-map",
        "lamp-3",
        server.lua.table_from({"name": "The lamp", "radius": 7.5}),
        client=player,
    )

    row = server.connection.raw.execute(
        "SELECT name, radius_override FROM map_entity_metadata"
        " WHERE entity_id = ?",
        ("lamp-3",),
    ).fetchone()
    assert row is not None, "the offer was not taken into the store"
    assert row[0] == "The lamp"
    assert row[1] == 7.5

    # And with no Spatial Link, because none was asked for.
    links = server.connection.raw.execute(
        "SELECT COUNT(*) FROM spatial_links WHERE entity_id = ?", ("lamp-3",)
    ).fetchone()
    assert links[0] == 0


def test_a_marker_is_taken_in_and_settled_like_every_other_type(
    server: MtaSandbox,
) -> None:
    """A marker is a Map Entity everywhere -- `shared/entity_types.lua`, the
    world scan, Pick Entity, the spatial poll, and the database's own CHECK
    constraint since version 5. Adoption alone still listed the other three by
    hand, so a marker could be pointed at, offered and never taken: it could
    not be named, and had no row to carry a radius or a corona.

    A marker also has no model at all -- `getElementModel` answers `false` on
    the real server -- so it is the type that finds every place a model was
    assumed to be there.
    """
    known = install_resource_world(
        server, current_resource="current-map", duplicate_entity_id="already-here"
    )
    offered = server.add_world_element(
        "marker", map_id="marker (corona) (1)"
    )
    offered["__parent"] = known["__parent"]
    player = server.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0

    server.trigger(
        "ankigta:updateEntityMetadata",
        server.lua.globals().resourceRoot,
        "current-map",
        "marker (corona) (1)",
        server.lua.table_from({"name": "Chapter three", "radius": 7.5}),
        client=player,
    )

    stored = server.connection.raw.execute(
        "SELECT entity_type, model FROM map_entities WHERE entity_id = ?",
        ("marker (corona) (1)",),
    ).fetchone()
    assert stored is not None, "a marker was offered and could not be taken in"
    assert stored[0] == "marker"

    settings = server.connection.raw.execute(
        "SELECT name, radius_override FROM map_entity_metadata"
        " WHERE entity_id = ?",
        ("marker (corona) (1)",),
    ).fetchone()
    assert settings is not None
    assert settings[0] == "Chapter three"
    assert settings[1] == 7.5


def test_a_marker_carries_every_per_entity_setting_the_others_do(
    server: MtaSandbox,
) -> None:
    """Not only a name and a radius. Once a marker is an ordinary Map Entity,
    nothing about it needs a special case, so it answers about its corona and
    its activation the way an object does."""
    known = install_resource_world(
        server, current_resource="current-map", duplicate_entity_id="already-here"
    )
    offered = server.add_world_element("marker", map_id="marker (corona) (1)")
    offered["__parent"] = known["__parent"]
    player = server.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0

    server.trigger(
        "ankigta:updateEntityMetadata",
        server.lua.globals().resourceRoot,
        "current-map",
        "marker (corona) (1)",
        server.lua.table_from(
            {
                "showCorona": True,
                "coronaColor": "#ff8800",
                "activationType": "key",
                "activationKey": "e",
            }
        ),
        client=player,
    )

    row = next(
        entry
        for entry in request_snapshot(server)["entities"]
        if entry["mapEntity"]["entityId"] == "marker (corona) (1)"
    )

    assert row["metadata"]["showCorona"] is True
    assert row["metadata"]["coronaColor"] == "#ff8800"
    assert row["metadata"]["activationType"] == "key"
    assert row["metadata"]["activationKey"] == "e"


def test_taking_an_editor_element_in_stores_the_editors_own_name(
    server: MtaSandbox,
) -> None:
    """The whole of ticket 07's premise, asked of the store.

    `assignID` in the stock editor writes `ped (1)` into the element's id --
    `editor_main/server/IDhandler.lua` sets it three ways at once, `setElementID`
    among them -- and MTA fills the same id in from the `<ped id="...">` of a
    saved `.map`. Adoption reads it, so the name is already the `entity_id` half
    of the Map Entity's primary key. Nothing is captured, migrated, or added to
    the schema for this ticket, and this is what says so.
    """
    known = install_resource_world(
        server, current_resource="current-map", duplicate_entity_id="already-here"
    )
    before = server.connection.raw.execute(
        "SELECT version FROM schema_meta WHERE singleton = 1"
    ).fetchone()[0]
    placed = server.add_world_element("ped", map_id="ped (1)", model=0)
    placed["__parent"] = known["__parent"]
    player = server.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0

    server.trigger(
        "ankigta:updateEntityMetadata",
        server.lua.globals().resourceRoot,
        "current-map",
        "ped (1)",
        server.lua.table_from({"radius": 5}),
        client=player,
    )

    stored = server.connection.raw.execute(
        "SELECT entity_id FROM map_entities WHERE entity_type = 'ped'"
    ).fetchall()
    assert [row[0] for row in stored] == ["ped (1)"]
    # And it took no new shape to hold it.
    after = server.connection.raw.execute(
        "SELECT version FROM schema_meta WHERE singleton = 1"
    ).fetchone()[0]
    assert after == before


def test_the_row_a_player_reads_says_what_the_editor_wrote(
    server: MtaSandbox, panel_client: MtaSandbox
) -> None:
    """The two halves joined: the server's own snapshot, handed to the client's
    own list. Each half asserted alone would let the name be right in the store
    and derived again on the way to the screen, which is the defect this ticket
    is about."""
    known = install_resource_world(
        server, current_resource="current-map", duplicate_entity_id="already-here"
    )
    for kind, name, model in (
        ("ped", "ped (1)", 0),
        ("ped", "ped (2)", 0),
        ("marker", "marker (corona) (1)", 0),
    ):
        placed = server.add_world_element(kind, map_id=name, model=model)
        placed["__parent"] = known["__parent"]
        player = server.add_study_player()
        player["x"], player["y"], player["z"] = 0, 0, 0
        server.trigger(
            "ankigta:updateEntityMetadata",
            server.lua.globals().resourceRoot,
            "current-map",
            name,
            server.lua.table_from({"radius": 5}),
            client=player,
        )

    snapshot = request_snapshot(server)
    push_client_snapshot(panel_client, entities=snapshot["entities"])

    named = {row["name"] for row in panel_client.pushed_panel_state()["entities"]}
    assert {"ped (1)", "ped (2)", "marker (corona) (1)"} <= named
    assert "Unnamed Map Entity" not in named
    assert panel_client.script_warnings == []


def test_taking_an_editor_element_in_writes_nothing_into_the_editor(
    server: MtaSandbox,
) -> None:
    """ADR 0025 keeps the stock Map Editor stock. Adoption writes ANKIGTA's own
    stamp onto the element and one row into ANKIGTA's own database -- no file
    anywhere, and none of the editor's own element data touched."""
    known = install_resource_world(
        server, current_resource="current-map", duplicate_entity_id="already-here"
    )
    placed = server.add_world_element(
        "object",
        map_id="object (sw_hedstones) (1)",
        model=12961,
    )
    placed["__parent"] = known["__parent"]
    placed["id"] = "object (sw_hedstones) (1)"
    placed["me:ID"] = "object (sw_hedstones) (1)"

    def files_but_our_own() -> dict[str, bytes]:
        """Everything on disk except the one file ANKIGTA owns."""
        return {
            path: content
            for path, content in dict(server.files).items()
            if path != "ankigta.sqlite"
        }

    files_before = files_but_our_own()
    player = server.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0

    server.trigger(
        "ankigta:updateEntityMetadata",
        server.lua.globals().resourceRoot,
        "current-map",
        "object (sw_hedstones) (1)",
        server.lua.table_from({"name": "The headstone"}),
        client=player,
    )

    assert files_but_our_own() == files_before, "adoption wrote somebody's file"
    assert placed["id"] == "object (sw_hedstones) (1)"
    assert placed["me:ID"] == "object (sw_hedstones) (1)"
    # Its own stamp, which is ANKIGTA's key and nobody else's.
    assert placed["ankigtaEntityId"] == "object (sw_hedstones) (1)"


def test_an_entity_stored_under_one_map_is_written_to_from_another(
    server: MtaSandbox,
) -> None:
    """The owner's `vgsSstairs04_lvs`, exactly.

    Its row was stored under `editor_dump` while the world had it under
    `editor_test`, so the identity the panel names -- built from the map it is
    standing in -- missed a row that plainly existed, and
    `findMapEntityByRuntimeElement` refused on the owning resource. `Draw
    always` came back "the entity was not changed" for a thing standing in
    front of the player.

    The element carries ANKIGTA's own stamp, and that is the durable half of
    its identity; the map it happens to be in today is not.
    """
    known = install_resource_world(
        server, current_resource="current-map", duplicate_entity_id="already-here"
    )
    seed_entity(
        server,
        map_id="a-map-that-is-not-running",
        resource_name="a-map-that-is-not-running",
        entity_id="stairs-9",
    )
    standing = server.add_world_element(
        entity_id="stairs-9", map_id="stairs-9", ankigtaEntityId="stairs-9"
    )
    standing["__parent"] = known["__parent"]
    player = server.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0

    server.trigger(
        "ankigta:updateEntityMetadata",
        server.lua.globals().resourceRoot,
        "current-map",
        "stairs-9",
        server.lua.table_from({"showCorona": True}),
        client=player,
    )

    refused = [
        event
        for event in server.recorder.client_events
        if event.name == "ankigta:pendingMapSaveNotice"
    ]
    assert refused == [], f"refused: {[event.args for event in refused]}"
    assert server.connection.raw.execute(
        "SELECT show_corona_override FROM map_entity_metadata"
        " WHERE entity_id = ?",
        ("stairs-9",),
    ).fetchone() == (1,)


def test_an_already_stamped_element_is_listed_as_the_entity_it_is(
    server: MtaSandbox,
) -> None:
    """Not offered again under empty metadata.

    The owner's stairs had a row under one map while the world held it under
    another, so it was listed as something to take in -- with `showCorona`
    hardcoded false over a row that said otherwise. Ticking the box wrote
    correctly and the next snapshot put it straight back.
    """
    known = install_resource_world(
        server, current_resource="current-map", duplicate_entity_id="already-here"
    )
    seed_entity(
        server,
        map_id="a-map-that-is-not-running",
        resource_name="a-map-that-is-not-running",
        entity_id="stairs-9",
    )
    server.connection.raw.execute(
        "INSERT INTO map_entity_metadata"
        " (map_id, entity_id, name, entity_tag, show_corona_override)"
        " VALUES (?, ?, '', '', 1)",
        ("a-map-that-is-not-running", "stairs-9"),
    )
    server.connection.raw.commit()
    standing = server.add_world_element(
        entity_id="stairs-9", map_id="stairs-9", ankigtaEntityId="stairs-9"
    )
    standing["__parent"] = known["__parent"]

    snapshot = request_snapshot(server)
    rows = {
        row["mapEntity"]["entityId"]: row for row in snapshot["entities"]
    }

    assert "stairs-9" in rows, sorted(rows)
    stairs = rows["stairs-9"]
    assert stairs["metadata"]["showCorona"] is True
    # A stored row, not an offer: an offer carries `adoptable`.
    assert "adoptable" not in stairs
    # And exactly once: an entity is one row, not a row and an offer of itself.
    assert [r["mapEntity"]["entityId"] for r in snapshot["entities"]].count(
        "stairs-9"
    ) == 1


def test_a_panel_row_describes_position_and_location_not_identity(
    panel_client: MtaSandbox,
) -> None:
    push_client_snapshot(panel_client, entities=[panel_entry()])

    row = panel_client.pushed_panel_state()["entities"][0]

    assert row["name"] == "North gate"
    assert row["description"] == "10.25, -20.50, 3.00 · Ganton"
    assert "current-map-id" not in row["description"]
    assert "gate-17" not in row["description"]
    assert "availabilityKey" not in row


def test_a_row_with_no_identity_at_all_uses_words(
    panel_client: MtaSandbox,
) -> None:
    """The one case with nothing to show. A stored Map Entity always has an
    `entity_id` -- it is half of its primary key -- so this is the guard rather
    than a case the player meets."""
    entry = panel_entry(name="")
    entry["mapEntity"]["entityId"] = ""
    entry["mapEntity"]["model"] = False
    push_client_snapshot(panel_client, entities=[entry])

    row = panel_client.pushed_panel_state()["entities"][0]

    assert row["name"] == "Unnamed Map Entity"


def test_a_row_is_called_what_the_map_editor_calls_it(
    panel_client: MtaSandbox,
) -> None:
    """The editor's own name is already the `entity_id` ANKIGTA stored.

    It is what the player reads beside the panel in the Map Editor, so it is
    what the row says. Deriving a name from the model told two peds of one skin
    apart from nothing and told a marker apart from nothing at all.
    """
    entry = panel_entry(entity_id="ped (1)", name="")
    entry["mapEntity"]["type"] = "ped"
    entry["mapEntity"]["model"] = 0
    push_client_snapshot(panel_client, entities=[entry])

    row = panel_client.pushed_panel_state()["entities"][0]

    assert row["name"] == "ped (1)"
    # `engineGetModelNameFromID` reads `CModelNames`, which holds the object
    # table and vehicles 400-610 and no peds at all. Asked about a ped it
    # answers `false` and logs `Expected valid model ID` -- a warning per ped
    # per snapshot, which buried everything else worth reading in the log.
    assert panel_client.script_warnings == []


def test_two_peds_of_one_skin_are_two_different_rows(
    panel_client: MtaSandbox,
) -> None:
    """The defect reported as item 39: both read `Ped skin 0`, and the editor
    standing beside them said `ped (1)` and `ped (2)`."""
    rows = []
    for name in ("ped (1)", "ped (2)"):
        entry = panel_entry(entity_id=name, name="")
        entry["mapEntity"]["type"] = "ped"
        entry["mapEntity"]["model"] = 0
        rows.append(entry)
    push_client_snapshot(panel_client, entities=rows)

    named = [row["name"] for row in panel_client.pushed_panel_state()["entities"]]

    assert sorted(named) == ["ped (1)", "ped (2)"]


def test_a_marker_is_named_from_the_same_place_as_every_other_type(
    panel_client: MtaSandbox,
) -> None:
    """Reported as item 38. A marker has no model, so a name derived from one
    fell straight through to `Unnamed Map Entity` -- while the editor beside it
    called the same thing `marker (corona) (1)`."""
    entry = panel_entry(entity_id="marker (corona) (1)", name="")
    entry["mapEntity"]["type"] = "marker"
    entry["mapEntity"]["model"] = False
    push_client_snapshot(panel_client, entities=[entry])

    row = panel_client.pushed_panel_state()["entities"][0]

    assert row["name"] == "marker (corona) (1)"
    assert panel_client.script_warnings == []


def test_an_entity_no_editor_named_reads_as_what_it_actually_is(
    panel_client: MtaSandbox,
) -> None:
    """Not every Map Entity comes out of the editor. A freeroam vehicle is
    adopted by where it stands, and its `entity_id` is that positional name --
    which the row says rather than dressing it up as something it is not."""
    entry = panel_entry(entity_id="at_9d1f4c2b7a", name="")
    entry["mapEntity"]["type"] = "vehicle"
    entry["mapEntity"]["model"] = 411
    push_client_snapshot(panel_client, entities=[entry])

    row = panel_client.pushed_panel_state()["entities"][0]

    assert row["name"] == "at_9d1f4c2b7a"
    # And not the model's name, which is a fact about the car rather than about
    # which car this is.
    assert "Infernus" not in row["name"]


@pytest.mark.parametrize(
    ("kind", "model"),
    [("ped", 0), ("ped", 264), ("object", 1337), ("vehicle", 411), ("marker", False)],
)
def test_what_a_row_is_called_does_not_depend_on_its_model(
    panel_client: MtaSandbox, kind: str, model: Any
) -> None:
    """No id->name table for ped skins is shipped, and none can be: the name is
    a function of the `entity_id` alone. `object (sw_hedstones) (1)` keeps the
    model name because the editor put it there, not because ANKIGTA looked one
    up."""
    entry = panel_entry(entity_id="thing (1)", name="")
    entry["mapEntity"]["type"] = kind
    entry["mapEntity"]["model"] = model
    push_client_snapshot(panel_client, entities=[entry])

    assert panel_client.pushed_panel_state()["entities"][0]["name"] == "thing (1)"


def test_a_card_linked_to_another_map_names_that_map(
    panel_client: MtaSandbox,
) -> None:
    uuid = "11111111-1111-4111-8111-111111111111"
    push_client_snapshot(
        panel_client,
        entities=[panel_entry()],
        card_links=[
            {
                "mapId": "current-map-id",
                "entityId": "here",
                "mapName": "current-map",
                "collectionUuid": uuid,
                "cardId": 7,
            },
            {
                "mapId": "other-map-id",
                "entityId": "elsewhere",
                "mapName": "Other Map",
                "collectionUuid": uuid,
                "cardId": 42,
            },
        ],
    )
    panel_client.eval(
        """
        function(uuid)
            triggerEvent("ankigta:cardPickerSnapshot", resourceRoot, {
                enabled = true,
                cards = {
                    {identity = {collectionUuid = uuid, cardId = 7},
                     deck = {name = "Deck"}, state = "review", sortField = "Here"},
                },
            })
        end
        """
    )(uuid)

    cards = {
        row["cardId"]: row
        for row in panel_client.pushed_panel_state()["cardPicker"]["cards"]
    }

    assert cards["7"]["foreignMap"] is False
    assert cards["42"]["foreignMap"] is True
    assert cards["42"]["foreignMapName"] == "Other Map"
    assert cards["42"]["label"] == ""


def test_renaming_uses_the_selected_identity_and_only_changes_the_name(
    panel_client: MtaSandbox,
) -> None:
    push_client_snapshot(panel_client, entities=[panel_entry()])
    panel_action(
        panel_client,
        "select",
        {"mapId": "current-map-id", "entityId": "gate-17"},
    )

    panel_action(panel_client, "setEntityName", {"name": "West entrance"})

    sent = [
        event
        for event in panel_client.recorder.server_events
        if event.name == "ankigta:updateEntityMetadata"
    ]
    assert len(sent) == 1
    assert sent[0].args[0:2] == ("current-map-id", "gate-17")
    assert panel_client.to_python(sent[0].args[2]) == {"name": "West entrance"}


def test_focusing_a_row_points_the_camera_without_moving_the_player(
    panel_client: MtaSandbox,
) -> None:
    panel_client.add_world_element(
        entity_id="gate-17",
        map_id="gate-17",
        x=-999,
        streamed=False,
        ankigtaEntityId="gate-17",
        ankigtaMapId="current-map-id",
    )
    element = panel_client.add_world_element(
        entity_id="gate-17",
        map_id="gate-17",
        x=10.25,
        y=-20.5,
        z=3,
        ankigtaEntityId="gate-17",
        ankigtaMapId="current-map-id",
    )
    push_client_snapshot(
        panel_client,
        entities=[panel_entry(available=True)],
    )
    assert "availabilityKey" not in panel_client.pushed_panel_state()["entities"][0]
    before_moves = list(panel_client.moved)
    before_camera = panel_client.camera_matrix
    panel_client.camera_interior = 7

    panel_action(
        panel_client,
        "focusEntity",
        {"mapId": "current-map-id", "entityId": "gate-17"},
    )

    assert panel_client.camera_matrix[3:6] == (10.25, -20.5, 3.0)
    assert panel_client.camera_interior == element["interior"]
    assert panel_client.moved == before_moves

    panel_action(panel_client, "close")

    assert panel_client.camera_matrix == before_camera
    assert panel_client.camera_interior == 7


def test_the_camera_comes_back_to_the_player_who_left_the_car(
    panel_client: MtaSandbox,
) -> None:
    """`getCameraTarget()` answers with the vehicle while the player rides one.

    Handing that element back afterwards is right only while they are still in
    it. Get out in between and the camera stays on an empty car, watching it
    from wherever it is parked -- the player left with no way to see themselves
    at all.
    """
    push_client_snapshot(panel_client, entities=[panel_entry(available=False)])
    car = panel_client.add_world_element(kind="vehicle")
    panel_client.occupied_vehicle = car
    panel_client.camera_target = car

    panel_action(
        panel_client,
        "focusEntity",
        {"mapId": "current-map-id", "entityId": "gate-17"},
    )
    # They get out while the camera is away.
    panel_client.occupied_vehicle = False
    panel_action(panel_client, "close")

    same = panel_client.eval("function(c) return getCameraTarget() == c end")
    assert same(car) is False
    assert panel_client.eval(
        "function() return getCameraTarget() == localPlayer end"
    )() is True


def test_the_camera_goes_back_to_the_car_they_are_still_sitting_in(
    panel_client: MtaSandbox,
) -> None:
    """Coming back wrong is not better than coming back."""
    push_client_snapshot(panel_client, entities=[panel_entry(available=False)])
    car = panel_client.add_world_element(kind="vehicle")
    panel_client.occupied_vehicle = car
    panel_client.camera_target = car

    panel_action(
        panel_client,
        "focusEntity",
        {"mapId": "current-map-id", "entityId": "gate-17"},
    )
    panel_action(panel_client, "close")

    assert panel_client.eval(
        "function(c) return getCameraTarget() == c end"
    )(car) is True


def test_focusing_a_distant_row_uses_its_authored_position_without_streaming(
    panel_client: MtaSandbox,
) -> None:
    push_client_snapshot(panel_client, entities=[panel_entry(available=False)])
    before_moves = list(panel_client.moved)
    before_camera = panel_client.camera_matrix
    panel_client.camera_interior = 7

    panel_action(
        panel_client,
        "focusEntity",
        {"mapId": "current-map-id", "entityId": "gate-17"},
    )

    assert panel_client.camera_matrix != before_camera
    assert panel_client.camera_matrix[3:6] == (10.25, -20.5, 3.0)
    assert panel_client.camera_interior == 0
    assert panel_client.moved == before_moves


def test_distant_camera_focus_holds_the_player_until_the_panel_closes(
    panel_client: MtaSandbox,
) -> None:
    push_client_snapshot(panel_client, entities=[panel_entry(available=False)])
    assert panel_client.eval("function() return isElementFrozen(localPlayer) end")() is False

    panel_action(
        panel_client,
        "focusEntity",
        {"mapId": "current-map-id", "entityId": "gate-17"},
    )

    assert panel_client.eval("function() return isElementFrozen(localPlayer) end")() is True

    panel_action(panel_client, "close")

    assert panel_client.eval("function() return isElementFrozen(localPlayer) end")() is False


def test_camera_focus_restores_an_already_frozen_player(
    panel_client: MtaSandbox,
) -> None:
    push_client_snapshot(panel_client, entities=[panel_entry(available=False)])
    panel_client.eval("function() setElementFrozen(localPlayer, true) end")()

    panel_action(
        panel_client,
        "focusEntity",
        {"mapId": "current-map-id", "entityId": "gate-17"},
    )
    panel_action(panel_client, "close")

    assert panel_client.eval("function() return isElementFrozen(localPlayer) end")() is True


def test_distant_camera_focus_holds_an_occupied_vehicle_too(
    panel_client: MtaSandbox,
) -> None:
    push_client_snapshot(panel_client, entities=[panel_entry(available=False)])
    vehicle = panel_client.add_world_element("vehicle")
    panel_client.occupied_vehicle = vehicle

    panel_action(
        panel_client,
        "focusEntity",
        {"mapId": "current-map-id", "entityId": "gate-17"},
    )

    assert panel_client.eval("function(v) return isElementFrozen(v) end")(vehicle) is True

    panel_action(panel_client, "close")

    assert panel_client.eval("function(v) return isElementFrozen(v) end")(vehicle) is False


def test_closing_after_camera_focus_never_requests_a_teleport(
    panel_client: MtaSandbox,
) -> None:
    push_client_snapshot(panel_client, entities=[panel_entry(available=False)])
    panel_action(
        panel_client,
        "focusEntity",
        {"mapId": "current-map-id", "entityId": "gate-17"},
    )

    panel_action(panel_client, "close")

    assert not [
        event
        for event in panel_client.recorder.server_events
        if event.name == "ankigta:teleportToEntity"
    ]
    assert panel_client.moved == []


def test_teleport_closes_the_panel_before_requesting_the_move(
    panel_client: MtaSandbox,
) -> None:
    push_client_snapshot(panel_client, entities=[panel_entry(available=False)])
    panel_action(
        panel_client,
        "select",
        {"mapId": "current-map-id", "entityId": "gate-17"},
    )
    panel_client.eval(
        """
        function()
            local originalTriggerServerEvent = triggerServerEvent
            triggerServerEvent = function(name, ...)
                if name == "ankigta:teleportToEntity" then
                    panelOpenAtTeleportRequest = isPanelOpen()
                end
                return originalTriggerServerEvent(name, ...)
            end
        end
        """
    )()

    panel_action(panel_client, "teleport")

    assert panel_client.eval("function() return panelOpenAtTeleportRequest end")() is False
    assert panel_client.eval("function() return isPanelOpen() end")() is False
    sent = [
        event
        for event in panel_client.recorder.server_events
        if event.name == "ankigta:teleportToEntity"
    ]
    assert len(sent) == 1
    assert sent[0].args == ("current-map-id", "gate-17")


def test_a_fresh_f7_snapshot_updates_entity_and_card_rows_without_reopening(
    panel_client: MtaSandbox,
) -> None:
    uuid = "11111111-1111-4111-8111-111111111111"
    unlinked = panel_entry()
    push_client_snapshot(panel_client, entities=[unlinked])
    panel_client.eval(
        """
        function(uuid)
            triggerEvent("ankigta:cardPickerSnapshot", resourceRoot, {
                enabled = true,
                cards = {
                    {identity = {collectionUuid = uuid, cardId = 42},
                     deck = {name = "Deck"}, state = "review", sortField = "Gate"},
                },
            })
        end
        """
    )(uuid)
    before = panel_client.pushed_panel_state()
    assert before["entities"][0]["linkState"] == "Unlinked"
    assert before["cardPicker"]["cards"][0]["linked"] is False

    linked = panel_entry()
    linked["link"] = {
        "state": "Active Spatial Link",
        "cardIdentity": {"collectionUuid": uuid, "cardId": 42},
    }
    push_client_snapshot(
        panel_client,
        entities=[linked],
        card_links=[
            {
                "mapId": "current-map-id",
                "entityId": "gate-17",
                "mapName": "current-map",
                "collectionUuid": uuid,
                "cardId": 42,
            }
        ],
    )

    after = panel_client.pushed_panel_state()
    assert after["entities"][0]["linkState"] == "Active Spatial Link"
    assert after["cardPicker"]["cards"][0]["linked"] is True
    assert after["cardPicker"]["cards"][0]["linkedMapName"] == "current-map"


def test_an_entity_change_refreshes_an_open_panel(panel_client: MtaSandbox) -> None:
    panel_client.recorder.server_events.clear()
    created = panel_client.add_world_element(entity_id="new-object", map_id="new-object")

    panel_client.trigger("onClientElementCreate", created)
    panel_client.fire_timers()

    assert [
        event
        for event in panel_client.recorder.server_events
        if event.name == "ankigta:requestF7"
    ]


# --- what a row inherits, and what it was told --------------------------------


def follows_the_global(**over: Any) -> dict[str, Any]:
    """A panel entry that has never been told a radius of its own."""
    entry = panel_entry(**over)
    entry["metadata"].pop("radius")
    return entry


def announce_global(sandbox: MtaSandbox, **values: Any) -> None:
    sandbox.eval(
        """
        function(values)
            triggerEvent("ankigta:settingsSnapshot", resourceRoot,
                {values = values})
        end
        """
    )(to_lua(sandbox, values))


def test_a_row_with_no_radius_of_its_own_shows_the_global_in_force(
    panel_client: MtaSandbox,
) -> None:
    """An override left unset used to arrive as the shipped default, so every
    row looked like a decision somebody had taken -- and turning the global up
    appeared to do nothing at all."""
    announce_global(panel_client, activationRadius=10)
    push_client_snapshot(panel_client, entities=[follows_the_global()])

    row = panel_client.pushed_panel_state()["entities"][0]

    assert row["radius"] == 10
    assert row["radiusInherited"] is True


def test_a_row_with_its_own_radius_says_it_was_chosen(
    panel_client: MtaSandbox,
) -> None:
    announce_global(panel_client, activationRadius=10)
    entry = panel_entry()
    entry["metadata"]["radius"] = 7.5
    push_client_snapshot(panel_client, entities=[entry])

    row = panel_client.pushed_panel_state()["entities"][0]

    assert row["radius"] == 7.5
    assert row["radiusInherited"] is False


def test_emptying_the_radius_asks_the_server_to_stop_holding_one(
    panel_client: MtaSandbox,
) -> None:
    """An emptied box is a different answer both from a number and from this
    message not being about the radius at all, so it travels as its own."""
    push_client_snapshot(panel_client, entities=[panel_entry()])
    panel_action(
        panel_client, "select", {"mapId": "current-map-id", "entityId": "gate-17"}
    )

    panel_action(panel_client, "setEntityMarks", {"radius": False})

    sent = [
        event
        for event in panel_client.recorder.server_events
        if event.name == "ankigta:updateEntityMetadata"
    ]
    assert len(sent) == 1
    assert panel_client.to_python(sent[0].args[2])["radius"] is False


def write_metadata(
    server: MtaSandbox, player: Any, metadata: dict[str, Any]
) -> None:
    server.trigger(
        "ankigta:updateEntityMetadata",
        server.lua.globals().resourceRoot,
        "current-map-id",
        "gate-17",
        server.lua.table_from(metadata),
        client=player,
    )


def stored_override(server: MtaSandbox) -> Any:
    row = server.connection.raw.execute(
        "SELECT radius_override FROM map_entity_metadata WHERE entity_id = ?",
        ("gate-17",),
    ).fetchone()
    return None if row is None else row[0]


def test_naming_an_entity_leaves_its_radius_following_the_global(
    server: MtaSandbox,
) -> None:
    """The bug in the owner's own database: three of five metadata rows carry a
    radius of 3 that nobody chose, written by the act of naming the thing or of
    ticking the box that is now `Show corona`. Every one of them stopped following the global the
    moment it was written."""
    seed_entity(
        server,
        map_id="current-map-id",
        resource_name="current-map",
        entity_id="gate-17",
    )
    player = server.add_study_player()

    write_metadata(server, player, {"name": "North gate"})

    stored = server.connection.raw.execute(
        "SELECT name, radius_override FROM map_entity_metadata WHERE entity_id = ?",
        ("gate-17",),
    ).fetchone()
    assert stored == ("North gate", None)


def test_a_radius_that_was_chosen_is_stored_and_can_be_given_back(
    server: MtaSandbox,
) -> None:
    seed_entity(
        server,
        map_id="current-map-id",
        resource_name="current-map",
        entity_id="gate-17",
    )
    player = server.add_study_player()

    write_metadata(server, player, {"radius": 7.5})
    assert stored_override(server) == 7.5

    # Another field is not an answer about the radius, so the radius stands.
    write_metadata(server, player, {"name": "North gate"})
    assert stored_override(server) == 7.5

    write_metadata(server, player, {"radius": "inherit"})
    assert stored_override(server) is None


def test_undo_puts_back_a_radius_that_was_following_the_global(
    server: MtaSandbox,
) -> None:
    """Undo has to restore "it followed the global" as faithfully as it
    restores a number, or one Undo quietly pins an entity to whatever the
    global happened to say."""
    seed_entity(
        server,
        map_id="current-map-id",
        resource_name="current-map",
        entity_id="gate-17",
    )
    player = server.add_study_player()
    write_metadata(server, player, {"radius": 7.5})
    assert stored_override(server) == 7.5

    server.trigger("ankigta:undo", server.lua.globals().resourceRoot, client=player)

    assert stored_override(server) is None


# --- a renamed row still says what it was -------------------------------------


def test_a_renamed_row_carries_the_name_it_had_before(
    panel_client: MtaSandbox,
) -> None:
    """The cosmetic name replaces the editor's, which is the point -- but the
    editor's is the only thing tying this row to what the Map Editor shows."""
    push_client_snapshot(
        panel_client,
        entities=[panel_entry(entity_id="object (gate) (1)", name="North gate")],
    )

    row = panel_client.pushed_panel_state()["entities"][0]

    assert row["name"] == "North gate"
    assert row["givenName"] == "North gate"
    assert row["originalName"] == "object (gate) (1)"


def test_a_row_nobody_named_has_no_earlier_name_to_show(
    panel_client: MtaSandbox,
) -> None:
    """Saying "originally gate-17" under a row headed the same is noise."""
    push_client_snapshot(panel_client, entities=[panel_entry(name="")])

    row = panel_client.pushed_panel_state()["entities"][0]

    assert row["givenName"] == ""
    assert row["originalName"] is False


def test_a_renamed_marker_still_says_what_the_editor_called_it(
    panel_client: MtaSandbox,
) -> None:
    """A marker had no default name to keep, so renaming one used to lose the
    only thread back to the editor's list."""
    entry = panel_entry(entity_id="marker (corona) (1)", name="Chapter three")
    entry["mapEntity"]["type"] = "marker"
    entry["mapEntity"]["model"] = False
    push_client_snapshot(panel_client, entities=[entry])

    row = panel_client.pushed_panel_state()["entities"][0]

    assert row["name"] == "Chapter three"
    assert row["originalName"] == "marker (corona) (1)"


def test_the_filter_matches_the_name_a_row_had_before_it_was_renamed(
    panel_client: MtaSandbox,
) -> None:
    """Naming a thing must not make it unfindable by what the Map Editor still
    calls it."""
    push_client_snapshot(
        panel_client,
        entities=[
            panel_entry(entity_id="object (gate) (17)", name="North gate"),
            panel_entry(entity_id="object (gate) (18)", name="South gate"),
        ],
    )

    panel_action(panel_client, "filter", {"text": "object (gate)"})
    assert len(panel_client.pushed_panel_state()["entities"]) == 2

    panel_action(panel_client, "filter", {"text": "North"})
    kept = panel_client.pushed_panel_state()["entities"]
    assert [row["entityId"] for row in kept] == ["object (gate) (17)"]


# --- pointing the camera is the player's answer -------------------------------


def test_the_page_is_told_to_point_the_camera_at_what_it_selects(
    panel_client: MtaSandbox,
) -> None:
    push_client_snapshot(panel_client, entities=[panel_entry()])

    assert panel_client.pushed_panel_state()["focusOnSelect"] is True


def test_the_client_setting_is_what_turns_that_off(
    panel_client: MtaSandbox,
) -> None:
    """Arrowing through fifty rows with the camera flying to each is not a way
    to read a list, so the player can say no -- on their own machine, because
    it is their own camera."""
    panel_client.eval(
        """
        function()
            ANKIGTA.ClientSettings = {
                get = function(key)
                    if key == "focusOnSelect" then return false end
                    return nil
                end,
            }
        end
        """
    )()
    push_client_snapshot(panel_client, entities=[panel_entry()])

    assert panel_client.pushed_panel_state()["focusOnSelect"] is False


# --- a relink moves what the entity said about its own zone -------------------


def relink(server: MtaSandbox, *, source: str, target: str) -> Any:
    """One value back, so a refusal cannot read as a success.

    `Store.relinkEntity` answers `false, reason`, and a two-value return
    arrives here as a tuple -- which is truthy however it went.
    """
    return server.eval(
        """
        function(sourceId, targetId)
            local ok, reason = ANKIGTA.Store.relinkEntity({
                sourceMapId = "current-map-id",
                sourceEntityId = sourceId,
                targetMapId = "current-map-id",
                targetEntityId = targetId,
            })
            if not ok then
                return tostring(reason)
            end
            return true
        end
        """
    )(source, target)


def override_of(server: MtaSandbox, entity_id: str) -> Any:
    row = server.connection.raw.execute(
        "SELECT radius_override FROM map_entity_metadata WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()
    return None if row is None else row[0]


def seed_pair(server: MtaSandbox) -> Any:
    for entity_id in ("gate-17", "gate-18"):
        seed_entity(
            server,
            map_id="current-map-id",
            resource_name="current-map",
            entity_id=entity_id,
        )
    server.connection.raw.execute(
        "INSERT INTO spatial_links (map_id, entity_id, collection_uuid, card_id,"
        " state, verified_map_sha256) VALUES (?, ?, ?, ?, 'active', ?)",
        ("current-map-id", "gate-17", "collection-a", 42, "a" * 64),
    )
    server.connection.raw.commit()
    return server.add_study_player()


def make_source_missing(server: MtaSandbox) -> None:
    """Relink exists for an entity whose Runtime Instance is gone, so the
    source has to actually be in that state for the call to do anything."""
    server.connection.raw.execute(
        "UPDATE map_entity_metadata SET presence_state = 'entity_missing'"
        " WHERE entity_id = 'gate-17'"
    )
    server.connection.raw.commit()


def test_a_relink_carries_a_radius_that_was_chosen(server: MtaSandbox) -> None:
    """Relink moves the entity's metadata, and a radius of its own is part of
    that. Dropping it would put the entity back on the global without anyone
    saying so."""
    player = seed_pair(server)
    write_metadata(server, player, {"radius": 7.5})
    assert override_of(server, "gate-17") == 7.5
    make_source_missing(server)

    assert relink(server, source="gate-17", target="gate-18") is True

    assert override_of(server, "gate-18") == 7.5


def test_a_relink_carries_the_absence_of_one(server: MtaSandbox) -> None:
    """And the other way: an entity that followed the global must not arrive at
    its new home pinned to a number nobody chose.

    The target here already has a radius of its own, so a relink that writes
    nothing would leave that number in force under the source's identity.
    """
    player = seed_pair(server)
    server.trigger(
        "ankigta:updateEntityMetadata",
        server.lua.globals().resourceRoot,
        "current-map-id",
        "gate-18",
        server.lua.table_from({"radius": 12}),
        client=player,
    )
    write_metadata(server, player, {"name": "North gate"})
    assert override_of(server, "gate-17") is None
    make_source_missing(server)

    assert relink(server, source="gate-17", target="gate-18") is True

    assert override_of(server, "gate-18") is None


def test_relinking_an_entity_commits_at_all(server: MtaSandbox) -> None:
    """It did not, on the trunk this branch came from.

    `Store.relinkEntity` handed `historyTransaction` a raw Lua table where every
    other caller hands it `historyTarget(...)`. `historySteps` binds that value
    straight into `change_history.target`, so the bind failed, the transaction
    rolled back and `Relink entity` answered `relink_transaction_failed` every
    single time. The two tests that mention relinking read the function's
    *source text* for the word `historyTransaction`, which is exactly the kind
    of test `docs/agents/lua-testing.md` says proves nothing about behaviour.
    """
    player = seed_pair(server)
    write_metadata(server, player, {"name": "North gate"})
    make_source_missing(server)

    assert relink(server, source="gate-17", target="gate-18") is True

    moved = server.connection.raw.execute(
        "SELECT entity_id FROM spatial_links WHERE state = 'active'"
    ).fetchall()
    assert moved == [("gate-18",)]
    # And it is one entry in Change History, so one Undo puts it back.
    recorded = server.connection.raw.execute(
        "SELECT operation, target FROM change_history ORDER BY history_id DESC"
        " LIMIT 1"
    ).fetchone()
    assert recorded[0] == "relink_entity"
    # `toJSON` serialises its argument *list*, so one table comes back wrapped.
    assert json.loads(recorded[1]) == [
        {"mapId": "current-map-id", "entityId": "gate-17"}
    ]
