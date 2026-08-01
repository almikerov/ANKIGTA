"""Ticket 31 — the world-polling that feeds the Activation Zone and the marker.

Tickets 22 and 23 built the decisions and left this half out, so in a running
resource nothing ever handed `Activation.update` a player position or a
candidate list. These tests drive the loop the way the game does: elements in
the world, a link set from the server, and a clock.

They assert on what the client asked the server for, never on what it called
internally: the whole point of this seam is that a card opens through the same
server-side path a manual opening uses.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


UUID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def client() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.load("shared/settings.lua")
    sandbox.load("shared/nearest.lua")
    sandbox.load("client/layout.lua")
    sandbox.load("client/activation.lua")
    sandbox.load("client/indicator.lua")
    sandbox.load("client/spatial.lua")
    try:
        yield sandbox
    finally:
        sandbox.close()


def link(
    entity_id: str = "e1",
    *,
    map_id: str = "m1",
    card_id: int = 7,
    radius: float = 3.0,
    show_radius: bool = False,
    eligible: bool = True,
) -> dict[str, Any]:
    return {
        "mapId": map_id,
        "entityId": entity_id,
        "cardIdentity": {"collectionUuid": UUID, "cardId": card_id},
        "radius": radius,
        "showRadius": show_radius,
        "eligible": eligible,
    }


def send_links(sandbox: MtaSandbox, links: list[dict[str, Any]]) -> None:
    sandbox.eval(
        """
        function(links)
            triggerEvent("ankigta:spatialCandidates", resourceRoot, links)
        end
        """
    )(
        sandbox.lua.table_from(
            [
                sandbox.lua.table_from(
                    {
                        **item,
                        "cardIdentity": sandbox.lua.table_from(item["cardIdentity"]),
                    }
                )
                for item in links
            ]
        )
    )


def send_next_card(
    sandbox: MtaSandbox,
    bearers: list[dict[str, str]],
    *,
    card_id: int = 7,
) -> None:
    sandbox.eval(
        """
        function(identity, bearers)
            triggerEvent("ankigta:nextCard", resourceRoot, identity, bearers)
        end
        """
    )(
        sandbox.lua.table_from({"collectionUuid": UUID, "cardId": card_id}),
        sandbox.lua.table_from(
            [sandbox.lua.table_from(bearer) for bearer in bearers]
        ),
    )


def tick(sandbox: MtaSandbox) -> Any:
    return sandbox.eval("function() return ANKIGTA.Spatial.tick() end")()


def configure(sandbox: MtaSandbox, **settings: Any) -> Any:
    return sandbox.eval(
        "function(s) return ANKIGTA.Activation.configure(s) end"
    )(sandbox.lua.table_from(settings))


def diagnostics(sandbox: MtaSandbox) -> dict[str, Any]:
    return dict(
        sandbox.to_python(
            sandbox.eval("function() return ANKIGTA.Spatial.diagnostics() end")()
        )
    )


def open_requests(sandbox: MtaSandbox) -> list[Any]:
    return [
        event
        for event in sandbox.recorder.server_events
        if event.name == "ankigta:requestSpatialOpen"
    ]


# --- the loop ----------------------------------------------------------------


def test_nothing_polls_until_the_server_says_what_to_watch(
    client: MtaSandbox,
) -> None:
    """A resource that starts polling on its own would run the scan for a
    player who has not begun studying."""
    assert diagnostics(client)["polling"] is False


def test_a_link_set_starts_the_poll_at_the_stated_cadence(
    client: MtaSandbox,
) -> None:
    client.add_world_element(x=0.0, ankigtaEntityId="e1")
    send_links(client, [link()])

    report = diagnostics(client)

    assert report["polling"] is True
    assert report["pollIntervalMs"] == 250
    timer = client.recorder.timers[-1]
    assert timer.interval_ms == 250
    # Zero repeats is MTA's "forever": a timer that stopped after one shot
    # would poll once and never again.
    assert timer.repeats == -1


def test_an_empty_link_set_stops_the_poll(client: MtaSandbox) -> None:
    """`Pause studying` empties the set, and the scan has to stop with it."""
    client.add_world_element(ankigtaEntityId="e1")
    send_links(client, [link()])

    send_links(client, [])

    assert diagnostics(client)["polling"] is False


def test_standing_in_a_zone_asks_the_server_to_open_that_card(
    client: MtaSandbox,
) -> None:
    client.add_world_element(x=1.0, ankigtaEntityId="e1")
    configure(client, delaySeconds=0)
    send_links(client, [link()])

    decision = client.to_python(tick(client))

    assert decision["entityId"] == "e1"
    requests = open_requests(client)
    assert len(requests) == 1
    assert requests[0].args[0] == "m1"
    assert requests[0].args[1] == "e1"
    assert client.to_python(requests[0].args[2]) == {
        "collectionUuid": UUID,
        "cardId": 7,
    }


def test_the_client_never_opens_the_card_itself(client: MtaSandbox) -> None:
    """There is one way into Review Mode, and the server owns it.

    A client that opened the card locally would be a second path, and it would
    skip Exact Card Admission on the way.
    """
    client.add_world_element(x=1.0, ankigtaEntityId="e1")
    configure(client, delaySeconds=0)
    send_links(client, [link()])

    tick(client)

    assert [event.name for event in client.recorder.local_events] == [
        "ankigta:spatialCandidates"
    ]


def test_an_unstreamed_instance_has_no_zone(client: MtaSandbox) -> None:
    client.add_world_element(x=1.0, streamed=False, ankigtaEntityId="e1")
    configure(client, delaySeconds=0)
    send_links(client, [link()])

    assert tick(client) is False
    assert diagnostics(client)["streamedInstances"] == 0
    assert diagnostics(client)["knownInstances"] == 1


def test_streaming_out_mid_countdown_cancels_the_opening(
    client: MtaSandbox,
) -> None:
    element = client.add_world_element(x=1.0, ankigtaEntityId="e1")
    configure(client, delaySeconds=60)
    send_links(client, [link()])
    tick(client)
    assert client.eval("function() return ANKIGTA.Activation.pending() end")()

    client.trigger("onClientElementStreamOut", element)
    tick(client)

    assert client.eval("function() return ANKIGTA.Activation.pending() end")() is False
    assert open_requests(client) == []


def test_the_zone_follows_the_current_position_not_the_authored_one(
    client: MtaSandbox,
) -> None:
    element = client.add_world_element(x=100.0, ankigtaEntityId="e1")
    configure(client, delaySeconds=0)
    send_links(client, [link()])
    assert tick(client) is False

    element["x"] = 1.0

    assert client.to_python(tick(client))["entityId"] == "e1"


def test_another_dimension_is_not_here(client: MtaSandbox) -> None:
    client.add_world_element(x=1.0, dimension=4, ankigtaEntityId="e1")
    configure(client, delaySeconds=0)
    send_links(client, [link()])

    assert tick(client) is False

    client.player_dimension = 4

    assert client.to_python(tick(client))["entityId"] == "e1"


def test_speed_is_read_from_the_world_and_gates_the_opening(
    client: MtaSandbox,
) -> None:
    """The gate is always applied; the observation has to carry a real speed
    for it to mean anything."""
    client.add_world_element(x=1.0, ankigtaEntityId="e1")
    configure(client, delaySeconds=0, maxSpeedKmh=30)
    send_links(client, [link()])
    # 0.5 units per physics step is 90 km/h.
    client.player_velocity = (0.5, 0.0, 0.0)

    assert tick(client) is False

    client.player_velocity = (0.0, 0.0, 0.0)

    assert client.to_python(tick(client))["entityId"] == "e1"


def test_the_speed_of_an_occupied_vehicle_is_the_speed_that_counts(
    client: MtaSandbox,
) -> None:
    """A passenger's own velocity is not what they are travelling at."""
    client.add_world_element(x=1.0, ankigtaEntityId="e1")
    configure(client, delaySeconds=0, maxSpeedKmh=30)
    send_links(client, [link()])
    client.occupied_vehicle = client.add_world_element(
        "vehicle", vx=0.5, ankigtaEntityId="car"
    )

    assert tick(client) is False


def test_an_open_review_stops_the_world_being_walked(client: MtaSandbox) -> None:
    client.add_world_element(x=1.0, ankigtaEntityId="e1")
    configure(client, delaySeconds=0)
    send_links(client, [link()])
    client.execute("function isReviewModeActive() return true end")

    assert tick(client) is False
    assert open_requests(client) == []


# --- the marker --------------------------------------------------------------


def test_the_marker_follows_the_bearing_entity_that_is_here(
    client: MtaSandbox,
) -> None:
    element = client.add_world_element(x=5.0, ankigtaEntityId="e1")
    send_links(client, [link()])
    send_next_card(client, [{"mapId": "m1", "entityId": "e1"}])
    client.eval("function() return ANKIGTA.Indicator.setMode('minimap_only') end")()

    plan = client.to_python(
        client.eval("function() return ANKIGTA.Indicator.refresh() end")()
    )

    assert plan["blip"] is True
    assert plan["x"] == 5.0

    element["x"] = 9.0
    moved = client.to_python(
        client.eval("function() return ANKIGTA.Indicator.refresh() end")()
    )

    assert moved["x"] == 9.0


def test_a_bearing_entity_that_is_not_here_is_not_marked(
    client: MtaSandbox,
) -> None:
    client.add_world_element(x=5.0, streamed=False, ankigtaEntityId="e1")
    send_links(client, [link()])
    send_next_card(client, [{"mapId": "m1", "entityId": "e1"}])
    client.eval("function() return ANKIGTA.Indicator.setMode('minimap_only') end")()

    plan = client.to_python(
        client.eval("function() return ANKIGTA.Indicator.refresh() end")()
    )

    assert plan["blip"] is False


def test_the_marker_reads_the_list_afresh_rather_than_a_stale_grouping(
    client: MtaSandbox,
) -> None:
    """The indicator groups candidates by card, keyed on the list it was given.

    Handing it one reused table would hand it a grouping built from whatever
    that table held the first time.
    """
    first = client.add_world_element(x=20.0, ankigtaEntityId="e1")
    client.add_world_element(x=4.0, ankigtaEntityId="e2")
    send_links(client, [link("e1"), link("e2")])
    send_next_card(client, [{"mapId": "m1", "entityId": "e1"}])
    client.eval("function() return ANKIGTA.Indicator.setMode('minimap_only') end")()
    assert (
        client.to_python(
            client.eval("function() return ANKIGTA.Indicator.refresh() end")()
        )["entityId"]
        == "e1"
    )

    send_next_card(client, [{"mapId": "m1", "entityId": "e2"}])
    client.trigger("onClientElementStreamOut", first)

    assert (
        client.to_python(
            client.eval("function() return ANKIGTA.Indicator.refresh() end")()
        )["entityId"]
        == "e2"
    )


# --- the index ---------------------------------------------------------------


def test_an_element_that_streams_in_later_joins_the_index(
    client: MtaSandbox,
) -> None:
    """A map may load after the link set arrived, and the entity in it is a
    zone from the moment it is here."""
    send_links(client, [link()])
    assert diagnostics(client)["streamedInstances"] == 0

    element = client.add_world_element(x=1.0, ankigtaEntityId="e1")
    client.trigger("onClientElementStreamIn", element)
    configure(client, delaySeconds=0)

    assert client.to_python(tick(client))["entityId"] == "e1"


def test_a_destroyed_instance_leaves_the_index_entirely(
    client: MtaSandbox,
) -> None:
    element = client.add_world_element(x=1.0, ankigtaEntityId="e1")
    send_links(client, [link()])

    client.trigger("onClientElementDestroy", element)

    report = diagnostics(client)
    assert report["knownInstances"] == 0
    assert report["streamedInstances"] == 0


def test_an_unmanaged_element_is_not_indexed(client: MtaSandbox) -> None:
    client.add_world_element(x=1.0)
    send_links(client, [link()])

    assert diagnostics(client)["knownInstances"] == 0


def test_stopping_the_resource_stops_the_poll(client: MtaSandbox) -> None:
    client.add_world_element(ankigtaEntityId="e1")
    send_links(client, [link()])

    client.trigger("onClientResourceStop", client.eval("resourceRoot"))

    assert diagnostics(client)["polling"] is False
