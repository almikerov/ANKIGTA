"""Ticket 31 — the server half of the polling gap.

One refresh answers three questions about the same moment: how much work there
is, which Spatial Link may open by itself, and which Map Entity carries the
marker. Ticket 30 recorded that no server code sent any of them.

The tests drive `server/main.lua` and `server/companion.lua` in a real Lua VM:
ask for the refresh, answer the HTTP request it made, and read what it sent to
the client.
"""

from __future__ import annotations

import json
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox
from tests.lua.sandbox import RESOURCE_ROOT


UUID = "11111111-1111-4111-8111-111111111111"
PORT = 51_500
MAP_ID = "map-ticket31"


def manifest_scripts(*kinds: str) -> list[str]:
    """The scripts meta.xml registers, in the order it registers them.

    Read out of the manifest rather than listed here, so a script that was
    never registered fails a test instead of working only in tests.
    """
    manifest = ElementTree.parse(RESOURCE_ROOT / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


@pytest.fixture
def server(tmp_path: Any) -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
    for script in manifest_scripts("shared", "server"):
        sandbox.load(script)
    # After the scripts, so it replaces the real one rather than being replaced
    # by it. What a published connection file looks like is ticket 03's, and
    # these tests are about what the gateway does once it has one.
    sandbox.execute(
        f"""
        ANKIGTA.ConnectionConfig.loadEffective = function()
            return {{port = {PORT}, token = "t"}}, false, false
        end
        """
    )
    sandbox.trigger("onResourceStart")
    try:
        yield sandbox
    finally:
        sandbox.close()


def seed(
    sandbox: MtaSandbox,
    links: list[tuple[str, int]],
    *,
    include_in_study: bool = True,
    radius: float = 3.0,
    show_radius: bool = False,
) -> None:
    raw = sandbox.connection.raw
    raw.execute(
        "INSERT OR IGNORE INTO maps (map_id, resource_name, map_name)"
        " VALUES (?, 'ankigta', 'Ticket 31')",
        (MAP_ID,),
    )
    raw.execute(
        "INSERT OR REPLACE INTO map_preferences (map_id, include_in_study)"
        " VALUES (?, ?)",
        (MAP_ID, 1 if include_in_study else 0),
    )
    for entity_id, card_id in links:
        raw.execute(
            "INSERT OR IGNORE INTO map_entities (map_id, entity_id,"
            " entity_type, model, authored_x, authored_y, authored_z,"
            " rotation_x, rotation_y, rotation_z, interior, dimension)"
            " VALUES (?, ?, 'object', 1337, 0, 0, 0, 0, 0, 0, 0, 0)",
            (MAP_ID, entity_id),
        )
        raw.execute(
            "INSERT OR REPLACE INTO map_entity_metadata (map_id, entity_id,"
            " radius, show_radius) VALUES (?, ?, ?, ?)",
            (MAP_ID, entity_id, radius, 1 if show_radius else 0),
        )
        raw.execute(
            "INSERT OR IGNORE INTO spatial_links (map_id, entity_id,"
            " collection_uuid, card_id, state, verified_map_sha256)"
            " VALUES (?, ?, ?, ?, 'active', ?)",
            (MAP_ID, entity_id, UUID, card_id, "a" * 64),
        )
    raw.commit()


def refresh(sandbox: MtaSandbox, player: Any) -> Any:
    return sandbox.eval(
        """
        function(player)
            triggerEvent(
                "ankigta:studyStateChanged",
                resourceRoot,
                player,
                {study = {sessionActive = true}}
            )
        end
        """
    )(player)


def answer(
    sandbox: MtaSandbox,
    states: dict[str, str],
    *,
    next_card: dict[str, Any] | None = None,
    index: int = -1,
) -> None:
    fetch = sandbox.recorder.remote_fetches[index]
    request_id = json.loads(fetch["options"]["postData"])["requestId"]
    sandbox.complete_fetch(
        index,
        body=json.dumps(
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": request_id,
                "ok": True,
                "error": None,
                "payload": {"cardStates": states, "nextCard": next_card},
            }
        ),
    )


def sent(sandbox: MtaSandbox, name: str) -> list[Any]:
    return [
        event for event in sandbox.recorder.client_events if event.name == name
    ]


def last_payload(sandbox: MtaSandbox, name: str, argument: int = 0) -> Any:
    events = sent(sandbox, name)
    assert events, f"no {name} was sent"
    return sandbox.to_python(events[-1].args[argument])


def as_list(value: Any) -> list[Any]:
    """A Lua array, as a list.

    An empty Lua table carries no shape, so it arrives as an empty mapping
    rather than as an empty list; both mean "nothing to watch".
    """
    return list(value.values()) if isinstance(value, dict) else list(value)


def key(card_id: int) -> str:
    return f"{UUID}/{card_id}"


# --- the refresh -------------------------------------------------------------


def test_the_refresh_asks_anki_for_every_linked_card(server: MtaSandbox) -> None:
    player = server.add_study_player()
    seed(server, [("e1", 11), ("e2", 12)])

    refresh(server, player)

    fetch = server.recorder.remote_fetches[-1]
    assert fetch["url"] == f"http://127.0.0.1:{PORT}/v1/cards/states"
    body = json.loads(fetch["options"]["postData"])
    assert sorted(
        identity["cardId"] for identity in body["cardIdentities"]
    ) == [11, 12]


def test_one_card_on_two_entities_is_asked_about_once(server: MtaSandbox) -> None:
    player = server.add_study_player()
    seed(server, [("e1", 11), ("e2", 11)])

    refresh(server, player)

    body = json.loads(server.recorder.remote_fetches[-1]["options"]["postData"])
    assert [identity["cardId"] for identity in body["cardIdentities"]] == [11]


def test_the_counters_the_hud_shows_come_from_the_answer(
    server: MtaSandbox,
) -> None:
    player = server.add_study_player()
    seed(server, [("e1", 11), ("e2", 12), ("e3", 13)])
    refresh(server, player)

    answer(
        server,
        {key(11): "new", key(12): "review", key(13): "suspended"},
    )

    counts = last_payload(server, "ankigta:statistics")
    assert counts["new"] == 1
    assert counts["due"] == 1
    assert counts["total"] == 2


def test_the_candidate_set_carries_identities_and_never_coordinates(
    server: MtaSandbox,
) -> None:
    """Where the Runtime Instance is now is the client's to read.

    A coordinate sent from here would be the authored one wearing the current
    one's name, and the zone would sit where the entity used to be.
    """
    player = server.add_study_player()
    seed(server, [("e1", 11)], radius=7.5, show_radius=True)
    refresh(server, player)

    answer(server, {key(11): "new"})

    candidates = as_list(last_payload(server, "ankigta:spatialCandidates"))
    assert len(candidates) == 1
    assert candidates[0] == {
        "mapId": MAP_ID,
        "entityId": "e1",
        "cardIdentity": {"collectionUuid": UUID, "cardId": 11},
        "radius": 7.5,
        "showRadius": True,
        "eligible": True,
    }


def test_a_card_anki_did_not_report_on_is_not_something_to_walk_into(
    server: MtaSandbox,
) -> None:
    player = server.add_study_player()
    seed(server, [("e1", 11), ("e2", 12)])
    refresh(server, player)

    answer(server, {key(11): "new"})

    candidates = as_list(last_payload(server, "ankigta:spatialCandidates"))
    assert [candidate["entityId"] for candidate in candidates] == ["e1"]


def test_suspended_and_buried_cards_do_not_activate(server: MtaSandbox) -> None:
    player = server.add_study_player()
    seed(server, [("e1", 11), ("e2", 12)])
    refresh(server, player)

    answer(server, {key(11): "suspended", key(12): "buried"})

    assert as_list(last_payload(server, "ankigta:spatialCandidates")) == []


def test_a_not_due_card_activates_only_with_early_review_enabled(
    server: MtaSandbox,
) -> None:
    player = server.add_study_player()
    seed(server, [("e1", 11)])
    refresh(server, player)
    answer(server, {key(11): "not_due"})
    assert as_list(last_payload(server, "ankigta:spatialCandidates")) == []

    server.eval(
        "function() return ANKIGTA.SettingsStore.set('allowEarlyReview', true) end"
    )()
    refresh(server, player)
    answer(server, {key(11): "not_due"})

    candidates = as_list(last_payload(server, "ankigta:spatialCandidates"))
    assert [candidate["entityId"] for candidate in candidates] == ["e1"]


def test_an_excluded_map_contributes_nothing(server: MtaSandbox) -> None:
    player = server.add_study_player()
    seed(server, [("e1", 11)], include_in_study=False)
    refresh(server, player)

    answer(server, {key(11): "new"})

    assert as_list(last_payload(server, "ankigta:spatialCandidates")) == []
    assert last_payload(server, "ankigta:statistics")["total"] == 0


# --- the next card -----------------------------------------------------------


def test_the_next_card_names_every_entity_carrying_it(server: MtaSandbox) -> None:
    player = server.add_study_player()
    seed(server, [("e1", 11), ("e2", 11), ("e3", 12)])
    refresh(server, player)

    answer(
        server,
        {key(11): "new", key(12): "review"},
        next_card={"collectionUuid": UUID, "cardId": 11},
    )

    identity = last_payload(server, "ankigta:nextCard", 0)
    bearers = as_list(last_payload(server, "ankigta:nextCard", 1))
    assert identity == {"collectionUuid": UUID, "cardId": 11}
    assert sorted(bearer["entityId"] for bearer in bearers) == ["e1", "e2"]


def test_no_session_means_no_next_card(server: MtaSandbox) -> None:
    player = server.add_study_player()
    seed(server, [("e1", 11)])
    refresh(server, player)

    answer(server, {key(11): "new"}, next_card=None)

    assert last_payload(server, "ankigta:nextCard", 0) is False
    assert as_list(last_payload(server, "ankigta:nextCard", 1)) == []


def test_a_next_card_nothing_carries_is_not_announced(server: MtaSandbox) -> None:
    """Anki may name a card whose entity is on an excluded map.

    Naming it with no bearer would leave the client marking nothing while
    believing it had a target.
    """
    player = server.add_study_player()
    seed(server, [("e1", 11)])
    refresh(server, player)

    answer(
        server,
        {key(11): "new"},
        next_card={"collectionUuid": UUID, "cardId": 999},
    )

    assert last_payload(server, "ankigta:nextCard", 0) is False


# --- pausing -----------------------------------------------------------------


def test_a_paused_session_empties_the_candidate_set(server: MtaSandbox) -> None:
    """`Pause studying` has to reach the world, and silence would not."""
    player = server.add_study_player()
    seed(server, [("e1", 11)])

    server.eval(
        """
        function(player)
            triggerEvent(
                "ankigta:studyStateChanged",
                resourceRoot,
                player,
                {study = {sessionActive = false}}
            )
        end
        """
    )(player)

    assert as_list(last_payload(server, "ankigta:spatialCandidates")) == []
    assert last_payload(server, "ankigta:statistics")["total"] == 0
    assert server.recorder.remote_fetches == []


def test_a_world_with_no_active_link_asks_anki_nothing(server: MtaSandbox) -> None:
    player = server.add_study_player()

    refresh(server, player)

    assert server.recorder.remote_fetches == []
    assert as_list(last_payload(server, "ankigta:spatialCandidates")) == []


# --- opening -----------------------------------------------------------------


def request_open(
    sandbox: MtaSandbox,
    player: Any,
    entity_id: str = "e1",
    *,
    map_id: str = MAP_ID,
    card_id: int | None = 11,
) -> None:
    sandbox.trigger(
        "ankigta:requestSpatialOpen",
        sandbox.eval("resourceRoot"),
        map_id,
        entity_id,
        (
            sandbox.lua.table_from({"collectionUuid": UUID, "cardId": card_id})
            if card_id is not None
            else False
        ),
        client=player,
    )


def test_walking_into_a_zone_opens_the_card_through_review_mode(
    server: MtaSandbox,
) -> None:
    """The same path a manual opening takes, so admission cannot be skipped."""
    player = server.add_study_player()
    seed(server, [("e1", 11)])

    request_open(server, player)

    fetch = server.recorder.remote_fetches[-1]
    assert fetch["url"].endswith("/v1/render/issue")
    assert json.loads(fetch["options"]["postData"])["cardIdentity"]["cardId"] == 11


def test_an_ordinary_player_cannot_open_a_card_by_asking(
    server: MtaSandbox,
) -> None:
    seed(server, [("e1", 11)])
    intruder = server.lua.table_from({"__element": True, "type": "player"})
    server.world_elements.append(intruder)

    request_open(server, intruder)

    assert server.recorder.remote_fetches == []


def test_the_server_refuses_an_entity_whose_link_is_not_active(
    server: MtaSandbox,
) -> None:
    player = server.add_study_player()
    seed(server, [("e1", 11)])
    server.connection.raw.execute(
        "UPDATE spatial_links SET state = 'card_missing' WHERE entity_id = 'e1'"
    )
    server.connection.raw.commit()

    request_open(server, player)

    assert server.recorder.remote_fetches == []
    notices = sent(server, "ankigta:pendingMapSaveNotice")
    assert notices[-1].args[1] == "link_not_active"


def test_the_server_decides_which_card_a_map_entity_carries(
    server: MtaSandbox,
) -> None:
    """A client proposing a card it is no longer linked to is refused rather
    than quietly given the right one: the card it meant is not the card it
    would get."""
    player = server.add_study_player()
    seed(server, [("e1", 11)])

    request_open(server, player, card_id=4242)

    assert server.recorder.remote_fetches == []
    assert sent(server, "ankigta:pendingMapSaveNotice")[-1].args[1] == "card_changed"
