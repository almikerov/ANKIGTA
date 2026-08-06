"""Ticket 01 — ANKIGTA speaks English, and carries nothing for speaking two.

Ticket 27 built a two-language interface and this file guarded it from two
directions: that no script outside `shared/locale.lua` compiled a string
constant in one language, and that the windows rendered in both. The second
direction is gone with the Russian table. The first one stays, and is stricter
than it was, because the string table itself has nothing to exempt:

- nothing anywhere in the resource compiles a Cyrillic string constant, read
  out of the chunk the interpreter holds rather than grepped out of the file;
- there is no language to choose, nothing reads the Windows locale, and a
  `language` left in a player's settings file is discarded rather than obeyed;
- the surfaces are rendered and read back, so a string that never reaches a
  control cannot pass by being present in the table.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any

import pytest

from tests.lua import MtaSandbox
from tests.lua.constants import string_constants
from tests.lua.strings import (
    LOCALE,
    RESOURCE,
    locale_keys,
    named_keys,
    resource_scripts,
)


UUID = "11111111-1111-4111-8111-111111111111"


def has_cyrillic(value: str) -> bool:
    return any("Ѐ" <= character <= "ӿ" for character in value)


def manifest_client_scripts() -> list[str]:
    """The client scripts meta.xml declares, in declared order."""
    manifest = ElementTree.parse(RESOURCE / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in ("shared", "client")
    ]


def client() -> MtaSandbox:
    sandbox = MtaSandbox()
    sandbox.load("shared/settings.lua")
    sandbox.load("shared/locale.lua")
    sandbox.load("shared/entity_types.lua")
    # Every window asks the layout manager where it goes (ticket 28), so it is
    # part of the client baseline the way the schema and the string table are.
    sandbox.load("client/layout.lua")
    return sandbox


def text(sandbox: MtaSandbox, key: str, *args: Any) -> str:
    call = sandbox.eval(
        "function(key, a, b) return ANKIGTA.Locale.format(key, a, b) end"
    )
    return str(call(key, *args) if args else sandbox.eval(
        "function(key) return ANKIGTA.Locale.text(key) end"
    )(key))


def panel_state(sandbox: MtaSandbox) -> dict[str, Any]:
    """The last whole state Lua pushed into the page."""
    return sandbox.pushed_panel_state()


def open_panel(sandbox: MtaSandbox) -> None:
    sandbox.load("client/panel.lua")
    # The panel binds its key when the resource starts, not while its chunk
    # loads: on an incremental reload a `cache="false"` script can run before
    # the shared schema it would have to read. MTA always fires this, so a
    # test that wants a bound key has to as well.
    sandbox.trigger("onClientResourceStart")
    sandbox.eval(
        'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
    )()
    for handler in sandbox.bound_keys.get(("F7", "down"), []):
        handler()
    sandbox.eval(
        'function() triggerEvent('
        '"ankigta:panelAction", resourceRoot, "ready", "{}") end'
    )()


def open_panel_with_entities(sandbox: MtaSandbox) -> None:
    open_panel(sandbox)
    sandbox.eval(
        """
        function()
            triggerEvent("ankigta:f7Snapshot", resourceRoot, {
                visible = true,
                cardPicker = {enabled = true},
                history = {canUndo = false, canRedo = false},
                entities = {
                    {
                        mapEntity = {
                            mapId = "m1", entityId = "e1", type = "object",
                            authored = {
                                position = {x = 1.0, y = 2.0, z = 3.0},
                                world = {interior = 0, dimension = 0},
                            },
                        },
                        runtimeInstance = {available = false},
                        link = {
                            state = "Unlinked",
                            metadata = {name = "Мой объект", entityTag = "мой тег"},
                        },
                    },
                },
            })
        end
        """
    )()


# --- nothing anywhere is written in another language -------------------------


def test_the_extractor_reads_what_the_chunk_holds_not_the_file(
    tmp_path: Path,
) -> None:
    """The guard is only worth anything if it can see a Cyrillic constant.

    It brings its own now, because the resource no longer holds one -- which is
    the point of the ticket, and would otherwise leave this guard passing
    because there is nothing left anywhere for it to find.
    """
    script = tmp_path / "smuggled.lua"
    script.write_text(
        "-- Настройки in a comment is not a constant.\n"
        'local greeting = "Настро" .. "йки"\n'
        "return greeting\n",
        encoding="utf-8",
    )

    constants = string_constants(script)

    # Concatenated halves arrive as the halves the interpreter holds, rather
    # than as the source line.
    assert "Настро" in constants
    assert any(has_cyrillic(value) for value in constants)
    # And a comment is not a constant.
    assert "Настройки" not in constants


@pytest.mark.parametrize(
    "script", [pytest.param(path, id=str(path.name)) for path in resource_scripts()]
)
def test_no_script_at_all_compiles_a_cyrillic_constant(script: Path) -> None:
    """No exemption, not even the string table: there is one language now."""
    hard_coded = [
        value for value in string_constants(script) if has_cyrillic(value)
    ]

    assert hard_coded == [], (
        f"{script.relative_to(RESOURCE)} hard-codes another language: "
        f"{hard_coded}. ANKIGTA ships in English; put the words in "
        "shared/locale.lua and look the key up at call time."
    )


@pytest.mark.parametrize(
    "script", [pytest.param(path, id=str(path.name)) for path in resource_scripts()]
)
def test_every_key_a_script_names_has_words_behind_it(script: Path) -> None:
    """A key with nothing behind it renders as itself on a control.

    `Locale.text` returns the key when the table has no string for it, and
    logs -- which a player sees as `settings.error.secret_not_readable` on a
    row and nobody sees in a debug log. Every ticket after this one adds
    strings, and this is what makes forgetting one a failing test.
    """
    missing = sorted(named_keys(script) - locale_keys())

    assert missing == [], (
        f"{script.relative_to(RESOURCE)} asks for keys shared/locale.lua does "
        f"not define: {missing}"
    )


def test_every_script_in_the_manifest_is_covered_by_the_guard() -> None:
    """A file the glob misses is a file the guard silently stops protecting."""
    covered = {path.resolve() for path in resource_scripts()}

    for relative in (
        "shared/locale.lua",
        "client/panel.lua",
        "client/review_mode.lua",
        "client/connection_status.lua",
        "server/main.lua",
        "server/map_identity.lua",
    ):
        assert (RESOURCE / relative).resolve() in covered


# --- there is no language to choose ------------------------------------------


def test_the_schema_offers_no_language_setting() -> None:
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")

        assert sandbox.eval(
            'function() return ANKIGTA.Settings.definition("language") end'
        )() is None
        ordered = sandbox.eval(
            "function() return ANKIGTA.Settings.orderedKeys() end"
        )()
        assert "language" not in {str(ordered[index]) for index in ordered.keys()}
    finally:
        sandbox.close()


def test_the_string_table_keeps_no_machinery_for_a_second_language() -> None:
    """Named one by one rather than as an exact key set.

    A later ticket is allowed to add a helper here; it is not allowed to bring
    any of these back, and an exact-set assertion would fail on the first
    without saying anything about the second.
    """
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/locale.lua")
        locale = sandbox.eval("ANKIGTA.Locale")

        for gone in (
            "language",
            "setLanguage",
            "detect",
            "onChange",
            "listeners",
            "availableLanguages",
        ):
            assert locale[gone] is None, gone
        # One table with one key each, rather than one table per language.
        assert sandbox.eval("ANKIGTA.Locale.text") is not None
        assert sandbox.eval("ANKIGTA.Locale.format") is not None
        assert sandbox.eval('ANKIGTA.Locale.strings["settings.title"]') == "Settings"
    finally:
        sandbox.close()


def test_the_settings_panel_offers_no_language_row() -> None:
    sandbox = client()
    try:
        open_panel_with_entities(sandbox)
        rows = panel_state(sandbox)["settings"]["rows"]

        keys = {str(row["key"]) for row in rows}
        assert keys, "the settings section rendered no rows at all"
        assert "language" not in keys
    finally:
        sandbox.close()


def test_nothing_asks_windows_what_language_it_is_in() -> None:
    """The whole client side, started the way meta.xml starts it.

    The sandbox reports a Russian Windows locale, so a module that still asked
    would be counted here -- and, before this ticket, would have answered the
    panel in Russian.
    """
    sandbox = MtaSandbox()
    try:
        for script in manifest_client_scripts():
            sandbox.load(script)
        sandbox.trigger("onClientResourceStart")
        open_panel(sandbox)

        assert sandbox.localization_reads == 0
        assert panel_state(sandbox)["locale"]["settings.title"] == "Settings"
    finally:
        sandbox.close()


def test_a_language_left_in_a_settings_file_is_discarded_not_obeyed() -> None:
    """The setting is gone; a player's file still holds it, and must still load."""
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        sandbox.load("shared/locale.lua")
        sandbox.load("client/layout.lua")
        sandbox.load("client/indicator.lua")
        sandbox.files["@ankigta-settings.json"] = (
            b'{"language":"ru","indicatorMode":"minimap_only"}'
        )
        sandbox.load("client/settings_store.lua")
        sandbox.trigger("onClientResourceStart")

        # The file loaded, rather than being refused over the key it no longer
        # knows -- the rest of the player's settings are still theirs.
        assert sandbox.eval("ANKIGTA.ClientSettings.loaded") is True
        assert sandbox.eval(
            'function() return ANKIGTA.ClientSettings.get("indicatorMode") end'
        )() == "minimap_only"
        assert sandbox.eval("ANKIGTA.Indicator.mode") == "minimap_only"

        # And the setting does not come back from the file that still holds it.
        refused, reason = sandbox.eval(
            'function() return ANKIGTA.ClientSettings.get("language") end'
        )()
        assert refused is False
        assert reason == "settings.error.unknown"
        assert "language" not in {
            str(key) for key in sandbox.eval("ANKIGTA.ClientSettings.all()").keys()
        }
        assert any(
            "discarded_stored_setting" in line and "language" in line
            for line in sandbox.recorder.debug_messages()
        )
    finally:
        sandbox.close()


# --- the panel -----------------------------------------------------------------


def repaint(sandbox: MtaSandbox) -> None:
    """A redraw the player did not ask for, from a source that is not the page."""
    sandbox.eval(
        """
        function()
            triggerEvent("ankigta:settingsSnapshot", resourceRoot, {
                values = {activationRadius = 4},
                maps = {},
            })
        end
        """
    )()


def test_the_panel_is_handed_words_for_the_keys_the_page_holds() -> None:
    """The page holds keys; the words arrive with the state.

    That the page holds a key *for* every surface is
    `tests/test_panel_locale_keys.py`'s job -- it reads the page. This one only
    asks that what Lua pushes carries words rather than the keys back again,
    which is what the state looked like when `toJSON` wrapped it in a list.
    """
    sandbox = client()
    try:
        open_panel_with_entities(sandbox)
        locale = panel_state(sandbox)["locale"]

        for key in (
            "f7.title",
            "f7.recheck",
            "f7.unlink",
            "f7.relink",
            "f7.pickEntity",
            "f7.cardPicker",
            "f7.copyOriginal",
            "f7.copyNew",
            "cardPicker.search",
            "cardPicker.link",
            "connection.connect",
            "study.start",
        ):
            assert locale.get(key), key
            assert locale[key] != key
    finally:
        sandbox.close()


def test_the_panel_gives_words_for_a_link_state_without_changing_it() -> None:
    """The state travels as the stored value; the words for it travel beside it."""
    sandbox = client()
    try:
        open_panel_with_entities(sandbox)
        state = panel_state(sandbox)

        # Unchanged by what is shown: the page compares against this.
        assert state["entities"][0]["linkState"] == "Unlinked"
        assert state["locale"]["f7.linkState.Unlinked"]
        assert "f7.runtime.destroyed" not in state["locale"]
        assert "availabilityKey" not in state["entities"][0]
    finally:
        sandbox.close()


def test_a_user_typed_name_and_entity_tag_are_never_looked_up() -> None:
    """User content is an argument, never a key.

    `Locale.format` looks up the template and substitutes; nothing it is handed
    is looked up in turn. That is the whole mechanism keeping card text, Map
    Entity names, Entity Tags and Anki Tags out of the table's reach -- there is
    no wrapper to forget to call, because there is no wrapper. It is also why a
    Russian Map Entity name stays a Russian Map Entity name in an interface
    with no Russian left in it.
    """
    sandbox = client()
    try:
        open_panel_with_entities(sandbox)

        # The name the user typed reaches the page exactly as they typed it.
        assert panel_state(sandbox)["entities"][0]["name"] == "Мой объект"

        summary = str(
            sandbox.eval(
                """
                function(name, tag)
                    return ANKIGTA.Locale.format(
                        "f7.metadataSummary", name, tag, 3.0,
                        ANKIGTA.Locale.text("common.yes")
                    )
                end
                """
            )("study.start", "settings.title")
        )
        # Both arguments happen to be real keys. They come back exactly as
        # typed, because arguments are not looked up.
        assert "study.start" in summary
        assert "settings.title" in summary
        assert "Start studying" not in summary
        assert "Settings" not in summary
    finally:
        sandbox.close()


def test_the_filter_the_player_typed_survives_a_repaint() -> None:
    sandbox = client()
    try:
        open_panel_with_entities(sandbox)
        sandbox.eval(
            """
            function(payload)
                triggerEvent(
                    "ankigta:panelAction", resourceRoot, "filter", payload
                )
            end
            """
        )('{"text":"e1"}')
        assert panel_state(sandbox)["entityFilter"] == "e1"

        repaint(sandbox)

        assert panel_state(sandbox)["entityFilter"] == "e1"
        # The rows survived the repaint rather than being asked for again.
        assert len(panel_state(sandbox)["entities"]) == 1
    finally:
        sandbox.close()


# --- the study line and the counter HUD ---------------------------------------


def test_the_counter_hud_names_its_counters_from_the_table() -> None:
    """`statistics.*` had no call site while the HUD spelled them out itself."""
    sandbox = client()
    try:
        sandbox.load("client/indicator.lua")
        sandbox.eval(
            """
            function()
                triggerEvent("ankigta:statistics", resourceRoot, {
                    total = 4, new = 1, learning = 1, due = 1, early = 1,
                })
                ANKIGTA.Indicator.render()
            end
            """
        )()

        drawn = " ".join(sandbox.drawn_text)
        for key in (
            "statistics.total",
            "statistics.new",
            "statistics.learning",
            "statistics.due",
            "statistics.early",
        ):
            assert text(sandbox, key) in drawn, f"{key} never reached the HUD"
        # The product name does not come from the table.
        assert "ANKIGTA" in drawn
    finally:
        sandbox.close()


# --- the connection status ----------------------------------------------------


def test_connection_status_lines_come_from_the_shared_table() -> None:
    sandbox = client()
    try:
        sandbox.load("client/connection_status.lua")

        sandbox.eval(
            """
            function()
                triggerEvent("ankigta:companionStatus", resourceRoot, {
                    state = "disconnected",
                    category = "timeout",
                    warningCategory = "empty_token",
                })
            end
            """
        )()

        assert text(sandbox, "connection.status.timeout") in sandbox.chat
        assert text(sandbox, "connection.status.empty_token") in sandbox.chat
    finally:
        sandbox.close()


def test_an_unknown_status_category_is_shown_with_its_raw_code() -> None:
    """The category is a stable technical value and is not looked up."""
    sandbox = client()
    try:
        sandbox.load("client/connection_status.lua")

        sandbox.eval(
            """
            function()
                triggerEvent("ankigta:companionStatus", resourceRoot, {
                    state = "disconnected",
                    category = "something_new",
                })
            end
            """
        )()

        assert sandbox.chat == [
            text(sandbox, "connection.status.disconnected") + " [something_new]"
        ]
    finally:
        sandbox.close()


# --- notices the server sends -------------------------------------------------


def test_a_server_notice_arrives_as_a_key_and_is_worded_by_the_client() -> None:
    sandbox = client()
    try:
        # Where a code goes instead of to the player, so it is loaded here the
        # way the string table is.
        sandbox.load("client/diagnostics.lua")
        sandbox.load("client/panel.lua")

        sandbox.eval(
            """
            function()
                triggerEvent(
                    "ankigta:pendingMapSaveNotice",
                    resourceRoot,
                    "notice.pendingNotConfirmed",
                    "partial_read_back"
                )
            end
            """
        )()

        assert sandbox.chat == [
            text(sandbox, "notice.pendingNotConfirmed", "partial_read_back")
        ]
        # The code itself does not reach the player -- ticket 09: a refusal a
        # person reads is a sentence. It is a stable technical value they may
        # have to quote, so it goes where every value is one.
        assert "partial_read_back" not in sandbox.chat[0]
        assert (
            sandbox.eval(
                'function()'
                ' return ANKIGTA.Diagnostics.snapshot().notice.outcome end'
            )()
            == "partial_read_back"
        )
    finally:
        sandbox.close()


def test_the_server_sends_no_sentence_of_its_own() -> None:
    """Every notice the server pushes has to be a key this side can look up."""
    known = locale_keys()

    for script in ("server/main.lua", "server/map_identity.lua"):
        constants = set(string_constants(RESOURCE / script))
        notices = {value for value in constants if value.startswith("notice.")}
        guidance = {value for value in constants if value.startswith("guidance.")}
        assert notices, f"{script} pushes no notice keys at all"
        assert notices <= known, f"{script} sends unknown notices: {notices - known}"
        assert guidance <= known, (
            f"{script} sends unknown guidance: {guidance - known}"
        )


# --- Review Mode --------------------------------------------------------------


def test_a_review_warning_is_worded_from_its_key_every_frame() -> None:
    """The key is stored, not the sentence, so the words stay the drawing's."""
    sandbox = client()
    try:
        sandbox.load("client/review_mode.lua")
        sandbox.eval(
            """
            function(url, uuid)
                triggerEvent("ankigta:openReviewMode", resourceRoot, {
                    url = url,
                    side = "question",
                    cardIdentity = {collectionUuid = uuid, cardId = 7},
                })
                triggerEvent("ankigta:reviewSide", resourceRoot, {url = ""})
            end
            """
        )("http://127.0.0.1:51234/render/token/index.html", UUID)

        sandbox.eval("function() renderReviewMode() end")()
        assert text(sandbox, "review.sideLoadFailed") in sandbox.drawn_text

        # No new event: only the table changes, and the next frame follows it,
        # which is what a warning frozen at event time could not do.
        sandbox.eval(
            'function() ANKIGTA.Locale.strings["review.sideLoadFailed"] ='
            ' "The card side did not load" end'
        )()
        sandbox.drawn_text.clear()
        sandbox.eval("function() renderReviewMode() end")()

        assert "The card side did not load" in sandbox.drawn_text
    finally:
        sandbox.close()


def test_a_rejected_rating_names_its_category() -> None:
    sandbox = client()
    try:
        sandbox.load("client/review_mode.lua")
        sandbox.eval(
            """
            function(url, uuid)
                triggerEvent("ankigta:openReviewMode", resourceRoot, {
                    url = url,
                    side = "answer",
                    cardIdentity = {collectionUuid = uuid, cardId = 7},
                })
                triggerEvent("ankigta:reviewResult", resourceRoot, {
                    state = "rejected",
                    category = "collection_unavailable",
                })
            end
            """
        )("http://127.0.0.1:51234/render/token/index.html", UUID)

        warning = sandbox.eval("function() return reviewModeState() end")().warning

        assert warning == text(
            sandbox, "review.ratingRejected", "collection_unavailable"
        )
        assert "collection_unavailable" in warning
    finally:
        sandbox.close()


# --- the table itself ---------------------------------------------------------


def test_a_string_with_the_wrong_placeholders_does_not_take_the_ui_down() -> None:
    sandbox = client()
    try:
        sandbox.eval(
            """
            function()
                ANKIGTA.Locale.strings["notice.linkFailed"] = "broken %d"
            end
            """
        )()

        value = sandbox.eval(
            'function() return ANKIGTA.Locale.format("notice.linkFailed", "why") end'
        )()

        assert value == "broken %d"
        assert any(
            "malformed_string" in line
            for line in sandbox.recorder.debug_messages()
        )
    finally:
        sandbox.close()


def test_a_key_the_table_lacks_shows_the_key_and_logs() -> None:
    """A gap has to be visible: a blank control is a gap nobody can diagnose."""
    sandbox = client()
    try:
        assert text(sandbox, "nothing.here") == "nothing.here"
        assert any(
            "missing_string" in line
            for line in sandbox.recorder.debug_messages()
        )
    finally:
        sandbox.close()
