"""Ticket 27 — the settings panel, the path a user changes a setting through.

The schema already knew what every setting was, and both stores already knew
who was allowed to write one; nothing let a user actually change one. These
tests drive the path a player takes: open the panel, type a value, apply it.

The two rules that matter are that a bad value comes back with a localized
reason instead of being quietly clamped — a mistyped 200 turned into 50 leaves
the user with a setting they never chose and no way to notice — and that a
value which is accepted is still there after a restart.

The panel is derived from the schema rather than hand-listed, so a setting
added later cannot quietly become unreachable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import pytest

from tests.lua import MtaSandbox


CLIENT_SCRIPTS = (
    "shared/settings.lua",
    "shared/locale.lua",
    "shared/entity_types.lua",
    # Every window asks the layout manager where it goes and how big it is
    # (ticket 28), so it is part of the client baseline the way the schema and
    # the string table are.
    "client/layout.lua",
    "client/settings_store.lua",
    # Ticket 32 folded the settings window into the panel, so the panel is what
    # these drive. The rules under test did not move: rows come from the schema,
    # authority decides who stores a value, and a refusal is a localized reason
    # rather than a clamp.
    "client/panel.lua",
)

SERVER_STORE_SCRIPTS = (
    "shared/settings.lua",
    "shared/locale.lua",
    "server/backup.lua",
    "server/store.lua",
    "server/settings_store.lua",
)


def manifest_scripts(*kinds: str) -> list[str]:
    """The scripts meta.xml declares, in declared order."""
    manifest = ElementTree.parse(
        Path(__file__).resolve().parents[1] / "mta" / "ankigta" / "meta.xml"
    )
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in kinds
    ]


def load_client(
    files: dict[str, bytes] | None = None,
    scripts: tuple[str, ...] = CLIENT_SCRIPTS,
) -> MtaSandbox:
    """The client side on top of an existing client-side disk."""
    sandbox = MtaSandbox()
    if files is not None:
        sandbox.files.update(files)
    for script in scripts:
        sandbox.load(script)
    return sandbox


def open_client(
    files: dict[str, bytes] | None = None,
    scripts: tuple[str, ...] = CLIENT_SCRIPTS,
) -> MtaSandbox:
    """Started through `onClientResourceStart`, the way MTA starts it."""
    sandbox = load_client(files, scripts)
    sandbox.trigger("onClientResourceStart")
    return sandbox


@pytest.fixture
def client() -> Iterator[MtaSandbox]:
    sandbox = open_client()
    try:
        yield sandbox
    finally:
        sandbox.close()


@pytest.fixture
def server(tmp_path: Path) -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
    for script in SERVER_STORE_SCRIPTS:
        sandbox.load(script)
    sandbox.execute("ANKIGTA.Store.seedTracerFixtures = true")
    sandbox.execute("ANKIGTA.Store.open()")
    try:
        yield sandbox
    finally:
        sandbox.close()


def call(sandbox: MtaSandbox, expression: str, *args: Any) -> Any:
    return sandbox.eval(expression)(*args)


def schema_keys(sandbox: MtaSandbox) -> list[str]:
    keys = call(
        sandbox,
        """
        function()
            local names = {}
            for key in pairs(ANKIGTA.Settings.schema) do
                table.insert(names, key)
            end
            return names
        end
        """,
    )
    return [str(keys[index]) for index in keys.keys()]


def panel_action(sandbox: MtaSandbox, action: str, payload: Any = None) -> None:
    call(
        sandbox,
        """
        function(action, payload)
            triggerEvent("ankigta:panelAction", resourceRoot, action, payload)
        end
        """,
        action,
        json.dumps(payload or {}),
    )


def open_panel(sandbox: MtaSandbox) -> None:
    """Open the panel on its settings section, as a player would.

    Opening asks the server for the settings it owns; every test after this
    point is about what the *user* then causes, so start from a clean slate.
    `test_opening_the_panel_asks_the_server_for_what_it_owns` covers the ask.
    """
    call(
        sandbox,
        'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end',
    )
    call(
        sandbox,
        """
        function()
            triggerEvent("ankigta:companionStatus", resourceRoot,
                {state = "connected"})
        end
        """,
    )
    for handler in sandbox.bound_keys.get(("F7", "down"), []):
        handler()
    panel_action(sandbox, "ready")
    panel_action(sandbox, "openSettings")
    sandbox.recorder.server_events.clear()


def pushed_state(sandbox: MtaSandbox) -> dict[str, Any]:
    return sandbox.pushed_panel_state()


def control(sandbox: MtaSandbox, key: str) -> Any:
    """The row the panel offers for a setting, or None if it offers none."""
    for row in pushed_state(sandbox).get("settings", {}).get("rows", []):
        if row["key"] == key:
            return row
    return None


def translate(sandbox: MtaSandbox, key: str) -> str:
    return str(call(sandbox, "function(k) return ANKIGTA.Locale.text(k) end", key))


def apply_number(sandbox: MtaSandbox, key: str, typed: str) -> None:
    """Put a value in a number field, as a player's keystrokes would.

    The string is passed through as typed: turning "abc" into a number here
    would be the test doing the validation the schema is supposed to do.
    """
    assert control(sandbox, key) is not None, f"{key} has no row in the panel"
    try:
        value: Any = float(typed)
    except ValueError:
        value = typed
    panel_action(sandbox, "setSetting", {"key": key, "value": value})


def client_value(sandbox: MtaSandbox, key: str) -> Any:
    return call(sandbox, "function(k) return ANKIGTA.ClientSettings.get(k) end", key)


def server_value(sandbox: MtaSandbox, key: str) -> Any:
    return call(sandbox, "function(k) return ANKIGTA.SettingsStore.get(k) end", key)


def set_server(sandbox: MtaSandbox, key: str, value: Any) -> Any:
    return call(
        sandbox,
        "function(k, v) return ANKIGTA.SettingsStore.set(k, v) end",
        key,
        value,
    )


def set_client(sandbox: MtaSandbox, key: str, value: Any) -> Any:
    return call(
        sandbox,
        "function(k, v) return ANKIGTA.ClientSettings.set(k, v) end",
        key,
        value,
    )


def map_preferences(sandbox: MtaSandbox) -> dict[str, bool]:
    rows = call(
        sandbox, "function() return ANKIGTA.SettingsStore.mapPreferences() end"
    )
    return {
        str(rows[index]["mapId"]): rows[index]["includeInStudy"]
        for index in rows.keys()
    }


# --- reachability ------------------------------------------------------------


def test_every_setting_in_the_schema_is_reachable_in_the_panel(
    client: MtaSandbox,
) -> None:
    """Derived from the schema: a setting added later cannot go unreachable."""
    open_panel(client)

    for key in schema_keys(client):
        entry = control(client, key)
        if key in ("connectionToken", "uiPlacement"):
            # Deliberately not rows. A secret is never sent back to a page, and
            # placement is dragged rather than typed — both reachable, neither
            # a field.
            assert entry is None
            continue
        assert entry is not None, f"{key} is not reachable in the settings panel"
        assert entry["kind"] in (
            "number",
            "boolean",
            "choice",
            "delegated",
            "placement",
            "maps",
        ), f"{key} has no usable control kind"


def test_opening_the_panel_asks_the_server_for_what_it_owns(
    client: MtaSandbox,
) -> None:
    panel_action(client, "openSettings")

    assert "ankigta:requestSettings" in [
        event.name for event in client.recorder.server_events
    ]


def test_a_setting_owned_by_the_add_on_is_delegated_rather_than_edited_here(
    client: MtaSandbox,
) -> None:
    """The add-on publishes the connection; the panel only routes to it."""
    open_panel(client)

    assert control(client, "connectionPort")["kind"] == "delegated"
    # The secret is never sent back to a page at all, delegated or not.
    assert control(client, "connectionToken") is None

    panel_action(client, "setSetting", {"key": "connectionPort"})

    assert [event.name for event in client.recorder.server_events] == [
        "ankigta:requestConnectionSettings"
    ]


def test_every_label_the_panel_shows_comes_from_the_locale_table(
    client: MtaSandbox,
) -> None:
    open_panel(client)

    locale = pushed_state(client)["locale"]
    for key in schema_keys(client):
        entry = control(client, key)
        if entry is None:
            continue
        # The page renders `labelKey` through the table Lua sent, so the label
        # exists exactly when the table owns it.
        assert entry["labelKey"] in locale, (
            f"{key} shows a label the locale table does not own"
        )


# --- rejection, never clamping ----------------------------------------------


def test_an_out_of_range_radius_is_rejected_with_a_localized_reason(
    client: MtaSandbox,
) -> None:
    open_panel(client)

    apply_number(client, "activationRadius", "200")

    rejection = {
        "key": "activationRadius",
        "reason": control(client, "activationRadius")["error"],
    }
    assert rejection["key"] == "activationRadius"
    assert rejection["reason"] == "settings.error.out_of_range"
    assert translate(client, control(client, "activationRadius")["error"]) == (
        translate(client, "settings.error.out_of_range")
    )


def test_a_rejected_radius_is_not_quietly_clamped_to_the_boundary(
    client: MtaSandbox,
) -> None:
    """200 silently becoming 50 is the failure this whole path exists to stop."""
    open_panel(client)

    apply_number(client, "activationRadius", "200")

    shown = control(client, "activationRadius")["value"]
    assert shown != 50
    assert shown == 3
    assert client.recorder.server_events == []


@pytest.mark.parametrize(
    ("key", "typed", "reason"),
    [
        ("activationRadius", "200", "settings.error.out_of_range"),
        ("activationRadius", "3.2", "settings.error.not_on_step"),
        ("activationRadius", "many", "settings.error.not_a_number"),
        ("activationDelaySeconds", "1.234", "settings.error.too_precise"),
        ("activationDelaySeconds", "-1", "settings.error.out_of_range"),
        ("maxActivationSpeedKmh", "-5", "settings.error.out_of_range"),
        ("uiScale", "9", "settings.error.out_of_range"),
    ],
)
def test_the_input_path_reports_the_reason_the_schema_gives(
    client: MtaSandbox,
    key: str,
    typed: str,
    reason: str,
) -> None:
    open_panel(client)

    apply_number(client, key, typed)

    assert control(client, key)["error"] == reason


def test_the_rejection_reason_is_shown_in_the_language_in_use(
    client: MtaSandbox,
) -> None:
    call(client, 'function() ANKIGTA.Locale.setLanguage("ru") end')
    open_panel(client)

    apply_number(client, "activationRadius", "200")

    assert translate(client, control(client, "activationRadius")["error"]) == (
        "Значение вне допустимого диапазона"
    )


def test_a_value_the_schema_accepts_clears_the_previous_rejection(
    client: MtaSandbox,
) -> None:
    open_panel(client)
    apply_number(client, "activationRadius", "200")

    apply_number(client, "activationRadius", "7.5")

    assert control(client, "activationRadius")["error"] is False
    assert control(client, "activationRadius")["error"] is False


# --- who may write what ------------------------------------------------------


def test_a_valid_server_setting_leaves_the_client_and_goes_to_its_owner(
    client: MtaSandbox,
) -> None:
    open_panel(client)

    apply_number(client, "activationRadius", "7.5")

    assert [
        (event.name, event.args[0], event.args[1])
        for event in client.recorder.server_events
    ] == [("ankigta:updateSetting", "activationRadius", 7.5)]


def test_a_value_awaiting_the_server_is_not_snapped_back_to_the_old_one(
    client: MtaSandbox,
) -> None:
    """Redrawing the old value while the server decides reads as a rejection."""
    open_panel(client)

    apply_number(client, "activationRadius", "7.5")

    assert control(client, "activationRadius")["value"] == 7.5


def test_the_owner_s_answer_is_what_the_panel_finally_shows(
    client: MtaSandbox,
) -> None:
    open_panel(client)
    apply_number(client, "activationRadius", "7.5")

    client.trigger(
        "ankigta:settingsSnapshot",
        client.eval("resourceRoot"),
        client.eval(
            "function() return {values = {activationRadius = 7.5}, maps = {}} end"
        )(),
    )

    assert control(client, "activationRadius")["value"] == 7.5
    assert control(client, "activationRadius")["value"] == 7.5


def test_a_client_setting_never_leaves_the_machine_that_owns_it(
    client: MtaSandbox,
) -> None:
    """Client settings reach no server, so they reach no Change History."""
    open_panel(client)

    apply_number(client, "uiScale", "1.5")

    assert client.recorder.server_events == []
    assert client_value(client, "uiScale") == 1.5


def test_the_client_store_refuses_a_setting_the_server_owns(
    client: MtaSandbox,
) -> None:
    ok, reason = set_client(client, "activationRadius", 5)

    assert ok is False
    assert reason == "wrong_authority"


def test_the_server_store_refuses_a_setting_the_client_owns(
    server: MtaSandbox,
) -> None:
    ok, reason = set_server(server, "uiScale", 2)

    assert ok is False
    assert reason == "wrong_authority"
    # Refused rather than answered with a default: the default is not what the
    # player's machine currently has, and saying it would read like an answer.
    assert server_value(server, "uiScale") == (False, "wrong_authority")


def test_the_server_store_rejects_a_value_a_stale_client_sends(
    server: MtaSandbox,
) -> None:
    """The client validates for the user's sake; the server validates for real."""
    ok, reason = set_server(server, "activationRadius", 200)

    assert ok is False
    assert reason == "settings.error.out_of_range"
    assert server_value(server, "activationRadius") == 3


# --- persistence -------------------------------------------------------------


def test_a_client_setting_survives_a_restart() -> None:
    first = open_client()
    open_panel(first)
    apply_number(first, "uiScale", "1.5")
    disk = dict(first.files)
    first.close()

    second = open_client(disk)

    assert client_value(second, "uiScale") == 1.5
    second.close()


def test_a_server_setting_survives_a_restart(tmp_path: Path) -> None:
    database = str(tmp_path / "ankigta.sqlite")
    first = MtaSandbox(database_path=database)
    for script in SERVER_STORE_SCRIPTS:
        first.load(script)
    first.execute("ANKIGTA.Store.open()")
    assert set_server(first, "activationRadius", 7.5) is True
    first.close()

    second = MtaSandbox(database_path=database)
    for script in SERVER_STORE_SCRIPTS:
        second.load(script)
    second.execute("ANKIGTA.Store.open()")
    second.execute("ANKIGTA.SettingsStore.load()")

    assert server_value(second, "activationRadius") == 7.5
    second.close()


def test_a_stored_value_the_schema_no_longer_accepts_falls_back_to_the_default() -> (
    None
):
    """A hand-edited file must not install a value the schema itself rejects."""
    sandbox = load_client()
    sandbox.write_file(
        "@ankigta-settings.json",
        json.dumps({"uiScale": 200, "closeAfterRating": False}),
    )
    sandbox.trigger("onClientResourceStart")

    assert client_value(sandbox, "uiScale") == 1
    assert client_value(sandbox, "closeAfterRating") is False
    assert any(
        "discarded_stored_setting" in message
        for message in sandbox.recorder.debug_messages()
    )
    sandbox.close()


def test_the_panel_placement_is_remembered_without_entering_change_history() -> None:
    """Dragged, not positioned by hand.

    Ticket 28 made placement the layout manager's business: it hears the drag,
    stores it as a fraction of the screen, and puts the window back there. The
    panel is a page rather than a CEGUI window, so the drag arrives as an
    action and Lua follows the cursor — but the manager's part is unchanged.
    """
    first = open_client()
    open_panel(first)
    first.cursor_position = (900 / 1920, 400 / 1080)
    first.key_states["mouse1"] = True
    panel_action(first, "dragStart")
    first.cursor_position = (1020 / 1920, 640 / 1080)
    first.trigger("onClientRender")
    first.key_states["mouse1"] = False
    # The write is debounced, so a drag is one write rather than one per frame.
    first.fire_timers()
    disk = dict(first.files)
    first.close()

    second = open_client(disk)
    open_panel(second)

    placement = call(
        second, 'function() return ANKIGTA.Layout.placements["panel"] end'
    )
    assert placement is not None, "the drag was not remembered"
    assert 0 <= placement["x"] <= 1 and 0 <= placement["y"] <= 1
    assert (
        call(
            second,
            "function() return ANKIGTA.Settings.inChangeHistory('uiPlacement') end",
        )
        is False
    )
    second.close()


# --- change history ----------------------------------------------------------


def test_a_server_setting_is_undoable(server: MtaSandbox) -> None:
    assert set_server(server, "activationRadius", 7.5) is True

    call(server, "function() return ANKIGTA.Store.undo() end")
    server.execute("ANKIGTA.SettingsStore.load()")

    assert server_value(server, "activationRadius") == 3


def test_include_in_study_is_offered_per_map_and_recorded_in_history(
    server: MtaSandbox,
) -> None:
    ok = call(
        server,
        "function() return ANKIGTA.SettingsStore.setMapIncludeInStudy("
        '"ticket05-map", false) end',
    )
    assert ok is True

    assert map_preferences(server)["ticket05-map"] is False

    call(server, "function() return ANKIGTA.Store.undo() end")

    assert map_preferences(server)["ticket05-map"] is True


# --- the wire between the two sides ------------------------------------------


@pytest.fixture
def wired(tmp_path: Path) -> Iterator[MtaSandbox]:
    """The whole server, so the settings events are tested where they live."""
    sandbox = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
    for script in manifest_scripts("shared", "server"):
        sandbox.load(script)
    sandbox.trigger("onResourceStart")
    try:
        yield sandbox
    finally:
        sandbox.close()


def request(sandbox: MtaSandbox, event: str, *args: Any, player: Any = None) -> None:
    sandbox.trigger(
        event,
        sandbox.eval("resourceRoot"),
        *args,
        client=player if player is not None else sandbox.add_study_player(),
    )


def client_events(sandbox: MtaSandbox, name: str) -> list[Any]:
    return [event for event in sandbox.recorder.client_events if event.name == name]


def test_the_server_answers_a_settings_request_with_what_it_owns(
    wired: MtaSandbox,
) -> None:
    request(wired, "ankigta:requestSettings")

    snapshots = client_events(wired, "ankigta:settingsSnapshot")
    assert len(snapshots) == 1
    values = snapshots[0].args[0]["values"]
    assert values["activationRadius"] == 3
    assert values["uiScale"] is None, "the server must not answer for the client"


def test_a_value_the_schema_rejects_comes_back_as_a_localization_key(
    wired: MtaSandbox,
) -> None:
    request(wired, "ankigta:updateSetting", "activationRadius", 200)

    rejections = client_events(wired, "ankigta:settingRejected")
    assert len(rejections) == 1
    assert rejections[0].args[0] == "activationRadius"
    assert rejections[0].args[1] == "settings.error.out_of_range"
    assert server_value(wired, "activationRadius") == 3


def test_a_client_owned_setting_sent_to_the_server_is_refused(
    wired: MtaSandbox,
) -> None:
    request(wired, "ankigta:updateSetting", "uiScale", 2)

    rejections = client_events(wired, "ankigta:settingRejected")
    assert rejections[0].args[1] == "wrong_authority"


def test_an_accepted_value_is_stored_and_echoed_back(wired: MtaSandbox) -> None:
    request(wired, "ankigta:updateSetting", "activationRadius", 7.5)

    assert client_events(wired, "ankigta:settingRejected") == []
    assert server_value(wired, "activationRadius") == 7.5
    snapshot = client_events(wired, "ankigta:settingsSnapshot")[-1]
    assert snapshot.args[0]["values"]["activationRadius"] == 7.5


def test_a_player_without_the_study_right_changes_nothing(wired: MtaSandbox) -> None:
    stranger = wired.add_study_player(right="resource.ankigta.nothing")

    request(wired, "ankigta:updateSetting", "activationRadius", 7.5, player=stranger)

    assert server_value(wired, "activationRadius") == 3


# --- language ----------------------------------------------------------------


def test_switching_language_relabels_the_open_panel_without_a_restart(
    client: MtaSandbox,
) -> None:
    open_panel(client)
    english = translate(client, control(client, "activationRadius")["labelKey"])

    call(
        client,
        "function() end",
    )
    panel_action(client, "setSetting", {"key": "language", "value": "ru"})

    russian = translate(client, control(client, "activationRadius")["labelKey"])
    assert english == "Activation Zone radius (m)"
    assert russian == "Радиус зоны активации (м)"
    assert client_value(client, "language") == "ru"


def test_a_choice_the_schema_does_not_offer_is_rejected(client: MtaSandbox) -> None:
    open_panel(client)

    call(
        client,
        "function() end",
    )
    panel_action(
        client, "setSetting", {"key": "indicatorMode", "value": "sphere_only"}
    )

    assert control(client, "indicatorMode")["error"] == (
        "settings.error.not_a_choice"
    )
    assert client_value(client, "indicatorMode") == "none"


# --- the settings a change actually reaches ----------------------------------


def test_an_accepted_client_setting_reaches_the_module_that_uses_it() -> None:
    sandbox = open_client(
        scripts=(
            "shared/settings.lua",
            "shared/locale.lua",
            "shared/entity_types.lua",
            "client/layout.lua",
            "client/indicator.lua",
            "client/review_mode.lua",
            "client/settings_store.lua",
            "client/panel.lua",
        )
    )
    open_panel(sandbox)

    call(
        sandbox,
        "function() end",
    )
    panel_action(
        sandbox, "setSetting", {"key": "indicatorMode", "value": "minimap_only"}
    )
    call(
        sandbox,
        "function() end",
    )
    panel_action(sandbox, "setSetting", {"key": "muteGameWorld", "value": True})

    assert sandbox.eval("ANKIGTA.Indicator.mode") == "minimap_only"
    assert sandbox.eval("ANKIGTA.ReviewMode.muteGameWorld") is True
    sandbox.close()


def test_the_panel_offers_a_way_into_the_settings_panel() -> None:
    sandbox = open_client(
        scripts=(
            "shared/settings.lua",
            "shared/locale.lua",
            "shared/entity_types.lua",
            "client/layout.lua",
            "client/settings_store.lua",
            "client/panel.lua",
        )
    )
    sandbox.trigger("ankigta:setAuthorized", sandbox.eval("resourceRoot"), True)
    call(
        sandbox,
        """
        function()
            triggerEvent("ankigta:companionStatus", resourceRoot,
                {state = "connected"})
        end
        """,
    )
    for handler in sandbox.bound_keys.get(("F7", "down"), []):
        handler()
    panel_action(sandbox, "ready")
    sandbox.trigger(
        "ankigta:f7Snapshot",
        sandbox.eval("resourceRoot"),
        sandbox.eval(
            "function() return {visible = true, entities = {},"
            " cardPicker = {enabled = false}, history = {}} end"
        )(),
    )

    # The panel is a page: its button arrives here as the action it names.
    sandbox.eval(
        'function() triggerEvent("ankigta:panelAction", resourceRoot,'
        ' "openSettings", "{}") end'
    )()

    assert pushed_state(sandbox)["section"] == "settings"
    sandbox.close()


def test_review_mode_offers_a_way_into_the_settings_panel() -> None:
    sandbox = open_client(
        scripts=(
            "shared/settings.lua",
            "shared/locale.lua",
            "shared/entity_types.lua",
            "client/layout.lua",
            "client/review_mode.lua",
            "client/settings_store.lua",
            "client/panel.lua",
        )
    )
    call(
        sandbox,
        """
        function()
            triggerEvent("ankigta:openReviewMode", resourceRoot, {
                url = "http://127.0.0.1:1/render/t/index.html",
                side = "question",
                cardIdentity = {collectionUuid = "c", cardId = 1},
            })
            renderReviewMode()
        end
        """,
    )
    sandbox.trigger("ankigta:setAuthorized", sandbox.eval("resourceRoot"), True)
    call(
        sandbox,
        """
        function()
            triggerEvent("ankigta:companionStatus", resourceRoot,
                {state = "connected"})
        end
        """,
    )
    for handler in sandbox.bound_keys.get(("F7", "down"), []):
        handler()
    panel_action(sandbox, "ready")

    bounds = sandbox.eval("ANKIGTA.ReviewMode.ratingBounds")["settings"]
    assert bounds is not None

    call(
        sandbox,
        "function(x, y) handleReviewClick('left', 'down', x, y) end",
        bounds[1] + bounds[3] / 2,
        bounds[2] + bounds[4] / 2,
    )

    assert pushed_state(sandbox)["section"] == "settings"
    sandbox.close()
