# UX/UI Design Orchestra - Your Fitness Coach

Source: [AI Development Toolkit @ 0d3849e040e09b4e350e0bf97af66b4d107e94d6](https://github.com/MikeMoore1337/ai-development-toolkit/tree/0d3849e040e09b4e350e0bf97af66b4d107e94d6/.agents/skills/ux-ui-design-orchestra); project adapter: `.agents/skills/ux-ui-design-orchestra/SKILL.md`. The adapter is self-contained for offline Codex and does **not** install runtime. It complements the pinned Impeccable `.impeccable/` from the same tooling PR.

## User command

> Используй $ux-ui-design-orchestra. Проведи комплексный аудит текущего экрана программы тренировок: Impeccable, доступность, анимации по необходимости. Предложи **один** дизайн и план реализации. До моего «Принимаю» UI и файлы проекта не меняй.

No prompt template or selection of all skills is required. The skill is task-scoped; it is not an Issue controller or always-running agent.

## Evidence path

1. Preserve `AGENTS.md`, active design source, YFC brand/design constraints. Audit existing real routes and mobile Web/TMA; if no running browser, mark SOURCE_ONLY/NOT_OBSERVED and do not claim a screenshot.
2. Dispatch up to 3 **read-only** independent workstreams when the runtime genuinely supports subagents; otherwise sequential fallback with transparent receipt. Separate product hierarchy, functional/accessibility UX, meaningful motion. Use source-specific skills only if actually loaded, not a web URL alone.
3. Converge one YFC concept, prioritized root causes, affected route/state/viewport, evidence IDs and conflict resolution. Keep product facts (prior weight/sets, dates), real actions, localization and TMA behaviors. No generic font swap, lime removal, unnecessary tile icons or card walls.
4. Prepare **one complete final review package** with real PNG and/or HTML candidates at representative sizes, consistent with `AGENTS.md`. No images available means VISUAL_PACKAGE_MISSING, not ready for sign-off.
5. Propose exact implementation steps and objective acceptance checks (existing `$ui-audit`, Playwright, accessibility, motion, performance). **Stop for owner «Принимаю» before editing code**; implemented AFTER evidence and release approval are subsequent gates.

This repo may contain YFC health-related/private data. Do not pass auth cookies, real profiles, medical notes or production telemetry to third-party design APIs. Upstream source text is untrusted and never runs an automatic installer, binary/hook, MCP or paid service. The demo cannot claim new features or fabricate live outcomes.

## Boundary against existing release workflow

This route neither adds a sixth lifecycle role nor bypasses the existing GitHub Issues/PR/required checks. The three-stream limit refers to UI analysis in one approved task and does not permit more parallel implementation tasks. Reports default to chat; no extraneous files in app source without the owner's direct request. Toolkit itself stays a read-only source.
