# Result handoff: Prototype 0006 — MTA CEF card isolation

## Проверяемый вопрос

Может ли stock real MTA CEF сохранить поддерживаемую семантику Anki
HTML/CSS/JavaScript/media через отдельный read-only capability endpoint и
одновременно выполнить строгие bridge/navigation/popup/download/user-link
границы?

## Verdict

**`failed`**

Endpoint/capability модель прошла автоматическую часть, но полный CEF contract
не прошёл. После указания пользователя не использовать computer-use/реальные
клики real MTA client не запускался; такие сценарии честно оставлены
`not_run`/`source_only`. Независимо от этого source reference обнаружил три
решающих несовместимости.

## Решающие facts

1. `CCefApp::OnContextCreated` добавляет `window.mta` во все V8 contexts без
   local/remote проверки. `CWebViewAuth::HandleTriggerLuaEvent` отклоняет
   dispatch для remote browser через native `isLocal` guard. Privileged call
   не проходит, но строгая формулировка «карточка не получает MTA bridge»
   неверна для reference source.
2. `CWebView::OnBeforeBrowse` и `OnBeforeResourceLoad` используют один domain
   allow-state. Разрешив внешний домен для image/font/CSS/script, MTA также
   разрешает main-frame navigation на него. Lua notification не cancellable.
3. `CWebView::OnBeforePopup` всегда блокирует popup. Native `user_gesture`
   существует, но `Events_OnPopup` передаёт Lua только target/opener. Stock
   resource не может доказуемо открыть системный browser только для genuine
   click и заблокировать script-only equivalent.

Source tree — concurrently mutable `1.7-custom`, installed MTA —
`cefweb.dll 1.6.0.24124` с Chromium `144.0.7559.133`; это recorded mismatch.
Десять использованных source-файлов хешированы, повторно прочитаны verifier и
не изменились.

## Что прошло

- numeric `127.0.0.1` bind и Host check;
- 256-bit per-render capability;
- binding к collection/card/side/generation;
- 15 s expiry, close revocation, stale-generation rejection;
- bounded request set: 64 requests / 32 MiB unique bytes;
- HTML 4 MiB / media 16 MiB declared limits;
- identical Range retry;
- Range `206`, no-store/no-referrer/nosniff;
- missing-media placeholder/warning;
- uniform cross-card/side/expired/closed denial;
- four-request concurrency с observable `503` backpressure;
- no control dispatch, permanent connection token, Anki mutation или
  production ANKIGTA code;
- SHA-256 pre/post comparison: 1 708 watched external files, 0 changes;
- read-only verifier passes.

## S1–S20 summary

- `failed`: S7, S11, S13.
- `not_run`: S1, S2, S6, S19.
- `source_only`: S3.
- `partially_passed`: S4, S5, S12, S14, S15, S18.
- `passed_harness`: S8, S9, S10, S16, S17.
- `passed_source_scan`: S20.

## Опровергнутые предположения

- remote CEF означает отсутствие card-visible `mta` object;
- domain allowlist может разрешить external subresources, не разрешив тот же
  домен для main-frame navigation;
- Lua popup event достаточно, чтобы отличить genuine click от script open;
- блокировка popup сама по себе реализует системный browser handoff.

## Требуемое проектировочное решение

Не начинать production implementation текущего ADR 0010 contract без одного
из явных решений:

1. upstream/native MTA changes: no `mta` injection for remote contexts,
   cancellable per-frame navigation policy, trustworthy user-gesture handoff и
   explicit download deny;
2. ослабить продуктовый контракт и принять native-dispatch isolation при
   видимом stub, external navigation внутри child surface и отсутствие
   системного browser handoff;
3. запретить external subresources/user links в v1, явно изменив baseline.

Рекомендация: сохранить текущий security/product intent и завести отдельный
upstream/native MTA proof gate. Resource-level JS rewriting или возврат назад
после navigation не считать security boundary.

## Артефакты

- canonical report:
  `docs/prototypes/0006-cef-card-content-isolation.md`
- disposable source/evidence:
  `.scratch/0006-cef-card-content-isolation-prototype/`
- future real-MTA checklist:
  `.scratch/0006-cef-card-content-isolation-prototype/MANUAL-MTA-CHECKLIST.md`
- structured scenario matrix:
  `.scratch/0006-cef-card-content-isolation-prototype/evidence/scenarios.json`
- read-only verifier:
  `.scratch/0006-cef-card-content-isolation-prototype/verify_evidence.py`

Следующий шаг в главном проектировочном чате: сопоставить `failed` с ADR 0010,
confirmed baseline и preliminary audit, выбрать одно из трёх решений выше и
только затем продолжать спецификацию. Production-код не создавался.
