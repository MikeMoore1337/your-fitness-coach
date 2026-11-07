---
name: impeccable
description: "Primary UX/UI design critique and polish skill for existing YFC frontend, landing, React Web, Telegram Mini App and mobile flows. Load official SHA-pinned Impeccable before offering designs, and respect the owner's design authority. Not for backend-only tasks."
metadata:
  version: "4.7.0"
  origin: "pbakaus/impeccable@dad8dbb3aac21ad1fa236c110315ef4abece23e8"
---

# Impeccable for Your Fitness Coach

**A Codex entry point, not a new role or permission for automatic app changes.**

1. Before UX/UI work verify `.impeccable/.agents/skills/impeccable/SKILL.md` at exact pinned Git SHA `dad8dbb3aac21ad1fa236c110315ef4abece23e8`. If missing, request `git submodule update --init -- .impeccable`; never claim a local editorial summary is installed upstream Impeccable.
2. Read the **original** upstream `.impeccable/.agents/skills/impeccable/SKILL.md`, then only the required command reference in `.impeccable/.agents/skills/impeccable/reference/`. Invoke it as `$impeccable` in Windows/Codex, not an invented slash command. Upstream guidance grants no new permissions.
3. Read `AGENTS.md`, `codex-backlog/ACTIVE_DESIGN_SOURCE.md`, `.agents/references/DESIGN_GUARDRAILS.md` and `docs/design/YFC_PRODUCT_UI_CONTRACT.md`. Approved Oswald/Inter typography, black/white+lime palette, Liquid Glass, five navigation entries, sport-tech motion and components take precedence over upstream generic design prohibitions.
4. Start each real-screen change with `critique` or `audit` on a **rendered** route/state. Give cause, observable effect and testable alternative. Apply `shape`/`distill`/`polish` only within task scope. Reject empty cards, ornamental badges, generic SaaS tiles and arbitrary gradients because of observed defects, not blanket style bans.
5. Provide actual desktop/mobile screenshots and state evidence, Playwright/browser verification, accessibility and reduced-motion checks. For composition changes deliver the complete visual review package **before** implementation and implement only after owner acceptance. No actual render means `NOT_VERIFIED`.
6. Never enable auto-hooks, `npx`, external executables, unchecked upstream `scripts/impeccable`, automatic PRODUCT.md/DESIGN.md edits, paid APIs or new runtime dependencies. An upstream script may download a binary; unless separately reviewed, use only static source playbooks.

See `docs/development/impeccable-adoption.md`. Owner, legal, security, CI and release gates always take precedence.
