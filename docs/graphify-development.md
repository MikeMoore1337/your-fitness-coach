# Graphify для разработки

Graphify используется только как локальный индекс кода для навигации, архитектурных вопросов и
impact analysis. Он не входит в runtime Your Fitness Coach и не является источником истины.

Поддерживаемая версия: `graphifyy==0.9.63` (актуальный upstream release проверен 18.09.2026).

## Установка

Graphify устанавливается отдельно от окружений backend/bot/frontend:

```bash
uv tool install "graphifyy==0.9.63"
```

Повторная установка той же поддерживаемой версии:

```bash
uv tool install --force "graphifyy==0.9.63"
```

Удаление:

```bash
uv tool uninstall graphifyy
```

Команды одинаковы в POSIX shell и PowerShell. Если `graphify` не найден после установки, выполните
`uv tool update-shell` и откройте новый терминал.

## Канонический запуск YFC

Всегда используйте обёртку репозитория, а не прямой `graphify`:

```bash
python scripts/graphify_yfc.py extract . --code-only --no-cluster
python scripts/graphify_yfc.py query "what code is affected by changing workout programs?"
python scripts/graphify_yfc.py explain "FastAPI"
python scripts/graphify_yfc.py explain "QueryClient"
python scripts/graphify_yfc.py path "FastAPI" "health"
```

Обёртка направляет graph и query log в `.artifacts/shared/graphify/`. Каталог уже исключён из Git.
Не создавайте и не коммитьте `graphify-out/`.

Для первого headless build используйте `extract . --code-only`: YFC содержит Markdown и другие
документы, а обычная mixed-corpus extraction может потребовать LLM/provider. Code-only режим строит
AST-граф локально без API key. Для обновления существующего code graph можно использовать:

```bash
python scripts/graphify_yfc.py update . --no-cluster
```

## Границы использования

- `.gitignore` автоматически учитывается Graphify; отдельный `.graphifyignore` сейчас не нужен.
- Не передавайте `--no-gitignore`: `.artifacts/`, `.env*`, private backlog и generated output должны
  оставаться вне corpus.
- Не запускайте `graphify install --project`, strict mode или Graphify git hooks для YFC.
- Для широких architecture/dependency/relationship/impact вопросов сначала используйте scoped
  `query`, `path`, `explain`, если graph актуален.
- Для известного точного файла/символа Graphify не нужен.
- Перед изменением кода проверяйте реальные source/tests/migrations/docs. При stale, ambiguous или
  incomplete graph переходите к исходникам.
- Не перестраивайте graph в каждой task без причины и не расширяйте scope задачи по результатам graph.
