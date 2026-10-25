# YFC #1211 - независимая приёмка SkillSpector

Дата 25.10.2026. Исходная реализация - закрытая [Issue #364](https://github.com/MikeMoore1337/your-fitness-coach/issues/364).

## Подтверждённые проверки

- Закреплённая NVIDIA SkillSpector: SHA d162d9b343e559be13df8ebba093df3bc9d58c90; основа релиза 2.11.2.
- [GitHub Actions Windows 2022 + Ubuntu 24.04](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/40202965437): **SUCCESS / SUCCESS**. На обеих ОС реально запущен pin через uvx. JSON --output записан и прочитан.
- Два безвредных синтетических навыка (EN/RU) на каждой ОС: SAFE/LOW, no-LLM, attempted LLM calls 0, полный каталог навыка обработан. Эти проверки **не доказывают** обнаружение сложной русскоязычной prompt injection.
- Первый обязательный слой - существующий scripts/skill_safety.py, offline без LLM. Запуск второго слоя остаётся привязанным к изменению .agents/skills/** через scripts/ci_contract.py и существующий policy CI; backend/frontend-only не приводит к установке SkillSpector.
- tests/test_ci_contract.py покрывает required group + исключения для product changes. tests/test_skillspector_guard.py проверяет SAFE/CAUTION/DO_NOT_INSTALL/HIGH, incomplete, reference_missing / reference_unresolved, malformed JSON, failure, LLM requested, удаление секретов из ENV, RU/EN synthetic verdicts, stale SAFE report, timeout и отсутствие исполняемого файла.
- Никакой автоматической установки проверенных навыков, новых обязательных платных API, Codex CLI, runtime dependency не добавлено.

## Обнаруженный дефект и устранение

До #1211 отчёт записывался на предсказуемый путь без предварительного удаления. Если внешний анализатор вернул успешный код, но не создал новый JSON, можно было прочитать старый SAFE. Исправлено удалением старого результата непосредственно перед вызовом и явным fail-closed при отсутствии нового. Для предотвращения зависаний добавлен предел исполнения 180 секунд.

## Ограничения

Статическая проверка (без LLM) не является доказательством безопасности RU/EN-инструкций. Подозрительные внешние навыки требуют ручной проверки и подтверждения владельца. SC4/OSV.dev может выполнять bounded online lookup координат зависимостей; отсутствие вызова LLM не означает полный запрет сети.

Проверка совместимости выполнена в эфемерных Windows/Linux GitHub runners, не на реальном ПК владельца. Пути этого PR - только scripts, tests, docs и GitHub Actions. scripts/deployment_scope.py относит эти developer-tooling изменения к no-deploy, что необходимо подтвердить фактической post-merge проверкой Release production.

**Условие закрытия:** exact-head CI, обе платформы, merge master, post-merge CI и проверенный no-deploy. Любой skipped шаг учитывается как NOT_RUN, а не PASS.
