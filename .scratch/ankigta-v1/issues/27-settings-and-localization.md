# 27 — Settings and localization

**What to build:** Полный пользовательский settings path с authority по компонентам, validation/defaults и переключаемым Russian/English UI.

**Blocked by:** 03 — Connection config and reconnect; 12 — Full ANKIGTA Session; 20 — Minimal Review Mode; 22 — Activation Zone and automatic opening.

**Status:** in-progress

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [ ] Server owns world/study settings and Change History; client owns presentation/input/audio; add-on owns listener/token/Anki internals. Схема объявляет authority и покрыта тестами, но **ни один write path через неё не проходит**.
- [ ] Manual connection overrides remain side-local and excluded from Change History. Схема это выражает; настоящий писатель `connection_config.lua` её не спрашивает, и схема пока не различает, *чья* сторона сделала override.
- [ ] Radius, delay, speed, early-review policy, indicator, pause, protection and Close after rating use confirmed defaults/ranges. Значения и диапазоны заданы; хранилища, которое бы их применяло, нет.
- [ ] Invalid numeric input is rejected with localized reason, not silently clamped. Валидация написана и mutation-проверена, но нет ни одного пути ввода, который бы её вызывал.
- [~] Russian and English ship as UTF-8 resources; Russian Windows locale defaults Russian, otherwise English. Определение локали покрыто тестами; поведение на настоящей русской Windows — ручная проверка.
- [~] Language switches without resource restart. Механизм работает и покрыт тестами, но переведён только Review Mode: 34 строки остаются захардкожены в `f7.lua`, `study.lua`, `main.lua`, `map_identity.lua`, `connection_status.lua`, и 4 в самом `review_mode.lua`.
- [x] Missing translation falls back to English and logs diagnostics.
- [x] Card text, user Map Entity names, Entity Tag and Anki Tag are never automatically translated. Выполняется тем, что пользовательский контент вообще не проходит через перевод.
- [x] Stable stored technical values do not change with language.

## Tests

- [ ] Authority/persistence/restart tests for every setting. Authority выводится из схемы и покрыт для каждой настройки; persistence не существует, поэтому и не тестируется.
- [ ] Validation boundary and default migration tests. Границы покрыты; migration-кода и migration-тестов нет.
- [~] Localization completeness, runtime switch and fallback tests. Покрыто для `locale.lua`; «полнота» означает паритет ключей ru/en, а не переведённый интерфейс.

## Components

- Server/client/add-on settings stores.
- F7/Review Mode settings UI.
- UTF-8 localization system.

## Implementation status

**Not finished. `Status: in-progress`, and the criteria above are reset to what
is actually true.** A first pass shipped a schema and a string table, and the
ticket was briefly marked resolved on that basis. Code review showed the claim
did not survive contact with the code, so the status is corrected rather than
defended.

### What exists and works

- `shared/settings.lua` — one schema both sides load, with per-setting authority
  (ADR 0014), defaults, ranges and validation. Rejection carries a localization
  key and never clamps: a mistyped 200 quietly becoming 50 leaves the user with
  a setting they never chose. Authority and rejection are both mutation-checked.
- `shared/locale.lua` — Russian and English as UTF-8 tables, `auto` following
  `getLocalization().code` (shape verified in
  `CLuaFunctionDefs::GetLocalization`), switching at call time with no resource
  restart, fallback to English with a logged diagnostic, and a visible key when
  a string is missing in every language.
- Tests are derived from the schema rather than hand-listed, so a new setting
  cannot slip through untested.

### What is missing, and must be built before this ticket closes

1. **The settings stores.** `Settings.validate`, `canWrite` and
   `inChangeHistory` have **zero production call sites**. Nothing reads or
   writes a setting through the schema, and nothing persists one. Existing
   writers bypass it: `connection_config.lua` does its own port range check,
   and `Store.setUserSetting` validates only that the key is a string.
2. **The F7 / Review Mode settings UI.** There is none. No setting in the schema
   is reachable or changeable by a user, which is why "invalid input is
   rejected" currently has no input to reject.
3. **The rest of the localization.** Only Review Mode reads the locale, and even
   it still has 4 hard-coded strings; 34 remain across five other files.

### Defects fixed while correcting the claim

- `connectionPort` and `connectionToken` carried a `false` default that failed
  their own validation rules. They are now explicitly optional: the add-on
  publishes them or the user sets them, and inventing a default meant shipping a
  value the schema itself rejects. A schema-derived test now proves every
  non-optional default passes its own rule.
- `pauseOnReviewerOpen` was ticked as covered but absent from the schema.
- Two "the schema and the module agree" tests were tautological — the modules
  read the schema, so equality was guaranteed. They now change the schema and
  assert that the module follows.
- A UTF-8 test grepped the `.lua` file for a literal; it now reads what the
  interpreter actually holds.
- `Locale.userText` was an identity function with no callers, and its test
  asserted the identity of the identity function. Both removed: the rule is kept
  by never routing user content through translation, not by a no-op.

Automated evidence: `pytest -q tests/test_settings_and_locale.py` → 80 passed;
full suite 544 passed; mypy strict clean.

## Manual runtime checklist

See `docs/checklists/ticket27-settings-localization.md` (`Status: not run`).
