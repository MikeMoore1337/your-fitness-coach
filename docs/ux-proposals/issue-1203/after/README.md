# #1203 · AFTER: профили оборудования

Реальные снимки работающих React-компонентов в Chromium 151.0.7922.34. API отвечает
синтетическими тестовыми данными; изображения упражнений могут отсутствовать. Экран замены
также использует тестовый ответ существующего API. Поэтому снимки показывают интерфейс,
а не подтверждают работу сервера или физического устройства.

Каждый лист содержит исходные снимки без масштабирования: верх экрана и нижнюю часть после
прокрутки. Mobile: 320×760, 360×800, 393×852 и 430×932 CSS px; desktop: 1280×900 CSS px.
Показаны обе темы. При открытом диалоге нижний снимок показывает его прокрученное содержимое.
Клавиатура моделируется через visualViewport; физическая клавиатура не снималась.

| Состояние | Dark | Light |
| --- | --- | --- |
| Профиль: вход в управление | [320/360](screens/profile-entry-dark-mobile-320-360.png) · [393/430](screens/profile-entry-dark-mobile-393-430.png) · [desktop](screens/profile-entry-dark-desktop.png) | [320/360](screens/profile-entry-light-mobile-320-360.png) · [393/430](screens/profile-entry-light-mobile-393-430.png) · [desktop](screens/profile-entry-light-desktop.png) |
| Несколько профилей, активен «Дом» | [320/360](screens/profiles-dark-mobile-320-360.png) · [393/430](screens/profiles-dark-mobile-393-430.png) · [desktop](screens/profiles-dark-desktop.png) | [320/360](screens/profiles-light-mobile-320-360.png) · [393/430](screens/profiles-light-mobile-393-430.png) · [desktop](screens/profiles-light-desktop.png) |
| Активен пустой профиль | [320/360](screens/profile-empty-dark-mobile-320-360.png) · [393/430](screens/profile-empty-dark-mobile-393-430.png) · [desktop](screens/profile-empty-dark-desktop.png) | [320/360](screens/profile-empty-light-mobile-320-360.png) · [393/430](screens/profile-empty-light-mobile-393-430.png) · [desktop](screens/profile-empty-light-desktop.png) |
| Новый профиль | [320/360](screens/editor-empty-dark-mobile-320-360.png) · [393/430](screens/editor-empty-dark-mobile-393-430.png) · [desktop](screens/editor-empty-dark-desktop.png) | [320/360](screens/editor-empty-light-mobile-320-360.png) · [393/430](screens/editor-empty-light-mobile-393-430.png) · [desktop](screens/editor-empty-light-desktop.png) |
| Изменение профиля | [320/360](screens/editor-filled-dark-mobile-320-360.png) · [393/430](screens/editor-filled-dark-mobile-393-430.png) · [desktop](screens/editor-filled-dark-desktop.png) | [320/360](screens/editor-filled-light-mobile-320-360.png) · [393/430](screens/editor-filled-light-mobile-393-430.png) · [desktop](screens/editor-filled-light-desktop.png) |
| Подтверждение удаления | [320/360](screens/delete-confirm-dark-mobile-320-360.png) · [393/430](screens/delete-confirm-dark-mobile-393-430.png) · [desktop](screens/delete-confirm-dark-desktop.png) | [320/360](screens/delete-confirm-light-mobile-320-360.png) · [393/430](screens/delete-confirm-light-mobile-393-430.png) · [desktop](screens/delete-confirm-light-desktop.png) |
| Каталог без профиля | [320/360](screens/catalog-none-dark-mobile-320-360.png) · [393/430](screens/catalog-none-dark-mobile-393-430.png) · [desktop](screens/catalog-none-dark-desktop.png) | [320/360](screens/catalog-none-light-mobile-320-360.png) · [393/430](screens/catalog-none-light-mobile-393-430.png) · [desktop](screens/catalog-none-light-desktop.png) |
| Каталог: доступные | [320/360](screens/catalog-available-dark-mobile-320-360.png) · [393/430](screens/catalog-available-dark-mobile-393-430.png) · [desktop](screens/catalog-available-dark-desktop.png) | [320/360](screens/catalog-available-light-mobile-320-360.png) · [393/430](screens/catalog-available-light-mobile-393-430.png) · [desktop](screens/catalog-available-light-desktop.png) |
| Каталог: все упражнения | [320/360](screens/catalog-all-dark-mobile-320-360.png) · [393/430](screens/catalog-all-dark-mobile-393-430.png) · [desktop](screens/catalog-all-dark-desktop.png) | [320/360](screens/catalog-all-light-mobile-320-360.png) · [393/430](screens/catalog-all-light-mobile-393-430.png) · [desktop](screens/catalog-all-light-desktop.png) |
| Каталог: нет результатов | [320/360](screens/catalog-empty-dark-mobile-320-360.png) · [393/430](screens/catalog-empty-dark-mobile-393-430.png) · [desktop](screens/catalog-empty-dark-desktop.png) | [320/360](screens/catalog-empty-light-mobile-320-360.png) · [393/430](screens/catalog-empty-light-mobile-393-430.png) · [desktop](screens/catalog-empty-light-desktop.png) |
| Каталог с пустым профилем | [320/360](screens/catalog-empty-profile-dark-mobile-320-360.png) · [393/430](screens/catalog-empty-profile-dark-mobile-393-430.png) · [desktop](screens/catalog-empty-profile-dark-desktop.png) | [320/360](screens/catalog-empty-profile-light-mobile-320-360.png) · [393/430](screens/catalog-empty-profile-light-mobile-393-430.png) · [desktop](screens/catalog-empty-profile-light-desktop.png) |
| Выбор профиля в каталоге | [320/360](screens/catalog-select-dark-mobile-320-360.png) · [393/430](screens/catalog-select-dark-mobile-393-430.png) · [desktop](screens/catalog-select-dark-desktop.png) | [320/360](screens/catalog-select-light-mobile-320-360.png) · [393/430](screens/catalog-select-light-mobile-393-430.png) · [desktop](screens/catalog-select-light-desktop.png) |
| Конструктор: доступные | [320/360](screens/picker-available-dark-mobile-320-360.png) · [393/430](screens/picker-available-dark-mobile-393-430.png) · [desktop](screens/picker-available-dark-desktop.png) | [320/360](screens/picker-available-light-mobile-320-360.png) · [393/430](screens/picker-available-light-mobile-393-430.png) · [desktop](screens/picker-available-light-desktop.png) |
| Конструктор: моделируемая клавиатура | [320/360](screens/picker-keyboard-dark-mobile-320-360.png) · [393/430](screens/picker-keyboard-dark-mobile-393-430.png) | [320/360](screens/picker-keyboard-light-mobile-320-360.png) · [393/430](screens/picker-keyboard-light-mobile-393-430.png) |
| Конструктор: все упражнения | [320/360](screens/picker-all-dark-mobile-320-360.png) · [393/430](screens/picker-all-dark-mobile-393-430.png) · [desktop](screens/picker-all-dark-desktop.png) | [320/360](screens/picker-all-light-mobile-320-360.png) · [393/430](screens/picker-all-light-mobile-393-430.png) · [desktop](screens/picker-all-light-desktop.png) |
| Выбор профиля в конструкторе | [320/360](screens/picker-select-dark-mobile-320-360.png) · [393/430](screens/picker-select-dark-mobile-393-430.png) · [desktop](screens/picker-select-dark-desktop.png) | [320/360](screens/picker-select-light-mobile-320-360.png) · [393/430](screens/picker-select-light-mobile-393-430.png) · [desktop](screens/picker-select-light-desktop.png) |
| Существующий диалог замены | [320/360](screens/replacement-dark-mobile-320-360.png) · [393/430](screens/replacement-dark-mobile-393-430.png) · [desktop](screens/replacement-dark-desktop.png) | [320/360](screens/replacement-light-mobile-320-360.png) · [393/430](screens/replacement-light-mobile-393-430.png) · [desktop](screens/replacement-light-desktop.png) |
| Выбор профиля при замене | [320/360](screens/replacement-select-dark-mobile-320-360.png) · [393/430](screens/replacement-select-dark-mobile-393-430.png) · [desktop](screens/replacement-select-dark-desktop.png) | [320/360](screens/replacement-select-light-mobile-320-360.png) · [393/430](screens/replacement-select-light-mobile-393-430.png) · [desktop](screens/replacement-select-light-desktop.png) |
| Нет сети | [320/360](screens/offline-dark-mobile-320-360.png) · [393/430](screens/offline-dark-mobile-393-430.png) · [desktop](screens/offline-dark-desktop.png) | [320/360](screens/offline-light-mobile-320-360.png) · [393/430](screens/offline-light-mobile-393-430.png) · [desktop](screens/offline-light-desktop.png) |
| Конфликт изменений | [320/360](screens/conflict-dark-mobile-320-360.png) · [393/430](screens/conflict-dark-mobile-393-430.png) · [desktop](screens/conflict-dark-desktop.png) | [320/360](screens/conflict-light-mobile-320-360.png) · [393/430](screens/conflict-light-mobile-393-430.png) · [desktop](screens/conflict-light-desktop.png) |
| Ошибка сохранения | [320/360](screens/error-dark-mobile-320-360.png) · [393/430](screens/error-dark-mobile-393-430.png) · [desktop](screens/error-dark-desktop.png) | [320/360](screens/error-light-mobile-320-360.png) · [393/430](screens/error-light-mobile-393-430.png) · [desktop](screens/error-light-desktop.png) |

Самопроверка в Codex: проверены переносы на 320 px, состояние выбора, контекст фильтра,
трёхколоночный конструктор и порядок оборудования в замене. В отдельных браузерных тестах
проверены переключение с клавиатуры, вложенный диалог, моделируемые safe-area и Telegram Back.
Снимки не являются отдельной визуальной приёмкой владельца.

Для части каталога полные требования оборудования пока не подтверждены. Такие упражнения и
пользовательские движения остаются в каталоге с пометкой «Проверить оборудование»; для
безопасной замены непроверенные варианты могут быть исключены сервером. Это ограничение
данных, а не результат, доказанный изображениями.

Связанные материалы: [Issue #1203](https://github.com/MikeMoore1337/your-fitness-coach/issues/1203),
[PR #1341](https://github.com/MikeMoore1337/your-fitness-coach/pull/1341),
[согласованный до реализации макет](../README.md).
