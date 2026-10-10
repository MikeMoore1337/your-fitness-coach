# Блокер обязательного CI: CodeQL

В [CI 38072118908](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38072118908), HEAD `7c9f9513`, CodeQL сообщил: `Cannot retrieve the full diff because there are too many (300) changed files in the pull request`. Diff-informed analysis не был применён; полный анализ выдал 7 блокирующих сигналов. Предыдущий [CI 38068141113](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38068141113), HEAD `cbc33336`, успешно применял diff-informed analysis и имел зелёный CodeQL.

Исходные файлы всех семи сигналов, workflow и SARIF-gate побайтово одинаковы на обоих HEAD. Git blob IDs и точные правила/строки сохранены в [JSON](ci-blocker.json). Это доказывает, что сигналы относятся к прежнему коду; это не доказывает отсутствие уязвимостей.

Затронуты OAuth-логирование, идентификатор отчёта Allure, два исторических HTML-прототипа и аватар аккаунта. Статус проверки: `NEEDS_MANUAL_VALIDATION`. Exploitability не подтверждена. Исправления таймера не изменяют эти потоки.

Порог, правила CodeQL и SARIF-gate сохранены. Исключения и подавления не добавлены. Уменьшение числа артефактов для обхода полного анализа не выполнялось. До разбора и устранения блокирующих сигналов `checks` не может быть принят как зелёный; состояние не является release-ready. Актуальный результат смотреть в [Checks PR #927](https://github.com/MikeMoore1337/your-fitness-coach/pull/927/checks).
