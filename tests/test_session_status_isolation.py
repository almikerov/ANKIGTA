"""A refused session is not a lost connection.

The connection window opens whenever the published status is neither
`connected` nor `connecting`. Session polling and health polling both went
through one `setStatus`, so a companion that was reachable and simply had no
ANKIGTA Session — the ordinary state before Start studying — published
`disconnected` every few seconds, and the window reopened on a healthy link
between two `connected` health replies.
"""

from __future__ import annotations

import json
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox
from tests.lua.sandbox import RESOURCE_ROOT


PORT = 51234


def manifest_scripts(*kinds: str) -> list[str]:
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


def study_player(sandbox: MtaSandbox) -> Any:
    return sandbox.add_study_player()


def request_session_start(sandbox: MtaSandbox, player: Any) -> Any:
    return sandbox.eval(
        "function(p) return ANKIGTA.CompanionGateway.requestSessionStart(p, {}) end"
    )(player)


def last_fetch_request_id(sandbox: MtaSandbox) -> str:
    fetch = sandbox.recorder.remote_fetches[-1]
    return str(json.loads(fetch["options"]["postData"])["requestId"])


def answer_with_error(
    sandbox: MtaSandbox,
    *,
    category: str,
    http_status: int,
    request_id: str | None = None,
    protocol: str = "ankigta-control",
) -> None:
    """Reply the way the companion replies when it refuses."""
    sandbox.complete_fetch(
        len(sandbox.recorder.remote_fetches) - 1,
        body=json.dumps(
            {
                "protocol": protocol,
                "protocolVersion": 1,
                "requestId": request_id or last_fetch_request_id(sandbox),
                "ok": False,
                "error": {"category": category, "message": category},
                "payload": None,
            }
        ),
        status=http_status,
    )


def status(sandbox: MtaSandbox) -> Any:
    return sandbox.eval(
        "function() return ANKIGTA.CompanionGateway.status end"
    )()


def test_no_session_yet_leaves_the_connection_reported_as_connected(
    server: MtaSandbox,
) -> None:
    player = study_player(server)
    request_session_start(server, player)

    answer_with_error(server, category="session_unavailable", http_status=503)

    assert status(server).state == "connected"
    assert status(server).category is False
    # The refusal is still reported, next to the connection rather than instead
    # of it: the player asked to start studying and did not.
    assert status(server).sessionCategory == "session_unavailable"


def test_the_connection_window_is_not_asked_to_open_by_a_refused_session(
    server: MtaSandbox,
) -> None:
    """What the player actually sees, rather than a field on a table."""
    player = study_player(server)
    request_session_start(server, player)

    answer_with_error(server, category="session_unavailable", http_status=503)

    published = [
        server.to_python(event.args[0])
        for event in server.recorder.client_events
        if event.name == "ankigta:companionStatus"
    ]
    assert published, "no status reached the client"
    # connection_settings.lua opens its window for any state that is neither of
    # these two, so this is the assertion that keeps the window shut.
    assert all(
        entry["state"] in ("connected", "connecting") for entry in published
    ), published


def test_a_reply_that_is_not_the_companion_still_disconnects(
    server: MtaSandbox,
) -> None:
    """The distinction is "did the companion answer", not "was it an error".

    A proxy page, a wrong port answering, or a truncated body leaves the link
    genuinely in doubt, and that has to keep reporting disconnected.
    """
    player = study_player(server)
    request_session_start(server, player)

    answer_with_error(
        server,
        category="session_unavailable",
        http_status=503,
        protocol="something-else",
    )

    assert status(server).state == "disconnected"


def test_a_reply_for_another_request_still_disconnects(
    server: MtaSandbox,
) -> None:
    player = study_player(server)
    request_session_start(server, player)

    answer_with_error(
        server,
        category="session_unavailable",
        http_status=503,
        request_id="some-other-request",
    )

    assert status(server).state == "disconnected"


def test_a_started_session_clears_the_earlier_refusal(
    server: MtaSandbox,
) -> None:
    player = study_player(server)
    request_session_start(server, player)
    answer_with_error(server, category="session_unavailable", http_status=503)
    assert status(server).sessionCategory == "session_unavailable"

    request_session_start(server, player)
    sandbox_request_id = last_fetch_request_id(server)
    server.complete_fetch(
        len(server.recorder.remote_fetches) - 1,
        body=json.dumps(
            {
                "protocol": "ankigta-control",
                "protocolVersion": 1,
                "requestId": sandbox_request_id,
                "ok": True,
                "error": None,
                "payload": {
                    "session": {
                        "sessionActive": True,
                        "ratingEnabled": True,
                        "filteredDeckCreated": True,
                        "reviewModeOpened": False,
                    }
                },
            }
        ),
        status=200,
    )

    assert status(server).state == "connected"
    assert status(server).sessionCategory is False
