# #1203 · Профили оборудования — визуальное предложение

**Статус: макет, реализация не начата.** Изображения и HTML содержат только условные данные.
Кнопки в прототипе показывают переходы между нарисованными состояниями и не сохраняют данные.
Принятие этого макета требуется до изменения рабочего интерфейса; после реализации потребуются
отдельная визуальная приёмка и разрешённая проверка DEV.

Основа: `dev` `a27896659d594dfacfa88901b44355d767c7e732`, существующие Oswald/Inter,
светлая и тёмная темы YFC, общие состояния выбора и мобильная навигация. Это развитие текущего
интерфейса, не новая дизайн-система. Desktop-редактор сохраняет день в центральной колонке.

## Что показано

Изображения ниже содержат **реальные рендеры HTML-макета в Chromium**: mobile — при ширине
320, 360, 393 и 430 CSS px, desktop — при ширине 1280 CSS px. Верхний ряд — начало экрана, нижний — после прокрутки
страницы или открытого диалога. Высоты: 760, 800, 852, 932 и 900 px соответственно.

| Состояние | Dark | Light |
| --- | --- | --- |
| Несколько профилей, активен «Дом» | [mobile](screens/profiles-dark-mobile.png) · [desktop](screens/profiles-dark-desktop.png) | [mobile](screens/profiles-light-mobile.png) · [desktop](screens/profiles-light-desktop.png) |
| Активен пустой профиль «Поездка» | [mobile](screens/profile-empty-dark-mobile.png) · [desktop](screens/profile-empty-dark-desktop.png) | [mobile](screens/profile-empty-light-mobile.png) · [desktop](screens/profile-empty-light-desktop.png) |
| Создание пустого профиля | [mobile](screens/editor-empty-dark-mobile.png) · [desktop](screens/editor-empty-dark-desktop.png) | [mobile](screens/editor-empty-light-mobile.png) · [desktop](screens/editor-empty-light-desktop.png) |
| Редактирование профиля | [mobile](screens/editor-filled-dark-mobile.png) · [desktop](screens/editor-filled-dark-desktop.png) | [mobile](screens/editor-filled-light-mobile.png) · [desktop](screens/editor-filled-light-desktop.png) |
| Подтверждение удаления | [mobile](screens/delete-confirm-dark-mobile.png) · [desktop](screens/delete-confirm-dark-desktop.png) | [mobile](screens/delete-confirm-light-mobile.png) · [desktop](screens/delete-confirm-light-desktop.png) |
| Каталог без выбранного профиля | [mobile](screens/catalog-none-dark-mobile.png) · [desktop](screens/catalog-none-dark-desktop.png) | [mobile](screens/catalog-none-light-mobile.png) · [desktop](screens/catalog-none-light-desktop.png) |
| Каталог: доступные | [mobile](screens/catalog-available-dark-mobile.png) · [desktop](screens/catalog-available-dark-desktop.png) | [mobile](screens/catalog-available-light-mobile.png) · [desktop](screens/catalog-available-light-desktop.png) |
| Каталог: все упражнения | [mobile](screens/catalog-all-dark-mobile.png) · [desktop](screens/catalog-all-dark-desktop.png) | [mobile](screens/catalog-all-light-mobile.png) · [desktop](screens/catalog-all-light-desktop.png) |
| Каталог: нет результата | [mobile](screens/catalog-empty-dark-mobile.png) · [desktop](screens/catalog-empty-dark-desktop.png) | [mobile](screens/catalog-empty-light-mobile.png) · [desktop](screens/catalog-empty-light-desktop.png) |
| Каталог с пустым профилем | [mobile](screens/catalog-empty-profile-dark-mobile.png) · [desktop](screens/catalog-empty-profile-dark-desktop.png) | [mobile](screens/catalog-empty-profile-light-mobile.png) · [desktop](screens/catalog-empty-profile-light-desktop.png) |
| Выбор упражнения в программе: доступные | [mobile](screens/picker-dark-mobile.png) · [desktop](screens/picker-dark-desktop.png) | [mobile](screens/picker-light-mobile.png) · [desktop](screens/picker-light-desktop.png) |
| Выбор упражнения в программе: все | [mobile](screens/picker-all-dark-mobile.png) · [desktop](screens/picker-all-dark-desktop.png) | [mobile](screens/picker-all-light-mobile.png) · [desktop](screens/picker-all-light-desktop.png) |
| Выбор профиля в конструкторе | [mobile](screens/picker-profile-dark-mobile.png) · [desktop](screens/picker-profile-dark-desktop.png) | [mobile](screens/picker-profile-light-mobile.png) · [desktop](screens/picker-profile-light-desktop.png) |
| Существующий диалог безопасной замены | [320/360](screens/replacement-dark-320-360.png) · [393/430](screens/replacement-dark-393-430.png) · [desktop](screens/replacement-dark-desktop.png) | [320/360](screens/replacement-light-320-360.png) · [393/430](screens/replacement-light-393-430.png) · [desktop](screens/replacement-light-desktop.png) |
| Выбор профиля для замены | [mobile](screens/replacement-profile-dark-mobile.png) · [desktop](screens/replacement-profile-dark-desktop.png) | [mobile](screens/replacement-profile-light-mobile.png) · [desktop](screens/replacement-profile-light-desktop.png) |
| Нет подключения | [mobile](screens/offline-dark-mobile.png) · [desktop](screens/offline-dark-desktop.png) | [mobile](screens/offline-light-mobile.png) · [desktop](screens/offline-light-desktop.png) |
| Одновременное изменение | [mobile](screens/conflict-dark-mobile.png) · [desktop](screens/conflict-dark-desktop.png) | [mobile](screens/conflict-light-mobile.png) · [desktop](screens/conflict-light-desktop.png) |
| Ошибка сохранения | [mobile](screens/error-dark-mobile.png) · [desktop](screens/error-dark-desktop.png) | [mobile](screens/error-light-mobile.png) · [desktop](screens/error-light-desktop.png) |

[HTML-макет](prototype.html) · [три исходные схемы](screens/directions.png) ·
[текущие экраны до изменений](before/)

Для локального просмотра HTML доступны параметры, например
`prototype.html?state=picker&theme=dark`. Список состояний соответствует именам строк таблицы;
это демонстратор, а не работающее приложение.

## Краткий аудит текущего dev

Снимки `before/` получены в Chromium на 393×844 и 1280×900 в двух темах. API подменён
тестовыми ответами. Локальный backend не запускался: отдельные запросы к изображениям получили
`ECONNREFUSED`. Это рендер текущих компонентов с неполными медиа, но не production и не проверка
физического устройства.

1. **Каталог:** уже фильтрует по отдельному виду оборудования, но не показывает выбранный
   личный набор и не разделяет доступные и все упражнения. Снимки: `before/catalog-*`;
   источник — `frontend/src/features/exercises/ExerciseCatalog.tsx`.
2. **Конструктор:** выбор уже находится в мобильной шторке и в правой desktop-панели;
   повторное использование этого места сохраняет центральный день. Снимки: `before/picker-*`;
   источник — `ProgramDayEditor.tsx` и `SearchableExercisePicker.tsx`.
3. **Замена:** оборудование выбирается вручную для текущей операции и отправляется в
   существующий серверный механизм. Снимки: `before/replacement-*`; источник —
   `WorkoutAdaptation.tsx` и `services/workout_adaptation.py`. Снимок показывает тестовое
   состояние загрузки вариантов, а не доказательство серверной совместимости.

Три структуры предварительно нарисованы в [сравнении](screens/directions.png). Выбрана A:
управление профилями отдельно, контекст и переключатель рядом с результатами. B занимает
слишком много места над результатами на телефоне; C вводит обязательный шаг перед поиском.
Для YFC здесь нужны названия реального оборудования, понятная маркировка неполных сведений и
сохранение рабочего контекста, а не декоративные карточки, маркетинговый экран или вымышленные
фотографии упражнений.

## Контракт предлагаемого поведения

- Без профиля прежний список и существующие фильтры продолжают работать. Выбор «Доступное» /
  «Все упражнения» показан при активном профиле.
- Пустой профиль не означает, что пользовательские упражнения исчезают: упражнения с неизвестными
  требованиями остаются видимыми с пометкой «Проверить». Упражнения без дополнительных
  принадлежностей могут быть показаны как доступные.
- Выбор профиля не изменяет программу, рабочие веса или историю. В конструкторе выбор профиля
  сохраняет текущий черновик. В замене пользователь может изменить основное оборудование для
  конкретного действия; дополнительные принадлежности берутся из выбранного профиля. Совместимость
  и применение остаются на сервере.
- Ошибки сети и конфликт версий сохраняют введённые данные на экране; успешное сохранение нельзя
  показывать до ответа сервера.

## Техническая неопределённость до реализации

Текущая синхронизация оборудования сохраняет один основной `equipment_id`, а турник и брусья
сводит к `bodyweight`. Существующий контракт замены принимает до девяти известных идентификаторов;
отдельные стойка, турник и брусья в этом перечне отсутствуют. Поэтому пример с принадлежностями
на макете — **предложение**, а не утверждение о работающей серверной проверке. Необходима
совместимая реализация, которая не обходит существующую проверку и учитывает запрет на правки
общего workout API, пересекающегося с #1132. До её доказательства доступность таких упражнений
нельзя считать подтверждённой.

Пользовательские именованные профили нельзя без анализа подменить существующими предпочтениями
мест тренировки: те имеют фиксированные типы, используются рекомендациями и могут изменяться
тренером для клиента. Права и параллельные изменения необходимо проверить на сервере.

На момент аудита [PR #1314](https://github.com/MikeMoore1337/your-fitness-coach/pull/1314)
из #1132 изменяет `api/v1/workouts.py`, `schemas/workout.py` и
`frontend/src/shared/api/schema.d.ts`. Первые два файла исключены владельцем из области #1203;
для генерируемой схемы возможен конфликт при дальнейшей реализации. Визуальные файлы этого
пакета не пересекаются с опубликованными файлами открытых PR. В локальном worktree #1195 на
момент проверки отслеживаемых изменений относительно `dev` не было. Открытый
[PR #1340](https://github.com/MikeMoore1337/your-fitness-coach/pull/1340) для #828 пока меняет
только собственный каталог макетов. Перед реализацией эти сведения нужно обновить.

## Проверка макета и ограничения

- 180 сочетаний состояния, темы и viewport отрисованы в Chromium; проверены ошибки страницы и
  отсутствие горизонтального переполнения документа и подписей оборудования.
- Исходные экраны каталога, конструктора и замены сняты в Chromium на синтетических данных.
- Это не тест рабочего UI: сохранение, серверные проверки, WebKit, PWA/TMA, физическое
  устройство, полный keyboard/a11y, CI и DEV пока не подтверждены.
- Методы Toolkit и текстовые руководства Impeccable прочитаны; launcher и детектор Impeccable
  по правилам проекта не запускались. Независимый QA ещё не выполнен.
