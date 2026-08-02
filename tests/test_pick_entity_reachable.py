"""Pressing Pick Entity has to actually start Pick Entity.

`tests/test_mta_ticket_24.py` checks that the two sides spell the event name
the same way, by reading the source. That can be true of a name nobody
registered: `triggerEvent` on a name MTA does not know calls no handler and
returns false, without a word in the log. The panel closed itself to get out of
the way and then nothing happened -- no cursor, no crosshair, no result.

So this drives the button instead of reading about it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox

RESOURCE = Path(__file__).resolve().parent.parent / "mta" / "ankigta"


def manifest_client_scripts() -> list[str]:
    """The client scripts meta.xml declares, in declared order."""
    manifest = ElementTree.parse(RESOURCE / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in ("shared", "client")
    ]


@pytest.fixture
def client() -> Iterator[MtaSandbox]:
    """The whole client side, started the way MTA starts it."""
    sandbox = MtaSandbox()
    for script in manifest_client_scripts():
        sandbox.load(script)
    sandbox.trigger("onClientResourceStart")
    sandbox.eval(
        'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
    )()
    # The workspace, not the gate: Pick Entity is offered on the far side.
    sandbox.eval(
        """
        function()
            triggerEvent("ankigta:companionStatus", resourceRoot,
                {state = "connected"})
        end
        """
    )()
    try:
        yield sandbox
    finally:
        sandbox.close()


def act(sandbox: MtaSandbox, action: str, payload: Any = None) -> None:
    """A button on the page, arriving as the action it names."""
    sandbox.eval(
        """
        function(action, payload)
            triggerEvent("ankigta:panelAction", resourceRoot, action, payload)
        end
        """
    )(action, json.dumps(payload or {}))


def picking(sandbox: MtaSandbox) -> bool:
    return bool(sandbox.eval("function() return isPickEntityActive() end")())


def test_the_pick_entity_button_starts_pick_entity(client: MtaSandbox) -> None:
    """The whole point of the button, from the click to the mode being on."""
    assert not picking(client), "nothing should be picking before the button"

    act(client, "pickEntity", {"mode": "pick"})

    assert picking(client), (
        "the panel asked for Pick Entity and Pick Entity did not start -- "
        "check that `ankigta:pickEntityStart` is registered with `addEvent`, "
        "because a handler alone is not registration"
    )


def test_the_panel_gets_out_of_the_way_before_the_world_is_aimed_at(
    client: MtaSandbox,
) -> None:
    """A panel over the world is a panel between the player and the target."""
    for handler in client.bound_keys.get(("F7", "down"), []):
        handler()
    assert client.eval("function() return ANKIGTA.Panel.isOpen() end")()

    act(client, "pickEntity", {"mode": "pick"})

    assert not client.eval("function() return ANKIGTA.Panel.isOpen() end")()
    assert picking(client)


def test_escape_leaves_pick_entity_and_brings_the_panel_back(
    client: MtaSandbox,
) -> None:
    """Cancelling is a way out, not a dead end with the controls still taken."""
    act(client, "pickEntity", {"mode": "pick"})
    assert picking(client)

    client.eval("function() cancelPickEntity() end")()

    assert not picking(client)
    assert client.eval("function() return ANKIGTA.Panel.isOpen() end")(), (
        "Pick Entity closed the panel on its way in and owes it back"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
