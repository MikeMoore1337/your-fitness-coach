# SkillSpector в YFC

NVIDIA SkillSpector используется как второй уровень проверки внешних agent skills.

## Слои защиты

### Layer 1 — YFC `skill_safety.py`

Всегда остаётся обязательным:

- stdlib-only;
- полностью offline;
- без LLM;
- без внешних runtime dependencies;
- запускается в pre-commit/CI/delivery;
- проверяет базовые опасные паттерны и `SOURCE.json`.

### Layer 2 — NVIDIA SkillSpector

Используется только когда меняются repository skills или когда внешний skill проверяется перед
vendoring.

Зафиксированная версия:

- release: `2.11.2`;
- commit: `69dcdfb74487d361ba4c811d088cfdea2ff3a9dc`;
- license: Apache-2.0.

SkillSpector не добавляется в `pyproject.toml`, backend, bot или frontend. Он запускается изолированно
через `uvx`.

## Production policy

Автоматический scan всегда static-only:

```text
--no-llm
--format json
--fail-on-incomplete
```

YFC wrapper дополнительно проверяет, что:

- `analysis_completeness.is_complete == true`;
- execution successful;
- LLM analysis не запрашивался и LLM calls не выполнялись;
- `SAFE` проходит;
- `CAUTION` проходит с явным warning;
- `DO_NOT_INSTALL`, `HIGH`, `CRITICAL` блокируют;
- malformed/incomplete/tool-error блокируют.

## Data egress

При static scan содержимое skill не отправляется LLM-провайдеру.

Wrapper удаляет из environment переменные, похожие на credentials/tokens/keys/secrets, до запуска
SkillSpector.

SkillSpector SC4 может выполнять собственный bounded lookup dependency coordinates в OSV.dev. При
недоступности сети upstream использует offline fallback. Это единственный допустимый внешний lookup
в default YFC static mode.

## CI routing

`.agents/skills/**` change добавляет CI group:

```text
external-skill-security
```

Она выполняется внутри существующего `policy` job после YFC policy-tests.

Если skills не менялись, SkillSpector:

- не устанавливается;
- не запускается;
- не увеличивает обычный product CI.

## Проверка кандидата до vendoring

Перед копированием внешнего skill в `.agents/skills/`:

```bash
python scripts/skillspector_guard.py scan /path/to/candidate-skill
```

После PASS:

1. добавить skill directory;
2. добавить `SOURCE.json` с immutable upstream commit и license provenance;
3. запустить YFC Layer 1;
4. открыть PR — CI повторит SkillSpector static scan.

## Что намеренно не используется

- SkillSpector MCP server;
- LLM semantic scan по умолчанию;
- OpenAI/Anthropic/NVIDIA API keys;
- runtime dependency;
- always-on SkillSpector pre-commit scan;
- замена `scripts/skill_safety.py`.
