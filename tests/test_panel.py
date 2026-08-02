"""Ticket 32 — one local CEF panel instead of a pile of CEGUI windows.

What a test can honestly assert about an HTML view is the conversation around
it: which browser was created, what Lua asked the page to render, and what the
resource does when the page answers. How it looks is a manual checklist item.

Two defects named by the owner as things the previous attempt got wrong are
pinned here rather than left to review: the cursor has to come back on *every*
exit path, and a list shown to a person is never ordered by raw id.
"""

from __future__ import annotations

import json
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox
from tests.lua.sandbox import RESOURCE_ROOT


UUID = "11111111-1111-4111-8111-111111111111"


def manifest_client_scripts() -> list[str]:
    manifest = ElementTree.parse(RESOURCE_ROOT / "meta.xml")
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
    try:
        yield sandbox
    finally:
        sandbox.close()


def press_f7(sandbox: MtaSandbox) -> None:
    for handler in sandbox.bound_keys.get(("F7", "down"), []):
        handler()


def authorize(sandbox: MtaSandbox) -> None:
    sandbox.eval(
        'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
    )()


def page_ready(sandbox: MtaSandbox) -> None:
    """The page telling Lua it has loaded, as app.js does on DOMContentLoaded."""
    sandbox.eval(
        """
        function()
            triggerEvent("ankigta:panelAction", resourceRoot, "ready", "{}")
        end
        """
    )()


def act(sandbox: MtaSandbox, action: str, payload: dict[str, Any] | None = None) -> None:
    sandbox.eval(
        """
        function(action, payload)
            triggerEvent("ankigta:panelAction", resourceRoot, action, payload)
        end
        """
    )(action, json.dumps(payload or {}))


def sent_states(sandbox: MtaSandbox) -> list[dict[str, Any]]:
    """Every state Lua pushed into the page, decoded."""
    states = []
    for code in sandbox.browser_javascript:
        start = code.find("(")
        end = code.rfind(")")
        if start == -1 or end == -1:
            continue
        try:
            states.append(json.loads(code[start + 1 : end]))
        except json.JSONDecodeError:
            continue
    return states


def last_state(sandbox: MtaSandbox) -> dict[str, Any]:
    states = sent_states(sandbox)
    assert states, "Lua never pushed a state into the page"
    return states[-1]


def server_events(sandbox: MtaSandbox, name: str) -> list[Any]:
    return [
        event for event in sandbox.recorder.server_events if event.name == name
    ]


# --- the browser itself -------------------------------------------------------


def test_f7_opens_one_local_browser_on_the_panel_page(client: MtaSandbox) -> None:
    authorize(client)

    press_f7(client)

    assert len(client.browsers) == 1
    # Remote browsers do not get the window.mta bridge honoured, so a panel
    # created remote would be a dead page (prototype 0006).
    assert client.browsers[0]["isLocal"] is True
    assert any("panel/index.html" in url for url in client.loaded_urls), (
        client.loaded_urls
    )


def test_f7_again_closes_the_panel(client: MtaSandbox) -> None:
    authorize(client)
    press_f7(client)

    press_f7(client)

    assert client.eval("function() return isPanelOpen() end")() is False


# --- the cursor comes back, on every path -------------------------------------


@pytest.mark.parametrize(
    "close",
    ["toggle", "resource_stop", "authorization_revoked"],
    ids=lambda value: str(value),
)
def test_the_cursor_is_restored_however_the_panel_ends(
    client: MtaSandbox, close: str
) -> None:
    """The previous attempt left the cursor on. Named by the owner, pinned here."""
    assert client.cursor_visible is False
    authorize(client)
    press_f7(client)
    assert client.cursor_visible is True

    if close == "toggle":
        press_f7(client)
    elif close == "resource_stop":
        client.trigger("onClientResourceStop")
    else:
        client.eval(
            'function() triggerEvent("ankigta:setAuthorized", resourceRoot, false) end'
        )()

    assert client.cursor_visible is False


def test_a_browser_that_cannot_be_created_leaves_the_cursor_alone(
    client: MtaSandbox,
) -> None:
    """Failing to open is not a reason to strand the player behind a cursor."""
    authorize(client)
    client.browser_available = False

    press_f7(client)

    assert client.cursor_visible is False
    assert client.eval("function() return isPanelOpen() end")() is False


def test_the_panel_does_not_take_a_cursor_that_was_already_showing(
    client: MtaSandbox,
) -> None:
    authorize(client)
    client.eval("function() showCursor(true) end")()

    press_f7(client)
    press_f7(client)

    # It was showing before the panel opened, so it is still showing after.
    assert client.cursor_visible is True


# --- what the page is told ----------------------------------------------------


def test_the_page_is_given_the_string_table_rather_than_baked_text(
    client: MtaSandbox,
) -> None:
    authorize(client)
    press_f7(client)

    page_ready(client)

    state = last_state(client)
    assert state["locale"]["panel.title"]
    assert state["locale"]["connection.connect"]
    assert state["language"] in ("en", "ru")


def test_the_language_setting_reaches_the_open_panel(client: MtaSandbox) -> None:
    authorize(client)
    press_f7(client)
    page_ready(client)

    client.eval('function() ANKIGTA.Locale.setLanguage("ru") end')()

    state = last_state(client)
    assert state["language"] == "ru"
    assert state["locale"]["connection.connect"] == "Подключиться"


# --- the connection gate ------------------------------------------------------


def announce(sandbox: MtaSandbox, **status: Any) -> None:
    sandbox.eval(
        """
        function(payload)
            triggerEvent(
                "ankigta:companionStatus", resourceRoot, fromJSON(payload)
            )
        end
        """
    )(json.dumps(status))


def test_a_disconnected_companion_opens_the_panel_on_its_gate(
    client: MtaSandbox,
) -> None:
    authorize(client)
    announce(client, state="disconnected", category="timeout")
    press_f7(client)
    page_ready(client)

    state = last_state(client)
    assert state["section"] == "connection"
    assert state["connection"]["state"] == "disconnected"
    assert state["connection"]["category"] == "timeout"


def test_a_connected_companion_opens_the_panel_on_the_workspace(
    client: MtaSandbox,
) -> None:
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)

    assert last_state(client)["section"] == "entities"


def test_connecting_from_the_gate_reaches_the_server(client: MtaSandbox) -> None:
    authorize(client)
    press_f7(client)
    page_ready(client)

    act(client, "connect")

    assert server_events(client, "ankigta:connectCompanion")


def test_the_gate_can_be_left_without_connecting(client: MtaSandbox) -> None:
    """The previous window could not be dismissed at all."""
    authorize(client)
    announce(client, state="disconnected", category="timeout")
    press_f7(client)
    page_ready(client)

    act(client, "close")

    assert client.eval("function() return isPanelOpen() end")() is False


def test_a_status_change_no_longer_opens_a_window_of_its_own(
    client: MtaSandbox,
) -> None:
    """The pop-up connection window is gone; the panel is the only surface.

    The Study window is still here and still opens on a status, which is why
    this asks about the connection window rather than about windows. It goes
    when the session lifts itself, in the same ticket.
    """
    announce(client, state="disconnected", category="timeout")

    titles = client.widget_texts("window")
    assert not [title for title in titles if "Companion Connection" in title], titles


# --- the entity workspace -----------------------------------------------------


def snapshot(sandbox: MtaSandbox) -> None:
    sandbox.eval(
        """
        function(uuid)
            triggerEvent("ankigta:f7Snapshot", resourceRoot, {
                visible = true,
                cardPicker = {enabled = true},
                history = {canUndo = false, canRedo = false},
                entities = {
                    {
                        mapEntity = {
                            mapId = "m1", entityId = "b", type = "object",
                            authored = {
                                position = {x = 1.0, y = 2.0, z = 3.0},
                                world = {interior = 0, dimension = 0},
                            },
                        },
                        runtimeInstance = {available = false},
                        link = {state = "Unlinked"},
                    },
                    {
                        mapEntity = {
                            mapId = "m1", entityId = "a", type = "vehicle",
                            authored = {
                                position = {x = 4.0, y = 5.0, z = 6.0},
                                world = {interior = 0, dimension = 0},
                            },
                        },
                        runtimeInstance = {available = false},
                        link = {
                            state = "Active Spatial Link",
                            cardIdentity = {collectionUuid = uuid, cardId = 7},
                        },
                    },
                },
            })
        end
        """
    )(UUID)


def test_the_entities_reach_the_page_with_their_link_state(
    client: MtaSandbox,
) -> None:
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)

    snapshot(client)

    entities = last_state(client)["entities"]
    assert len(entities) == 2
    assert {entry["entityId"] for entry in entities} == {"a", "b"}
    assert all("linkState" in entry for entry in entities)


def test_entities_are_ordered_for_a_reader_not_by_raw_id(
    client: MtaSandbox,
) -> None:
    """The previous attempt sorted by id, which is nobody's mental model."""
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)

    snapshot(client)

    entities = last_state(client)["entities"]
    # The linked one is the one with work already done on it and comes first;
    # the arrival order of the snapshot put it second.
    assert entities[0]["linkState"] == "Active Spatial Link"


# --- the page carries keys, not sentences -------------------------------------


def panel_file(name: str) -> str:
    return (RESOURCE_ROOT / "client" / "panel" / name).read_text(encoding="utf-8")


def test_the_page_ships_no_readable_text_of_its_own() -> None:
    """A key in the markup, a sentence only from the table.

    The Cyrillic guard reads compiled Lua chunks and cannot see an HTML file,
    so the page needs its own check — otherwise the one place with no guard is
    the one place with the most words.
    """
    import re

    page = panel_file("index.html")
    # Text nodes between tags, minus the ones that are only whitespace.
    stray = [
        fragment.strip()
        for fragment in re.findall(r">([^<>]+)<", page)
        if fragment.strip()
    ]
    # ANKIGTA is a product name, not a word to translate. It appears twice:
    # the document title and the heading.
    assert set(stray) == {"ANKIGTA"}, stray


def test_every_key_the_page_asks_for_exists_in_english() -> None:
    import re

    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/locale.lua")
        english = sandbox.eval("ANKIGTA.Locale.strings.en")
        known = {str(key) for key in english.keys()}
    finally:
        sandbox.close()

    page = panel_file("index.html")
    asked = set(re.findall(r'data-i18n="([^"]+)"', page))
    assert asked, "the page asks for no keys at all"
    assert asked <= known, asked - known

    # The keys app.js builds are prefixes; both families have to exist.
    app = panel_file("app.js")
    for prefix in re.findall(r'"([a-z][a-zA-Z.]*\.)" \+', app):
        assert any(key.startswith(prefix) for key in known), prefix


def test_opening_the_panel_asks_for_the_status_it_has_not_been_told(
    client: MtaSandbox,
) -> None:
    """A stable connection sends nothing, and silence is not disconnection.

    The gateway publishes a status when it changes and when a player logs in.
    A panel opened at any other moment has never been told anything, and
    treating that as `disconnected` showed the connection gate over a healthy
    link — which reads exactly like the connection dropping again.
    """
    authorize(client)

    press_f7(client)

    assert server_events(client, "ankigta:requestCompanionStatus")


# --- the workspace actions ----------------------------------------------------


def linked_snapshot(sandbox: MtaSandbox) -> None:
    sandbox.eval(
        """
        function(uuid)
            triggerEvent("ankigta:f7Snapshot", resourceRoot, {
                visible = true,
                cardPicker = {enabled = true},
                history = {canUndo = true, canRedo = true},
                entities = {
                    {
                        mapEntity = {
                            mapId = "m1", entityId = "e1", type = "object",
                            authored = {
                                position = {x = 1.0, y = 2.0, z = 3.0},
                                world = {interior = 0, dimension = 0},
                            },
                        },
                        runtimeInstance = {available = true},
                        link = {
                            state = "Active Spatial Link",
                            recheckAvailable = true,
                            cardIdentity = {collectionUuid = uuid, cardId = 7},
                        },
                    },
                },
            })
        end
        """
    )(UUID)


def open_workspace(sandbox: MtaSandbox) -> None:
    authorize(sandbox)
    announce(sandbox, state="connected")
    press_f7(sandbox)
    page_ready(sandbox)
    linked_snapshot(sandbox)
    act(sandbox, "select", {"mapId": "m1", "entityId": "e1"})


def test_every_workspace_action_reaches_the_event_it_always_did(
    client: MtaSandbox,
) -> None:
    """The panel replaces the windows; it does not replace the protocol."""
    open_workspace(client)

    act(client, "unlink")
    act(client, "recheck")
    act(client, "copyDecision", {"decision": "new_copy"})
    act(client, "undo")
    act(client, "redo")
    act(client, "searchCards", {"query": "", "deck": "Chinese"})

    for name in (
        "ankigta:unlinkCardFromEntity",
        "ankigta:recheckPendingMapSave",
        "ankigta:resolveMapCopyDecision",
        "ankigta:undo",
        "ankigta:redo",
        "ankigta:requestCardPicker",
    ):
        assert server_events(client, name), name


def test_an_action_with_nothing_selected_sends_nothing(client: MtaSandbox) -> None:
    """A button that acts on "whatever was last in the list" is how a
    confirmation ends up applied to the wrong row."""
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)
    linked_snapshot(client)

    act(client, "unlink")
    act(client, "recheck")

    assert server_events(client, "ankigta:unlinkCardFromEntity") == []
    assert server_events(client, "ankigta:recheckPendingMapSave") == []


def test_linking_needs_both_a_map_entity_and_a_card(client: MtaSandbox) -> None:
    open_workspace(client)

    act(client, "link")
    assert server_events(client, "ankigta:linkCardToEntity") == []

    act(client, "selectCard", {"cardId": "7", "collectionUuid": UUID})
    act(client, "link")

    events = server_events(client, "ankigta:linkCardToEntity")
    assert events
    identity = client.to_python(events[-1].args[2])
    assert identity["cardId"] == 7
    assert identity["collectionUuid"] == UUID


def test_the_card_list_is_not_ordered_by_card_id(client: MtaSandbox) -> None:
    """Named by the owner as a defect of the previous attempt."""
    open_workspace(client)
    client.eval(
        """
        function(uuid)
            triggerEvent("ankigta:cardPickerSnapshot", resourceRoot, {
                enabled = true,
                cards = {
                    {identity = {collectionUuid = uuid, cardId = 1},
                     deck = {name = "Zebra"}, state = "review"},
                    {identity = {collectionUuid = uuid, cardId = 9},
                     deck = {name = "Alpha"}, state = "review"},
                },
            })
        end
        """
    )(UUID)

    cards = last_state(client)["cardPicker"]["cards"]
    assert [card["deck"] for card in cards] == ["Alpha", "Zebra"]


def test_a_server_notice_reaches_the_panel_as_well_as_the_chat(
    client: MtaSandbox,
) -> None:
    open_workspace(client)

    client.eval(
        """
        function()
            triggerEvent(
                "ankigta:pendingMapSaveNotice",
                resourceRoot,
                "notice.unlinked",
                "unlink"
            )
        end
        """
    )()

    assert last_state(client)["notice"]["key"] == "notice.unlinked"
    assert client.chat


# --- dragging -----------------------------------------------------------------


def cursor_at(sandbox: MtaSandbox, x: float, y: float) -> None:
    """Where MTA says the cursor is, in the 0..1 the API actually returns."""
    width, height = 1920.0, 1080.0
    sandbox.cursor_position = (x / width, y / height)


def hold_mouse(sandbox: MtaSandbox, down: bool) -> None:
    sandbox.key_states["mouse1"] = down


def render(sandbox: MtaSandbox) -> None:
    sandbox.trigger("onClientRender")


def panel_rect(sandbox: MtaSandbox) -> Any:
    return sandbox.eval(
        'function() return {ANKIGTA.Layout.rect("panel")} end'
    )()


def test_the_panel_is_dragged_by_its_top_bar(client: MtaSandbox) -> None:
    """The page cannot move its own window, so Lua moves it.

    The previous resource did exactly this: mousedown on the bar starts it,
    a render loop follows the cursor, and releasing the button ends it.
    """
    authorize(client)
    press_f7(client)
    page_ready(client)
    before = panel_rect(client)

    cursor_at(client, 900, 400)
    hold_mouse(client, True)
    act(client, "dragStart")
    cursor_at(client, 1000, 460)
    render(client)

    after = panel_rect(client)
    assert (after[1], after[2]) != (before[1], before[2]), (before, after)
    assert after[1] == before[1] + 100
    assert after[2] == before[2] + 60


def test_letting_go_of_the_button_ends_the_drag(client: MtaSandbox) -> None:
    """A mouseup that lands outside the page never reaches it, so the loop
    watches the button rather than waiting to be told."""
    authorize(client)
    press_f7(client)
    page_ready(client)

    cursor_at(client, 900, 400)
    hold_mouse(client, True)
    act(client, "dragStart")
    cursor_at(client, 1000, 400)
    render(client)
    moved = panel_rect(client)

    hold_mouse(client, False)
    render(client)
    cursor_at(client, 1400, 400)
    render(client)

    assert panel_rect(client)[1] == moved[1]


def test_a_dragged_panel_is_remembered_as_a_fraction_of_the_screen(
    client: MtaSandbox,
) -> None:
    """Ticket 28's rule: a placement means the same corner at any resolution."""
    authorize(client)
    press_f7(client)
    page_ready(client)

    cursor_at(client, 900, 400)
    hold_mouse(client, True)
    act(client, "dragStart")
    cursor_at(client, 700, 300)
    render(client)
    hold_mouse(client, False)

    placement = client.eval(
        'function() return ANKIGTA.Layout.placements["panel"] end'
    )()
    assert placement is not None
    assert 0 <= placement.x <= 1 and 0 <= placement.y <= 1


def test_the_panel_never_leaves_the_screen(client: MtaSandbox) -> None:
    authorize(client)
    press_f7(client)
    page_ready(client)

    cursor_at(client, 900, 400)
    hold_mouse(client, True)
    act(client, "dragStart")
    cursor_at(client, 5000, 5000)
    render(client)

    rect = panel_rect(client)
    x, y, width, height = rect[1], rect[2], rect[3], rect[4]
    assert x >= 0 and y >= 0
    assert x + width <= 1920 and y + height <= 1080
