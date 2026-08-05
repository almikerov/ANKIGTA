# Panel rebuild 05 — activation by key, and applying a global to everything

Status: not run

This checklist requires a separately authorized MTA runtime. It is not executed
by repository implementation or review work. Everything below that a machine can
answer is already answered by `tests/test_activation_by_key.py`; what is left
here is what needs a person to look at a frame.

## The prompt is readable

The harness can say that ANKIGTA asked MTA to draw `E to view` at a screen
position, and that it stopped asking past 150 metres and behind the camera. It
cannot say whether the result is legible.

1. Link a card to an object, set `Activation type` to `Key`, and walk into the
   Activation Zone. The prompt appears over the object and faces you as you walk
   around it.
2. It is readable against a bright sky, against dark ground, and with the
   ANKIGTA HUD counters behind it.
3. Walk backwards until it disappears, and confirm it goes at roughly a city
   block rather than snapping out under your feet or hanging in the air after
   the object's own detail has dropped.
4. Stand still and watch for a few seconds: the prompt does not flicker between
   frames.

## The press

5. Press the key named in the prompt. The card opens.
6. Press it again while the card is open: nothing happens twice, and closing the
   card leaves you back with the prompt while you are still inside the zone.
7. Walk out of the zone and press the key. Nothing opens.
8. Set `Activation delay` to 30 seconds and repeat step 5. The card still opens
   on the press — the delay is not a gate on it.
9. Walk into the zone while running, then while driving through it, and press
   the key each time. It opens both times: the speed threshold gates a card that
   opens by itself, not one you asked for.
10. Set the entity's own `Activation key` to something else, and confirm the
    prompt names *that* key and that the global one no longer opens it while you
    are standing there.

## Nothing else moved

11. Set `Activation type` back to `Automatic` and confirm a card still opens by
    itself, with the delay and the speed threshold behaving as before.
12. Rate the card. The rating reaches Anki exactly as it does for a card opened
    by walking up to it.
13. Confirm the key you chose still does whatever GTA does with it while no card
    is being offered.

## Applying a global to everything

14. Open Settings and confirm every setting a link can override — Activation
    Zone radius, Activation type, Activation key, Show corona, Corona colour,
    Corona opacity — carries `Apply to all` beside it, and that no other setting
    does.
15. Give three different objects their own radius. Press `Apply to all` beside
    `Activation Zone radius (m)`: the question names **3**.
16. Cancel. The three objects still have their own radius.
17. Press it again and confirm. All three now show the global in their radius
    box, marked `following Settings`.
18. Change the global radius. All three move with it.
19. Confirm the corona colour those objects were given is untouched.
20. Press Undo once. All three have their own radius back, with the numbers each
    of them had.

## What to record

For each step: what you did, what you saw, and — where it did not match — a
screenshot and the matching lines from `clientscript.log` and `server.log`.
