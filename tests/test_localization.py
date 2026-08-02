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
        "client/f7.lua",
        "client/panel.lua",
        "client/review_mode.lua",
        "client/connection_status.lua",
        "server/main.lua",
        "server/map_identity.lua",
    ):
        assert (RESOURCE / relative).resolve() in covered


# --- the F7 window ------------------------------------------------------------


def f7_snapshot(sandbox: MtaSandbox) -> None:
    """Render one snapshot holding every state the window has text for."""
    sandbox.eval(
        """
        function(uuid)
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
                            state = "Pending Map Save",
                            guidanceKey = "guidance.retrySave",
                            recheckAvailable = true,
                        },
                    },
                    {
                        mapEntity = {
                            mapId = "m1",
                            entityId = "e2",
                            type = "vehicle",
                            authored = {
                                position = {x = 4.0, y = 5.0, z = 6.0},
                                world = {interior = 1, dimension = 2},
                            },
                        },
                        runtimeInstance = {available = false},
                        link = {state = "Unlinked"},
                    },
                    {
                        mapEntity = {
                            mapId = "m1",
                            entityId = "e3",
                            type = "ped",
                            authored = {
                                position = {x = 7.0, y = 8.0, z = 9.0},
                                world = {interior = 0, dimension = 0},
                            },
                        },
                        runtimeInstance = {available = false},
                        link = {
                            state = "Card missing",
                            guidanceKey = "guidance.cardMissing",
                            cardIdentity = {collectionUuid = uuid, cardId = 7},
                            metadata = {
                                name = "Мой объект",
                                entityTag = "мой тег",
                                radius = 3.0,
                                showRadius = true,
                            },
                        },
                    },
                },
            })
        end
        """
    )(UUID)


@pytest.fixture(params=["en", "ru"])
def f7(request: pytest.FixtureRequest) -> Iterator[tuple[MtaSandbox, str]]:
    sandbox = client(str(request.param))
    sandbox.load("client/f7.lua")
    try:
        yield sandbox, str(request.param)
    finally:
        sandbox.close()


def test_the_f7_window_is_written_in_the_active_language(
    f7: tuple[MtaSandbox, str],
) -> None:
    sandbox, _language = f7

    f7_snapshot(sandbox)

    written = sandbox.widget_texts() + sandbox.grid_texts()
    for key in (
        "f7.title",
        "f7.column.mapEntity",
        "f7.column.type",
        "f7.column.authored",
        "f7.column.runtime",
        "f7.column.link",
        "f7.recheck",
        "f7.copyOriginal",
        "f7.copyNew",
        "f7.relink",
        "f7.unlink",
        "f7.replaceCard",
        "f7.cardPicker",
        "f7.pickEntity",
        "f7.undo",
        "f7.redo",
    ):
        assert text(sandbox, key) in written, f"{key} never reached a control"


def test_the_f7_window_translates_the_link_state_and_its_guidance(
    f7: tuple[MtaSandbox, str],
) -> None:
    sandbox, _language = f7

    f7_snapshot(sandbox)

    cells = sandbox.grid_texts()
    pending = text(sandbox, "f7.linkState.Pending Map Save")
    assert any(
        cell.startswith(pending) and text(sandbox, "guidance.retrySave") in cell
        for cell in cells
    )
    assert any(
        text(sandbox, "f7.linkState.Card missing") in cell for cell in cells
    )
    assert any(
        text(sandbox, "f7.runtime.destroyed") == cell for cell in cells
    )


def test_the_stored_link_state_does_not_change_with_the_language() -> None:
    """The display follows the language; what the client compares does not."""
    russian = client("ru")
    try:
        russian.load("client/f7.lua")
        f7_snapshot(russian)

        # Unlinked is the state the Card Picker button gates on. If translating
        # the display had changed the value, the button would be dead in
        # Russian.
        picker = text(russian, "f7.cardPicker")
        enabled = [
            widget.enabled
            for widget in russian.widgets
            if widget.text == picker and widget.kind == "button"
        ]
        assert enabled == [True]
    finally:
        russian.close()


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


def test_switching_language_relabels_an_f7_window_that_is_already_open() -> None:
    """A window writes its labels once, so it has to be told to rebuild.

    Without this the criterion would really read "switching needs no restart,
    but close every window first".
    """
    sandbox = client("en")
    try:
        sandbox.load("client/f7.lua")
        f7_snapshot(sandbox)
        assert "Check again" in sandbox.widget_texts()

        # No new snapshot: the window rebuilds from the one it already has, so
        # a disconnected client relabels too.
        before = len(sandbox.recorder.server_events)
        sandbox.eval('function() ANKIGTA.Locale.setLanguage("ru") end')()

        assert "Проверить ещё раз" in sandbox.widget_texts()
        assert "Check again" not in sandbox.widget_texts()
        assert not [
            event
            for event in sandbox.recorder.server_events[before:]
            if event.name == "ankigta:requestF7"
        ]
    finally:
        sandbox.close()


def picker_edits(sandbox: MtaSandbox) -> list[Any]:
    """Live edit controls inside the Card Picker window."""
    pickers = {
        index
        for index, widget in enumerate(sandbox.widgets)
        if widget.kind == "window"
        and not widget.destroyed
        and "Card Picker" in widget.text
    }
    return [
        widget
        for widget in sandbox.widgets
        if widget.kind == "edit"
        and not widget.destroyed
        and widget.parent in pickers
    ]


def test_relabelling_the_card_picker_keeps_what_the_player_typed() -> None:
    sandbox = client("en")
    try:
        sandbox.load("client/f7.lua")
        f7_snapshot(sandbox)
        sandbox.eval(
            """
            function()
                triggerEvent("ankigta:cardPickerSnapshot", resourceRoot, {
                    enabled = true,
                    cards = {},
                    existingLinks = {},
                })
            end
            """
        )()
        # The Card Picker's own field, not F7's Map Entity filter, which is a
        # live edit control in the window behind it.
        edits = picker_edits(sandbox)
        assert len(edits) == 1
        edits[0].text = "Колода::Мой набор"

        sandbox.eval('function() ANKIGTA.Locale.setLanguage("ru") end')()

        rebuilt = picker_edits(sandbox)
        assert len(rebuilt) == 1
        assert rebuilt[0].text == "Колода::Мой набор"
        assert text(sandbox, "cardPicker.search") in sandbox.widget_texts()
    finally:
        sandbox.close()


def test_switching_language_reaches_the_next_f7_render() -> None:
    sandbox = client("en")
    try:
        sandbox.load("client/f7.lua")
        f7_snapshot(sandbox)
        assert "Check again" in sandbox.widget_texts()

        sandbox.eval('function() ANKIGTA.Locale.setLanguage("ru") end')()
        f7_snapshot(sandbox)

        # The English window was destroyed and rebuilt in Russian, with no
        # resource restart in between.
        assert "Проверить ещё раз" in sandbox.widget_texts()
        assert "Check again" not in sandbox.widget_texts()
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
        sandbox.load("client/f7.lua")

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
    import json

    for code in reversed(sandbox.browser_javascript):
        start, end = code.find("("), code.rfind(")")
        if start == -1 or end == -1:
            continue
        try:
            state = json.loads(code[start + 1 : end])
        except json.JSONDecodeError:
            continue
        return state["locale"]["connection.connect"] == expected
    return False


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
        f7_snapshot(sandbox)
        russian = sandbox.widget_texts()
        assert str(label("f7.recheck")) in russian
        assert "Проверить ещё раз" in russian
        # The panel is told in whole, so the same switch reaches it too.
        assert study_status_reaches_the_panel(sandbox, "Подключиться")

        assert set_setting("language", "en") is True
        f7_snapshot(sandbox)
        english = sandbox.widget_texts()
        assert "Check again" in english
        assert "Проверить ещё раз" not in english
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
