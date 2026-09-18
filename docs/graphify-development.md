# Graphify для разработки

Graphify используется только как локальный индекс кода для навигации, архитектурных вопросов и
impact analysis. Он не входит в runtime Your Fitness Coach и не является источником истины.

Поддерживаемая версия: `graphifyy==0.9.63`.

## Обычный запуск

В нормальной работе Graphify вручную устанавливать и отдельно строить не нужно. Канонический
bootstrap:

```bash
python scripts/graphify_yfc.py bootstrap
```

Он идемпотентно:

1. ищет `graphify` в `PATH` и в каталоге `uv tool dir --bin`;
2. проверяет точную поддерживаемую версию;
3. при отсутствии Graphify устанавливает `graphifyy==0.9.63` через `uv tool install`;
4. при другой версии переустанавливает pinned-версию;
5. при отсутствии graph строит code-only AST graph;
6. при существующем graph запускает инкрементальный `graphify update`.

Первичная установка требует доступ к сети/PyPI. Построение и обновление code-only graph не требуют
LLM, API key или внешнего AI provider.

В Codex bootstrap запускается один раз перед нетривиальным широким
architecture/dependency/relationship/impact analysis. Для точечной правки в уже известном файле
Graphify не нужен.

Если bootstrap недоступен из-за отсутствующего `uv`, сети или другой локальной проблемы, это само
по себе не блокирует обычную задачу: нужно перейти к прямому чтению актуальных source/tests/migrations/docs.

## Канонический output

Обёртка всегда направляет graph и query log в:

```
.artifacts/shared/graphify/
```

Каталог исключён из Git. `graphify-out/` создавать или коммитить нельзя.

## Ручная установка и восстановление

Обычно этот раздел не нужен, потому что bootstrap выполняет установку сам.

```bash
uv tool install "graphifyy==0.9.63"
uv tool install --force "graphifyy==0.9.63"
uv tool uninstall graphifyy
```

Если `graphify` после ручной установки не находится в `PATH`, обёртка всё равно пытается найти его
через `uv tool dir --bin`.

## Запросы

После bootstrap используются обычные scoped-команды:

```bash
python scripts/graphify_yfc.py query "what code is affected by changing workout programs?"
python scripts/graphify_yfc.py explain "FastAPI"
python scripts/graphify_yfc.py explain "QueryClient"
python scripts/graphify_yfc.py path "FastAPI" "health"
```

Для ручного обновления существующего graph доступна команда:

```bash
python scripts/graphify_yfc.py update . --no-cluster
```

## Границы использования

- `.gitignore` автоматически учитывается Graphify; отдельный `.graphifyignore` сейчас не нужен.
- Не передавайте `--no-gitignore`: `.artifacts/`, `.env*`, private backlog и generated output должны
  оставаться вне corpus.
- Не запускайте `graphify install --project`, strict mode или Graphify git hooks для YFC.
- Не включайте semantic/LLM extraction в автоматический bootstrap.
- Для широких вопросов используйте scoped `query`, `path`, `explain`, если graph актуален.
- Перед изменением кода проверяйте реальные source/tests/migrations/docs. При stale, ambiguous или
  incomplete graph переходите к исходникам.
- Не запускайте bootstrap для каждой мелкой правки и не расширяйте scope задачи по результатам graph.
