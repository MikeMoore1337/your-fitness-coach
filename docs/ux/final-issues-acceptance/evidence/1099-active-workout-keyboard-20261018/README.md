# Issue #1099: keyboard-input scroll evidence

Дата: 2026-10-18
Сценарий: синтетический активный workout fixture, браузерный iOS-viewport 393×844, modeled `visualViewport.height=420`, ввод веса `50`, переход в повторы, ввод `12`, ожидание server ACK.

## BEFORE

`origin/master` at `afc9a3e918f4085e506b711c5cacfe4b5c5a0f5c`.

На том же Playwright-сценарии после стабилизации поля изменение `scrollY` составило **105 px**. Запись: [before-origin-master-chromium.webm](./before-origin-master-chromium.webm).

## AFTER

После исправления на той же последовательности `scrollY` остаётся в пределах **1 px**, а после стабилизации и ACK новые вызовы `scrollBy`/`scrollTo` отсутствуют. Записи: [after-fixed-chromium.webm](./after-fixed-chromium.webm) и [after-fixed-webkit.webm](./after-fixed-webkit.webm).

Регрессионный тест: `#1099 keeps scroll stable after keyboard input and server ACK`. Матрица #1001 дополнительно проверяет 320/360/393/430 px, Dark/Light, повторный ввод, изменение высоты и `visualViewport.offsetTop`, offline→online, ручной скролл, reload и переходы между подходами.

Записи показывают безопасный synthetic/browser evidence. Это не доказательство поведения на физическом iPhone Safari, в нативном Telegram Mini App или в production.
