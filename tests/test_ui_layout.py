"""Ticket 28 — UI Scale and layout.

The interface has to stay usable at every supported resolution, at every
allowed scale, and after the player has moved things around. Three rules do
most of the work:

- a surface is never bigger than the screen, so its title is always grabbable
  and its buttons are always reachable;
- a placement is a fraction of the screen, so it means the same thing at
  1280x720 and 3840x2160;
- a placement is client-owned, so it never reaches the server (ADR 0028).

Everything here runs the real client scripts in a real Lua 5.1 interpreter and
reads the geometry back off the controls the resource created. What only a
human can judge -- whether the result is readable -- is in
`docs/checklists/ticket28-ui-scale-layout.md`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox
from tests.lua.constants import string_constants


RESOURCE = Path(__file__).resolve().parents[1] / "mta" / "ankigta"
UUID = "11111111-1111-4111-8111-111111111111"

#: The resolutions story 54 names.
RESOLUTIONS = [(1280, 720), (1920, 1080), (3840, 2160)]

#: The bounds the schema allows, plus the shipped default.
SCALES = [0.5, 1, 2]

#: Every surface the layout manager places, with the window that shows it. The
#: dx-drawn ones have no control to read back, so they are listed separately.
WINDOW_SURFACES = [
    "panel",
]
DRAWN_SURFACES = ["review", "hud"]


def manifest_client_scripts() -> list[str]:
    """The client scripts meta.xml declares, in declared order."""
    manifest = ElementTree.parse(RESOURCE / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in ("shared", "client")
    ]


def start_client(
    files: dict[str, bytes] | None = None,
    *,
    width: float = 1920,
    height: float = 1080,
    language: str = "en",
) -> MtaSandbox:
    """The whole client side, started the way MTA starts it."""
    sandbox = MtaSandbox()
    sandbox.screen_width, sandbox.screen_height = width, height
    if files is not None:
        sandbox.files.update(files)
    for script in manifest_client_scripts():
        sandbox.load(script)
    sandbox.trigger("onClientResourceStart")
    # The panel belongs to the Study Player, and so does the way into it.
    sandbox.eval(
        'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
    )()
    # These are about layout, not about the gate: the gate legitimately wins
    # the section while there is no companion, so give them one.
    sandbox.eval(
        """
        function()
            triggerEvent("ankigta:companionStatus", resourceRoot,
                {state = "connected"})
        end
        """
    )()
    sandbox.eval("function(l) ANKIGTA.Locale.setLanguage(l) end")(language)
    return sandbox


def set_setting_action(sandbox: MtaSandbox, action: str, payload: Any) -> None:
    sandbox.eval(
        """
        function(action, payload)
            triggerEvent("ankigta:panelAction", resourceRoot, action, payload)
        end
        """
    )(action, json.dumps(payload))


def pushed_section(sandbox: MtaSandbox) -> str:
    for code in reversed(sandbox.browser_javascript):
        start, end = code.find("("), code.rfind(")")
        if start == -1 or end == -1:
            continue
        try:
            return str(json.loads(code[start + 1 : end])["section"])
        except (json.JSONDecodeError, KeyError):
            continue
    raise AssertionError("the panel pushed no state")


@pytest.fixture
def client() -> Iterator[MtaSandbox]:
    sandbox = start_client()
    try:
        yield sandbox
    finally:
        sandbox.close()


# --- driving the interface ---------------------------------------------------


def text(sandbox: MtaSandbox, key: str) -> str:
    return str(
        sandbox.eval("function(k) return ANKIGTA.Locale.text(k) end")(key)
    )


def scale(sandbox: MtaSandbox) -> float:
    return float(sandbox.eval("ANKIGTA.Layout.scale()"))


def set_scale(sandbox: MtaSandbox, value: Any) -> Any:
    return sandbox.eval("function(v) return ANKIGTA.Layout.setScale(v) end")(value)


def rect(sandbox: MtaSandbox, surface: str) -> tuple[float, float, float, float]:
    result = sandbox.eval("function(k) return ANKIGTA.Layout.rect(k) end")(surface)
    assert result[0] is not False, f"{surface}: {result[1]}"
    return tuple(float(value) for value in result[:4])  # type: ignore[return-value]


def placement(sandbox: MtaSandbox) -> dict[str, dict[str, float]]:
    stored = sandbox.eval("function() return ANKIGTA.Layout.snapshot() end")()
    return {
        str(key): {"x": float(stored[key]["x"]), "y": float(stored[key]["y"])}
        for key in stored.keys()
    }


def stored_settings(sandbox: MtaSandbox) -> dict[str, Any]:
    return json.loads(sandbox.read_file("@ankigta-settings.json"))


def open_f7(sandbox: MtaSandbox, *, link_state: str = "Active Spatial Link") -> None:
    """Open the window these placement tests drag.

    Ticket 32 moved F7 to a CEF page, which the layout manager sizes but does
    not place, so the settings panel is what stands in for "a window" here.
    The properties under test — dragged once, stored as a fraction, clamped
    back onto a smaller screen — belong to the manager, not to F7.
    """
    sandbox.eval(
        """
        function()
            triggerEvent("ankigta:setAuthorized", resourceRoot, true)
            triggerEvent("ankigta:openSettings", resourceRoot)
        end
        """
    )()


def _unused_open_f7(sandbox: MtaSandbox, *, link_state: str = "x") -> None:
    sandbox.eval(
        """
        function(uuid, linkState)
            triggerEvent("ankigta:setAuthorized", resourceRoot, true)
            triggerEvent("ankigta:f7Snapshot", resourceRoot, {
                visible = true,
                cardPicker = {enabled = true},
                history = {canUndo = true, canRedo = true},
                entities = {
                    {
                        mapEntity = {
                            mapId = "m1",
                            entityId = "e1",
                            type = "object",
                            authored = {
                                position = {x = 1.0, y = 2.0, z = 3.0},
                                world = {interior = 0, dimension = 0},
                            },
                        },
                        runtimeInstance = {available = false},
                        link = {
                            state = linkState,
                            cardIdentity = {collectionUuid = uuid, cardId = 7},
                        },
                    },
                },
            })
        end
        """
    )(UUID, link_state)


def open_card_picker(sandbox: MtaSandbox) -> None:
    sandbox.eval(
        """
        function(uuid)
            triggerEvent("ankigta:cardPickerSnapshot", resourceRoot, {
                enabled = true,
                cards = {
                    {
                        identity = {collectionUuid = uuid, cardId = 7},
                        deck = {name = "Deck"},
                        state = "new",
                    },
                },
                existingLinks = {},
            })
        end
        """
    )(UUID)


def select_first_row(sandbox: MtaSandbox) -> None:
    """Select the first F7 row, as a click on the grid does."""
    grid = sandbox.live_widgets("gridlist")[0]
    sandbox.widgets[grid].selected_row = 0
    sandbox.click_widget(grid)


def set_setting(sandbox: MtaSandbox, key: str, value: Any) -> None:
    """Change a setting the way the panel's one write path does."""
    sandbox.eval(
        """
        function(payload)
            triggerEvent("ankigta:panelAction", resourceRoot,
                "setSetting", payload)
        end
        """
    )(json.dumps({"key": key, "value": value}))


def settings_row(sandbox: MtaSandbox, key: str) -> Any:
    for code in reversed(sandbox.browser_javascript):
        start, end = code.find("("), code.rfind(")")
        if start == -1 or end == -1:
            continue
        try:
            state = json.loads(code[start + 1 : end])
        except json.JSONDecodeError:
            continue
        for row in state.get("settings", {}).get("rows", []):
            if row["key"] == key:
                return row
    return None


def reset_layout(sandbox: MtaSandbox) -> None:
    sandbox.eval(
        'function() triggerEvent("ankigta:panelAction", resourceRoot,'
        ' "resetLayout", "{}") end'
    )()


def page_ready(sandbox: MtaSandbox) -> None:
    """The page telling Lua it loaded; nothing is pushed into it before that."""
    sandbox.eval(
        'function() triggerEvent("ankigta:panelAction", resourceRoot,'
        ' "ready", "{}") end'
    )()


def open_every_window(sandbox: MtaSandbox) -> None:
    """Put the panel on screen. Ticket 32 left exactly one surface to place."""
    sandbox.commands["ankigta-ui"][0]()
    page_ready(sandbox)


def panel_rect(sandbox: MtaSandbox) -> tuple[float, float, float, float]:
    rect = sandbox.eval('function() return {ANKIGTA.Layout.rect("panel")} end')()
    return rect[1], rect[2], rect[3], rect[4]


def drag_panel(sandbox: MtaSandbox, x: float, y: float) -> None:
    """Drag the panel to a screen position, the way a player does.

    The page reports only that a drag began; Lua follows the cursor. Both ends
    of that are exercised here rather than reaching for guiSetPosition, which
    would prove nothing about the path a player takes.
    """
    width, height = sandbox.eval("function() return guiGetScreenSize() end")()
    start_x, start_y, _w, _h = panel_rect(sandbox)
    sandbox.cursor_position = (start_x / width, start_y / height)
    sandbox.key_states["mouse1"] = True
    sandbox.eval(
        'function() triggerEvent("ankigta:panelAction", resourceRoot,'
        ' "dragStart", "{}") end'
    )()
    sandbox.cursor_position = (x / width, y / height)
    sandbox.trigger("onClientRender")
    sandbox.key_states["mouse1"] = False


def open_review(sandbox: MtaSandbox, *, side: str = "question") -> None:
    sandbox.eval(
        """
        function(uuid, side)
            triggerEvent("ankigta:openReviewMode", resourceRoot, {
                url = "http://127.0.0.1:51234/render/token/index.html",
                side = side,
                cardIdentity = {collectionUuid = uuid, cardId = 7},
            })
        end
        """
    )(UUID, side)
    sandbox.eval("function() renderReviewMode() end")()


def click(sandbox: MtaSandbox, x: float, y: float, state: str = "down") -> None:
    """A click at a screen position, as `onClientClick` reports one.

    Arguments three and four are the cursor; the world point follows
    (`CClientGame::ProcessMessage` pushes `vecCursorPosition` before
    `vecCollision`).
    """
    sandbox.trigger("onClientClick", None, "left", state, x, y, 0.0, 0.0, 0.0)


def move_cursor(sandbox: MtaSandbox, x: float, y: float) -> None:
    """`onClientCursorMove` reports the relative position, then the absolute."""
    sandbox.trigger(
        "onClientCursorMove",
        None,
        x / sandbox.screen_width,
        y / sandbox.screen_height,
        x,
        y,
        0.0,
        0.0,
        0.0,
    )


def drag_drawn_surface(
    sandbox: MtaSandbox,
    start: tuple[float, float],
    end: tuple[float, float],
) -> None:
    click(sandbox, *start, state="down")
    move_cursor(sandbox, *end)
    click(sandbox, *end, state="up")


# --- UI Scale ----------------------------------------------------------------


def test_ui_scale_defaults_to_one(client: MtaSandbox) -> None:
    assert client.eval('ANKIGTA.Settings.default("uiScale")') == 1
    assert scale(client) == 1


@pytest.mark.parametrize("value", [0.5, 0.75, 1, 1.23, 1.95, 2])
def test_ui_scale_accepts_the_range_story_54_gives_it(
    client: MtaSandbox,
    value: float,
) -> None:
    assert set_scale(client, value) is True
    assert scale(client) == value


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (0.49, "settings.error.out_of_range"),
        (2.01, "settings.error.out_of_range"),
        (3, "settings.error.out_of_range"),
        # Two decimal places by hand, no more.
        (1.234, "settings.error.too_precise"),
        ("large", "settings.error.not_a_number"),
    ],
)
def test_a_scale_outside_the_range_is_refused_with_a_reason_never_clamped(
    client: MtaSandbox,
    value: Any,
    reason: str,
) -> None:
    refused, why = set_scale(client, value)

    assert refused is False
    assert why == reason
    # Not clamped to the nearest allowed value: a scale the player never chose
    # is worse than a refusal they can read.
    assert scale(client) == 1


def test_ui_scale_steps_by_005_and_stops_at_the_bounds(
    client: MtaSandbox,
) -> None:
    """The step is the manager's rule, not a button's.

    Ticket 32 folded the +/- pair into one number row, so the rule is asserted
    where it lives rather than through two controls that no longer exist.
    """
    step = client.eval("ANKIGTA.Layout.scaleStep")
    assert step == 0.05

    client.commands["ankigta-ui"][0]()
    page_ready(client)
    set_setting(client, "uiScale", 1.05)
    assert scale(client) == 1.05

    # The bounds refuse rather than clamp, which is the same rule the row above
    # is checked against.
    refused, _why = set_scale(client, 2.05)
    assert refused is False
    assert scale(client) == 1.05

def test_a_value_typed_by_hand_is_taken_at_two_decimal_places(
    client: MtaSandbox,
) -> None:
    """The 0.05 step belongs to the buttons, not to the setting.

    Making it a validation rule would refuse 1.23, which story 54 allows.
    """
    client.commands["ankigta-ui"][0]()
    # UI scale is a row of the settings panel like any other, so the field
    # starts at the current value and Apply is the row's own button.
    set_setting(client, "uiScale", 1.23)

    assert scale(client) == 1.23


def test_a_refused_value_typed_by_hand_says_why_in_the_players_language(
    client: MtaSandbox,
) -> None:
    """Shown under the row it refused, not in the chat log.

    A reason that scrolls away with the next chat line is a reason the player
    can miss; the row keeps it next to the value that caused it.
    """
    client.eval("function(l) ANKIGTA.Locale.setLanguage(l) end")("ru")
    client.commands["ankigta-ui"][0]()
    page_ready(client)
    set_setting(client, "uiScale", 9)


    assert scale(client) == 1
    assert settings_row(client, "uiScale")["error"] == "settings.error.out_of_range"


def test_a_scale_change_reaches_an_open_window_without_reopening_it(
    client: MtaSandbox,
) -> None:
    """"Applies immediately" means the surface on screen, not the next one.

    The controls inside are HTML and scale with the page, so what this side
    still owns — and what this checks — is that the open surface itself grows
    without being closed and reopened.
    """
    open_f7(client)
    page_ready(client)
    before = panel_rect(client)

    set_scale(client, 1.5)

    after = panel_rect(client)
    assert after[2] == pytest.approx(before[2] * 1.5, abs=1)
    assert after[3] == pytest.approx(before[3] * 1.5, abs=1)

def test_the_scale_is_stored_and_reapplied_after_a_restart(
    client: MtaSandbox,
) -> None:
    set_scale(client, 1.35)
    assert stored_settings(client)["uiScale"] == 1.35

    restarted = start_client(dict(client.files))
    try:
        assert scale(restarted) == 1.35
    finally:
        restarted.close()


# --- reachability at every supported resolution -------------------------------


@pytest.mark.parametrize(
    ("width", "height"), RESOLUTIONS, ids=lambda value: str(value)
)
@pytest.mark.parametrize("wanted", SCALES)
def test_every_surface_stays_on_screen_at_every_resolution_and_scale(
    width: int,
    height: int,
    wanted: float,
) -> None:
    sandbox = start_client(width=width, height=height)
    try:
        assert set_scale(sandbox, wanted) is True
        # The modal surface only exists once a modal has been raised.
        open_f7(sandbox)

        for surface in WINDOW_SURFACES + DRAWN_SURFACES:
            x, y, surface_width, surface_height = rect(sandbox, surface)
            assert x >= 0 and y >= 0, surface
            assert x + surface_width <= width, surface
            assert y + surface_height <= height, surface
    finally:
        sandbox.close()


@pytest.mark.parametrize(
    ("width", "height"), RESOLUTIONS, ids=lambda value: str(value)
)
@pytest.mark.parametrize("wanted", SCALES)
def test_no_control_falls_outside_the_window_that_holds_it(
    width: int,
    height: int,
    wanted: float,
) -> None:
    """The layout acceptance test story 54 asks for, after ticket 32.

    The controls became HTML in one page, and CSS keeps them inside it — there
    is no CEGUI frame left to overflow. What is still this side's job, and
    still the thing story 54 is about, is that the surface itself is wholly on
    screen at every scale and resolution: a panel whose title bar is off the
    top is a panel that cannot be moved back.
    """
    sandbox = start_client(width=width, height=height)
    try:
        assert set_scale(sandbox, wanted) is True
        open_every_window(sandbox)

        x, y, panel_width, panel_height = panel_rect(sandbox)
        assert x >= 0 and y >= 0, (x, y)
        assert x + panel_width <= width, (x, panel_width, width)
        assert y + panel_height <= height, (y, panel_height, height)

        # Any CEGUI control still alive — the recovery screen is the last one —
        # keeps the original rule.
        windows = {
            index: sandbox.widgets[index]
            for index in sandbox.live_widgets("window")
        }
        for index, control in enumerate(sandbox.widgets):
            if control.destroyed or control.parent not in windows:
                continue
            frame = windows[control.parent]
            assert control.x >= 0 and control.y >= 0, (index, control.text)
            assert control.x + control.width <= frame.width + 1, (
                f"{control.kind} {control.text!r} runs past the right edge of "
                f"{frame.text!r} at {width}x{height} scale {wanted}"
            )
            assert control.y + control.height <= frame.height + 1, (
                f"{control.kind} {control.text!r} runs past the bottom of "
                f"{frame.text!r} at {width}x{height} scale {wanted}"
            )
    finally:
        sandbox.close()

def test_a_surface_too_big_for_the_screen_is_capped_and_the_setting_is_not() -> None:
    """F7 is 900x360 by design; at scale 2 that is taller than a 720p screen.

    The rendered size gives way, not the stored setting: clamping the setting
    would leave the player with a scale they never chose the next time they
    played at a bigger resolution.
    """
    sandbox = start_client(width=1280, height=720)
    try:
        assert set_scale(sandbox, 2) is True
        _x, _y, width, height = rect(sandbox, "panel")

        assert width <= 1280 and height <= 720
        assert width < 900 * 2
        assert scale(sandbox) == 2
        assert stored_settings(sandbox)["uiScale"] == 2
    finally:
        sandbox.close()


# --- moving windows -----------------------------------------------------------


def test_dragging_f7_by_its_title_is_remembered_as_a_fraction_of_the_screen(
    client: MtaSandbox,
) -> None:
    open_f7(client)

    drag_panel(client, 480, 216)

    assert placement(client)["panel"] == {"x": 0.25, "y": 0.2}


def test_a_window_is_movable_by_its_title_and_never_resizable(
    client: MtaSandbox,
) -> None:
    """Moved by its bar, and never resized by dragging an edge.

    The panel is a page, so "resizable" is not a property a player can reach:
    its size comes from UI Scale alone. What is still checkable here is that
    the bar moves it and the size does not change while it does.
    """
    client.commands["ankigta-ui"][0]()
    page_ready(client)
    _x, _y, width_before, height_before = panel_rect(client)

    drag_panel(client, 480, 216)

    x, y, width, height = panel_rect(client)
    assert (x, y) == (480, 216)
    assert (width, height) == (width_before, height_before)

def test_a_placement_survives_a_restart(client: MtaSandbox) -> None:
    open_f7(client)
    drag_panel(client, 480, 216)
    # The write is debounced, so a drag is one write rather than one per frame.
    client.fire_timers()
    assert stored_settings(client)["uiPlacement"]["panel"] == {"x": 0.25, "y": 0.2}

    restarted = start_client(dict(client.files))
    try:
        open_f7(restarted)
        assert panel_rect(restarted)[:2] == (480, 216)
    finally:
        restarted.close()


def test_a_drag_is_written_once_rather_than_once_per_frame(
    client: MtaSandbox,
) -> None:
    """CEGUI reports a drag as a stream of moves."""
    open_f7(client)

    for step in range(20):
        drag_panel(client, 400 + step, 300 + step)

    pending = [timer for timer in client.recorder.timers if not timer.cancelled]
    assert len([timer for timer in pending if timer.repeats == 1]) == 1


def test_a_placement_made_at_one_resolution_lands_in_the_same_place_at_another(
    client: MtaSandbox,
) -> None:
    """Normalized, so the corner means the same thing on every screen."""
    open_f7(client)
    drag_panel(client, 480, 216)
    client.fire_timers()

    for width, height in RESOLUTIONS:
        restarted = start_client(dict(client.files), width=width, height=height)
        try:
            x, y, panel_width, panel_height = rect(restarted, "panel")
            # The fraction is what was stored, so it lands in the same place —
            # except where the surface is nearly as large as the screen, and
            # then being wholly visible wins over being at the same fraction.
            # Both are ticket 28's rule; the clamp is the half that matters at
            # 1280x720.
            assert (x, y) == (
                min(round(0.25 * width), width - panel_width),
                min(round(0.2 * height), height - panel_height),
            )
            assert x >= 0 and y >= 0
            assert x + panel_width <= width and y + panel_height <= height
        finally:
            restarted.close()


def test_a_placement_off_the_new_screen_is_clamped_back_onto_it() -> None:
    """A window dragged to the bottom-right of a 4K screen, reopened at 720p."""
    big = start_client(width=3840, height=2160)
    try:
        open_f7(big)
        _x, _y, width, height = rect(big, "panel")
        drag_panel(big, 3840 - width, 2160 - height)
        big.fire_timers()
        files = dict(big.files)
    finally:
        big.close()

    small = start_client(files, width=1280, height=720)
    try:
        x, y, width, height = rect(small, "panel")
        assert x + width <= 1280
        assert y + height <= 720
        # The title bar is what the player has to be able to grab.
        assert y >= 0 and x >= 0
    finally:
        small.close()


def test_the_screen_changing_size_puts_an_open_window_back_on_it(
    client: MtaSandbox,
) -> None:
    """MTA reports no resolution change, so the manager polls for it."""
    open_f7(client)
    drag_panel(client, 1000, 700)

    client.screen_width, client.screen_height = 1280, 720
    client.eval("function() return ANKIGTA.Layout.refresh() end")()

    x, y, width, height = panel_rect(client)
    assert x + width <= 1280
    assert y + height <= 720


def test_a_stored_placement_that_is_not_one_is_discarded_with_a_diagnostic() -> None:
    sandbox = MtaSandbox()
    sandbox.write_file(
        "@ankigta-settings.json",
        json.dumps({"uiPlacement": {"panel": {"x": 4.5, "y": -2}}}),
    )
    try:
        for script in manifest_client_scripts():
            sandbox.load(script)
        sandbox.trigger("onClientResourceStart")

        assert placement(sandbox) == {}
        assert any(
            "discarded_stored_setting" in line
            for line in sandbox.recorder.debug_messages()
        )
    finally:
        sandbox.close()


def test_a_placement_the_file_will_not_take_is_reported_rather_than_lost(
    client: MtaSandbox,
) -> None:
    """The window stays where the player put it; the file did not take it."""
    open_f7(client)
    client.file_writes_fail = True

    drag_panel(client, 480, 216)
    client.fire_timers()

    assert placement(client)["panel"] == {"x": 0.25, "y": 0.2}
    assert any(
        "ui_placement_not_stored" in line
        for line in client.recorder.debug_messages()
    )


def test_a_placement_for_a_surface_this_version_no_longer_has_is_dropped() -> None:
    """Carrying it forever would keep a file growing for windows that are gone."""
    sandbox = MtaSandbox()
    sandbox.write_file(
        "@ankigta-settings.json",
        json.dumps(
            {"uiPlacement": {"panel": {"x": 0.1, "y": 0.2}, "gone": {"x": 0.3, "y": 0.4}}}
        ),
    )
    try:
        for script in manifest_client_scripts():
            sandbox.load(script)
        sandbox.trigger("onClientResourceStart")

        assert set(placement(sandbox)) == {"panel"}
    finally:
        sandbox.close()


# --- modal warnings -----------------------------------------------------------


def test_review_mode_drags_by_its_title_and_rates_by_its_buttons(
    client: MtaSandbox,
) -> None:
    open_review(client, side="answer")
    x, y, width, _height = rect(client, "review")

    # The title bar moves the card and rates nothing. Grabbed near the left
    # edge, so the cursor carries the whole surface rather than pushing its
    # left edge past the screen.
    drag_drawn_surface(client, (x + 20, y + 4), (x + 220, y + 104))
    client.eval("function() renderReviewMode() end")()
    assert placement(client)["review"]["x"] == pytest.approx(
        (x + 200) / 1920, abs=0.01
    )
    assert not [
        event
        for event in client.recorder.server_events
        if event.name == "ankigta:submitRating"
    ]

    # The rating bar still rates.
    bounds = client.eval(
        "function() return ANKIGTA.ReviewMode.ratingBounds.good end"
    )()
    click(client, bounds[1] + bounds[3] / 2, bounds[2] + bounds[4] / 2)
    assert [
        event
        for event in client.recorder.server_events
        if event.name == "ankigta:submitRating"
    ]


def test_the_review_surface_follows_the_scale_and_stays_on_screen() -> None:
    sandbox = start_client(width=1280, height=720)
    try:
        open_review(sandbox)
        _x, _y, small_width, _height = rect(sandbox, "review")

        set_scale(sandbox, 1.5)
        x, y, width, height = rect(sandbox, "review")

        assert width > small_width
        assert x >= 0 and y >= 0
        assert x + width <= 1280 and y + height <= 720
    finally:
        sandbox.close()


def test_review_mode_stays_modal_to_the_keyboard_and_mouse(
    client: MtaSandbox,
) -> None:
    """Story 55: the card is answered with a keyboard and a mouse, and closed
    with a key that exists on one."""
    open_review(client)

    assert ("escape", "down") in client.bound_keys
    for handler in client.bound_keys[("escape", "down")]:
        handler()

    assert client.eval("function() return isReviewModeActive() end")() is False


# --- the HUD ------------------------------------------------------------------


def push_statistics(sandbox: MtaSandbox) -> None:
    sandbox.eval(
        """
        function()
            triggerEvent("ankigta:statistics", resourceRoot, {
                total = 4, new = 1, learning = 1, due = 1, early = 1,
            })
        end
        """
    )()


def test_the_hud_does_not_move_outside_edit_hud_layout(client: MtaSandbox) -> None:
    push_statistics(client)
    x, y, width, height = rect(client, "hud")

    drag_drawn_surface(client, (x + width / 2, y + height / 2), (400, 400))

    assert placement(client) == {}
    assert rect(client, "hud") == (x, y, width, height)


def test_the_hud_moves_in_edit_hud_layout_and_is_remembered(
    client: MtaSandbox,
) -> None:
    push_statistics(client)
    client.eval("function() ANKIGTA.Layout.setHudEditMode(true) end")()
    x, y, width, height = rect(client, "hud")

    drag_drawn_surface(client, (x + 10, y + 10), (400, 400))
    client.fire_timers()

    moved_x, moved_y, _width, _height = rect(client, "hud")
    assert (moved_x, moved_y) == (390, 390)
    assert stored_settings(client)["uiPlacement"]["hud"] == {
        "x": pytest.approx(390 / 1920),
        "y": pytest.approx(390 / 1080),
    }


def test_an_open_card_keeps_the_hud_still_even_in_edit_hud_layout(
    client: MtaSandbox,
) -> None:
    """Review Mode is modal (story 48), and that includes the mouse."""
    push_statistics(client)
    client.eval("function() ANKIGTA.Layout.setHudEditMode(true) end")()
    open_review(client)
    x, y, width, height = rect(client, "hud")

    drag_drawn_surface(client, (x + 10, y + 10), (400, 400))

    assert "hud" not in placement(client)
    assert rect(client, "hud") == (x, y, width, height)


def test_edit_hud_layout_is_a_setting_the_player_turns_on(
    client: MtaSandbox,
) -> None:
    client.commands["ankigta-ui"][0]()
    page_ready(client)
    assert client.eval("function() return ANKIGTA.Layout.hudEditMode() end")() is False

    set_setting_action(client, "editHud", {"value": True})

    assert client.eval("function() return ANKIGTA.Layout.hudEditMode() end")() is True


def test_the_hud_follows_the_scale(client: MtaSandbox) -> None:
    push_statistics(client)
    client.drawn_text_boxes.clear()
    client.eval("function() return ANKIGTA.Indicator.render() end")()
    before = client.drawn_text_boxes[-1]

    set_scale(client, 2)
    client.drawn_text_boxes.clear()
    client.eval("function() return ANKIGTA.Indicator.render() end")()
    after = client.drawn_text_boxes[-1]

    assert after["scale"] == 2
    assert after["right"] - after["left"] == pytest.approx(
        (before["right"] - before["left"]) * 2, abs=2
    )


# --- Reset UI layout ----------------------------------------------------------


def test_reset_ui_layout_restores_the_shipped_scale_and_placement(
    client: MtaSandbox,
) -> None:
    open_f7(client)
    drag_panel(client, 40, 40)
    set_scale(client, 1.8)
    client.eval("function() ANKIGTA.Layout.setHudEditMode(true) end")()

    reset_layout(client)

    assert scale(client) == 1
    assert placement(client) == {}
    assert client.eval("function() return ANKIGTA.Layout.hudEditMode() end")() is False
    assert stored_settings(client)["uiPlacement"] == {}
    assert stored_settings(client)["uiScale"] == 1


def test_reset_ui_layout_survives_a_restart(client: MtaSandbox) -> None:
    open_f7(client)
    drag_panel(client, 40, 40)
    client.fire_timers()
    reset_layout(client)

    restarted = start_client(dict(client.files))
    try:
        assert placement(restarted) == {}
        assert scale(restarted) == 1
    finally:
        restarted.close()


@pytest.mark.parametrize("wanted", SCALES)
@pytest.mark.parametrize(
    ("width", "height"), RESOLUTIONS, ids=lambda value: str(value)
)
def test_reset_ui_layout_is_reachable_however_the_layout_was_left(
    wanted: float,
    width: int,
    height: int,
) -> None:
    """The way back cannot depend on the state it is the way back from.

    `Reset UI layout` is a row in the settings panel, but that panel is laid
    out by the very thing being reset. So the way back is also a command, which
    cannot be too big for the screen, dragged off it, or scaled out of reach.
    """
    sandbox = start_client(width=width, height=height)
    try:
        set_scale(sandbox, wanted)
        open_f7(sandbox)
        # Everything shoved into one corner, at the extreme scale.
        for surface in ("f7", "cardPicker", "hud", "review"):
            sandbox.eval("function(k, x, y) ANKIGTA.Layout.remember(k, x, y) end")(
                surface, width, height
            )

        sandbox.commands["ankigta-ui-reset"][0]()

        assert scale(sandbox) == 1
        assert placement(sandbox) == {}
    finally:
        sandbox.close()


@pytest.mark.parametrize("wanted", SCALES)
@pytest.mark.parametrize(
    ("width", "height"), RESOLUTIONS, ids=lambda value: str(value)
)
def test_the_reset_row_is_inside_the_panel_at_every_scale(
    wanted: float,
    width: int,
    height: int,
) -> None:
    """Reset stays reachable however the layout was left.

    The row itself is HTML and CSS keeps it inside the page, so what this
    checks is the part that can still go wrong here: the panel is on screen,
    and the reset it offers actually puts scale and placement back.
    """
    sandbox = start_client(width=width, height=height)
    try:
        set_scale(sandbox, wanted)
        sandbox.commands["ankigta-ui"][0]()
        page_ready(sandbox)
        drag_panel(sandbox, width * 0.4, height * 0.4)

        panel_x, panel_y, panel_width, panel_height = rect(sandbox, "panel")
        assert panel_x >= 0 and panel_y >= 0
        assert panel_x + panel_width <= width
        assert panel_y + panel_height <= height

        reset_layout(sandbox)

        assert scale(sandbox) == 1
        assert placement(sandbox) == {}
    finally:
        sandbox.close()

def test_the_panel_is_reachable_from_f7_as_well_as_from_the_command(
    client: MtaSandbox,
) -> None:
    """One panel, so one entry: the UI scale rows live in the settings panel
    rather than in a second window offering the same value."""
    open_f7(client)
    page_ready(client)
    client.eval(
        'function() triggerEvent("ankigta:panelAction", resourceRoot,'
        ' "openSettings", "{}") end'
    )()
    from_panel = pushed_section(client)

    client.commands["ankigta-ui"][0]()
    page_ready(client)
    from_command = pushed_section(client)

    assert from_panel == "settings"
    assert from_command == "settings"


# --- authority ----------------------------------------------------------------


def test_ui_scale_and_placement_never_reach_the_server(client: MtaSandbox) -> None:
    """ADR 0028. They live on this machine, so nothing is sent anywhere."""
    open_f7(client)
    drag_panel(client, 40, 40)
    set_scale(client, 1.5)
    client.fire_timers()

    for event in client.recorder.server_events:
        assert "uiScale" not in str(event.args)
        assert "uiPlacement" not in str(event.args)


@pytest.mark.parametrize("key", ["uiScale", "uiPlacement"])
def test_the_server_refuses_to_store_a_setting_the_client_owns(key: str) -> None:
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")

        assert sandbox.eval(
            "function(k) return ANKIGTA.Settings.inChangeHistory(k) end"
        )(key) is False
        refused, reason = sandbox.eval(
            "function(k) return ANKIGTA.Settings.canWrite('server', k) end"
        )(key)
        assert refused is False
        assert reason == "wrong_authority"
    finally:
        sandbox.close()


# --- gamepads (ADR 0015) -------------------------------------------------------

#: MTA's gamepad key names, from `g_KeyBinds` in `Client/core/CKeyBinds.cpp`:
#: `joy1`..`joy32`, four POV directions and fourteen axes.
GAMEPAD_KEYS = (
    [f"joy{button}" for button in range(1, 33)]
    + ["pov_up", "pov_right", "pov_down", "pov_left"]
    + [f"axis_{axis}" for axis in range(1, 15)]
)

#: Bindable GTA controls a pad can press. Binding an ANKIGTA action to one of
#: these would make a controller trigger it without ANKIGTA ever saying so.
GTA_CONTROLS = [
    "fire",
    "next_weapon",
    "previous_weapon",
    "forwards",
    "backwards",
    "left",
    "right",
    "enter_exit",
    "jump",
    "sprint",
    "crouch",
    "action",
    "aim_weapon",
    "vehicle_fire",
    "vehicle_secondary_fire",
    "accelerate",
    "brake_reverse",
    "horn",
    "sub_mission",
    "handbrake",
    "look_left",
    "look_right",
    "look_behind",
    "radio_next",
    "radio_previous",
    "change_camera",
]


def test_no_ankigta_action_is_bound_to_a_gamepad_key_or_a_game_control(
    client: MtaSandbox,
) -> None:
    open_f7(client)
    open_review(client)

    bound = {key for key, _state in client.bound_keys}

    assert bound, "the client binds nothing at all, which cannot be right"
    assert not bound & set(GAMEPAD_KEYS)
    assert not bound & set(GTA_CONTROLS)
    # What is left is a keyboard, which is all v1 supports.
    assert bound <= {"F7", "escape"}


@pytest.mark.parametrize("key", GAMEPAD_KEYS)
def test_a_gamepad_button_triggers_no_ankigta_action(
    client: MtaSandbox,
    key: str,
) -> None:
    """A connected controller is noise ANKIGTA neither uses nor reacts to."""
    open_f7(client)
    open_review(client)
    before = len(client.recorder.server_events)

    for state in ("down", "up"):
        assert (key, state) not in client.bound_keys

    assert len(client.recorder.server_events) == before
    assert client.eval("function() return isReviewModeActive() end")() is True


def test_no_client_script_touches_a_joystick_api() -> None:
    """ADR 0015: no gamepad navigation, prompts, remapping or support.

    Read out of the compiled chunk rather than the file, so a name built by
    concatenation cannot slip past and a comment cannot fail it.
    """
    forbidden = {
        "getJoystickState",
        "setJoystickMode",
        "getAnalogControlState",
        "setAnalogControlState",
        "getBoundKeys",
        "getFunctionsBoundToKey",
    }

    for relative in manifest_client_scripts():
        constants = set(string_constants(RESOURCE / relative))
        assert not constants & forbidden, relative
        assert not {value for value in constants if value.startswith("joy")}, relative
