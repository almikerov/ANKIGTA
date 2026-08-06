"""Panel rebuild 08 — the map says which objects are ANKIGTA's.

Only the Next Card Indicator ever put anything on the map: one blip, for one
card. `Show every Map Entity on the map` is the other half, and the question it
answers is not "where are my objects" but "which of them are ready" — so it is
three states in three colours rather than one dot repeated.

What the harness cannot do is look at a radar. It can say which blips ANKIGTA
asked MTA for, where, in what colour and with what sprite, and that is what
every claim below is made of.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox


REPO_ROOT = Path(__file__).resolve().parents[1]

MAP_ID = "current-map-id"
UUID = "11111111-1111-4111-8111-111111111111"

#: The sprite the Next Card Indicator has always used. Anki-agnostic: the mark
#: means "next card", not a gameplay objective.
NEXT_CARD_SPRITE = 41


def manifest_scripts(*kinds: str) -> list[str]:
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

    Every client script in manifest order, then `onClientResourceStart`: the map
    is polled by a timer that only exists because the resource started, and the
    panel asks for its snapshot because the player was authorized.

    `client/spatial.lua` hands the indicator a candidate source of its own,
    filled by walking the streamed world. That is put back to the event's own
    candidates here, which is the other path the module supports and the one
    that lets a test say which card is next without building a world first --
    what the map reads off the indicator is which *entity* is marked, and that
    is the same either way.
    """
    sandbox = MtaSandbox()
    try:
        for script in manifest_scripts("shared", "client"):
            sandbox.load(script)
        sandbox.trigger("onClientResourceStart")
        sandbox.eval("function() ANKIGTA.Indicator.setCandidateSource(false) end")()
        yield sandbox
    finally:
        sandbox.close()


def authorize(sandbox: MtaSandbox) -> None:
    sandbox.eval(
        'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
    )()


def entry(
    *,
    entity_id: str = "object (gate) (1)",
    map_id: str = MAP_ID,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    dimension: int = 0,
    link_state: str = "Unlinked",
) -> dict[str, Any]:
    """One entry of the F7 snapshot, as `server/main.lua` builds it."""
    return {
        "mapEntity": {
            "mapId": map_id,
            "entityId": entity_id,
            "type": "object",
            "model": 1337,
            "map": {"resourceName": "current-map", "mapName": "Current Map"},
            "authored": {
                "position": {"x": x, "y": y, "z": z},
                "rotation": {"x": 0, "y": 0, "z": 0},
                "world": {"interior": 0, "dimension": dimension},
            },
        },
        "runtimeInstance": {"available": True, "referenceId": entity_id},
        "metadata": {"name": "", "entityTag": ""},
        "link": {"state": link_state},
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


def show_on_map(sandbox: MtaSandbox, value: bool = True) -> Any:
    """Through the store the player's own settings go through, not by poking
    the module: what has to work is the whole path from the panel down."""
    return sandbox.eval(
        'function(v) return ANKIGTA.ClientSettings.set("showEntitiesOnMap", v) end'
    )(value)


def set_mode(sandbox: MtaSandbox, mode: str) -> Any:
    return sandbox.eval(
        'function(m) return ANKIGTA.ClientSettings.set("indicatorMode", m) end'
    )(mode)


def next_card(
    sandbox: MtaSandbox,
    *,
    entity_id: str = "object (gate) (1)",
    map_id: str = MAP_ID,
    x: float = 0.0,
    card_id: int = 7,
) -> None:
    """The scheduler's choice, as the server announces it."""
    sandbox.eval(
        """
        function(identity, candidates)
            triggerEvent(
                "ankigta:nextCard", resourceRoot, identity, candidates
            )
        end
        """
    )(
        to_lua(sandbox, {"collectionUuid": UUID, "cardId": card_id}),
        to_lua(
            sandbox,
            [
                {
                    "mapId": map_id,
                    "entityId": entity_id,
                    "cardIdentity": {"collectionUuid": UUID, "cardId": card_id},
                    "x": x,
                    "y": 0.0,
                    "z": 0.0,
                    "interior": 0,
                    "dimension": 0,
                    "eligible": True,
                    "present": True,
                    "hasCorona": False,
                    "radius": 3.0,
                }
            ],
        ),
    )


def refresh(sandbox: MtaSandbox) -> Any:
    return sandbox.eval("function() return ANKIGTA.Indicator.refreshMap() end")()


def live_blips(sandbox: MtaSandbox) -> list[Any]:
    return [blip for blip in sandbox.blips if blip["__destroyed"] is not True]


def entity_blips(sandbox: MtaSandbox) -> list[Any]:
    """Every blip except the Next Card Indicator's own, told apart by sprite."""
    return [
        blip for blip in live_blips(sandbox) if blip["icon"] != NEXT_CARD_SPRITE
    ]


def appearance(sandbox: MtaSandbox, state: str) -> dict[str, Any]:
    look = sandbox.eval(
        "function(s) return ANKIGTA.Indicator.stateAppearance(s) end"
    )(state)
    assert look is not None, f"no appearance for {state}"
    return {str(key): look[key] for key in look.keys()}


def looks_like(blip: Any, look: dict[str, Any]) -> bool:
    return (
        blip["icon"] == look["icon"]
        and blip["red"] == look["red"]
        and blip["green"] == look["green"]
        and blip["blue"] == look["blue"]
        and blip["alpha"] == look["alpha"]
    )


def blip_limit(sandbox: MtaSandbox) -> int:
    return int(
        sandbox.eval("function() return ANKIGTA.Indicator.mapBlipLimit() end")()
    )


# --- the toggle is a toggle ---------------------------------------------------


def test_nothing_is_on_the_map_until_the_toggle_is_on(client: MtaSandbox) -> None:
    """It ships off: a world with hundreds of entities is a map with hundreds
    of blips, and that is the player's decision to make."""
    authorize(client)
    push_snapshot(client, [entry(), entry(entity_id="object (gate) (2)")])

    refresh(client)

    assert entity_blips(client) == []
    assert client.eval("ANKIGTA.Settings.default('showEntitiesOnMap')") is False


def test_the_toggle_puts_one_blip_on_every_map_entity_ankigta_knows(
    client: MtaSandbox,
) -> None:
    authorize(client)
    push_snapshot(
        client,
        [
            entry(entity_id="object (gate) (1)", x=10.0),
            entry(entity_id="object (gate) (2)", x=20.0),
            entry(entity_id="object (gate) (3)", x=30.0),
        ],
    )
    show_on_map(client)

    refresh(client)

    assert len(entity_blips(client)) == 3
    assert sorted(blip["x"] for blip in entity_blips(client)) == [10.0, 20.0, 30.0]


def test_turning_it_off_takes_the_blips_back_off_the_map(
    client: MtaSandbox,
) -> None:
    authorize(client)
    push_snapshot(client, [entry()])
    show_on_map(client)
    refresh(client)
    assert len(entity_blips(client)) == 1

    show_on_map(client, False)

    assert entity_blips(client) == []


def test_the_map_fills_in_without_f7_having_been_opened(
    client: MtaSandbox,
) -> None:
    """A mark that is a property of the world does not wait for a window, and a
    timer started when the resource started is what makes that true."""
    authorize(client)
    show_on_map(client)
    push_snapshot(client, [entry()])
    client.eval("function() ANKIGTA.Indicator.clearMap() end")()
    assert entity_blips(client) == []

    client.fire_timers()

    assert len(entity_blips(client)) == 1
    # And the panel never opened: nothing here is a browser.
    assert client.browsers == []


# --- which of them are ready --------------------------------------------------


def test_connected_disconnected_and_next_card_are_three_different_colours(
    client: MtaSandbox,
) -> None:
    """The question the map answers is which of them are ready, so the answer
    has to be readable without clicking anything."""
    colours = {
        tuple(
            appearance(client, state)[channel]
            for channel in ("red", "green", "blue")
        )
        for state in ("connected", "disconnected", "next_card")
    }

    assert len(colours) == 3


def test_an_entity_with_a_usable_link_reads_as_connected(
    client: MtaSandbox,
) -> None:
    authorize(client)
    push_snapshot(client, [entry(link_state="Active Spatial Link")])
    show_on_map(client)

    refresh(client)

    assert looks_like(entity_blips(client)[0], appearance(client, "connected"))


@pytest.mark.parametrize(
    "link_state",
    [
        "Unlinked",
        "Card missing",
        "Entity missing",
        "Pending Map Save",
        "Identity Collision",
    ],
)
def test_an_entity_ankigta_cannot_study_through_reads_as_disconnected(
    client: MtaSandbox, link_state: str
) -> None:
    """One answer rather than five. The map is being read to decide where to
    go, and "why is this one not ready" is the panel's question, not the map's.
    """
    authorize(client)
    push_snapshot(client, [entry(link_state=link_state)])
    show_on_map(client)

    refresh(client)

    assert looks_like(entity_blips(client)[0], appearance(client, "disconnected"))


def test_the_next_card_is_marked_as_the_next_card(client: MtaSandbox) -> None:
    authorize(client)
    push_snapshot(client, [entry(link_state="Active Spatial Link")])
    show_on_map(client)
    set_mode(client, "minimap_only")
    next_card(client)

    refresh(client)

    marks = live_blips(client)
    assert len(marks) == 1
    assert looks_like(marks[0], appearance(client, "next_card"))


def test_an_entity_that_is_both_the_next_card_and_connected_reads_as_next_card(
    client: MtaSandbox,
) -> None:
    """Next card wins: it is the more specific answer and it is the one the
    player is looking for. One mark on the spot, not two."""
    authorize(client)
    push_snapshot(
        client,
        [
            entry(entity_id="object (gate) (1)", link_state="Active Spatial Link"),
            entry(
                entity_id="object (gate) (2)",
                x=40.0,
                link_state="Active Spatial Link",
            ),
        ],
    )
    show_on_map(client)
    set_mode(client, "minimap_only")
    next_card(client, entity_id="object (gate) (1)")

    refresh(client)

    assert len(live_blips(client)) == 2
    chosen = [blip for blip in live_blips(client) if blip["x"] == 0.0]
    assert len(chosen) == 1
    assert looks_like(chosen[0], appearance(client, "next_card"))
    other = [blip for blip in live_blips(client) if blip["x"] == 40.0]
    assert looks_like(other[0], appearance(client, "connected"))


def test_an_entity_that_stops_being_the_next_card_goes_back_to_its_own_state(
    client: MtaSandbox,
) -> None:
    authorize(client)
    push_snapshot(client, [entry(link_state="Active Spatial Link")])
    show_on_map(client)
    set_mode(client, "minimap_only")
    next_card(client)
    refresh(client)
    assert looks_like(live_blips(client)[0], appearance(client, "next_card"))

    set_mode(client, "none")
    refresh(client)

    assert len(live_blips(client)) == 1
    assert looks_like(live_blips(client)[0], appearance(client, "connected"))


# --- the two settings are independent -----------------------------------------


@pytest.mark.parametrize("mode", ["none", "minimap_only", "beam_and_minimap"])
@pytest.mark.parametrize("on_map", [False, True])
def test_the_toggle_and_the_indicator_do_not_break_each_other(
    client: MtaSandbox, mode: str, on_map: bool
) -> None:
    """`indicatorMode` answers "how is the *next card* marked" about one
    entity; this answers "is the rest of the world marked at all". Neither is
    a value of the other, and neither may take the other's mark away.
    """
    authorize(client)
    push_snapshot(
        client,
        [
            entry(entity_id="object (gate) (1)", link_state="Active Spatial Link"),
            entry(entity_id="object (gate) (2)", x=40.0),
        ],
    )
    show_on_map(client, on_map)
    set_mode(client, mode)
    next_card(client, entity_id="object (gate) (1)")

    refresh(client)

    marks = live_blips(client)
    # The next card is marked whenever the indicator is set to mark it, whether
    # or not the rest of the world is on the map.
    marked_next = [
        blip
        for blip in marks
        if looks_like(blip, appearance(client, "next_card"))
    ]
    assert len(marked_next) == (0 if mode == "none" else 1)
    # And the rest of the world is on the map whenever the toggle says so,
    # whatever the indicator is doing.
    others = [blip for blip in marks if blip not in marked_next]
    assert len(others) == ((2 if mode == "none" else 1) if on_map else 0)


def test_the_beam_is_the_indicators_and_never_reaches_the_map(
    client: MtaSandbox,
) -> None:
    """The mark in the world and the mark on the map are two answers, and only
    one of them is what this toggle is about."""
    authorize(client)
    push_snapshot(client, [entry()])
    show_on_map(client)
    set_mode(client, "beam_and_minimap")
    next_card(client)
    refresh(client)

    client.trigger("onClientRender")

    assert client.drawn_material_lines_3d != []
    assert len(live_blips(client)) == 1


# --- blips are cheap but not free ---------------------------------------------


def test_the_stated_number_is_a_number_worth_stating(client: MtaSandbox) -> None:
    """The tests below take the limit from the module, so on its own a wrong
    number could not fail them. This is the range it has to be in, and neither
    end is arbitrary.

    GTA San Andreas has 175 radar trace slots in total -- `MAX_MARKERS` in
    `game_sa/CRadarSA.h` -- shared with the game's own icons and with every
    other resource, and `CRadarSA::GetFreeMarker` answers NULL rather than
    complaining once they are gone. So ANKIGTA takes a minority of them. Below a
    couple of dozen it would be hiding entities from a world small enough to
    show whole.
    """
    stated = blip_limit(client)

    assert 24 <= stated <= 87


def test_past_the_stated_number_the_nearest_are_the_ones_drawn(
    client: MtaSandbox,
) -> None:
    """Said rather than discovered. Nearest to the player, because the map is
    read to decide where to go next."""
    authorize(client)
    limit = blip_limit(client)
    client.player_position = (0.0, 0.0, 0.0)
    # Furthest first, so an implementation that simply took the first N would
    # keep exactly the wrong ones.
    push_snapshot(
        client,
        [
            entry(entity_id=f"object (gate) ({index})", x=float(1000 - index))
            for index in range(limit + 10)
        ],
    )
    show_on_map(client)

    refresh(client)

    drawn = entity_blips(client)
    assert len(drawn) == limit
    nearest = sorted(float(1000 - index) for index in range(limit + 10))[:limit]
    assert sorted(blip["x"] for blip in drawn) == nearest


def test_the_next_card_is_never_the_one_dropped(client: MtaSandbox) -> None:
    """It is the one mark the player is being sent to, so dropping it for being
    far away would drop the only reason they are looking."""
    authorize(client)
    limit = blip_limit(client)
    client.player_position = (0.0, 0.0, 0.0)
    entities = [
        entry(entity_id=f"object (gate) ({index})", x=float(index))
        for index in range(limit + 10)
    ]
    entities.append(
        entry(entity_id="far away", x=5000.0, link_state="Active Spatial Link")
    )
    push_snapshot(client, entities)
    show_on_map(client)
    set_mode(client, "minimap_only")
    next_card(client, entity_id="far away", x=5000.0)

    refresh(client)

    marked = [
        blip
        for blip in live_blips(client)
        if looks_like(blip, appearance(client, "next_card"))
    ]
    assert len(marked) == 1
    # And the cap still holds over everything ANKIGTA puts there.
    assert len(live_blips(client)) == limit


def test_walking_towards_them_changes_which_ones_are_drawn(
    client: MtaSandbox,
) -> None:
    """The set follows the player, so a blip dropped for distance comes back
    when the player is near enough for it to be worth having."""
    authorize(client)
    limit = blip_limit(client)
    client.player_position = (0.0, 0.0, 0.0)
    push_snapshot(
        client,
        [
            entry(entity_id=f"object (gate) ({index})", x=float(index * 10))
            for index in range(limit + 1)
        ],
    )
    show_on_map(client)
    refresh(client)
    furthest = float(limit * 10)
    assert furthest not in {blip["x"] for blip in entity_blips(client)}

    client.player_position = (furthest, 0.0, 0.0)
    refresh(client)

    assert furthest in {blip["x"] for blip in entity_blips(client)}


# --- what a blip is put on ----------------------------------------------------


def test_a_blip_is_drawn_for_an_entity_that_is_not_here(
    client: MtaSandbox,
) -> None:
    """The map is the one surface that can show a Map Entity the player cannot
    see, so it reads the authored position rather than a Runtime Instance's --
    an entity three districts away has no element here to read one off.

    Nothing in this test is streamed in: the world is empty.
    """
    authorize(client)
    push_snapshot(client, [entry(x=1500.0, y=-900.0, z=12.0)])
    show_on_map(client)

    refresh(client)

    blip = entity_blips(client)[0]
    assert (blip["x"], blip["y"], blip["z"]) == (1500.0, -900.0, 12.0)


def test_a_blip_carries_the_dimension_of_the_thing_it_marks(
    client: MtaSandbox,
) -> None:
    """MTA hides a blip whose dimension is not the player's
    (`CClientRadarMarker::RelateDimension`), so an entity in another dimension
    must not clutter the map of this one."""
    authorize(client)
    push_snapshot(client, [entry(dimension=17)])
    show_on_map(client)

    refresh(client)

    assert entity_blips(client)[0]["dimension"] == 17


def test_an_entity_with_no_position_is_not_put_on_the_map(
    client: MtaSandbox,
) -> None:
    """A stored record too damaged to draw, rather than a state to colour."""
    authorize(client)
    broken = entry()
    broken["mapEntity"]["authored"]["position"] = {}
    push_snapshot(client, [broken, entry(entity_id="object (gate) (2)", x=5.0)])
    show_on_map(client)

    refresh(client)

    assert len(entity_blips(client)) == 1
    assert entity_blips(client)[0]["x"] == 5.0


def test_a_row_hidden_by_the_filter_is_still_on_the_map(
    client: MtaSandbox,
) -> None:
    """A row hidden from a list is still a thing standing in the world, and
    hiding it must not take it off the map -- the same rule the coronas follow.
    """
    authorize(client)
    push_snapshot(
        client,
        [
            entry(entity_id="object (gate) (1)"),
            entry(entity_id="object (fence) (1)", x=25.0),
        ],
    )
    show_on_map(client)
    client.eval(
        """
        function(payload)
            triggerEvent("ankigta:panelAction", resourceRoot, "filter", payload)
        end
        """
    )(json.dumps({"text": "fence"}))

    refresh(client)

    assert len(entity_blips(client)) == 2


def test_a_blip_goes_when_ankigta_stops_knowing_the_entity(
    client: MtaSandbox,
) -> None:
    authorize(client)
    push_snapshot(
        client,
        [entry(entity_id="object (gate) (1)"), entry(entity_id="object (gate) (2)")],
    )
    show_on_map(client)
    refresh(client)
    assert len(entity_blips(client)) == 2

    push_snapshot(client, [entry(entity_id="object (gate) (1)")])
    refresh(client)

    assert len(entity_blips(client)) == 1


def test_stopping_the_resource_takes_every_blip_off_the_map(
    client: MtaSandbox,
) -> None:
    authorize(client)
    push_snapshot(client, [entry()])
    show_on_map(client)
    set_mode(client, "minimap_only")
    next_card(client)
    refresh(client)
    assert len(live_blips(client)) == 1

    client.trigger("onClientResourceStop")

    assert live_blips(client) == []


# --- reconciled rather than rebuilt -------------------------------------------


def test_a_blip_that_has_not_changed_is_left_exactly_as_it_is(
    client: MtaSandbox,
) -> None:
    """MTA destroys and re-creates every radar trace in ordering order whenever
    the list changes (`CClientRadarMarkerManager::OrderMarkers`), so replacing a
    blip four times a second would re-cut the whole map -- everybody's, not only
    ANKIGTA's."""
    authorize(client)
    push_snapshot(client, [entry()])
    show_on_map(client)
    refresh(client)
    first = entity_blips(client)[0]

    for _ in range(4):
        refresh(client)

    assert len(client.blips) == 1
    assert entity_blips(client) == [first]


def test_a_poll_that_finds_the_same_world_does_not_re_cut_the_map(
    client: MtaSandbox,
) -> None:
    """`setElementDimension` on a blip is not a value write.
    `CClientRadarMarker::SetDimension` goes through `RelateDimension`, which
    asks the manager to re-order -- destroying and re-creating every radar trace
    on the client, the game's own and every other resource's included -- whether
    or not the dimension is different. Four times a second, over sixty blips,
    that is the whole map being re-cut for nothing.
    """
    authorize(client)
    push_snapshot(
        client,
        [
            entry(entity_id="object (gate) (1)", dimension=17),
            entry(entity_id="object (gate) (2)", x=5.0),
        ],
    )
    show_on_map(client)
    refresh(client)
    client.dimension_writes.clear()

    for _ in range(4):
        refresh(client)

    assert [
        write for write in client.dimension_writes if write[0] == "blip"
    ] == []


def test_an_entity_that_moves_to_another_dimension_takes_its_blip_with_it(
    client: MtaSandbox,
) -> None:
    """The guard above is about repeating a write, not about skipping one."""
    authorize(client)
    push_snapshot(client, [entry(dimension=0)])
    show_on_map(client)
    refresh(client)

    push_snapshot(client, [entry(dimension=17)])
    refresh(client)

    assert entity_blips(client)[0]["dimension"] == 17


def test_a_blip_that_changes_state_is_recoloured_in_place(
    client: MtaSandbox,
) -> None:
    authorize(client)
    push_snapshot(client, [entry(link_state="Unlinked")])
    show_on_map(client)
    refresh(client)
    blip = entity_blips(client)[0]
    assert looks_like(blip, appearance(client, "disconnected"))

    push_snapshot(client, [entry(link_state="Active Spatial Link")])
    refresh(client)

    assert entity_blips(client) == [blip]
    assert looks_like(blip, appearance(client, "connected"))
    assert len(client.blips) == 1


def test_the_panel_does_not_re_read_the_world_because_of_its_own_blips(
    client: MtaSandbox,
) -> None:
    """A corona is a marker and a marker is one of the types a card can hang
    on, which is why the marks have to say which elements are theirs. A blip is
    none of those types, so this is a claim about the type list rather than
    about ownership -- and it is worth pinning, because the loop it would start
    is the same one: draw, re-read, decide, draw."""
    authorize(client)
    push_snapshot(client, [entry()])
    show_on_map(client)
    before = len(
        [e for e in client.recorder.server_events if e.name == "ankigta:requestF7"]
    )

    refresh(client)
    client.fire_timers()

    after = len(
        [e for e in client.recorder.server_events if e.name == "ankigta:requestF7"]
    )
    assert after == before
    assert len(entity_blips(client)) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
