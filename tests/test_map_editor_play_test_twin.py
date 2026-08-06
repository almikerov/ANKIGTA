"""Panel rebuild 09 — linking while the editor is play-testing.

The world these tests build is the one the owner's running server holds while
Test is pressed, measured there: every authored element exists **twice** — the
editor's own copy under `editor_main` in its working dimension, and the
play-test's copy under `editor_test` in dimension 0, which is where the player
is standing and so is the copy they are pointing at. Both were written out of
one document, so both answer to the same `id`.

ANKIGTA used to read the second one as a different entity, and refused to link
it: `editor_play_test_map`. It is not a different entity. It is the same
entity seen from inside the test, and the copy that outlives the test is the
editor's.
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


def manifest_scripts(*kinds: str) -> list[str]:
    manifest = ElementTree.parse(REPO_ROOT / "mta" / "ankigta" / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


@contextmanager
def build_server(database_path: Path) -> Iterator[MtaSandbox]:
    """A server side started the way `meta.xml` starts it.

    A factory as well as a fixture, because one of these tests has to compare
    what two servers stored: the same object linked inside a play-test and
    outside one is the same Map Entity, and nothing weaker than two rows put
    side by side says so.
    """
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
    map_name: str = "editor_dump",
    map_identity: str | None = None,
    working_dimension: int = 200,
) -> Any:
    """The stock editor holding one map, and that map's files.

    `editor_dump` is the editor's autosave, and is the map's name until
    somebody presses Save As — which is the state the owner's server is in.
    So is `map_identity = None`: the map on it carries no ANKIGTA identity
    yet, because nothing on it has been linked. A test that needs the editor
    to be holding a *particular* map says which.
    """
    editor_root = sandbox.add_resource("editor_main")
    sandbox.editor_map_name = map_name
    sandbox.editor_working_dimension = working_dimension
    sandbox.write_file(
        f":{map_name}/meta.xml", f'<meta><map src="{map_name}.map" /></meta>'
    )
    document = ["<map>"]
    if map_identity is not None:
        document.append(f'  <ankigta_map_identity ankigtaMapId="{map_identity}" />')
        identity = sandbox.add_world_element(
            "ankigta_map_identity",
            map_id="ankigta_map_identity (1)",
            dimension=working_dimension,
        )
        identity["__parent"] = editor_root
        identity["ankigtaMapId"] = map_identity
    document.append("</map>")
    sandbox.write_file(
        f":{map_name}/{map_name}.map", "\n".join(document) + "\n"
    )
    return editor_root


def editor_element(
    sandbox: MtaSandbox,
    editor_root: Any,
    *,
    entity_id: str,
    kind: str = "object",
    x: float = 0.0,
) -> Any:
    """One element the editor is holding, in its working dimension."""
    element = sandbox.add_world_element(
        kind,
        map_id=entity_id,
        dimension=int(sandbox.editor_working_dimension or 0),
        x=x,
    )
    element["__parent"] = editor_root
    return element


def study_player(sandbox: MtaSandbox, *, dimension: int) -> Any:
    player = sandbox.add_study_player()
    player["x"], player["y"], player["z"] = 0, 0, 0
    player["dimension"] = dimension
    player["interior"] = 0
    return player


def adopt(sandbox: MtaSandbox, player: Any, name: str) -> None:
    """Link, as the panel's button reaches the server: a name and a card."""
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


def refusal(sandbox: MtaSandbox) -> str | None:
    told = notices(sandbox)
    return str(told[-1].args[1]) if told else None


def stored_rows(sandbox: MtaSandbox) -> list[tuple[Any, ...]]:
    connection: sqlite3.Connection = sandbox.connection.raw
    return connection.execute(
        "SELECT maps.map_id, maps.resource_name, maps.map_name,"
        " map_entities.entity_id, map_entities.entity_type,"
        " map_entities.authored_x, map_entities.dimension"
        " FROM map_entities JOIN maps ON maps.map_id = map_entities.map_id"
        " ORDER BY map_entities.entity_id"
    ).fetchall()


def owning_resource(sandbox: MtaSandbox, element: Any) -> str | None:
    return sandbox.eval(
        "function(element) return ANKIGTA.World.owningResource(element) end"
    )(element)


# --- what the stubs have to know ---------------------------------------------


def test_a_play_test_duplicates_every_element_into_another_world(
    server: MtaSandbox,
) -> None:
    """The measurement this ticket started from, as a fixture.

    Without this the behaviour under test cannot be reached at all: one copy
    of each element is the world ANKIGTA already handled, and a fix proven
    against it would pass in tests and fail in the game.
    """
    editor_root = editor_with_map_open(server)
    editor_element(server, editor_root, entity_id="object (crate) (1)", x=42)
    editor_element(
        server, editor_root, entity_id="vehicle (Sentinel) (1)", kind="vehicle"
    )

    server.start_play_test()

    seen = server.eval(
        """
        function()
            local out = {}
            for _, kind in ipairs({"object", "vehicle"}) do
                for _, element in ipairs(getElementsByType(kind)) do
                    out[#out + 1] = getElementID(element)
                        .. "|" .. tostring(ANKIGTA.World.owningResource(element))
                        .. "|" .. tostring(getElementDimension(element))
                end
            end
            table.sort(out)
            return table.concat(out, "\\n")
        end
        """
    )()

    assert seen.split("\n") == [
        "object (crate) (1)|editor_main|200",
        "object (crate) (1)|editor_test|0",
        "vehicle (Sentinel) (1)|editor_main|200",
        "vehicle (Sentinel) (1)|editor_test|0",
    ]


def test_the_play_test_copy_carries_what_the_document_carries(
    server: MtaSandbox,
) -> None:
    """Test is the ordinary save with `test = true`, and a save writes every
    element data key but the ones prefixed `me:` or `edf:`
    (`createElementAttributesForSaving`). So an ANKIGTA stamp reaches the copy
    and the editor's own `me:ID` does not."""
    editor_root = editor_with_map_open(server)
    element = editor_element(server, editor_root, entity_id="object (crate) (1)")
    element["ankigtaEntityId"] = "object (crate) (1)"
    element["me:ID"] = "editor invented this"
    server.add_edf_representation(element)

    server.start_play_test()

    copies = server.eval(
        """
        function()
            local out = {}
            for _, element in ipairs(getElementsByType("object")) do
                if ANKIGTA.World.owningResource(element) == "editor_test" then
                    out[#out + 1] = tostring(
                        getElementData(element, "ankigtaEntityId")
                    ) .. "|" .. tostring(
                        getElementData(element, "me:ID") or "unwritten"
                    ) .. "|" .. tostring(
                        ANKIGTA.World.isEditorRepresentation(element)
                    )
                end
            end
            return table.concat(out, "\\n")
        end
        """
    )()

    # One line, not two: EDF's drawing of an element is not written out either.
    assert copies == "object (crate) (1)|unwritten|false"


# --- an object pointed at during a play-test is linkable ---------------------


def test_an_object_is_adopted_while_the_editor_is_play_testing(
    server: MtaSandbox,
) -> None:
    editor_root = editor_with_map_open(server)
    editor_element(server, editor_root, entity_id="object (crate) (1)", x=42)
    server.start_play_test()
    player = study_player(server, dimension=0)

    adopt(server, player, "object (crate) (1)")

    assert refusal(server) is None, refusal(server)
    assert stored_rows(server) == [
        (
            "editor_dump",
            "editor_dump",
            "editor_dump.map",
            "object (crate) (1)",
            "object",
            42.0,
            200,
        )
    ]


def test_it_is_recorded_against_the_map_that_owns_it(
    server: MtaSandbox,
) -> None:
    """`editor_test` is rewritten from whatever map is open on the next Test
    press, so a row stored against it is a link to something that stops
    existing. The map that owns the entity is the one the editor has open."""
    editor_root = editor_with_map_open(server)
    editor_element(server, editor_root, entity_id="object (crate) (1)")
    server.start_play_test()
    player = study_player(server, dimension=0)

    adopt(server, player, "object (crate) (1)")

    rows = stored_rows(server)
    assert [row[0] for row in rows] == ["editor_dump"]
    assert [row[1] for row in rows] == ["editor_dump"]
    # And the document is written down as a document, so every later reader
    # can open it.
    assert [row[2] for row in rows] == ["editor_dump.map"]


def test_the_card_is_hung_on_the_copy_that_outlives_the_test(
    server: MtaSandbox,
) -> None:
    """The identity has to be written where the editor will save it.

    Written onto the play-test copy it is never saved, so the read-back never
    confirms and the Spatial Link stays Pending Map Save for ever — and the
    element it was written on is destroyed when the test ends.
    """
    editor_root = editor_with_map_open(server)
    working = editor_element(
        server, editor_root, entity_id="object (crate) (1)"
    )
    server.start_play_test()
    player = study_player(server, dimension=0)

    adopt(server, player, "object (crate) (1)")

    assert refusal(server) is None, refusal(server)
    assert working["ankigtaEntityId"] == "object (crate) (1)"
    stamped = server.eval(
        """
        function()
            local out = {}
            for _, element in ipairs(getElementsByType("object")) do
                if getElementData(element, "ankigtaEntityId") then
                    out[#out + 1] = tostring(
                        ANKIGTA.World.owningResource(element)
                    )
                end
            end
            table.sort(out)
            return table.concat(out, ",")
        end
        """
    )()
    # The copy the player pointed at is stamped too, so a second Link on it
    # during the same test is recognised rather than adopted again -- but the
    # editor's own copy is the one that had to be.
    assert "editor_main" in stamped.split(",")


def test_the_same_object_is_one_map_entity_inside_and_outside_a_play_test(
    tmp_path: Path,
) -> None:
    """Two servers, one object, one row shape.

    If the two disagree then linking an object depends on whether Test was
    pressed, which is the whole defect restated.
    """
    written = []
    for playing in (False, True):
        with build_server(tmp_path / f"play-test-{playing}.sqlite") as sandbox:
            editor_root = editor_with_map_open(sandbox)
            editor_element(
                sandbox, editor_root, entity_id="object (crate) (1)", x=42
            )
            if playing:
                sandbox.start_play_test()
            player = study_player(
                sandbox, dimension=0 if playing else 200
            )

            adopt(sandbox, player, "object (crate) (1)")

            assert refusal(sandbox) is None, refusal(sandbox)
            written.append(stored_rows(sandbox))

    assert written[0] == written[1]


def test_linking_both_copies_does_not_make_two_rows(server: MtaSandbox) -> None:
    """The player links what they are looking at during the test, stops it,
    and links the same object again in the editor. One object, one row."""
    editor_root = editor_with_map_open(server)
    editor_element(server, editor_root, entity_id="object (crate) (1)")
    server.start_play_test()
    inside = study_player(server, dimension=0)

    adopt(server, inside, "object (crate) (1)")
    assert refusal(server) is None, refusal(server)

    outside = study_player(server, dimension=200)
    adopt(server, outside, "object (crate) (1)")

    assert len(stored_rows(server)) == 1
    # Recognised as the entity it already is, rather than taken in twice.
    assert refusal(server) == "entity_already_adopted"


# --- and refused where there is nothing else ---------------------------------


def test_a_play_test_running_without_the_editor_is_refused(
    server: MtaSandbox,
) -> None:
    """No editor, so nothing is holding the map this test was built from."""
    play_test_root = server.add_resource("editor_test", resource_type="map")
    element = server.add_world_element("object", map_id="object (bin) (1)")
    element["__parent"] = play_test_root
    player = study_player(server, dimension=0)

    adopt(server, player, "object (bin) (1)")

    assert stored_rows(server) == []
    assert refusal(server) == "play_test_without_open_map"


def test_a_play_test_of_another_map_is_refused(server: MtaSandbox) -> None:
    """The identity the test carries is one no working copy answers to.

    The editor was holding one map when Test was pressed and is holding
    another now, so the object standing in front of the player has no copy
    that outlives the test.
    """
    first = editor_with_map_open(server, map_identity="map-being-tested")
    editor_element(server, first, entity_id="object (crate) (1)")
    server.start_play_test()
    # The editor opens something else. Its elements and its identity go with
    # it; the test keeps running against the map it was built from.
    for element in list(server.world_elements):
        if owning_resource(server, element) == "editor_main":
            server.eval("function(e) destroyElement(e) end")(element)
    second = editor_with_map_open(
        server, map_name="otherMap", map_identity="another-map"
    )
    editor_element(server, second, entity_id="object (crate) (1)")
    player = study_player(server, dimension=0)

    adopt(server, player, "object (crate) (1)")

    assert stored_rows(server) == []
    assert refusal(server) == "play_test_of_another_map"


def test_a_play_test_copy_the_editor_no_longer_holds_is_refused(
    server: MtaSandbox,
) -> None:
    """Deleted in the editor while the test was running.

    The editor parks a deleted element in `workingDimension + 1` rather than
    destroying it, and a parked element is not something to link a card to.
    """
    editor_root = editor_with_map_open(server)
    working = editor_element(
        server, editor_root, entity_id="object (crate) (1)"
    )
    server.start_play_test()
    working["dimension"] = int(server.editor_working_dimension or 0) + 1
    player = study_player(server, dimension=0)

    adopt(server, player, "object (crate) (1)")

    assert stored_rows(server) == []
    assert refusal(server) == "play_test_copy_has_no_original"


# --- and says so in words a player can read ----------------------------------


@pytest.fixture
def panel_client() -> Iterator[MtaSandbox]:
    """The side that draws, which is the side that words a refusal."""
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


def tell(sandbox: MtaSandbox, key: str, reason: str) -> None:
    sandbox.eval(
        """
        function(key, reason)
            triggerEvent(
                "ankigta:pendingMapSaveNotice", resourceRoot, key, reason
            )
        end
        """
    )(key, reason)


PLAY_TEST_REFUSALS = (
    "play_test_without_open_map",
    "play_test_of_another_map",
    "play_test_copy_has_no_original",
)


@pytest.mark.parametrize("reason", PLAY_TEST_REFUSALS)
def test_a_play_test_refusal_reads_as_a_sentence(
    panel_client: MtaSandbox, reason: str
) -> None:
    tell(panel_client, "notice.adoptFailed", reason)

    said = panel_client.chat[-1]
    assert reason not in said, said
    assert said.endswith("."), said
    # Long enough to be an explanation rather than a relabelled token.
    assert len(said.split(" ")) >= 8, said


def test_the_two_play_test_refusals_do_not_say_the_same_thing(
    panel_client: MtaSandbox,
) -> None:
    """Which of the situations it is, not merely that it is one of them."""
    said = []
    for reason in PLAY_TEST_REFUSALS:
        tell(panel_client, "notice.adoptFailed", reason)
        said.append(panel_client.chat[-1])

    assert len(set(said)) == len(PLAY_TEST_REFUSALS)


def test_no_refusal_the_panel_shows_is_a_bare_token(
    panel_client: MtaSandbox,
) -> None:
    """Both surfaces, because a notice is drawn twice: in the chat box, and
    inside the panel page, which takes `detail` as it is given."""
    tell(panel_client, "notice.entityUpdateFailed", "play_test_of_another_map")

    detail = panel_client.eval(
        "function() return notice and notice.detail or false end"
    )()
    assert "play_test_of_another_map" not in str(detail), detail
    assert "play_test_of_another_map" not in panel_client.chat[-1]


def test_every_refusal_these_paths_produce_has_a_sentence(
    panel_client: MtaSandbox,
) -> None:
    """The vocabulary of the paths this ticket owns — adopting something the
    player pointed at, and linking a card to it — worded rather than shown."""
    sentence_for = panel_client.eval(
        "function(code) return ANKIGTA.Locale.reason(code) end"
    )
    for code in (
        "play_test_without_open_map",
        "play_test_of_another_map",
        "play_test_copy_has_no_original",
        "play_test_original_not_unique",
        "entity_already_adopted",
        "entity_has_no_durable_id",
        "entity_no_longer_in_the_world",
        "entity_not_an_element",
        "entity_not_managed",
        "entity_not_streamed",
        "entity_already_linked",
        "entity_runtime_not_found",
        "entity_runtime_not_unique",
        "target_type_not_supported",
        "map_entity_not_loaded",
        "map_entity_ambiguous",
        "map_identity_not_unique",
        "invalid_anki_card_identity",
        "saved_map_not_readable",
        "no_loaded_map",
        "ambiguous_map_file",
        "authentication_required",
        "forbidden",
        "storage_unavailable",
    ):
        said = sentence_for(code)
        assert said != code, f"{code} is still a bare token"
        assert str(said).endswith("."), f"{code}: {said}"


def test_an_unworded_code_is_reported_rather_than_silently_shown(
    panel_client: MtaSandbox,
) -> None:
    """A gap is found by the debug log, the way a missing string is."""
    before = len(panel_client.recorder.debug)

    panel_client.eval(
        'function() return ANKIGTA.Locale.reason("a_code_nobody_worded") end'
    )()

    raised = panel_client.recorder.debug_messages()[before:]
    assert any("a_code_nobody_worded" in line for line in raised), raised
