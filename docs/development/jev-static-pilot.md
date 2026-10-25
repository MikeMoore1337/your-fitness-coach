# Jev Test Impact - изолированный static-only пилот (YFC #1212)

Источник: [holasoymalva/jev-test-impact](https://github.com/holasoymalva/jev-test-impact), pinned `f3bdc84c1e5f2b1852b042506cd857899baf2078`, версия исходника 0.1.3, MIT (2026 contributors), Node.js >=22, PNPM 11.5.0. Код исполняется только в временном GitHub-hosted runner; в приложении и локальном окружении не установлен.

## Цель и риск

YFC - монорепозиторий с `frontend/package.json`, Vitest и отдельным Python/БД контуром. Upstream `GitDiffProvider` получает пути `frontend/...` от Git корня, в то время как `discoverTests(root=frontend)` использует пути относительно frontend. Это потенциальное несовпадение может приводить к false negatives. До реальных проверок нельзя утверждать ни экономию времени, ни полноту регрессии.

## Эксперимент

Необязательный workflow `.github/workflows/jev-static-pilot.yml` запускает pinned оригинальный TypeScript CLI с `select --static --json`, без TypeSafe ключа/API, на четырёх временных изменениях изолированного checkout:
- `frontend/src/shared/queryKeys.ts` (общий модуль);
- `frontend/src/features/workouts/TodayWorkout.tsx` (функция тренировки);
- `frontend/tsconfig.json` (должна приводить к полному набору);
- `frontend/package-lock.json` (должна приводить к полному набору).

Код приложения не коммитится и не публикуется с синтетическими изменениями. `scripts/jev_static_pilot_report.py` различает `NO_GO` и `STATIC_DISCOVERY_PLAUSIBLE_NOT_ADOPTED`, сохраняет факт числа найденных/выбранных файлов, latency самого selector, но **не** выдаёт это за ускорение полного выполнения тестов. Пропуск тестов, отсутствие full-suite fallback, отсутствие test discovery и любой model API делают пилот неприемлемым.

Workflow имеет только `contents: read`, не запускает production deploy, не меняет обязательные CI jobs, не требует токенов модели. Итог `NO_GO` - допустимый результат исследования, но не основание делать обязательный CI красным.

## Решение

Фактически выполнен pinned upstream в изолированном runner: [run #40208579692](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/40208579692), artifact `jev-static-only-research`, ID `12604932420`. Исходный CLI выводил двухстрочный информационный префикс PNPM перед JSON. Первоначальный парсер не учёл его и ошибочно записал пустые метрики; исправленный парсер теперь различает формат вывода и реальный отрицательный результат.

Точные факты после независимого разбора исходных артефактов:

| Изменение | discovered | candidates | selected | fullSuite | selectionMs |
| --- | ---: | ---: | ---: | --- | ---: |
| `frontend/src/shared/queryKeys.ts` | 238 | 0 | 0 | false | 1426.93 |
| `frontend/src/features/workouts/TodayWorkout.tsx` | 238 | 0 | 0 | false | 193.33 |
| `frontend/tsconfig.json` | 238 | 238 | 238 | true | 90.82 |
| `frontend/package-lock.json` | 238 | 238 | 238 | true | 79.21 |

В обоих полных выборах присутствовали **78 Playwright E2E specs**. `jevRequests=0` во всех четырёх сценариях. Это подтверждённый **NO_GO для прямого применения upstream как селектора Vitest в YFC**: критичные исходники могут выбирать 0 тестов, а полная выборка включает тесты чужого framework. Данные являются **искусственными временными диффами на реальном дереве YFC**, не измерением регрессионной полноты/ускорения в продакшене. Фактический full-vs-selected runtime и способность ловить известные мутации остаются `NOT_MEASURED`.

**Выпуск разрешён исключительно для исследовательского source-only workflow и достоверного отчёта.** Отсутствует разрешение превращать исходный JTI в обязательный runner или заменять им CI. Удаление этого workflow, скрипта, тестов и документации полностью возвращает прежнее состояние.
