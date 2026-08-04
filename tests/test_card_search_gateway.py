"""Panel-usability ticket 04 — the search the player writes, and its refusal.

The Card Picker asked Anki for cards with a deck filter and an empty query.
Two things were missing between the panel and the companion: a written Anki
expression had no way through, and an expression Anki refuses came back
indistinguishable from a dead link -- both arrived as `protocol_error`, which
tells the player to check their connection when what needs checking is the
bracket they left open.

These drive the gateway in a real Lua 5.1 interpreter: what it puts on the
wire, and what it does with each of the two answers the companion can give.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


@pytest.fixture
def server() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.execute(
        """
        ANKIGTA = ANKIGTA or {}
        ANKIGTA.ConnectionConfig = {
            loadEffective = function()
                return {port = 51234, token = "t"}, false, false
            end,
        }
        ANKIGTA.Store = {listMapEntities = function() return {} end}
        """
    )
    sandbox.load("server/companion.lua")
    try:
        yield sandbox
    finally:
        sandbox.close()


def search(sandbox: MtaSandbox, query: str, scope: Any = None) -> Any:
    player = sandbox.add_study_player()
    return sandbox.eval(
        """
        function(player, query, scope)
            return ANKIGTA.CompanionGateway.requestCardPicker(
                player, query, false, 0, 50, scope
            )
        end
        """
    )(player, query, scope)


def sent(sandbox: MtaSandbox) -> dict[str, Any]:
    return json.loads(sandbox.recorder.remote_fetches[-1]["options"]["postData"])


def notices(sandbox: MtaSandbox) -> list[Any]:
    return [
        event
        for event in sandbox.recorder.client_events
        if event.name == "ankigta:pendingMapSaveNotice"
    ]


def answer(sandbox: MtaSandbox, *, status: int, body: dict[str, Any]) -> None:
    sandbox.complete_fetch(body=json.dumps(body), status=status)


def test_a_written_expression_is_put_on_the_wire_as_written(
    server: MtaSandbox,
) -> None:
    """The gateway carries the expression; it does not have opinions about it.

    `-is:suspended` is Anki's to understand. Anything this side did to the
    text would make the panel and Anki disagree about what was asked.
    """
    accepted, _ = search(server, "deck:Spanish tag:verb -is:suspended")

    assert accepted is True
    body = sent(server)
    assert body["query"] == "deck:Spanish tag:verb -is:suspended"
    assert body["scope"] == "cards"


def test_the_scope_the_player_chose_travels_with_the_search(
    server: MtaSandbox,
) -> None:
    search(server, "", "notes")

    assert sent(server)["scope"] == "notes"


def test_a_scope_the_picker_does_not_have_never_reaches_the_network(
    server: MtaSandbox,
) -> None:
    accepted, reason = search(server, "", "decks")

    assert accepted is False
    assert reason == "invalid_scope"
    assert server.recorder.remote_fetches == []


def test_a_refused_expression_is_reported_as_refused_not_as_a_dead_link(
    server: MtaSandbox,
) -> None:
    """The companion answered, in its own protocol, that the search was bad.

    Reporting that as `protocol_error` sends the player to the connection
    screen over a healthy connection, and says nothing about the expression --
    which is the only thing that is actually wrong.
    """
    search(server, "deck:(Spanish")
    request_id = sent(server)["requestId"]

    answer(
        server,
        status=400,
        body={
            "protocol": "ankigta-control",
            "protocolVersion": 1,
            "requestId": request_id,
            "ok": False,
            "error": {
                "category": "search_rejected",
                "message": "Invalid search - please check for typing mistakes.",
            },
            "payload": None,
        },
    )

    reported = notices(server)[-1]
    assert reported.args[0] == "notice.cardPickerRejected"
    assert "typing mistakes" in reported.args[1]


def test_a_search_that_did_not_reach_the_companion_is_still_a_transport_failure(
    server: MtaSandbox,
) -> None:
    """A proxy page with a 400 on it is not the companion refusing a search."""
    search(server, "deck:Spanish")

    answer(server, status=400, body={"nothing": "to do with ANKIGTA"})

    reported = notices(server)[-1]
    assert reported.args[0] == "notice.cardPickerUnavailable"
    assert reported.args[1] == "protocol_error"


def test_a_search_of_every_deck_reaches_the_panel_with_its_scope(
    server: MtaSandbox,
) -> None:
    """A page with no deck filter is an answer, not a malformed envelope.

    The companion says "no deck filter" with JSON `null`, which MTA decodes to
    nil rather than to `false`. A validator written against `false` alone threw
    the whole page away -- every card in it -- and told the player the
    connection was at fault.
    """
    search(server, "", "notes")
    request_id = sent(server)["requestId"]

    answer(
        server,
        status=200,
        body={
            "protocol": "ankigta-control",
            "protocolVersion": 1,
            "requestId": request_id,
            "ok": True,
            "error": None,
            "payload": {
                "cards": [],
                "page": 0,
                "pageSize": 50,
                "total": 0,
                "query": "",
                "deckFilter": None,
                "scope": "notes",
                "decks": [],
            },
        },
    )

    snapshots = [
        event
        for event in server.recorder.client_events
        if event.name == "ankigta:cardPickerSnapshot"
    ]
    assert snapshots, notices(server)
    assert server.to_python(snapshots[-1].args[0])["scope"] == "notes"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
