# Предложение: заметка с прошлого выполнения — #1195

Это макет для согласования, **не AFTER реализации**. Основа — экран YFC из `dev`
`a27896659d594dfacfa88901b44355d767c7e732` с таймером отдыха v2. Блок добавлен
в браузере к работающему приложению для просмотра композиции; данные синтетические.

Одна и та же сворачиваемая заметка показана под запланированной тренировкой на экране
«Сегодня» и перед упражнениями в активной тренировке. По умолчанию текст развёрнут.
Указаны номер и название прошлого дня и фактическая дата его завершения. Если после
этой записи было более позднее выполнение без заметки, заголовок меняется на
«Последняя сохранённая заметка». При отсутствии достоверной записи блок не показывается.

| Экран и состояние | Dark | Light |
| --- | --- | --- |
| Активная, Chromium 393 × 844 | [PNG](chromium-dark-393-note.png) | [PNG](chromium-light-393-note.png) |
| Запланированная, Chromium 393 × 844 | [PNG](chromium-dark-393-planned.png) | [PNG](chromium-light-393-planned.png) |
| Более старая заметка, Chromium 393 × 844 | [PNG](chromium-dark-393-older.png) | [PNG](chromium-light-393-older.png) |
| Свёрнута, Chromium 393 × 844 | [PNG](chromium-dark-393-collapsed.png) | [PNG](chromium-light-393-collapsed.png) |
| Активная, WebKit 393 × 844 | [PNG](webkit-dark-393-note.png) | [PNG](webkit-light-393-note.png) |
| Запланированная, WebKit 393 × 844 | [PNG](webkit-dark-393-planned.png) | [PNG](webkit-light-393-planned.png) |
| Более старая заметка, WebKit 393 × 844 | [PNG](webkit-dark-393-older.png) | [PNG](webkit-light-393-older.png) |
| Свёрнута, WebKit 393 × 844 | [PNG](webkit-dark-393-collapsed.png) | [PNG](webkit-light-393-collapsed.png) |
| Активная, Chromium 320 × 844 | [PNG](chromium-dark-320-note.png) | [PNG](chromium-light-320-note.png) |
| Активная, Chromium 1440 × 1000 | [PNG](chromium-dark-1440-note.png) | [PNG](chromium-light-1440-note.png) |

Все размеры приведены в CSS px, DPR 1. В макете нет записи в историю или изменения
подходов. Клавиатура, safe-area, offline/reconnect, длинные заметки и реальная интеграция
будут проверены после утверждения и реализации. WebKit на компьютере не подтверждает
работу на физическом iPhone или в настоящем Telegram Mini App.

Решение владельца: утвердить эту композицию для реализации либо указать изменения.
Последующая приёмка реального AFTER и разрешение на интеграцию в `dev` — отдельные решения.
