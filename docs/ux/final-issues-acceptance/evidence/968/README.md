# #968 — Quick Add: исторические AFTER до #991

Это исторические снимки PR #972, сохранённые в `5c036e8d8af5eab1f3b3643f010a74d898b131e9` до релиза #991. Они не подтверждают исправление на текущем master и не входят в новый пакет окончательной визуальной приёмки. Новые AFTER публикуются в едином итоговом пакете legacy PR closeout после интеграционного прогона.

Снимки сделаны настоящим Playwright Chromium/WebKit тестом с безопасными синтетическими данными, без пользовательских профилей и персональных записей.

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
