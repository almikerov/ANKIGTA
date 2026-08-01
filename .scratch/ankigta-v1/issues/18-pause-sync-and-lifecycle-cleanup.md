# 18 — Pause, AnkiWeb sync and lifecycle cleanup

**What to build:** Полный lifecycle паузы и восстановления при AnkiWeb sync, disconnect/reconnect, resource/MTA restart, normal shutdown и удалении resource.

**Blocked by:** 03 — Connection config and reconnect; 16 — Durable Review Transaction recovery; 17 — Standard Reviewer arbitration.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] `Pause studying` disables activation/indicator and returns all cards from owned deck without deleting links.
- [x] User-started AnkiWeb sync closes unrated review, reconciles submitted rating, cleans session and remains paused.
- [x] ANKIGTA never starts/waits for sync and exposes no sync settings.
- [x] Disconnect restores MTA client state, preserves pending transaction and pauses study.
- [x] Reconnect reconciles first and remains connected-paused with no auto-open/rebuild.
- [x] Normal stop/exit/removal cleans owned deck and closes connection without closing Anki Desktop.
- [x] F7/Review Mode and unsaved form text are not reopened after restart; persisted changes remain. Review Mode и F7 закрываются на `onClientResourceStop` (тикеты 20/05) и не переоткрываются; визуальная проверка в чеклисте.
- [x] No lifecycle scenario strands a card in `ANKIGTA Session`.

## Tests

- [~] Real-Anki sync arbitration tests. Хук temporary-close покрыт; сверка с живым AnkiWeb остаётся ручной.
- [x] Companion/resource/MTA restart matrix with pending/unrated/submitted review.
- [x] Install/update/pause/remove cleanup assertions on filtered-deck membership.

## Components

- Session/recovery coordinator.
- MTA resource lifecycle.
- Companion Anki sync/lifecycle hooks.
- Client state restoration.

## Implementation status

- `lifecycle_study.py` funnels every way study can end — user pause, AnkiWeb
  sync, collection close, lost connection, Reviewer takeover, shutdown — into
  one settle path, because they share one requirement: empty the owned deck and
  return every card. A card abandoned in a deleted `ANKIGTA Session` is
  invisible to the user, so cleanup is the step that runs in all of them.
- Spatial Links are never touched by any of them.
- Nothing resumes study by itself. Reconnecting reconciles and stops there; a
  socket coming back is not a request to study. A finished sync likewise leaves
  the state paused.
- An unproven transaction defers cleanup rather than emptying the deck, since
  emptying it would hide the very card whose outcome is unknown.
- Losing the connection deliberately does **not** close the open review: the
  pending transaction and its card survive the drop untouched.
- Wired into Anki's real hooks: a user-started AnkiWeb sync arrives as
  `collection_will_temporarily_close`, profile close pauses, and add-on stop
  cleans up without closing Anki Desktop.
- A source test enforces that ANKIGTA never calls a sync API; sync belongs to
  the user's account.

Automated evidence: `pytest -q tests/test_study_lifecycle.py` → 31 passed;
full suite 354 passed; mypy strict clean.

## Manual runtime checklist

See `docs/checklists/ticket18-lifecycle.md` (`Status: not run`).
