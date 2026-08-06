"""Ticket 11 — the panel fades when the mouse is not on it.

While the cursor is on the panel it is being used and is fully opaque; while
the cursor is elsewhere the player is looking at something else and the panel
rests at a client-owned idle opacity. A field being typed into is being used
whatever the mouse is doing, because MTA's cursor does not move on its own.

Everything here runs the real client scripts in a real Lua 5.1 interpreter and
reads the alpha back off the browser control the resource created. Whether the
surface *renders* at that alpha is CEF and CEGUI's half: `guiSetAlpha` reaches
`CEGUI::Window::setAlpha`, and the browser is a `CEGUI::StaticImage` whose
`onAlphaChanged` re-modulates the webview texture by the effective alpha
(`Client/gui/CGUIWebBrowser_Impl.cpp`,
`vendor/cegui-0.4.0-custom/src/elements/CEGUIStaticImage.cpp`). Seeing it is
the manual checklist item the ticket keeps.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox


RESOURCE = Path(__file__).resolve().parents[1] / "mta" / "ankigta"

#: The shipped default and floor of `panelIdleOpacity`, pinned here so a test
#: failure names the number that moved.
DEFAULT_IDLE = 0.6
FLOOR = 0.2


def manifest_client_scripts() -> list[str]:
    manifest = ElementTree.parse(RESOURCE / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in ("shared", "client")
    ]


def start_client() -> MtaSandbox:
    sandbox = MtaSandbox()
    sandbox.screen_width, sandbox.screen_height = 1920, 1080
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
    return sandbox


@pytest.fixture
def client() -> Iterator[MtaSandbox]:
    sandbox = start_client()
    try:
        yield sandbox
    finally:
        sandbox.close()


def open_f7(sandbox: MtaSandbox) -> None:
    for handler in sandbox.bound_keys.get(("F7", "down"), []):
        handler()


def act(sandbox: MtaSandbox, action: str, payload: Any = None) -> None:
    sandbox.eval(
        """
        function(action, payload)
            triggerEvent("ankigta:panelAction", resourceRoot, action, payload)
        end
        """
    )(action, json.dumps(payload or {}))


def page_ready(sandbox: MtaSandbox) -> None:
    act(sandbox, "ready")


def panel_alpha(sandbox: MtaSandbox) -> float:
    browsers = sandbox.live_widgets("browser")
    assert browsers, "no browser control is alive"
    return float(sandbox.widgets[browsers[-1]].alpha)


def panel_center(sandbox: MtaSandbox) -> tuple[float, float]:
    rect = sandbox.eval(
        'function() return {ANKIGTA.Layout.rect("panel")} end'
    )()
    return (
        (rect[1] + rect[3] / 2) / 1920,
        (rect[2] + rect[4] / 2) / 1080,
    )


#: A spot no default-placed panel covers.
OUTSIDE = (0.01, 0.01)


def render(sandbox: MtaSandbox, frames: int = 1) -> None:
    for _frame in range(frames):
        sandbox.trigger("onClientRender")


#: More frames than any fade needs: the step is 0.1 per frame, so the longest
#: journey (1 down to the 0.2 floor) is eight.
PLENTY = 15


def settings_row(sandbox: MtaSandbox, key: str) -> Any:
    for state in reversed(sandbox.pushed_panel_states()):
        for row in state.get("settings", {}).get("rows", []):
            if row["key"] == key:
                return row
    return None


def test_the_panel_is_fully_opaque_while_the_cursor_is_over_it(
    client: MtaSandbox,
) -> None:
    open_f7(client)
    page_ready(client)
    client.cursor_position = panel_center(client)

    render(client, PLENTY)

    assert panel_alpha(client) == 1


def test_it_fades_to_the_configured_opacity_when_the_cursor_leaves(
    client: MtaSandbox,
) -> None:
    """A fade, not a snap: a step per frame until it rests at the setting."""
    open_f7(client)
    page_ready(client)
    client.cursor_position = OUTSIDE

    render(client)
    after_one = panel_alpha(client)
    render(client, PLENTY)

    assert after_one < 1
    assert after_one > DEFAULT_IDLE
    assert panel_alpha(client) == pytest.approx(DEFAULT_IDLE)


def test_the_cursor_coming_back_makes_it_opaque_again(
    client: MtaSandbox,
) -> None:
    open_f7(client)
    page_ready(client)
    client.cursor_position = OUTSIDE
    render(client, PLENTY)
    assert panel_alpha(client) == pytest.approx(DEFAULT_IDLE)

    client.cursor_position = panel_center(client)
    render(client, PLENTY)

    assert panel_alpha(client) == 1


def test_the_idle_opacity_is_a_client_setting_stored_on_this_machine(
    client: MtaSandbox,
) -> None:
    open_f7(client)
    page_ready(client)
    act(client, "setSetting", {"key": "panelIdleOpacity", "value": 0.35})
    client.cursor_position = OUTSIDE

    render(client, PLENTY)

    assert panel_alpha(client) == pytest.approx(0.35)
    stored = json.loads(client.read_file("@ankigta-settings.json"))
    assert stored["panelIdleOpacity"] == 0.35
    # Client-owned: nothing about it crosses the wire (ADR 0014).
    for event in client.recorder.server_events:
        assert "panelIdleOpacity" not in str(event.args)


def test_a_field_being_typed_into_does_not_fade(client: MtaSandbox) -> None:
    """The cursor is on the keyboard, and MTA's cursor does not move on its
    own. A panel that fades mid-sentence is worse than one that never fades."""
    open_f7(client)
    page_ready(client)
    client.cursor_position = OUTSIDE
    act(client, "typing", {"active": True})

    render(client, PLENTY)
    assert panel_alpha(client) == 1

    act(client, "typing", {"active": False})
    render(client, PLENTY)
    assert panel_alpha(client) == pytest.approx(DEFAULT_IDLE)


def test_a_value_below_the_floor_is_refused_with_a_reason_never_clamped(
    client: MtaSandbox,
) -> None:
    """Zero would be a window that is still there, still eats the cursor, and
    cannot be seen. The floor is a rule the store enforces, not a warning."""
    open_f7(client)
    page_ready(client)

    for hidden in (0, 0.1, FLOOR - 0.01):
        act(client, "setSetting", {"key": "panelIdleOpacity", "value": hidden})
        row = settings_row(client, "panelIdleOpacity")
        assert row["error"] == "settings.error.out_of_range", hidden
        assert row["value"] == DEFAULT_IDLE

    # The floor itself is a value, not a warning.
    act(client, "setSetting", {"key": "panelIdleOpacity", "value": FLOOR})
    assert settings_row(client, "panelIdleOpacity")["error"] is False
    assert settings_row(client, "panelIdleOpacity")["value"] == FLOOR


def test_the_opacity_is_shown_at_its_declared_precision(
    client: MtaSandbox,
) -> None:
    """Two decimals, like every numeric that is read by a person: the row says
    so, and a hand-typed third decimal is refused rather than rounded."""
    open_f7(client)
    page_ready(client)
    act(client, "openSettings")

    row = settings_row(client, "panelIdleOpacity")
    assert row is not None
    assert row["decimals"] == 2
    assert row["min"] == FLOOR
    assert row["max"] == 1

    act(client, "setSetting", {"key": "panelIdleOpacity", "value": 0.345})
    assert (
        settings_row(client, "panelIdleOpacity")["error"]
        == "settings.error.too_precise"
    )


def test_a_reopened_panel_starts_opaque(client: MtaSandbox) -> None:
    open_f7(client)
    page_ready(client)
    client.cursor_position = OUTSIDE
    render(client, PLENTY)
    assert panel_alpha(client) == pytest.approx(DEFAULT_IDLE)

    open_f7(client)
    open_f7(client)
    page_ready(client)

    assert panel_alpha(client) == 1
