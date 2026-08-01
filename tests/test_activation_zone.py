"""Ticket 22 — Activation Zone and automatic opening.

The rules that matter are about restraint: what cancels a countdown, what
refuses to open at all, and what an already-open card is allowed to ignore.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


UUID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def activation() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.load("shared/nearest.lua")
    sandbox.load("client/activation.lua")
    try:
        yield sandbox
    finally:
        sandbox.close()


def configure(sandbox: MtaSandbox, **settings: Any) -> Any:
    return sandbox.eval(
        """
        function(radius, delay, speed)
            local settings = {}
            if radius ~= nil then settings.defaultRadius = radius end
            if delay ~= nil then settings.delaySeconds = delay end
            if speed ~= nil then settings.maxSpeedKmh = speed end
            return ANKIGTA.Activation.configure(settings)
        end
        """
    )(
        settings.get("default_radius"),
        settings.get("delay_seconds"),
        settings.get("max_speed"),
    )


def update(
    sandbox: MtaSandbox,
    now: float,
    *,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    interior: int = 0,
    dimension: int = 0,
    speed: float = 0.0,
    review_open: bool = False,
    candidates: list[dict[str, Any]] | None = None,
) -> Any:
    lua_candidates = sandbox.lua.table_from(
        [sandbox.lua.table_from(item) for item in (candidates or [])]
    )
    player = sandbox.lua.table_from(
        {
            "x": x,
            "y": y,
            "z": z,
            "interior": interior,
            "dimension": dimension,
            "speedKmh": speed,
            "reviewOpen": review_open,
        }
    )
    return sandbox.eval(
        "function(now, player, candidates)"
        " return ANKIGTA.Activation.update(now, player, candidates) end"
    )(now, player, lua_candidates)


def entity(
    entity_id: str = "e1",
    *,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    radius: float = 3.0,
    interior: int = 0,
    dimension: int = 0,
    eligible: bool = True,
    present: bool = True,
) -> dict[str, Any]:
    return {
        "mapId": "m1",
        "entityId": entity_id,
        "x": x,
        "y": y,
        "z": z,
        "radius": radius,
        "interior": interior,
        "dimension": dimension,
        "eligible": eligible,
        "present": present,
    }


# --- settings ----------------------------------------------------------------


def test_a_new_entity_inherits_the_current_global_radius(
    activation: MtaSandbox,
) -> None:
    assert activation.eval("ANKIGTA.Activation.radiusForNewEntity()") == 3

    configure(activation, default_radius=7.5)

    assert activation.eval("ANKIGTA.Activation.radiusForNewEntity()") == 7.5


@pytest.mark.parametrize("radius", [0.5, 3, 7.5, 50])
def test_radii_on_the_step_within_range_are_accepted(
    activation: MtaSandbox,
    radius: float,
) -> None:
    assert activation.eval(
        "function(r) return ANKIGTA.Activation.validRadius(r) end"
    )(radius) is True


@pytest.mark.parametrize(
    ("radius", "reason"),
    [
        (0, "radius_out_of_range"),
        (0.4, "radius_out_of_range"),
        (50.5, "radius_out_of_range"),
        (200, "radius_out_of_range"),
        (1.3, "radius_not_on_step"),
        ("abc", "radius_not_a_number"),
    ],
)
def test_an_invalid_radius_is_rejected_never_clamped(
    activation: MtaSandbox,
    radius: Any,
    reason: str,
) -> None:
    ok, why = activation.eval(
        "function(r) return ANKIGTA.Activation.validRadius(r) end"
    )(radius)

    assert ok is False
    assert why == reason
    # Rejection, not correction: a silently clamped 200 would leave the user
    # with a zone they never chose.
    assert activation.eval("ANKIGTA.Activation.radiusForNewEntity()") == 3


@pytest.mark.parametrize("delay", [0, 0.25, 1, 12.34, 60])
def test_delays_within_range_and_precision_are_accepted(
    activation: MtaSandbox,
    delay: float,
) -> None:
    assert activation.eval(
        "function(d) return ANKIGTA.Activation.validDelay(d) end"
    )(delay) is True


@pytest.mark.parametrize("delay", [-1, 60.5, 1.234])
def test_an_invalid_delay_is_rejected(activation: MtaSandbox, delay: float) -> None:
    ok, _reason = activation.eval(
        "function(d) return ANKIGTA.Activation.validDelay(d) end"
    )(delay)
    assert ok is False


# --- opening -----------------------------------------------------------------


def test_a_card_opens_after_the_delay_inside_the_zone(
    activation: MtaSandbox,
) -> None:
    candidates = [entity(x=1.0)]

    assert update(activation, 0.0, candidates=candidates) is False
    assert update(activation, 0.5, candidates=candidates) is False

    opened = update(activation, 1.0, candidates=candidates)
    assert opened is not False
    assert opened["entityId"] == "e1"


def test_a_zero_delay_opens_on_the_first_observation(
    activation: MtaSandbox,
) -> None:
    configure(activation, delay_seconds=0)

    opened = update(activation, 0.0, candidates=[entity(x=1.0)])

    assert opened is not False


def test_leaving_every_zone_cancels_the_countdown(activation: MtaSandbox) -> None:
    candidates = [entity(x=1.0)]
    update(activation, 0.0, candidates=candidates)
    assert activation.eval("ANKIGTA.Activation.pending()") is not False

    update(activation, 0.5, x=100.0, candidates=candidates)

    assert activation.eval("ANKIGTA.Activation.pending()") is False
    # Returning restarts the clock rather than resuming it.
    update(activation, 0.6, candidates=candidates)
    assert update(activation, 1.0, candidates=candidates) is False


def test_the_nearest_entity_is_recalculated_during_the_countdown(
    activation: MtaSandbox,
) -> None:
    far = entity("far", x=2.5)
    near = entity("near", x=0.5)

    update(activation, 0.0, candidates=[far])
    # A closer zone appears; it takes over the countdown.
    update(activation, 0.5, candidates=[far, near])
    opened = update(activation, 1.6, candidates=[far, near])

    assert opened is not False
    assert opened["entityId"] == "near"


def test_retargeting_restarts_the_clock(activation: MtaSandbox) -> None:
    far = entity("far", x=2.5)
    near = entity("near", x=0.5)

    update(activation, 0.0, candidates=[far])
    update(activation, 0.9, candidates=[far, near])

    # Walking past one zone into another must not open the second instantly.
    assert update(activation, 1.0, candidates=[far, near]) is False


# --- refusals ----------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"eligible": False},  # pending, missing, unavailable or excluded
        {"present": False},  # runtime instance destroyed or unstreamed
    ],
)
def test_an_ineligible_entity_never_opens(
    activation: MtaSandbox,
    kwargs: dict[str, Any],
) -> None:
    candidates = [entity(x=0.5, **kwargs)]

    for now in (0.0, 1.0, 2.0, 5.0):
        assert update(activation, now, candidates=candidates) is False


def test_a_destroyed_runtime_instance_cancels_without_deleting_the_link(
    activation: MtaSandbox,
) -> None:
    present = [entity(x=0.5)]
    update(activation, 0.0, candidates=present)

    gone = [entity(x=0.5, present=False)]
    assert update(activation, 0.5, candidates=gone) is False
    assert activation.eval("ANKIGTA.Activation.pending()") is False
    # The link is untouched: the candidate is still supplied, just not present.
    assert update(activation, 1.0, candidates=present) is False


def test_a_zone_outside_the_current_interior_does_not_activate(
    activation: MtaSandbox,
) -> None:
    candidates = [entity(x=0.5, interior=3)]

    for now in (0.0, 1.0, 2.0):
        assert update(activation, now, interior=0, candidates=candidates) is False


def test_a_zone_in_another_dimension_does_not_activate(
    activation: MtaSandbox,
) -> None:
    candidates = [entity(x=0.5, dimension=17)]

    for now in (0.0, 1.0, 2.0):
        assert update(activation, now, dimension=0, candidates=candidates) is False


def test_changing_interior_cancels_a_pending_opening(
    activation: MtaSandbox,
) -> None:
    candidates = [entity(x=0.5)]
    update(activation, 0.0, candidates=candidates)

    assert update(activation, 0.5, interior=4, candidates=candidates) is False
    assert activation.eval("ANKIGTA.Activation.pending()") is False


def test_the_speed_gate_blocks_and_is_always_active(activation: MtaSandbox) -> None:
    configure(activation, max_speed=20)
    candidates = [entity(x=0.5)]

    update(activation, 0.0, speed=5, candidates=candidates)
    assert update(activation, 0.5, speed=80, candidates=candidates) is False
    assert activation.eval("ANKIGTA.Activation.pending()") is False


def test_a_zero_speed_limit_requires_a_complete_stop(
    activation: MtaSandbox,
) -> None:
    configure(activation, max_speed=0, delay_seconds=0)
    candidates = [entity(x=0.5)]

    assert update(activation, 0.0, speed=0.5, candidates=candidates) is False
    assert update(activation, 1.0, speed=0, candidates=candidates) is not False


def test_the_default_speed_limit_does_not_get_in_the_way(
    activation: MtaSandbox,
) -> None:
    candidates = [entity(x=0.5)]

    update(activation, 0.0, speed=300, candidates=candidates)
    assert update(activation, 1.0, speed=300, candidates=candidates) is not False


def test_an_open_review_is_never_interrupted(activation: MtaSandbox) -> None:
    candidates = [entity(x=0.5)]

    for now in (0.0, 1.0, 5.0):
        assert (
            update(activation, now, review_open=True, candidates=candidates) is False
        )


def test_activation_resumes_after_the_review_closes(
    activation: MtaSandbox,
) -> None:
    candidates = [entity(x=0.5)]
    update(activation, 0.0, review_open=True, candidates=candidates)

    update(activation, 1.0, candidates=candidates)
    assert update(activation, 2.0, candidates=candidates) is not False


# --- a total order over candidates -------------------------------------------
#
# On a 5,000-link fixture, two entities at exactly the same distance is an
# ordinary occurrence rather than a corner case. A strict `<` against the
# running best resolves it by whichever candidate the server's snapshot
# happened to put first, which makes the resulting report unreproducible.


def test_equidistant_candidates_resolve_the_same_way_in_either_order(
    activation: MtaSandbox,
) -> None:
    configure(activation, delay_seconds=0)
    left = entity("bbb", x=-1.0)
    right = entity("aaa", x=1.0)

    forwards = update(activation, 0.0, candidates=[left, right])
    activation.eval("ANKIGTA.Activation.cancel()")
    backwards = update(activation, 1.0, candidates=[right, left])

    assert forwards is not False
    assert backwards is not False
    assert forwards["entityId"] == backwards["entityId"]


def test_the_tie_break_is_the_map_entity_identity_not_the_snapshot_order(
    activation: MtaSandbox,
) -> None:
    configure(activation, delay_seconds=0)
    # Same distance, same map: the smaller Map Entity id is the specified
    # winner, so the choice can be stated in a bug report and reproduced.
    first = entity("zzz", x=1.0)
    second = entity("aaa", y=1.0)

    opened = update(activation, 0.0, candidates=[first, second])

    assert opened["entityId"] == "aaa"


def test_entities_from_different_maps_tie_break_on_the_map_id_first(
    activation: MtaSandbox,
) -> None:
    configure(activation, delay_seconds=0)
    later = entity("aaa", x=1.0)
    later["mapId"] = "m2"
    earlier = entity("zzz", y=1.0)
    earlier["mapId"] = "m1"

    opened = update(activation, 0.0, candidates=[later, earlier])

    assert opened["mapId"] == "m1"
    assert opened["entityId"] == "zzz"


def test_a_strictly_nearer_candidate_still_beats_a_smaller_identity(
    activation: MtaSandbox,
) -> None:
    configure(activation, delay_seconds=0)
    far = entity("aaa", x=2.0)
    near = entity("zzz", x=0.5)

    opened = update(activation, 0.0, candidates=[far, near])

    assert opened["entityId"] == "zzz"


def test_an_observation_stopped_by_a_gate_does_not_walk_the_world(
    activation: MtaSandbox,
) -> None:
    """The gates are cheap; the world is not.

    An open card and a speeding player both mean nothing may open, whatever is
    around. Measuring every streamed Spatial Link first and then discarding the
    answer is a full scan per observation for a decision already made — and
    this runs against the whole streamed world, inside the frame budget the
    HUD and the Next Card Indicator share.

    Counted rather than timed: what is asserted is that the entities are not
    looked at at all, which no duration can establish.
    """
    build = activation.eval(
        """
        function(n, uuid, reads)
            local list = {}
            for index = 1, n do
                local fields = {
                    mapId = "m1",
                    entityId = "e" .. index,
                    cardIdentity = {collectionUuid = uuid, cardId = index},
                    x = 1.0, y = 0.0, z = 0.0,
                    interior = 0, dimension = 0,
                    eligible = true, present = true, radius = 3.0,
                }
                list[index] = setmetatable({}, {
                    __index = function(_, key)
                        reads[key] = (reads[key] or 0) + 1
                        return fields[key]
                    end,
                })
            end
            return list
        end
        """
    )
    reads = activation.eval("{}")
    candidates = build(200, UUID, reads)
    observe = activation.eval(
        """
        function(now, candidates, reviewOpen, speed)
            return ANKIGTA.Activation.update(now, {
                x = 0.0, y = 0.0, z = 0.0,
                interior = 0, dimension = 0,
                speedKmh = speed,
                reviewOpen = reviewOpen,
            }, candidates)
        end
        """
    )

    # An ordinary observation does look, or it could not choose anything.
    assert observe(0.0, candidates, False, 0) is False
    assert reads["eligible"] == 200
    for key in list(reads.keys()):
        reads[key] = 0

    assert observe(1.0, candidates, True, 0) is False
    assert observe(2.0, candidates, False, 99999) is False

    assert {key: value for key, value in reads.items() if value} == {}
