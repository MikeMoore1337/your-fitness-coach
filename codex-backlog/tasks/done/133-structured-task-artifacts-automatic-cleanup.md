# Task 133 — Структурированные task artifacts и автоматическая безопасная очистка

- **Статус:** completed / implementation `b25d459a07d1e583e40e2aaaf151649cc5d7de73` / 2026-09-03
- **Тип:** implementation / repository hygiene / task lifecycle
- **Основная роль:** `implementer`
- **Дополнительные роли lifecycle:** `independent-reviewer`, `qa-verifier`
- **Рекомендуемые skills:** `$platform-engineer`, `$python-engineer`, `$security-engineer`,
  `$technical-writer`
- **Условные skills:** нет
- **Зависимости:** 127, 127A, 131, 132

<!-- task-session
dependencies: 127, 127A, 131, 132
executable: true
concurrency: exclusive-write
owner_gate: destructive-action
integration: task-pr-to-dev
-->

## Контекст

Локальный `.artifacts/` используется как единый ignored-каталог для task worktrees, caches,
temporary files, test databases, logs, screenshots, reports, deliverables, backups, deployment и
recovery evidence. Сейчас в нём смешаны данные разных сроков жизни и завершённых tasks, а единая
автоматическая очистка после terminal task closeout отсутствует.

Снимок до начала Task 133 показал основные источники расхода диска: `.artifacts/cache/` около
`3.1 GiB`, `.artifacts/tmp/` около `1.7 GiB`, `.artifacts/worktrees/` около `1.6 GiB`, а также
исторические task-specific screenshots, audits, reports и deliverables. Этот снимок является только
ориентиром: перед реализацией обязательно повторить read-only inventory и проверить актуальные
controller leases, registered Git worktrees и процессы текущей task.

Task 132 имеет hard dependency precedence, потому что уже изменяет `scripts/task_session.py` и
release closeout. Task 133 не стартует параллельно и реализуется только поверх завершённой Task 132.

## Цель

Сделать `.artifacts/` управляемым рабочим пространством:

1. новые артефакты создаются только в документированной структуре и получают понятный срок жизни;
2. временные task-owned данные автоматически удаляются после успешного terminal closeout;
3. нужные evidence и deliverables сохраняются в предсказуемых task-specific путях;
4. worktrees, backups, deployment/recovery evidence и данные активных tasks защищены от общей
   очистки;
5. текущий накопившийся мусор инвентаризируется и безопасно удаляется после отдельного точного
   dry-run;
6. правило закрепляется в tracked документации и обязательных инструкциях для дальнейшей работы.

## Каноническая структура

Task должна утвердить и реализовать следующий минимальный контракт либо эквивалентную структуру,
если инспекция существующих producers докажет более безопасный вариант:

```text
.artifacts/
  worktrees/                 # только controller-managed Git worktrees
  tasks/
    <TASK_ID>/
      temporary/             # удаляется после terminal closeout
      evidence/              # отобранные проверки, screenshots, traces, reports
      deliverables/          # файлы, явно предназначенные владельцу
      logs/                  # task-local диагностические логи с ограниченным retention
      manifest.json          # classification, provenance и retention
  runtime/
    cache/                   # воспроизводимые caches, не source of truth
    tmp/                     # process-local temporary data
    tests/                   # test databases, coverage и generated test output
  shared/                    # только явно классифицированные reusable local assets
  operations/
    backups/                 # защищённые operational backups
    deployments/             # deployment evidence
    recovery/                # recovery/controller evidence
```

Если совместимость требует временно оставить существующие top-level `cache/`, `tmp/`, `tests/`,
`backups/`, `deployments/` или `recovery/`, task обязана зафиксировать migration path и не создавать
две постоянные конкурирующие структуры.

## Классы и retention

### `temporary`

- Воспроизводимые caches, test databases, downloaded CI bundles, preview output, temporary renders,
  raw logs и промежуточные файлы.
- Удаляются автоматически только после terminal success соответствующей task.
- Shared cache очищается только при отсутствии другого активного lease/process consumer либо по
  отдельной безопасной TTL/size policy.

### `evidence`

- Только отобранные результаты, реально нужные для owner/human gate, review, QA, release proof или
  последующего расследования.
- Хранятся под точным Task ID, а не в общей плоской папке.
- Task manifest фиксирует назначение, создателя/command context, created time и retention/disposition.
- Raw evidence без durable значения не должна бессрочно сохраняться по умолчанию.

### `deliverables`

- Только явно предназначенные владельцу материалы: согласованные изображения, документы, bundles
  или экспортируемые результаты.
- Не удаляются общей автоматической очисткой. Удаление требует отдельного exact target decision.

### `protected operations`

- Registered/active worktrees, controller state, recovery anchors, backups, deployment evidence и
  иные данные, потеря которых может усложнить rollback или расследование.
- Никогда не удаляются generic cleanup. Для каждого типа используется его собственный lifecycle и
  safety proof.

## Scope реализации

1. Провести inventory всех tracked producers и consumers `.artifacts/` в `scripts/`, test configs,
   Playwright, backend/frontend tests, controller и documentation.
2. Добавить один repository-native Python manager для:
   - read-only `audit`/`dry-run`;
   - task-scoped path allocation и manifest validation;
   - cleanup конкретной завершённой task;
   - bounded stale runtime cleanup;
   - machine-readable и компактного human-readable результата.
3. Не добавлять новую dependency, если достаточно standard library и текущего project tooling.
4. Интегрировать cleanup в canonical closeout после Task 132:
   - `task_session.py finish` очищает только exact task-owned temporary data и сохраняет результат в
     controller history;
   - `run_task_delivery.py` после закрытия worker log и успешного `_verify_closeout` очищает свои
     delivery temporary artifacts, сохраняя только необходимый итог;
   - failure cleanup не маскируется: closeout останавливается fail-closed с точным списком
     сохранённых путей и причиной.
5. Перевести ключевые artifact producers на канонические task-scoped paths. Не выполнять слепой
   массовый rename; сначала проверить durable references и consumers.
6. Добавить validation, запрещающую новые ad-hoc top-level artifact directories без явно
   зарегистрированного класса.
7. Зафиксировать рабочее правило:
   - обновить root `AGENTS.md`;
   - обновить `codex-backlog/TASK_EXECUTION_LIFECYCLE.md` и при необходимости `GLOBAL_RULES.md`;
   - создать или обновить русскоязычную long-term документацию под `docs/` с layout, retention,
     командами audit/cleanup, troubleshooting и recovery;
   - final-report contract должен показывать, что удалено, что сохранено, сколько места освобождено
     и были ли cleanup errors.
8. Выполнить одноразовую очистку текущего `.artifacts/` по правилам раздела ниже.

## Одноразовая очистка текущего состояния

Перед удалением сформировать exact dry-run inventory с абсолютным подтверждённым root,
относительными target paths, category, причиной, размером и disposition:

- `DELETE` — однозначно воспроизводимые и неиспользуемые temporary данные;
- `MOVE` — нужные task evidence/deliverables, переносимые в каноническую структуру;
- `KEEP` — активные, защищённые или явно нужные данные;
- `REVIEW` — неоднозначные данные, которые нельзя удалять автоматически.

Первое массовое удаление является `DESTRUCTIVE_ACTION`: после dry-run требуется owner checkpoint с
точным `DELETE/MOVE` plan. Общая фраза о необходимости очистки не разрешает расширять targets после
этого checkpoint. После подтверждения применить только неизменившийся plan; при drift повторить
dry-run.

Cleanup обязана:

- не выполняться при активном несовместимом lease или незавершённой Task 132;
- сверять `git worktree list --porcelain` и controller state;
- не удалять registered worktree обычным filesystem delete;
- сохранять dirty worktree, interrupted Git operation, unique commits и recovery anchors;
- не обходить path containment через symlink/junction/reparse point;
- не следовать за target вне exact resolved `.artifacts/` root;
- не использовать broad glob как финальный deletion target;
- не удалять unclassified `REVIEW` data;
- выдавать итоговые counts/bytes и список отказов без secrets, tokens, PII и полного содержимого
  чувствительных логов.

## Не входит

- очистка production host или production backups;
- удаление Git branches/worktrees в обход `task_session.py`;
- удаление owner deliverables без отдельного exact target decision;
- публикация `.artifacts/` или добавление их в Git;
- перенос `.artifacts/` в внешнее object storage;
- изменение application business logic;
- автоматическое удаление данных только по возрасту без classification и safety checks.

## Обязательные проверки

- Unit tests: path containment, normalization, symlink/junction/reparse protection, task ID matching,
  classification, manifest validation, dry-run/apply parity и idempotence.
- Controller tests: active lease, parallel compatible lease, unfinished/failed task, terminal success,
  cleanup partial failure и history/result recording.
- Worktree tests: registered, dirty, unique commits, detached recovery worktree и orphan directory.
- Windows tests: locked file, long path и narrow `safe.directory` handling без global config.
- Delivery tests: open worker log не удаляется; cleanup запускается только после terminal closeout.
- Documentation/link/manifest checks и `git diff --check`.
- До/после disk inventory с одинаковой методикой подсчёта.

## Acceptance criteria

- Есть одна каноническая документированная структура `.artifacts/` и один источник правил retention.
- Root `AGENTS.md` и task lifecycle требуют использовать эту структуру в каждой новой работе.
- Repository-native manager поддерживает безопасные `audit`, `dry-run`, task cleanup и validation.
- Terminal task closeout автоматически удаляет exact task-owned temporary artifacts и записывает
  результат в history/final report.
- Evidence и deliverables сохраняются по Task ID; generic cleanup их не удаляет.
- Active/dirty/unique/recovery worktrees, backups и deployment evidence защищены тестами.
- Новые ad-hoc top-level artifact paths обнаруживаются validation.
- Текущий мусор удалён только по owner-approved unchanged plan; нужные файлы перенесены и имеют
  manifest/classification.
- Итог содержит before/after bytes, освобождённое место, `DELETE/MOVE/KEEP/REVIEW` summary и точные
  unresolved cleanup failures.
- Нет изменений production data, secrets, external infrastructure или application behavior.

## Release eligibility

Task не является `AUTO_RELEASE_ELIGIBLE` до прохождения `DESTRUCTIVE_ACTION` checkpoint для
одноразовой очистки. После exact owner decision, безопасной очистки, review/QA и terminal green
checks дальнейший обычный PR/release closeout следует каноническому lifecycle без дополнительных
generic approvals.
