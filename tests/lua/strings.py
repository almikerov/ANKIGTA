"""What the string table holds, and what a chunk asks it for.

Both are read out of the loaded resource rather than out of the source text:
`docs/agents/lua-testing.md` says a grep sees comments, misses strings built by
concatenation, and breaks on reformatting. The table is a Lua chunk, so it is
loaded and its keys read back; a script's keys are constants in its compiled
chunk, so they come from `constants.py`.

`tests/test_localization.py` uses these for the Lua side and
`tests/test_panel_locale_keys.py` for the page. They live here rather than in
either so neither has to import the other's test module to get at them.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from tests.lua.constants import string_constants
from tests.lua.sandbox import MtaSandbox


RESOURCE = Path(__file__).resolve().parents[2] / "mta" / "ankigta"
LOCALE = RESOURCE / "shared" / "locale.lua"

#: What a key looks like: dotted lower-camel segments, no leading digit, no
#: colon, and never left open at the end.
KEY_SHAPE = re.compile(r"^[a-z][A-Za-z0-9]*(\.[A-Za-z][A-Za-z0-9_ ]*)+$")
#: The same shape left open at the end: half of a key a script completes at
#: runtime -- `"connection.status." .. category`. What completes it is a
#: technical value from the server, so the family is open-ended by design.
PREFIX_SHAPE = re.compile(r"^[a-z][A-Za-z0-9]*(\.[A-Za-z][A-Za-z0-9_]*)*\.$")
#: A dotted constant that is a file on disk rather than a key in the table.
FILE_SUFFIXES = (
    ".json", ".lua", ".html", ".js", ".css", ".xml", ".map", ".tmp", ".sqlite",
)


def resource_scripts() -> list[Path]:
    """Every Lua script the resource ships, in a stable order."""
    return sorted(RESOURCE.glob("**/*.lua"))


@cache
def locale_keys() -> frozenset[str]:
    """Every key the table defines, read out of the loaded chunk."""
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/locale.lua")
        return frozenset(
            str(key) for key in sandbox.eval("ANKIGTA.Locale.strings").keys()
        )
    finally:
        sandbox.close()


def named_keys(script: Path) -> set[str]:
    """The keys a script asks the table for, as its chunk holds them.

    A key is recognised by its shape rather than by its first segment. Reading
    the family off the table would only ever find a family that already exists,
    and the string a later ticket forgets is most likely the first one of a new
    family -- exactly the case this has to catch.

    Two shapes match by accident and are named here rather than guessed at: a
    filename, and an MTA ACL right. A constant left open at the end is half of
    a key the script builds at runtime; those are `key_prefixes`.
    """
    return {
        value
        for value in string_constants(script)
        if KEY_SHAPE.match(value)
        and not value.endswith(FILE_SUFFIXES)
        and not value.startswith("resource.")
    }


@cache
def key_prefixes() -> frozenset[str]:
    """Every open-ended family a script completes at runtime.

    Read off the chunks rather than listed here, so a new family is picked up
    by whoever adds it rather than by whoever remembers a list. The string
    table is skipped: its own keys are constants in its own chunk, and one
    ending in a dot would open a family nothing actually builds.
    """
    prefixes: set[str] = set()
    for script in resource_scripts():
        if script.resolve() == LOCALE.resolve():
            continue
        prefixes |= {
            value
            for value in string_constants(script)
            if PREFIX_SHAPE.match(value)
        }
    return frozenset(prefixes)


@cache
def schema_labels() -> frozenset[str]:
    """One `settings.<key>` per setting the Settings list draws a row for.

    The settings rows are derived from the schema at runtime, so a setting
    added with no label behind it renders as `settings.uiScale` on its row.
    Out of the chunk rather than the file: the regex this replaced wanted
    `authority` on the line after the key and missed the eight settings written
    on one line, `uiScale` among them.

    A setting the schema places on another surface is not one of these. Its
    label is that surface's -- `f7.drawRadius` is a `data-i18n` on the entity
    pane -- and asking for `settings.drawRadius` here would demand a string for
    a row that no longer exists.
    """
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        keys = sandbox.eval("ANKIGTA.Settings.orderedKeys()")
        return frozenset("settings." + str(keys[index]) for index in keys.keys())
    finally:
        sandbox.close()


@cache
def schema_choices() -> frozenset[str]:
    """One `settings.value.<value>` per option a choice setting offers.

    Same reason as the labels: the dropdown is built from the schema, so a
    value added there with no words behind it renders as its own name.
    """
    sandbox = MtaSandbox()
    try:
        sandbox.load("shared/settings.lua")
        schema = sandbox.eval("ANKIGTA.Settings.schema")
        options = set()
        for key in schema.keys():
            rule = schema[key]["rule"]
            if rule is not None and rule["kind"] == "choice":
                values = rule["values"]
                for index in values.keys():
                    options.add("settings.value." + str(values[index]))
        return frozenset(options)
    finally:
        sandbox.close()
