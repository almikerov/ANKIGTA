# Use server-side Lua as the only MTA gateway to Anki

В MTA только server-side Lua обращается к привилегированному control API локального ANKIGTA companion add-on и хранит параметры подключения к нему. Создание сессии, чтение scheduler state, оценки, сверка Review Transaction и любые изменения Anki никогда не доступны client-side Lua или CEF.

Для точного отображения карточки CEF может напрямую получать только HTML и media через отдельный loopback read-only content endpoint add-on. Доступ выдаётся короткоживущей capability URL для одного render; endpoint не принимает команды, не изменяет Anki, не раскрывает постоянный connection token и не даёт доступ к control API. Карточный JavaScript не получает работающего privileged dispatch; card-visible stock-MTA `window.mta` stub допускается по ADR 0026.

Prototype 0004 подтвердил control path на настоящем MTA Server 1.6 build 24124: server-side `fetchRemote` обменивался с companion harness через IPv4 loopback, а disposable resource не содержал client-side Lua или CEF control gateway. Это доказывает транспортную осуществимость control API, но отдельный read-only content endpoint и его capability isolation должны пройти CEF prototype.

Prototype 0006 подтвердил disposable content endpoint и capability model в harness. Он также показал, что remote privileged dispatch блокируется native `isLocal` guard, хотя card-visible `window.mta` stub inject-ится. ADR 0026 принимает это stock-MTA ограничение для v1.
