# 17 — Standard Reviewer arbitration

**What to build:** Взаимоисключающий lifecycle между обычным Anki Reviewer и `ANKIGTA Session`, включая безопасное ожидание уже начатого stock callback.

**Blocked by:** 12 — Full ANKIGTA Session; 16 — Durable Review Transaction recovery.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Starting normal Reviewer pauses ANKIGTA and cleans owned session only after submitted transaction reconciliation.
- [x] Unrated standard question/answer exits without Anki mutation through the version-gated tested AQT surface.
- [x] In-flight standard rating displays `Завершаем оценку Anki…` and leaves Reviewer state untouched until callback completes.
- [x] Completion then closes Reviewer and permits session startup.
- [x] Timeout never forces cleanup, monkey-patches callback or starts session.
- [x] Ending ordinary Reviewer never resumes ANKIGTA automatically.
- [x] Unsupported Anki build blocks session arbitration rather than guessing lifecycle.

## Tests

- [~] Real-Anki question/answer leave tests (manual: not run).
- [x] In-flight asynchronous callback completion and timeout tests.
- [x] Reviewer-start-during-active-session cleanup/reconciliation tests.

## Components

- Companion Anki lifecycle observer.
- Session coordinator.
- MTA pending-start/status UI.

## Implementation status

- `arbitration.py` holds the mutual-exclusion state machine. Opening Anki's
  Reviewer pauses ANKIGTA; closing it never resumes ANKIGTA, because restarting
  a game session unasked is worse than asking for a button press (ADR 0022).
- Handover is refused while a submitted ANKIGTA transaction is still unproven,
  and the owned deck is not cleaned in that case — otherwise the two modes could
  disagree about what happened.
- An unrated question or answer is left through the version-gated
  `moveToState("deckBrowser")` surface, which prototype 0003 measured as
  mutation-free. If the Reviewer does not actually reach the deck browser, that
  is reported rather than forced.
- An in-flight standard rating is waited for, visibly. Prototype 0003 disproved
  the shortcut of closing the Reviewer and letting the rating finish in the
  background: the stock callback still depends on `Reviewer.card`. Repeated
  requests while waiting change nothing, since a timeout is not permission.
- An unsupported build blocks arbitration instead of guessing at the lifecycle.
- A source test enforces ADR 0022's three prohibitions: no monkey-patching, no
  private state mutation, no forced cancellation.

The version-sensitive AQT slice is confined to one `ReviewerSurface` protocol,
so the next Anki version needs re-verifying in one place rather than several.

Automated evidence: `pytest -q tests/test_arbitration.py` → 15 passed; full
suite 323 passed; mypy strict clean.

## Manual runtime checklist

See `docs/checklists/ticket17-reviewer-arbitration.md` (`Status: not run`).
