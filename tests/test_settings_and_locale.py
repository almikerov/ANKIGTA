"""Ticket 27 — settings authority, and the string table behind their labels.

Two rules do most of the work. A side may only write what it owns (ADR 0014),
and bad input is rejected with a reason rather than quietly clamped — a
mistyped 200 turned into 50 leaves the user with a setting they never chose.
The reason has to be readable, which is where the string table comes in;
ticket 01 left one table and no language to pick it with.
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
        ("reviewMode", "server"),
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


def test_change_history_covers_exactly_what_the_server_owns(
    settings: MtaSandbox,
) -> None:
    """ADR 0028, derived from the schema rather than listed here.

    Undo works by having the server rewrite what it holds, so a value living on
    the player's machine or in the add-on is not something it can put back.
    Reading membership off authority in both directions is what stops a new
    client setting from arriving as undoable while nothing records it, and a new
    server setting from quietly falling out of the history.
    """
    authority_of = settings.eval(
        "function(k) return ANKIGTA.Settings.authorityOf(k) end"
    )

    keys = [str(key) for key in settings.eval("ANKIGTA.Settings.schema").keys()]
    assert len(keys) > 1
    for key in keys:
        assert in_history(settings, key) is (authority_of(key) == "server"), key


@pytest.mark.parametrize(
    "key",
    ["activationRadius", "reviewMode", "includeInStudy"],
)
def test_settings_the_server_owns_are_undoable(
    settings: MtaSandbox,
    key: str,
) -> None:
    assert in_history(settings, key) is True


@pytest.mark.parametrize(
    "key",
    ["connectionPort", "connectionToken", "uiPlacement", "indicatorMode", "uiScale"],
)
def test_settings_the_server_does_not_own_stay_out_of_change_history(
    settings: MtaSandbox,
    key: str,
) -> None:
    """The player's machine keeps these in its own file. They persist across a
    restart -- see the client store's restart test -- but the server's history
    is not where that persistence lives, and undo has no way to reach them."""
    assert in_history(settings, key) is False


def test_a_server_setting_can_still_be_excluded_from_history(
    settings: MtaSandbox,
) -> None:
    """Authority is the rule, not the whole story: a server setting that should
    not be journalled can still say so, and is believed."""
    settings.eval(
        "function() ANKIGTA.Settings.schema.activationRadius.excludedFromHistory"
        " = true end"
    )()

    assert in_history(settings, "activationRadius") is False


# --- defaults ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("activationRadius", 3),
        ("activationDelaySeconds", 0),
        ("maxActivationSpeedKmh", 0),
        ("reviewMode", "allow_due"),
        ("indicatorMode", "none"),
        ("reviewProtection", True),
        ("disablePlayerControls", True),
        ("closeAfterRating", True),
        ("cardAudioEnabled", True),
        ("muteGameWorld", False),
        ("uiScale", 1),
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


def test_panel_order_starts_with_the_companion_port(
    settings: MtaSandbox,
) -> None:
    """Nothing else in the panel does anything until Anki is reachable."""
    ordered = settings.eval("function() return ANKIGTA.Settings.orderedKeys() end")()

    assert ordered[1] == "connectionPort"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("f7.filter", "Search Map Entity"),
        ("f7.filterApply", "Search"),
        ("common.close", "X"),
        ("settings.close", "X"),
        ("f7.teleport", "Teleport"),
        ("settings.muteGameWorld", "Mute world while reviewing"),
        ("settings.closeAfterRating", "Close cards after rating"),
        ("settings.maxActivationSpeedKmh", "Open cards when speed lower than:"),
    ],
)
def test_panel_words_say_what_the_controls_do(
    locale: MtaSandbox,
    key: str,
    expected: str,
) -> None:
    assert locale.eval("function(value) return ANKIGTA.Locale.text(value) end")(
        key
    ) == expected


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
        ("reviewMode", "allow_early", "settings.error.not_a_choice"),
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
        ("reviewMode", "allow_all"),
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


def test_every_rejection_reason_has_words_behind_it(settings: MtaSandbox) -> None:
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
            ("reviewMode", "allow_early"),
            ("nonexistent", 1),
        ):
            _ok, reason = sandbox.eval(
                "function(k, v) return ANKIGTA.Settings.validate(k, v) end"
            )(key, value)
            text = sandbox.eval("function(k) return ANKIGTA.Locale.text(k) end")(
                reason
            )
            assert text != reason, f"{reason} has no words behind it"
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


# --- a colour is a value the schema knows about ------------------------------
#
# Nothing in the schema is a colour yet: tickets 04 and 06 each add one. The
# rule ships here because the picker that chooses one does, and because a rule
# added alongside its first setting would be a rule written twice. Until then
# it is exercised against a schema entry the test adds, which is exactly what
# those tickets will add for real.


def with_a_colour(sandbox: MtaSandbox, **definition: Any) -> None:
    sandbox.eval(
        """
        function(key, default)
            ANKIGTA.Settings.schema[key] = {
                authority = ANKIGTA.Settings.SERVER,
                default = default,
                rule = {kind = "color"},
            }
        end
        """
    )(definition["key"], definition["default"])


@pytest.mark.parametrize(
    "value",
    ["#000000", "#ffffff", "#38bdf8", "#FFAA00"],
)
def test_a_colour_is_accepted_as_six_hex_digits(
    settings: MtaSandbox, value: str
) -> None:
    with_a_colour(settings, key="coronaColor", default="#38bdf8")

    assert validate(settings, "coronaColor", value) is True


@pytest.mark.parametrize(
    "value",
    ["#38bdf", "38bdf8", "#38bdf8f", "#3z3z3z", "rebeccapurple", 16711680, ""],
)
def test_anything_that_is_not_a_colour_is_refused_with_a_reason(
    settings: MtaSandbox, value: Any
) -> None:
    """Half a hex code is not a colour, and a control that quietly picks black
    on a typo is worse than one that says no."""
    with_a_colour(settings, key="coronaColor", default="#38bdf8")

    ok, why = validate(settings, "coronaColor", value)

    assert ok is False
    assert why == "settings.error.not_a_color"


def test_a_colour_is_stored_under_one_spelling(settings: MtaSandbox) -> None:
    """`#FFAA00` and `#ffaa00` compared as text are two stored values for one
    colour, which is a comparison that starts reporting changes nobody made."""
    with_a_colour(settings, key="coronaColor", default="#38bdf8")

    normalized = settings.eval(
        "function(k, v) return ANKIGTA.Settings.normalize(k, v) end"
    )("coronaColor", "#FFAA00")

    assert normalized == "#ffaa00"


def test_the_reason_a_colour_is_refused_has_words_behind_it(
    locale: MtaSandbox,
) -> None:
    """A reason the user cannot read is not a reason."""
    words = locale.eval(
        "function(k) return ANKIGTA.Locale.text(k) end"
    )("settings.error.not_a_color")

    assert words != "settings.error.not_a_color"


def test_the_camera_setting_belongs_to_the_player_and_is_on_by_default(
    settings: MtaSandbox,
) -> None:
    """Selecting a row and looking at it are the same intention almost every
    time, and where one player's camera goes is one player's machine's answer.
    """
    assert can_write(settings, "client", "focusOnSelect") is True
    assert can_write(settings, "server", "focusOnSelect") is not True
    assert settings.eval(
        "function() return ANKIGTA.Settings.default('focusOnSelect') end"
    )() is True
