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
    "f7",
    "cardPicker",
    "f7Modal",
    "study",
    "connection",
    "connectionSettings",
    "uiSettings",
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
    sandbox.eval("function(l) ANKIGTA.Locale.setLanguage(l) end")(language)
    return sandbox


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


def open_study(sandbox: MtaSandbox) -> None:
    sandbox.commands["ankigta"][0]()


def open_connection_windows(sandbox: MtaSandbox) -> None:
    sandbox.eval(
        """
        function()
            triggerEvent("ankigta:companionStatus", resourceRoot, {
                state = "disconnected",
                category = "timeout",
            })
            triggerEvent("ankigta:connectionSettingsSnapshot", resourceRoot, {
                mode = "automatic",
                port = 40007,
                tokenConfigured = true,
            })
        end
        """
    )()


def open_every_window(sandbox: MtaSandbox) -> None:
    """Put one of every window on screen, including a modal warning."""
    open_f7(sandbox)
    select_first_row(sandbox)
    sandbox.click_widget(text(sandbox, "f7.unlink"))
    open_card_picker(sandbox)
    open_study(sandbox)
    open_connection_windows(sandbox)
    sandbox.commands["ankigta-ui"][0]()


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


def test_the_buttons_move_ui_scale_by_005_and_stop_at_the_bounds(
    client: MtaSandbox,
) -> None:
    step = client.eval("ANKIGTA.Layout.scaleStep")
    assert step == 0.05

    client.commands["ankigta-ui"][0]()
    larger = text(client, "ui.larger")
    smaller = text(client, "ui.smaller")

    client.click_widget(larger)
    assert scale(client) == 1.05

    for _ in range(40):
        client.click_widget(larger)
    assert scale(client) == 2

    for _ in range(40):
        client.click_widget(smaller)
    assert scale(client) == 0.5


def test_a_value_typed_by_hand_is_taken_at_two_decimal_places(
    client: MtaSandbox,
) -> None:
    """The 0.05 step belongs to the buttons, not to the setting.

    Making it a validation rule would refuse 1.23, which story 54 allows.
    """
    client.commands["ankigta-ui"][0]()
    # The field starts at the current scale, which is what the player edits.
    field = client.find_widget("1.00", "edit")
    client.widgets[field].text = "1.23"

    client.click_widget(text(client, "ui.applyScale"))

    assert scale(client) == 1.23


def test_a_refused_value_typed_by_hand_says_why_in_the_players_language(
    client: MtaSandbox,
) -> None:
    client.eval("function(l) ANKIGTA.Locale.setLanguage(l) end")("ru")
    client.commands["ankigta-ui"][0]()
    field = client.live_widgets("edit")[-1]
    client.widgets[field].text = "9"

    client.click_widget(text(client, "ui.applyScale"))

    assert scale(client) == 1
    assert client.chat, "a refusal the player cannot see is not a refusal"
    assert text(client, "settings.error.out_of_range") in client.chat[-1]


def test_a_scale_change_reaches_an_open_window_without_reopening_it(
    client: MtaSandbox,
) -> None:
    """"Applies immediately" means the window on screen, not the next one."""
    open_f7(client)
    before = client.widget_rect(client.find_widget(text(client, "f7.title")))

    set_scale(client, 1.5)

    after = client.widget_rect(client.find_widget(text(client, "f7.title")))
    assert after[2] == pytest.approx(before[2] * 1.5, abs=1)
    assert after[3] == pytest.approx(before[3] * 1.5, abs=1)
    # And the controls inside it grew with it, rather than staying put in a
    # bigger frame.
    recheck = client.widget_rect(client.find_widget(text(client, "f7.recheck")))
    assert recheck[2] == pytest.approx(174 * 1.5, abs=1)


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
        select_first_row(sandbox)
        sandbox.click_widget(text(sandbox, "f7.unlink"))

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
    """The layout acceptance test story 54 asks for.

    A button past the right edge of its window is a required primary action the
    player cannot reach, and CEGUI does not scroll to it.
    """
    sandbox = start_client(width=width, height=height)
    try:
        assert set_scale(sandbox, wanted) is True
        open_every_window(sandbox)

        windows = {
            index: sandbox.widgets[index]
            for index in sandbox.live_widgets("window")
        }
        assert len(windows) >= len(WINDOW_SURFACES)

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
        _x, _y, width, height = rect(sandbox, "f7")

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
    window = client.find_widget(text(client, "f7.title"))

    client.drag_window(window, 480, 270)

    assert placement(client)["f7"] == {"x": 0.25, "y": 0.25}


def test_a_window_is_movable_by_its_title_and_never_resizable(
    client: MtaSandbox,
) -> None:
    """The size is UI Scale's to decide.

    A hand-resized window would have its controls at the wrong size the moment
    it was reopened, because the controls are built for the scale, not for the
    frame.
    """
    open_f7(client)
    window = client.widgets[client.find_widget(text(client, "f7.title"))]

    assert window.movable is True
    assert window.sizable is False


def test_a_placement_survives_a_restart(client: MtaSandbox) -> None:
    open_f7(client)
    client.drag_window(client.find_widget(text(client, "f7.title")), 480, 270)
    # The write is debounced, so a drag is one write rather than one per frame.
    client.fire_timers()
    assert stored_settings(client)["uiPlacement"]["f7"] == {"x": 0.25, "y": 0.25}

    restarted = start_client(dict(client.files))
    try:
        open_f7(restarted)
        assert restarted.widget_rect(
            restarted.find_widget(text(restarted, "f7.title"))
        )[:2] == (480, 270)
    finally:
        restarted.close()


def test_a_drag_is_written_once_rather_than_once_per_frame(
    client: MtaSandbox,
) -> None:
    """CEGUI reports a drag as a stream of moves."""
    open_f7(client)
    window = client.find_widget(text(client, "f7.title"))

    for step in range(20):
        client.drag_window(window, 400 + step, 300 + step)

    pending = [timer for timer in client.recorder.timers if not timer.cancelled]
    assert len([timer for timer in pending if timer.repeats == 1]) == 1


def test_a_placement_made_at_one_resolution_lands_in_the_same_place_at_another(
    client: MtaSandbox,
) -> None:
    """Normalized, so the corner means the same thing on every screen."""
    open_f7(client)
    client.drag_window(client.find_widget(text(client, "f7.title")), 480, 270)
    client.fire_timers()

    for width, height in RESOLUTIONS:
        restarted = start_client(dict(client.files), width=width, height=height)
        try:
            x, y, _width, _height = rect(restarted, "f7")
            assert (x / width, y / height) == pytest.approx((0.25, 0.25), abs=0.01)
        finally:
            restarted.close()


def test_a_placement_off_the_new_screen_is_clamped_back_onto_it() -> None:
    """A window dragged to the bottom-right of a 4K screen, reopened at 720p."""
    big = start_client(width=3840, height=2160)
    try:
        open_f7(big)
        client_window = big.find_widget(text(big, "f7.title"))
        _x, _y, width, height = rect(big, "f7")
        big.drag_window(client_window, 3840 - width, 2160 - height)
        big.fire_timers()
        files = dict(big.files)
    finally:
        big.close()

    small = start_client(files, width=1280, height=720)
    try:
        x, y, width, height = rect(small, "f7")
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
    client.drag_window(client.find_widget(text(client, "f7.title")), 1000, 700)

    client.screen_width, client.screen_height = 1280, 720
    client.eval("function() return ANKIGTA.Layout.refresh() end")()

    x, y, width, height = client.widget_rect(
        client.find_widget(text(client, "f7.title"))
    )
    assert x + width <= 1280
    assert y + height <= 720


def test_a_stored_placement_that_is_not_one_is_discarded_with_a_diagnostic() -> None:
    sandbox = MtaSandbox()
    sandbox.write_file(
        "@ankigta-settings.json",
        json.dumps({"uiPlacement": {"f7": {"x": 4.5, "y": -2}}}),
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

    client.drag_window(client.find_widget(text(client, "f7.title")), 480, 270)
    client.fire_timers()

    assert placement(client)["f7"] == {"x": 0.25, "y": 0.25}
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
            {"uiPlacement": {"f7": {"x": 0.1, "y": 0.2}, "gone": {"x": 0.3, "y": 0.4}}}
        ),
    )
    try:
        for script in manifest_client_scripts():
            sandbox.load(script)
        sandbox.trigger("onClientResourceStart")

        assert set(placement(sandbox)) == {"f7"}
    finally:
        sandbox.close()


# --- modal warnings -----------------------------------------------------------


@pytest.mark.parametrize(
    ("button_key", "title_key"),
    [
        ("f7.unlink", "f7.unlink.title"),
        ("f7.replaceCard", "cardPicker.replaceTitle"),
    ],
)
def test_a_modal_warning_is_centred_on_f7_and_travels_with_it(
    client: MtaSandbox,
    button_key: str,
    title_key: str,
) -> None:
    open_f7(client)
    select_first_row(client)
    client.click_widget(text(client, button_key))
    if title_key == "cardPicker.replaceTitle":
        # Replace raises the Card Picker first; the warning follows the choice.
        open_card_picker(client)
        card_grid = client.live_widgets("gridlist")[-1]
        client.widgets[card_grid].selected_row = 0
        client.click_widget(card_grid)
        client.click_widget(text(client, "cardPicker.previewReplacement"))
        title_key = "f7.replace.title"

    parent = client.find_widget(text(client, "f7.title"))
    modal = client.find_widget(text(client, title_key))

    def centred_on_parent() -> bool:
        px, py, pwidth, pheight = client.widget_rect(parent)
        mx, my, mwidth, mheight = client.widget_rect(modal)
        return (
            mx == pytest.approx(px + (pwidth - mwidth) / 2, abs=1)
            and my == pytest.approx(py + (pheight - mheight) / 2, abs=1)
        )

    assert centred_on_parent()
    client.drag_window(parent, 80, 60)
    assert centred_on_parent(), "the warning stayed behind when F7 moved"


# --- Review Mode --------------------------------------------------------------


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
    checkbox = client.find_widget(text(client, "ui.editHud"), "checkbox")
    assert client.eval("function() return ANKIGTA.Layout.hudEditMode() end")() is False

    client.widgets[checkbox].selected = True
    client.click_widget(checkbox)

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
    client.drag_window(client.find_widget(text(client, "f7.title")), 40, 40)
    set_scale(client, 1.8)
    client.eval("function() ANKIGTA.Layout.setHudEditMode(true) end")()

    client.commands["ankigta-ui"][0]()
    client.click_widget(text(client, "ui.reset"))

    assert scale(client) == 1
    assert placement(client) == {}
    assert client.eval("function() return ANKIGTA.Layout.hudEditMode() end")() is False
    assert stored_settings(client)["uiPlacement"] == {}
    assert stored_settings(client)["uiScale"] == 1


def test_reset_ui_layout_survives_a_restart(client: MtaSandbox) -> None:
    open_f7(client)
    client.drag_window(client.find_widget(text(client, "f7.title")), 40, 40)
    client.fire_timers()
    client.commands["ankigta-ui"][0]()
    client.click_widget(text(client, "ui.reset"))

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
    """The way back cannot depend on the state it is the way back from."""
    sandbox = start_client(width=width, height=height)
    try:
        set_scale(sandbox, wanted)
        open_f7(sandbox)
        # Everything shoved into one corner, at the extreme scale.
        for surface in ("f7", "cardPicker", "hud", "review"):
            sandbox.eval("function(k, x, y) ANKIGTA.Layout.remember(k, x, y) end")(
                surface, width, height
            )

        sandbox.commands["ankigta-ui"][0]()

        button = sandbox.find_widget(text(sandbox, "ui.reset"))
        panel = sandbox.widgets[sandbox.find_widget(text(sandbox, "ui.title"))]
        panel_x, panel_y, panel_width, panel_height = rect(sandbox, "uiSettings")
        assert panel_x + panel_width <= width
        assert panel_y + panel_height <= height
        control = sandbox.widgets[button]
        assert control.x + control.width <= panel.width + 1
        assert control.y + control.height <= panel.height + 1

        sandbox.click_widget(button)
        assert scale(sandbox) == 1
        assert placement(sandbox) == {}
    finally:
        sandbox.close()


def test_the_panel_is_reachable_from_f7_as_well_as_from_the_command(
    client: MtaSandbox,
) -> None:
    open_f7(client)

    client.click_widget(text(client, "ui.open"))

    assert client.eval("function() return isUiSettingsOpen() end")() is True


# --- authority ----------------------------------------------------------------


def test_ui_scale_and_placement_never_reach_the_server(client: MtaSandbox) -> None:
    """ADR 0028. They live on this machine, so nothing is sent anywhere."""
    open_f7(client)
    client.drag_window(client.find_widget(text(client, "f7.title")), 40, 40)
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
