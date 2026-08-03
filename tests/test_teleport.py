"""Ticket 25 — teleport and Runtime Instance lifecycle.

Two rules carry this ticket. The teleport target is one consistent snapshot —
position, interior and dimension all from the same source — because mixing a
live position with an authored interior would drop the player somewhere that
exists in neither. And ANKIGTA observes the instance lifecycle without owning
it: it never respawns anything (ADR 0004), and it never searches for a safe
landing point (ADR 0005).
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


@pytest.fixture
def teleport() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.load("shared/entity_types.lua")
    sandbox.load("server/teleport.lua")
    try:
        yield sandbox
    finally:
        sandbox.close()


AUTHORED = {
    "authoredX": 10.5,
    "authoredY": -20.25,
    "authoredZ": 4.75,
    "interior": 3,
    "dimension": 17,
}


def record(sandbox: MtaSandbox, **overrides: Any) -> Any:
    values = dict(AUTHORED)
    values.update(overrides)
    return sandbox.lua.table_from(values)


def instance(
    sandbox: MtaSandbox,
    *,
    x: float = 100.0,
    y: float = 200.0,
    z: float = 30.0,
    interior: int = 0,
    dimension: int = 0,
    element_type: str = "object",
) -> Any:
    element = sandbox.lua.table_from(
        {
            "__element": True,
            "type": element_type,
            "x": x,
            "y": y,
            "z": z,
            "interior": interior,
            "dimension": dimension,
        }
    )
    return element


def resolve(sandbox: MtaSandbox, mapped: Any, element: Any = None) -> Any:
    return sandbox.eval(
        "function(record, element)"
        " return ANKIGTA.Teleport.resolveTarget(record, element) end"
    )(mapped, element if element is not None else False)


# --- target resolution -------------------------------------------------------


def test_an_available_instance_supplies_the_whole_snapshot(
    teleport: MtaSandbox,
) -> None:
    target = resolve(teleport, record(teleport), instance(teleport, interior=5, dimension=9))

    assert target["source"] == "runtime"
    assert (target["x"], target["y"], target["z"]) == (100.0, 200.0, 30.0)
    assert target["interior"] == 5
    assert target["dimension"] == 9


def test_a_missing_instance_falls_back_to_the_authored_snapshot(
    teleport: MtaSandbox,
) -> None:
    target = resolve(teleport, record(teleport), False)

    assert target["source"] == "authored"
    assert (target["x"], target["y"], target["z"]) == (10.5, -20.25, 4.75)
    assert target["interior"] == 3
    assert target["dimension"] == 17


def test_a_destroyed_instance_falls_back_to_the_authored_snapshot(
    teleport: MtaSandbox,
) -> None:
    element = instance(teleport)
    teleport.eval("function(e) destroyElement(e) end")(element)

    target = resolve(teleport, record(teleport), element)

    assert target["source"] == "authored"
    assert target["interior"] == 3


def test_the_snapshot_never_mixes_live_position_with_authored_context(
    teleport: MtaSandbox,
) -> None:
    """The race this guards against would land the player nowhere real."""
    element = instance(teleport, x=100.0, interior=5, dimension=9)
    # The element disappears part-way through reading it.
    teleport.vanish_after_position_read = element

    target = resolve(teleport, record(teleport), element)

    assert target["source"] == "authored"
    assert (target["x"], target["y"], target["z"]) == (10.5, -20.25, 4.75)
    assert target["interior"] == 3
    assert target["dimension"] == 17


def test_an_unreadable_instance_falls_back_wholly(teleport: MtaSandbox) -> None:
    element = instance(teleport)
    teleport.position_read_fails = True

    target = resolve(teleport, record(teleport), element)

    assert target["source"] == "authored"
    assert target["interior"] == 3


# --- teleporting -------------------------------------------------------------


def perform(sandbox: MtaSandbox, player: Any, target: Any) -> Any:
    return sandbox.eval(
        "function(player, target)"
        " return ANKIGTA.Teleport.moveTo(player, target) end"
    )(player, target)


def player(sandbox: MtaSandbox) -> Any:
    return sandbox.lua.table_from(
        {"__element": True, "type": "player", "x": 0.0, "y": 0.0, "z": 0.0}
    )


def test_an_on_foot_player_is_moved_with_the_whole_snapshot(
    teleport: MtaSandbox,
) -> None:
    subject = player(teleport)
    target = resolve(teleport, record(teleport), False)

    assert perform(teleport, subject, target) is True

    moved = teleport.moved[-1]
    assert moved["type"] == "player"
    assert moved["position"] == (10.5, -20.25, 4.75)
    assert moved["interior"] == 3
    assert moved["dimension"] == 17


def test_an_occupied_vehicle_and_every_passenger_move_together(
    teleport: MtaSandbox,
) -> None:
    subject = player(teleport)
    vehicle = teleport.lua.table_from(
        {"__element": True, "type": "vehicle", "name": "car"}
    )
    passenger = teleport.lua.table_from(
        {"__element": True, "type": "player", "name": "passenger"}
    )
    teleport.occupied_vehicle = vehicle
    teleport.vehicle_occupants = {0: subject, 2: passenger}

    target = resolve(teleport, record(teleport), False)
    perform(teleport, subject, target)

    kinds = [item["type"] for item in teleport.moved]
    assert "vehicle" in kinds, "the vehicle itself must move"
    # Every occupant follows into the same interior and dimension.
    assert all(item["interior"] == 3 for item in teleport.moved)
    assert all(item["dimension"] == 17 for item in teleport.moved)
    assert len(teleport.moved) >= 3


def teleport_source() -> str:
    from pathlib import Path

    return (
        Path(__file__).resolve().parents[1]
        / "mta"
        / "ankigta"
        / "server"
        / "teleport.lua"
    ).read_text(encoding="utf-8")


def test_teleport_makes_no_attempt_to_find_a_safe_landing_point() -> None:
    """ADR 0005: water, empty space, collision and vehicle interiors are fine."""
    source = teleport_source()

    for forbidden in (
        "processLineOfSight",
        "getGroundPosition",
        "isLineOfSightClear",
        "getWaterLevel",
    ):
        assert forbidden not in source, f"teleport must not call {forbidden}"


def test_ankigta_never_respawns_or_recreates_an_entity() -> None:
    """ADR 0004: respawn belongs to the map or the resource that made it."""
    source = teleport_source()

    for forbidden in (
        "createObject",
        "createVehicle",
        "createPed",
        "respawnVehicle",
    ):
        assert forbidden not in source, f"teleport must not call {forbidden}"


# --- lifecycle ---------------------------------------------------------------


def availability(sandbox: MtaSandbox, element: Any) -> Any:
    return sandbox.eval(
        "function(e) return ANKIGTA.Teleport.runtimeAvailable(e) end"
    )(element)


def test_destruction_removes_availability_only(teleport: MtaSandbox) -> None:
    element = instance(teleport)
    assert availability(teleport, element) is True

    teleport.eval("function(e) destroyElement(e) end")(element)

    assert availability(teleport, element) is False
    # The record is untouched, so the Spatial Link survives.
    target = resolve(teleport, record(teleport), element)
    assert target["source"] == "authored"


def world_entity(
    sandbox: MtaSandbox,
    entity_id: str,
    *,
    map_id: str = "m1",
    x: float = 100.0,
    element_type: str = "object",
) -> Any:
    element = sandbox.lua.table_from(
        {
            "__element": True,
            "type": element_type,
            "x": x,
            "y": 200.0,
            "z": 30.0,
            "interior": 0,
            "dimension": 0,
            "ankigtaEntityId": entity_id,
            "ankigtaMapId": map_id,
        }
    )
    sandbox.world_elements.append(element)
    return element


def find(sandbox: MtaSandbox, map_id: str, entity_id: str) -> Any:
    return sandbox.eval(
        "function(m, e) return ANKIGTA.Teleport.findRuntimeInstance(m, e) end"
    )(map_id, entity_id)


def test_a_reappearing_instance_with_the_same_identity_is_found_again(
    teleport: MtaSandbox,
) -> None:
    """ADR 0004: the map brings it back, and ANKIGTA recognises it by ID."""
    original = world_entity(teleport, "ticket25-entity")
    assert find(teleport, "m1", "ticket25-entity") is not False

    teleport.eval("function(e) destroyElement(e) end")(original)
    assert find(teleport, "m1", "ticket25-entity") is False
    # Availability is gone, so the authored snapshot is used meanwhile.
    assert resolve(teleport, record(teleport), original)["source"] == "authored"

    # A different element object, same persistent identity.
    world_entity(teleport, "ticket25-entity", x=250.0)

    found = find(teleport, "m1", "ticket25-entity")
    assert found is not False
    assert resolve(teleport, record(teleport), found)["source"] == "runtime"
    assert resolve(teleport, record(teleport), found)["x"] == 250.0


def test_a_different_entity_id_is_not_matched(teleport: MtaSandbox) -> None:
    world_entity(teleport, "ticket25-entity")

    assert find(teleport, "m1", "some-other-entity") is False


def test_teleporting_to_a_map_entity_resolves_its_instance_first(
    teleport: MtaSandbox,
) -> None:
    world_entity(teleport, "ticket25-entity", x=250.0)
    subject = player(teleport)

    ok, source = teleport.eval(
        "function(p, r) return ANKIGTA.Teleport.toMapEntity(p, r) end"
    )(subject, record(teleport, mapId="m1", entityId="ticket25-entity"))

    assert ok is True
    assert source == "runtime"
    assert teleport.moved[-1]["position"][0] == 250.0


def test_teleporting_to_a_missing_entity_uses_the_authored_snapshot(
    teleport: MtaSandbox,
) -> None:
    subject = player(teleport)

    ok, source = teleport.eval(
        "function(p, r) return ANKIGTA.Teleport.toMapEntity(p, r) end"
    )(subject, record(teleport, mapId="m1", entityId="ticket25-entity"))

    assert ok is True
    assert source == "authored"
    assert teleport.moved[-1]["position"] == (10.5, -20.25, 4.75)


def test_every_passenger_gets_the_interior_not_just_the_vehicle(
    teleport: MtaSandbox,
) -> None:
    """MTA propagates a vehicle's dimension to occupants, but not its interior.

    Verified in CStaticFunctionDefinitions::SetElementDimension, which loops the
    vehicle's seats, against SetElementInterior, which does not. A passenger
    left in interior 0 would drop out of the world.
    """
    subject = player(teleport)
    vehicle = teleport.lua.table_from(
        {"__element": True, "type": "vehicle", "name": "car"}
    )
    passenger = teleport.lua.table_from(
        {"__element": True, "type": "player", "name": "passenger"}
    )
    teleport.occupied_vehicle = vehicle
    teleport.vehicle_occupants = {0: subject, 2: passenger}

    perform(teleport, subject, resolve(teleport, record(teleport), False))

    by_name = {entry["key"][1]: entry for entry in teleport.moved}
    assert by_name["passenger"]["interior"] == 3
    assert by_name["passenger"]["dimension"] == 17


def test_the_driver_in_seat_zero_is_not_skipped(teleport: MtaSandbox) -> None:
    """MTA keys occupants by seat from 0 and omits empty seats.

    Verified in CLuaVehicleDefs::GetVehicleOccupants, which loops
    `for ucSeat = 0; ucSeat <= ucMaxPassengers` and only sets a key when that
    seat holds a ped. `ipairs` would start at 1 -- skipping the driver, who is
    the teleporting player -- and stop at the first gap.
    """
    driver = player(teleport)
    vehicle = teleport.lua.table_from(
        {"__element": True, "type": "vehicle", "name": "car"}
    )
    rear = teleport.lua.table_from(
        {"__element": True, "type": "player", "name": "rear"}
    )
    teleport.occupied_vehicle = vehicle
    # Driver in seat 0, nobody in seat 1, a passenger in seat 2.
    teleport.vehicle_occupants = {0: driver, 2: rear}

    perform(teleport, driver, resolve(teleport, record(teleport), False))

    by_name = {entry["key"][1]: entry for entry in teleport.moved}
    assert by_name["player"]["interior"] == 3, "the driver must not be skipped"
    assert by_name["rear"]["interior"] == 3, "a gap must not stop iteration"
