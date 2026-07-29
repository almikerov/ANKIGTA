# Accept stock MTA card-browser limits

ANKIGTA v1 использует stock MTA CEF без native/upstream fork и не блокирует реализацию из-за строгих browser-isolation обещаний, опровергнутых Prototype 0006.

Card-visible `window.mta` stub допускается: обязательная граница состоит в том, что native `isLocal` guard не позволяет remote card content выполнить privileged MTA dispatch. Companion control API, rating, scheduler, collection operations и постоянный connection token по-прежнему недоступны карточке.

External HTTP(S) images, fonts, styles and scripts разрешаются через штатные domain permissions MTA. Поскольку stock MTA использует тот же allow-state для main-frame navigation, ANKIGTA принимает возможность перехода карточной child surface на разрешённый внешний домен. Верхняя Lua/dx оболочка Review Mode остаётся отдельной.

После такого main-frame navigation состояние становится External Card Page. Кнопки Again/Hard/Good/Easy остаются доступны; действие `Вернуться к карточке` получает новое предъявление текущей стороны, но не является условием оценивания.

Stock popup blocking сохраняется. ANKIGTA не обещает отличать genuine user click от script-only popup, автоматически открывать ссылки в системном браузере Windows, поддерживать downloads или контролировать поведение сторонней страницы. Для v1 это неподдерживаемые возможности, а не обязательные security boundaries.

Read-only content endpoint и короткоживущая per-render capability сохраняются, потому что они прошли harness и отделяют тяжёлый card content от companion control API. Real-MTA fidelity, playback and lifecycle остаются предметом последующей проверки сокращённого контракта.
