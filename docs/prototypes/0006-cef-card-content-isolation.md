# Prototype 0006 — MTA CEF card-content isolation

Дата: 2026-07-29  
Итоговый verdict: **`failed`**

## Короткий ответ

Полный контракт из handoff не подтверждён. Disposable read-only content
endpoint и короткоживущие render capabilities работают в автоматическом
harness, но доступный source reference stock MTA противоречит трём обязательным
границам:

1. render-process без проверки local/remote добавляет `window.mta` в каждый V8
   context. Browser-process затем безопасно отбрасывает `TriggerLuaEvent` для
   remote browser, поэтому привилегированный вызов не проходит, но строгое
   обещание «card JavaScript вообще не получает MTA bridge» не выполнено.
2. Один domain allow-state разрешает и external subresources, и main-frame
   navigation. Lua получает `onClientBrowserNavigate` как уведомление после
   native решения и не может отменить переход до запроса.
3. `OnBeforePopup` всегда блокирует popup. CEF передаёт native параметр
   `user_gesture`, но MTA не передаёт его в Lua popup event. Disposable resource
   поэтому не может доказуемо открыть системный браузер только для genuine user
   click и отличить его от script-only `window.open`.

После явного указания пользователя не применять computer-use/реальные клики
MTA client не запускался. Это означает, что fidelity, playback, focus,
downloads, lifecycle и system-browser поведение не могут считаться
проверенными. Отсутствующие наблюдения не повышены до `passed`.

## Проверяемый вопрос

Может ли настоящий MTA CEF семантически эквивалентно отображать поддерживаемые
Anki HTML/CSS/JavaScript/media через отдельный read-only loopback content
endpoint, не предоставляя карточке MTA/control privileges, и одновременно
надёжно ограничивать capability, navigation, popup и downloads?

Успех требовал выполнения всех S1–S20. Наличие решающих `failed` и обязательных
`not_run` даёт общий `failed`.

## Среда и provenance

| Компонент | Наблюдаемое значение |
| --- | --- |
| OS | Windows 11 Pro `10.0.26200`, build 26200, AMD64 |
| MTA launcher | file version `1.24103.0.0`, SHA-256 `9754dff6…31e07` |
| installed `cefweb.dll` | `1.6.0.24124`, SHA-256 `edc883d3…98277` |
| installed `CEFLauncher_DLL.dll` | `1.6.0.24124`, SHA-256 `99f976bf…987f` |
| installed CEF/Chromium | `144.0.13+g9f739aa+chromium-144.0.7559.133`, SHA-256 `0d6700ac…3091` |
| harness | CPython 3.14.6, stdlib `ThreadingHTTPServer`, prototype version 0 |
| source reference | concurrently mutable MTA `1.7-custom` tree; 10 individually read files, per-file SHA-256/read time retained |

Source reference и installed MTA build не совпадают по версии. Поэтому source
results являются сильными архитектурными ограничениями и основанием для
отрицательного prototype verdict, но не заменяют runtime-наблюдение installed
1.6 build. Повторное чтение verifier подтвердило неизменность всех 10
использованных reference-файлов.

## Safety и область изменений

Весь disposable source, corpus и evidence находится под:

```text
.scratch/0006-cef-card-content-isolation-prototype/
```

Исключения — только этот канонический отчёт и result handoff. MTA/GTA/Anki не
запускались, installer не использовался, Anki profiles не открывались,
production ANKIGTA code не создавался.

До и после автоматического запуска побайтово проверены 1 708 файлов:

- installed MTA executables, CEF, client config/log;
- известные MTA resources;
- Anki `prefs21.db` и обе найденные `collection.anki2`;
- `gta_sa.set`;
- `AGENTS.md`, `CONTEXT.md`, ADR и design documents.

Изменений: **0**. Source tree оставался read-only; build/test/cache/Git
операции в нём не выполнялись.

## Capability contract

До тестов объявлено:

- 256 бит случайности (`secrets.token_urlsafe(32)`);
- bind только `127.0.0.1` и проверка numeric Host;
- identity: collection + card ID + side + generation;
- lifetime 15 секунд;
- один render — максимум 64 GET/HEAD request и 32 MiB unique bytes;
- HTML ≤ 4 MiB, individual media ≤ 16 MiB;
- одинаковый normalized retry разрешён и не тратит unique-byte budget повторно;
- close, expiry и новая generation дают одинаковый non-enumerating denial;
- endpoint не имеет rating/scheduler/collection/session dispatch;
- `Cache-Control: no-store`, `Referrer-Policy: no-referrer`,
  `X-Content-Type-Options: nosniff`;
- максимум четыре одновременно обслуживаемых запроса.

Измеренный endpoint smoke-run:

| Проверка | Результат |
| --- | --- |
| HTML document | `200`, 1.942 ms |
| Unicode/space SVG path | `200`, 1.697 ms |
| missing media | placeholder SVG + `X-ANKIGTA-Warning: missing-media` |
| Range | `206`, ровно 1024 bytes, 1.268 ms |
| identical Range retry | request count вырос, unique-byte budget не вырос |
| POST render | `405` до dispatch |
| control path | `405` до dispatch |
| guessed/cross-side/cross-card | uniform denial |
| stale generation / close / expiry | uniform `404` |
| per-media limit | `413` |
| request budget | `200`, `200`, затем `429` |
| concurrency | 5 bounded `206`, 7 backpressure `503`, identity mix отсутствует |

Это характеристики disposable Python harness, не performance SLA MTA/CEF.

## Corpus

Versioned `corpus.json` содержит 13 групп: plain/Unicode, Anki front/back CSS,
layout/fonts/pseudo-elements/animation, safe JavaScript, local media,
relative/escaped/Unicode names, side audio/autoplay, script-heavy template,
external resources, missing media, large content, adversarial
popup/navigation/download/bridge fixtures и unsafe static preview.

Reference screenshot/DOM/computed-style capture не выполнялся. Поэтому corpus
готов к будущему real-MTA прогону, но сам по себе не доказывает fidelity.

## S1–S20

| ID | Verdict | Факт |
| --- | --- | --- |
| S1 | `not_run` | Real MTA CEF не запускался. |
| S2 | `not_run` | Нет MTA/reference screenshots, DOM/styles/layout comparison. |
| S3 | `source_only` | Remote JavaScript поддерживается при включённой MTA setting; runtime interaction не наблюдался. |
| S4 | `partially_passed` | MIME/relative/Unicode/Range endpoint прошли; playback events в MTA не проверены. |
| S5 | `partially_passed` | Placeholder/warning прошёл; Review Mode/rating UI не наблюдался. |
| S6 | `not_run` | External image/font/CSS/script в MTA не загружались. |
| S7 | **`failed`** | `window.mta` видим в каждом V8 context; remote native dispatch блокируется, но strict no-bridge exposure нарушен. |
| S8 | `passed_harness` | Content endpoint только GET/HEAD; control/mutation attempts не dispatch-ятся. |
| S9 | `passed_harness` | Cross-card/side/generation/closed/expired misuse отклонён одинаково. |
| S10 | `passed_harness` | Bounded render set, retry, expiry и close revocation прошли. |
| S11 | **`failed`** | Domain permission не отделяет main navigation от subresource; Lua event не cancellable. |
| S12 | `partially_passed` | Popup native-кодом блокируется; download policy runtime не доказана. |
| S13 | **`failed`** | `user_gesture` теряется до Lua; genuine click нельзя доказуемо отличить от script-only. |
| S14 | `partially_passed` | Static preview identity отдаёт безопасный preview, control API отсутствует; MTA UI не наблюдался. |
| S15 | `partially_passed` | Endpoint limits/Range/chunked writes есть; CEF memory/paint/cancel не измерены. |
| S16 | `passed_harness` | Generation invalidation и no-store/no-referrer прошли. |
| S17 | `passed_harness` | Bounded concurrency/backpressure без identity mix прошли. |
| S18 | `partially_passed` | Endpoint failure bounded; closable Review Mode/rating block/recovery не наблюдались. |
| S19 | `not_run` | Esc/focus/resource/reconnect требуют real MTA client. |
| S20 | `passed_source_scan` | Нет control gateway, permanent connection token, Anki mutation или production ANKIGTA code; external hashes совпали. |

## Observed facts, inferences и unproved boundaries

Наблюдаемые facts:

- render-process source создаёт `window.mta` без local/remote condition;
- browser-process проверяет `isLocal` и отклоняет remote TriggerLuaEvent;
- remote JavaScript включается отдельной setting;
- domain allow-state используется для navigation и resource load;
- popup всегда блокируется;
- native `user_gesture` не входит в Lua popup event;
- endpoint/capability и cleanup invariants прошли verifier.

Inference:

- отдельный remote browser сохраняет Lua/dx Review Mode shell, даже если его
  собственный main frame ушёл на внешний URL;
- немедленная загрузка safe document после `onClientBrowserNavigate` является
  recovery, а не блокировкой до внешнего запроса;
- naming/stub `mta` не даёт привилегию из-за native `isLocal` guard, но требует
  изменить строгое продуктовое утверждение либо MTA native behavior.

Не доказано:

- совпадает ли installed 1.6 behavior с 1.7-custom reference;
- semantic/pixel fidelity;
- audio/video/autoplay;
- downloads и filesystem effects;
- focus/Esc/resource/reconnect lifecycle;
- real request fan-out, CEF memory и first paint;
- genuine click и системный браузер.

## Решения для главного проектировочного чата

До production implementation необходимо выбрать одно:

1. Изменить принятый контракт: допустить card-visible `window.mta` stub при
   доказанном native remote-dispatch denial, допустить external navigation
   внутри child surface и отказаться от automatic system-browser opening.
2. Получить upstream/native MTA changes:
   - не inject `mta` в remote browser contexts;
   - отдельная cancellable main-frame policy, не связанная с subresource
     allowlist;
   - передача trustworthy `user_gesture` либо native system-browser action;
   - явный download deny handler.
3. Запретить external subresources/user links для v1. Это противоречит текущему
   baseline и требует явного продуктового решения, а не скрытой фильтрации.

Resource-level naming checks, `onClientBrowserNavigate` recovery и JavaScript
rewriting не следует принимать как достаточную security isolation.

## Reproduction и verifier

```powershell
& .\.scratch\0006-cef-card-content-isolation-prototype\run.ps1
python .\.scratch\0006-cef-card-content-isolation-prototype\verify_evidence.py
```

Канонический verifier:

```text
evidence verification result: passed
overall verdict: failed
S1-S20 entries: 20
decisive failures: S7, S11, S13
external isolation: passed
source reference unchanged: yes
```

Manual real-MTA completion checklist сохранён рядом с prototype. Read-only
verifier не создаёт и не изменяет файлы.
