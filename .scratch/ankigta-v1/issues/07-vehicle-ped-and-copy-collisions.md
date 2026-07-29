# 07 — Vehicle, ped and copied-ID collisions

**What to build:** Расширить проверенный identity workflow на vehicle и ped и сделать clone/resource copy/Save As/map copy коллизии видимыми и неактивными до явного решения.

**Blocked by:** 06 — Object Pending Map Save.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Vehicle и ped проходят тот же Pending Map Save → stock Save → read-back lifecycle, что object.
- [ ] Duplicate map/entity IDs обнаруживаются до активации; все неоднозначные владельцы исключаются из study.
- [ ] Resource rename сохраняет прежнюю map identity и Spatial Link.
- [ ] Map/resource copy и Save As предлагают original/renamed versus new-copy decision.
- [ ] New copy получает новые map/entity IDs через stock Save и не наследует Spatial Link автоматически.
- [ ] Ошибка или несохранённое решение оставляет коллизию заблокированной, не переписывая `.map` в фоне.

## Tests

- [ ] Real Editor matrix object/vehicle/ped save/reopen/move/model edit.
- [ ] Clone, copyResource, renameResource, Save As и copied-resource collision tests.
- [ ] Restart/reload и ambiguous owner recovery tests.

## Components

- Map identity/collision coordinator.
- F7 copied-map decision UI.
- Stock Map Editor integration.

