# Limit v1 to tested Anki Desktop versions on Windows with FSRS

Первая версия поддерживает Windows, FSRS и явно протестированный диапазон актуальных версий Anki Desktop. На неподдерживаемой версии просмотр может оставаться доступным, но создание сессии и отправка оценок блокируются до прохождения интеграционных тестов.

Prototype 0001 проверен на Anki Desktop 26.05, V3 scheduler и явно включённом FSRS. Его отрицательный результат для non-top exact-card rating считается версионно привязанным и не переносится молча на другие версии.

Prototype 0002 на той же версии положительно подтвердил Exact Card Admission через настоящую rescheduling filtered deck и эквивалентность результатов FSRS контрольному Anki Reviewer для проверенной матрицы состояний и оценок. Эта совместимость также не переносится на другую версию без повторного интеграционного прогона.

Prototype 0003 на Anki 26.05 подтвердил durable coordinator recovery, но не нашёл документированного add-on API для переключения профиля или закрытия Reviewer. Проверенные AQT-механизмы non-private, но version-sensitive; они не могут считаться поддерживаемым контрактом v1 без отдельного решения и интеграционного gate.

Prototype 0004 проверен на Windows 11 и MTA Server 1.6 release build 24124. Numeric IPv4 loopback прошёл и принят как единственный transport path v1; IPv6 `::1` оказался несовместим с протестированным MTA HTTP path и в v1 не поддерживается. Поддержка другого MTA build требует повторного transport integration test.
