# Issue #885: AFTER импорта FatSecret

Снимки сделаны в Chromium с синтетическими данными. Окно: 393 × 844 и 1280 × 800; светлая и тёмная темы. Полный экран страницы.

CSV и PDF обработаны приложением через локальный API и отдельную тестовую PostgreSQL; окружающие API приложения заменены тестовыми ответами. Ошибки, восстановление и конфликт воспроизведены тестовыми ответами API. Это не production и не проверка физического устройства.

Реальные CSV/PDF и моделируемые состояния также проверены в WebKit; в обоих браузерах дополнительно проверены ширины 320, 360 и 430 px. Для конфликта сняты только 393 и 1280 px.

| Состояние | Светлая, 393 | Светлая, 1280 | Тёмная, 393 | Тёмная, 1280 |
| --- | --- | --- | --- | --- |
| Выбор файла | [PNG](csv-source-real-light-393.png) | [PNG](csv-source-real-light-1280.png) | [PNG](csv-source-real-dark-393.png) | [PNG](csv-source-real-dark-1280.png) |
| CSV: проверка | [PNG](csv-preview-real-light-393.png) | [PNG](csv-preview-real-light-1280.png) | [PNG](csv-preview-real-dark-393.png) | [PNG](csv-preview-real-dark-1280.png) |
| CSV: уточнение КБЖУ и типа | [PNG](csv-correction-real-light-393.png) | [PNG](csv-correction-real-light-1280.png) | [PNG](csv-correction-real-dark-393.png) | [PNG](csv-correction-real-dark-1280.png) |
| CSV: подтверждение | [PNG](csv-confirmation-real-light-393.png) | [PNG](csv-confirmation-real-light-1280.png) | [PNG](csv-confirmation-real-dark-393.png) | [PNG](csv-confirmation-real-dark-1280.png) |
| CSV: результат | [PNG](csv-result-real-light-393.png) | [PNG](csv-result-real-light-1280.png) | [PNG](csv-result-real-dark-393.png) | [PNG](csv-result-real-dark-1280.png) |
| PDF: проверка | [PNG](pdf-preview-real-light-393.png) | [PNG](pdf-preview-real-light-1280.png) | [PNG](pdf-preview-real-dark-393.png) | [PNG](pdf-preview-real-dark-1280.png) |
| PDF: результат | [PNG](pdf-result-real-light-393.png) | [PNG](pdf-result-real-light-1280.png) | [PNG](pdf-result-real-dark-393.png) | [PNG](pdf-result-real-dark-1280.png) |
| Неподходящий файл | [PNG](mock-invalid-light-393.png) | [PNG](mock-invalid-light-1280.png) | [PNG](mock-invalid-dark-393.png) | [PNG](mock-invalid-dark-1280.png) |
| Пропущенная строка | [PNG](mock-skipped-light-393.png) | [PNG](mock-skipped-light-1280.png) | [PNG](mock-skipped-dark-393.png) | [PNG](mock-skipped-dark-1280.png) |
| Нет ответа на подтверждение | [PNG](mock-uncertain-light-393.png) | [PNG](mock-uncertain-light-1280.png) | [PNG](mock-uncertain-dark-393.png) | [PNG](mock-uncertain-dark-1280.png) |
| Восстановление после перезагрузки | [PNG](mock-recovery-light-393.png) | [PNG](mock-recovery-light-1280.png) | [PNG](mock-recovery-dark-393.png) | [PNG](mock-recovery-dark-1280.png) |
| Конфликт с каталогом | [PNG](conflict-conflict-light-393.png) | [PNG](conflict-conflict-light-1280.png) | [PNG](conflict-conflict-dark-393.png) | [PNG](conflict-conflict-dark-1280.png) |

Нужно решение владельца: принять или отклонить визуальный результат всех состояний. До принятия merge не выполняется.
