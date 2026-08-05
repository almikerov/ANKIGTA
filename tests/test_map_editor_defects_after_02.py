"""What the owner hit in the Map Editor after ticket 02 shipped.

The world these tests build is the one the live server actually held. The
editor has an **unsaved** map open, so `getCurrentMapName()` answers
`editor_dump` — the editor's autosave, which is that map's name until somebody
presses Save As. The map document carries the persistent ANKIGTA identity it
was given while it was being play-tested, `editor_test`. The stored rows are
keyed by that identity.

So one map answers to three different strings at once, and every defect here is
ANKIGTA picking the wrong one.
"""

from __future__ import annotations

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
    '  <ankigta_map_identity ankigtaMapId="editor_test" />\n'
    '  <object id="object (bin) (1)" ankigtaEntityId="object (bin) (1)" />\n'
    "</map>\n"
)


def owners_world(sandbox: MtaSandbox) -> Any:
    """The editor holding an unsaved map whose identity is not its name."""
    editor_root = sandbox.add_resource("editor_main")
    sandbox.editor_map_name = "editor_dump"
    sandbox.editor_working_dimension = 200
    sandbox.write_file(
        ":editor_dump/meta.xml", '<meta><map src="editor_dump.map" /></meta>'
    )
    sandbox.write_file(":editor_dump/editor_dump.map", MAP_DOCUMENT)
    identity = sandbox.add_world_element(
        "ankigta_map_identity", map_id="ankigta_map_identity (1)", dimension=200
    )
    identity["__parent"] = editor_root
    identity["ankigtaMapId"] = "editor_test"
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
    """One element the editor has open, with EDF's drawing of it beside it."""
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


def seed_owner_row(
    sandbox: MtaSandbox, entity_id: str = "object (bin) (1)"
) -> None:
    """A row adopted before the fix: `map_name` holds the RESOURCE name."""
    connection: sqlite3.Connection = sandbox.connection.raw
    connection.execute(
        "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
        " VALUES ('editor_test', 'editor_test', 'editor_test')"
    )
    connection.execute(
        "INSERT OR REPLACE INTO map_entities (map_id, entity_id, entity_type,"
        " model, authored_x, authored_y, authored_z, rotation_x, rotation_y,"
        " rotation_z, interior, dimension)"
        " VALUES ('editor_test', ?, 'object', 1337, 0, 0, 0, 0, 0, 0, 0, 200)",
        (entity_id,),
    )
    connection.commit()


def study_player(sandbox: MtaSandbox, *, dimension: int = 200) -> Any:
    player = sandbox.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0
    player["dimension"] = dimension
    player["interior"] = 0
    return player


def snapshot_of(sandbox: MtaSandbox, player: Any) -> dict[str, Any]:
    sandbox.trigger(
        "ankigta:requestF7", sandbox.lua.globals().resourceRoot, client=player
    )
    event = sandbox.recorder.client_events[-1]
    assert event.name == "ankigta:f7Snapshot"
    return sandbox.to_python(event.args[0])


def notices(sandbox: MtaSandbox) -> list[Any]:
    return [
        event
        for event in sandbox.recorder.client_events
        if event.name == "ankigta:pendingMapSaveNotice"
    ]


def adopt(sandbox: MtaSandbox, player: Any, name: str) -> None:
    sandbox.trigger(
        "ankigta:adoptEntity",
        sandbox.lua.globals().resourceRoot,
        name,
        sandbox.lua.table_from({"collectionUuid": UUID, "cardId": 42}),
        client=player,
    )


# --- "in the list I see TWO entries of that object" ---------------------------


def test_one_object_is_one_row_when_the_map_answers_to_three_names(
    server: MtaSandbox,
) -> None:
    """The map's identity is `editor_test`; its resource is `editor_dump`.

    Scoping the list by resource name put the stored row outside the map it is
    on, so the row was emitted as an orphan AND the element standing right
    there was offered as something to adopt.
    """
    editor_root = owners_world(server)
    seed_owner_row(server)
    editor_element(server, editor_root, entity_id="object (bin) (1)")
    player = study_player(server)

    entities = snapshot_of(server, player)["entities"]
    keys = [
        (entry["mapEntity"]["mapId"], entry["mapEntity"]["entityId"])
        for entry in entities
    ]

    assert keys.count(("editor_test", "object (bin) (1)")) == 1
    assert len(keys) == len(set(keys)), keys


# --- "Missing Entity, though the camera finds them" ---------------------------


def test_an_object_standing_on_the_open_map_is_not_reported_missing(
    server: MtaSandbox,
) -> None:
    """Two causes, both gone.

    `editor_dump` was declared throwaway, so its rows were marked missing
    without anything being read; and `map_name` held a resource name, so the
    presence read opened `:editor_dump/editor_dump`, which is not a file.
    """
    editor_root = owners_world(server)
    seed_owner_row(server)
    editor_element(server, editor_root, entity_id="object (bin) (1)")
    player = study_player(server)

    entities = snapshot_of(server, player)["entities"]
    row = next(
        entry for entry in entities
        if entry["mapEntity"]["entityId"] == "object (bin) (1)"
    )

    assert row["link"]["state"] != "Entity missing", row["link"]
    stored = server.connection.raw.execute(
        "SELECT presence_state FROM map_entity_metadata WHERE entity_id = ?",
        ("object (bin) (1)",),
    ).fetchone()
    assert stored in (None, ("identified",))


def test_the_map_locator_names_the_declared_document_not_the_resource(
    server: MtaSandbox,
) -> None:
    owners_world(server)

    resolved = server.eval(
        "function()"
        " return ANKIGTA.MapIdentity.currentMapLocator().virtualPath end"
    )()

    assert resolved == ":editor_dump/editor_dump.map"


# --- "Original / New copy buttons I do not understand" ------------------------


def test_no_copy_decision_is_offered_for_a_map_nobody_copied(
    server: MtaSandbox,
) -> None:
    """`maps.map_name` held `editor_test` while the document is
    `editor_dump.map`, and the copy check compared those two strings."""
    editor_root = owners_world(server)
    seed_owner_row(server)
    editor_element(server, editor_root, entity_id="object (bin) (1)")
    player = study_player(server)

    collision = server.eval(
        """
        function()
            local locator = ANKIGTA.MapIdentity.currentMapLocator()
            return ANKIGTA.MapIdentity.detectIdentityCollisions(
                "editor_test", "object (bin) (1)", locator
            )
        end
        """
    )()

    assert collision is False
    entities = snapshot_of(server, player)["entities"]
    assert [entry for entry in entities if entry.get("copyCollision")] == []


def test_one_entitys_collision_does_not_paint_every_row_of_its_map(
    server: MtaSandbox,
) -> None:
    """A map-wide flag was consulted before the per-row record.

    On a row that borrowed the flag both buttons answer
    `identity_collision_not_found`, so the player was offered a decision that
    could not be made.
    """
    connection: sqlite3.Connection = server.connection.raw
    connection.execute(
        "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
        " VALUES ('m1', 'm1', 'm1.map')"
    )
    for entity_id in ("touched", "untouched"):
        connection.execute(
            "INSERT OR REPLACE INTO map_entities (map_id, entity_id,"
            " entity_type, model, authored_x, authored_y, authored_z,"
            " rotation_x, rotation_y, rotation_z, interior, dimension)"
            " VALUES ('m1', ?, 'object', 1337, 0, 0, 0, 0, 0, 0, 0, 0)",
            (entity_id,),
        )
    connection.commit()

    server.eval(
        "function() return ANKIGTA.Store.markEntityIdentityCollision("
        '"m1", "touched", "copied_resource_or_rename_requires_decision") end'
    )()

    painted = server.eval(
        """
        function()
            local rows = ANKIGTA.Store.listMapEntities()
            local out = {}
            for _, row in ipairs(rows) do
                out[row.entity_id] =
                    ANKIGTA.Store.rowIsIdentityCollision(row) == true
            end
            return out
        end
        """
    )()

    assert server.to_python(painted) == {"touched": True, "untouched": False}


def test_a_stale_collision_is_re_checked_rather_than_believed(
    server: MtaSandbox,
) -> None:
    """The rows a broken predicate wrote must not outlive it.

    `recoverPersistedCollisions` runs on every start; believing what it finds
    kept the buttons on screen after the cause was fixed.
    """
    owners_world(server)
    seed_owner_row(server)
    server.eval(
        "function() return ANKIGTA.Store.markEntityIdentityCollision("
        '"editor_test", "object (bin) (1)",'
        ' "copied_resource_or_rename_requires_decision") end'
    )()

    server.eval(
        "function() return ANKIGTA.MapIdentity.recoverPersistedCollisions() end"
    )()

    assert server.connection.raw.execute(
        "SELECT COUNT(*) FROM identity_collisions"
    ).fetchone()[0] == 0


# --- "the objects still would not link: editor_scratch_resource" --------------


def test_a_link_can_be_made_on_the_unsaved_map_the_editor_has_open(
    server: MtaSandbox,
) -> None:
    """`editor_dump` is the editor's autosave of the map being edited.

    It is that map's name for as long as the map is unsaved, which is the
    editor's default state — so refusing it refused the normal case.
    """
    editor_root = owners_world(server)
    editor_element(
        server, editor_root, entity_id="object (crate) (1)", stamped=False, x=42
    )
    player = study_player(server)

    adopt(server, player, "object (crate) (1)")

    row = server.connection.raw.execute(
        "SELECT maps.map_name, map_entities.authored_x FROM maps"
        " JOIN map_entities ON map_entities.map_id = maps.map_id"
        " WHERE map_entities.entity_id = ?",
        ("object (crate) (1)",),
    ).fetchone()
    assert row is not None, [notice.args for notice in notices(server)]
    # The map's document is written down as a document, not as a resource, so
    # every later reader can open it.
    assert row[0] == "editor_dump.map"
    assert row[1] == 42


def test_the_play_test_copy_is_still_refused_and_says_so(
    server: MtaSandbox,
) -> None:
    """`editor_test` is rebuilt from whatever map is open on every Test."""
    play_test_root = server.add_resource("editor_test", resource_type="map")
    element = server.add_world_element("object", map_id="object (bin) (1)")
    element["__parent"] = play_test_root
    player = study_player(server, dimension=0)

    adopt(server, player, "object (bin) (1)")

    assert server.connection.raw.execute(
        "SELECT COUNT(*) FROM map_entities"
    ).fetchone()[0] == 0
    assert notices(server)[-1].args[1] == "editor_play_test_map"
