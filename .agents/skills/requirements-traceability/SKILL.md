---
name: requirements-traceability
description: "Connect requirements to test cases, executions and evidence. Use when auditability or cross-team handoff is needed."
metadata:
  pack: "qa"
  version: "1.0.0"
---

# Requirements Traceability

1. Assign stable, repository-appropriate IDs or reuse existing tracker IDs; do not invent external issue IDs.
2. Create links `requirement -> test design -> implemented check -> execution -> evidence`.
3. Mark planned, implemented, executed, passed, failed and unknown as distinct statuses.
4. Store links in the existing issue/PR artifacts when possible; avoid creating a shadow source of truth.
5. Update mapping when scope changes, including approved exclusions and outstanding risks.

Use [traceability worksheet](references/TRACEABILITY.md) for a concise example. Jira and Test IT are optional integrations, not dependencies.


## YFC adaptation (development guidance only)

Source: [AI Development Toolkit](https://github.com/MikeMoore1337/ai-development-toolkit/blob/3a9bf14772ab579d37c6f4f9615db505ab6ac259/extensions/qa/skills/requirements-traceability/SKILL.md), pinned commit `3a9bf14772ab579d37c6f4f9615db505ab6ac259`.
Use only for: Complex Issue with multiple acceptance criteria requiring traceable evidence. Follow current YFC Issue, `AGENTS.md`, QA router, design/approval constraints, and protected `master` GitHub Flow. No new agent, controller, provider, runtime, or deployment permissions are granted.
