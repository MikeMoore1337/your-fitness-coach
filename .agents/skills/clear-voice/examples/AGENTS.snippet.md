# Необязательное дополнение к локальному AGENTS.md

Вставляйте только в тот проект, куда реально добавили папку скилла. Это **пример фрагмента**, не готовая замена текущего AGENTS.md.

```markdown
## Редактура текстов

При создании или правке пользовательских и проектных текстов используй `$clear-voice`
из `.agents/skills/clear-voice/SKILL.md`, выбирая подходящий профиль в `profiles/`.
Существующие требования безопасности, фактической точности, локализации, юридической
проверки, схем данных, review и owner-approval имеют приоритет. Clear Voice не
заменяет профильных специалистов и не даёт разрешения на публикацию или запись.
```

Для Second Brain добавьте, если нужно: «Профиль `second-brain` не меняет пять полей NoteDraft, отдельное provenance и Safe Write».

Для YFC добавьте, если нужно: «Профиль `yfc` не заменяет `$evidence-content-editor`, `$fitness-domain-reviewer`, `$technical-writer` или `$localization-engineer`».

Hermes runtime не читает `AGENTS.md`. Для него смотрите `adapters/hermes/README.md`.
