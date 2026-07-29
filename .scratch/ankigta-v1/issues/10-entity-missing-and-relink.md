# 10 — Entity missing and Relink entity

**What to build:** Сохранять связь и метаданные исчезнувшей из карты Map Entity и переносить их на выбранную незанятую Map Entity через Relink entity.

**Blocked by:** 07 — Vehicle, ped and copied-ID collisions; 08 — Card Picker and first Spatial Link.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Entity missing создаётся только при отсутствии persisted Map Entity, а не при destruction/unstreamed Runtime Instance.
- [ ] Missing-запись сохраняет Spatial Link, name, Entity Tag, radius и `Show radius`.
- [ ] Relink target выбирается из незанятых Map Entity через F7 list или Pick Entity.
- [ ] Target сохраняет свои `ankigtaMapId`/entity ID; старая identity ему не присваивается.
- [ ] Confirmation сравнивает переносимые метаданные; после успеха старая active missing-запись исчезает без дубликата.
- [ ] Операция атомарна в server storage и предоставляет reversible change для будущего Change History.

## Tests

- [ ] Map edit/reload → Entity missing → Relink end-to-end test.
- [ ] Cross-map/interior/dimension target tests.
- [ ] Occupied target, failed transaction и restart consistency tests.

## Components

- Server Map Entity/Spatial Link model.
- F7 missing/relink workflow.
- Pick Entity integration seam.
