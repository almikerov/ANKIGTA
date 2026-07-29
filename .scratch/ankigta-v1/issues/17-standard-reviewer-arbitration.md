# 17 — Standard Reviewer arbitration

**What to build:** Взаимоисключающий lifecycle между обычным Anki Reviewer и `ANKIGTA Session`, включая безопасное ожидание уже начатого stock callback.

**Blocked by:** 12 — Full ANKIGTA Session; 16 — Durable Review Transaction recovery.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Starting normal Reviewer pauses ANKIGTA and cleans owned session only after submitted transaction reconciliation.
- [ ] Unrated standard question/answer exits without Anki mutation through the version-gated tested AQT surface.
- [ ] In-flight standard rating displays `Завершаем оценку Anki…` and leaves Reviewer state untouched until callback completes.
- [ ] Completion then closes Reviewer and permits session startup.
- [ ] Timeout never forces cleanup, monkey-patches callback or starts session.
- [ ] Ending ordinary Reviewer never resumes ANKIGTA automatically.
- [ ] Unsupported Anki build blocks session arbitration rather than guessing lifecycle.

## Tests

- [ ] Real-Anki question/answer leave tests.
- [ ] In-flight asynchronous callback completion and timeout tests.
- [ ] Reviewer-start-during-active-session cleanup/reconciliation tests.

## Components

- Companion Anki lifecycle observer.
- Session coordinator.
- MTA pending-start/status UI.

