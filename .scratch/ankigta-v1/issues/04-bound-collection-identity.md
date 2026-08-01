# 04 — Bound Anki Collection identity

**What to build:** Устойчивую Anki Card Identity через add-on-owned collection UUID, выбор одной Bound Anki Collection и Collection Copy Decision для копии, переноса или восстановления.

**Blocked by:** 01 — Companion health and Anki version.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Collection UUID создаётся атомарно в collection config и переживает restart и profile rename.
- [x] Profile name/path и один `cardId` нигде не принимаются за устойчивую Anki Card Identity.
- [x] Пользователь явно выбирает одну Bound Anki Collection; другая открытая коллекция даёт paused/wrong-collection state.
- [x] Если прежний экземпляр UUID зарегистрирован локально, дубликат автоматически получает новый UUID и не наследует Spatial Link.
- [x] Если прежний экземпляр отсутствует, предлагаются `Это прежняя коллекция` и `Это новая копия`, причём новая копия является default.
- [x] Ошибка назначения/регистрации UUID оставляет коллекцию unbound и не создаёт частичный перенос.
- [x] ANKIGTA не запускает Anki и не переключает профиль.

## Tests

- [x] Real-Anki тесты двух профилей с одинаковым числовым `cardId`.
- [x] Restart/rename/copy/restore/import collision matrix.
- [x] Fault-injection атомарного UUID assignment и local registry update.

## Components

- Companion collection identity registry.
- Collection configuration.
- Bound collection settings/status UI.
