# 07 — Vehicle, ped and copied-ID collisions

**What to build:** Расширить проверенный identity workflow на vehicle и ped и сделать clone/resource copy/Save As/map copy коллизии видимыми и неактивными до явного решения.

**Blocked by:** 06 — Object Pending Map Save.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Vehicle и ped проходят тот же Pending Map Save → stock Save → read-back lifecycle, что object.
- [x] Duplicate map/entity IDs обнаруживаются до активации; все неоднозначные владельцы исключаются из study.
- [x] Resource rename сохраняет прежнюю map identity и Spatial Link.
- [x] Map/resource copy и Save As предлагают original/renamed versus new-copy decision.
- [x] New copy получает новые map/entity IDs через stock Save и не наследует Spatial Link автоматически.
- [x] Ошибка или несохранённое решение оставляет коллизию заблокированной, не переписывая `.map` в фоне.

## Tests

- [x] Source-contract/local-fixture matrix plus a manual Editor object/vehicle/ped save/reopen/move/model-edit checklist left `not run`.
- [x] Clone, copyResource, renameResource, Save As и copied-resource collision tests.
- [x] Restart/reload и ambiguous owner recovery tests.

## Components

- Map identity/collision coordinator.
- F7 copied-map decision UI.
- Stock Map Editor integration.

## Comments

- Implemented the shared object/vehicle/ped Pending Map Save and independent
  read-back path, copied-ID collision blocking, copy decision flow, and
  supported-entity schema migration.
- Automated evidence: `pytest -q tests/test_mta_ticket_07.py
  tests/test_mta_ticket_06.py tests/test_mta_ticket_05.py` → 29 passed.
- Manual stock Map Editor/MTA runtime checklist remains `not run` per the
  repository MTA/GTA reference-only boundary.
