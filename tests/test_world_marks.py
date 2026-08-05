"""Panel rebuild 04 — what ANKIGTA draws into the world.

One module, one rule about distance, and a mark that belongs to the entity
rather than to a window. `Draw always` made a drawn radius permanent, which
confused two different things; they are pulled apart here — `Draw radius` is a
way of looking and lives on the client, `Show corona` is a property of the
entity and lives in the store.

What the harness cannot do is look at a frame. It can say which lines and
markers ANKIGTA asked MTA for, with what size, colour and attachment, which is
what every claim below is made of.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox
from tests.lua.strings import named_keys, resource_scripts


REPO_ROOT = Path(__file__).resolve().parents[1]

MAP_ID = "current-map-id"


def locale_table() -> dict[str, str]:
    """The shipped strings, read out of the loaded chunk rather than grepped.

    `docs/agents/lua-testing.md`: a grep over the file sees comments and misses
    anything built by concatenation.
    """
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/locale.lua")
        strings = sandbox.eval("ANKIGTA.Locale.strings")
        return {str(key): str(strings[key]) for key in strings.keys()}
    finally:
        sandbox.close()


def manifest_scripts(*kinds: str) -> list[str]:
    """The scripts meta.xml declares, in declared order.

    Reading the manifest rather than listing the scripts means one that was
    never registered fails here instead of quietly working in tests only --
    which is how `zone_marks.lua` once sat in the deployed folder for days,
    undeclared and never loaded.
    """
    manifest = ElementTree.parse(REPO_ROOT / "mta" / "ankigta" / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


def to_lua(sandbox: MtaSandbox, value: Any) -> Any:
    if isinstance(value, dict):
        return sandbox.lua.table_from(
            {key: to_lua(sandbox, item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return sandbox.lua.table_from([to_lua(sandbox, item) for item in value])
    return value


@pytest.fixture
def client() -> Iterator[MtaSandbox]:
    """A whole client side, started the way MTA starts it.

    Every client script in manifest order, then `onClientResourceStart`: the
    marks are polled by a timer that only exists because the resource started,
    and the panel asks for its snapshot because the player was authorized.
    """
    sandbox = MtaSandbox()
    try:
        for script in manifest_scripts("shared", "client"):
            sandbox.load(script)
        sandbox.trigger("onClientResourceStart")
        yield sandbox
    finally:
        sandbox.close()


def authorize(sandbox: MtaSandbox) -> None:
    sandbox.eval(
        'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
    )()


def entry(
    *,
    entity_id: str = "gate-17",
    map_id: str = MAP_ID,
    radius: Any = False,
    show_corona: bool = False,
    corona_color: Any = False,
    corona_opacity: Any = False,
) -> dict[str, Any]:
    """One entry of the F7 snapshot, as `server/main.lua` builds it.

    `false` is the entity saying nothing of its own, which is what the store
    means by a NULL override, an empty colour and an opacity out of range.
    """
    return {
        "mapEntity": {
            "mapId": map_id,
            "entityId": entity_id,
            "type": "object",
            "model": 1337,
            "map": {"resourceName": "current-map", "mapName": "Current Map"},
            "authored": {
                "position": {"x": 0, "y": 0, "z": 0},
                "rotation": {"x": 0, "y": 0, "z": 0},
                "world": {"interior": 0, "dimension": 0},
            },
        },
        "runtimeInstance": {"available": True, "referenceId": entity_id},
        "metadata": {
            "name": "",
            "entityTag": "",
            "radius": radius,
            "showCorona": show_corona,
            "coronaColor": corona_color,
            "coronaOpacity": corona_opacity,
        },
        "link": {"state": "Unlinked"},
    }


def push_snapshot(sandbox: MtaSandbox, entities: list[dict[str, Any]]) -> None:
    snapshot = {
        "visible": True,
        "cardPicker": {"enabled": False},
        "history": {"canUndo": False, "canRedo": False},
        "entities": entities,
        "currentMap": {"resourceName": "current-map", "mapIds": [MAP_ID]},
        "cardLinks": [],
    }
    sandbox.eval(
        """
        function(snapshot)
            triggerEvent("ankigta:f7Snapshot", resourceRoot, snapshot)
        end
        """
    )(to_lua(sandbox, snapshot))


def standing(
    sandbox: MtaSandbox,
    *,
    entity_id: str = "gate-17",
    map_id: str = MAP_ID,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
) -> Any:
    """The Runtime Instance of a Map Entity, stamped the way ANKIGTA stamps it."""
    return sandbox.add_world_element(
        x=x,
        y=y,
        z=z,
        ankigtaEntityId=entity_id,
        ankigtaMapId=map_id,
    )


def announce_client(sandbox: MtaSandbox, **values: Any) -> None:
    """A client-owned setting, applied the way the client store applies one."""
    sandbox.eval(
        "function(values) return ANKIGTA.WorldMarks.applySettings(values) end"
    )(to_lua(sandbox, values))


def announce_server(sandbox: MtaSandbox, **values: Any) -> None:
    """Server-owned settings, arriving over the wire the way they really do."""
    sandbox.eval(
        """
        function(values)
            triggerEvent("ankigta:settings", resourceRoot, values)
        end
        """
    )(to_lua(sandbox, values))


def select(sandbox: MtaSandbox, entity_id: str, map_id: str = MAP_ID) -> None:
    sandbox.eval(
        """
        function(payload)
            triggerEvent("ankigta:panelAction", resourceRoot, "select", payload)
        end
        """
    )(json.dumps({"mapId": map_id, "entityId": entity_id}))


def refresh(sandbox: MtaSandbox) -> Any:
    return sandbox.eval("function() return ANKIGTA.WorldMarks.refresh() end")()


def live_markers(sandbox: MtaSandbox) -> list[Any]:
    return [
        marker for marker in sandbox.markers if marker["__destroyed"] is not True
    ]


def ring_radii(sandbox: MtaSandbox, x: float = 0.0, y: float = 0.0) -> set[float]:
    """How far from `x`, `y` the drawn segments are, rounded to millimetres.

    A sphere is three great circles, so a segment in the vertical planes passes
    through the centre; only the horizontal one is a ring at the radius, which
    is what this asks about.
    """
    return {
        round(
            ((point["startX"] - x) ** 2 + (point["startY"] - y) ** 2) ** 0.5, 3
        )
        for point in sandbox.drawn_lines_3d
        if round(point["startZ"], 3) == round(point["endZ"], 3)
    }


# --- a corona is a property of the entity ------------------------------------


def test_a_corona_is_drawn_without_f7_having_been_opened_first(
    client: MtaSandbox,
) -> None:
    """The snapshot used to be sent only in answer to F7 being pressed, so a
    mark that is a property of the world waited for a window."""
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True)])

    refresh(client)

    assert len(live_markers(client)) == 1
    # And the panel never opened: nothing here is a browser.
    assert client.browsers == []


def test_the_snapshot_is_asked_for_as_soon_as_the_player_is_authorized(
    client: MtaSandbox,
) -> None:
    """Which entities wear a corona is only in that snapshot, so a client that
    waits for F7 shows none until somebody opens it."""
    authorize(client)

    assert "ankigta:requestF7" in [
        event.name for event in client.recorder.server_events
    ]


def test_a_corona_is_sized_by_the_activation_zone_it_stands_for(
    client: MtaSandbox,
) -> None:
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True, radius=7.5)])

    refresh(client)

    assert [marker["size"] for marker in live_markers(client)] == [7.5]
    assert [marker["markerType"] for marker in live_markers(client)] == ["corona"]


def test_a_corona_on_an_entity_with_no_radius_is_the_size_of_the_global(
    client: MtaSandbox,
) -> None:
    """The entity follows Settings, so the mark has to be the size the card
    will really open at -- not the size the shipped default happens to be."""
    authorize(client)
    announce_server(client, activationRadius=12)
    standing(client)
    push_snapshot(client, [entry(show_corona=True, radius=False)])

    refresh(client)

    assert [marker["size"] for marker in live_markers(client)] == [12]


def test_a_corona_follows_its_object_as_the_object_moves(
    client: MtaSandbox,
) -> None:
    """Attached rather than moved: MTA writes the target's matrix into an
    attached element every frame, so following it in Lua would be this module's
    own polling loop over elements MTA is already moving."""
    authorize(client)
    element = standing(client, x=10.0, y=20.0, z=3.0)
    push_snapshot(client, [entry(show_corona=True)])

    refresh(client)
    marker = live_markers(client)[0]
    assert len(client.attachments) == 1
    # Compared inside Lua: lupa hands out a fresh wrapper per crossing, so two
    # references to one element are not the same Python object.
    assert client.eval(
        "function(m, e) return getElementAttachedTo(m) == e end"
    )(marker, element) is True

    element["x"], element["y"], element["z"] = 40.0, 60.0, 5.0

    moved = client.eval("function(m) return {getElementPosition(m)} end")(marker)
    assert (moved[1], moved[2], moved[3]) == (40.0, 60.0, 5.0)


def test_a_corona_goes_when_the_thing_it_marks_is_destroyed(
    client: MtaSandbox,
) -> None:
    """MTA breaks the attachment rather than destroying what was attached, so
    without this the corona hangs in the air where the object used to be."""
    authorize(client)
    element = standing(client)
    push_snapshot(client, [entry(show_corona=True)])
    refresh(client)
    assert len(live_markers(client)) == 1

    client.eval("function(e) destroyElement(e) end")(element)

    assert live_markers(client) == []


def test_a_corona_goes_when_the_entity_stops_asking_for_one(
    client: MtaSandbox,
) -> None:
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True)])
    refresh(client)
    assert len(live_markers(client)) == 1

    push_snapshot(client, [entry(show_corona=False)])
    refresh(client)

    assert live_markers(client) == []


def test_a_corona_that_has_not_changed_is_left_exactly_as_it_is(
    client: MtaSandbox,
) -> None:
    """Reconciled rather than rebuilt: destroying and recreating every marker
    four times a second would flicker, and would churn the element events the
    panel listens to."""
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True)])
    refresh(client)
    first = live_markers(client)[0]

    for _ in range(4):
        refresh(client)

    assert len(client.markers) == 1
    assert live_markers(client) == [first]


def test_a_resized_zone_resizes_the_corona_rather_than_replacing_it(
    client: MtaSandbox,
) -> None:
    """`setMarkerSize` resizes in place, so the marker -- and the attachment
    that makes it follow its object -- survives the change."""
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True, radius=3)])
    refresh(client)
    marker = live_markers(client)[0]

    push_snapshot(client, [entry(show_corona=True, radius=9)])
    refresh(client)

    assert live_markers(client) == [marker]
    assert marker["size"] == 9
    assert len(client.markers) == 1


# --- what a corona looks like ------------------------------------------------


def test_a_corona_follows_the_settings_colour_and_opacity(
    client: MtaSandbox,
) -> None:
    authorize(client)
    announce_server(client, coronaColor="#ff8000", coronaOpacity=0.5)
    standing(client)
    push_snapshot(client, [entry(show_corona=True)])

    refresh(client)

    marker = live_markers(client)[0]
    assert (marker["red"], marker["green"], marker["blue"]) == (255, 128, 0)
    assert marker["alpha"] == 128


def test_an_entity_may_say_its_own_colour_and_opacity(
    client: MtaSandbox,
) -> None:
    """The shape the Activation Zone radius already has: a global, and an
    override on the link."""
    authorize(client)
    announce_server(client, coronaColor="#ff8000", coronaOpacity=0.5)
    standing(client)
    push_snapshot(
        client,
        [entry(show_corona=True, corona_color="#00ff40", corona_opacity=1)],
    )

    refresh(client)

    marker = live_markers(client)[0]
    assert (marker["red"], marker["green"], marker["blue"]) == (0, 255, 64)
    assert marker["alpha"] == 255


def test_the_shipped_opacity_is_six_tenths(client: MtaSandbox) -> None:
    """Nothing has been said about opacity anywhere, so what is drawn is the
    number the ticket states."""
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True)])

    refresh(client)

    assert live_markers(client)[0]["alpha"] == round(0.6 * 255)


def test_a_stored_colour_that_fails_its_own_rule_falls_back_rather_than_drawing_black(
    client: MtaSandbox,
) -> None:
    """Black is a colour somebody could have meant, and this never is -- so a
    corrupted or hand-edited value falls back to the shipped default."""
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True, corona_color="not-a-colour")])

    refresh(client)

    shipped = client.eval(
        "function() return ANKIGTA.Settings.default('coronaColor') end"
    )()
    red, green, blue = client.eval(
        "function(v) return ANKIGTA.Settings.colorChannels(v) end"
    )(shipped)
    marker = live_markers(client)[0]
    assert (marker["red"], marker["green"], marker["blue"]) == (red, green, blue)
    assert (marker["red"], marker["green"], marker["blue"]) != (0, 0, 0)


def test_an_opacity_out_of_range_falls_back_to_the_shipped_one(
    client: MtaSandbox,
) -> None:
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True, corona_opacity=4)])

    refresh(client)

    assert live_markers(client)[0]["alpha"] == round(0.6 * 255)


def test_changing_a_colour_recolours_the_corona_in_place(
    client: MtaSandbox,
) -> None:
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True, corona_color="#ff8000")])
    refresh(client)
    marker = live_markers(client)[0]

    push_snapshot(client, [entry(show_corona=True, corona_color="#0080ff")])
    refresh(client)

    assert live_markers(client) == [marker]
    assert (marker["red"], marker["green"], marker["blue"]) == (0, 128, 255)


# --- Draw radius is the client's own way of looking --------------------------


def test_draw_radius_draws_the_selected_rows_zone(client: MtaSandbox) -> None:
    authorize(client)
    standing(client)
    standing(client, entity_id="gate-18", x=100.0)
    push_snapshot(client, [entry(), entry(entity_id="gate-18", radius=7.5)])
    announce_client(client, drawRadius=True)
    select(client, "gate-18")

    refresh(client)
    client.trigger("onClientRender")

    assert ring_radii(client, x=100.0) == {7.5}


def test_nothing_is_drawn_for_an_unselected_row(client: MtaSandbox) -> None:
    """A way of looking is about the row being looked at, not about every row
    in the list."""
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(radius=7.5)])
    announce_client(client, drawRadius=True)

    refresh(client)
    client.trigger("onClientRender")

    assert client.drawn_lines_3d == []


def test_nothing_is_drawn_while_the_setting_is_off(client: MtaSandbox) -> None:
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(radius=7.5)])
    select(client, "gate-17")

    refresh(client)
    client.trigger("onClientRender")

    assert client.drawn_lines_3d == []


def test_the_drawn_zone_is_the_radius_actually_in_force(
    client: MtaSandbox,
) -> None:
    """A zone drawn at 3 while the setting says 10 lies about where the card
    will open."""
    authorize(client)
    announce_server(client, activationRadius=10)
    announce_client(client, drawRadius=True)
    standing(client)
    push_snapshot(client, [entry(radius=False)])
    select(client, "gate-17")

    refresh(client)
    client.trigger("onClientRender")

    assert ring_radii(client) == {10.0}


def test_the_drawn_zone_follows_its_object_and_outlives_the_panel(
    client: MtaSandbox,
) -> None:
    """The point of it being the client's: the player sizes a zone, closes F7
    and walks the edge of it."""
    authorize(client)
    element = standing(client)
    push_snapshot(client, [entry(radius=5)])
    announce_client(client, drawRadius=True)
    select(client, "gate-17")
    refresh(client)

    client.eval("function() ANKIGTA.Panel.close() end")()
    element["x"], element["y"] = 30.0, 40.0
    client.trigger("onClientRender")

    assert ring_radii(client, x=30.0, y=40.0) == {5.0}


def test_a_zone_is_not_drawn_on_a_thing_that_is_not_here(
    client: MtaSandbox,
) -> None:
    """The old ring fell back to the authored position when no element could be
    found, which is how a mark came to hang in the air over nothing."""
    authorize(client)
    push_snapshot(client, [entry(radius=5)])
    announce_client(client, drawRadius=True)
    select(client, "gate-17")

    refresh(client)
    client.trigger("onClientRender")

    assert client.drawn_lines_3d == []


# --- one distance, for everything drawn --------------------------------------


def far_away(sandbox: MtaSandbox) -> float:
    """A metre past wherever ANKIGTA stops drawing."""
    return sandbox.eval(
        "function() return ANKIGTA.WorldMarks.drawDistance() end"
    )() + 1


def test_a_drawn_zone_stops_at_the_stated_distance(client: MtaSandbox) -> None:
    authorize(client)
    beyond = far_away(client)
    element = standing(client, x=beyond)
    push_snapshot(client, [entry(radius=5)])
    announce_client(client, drawRadius=True)
    select(client, "gate-17")
    refresh(client)

    client.trigger("onClientRender")
    assert client.drawn_lines_3d == []

    # And is drawn again from close enough to see it.
    element["x"] = 10.0
    client.trigger("onClientRender")
    assert ring_radii(client, x=10.0) == {5.0}


def test_a_corona_stops_at_the_same_distance(client: MtaSandbox) -> None:
    """The corona is an element rather than something drawn per frame, so the
    rule takes it out of the world instead of skipping a draw."""
    authorize(client)
    element = standing(client, x=far_away(client))
    push_snapshot(client, [entry(show_corona=True)])

    refresh(client)
    assert live_markers(client) == []

    element["x"] = 10.0
    refresh(client)
    assert len(live_markers(client)) == 1

    element["x"] = far_away(client)
    refresh(client)
    assert live_markers(client) == []


def test_the_next_card_indicator_stops_at_the_same_distance(
    client: MtaSandbox,
) -> None:
    """One rule for every drawn mark, so a mark added later inherits it rather
    than repeating it. The indicator's is a beam drawn through the same door."""
    beam = client.eval(
        """
        function(x)
            return ANKIGTA.WorldMarks.beam(x, 0, 0, 3, 0)
        end
        """
    )

    assert beam(10.0) is True
    assert beam(far_away(client)) is False


def test_the_distance_is_measured_from_the_camera_not_the_player(
    client: MtaSandbox,
) -> None:
    """The panel flies the camera to a row while the player stays put, and it
    does that in order to look at the mark."""
    client.player_position = (0.0, 0.0, 0.0)
    client.camera_matrix = (500.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    assert client.eval(
        "function() return ANKIGTA.WorldMarks.visible(505, 0, 0) end"
    )() is True
    assert client.eval(
        "function() return ANKIGTA.WorldMarks.visible(0, 0, 0) end"
    )() is False


# --- the marks are ANKIGTA's own, and the panel knows it ---------------------


def test_the_panel_does_not_re_read_the_world_because_of_its_own_coronas(
    client: MtaSandbox,
) -> None:
    """A corona is a marker, and a marker is one of the types a card can hang
    on -- so without this, drawing one asks the server to rebuild the snapshot,
    which decides where the coronas go, which draws another."""
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True)])
    before = len(
        [e for e in client.recorder.server_events if e.name == "ankigta:requestF7"]
    )

    refresh(client)
    client.fire_timers()

    after = len(
        [e for e in client.recorder.server_events if e.name == "ankigta:requestF7"]
    )
    assert after == before
    assert len(live_markers(client)) == 1


def test_the_indicator_emphasizes_a_corona_rather_than_marking_the_spot_twice(
    client: MtaSandbox,
) -> None:
    """`Draw always` is gone, so what the spatial poll asks is whether a mark
    is standing here now -- which only the side that draws can answer."""
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True)])
    refresh(client)

    assert client.eval(
        "function() return ANKIGTA.WorldMarks.showsCorona('current-map-id', 'gate-17') end"
    )() is True
    assert client.eval(
        "function() return ANKIGTA.WorldMarks.showsCorona('current-map-id', 'gate-18') end"
    )() is False


def test_stopping_the_resource_takes_every_corona_out_of_the_world(
    client: MtaSandbox,
) -> None:
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True)])
    refresh(client)
    assert len(live_markers(client)) == 1

    client.trigger("onClientResourceStop")

    assert live_markers(client) == []


def test_the_marks_are_polled_without_anything_asking_them_to(
    client: MtaSandbox,
) -> None:
    """A mark that is a property of the world does not wait for a window, and
    a timer started when the resource started is what makes that true."""
    authorize(client)
    standing(client)
    push_snapshot(client, [entry(show_corona=True)])
    client.eval("function() ANKIGTA.WorldMarks.clear() end")()
    assert live_markers(client) == []

    client.fire_timers()

    assert len(live_markers(client)) == 1


# --- `Draw always` is gone ---------------------------------------------------


def test_draw_always_is_gone_from_the_string_table() -> None:
    """It named a per-link switch that made a drawn radius permanent, which
    confused a way of looking with a property of the thing looked at. Both
    halves exist now under their own names, and the words for the old one
    cannot still be on a control somewhere."""
    table = locale_table()

    assert "f7.drawAlways" not in table
    assert "f7.showRadius" not in table
    assert [key for key, words in table.items() if "Draw always" in words] == []
    # And the two that replaced it are there to be shown.
    assert "Show corona" in table["f7.showCorona"]
    assert "settings.drawRadius" in table


# --- what the entity remembers about its own corona --------------------------
#
# The server half. A corona is stored on the entity, so it survives a restart
# and looks the same to everyone -- which is the whole difference between it
# and `Draw radius`.


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


def seed_entity(sandbox: MtaSandbox, entity_id: str = "gate-17") -> None:
    connection = sandbox.connection.raw
    connection.execute(
        "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
        " VALUES (?, 'current-map', 'Current Map')",
        (MAP_ID,),
    )
    connection.execute(
        "INSERT OR REPLACE INTO map_entities (map_id, entity_id, entity_type,"
        " model, authored_x, authored_y, authored_z, rotation_x, rotation_y,"
        " rotation_z, interior, dimension)"
        " VALUES (?, ?, 'object', 1337, 10, 20, 30, 0, 0, 0, 0, 0)",
        (MAP_ID, entity_id),
    )
    connection.commit()


def write_metadata(
    sandbox: MtaSandbox, player: Any, metadata: dict[str, Any]
) -> None:
    sandbox.trigger(
        "ankigta:updateEntityMetadata",
        sandbox.lua.globals().resourceRoot,
        MAP_ID,
        "gate-17",
        to_lua(sandbox, metadata),
        client=player,
    )


def snapshot_row(sandbox: MtaSandbox, player: Any) -> dict[str, Any]:
    sandbox.trigger(
        "ankigta:requestF7", sandbox.lua.globals().resourceRoot, client=player
    )
    event = sandbox.recorder.client_events[-1]
    assert event.name == "ankigta:f7Snapshot"
    snapshot = sandbox.to_python(event.args[0])
    rows = {row["mapEntity"]["entityId"]: row for row in snapshot["entities"]}
    return rows["gate-17"]


def refusals(sandbox: MtaSandbox) -> list[Any]:
    return [
        event.args
        for event in sandbox.recorder.client_events
        if event.name == "ankigta:pendingMapSaveNotice"
    ]


def test_show_corona_is_stored_on_the_entity(server: MtaSandbox) -> None:
    seed_entity(server)
    player = server.add_study_player()

    write_metadata(server, player, {"showCorona": True})

    assert server.connection.raw.execute(
        "SELECT show_radius FROM map_entity_metadata WHERE entity_id = ?",
        ("gate-17",),
    ).fetchone() == (1,)
    assert snapshot_row(server, player)["metadata"]["showCorona"] is True


def test_a_colour_and_an_opacity_are_stored_on_the_entity(
    server: MtaSandbox,
) -> None:
    seed_entity(server)
    player = server.add_study_player()

    write_metadata(
        server, player, {"coronaColor": "#FF8000", "coronaOpacity": 0.25}
    )

    row = snapshot_row(server, player)["metadata"]
    # One spelling for one colour, decided by the schema and applied here.
    assert row["coronaColor"] == "#ff8000"
    assert row["coronaOpacity"] == 0.25


def test_an_entity_that_says_nothing_follows_settings(
    server: MtaSandbox,
) -> None:
    """`false`, not a copy of today's global: a copy would go stale the moment
    the setting changed, and the entity would stop following it."""
    seed_entity(server)
    player = server.add_study_player()

    write_metadata(server, player, {"name": "North gate"})

    row = snapshot_row(server, player)["metadata"]
    assert row["coronaColor"] is False
    assert row["coronaOpacity"] is False


def test_clearing_a_colour_goes_back_to_following_settings(
    server: MtaSandbox,
) -> None:
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(server, player, {"coronaColor": "#ff8000"})

    write_metadata(server, player, {"coronaColor": False})

    assert snapshot_row(server, player)["metadata"]["coronaColor"] is False


def test_setting_one_field_does_not_erase_the_others(
    server: MtaSandbox,
) -> None:
    """The page sends only what the player touched."""
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(
        server,
        player,
        {"showCorona": True, "coronaColor": "#ff8000", "coronaOpacity": 0.25},
    )

    write_metadata(server, player, {"name": "North gate"})

    row = snapshot_row(server, player)["metadata"]
    assert row["name"] == "North gate"
    assert row["showCorona"] is True
    assert row["coronaColor"] == "#ff8000"
    assert row["coronaOpacity"] == 0.25


@pytest.mark.parametrize(
    "metadata",
    [
        {"coronaColor": "not-a-colour"},
        {"coronaColor": True},
        {"coronaOpacity": 4},
        {"coronaOpacity": "half"},
    ],
)
def test_a_value_the_schema_would_refuse_is_refused_here_too(
    server: MtaSandbox, metadata: dict[str, Any]
) -> None:
    """A value cannot be legal in Settings and illegal on an entity, and the
    schema is the side both can reach. `true` is in the list because
    normalizing a boolean as a colour is an error rather than a refusal, which
    took the handler down instead of answering no."""
    seed_entity(server)
    player = server.add_study_player()

    write_metadata(server, player, metadata)

    assert refusals(server) != []
    row = snapshot_row(server, player)["metadata"]
    assert row["coronaColor"] is False
    assert row["coronaOpacity"] is False


def test_undo_puts_back_the_corona_the_entity_had(server: MtaSandbox) -> None:
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(
        server, player, {"showCorona": True, "coronaColor": "#ff8000"}
    )

    write_metadata(
        server, player, {"showCorona": False, "coronaColor": "#0080ff"}
    )
    assert server.eval("function() return ANKIGTA.Store.undo() end")() is not False

    row = snapshot_row(server, player)["metadata"]
    assert row["showCorona"] is True
    assert row["coronaColor"] == "#ff8000"


def test_an_undo_journalled_before_the_rename_still_means_a_corona(
    server: MtaSandbox,
) -> None:
    """Change History is JSON on disk, so a row written before `showRadius`
    became `showCorona` still says the old word -- and it is exactly the rows
    that predate an upgrade that Undo exists to put back."""
    seed_entity(server)
    player = server.add_study_player()
    write_metadata(server, player, {"showCorona": True})
    server.connection.raw.execute(
        "UPDATE change_history SET before_json = REPLACE("
        " before_json, 'showCorona', 'showRadius')"
    )
    server.connection.raw.execute(
        "UPDATE change_history SET after_json = REPLACE("
        " after_json, 'showCorona', 'showRadius')"
    )
    server.connection.raw.commit()

    assert server.eval("function() return ANKIGTA.Store.redo() end")() is not None
    assert server.eval("function() return ANKIGTA.Store.undo() end")() is not False
    assert server.eval("function() return ANKIGTA.Store.redo() end")() is not False

    assert snapshot_row(server, player)["metadata"]["showCorona"] is True


def test_nothing_in_the_resource_asks_for_a_string_called_draw_always() -> None:
    """A key with no words behind it renders as its own name, which is how a
    removed string shows up on screen as `f7.drawAlways`."""
    asked = set()
    for script in resource_scripts():
        asked |= named_keys(script)
    page = (
        REPO_ROOT / "mta" / "ankigta" / "client" / "panel" / "index.html"
    ).read_text(encoding="utf-8")

    assert "f7.drawAlways" not in asked
    assert "f7.showRadius" not in asked
    assert "drawAlways" not in page
    assert "showRadius" not in page
