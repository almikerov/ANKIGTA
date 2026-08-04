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
        sandbox.eval('function() ANKIGTA.Locale.setLanguage("en") end')()
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
            "showRadius": False,
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
    representation["__edf_representation"] = True
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
        "SELECT name, radius FROM map_entity_metadata WHERE entity_id = ?",
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


def test_a_zone_that_asks_to_be_shown_is_drawn_at_its_own_radius(
    panel_client: MtaSandbox,
) -> None:
    """`showRadius` had no drawing behind it at all.

    It only told the Next Card Indicator to pulse its own column where a zone
    happened to coincide -- so a zone appeared for the one card the scheduler
    had chosen next, in one indicator mode, and never otherwise. Turning the
    setting on therefore did nothing visible, which is what was reported.
    """
    quiet = panel_entry()
    shown = panel_entry(entity_id="gate-18")
    shown["metadata"]["showRadius"] = True
    shown["metadata"]["radius"] = 7.5
    push_client_snapshot(panel_client, entities=[quiet, shown])

    panel_client.trigger("onClientRender")
    ring = panel_client.drawn_lines_3d

    assert ring, "the zone was not drawn"
    # A ring around the entity, at the radius the entity carries.
    x, y = 10.25, -20.5
    distances = {
        round(((p["startX"] - x) ** 2 + (p["startY"] - y) ** 2) ** 0.5, 3)
        for p in ring
    }
    assert distances == {7.5}
    # One ring, not two: the row that did not ask for one contributed nothing.
    assert len(ring) == 24
    assert {segment["width"] for segment in ring} == {2.0}


def test_no_zone_is_drawn_while_the_panel_is_shut(
    panel_client: MtaSandbox,
) -> None:
    """It is the panel's snapshot, and costs nothing when F7 is closed."""
    shown = panel_entry()
    shown["metadata"]["showRadius"] = True
    push_client_snapshot(panel_client, entities=[shown])
    panel_client.eval("function() togglePanel() end")()
    panel_client.drawn_lines_3d.clear()

    panel_client.trigger("onClientRender")

    assert panel_client.drawn_lines_3d == []


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


def test_an_unnamed_row_uses_words_instead_of_its_identifier(
    panel_client: MtaSandbox,
) -> None:
    entry = panel_entry(name="")
    entry["mapEntity"]["model"] = False
    push_client_snapshot(panel_client, entities=[entry])

    row = panel_client.pushed_panel_state()["entities"][0]

    assert row["name"] == "Unnamed Map Entity"
    assert row["entityId"] not in row["name"]


def test_a_ped_is_named_by_its_skin_and_never_asked_about_as_an_object(
    panel_client: MtaSandbox,
) -> None:
    """`engineGetModelNameFromID` reads `CModelNames`, which holds objects.

    Asked about a ped skin it answers `false` and logs `Expected valid model
    ID` -- a warning per ped per snapshot, which both left every ped reading as
    "Unnamed Map Entity" and buried anything else worth reading in the client
    log. MTA has no name for a ped skin at all, so the skin is the name.
    """
    entry = panel_entry(name="")
    entry["mapEntity"]["type"] = "ped"
    entry["mapEntity"]["model"] = 7
    push_client_snapshot(panel_client, entities=[entry])

    row = panel_client.pushed_panel_state()["entities"][0]

    assert row["name"] == "Ped skin 7"
    assert panel_client.script_warnings == []


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
