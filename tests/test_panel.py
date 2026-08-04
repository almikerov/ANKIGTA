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
    return sandbox.pushed_panel_states()


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


def test_the_panel_gives_the_cursor_back_to_whoever_else_wanted_it(
    client: MtaSandbox,
) -> None:
    """Opening over another resource's window, and closing, changes nothing.

    MTA counts cursor requests across resources and shows it while the count is
    above zero. Reading `isCursorShowing()` on the way in reads somebody else's
    answer, and handing that answer back on the way out means never letting go:
    open Hot Reload, then this, then close both, and the cursor stays on screen
    with nothing left to dismiss it.
    """
    authorize(client)
    client.another_resource_shows_cursor()

    press_f7(client)
    assert client.cursor_visible is True
    press_f7(client)

    # The other resource is still asking, so it is still on.
    assert client.cursor_visible is True

    # And when that one closes too, it goes -- which is the bug: it did not.
    client.another_resource_hides_cursor()
    assert client.cursor_visible is False


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


def test_opening_the_panel_requests_the_current_connection_fields(
    client: MtaSandbox,
) -> None:
    authorize(client)
    announce(client, state="disconnected")

    press_f7(client)

    assert server_events(client, "ankigta:requestConnectionSettings")


def test_the_connection_screen_receives_prefilled_port_and_token_state(
    client: MtaSandbox,
) -> None:
    authorize(client)
    announce(client, state="disconnected", category="timeout")
    press_f7(client)
    page_ready(client)

    client.trigger(
        "ankigta:connectionSettingsSnapshot",
        client.eval("resourceRoot"),
        client.lua.table_from(
            {
                "valid": True,
                "mode": "automatic",
                "port": 40123,
                "tokenConfigured": True,
                "tokenDisabled": False,
            }
        ),
    )

    connection = last_state(client)["connection"]
    assert connection["state"] == "disconnected"
    assert connection["port"] == 40123
    assert connection["tokenConfigured"] is True


def test_changing_connection_fields_applies_without_confirmation(
    client: MtaSandbox,
) -> None:
    authorize(client)
    announce(client, state="disconnected")
    press_f7(client)
    page_ready(client)

    act(
        client,
        "updateConnection",
        {"mode": "manual", "port": 40123, "token": "new", "keepToken": False},
    )

    updates = server_events(client, "ankigta:updateConnectionSettings")
    assert len(updates) == 1
    assert updates[0].args[0]["port"] == 40123


def test_a_refused_connection_port_reports_the_reason_on_its_own_row(
    client: MtaSandbox,
) -> None:
    authorize(client)
    announce(client, state="disconnected")
    press_f7(client)
    page_ready(client)

    client.trigger(
        "ankigta:settingRejected",
        client.eval("resourceRoot"),
        "connectionPort",
        "settings.error.out_of_range",
    )

    connection = last_state(client)["connection"]
    assert connection["portError"] == "settings.error.out_of_range"
    assert connection["tokenError"] is False


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


def test_the_expression_and_the_scope_the_page_chose_reach_the_server(
    client: MtaSandbox,
) -> None:
    """The panel is the only place an Anki expression can be written.

    It reaches the server as written -- `-is:suspended` means "not suspended"
    to Anki and nothing at all to a substring match -- and the note/card switch
    travels with it, because it decides what the rows come back as.
    """
    open_workspace(client)

    act(
        client,
        "searchCards",
        {"query": "deck:Spanish tag:verb -is:suspended", "deck": "", "scope": "notes"},
    )

    request = server_events(client, "ankigta:requestCardPicker")[-1]
    assert request.args[0] == "deck:Spanish tag:verb -is:suspended"
    assert request.args[4] == "notes"


def test_a_search_with_no_scope_chosen_leaves_the_server_to_its_default(
    client: MtaSandbox,
) -> None:
    """`""` is not a scope, and the server refuses one it does not have."""
    open_workspace(client)

    act(client, "searchCards", {"query": "", "deck": "", "scope": ""})

    assert server_events(client, "ankigta:requestCardPicker")[-1].args[4] is False


def test_the_page_is_told_what_the_rows_it_has_are_an_answer_to(
    client: MtaSandbox,
) -> None:
    open_workspace(client)
    client.eval(
        """
        function()
            triggerEvent("ankigta:cardPickerSnapshot", resourceRoot, {
                enabled = true,
                cards = {},
                query = "tag:verb",
                scope = "notes",
            })
        end
        """
    )()

    picker = last_state(client)["cardPicker"]
    assert picker["query"] == "tag:verb"
    assert picker["scope"] == "notes"


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


# --- the settings section -----------------------------------------------------


def open_settings(sandbox: MtaSandbox) -> None:
    act(sandbox, "openSettings")


def settings_rows(sandbox: MtaSandbox) -> list[dict[str, Any]]:
    return last_state(sandbox).get("settings", {}).get("rows", [])


def row_for(sandbox: MtaSandbox, key: str) -> dict[str, Any]:
    for row in settings_rows(sandbox):
        if row["key"] == key:
            return row
    raise AssertionError(f"{key} is not offered: {[r['key'] for r in settings_rows(sandbox)]}")


def test_settings_are_a_section_of_the_panel_not_a_window(
    client: MtaSandbox,
) -> None:
    """The last window folds in; eight became one, and now one becomes none."""
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)

    open_settings(client)

    assert last_state(client)["section"] == "settings"
    titles = client.widget_texts("window")
    assert not [title for title in titles if "Settings" in title], titles


def test_every_setting_the_schema_owns_is_offered(client: MtaSandbox) -> None:
    """Built from the schema, so a setting added later cannot go unreachable."""
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)
    open_settings(client)

    offered = {row["key"] for row in settings_rows(client)}
    expected = set(
        client.eval(
            """
            function()
                local keys = {}
                for key in pairs(ANKIGTA.Settings.schema) do
                    table.insert(keys, key)
                end
                return keys
            end
            """
        )().values()
    )
    # The two the panel deliberately keeps elsewhere: a secret is never shown
    # back, and placement is dragged rather than typed.
    assert expected - offered <= {"connectionToken", "uiPlacement"}


def test_a_row_carries_the_control_its_rule_asks_for(client: MtaSandbox) -> None:
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)
    open_settings(client)

    assert row_for(client, "activationRadius")["kind"] == "number"
    assert row_for(client, "reviewProtection")["kind"] == "boolean"
    assert row_for(client, "indicatorMode")["kind"] == "choice"
    assert row_for(client, "indicatorMode")["options"]


def test_a_number_row_carries_its_range_so_the_field_can_say_it(
    client: MtaSandbox,
) -> None:
    """Helper text beats discovering the range by being refused."""
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)
    open_settings(client)

    row = row_for(client, "activationRadius")
    assert row["min"] == 0.5
    assert row["max"] == 50
    assert row["step"]


def test_a_refused_value_is_reported_on_its_own_row(client: MtaSandbox) -> None:
    """Errors belong next to the field, never collected at the top."""
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)
    open_settings(client)

    act(client, "setSetting", {"key": "activationRadius", "value": 500})

    row = row_for(client, "activationRadius")
    assert row["error"], row
    # The reason is a key the string table translates, not a sentence from here.
    assert row["error"].startswith("settings.error.")


def test_an_accepted_value_clears_the_reason_it_replaced(
    client: MtaSandbox,
) -> None:
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)
    open_settings(client)
    act(client, "setSetting", {"key": "activationRadius", "value": 500})
    assert row_for(client, "activationRadius")["error"]

    act(client, "setSetting", {"key": "activationRadius", "value": 7})

    assert not row_for(client, "activationRadius")["error"]
    # The value itself does not move yet: this one is the server's, and
    # snapping the field while it is still deciding would read as a refusal.
    # The snapshot is what shows the new number.
    client.eval(
        """
        function()
            triggerEvent("ankigta:settingsSnapshot", resourceRoot,
                {activationRadius = 7})
        end
        """
    )()
    assert row_for(client, "activationRadius")["value"] == 7


def test_a_client_owned_setting_is_stored_without_asking_the_server(
    client: MtaSandbox,
) -> None:
    """ADR 0014: the player's machine owns it, so nothing is sent anywhere."""
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)
    open_settings(client)
    before = len(client.recorder.server_events)

    act(client, "setSetting", {"key": "reviewProtection", "value": False})

    assert not [
        event
        for event in client.recorder.server_events[before:]
        if event.name == "ankigta:updateSetting"
    ]
    assert row_for(client, "reviewProtection")["value"] is False


def test_a_server_owned_setting_is_asked_for_rather_than_stored_here(
    client: MtaSandbox,
) -> None:
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)
    open_settings(client)

    act(client, "setSetting", {"key": "activationRadius", "value": 7})

    assert [
        event
        for event in client.recorder.server_events
        if event.name == "ankigta:updateSetting"
    ]


def test_the_ui_scale_lives_here_too(client: MtaSandbox) -> None:
    """Ticket 28's own panel folds in with the rest."""
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)
    open_settings(client)

    assert row_for(client, "uiScale")["kind"] == "number"

    act(client, "setSetting", {"key": "uiScale", "value": 1.25})

    assert client.eval("function() return ANKIGTA.Layout.scale() end")() == 1.25


def test_leaving_settings_returns_to_where_the_player_was(
    client: MtaSandbox,
) -> None:
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)
    open_settings(client)

    act(client, "closeSettings")

    assert last_state(client)["section"] == "entities"


def test_the_secret_is_never_sent_back_to_the_page(client: MtaSandbox) -> None:
    authorize(client)
    announce(client, state="connected")
    press_f7(client)
    page_ready(client)
    open_settings(client)

    blob = json.dumps(last_state(client))
    assert "connectionToken" not in [row["key"] for row in settings_rows(client)]
    assert "Bearer" not in blob
