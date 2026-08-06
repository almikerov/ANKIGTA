# Panel rebuild 06 — Review mode `Show text`, manual checklist

Status: not run

Everything a test can reach is covered automatically: which text ANKIGTA asked
MTA to draw and at what scale and colour, what the server put on the wire, what
the store holds, and what the panel row says. What no test can reach is whether
what rendered is *readable* — a frame, at a real resolution, against a real
sky — so that is here.

`docs/agents/mta-gta-reference-policy.md`: the harness does not render, and the
development tooling cannot say whether a frame is legible. These are the two
things it names as out of reach, and this list is exactly them.

## Setting it up

The owner's database holds no Map Entity. To see anything at all:

1. Open the stock Map Editor, place two or three objects and save the map.
2. Press F7, select each object, pick a card in the Card Picker and press Link.
3. In Settings, set `Review mode` to `Show text`.

## The words are on the object

- Walk up to a linked object. Its card's first field with words is drawn above
  it, not inside it.
- Read it from four sides and from above. It faces you from each, and there is
  no side from which it is edge-on or mirrored.
- Walk backwards until it disappears, and confirm it goes at roughly the
  `Text Label distance (m)` you set rather than at the edge of the object's
  own draw distance.
- Set the distance to its maximum and walk out to it. The label goes before the
  object does — 150 m is the ceiling everything ANKIGTA draws stops at.

## Legibility, which is the whole reason the outline exists

- Set `Text Label colour` to white and stand so the label is against a white
  wall, then against a bright midday sky. It stays readable.
- Set it to black and stand under a night sky. Same.
- Set `Text Label size` to 0.25 and to 5 and confirm both are usable rather
  than unreadable at one end and covering the screen at the other. Judge each
  standing next to the object: a label also shrinks with distance on purpose —
  the size is multiplied by roughly 1.5 up close and 0.55 at the far edge of
  the distance setting — so `0.25` read from thirty metres away is meant to be
  small, and `0.25` read from two metres is the one to judge.

## Wrapping and the ellipsis

- Link a card whose chosen field is a paragraph. Confirm it wraps between
  words, stops at three lines, and that the last line ends in `…`.
- Confirm the ellipsis is inside the line rather than hanging off its right
  edge.

## Reading while moving

- Drive past a labelled object at speed. The label is drawn the whole way past;
  it does not blink out the way an Activation Zone's offer would.

## Too many at once

- Put more than 24 linked objects within the label distance of one another and
  stand among them.
- Confirm the nearest 24 carry labels, and that `+N more Text Labels nearby`
  appears under the HUD counters.
- Walk towards the far ones and confirm the set changes as you move rather than
  staying whichever 24 arrived first.

## One entity shows one thing

- Set `Activation type` to `Key` on a labelled object and stand in its zone.
  Confirm the object carries its Text Label and **not** `E to view`.
- Change `Review mode` back to `Allow due`. Confirm the label goes and
  `E to view` comes back on the same object.

## Nothing is presented and nothing is rated

- In `Show text`, walk into a linked object's Activation Zone and wait. No card
  opens.
- Press the activation key on a labelled object. No card opens.
- Confirm the settings row under `Review mode` says that reading a label writes
  no repetition, and that no `Start studying` button is offered.
- In Anki, confirm no ANKIGTA filtered deck was built or rebuilt while the mode
  was on, and that no card's review history moved.

## With Anki shut

- With the mode on and labels drawn, quit Anki.
- Confirm the labels stay exactly as they were.
- Restart the MTA resource with Anki still shut and confirm the labels come
  back from the cache.

## Editing the card

- Open the inspector on a labelled card, change the field the label is showing
  and press Save.
- Confirm the object's label changes without pressing anything else.

## When a field cannot be shown

- Set `Text Label field` to a field name one of your note types does not have.
- Confirm that object still shows something — its first field with words — and
  that its row in F7 says it is falling back and names both fields.
- Put only an image or a `[sound:]` in the chosen field of another note and
  confirm the same, with the other reason.
