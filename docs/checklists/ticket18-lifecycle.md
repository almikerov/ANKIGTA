# Ticket 18 — Lifecycle manual checklist

Status: not run

Every exit path and the "never strand a card" guarantee are covered
automatically, including the real Anki hooks. What remains needs a live
collection and a real MTA server: confirming that an AnkiWeb sync actually
arrives as a temporary close on the pinned build, and that restarts leave
nothing behind.

Use a disposable Anki profile and take a native backup first.

## Scenarios

- Press `Pause studying`. Confirm activation zones and the next-card indicator
  go quiet, every card returns to its home deck, and no Spatial Link is removed.
- Start an AnkiWeb sync with a session running and an unrated card open.
  Confirm the card closes without a `revlog` row, the owned deck is emptied and
  removed, and ANKIGTA stays paused after the sync finishes.
- Repeat with a submitted-but-unproven rating. Confirm cleanup is deferred, the
  card is not hidden, and reconciliation happens before anything is emptied.
- Confirm ANKIGTA offers no sync setting anywhere and never initiates a sync.
- Kill the companion mid-session. Confirm MTA restores client state, the pending
  transaction survives, and study is paused.
- Reconnect. Confirm reconciliation runs first, the state is connected-paused,
  and no card reopens and no deck rebuilds by itself.
- Restart the MTA resource, then the whole MTA server, then Anki. For each,
  confirm no card is left in `ANKIGTA Session` and no filtered deck survives.
- Stop the resource, quit Anki normally, and remove the add-on. Confirm each
  cleans the owned deck and closes the connection **without** closing Anki
  Desktop.
- Leave F7 open with unsaved text, then restart. Confirm F7 and Review Mode do
  not reopen, the unsaved text is gone, and persisted changes remain.

## Expected evidence

Per scenario: filtered-deck membership before and after, each card's current and
home deck, the `revlog` delta, and the journal state.
