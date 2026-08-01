# 10 — Entity missing and Relink entity

**What to build:** Сохранять связь и метаданные исчезнувшей из карты Map Entity и переносить их на выбранную незанятую Map Entity через Relink entity.

**Blocked by:** 07 — Vehicle, ped and copied-ID collisions; 08 — Card Picker and first Spatial Link.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Entity missing создаётся только при отсутствии persisted Map Entity, а не при destruction/unstreamed Runtime Instance.
- [x] Missing-запись сохраняет Spatial Link, name, Entity Tag, radius и `Show radius`.
- [x] Relink target выбирается из незанятых Map Entity через F7 list или Pick Entity.
- [x] Target сохраняет свои `ankigtaMapId`/entity ID; старая identity ему не присваивается.
- [x] Confirmation сравнивает переносимые метаданные; после успеха старая active missing-запись исчезает без дубликата.
- [x] Операция атомарна в server storage и предоставляет reversible change для будущего Change History.

## Tests

- [ ] Map edit/reload → Entity missing → Relink end-to-end test (manual runtime: not run).
- [ ] Cross-map/interior/dimension target tests (manual runtime: not run).
- [ ] Occupied target, failed transaction и restart consistency tests (manual runtime: not run).

## Components

- Server Map Entity/Spatial Link model.
- F7 missing/relink workflow.
- Pick Entity integration seam.

## Comments

- Implemented repository-local Entity missing detection from saved map XML,
  persistent metadata/presence state, F7 list and Pick Entity Relink workflow,
  metadata preview, target identity preservation, atomic Spatial Link transfer,
  and a reversible Change History payload.
- Ticket-local checks: `pytest -q tests/test_mta_ticket_10.py` → 5 passed.
  Blocking-edge checks for tickets 07/08 and Card Picker → 22 passed.
- Full suite was attempted; unrelated pre-existing failures remain in the
  integration harness and stale ticket 05/09 source-contract checks.
- Real MTA/Map Editor scenarios remain `not run` under the repository runtime
  boundary; see `docs/checklists/ticket10-entity-missing-relink.md`.
