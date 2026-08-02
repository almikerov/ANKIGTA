"""Point at an object the stock Map Editor placed, and hang a card on it.

Before this, Pick Entity would only accept an object ANKIGTA had already
adopted, so a map full of editor objects showed the one row that shipped as a
fixture, and there was no way from the panel to add a second. Adoption existed
-- `prepareObjectPendingMapSave` -- but nothing reached it.

`me:ID` stays the gate. It is what the stock editor writes and what puts the
object's identity in a `.map` file rather than in a session, so it is the only
thing that can bring the same object back for the card to still mean something.
An object another resource spawned carries none, and stays out.
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
    manifest = ElementTree.parse(RESOURCE / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in ("shared", "client")
    ]


@pytest.fixture
def client() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    for script in manifest_client_scripts():
        sandbox.load(script)
    sandbox.trigger("onClientResourceStart")
    sandbox.eval(
        'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
    )()
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
    sandbox.eval(
        """
        function(action, payload)
            triggerEvent("ankigta:panelAction", resourceRoot, action, payload)
        end
        """
    )(action, json.dumps(payload or {}))


def click_on(sandbox: MtaSandbox, element: Any) -> None:
    """A left click with the cursor over `element`, as MTA reports it."""
    sandbox.eval(
        """
        function(target)
            triggerEvent("onClientClick", root,
                "left", "down", 100, 100, 1, 2, 3, target)
        end
        """
    )(element)


def sent(sandbox: MtaSandbox, name: str) -> list[Any]:
    return [
        event for event in sandbox.recorder.server_events if event.name == name
    ]


def test_an_object_from_a_loaded_map_is_offered_although_no_editor_is_open(
    client: MtaSandbox,
) -> None:
    """The real case: spawned in freeroam, on a map somebody built earlier.

    `me:ID` is written by the stock Map Editor and only while the map is open
    in it. Requiring it meant a player merely walking around a map full of
    objects was offered none of them -- the gate is the `id` the `.map` file
    gave the element, which is there whenever the map is loaded at all.
    """
    fresh = client.add_world_element(
        "object", map_id="object (sw_hedstones) (1)"
    )

    act(client, "pickEntity", {"mode": "pick"})
    click_on(client, fresh)

    asked = sent(client, "ankigta:pickEntity")
    assert asked, (
        "an object the stock editor placed was refused before the server was "
        "even asked about it"
    )
    # Compared by the name the map file gave it: two lupa wrappers around one
    # Lua table are not the same Python object.
    assert asked[-1].args[0]["__id"] == "object (sw_hedstones) (1)"


def test_an_object_no_map_file_named_is_taken_by_where_it_stands(
    client: MtaSandbox,
) -> None:
    """A freeroam vehicle has no name in any file, and is still takeable.

    The prior resource keyed on what a thing is and where it stands, which is
    why it could take one. The trade is real and is not hidden: move the thing
    and the name changes. A `.map` id, where there is one, is preferred for
    exactly that reason.
    """
    spawned = client.add_world_element("vehicle", x=12.0, y=20.0, z=3.0)

    act(client, "pickEntity", {"mode": "pick"})
    click_on(client, spawned)

    assert sent(client, "ankigta:pickEntity"), (
        "an element with no map-file name must still be offered -- naming it "
        "by where it stands is what the old resource did"
    )


def test_the_cursor_is_the_aim_so_this_works_outside_the_map_editor(
    client: MtaSandbox,
) -> None:
    """Pick Entity shows the cursor rather than hiding it.

    MTA raises `onClientClick` from the cursor position, so with the cursor
    hidden the click never arrived at all -- and aiming by turning the whole
    camera is not usable while spawned in freeroam.
    """
    act(client, "pickEntity", {"mode": "pick"})

    assert client.eval("function() return isCursorShowing() end")()


def test_linking_a_card_adopts_the_object_the_player_pointed_at(
    client: MtaSandbox,
) -> None:
    """Adoption and the link are one act: the card is what the object is for."""
    fresh = client.add_world_element("object", **{"me:ID": "editor-7"})
    act(client, "pickEntity", {"mode": "pick"})
    click_on(client, fresh)
    # The server accepted it as adoptable and sent the element back.
    client.eval(
        """
        function(target)
            triggerEvent("ankigta:pickEntityResult", resourceRoot,
                true, "adoptable", false, false, "pick", target)
        end
        """
    )(fresh)

    act(client, "selectCard", {"cardId": "1001", "collectionUuid": "abc"})
    act(client, "link")

    adopted = sent(client, "ankigta:adoptEntity")
    assert adopted, "Link on an unadopted object must ask the server to adopt it"
    assert adopted[-1].args[0]["me:ID"] == "editor-7"
    assert adopted[-1].args[1]["cardId"] == 1001
    assert not sent(client, "ankigta:linkCardToEntity"), (
        "there is no map entity to link to yet -- adoption is what makes one"
    )


def test_the_page_is_told_it_may_link_although_no_row_is_selected(
    client: MtaSandbox,
) -> None:
    """Otherwise the button the player needs is the one that is greyed out."""
    fresh = client.add_world_element("object", **{"me:ID": "editor-7"})
    for handler in client.bound_keys.get(("F7", "down"), []):
        handler()
    act(client, "pickEntity", {"mode": "pick"})
    click_on(client, fresh)
    client.eval(
        """
        function(target)
            triggerEvent("ankigta:pickEntityResult", resourceRoot,
                true, "adoptable", false, false, "pick", target)
        end
        """
    )(fresh)
    act(client, "ready")

    selected = client.pushed_panel_state()["selected"]
    assert selected["adopting"] is True
    assert selected["mapId"] is False, "an unadopted object has no row to be"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
