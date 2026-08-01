# 28 — UI Scale and layout

**What to build:** Масштабируемое и восстанавливаемое размещение F7, Review Mode и HUD на поддерживаемых разрешениях.

**Blocked by:** 20 — Minimal Review Mode; 23 — Next Card Indicator and statistics.

**Status:** resolved

**Environment boundary:** Follow `AGENTS.md` and `docs/agents/mta-gta-reference-policy.md`. Verify programmatically — launching disposable copies is allowed, driving a GUI with screenshots or synthetic input is not, and the installed MTA/GTA tree stays unmodified. Acceptance that only a human can observe stays a manual checklist marked `not run`.

## Acceptance criteria

- [x] UI Scale defaults 1, accepts 0.5–2, button step 0.05 and manual two-decimal input. Шаг принадлежит кнопкам, а не схеме: правило валидации с шагом 0.05 отвергало бы `1.23`, которое story 54 разрешает. Кнопки останавливаются на границах, а не заворачиваются.
- [x] Scale applies immediately; required primary actions remain reachable without horizontal page scrolling. Открытое окно перестраивается через `Layout.onChange` — без перезапуска ресурса и без переоткрытия. Тест проходит по каждому контролу каждого окна на трёх разрешениях и трёх масштабах и требует, чтобы он помещался в своё окно.
- [x] F7/Review Mode drag by title; HUD moves only in Edit HUD layout. Окна CEGUI перетаскиваются своим заголовком, и `onClientGUIMove` сообщает результат. Review Mode рисует собственную полосу заголовка, потому что это dx-поверхность. У HUD заголовка нет, поэтому его захватывает вся площадь — и только в Edit HUD layout.
- [x] Modal warnings move with parent. `Unlink`, `Replace card` и предпросмотр Relink центрируются на F7 и переезжают вместе с ним.
- [x] Positions persist as normalized client coordinates outside Change History. Хранится доля экрана, а не пиксель; настройка клиентская, поэтому в историю не попадает по authority (ADR 0028).
- [x] Resolution/aspect/scale changes clamp windows so a title remains reachable. Поверхность никогда не больше экрана и всегда целиком на экране, поэтому заголовок доступен всегда. События смены разрешения в MTA нет — состояние опрашивается таймером.
- [x] `Reset UI layout` is always visible/reachable. Панель открывается и из F7, и командой `/ankigta-ui`; тест приводит раскладку в худшее состояние на каждом разрешении и масштабе и убеждается, что кнопка на экране, внутри своего окна и работает.
- [x] 1280×720, 1920×1080 and 3840×2160 pass layout tests.
- [x] Connected gamepad triggers no ANKIGTA action and has no dedicated UI/support. ADR 0015.

## Tests

- [x] Automated layout screenshots/geometry assertions at three resolutions and scale boundaries. Скриншотов нет и не будет — политика окружения запрещает проверять GUI пикселями. Вместо них геометрия читается обратно с настоящих контролов, созданных настоящими скриптами в настоящем Lua 5.1.
- [x] Drag, persistence, clamp and reset tests.
- [x] Keyboard/mouse modal accessibility and gamepad-noise test.

## Components

- MTA client window/HUD layout manager.
- F7, Review Mode and HUD presentation.
- Client UI settings.

## Implementation status

- `client/layout.lua` — менеджер раскладки. До него каждое окно само звало
  `guiGetScreenSize()` и раскладывало себя в абсолютных пикселях. Из того, что
  это забрали, следуют обе половины тикета: один UI Scale, доезжающий сразу до
  всех окон, и размещение, переживающее смену разрешения.
- Размер поверхности ограничен экраном, а **настройка — нет**. Окно выше
  экрана — это заголовок, за который нельзя взяться, и кнопки, до которых
  нельзя дотянуться, и никакое перетаскивание этого не чинит. При этом
  подрезать саму настройку значило бы оставить игроку масштаб, который он не
  выбирал, когда он в следующий раз сыграет на большем экране.
- Размещение нормализовано долей экрана. Пиксель означал бы «этот угол» ровно
  до первой смены разрешения.
- Схема получила правило `placement`: сохранённое размещение проверяется, а не
  принимается на веру, и повреждённое отбрасывается в default с диагностикой,
  как любое другое непрошедшее значение.
- Запись размещения дебаунсится. CEGUI сообщает перетаскивание потоком
  `onClientGUIMove` по кадру, и запись файла на каждый из них переписала бы его
  сотню раз ради одного решения.

**ADR 0028 написан здесь.** Тикет 27 оставил открытым вопрос, что делать с
клиентскими настройками в Change History, с двумя вариантами: журналировать их
на сервер или помечать флагом. Первый нарушает ADR 0014 ради Undo для «размер
шрифта был другой». Второй — правило, записанное столько раз, сколько
настроек, и ошибающееся там, где про флаг забудут. Принадлежность истории
теперь выводится из authority.

**Дефект, найденный в чужом коде по дороге.** `handleReviewClick` считала
курсором аргументы 5 и 6 `onClientClick` — это мировая точка, а не курсор.
Курсор — это аргументы 3 и 4 (`CClientGame::ProcessMessage` кладёт
`vecCursorPosition` перед `vecCollision`). Тест тикета 20 повторял ту же
ошибку в своём помощнике, поэтому и код, и тест соглашались друг с другом и ни
разу не соглашались с MTA. Исправлено вместе с тестом: попадание по кнопке —
это ровно то, на чём стоит вся геометрия этого тикета.

**Расширенная песочница.** Контролы теперь записывают свою геометрию,
`guiSetPosition`/`guiGetPosition`/`guiSetSize`/`guiGetSize`/
`guiWindowSetMovable`/`guiWindowSetSizable` отвечают как в MTA,
`guiGetScreenSize()` двигается тестом, `dxDraw*` записывают прямоугольники, а
обработчик, повешенный на контрол, вызывается только для этого контрола — как
делает `CClientGUIElement::CallEvent`, и в отличие от прежней песочницы, где
клик по одному окну достался бы кнопкам всех.

### Наблюдения из справочника MTA

Прочитано только для этого тикета, только на чтение
(`docs/agents/mta-gta-reference-policy.md`), 2026-08-01T16:49:39Z:

- `Client/mods/deathmatch/logic/CClientGame.cpp`,
  SHA-256 `ad47cd66c3764a8b2bb7299fa39a706fbfe1cb5d3a2853e1b18d1efab3f8c60d` —
  `onClientGUIMove`/`onClientGUISize` существуют и приходят без аргументов
  (`OnMove`, `OnSize`); `onClientClick` кладёт курсор в аргументы 3–4 и мировую
  точку в 5–7; `onClientCursorMove` кладёт относительную позицию, затем
  абсолютную; события смены разрешения нет — `onClientRestore` срабатывает на
  разворачивание окна, поэтому размер экрана опрашивается.
- `Client/core/CKeyBinds.cpp`,
  SHA-256 `d87c62055f7763f9ea3057a092b73cc074abfa45b9f0f7b2941a19ee6d61d542` —
  имена геймпадных клавиш: `joy1`..`joy32`, `pov_up/right/down/left`,
  `axis_1`..`axis_14`; плюс список игровых control, которые контроллер тоже
  нажимает. Тест требует, чтобы ANKIGTA не биндила ни одного из них.
- `Client/gui/CGUIWindow_Impl.cpp` — CEGUI FrameWindow по умолчанию и подвижен,
  и изменяем по размеру, поэтому изменение размера выключается явно: размер —
  дело UI Scale.

Automated evidence: `pytest -q tests/test_ui_layout.py` → 122 passed;
весь набор без `tests/test_mta_ticket_02.py` → 842 passed, 1 skipped; mypy
strict clean. `tests/test_mta_ticket_02.py` (14 failed) требует настроенного
MTA-сервера и падает так же на базовом коммите — к этому тикету отношения не
имеет.

## Manual runtime checklist

См. `docs/checklists/ticket28-ui-scale-layout.md` (`Status: not run`).
Читаемость на каждом масштабе, ощущение перетаскивания, поведение CEF при
смене размера поверхности и реакция на настоящий контроллер — это то, что
может увидеть только человек.
