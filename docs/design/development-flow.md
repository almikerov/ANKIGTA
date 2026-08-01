# ANKIGTA development flow

> This is the recommended command path from the current empty repository. Do not jump directly from the preliminary spec to `/implement`.
>
> Send each prompt below together with its slash-command in the same message. Replace text in `<angle brackets>` with the relevant file or prototype question.

## Chat map

| Phase | Where it happens | Context rule |
| --- | --- | --- |
| Repository setup | **This current design chat** | Run once; remain here afterward |
| Product interview | **This current design chat** | Continue the existing `/grill-with-docs` interview |
| Each technical prototype | **A separate new chat for each prototype** | Enter with a handoff file; do not mix prototype code into the design chat |
| Incorporating prototype findings | **Return to this current design chat** | Reference the handoff produced by the prototype chat |
| `/to-spec` and `/to-tickets` | **This current design chat** | Keep the accumulated design context intact through both commands |
| Each implementation ticket | **A separate new chat for that ticket** | One fresh chat per ticket; provide the ticket file |
| Independent code review, if requested | **A separate new chat** | Review against a fixed commit or merge-base |

Do not use `/compact` in this chat during grilling, specification, or ticket creation. If this chat approaches its context limit, use `/handoff`, open one replacement design chat, and treat that replacement as the new main design chat.

## 0. Configure the repository once — this current chat

Send:

```text
/setup-matt-pocock-skills

Настрой текущий репозиторий ANKIGTA для дальнейшей работы engineering skills.
Репозиторий новый, удалённого issue tracker пока нет. Рекомендуй local Markdown
под .scratch, стандартные triage labels и single-context domain docs.
Сначала покажи предлагаемые файлы и изменения, а записывай их только после
моего подтверждения. Если нужно выбрать между AGENTS.md и CLAUDE.md, спроси меня.
```

The setup skill requires confirmation before writing. After setup, stay in this chat.

## 1. Finish product and architecture decisions — this current chat

The interview is already running. If it needs to be invoked again in this chat, send:

```text
/grill-with-docs

Продолжай качественное проектирование ANKIGTA с текущего состояния.
Сначала прочитай CONTEXT.md, docs/adr/, docs/design/confirmed-baseline.md и
docs/design/preliminary-spec-audit.md. Старый ANKIGTA_SPEC.md используй только
как предварительное сырьё, а не как источник истины.

Не начинай интервью с нуля и не повторяй подтверждённые вопросы. Задавай строго
по одному самому важному нерешённому вопросу, всегда давай свою рекомендацию и
жди моего ответа. Подтверждённые термины и решения сразу записывай в проектные
документы. Не начинай реализацию, пока я явно не подтвержу общее понимание.
```

Update `CONTEXT.md` when terminology becomes precise and add an ADR only for an expensive, surprising trade-off.

## 2. Prove risky technical assumptions — one new chat per prototype

Use this four-step sequence for every independent proof.

### 2.1 Prepare the prototype handoff — this current design chat

Send:

```text
/handoff

Подготовь handoff для отдельного технического прототипа:
<точный проверяемый вопрос прототипа>.

Включи только необходимый контекст, принятые ограничения, критерий успешности,
сценарии проверки и ссылки на соответствующие ADR. Прототип должен дать решение,
а не создавать производственный код ANKIGTA.
```

### 2.2 Run the prototype — a new chat

Open a new chat in the same ANKIGTA folder, attach or reference the handoff file produced above, then send:

```text
/prototype

Используй приложенный handoff. Создай одноразовый прототип, который отвечает
только на вопрос: <точный проверяемый вопрос>.

Сначала сформулируй наблюдаемый критерий успеха. Затем реализуй минимальную
проверку, запусти её и зафиксируй фактические результаты и ограничения.
Не строй производственную архитектуру и не расширяй объём задачи.
Сохрани выводы в Markdown-файле внутри репозитория.
```

### 2.3 Return the result — the same prototype chat

At the end of the prototype chat, send:

```text
/handoff

Подготовь handoff обратно в основной проектировочный чат ANKIGTA.
Зафиксируй проверяемый вопрос, фактический результат, доказательства,
неподтвердившиеся предположения, ограничения и решения, которые теперь можно
принять. Отдели выводы от одноразового кода прототипа.
```

### 2.4 Incorporate the result — return to this current design chat

Reference the resulting handoff file and send:

```text
/grill-with-docs

Прими результаты приложенного прототипа обратно в проектирование ANKIGTA.
Сопоставь их с CONTEXT.md, ADR и confirmed-baseline. Обнови документы, явно
отметь опровергнутые предположения и продолжи интервью с одного самого важного
оставшегося решения. Не начинай реализацию.
```

Recommended prototype questions, in order:

1. **Completed — failed on Anki 26.05:** `<Может ли companion add-on открыть точную карточку и применить её оценку ровно один раз после повторного запроса?>`
2. **Completed — passed on Anki 26.05:** `<Может ли настоящая rescheduling filtered deck штатно сделать целевую карточку scheduler-top и сохранить корректное поведение FSRS для new, learning, relearning, review, suspended, buried и досрочных повторений?>`
3. **Completed — partially passed on Anki 26.05:** `<Может ли companion add-on через поддерживаемые механизмы Anki безопасно переключать Bound Anki Collection, немедленно закрывать стандартный Reviewer и после перезапуска завершать Review Transaction ровно один раз до восстановления filtered deck?>` Durable recovery passed; supported profile switching and safe immediate in-flight Reviewer cleanup did not.
4. **Completed — partially passed on Windows 11 / MTA Server 1.6 build 24124:** `<Может ли server-side Lua MTA надёжно обмениваться локальными HTTP-запросами с companion add-on на loopback?>` Numeric IPv4 loopback and the required transport/recovery scenarios passed; IPv6 `::1` was incompatible, production config publication and transport limits remain unproved, and a post-run installer safety deviation kept the overall verdict partial.
5. **Completed — failed; product fallback accepted:** `<Можно ли безопасно записывать ID карт и сущностей через Map Editor, обнаруживать копии и восстанавливаться после сбоя сохранения?>` v1 will use the stock MTA Map Editor without a fork. It accepts non-atomic save and missing external-conflict protection, while keeping duplicate blocking, Pending Map Save and post-save read-back as ANKIGTA responsibilities.
6. **Completed — failed; product fallback accepted:** `<Можно ли изолировать сложный или враждебный HTML/CSS/JavaScript/media карточки в CEF без доступа к MTA bridge?>` The disposable endpoint/capability model passed its harness. v1 will use stock MTA without a native fork: it accepts the non-privileged `window.mta` stub and child-surface navigation coupled to external-resource permissions, and drops the system-browser handoff promise.

Prototype code is disposable; only its evidence and conclusions return to the design chat. If the decision map expands beyond one manageable context, use `/wayfinder`.

## 3. Produce the buildable specification — this current design chat

After the user explicitly confirms shared understanding and all mandatory prototype gates have answers, send:

```text
/to-spec

Создай новую реализационно готовую спецификацию ANKIGTA на основе текущего
CONTEXT.md, принятых ADR, confirmed-baseline и результатов прототипов.

Старый ANKIGTA_SPEC.md не исправляй и не используй как источник истины.
У каждого поведения должны быть проверяемые acceptance criteria; открытые
вопросы и неподтверждённые технические предположения не маскируй под решения.
Спецификация должна явно описывать границы v1, состояния ошибок, восстановление,
поддерживаемые версии и исключённые возможности.
```

Do not open a new chat between `/to-spec` and `/to-tickets`.

## 4. Split work into blocker-aware tickets — this current design chat

Send:

```text
/to-tickets

Разбей утверждённую спецификацию ANKIGTA на небольшие tracer-bullet tickets.
Для каждого тикета укажи цель, наблюдаемое поведение, acceptance criteria,
необходимые тесты, затрагиваемые компоненты и явные blocking edges.

Сохрани тикеты по правилам настроенного issue tracker. Не создавай один общий
тикет и не включай необязательную полировку в критический путь v1.
```

Recommended tracer-bullet sequence:

1. Local companion health/profile endpoint.
2. Durable exactly-once review transaction.
3. MTA server gateway.
4. One persisted Map Entity linked to one study target.
5. Minimal question → answer → rating loop.
6. Filtered-deck queue and next-card selection.
7. Map identity/writeback and recovery.
8. F7 management interface.
9. Spatial zones, HUD, marker and dynamic entities.
10. Media/template isolation, settings, diagnostics and performance.

After `/to-tickets` completes, the main design chat has finished its job.

## 5. Implement — one new chat per ticket

For each unblocked ticket, open a fresh chat in the ANKIGTA folder, attach or reference that ticket file, then send:

```text
/implement

Реализуй только приложенный тикет ANKIGTA и соблюдай его blocking edges.
Перед работой прочитай AGENTS.md, CONTEXT.md, релевантные ADR, спецификацию и
сам тикет. Обязательно соблюдай `docs/agents/mta-gta-reference-policy.md`:
проверяй программно, запускать одноразовые копии можно, управлять GUI через
скриншоты и синтетический ввод нельзя, установленный MTA/GTA не изменяй.
Проверки, которые может увидеть только человек, оставляй `not run` с точным
ручным checklist.
Работай test-first небольшими red-green-refactor шагами. Не реализуй соседние
тикеты и не меняй подтверждённые продуктовые решения.

В конце выполни проверки из тикета и code review относительно исходной точки.
Не коммить изменения, если acceptance criteria не выполнены.
```

Do not implement two tickets in one chat. `/implement` should drive `/tdd` internally and finish with `/code-review`.

## 6. Replace a full design chat

In the design chat that is becoming too full, send:

```text
/handoff

Сохрани текущее состояние проектирования ANKIGTA для продолжения в новом чате:
цель, подтверждённые решения, изменённые документы, результаты прототипов,
незавершённые вопросы, риски и точный следующий шаг. Не пересказывай
нерелевантную историю.
```

Open a new chat in the same folder, attach the handoff, and send:

```text
/grill-with-docs

Продолжи основной проектировочный поток ANKIGTA из приложенного handoff.
Прочитай указанные в нём CONTEXT.md, ADR и рабочие документы. Не начинай
интервью заново, не повторяй закрытые вопросы и не начинай реализацию.
Задай один самый важный оставшийся вопрос со своей рекомендацией.
```

This new chat now becomes the main design chat.

## 7. Replace an unfinished implementation chat

In the old implementation chat, create a handoff using:

```text
/handoff

Сохрани состояние реализации текущего тикета ANKIGTA: acceptance criteria,
изменённые файлы, завершённые и падающие тесты, принятые технические решения,
оставшиеся шаги и точную исходную точку для code review.
```

Open a new chat in the same folder, attach both the ticket and handoff, then send:

```text
/implement

Продолжи только приложенный тикет ANKIGTA из приложенного handoff.
Сначала прочитай AGENTS.md и `docs/agents/mta-gta-reference-policy.md`, затем
проверь текущее состояние файлов и тестов; не повторяй уже завершённые шаги.
Проверяй программно и не изменяй установленный MTA/GTA. Доведи
программно проверяемые acceptance criteria до выполнения, явно оставь
наблюдаемые человеком checks `not run` с ручным checklist и закончи code review.
```
