"""Every string the panel can put on screen must exist in the locale table.

The panel's `t()` falls back to the key itself, so a missing string does not
fail loudly -- it renders as `settings.title` where the word "Settings" should
be. That is invisible to every existing test, because no test renders the page.

This one reads the keys straight out of the page and the schema, and checks
them against the table `shared/locale.lua` loads. It is the seam the CEF
checklist cannot be. `tests/test_localization.py` does the same for the keys
the Lua side names; between them, every key anything asks for is checked.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_localization import locale_keys

REPO = Path(__file__).resolve().parent.parent
PANEL = REPO / "mta" / "ankigta" / "client" / "panel"
PANEL_LUA = REPO / "mta" / "ankigta" / "client" / "panel.lua"
SETTINGS_LUA = REPO / "mta" / "ankigta" / "shared" / "settings.lua"


def html_keys() -> set[str]:
    source = (PANEL / "index.html").read_text(encoding="utf-8")
    keys = set(re.findall(r'data-i18n="([^"]+)"', source))
    keys |= set(re.findall(r'data-i18n-placeholder="([^"]+)"', source))
    return keys


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

    # `runtimeStatusKey` returns these three, whole.
    panel = PANEL_LUA.read_text(encoding="utf-8")
    keys |= set(re.findall(r'return "(f7\.runtime\.[^"]+)"', panel))

    # The connection line: two fixed states, plus whatever category the
    # gateway reports.
    keys |= {"connection.status.connected", "connection.status.connecting",
             "connection.status.disconnected"}

    # One label per setting the schema defines, because the rows are derived
    # from the schema rather than listed in the page.
    settings = SETTINGS_LUA.read_text(encoding="utf-8")
    for key in re.findall(r'\n    (\w+) = \{\n\s+authority', settings):
        keys.add("settings." + key)

    # And one per value a choice offers, for the same reason: the options come
    # from the schema at runtime, so a value added there with no string behind
    # it renders in the dropdown as `settings.value.allow_due`.
    for values in re.findall(r"rule = choice\(\{([^}]*)\}\)", settings):
        for value in re.findall(r'"([^"]+)"', values):
            keys.add("settings.value." + value)

    # Booleans render their value as a word.
    keys |= {"settings.value.true", "settings.value.false"}
    return keys


def panel_lua_keys() -> set[str]:
    """Keys the Lua side names for the page to translate."""
    source = PANEL_LUA.read_text(encoding="utf-8")
    keys = set(re.findall(r'key = "([a-z][\w]*\.[\w.]+)"', source))
    keys |= set(re.findall(r'format\(\s*\n?\s*"([\w]+\.[\w.]+)"', source))
    keys |= set(re.findall(r'"(notice\.[\w.]+)"', source))
    return {key for key in keys if "." in key}


def all_panel_keys() -> set[str]:
    return html_keys() | js_literal_keys() | js_prefixed_keys() | panel_lua_keys()


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
