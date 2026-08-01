# 27 — Settings and localization

**What to build:** Полный пользовательский settings path с authority по компонентам, validation/defaults и переключаемым Russian/English UI.

**Blocked by:** 03 — Connection config and reconnect; 12 — Full ANKIGTA Session; 20 — Minimal Review Mode; 22 — Activation Zone and automatic opening.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] Server owns world/study settings and Change History; client owns presentation/input/audio; add-on owns listener/token/Anki internals. Каждая сторона теперь пишет только своё: `Store.setUserSetting` и `SettingsStore` отказывают в `wrong_authority`, клиентское хранилище не принимает серверную настройку ни из файла, ни из события, сервер больше не досылает `closeAfterRating`. Change History теперь тоже выводится из authority, а не из флага у каждой настройки: журналируется только серверное, потому что история — таблица в серверной SQLite, а undo не дотягивается до файла на машине игрока (ADR 0028). Клиентские настройки при этом сохраняются как и прежде — исключение из истории про отменяемость, не про долговечность.
- [x] Manual connection overrides remain side-local and excluded from Change History. Override штампуется стороной (`Settings.overrideBy`), чужой и неподписанный override отклоняются (`foreign_manual_connection_override`), а база отказывается его хранить (`not_a_stored_setting`).
- [x] Radius, delay, speed, early-review policy, indicator, pause, protection and Close after rating use confirmed defaults/ranges. Семь из восьми читаются, пишутся, переживают restart и берут default/диапазон из схемы: radius/delay/speed доезжают до клиентского `Activation`, indicator/protection/close-after-rating применяются клиентским хранилищем, early-review policy принадлежит серверу и переживает перезапуск. Восьмого — «pause» — в спецификации нет как настройки: пауза при открытии обычного Reviewer автоматическая и безусловная (ADR 0022, spec story 44), а `Начать обучение` / `Pause studying` — кнопка тикета 18, а не значение с default и диапазоном. Настройка `pauseOnReviewerOpen`, заведённая когда-то под этот пункт, удалена из схемы и локали: она обещала выключатель для инварианта, который выключать нельзя, и панель показывала бы переключатель, не делающий ничего.
- [x] Invalid numeric input is rejected with localized reason, not silently clamped. Отказ с ключом локализации возвращает каждый производственный путь записи (порт, БД, клиентский файл, серверный push), и теперь у него есть путь пользовательского ввода: панель валидирует до отправки, сервер — повторно на приёме, а повод едет обратно ключом и рисуется под строкой, которую отклонили.
- [~] Russian and English ship as UTF-8 resources; Russian Windows locale defaults Russian, otherwise English. Определение локали покрыто тестами; поведение на настоящей русской Windows — ручная проверка.
- [x] Language switches without resource restart. Весь интерфейс читает строки из `locale.lua`: F7 со всеми окнами подтверждения и Card Picker, Study, Review Mode, connection status и настройки подключения, HUD счётчиков. Окно, уже открытое в момент смены языка, перестраивается через `Locale.onChange` из снимка, который у него уже есть, — без перезапуска ресурса и без запроса к серверу. Серверные сообщения едут ключом, а не предложением: язык принадлежит клиенту, и переводит та сторона, которая рисует.
- [x] Missing translation falls back to English and logs diagnostics.
- [x] Card text, user Map Entity names, Entity Tag and Anki Tag are never automatically translated. Держится тем, что такой контент не проходит через перевод: `Locale.format` ищет только шаблон, а аргументы подставляет как есть и не ищет их в свою очередь. Тест передаёт в него две настоящие ключевые строки и убеждается, что они возвращаются буквально.
- [x] Stable stored technical values do not change with language. Состояния Spatial Link, режимы подключения и коды ошибок хранятся и сравниваются как есть; от языка зависит только их отображение. Тест смены языка проверяет, что кнопка Card Picker, которая гейтится на `"Unlinked"`, остаётся живой по-русски.

## Tests

- [x] Authority/persistence/restart tests for every setting. Наборы для restart выводятся из схемы (`keys_owned_by`), поэтому новая настройка ломает тест, пока её не покроют: 5 серверных через SQLite, 9 клиентских через клиентский файл, 2 connection — через connection file. Обе стороны стартуют через `onResourceStart` / `onClientResourceStart`, а список скриптов читается из `meta.xml`. Тем же способом выведена и принадлежность к Change History: тест перебирает всю схему и сверяет `inChangeHistory` с `authorityOf`, поэтому список нельзя разойтись с правилом второй раз.
- [~] Validation boundary and default migration tests. Границы покрыты, и покрыт случай «сохранённое значение больше не проходит текущую схему» — оно отбрасывается в default с диагностикой, на обеих сторонах. Настоящей migration (переписывания старых значений в новые) нет ни в коде, ни в тестах: в v1 нет ни одной версии схемы настроек, из которой было бы во что переписывать. Versioned migrations — предмет тикета 29, и первый настоящий тест на них появится там.
- [x] Localization completeness, runtime switch and fallback tests. «Полнота» больше не означает паритет ключей ru/en. `tests/test_localization.py` проверяет её с двух сторон: ни один скрипт, кроме `locale.lua`, не компилирует кириллическую строковую константу (читается таблица констант из `string.dump`, а не текст файла), и окна рисуются на обоих языках, а тексты контролов читаются обратно — строка, которая не доехала до контрола, не проходит, даже если лежит в таблице.

## Components

- Server/client/add-on settings stores.
- F7/Review Mode settings UI.
- UTF-8 localization system.

## Implementation status

**Finished in four passes.** A first pass shipped a schema and a string table,
and the ticket was briefly marked resolved on that basis. Code review showed the
claim did not survive contact with the code, so the status was corrected rather
than defended. A second pass built the stores, so the schema got production call
sites. A third pass translated the interface, so the string table got them too.
A fourth pass built the settings UI, and the three gaps the third pass had
written down — the UI itself, the Change History decision, and two settings
without a consumer — are what it closed.

The order mattered. The Change History defect was invisible while no user could
change a client-owned setting: the schema said `indicatorMode` was undoable,
nothing recorded it, and nothing ever asked. Building the panel is what made the
lie reachable, and fixing it is what closed the ticket.

### What exists and works

- `shared/settings.lua` — one schema both sides load, with per-setting authority
  (ADR 0014), defaults, ranges and validation. Rejection carries a localization
  key and never clamps: a mistyped 200 quietly becoming 50 leaves the user with
  a setting they never chose. Authority and rejection are both mutation-checked.
- `shared/locale.lua` — Russian and English as UTF-8 tables, `auto` following
  `getLocalization().code` (shape verified in
  `CLuaFunctionDefs::GetLocalization`), switching at call time with no resource
  restart, `Locale.onChange` for the windows that cannot re-read on their own,
  fallback to English with a logged diagnostic, and a visible key when a string
  is missing in every language.
- Tests are derived from the schema rather than hand-listed, so a new setting
  cannot slip through untested.

### The settings stores (built)

The schema now has production call sites on every side.

- `server/settings_store.lua` — reads, writes and re-reads on start everything
  the server owns. `Settings.writeKind` decides *where* a setting lives, so the
  store never learns a range: the six world/study settings go to SQLite through
  `Store.setUserSetting`, and the connection override goes to the connection
  file. `main.lua` loads it in `onResourceStart`, before anything reads a
  setting.
- `client/settings_store.lua` — the nine settings the player's machine owns,
  in a private client file written through the same candidate → verify →
  replace sequence the connection file uses, applied on load to `Indicator`,
  `Locale` and Review Mode. It refuses a server-owned setting whether it
  arrives from an edited file or from the server.
- `Store.setUserSetting` no longer checks only that the key is a string. It
  refuses an unknown setting, one this side does not own and one the schema
  rejects, and it records Change History only when `inChangeHistory` says so.
- `connection_config.lua` has no port range of its own. Reader and writer both
  ask the schema, so narrowing `connectionPort` in the schema narrows both.
- The server no longer sends `closeAfterRating` when it opens a card. The
  client owns it (ADR 0014) and reads it from its own store.
- A study request no longer carries the early-review policy past itself: it
  changes the setting the server owns, and the setting is what the companion is
  told — so a session started after a restart uses the same policy as the one
  before, and a request without a flag no longer silently means "no".
- The add-on cannot call a Lua schema, so a test reads `connectionPort`'s
  bounds out of it and holds `set_manual_connection` to exactly those. Without
  that, "the port range" is two numbers in two languages.

Whose side made an override is now part of the schema: `Settings.overrideBy`
stamps a record with its side and `overrideAppliesTo` answers whether it
governs a given side. A manual connection file stamped by another side, or not
stamped at all, is refused rather than adopted.

### The settings UI (built)

`client/settings_ui.lua` is one panel, opened from F7 and from Review Mode.
Review Mode swallows the game's hotkeys, F7 included, so a settings entry that
only existed on the F7 window would have been unreachable from the one screen
where a player most wants `Close after rating`.

- Rows come from `Settings.orderedKeys()`, not from a list in the UI. A setting
  missing from `Settings.order` is still drawn, sorted, after the ordered ones:
  forgetting to place a new setting is a layout mistake, and hiding it from the
  only screen that can change it would promote that mistake into an unreachable
  setting.
- Each row asks the schema what it is — number, toggle, choice, secret, opaque —
  so the panel has no per-setting code and no second copy of the ranges.
- The client edits client-owned settings in place through `ClientSettings`; the
  server-owned ones travel over four events (`requestSettings`,
  `settingsSnapshot`, `updateSetting`, `settingRejected`). The snapshot carries
  only what the server owns: the player's own settings never leave the machine,
  so the server has no value to answer with and does not invent one.
- Validation happens twice on purpose. The client checks so the user sees the
  reason next to the field they typed in; the server checks again because a
  value arriving over the wire has been checked by nothing this side owns.
- `includeInStudy` is per map, so it is a row per loaded map rather than one
  toggle — excluding one map must not take the Active Map Set with it.

### The three gaps the third pass left, and how each closed

1. **Change History for client-owned settings.** Resolved by ADR 0028: only
   what the server owns is journalled, and `inChangeHistory` now derives that
   from `authority` instead of repeating an `excludedFromHistory` flag per
   setting. The flag survives as the exception for a server setting that should
   not be journalled. Deriving it is what makes the defect unrepeatable — a new
   client setting cannot arrive claiming to be undoable while nothing records
   it. The settings themselves still persist in the client's own file and are
   re-applied on start; exclusion is about undo, not about durability.
2. **The F7 / Review Mode settings UI.** Built, above.
3. **Two settings with a store but no consumer.** `includeInStudy` kept its
   place: the panel writes it per map into `map_preferences` through
   `SettingsStore.setMapIncludeInStudy`, and the schema entry is what validates
   those writes and supplies the default a new map starts with — the first of
   the two outcomes this ticket allowed. `pauseOnReviewerOpen` took the second
   and left the schema. Pausing when Anki's Reviewer opens is automatic and
   unconditional (ADR 0022): the two study modes are mutually exclusive, so a
   switch that turns the pause off would offer the user a state the arbitration
   in tickets 17 and 18 exists to prevent. With the panel built it would have
   been worse than unused — a visible toggle wired to nothing.

### The localization (built)

The string table had no readers worth the name. Review Mode read four keys and
hard-coded four more sentences; the other 34 lived in `f7.lua`, `study.lua`,
`main.lua`, `map_identity.lua` and `connection_status.lua`, and every English
label in F7 was hard-coded too — so a Russian player got a Russian settings
schema and an English window.

- `shared/locale.lua` now carries the whole interface: F7 and its confirmation
  windows, the Card Picker, Study, Review Mode, connection status and settings,
  and the counter HUD. `Locale.format` fills placeholders from the template,
  never the other way round.
- `connection_status.lua` had its own two-language table and its own
  `getLocalization()` call. Both are gone: one language setting, not one per
  module, or changing it moves the rest of the interface and leaves the
  connection lines behind.
- The server sends a key and the outcome code, never a sentence. Language is a
  client-owned setting (ADR 0014), so only the client knows which language to
  render, and `map_identity.lua` publishes `guidanceKey` rather than guidance.
- A window writes its labels once, when the control is built, so `Locale.onChange`
  tells the modules that hold text on screen to rebuild — from the snapshot they
  already have, so a disconnected client relabels too. Without that, "switching
  needs no restart" would have meant "switching needs no restart, but close
  every window first".
- Review Mode stores the key and its arguments, not finished text, so a warning
  already on screen follows a switch to the next frame.
- `statistics.total`/`new`/`learning`/`due`/`early` had no call site at all
  while the HUD spelled them out in English. They have one now.
- What stays untranslated is unchanged and is now checked: card text, Map Entity
  names, Entity Tags and Anki Tags are arguments to `Locale.format` and are never
  looked up; link states, connection modes and error categories keep their stored
  technical value, and only their display follows the language.

### Harness work the localization needed

`tests/lua/` could not create a control, so no test had ever read what an F7
window says. It now stubs `gui*` with MTA's indexing (rows from 0, columns from
1, `-1` for no selection), records each control's text, destroys children with
their window as CEGUI does, and records `dxDrawText`.

`tests/lua/constants.py` dumps a script through the same Lua 5.1 interpreter and
walks the string constants out of the bytecode, so "no hard-coded Russian" is
decided by the constant table the compiler produced rather than by a grep that
sees comments and misses concatenation. Nine source-text assertions in the older
ticket tests were pointed at the key the call site now looks up, and four were
replaced by running the window.

### Defects fixed while correcting the claim

- `connectionPort` and `connectionToken` carried a `false` default that failed
  their own validation rules. They are now explicitly optional: the add-on
  publishes them or the user sets them, and inventing a default meant shipping a
  value the schema itself rejects. A schema-derived test now proves every
  non-optional default passes its own rule.
- `pauseOnReviewerOpen` was ticked as covered but absent from the schema. Adding
  it turned out to be the wrong repair: the fourth pass removed it instead,
  because ADR 0022 makes the pause unconditional and a setting cannot offer to
  switch off an invariant.
- Eight client-owned settings claimed to be undoable and were recorded nowhere
  (ADR 0028). The claim was true of the schema and false of the code from the
  moment the stores were built; it stayed invisible until the panel gave a user
  a way to change them.
- Two "the schema and the module agree" tests were tautological — the modules
  read the schema, so equality was guaranteed. They now change the schema and
  assert that the module follows.
- A UTF-8 test grepped the `.lua` file for a literal; it now reads what the
  interpreter actually holds.
- `Locale.userText` was an identity function with no callers, and its test
  asserted the identity of the identity function. Both removed: the rule is kept
  by never routing user content through translation, not by a no-op.

### Harness work this needed

`tests/lua/` could not open a file, so `connection_config.lua` had never been
executed by a test at all — only grepped. It now has the resource file API
(`fileOpen` fails on a missing file, `fileCreate` truncates, `fileRename`
refuses an existing destination), `hash()` returning **lowercase** hex where
`sha256()` returns uppercase, and accounts/ACL rights, all taken from the MTA
source rather than from memory. Both sides can now be started the way MTA
starts them, with the script list read out of `meta.xml`.

### Harness work the settings UI needed

`tests/lua/sandbox.py` could create a control but not click one: its
`addEventHandler` dropped the element a handler was attached to, so every click
went to every handler. Controls now record their position, handlers remember
their element, and a click can name one. Without that, "the panel rejects an
out-of-range radius" could only have been asserted about the panel as a whole.

Automated evidence: `pytest -q tests/test_settings_stores.py` → 56 passed;
`tests/test_settings_and_locale.py` → 92 passed; `tests/test_settings_ui.py` →
38 passed; `tests/test_localization.py` → 49 passed, 1 skipped (`locale.lua` is
where the Russian lives); full suite 777 passed, 1 skipped; mypy clean on its
configured scope (17 files). Each load-bearing test was mutation-checked:
breaking the authority gate, the range lookup, the history predicate, the
override side, the normalizer, the rollback, the server's push, the
language-change notification, the placeholder substitution or the guidance key
makes a test fail, and planting one Russian literal back into `f7.lua` fails
both the constant guard and the render test. Restoring the old history rule
(`excludedFromHistory ~= true`) fails six tests, five of them naming the setting
that would start lying again.

### Merged with ticket 28

Панель переехала на менеджер раскладки тикета 28: она больше не зовёт
`guiGetScreenSize()` и не пишет `uiPlacement` сама — размещение хранит
менеджер, долей экрана. Оттуда же в неё пришёл блок под строкой `uiScale`:
шаги ±0.05, `Edit HUD layout` и `Reset UI layout` — действия над раскладкой, а
не значения схемы, поэтому они строки этой панели, а не второе окно с тем же
масштабом.

## Manual runtime checklist

See `docs/checklists/ticket27-settings-localization.md` (`Status: not run`).
