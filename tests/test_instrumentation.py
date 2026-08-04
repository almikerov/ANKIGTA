"""Ticket 30 — the seams a benchmark and a bug report both read.

Before this ticket, F7 opening, a Card Picker search returning and an
Activation Zone deciding were each "it happened" and nothing else. There was no
number to hold against a threshold and nothing for a player to paste into a
report. These tests pin what each surface now says about itself.

They assert behaviour: the state is produced by running the real modules and
driving them the way MTA does, never by reading their source.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox


REPO_ROOT = Path(__file__).resolve().parents[1]
UUID = "11111111-1111-4111-8111-111111111111"


def manifest_scripts(*kinds: str) -> list[str]:
    """The scripts meta.xml declares, in declared order."""
    manifest = ElementTree.parse(REPO_ROOT / "mta" / "ankigta" / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


def load_client() -> MtaSandbox:
    sandbox = MtaSandbox()
    for script in manifest_scripts("shared", "client"):
        sandbox.load(script)
    return sandbox


def start_server(database_path: str) -> MtaSandbox:
    sandbox = MtaSandbox(database_path=database_path)
    for script in manifest_scripts("shared", "server"):
        sandbox.load(script)
    return sandbox


@pytest.fixture
def client() -> Iterator[MtaSandbox]:
    sandbox = load_client()
    try:
        yield sandbox
    finally:
        sandbox.close()


def report(sandbox: MtaSandbox) -> dict[str, Any]:
    raw = sandbox.eval("function() return ANKIGTA.Diagnostics.snapshot() end")()
    return sandbox.to_python(raw)


def lines(sandbox: MtaSandbox) -> list[str]:
    raw = sandbox.eval("function() return ANKIGTA.Diagnostics.lines() end")()
    return [str(value) for value in sandbox.to_python(raw)]


# --- spatial ------------------------------------------------------------------


def observe(
    sandbox: MtaSandbox,
    now: float,
    candidates: list[dict[str, Any]],
    *,
    x: float = 0.0,
    speed: float = 0.0,
    review_open: bool = False,
) -> Any:
    lua_candidates = sandbox.lua.table_from(
        [sandbox.lua.table_from(item) for item in candidates]
    )
    player = sandbox.lua.table_from(
        {
            "x": x,
            "y": 0.0,
            "z": 0.0,
            "interior": 0,
            "dimension": 0,
            "speedKmh": speed,
            "reviewOpen": review_open,
        }
    )
    return sandbox.eval(
        "function(now, player, candidates)"
        " return ANKIGTA.Activation.update(now, player, candidates) end"
    )(now, player, lua_candidates)


def candidate(
    entity_id: str,
    *,
    x: float,
    radius: float = 3.0,
    eligible: bool = True,
) -> dict[str, Any]:
    return {
        "mapId": "m1",
        "entityId": entity_id,
        "x": x,
        "y": 0.0,
        "z": 0.0,
        "radius": radius,
        "interior": 0,
        "dimension": 0,
        "eligible": eligible,
        "present": True,
    }


def test_the_spatial_report_states_what_is_tracked_and_what_is_nearest(
    client: MtaSandbox,
) -> None:
    observe(
        client,
        0.0,
        [
            candidate("far", x=2.0),
            candidate("near", x=1.5),
            candidate("out-of-range", x=40.0),
        ],
    )

    spatial = report(client)["spatial"]

    # Everything the server offered, not only what was close enough: "there are
    # candidates but none of them are near you" is the answer most worth having.
    assert spatial["tracked"] == 3
    assert spatial["inZone"] == 2
    assert spatial["nearestEntityId"] == "near"
    assert spatial["nearestMapId"] == "m1"
    assert spatial["nearestDistance"] == pytest.approx(1.5)


def test_the_report_says_whether_the_world_is_being_polled_at_all(
    client: MtaSandbox,
) -> None:
    """The other half of "why did the card not open".

    The decision's own report cannot say that nothing is asking it, or that the
    entity has no Runtime Instance here to ask about.
    """
    idle = report(client)["polling"]
    assert idle["polling"] is False
    assert idle["links"] == 0

    client.add_world_element(x=1.0, ankigtaEntityId="e1")
    client.eval(
        """
        function()
            triggerEvent("ankigta:spatialCandidates", resourceRoot, {
                {mapId = "m1", entityId = "e1", radius = 3},
            })
        end
        """
    )()

    running = report(client)["polling"]
    assert running["polling"] is True
    assert running["links"] == 1
    assert running["streamedInstances"] == 1
    assert running["pollIntervalMs"] == 250


def test_the_nearest_distance_is_a_distance_not_its_square(
    client: MtaSandbox,
) -> None:
    """Reporting the squared distance would read plausibly and be wrong past
    one metre, which is where every real zone is."""
    observe(client, 0.0, [candidate("e1", x=2.5)])

    assert report(client)["spatial"]["nearestDistance"] == pytest.approx(2.5)


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({}, "counting_down"),
        ({"review_open": True}, "review_open"),
        ({"speed": 99999}, "too_fast"),
    ],
)
def test_the_report_says_why_nothing_is_opening(
    client: MtaSandbox,
    kwargs: dict[str, Any],
    reason: str,
) -> None:
    if reason == "counting_down":
        client.eval(
            "function() return ANKIGTA.Activation.configure({delaySeconds = 1}) end"
        )()
    observe(client, 0.0, [candidate("e1", x=1.0)], **kwargs)

    assert report(client)["spatial"]["reason"] == reason


def test_a_candidate_out_of_every_zone_is_reported_as_such(
    client: MtaSandbox,
) -> None:
    observe(client, 0.0, [candidate("e1", x=40.0)])

    spatial = report(client)["spatial"]

    assert spatial["tracked"] == 1
    assert spatial["inZone"] == 0
    assert spatial["reason"] == "no_zone"
    # `false`, the way MTA reports "no such thing", rather than a key that
    # disappears from the report when there is nothing to name.
    assert spatial["nearestEntityId"] is False


def test_the_report_names_the_card_that_is_open_and_stops_when_it_closes(
    client: MtaSandbox,
) -> None:
    client.eval(
        "function() return ANKIGTA.Activation.configure({delaySeconds = 0}) end"
    )()
    candidates = [candidate("e1", x=1.0)]

    assert observe(client, 0.0, candidates) is not False
    assert report(client)["spatial"]["openEntityId"] == "e1"

    # It stays named while the review holds the world.
    observe(client, 1.0, candidates, review_open=True)
    assert report(client)["spatial"]["openEntityId"] == "e1"

    # And stops being named on the first observation that runs with the review
    # closed, so the report cannot go on describing a card already finished.
    observe(client, 2.0, candidates, x=40.0)
    assert report(client)["spatial"]["openEntityId"] is False


# --- F7 -----------------------------------------------------------------------


def seed(sandbox: MtaSandbox, entities: int, links: int) -> None:
    from tests.perf.dataset import fill_store

    fill_store(sandbox, map_entities=entities, spatial_links=links)


def test_the_f7_snapshot_carries_what_it_cost_and_over_how_much(
    tmp_path: Any,
) -> None:
    server = start_server(str(tmp_path / "ankigta.sqlite"))
    try:
        player = server.add_study_player()
        server.trigger("onResourceStart")
        seed(server, 40, 25)

        server.trigger(
            "ankigta:requestF7",
            server.eval("resourceRoot"),
            client=player,
        )
        sent = server.recorder.client_events[-1]
        snapshot = server.to_python(sent.args[0])
        diagnostics = snapshot["diagnostics"]

        assert sent.name == "ankigta:f7Snapshot"
        assert diagnostics["entityCount"] == len(snapshot["entities"])
        assert diagnostics["linkCount"] == 25
        # The tracer entities the store seeds are part of the world too, so the
        # count is the store's answer rather than what this test inserted.
        assert diagnostics["mapEntities"] >= 40
        assert diagnostics["spatialLinks"] == 25
        assert isinstance(diagnostics["buildMs"], (int, float))
        assert diagnostics["overReferenceVolume"] is False
    finally:
        server.close()


def test_the_client_records_the_wait_it_measured_and_what_the_server_reported(
    client: MtaSandbox,
) -> None:
    client.eval(
        """
        function()
            triggerEvent("ankigta:setAuthorized", resourceRoot, true)
        end
        """
    )()
    # Pressing F7 is what starts the clock, so the request is made the way the
    # key binding makes it rather than by calling the handler.
    for handler in client.bound_keys[("F7", "down")]:
        handler()
    client.advance(180)
    client.eval(
        """
        function()
            triggerEvent("ankigta:f7Snapshot", resourceRoot, {
                visible = true,
                cardPicker = {enabled = true},
                history = {},
                entities = {},
                diagnostics = {
                    buildMs = 42,
                    entityCount = 9000,
                    linkCount = 4500,
                    mapEntities = 9000,
                    spatialLinks = 4500,
                    overReferenceVolume = false,
                },
            })
        end
        """
    )()

    f7 = report(client)["f7"]

    assert f7["serverBuildMs"] == 42
    assert f7["entityCount"] == 9000
    assert f7["linkCount"] == 4500
    # The wait the player actually had, which is longer than the server's part.
    assert f7["openMs"] >= 180
    assert f7["openMs"] >= f7["serverBuildMs"]


# --- search -------------------------------------------------------------------


def test_a_card_picker_page_is_reported_with_its_size_and_its_total(
    client: MtaSandbox,
) -> None:
    client.eval(
        """
        function(uuid)
            triggerEvent("ankigta:setAuthorized", resourceRoot, true)
            triggerEvent("ankigta:cardPickerSnapshot", resourceRoot, {
                enabled = true,
                page = 0,
                pageSize = 50,
                total = 100000,
                deckFilter = "Default",
                cards = {
                    {
                        cardIdentity = {collectionUuid = uuid, cardId = 1},
                        deckName = "Default",
                        state = "new",
                        tags = {},
                    },
                },
            })
        end
        """
    )(UUID)

    search = report(client)["search"]

    assert search["total"] == 100000
    assert search["pageSize"] == 50
    assert search["shown"] == 1
    assert search["deckFilter"] == "Default"


def test_the_search_the_player_started_carries_the_wait_they_had(
    client: MtaSandbox,
) -> None:
    """The clock starts at the button, and the button is what presses it.

    A page that arrived without a search behind it carries no wait, and one the
    player asked for carries theirs. The two used to be indistinguishable: the
    stamp was written where the button is wired and read further down the file,
    where a later local shadowed it, so every search reported no wait at all.
    """
    open_picker = client.eval(
        """
        function(uuid, total)
            triggerEvent("ankigta:setAuthorized", resourceRoot, true)
            triggerEvent("ankigta:cardPickerSnapshot", resourceRoot, {
                enabled = true,
                page = 0,
                pageSize = 50,
                total = total,
                deckFilter = "Default",
                cards = {
                    {
                        cardIdentity = {collectionUuid = uuid, cardId = 1},
                        deckName = "Default",
                        state = "new",
                        tags = {},
                    },
                },
            })
        end
        """
    )
    open_picker(UUID, 100000)
    # A picker that opened on its own is not a search anyone waited for.
    assert report(client)["search"]["pageMs"] is False

    # The panel is a page: the button lives in HTML, and pressing it arrives
    # here as the action the page names.
    client.eval(
        """
        function()
            triggerEvent(
                "ankigta:panelAction", resourceRoot, "searchCards",
                '{"query":"","deck":"Default"}'
            )
        end
        """
    )()
    client.advance(500)
    open_picker(UUID, 400)

    search = report(client)["search"]

    # Comfortably inside the pushed clock rather than exactly on it: the
    # sandbox's tick never repeats, so two reads in the same millisecond are a
    # millisecond apart and an exact bound would be a coin toss.
    assert search["pageMs"] >= 450
    assert search["total"] == 400


# --- session ------------------------------------------------------------------


def test_a_rebuild_in_flight_is_reported_with_its_progress(
    client: MtaSandbox,
) -> None:
    client.eval(
        """
        function()
            triggerEvent("ankigta:companionStatus", resourceRoot, {
                state = "connected",
                study = {
                    sessionActive = false,
                    pausedReason = "rebuilding",
                    progress = 1200,
                    total = 5000,
                    cardCount = 5000,
                    filteredDeckCreated = false,
                },
            })
        end
        """
    )()

    session = report(client)["session"]

    assert session["pausedReason"] == "rebuilding"
    assert session["progress"] == 1200
    assert session["total"] == 5000
    assert session["connection"] == "connected"


# --- the report as a player pastes it ----------------------------------------


def test_the_report_reads_the_same_way_twice_for_the_same_state(
    client: MtaSandbox,
) -> None:
    observe(client, 0.0, [candidate("e1", x=1.0)])

    assert lines(client) == lines(client)


def test_every_reported_value_is_a_technical_value_rather_than_a_sentence(
    client: MtaSandbox,
) -> None:
    """A report is pasted from one person to another, so nothing in it may be
    a sentence: only the heading comes from the string table."""
    observe(client, 0.0, [candidate("e1", x=1.0)])

    for line in lines(client):
        section, _, rest = line.partition(" ")
        assert section == section.strip()
        for pair in rest.split(" "):
            assert "=" in pair, line
            assert pair.isascii(), line


def test_the_command_prints_a_heading_from_the_table_and_the_raw_state() -> None:
    sandbox = load_client()
    try:
        observe(sandbox, 0.0, [candidate("e1", x=1.0)])

        sandbox.commands["ankigta-diagnostics"][0]()

        heading = sandbox.eval(
            "function() return ANKIGTA.Locale.text('diagnostics.title') end"
        )()
        assert sandbox.chat[0] == heading
        assert heading != "diagnostics.title"
        assert any(line.startswith("spatial ") for line in sandbox.chat[1:])
    finally:
        sandbox.close()


# --- the reference volume ----------------------------------------------------


def volume(sandbox: MtaSandbox) -> dict[str, Any]:
    return sandbox.to_python(
        sandbox.eval("function() return ANKIGTA.Store.volumeReport() end")()
    )


def test_a_world_inside_the_reference_volume_is_not_flagged(tmp_path: Any) -> None:
    server = start_server(str(tmp_path / "ankigta.sqlite"))
    try:
        server.trigger("onResourceStart")
        seed(server, 100, 50)

        assert volume(server)["overReference"] is False
        assert not any(
            "volume_over_reference" in message
            for message in server.recorder.debug_messages()
        )
    finally:
        server.close()


def test_passing_the_reference_volume_warns_once_and_keeps_serving(
    tmp_path: Any,
) -> None:
    server = start_server(str(tmp_path / "ankigta.sqlite"))
    try:
        server.trigger("onResourceStart")
        reference = volume(server)["referenceSpatialLinks"]
        seed(server, reference + 20, reference + 10)

        first = volume(server)
        second = volume(server)

        assert first["overReference"] is True
        assert second["overReference"] is True
        assert first["spatialLinks"] == reference + 10
        warnings = [
            message
            for message in server.recorder.debug_messages()
            if "volume_over_reference" in message
        ]
        # Once per crossing: a line on every F7 open would be noise, and the
        # state stays readable from the report itself.
        assert len(warnings) == 1
        # Over the reference volume is not a cap: every row is still served.
        # Counted in Lua, because marshalling ten thousand rows into Python
        # would measure lupa rather than the store.
        served = server.eval(
            "function() return #ANKIGTA.Store.listMapEntities() end"
        )()
        assert served == first["mapEntities"]
    finally:
        server.close()


def test_the_reference_volume_is_at_least_what_the_ticket_states(
    tmp_path: Any,
) -> None:
    """A floor, not the current value: a later ticket may promise more, and
    must never quietly promise less."""
    server = start_server(str(tmp_path / "ankigta.sqlite"))
    try:
        server.trigger("onResourceStart")
        current = volume(server)

        assert current["referenceMapEntities"] >= 10000
        assert current["referenceSpatialLinks"] >= 5000
    finally:
        server.close()
