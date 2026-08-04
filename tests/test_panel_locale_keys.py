"""Every string the panel can put on screen must exist in the locale table.

The panel's `t()` falls back to the key itself, so a missing string does not
fail loudly -- it renders as `settings.title` where the word "Settings" should
be. That is invisible to every existing test, because no test renders the page.

This one reads the keys straight out of the page and the schema, and checks
them against `shared/locale.lua`. It is the seam the CEF checklist cannot be.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PANEL = REPO / "mta" / "ankigta" / "client" / "panel"
LOCALE_LUA = REPO / "mta" / "ankigta" / "shared" / "locale.lua"
PANEL_LUA = REPO / "mta" / "ankigta" / "client" / "panel.lua"
SETTINGS_LUA = REPO / "mta" / "ankigta" / "shared" / "settings.lua"


def locale_tables() -> dict[str, set[str]]:
    """The keys each language defines, read out of the Lua source.

    Parsed rather than executed: there is no Lua runtime in this suite, and the
    table is a flat literal, so a regex over each language's block is honest.
    """
    source = LOCALE_LUA.read_text(encoding="utf-8")
    tables: dict[str, set[str]] = {}
    # Each language opens with `    en = {` at one indent inside `Locale.strings`.
    for match in re.finditer(r"\n    (\w+) = \{\n", source):
        language = match.group(1)
        start = match.end()
        depth = 1
        index = start
        while index < len(source) and depth > 0:
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
            index += 1
        block = source[start:index]
        tables[language] = set(re.findall(r'\["([^"]+)"\]\s*=', block))
    return tables


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


def test_the_panel_names_keys_the_locale_table_defines() -> None:
    """No label may render as its own key.

    English is the fallback, so a key absent here is a key the player reads as
    `f7.pickEntity` on a button.
    """
    english = locale_tables()["en"]
    missing = sorted(key for key in all_panel_keys() if key not in english)
    assert not missing, (
        "the panel renders these as raw keys, because `en` does not define "
        f"them:\n  " + "\n  ".join(missing)
    )


def test_every_panel_key_is_translated_too() -> None:
    """A gap in Russian is a bug to fix, not something to hide (locale.lua)."""
    tables = locale_tables()
    english = tables["en"]
    for language, defined in tables.items():
        if language == "en":
            continue
        missing = sorted(
            key for key in all_panel_keys() if key in english and key not in defined
        )
        assert not missing, (
            f"`{language}` falls back to English for panel strings:\n  "
            + "\n  ".join(missing)
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
