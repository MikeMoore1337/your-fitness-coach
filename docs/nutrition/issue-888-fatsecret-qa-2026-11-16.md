# QA импорта FatSecret — #888, 16 ноября 2026

**Итог: BLOCKED; Issue остаётся открытой.** Проверенное содержимое `dev` — [`b89c57a075be63687c366ff1f54ff82599dc4878`](https://github.com/MikeMoore1337/your-fitness-coach/commit/b89c57a075be63687c366ff1f54ff82599dc4878). Данные для текущих проверок синтетические. Историческая [приёмка фазы A владельцем](https://github.com/MikeMoore1337/your-fitness-coach/issues/888#issuecomment-6892707636) сохраняет указанные в ней ограничения и не распространяется на остальные критерии #888.

| Область | Результат | Доказательство и границы |
| --- | --- | --- |
| Фаза A | PASS в принятом владельцем объёме | Текущие тесты CSV/PDF и каталога прошли. Исходный PDF ранее безопасно отклонён; успешный импорт и полная эквивалентность реальной пары не доказаны. |
| Фаза B | PASS в проверенном объёме | Предложения, редактирование порции, явное согласие, сохранение, повтор и изоляция прошли с настоящими интерфейсом, API и PostgreSQL. Конкурентность проверялась отдельно серверными тестами. |
| Фаза C | PASS в проверенном объёме | Реальный API и PostgreSQL: выбранная дата, исходные КБЖУ, статус, дневник другого пользователя, отчёт и повтор; дополнительно проверены null, snapshot, конфликты и откат. Адаптивный расчёт не учитывает импортированный день до явной отметки complete. |
| Совместная интеграция | PASS в проверенном объёме | Один синтетический CSV: каталог для A/B → изменённый шаблон A → отдельный перенос дня → повторная загрузка и подтверждение без дублирования продукта, шаблона или записи. Исходные строки и данные B сохранены. |
| API / PostgreSQL | PASS в проверенном объёме | 300 passed, 2 skipped в основном наборе; отдельно 1 passed для разрыва соединения на специальной тестовой базе. Один из двух пропусков таким образом закрыт отдельным прогоном; другой проверяет неподдерживаемую платформу и пропущен на поддерживаемом non-root Linux. |
| Security | BLOCKED для полной приёмки | Автотесты охватывают ownership, конкуренцию, rollback, отзыв сессии, формулы, повреждённые/зашифрованные PDF и ограничения. В журнале синтетического API не найдено тестовое имя, имя файла или JWT-подобные строки. Все CI-артефакты и реальные данные этого прогона не проверены. |
| Performance | PASS в проверенной локальной конфигурации | Контролируемый прогон — 20/20 успешных цепочек с двумя параллельными клиентами и 200 строками; предыдущие 429/409/401 и ограничения воспроизведения сохранены ниже. Production VPS не проверялся. |
| UI | PASS в проверенном объёме | Chromium и WebKit: 36 passed из первого прогона и 6 passed после создания отсутствовавшего синтетического PDF. Реальные CSV/PDF-загрузки используют API и PostgreSQL, но часть остальных ответов подменена. На этих сценариях проверялись 320/360/393/430/1280 px, Light/Dark, фокус и подтверждение; PWA/TMA — тестовая эмуляция. |
| Регрессия | PASS в проверенном автоматизированном объёме | 39 тестов миграций, дневника, целей и отчётов; 176 тестов питания, этикеток, планирования, экспорта/удаления аккаунта и демо; 66 frontend unit-тестов. Дополнительно проверены календарный переход, отчёт и вход адаптивного расчёта. |
| CI / миграции | PASS в проверенном объёме | PostgreSQL 16 обновлена до `0159_nutrition_meal_notes`; синтетические данные восстановлены в отдельную БД, пять таблиц совпали по количеству и контрольной сумме. [CI dev](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/43829366354): `branch-checks` success, многие профильные задания пропущены маршрутизатором. Production restore не проверялся. |

## Выполненные команды

Backend запускался в Linux-контейнере с Python 3.14, non-root, PostgreSQL 16 в отдельной Docker-сети. `TEST_DATABASE_URL` указывал исключительно на отдельную синтетическую БД; значения тестовых учётных данных здесь опущены. Код приложения во всех прогонах соответствует указанному SHA `dev`; два новых серверных теста и новый E2E находятся в PR с этим отчётом.

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

python -m pytest -q backend/tests/test_nutrition_import_history.py backend/tests/test_nutrition_import_drafts.py backend/tests/test_nutrition_import_api.py --basetemp=/tmp/yfc-qa888-final -o cache_dir=/tmp/yfc-qa888-final-cache -rs
# после добавления проверок адаптивных входов и bounded cleanup: 42 passed, 46.61 s
```

Playwright обращался к локальному API с отдельной мигрированной БД. Первый пробный запуск до приведённых команд использовал устаревший frontend, встроенный в образ, и был остановлен; после подключения сборки проверяемого SHA сценарии запущены заново. Эти ошибки подготовки стенда не считаются дефектом продукта. Ошибки отсутствующей fixture сохранены в итогах первого корректного прогона, а не скрыты.

## Нагрузочный сценарий

Существующий `backend/tests/benchmark_nutrition_import.py` выполнен через временный локальный адаптер: изменены только адрес API, имена двух контейнеров и подключение счётчика PostgreSQL. Каждому из контейнеров API и PostgreSQL заданы лимиты 1 CPU и 1 GiB; общие накладные расходы Docker/хоста не ограничены этим бюджетом. База и продукты синтетические; production VPS не использовался. Штатный лимит `30/hour` на адрес и лимиты пользователя/парсеров не изменялись.

- После UI-прогонов: 20 попыток, параллельность 2, 200 строк в каждом файле; 2 завершились, 18 получили HTTP 429. Это не чистое окно измерения.
- После перезапуска тестового API и сброса его in-memory счётчика адреса: 20 попыток за 14,877 с, 17 полных успешных цепочек. Одна остановилась на confirm с `409 preview_changed`, две — на review с `401`; заголовок авторизации в обоих случаях присутствовал. `409` может быть защитой от изменения preview, но причину конкретного изменения и причину двух `401` этот прогон не установил. Требуется отдельная диагностика, а не повтор того же прогона.
- Для 17 успешных цепочек: upload p50 1,315 с, p95/max 1,636 с; review p50 0,044 с, p95/max 0,306 с; confirm p50 0,062 с, p95/max 0,269 с. Это выборка успешных операций, не оценка всех запросов.
- Девять выборок `docker stats`: максимум API 99,58% CPU и 266,8 MiB; PostgreSQL 4,08% CPU и 198,9 MiB. Максимум активных PostgreSQL client backend в этих выборках — 1. Пиковые значения между выборками могли быть пропущены. Тест не доказывает лимиты production и не измеряет непрерывный профиль памяти или отдельную нагрузку cleanup.

### Продолжение диагностики

- **409:** на том же API два пользователя загрузили одинаковый синтетический файл и получили отдельные preview. После подтверждения первого во втором появилось новое fuzzy-предложение; подпись preview изменилась, а подтверждение старой подписи вернуло `409 preview_changed`. Повторная проверка обязательна: конфликт защищает от подтверждения изменившихся данных. Конкретное содержимое preview первоначального 409 не сохранилось, поэтому это воспроизведённый механизм, согласующийся с наблюдением, а не доказанная причина именно первого ответа.
- **401:** в отдельном диагностическом прогоне повторились два 401 на review; локальная диагностика без записи токенов показала `ImmatureSignatureError` сразу после обратного скачка часов контейнера на 2,242 секунды относительно monotonic clock. До запуска наблюдался ещё один скачок на 2,179 секунды. Первоначальные 401 не содержали класса ошибки, поэтому причинная связь с теми конкретными ответами остаётся вероятной, но не доказанной. Проверка JWT и системные часы не изменялись.
- **Контрольный замер:** после перезапуска только тестового API с неизменёнными лимитами подготовлены 20 синтетических сессий; перед нагрузкой проверено, что время сервера опередило выдачу токенов на пять секунд. Продуктам заданы разные имена, чтобы исключить намеренно проверенный выше конфликт общего каталога. При параллельности 2 и 200 строках: **20/20**, 14,393 с; upload p50 1,321 / p95 1,416 / max 1,422 с, review 0,040 / 0,071 / 0,275 с, confirm 0,056 / 0,067 / 0,070 с. В восьми выборках максимум API 102,07% CPU и 269,9 MiB, PostgreSQL 5,44% CPU и 97,7 MiB; активных клиентских backend — максимум 1. Сэмплирование не гарантирует обнаружение пиков, Docker/хост имеют дополнительные расходы. Это локальная синтетическая среда, не production VPS.

### Дополнительные проверки

- `npx playwright test --config=playwright.cross-browser.config.ts nutrition-import-integrated.spec.ts --project=chromium --workers=1 --reporter=line` — **1 passed, 19,3 с**, с `PW_REAL_IMPORT_BASE` и `PW_BASE_URL`, указывающими на локальный API. Без подмены ответов YFC проверены весь A/B/C, пользователь B, повтор, уникальность каталога, шаблона и дневника, исходные строки, отчёт и выбранный день календаря. Тест допускает только локальный dev API. Он ожидает продвижения часов стенда после выдачи тестовых токенов; это не меняет серверную авторизацию.
- Новые PostgreSQL-тесты проверяют ограниченную очистку четырёх истёкших черновиков партиями по два, сохранность неистёкшего черновика и дневника, а также вход адаптивного расчёта до и после явного завершения импортированного дня.
- `npm run typecheck`, `npm run lint`, целевые ESLint/Prettier и Ruff — PASS. Предыдущие ошибки типов и форматирования в новом тесте исправлены до итогового прогона.
- `pg_dump -Fc --no-owner --no-privileges qa888ui`, затем `pg_restore --exit-on-error --no-owner --no-privileges` в пустую отдельную БД — PASS. Для `alembic_version`, `foods`, `food_diary_entries`, `nutrition_import_drafts`, `nutrition_meal_templates` совпали count и hash полных строк: 1, 42, 3, 54 и 4 соответственно. Проверялись только синтетические данные и перечисленные таблицы.
- В журналах тестового API совпадений по синтетическому имени продукта, имени CSV и JWT-подобному шаблону — 0. Это не полный аудит других журналов, CI-артефактов и личных файлов.

## Оставшиеся условия

- Для фаз B/C не подтверждены реальные iOS/PWA/TMA и screen reader. Предыдущее решение по ограничениям фазы A не переносится на них автоматически; нужны доступная среда и проверка либо отдельное решение владельца по этим условиям.
- Не подтверждены все CI-артефакты и журналы на отсутствие персональных данных; проверенные границы перечислены выше и в ранее принятой фазе A. Production VPS и production restore не проверялись; замер и восстановление синтетические.
- Реальные файлы в этом продолжении не открывались. Повреждённый PDF не объявляется успешно импортированным, а непроверенные сопоставления CSV не подтверждаются автоматически. Исключения за пределами ранее принятой фазы A не предполагаются.

`#880` и `#957` не закрывались. Merge, deploy и изменения production не выполнялись.
