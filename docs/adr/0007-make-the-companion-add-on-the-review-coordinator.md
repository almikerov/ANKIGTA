# Make the companion add-on the sole Review Transaction coordinator

MTA передаёт companion add-on точную Anki Card Identity, а add-on через планировщик Anki получает карточку, применяет Again/Hard/Good/Easy только после того, как Anki признал её scheduler-admitted, и возвращает подтверждённый результат и следующую карточку. MTA не изменяет расписание параллельным путём, а companion add-on не реализует собственный планировщик и не меняет приватную очередь: Anki остаётся единственным владельцем расписания.

Prototype 0001 доказал для Anki 26.05, что произвольную non-top карточку можно отрендерить, но `Scheduler.answerCard()` отклоняет её с `not at top of queue`. Prototype 0002 доказал поддерживаемый Exact Card Admission через временный X-only rebuild принадлежащей ANKIGTA rescheduling filtered deck. Coordinator обязан после rebuild наблюдать X как scheduler-top и только затем передавать оценку штатному планировщику; прямое оценивание non-top карточки остаётся запрещено.

Prototype 0003 подтвердил, что coordinator может надёжно восстанавливать собственную Review Transaction, но не может безопасно перехватывать стандартный Anki Reviewer посреди его асинхронного callback оценки. Уже начатая операция обычного Reviewer должна закончить штатный lifecycle до любых действий с `ANKIGTA Session`.

Prototype 0004 подтвердил transport boundary: параллельные read-запросы могут выполняться независимо, а review-запросы сериализуются одним MTA queue/coordinator path. `requestId` коррелирует транспорт, но не заменяет `reviewTransactionId`.
