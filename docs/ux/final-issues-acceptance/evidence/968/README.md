# #968 — Quick Add: actual AFTER

Это текущий browser evidence для PR #972. Снимки сделаны настоящим Playwright Chromium/WebKit тестом с безопасными синтетическими данными, без пользовательских профилей и персональных записей.

Проверенный сценарий: открыть «Быстрый ввод» в дневнике питания, отобразить поля «Калории» и «Время (необязательно)», проверить DOM-границы и горизонтальный overflow, затем сохранить AFTER-кадр. Матрица: Light/Dark × 320/360/393/430 CSS px. В тесте также проверяется единая touch-height полей не менее 44px.

## AFTER gallery

### Chromium

| Тема  | 320                                           | 360                                           | 393                                           | 430                                           |
| ----- | --------------------------------------------- | --------------------------------------------- | --------------------------------------------- | --------------------------------------------- |
| Light | [PNG](after/chromium-quick-add-light-320.png) | [PNG](after/chromium-quick-add-light-360.png) | [PNG](after/chromium-quick-add-light-393.png) | [PNG](after/chromium-quick-add-light-430.png) |
| Dark  | [PNG](after/chromium-quick-add-dark-320.png)  | [PNG](after/chromium-quick-add-dark-360.png)  | [PNG](after/chromium-quick-add-dark-393.png)  | [PNG](after/chromium-quick-add-dark-430.png)  |

### WebKit

| Тема  | 320                                         | 360                                         | 393                                         | 430                                         |
| ----- | ------------------------------------------- | ------------------------------------------- | ------------------------------------------- | ------------------------------------------- |
| Light | [PNG](after/webkit-quick-add-light-320.png) | [PNG](after/webkit-quick-add-light-360.png) | [PNG](after/webkit-quick-add-light-393.png) | [PNG](after/webkit-quick-add-light-430.png) |
| Dark  | [PNG](after/webkit-quick-add-dark-320.png)  | [PNG](after/webkit-quick-add-dark-360.png)  | [PNG](after/webkit-quick-add-dark-393.png)  | [PNG](after/webkit-quick-add-dark-430.png)  |

Тест не изменяет nutrition payload, формулы, сохранение черновика, структуру приёма пищи или API. Реальные iPhone/WebKit, Telegram iOS и VoiceOver этим пакетом не подтверждаются.
