# Isolate card content from the privileged MTA bridge

Части этого решения о невидимом MTA bridge, блокировке external navigation и обязательном system-browser handoff отменены ADR 0026 после Prototype 0006. Требования семантически эквивалентного отображения и блокировки оценки при ошибке шаблона заменены best-effort контрактом ADR 0027.

HTML, CSS, media and допустимый JavaScript карточки выполняются в отдельном CEF-контексте без доступа к MTA bridge, постоянному connection token и привилегированному companion control API. Неподдерживаемый или небезопасный шаблон получает безопасный статический preview, а оценивание блокируется, чтобы неполное предъявление не изменило расписание.

Изоляция и транспорт не должны менять вид или допустимое поведение поддерживаемой карточки. ANKIGTA сохраняет полученные от Anki HTML, CSS, JavaScript и media references семантически эквивалентными; оптимизация не может удалять, обрезать или произвольно переписывать содержимое.

После допуска карточки через server-side control API CEF получает короткоживущую capability URL для одного render и загружает через отдельный read-only loopback content endpoint add-on HTML и media как обычная веб-страница. Content endpoint поддерживает только получение предъявления, не принимает rating или scheduler-команды, не раскрывает collection API и не использует постоянный connection token. Capability истекает после закрытия Review Mode или короткого timeout и не переиспользуется для другой карточки.

Control JSON ограничивается 2 MiB и не несёт тяжёлые media. Общий размер карточки этим лимитом не ограничен: HTML и media передаются content endpoint отдельно. Точные streaming/range/cache limits должны пройти CEF isolation prototype, который докажет rendering fidelity на реальных шаблонах.

Карточный CEF может свободно загружать внешние HTTP(S)-ресурсы, включая изображения, шрифты, стили и скрипты. Внешний сетевой доступ не предоставляет MTA bridge, companion control API, connection token или render capability для другой карточки. ANKIGTA не обещает доступность, приватность или неизменность сторонних ресурсов и не считает их частью локальной Anki media collection.

Карточный документ не может заменить верхний Review Mode, автоматически открыть новое окно, выполнить внешнее перенаправление или начать скачивание. Только ссылка, явно активированная пользователем, открывается вне CEF в системном браузере Windows. Subresource-запросы внутри карточки при этом остаются разрешены.

Prototype 0006 завершился `failed` и не подтвердил этот полный контракт на stock MTA. Reference source inject-ит card-visible `window.mta` даже в remote context, хотя native guard блокирует privileged dispatch; один domain allow-state одновременно разрешает external subresources и main-frame navigation; native `user_gesture` не передаётся Lua для доказуемого system-browser handoff. Resource-level rewriting и возврат после navigation не являются достаточной границей. ADR 0026 заменяет эти невыполнимые части решения практичным stock-MTA контрактом v1.
