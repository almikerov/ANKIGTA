# Ticket 32 — the panel, manual checklist

Status: not run

The panel is an HTML page in stock MTA CEF. Everything a test can reach is
covered automatically: which browser was created, what Lua pushed into it, what
the page's actions do, and that every string is a key. What no test can reach is
whether the page *renders* — CEF fidelity, fonts, layout at real resolutions,
and the feel of the cursor — so that is here.

## The page renders at all

- Press F7. The panel appears as one dark overlay, not a system dialog, and the
  world stays visible behind it.
- Confirm no scrollbar on the shell itself, and no horizontal scroll anywhere.
- Confirm the Segoe UI fallback is in use and no text is boxed or missing — the
  page loads no web font on purpose, because the machine may be offline.

## The cursor

- Open and close with F7. The cursor goes and comes back.
- Open the panel, then press Escape. Same.
- Open the panel while the cursor was *already* showing for another resource.
  Close it. The cursor is still showing.
- Stop the resource with the panel open. The cursor comes back.

## The gate

- With Anki closed, press F7. The panel opens on the connection section.
- Press Close. It closes; you are not trapped.
- Type a port and token, press Apply, then Connect. Confirm the status line at
  the top turns green and the panel moves to the workspace.

## The workspace

- Confirm the Map Entity list shows name, id, type, Runtime Instance state and
  Spatial Link state, and that the state is readable as a word rather than only
  as a colour.
- Type in the filter and press Filter. Confirm the count reads `Showing N of M`.
- Search a deck in the Card Picker. Confirm the rows are grouped by deck rather
  than by card id.
- Select a Map Entity and a card, press Link. Then Unlink. Then Replace card.
- Press Pick Entity, click an object in the world, and confirm the panel comes
  back with that entity selected — even if your filter would have hidden it.
- Undo and Redo, and confirm the buttons grey out when there is nothing to do.

## Scale, language and study

- Change UI scale in the settings panel and reopen the panel. It is bigger.
- Switch language with the panel open. Every label changes without a restart,
  and the filter text you typed is still there.
- With cards linked and Anki connected, confirm studying starts on its own —
  there is no Start button to press.
- Open Anki's own Reviewer. Confirm ANKIGTA pauses and the panel offers one
  way back, not four.

## Expected evidence

Screenshots of the panel at 1280x720, 1920x1080 and 4K, in both languages, and
a note of any label that clips.
