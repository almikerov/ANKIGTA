# Render cards best effort in stock MTA CEF

ANKIGTA v1 не обещает пиксельное или полностью поведенческое совпадение карточки между Anki Desktop и stock MTA CEF. Supported Card предъявляется настолько полно, насколько это позволяет stock MTA CEF.

ANKIGTA передаёт полученные HTML, CSS, JavaScript и media references без намеренного удаления или обрезки, но принимает различия движка, доступных web features, шрифтов, autoplay и поведения сторонних ресурсов. Небольшие визуальные или поведенческие отличия сами по себе не блокируют Again/Hard/Good/Easy.

Явная ошибка загрузки, ошибка HTML, JavaScript, шаблона или media показывает предупреждение, но не блокирует Again/Hard/Good/Easy. Пользователь может оценить карточку даже при неполном или повреждённом предъявлении. External Card Page также не блокирует оценивание; `Вернуться к карточке` остаётся необязательным действием.

Совместимость проверяется smoke и lifecycle тестами на поддерживаемом stock MTA build, а не исчерпывающим whitelist всех HTML/CSS/JavaScript features и не сравнением pixel-perfect screenshots с Anki Desktop.
