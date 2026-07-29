# Prototype 0005 — постоянные ID в MTA Map Editor

Дата: 2026-07-29  
Фаза: ограниченный runtime smoke-check, затем manual/source analysis  
Вердикт: **failed — принятый контракт постоянной identity не доказан и частично несовместим со stock save lifecycle**

## Проверяемый ответ

Официальный manual, установленный `editor_main` и исходный код MTA дают
достаточно точный архитектурный ответ без дальнейшего запуска:

- `ankigtaEntityId` можно хранить штатно как element data/EDF property.
  Установленный Editor сериализует такие данные в атрибут XML-элемента.
- `ankigtaMapId` нельзя надёжно хранить как произвольный атрибут корня
  `<map>` через stock Editor: при save корень создаётся заново, а Editor
  возвращает на него только собственные `xmlns:edf` и `edf:definitions`.
  Поддерживаемая форма — отдельный EDF custom child element.
- Публичного durable `before-save`/`after-save` callback с независимым
  read-back нет. Внутренний `saveloadtest_return` не является таким
  контрактом.
- Нет hash/mtime compare, CAS или предупреждения о внешнем изменении перед
  overwrite.
- Stock Editor удаляет прежний `.map`, создаёт и сохраняет новый пустой
  `<map>`, затем наполняет и сохраняет его повторно. Низкоуровневый XML writer
  использует temp/backup recovery, но не делает атомарной всю Editor-транзакцию:
  исходный map уже удалён до его вызова.
- `cloneElement` копирует весь custom data manager, а Editor перевыдаёт только
  собственный `id`/`me:ID`. Поэтому custom `ankigtaEntityId` дублируется.
- `copyResource` копирует embedded IDs; `renameResource` переносит resource без
  rewrite и сохраняет IDs. Editor Save As — создание/перезапись другого
  resource, а не rename.

Эти результаты отвечают на вопрос о штатных механизмах, но не являются
выполнением S1–S18. В runtime не было создано и сохранено ни одной disposable
map, ID не назначались и независимый read-back не выполнялся. Поэтому итоговый
`failed` не повышен.

## Фактическая runtime-граница

До переключения на manual/source analysis был выполнен только smoke-check:

1. Запущен отдельный sandbox MTA Server на `127.0.0.1:22010`.
2. Сервер загрузил 207 resources, 0 failed.
3. Запущен disposable resource `ankigta_p0005_runtime`; его log прямо
   фиксирует `directMapXmlWrite=false`.
4. Реальный MTA client подключился по loopback.
5. Интерфейс настоящего MTA Map Editor был виден.

На этом runtime-проверка остановилась. Не выполнялись:

- создание `p0005_*` map/resource fixture;
- штатный Save/Save As disposable map;
- присвоение `ankigtaMapId` или `ankigtaEntityId`;
- close/reopen, duplicate/copy/rename, collision и interruption;
- независимый read-back сохранённого `.map`.

Поиск после runtime не обнаружил `p0005_*.map` и вхождений prototype ID в
`.map`. Harness не писал ID в XML напрямую или в фоне.

## Происхождение исходников

### Установленный Editor

Развёрнутые из установленной MTA файлы
`editor_main/server/{saveloadtest_server,resourcehooks,createdestroy,IDhandler,import,save_backup}.lua`,
`edf/edf.lua` и `editor_main/meta.xml` побайтово совпали с официальным
[`mtasa-resources@f93681a`](https://github.com/multitheftauto/mtasa-resources/commit/f93681a3849e56e9f5ea39ca15b177eb8858b297).
Именно этот хешированный installed Editor является основным статическим
доказательством его save/clone поведения.

### Предоставленный пользователем MTA source

Read-only reference:

`C:\Проекты\Программы\GTARESTORED\PED BEHAVIOUR REFERENCE\MTA source code`

В дереве 9 152 файла, 301 588 648 байт, `.git` отсутствует. По Git blob
границе критических файлов оно идентифицировано как официальный
[`mtasa-blue@d564415a`](https://github.com/multitheftauto/mtasa-blue/commit/d564415ae58c3660bb0d3cd509c9be97dfc60101).
Поскольку локальной Git metadata нет, всё дерево классифицировано как
**reference**, а не как самостоятельное доказательство поведения установленной
сборки. Для выводов использованы только конкретные хешированные файлы, сверенные
с official upstream.

Эта папка одновременно принадлежит другому активному тикету. Prototype 0005
ничего в ней не записывал, не запускал там build/test/cache generation и не
выполнял Git/worktree операции. Общий diff дерева не использован как evidence.
Четыре использованных файла были точечно перечитаны в
`2026-07-29T14:37:46Z`; их SHA-256 не изменились. Остальная часть дерева может
законно меняться параллельно и остаётся вне доказательной границы.

SHA-256 критических reference-файлов:

| Файл | SHA-256 |
|---|---|
| `Shared/XML/CXMLFileImpl.cpp` | `2FA8738D4C55E0CF5E401F2143BE40E7168B2DB01A2FFD2AD2A2773618EBF343` |
| `Shared/mods/deathmatch/logic/luadefs/CLuaXMLDefs.cpp` | `4C64E7D4222A40C3E85E84A86585688017119F93BD3C9E9965A9FA22CB82C578` |
| `Server/mods/deathmatch/logic/CStaticFunctionDefinitions.cpp` | `D38896A07FE1D59591EAA2C797BE470368449A146C678FBBDE382FE27D28E85E` |
| `Server/mods/deathmatch/logic/CResourceManager.cpp` | `37FAF322B8CD9FDB92AE94DA9B10B558FAFA3137F056CBD988A1A5907CD266BC` |

## Поддерживаемая поверхность и границы

| Механизм | Вывод |
|---|---|
| element data / EDF property | поддерживаемый serialization path для entity/custom child identity |
| EDF import/custom element | поддерживаемый вариант map metadata как child, но не root attribute |
| Save / Save As | штатный workflow, но без durable external read-back contract |
| `saveloadtest_return` | внутренний callback; не публичная гарантия устойчивой записи |
| `cloneElement` | копирует custom data и создаёт duplicate-ID risk |
| `copyResource` | копирует resource-файлы и embedded IDs |
| `renameResource` | сохраняет embedded IDs; не равен Editor Save As |
| XML `WriteSafer` | temp/backup recovery отдельной XML-записи, не атомарность всей Editor save transaction |

Официальные первичные материалы:
[Map Editor](https://wiki.multitheftauto.com/wiki/Resource:Editor),
[EDF](https://wiki.multitheftauto.com/wiki/Resource:Editor/EDF),
[Editor plugins/import](https://wiki.multitheftauto.com/wiki/Resource:Editor/Plugins),
[element data](https://wiki.multitheftauto.com/wiki/Element_data),
[`cloneElement`](https://wiki.multitheftauto.com/wiki/CloneElement),
[`copyResource`](https://wiki.multitheftauto.com/wiki/CopyResource) и
[`renameResource`](https://wiki.multitheftauto.com/wiki/RenameResource).
Точный построчный source analysis находится в
`.scratch/0005-map-editor-identity-persistence-prototype/evidence/manual-research.md`.

## S1–S19

`not_run` означает, что acceptance scenario не был выполнен на сохранённом
disposable fixture. Source/manual result не повышает такой сценарий до runtime
pass.

| ID | Runtime | Manual/source result |
|---|---|---|
| S1 | `not_run` | Editor поддерживает обычные/custom elements; fixture inventory не создан |
| S2 | `not_run` | entity/custom-child path поддержан; произвольный map-root path отсутствует |
| S3 | `not_run` | `Pending Map Save` — ответственность ANKIGTA/prototype, не stock MTA |
| S4 | `not_run` | публичного durable completion + independent read-back contract нет |
| S5 | `not_run` | load/save алгоритм виден, close/reopen equality не наблюдалось |
| S6 | `not_run` | identity отделена от position/model полей; end-to-end не проверен |
| S7 | `not_run` | resource rename сохраняет IDs; Save As не является rename |
| S8 | `not_run` | clone гарантированно копирует custom data; collision risk доказан |
| S9 | `not_run` | stock validation arbitrary identity отсутствует |
| S10 | `not_run` | resource copy сохраняет embedded IDs; detection не проверен |
| S11 | `not_run` | rename сохраняет IDs, но old-owner semantics в MTA нет |
| S12 | `not_run` | Save As переносит текущие in-memory IDs и не reidentity-ит |
| S13 | `not_run` | pending removal/notification и reload boundary не проверены |
| S14 | `not_run` | **stock conflict safety failed by source**: нет compare/CAS |
| S15 | `not_run` | **Editor-level atomicity failed by source**: delete/create/empty-map window |
| S16 | `not_run` | invalid/partial identity validation stock Editor не предоставляет |
| S17 | `not_run` | unload/reload/restart fixture не выполнялся |
| S18 | `not_run` | Undo stack использует специализированные события; UI boundary не проверен |
| S19 | `partially_run` | cleanup доказан, но внешний client вышел за allowlist до exact restore |

Машинно-читаемая детализация:
`.scratch/0005-map-editor-identity-persistence-prototype/evidence/scenarios.json`.

## Изоляция и cleanup

После системного сбоя отдельно установлено:

- процессов MTA/GTA нет;
- `subst` mappings нет;
- sandbox и evidence присутствуют;
- disposable `.map` не создан.

Обычный зарегистрированный MTA client во время loopback-подключения изменил
шесть файлов `MTA/config`/`MTA/logs` и создал `console-input.log` вне allowlist.
Это сохранено как реальное отклонение, поэтому S19 не получает полный pass.
Изменённые версии архивированы read-only в
`evidence/runtime/external-client-deviation/`; исходные версии восстановлены
побайтово, добавленный log после архивации удалён.

Финальный pre/post-cleanup comparison показал одинаковые SHA-256 для всех
контролируемых targets:

- всей `C:\Games\MTA San Andreas 1.6`;
- Anki `prefs21.db` и двух `collection.anki2`;
- `gta_sa.set`;
- `AGENTS.md`, `CONTEXT.md`, всех ADR и design docs;
- отчётов Prototype 0001–0004.

Существующие `anki_map_editor`, `editor_test`, `editor_dump`,
`editor_map_backups`, пользовательские/production maps и Anki data не
использовались как fixtures и после cleanup не изменены.

## Evidence и verifier

Ключевые артефакты:

- `evidence/runtime/runtime-phase-summary.json`;
- `evidence/runtime/isolation-pre.json`;
- `evidence/runtime/isolation-post.json`;
- `evidence/runtime/isolation-post-cleanup.json`;
- `evidence/source-reference-runtime.json`;
- `evidence/manual-research.md`;
- `evidence/scenarios.json`;
- `evidence/manifest.json`.

Read-only verifier:
`.scratch/0005-map-editor-identity-persistence-prototype/verify_evidence.py`.
Он проверяет S1–S18=`not_run`, S19=`partially_run`, итоговый `failed`,
целостность manifests, exact pre/post-cleanup hashes и отсутствие процессов в
post-cleanup snapshot. Финальный запуск завершился с exit code `0`:
`{"status":"verified","mode":"read_only"}`. Результат сохранён в
`evidence/verifier-result.json`.

## Итог

Prototype 0005 завершён с честным `failed`.

Поддерживаемый дальнейший дизайн может использовать EDF custom child для
`ankigtaMapId` и element data для `ankigtaEntityId`, но этого недостаточно для
принятого контракта. Без отдельного identity-aware orchestration остаются:

- duplicate/copy collisions;
- отсутствие stock external-conflict protection;
- неатомарная Editor save transaction;
- отсутствие публичного durable read-back completion.

Любая неоднозначная или ещё не перечитанная identity должна оставаться в
`Pending Map Save`. Production-код ANKIGTA не создавался; `CONTEXT.md`, ADR и
design baseline не изменялись.
