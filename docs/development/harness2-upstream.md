# Подключение оригинального Harness² к разработке YFC (DEV)

Сценарий использует **исходный** [google-research/harness2](https://github.com/google-research/harness2) через установленный Toolkit [#421](https://github.com/MikeMoore1337/ai-development-toolkit/issues/421). Нет форка, копии исходников, собственного оптимизатора или нового движка оценок. Код YFC и production не зависят от Harness².

## Условия

1. На Windows 11 доступен WSL2 с дистрибутивом **Ubuntu** и Python 3.12.
2. В Ubuntu из локального Toolkit отдельно и с согласия пользователя выполнено `bash integrations/harness2/install.sh install`. Источник закреплён на SHA `1cfe254e8d25b15f37048c3730134686abe60335`.
3. Система работает без Codex/Claude CLI, платных API и доступа к production-секретам. Отдельная установка не активирует модели.

В PowerShell из checkout YFC `dev`:

```powershell
.\scripts\harness2_dev.ps1 -Action Status
# Только при наличии отдельно подготовленного исходного benchmark:
# .\scripts\harness2_dev.ps1 -Action Check -Benchmark lab
# Только если оригинальный upstream уже создал и оценил результат:
# .\scripts\harness2_dev.ps1 -Action Report -Benchmark lab
```

Этот локальный помощник проверяет SHA и источник установленного upstream в WSL2 и вызывает **штатные** `harness2-check` / `harness2-report`. Он не выполняет `harness2`, не запускает оценку моделей и не пишет данные YFC. Это developer opt-in, а не часть `scripts/agent_harness.py`, `pytest`, контейнеров DEV или mandatory CI.

**Ограничение:** текущий upstream работает с JobBench, LAB и WorkBuddy-Bench. Он **не принимает произвольные pytest/Playwright-сценарии YFC из коробки**. Результаты нативных upstream-бенчмарков не являются доказательством качества YFC. Для такого сценария понадобится отдельная поддерживаемая upstream-интеграция, а не переписывание Harness².

Оригинальный Codex executor у Harness² не равен Codex Desktop и отключает собственную песочницу. Владельцу запрещено использовать Codex/Claude CLI и дополнительные платные API; это не меняется.

## Приёмка

- `Status` должен подтвердить исходную установку на реальной Windows/WSL2 машине.
- `Check` и `Report` допустимы только при наличии и подготовке соответствующих оригинальных данных; отсутствие этих данных - ожидаемая ошибка, **не** успешная оценка.
- Если WSL2/установка отсутствует, ошибка явная и не затрагивает основное приложение.
- Никаких изменений данных DEV и production, AGENTS.md, маршрутизации QA или обязательного CI.

Issue [#1288](https://github.com/MikeMoore1337/your-fitness-coach/issues/1288). Все изменения только через `dev`; PR в `master` не открывается.
