# 06 — Object Pending Map Save

**What to build:** Полный stock Map Editor путь для одного object: подготовить постоянные map/entity IDs и Spatial Link, сохранить штатной командой, выполнить независимый read-back и только затем активировать запись.

**Blocked by:** 05 — Admin-only F7 with one persisted Map Entity.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] `ankigtaMapId` представляется EDF custom child, а object identity — element data/EDF property.
- [x] До подтверждения Save запись имеет Pending Map Save и исключена из study/activation/statistics/markers.
- [x] ANKIGTA не редактирует `.map` напрямую или в фоне.
- [x] После штатного Save изменение обнаруживается, файл перечитывается независимо и однозначные IDs активируют запись.
- [x] `Проверить ещё раз` повторяет только read-back.
- [x] Close/reload без Save удаляет pending-запись с уведомлением; она не восстанавливается после restart.
- [x] Partial/ambiguous read-back оставляет состояние pending и не обещает atomic/external-conflict safety.

## Tests

- [ ] Real stock Map Editor Save/close/reopen test на disposable object/map — `not run`: MTA/GTA запрещено запускать в этой implementation-задаче.
- [x] Repository-local source-contract test отсутствия background `.map` write и hash-based наблюдателя.
- [x] Repository-local fault/source-contract tests: unsaved close, partial/ambiguous/interrupted save и manual recheck.

## Manual runtime checklist

Status: `not run`.

1. В отдельно разрешённой disposable-среде открыть stock Map Editor и карту с одним object.
2. Подготовить Spatial Link через ANKIGTA; убедиться, что F7 показывает `Pending Map Save`, а study/activation/statistics/markers недоступны.
3. До штатного Save сравнить SHA-256 `.map` с исходным: фоновая запись отсутствует.
4. Выполнить stock Save, дождаться независимого read-back и проверить переход в `Active Spatial Link`.
5. Закрыть и заново открыть карту; проверить те же `ankigtaMapId`, `ankigtaEntityId` и активную запись.
6. Повторить на disposable-копии для unsaved close, частичного/прерванного файла и неоднозначных IDs: состояние остаётся безопасно Pending либо удаляется только для неизменённого unsaved close; `Проверить ещё раз` не назначает ID и не пишет `.map`.
7. Сохранить журнал F7/уведомлений, pre/post SHA-256 карты и прочитанные из сохранённого XML IDs как evidence.

## Components

- MTA server Map Editor integration.
- EDF identity representation.
- F7 Pending Map Save UI.
- Map change observer/read-back validator.

## Answer

Реализован ограниченный тикетом 06 путь для одного object поверх stock Map Editor: EDF custom child для map identity, EDF property для object identity, memory-only `Pending Map Save`, hash-наблюдатель, независимый XML read-back, ручная повторная проверка и транзакционная активация Spatial Link только после однозначного подтверждения IDs.

Pending не сохраняется в SQLite и исключён из study/activation/statistics/markers. ANKIGTA не содержит вызовов прямой записи `.map`. Неизменённый close/reload удаляет pending с уведомлением; partial/ambiguous read-back сохраняет pending и честно сообщает ограничения stock Editor. Уже существующие несовпадающие постоянные IDs отклоняются до назначения новых значений.

Проверки выполнены только по исходникам, зафиксированным manual/source выводам и repository-local тестам. Реальный stock Map Editor сценарий оставлен `not run` в соответствии с environment boundary.
