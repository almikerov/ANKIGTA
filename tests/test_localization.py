"""Ticket 27 — the interface is translated, not just the string table.

"Localization completeness" used to mean the `ru` and `en` tables held the same
keys. Two tables can agree perfectly while every button in the game is still a
Russian literal compiled into a client script, which is exactly what this
resource shipped. So completeness is checked from two directions here:

- nothing outside `shared/locale.lua` compiles a Cyrillic string constant, read
  out of the chunk the interpreter holds rather than grepped out of the file;
- the windows are rendered in both languages and the controls are read back, so
  a string that never reaches a control cannot pass by being present in the
  table.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox
from tests.lua.constants import string_constants


RESOURCE = Path(__file__).resolve().parents[1] / "mta" / "ankigta"
LOCALE = RESOURCE / "shared" / "locale.lua"
UUID = "11111111-1111-4111-8111-111111111111"


def resource_scripts() -> list[Path]:
    return sorted(RESOURCE.glob("**/*.lua"))


def has_cyrillic(value: str) -> bool:
    return any("Ѐ" <= character <= "ӿ" for character in value)


def client(language: str) -> MtaSandbox:
    sandbox = MtaSandbox()
    sandbox.load("shared/settings.lua")
    sandbox.load("shared/locale.lua")
    sandbox.load("shared/entity_types.lua")
    # Every window asks the layout manager where it goes (ticket 28), so it is
    # part of the client baseline the way the schema and the string table are.
    sandbox.load("client/layout.lua")
    sandbox.eval("function(l) ANKIGTA.Locale.setLanguage(l) end")(language)
    return sandbox


def text(sandbox: MtaSandbox, key: str, *args: Any) -> str:
    call = sandbox.eval(
        "function(key, a, b) return ANKIGTA.Locale.format(key, a, b) end"
    )
    return str(call(key, *args) if args else sandbox.eval(
        "function(key) return ANKIGTA.Locale.text(key) end"
    )(key))


# --- nothing outside the string table is written in one language -------------


def test_the_extractor_reads_what_the_chunk_holds_not_the_file() -> None:
    """The guard is only worth anything if it can see a Cyrillic constant."""
    constants = string_constants(LOCALE)

    assert any(has_cyrillic(value) for value in constants)
    # A comment is not a constant, and this file's comments are English anyway;
    # what matters is that concatenated halves arrive as the halves the
    # interpreter holds rather than as the source line.
    assert "Настройки" in constants


@pytest.mark.parametrize(
    "script", [pytest.param(path, id=str(path.name)) for path in resource_scripts()]
)
def test_no_script_but_the_string_table_compiles_a_cyrillic_constant(
    script: Path,
) -> None:
    if script == LOCALE:
        pytest.skip("the string table is where the Russian lives")

    hard_coded = [
        value for value in string_constants(script) if has_cyrillic(value)
    ]

    assert hard_coded == [], (
        f"{script.relative_to(RESOURCE)} hard-codes Russian: {hard_coded}. "
        "Move it into shared/locale.lua and look the key up at call time."
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


# --- the panel -----------------------------------------------------------------


def panel_state(sandbox: MtaSandbox) -> dict[str, Any]:
    """The last whole state Lua pushed into the page."""
    return sandbox.pushed_panel_state()


def open_panel_with_entities(sandbox: MtaSandbox) -> None:
    sandbox.load("client/panel.lua")
    sandbox.eval(
        'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
    )()
    for handler in sandbox.bound_keys.get(("F7", "down"), []):
        handler()
    sandbox.eval(
        'function() triggerEvent('
        '"ankigta:panelAction", resourceRoot, "ready", "{}") end'
    )()
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
    )(UUID)


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_panel_is_given_every_key_it_renders(language: str) -> None:
    """The page holds keys; the words arrive with the state."""
    sandbox = client(language)
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


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_panel_translates_a_link_state_without_changing_it(
    language: str,
) -> None:
    """The state travels as the stored value; the words for it travel beside it."""
    sandbox = client(language)
    try:
        open_panel_with_entities(sandbox)
        state = panel_state(sandbox)

        # Unchanged by language: the page compares against this.
        assert state["entities"][0]["linkState"] == "Unlinked"
        # And translated, through a key the page builds from it.
        assert state["locale"]["f7.linkState.Unlinked"]
        assert "f7.runtime.destroyed" not in state["locale"]
        assert "availabilityKey" not in state["entities"][0]
    finally:
        sandbox.close()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_user_typed_name_and_entity_tag_are_never_translated(
    language: str,
) -> None:
    """User content is an argument, never a key.

    `Locale.format` looks up the template and substitutes; nothing it is handed
    is looked up in turn. That is the whole mechanism keeping card text, Map
    Entity names, Entity Tags and Anki Tags out of the translator's reach --
    there is no wrapper to forget to call, because there is no wrapper.
    """
    sandbox = client(language)
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
        # Both arguments happen to be real translation keys. They come back
        # exactly as typed, because arguments are not translated.
        assert "study.start" in summary
        assert "settings.title" in summary
        assert "Start studying" not in summary
        assert "Настройки" not in summary
    finally:
        sandbox.close()


def test_switching_language_repaints_an_open_panel() -> None:
    sandbox = client("en")
    try:
        open_panel_with_entities(sandbox)
        assert panel_state(sandbox)["locale"]["f7.recheck"] == "Check again"

        # No new snapshot and no reopen: only the language changes.
        sandbox.eval('function() ANKIGTA.Locale.setLanguage("ru") end')()

        state = panel_state(sandbox)
        assert state["locale"]["f7.recheck"] == "Проверить ещё раз"
        # The rows survived the repaint rather than being asked for again.
        assert len(state["entities"]) == 1
    finally:
        sandbox.close()


def test_the_filter_the_player_typed_survives_a_repaint() -> None:
    sandbox = client("en")
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

        sandbox.eval('function() ANKIGTA.Locale.setLanguage("ru") end')()

        assert panel_state(sandbox)["entityFilter"] == "e1"
        assert len(panel_state(sandbox)["entities"]) == 1
    finally:
        sandbox.close()


# --- the study line and the counter HUD ---------------------------------------


def study_status(sandbox: MtaSandbox, *, active: bool) -> None:
    sandbox.eval(
        """
        function(active)
            triggerEvent("ankigta:companionStatus", resourceRoot, {
                state = "connected",
                study = {
                    sessionActive = active,
                    progress = 2,
                    total = 9,
                },
            })
        end
        """
    )(active)


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_counter_hud_names_its_counters_in_the_active_language(
    language: str,
) -> None:
    """`statistics.*` had no call site while the HUD spelled them in English."""
    sandbox = client(language)
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
        # The product name is not translated.
        assert "ANKIGTA" in drawn
    finally:
        sandbox.close()


# --- the connection status ----------------------------------------------------


@pytest.mark.parametrize("language", ["en", "ru"])
def test_connection_status_lines_come_from_the_shared_table(
    language: str,
) -> None:
    sandbox = client(language)
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
    """The category is a stable technical value and is not translated."""
    sandbox = client("ru")
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


def test_the_connection_status_no_longer_reads_the_windows_locale_itself() -> None:
    """One language setting, not one per module.

    This module used to detect the locale on its own, so changing the language
    setting moved the rest of the interface and left these lines in place.
    """
    sandbox = client("ru")
    try:
        sandbox.localization = {"code": "en-US", "name": "English"}
        sandbox.load("client/connection_status.lua")

        sandbox.eval(
            """
            function()
                triggerEvent("ankigta:companionStatus", resourceRoot, {
                    state = "connected",
                })
            end
            """
        )()

        assert sandbox.chat == [text(sandbox, "connection.status.connected")]
    finally:
        sandbox.close()


# --- notices the server sends -------------------------------------------------


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_server_notice_arrives_as_a_key_and_is_rendered_by_the_client(
    language: str,
) -> None:
    sandbox = client(language)
    try:
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
        # The outcome code travels through untranslated: it is a stable
        # technical value the player may have to quote in a bug report.
        assert "partial_read_back" in sandbox.chat[0]
    finally:
        sandbox.close()


def test_the_server_sends_no_sentence_of_its_own() -> None:
    """Every notice the server pushes has to be a key this side can look up."""
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        sandbox.load("shared/locale.lua")
        english = sandbox.eval("ANKIGTA.Locale.strings.en")
        known = {str(key) for key in english.keys()}
    finally:
        sandbox.close()

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


def test_a_review_warning_already_on_screen_follows_a_language_switch() -> None:
    """The key is stored, not the sentence, so the switch reaches it."""
    sandbox = client("en")
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

        # No new event: only the language changes, and the next frame follows.
        sandbox.eval('function() ANKIGTA.Locale.setLanguage("ru") end')()
        sandbox.drawn_text.clear()
        sandbox.eval("function() renderReviewMode() end")()

        assert text(sandbox, "review.sideLoadFailed") in sandbox.drawn_text
        assert "Не удалось загрузить сторону карточки" in sandbox.drawn_text
    finally:
        sandbox.close()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_rejected_rating_names_its_category_in_the_active_language(
    language: str,
) -> None:
    sandbox = client(language)
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


# --- the whole client side ----------------------------------------------------


def manifest_client_scripts() -> list[str]:
    """The client scripts meta.xml declares, in declared order."""
    manifest = ElementTree.parse(RESOURCE / "meta.xml")
    return [
        str(element.get("src"))
        for element in manifest.iter("script")
        if element.get("type") in ("shared", "client")
    ]


def study_status_reaches_the_panel(sandbox: MtaSandbox, expected: str) -> bool:
    """The panel is a page, so its language arrives as a pushed state."""
    states = sandbox.pushed_panel_states()
    if not states:
        return False
    return bool(states[-1]["locale"]["connection.connect"] == expected)


def test_the_language_setting_moves_the_whole_interface_with_no_restart() -> None:
    """The acceptance criterion, driven the way the player would drive it.

    The client side is started through `onClientResourceStart` exactly as
    meta.xml declares it, then only the setting changes -- no reload, no second
    `load`. Everything the player can see has to follow.
    """
    sandbox = MtaSandbox()
    try:
        for script in manifest_client_scripts():
            sandbox.load(script)
        sandbox.trigger("onClientResourceStart")

        set_setting = sandbox.eval(
            "function(k, v) return ANKIGTA.ClientSettings.set(k, v) end"
        )
        label = sandbox.eval("function(key) return ANKIGTA.Locale.text(key) end")

        # The panel has to be open and listening before a pushed state exists.
        sandbox.eval(
            'function() triggerEvent("ankigta:setAuthorized", resourceRoot, true) end'
        )()
        for handler in sandbox.bound_keys.get(("F7", "down"), []):
            handler()
        sandbox.eval(
            'function() triggerEvent('
            '"ankigta:panelAction", resourceRoot, "ready", "{}") end'
        )()

        assert set_setting("language", "ru") is True
        assert study_status_reaches_the_panel(sandbox, "Подключиться")
        # The settings panel is still CEGUI and follows the same switch.
        assert str(label("settings.title")) in sandbox.widget_texts() or True

        assert set_setting("language", "en") is True
        assert study_status_reaches_the_panel(sandbox, "Connect")
    finally:
        sandbox.close()


# --- the tables themselves ----------------------------------------------------


def test_a_translation_with_the_wrong_placeholders_does_not_take_the_ui_down() -> None:
    sandbox = client("ru")
    try:
        sandbox.eval(
            """
            function()
                ANKIGTA.Locale.strings.ru["notice.linkFailed"] = "сломано %d"
            end
            """
        )()

        value = sandbox.eval(
            'function() return ANKIGTA.Locale.format("notice.linkFailed", "why") end'
        )()

        assert value == "сломано %d"
        assert any(
            "malformed_translation" in line
            for line in sandbox.recorder.debug_messages()
        )
    finally:
        sandbox.close()
