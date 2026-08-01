"""Ticket 27 — settings authority and localization.

Two rules do most of the work. A side may only write what it owns (ADR 0014),
and bad input is rejected with a reason rather than quietly clamped — a
mistyped 200 turned into 50 leaves the user with a setting they never chose.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from tests.lua import MtaSandbox


@pytest.fixture
def settings() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.load("shared/settings.lua")
    try:
        yield sandbox
    finally:
        sandbox.close()


@pytest.fixture
def locale() -> Iterator[MtaSandbox]:
    sandbox = MtaSandbox()
    sandbox.load("shared/locale.lua")
    try:
        yield sandbox
    finally:
        sandbox.close()


def validate(sandbox: MtaSandbox, key: str, value: Any) -> Any:
    return sandbox.eval(
        "function(k, v) return ANKIGTA.Settings.validate(k, v) end"
    )(key, value)


def can_write(sandbox: MtaSandbox, side: str, key: str) -> Any:
    return sandbox.eval(
        "function(s, k) return ANKIGTA.Settings.canWrite(s, k) end"
    )(side, key)


# --- authority ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "owner"),
    [
        ("activationRadius", "server"),
        ("activationDelaySeconds", "server"),
        ("maxActivationSpeedKmh", "server"),
        ("allowEarlyReview", "server"),
        ("includeInStudy", "server"),
        ("indicatorMode", "client"),
        ("reviewProtection", "client"),
        ("disablePlayerControls", "client"),
        ("closeAfterRating", "client"),
        ("cardAudioEnabled", "client"),
        ("muteGameWorld", "client"),
        ("uiScale", "client"),
        ("uiPlacement", "client"),
        ("connectionPort", "addon"),
        ("connectionToken", "addon"),
    ],
)
def test_each_setting_has_the_owner_adr_0014_gives_it(
    settings: MtaSandbox,
    key: str,
    owner: str,
) -> None:
    assert settings.eval(
        "function(k) return ANKIGTA.Settings.authorityOf(k) end"
    )(key) == owner


def test_a_side_cannot_write_a_setting_it_does_not_own(
    settings: MtaSandbox,
) -> None:
    assert can_write(settings, "server", "activationRadius") is True
    ok, reason = can_write(settings, "client", "activationRadius")
    assert ok is False
    assert reason == "wrong_authority"

    assert can_write(settings, "client", "indicatorMode") is True
    assert can_write(settings, "server", "indicatorMode")[0] is False


def test_a_manual_connection_override_is_writable_on_either_side(
    settings: MtaSandbox,
) -> None:
    """ADR 0014: the override is local, even though the add-on owns the value."""
    for side in ("server", "client"):
        assert can_write(settings, side, "connectionPort") is True
        assert can_write(settings, side, "connectionToken") is True


def test_an_unknown_setting_is_never_writable(settings: MtaSandbox) -> None:
    ok, reason = can_write(settings, "server", "somethingInvented")

    assert ok is False
    assert reason == "unknown_setting"


def test_writing_a_setting_you_own_is_not_the_same_as_overriding_it(
    settings: MtaSandbox,
) -> None:
    """The store has to put the two in different places, so the schema has to
    tell them apart."""
    write_kind = settings.eval(
        "function(s, k) return ANKIGTA.Settings.writeKind(s, k) end"
    )

    assert write_kind("server", "activationRadius") == "authority"
    assert write_kind("addon", "connectionPort") == "authority"
    assert write_kind("server", "connectionPort") == "local_override"
    assert write_kind("client", "connectionPort") == "local_override"
    assert write_kind("client", "activationRadius")[0] is False


@pytest.mark.parametrize("key", ["activationRadius", "indicatorMode", "connectionPort"])
def test_a_side_the_schema_does_not_know_may_not_write_anything(
    settings: MtaSandbox,
    key: str,
) -> None:
    ok, reason = can_write(settings, "somewhere_else", key)

    assert ok is False
    assert reason == "wrong_authority"
    assert settings.eval(
        "function(s, k) return ANKIGTA.Settings.writeKind(s, k) end"
    )("somewhere_else", key)[0] is False


def test_an_override_carries_the_side_that_made_it(settings: MtaSandbox) -> None:
    record = settings.eval(
        "function(s, k, v) return ANKIGTA.Settings.overrideBy(s, k, v) end"
    )("server", "connectionPort", "40009")

    assert record["side"] == "server"
    assert record["key"] == "connectionPort"
    # Normalized, so a port typed into a text field is not stored as text.
    assert record["value"] == 40009


def test_an_override_applies_only_to_the_side_that_made_it(
    settings: MtaSandbox,
) -> None:
    applies = settings.eval(
        "function(s, side) return ANKIGTA.Settings.overrideAppliesTo("
        "s, {key = 'connectionPort', side = side, value = 1}) end"
    )

    assert applies("server", "server") is True
    assert applies("server", "client") is False
    assert applies("client", "server") is False


@pytest.mark.parametrize(
    ("key", "value", "reason"),
    [
        ("activationRadius", 3, "not_a_local_override"),
        ("connectionPort", 70000, "settings.error.out_of_range"),
        ("nothingLikeThis", 1, "unknown_setting"),
    ],
)
def test_only_a_valid_local_override_can_be_stamped(
    settings: MtaSandbox,
    key: str,
    value: Any,
    reason: str,
) -> None:
    refused, why = settings.eval(
        "function(s, k, v) return ANKIGTA.Settings.overrideBy(s, k, v) end"
    )("server", key, value)

    assert refused is False
    assert why == reason


def in_history(sandbox: MtaSandbox, key: str) -> Any:
    return sandbox.eval(
        "function(k) return ANKIGTA.Settings.inChangeHistory(k) end"
    )(key)


@pytest.mark.parametrize(
    "key",
    ["connectionPort", "connectionToken", "uiPlacement"],
)
def test_connection_and_ui_placement_stay_out_of_change_history(
    settings: MtaSandbox,
    key: str,
) -> None:
    assert in_history(settings, key) is False


def test_no_setting_another_side_owns_is_in_change_history(
    settings: MtaSandbox,
) -> None:
    """ADR 0028, derived rather than listed.

    Undo works by having the server rewrite what it holds, so a value that
    lives on the player's machine or in the add-on is not something it can put
    back. Reading it off authority is what stops a new client setting from
    silently arriving in the history because nobody remembered to exclude it.
    """
    schema = settings.eval("ANKIGTA.Settings.schema")

    for name in schema.keys():
        authority = settings.eval(
            "function(k) return ANKIGTA.Settings.authorityOf(k) end"
        )(str(name))
        if authority == "server":
            continue
        assert in_history(settings, str(name)) is False, name


@pytest.mark.parametrize(
    "key",
    ["activationRadius", "allowEarlyReview", "includeInStudy"],
)
def test_settings_the_server_owns_are_undoable(
    settings: MtaSandbox,
    key: str,
) -> None:
    assert in_history(settings, key) is True


# --- defaults ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("activationRadius", 3),
        ("activationDelaySeconds", 1),
        ("maxActivationSpeedKmh", 10000),
        ("allowEarlyReview", False),
        ("indicatorMode", "none"),
        ("reviewProtection", True),
        ("disablePlayerControls", True),
        ("closeAfterRating", True),
        ("cardAudioEnabled", True),
        ("muteGameWorld", False),
        ("uiScale", 1),
        ("language", "auto"),
    ],
)
def test_defaults_match_what_the_modules_already_ship(
    settings: MtaSandbox,
    key: str,
    expected: Any,
) -> None:
    assert settings.eval(
        "function(k) return ANKIGTA.Settings.default(k) end"
    )(key) == expected


def test_the_activation_module_takes_its_defaults_from_the_schema() -> None:
    """Asserting equality alone is tautological now that the module reads the
    schema, so change the schema and check the module actually follows."""
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        sandbox.eval(
            "function() ANKIGTA.Settings.schema.activationRadius.default = 12.5 end"
        )()
        sandbox.load("client/activation.lua")

        assert sandbox.eval("ANKIGTA.Activation.settings.defaultRadius") == 12.5
        assert sandbox.eval("ANKIGTA.Activation.radiusForNewEntity()") == 12.5
    finally:
        sandbox.close()


def test_the_indicator_takes_its_default_from_the_schema() -> None:
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        sandbox.eval(
            "function() ANKIGTA.Settings.schema.indicatorMode.default = "
            "'minimap_only' end"
        )()
        sandbox.load("client/indicator.lua")
        assert sandbox.eval("ANKIGTA.Indicator.mode") == "minimap_only"
    finally:
        sandbox.close()


def test_the_indicator_modes_match_the_schema(settings: MtaSandbox) -> None:
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        sandbox.load("client/indicator.lua")

        modes = sandbox.eval("ANKIGTA.Indicator.availableModes()")
        allowed = sandbox.eval(
            'ANKIGTA.Settings.schema.indicatorMode.rule.values'
        )
        assert {modes[k] for k in modes.keys()} == {
            allowed[k] for k in allowed.keys()
        }
    finally:
        sandbox.close()


# --- validation --------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "value", "reason"),
    [
        ("activationRadius", 200, "settings.error.out_of_range"),
        ("activationRadius", 0, "settings.error.out_of_range"),
        ("activationRadius", 1.3, "settings.error.not_on_step"),
        ("activationRadius", "wide", "settings.error.not_a_number"),
        ("activationDelaySeconds", -1, "settings.error.out_of_range"),
        ("activationDelaySeconds", 1.234, "settings.error.too_precise"),
        ("maxActivationSpeedKmh", -5, "settings.error.out_of_range"),
        ("indicatorMode", "sphere_only", "settings.error.not_a_choice"),
        ("allowEarlyReview", "yes", "settings.error.not_a_boolean"),
        ("uiScale", 10, "settings.error.out_of_range"),
    ],
)
def test_invalid_input_is_rejected_with_a_reason_never_clamped(
    settings: MtaSandbox,
    key: str,
    value: Any,
    reason: str,
) -> None:
    ok, why = validate(settings, key, value)

    assert ok is False
    assert why == reason


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("activationRadius", 0.5),
        ("activationRadius", 50),
        ("activationDelaySeconds", 0),
        ("activationDelaySeconds", 60),
        ("activationDelaySeconds", 12.34),
        ("maxActivationSpeedKmh", 0),
        ("indicatorMode", "minimap_only"),
        ("allowEarlyReview", True),
        ("uiScale", 0.5),
        ("uiScale", 2),
        # Story 54 allows two decimal places by hand; only the buttons move in
        # 0.05, and a validation step would reject this.
        ("uiScale", 1.23),
    ],
)
def test_values_at_the_boundaries_are_accepted(
    settings: MtaSandbox,
    key: str,
    value: Any,
) -> None:
    assert validate(settings, key, value) is True


def test_every_rejection_reason_has_a_translation(settings: MtaSandbox) -> None:
    """A reason the user cannot read is not a reason."""
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        sandbox.load("shared/locale.lua")
        for key, value in (
            ("activationRadius", 200),
            ("activationRadius", 1.3),
            ("activationRadius", "wide"),
            ("activationDelaySeconds", 1.234),
            ("indicatorMode", "sphere_only"),
            ("allowEarlyReview", "yes"),
            ("nonexistent", 1),
        ):
            _ok, reason = sandbox.eval(
                "function(k, v) return ANKIGTA.Settings.validate(k, v) end"
            )(key, value)
            for language in ("en", "ru"):
                sandbox.eval("function(l) ANKIGTA.Locale.setLanguage(l) end")(language)
                text = sandbox.eval("function(k) return ANKIGTA.Locale.text(k) end")(
                    reason
                )
                assert text != reason, f"{reason} untranslated in {language}"
    finally:
        sandbox.close()


# --- localization ------------------------------------------------------------


def test_english_is_the_default(locale: MtaSandbox) -> None:
    assert locale.eval("ANKIGTA.Locale.language") == "en"


@pytest.mark.parametrize("code", ["ru", "ru-RU", "RU", "ru_RU"])
def test_a_russian_windows_locale_selects_russian(
    locale: MtaSandbox,
    code: str,
) -> None:
    # getLocalization() returns {code, name} -- verified in
    # CLuaFunctionDefs::GetLocalization.
    detected = locale.eval(
        "function(c) return ANKIGTA.Locale.detect({code = c, name = 'x'}) end"
    )(code)

    assert detected == "ru"


@pytest.mark.parametrize("code", ["en-US", "de", "fr", "", "pl"])
def test_any_other_locale_selects_english(locale: MtaSandbox, code: str) -> None:
    detected = locale.eval(
        "function(c) return ANKIGTA.Locale.detect({code = c, name = 'x'}) end"
    )(code)

    assert detected == "en"


def test_language_switches_without_a_resource_restart(locale: MtaSandbox) -> None:
    before = locale.eval('ANKIGTA.Locale.text("settings.title")')
    assert before == "Settings"

    locale.eval('function() ANKIGTA.Locale.setLanguage("ru") end')()

    assert locale.eval('ANKIGTA.Locale.text("settings.title")') == "Настройки"
    locale.eval('function() ANKIGTA.Locale.setLanguage("en") end')()
    assert locale.eval('ANKIGTA.Locale.text("settings.title")') == "Settings"


def test_auto_follows_the_reported_locale(locale: MtaSandbox) -> None:
    ok, chosen = locale.eval(
        "function() return ANKIGTA.Locale.setLanguage("
        "'auto', {code = 'ru-RU', name = 'Russian'}) end"
    )()

    assert ok is True
    assert chosen == "ru"
    assert locale.eval('ANKIGTA.Locale.text("settings.title")') == "Настройки"


def test_both_languages_cover_the_same_keys(locale: MtaSandbox) -> None:
    english = locale.eval("ANKIGTA.Locale.strings.en")
    russian = locale.eval("ANKIGTA.Locale.strings.ru")

    assert set(english.keys()) == set(russian.keys())


def test_russian_strings_survive_the_round_trip_as_utf8(
    locale: MtaSandbox,
) -> None:
    """Read what the interpreter actually holds, not the file's bytes."""
    locale.eval('function() ANKIGTA.Locale.setLanguage("ru") end')()

    value = locale.eval('ANKIGTA.Locale.text("settings.title")')

    assert value == "Настройки"
    assert value.encode("utf-8").decode("utf-8") == value


def test_a_missing_translation_falls_back_to_english_and_logs(
    locale: MtaSandbox,
) -> None:
    locale.eval(
        'function() ANKIGTA.Locale.strings.ru["settings.title"] = nil end'
    )()
    locale.eval('function() ANKIGTA.Locale.setLanguage("ru") end')()

    assert locale.eval('ANKIGTA.Locale.text("settings.title")') == "Settings"
    assert any(
        "missing_translation" in line for line in locale.recorder.debug_messages()
    )


def test_a_key_missing_everywhere_shows_the_key_and_logs(
    locale: MtaSandbox,
) -> None:
    value = locale.eval('ANKIGTA.Locale.text("nothing.here")')

    # Visible gap beats a blank control nobody can diagnose.
    assert value == "nothing.here"
    assert any(
        "untranslated_key" in line for line in locale.recorder.debug_messages()
    )


def test_stored_technical_values_do_not_change_with_language(
    settings: MtaSandbox,
) -> None:
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        sandbox.load("shared/locale.lua")

        def snapshot() -> tuple[Any, ...]:
            return (
                sandbox.eval('ANKIGTA.Settings.default("indicatorMode")'),
                sandbox.eval('ANKIGTA.Settings.authorityOf("activationRadius")'),
                sandbox.eval('ANKIGTA.Settings.default("activationRadius")'),
            )

        sandbox.eval('function() ANKIGTA.Locale.setLanguage("en") end')()
        english = snapshot()
        sandbox.eval('function() ANKIGTA.Locale.setLanguage("ru") end')()

        assert snapshot() == english
    finally:
        sandbox.close()


def test_every_setting_has_an_authority_and_a_default_that_passes_its_own_rule(
    settings: MtaSandbox,
) -> None:
    """Derived from the schema, so a new setting cannot slip through untested."""
    schema = settings.eval("ANKIGTA.Settings.schema")
    names = list(schema.keys())
    assert len(names) > 10

    for name in names:
        authority = settings.eval(
            "function(k) return ANKIGTA.Settings.authorityOf(k) end"
        )(name)
        assert authority in {"server", "client", "addon"}, name

        definition = settings.eval(
            "function(k) return ANKIGTA.Settings.definition(k) end"
        )(name)
        if definition["optional"] is True:
            continue
        default = settings.eval(
            "function(k) return ANKIGTA.Settings.default(k) end"
        )(name)
        assert settings.eval(
            "function(k, v) return ANKIGTA.Settings.validate(k, v) end"
        )(name, default) is True, f"{name} default {default!r} fails its own rule"


def test_every_setting_is_writable_by_exactly_one_side_unless_local(
    settings: MtaSandbox,
) -> None:
    schema = settings.eval("ANKIGTA.Settings.schema")

    for name in schema.keys():
        writers = [
            side
            for side in ("server", "client", "addon")
            if settings.eval(
                "function(s, k) return ANKIGTA.Settings.canWrite(s, k) end"
            )(side, name)
            is True
        ]
        definition = settings.eval(
            "function(k) return ANKIGTA.Settings.definition(k) end"
        )(name)
        if definition["localOverride"] is True:
            assert set(writers) >= {"server", "client"}, name
        else:
            assert len(writers) == 1, f"{name} writable by {writers}"
