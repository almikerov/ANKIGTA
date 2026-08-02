# Remaining work plan

State at the time of writing: tickets 01–12, 14, 15, 16, 19 and 24 are
`resolved`. Fourteen remain. Full suite 255 passed, mypy strict clean, working
tree clean at `ffeae41`.

## Order

Blocking edges allow several orders; this one front-loads whatever unblocks the
most, so the frontier never narrows to a single ticket.

| # | Ticket | Unblocks | Why here |
| --- | --- | --- | --- |
| 1 | **20** Minimal Review Mode | 21, 22, 26, 27, 28 | Highest leverage in the whole backlog; also closes the first end-to-end loop |
| 2 | **13** Early, unavailable and daily limits | 23 | Independent of 20; touches only the companion |
| 3 | **17** Standard Reviewer arbitration | 18 | Needs 16's journal, which exists |
| 4 | **18** Pause, AnkiWeb sync and lifecycle cleanup | 30, 31 | — |
| 5 | **22** Activation Zone and automatic opening | 23, 27 | First spatial behaviour on top of Review Mode |
| 6 | **21** Best-effort CEF, media and External Card Page | 30, 31 | — |
| 7 | **26** Review Protection and client restoration | 30 | — |
| 8 | **25** Teleport and Runtime Instance lifecycle | 30 | Free since ticket 07; slot it wherever convenient |
| 9 | **23** Next Card Indicator and statistics | 28, 30 | — |
| 10 | **27** Settings and localization | 30, 31 | — |
| 11 | **28** UI Scale and layout | 30 | — |
| 12 | **29** Migrations, backups and corruption recovery | 30, 31 | Free since ticket 11; slot it wherever convenient |
| 13 | **30** Performance and large-data acceptance suite | 31 | Needs everything above |
| 14 | **31** Packaging and release certification | — | Last by construction |

## What can run in parallel

Sequential is the safe default: most remaining tickets touch
`mta/ankigta/server/main.lua` or `companion/ankigta_companion/session.py`, and
two sessions editing either will conflict.

Two genuinely disjoint pairs, if you want a second session running:

- **13 + 29** — 13 is `session.py` / `cards.py`; 29 is `store.lua` / `journal.py`.
- **25 + 21** — 25 is server-side entity lifecycle; 21 is the CEF surface.

Do not run 13 and 17 together (both own `session.py`), or 20 and 25 together
(both own the MTA client).

## Per-ticket prompt

One fresh session per ticket, per `development-flow.md`:

```text
/implement

Реализуй только тикет .scratch/ankigta-v1/issues/NN-<slug>.md и соблюдай его
blocking edges. Перед работой прочитай AGENTS.md, docs/agents/lua-testing.md,
docs/agents/mta-gta-reference-policy.md, CONTEXT.md, релевантные ADR и
спецификацию.

Server-side Lua тестируй через исполняемый харнесс tests/lua/ — не добавляй
проверок подстрок в исходниках. Работай test-first небольшими шагами.
Проверки, которые может увидеть только человек, оставляй `not run` с точным
ручным checklist в docs/checklists/.

В конце: полный pytest, mypy, code review относительно исходной точки.
Не коммить, если acceptance criteria не выполнены.
```

## House rules that now apply

Established during tickets 14–19; a fresh session will not know them unless the
prompt above points at the docs:

- **Lua is executed, not grepped.** `tests/lua/` loads the real scripts into
  Lua 5.1 with MTA API stubs over real SQLite. Every source-text assertion in
  this repo has broken at least once, and one was once "fixed" by adding a
  comment to `store.lua` whose only job was to contain the searched-for string.
- **Pin floors, not current values.** `schema version >= 4`, never `== 4`.
- **Mutation-check the load-bearing tests.** Break the constant or the predicate
  and confirm a test fails. Two tests written during ticket 16 passed under
  mutation until they were strengthened.
- **Make test doubles match the producer's real shape.** This has now caused
  three shipped bugs in a row: ticket 25 iterated vehicle occupants with
  `ipairs` because the stub returned a dense 1-based table where MTA returns a
  sparse seat-keyed one; ticket 23 read camelCase fields where `Store` hands
  back raw snake_case SQLite rows; and ticket 32 pushed `[state]` into a page
  reading `state`, because the `toJSON` double returned the bare object where
  MTA serialises its *argument list* and wraps. All three looked green. Before
  writing a double, read what actually produces that value.

  The third one shipped a panel that opened blank — every label rendered as
  its own key and every section stayed hidden — with 1142 tests passing.
  Two things let it through, and both are worth naming. The double was
  *asymmetric with itself*: `toJSON` did not wrap and `fromJSON` did not
  unwrap, so round-trips through storage agreed with each other and with
  nothing else. And **seven** tests had each hand-rolled their own
  `code.find("(")` parser to read the pushed state back, so not one of them
  could tell the two shapes apart. A double that lies is worse the more places
  read it by hand: the decoder now lives on `MtaSandbox` alone, and it asserts
  the shape rather than shrugging at one it does not recognise.
- **Never claim coverage you do not have.** Where a criterion can only be
  observed by a human, mark it `[~]` with the reason and write the checklist.
- **`fetchRemote` callback arguments must be a pure array table.** MTA forwards
  them with `lua_next`, whose order Lua does not guarantee.

## Known follow-ups, deliberately not in the ticket list

- Lazy DB seeding inside `Store.findMapEntityByRuntimeElement` makes a read path
  mutate the database.
- Mixed array/hash `fetchRemote` argument tables remain on the health, card and
  session paths in `companion.lua`.
