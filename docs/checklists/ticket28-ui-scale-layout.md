# Ticket 28 — UI Scale and layout manual checklist

Status: not run

Geometry is covered automatically: every surface is placed, clamped and
measured in a real Lua interpreter at 1280×720, 1920×1080 and 3840×2160 and at
scale 0.5, 1 and 2, and every control is checked against the window that holds
it. What no test can answer is whether the result is *readable*, whether a drag
feels like a drag, and whether CEF behaves when the surface around it changes
size.

## Scenarios

### UI Scale

- Open `/ankigta-ui`. Confirm the scale reads `1.00`, that `Smaller` and
  `Larger` move it by 0.05 per press, and that they stop at 0.50 and 2.00
  instead of wrapping or continuing.
- Type `1.23` into the exact-value field and press `Apply`. Confirm it is
  accepted. Type `1.234` and `9`, and confirm each is refused with a readable
  reason in the chat and that the scale does not change.
- With F7, the Card Picker, Study, the connection windows and Review Mode open
  in turn, change the scale and confirm each redraws at the new size
  immediately, with no resource restart and no reopening.
- At 0.50 on 1280×720, confirm every label is still legible rather than merely
  present. At 2.00 on 1280×720, confirm the windows are capped to the screen
  and that every button is still reachable with the mouse.
- Switch the game to each of 1280×720, 1920×1080 and 3840×2160 and repeat the
  reading pass. Report the smallest scale at which text stops being readable
  on each.

### Dragging

- Drag F7 by its title bar to each screen corner. Confirm it moves smoothly,
  that the grid and the buttons move with it, and that it never leaves the
  screen.
- Repeat for the Card Picker, Study, both connection windows and the UI panel.
- With F7 open, raise `Unlink` and `Replace card`. Confirm the warning appears
  centred on F7 and that dragging F7 carries the warning with it.
- Open Review Mode and drag it by its title bar. Confirm the card image and the
  rating bar follow, and that a click on the title never reveals or rates.
- Click each rating button after dragging, and confirm the rating lands on the
  button the cursor is over.

### Edit HUD layout

- With Edit HUD layout off, click and drag over the HUD counters. Confirm
  nothing moves and nothing else in the game reacts to the click.
- Turn Edit HUD layout on. Confirm the HUD shows its grab area and its hint,
  drag it to another corner, and confirm the counters stay readable there.
- Turn Edit HUD layout off and confirm the HUD stays where it was put and can
  no longer be dragged.

### Persistence and recovery

- Drag every window somewhere unusual, then `/restart ankigta`. Confirm every
  window comes back where it was left.
- With windows near the bottom-right, change the resolution from 3840×2160 to
  1280×720. Confirm each window is pulled back onto the screen with its title
  bar reachable, within a second or so of the change.
- Change the aspect ratio (for example 1280×1024) and confirm the same.
- Press `Reset UI layout`. Confirm the scale returns to 1.00, every window
  returns to the centre, the HUD returns to the top right and Edit HUD layout
  is off.
- Confirm `Reset UI layout` is reachable both from F7 and from the
  `/ankigta-ui` chat command, including after everything has been dragged into
  one corner at scale 2.00.

### CEF

- Change the scale while a card is open and confirm the card image follows the
  new surface size without the card reloading, losing its side, or losing
  audio.
- Drag Review Mode while a card is playing audio and confirm the audio is
  uninterrupted.
- Confirm the card is still clickable, scrollable and typable after a drag and
  after a scale change.

### Gamepad (ADR 0015)

- Connect a controller. With F7, Review Mode and the UI panel open in turn,
  work every stick, trigger, D-pad direction and button. Confirm no ANKIGTA
  action fires: nothing opens, closes, reveals, rates, moves or resets.
- Confirm the controller does not steal focus from CEF while a card is open,
  and that typing into the card still reaches it afterwards.
- Confirm no ANKIGTA screen mentions a controller, offers a controller prompt
  or offers controller remapping.

## Expected evidence

Per scenario: the resolution and UI Scale in force, a description of what was
observed, and for the reading passes the smallest scale that was still legible.
For the gamepad pass: the controller model, and the list of inputs exercised
against the observation that none of them produced an ANKIGTA action.
