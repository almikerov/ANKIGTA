"""Panel rebuild 12 — the row and the edit disagree about which world.

The world these tests build is the one the owner's running server held on
2026-08-06, measured there: **one authored object standing in the world three
times**. The editor holds the map it has open in its working dimension, a Test
press left `editor_test` holding a copy of it in the ordinary world, and the
map saved under its own name runs there too. All three answer to one
`getElementID`, because one document produced them.

Both filters that decide whether an element belongs to the map in front of the
player named a single one of those copies, so the answer changed with where the
player happened to be standing. The panel offered a row from one world and
refused to edit it from another — `entity_element_not_found`, with nothing
stored and nothing written.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox


REPO_ROOT = Path(__file__).resolve().parents[1]
UUID = "11111111-1111-4111-8111-111111111111"

#: The object the owner could not edit, named the way the stock editor names it.
RUBBISH = "object (CJ_SKIP_Rubbish) (1)"
#: The name they saved the map under.
SAVED_MAP = "dum"
#: The editor's own world. Everything else stands in the ordinary one.
WORKING_DIMENSION = 200


def manifest_scripts(*kinds: str) -> list[str]:
    manifest = ElementTree.parse(REPO_ROOT / "mta" / "ankigta" / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


@contextmanager
def build_server(database_path: Path) -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox(database_path=str(database_path))
    try:
        for script in manifest_scripts("shared", "server"):
            sandbox.load(script)
        sandbox.trigger("onResourceStart")
        yield sandbox
    finally:
        sandbox.close()


@pytest.fixture
def server(tmp_path: Path) -> Iterator[MtaSandbox]:
    with build_server(tmp_path / "ankigta.sqlite") as sandbox:
        yield sandbox


# --- the world the owner's server holds --------------------------------------


def editor_with_map_open(
    sandbox: MtaSandbox,
    *,
    map_name: str = SAVED_MAP,
    map_identity: str | None = None,
) -> Any:
    """The stock editor holding one map, and that map's files."""
    editor_root = sandbox.add_resource("editor_main")
    sandbox.editor_map_name = map_name
    sandbox.editor_working_dimension = WORKING_DIMENSION
    sandbox.write_file(
        f":{map_name}/meta.xml", f'<meta><map src="{map_name}.map" /></meta>'
    )
    document = ["<map>"]
    if map_identity is not None:
        document.append(f'  <ankigta_map_identity ankigtaMapId="{map_identity}" />')
        identity = sandbox.add_world_element(
            "ankigta_map_identity",
            map_id="ankigta_map_identity (1)",
            dimension=WORKING_DIMENSION,
        )
        identity["__parent"] = editor_root
        identity["ankigtaMapId"] = map_identity
    document.append("</map>")
    sandbox.write_file(f":{map_name}/{map_name}.map", "\n".join(document) + "\n")
    return editor_root


def editor_element(
    sandbox: MtaSandbox,
    editor_root: Any,
    *,
    entity_id: str = RUBBISH,
    kind: str = "object",
    x: float = 0.0,
) -> Any:
    """One element the editor is holding, in its working dimension."""
    element = sandbox.add_world_element(
        kind, map_id=entity_id, dimension=WORKING_DIMENSION, x=x
    )
    element["__parent"] = editor_root
    return element


def owners_world(
    sandbox: MtaSandbox,
    *,
    map_name: str = SAVED_MAP,
    saved_as: str | None = None,
    map_identity: str | None = None,
) -> Any:
    """One authored object, standing in the world three times.

    `saved_as` is the resource the map was saved into, which is the map's own
    name unless a test is making the point that the two are different strings.
    """
    editor_root = editor_with_map_open(
        sandbox, map_name=map_name, map_identity=map_identity
    )
    element = editor_element(sandbox, editor_root)
    sandbox.start_play_test()
    sandbox.start_saved_map(saved_as or map_name)
    return element


def study_player(sandbox: MtaSandbox, *, dimension: int) -> Any:
    player = sandbox.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0
    player["dimension"] = dimension
    player["interior"] = 0
    return player


# --- how the panel reaches the server ----------------------------------------


def open_panel(sandbox: MtaSandbox, player: Any) -> dict[str, Any]:
    sandbox.trigger(
        "ankigta:requestF7", sandbox.lua.globals().resourceRoot, client=player
    )
    return sandbox.to_python(sandbox.recorder.client_events[-1].args[0])


def rows_for(snapshot: dict[str, Any], entity_id: str) -> list[dict[str, Any]]:
    entities = snapshot["entities"]
    listed = entities.values() if isinstance(entities, dict) else entities
    return [
        entry for entry in listed if entry["mapEntity"]["entityId"] == entity_id
    ]


def edit_name(
    sandbox: MtaSandbox, player: Any, map_id: str, entity_id: str, name: str
) -> None:
    """Type a name into the entity pane, as the panel sends it."""
    sandbox.trigger(
        "ankigta:updateEntityMetadata",
        sandbox.lua.globals().resourceRoot,
        map_id,
        entity_id,
        sandbox.lua.table_from({"name": name}),
        client=player,
    )


def notices(sandbox: MtaSandbox) -> list[Any]:
    return [
        event
        for event in sandbox.recorder.client_events
        if event.name == "ankigta:pendingMapSaveNotice"
    ]


def refusal(sandbox: MtaSandbox) -> str | None:
    told = notices(sandbox)
    return str(told[-1].args[1]) if told else None


def stored_names(sandbox: MtaSandbox) -> list[tuple[Any, ...]]:
    connection: sqlite3.Connection = sandbox.connection.raw
    return connection.execute(
        "SELECT map_entities.map_id, map_entities.entity_id,"
        " map_entity_metadata.name"
        " FROM map_entities LEFT JOIN map_entity_metadata"
        " ON map_entity_metadata.map_id = map_entities.map_id"
        " AND map_entity_metadata.entity_id = map_entities.entity_id"
        " ORDER BY map_entities.entity_id"
    ).fetchall()


# --- what the stub has to know -----------------------------------------------


def test_one_authored_object_stands_in_the_world_three_times(
    server: MtaSandbox,
) -> None:
    """The measurement this ticket started from, as a fixture.

    Without the third copy the behaviour under test cannot be reached at all:
    two copies pass a filter that names one of them, and a fix proven against
    that world would pass in tests and fail in the game.
    """
    owners_world(server)

    seen = server.eval(
        """
        function()
            local out = {}
            for _, element in ipairs(getElementsByType("object")) do
                out[#out + 1] = getElementID(element)
                    .. "|" .. tostring(ANKIGTA.World.owningResource(element))
                    .. "|" .. tostring(getElementDimension(element))
            end
            table.sort(out)
            return table.concat(out, "\\n")
        end
        """
    )()

    assert seen.split("\n") == [
        f"{RUBBISH}|dum|0",
        f"{RUBBISH}|editor_main|200",
        f"{RUBBISH}|editor_test|0",
    ]


def test_the_saved_map_and_the_play_test_are_both_running_maps(
    server: MtaSandbox,
) -> None:
    """Two resources of type `map`, holding one map between them.

    Read as two maps the player could be standing in, they are a tie — and a
    tie is answered by not guessing, which left the map's own world with no
    current map at all.
    """
    owners_world(server)

    running = server.eval(
        """
        function()
            local out = {}
            for _, resource in ipairs(getResources()) do
                if getResourceState(resource) == "running"
                    and getResourceInfo(resource, "type") == "map"
                then
                    out[#out + 1] = getResourceName(resource)
                end
            end
            table.sort(out)
            return table.concat(out, ",")
        end
        """
    )()

    assert running == "dum,editor_test"


# --- a row the panel offered is editable, from either world ------------------


@pytest.mark.parametrize(
    "dimension", [WORKING_DIMENSION, 0], ids=["in-the-editor", "in-the-map"]
)
def test_an_offered_row_is_editable_without_moving_the_player(
    server: MtaSandbox, dimension: int
) -> None:
    """The whole defect, from the panel's side.

    The row the list offers carries the identity the edit is sent under, so
    asking for one and then editing it is the owner's own workflow. It was
    refused with `entity_element_not_found`, and nothing was stored.
    """
    owners_world(server)
    player = study_player(server, dimension=dimension)

    snapshot = open_panel(server, player)
    offered = rows_for(snapshot, RUBBISH)
    assert len(offered) == 1, offered
    row = offered[0]["mapEntity"]

    edit_name(server, player, row["mapId"], row["entityId"], "Skip")

    assert refusal(server) is None, refusal(server)
    assert stored_names(server) == [(SAVED_MAP, RUBBISH, "Skip")]


@pytest.mark.parametrize(
    "dimension", [WORKING_DIMENSION, 0], ids=["in-the-editor", "in-the-map"]
)
def test_the_map_in_front_of_the_player_is_the_map_either_way(
    server: MtaSandbox, dimension: int
) -> None:
    """Which copy they are standing in is not which map they are on."""
    owners_world(server)
    player = study_player(server, dimension=dimension)

    snapshot = open_panel(server, player)

    assert snapshot["currentMap"] is not False
    assert snapshot["currentMap"]["resourceName"] == SAVED_MAP


def test_the_row_is_offered_once_however_many_copies_carry_it(
    server: MtaSandbox,
) -> None:
    """Three copies of one authored object are one offer, not three."""
    owners_world(server)
    player = study_player(server, dimension=0)

    snapshot = open_panel(server, player)

    assert len(rows_for(snapshot, RUBBISH)) == 1
    assert snapshot["candidatesShown"] == 1
    assert snapshot["candidatesFound"] == 1


@pytest.mark.parametrize(
    "dimension", [WORKING_DIMENSION, 0], ids=["in-the-editor", "in-the-map"]
)
def test_the_row_describes_the_copy_the_edit_will_take_in(
    server: MtaSandbox, dimension: int
) -> None:
    """One offer either way — but of *which* copy.

    The copies share a position and not a dimension, and the row's dimension is
    what the map draws its blip in. Offered from whichever copy the walk met
    first, a row could describe the world the player is not in and then be
    taken in from the one they are.
    """
    owners_world(server)
    player = study_player(server, dimension=dimension)

    snapshot = open_panel(server, player)
    offered = rows_for(snapshot, RUBBISH)
    assert len(offered) == 1, offered
    assert offered[0]["mapEntity"]["authored"]["world"]["dimension"] == dimension

    edit_name(server, player, SAVED_MAP, RUBBISH, "Skip")

    assert refusal(server) is None, refusal(server)
    connection: sqlite3.Connection = server.connection.raw
    assert connection.execute(
        "SELECT dimension FROM map_entities"
    ).fetchall() == [(dimension,)]


def test_editing_it_from_one_world_and_then_the_other_is_one_map_entity(
    server: MtaSandbox,
) -> None:
    """The row survives the player walking out of the editor and back in."""
    owners_world(server)
    inside = study_player(server, dimension=WORKING_DIMENSION)
    outside = study_player(server, dimension=0)

    edit_name(server, inside, SAVED_MAP, RUBBISH, "Skip")
    edit_name(server, outside, SAVED_MAP, RUBBISH, "Rubbish skip")

    assert refusal(server) is None, refusal(server)
    assert stored_names(server) == [(SAVED_MAP, RUBBISH, "Rubbish skip")]


# --- resolved by map identity, not by the name of a copy ---------------------


def test_a_copy_carrying_the_maps_identity_is_the_map_whatever_it_is_called(
    server: MtaSandbox,
) -> None:
    """The editor's autosave is `editor_dump` until somebody presses Save As.

    Saved, the same document answers to a second name — and the only thing
    that says the two are one map is the ANKIGTA identity written into it. A
    filter matching on names cannot reach the saved copy at all.
    """
    owners_world(
        server, map_name="editor_dump", saved_as=SAVED_MAP, map_identity="map-1"
    )
    player = study_player(server, dimension=0)

    snapshot = open_panel(server, player)
    offered = rows_for(snapshot, RUBBISH)
    assert len(offered) == 1, offered

    edit_name(server, player, offered[0]["mapEntity"]["mapId"], RUBBISH, "Skip")

    assert refusal(server) is None, refusal(server)
    assert [row[2] for row in stored_names(server)] == ["Skip"]


def test_a_map_carrying_another_identity_is_another_map(
    server: MtaSandbox,
) -> None:
    """Widening the owner test is not accepting everything standing about.

    A second map running in the same world carries an identity of its own, and
    its objects are not offers on the map the player is looking at.
    """
    owners_world(server, map_identity="map-1")
    other_root = server.add_resource("other-map", resource_type="map")
    stranger = server.add_world_element(
        "object", map_id="object (crate) (1)", dimension=0, x=5
    )
    stranger["__parent"] = other_root
    identity = server.add_world_element(
        "ankigta_map_identity", map_id="ankigta_map_identity (2)", dimension=0
    )
    identity["__parent"] = other_root
    identity["ankigtaMapId"] = "map-2"
    player = study_player(server, dimension=WORKING_DIMENSION)

    snapshot = open_panel(server, player)

    assert rows_for(snapshot, "object (crate) (1)") == []
    assert len(rows_for(snapshot, RUBBISH)) == 1


# --- and what it must not break ----------------------------------------------


def test_an_edf_representation_is_still_never_an_entity(
    server: MtaSandbox,
) -> None:
    """Ticket 02 bought this filter with real breakage.

    EDF parents its drawing to the element it draws and stamps it `edf:rep`,
    and the drawing carries the identity the `.map` file gave the element. It
    is not a second copy of anything, and it is not a row.
    """
    element = owners_world(server)
    representation = server.add_edf_representation(element)
    player = study_player(server, dimension=WORKING_DIMENSION)

    snapshot = open_panel(server, player)
    assert len(rows_for(snapshot, RUBBISH)) == 1

    edit_name(server, player, SAVED_MAP, RUBBISH, "Skip")

    assert refusal(server) is None, refusal(server)
    assert stored_names(server) == [(SAVED_MAP, RUBBISH, "Skip")]
    # The representation was never the element the edit was recorded against.
    assert representation["ankigtaEntityId"] is None
    assert element["ankigtaEntityId"] == RUBBISH


def test_a_genuine_duplicate_is_still_refused_and_says_which(
    server: MtaSandbox,
) -> None:
    """Two authored objects answering to one name, both in the player's world.

    Neither is a copy of the other, so which of them is meant is a question
    only the player can answer — and writing to whichever the walk reached
    first is what the refusal exists to stop.
    """
    editor_root = editor_with_map_open(server)
    editor_element(server, editor_root)
    editor_element(server, editor_root, x=50)
    player = study_player(server, dimension=WORKING_DIMENSION)

    edit_name(server, player, SAVED_MAP, RUBBISH, "Skip")

    assert stored_names(server) == []
    told = refusal(server)
    assert told is not None
    assert told.startswith("entity_runtime_not_unique:"), told
    # Which thing, and how many of it -- the shape the link path refuses in and
    # the one the string table words.
    assert RUBBISH in told, told
    assert "2 copies" in told, told


def test_that_refusal_reaches_the_player_as_a_sentence(
    server: MtaSandbox,
) -> None:
    """A code with a subject after it is worded, not shown raw."""
    said = server.eval(
        "function(code) return ANKIGTA.Locale.reason(code) end"
    )(f"entity_runtime_not_unique: {RUBBISH} (2 copies)")

    assert "entity_runtime_not_unique" not in said, said
    assert RUBBISH in said, said


def test_the_play_tests_copy_is_not_a_duplicate_of_the_map_it_tests(
    server: MtaSandbox,
) -> None:
    """Both stand in the ordinary world, so the player's own world cannot tell
    them apart — and they are one entity, not two."""
    owners_world(server)
    player = study_player(server, dimension=0)

    edit_name(server, player, SAVED_MAP, RUBBISH, "Skip")

    assert refusal(server) is None, refusal(server)
    assert stored_names(server) == [(SAVED_MAP, RUBBISH, "Skip")]


def test_an_object_deleted_in_the_editor_is_still_not_offered(
    server: MtaSandbox,
) -> None:
    """Delete parks the element in `workingDimension + 1` rather than
    destroying it, and a parked element is not something to offer."""
    editor_root = editor_with_map_open(server)
    element = editor_element(server, editor_root)
    element["dimension"] = WORKING_DIMENSION + 1
    player = study_player(server, dimension=WORKING_DIMENSION)

    snapshot = open_panel(server, player)

    assert rows_for(snapshot, RUBBISH) == []


def test_the_parked_copy_is_never_the_one_an_edit_lands_on(
    server: MtaSandbox,
) -> None:
    """The saved map still holds the object until the player saves again, so
    there is still something to edit — and the copy in the bin is not it.

    The deleted dimension is read wherever the walk can meet an element the
    editor is holding, which is now every world the editor has a map open in.
    """
    editor_root = editor_with_map_open(server)
    parked = editor_element(server, editor_root)
    server.start_saved_map(SAVED_MAP)
    parked["dimension"] = WORKING_DIMENSION + 1
    player = study_player(server, dimension=WORKING_DIMENSION)

    edit_name(server, player, SAVED_MAP, RUBBISH, "Skip")

    assert refusal(server) is None, refusal(server)
    assert stored_names(server) == [(SAVED_MAP, RUBBISH, "Skip")]
    assert parked["ankigtaEntityId"] is None
