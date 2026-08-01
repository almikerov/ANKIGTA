# 20 — Minimal Review Mode

**What to build:** Модальный MTA Review Mode, который показывает question/answer через stock CEF, оставляет outer rating controls под Lua/dx и завершает одну Review Transaction.

**Blocked by:** 15 — One rating through MTA; 19 — Read-only card content capability.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Review Mode opens question, explicitly reveals answer and shows Again/Hard/Good/Easy for scheduler-admitted card.
- [x] CEF получает только short-lived content capability; control API/token остаются server-side.
- [x] `Esc` closes without rating if none submitted.
- [x] После submit кнопки не создают второй logical transaction; confirmed result updates/close behavior.
- [x] `Close after rating` closes after every accepted rating, including Again.
- [x] F7/E/1–9/+/− не выполняют игровые ANKIGTA actions while modal.
- [x] Alt+Tab не closes/rates и требует click-to-refocus.
- [x] Close/failure restores captured cursor/control/camera/audio state, not unconditional defaults.

## Tests

- [x] Repository-local Review Mode contract test plus a manual MTA question → answer → rating checklist left `not run`.
- [x] Esc, duplicate click, focus loss and Close after rating tests.
- [x] CEF/resource failure cleanup test.

## Components

- MTA client Review Mode shell.
- Stock MTA CEF child surface.
- MTA server rating/session path.

## Implementation status

- `client/review_mode.lua` is the modal shell: a CEF child surface for the card
  and a dx rating bar drawn **outside** it, so card HTML cannot impersonate a
  rating control.
- The client never performs HTTP, holds no token and knows no control path. It
  receives a URL from the server and sends back a rating name; the server owns
  capability issuance, admission and the rating itself.
- One accepted rating per open card: further clicks while in flight or after a
  confirmed result submit nothing.
- `Esc` closes when nothing was submitted and refuses while a rating is in
  flight, since closing then would leave the player unsure whether it counted.
- Focus loss neither closes nor rates, and the click that restores focus is
  consumed rather than being treated as a rating.
- Open captures the cursor, the controls it disables, the camera target and the
  radio channel, and close restores those exact values — including on a failed
  open, an authorization loss or a resource stop.
- An `outcome_unknown` result keeps the card open and says so, rather than
  showing either success or failure.
- Server side: `Gateway.requestRender` issues the capability through
  `/v1/render/issue`, and `/v1/render/close` revokes it on close instead of
  waiting out the 15-second lifetime.

Ticket 02's client-side guard forbade the literal `127.0.0.1` in client scripts.
CEF requires the client to whitelist the content endpoint's host via
`requestBrowserDomains`, so that assertion was narrowed to its actual intent:
no `fetchRemote`, no credentials, no control paths, and loopback permitted only
on a `requestBrowserDomains` line. The URL, port and capability still arrive
from the server.

Automated evidence: `pytest -q tests/test_review_mode_behavior.py` → 30 passed;
full suite 279 passed; mypy strict clean.

## Manual runtime checklist

See `docs/checklists/ticket20-review-mode.md` (`Status: not run`).
