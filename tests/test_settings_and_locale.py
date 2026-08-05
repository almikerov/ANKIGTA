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
        # What a corona looks like is a property of the world every player
        # sees; whether the selected row's zone is drawn is one player's way
        # of looking.
        ("coronaColor", "server"),
        ("coronaOpacity", "server"),
        ("drawRadius", "client"),
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
    ["activationRadius", "reviewMode", "activationDelaySeconds"],
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


def test_panel_order_starts_with_ui_scale_then_the_companion_port(
    settings: MtaSandbox,
) -> None:
    """UI Scale is the one a player reaches for before any other: nothing on
    this panel can be read comfortably until the interface is a readable size,
    and on a list this long it was second from last, at the bottom of a scroll.

    The companion port keeps second place for the reason it had first --
    nothing else in the panel does anything until Anki is reachable.
    """
    ordered = settings.eval("function() return ANKIGTA.Settings.orderedKeys() end")()

    assert ordered[1] == "uiScale"
    assert ordered[2] == "connectionPort"


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
# The rule shipped with ticket 03, which built the picker that chooses one, and
# was exercised against a schema entry the test invented because nothing in the
# schema was a colour yet. Ticket 04 added the first real one, so these ask the
# shipped setting instead.


@pytest.mark.parametrize(
    "value",
    ["#000000", "#ffffff", "#38bdf8", "#FFAA00"],
)
def test_a_colour_is_accepted_as_six_hex_digits(
    settings: MtaSandbox, value: str
) -> None:
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
    ok, why = validate(settings, "coronaColor", value)

    assert ok is False
    assert why == "settings.error.not_a_color"


def test_a_colour_is_stored_under_one_spelling(settings: MtaSandbox) -> None:
    """`#FFAA00` and `#ffaa00` compared as text are two stored values for one
    colour, which is a comparison that starts reporting changes nobody made."""
    normalized = settings.eval(
        "function(k, v) return ANKIGTA.Settings.normalize(k, v) end"
    )("coronaColor", "#FFAA00")

    assert normalized == "#ffaa00"


def test_the_shipped_corona_colour_is_a_colour_by_its_own_rule(
    settings: MtaSandbox,
) -> None:
    """A default that fails the rule is a resource that ships unusable."""
    shipped = settings.eval(
        "function() return ANKIGTA.Settings.default('coronaColor') end"
    )()

    assert validate(settings, "coronaColor", shipped) is True


def test_a_colour_is_read_as_the_channels_it_is_drawn_in(
    settings: MtaSandbox,
) -> None:
    """One reader of the format, beside the rule that decides it."""
    channels = settings.eval(
        "function(v) return ANKIGTA.Settings.colorChannels(v) end"
    )

    assert tuple(channels("#3cc8ff")) == (0x3C, 0xC8, 0xFF)
    assert tuple(channels("#000000")) == (0, 0, 0)


@pytest.mark.parametrize(
    "value", ["#3cc8f", "3cc8ff", "rebeccapurple", "", 0, True, None]
)
def test_a_colour_the_rule_would_refuse_has_no_channels_at_all(
    settings: MtaSandbox, value: Any
) -> None:
    """`nil` rather than three zeroes: whatever draws with this has to be able
    to fall back, and black is a colour somebody could have chosen."""
    assert settings.eval(
        "function(v) return ANKIGTA.Settings.colorChannels(v) end"
    )(value) is None


def test_corona_opacity_ships_at_six_tenths(settings: MtaSandbox) -> None:
    """The number the ticket states. It is also the number a value stored by a
    schema that no longer exists must not quietly outrank -- which is
    `test_migrations.py`'s to hold, because only the store can."""
    assert settings.eval(
        "function() return ANKIGTA.Settings.default('coronaOpacity') end"
    )() == 0.6
    assert validate(settings, "coronaOpacity", 0.6) is True
    assert validate(settings, "coronaOpacity", 1.4)[0] is False
    assert validate(settings, "coronaOpacity", -0.1)[0] is False


def test_drawing_the_selected_zone_is_off_until_the_player_asks(
    settings: MtaSandbox,
) -> None:
    """A way of looking is nobody's default: a zone drawn around whatever row
    happens to be selected is a line across the world nobody asked for."""
    assert settings.eval(
        "function() return ANKIGTA.Settings.default('drawRadius') end"
    )() is False


# --- which surface a setting is offered on -----------------------------------


def test_drawing_the_selected_zone_is_offered_beside_show_corona(
    settings: MtaSandbox,
) -> None:
    """`Draw radius` and `Show corona` answer one question between them -- "what
    do I see around this row" -- and both are reached while a row is selected.
    So it names the surface it belongs to, and is not a row in Settings nor a
    line in the order they are laid out in.
    """
    assert settings.eval(
        "function() return ANKIGTA.Settings.shownWith('drawRadius') end"
    )() == "entity"
    order = settings.eval("ANKIGTA.Settings.order")
    assert "drawRadius" not in {str(order[index]) for index in order.keys()}
    ordered = settings.eval("function() return ANKIGTA.Settings.orderedKeys() end")()
    assert "drawRadius" not in {
        str(ordered[index]) for index in ordered.keys()
    }


def test_a_setting_that_names_no_surface_belongs_to_settings(
    settings: MtaSandbox,
) -> None:
    """Otherwise every setting would have to remember to say so, and the one
    that forgot would be the one nobody could reach."""
    for key in ("uiScale", "coronaOpacity", "indicatorMode"):
        assert settings.eval(
            "function(k) return ANKIGTA.Settings.shownWith(k) end"
        )(key) == "settings", key


def test_a_setting_the_settings_list_does_not_show_is_left_out_of_its_order(
    settings: MtaSandbox,
) -> None:
    """`orderedKeys` appends a setting missing from `Settings.order` so that
    forgetting to lay one out cannot hide it. A setting shown on another surface
    is not that mistake -- it is reachable and named -- so it is left out rather
    than appended to a list it does not belong to."""
    settings.eval(
        """
        function()
            ANKIGTA.Settings.schema.somewhereElse =
                {authority = "client", default = false,
                 rule = {kind = "boolean"}, shownWith = "entity"}
            ANKIGTA.Settings.schema.forgotten =
                {authority = "client", default = false,
                 rule = {kind = "boolean"}}
        end
        """
    )()
    ordered = settings.eval("function() return ANKIGTA.Settings.orderedKeys() end")()
    keys = {str(ordered[index]) for index in ordered.keys()}

    assert "forgotten" in keys
    assert "somewhereElse" not in keys


def test_the_map_toggle_is_the_players_own_and_off_until_asked_for(
    settings: MtaSandbox,
) -> None:
    """A world with hundreds of entities is a map with hundreds of blips, so
    nobody gets one they did not ask for. And it is a toggle of its own rather
    than a fourth value of `indicatorMode`: that setting answers "how is the
    next card marked" about one entity, this one answers "is the rest of the
    world marked at all".
    """
    assert can_write(settings, "client", "showEntitiesOnMap") is True
    assert can_write(settings, "server", "showEntitiesOnMap") is not True
    assert settings.eval(
        "function() return ANKIGTA.Settings.default('showEntitiesOnMap') end"
    )() is False
    modes = settings.eval("ANKIGTA.Settings.schema.indicatorMode.rule.values")
    assert "showEntitiesOnMap" not in {
        str(modes[index]) for index in modes.keys()
    }


# --- a number is put back to the precision its rule declares -----------------


def test_a_value_off_the_wire_is_read_at_the_precision_its_rule_declares(
    settings: MtaSandbox,
) -> None:
    """Measured on the owner's running server: every server-to-client hop packs
    a non-integer Lua number into a 32-bit float, so a stored `0.6` arrives as
    `0.60000001999999997` and is read as `0.60000002`.
    """
    rounded = settings.eval(
        "function(k, v) return ANKIGTA.Settings.rounded(k, v) end"
    )

    assert rounded("coronaOpacity", 0.60000001999999997) == 0.6
    assert rounded("coronaOpacity", 0.55000000999999998) == 0.55
    # And a value that never lost anything is handed straight back.
    assert rounded("coronaOpacity", 0.25) == 0.25


def test_only_a_rule_that_declares_a_precision_gets_one_applied(
    settings: MtaSandbox,
) -> None:
    """A rule with no `decimals` declares none, and none of them needs one:
    those settings step in whole or half units, and both are exact on the wire.
    Rounding them anyway would be this function inventing a rule.
    """
    rounded = settings.eval(
        "function(k, v) return ANKIGTA.Settings.rounded(k, v) end"
    )

    assert rounded("activationRadius", 7.5) == 7.5
    assert rounded("connectionPort", 40001) == 40001
    # Not a number and not a numeric setting: handed back untouched rather than
    # turned into one.
    assert rounded("coronaColor", "#3cc8ff") == "#3cc8ff"
    assert rounded("coronaOpacity", False) is False
    assert rounded("nothing at all", 0.6) == 0.6


def test_every_numeric_setting_declares_a_precision_or_steps_exactly(
    settings: MtaSandbox,
) -> None:
    """The invariant behind the rule above, over the whole schema rather than
    over the settings the tail was noticed on.

    A numeric setting either says how many decimals it has -- and is put back to
    them -- or steps in units a 32-bit float holds exactly. A third kind would
    be a setting that can arrive with a tail and has nothing to be put back to.
    """
    numeric = settings.eval(
        """
        function()
            local found = {}
            for key, definition in pairs(ANKIGTA.Settings.schema) do
                if definition.rule.kind == "number" then
                    found[key] = definition.rule
                end
            end
            return found
        end
        """
    )()

    assert len(list(numeric.keys())) > 0
    for key in numeric.keys():
        rule = numeric[key]
        if rule["decimals"]:
            continue
        step = rule["step"]
        assert step is not None, f"{key} declares neither decimals nor a step"
        # Exact in single precision: a whole number, or a fraction whose
        # denominator is a power of two.
        assert (float(step) * 2) % 1 == 0, f"{key} steps by {step}"


def test_a_choice_stored_under_the_name_it_used_to_have_is_still_that_choice(
    settings: MtaSandbox,
) -> None:
    """`sphere_and_minimap` named a shape nothing ever drew -- what stands over
    the next card is a beam, and the sphere is the Activation Zone.

    A stored setting is the player's answer, so the rename carries: the old word
    validates, and normalizing puts it into the one the rule offers today.
    """
    assert validate(settings, "indicatorMode", "sphere_and_minimap") is True
    assert settings.eval(
        "function(k, v) return ANKIGTA.Settings.normalize(k, v) end"
    )("indicatorMode", "sphere_and_minimap") == "beam_and_minimap"
    # The list a player is offered holds only the name it is called now.
    values = settings.eval("ANKIGTA.Settings.schema.indicatorMode.rule.values")
    assert "sphere_and_minimap" not in {
        str(values[index]) for index in values.keys()
    }
    # And a word that was never one of the choices is still refused.
    assert validate(settings, "indicatorMode", "sphere_only")[0] is False


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
