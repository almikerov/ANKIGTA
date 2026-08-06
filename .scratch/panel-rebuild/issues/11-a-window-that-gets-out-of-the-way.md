# 11 — A window that gets out of the way, and comes back where it was left

**What to build:** the panel fades when the mouse is not on it, may be dragged
anywhere at all, and opens where it always opens.

Three things, one idea: the window stops being something the player has to
manage. Reported after the wave, and not in the 24–44 list — it was asked for
and never written down, which is why it is a ticket rather than a correction.

## It fades when the mouse leaves it

The panel sits over the world the player is trying to look at. While the cursor
is on it, it is being used and is fully opaque; while the cursor is elsewhere,
the player is looking at something else and the panel is in the way.

**The idle opacity is a setting**, client-owned like everything about how this
machine draws. A client setting never crosses the wire, so it is free of the
32-bit float tail ticket 08 dealt with — but it still shows at the precision its
own rule declares, because that is now how every numeric setting behaves.

Three things to get right, none of which the sentence above says:

- **A floor.** Zero is a window that is still there, still eats the cursor, and
  cannot be seen. Whatever the minimum is, it is a number a player cannot fade
  past, not a warning.
- **Typing.** A field being typed into is being used, whatever the mouse is
  doing — the cursor is on the keyboard, and MTA's cursor does not move on its
  own. A panel that fades mid-sentence is worse than one that never fades.
- **Whether MTA can do it at all.** The panel is a `guiCreateBrowser`, and
  nothing in this resource has ever set its alpha. Measure `guiSetAlpha` against
  it on the live server before building on the assumption — if the browser
  surface ignores alpha, say so and say what the alternative is.

## It may be dragged anywhere

`client/layout.lua` clamps every surface inside the screen: `Layout.rect`
(lines ~190) and `Layout.remember` (lines ~212), and stored placements are
clamped to 0..1 again on read (~403). For the panel that clamp goes.

The clamp existed for one reason — a window dragged off the edge is a window
you cannot get back — and the next section removes that reason.

## It opens where it always opens

Every F7 press puts the panel at its default position. Not "restores if it is
off screen": always, unconditionally, so there is one thing the player can rely
on and no state to notice.

**Half of this already shipped.** Ticket 08 made the Settings *screen* not
outlive the window it was opened in (reported item 44). This is the same rule
applied to *where the window is*, and the two should read as one rule in the
code rather than two coincidences.

**Say what happens to the other three surfaces.** `Layout` knows `panel`,
`hud`, `review` and `table`. The panel is what was asked about. `review` and
`table` are opened too, so they plausibly follow the same rule; `hud` has no
"open" moment to reset on and is placed deliberately in `Edit HUD layout`, so it
keeps both its clamp and its saved placement. Decide for each and write the
decision down — a rule that applies to one surface for unstated reasons is the
thing that makes the next ticket guess.

## And then the restore buttons go

`Reset UI layout` — the `#reset-layout` button and the `/ankigta-ui-reset`
command — exists because a window could be put somewhere unreachable. It cannot
be any more.

**But check what it actually resets before removing it.**
`actions.resetLayout` calls `Layout.reset()`, which clears **every** placement
*and* puts UI Scale back to its default. So removing the button removes the only
way back from a UI Scale of 0.5 as well.

That is fine only if the argument holds all the way: the panel always opens at
its default position and therefore is always reachable, the HUD keeps its clamp
and therefore is never lost, and UI Scale is reachable from a panel that is
always where it should be. Check each link. If one does not hold, keep the
control and say which link failed rather than shipping a rescue that no longer
rescues.

**Blocked by:** None — 10 is on the trunk.

**Status:** ready-for-agent

- [ ] The panel is fully opaque while the cursor is over it
- [ ] It fades to the configured opacity when the cursor is elsewhere
- [ ] The opacity is a client setting, shown at its declared precision
- [ ] It cannot be set to a value that makes the panel invisible
- [ ] A field being typed into does not fade
- [ ] `guiSetAlpha` on the browser is measured on the live server, not assumed
- [ ] The panel can be dragged past every screen edge
- [ ] Pressing F7 puts the panel at its default position, every time
- [ ] Settings not outliving the window and position not outliving it are one
      rule in the code, not two
- [ ] What `review`, `table` and `hud` do is decided and written down
- [ ] The HUD still cannot be dragged off screen
- [ ] `Reset UI layout` and `/ankigta-ui-reset` are gone, or kept with the
      reason they are still needed
- [ ] UI Scale is still recoverable from a scale that is hard to read
