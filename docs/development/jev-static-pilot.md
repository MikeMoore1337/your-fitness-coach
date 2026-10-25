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

Пока фактический workflow не завершён и отчёт не проверен: `NOT_MEASURED` / `NOT_ADOPTED`. Даже если static discovery убедителен, обязательные GitHub CI и release regressions продолжают запускать прежние тесты. Для включения локальной команды необходим отдельный независимый регрессионный A/B по известным падающим тестам и подтверждённое отсутствие false negatives. Удаление этого workflow, скрипта, тестов и документации полностью возвращает прежнее состояние.
