---
status: accepted
---

# Gate a real rescheduling filtered deck behind a compatibility prototype

Предпочтительный механизм `ANKIGTA Session` — настоящая filtered deck с rescheduling, которой управляет companion add-on.

Prototype 0002 прошёл на Anki Desktop 26.05 с V3 scheduler и FSRS. Он подтвердил полную сессию из точного набора `cardId` и штатный Exact Card Admission: временно перестроить ту же принадлежащую ANKIGTA filtered deck в X-only набор, получить X как scheduler-top, оценить X через Anki и перестроить полный набор. Поведение new, learning, relearning, due review и future review при Again/Hard/Good/Easy совпало с контрольным Anki Reviewer; suspended и buried остались исключёнными и Preview only. Pause/stop, rebuild и проверенные recovery boundaries не оставили карточки в filtered deck и не создали лишних `revlog`.

Доказательство версионно ограничено. Используемые backend-операции Anki не являются private queue mutation, но требуют интеграционных тестов на каждой поддерживаемой версии. Сбой внутри атомарной backend-перестройки не был внедрён. Прототип также доказал, что порядок exact-ID не определяет scheduler-top и что filtered deck обходит исходный дневной лимит новых карточек. ANKIGTA принимает это поведение намеренно: все связанные новые карточки доступны, а карточка сверх сегодняшнего лимита Anki получает явное предупреждение в Review Mode.

Prototype 0003 подтвердил, что после перезапуска owned filtered deck можно восстанавливать без лишнего `revlog`, если сначала durable coordinator однозначно сверил Review Transaction. При `Outcome Unknown` rebuild, cleanup и переключение коллекции запрещены. Crash внутри атомарной backend answer/rebuild операции остаётся непроверенной границей.
