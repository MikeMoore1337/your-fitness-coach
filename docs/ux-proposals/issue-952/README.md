# Issue #952 — макет целей КБЖУ по дням

Это один интерактивный прототип для визуального согласования. Данные вымышлены; прототип не подключён к API, не сохраняет изменения и не является скриншотом реализованной функции.

- База исследования: dev d37183fbff3c69ddf21b1e2df1117ab5f3da3664.
- Контекст дневника: [мобильный Dark](https://github.com/MikeMoore1337/your-fitness-coach/blob/da94fdc508f5ac1a3e46f9ef9b8ec267bddef715/docs/ux-proposals/issue-1429/after/chromium-dark-393-partial.png) и [desktop Light](https://github.com/MikeMoore1337/your-fitness-coach/blob/da94fdc508f5ac1a3e46f9ef9b8ec267bddef715/docs/ux-proposals/issue-1429/after/chromium-light-1280-partial.png) из открытого Draft PR #1437. Это evidence параллельной ветки, а не подтверждение production.
- [Открыть HTML-прототип](preview.html). Верхняя строка переключает состояния и тему; редактирование и подтверждение показаны только для примера.
- Chromium: мобильные viewport 390×844 и 320×720, desktop 1280×900, обе темы. Полные мобильные снимки сделаны со скрытой нижней панелью, чтобы она не перекрывала содержимое при склейке всей страницы; рядом приведены снимки реального viewport с панелью.
- Проверены отсутствие горизонтального переполнения, размещение кнопок внутри панелей и примеры переключения области, темы и редактируемых значений. Это проверка макета, не E2E продукта.

## Все состояния

| Состояние | Mobile Dark | Mobile Light | Desktop Dark | Desktop Light |
| --- | --- | --- | --- | --- |
| Цель на дату | [полный](evidence/chromium-390x844-dark-day.png) · [экран](evidence/chromium-390x844-dark-day-viewport.png) | [полный](evidence/chromium-390x844-light-day.png) · [экран](evidence/chromium-390x844-light-day-viewport.png) | [1280×900](evidence/chromium-1280x900-dark-day.png) | [1280×900](evidence/chromium-1280x900-light-day.png) |
| Базовая цель, типы дней и недель | [полный](evidence/chromium-390x844-dark-settings.png) · [экран](evidence/chromium-390x844-dark-settings-viewport.png) | [полный](evidence/chromium-390x844-light-settings.png) · [экран](evidence/chromium-390x844-light-settings-viewport.png) | [1280×900](evidence/chromium-1280x900-dark-settings.png) | [1280×900](evidence/chromium-1280x900-light-settings.png) |
| Ручное изменение и область действия | [полный](evidence/chromium-390x844-dark-override.png) · [экран](evidence/chromium-390x844-dark-override-viewport.png) | [полный](evidence/chromium-390x844-light-override.png) · [экран](evidence/chromium-390x844-light-override-viewport.png) | [1280×900](evidence/chromium-1280x900-dark-override.png) | [1280×900](evidence/chromium-1280x900-light-override.png) |
| Подтверждение одной даты | [полный](evidence/chromium-390x844-dark-single.png) · [экран](evidence/chromium-390x844-dark-single-viewport.png) | [полный](evidence/chromium-390x844-light-single.png) · [экран](evidence/chromium-390x844-light-single-viewport.png) | [1280×900](evidence/chromium-1280x900-dark-single.png) | [1280×900](evidence/chromium-1280x900-light-single.png) |
| Подтверждение будущих повторений | [полный](evidence/chromium-390x844-dark-future.png) · [экран](evidence/chromium-390x844-dark-future-viewport.png) | [полный](evidence/chromium-390x844-light-future.png) · [экран](evidence/chromium-390x844-light-future-viewport.png) | [1280×900](evidence/chromium-1280x900-dark-future.png) | [1280×900](evidence/chromium-1280x900-light-future.png) |
| Изменение программы и конфликт | [полный](evidence/chromium-390x844-dark-conflict.png) · [экран](evidence/chromium-390x844-dark-conflict-viewport.png) | [полный](evidence/chromium-390x844-light-conflict.png) · [экран](evidence/chromium-390x844-light-conflict-viewport.png) | [1280×900](evidence/chromium-1280x900-dark-conflict.png) | [1280×900](evidence/chromium-1280x900-light-conflict.png) |
| Проверка пересчёта | [полный](evidence/chromium-390x844-dark-preview.png) · [экран](evidence/chromium-390x844-dark-preview-viewport.png) | [полный](evidence/chromium-390x844-light-preview.png) · [экран](evidence/chromium-390x844-light-preview-viewport.png) | [1280×900](evidence/chromium-1280x900-dark-preview.png) | [1280×900](evidence/chromium-1280x900-light-preview.png) |
| Цель не задана | [полный](evidence/chromium-390x844-dark-empty.png) · [экран](evidence/chromium-390x844-dark-empty-viewport.png) | [полный](evidence/chromium-390x844-light-empty.png) · [экран](evidence/chromium-390x844-light-empty-viewport.png) | [1280×900](evidence/chromium-1280x900-dark-empty.png) | [1280×900](evidence/chromium-1280x900-light-empty.png) |

Узкий экран 320×720: [настройки Dark](evidence/chromium-320x720-dark-settings.png), [настройки Light](evidence/chromium-320x720-light-settings.png), [изменение Dark](evidence/chromium-320x720-dark-override.png), [изменение Light](evidence/chromium-320x720-light-override.png), [конфликт Dark](evidence/chromium-320x720-dark-conflict.png), [конфликт Light](evidence/chromium-320x720-light-conflict.png), [одна дата Dark](evidence/chromium-320x720-dark-single.png), [одна дата Light](evidence/chromium-320x720-light-single.png). Для каждого есть соседний файл с суффиксом -viewport и нижней панелью.

## Решение владельца

Оценить пакет целиком: расположение цели на выбранную дату; базовую цель, типы дней и недель; ручное изменение одной даты или будущих повторений; предупреждение об изменении программы и отдельное подтверждение; отсутствие цели.

Принятие макета разрешает только реализацию согласованной композиции. После реализации нужны реальные AFTER-снимки, отдельная визуальная приёмка и отдельное решение о выпуске.
