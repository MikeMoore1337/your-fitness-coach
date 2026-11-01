# Оригинальный Harness² для разработки YFC (необязательная интеграция DEV)

YFC использует **только официальный** [google-research/harness2](https://github.com/google-research/harness2) через существующий [AI Development Toolkit #421](https://github.com/MikeMoore1337/ai-development-toolkit/issues/421). Никаких форков, встроенного evaluator, новых зависимостей Python/Docker в YFC или изменений production. Это инструмент разработчика, не пользовательская функция.

## Границы и совместимость

- Оригинальный Harness²: `0.1.0`, закреплённый Git SHA `1cfe254e8d25b15f37048c3730134686abe60335`, официальные CLI `harness2-setup`, `harness2-check`, `harness2`, `harness2-report`.
- Только отдельная Ubuntu WSL2 в Windows 11 и изолированный Python 3.12 в каталоге Toolkit внутри Linux HOME. Python 3.14, окружения и данные YFC не изменяются.
- Для Windows PowerShell 5.1/7 маршрутизация выполняется через `integrations/harness2/acceptance.ps1` Toolkit **не старее** `397b5e9241e1266e82c81f5924c8a72b0c47eacf`. Он обнаруживает `Ubuntu-24.04`, `Ubuntu`, `Ubuntu-22.04` или другие `Ubuntu-XX.YY`, отказывает для `docker-desktop` и передаёт Bash **путём к отдельному LF-файлу**, а не многострочным аргументом `bash -c`.
- Скрипт YFC разрешает лишь `Preflight`, `Status`, `SetupPreview`, `Check`, `RunPreview`, `Report`, `Artifacts`. Он проверяет происхождение локального Toolkit, минимальную ревизию, чистоту интеграционных файлов, неизменённость пина и отсутствие символьных ссылок в целевых путях. Установку, скачивание benchmark и выполнение моделей он **не** запускает.
- Настоящие upstream benchmark: JobBench (`jb`), LAB (`lab`), WorkBuddy-Bench (`wb`). Harness² не умеет оценивать произвольные pytest/Playwright-сценарии YFC без отдельного согласованного адаптера.

## Приёмка в Windows PowerShell (без скачиваний)

Toolkit должен быть **уже установлен** как отдельный проверенный Git checkout. По умолчанию YFC ищет его в соседнем каталоге: `D:\Pet-projects\ai-development-toolkit` при работе из `D:\Pet-projects\yfc-dev`. Для иного расположения добавьте `-ToolkitRoot 'D:\путь с пробелами\ai-development-toolkit'` к каждой команде.

```powershell
Set-Location 'D:\Pet-projects\yfc-dev'
.\scripts\harness2_dev.ps1 -Action Preflight
.\scripts\harness2_dev.ps1 -Action Status
```

`Preflight` проверяет WSL2, Linux Git, Python 3.12 и доступность npm/uv; не устанавливает зависимости. Если исходный Harness² пока отсутствует, `Status` должен **отказать**, а не выдавать фиктивный PASS. При наличии установки и разрешённых данных:

```powershell
.\scripts\harness2_dev.ps1 -Action SetupPreview -Benchmark lab
.\scripts\harness2_dev.ps1 -Action Check -Benchmark lab
.\scripts\harness2_dev.ps1 -Action RunPreview -Benchmark lab
.\scripts\harness2_dev.ps1 -Action Report -Benchmark lab
.\scripts\harness2_dev.ps1 -Action Artifacts
```

`SetupPreview` и `RunPreview` вызывают штатные `--dry-run`, не модельный прогон. `Check` лишь проверяет внешние зависимости/учётные данные, а `Report` имеет смысл **только после наличия настоящих оценённых результатов**. Отказ при неподготовленном benchmark ожидаем. `Artifacts` перечисляет имена отчётов из официального `HARNESS2_RUNS_DIR`, не раскрывая сырые логи и секреты.

Для выбора установленного дистрибутива разрешён `-Distribution Ubuntu-24.04`. Ubuntu **не** устанавливается автоматически, WSL default и сетевые настройки не меняются. При ошибке `HARNESS2_TOOLKIT_CHECKOUT_MISSING` укажите `-ToolkitRoot`. При ошибке `HARNESS2_TOOLKIT_REVISION_TOO_OLD_OR_SHALLOW` обновите проверенный checkout Toolkit до версии, содержащей #479. Если Python 3.12 или Ubuntu не установлены, сначала зафиксируйте блокер; установка оригинала из Toolkit требует **отдельного разрешения** на сетевые скачивания и проверки сторонних лицензий.

## Безопасность и доказательства

Штатная установка Toolkit сверяет исходный SHA, Git origin, маркер, версию пакета, чистоту tracked upstream и наличие настоящих CLI. Символические ссылки на опасные директории/исполняемые файлы блокируются проверками Toolkit. В YFC не допускаются `Install`, `Setup`, `Remove`, модельные действия, `harness2-demo`, судья, Codex CLI/Claude CLI и платные API. Обычные DEV/CI/release работают и при полностью отсутствующем Harness².

Отдельный Windows CI выполняет **только имитацию** вызовов PowerShell 5.1/7 с подменой Toolkit без WSL, интернета и моделей. Он не подтверждает установку на компьютере владельца. Полная эксплуатационная приёмка требует фактических выводов `Preflight`/`Status` на Windows/Ubuntu WSL2 и доступных штатных CLI без платных вызовов. `MODEL_RUN=BLOCKED_BY_OWNER_POLICY`, `MODEL_EFFICACY=NOT_MEASURED`.

[Issue YFC #1288](https://github.com/MikeMoore1337/your-fitness-coach/issues/1288). Изменения интеграции проводятся только через PR в `dev`.
