# Testing the MTA Lua resource

## Prefer the executable harness

`tests/lua/` loads the real resource scripts into a real Lua 5.1 interpreter —
the version MTA embeds — and backs the MTA API with recording stubs. Tests call
the code and assert on what it did.

```python
from tests.lua import MtaSandbox

sandbox = MtaSandbox(database_path=str(tmp_path / "ankigta.sqlite"))
sandbox.load("server/store.lua")
sandbox.execute('ANKIGTA.Store.open()')
sandbox.execute('ANKIGTA.Store.setUserSetting("radius", 7)')
```

`tests/test_store_behavior.py` is the worked example.

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
