---
name: ux-ui-design-orchestra
description: "Run a unified read-only UX/UI audit of YFC Web, Telegram Mini App, landing or mobile screens through Impeccable, accessibility and motion expertise; produce one sport-tech design proposal and plan, never editing UI before owner visual approval."
metadata:
  version: "1.0.0"
  source: "AI Development Toolkit@0d3849e040e09b4e350e0bf97af66b4d107e94d6"
---

# YFC UX/UI Design Orchestra

**Trigger**: «Проведи комплексный UX/UI-аудит», «проверь экран несколькими скиллами», «предложи один редизайн без нейрослопа». Not for backend or ordinary implementation where visual design has been approved.

Read project `AGENTS.md`, `codex-backlog/ACTIVE_DESIGN_SOURCE.md`, `.agents/references/DESIGN_GUARDRAILS.md`, `docs/design/YFC_PRODUCT_UI_CONTRACT.md` and the [local process](../../../docs/development/ux-ui-design-orchestra.md). Common methodology: [AI Development Toolkit UX/UI Design Orchestra at exact commit](https://github.com/MikeMoore1337/ai-development-toolkit/blob/0d3849e040e09b4e350e0bf97af66b4d107e94d6/.agents/skills/ux-ui-design-orchestra/SKILL.md); if inaccessible, use this local contract and record `GUIDANCE_ONLY`, not `LOADED` for Toolkit upstream.

**Default `audit-proposal` = READ_ONLY.** No UI/CSS/TypeScript, asset, test, design document, backend, workflows, production, issue/PR or app modification. Return one unified audit and design plan in chat. Only save preview PNG/HTML to an authorized review location when actually generated. A text idea is `TEXT_SPEC`, not a screenshot.

**Specialist selection (at most 3 independent read-only analyses):**
- Primary: `$impeccable` original pinned submodule, loaded only when initialized; `$product-designer` defines the YFC brand and task-specific visual direction. Sport-tech, Oswald/Inter, black+lime/dark and white+lime/light, Liquid Glass, 5-tab mobile dock, one-hand flows and motion are owner anchors, not slop.
- Technical: `$ui-audit`, `$accessibility-engineer` and UI Skills method *only as needed*; mobile 320/360/390/430, TMA, light/dark, states, touch/keyboard, safe area, focus, error/loading/empty, Russian UI.
- Motion: `$motion-design-engineer` and Emil's motion methods *only if the actual task requires animation*; reduced motion and performance. Taste or UI UX Pro Max only for owner-authorized visual exploration. External CLI/hooks/installers are never launched automatically.

Delegate with actual client subagent tool when available, max 3 simultaneously. Report tool IDs and whether specialized or generic. If not available, run these reviews sequentially and label `SEQUENTIAL` (not imaginary independent agents). Each receives same inspected state/viewport, revision, and design constraints, without credentials/personal health data.

**Convergence**: confirmed issues with evidence IDs versus hypotheses, causes, severity, alternatives, one recommended concept preserving brand, component/interaction/state changes, QA checklist, real visual package, later implementation order, approvals. Distinguish rendered from code-only and unobserved. For substantial visual changes deliver all completed final PNG/HTML candidates together; **stop before implementation until owner's «Принимаю»**. Acceptance of mockup does not authorize release; afterward real AFTER evidence and separate acceptance/release as in AGENTS.

No second controller, local daemon, paid API, permanent report inside repo, or automatic merge/deploy. Missing browser or upstream skill is NOT_RUN, never PASS.
