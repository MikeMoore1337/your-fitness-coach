# #920 — AFTER: устаревший предпросмотр

Реальный frontend из commit `6c185c48b7863a00f35070a41b37749a755104e9`, локальная production-сборка и синтетические API-ответы. Открыт предпросмотр изменения срока; другая операция изменила ревизию в родительском экране. Предупреждение появилось, применение стало недоступно, выбранные значения сохранились.

Playwright: 8/8 сценариев, Chromium и WebKit, тёмная и светлая темы, ширины 393 и 1440 px, высота viewport 900 px. Снимки показывают компонент целиком. Физические устройства, реальный Telegram и production не проверялись.

| Браузер и тема | 393 px | 1440 px |
| --- | --- | --- |
| Chromium, тёмная | [393](chromium-dark-393-stale.png) | [1440](chromium-dark-1440-stale.png) |
| Chromium, светлая | [393](chromium-light-393-stale.png) | [1440](chromium-light-1440-stale.png) |
| Webkit, тёмная | [393](webkit-dark-393-stale.png) | [1440](webkit-dark-1440-stale.png) |
| Webkit, светлая | [393](webkit-light-393-stale.png) | [1440](webkit-light-1440-stale.png) |
