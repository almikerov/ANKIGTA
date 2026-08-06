"""Every string the panel can put on screen must exist in the locale table.

The panel's `t()` falls back to the key itself, so a missing string does not
fail loudly -- it renders as `settings.title` where the word "Settings" should
be. That is invisible to every existing test, because no test renders the page.

This one reads the keys straight out of the page and the schema, and checks
them against the table `shared/locale.lua` loads. It is the seam the CEF
checklist cannot be. `tests/test_localization.py` does the same for the keys
the Lua side names; between them, every key anything asks for is checked.

The loop closes the other way too: a string nothing looks up reaches no
surface, and `NOT_YET_RENDERED` below names the 65 in that state today --
labels of the CEGUI windows the panel replaced. That list may only shrink, so
a string added from here on has to have somewhere to go.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.lua.constants import string_constants
from tests.lua.strings import (
    LOCALE,
    key_prefixes,
    locale_keys,
    named_keys,
    resource_scripts,
    schema_choices,
    schema_labels,
)

REPO = Path(__file__).resolve().parent.parent
PANEL = REPO / "mta" / "ankigta" / "client" / "panel"
PANEL_LUA = REPO / "mta" / "ankigta" / "client" / "panel.lua"


def html_keys() -> set[str]:
    """Every key the markup names, whichever part of a control it fills.

    Read as one family rather than one attribute at a time: `applyLocale` walks
    `data-i18n`, `data-i18n-placeholder` and `data-i18n-title`, and a fourth
    added there with no line added here would leave its strings looking like
    words nothing asks for.
    """
    source = (PANEL / "index.html").read_text(encoding="utf-8")
    return set(re.findall(r'data-i18n(?:-[a-z]+)?="([^"]+)"', source))


def js_literal_keys() -> set[str]:
    """`t("...")` with a literal argument, as written in the view.

    Anchored so `createElement("select")` is not read as a call to `t`.
    """
    source = (PANEL / "app.js").read_text(encoding="utf-8")
    return set(re.findall(r'(?<![\w.])t\("([^"]+)"\)', source))


def js_prefixed_keys() -> set[str]:
    """The keys the view builds by concatenation, expanded from their sources.

    Each is `t("prefix." + value)` where the values are enumerated somewhere in
    this repo -- the tone table, the settings schema, the Lua side's runtime
    status. Expanded here so a state that never appears in a screenshot is
    still covered.
    """
    keys: set[str] = set()

    js = (PANEL / "app.js").read_text(encoding="utf-8")
    # `TONES` names every link state the panel can be handed.
    tones = re.search(r"var TONES = \{(.*?)\n  \};", js, re.S)
    assert tones, "TONES table not found in app.js"
    for state in re.findall(r'"([^"]+)":', tones.group(1)):
        keys.add("f7.linkState." + state)

    # `runtimeStatusKey` returns these whole, so the chunk holds them entire.
    keys |= {
        value
        for value in string_constants(PANEL_LUA)
        if value.startswith("f7.runtime.")
    }

    # The connection line: two fixed states, plus whatever category the
    # gateway reports.
    keys |= {"connection.status.connected", "connection.status.connecting",
             "connection.status.disconnected"}

    # One label per setting the schema defines, and one per value a choice
    # offers, because the rows and their dropdowns are derived from the schema
    # rather than listed in the page.
    keys |= set(schema_labels()) | set(schema_choices())

    # Booleans render their value as a word.
    keys |= {"settings.value.true", "settings.value.false"}
    return keys


def all_panel_keys() -> set[str]:
    """What the page can ask the table for.

    The Lua side's own keys are not here: `named_keys` in
    `tests/test_localization.py` reads those out of the compiled chunk, which
    is the same job done without grepping the file.
    """
    return html_keys() | js_literal_keys() | js_prefixed_keys()


def test_the_panel_names_keys_the_string_table_defines() -> None:
    """No label may render as its own key.

    There is no second table to fall back to, so a key absent here is a key the
    player reads as `f7.pickEntity` on a button.
    """
    defined = locale_keys()
    missing = sorted(key for key in all_panel_keys() if key not in defined)
    assert not missing, (
        "the panel renders these as raw keys, because shared/locale.lua does "
        f"not define them:\n  " + "\n  ".join(missing)
    )


#: Strings in the table that nothing looks up yet, and so reach no surface.
#:
#: Every one is a label from a CEGUI window the CEF panel replaced. They are
#: listed rather than deleted because panel-rebuild tickets 03 (settings rows
#: and dropdowns) and 05 (study) rebuild the surfaces that want many of them,
#: and deleting them here would only mean typing them back there.
#:
#: This list may only shrink. A ticket that wires one up removes its line; a
#: ticket that decides a surface is gone for good deletes the string and the
#: line together. Nothing may be added: a string added from now on has to have
#: somewhere to go.
NOT_YET_RENDERED = frozenset({
    "cardPicker.alreadyLinked",
    "cardPicker.column.collection",
    "cardPicker.column.deck",
    "cardPicker.column.state",
    "cardPicker.previewReplacement",
    "cardPicker.replaceTitle",
    "common.confirm",
    "common.no",
    "common.yes",
    "connection.advanced",
    "connection.automaticMode",
    "connection.clearTokenFirst",
    "connection.connect",
    "connection.currentMode",
    "connection.disableToken",
    "connection.disconnected",
    "connection.dismissWarning",
    "connection.manualMode",
    "connection.manualPort",
    "connection.replacementToken",
    "connection.settingsTitle",
    "connection.title",
    "connection.tokenDisabled",
    "connection.tokenProtected",
    "f7.authoredPosition",
    "f7.cardIdentity",
    "f7.cardLabel",
    "f7.cardPicker",
    "f7.column.authored",
    "f7.column.link",
    "f7.column.mapEntity",
    "f7.column.runtime",
    "f7.column.type",
    "f7.entityLabel",
    "f7.metadataSummary",
    "f7.relink.chooseTarget",
    "f7.relink.metadataMoved",
    "f7.relink.missing",
    "f7.relink.pickTarget",
    "f7.relink.target",
    "f7.relink.title",
    "f7.replace.confirm",
    "f7.replace.explanation",
    "f7.replace.newCard",
    "f7.replace.oldCard",
    "f7.replace.title",
    "f7.unlink.confirm",
    "f7.unlink.explanation",
    "f7.unlink.title",
    "inspector.close",
    "panel.connection.explain",
    "panel.title",
    "study.cancelRebuild",
    "study.disconnected",
    "study.pause",
    "study.rebuild",
    "study.stop",
    "study.title",
    "ui.editHudExplanation",
    "ui.larger",
    "ui.smaller",
})


def unrendered_strings() -> set[str]:
    """Table strings no script and no part of the page ever asks for.

    "Asks for" spans both sides: a Lua constant shaped like a key, read out of
    the compiled chunk; a `data-i18n` or `t("...")` on the page; the families
    the schema and the tone table complete; and the open-ended families a
    script builds at runtime, such as `"connection.status." .. category`.

    The string table itself is not an asker. Its own keys are constants in its
    own chunk, so counting them would make every string its own caller.
    """
    asked = set(all_panel_keys())
    for script in resource_scripts():
        if script.resolve() == LOCALE.resolve():
            continue
        asked |= named_keys(script)

    prefixes = tuple(key_prefixes())
    return {
        key
        for key in locale_keys()
        if key not in asked and not key.startswith(prefixes)
    }


def test_a_string_no_surface_can_reach_is_one_nothing_asks_for() -> None:
    """The loop closed the other way, against a list that may only shrink.

    The guards above catch a key with no words behind it. This one catches the
    reverse -- words with no key asking for them, which no control is ever
    given. Both directions matter, and only this one can see a label left
    behind by a window that no longer exists.
    """
    new = sorted(unrendered_strings() - NOT_YET_RENDERED)

    assert new == [], (
        "shared/locale.lua gained strings nothing looks up, so no surface can "
        f"render them:\n  " + "\n  ".join(new)
    )


def test_the_backlog_of_unrendered_strings_never_grows_stale() -> None:
    """A name on the list that is no longer unrendered is a line to delete.

    Without this the list would be a place to put a string and forget it: a
    ticket could wire one up, leave its line behind, and the guard above would
    keep excusing a name that no longer needs excusing.
    """
    stale = sorted(NOT_YET_RENDERED - unrendered_strings())

    assert stale == [], (
        "these are rendered now, or gone from the table; drop them from "
        f"NOT_YET_RENDERED:\n  " + "\n  ".join(stale)
    )


def test_the_page_reaches_every_element_it_binds() -> None:
    """A click handler bound to a missing id throws and kills the rest.

    `app.js` binds its handlers at the end of one IIFE with no try/catch, so
    the first `getElementById(...)` that returns null throws a TypeError and
    every later binding -- and `window.ANKIGTA = {receive}` -- never happens.
    That is a blank, dead panel, and no existing test would see it.
    """
    html = (PANEL / "index.html").read_text(encoding="utf-8")
    js = (PANEL / "app.js").read_text(encoding="utf-8")
    present = set(re.findall(r'\sid="([^"]+)"', html))

    wanted = set(re.findall(r'getElementById\("([^"]+)"\)', js))
    simple = re.search(r"var SIMPLE = \{(.*?)\n  \};", js, re.S)
    assert simple, "SIMPLE table not found in app.js"
    wanted |= set(re.findall(r'"([^"]+)":', simple.group(1)))

    missing = sorted(wanted - present)
    assert not missing, (
        "app.js reaches for ids the page does not define, which throws before "
        f"`window.ANKIGTA` is ever set:\n  " + "\n  ".join(missing)
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
