# #828 — копирование завершённой тренировки: предложение

Статус: **обновлённый макет для согласования, функция не реализована**. Основа — dev на
a27896659d594dfacfa88901b44355d767c7e732; [Issue #828](https://github.com/MikeMoore1337/your-fitness-coach/issues/828),
[Draft PR #1340](https://github.com/MikeMoore1337/your-fitness-coach/pull/1340).

## Компоновка и поведение

- На экране завершения вторичная кнопка «Скопировать тренировку» расположена сразу
  под итоговыми показателями.
- В истории такая же кнопка находится внутри каждой завершённой тренировки, под её фактами.
- После успешного копирования показывается обычное сообщение «Тренировка скопирована».
- Если буфер обмена недоступен, открывается существующий по стилю диалог с готовым
  текстом, кнопкой «Выделить» и возможностью скопировать текст средствами устройства.
- Пока загружаются подробности исторической тренировки, кнопка показывает загрузку.
  При ошибке загрузки показывается ошибка с предложением повторить попытку; успех
  копирования не объявляется.
- Текст включает только сохранённые название, дату, упражнения и выполненные подходы
  с доступными показателями. Личные заметки и комментарии, идентификаторы и служебные
  данные автоматически не добавляются.

## Снимки

Chromium; mobile — viewport 393 × 844, desktop — 1280 × 900. Сняты обычный кабинет
и работающий локальный DEV, а не демооболочка. Manifest сборки и пять ключевых файлов
этих экранов побайтно совпали с локальной сборкой указанного dev. Снимки «Без кнопки»
показывают реальный существующий экран; остальные элементы макета добавлены в DOM
только для просмотра. Все API-ответы подменены синтетическими данными, DEV-база
не изменялась. Это **не работающий функционал** и не AFTER.

### Завершение

| Состояние | Mobile Light | Mobile Dark | Desktop Light | Desktop Dark |
| --- | --- | --- | --- | --- |
| Без кнопки | [открыть](completion-baseline-mobile-light.png) | [открыть](completion-baseline-mobile-dark.png) | [открыть](completion-baseline-desktop-light.png) | [открыть](completion-baseline-desktop-dark.png) |
| Действие | [открыть](completion-mobile-light.png) | [открыть](completion-mobile-dark.png) | [открыть](completion-desktop-light.png) | [открыть](completion-desktop-dark.png) |
| Результаты раскрыты | [открыть](completion-expanded-mobile-light.png) | [открыть](completion-expanded-mobile-dark.png) | [открыть](completion-expanded-desktop-light.png) | [открыть](completion-expanded-desktop-dark.png) |
| Успех | [открыть](completion-success-mobile-light.png) | [открыть](completion-success-mobile-dark.png) | [открыть](completion-success-desktop-light.png) | [открыть](completion-success-desktop-dark.png) |
| Ручное копирование | [открыть](completion-fallback-mobile-light.png) | [открыть](completion-fallback-mobile-dark.png) | [открыть](completion-fallback-desktop-light.png) | [открыть](completion-fallback-desktop-dark.png) |

### История

| Состояние | Mobile Light | Mobile Dark | Desktop Light | Desktop Dark |
| --- | --- | --- | --- | --- |
| Без кнопки | [открыть](history-baseline-mobile-light.png) | [открыть](history-baseline-mobile-dark.png) | [открыть](history-baseline-desktop-light.png) | [открыть](history-baseline-desktop-dark.png) |
| Действие | [открыть](history-mobile-light.png) | [открыть](history-mobile-dark.png) | [открыть](history-desktop-light.png) | [открыть](history-desktop-dark.png) |
| Две записи | [открыть](history-second-mobile-light.png) | [открыть](history-second-mobile-dark.png) | [открыть](history-second-desktop-light.png) | [открыть](history-second-desktop-dark.png) |
| Успех | [открыть](history-success-mobile-light.png) | [открыть](history-success-mobile-dark.png) | [открыть](history-success-desktop-light.png) | [открыть](history-success-desktop-dark.png) |
| Ручное копирование | [открыть](history-fallback-mobile-light.png) | [открыть](history-fallback-mobile-dark.png) | [открыть](history-fallback-desktop-light.png) | [открыть](history-fallback-desktop-dark.png) |

Нужно решение владельца по обеим точкам входа и ручному варианту. После согласования:
реализация и функциональные проверки, затем отдельная приёмка настоящих AFTER и
разрешённая пользователем интеграция только в dev.
