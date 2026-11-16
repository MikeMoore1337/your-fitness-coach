# QA импорта FatSecret — #888, 16 ноября 2026

**Итог: BLOCKED; Issue остаётся открытой.** Проверенное содержимое `dev` — [`b89c57a075be63687c366ff1f54ff82599dc4878`](https://github.com/MikeMoore1337/your-fitness-coach/commit/b89c57a075be63687c366ff1f54ff82599dc4878). Данные для текущих проверок синтетические. Историческая [приёмка фазы A владельцем](https://github.com/MikeMoore1337/your-fitness-coach/issues/888#issuecomment-6892707636) сохраняет указанные в ней ограничения и не распространяется на остальные критерии #888.

| Область | Результат | Доказательство и границы |
| --- | --- | --- |
| Фаза A | BLOCKED для полной текущей приёмки | Текущие тесты CSV/PDF и каталога прошли в указанном ниже объёме. Владелец ранее принял DEV-результат с ограничениями; исходный PDF безопасно отклонён, успешный импорт и полная эквивалентность реальной пары не доказаны. |
| Фаза B | BLOCKED для полной текущей приёмки | Проверены серверные предложения, подтверждение, повтор, конкурентность и изоляция. Браузерные сценарии предложений используют подменённые ответы API; [предыдущий настоящий E2E](https://github.com/MikeMoore1337/your-fitness-coach/issues/886#issuecomment-6893636465) относится к другому SHA. |
| Фаза C | BLOCKED для полной текущей приёмки | PostgreSQL-тесты проверяют даты, null, snapshot, повторы, конфликты, откат и изоляцию; браузерный синтетический CSV прошёл через настоящий API и отдельную БД. Влияние на все заявленные потребители не доказано сквозным сценарием. |
| Совместная интеграция | NOT_RUN | Единой последовательности A → общий каталог для B → шаблон → история → повтор на одном файле не выполнено. Отдельные результаты не заменяют её. |
| API / PostgreSQL | PASS в проверенном объёме | 300 passed, 2 skipped в основном наборе; отдельно 1 passed для разрыва соединения на специальной тестовой базе. Один из двух пропусков таким образом закрыт отдельным прогоном; другой проверяет неподдерживаемую платформу и пропущен на поддерживаемом non-root Linux. |
| Security | BLOCKED для полной приёмки | Тесты охватывают ownership, повторные и конкурентные подтверждения, отзыв сессии, проверку содержимого файлов и приватность черновика. Полный перечень отрицательных сценариев и всех CI-артефактов не проверен; отсутствие утечек повсюду не заявляется. |
| Performance | FAIL для выполненного нагрузочного сценария | После браузерных тестов оставшийся лимит адреса дал 2 успешные операции и 18 HTTP 429. В новом процессе со штатными лимитами — 17 успешных из 20, один `409 preview_changed` и два `401` при review. Причина этих трёх ответов не установлена; подробности ниже. |
| UI | PASS в проверенном объёме | Chromium и WebKit: 36 passed из первого прогона и 6 passed после создания отсутствовавшего синтетического PDF. Реальные CSV/PDF-загрузки используют API и PostgreSQL, но часть остальных ответов подменена. На этих сценариях проверялись 320/360/393/430/1280 px, Light/Dark, фокус и подтверждение; PWA/TMA — тестовая эмуляция. |
| Регрессия | BLOCKED для полной приёмки | 39 тестов миграций, дневника, целей и отчётов; 176 тестов питания, этикеток, планирования, экспорта/удаления аккаунта и демо; 66 frontend unit-тестов. Отдельные заявленные сквозные связи и все устройства не подтверждены. |
| CI / миграции | PASS в проверенном объёме | Пустая PostgreSQL 16 обновлена до `0159_nutrition_meal_notes`; тесты миграций и ограничений прошли. [CI dev](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/43829366354): `branch-checks` success на указанном SHA, однако многие профильные задания пропущены маршрутизатором. Restore production-shaped данных не проверен. |

## Выполненные команды

Backend запускался в Linux-контейнере с Python 3.14, non-root, PostgreSQL 16 в отдельной Docker-сети. `TEST_DATABASE_URL` указывал исключительно на отдельную синтетическую БД; значения тестовых учётных данных здесь опущены. Все команды ниже относятся к указанному SHA.

```text
python -m pytest -q backend/tests/test_nutrition_import_contract.py backend/tests/test_nutrition_import_v2_contract.py backend/tests/test_nutrition_import_validation.py backend/tests/test_nutrition_import_runner.py backend/tests/test_nutrition_import_fatsecret_csv.py backend/tests/test_nutrition_import_fatsecret_pdf.py backend/tests/test_nutrition_import_pdf_text.py backend/tests/test_nutrition_import_pdf_sandbox.py backend/tests/test_nutrition_import_drafts.py backend/tests/test_nutrition_import_api.py backend/tests/test_nutrition_catalog_import.py backend/tests/test_nutrition_import_meals.py backend/tests/test_nutrition_import_history.py --basetemp=/tmp/yfc-qa888-pytest -o cache_dir=/tmp/yfc-qa888-cache
# 300 passed, 2 skipped, 318.92 s

python -m pytest -q backend/tests/test_nutrition_import_drafts.py::test_database_disconnect_rolls_back_then_retry_succeeds --basetemp=/tmp/yfc-qa888-disconnect -o cache_dir=/tmp/yfc-qa888-disconnect-cache
# 1 passed, 6.55 s; отдельная БД с именем *_test

python -m pytest -q backend/tests/test_nutrition_catalog_migration.py backend/tests/test_food_diary.py backend/tests/test_nutrition_reports.py backend/tests/test_nutrition_target_history.py --basetemp=/tmp/yfc-qa888-regression -o cache_dir=/tmp/yfc-qa888-regression-cache
# 39 passed, 59.22 s

python -m pytest -q backend/tests/test_nutrition.py backend/tests/test_nutrition_label.py backend/tests/test_nutrition_plan.py backend/tests/test_nutrition_power.py backend/tests/test_nutrition_suggestions.py backend/tests/test_account_export.py backend/tests/test_account_lifecycle.py backend/tests/test_demo.py --basetemp=/tmp/yfc-qa888-related -o cache_dir=/tmp/yfc-qa888-related-cache
# 176 passed, 184.61 s

alembic upgrade head
# PASS на новой пустой PostgreSQL 16, до 0159_nutrition_meal_notes

npm run build
# PASS; зависимости из существующей установки с совпадающим package-lock.json

npx vitest run tests/unit/features/nutrition/NutritionHistoryImport.test.tsx tests/unit/features/nutrition/NutritionDiary.test.tsx tests/unit/features/nutrition/MealPlanner.test.tsx tests/unit/features/nutrition/NutritionTargetHistory.test.tsx tests/unit/features/workouts/NutritionReport.test.tsx
# 5 файлов, 66 passed

npx playwright test --config=playwright.cross-browser.config.ts nutrition-diary.spec.ts --project=chromium --project=webkit --grep 'Issue 88[567]' --workers=1 --reporter=line
# 36 passed, 6 failed: отсутствовала временная синтетическая PDF fixture
npx playwright test --config=playwright.cross-browser.config.ts nutrition-diary.spec.ts --project=chromium --grep 'Issue 885 real synthetic PDF import' --workers=1 --reporter=line
# после создания fixture существующей synthetic_pdf(): 6 passed
```

Playwright обращался к локальному API с отдельной мигрированной БД. Первый пробный запуск до приведённых команд использовал устаревший frontend, встроенный в образ, и был остановлен; после подключения сборки проверяемого SHA сценарии запущены заново. Эти ошибки подготовки стенда не считаются дефектом продукта. Ошибки отсутствующей fixture сохранены в итогах первого корректного прогона, а не скрыты.

## Нагрузочный сценарий

Существующий `backend/tests/benchmark_nutrition_import.py` выполнен через временный локальный адаптер: изменены только адрес API, имена двух контейнеров и подключение счётчика PostgreSQL. Каждому из контейнеров API и PostgreSQL заданы лимиты 1 CPU и 1 GiB; общие накладные расходы Docker/хоста не ограничены этим бюджетом. База и продукты синтетические; production VPS не использовался. Штатный лимит `30/hour` на адрес и лимиты пользователя/парсеров не изменялись.

- После UI-прогонов: 20 попыток, параллельность 2, 200 строк в каждом файле; 2 завершились, 18 получили HTTP 429. Это не чистое окно измерения.
- После перезапуска тестового API и сброса его in-memory счётчика адреса: 20 попыток за 14,877 с, 17 полных успешных цепочек. Одна остановилась на confirm с `409 preview_changed`, две — на review с `401`; заголовок авторизации в обоих случаях присутствовал. `409` может быть защитой от изменения preview, но причину конкретного изменения и причину двух `401` этот прогон не установил. Требуется отдельная диагностика, а не повтор того же прогона.
- Для 17 успешных цепочек: upload p50 1,315 с, p95/max 1,636 с; review p50 0,044 с, p95/max 0,306 с; confirm p50 0,062 с, p95/max 0,269 с. Это выборка успешных операций, не оценка всех запросов.
- Девять выборок `docker stats`: максимум API 99,58% CPU и 266,8 MiB; PostgreSQL 4,08% CPU и 198,9 MiB. Максимум активных PostgreSQL client backend в этих выборках — 1. Пиковые значения между выборками могли быть пропущены. Тест не доказывает лимиты production и не измеряет непрерывный профиль памяти или отдельную нагрузку cleanup.

## Оставшиеся условия

- Выполнить единый синтетический сценарий A/B/C с проверкой повторного импорта, владельцев и исходных данных на актуальном интегрированном коде.
- Подтвердить недостающие заявленные связи истории с календарём, адаптивными калориями и остальными регрессиями, а также полный перечень security/cleanup и восстановление данных в применимом объёме.
- Установить причины `409` и двух `401` в нагрузочном сценарии и проверить поведение при конкурентной нагрузке; дополнить проверкой ограниченности очистки и измерениями в сопоставимой среде.
- Выполнить обязательные проверки среды и владельческие решения, для которых нет доказательств. Физические iOS/PWA/TMA, production VPS и production не проверялись; реальные файлы в этом прогоне не открывались. Повреждённый PDF не объявляется успешно импортированным, а непроверенные сопоставления CSV не подтверждаются автоматически.

`#880` и `#957` не закрывались. Merge, deploy и изменения production не выполнялись.
