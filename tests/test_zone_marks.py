"""Panel usability 06 — seeing the world through the panel.

Three marks, three questions. The outline says *which* thing a row is, for as
long as F7 is open. `Draw radius` draws the selected row's Activation Zone and
outlives the panel closing. `Show corona` hangs a corona on the entity itself,
sized by its zone and coloured by the entity or, where it says nothing, by
Settings.

The decision is a pure function and is tested as one; what is drawn is read
back off the sandbox, because a line drawn into the world has no control to
read it off.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


DEFAULT_COLOUR = "#3cc8ff"


@pytest.fixture
def marks() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.load("shared/settings.lua")
    sandbox.load("client/zone_marks.lua")
    try:
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


def mark(
    entity_id: str = "e1",
    *,
    map_id: str = "m1",
    radius: float = 3.0,
    show_corona: bool = False,
    colour: Any = False,
    opacity: Any = False,
    present: bool = True,
) -> dict[str, Any]:
    return {
        "mapId": map_id,
        "entityId": entity_id,
        "radius": radius,
        "showCorona": show_corona,
        "coronaColour": colour,
        "coronaOpacity": opacity,
        "present": present,
    }


def view(
    *,
    panel_open: bool = False,
    selected: str | None = None,
    map_id: str = "m1",
    draw_radius: bool = False,
    colour: str = DEFAULT_COLOUR,
    opacity: float = 0.5,
) -> dict[str, Any]:
    return {
        "panelOpen": panel_open,
        "selectedMapId": map_id if selected else False,
        "selectedEntityId": selected if selected else False,
        "drawRadius": draw_radius,
        "coronaColour": colour,
        "coronaOpacity": opacity,
    }


def plan(
    sandbox: MtaSandbox, current: dict[str, Any], entries: list[dict[str, Any]]
) -> Any:
    return sandbox.eval(
        "function(v, m) return ANKIGTA.ZoneMarks.plan(v, m) end"
    )(to_lua(sandbox, current), to_lua(sandbox, entries))


# --- the outline -------------------------------------------------------------


def test_the_selected_row_is_outlined_where_it_stands(marks: MtaSandbox) -> None:
    result = plan(
        marks,
        view(panel_open=True, selected="e1"),
        [mark("e1"), mark("e2")],
    )

    assert result.outline.entityId == "e1"


def test_selecting_another_row_moves_the_outline(marks: MtaSandbox) -> None:
    result = plan(
        marks,
        view(panel_open=True, selected="e2"),
        [mark("e1"), mark("e2")],
    )

    assert result.outline.entityId == "e2"


def test_closing_f7_takes_the_outline_away(marks: MtaSandbox) -> None:
    """The outline answers "which row is this?", which nobody is asking with
    the list shut. `Draw radius` is the mark that outlives a close."""
    result = plan(marks, view(panel_open=False, selected="e1"), [mark("e1")])

    assert result.outline is False


def test_a_row_with_no_runtime_instance_is_not_outlined(marks: MtaSandbox) -> None:
    """There is nothing standing in the world to draw a box around. The Map
    Entity record and its Spatial Link are untouched either way."""
    result = plan(
        marks,
        view(panel_open=True, selected="e1"),
        [mark("e1", present=False)],
    )

    assert result.outline is False


def test_nothing_is_outlined_when_nothing_is_selected(marks: MtaSandbox) -> None:
    result = plan(marks, view(panel_open=True), [mark("e1"), mark("e2")])

    assert result.outline is False


# --- Draw radius -------------------------------------------------------------


def test_draw_radius_draws_the_selected_rows_zone(marks: MtaSandbox) -> None:
    result = plan(
        marks,
        view(panel_open=True, selected="e1", draw_radius=True),
        [mark("e1", radius=7.5), mark("e2", radius=2)],
    )

    assert result.zone.entityId == "e1"
    assert result.zone.radius == 7.5


def test_the_zone_survives_the_panel_closing(marks: MtaSandbox) -> None:
    """A client setting rather than a mode: the player sizes a zone, closes F7
    and walks the edge of it."""
    result = plan(
        marks,
        view(panel_open=False, selected="e1", draw_radius=True),
        [mark("e1")],
    )

    assert result.zone.entityId == "e1"
    assert result.outline is False


def test_no_zone_is_drawn_while_the_setting_is_off(marks: MtaSandbox) -> None:
    result = plan(
        marks,
        view(panel_open=True, selected="e1", draw_radius=False),
        [mark("e1")],
    )

    assert result.zone is False


def test_the_zone_needs_something_to_be_drawn_around(marks: MtaSandbox) -> None:
    result = plan(
        marks,
        view(selected="e1", draw_radius=True),
        [mark("e1", present=False)],
    )

    assert result.zone is False


# --- Show corona -------------------------------------------------------------


def test_a_corona_is_worn_unselected_and_with_the_panel_closed(
    marks: MtaSandbox,
) -> None:
    """`Show corona` is a property of the entity, not a way of looking: it does
    not depend on anyone having the list open or the row picked out."""
    result = plan(
        marks,
        view(panel_open=False),
        [mark("e1", show_corona=True), mark("e2")],
    )

    assert [corona.entityId for corona in result.coronas.values()] == ["e1"]


def test_a_corona_is_sized_by_the_zone_it_stands_for(marks: MtaSandbox) -> None:
    result = plan(marks, view(), [mark("e1", show_corona=True, radius=12)])

    assert result.coronas[1].radius == 12


def test_an_entity_that_is_both_wears_one_corona_not_two(
    marks: MtaSandbox,
) -> None:
    """Selected, zone-drawn and corona-wearing all at once. Each Map Entity is
    visited once, so being several things cannot produce several coronas."""
    result = plan(
        marks,
        view(panel_open=True, selected="e1", draw_radius=True),
        [mark("e1", show_corona=True)],
    )

    assert len(result.coronas) == 1
    assert result.outline.entityId == "e1"
    assert result.zone.entityId == "e1"


def test_a_corona_needs_a_runtime_instance_to_hang_on(marks: MtaSandbox) -> None:
    result = plan(marks, view(), [mark("e1", show_corona=True, present=False)])

    assert len(result.coronas) == 0


def test_a_corona_follows_settings_where_the_entity_says_nothing(
    marks: MtaSandbox,
) -> None:
    result = plan(
        marks,
        view(colour="#112233", opacity=0.25),
        [mark("e1", show_corona=True)],
    )

    assert result.coronas[1].colour == "#112233"
    assert result.coronas[1].opacity == 0.25


def test_an_entity_may_say_otherwise(marks: MtaSandbox) -> None:
    result = plan(
        marks,
        view(colour="#112233", opacity=0.25),
        [mark("e1", show_corona=True, colour="#ff0000", opacity=1)],
    )

    assert result.coronas[1].colour == "#ff0000"
    assert result.coronas[1].opacity == 1


def test_an_entity_may_be_fully_transparent_on_purpose(
    marks: MtaSandbox,
) -> None:
    """Zero is a value, not an absence. Reading it as "says nothing" would make
    the one setting a player cannot express the one they asked for."""
    result = plan(
        marks,
        view(opacity=0.5),
        [mark("e1", show_corona=True, opacity=0)],
    )

    assert result.coronas[1].opacity == 0


# --- what reaches the world --------------------------------------------------


ENTRY = {
    "mapEntity": {
        "mapId": "m1",
        "entityId": "e1",
        "type": "object",
        "model": 1337,
        "map": {"resourceName": "m", "mapName": "M"},
        "authored": {
            "position": {"x": 0, "y": 0, "z": 0},
            "rotation": {"x": 0, "y": 0, "z": 0},
            "world": {"interior": 0, "dimension": 0},
        },
    },
    "runtimeInstance": {"available": True, "referenceId": "e1"},
    "metadata": {
        "name": "Gate",
        "entityTag": "",
        "radius": 4,
        "showCorona": False,
        "coronaColour": False,
        "coronaOpacity": False,
    },
    "link": {"state": "Unlinked"},
}


@pytest.fixture
def world() -> Iterator[MtaSandbox]:
    """The panel and the marks together, with one object standing in the world.

    The marks read the selection and the entities off the panel rather than
    being told, so the panel has to really be there.
    """
    sandbox = MtaSandbox()
    sandbox.load("shared/settings.lua")
    sandbox.load("shared/locale.lua")
    sandbox.load("shared/entity_types.lua")
    sandbox.load("client/layout.lua")
    sandbox.load("client/panel.lua")
    sandbox.load("client/zone_marks.lua")
    sandbox.add_world_element(
        "object", x=10.0, y=20.0, z=30.0, model=1337, ankigtaEntityId="e1"
    )
    sandbox.eval('function() ANKIGTA.Locale.setLanguage("en") end')()
    # A corona is worn whether or not anyone opens the list, so the panel is
    # authorized but left shut. Every test that needs it open says so.
    sandbox.eval(
        'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
    )()
    try:
        yield sandbox
    finally:
        sandbox.close()


def snapshot(sandbox: MtaSandbox, entries: list[dict[str, Any]]) -> None:
    sandbox.eval(
        'function(s) triggerEvent("ankigta:f7Snapshot", resourceRoot, s) end'
    )(
        to_lua(
            sandbox,
            {
                "visible": True,
                "cardPicker": {"enabled": True},
                "history": {"canUndo": False, "canRedo": False},
                "entities": entries,
            },
        )
    )


def entry(**metadata: Any) -> dict[str, Any]:
    merged = json.loads(json.dumps(ENTRY))
    merged["metadata"].update(metadata)
    return merged


def select(sandbox: MtaSandbox, entity_id: str) -> None:
    sandbox.eval(
        """
        function(payload)
            triggerEvent("ankigta:panelAction", resourceRoot, "select", payload)
        end
        """
    )(json.dumps({"mapId": "m1", "entityId": entity_id}))


def refresh(sandbox: MtaSandbox) -> Any:
    return sandbox.eval("function() return ANKIGTA.ZoneMarks.refresh() end")()


def render(sandbox: MtaSandbox) -> None:
    sandbox.eval("function() ANKIGTA.ZoneMarks.render() end")()


def open_panel(sandbox: MtaSandbox) -> None:
    sandbox.eval(
        """
        function()
            togglePanel()
            triggerEvent("ankigta:panelAction", resourceRoot, "ready", "{}")
        end
        """
    )()


def test_show_corona_puts_a_corona_in_the_world(world: MtaSandbox) -> None:
    snapshot(world, [entry(showCorona=True, radius=6)])

    refresh(world)

    assert len(world.markers) == 1
    marker = world.markers[0]
    assert marker["markerType"] == "corona"
    assert marker["size"] == 6
    # The shipped default, because this entity says nothing of its own.
    assert (marker["red"], marker["green"], marker["blue"]) == (0x3C, 0xC8, 0xFF)
    assert marker["alpha"] == 128


def test_a_corona_is_attached_to_the_thing_it_marks(world: MtaSandbox) -> None:
    """So it keeps up with a vehicle without this module moving it every frame."""
    snapshot(world, [entry(showCorona=True)])

    refresh(world)

    assert len(world.attachments) == 1
    marker, target = world.attachments[0]
    # By what the tables say rather than by identity: lupa hands out a fresh
    # wrapper per crossing, so two references to one Lua table are not `==`.
    assert marker["markerType"] == "corona"
    assert target["ankigtaEntityId"] == "e1"


def test_an_unchanged_corona_is_left_alone(world: MtaSandbox) -> None:
    """Rebuilding every marker four times a second would flicker, and would
    churn the element events the panel listens to."""
    snapshot(world, [entry(showCorona=True)])
    refresh(world)

    refresh(world)
    refresh(world)

    assert len(world.markers) == 1


def test_a_corona_destroyed_by_something_else_is_put_back(
    world: MtaSandbox,
) -> None:
    """The record of it still matches the plan, and a matching record is one
    this never replaces -- so the entity would go unmarked for as long as
    nothing about it changed."""
    snapshot(world, [entry(showCorona=True)])
    refresh(world)
    world.eval("function(m) destroyElement(m) end")(world.markers[0])

    refresh(world)

    assert len(world.markers) == 2
    assert world.markers[1]["__destroyed"] is not True


def test_turning_show_corona_off_takes_the_corona_away(world: MtaSandbox) -> None:
    snapshot(world, [entry(showCorona=True)])
    refresh(world)

    snapshot(world, [entry(showCorona=False)])
    refresh(world)

    assert all(marker["__destroyed"] is True for marker in world.markers)


def test_the_entitys_own_colour_reaches_the_corona(world: MtaSandbox) -> None:
    snapshot(world, [entry(showCorona=True, coronaColour="#ff0000", coronaOpacity=1)])

    refresh(world)

    marker = world.markers[0]
    assert (marker["red"], marker["green"], marker["blue"]) == (255, 0, 0)
    assert marker["alpha"] == 255


def test_a_corona_is_not_a_map_entity_the_panel_must_re_read(
    world: MtaSandbox,
) -> None:
    """A corona is a marker, and a marker is a type a card can hang on. Without
    the marks saying which markers are theirs, ANKIGTA drawing one would make
    the panel ask the server for the whole list again -- which produces the
    next snapshot, which moves a corona."""
    open_panel(world)
    snapshot(world, [entry(showCorona=True)])
    # Counted before the corona exists: MTA raises `onClientElementCreate` from
    # inside `createMarker`, so the panel is asked whether the element is ours
    # in the moment between the marker existing and this module having anything
    # to write down. Counting afterwards would pass whatever happened.
    before = len(world.recorder.timers)

    refresh(world)

    assert len(world.markers) == 1
    assert world.eval("function(m) return ANKIGTA.ZoneMarks.owns(m) end")(
        world.markers[0]
    ) is True
    assert len(world.recorder.timers) == before, (
        "creating a corona scheduled a re-read of the Map Entity list"
    )


def test_taking_a_corona_away_is_not_a_map_entity_leaving_either(
    world: MtaSandbox,
) -> None:
    """The same window, on the way out: the panel is asked from inside
    `destroyElement`, so a marker disowned a statement too early reads to it as
    a Map Entity vanishing from the world."""
    open_panel(world)
    snapshot(world, [entry(showCorona=True)])
    refresh(world)
    marker = world.markers[0]
    before = len(world.recorder.timers)

    snapshot(world, [entry(showCorona=False)])
    refresh(world)

    assert marker["__destroyed"] is True
    assert len(world.recorder.timers) == before


def test_the_outline_is_drawn_around_the_selected_row(world: MtaSandbox) -> None:
    open_panel(world)
    snapshot(world, [entry()])
    select(world, "e1")
    refresh(world)

    render(world)

    # Twelve edges of a box, around where the object actually stands.
    assert len(world.drawn_lines_3d) == 12
    xs = [line["startX"] for line in world.drawn_lines_3d]
    assert min(xs) == pytest.approx(9.0)
    assert max(xs) == pytest.approx(11.0)


def test_nothing_is_drawn_for_a_row_nobody_selected(world: MtaSandbox) -> None:
    open_panel(world)
    snapshot(world, [entry()])
    refresh(world)

    render(world)

    assert world.drawn_lines_3d == []


def test_the_zone_is_drawn_as_a_sphere_around_the_selected_row(
    world: MtaSandbox,
) -> None:
    """Three great circles, not a ring on the ground: the zone is a distance in
    three dimensions and a ring says nothing about the storey above."""
    snapshot(world, [entry(radius=5)])
    select(world, "e1")
    world.eval(
        "function() ANKIGTA.ZoneMarks.applySettings({drawRadius = true}) end"
    )()
    refresh(world)

    render(world)

    # Three circles of sixteen segments; the panel is shut, so no outline.
    assert len(world.drawn_lines_3d) == 48
    distances = {
        round(
            (
                (line["startX"] - 10.0) ** 2
                + (line["startY"] - 20.0) ** 2
                + (line["startZ"] - 30.0) ** 2
            )
            ** 0.5,
            3,
        )
        for line in world.drawn_lines_3d
    }
    assert distances == {5.0}


def test_a_model_with_no_bounding_box_still_gets_an_outline(
    world: MtaSandbox,
) -> None:
    """MTA answers with a single `false` there, not with six zeroes."""
    world.bounding_box_fails = True
    open_panel(world)
    snapshot(world, [entry()])
    select(world, "e1")
    refresh(world)

    render(world)

    assert len(world.drawn_lines_3d) == 12


def test_the_indicator_is_told_a_corona_already_marks_the_spot(
    world: MtaSandbox,
) -> None:
    """So it emphasizes that mark rather than putting a second one on top."""
    snapshot(world, [entry(showCorona=True)])
    refresh(world)

    shows = world.eval(
        'function() return ANKIGTA.ZoneMarks.showsCorona("m1", "e1") end'
    )()
    absent = world.eval(
        'function() return ANKIGTA.ZoneMarks.showsCorona("m1", "e2") end'
    )()

    assert shows is True
    assert absent is False


def test_the_marks_have_something_to_draw_before_f7_is_ever_opened(
    world: MtaSandbox,
) -> None:
    """A corona is worn by the entity, so it cannot wait for the player to look
    at the list. The snapshot is where the client learns which entities wear
    one, and it was asked for only when F7 opened -- so a player who never
    opened it saw none, and one who did saw them appear as if the panel had
    put them there.
    """
    asked = [
        event
        for event in world.recorder.server_events
        if event.name == "ankigta:requestF7"
    ]

    # The fixture authorized the client and never opened the panel.
    assert len(asked) == 1
    assert world.eval("function() return ANKIGTA.Panel.isOpen() end")() is False


# --- what the entity remembers ----------------------------------------------


@pytest.fixture
def store(tmp_path: Any) -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
    sandbox.load("shared/settings.lua")
    sandbox.load("server/backup.lua")
    sandbox.load("server/store.lua")
    sandbox.eval("function() ANKIGTA.Store.seedTracerFixtures = true end")()
    sandbox.eval("function() return ANKIGTA.Store.open() end")()
    try:
        yield sandbox
    finally:
        sandbox.close()


def a_map_entity(sandbox: MtaSandbox) -> tuple[str, str]:
    """The first Map Entity the tracer fixture seeded."""
    row = sandbox.connection.raw.execute(
        "SELECT map_id, entity_id FROM map_entities ORDER BY entity_id LIMIT 1"
    ).fetchone()
    return str(row[0]), str(row[1])


def write_metadata(sandbox: MtaSandbox, map_id: str, entity_id: str, **fields: Any):
    return sandbox.eval(
        "function(m, e, f) return ANKIGTA.Store.updateEntityMetadata(m, e, f) end"
    )(map_id, entity_id, to_lua(sandbox, fields))


def read_metadata(sandbox: MtaSandbox, map_id: str, entity_id: str) -> dict[str, Any]:
    row = sandbox.eval(
        "function(m, e) return ANKIGTA.Store.getMapEntity(m, e) end"
    )(map_id, entity_id)
    colour, opacity = sandbox.eval(
        "function(r) return ANKIGTA.Store.coronaOf(r) end"
    )(row)
    return {
        "showCorona": row["show_radius"] == 1,
        "coronaColour": colour,
        "coronaOpacity": opacity,
    }


def test_an_entity_with_nothing_of_its_own_says_so(store: MtaSandbox) -> None:
    """Not "no colour" but "the one Settings says", which is why it cannot be
    stored as a copy of the setting: the copy would go stale the moment the
    setting changed."""
    map_id, entity_id = a_map_entity(store)

    assert read_metadata(store, map_id, entity_id) == {
        "showCorona": False,
        "coronaColour": False,
        "coronaOpacity": False,
    }


def test_an_entity_remembers_the_look_it_was_given(store: MtaSandbox) -> None:
    map_id, entity_id = a_map_entity(store)

    write_metadata(
        store,
        map_id,
        entity_id,
        showCorona=True,
        coronaColour="#ff8800",
        coronaOpacity=0.25,
    )

    assert read_metadata(store, map_id, entity_id) == {
        "showCorona": True,
        "coronaColour": "#ff8800",
        "coronaOpacity": 0.25,
    }


def test_clearing_a_look_puts_the_entity_back_on_settings(
    store: MtaSandbox,
) -> None:
    """`false` is the player emptying the field, which is a decision and not an
    absence -- storing it as "unchanged" is how "follow Settings again" would
    silently do nothing."""
    map_id, entity_id = a_map_entity(store)
    write_metadata(store, map_id, entity_id, coronaColour="#ff8800", coronaOpacity=1)

    write_metadata(store, map_id, entity_id, coronaColour=False, coronaOpacity=False)

    stored = read_metadata(store, map_id, entity_id)
    assert stored["coronaColour"] is False
    assert stored["coronaOpacity"] is False


def test_a_fully_transparent_corona_is_not_read_as_unset(
    store: MtaSandbox,
) -> None:
    """Zero is a value. Reading it as "says nothing" would make the one setting
    a player cannot express the one they chose."""
    map_id, entity_id = a_map_entity(store)

    write_metadata(store, map_id, entity_id, coronaOpacity=0)

    assert read_metadata(store, map_id, entity_id)["coronaOpacity"] == 0


def test_undo_puts_back_the_look_the_entity_had(store: MtaSandbox) -> None:
    """The corona is a property of the thing, so it is the server's to hold and
    the server's to put back (ADR 0028)."""
    map_id, entity_id = a_map_entity(store)
    write_metadata(store, map_id, entity_id, coronaColour="#ff8800", coronaOpacity=0.25)

    write_metadata(store, map_id, entity_id, coronaColour="#00ff00", coronaOpacity=1)
    store.eval("function() return ANKIGTA.Store.undo() end")()

    assert read_metadata(store, map_id, entity_id) == {
        "showCorona": False,
        "coronaColour": "#ff8800",
        "coronaOpacity": 0.25,
    }


def test_stopping_takes_every_corona_out_of_the_world(world: MtaSandbox) -> None:
    snapshot(world, [entry(showCorona=True)])
    refresh(world)

    world.trigger("onClientResourceStop")

    assert all(marker["__destroyed"] is True for marker in world.markers)
