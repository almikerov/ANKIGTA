# What the earlier Anki-in-GTA attempt got right

Three resources predate this repository and sit in the owner's own MTA install:
`anki_gta` (an Anki add-on plus tooling and docs), `anki_in_gta` (the runtime
MTA resource) and `anki_map_editor` (a Map Editor extension). They are not
ANKIGTA v1 and are not maintained, but they solved the same problem once, and
some of what they concluded is worth carrying across.

Read on 2026-08-01, read-only, from
`C:\Games\MTA San Andreas 1.6\server\mods\deathmatch\resources\`. Nothing there
was modified. Line counts: 1811 Lua across `anki_in_gta`, ~1000 across
`anki_map_editor`, 618 KB of add-on and docs under `anki_gta`.

## Worth taking

### A static check that every locale key at a call site exists

`anki_gta/scripts/verify.py` checks localization in **both** directions: keys
present in `en.json` but missing from `ru.json`, *and* every key referenced in
Lua, JS or HTML that does not exist in `en.json` at all.

ANKIGTA has the first (`test_both_languages_cover_the_same_keys`) and a runtime
diagnostic (`untranslated_key`), but nothing static for the second. A key
misspelled at a call site renders as the key text and logs — but only if that
code path runs, which for a rarely-hit error branch may be never.

We can do this better than they did. Their version greps the source with a
regex and needs a `dynamic_prefixes` allowlist to suppress false positives.
`tests/lua/constants.py` already reads the constant table out of the compiled
chunk, so the check becomes: every constant that looks like a locale key and is
passed to `Locale.text`/`Locale.format` must exist in `en`. Cheap, and it turns
a runtime diagnostic into a build-time failure.

### Make the nearest-candidate order total

`anki_in_gta/proximity.lua` sorts candidates by distance, then by descending
priority, then by binding ID, so two objects at the same distance always resolve
the same way.

ANKIGTA's `client/activation.lua:162` and `client/indicator.lua:90` both pick
with a strict `<` against the running best, so equidistant candidates resolve by
whatever order the server's snapshot happened to arrive in. That is not a bug
anyone will see often, and it is exactly the kind of thing that becomes an
unreproducible report. A tie-break on the Map Entity's stable ID costs one line
and makes the choice specified.

### Reject an invisible Runtime Instance

Their eligibility test includes `getElementAlpha(element) > 0` alongside the
interior and dimension checks. ANKIGTA checks `available`, interior and
dimension but not alpha, so a bound entity faded to invisible by another
resource still activates. Whether that is wrong depends on what invisible means
in the map, which is a question for the activation ticket rather than something
to change blind.

### A diagnostics accessor for the activation state

`ankiProximityDiagnostics()` returns tracked count, nearest binding, its
distance and the currently open one. ANKIGTA exports `getStoreStatus` and
`getCompanionConnectionStatus` but has no equivalent for activation, so "why did
it not open" has no cheap answer from a player's machine.

### A human name with a fallback chain

`anki_map_editor/selection.lua:elementName` tries `name`, `me:name`, `me:Name`,
`me:ID`, then the model name via `engineGetModelNameFromID` /
`getVehicleNameFromModel`. ANKIGTA shows the Map Entity name the user typed and
falls back to the raw id. Falling back to the model name would make an unnamed
entity readable in F7 without the user naming it first — and a model name is not
user content, so it does not touch the no-translation rule.

### Manual checklist items worth folding into ours

`anki_gta/docs/MANUAL_TESTS.md` is unusually concrete. Four items have no
counterpart in our three checklists and belong there:

- **500 bindings while watching frame time.** ANKIGTA has no stated activation
  budget at all. Theirs is explicit: a 250 ms timer, roughly 2000 distance tests
  per second at 500 bindings, and the claim that this is why a render-frame
  full-map scan was rejected.
- **Restart the resource while a review is open**, then confirm controls,
  cursor, freeze and audio are restored. ANKIGTA restores captured state on
  `onClientResourceStop`, and that path is covered by unit tests, but not by a
  human doing it on a real client.
- **Move a bound door, vehicle or elevator while running** and confirm the
  radius follows the current position rather than the authored one.
- **Destroy a bound object and recreate it with the same element ID**, then
  confirm the binding resolves again. ANKIGTA models this as Entity Missing plus
  Relink entity; the checklist should say what a human should see.

## Deliberately different — do not carry across

### Rating by card id is not scheduler admission

Their add-on answers a card through `POST cards/{id}/answer`, which calls the
scheduler on whatever card the id names after a policy check on due/suspended/
buried state.

ANKIGTA concluded the opposite and built Exact Card Admission for it: rebuild
the filtered deck to exactly card X, verify the scheduler returned X as
scheduler-top, rate, then rebuild the full set. Being able to render a card by
id does not make it the card the scheduler admits. This is written down here
because the simpler shape is genuinely tempting and would look like a
simplification rather than the regression it is.

### Their atomic save is not atomic

`anki_in_gta/persistence.lua:saveBindingDocument` writes a `.tmp`, then
**deletes the final file** and renames the temp over it. A crash between the
delete and the rename leaves neither. It half-recovers — on a failed rename it
re-reads the temp and tries to write the final path again — but the window is
real.

ANKIGTA's connection file and backups use candidate → verify → replace, and
ticket 29's restore keeps the original in place until the replacement has been
verified and then moves it to quarantine rather than deleting it. That is the
difference worth keeping in view whenever someone proposes "just rename it".

### A shipped default token

Both of their components default to the token `anki-gta`, with no minimum
length, masked in settings until Show. ANKIGTA's add-on generates a token and
publishes it atomically in the connection file, and an empty token is a warning
the user has to dismiss. A fixed default that ships in two places is a
credential everyone has.

### Per-map JSON versus one database

Their bindings live in `bindings/<sanitised map name>.json` with a `version`
field and a 0 → 1 migration. It is simple and it survives Map Editor not being
loaded. ANKIGTA put everything in one SQLite because Change History, undo,
identity collisions and statistics all need to be queried across maps — and
ticket 29 then had to build migrations, rotation, quarantine and restore around
it. Neither choice is free; the note here is only that the JSON shape was chosen
for a system without undo.

## Already covered, differently

- **English fallback, UTF-8, no sentences in code.** They enforce it with JSON
  locale files and a documented "do not put user-facing sentences in Python,
  Lua, JavaScript or HTML" rule. ANKIGTA enforces the same rule with Lua tables
  and a guard that reads the compiled constants, which is stronger: their rule
  is a convention plus a regex, ours fails the build.
- **Orphaned bindings are retained and reported, never silently reassigned.**
  ANKIGTA's Entity Missing, Card missing and Identity Collision states.
- **One review open at a time.** Both.
- **Loopback only, bearer token, no SQL or path endpoints, media resolved
  against the collection root.** Both.
- **Editor gives an un-ID'd element a readable stable ID** and keeps `id`,
  `me:ID` and the native element ID in step. ANKIGTA's Pending Map Save and
  independent read-back cover the same ground and additionally refuse to trust
  the write until it has been read back.


## Second reading: the interface and the working loop

The first reading covered architecture and missed the part the owner actually
felt. Read again on 2026-08-03, this time `anki_map_editor/web/index.html`,
`selection.lua` and `anki_in_gta/bindings.lua`.

Their binding panel is not a list of what the system already holds. It is a
two-column workspace with the steps numbered on screen — **1 Choose object**,
**2 Choose card** — and arrows between the columns for Link and Unlink. That
framing is why it was usable: it says what to do rather than showing what is
stored.

### Taken

- **A readable name for a row nobody named.** `selection.lua:elementName` walks
  `name`, `me:name`, `me:Name`, `me:ID` and then the *model* name via
  `engineGetModelNameFromID` / `getVehicleNameFromModel`. Without that last
  step a world candidate reads as the hash that identifies it. Ours now does
  the same, client-side, because the server has no model tables.
- **Take me there.** Their object column has Teleport next to Select in-game.
  A row you cannot find in the world is a row you cannot judge, and ANKIGTA had
  `teleportPlayerToMapEntity` exported with nothing calling it.
- **The dimension belongs in the key.** Their `archiveKey` carries interior
  *and* dimension. Ours carried only the interior, so two identical objects in
  two dimensions would have been one name.

### Worth taking next

- **A deck picker before the search, and filters for tag, note type, card id
  and note id.** Ours searches a deck by name and nothing else.
- **A card inspector**: read, edit, create and delete the note from the panel,
  with its fields and tags. Ours can only pick an existing card.
- **An archive tab** for bindings whose object is gone, and a way to clear it.
  Ours reports Entity missing on the row and offers Relink, which is the same
  information with no place to stand back and look at it.
- **Per-object activation settings inline** — radius and show-radius on the
  object, next to the object. Ours has one global radius in Settings.
- **A replace dialog that shows both cards**, old and new, before it commits.
  Ours replaces on a button with no confirmation.
- **Numbered steps.** Cheap, and it is the difference between a workspace and
  a pair of lists.

### Deliberately not taken

- **Their default token `anki-gta`**, already noted above.
- **`pickup`, `marker` and `colshape` as bindable types.** They allowed them;
  we support object, vehicle and ped. Widening is a spec question, not a
  drive-by change.
