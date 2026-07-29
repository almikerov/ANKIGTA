# 06 — Object Pending Map Save

**What to build:** Полный stock Map Editor путь для одного object: подготовить постоянные map/entity IDs и Spatial Link, сохранить штатной командой, выполнить независимый read-back и только затем активировать запись.

**Blocked by:** 05 — Admin-only F7 with one persisted Map Entity.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] `ankigtaMapId` представляется EDF custom child, а object identity — element data/EDF property.
- [ ] До подтверждения Save запись имеет Pending Map Save и исключена из study/activation/statistics/markers.
- [ ] ANKIGTA не редактирует `.map` напрямую или в фоне.
- [ ] После штатного Save изменение обнаруживается, файл перечитывается независимо и однозначные IDs активируют запись.
- [ ] `Проверить ещё раз` повторяет только read-back.
- [ ] Close/reload без Save удаляет pending-запись с уведомлением; она не восстанавливается после restart.
- [ ] Partial/ambiguous read-back оставляет состояние pending и не обещает atomic/external-conflict safety.

## Tests

- [ ] Real stock Map Editor Save/close/reopen test на disposable object/map.
- [ ] Hash-based тест отсутствия background `.map` write.
- [ ] Fault tests unsaved close, partial file, interrupted save и manual recheck.

## Components

- MTA server Map Editor integration.
- EDF identity representation.
- F7 Pending Map Save UI.
- Map change observer/read-back validator.

