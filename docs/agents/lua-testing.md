# Testing the MTA Lua resource

## Prefer the executable harness

`tests/lua/` loads the real resource scripts into a real Lua 5.1 interpreter —
the version MTA embeds — and backs the MTA API with recording stubs. Tests call
the code and assert on what it did.

```python
from tests.lua import MtaSandbox

sandbox = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
# Load in meta.xml order: the store validates against the shared schema.
sandbox.load("shared/settings.lua")
sandbox.load("server/store.lua")
sandbox.execute('ANKIGTA.Store.open()')
sandbox.execute('ANKIGTA.Store.setUserSetting("activationRadius", 7)')
```

`tests/test_store_behavior.py` is the worked example.

Where a test needs the whole side, read the script list out of `meta.xml` and
fire `onResourceStart` / `onClientResourceStart` rather than hand-listing the
scripts — see `manifest_scripts` in `tests/test_settings_stores.py`. A script
that was never registered then fails the test instead of working in tests only.

## The interface can be rendered

`gui*` is stubbed, so a client window can be built and read back. Controls are
recorded in creation order with the text the resource actually wrote into them,
and destroying a window takes its children with it the way CEGUI does.

```python
sandbox.load("shared/locale.lua")
sandbox.load("client/study.lua")
sandbox.trigger("ankigta:companionStatus", ...)
assert "Начать обучение" in sandbox.widget_texts()
```

`sandbox.widget_texts()` is every live control's text, `sandbox.grid_texts()`
every grid heading and cell, and `sandbox.drawn_text` every string handed to
`dxDrawText`. `getLocalization()` reports `sandbox.localization`. Indexing
follows MTA: grid rows from 0, columns from 1, and `-1` for no selection.

This is what makes "the interface is translated" checkable. A string present in
`locale.lua` but never written into a control fails the render test, which a
key-parity check cannot see.

## Reading the constants a chunk holds

`tests/lua/constants.py` dumps a script through the same Lua 5.1 interpreter and
walks the string constants out of the bytecode. Use it where a test needs to
know what the code will look up — `"f7.recheck" in string_constants(F7)` — and
never grep the file for the same thing: a grep sees comments, misses strings
built by concatenation, and breaks on reformatting.

`tests/test_localization.py` uses it for the guard that no script outside
`shared/locale.lua` compiles a Cyrillic string constant.

## Do not add source-text assertions

Searching a `.lua` file for a substring proves nothing about behavior and breaks
whenever a later ticket edits the file. Every such test in this repository has
already broken at least once, and one of them was "fixed" by adding a comment to
`store.lua` whose only purpose was to contain the searched-for text.

Where a source-contract test is genuinely the right tool — proving a token never
appears in client-side code, or that a script is registered server-side only —
assert the invariant rather than an incidental detail:

- pin a floor (`schema version >= 4`), never an exact current value;
- assert that a call is unreachable outside its guard, never a count of call
  sites;
- assert the behavior a constant produces, never the constant's literal text.

## Stub fidelity

Stubs follow the MTA server source, not memory. Three details that are easy to
get wrong and that the harness gets right:

- `dbPoll` returns `rows, affectedRows, lastInsertId`, or `false, errorCode,
  errorMessage` on failure.
- A SQL NULL arrives in Lua as boolean `false`, not `nil`, so the column key
  stays present in the row table.
- `sha256` returns **uppercase** hex.

When you need an MTA function the sandbox does not stub yet, read its
implementation in the MTA source reference before adding it — see
`mta-gta-reference-policy.md` for the path and the read-only rules.

## What the harness cannot do

It does not render, stream, run CEF, or process input. Acceptance that depends on
those stays a manual checklist item marked `not run`.
