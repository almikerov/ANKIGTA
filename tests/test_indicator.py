"""Ticket 23 — the Next Card Indicator.

The queue is global; the indicator is not. It may only point at an instance
that is actually reachable, and only at one of them, and it must never turn
itself into an Activation Zone.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


UUID = "11111111-1111-4111-8111-111111111111"
OTHER_UUID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def indicator() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    # The HUD asks the layout manager where it goes (ticket 28), so the modules
    # it is declared after in meta.xml load with it.
    sandbox.load("shared/settings.lua")
    sandbox.load("shared/nearest.lua")
    sandbox.load("client/layout.lua")
    sandbox.load("client/indicator.lua")
    try:
        yield sandbox
    finally:
        sandbox.close()


def set_mode(sandbox: MtaSandbox, mode: str) -> Any:
    return sandbox.eval("function(m) return ANKIGTA.Indicator.setMode(m) end")(mode)


def candidate(
    entity_id: str = "e1",
    *,
    card_id: int = 7,
    collection_uuid: str = UUID,
    x: float = 0.0,
    interior: int = 0,
    dimension: int = 0,
    eligible: bool = True,
    present: bool = True,
    has_zone: bool = False,
    radius: float = 3.0,
) -> dict[str, Any]:
    return {
        "mapId": "m1",
        "entityId": entity_id,
        "cardIdentity": {"collectionUuid": collection_uuid, "cardId": card_id},
        "x": x,
        "y": 0.0,
        "z": 0.0,
        "interior": interior,
        "dimension": dimension,
        "eligible": eligible,
        "present": present,
        "hasActivationZone": has_zone,
        "radius": radius,
    }


def plan(
    sandbox: MtaSandbox,
    candidates: list[dict[str, Any]],
    *,
    card_id: int = 7,
    collection_uuid: str = UUID,
    interior: int = 0,
    dimension: int = 0,
) -> Any:
    lua_candidates = sandbox.lua.table_from(
        [
            sandbox.lua.table_from(
                {
                    **item,
                    "cardIdentity": sandbox.lua.table_from(item["cardIdentity"]),
                }
            )
            for item in candidates
        ]
    )
    player = sandbox.lua.table_from(
        {"x": 0.0, "y": 0.0, "z": 0.0, "interior": interior, "dimension": dimension}
    )
    identity = sandbox.lua.table_from(
        {"collectionUuid": collection_uuid, "cardId": card_id}
    )
    return sandbox.eval(
        "function(p, c, i) return ANKIGTA.Indicator.plan(p, c, i) end"
    )(player, lua_candidates, identity)


# --- modes -------------------------------------------------------------------


def test_the_default_mode_shows_nothing(indicator: MtaSandbox) -> None:
    assert indicator.eval("ANKIGTA.Indicator.mode") == "none"

    result = plan(indicator, [candidate(x=5.0)])

    assert result["blip"] is False
    assert result["sphere"] is False


def test_there_are_exactly_three_modes_and_no_sphere_only(
    indicator: MtaSandbox,
) -> None:
    modes = indicator.eval("ANKIGTA.Indicator.availableModes()")
    values = {modes[key] for key in modes.keys()}

    assert values == {"sphere_and_minimap", "minimap_only", "none"}
    # A sphere with no minimap marker only helps someone already looking at it.
    assert set_mode(indicator, "sphere_only")[0] is False


def test_minimap_only_shows_a_blip_without_a_sphere(indicator: MtaSandbox) -> None:
    set_mode(indicator, "minimap_only")

    result = plan(indicator, [candidate(x=5.0)])

    assert result["blip"] is True
    assert result["sphere"] is False


def test_sphere_and_minimap_shows_both(indicator: MtaSandbox) -> None:
    set_mode(indicator, "sphere_and_minimap")

    result = plan(indicator, [candidate(x=5.0)])

    assert result["blip"] is True
    assert result["sphere"] is True


def test_an_invalid_mode_is_rejected(indicator: MtaSandbox) -> None:
    set_mode(indicator, "minimap_only")

    ok, reason = set_mode(indicator, "shout_loudly")

    assert ok is False
    assert reason == "invalid_indicator_mode"
    assert indicator.eval("ANKIGTA.Indicator.mode") == "minimap_only"


# --- target selection --------------------------------------------------------


def test_only_the_nearest_entity_for_the_card_is_marked(
    indicator: MtaSandbox,
) -> None:
    set_mode(indicator, "minimap_only")
    candidates = [
        candidate("far", x=40.0),
        candidate("near", x=5.0),
        candidate("middle", x=20.0),
    ]

    result = plan(indicator, candidates)

    assert result["entityId"] == "near"


def test_an_entity_for_a_different_card_is_not_marked(
    indicator: MtaSandbox,
) -> None:
    set_mode(indicator, "minimap_only")
    candidates = [candidate("other", card_id=99, x=1.0), candidate("target", x=50.0)]

    result = plan(indicator, candidates)

    assert result["entityId"] == "target"


def test_the_same_card_id_in_another_collection_is_not_the_next_card(
    indicator: MtaSandbox,
) -> None:
    set_mode(indicator, "minimap_only")
    candidates = [candidate("imposter", collection_uuid=OTHER_UUID, x=1.0)]

    result = plan(indicator, candidates)

    assert result["blip"] is False


@pytest.mark.parametrize(
    "kwargs",
    [{"eligible": False}, {"present": False}],
)
def test_an_unreachable_entity_is_not_marked(
    indicator: MtaSandbox,
    kwargs: dict[str, Any],
) -> None:
    set_mode(indicator, "sphere_and_minimap")

    result = plan(indicator, [candidate(x=1.0, **kwargs)])

    assert result["blip"] is False
    assert result["sphere"] is False


def test_the_indicator_obeys_the_current_world_context(
    indicator: MtaSandbox,
) -> None:
    """The queue is global, but a marker must point somewhere reachable."""
    set_mode(indicator, "minimap_only")
    elsewhere = [candidate("inside", interior=5, x=1.0)]

    assert plan(indicator, elsewhere, interior=0)["blip"] is False
    assert plan(indicator, elsewhere, interior=5)["blip"] is True

    other_dimension = [candidate("d17", dimension=17, x=1.0)]
    assert plan(indicator, other_dimension, dimension=0)["blip"] is False
    assert plan(indicator, other_dimension, dimension=17)["blip"] is True


def test_nothing_is_marked_when_the_next_card_is_not_in_this_world(
    indicator: MtaSandbox,
) -> None:
    set_mode(indicator, "sphere_and_minimap")

    result = plan(indicator, [])

    assert result["blip"] is False
    assert result["sphere"] is False


# --- the sphere is not an Activation Zone ------------------------------------


def test_the_indicator_leaves_the_activation_zone_untouched() -> None:
    """Run both modules together and check Activation's own state, rather than
    searching the indicator's source for a list of function names."""
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/nearest.lua")
        sandbox.load("client/activation.lua")
        sandbox.load("client/indicator.lua")
        sandbox.eval(
            "function() return ANKIGTA.Activation.configure({"
            "defaultRadius = 7.5, delaySeconds = 1}) end"
        )()
        # Put a countdown in flight so a careless indicator could disturb it.
        sandbox.eval(
            """
            function(uuid)
                ANKIGTA.Activation.update(0, {
                    x = 0, y = 0, z = 0, interior = 0, dimension = 0,
                    speedKmh = 0, reviewOpen = false,
                }, {{
                    mapId = "m1", entityId = "e1",
                    x = 1, y = 0, z = 0, radius = 7.5,
                    interior = 0, dimension = 0,
                    eligible = true, present = true,
                }})
            end
            """
        )(UUID)
        pending_before = sandbox.eval("ANKIGTA.Activation.pending()")
        assert pending_before is not False

        set_mode(sandbox, "sphere_and_minimap")
        plan(sandbox, [candidate(x=1.0, has_zone=True, radius=7.5)])
        sandbox.eval("function() return ANKIGTA.Indicator.refresh() end")()

        assert sandbox.eval("ANKIGTA.Activation.radiusForNewEntity()") == 7.5
        assert sandbox.eval("ANKIGTA.Activation.pending()") is not False
        assert sandbox.eval("ANKIGTA.Activation.settings.delaySeconds") == 1
    finally:
        sandbox.close()


def test_an_overlapping_zone_is_emphasized_rather_than_doubled(
    indicator: MtaSandbox,
) -> None:
    set_mode(indicator, "sphere_and_minimap")

    result = plan(indicator, [candidate(x=1.0, has_zone=True, radius=7.5)])

    assert result["sphere"] is True
    assert result["emphasized"] is True
    # One sphere, at the zone's own size, not a second one on top.
    assert result["sphereRadius"] == 7.5


def test_without_an_overlapping_zone_the_sphere_is_plain(
    indicator: MtaSandbox,
) -> None:
    set_mode(indicator, "sphere_and_minimap")

    result = plan(indicator, [candidate(x=1.0, has_zone=False)])

    assert result["sphere"] is True
    assert result["emphasized"] is False


def test_minimap_only_never_emphasizes_a_sphere_it_is_not_drawing(
    indicator: MtaSandbox,
) -> None:
    set_mode(indicator, "minimap_only")

    result = plan(indicator, [candidate(x=1.0, has_zone=True)])

    assert result["sphere"] is False
    assert result["sphereRadius"] is None


# --- rendering and wiring ----------------------------------------------------


def push(sandbox: MtaSandbox, event: str, *args: Any) -> None:
    sandbox.eval(
        "function(name, a, b) triggerEvent(name, resourceRoot, a, b) end"
    )(event, *args, *([None] * (2 - len(args))))


def test_statistics_arrive_from_the_server_and_reach_the_hud(
    indicator: MtaSandbox,
) -> None:
    counts = indicator.lua.table_from(
        {"total": 4, "new": 1, "learning": 1, "due": 1, "early": 1}
    )
    push(indicator, "ankigta:statistics", counts)

    state = indicator.eval("function() return ANKIGTA.Indicator.hudState() end")()

    assert state["counts"]["total"] == 4
    # The HUD draws even with the indicator off: the counts are not the marker.
    indicator.eval("function() return ANKIGTA.Indicator.render() end")()


def test_the_next_card_arrives_from_the_server_and_creates_a_blip(
    indicator: MtaSandbox,
) -> None:
    set_mode(indicator, "minimap_only")
    identity = indicator.lua.table_from({"collectionUuid": UUID, "cardId": 7})
    candidates = indicator.lua.table_from(
        [
            indicator.lua.table_from(
                {
                    **candidate(x=5.0),
                    "cardIdentity": indicator.lua.table_from(
                        {"collectionUuid": UUID, "cardId": 7}
                    ),
                }
            )
        ]
    )

    push(indicator, "ankigta:nextCard", identity, candidates)

    assert len(indicator.blips) == 1
    assert indicator.eval(
        "function() return ANKIGTA.Indicator.hudState() end"
    )()["hasBlip"] is True


def test_the_blip_goes_away_when_the_card_becomes_unreachable(
    indicator: MtaSandbox,
) -> None:
    set_mode(indicator, "minimap_only")
    identity = indicator.lua.table_from({"collectionUuid": UUID, "cardId": 7})

    def send(present: bool) -> None:
        push(
            indicator,
            "ankigta:nextCard",
            identity,
            indicator.lua.table_from(
                [
                    indicator.lua.table_from(
                        {
                            **candidate(x=5.0, present=present),
                            "cardIdentity": indicator.lua.table_from(
                                {"collectionUuid": UUID, "cardId": 7}
                            ),
                        }
                    )
                ]
            ),
        )

    send(True)
    assert indicator.eval(
        "function() return ANKIGTA.Indicator.hudState() end"
    )()["hasBlip"] is True

    send(False)
    assert indicator.eval(
        "function() return ANKIGTA.Indicator.hudState() end"
    )()["hasBlip"] is False


def test_the_blip_is_removed_when_the_resource_stops(indicator: MtaSandbox) -> None:
    set_mode(indicator, "minimap_only")
    push(
        indicator,
        "ankigta:nextCard",
        indicator.lua.table_from({"collectionUuid": UUID, "cardId": 7}),
        indicator.lua.table_from(
            [
                indicator.lua.table_from(
                    {
                        **candidate(x=5.0),
                        "cardIdentity": indicator.lua.table_from(
                            {"collectionUuid": UUID, "cardId": 7}
                        ),
                    }
                )
            ]
        ),
    )
    assert indicator.eval(
        "function() return ANKIGTA.Indicator.hudState() end"
    )()["hasBlip"] is True

    indicator.trigger("onClientResourceStop", None)

    assert indicator.eval(
        "function() return ANKIGTA.Indicator.hudState() end"
    )()["hasBlip"] is False


# --- a total order over candidates -------------------------------------------
#
# One card may be linked to several Map Entity, and two of them may sit at
# exactly the same distance. Which one carries the marker has to be a property
# of the world rather than of the order the snapshot arrived in.


def test_equidistant_targets_resolve_the_same_way_in_either_order(
    indicator: MtaSandbox,
) -> None:
    set_mode(indicator, "minimap_only")
    left = candidate("bbb", x=-4.0)
    right = candidate("aaa", x=4.0)

    forwards = plan(indicator, [left, right])
    backwards = plan(indicator, [right, left])

    assert forwards["entityId"] == backwards["entityId"]


def test_the_indicator_tie_break_is_the_map_entity_identity(
    indicator: MtaSandbox,
) -> None:
    set_mode(indicator, "minimap_only")

    result = plan(indicator, [candidate("zzz", x=4.0), candidate("aaa", x=-4.0)])

    assert result["entityId"] == "aaa"


def test_a_nearer_target_still_wins_against_a_smaller_identity(
    indicator: MtaSandbox,
) -> None:
    set_mode(indicator, "minimap_only")

    result = plan(indicator, [candidate("aaa", x=9.0), candidate("zzz", x=1.0)])

    assert result["entityId"] == "zzz"


def test_a_repeated_plan_over_the_same_world_only_looks_at_the_card_it_marks(
    indicator: MtaSandbox,
) -> None:
    """The marker is for one card; the world carries every other one.

    This runs on every rendered frame, inside the budget shared with the
    Activation Zone and the HUD. Walking every streamed Spatial Link to find
    the handful carrying this card was most of that budget spent rejecting
    entities that were never eligible for the marker.

    Counted rather than timed: a time is a property of the machine, and what is
    being asserted is that the entities carrying other cards are not looked at
    at all.
    """
    set_mode(indicator, "minimap_only")
    # Each candidate reports every field read on it, so the test can see which
    # of them the plan actually inspected — including the identity, which is
    # what a scan looking for the marked card reads first.
    world = indicator.eval(
        """
        function(n, uuid, reads)
            local list = {}
            for index = 1, n do
                local fields = {
                    mapId = "m1",
                    entityId = "other-" .. index,
                    cardIdentity = {collectionUuid = uuid, cardId = 1000 + index},
                }
                list[index] = setmetatable({}, {
                    __index = function(_, key)
                        reads[key] = (reads[key] or 0) + 1
                        return fields[key]
                    end,
                })
            end
            list[n + 1] = {
                mapId = "m1",
                entityId = "marked",
                cardIdentity = {collectionUuid = uuid, cardId = 7},
                x = 3.0, y = 0.0, z = 0.0,
                interior = 0, dimension = 0,
                eligible = true, present = true,
                hasActivationZone = false, radius = 3.0,
            }
            return list
        end
        """
    )
    reads = indicator.eval("{}")
    candidates = world(500, UUID, reads)
    player = indicator.lua.table_from(
        {"x": 0.0, "y": 0.0, "z": 0.0, "interior": 0, "dimension": 0}
    )
    identity = indicator.lua.table_from({"collectionUuid": UUID, "cardId": 7})
    run = indicator.eval(
        "function(p, c, i) return ANKIGTA.Indicator.plan(p, c, i) end"
    )

    assert run(player, candidates, identity)["entityId"] == "marked"
    # The first plan over a list it has not seen groups it by card, which reads
    # each candidate's identity once. What must not happen is the frame after.
    assert reads["cardIdentity"] == 500
    for key in list(reads.keys()):
        reads[key] = 0

    assert run(player, candidates, identity)["entityId"] == "marked"

    assert {key: value for key, value in reads.items() if value} == {}
