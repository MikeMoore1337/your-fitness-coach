# Dock 4+1 — дизайн-предложение для #1504

Интерактивный синтетический прототип для предварительного утверждения владельцем. Это не production UI и не реальные AFTER-снимки. За основу взят прототип аудита #993; данные демонстрационные и не сохраняются.

Четыре раздела находятся в одной капсуле, круглая кнопка справа открывает Quick Add. При 320–430 CSS px разделы расположены в одну строку. При сверхузкой доступной ширине (например, 393 px при zoom 200%) по решению владельца от 20.11.2026 вкладки перестраиваются в две строки, а кнопка остаётся рядом. Это решение о reflow ещё не является утверждением всего макета.

## Просмотр

Скачайте каталог целиком и откройте `index.html` в браузере: ссылки GitHub показывают исходный HTML, а не исполняют его. Кнопка темы, четыре раздела и открытие/закрытие Quick Add работают без сервера. Действия «Кардио», «Замер» и «Самочувствие» обозначены заглушками; запись данных не выполняется. Профиль, экран тренировки и таймер служат только синтетическим контекстом.

Снимки сделаны с viewport **393 × 852 CSS px**, Chromium и WebKit, обе темы; дополнительно есть **320 × 852**. Состояния «Сегодня», «План», «Питание», «Прогресс» и открытый Quick Add включены в `screens/`. Для zoom 200% исходный viewport Chromium — 393 × 852; эффективная ширина около 196 CSS px.

| Состояние | Светлая тема | Тёмная тема |
| --- | --- | --- |
| Сегодня | [Chromium](screens/chromium-393-light-today.png) | [Chromium](screens/chromium-393-dark-today.png) |
| План | [Chromium](screens/chromium-393-light-plan.png) | [Chromium](screens/chromium-393-dark-plan.png) |
| Питание | [Chromium](screens/chromium-393-light-nutrition.png) | [Chromium](screens/chromium-393-dark-nutrition.png) |
| Прогресс | [Chromium](screens/chromium-393-light-progress.png) | [Chromium](screens/chromium-393-dark-progress.png) |
| Quick Add | [Chromium](screens/chromium-393-light-sheet.png) | [Chromium](screens/chromium-393-dark-sheet.png) |
| Zoom 200%, две строки | [Chromium](screens/chromium-393-light-zoom200.png) | [Chromium](screens/chromium-393-dark-zoom200.png) |

WebKit: [Light](screens/webkit-393-light-today.png), [Dark](screens/webkit-393-dark-today.png), [Quick Add Light](screens/webkit-393-light-sheet.png), [Quick Add Dark](screens/webkit-393-dark-sheet.png). Полный набор включённых снимков — каталог `screens/`.

## Что проверено у прототипа

- 20 сочетаний Chromium/WebKit × 320/360/390/393/430 × Light/Dark: четыре кнопки в ряд, размеры не меньше 44 CSS px, видимые подписи, отсутствие корневого overflow; открытие и закрытие Quick Add из каждого раздела, возврат фокуса, центральный hit-test кнопки.
- 32 проверки последнего действия: четыре раздела × Chromium/WebKit × 320/393 × Light/Dark; после фокуса элемент находится над dock и доступен hit-test.
- Настоящий Chromium zoom 200% в обеих темах: две строки, размеры не меньше 44 CSS px, видимые подписи и переходы по четырём разделам. Клавиатурные Enter/Escape и возврат фокуса, а также смена ориентации проверены в Chromium и WebKit.
- Impeccable context и detector, Taste lint и inspect, UI UX Pro Max search вызваны локально. Impeccable detector сообщил три предупреждения: 11 px, tracking и Inter. Taste lint — 0 FAIL / 8 WARN; inspect — предупреждение о размере заголовка. Inter/Oswald и навигационный Liquid Glass — заданные брендовые ограничения, а предупреждения о размере текста остаются предметом оценки.

Команды проверки — `check.cjs`, `clearance-check.cjs`, `zoom-check.cjs`. Им нужен установленный Playwright, доступный Node через `NODE_PATH`, и локальные браузеры Playwright. Zoom-проверка использует включённое локальное расширение `zoom-extension`; оно только задаёт zoom вкладки и не отправляет данные.

## Ограничения и дальнейший порядок

Полный независимый Impeccable critique и независимая QA не выполнялись. Реальные iPhone/Safari, PWA, Telegram Mini App, системная клавиатура, VoiceOver и production — **NOT_VERIFIED**. Фокус поля в прототипе лишь моделирует скрытие общей группы; это не доказательство работы visualViewport или клавиатуры устройства. Прокрутка последнего действия проверена только в синтетических экранах и сценариях выше.

Этот пакет описывает мобильный Dock; существующий desktop sidebar не предлагается заменять. До реализации нужно согласовать reflow в актуальном `dev`, общие компоненты #994 и motion #982. После утверждения макета требуется отдельное разрешение на production-реализацию, затем реальные AFTER с SHA и отдельные visual/release approvals. #989 остаётся финальной сквозной QA.

`OWNER_VISUAL_APPROVAL=PENDING · PRODUCTION_IMPLEMENTATION=NOT_AUTHORIZED · MERGE/DEPLOY=NOT_AUTHORIZED`.
