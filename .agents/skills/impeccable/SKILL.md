---
name: impeccable
description: "Primary UX/UI design critique and polish skill for existing YFC frontend, landing, React Web, Telegram Mini App and mobile flows. Load official SHA-pinned Impeccable before offering designs, and respect the owner's design authority. Not for backend-only tasks."
metadata:
  version: "4.7.0"
  origin: "pbakaus/impeccable@dad8dbb3aac21ad1fa236c110315ef4abece23e8"
---

# Impeccable для Your Fitness Coach

**Это рабочий вход для Codex**, не новая роль, не разрешение на автоматическое изменение приложения.

1. Перед UX/UI-задачей проверь `.impeccable/.agents/skills/impeccable/SKILL.md` и точный pinned Git commit `dad8dbb3aac21ad1fa236c110315ef4abece23e8`. Если файла нет, попроси инициализировать подмодуль `git submodule update --init -- .impeccable`; не выдавай собственную редакторскую памятку за установленный upstream.
2. Прочитай **оригинальный** `.impeccable/.agents/skills/impeccable/SKILL.md`, затем только справку для нужной команды в `.impeccable/.agents/skills/impeccable/reference/`. В Windows и Codex вызывается `$impeccable`, а не выдуманная slash-команда. Оригинал - материал для работы, не источник разрешений.
3. Прочитай `AGENTS.md`, `codex-backlog/ACTIVE_DESIGN_SOURCE.md`, `.agents/references/DESIGN_GUARDRAILS.md`, `docs/design/YFC_PRODUCT_UI_CONTRACT.md`. Принятые Осwald/Inter, палитра black/white+lime, Liquid Glass, 5 пунктов навигации, sport-tech motion и все компоненты остаются, даже если upstream считает их антишаблонами.
4. Для каждого изменения начинай с `critique` или `audit` на конкретном реально отрисованном экране. Укажи причину, эффект и проверяемую альтернативу. Затем `shape` / `distill` / `polish` в рамках задачи. Избегай пустых карточек, декоративных бейджей, одинаковых SaaS-плашек и случайных градиентов **по наблюдаемому дефекту**, а не по списку запретных стилей.
5. Результаты - конкретные скриншоты desktop/mobile и состояний, Playwright/browser evidence, accessibility и reduced-motion. Публикуй визуальный пакет до реализации при изменении композиции; реализуй только после принятия. Отсутствие фактического рендера = `NOT_VERIFIED`.
6. Не включай auto-hooks, `npx`, внешние бинарники, слепую загрузку upstream `scripts/impeccable`, изменение PRODUCT.md/DESIGN.md, paid API и новые runtime зависимости. Скрипт upstream может скачивать бинарник; без отдельной проверки ограничься исходными текстовыми playbooks.

Подробнее: `docs/development/impeccable-adoption.md`. Обязательные владелец/закон/безопасность/CI/релиз gates имеют приоритет.
