# #1440 · Питание: единый макет, этап A

Это **проектное предложение**, а не работающий экран, релиз или подтверждение исправлений. Данные вымышлены. База приложения — [dev d37183fb](https://github.com/MikeMoore1337/your-fitness-coach/commit/d37183fbff3c69ddf21b1e2df1117ab5f3da3664), включая #951. Отдельно учтён [AFTER Draft PR #1437, da94fdc5](https://github.com/MikeMoore1337/your-fitness-coach/blob/da94fdc508f5ac1a3e46f9ef9b8ec267bddef715/docs/ux-proposals/issue-1429/after/README.md); изменения в этой ветке не выполнялись.

## Интерактивный макет

[Скачать автономный HTML](preview/nutrition-1440.html) через кнопку Download в GitHub и открыть сохранённый файл в браузере. Верхняя служебная панель переключает тему и основные состояния; её нет на снимках приложения ниже. Состояние прототипа хранится только в памяти вкладки и сбрасывается при перезагрузке. Сетевые запросы и сохранение в реальный дневник отсутствуют. Некоторые дополнительные разделы и части выбора продукта показаны как точки входа: их содержимое и реальные интеграции здесь не реализованы. [Принятый реальный интерфейс выбора продуктов #951](https://github.com/MikeMoore1337/your-fitness-coach/blob/d69e443068d2f5a9755253155e738e5f5f5e16f8/docs/ux-proposals/issue-951/after/README.md) остаётся источником подробностей.

Использованы оригинальные YFC WeekStrip, Button, Field, Input, Select, Icon, стили и токены из dev; новые файлы — только изолированный прототип. [Исходник макета](preview/main.tsx), [стили](preview/prototype.css), [лицензии шрифтов и библиотек](preview/licenses/).

## Основная матрица

Полная страница, окно **320/360/393/430 × 844** и **1280 × 900 CSS px**. На длинном снимке закреплённый dock показан в позиции первого экрана; отдельные кадры «экран» показывают обычный viewport. Chromium 151.0.7922.34, WebKit 26.5.

| Ширина | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
|---|---|---|---|---|
| 320 | [заполнен](evidence/chromium-light-320-filled.png) · [пустой](evidence/chromium-light-320-empty.png) · [экран](evidence/chromium-light-320-viewport.png) | [заполнен](evidence/chromium-dark-320-filled.png) · [пустой](evidence/chromium-dark-320-empty.png) · [экран](evidence/chromium-dark-320-viewport.png) | [заполнен](evidence/webkit-light-320-filled.png) · [пустой](evidence/webkit-light-320-empty.png) · [экран](evidence/webkit-light-320-viewport.png) | [заполнен](evidence/webkit-dark-320-filled.png) · [пустой](evidence/webkit-dark-320-empty.png) · [экран](evidence/webkit-dark-320-viewport.png) |
| 360 | [заполнен](evidence/chromium-light-360-filled.png) · [пустой](evidence/chromium-light-360-empty.png) · [экран](evidence/chromium-light-360-viewport.png) | [заполнен](evidence/chromium-dark-360-filled.png) · [пустой](evidence/chromium-dark-360-empty.png) · [экран](evidence/chromium-dark-360-viewport.png) | [заполнен](evidence/webkit-light-360-filled.png) · [пустой](evidence/webkit-light-360-empty.png) · [экран](evidence/webkit-light-360-viewport.png) | [заполнен](evidence/webkit-dark-360-filled.png) · [пустой](evidence/webkit-dark-360-empty.png) · [экран](evidence/webkit-dark-360-viewport.png) |
| 393 | [заполнен](evidence/chromium-light-393-filled.png) · [пустой](evidence/chromium-light-393-empty.png) · [экран](evidence/chromium-light-393-viewport.png) | [заполнен](evidence/chromium-dark-393-filled.png) · [пустой](evidence/chromium-dark-393-empty.png) · [экран](evidence/chromium-dark-393-viewport.png) | [заполнен](evidence/webkit-light-393-filled.png) · [пустой](evidence/webkit-light-393-empty.png) · [экран](evidence/webkit-light-393-viewport.png) | [заполнен](evidence/webkit-dark-393-filled.png) · [пустой](evidence/webkit-dark-393-empty.png) · [экран](evidence/webkit-dark-393-viewport.png) |
| 430 | [заполнен](evidence/chromium-light-430-filled.png) · [пустой](evidence/chromium-light-430-empty.png) · [экран](evidence/chromium-light-430-viewport.png) | [заполнен](evidence/chromium-dark-430-filled.png) · [пустой](evidence/chromium-dark-430-empty.png) · [экран](evidence/chromium-dark-430-viewport.png) | [заполнен](evidence/webkit-light-430-filled.png) · [пустой](evidence/webkit-light-430-empty.png) · [экран](evidence/webkit-light-430-viewport.png) | [заполнен](evidence/webkit-dark-430-filled.png) · [пустой](evidence/webkit-dark-430-empty.png) · [экран](evidence/webkit-dark-430-viewport.png) |
| 1280 | [заполнен](evidence/chromium-light-1280-filled.png) · [пустой](evidence/chromium-light-1280-empty.png) · [экран](evidence/chromium-light-1280-viewport.png) | [заполнен](evidence/chromium-dark-1280-filled.png) · [пустой](evidence/chromium-dark-1280-empty.png) · [экран](evidence/chromium-dark-1280-viewport.png) | [заполнен](evidence/webkit-light-1280-filled.png) · [пустой](evidence/webkit-light-1280-empty.png) · [экран](evidence/webkit-light-1280-viewport.png) | [заполнен](evidence/webkit-dark-1280-filled.png) · [пустой](evidence/webkit-dark-1280-empty.png) · [экран](evidence/webkit-dark-1280-viewport.png) |

## Состояния и действия · 393 × 844

| Сценарий | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
|---|---|---|---|---|
| Раскрытый приём и длинное название | [открыть](evidence/chromium-light-393-meal-open.png) | [открыть](evidence/chromium-dark-393-meal-open.png) | [открыть](evidence/webkit-light-393-meal-open.png) | [открыть](evidence/webkit-dark-393-meal-open.png) |
| Повтор и отмена | [открыть](evidence/chromium-light-393-repeat-undo.png) | [открыть](evidence/chromium-dark-393-repeat-undo.png) | [открыть](evidence/webkit-light-393-repeat-undo.png) | [открыть](evidence/webkit-dark-393-repeat-undo.png) |
| Выбор трёх продуктов | [открыть](evidence/chromium-light-393-picker-3.png) | [открыть](evidence/chromium-dark-393-picker-3.png) | [открыть](evidence/webkit-light-393-picker-3.png) | [открыть](evidence/webkit-dark-393-picker-3.png) |
| Другие способы добавления | [открыть](evidence/chromium-light-393-picker-paths.png) | [открыть](evidence/chromium-dark-393-picker-paths.png) | [открыть](evidence/webkit-light-393-picker-paths.png) | [открыть](evidence/webkit-dark-393-picker-paths.png) |
| Другой напиток и объём | [открыть](evidence/chromium-light-393-custom-water.png) | [открыть](evidence/chromium-dark-393-custom-water.png) | [открыть](evidence/webkit-light-393-custom-water.png) | [открыть](evidence/webkit-dark-393-custom-water.png) |
| Вся история воды | [открыть](evidence/chromium-light-393-history-open.png) | [открыть](evidence/chromium-dark-393-history-open.png) | [открыть](evidence/webkit-light-393-history-open.png) | [открыть](evidence/webkit-dark-393-history-open.png) |
| Редактирование записи воды | [открыть](evidence/chromium-light-393-history-edit.png) | [открыть](evidence/chromium-dark-393-history-edit.png) | [открыть](evidence/webkit-light-393-history-edit.png) | [открыть](evidence/webkit-dark-393-history-edit.png) |
| Подтверждение удаления | [открыть](evidence/chromium-light-393-history-delete.png) | [открыть](evidence/chromium-dark-393-history-delete.png) | [открыть](evidence/webkit-light-393-history-delete.png) | [открыть](evidence/webkit-dark-393-history-delete.png) |
| Справочный ориентир | [открыть](evidence/chromium-light-393-water-reference.png) | [открыть](evidence/chromium-dark-393-water-reference.png) | [открыть](evidence/webkit-light-393-water-reference.png) | [открыть](evidence/webkit-dark-393-water-reference.png) |
| Мои кружки и бутылки | [открыть](evidence/chromium-light-393-presets-open.png) | [открыть](evidence/chromium-dark-393-presets-open.png) | [открыть](evidence/webkit-light-393-presets-open.png) | [открыть](evidence/webkit-dark-393-presets-open.png) |
| Неизвестен результат записи | [открыть](evidence/chromium-light-393-water-uncertain.png) | [открыть](evidence/chromium-dark-393-water-uncertain.png) | [открыть](evidence/webkit-light-393-water-uncertain.png) | [открыть](evidence/webkit-dark-393-water-uncertain.png) |
| Без ориентира воды | [открыть](evidence/chromium-light-393-no-goal.png) | [открыть](evidence/chromium-dark-393-no-goal.png) | [открыть](evidence/webkit-light-393-no-goal.png) | [открыть](evidence/webkit-dark-393-no-goal.png) |
| Выше ориентира | [открыть](evidence/chromium-light-393-water-over.png) | [открыть](evidence/chromium-dark-393-water-over.png) | [открыть](evidence/webkit-light-393-water-over.png) | [открыть](evidence/webkit-dark-393-water-over.png) |
| Неизвестные нутриенты | [открыть](evidence/chromium-light-393-unknown.png) | [открыть](evidence/chromium-dark-393-unknown.png) | [открыть](evidence/webkit-light-393-unknown.png) | [открыть](evidence/webkit-dark-393-unknown.png) |
| Настройки КБЖУ открыты | [открыть](evidence/chromium-light-393-extra-open.png) | [открыть](evidence/chromium-dark-393-extra-open.png) | [открыть](evidence/webkit-light-393-extra-open.png) | [открыть](evidence/webkit-dark-393-extra-open.png) |
| План питания открыт | [открыть](evidence/chromium-light-393-plan-open.png) | [открыть](evidence/chromium-dark-393-plan-open.png) | [открыть](evidence/webkit-light-393-plan-open.png) | [открыть](evidence/webkit-dark-393-plan-open.png) |
| Список покупок открыт | [открыть](evidence/chromium-light-393-shopping-open.png) | [открыть](evidence/chromium-dark-393-shopping-open.png) | [открыть](evidence/webkit-light-393-shopping-open.png) | [открыть](evidence/webkit-dark-393-shopping-open.png) |
| Загрузка дневника | [открыть](evidence/chromium-light-393-loading.png) | [открыть](evidence/chromium-dark-393-loading.png) | [открыть](evidence/webkit-light-393-loading.png) | [открыть](evidence/webkit-dark-393-loading.png) |
| Ошибка дневника | [открыть](evidence/chromium-light-393-error.png) | [открыть](evidence/chromium-dark-393-error.png) | [открыть](evidence/webkit-light-393-error.png) | [открыть](evidence/webkit-dark-393-error.png) |
| Загрузка воды | [открыть](evidence/chromium-light-393-water-loading.png) | [открыть](evidence/chromium-dark-393-water-loading.png) | [открыть](evidence/webkit-light-393-water-loading.png) | [открыть](evidence/webkit-dark-393-water-loading.png) |
| Ошибка воды | [открыть](evidence/chromium-light-393-water-error.png) | [открыть](evidence/chromium-dark-393-water-error.png) | [открыть](evidence/webkit-light-393-water-error.png) | [открыть](evidence/webkit-dark-393-water-error.png) |
| Копирование и дата назначения | [открыть](evidence/chromium-light-393-copy-preview.png) | [открыть](evidence/chromium-dark-393-copy-preview.png) | [открыть](evidence/webkit-light-393-copy-preview.png) | [открыть](evidence/webkit-dark-393-copy-preview.png) |
| Глобальное меню + | [открыть](evidence/chromium-light-393-plus-menu.png) | [открыть](evidence/chromium-dark-393-plus-menu.png) | [открыть](evidence/webkit-light-393-plus-menu.png) | [открыть](evidence/webkit-dark-393-plus-menu.png) |
| Переход к воде и нижний dock | [открыть](evidence/chromium-light-393-water-viewport.png) | [открыть](evidence/chromium-dark-393-water-viewport.png) | [открыть](evidence/webkit-light-393-water-viewport.png) | [открыть](evidence/webkit-dark-393-water-viewport.png) |
| Фокус при уменьшенном окне 393 × 430 | [открыть](evidence/chromium-light-393-short-viewport-focus.png) | [открыть](evidence/chromium-dark-393-short-viewport-focus.png) | [открыть](evidence/webkit-light-393-short-viewport-focus.png) | [открыть](evidence/webkit-dark-393-short-viewport-focus.png) |

Длинное название ёмкости: [chromium light](evidence/chromium-light-320-long-name.png) · [chromium dark](evidence/chromium-dark-320-long-name.png) · [webkit light](evidence/webkit-light-320-long-name.png) · [webkit dark](evidence/webkit-dark-320-long-name.png) · 

Узкий reflow 160 × 422 CSS px (приближение доступной ширины, **не проверка фактического browser zoom 200%**): [chromium light](evidence/chromium-light-160-reflow.png) · [chromium dark](evidence/chromium-dark-160-reflow.png) · [webkit light](evidence/webkit-light-160-reflow.png) · [webkit dark](evidence/webkit-dark-160-reflow.png) · 

## До и предложено

- **До, dev:** [сопоставление #1429, 393 Light](https://github.com/MikeMoore1337/your-fitness-coach/blob/44dacca74aef179ec2f30d3029ba97835333f95e/docs/ux-proposals/issue-1429/comparison-393-partial-light.png) и [Dark](https://github.com/MikeMoore1337/your-fitness-coach/blob/44dacca74aef179ec2f30d3029ba97835333f95e/docs/ux-proposals/issue-1429/comparison-393-partial-dark.png): после КБЖУ рекомендации и проверка предшествуют еде. В #1437 порядок уже изменён; это отдельный ещё не интегрированный PR.
- **Предложено:** дата и неделя → еда/вода → компактные КБЖУ → четыре приёма → вода → статус дня и подбор → настройки, план и покупки. Быстрый повтор предложен в строке подходящего приёма, с отменой.
- В карточке воды — 1 нажатие на объём; с первого экрана макета — 2 действия: «Добавить воду» и объём. В существующем пути из другого экрана независимый аудит измерил 3 действия: «+» → «Вода» → объём. Это сравнение разных точек входа, а не замер времени или производительности.
- #950 зафиксировал 1/3/6 продуктов как **4/10/19 действий**, а опубликованный результат #951 — **4/8/14** по его методике. Данный дизайн-прототип не выполняет настоящий batch commit и не является новым измерением #951. Field p95 и пользовательское ускорение: NO_DATA.
- Скролл: водная кнопка на первом экране переводит к быстрым объёмам без ручной прокрутки; абсолютные расстояния в ранее опубликованном BEFORE и данном макете получены на разных фикстурах и не считаются сопоставимым выигрышем.

## Соответствие связанным задачам

| Контракт | Как отражён в макете / что остаётся отдельной работой |
|---|---|
| #1430, #1435 | КБЖУ каждого приёма и 2×2 на мобильном; «— / нет данных» отдельно от нуля. Серверные агрегаты и цели по датам не меняются. |
| #1431, #1432 | Кнопка копирования, выбор другой даты и предпросмотр; исправление текущего 422 не реализовано. |
| #1433, #1436 | Компактные подбор и статус дня с доступными раскрытиями. Ранжирование и все реальные статусы требуют реализации и тестов. |
| #1434 / #1429 | Повтор расположен у приёма; проектное действие в одно нажатие с отменой сохраняет принятую механику #1429. Требование #1434 о preview и подтверждении для повтора конфликтует с этой механикой: требуется решение владельца. Копирование в другую дату показывает preview. |
| #869, #868, #1048, #1441, #1442 | Три быстрых объёма, три последние записи, полная история, свои ёмкости, ориентир, одно раскрытие настроек КБЖУ, план/покупки; глобальное + ведёт к воде. |
| #880, #952–#956 | Будущие точки интеграции: импорт/источник — существующий каталог и выбор продуктов; датированные цели — настройки КБЖУ; объяснения — подбор/отчёт; тренер — существующий Coach OS; текстовый ввод — выбор продуктов; необязательные заметки — контекст приёма после privacy-решения. Это места для будущих согласований, не заявления о готовности функций. Фото блюда показано недоступным. |

[Независимый аудит #1441](https://github.com/MikeMoore1337/your-fitness-coach/issues/1441#issuecomment-6687648271): учтены привязка отмены к дню, видимый тип напитка в пресете, перенос длинного имени, пустая/выключенная цель, фактическое превышение и отдельное состояние сомнительного результата с безопасным повтором. Прототип не доказывает исправление A1/A2, идемпотентность или отсутствие потери данных в приложении.

## Проверки и ограничения

- Локальные скриншоты и взаимодействия: Chromium и WebKit, обе темы, 320/360/393/430/1280, пустой/заполненный день. Проверены отсутствие горизонтального переполнения страницы и размеры доступных controls не меньше 44 CSS px в базовых состояниях, длинном названии и reflow; отдельные сценарии перечислены в матрице. [Машинный итог](evidence/checks.json).
- На синтетическом макете проверены выбор 1/3/6 продуктов, открытие/закрытие приёма, быстрый ввод воды и отмена, смена даты, видимый фокус воды над dock, + → Вода, полная история, формы, диалог копирования с запрещённой исходной датой и Escape. Это не проверка API, БД, реального сохранения или состояния production.
- Модель 393 × 430 и узкий reflow — не системная клавиатура и не реальный browser zoom. Физические iPhone/Android, Safari на устройстве, реальный Telegram/PWA, VoiceOver/другие screen reader, полный контраст и все платформенные состояния: NOT_VERIFIED.
- #1441 A1/A2 требуют будущего исправления и регрессионных тестов на реальных контрактах; независимый аудит и макет не являются approval кода. #1437 и runtime не менялись; merge/deploy не выполнялись.

**Решение владельца:** принять этот единый Dark/Light макет для дальнейшей отдельной реализации или указать конкретные изменения? Отдельно выбрать семантику повтора: сохранить одно нажатие с отменой либо требовать предварительный просмотр и подтверждение. Визуальное утверждение не означает разрешение на этапы B/C/D или выпуск.
