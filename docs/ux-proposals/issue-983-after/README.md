# #983 — реальные AFTER для визуальной приёмки

Реализация: `33c8711930958f444a5416e4481c4de65f77d2ee`, исходный `dev`: `72626d12dc38d1cd26f170ca721830778289a619`. Это снимки собранного приложения с синтетическими данными; они не являются проверкой production или реального телефона. Утверждение прототипа #982 не заменяет отдельную приёмку этого AFTER.

## Жесты

- [Chromium, Light](videos/chromium-gestures-light.webm) · [Chromium, Dark](videos/chromium-gestures-dark.webm)
- [WebKit, Light](videos/webkit-gestures-light.webm) · [WebKit, Dark](videos/webkit-gestures-dark.webm)
- Прерывание закрытия и mocked Telegram Back: [Chromium](videos/chromium-telegram-interruption.webm) · [WebKit](videos/webkit-telegram-interruption.webm)

В видео последовательно показаны 320, 360, 393 и 430 CSS px: неделя в обе стороны и короткий жест, который её не меняет. Недостаточный жест панели возвращает её на место; достаточный закрывает. Правило ленты: сначала прокручиваются скрытые дни, затем на достигнутой границе следующий жест меняет неделю. Дополнительный тест touch с искусственно суженной лентой выполнен в Chromium; WebKit в этом тесте намеренно пропущен, поскольку CDP ему недоступен.

## Снимки

В папке [screenshots](screenshots/) имена имеют вид `{chromium|webkit}-{320|360|393|430}-{light|dark}-{week|sheet}.png`. Снимки `*-393-tma-sheet.png` получены с mocked Telegram; `dock-zoom-200-*.png` — реальный масштаб браузера Chromium 200% в двух темах.

В папке [screens](screens/) приведены Today, Plan (`programs`), Nutrition и Progress на ширине 393 px в Chromium/WebKit, Dark/Light. Они сняты существующей регрессией Dock 4+1 с API-фикстурами. Пиксельная ширина PNG в WebKit может отличаться от CSS px из-за масштаба устройства.

Примеры: [лента, Chromium Light 393](screenshots/chromium-393-light-week.png) · [панель, WebKit Dark 320](screenshots/webkit-320-dark-sheet.png) · [Progress, WebKit Dark 393](screens/webkit-progress-393-dark.png).

## Проверки и границы

- PASS: 1505 unit-тестов до исправления offline; после него — 93 адресных теста Nutrition/Hydration. Typecheck, lint, проверка форматирования, production build и неизменённые performance-бюджеты.
- PASS: девять браузерных сценариев жестов; один Chromium CDP-сценарий намеренно пропущен в WebKit. Проверены прерывание, отмена, фокус, mocked Telegram Back, reduced motion и эмулированная потеря сети.
- PASS: 20 существующих регрессионных сценариев Dock 4+1 и Quick Add в Chromium/WebKit на пяти ширинах в обеих темах.
- PASS: реальный масштаб Chromium 200%, Light/Dark; Dock 4+1 и открытие/закрытие панели.
- Реальный iPhone/Safari/PWA/TMA и реальные сетевые условия: NOT_RUN. Браузерная эмуляция, offline в Playwright и mocked TMA их не подтверждают.
- Owner visual acceptance, CI точного head, merge в dev и обновление Windows DEV проверяются отдельно; этот пакет сам по себе их не подтверждает.

Для утверждения: проверить следование ленты и панели за жестом, возврат и закрытие, обе темы, читаемость и совместимость с Dock. После отдельной визуальной приёмки и успешных обязательных проверок можно продолжить разрешённое объединение в dev и обновление Windows DEV.
