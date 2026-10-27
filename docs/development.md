# Development workflow

Обычная работа YFC следует стандартному GitHub Flow:

```text
GitHub Issue -> короткая Git branch -> Pull Request -> GitHub Checks -> merge в master
```

GitHub Issue — canonical task contract. Для большой спецификации Issue может ссылаться на
tracked Markdown-файл. Обязательное локальное зеркало Issue не создаётся.

GitHub is the operational source of truth for task, integration and verification state.

## Локальная работа

```bash
git fetch --prune origin
git switch -c feature/short-description origin/master
# implementation and targeted checks
git status
git diff --check
git push -u origin feature/short-description
gh pr create --base master
```

Codex worktree допустим как удобство. Он не является task identity, release state или merge
correctness. Clean merged worktree можно удалить best effort; dirty worktree и worktree с unique
commits не удаляются автоматически.

## Pull Request

PR target — protected `master`. Required deterministic Checks являются merge gate. Проверки
относятся к текущему PR head; при изменении head GitHub запускает их снова. Нет отдельной
локальной lease, queue, owner, fingerprint или recovery database.

Минимальный локальный набор выбирается по риску:

```bash
python scripts/local_checks.py
python scripts/run_pytest.py <target> -q
npm --prefix frontend run check
python -m pre_commit run --all-files
```

Полная матрица и aggregate result `checks` определены в [CI workflow](../.github/workflows/ci.yml).
CodeQL, runtime dependency audit и Trivy остаются deterministic PR checks.

## Recovery interrupted session

Продолжение определяется только текущим состоянием GitHub/Git:

```bash
git status
git branch --show-current
git log --oneline --decorate -20
git worktree list
gh pr status
gh pr view <number>
gh run list --branch <branch>
```

Существующая branch означает «продолжить branch». Открытый PR означает «продолжить PR».
Merged PR означает, что integration состоялся. Успешная Actions deployment означает, что
release состоялся. Stale clean worktree не блокирует pipeline; dirty/unique worktree сохраняется.

## Что не является обязательным

`scripts/agent_flow.py`, `scripts/agent_harness.py`, Graphify и Ponytail — optional developer
assistance. Их failure не блокирует Issue, branch, PR, merge или deploy. `.artifacts/` хранит
только derived evidence и temporary data; cleanup — warning, а не completion gate.

Следующая product task не запускается автоматически.
