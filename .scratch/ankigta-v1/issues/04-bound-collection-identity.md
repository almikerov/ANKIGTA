# 04 — Bound Anki Collection identity

**What to build:** Устойчивую Anki Card Identity через add-on-owned collection UUID, выбор одной Bound Anki Collection и Collection Copy Decision для копии, переноса или восстановления.

**Blocked by:** 01 — Companion health and Anki version.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Collection UUID создаётся атомарно в collection config и переживает restart и profile rename.
- [ ] Profile name/path и один `cardId` нигде не принимаются за устойчивую Anki Card Identity.
- [ ] Пользователь явно выбирает одну Bound Anki Collection; другая открытая коллекция даёт paused/wrong-collection state.
- [ ] Если прежний экземпляр UUID зарегистрирован локально, дубликат автоматически получает новый UUID и не наследует Spatial Link.
- [ ] Если прежний экземпляр отсутствует, предлагаются `Это прежняя коллекция` и `Это новая копия`, причём новая копия является default.
- [ ] Ошибка назначения/регистрации UUID оставляет коллекцию unbound и не создаёт частичный перенос.
- [ ] ANKIGTA не запускает Anki и не переключает профиль.

## Tests

- [ ] Real-Anki тесты двух профилей с одинаковым числовым `cardId`.
- [ ] Restart/rename/copy/restore/import collision matrix.
- [ ] Fault-injection атомарного UUID assignment и local registry update.

## Components

- Companion collection identity registry.
- Collection configuration.
- Bound collection settings/status UI.

