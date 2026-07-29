# 18 — Pause, AnkiWeb sync and lifecycle cleanup

**What to build:** Полный lifecycle паузы и восстановления при AnkiWeb sync, disconnect/reconnect, resource/MTA restart, normal shutdown и удалении resource.

**Blocked by:** 03 — Connection config and reconnect; 16 — Durable Review Transaction recovery; 17 — Standard Reviewer arbitration.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] `Pause studying` disables activation/indicator and returns all cards from owned deck without deleting links.
- [ ] User-started AnkiWeb sync closes unrated review, reconciles submitted rating, cleans session and remains paused.
- [ ] ANKIGTA never starts/waits for sync and exposes no sync settings.
- [ ] Disconnect restores MTA client state, preserves pending transaction and pauses study.
- [ ] Reconnect reconciles first and remains connected-paused with no auto-open/rebuild.
- [ ] Normal stop/exit/removal cleans owned deck and closes connection without closing Anki Desktop.
- [ ] F7/Review Mode and unsaved form text are not reopened after restart; persisted changes remain.
- [ ] No lifecycle scenario strands a card in `ANKIGTA Session`.

## Tests

- [ ] Real-Anki sync arbitration tests.
- [ ] Companion/resource/MTA restart matrix with pending/unrated/submitted review.
- [ ] Install/update/pause/remove cleanup assertions on filtered-deck membership.

## Components

- Session/recovery coordinator.
- MTA resource lifecycle.
- Companion Anki sync/lifecycle hooks.
- Client state restoration.

