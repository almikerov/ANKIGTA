# 23 — Next Card Indicator and statistics

**What to build:** HUD, Next Card Indicator и уникальные `Total/New/Learning/Due/Early`, согласованные с наблюдаемым Anki state и текущим Active Map Set.

**Blocked by:** 13 — Early, unavailable and daily-limit behavior; 22 — Activation Zone and automatic opening.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Statistics count unique Anki Card Identity, not number of Spatial Link.
- [x] `Total` is union of `New`, `Learning`, `Due`, `Early`; Early always visible and zero when disabled/empty.
- [x] Suspended/Buried/Card missing/Pending Map Save/excluded maps do not count.
- [~] Counts refresh after Anki notification, link/map/session changes and completed review without reimplementing scheduler. Пересчёт чистый и без собственного планировщика (проверяется тестом); частота обновления в живом HUD — ручная проверка.
- [x] Indicator modes exactly: sphere+minimap, minimap only, nothing; default nothing and no sphere-only mode.
- [x] Multiple entities for next card mark only nearest eligible entity.
- [x] Temporary sphere does not alter/create Activation Zone; overlap renders one emphasized/pulsing sphere.
- [x] Indicator obeys current runtime availability/world context while queue remains global.

## Tests

- [x] Scheduler-state/statistics matrix and duplicate-link tests.
- [x] Active Map Set and status refresh tests.
- [~] Repository-local indicator/state tests plus a manual MTA visual-behavior checklist left `not run`.

## Components

- Companion statistics query.
- Server aggregation/next-target selection.
- MTA Statistics HUD, Minimap Blip and sphere renderer.

## Implementation status

- `server/statistics.lua` counts **cards, not links**: one card linked to five
  entities is one card to study, and reporting five would tell the player they
  have more work than they have.
- Nothing here decides a card's state. A card Anki has not reported on is not
  counted, because the alternative is guessing, and guessing is a second
  scheduler (ADR 0017). A test pins the Lua bucket names against the
  companion's own `CardState` enum so the two cannot drift apart.
- `/v1/cards/states` is the companion statistics query: it reports observed
  state per Anki Card Identity and simply omits a card it cannot read.
- `client/indicator.lua` has exactly three modes and defaults to nothing. There
  is deliberately no sphere-only mode: a sphere with no minimap marker only
  helps someone already looking at it. It renders the HUD counts, creates and
  moves the Minimap Blip, and draws the temporary sphere, driven by two server
  events and `onClientRender`.
- The queue is global but the indicator is not — it points only at an instance
  in the player's own interior and dimension, and only at the nearest one.
  Both rules are mutation-checked.

**Defect found by code review, in this ticket's own code.** `Statistics` read
camelCase fields, but `Store` hands back raw SQLite rows (`collection_uuid`,
`card_id`, `link_state`, `map_id`). Against real rows it would have matched
nothing and reported zero for everything — which looks exactly like "no work to
do", so it might have gone unnoticed for a long time. The test double had
invented the camelCase shape, the same failure mode as ticket 25's occupant
stub. The double now builds rows the way `Store` emits them, and a test pins
that shape explicitly.

**Two review findings acted on rather than argued with.** The
"indicator never touches the Activation Zone" test was a hand-picked blocklist
of function names; it now loads both modules together, puts a countdown in
flight and asserts Activation's own state is unchanged. And a `seen` marker
carried a comment claiming subtlety it did not have — the mutation survived, so
the code was simplified instead of the comment being kept.

Automated evidence: `pytest -q tests/test_statistics.py tests/test_indicator.py`
→ 39 passed; full suite 462 passed; mypy strict clean.

## Where the polling lives (added by ticket 31)

Like ticket 22, this ticket built the rules and left out what feeds them. Ticket
30 found that no server code sent `ankigta:statistics` or `ankigta:nextCard`
and nothing called `Statistics.summarize`, so the HUD stayed blank and the
marker never appeared. Ticket 31 wrote that half.

- One refresh answers all three questions at once, in `server/main.lua`: how
  much work there is, which Spatial Link may activate, and which Map Entity
  carries the marker. They are statements about the same moment, and asking
  twice would let them disagree about it.
- `ANKIGTA.CompanionGateway.requestCardStates` is the query. It posts every
  linked Anki Card Identity to `/v1/cards/states`, which now answers with the
  observed state per card **and** with `nextCard` — the card Anki's own
  scheduler has as top. ANKIGTA still decides nothing about card state or order
  (ADR 0017).
- The refresh runs when the session state changes and when a link, replace,
  unlink or relink invalidates what was counted.
- `ankigta:nextCard` carries the identity and the Map Entity carrying it,
  never coordinates. `client/spatial.lua` resolves those to live positions
  **every frame** — the marker follows a moving Runtime Instance frame by
  frame rather than in 250 ms steps — through
  `Indicator.setCandidateSource`, which is the one change to this ticket's own
  module.
- A next card that nothing in the Active Map Set carries is not announced: a
  marker with no target would leave the player believing they had one.

Tests: `tests/test_study_refresh.py` and `tests/test_spatial_polling.py`.

## Manual runtime checklist

See `docs/checklists/ticket23-indicator-statistics.md` (`Status: not run`).
