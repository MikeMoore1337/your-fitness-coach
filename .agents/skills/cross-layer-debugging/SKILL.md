---
name: cross-layer-debugging
description: "Use when locating and fixing a reproduced defect across UI, API, service, worker or database boundaries."
---

# Cross-layer debugging

**Use for:** an observed cross-layer defect with traceable symptoms. **Do not use for:** speculative architecture design or general code review without a failing journey.

**Inputs:** expected vs observed behavior, reproducible steps, environment, timestamps, safe logs/request IDs, known contracts and permission boundaries.

1. Reproduce the user-facing failure and record the precise input, expected outcome, actual outcome and environment without collecting secrets.
2. Correlate each hop from UI through request, service, persistence and response/event. Identify the **first** mismatch against a verified contract, not merely the layer where the symptom is visible.
3. State a falsifiable hypothesis, a confirming observation and an alternative explanation (cache, deployment drift, test harness or backend).
4. Gather counterevidence. If the first mismatch or root cause cannot be proved, report it as a hypothesis and stop before speculative production changes.
5. Apply the smallest fix at the owning layer, rerun the original failure and neighboring/negative cases; record which checks were actually executed.

**Example:** the UI shows the previous value after PUT 200. Inspect response version, DB commit, cache invalidation and request order before assuming that the backend failed. A late GET may be the first mismatch.

**Output:** sanitized evidence chain, first divergent seam, confirmed or provisional root cause, fix/diff (if authorized), verified regressions and NOT_MEASURED gaps. No production debugging writes without approval.


## YFC adaptation (development guidance only)

Source: [AI Development Toolkit](https://github.com/MikeMoore1337/ai-development-toolkit/blob/3a9bf14772ab579d37c6f4f9615db505ab6ac259/extensions/fullstack/skills/cross-layer-debugging/SKILL.md), pinned commit `3a9bf14772ab579d37c6f4f9615db505ab6ac259`.
Use only for: A reproduced error crossing React/TMA, FastAPI and PostgreSQL/worker. Follow current YFC Issue, `AGENTS.md`, QA router, design/approval constraints, and protected `master` GitHub Flow. No new agent, controller, provider, runtime, or deployment permissions are granted.
