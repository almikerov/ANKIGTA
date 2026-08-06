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

**Status:** implemented on `claude/panel-window-out-of-the-way-7f3a21`, awaiting
merge and an eyes-on pass (see "What remains manual" below)

- [x] The panel is fully opaque while the cursor is over it
- [x] It fades to the configured opacity when the cursor is elsewhere
- [x] The opacity is a client setting, shown at its declared precision
- [x] It cannot be set to a value that makes the panel invisible
- [x] A field being typed into does not fade
- [x] `guiSetAlpha` on the browser is measured on the live server, not assumed
- [x] The panel can be dragged past every screen edge
- [x] Pressing F7 puts the panel at its default position, every time
- [x] Settings not outliving the window and position not outliving it are one
      rule in the code, not two
- [x] What `review`, `table` and `hud` do is decided and written down
- [x] The HUD still cannot be dragged off screen
- [x] `Reset UI layout` and `/ankigta-ui-reset` are gone, or kept with the
      reason they are still needed
- [x] UI Scale is still recoverable from a scale that is hard to read

## Implementation notes (2026-08-06)

**The setting.** `panelIdleOpacity`, client-owned, default 0.6, rule
`numeric(0.2, 1, nil, 2)`. The 0.2 floor is enforced by `validate` like any
out-of-range number — refused with a reason, never clamped — so no stored
value can make the panel invisible. Shown at two decimals through the same
`Settings.rounded` boundary every numeric row uses. The fade itself is a step
of 0.1 per frame toward the target (`client/panel.lua`, `fadePanel`), fully
opaque while the cursor is over the widget, a drag is in progress, or the page
reports a field holding focus (`typing` action on `focusin`/`focusout`, with a
`relatedTarget` check so tabbing between fields never reads as letting go).

**`guiSetAlpha` measured, not assumed.** On the owner's running server,
against a real `guiCreateBrowser` element on the connected client
(GreyDesk87, 2026-08-06): default alpha read 1.0, `guiSetAlpha(probe, 0.25)`
returned true and `guiGetAlpha` read back 0.25. The render path is the MTA
source's (read 2026-08-06, reference tree): `guiSetAlpha` →
`CStaticFunctionDefinitions::GUISetAlpha` (clamps 0..1;
`CLuaGUIDefs.cpp` SHA-256 C177F7DA…5048980,
`CStaticFunctionDefinitions.cpp` CF53771A…66D5B667) →
`CGUIElement_Impl::SetAlpha` → CEGUI `Window::setAlpha`
(`CGUIElement_Impl.cpp` 85DFA0C5…953BAB5); the browser widget is a CEGUI
`StaticImage` over the webview texture (`CGUIWebBrowser_Impl.cpp`
A142AE21…9DD48E4) whose `onAlphaChanged` re-modulates the image colours by
`getEffectiveAlpha()` (`CEGUIStaticImage.cpp` 0DC6D6E0…A2C2D978). A
pixel-level proof through the devserver screenshot tool is impossible: a probe
CEGUI window placed mid-screen does not appear in its captures at all, so the
capture path excludes the GUI layer — verified before concluding, probes and
screenshots destroyed after.

What the repository carries forward from that probe is the sandbox stub
(`tests/lua/sandbox.py`: `guiSetAlpha` accepts, clamps 0..1, and
`guiGetAlpha` reads back) and the tests standing on it. The probe itself is a
one-off against a running client and is not re-runnable evidence — which is
the rule in `docs/agents/mta-gta-reference-policy.md`: a live finding becomes
a test, or it did not happen. Anyone doubting the stub can repeat the probe:
`guiCreateBrowser`, `guiSetAlpha(probe, 0.25)`, `guiGetAlpha(probe)`.

**The surfaces, decided.** `panel` is `transient` (`client/layout.lua`,
`Layout.define` docs): unclamped in `rect`/`moveTo`, excluded from
`snapshot` — an off-screen fraction outside 0..1 would otherwise poison the
whole placement write — never persisted, and a stored one from an older build
is dropped on read. `closePanel` clears the section and forgets the placement
under one comment: nothing about the window outlives the window. `review`
keeps its clamp *and* its saved placement — it reopens on every card of a
session, and forgetting the player's adjustment fifty times an hour is the
wrong reading of this rule; the clamp is what guarantees it can never be
lost. `hud` keeps both for the stronger reason the ticket already gives: no
"open" moment, placed deliberately in Edit HUD layout. **`table` does not
exist** — `Layout` knows `panel`, `review`, `hud` plus dead CEGUI-era defines
(`f7`, `cardPicker`, `study`, `connection`, `connectionSettings`,
`settings`) with no callers; this list was written from an older shape of the
code.

**The rescue, removed with its argument checked.** Every link is now a test
(`tests/test_ui_layout.py`, "the rescue that no longer rescues"): pressing F7
at either extreme of the allowed scale, at each supported resolution, puts the
panel wholly on screen, and UI Scale is typed back to 1 from the row it opens
onto; the HUD and Review Mode cannot be dragged off screen. The test presses
F7 rather than calling `/ankigta-ui` on purpose — the command is the fallback,
and a link tested only through the fallback is a link that has not been
tested. `#reset-layout`, `actions.resetLayout`,
`/ankigta-ui-reset`, `Layout.reset` and the `ui.reset*` strings are gone.

**What remains manual** (`docs/agents/mta-gta-reference-policy.md` §testing):
whether the fade *looks* right in game — the browser visibly resting at the
configured opacity, snapping to opaque under the cursor, and holding while
typing. The programmatic seam (alpha written to the widget, and the CEGUI
source path above) is tested; the rendered frame is not automatable here.
Expected evidence when the owner looks: the panel at rest is see-through at
roughly 0.6, becomes solid the moment the mouse touches it, and does not fade
while the cursor sits in a search box mid-word.
