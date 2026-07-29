# 01 — Companion health and Anki version

**What to build:** Минимальный companion add-on, который внутри уже запущенного Anki отвечает на локальный health-запрос и сообщает наблюдаемую коллекцию, версию Anki, состояние V3 scheduler и FSRS. Это первый проверяемый вертикальный путь через реальный add-on lifecycle, без запуска обучения и изменения Anki.

**Blocked by:** None — can start immediately.

**Status:** resolved

## Acceptance criteria

- [x] Add-on загружается штатным способом в Anki Desktop 26.05 на Windows и не изменяет коллекцию при запуске.
- [x] Health-запрос возвращает versioned protocol envelope, `requestId`, версию Anki, наличие V3/FSRS и сведения о текущей открытой коллекции.
- [x] Отсутствующая или закрывающаяся коллекция возвращает отдельное наблюдаемое состояние, а не ложный success.
- [x] Неподдерживаемая версия/конфигурация видна как compatibility failure; Preview/read-only возможность не смешивается с разрешением rating/session.
- [x] Add-on не запускает Anki, не переключает профиль и не создаёт `ANKIGTA Session`.

## Tests

- [x] Интеграционный тест на настоящем Anki Desktop 26.05 с FSRS.
- [x] Contract-тест корректного, отсутствующего и повреждённого `requestId`/protocol envelope.
- [x] Lifecycle-тест открытия/закрытия коллекции и выгрузки add-on без мутации Anki.

## Components

- Companion add-on lifecycle.
- Versioned companion control contract.
- Anki compatibility probe.
