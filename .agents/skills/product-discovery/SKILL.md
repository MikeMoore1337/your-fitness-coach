---
name: product-discovery
description: >
  Define or refine product requirements, target users, jobs-to-be-done, critical journeys,
  first-use experience, MVP scope, success signals, risks and testable acceptance criteria. Use
  before designing or implementing a new product, major feature, onboarding flow or substantial
  behavior change. Do not use for implementation-only tasks with already approved requirements.
---

# product-discovery

Do not design technology or screens before understanding the user's problem and expected outcome. Discovery should reduce uncertainty enough for verifiable design/engineering decisions, not generate a long document.

## Product brief

Concise facts: problem/context, target users/roles, Jobs-to-be-Done or desired outcome, user/product value, critical journeys, mandatory constraints, scope/MVP inclusions and exclusions, unknowns/dependencies/risks and success criteria without fabricated metrics.

Distinguish facts, confirmed requirements, assumptions, open questions and desirable improvements. Never invent market research, statistics, analytics or user behavior.

## Primary device and context

State the primary device and usage context. For YFC Personal/client daily flows default to smartphone-first, Mobile Web/TMA, short activities during workouts/day, one hand, keyboard, interruptions, unreliable network; desktop remains first-class for detailed setup/analytics. A desktop wireframe alone is not complete acceptance. Explicitly mark Coach/Admin flows as desktop-first when justified, with mobile fallback/TMA boundaries.

## Critical journeys

For each journey identify trigger, preconditions, main path, meaningful alternatives, failure/empty/permission/degraded states, observable completion, post-action UI and recovery (undo/correct/retry). Focus on end-to-end goals rather than isolated screens.

## First use and time-to-value

For new products/roles/major features assess what is self-explanatory, the smallest action that provides first value, deferrable setup/data collection, whether onboarding demands too much, need for examples/demo/empty-state hints and what encourages continued use. Do not introduce onboarding for its own sake when direct entry works.

## Friction and cognitive load

Find unnecessary mandatory steps, repeated entry of known data, premature decisions, internal jargon, overloaded forms, missing sensible defaults and safe shortcuts for repeated actions. Recommend recent/favorites/templates/history only when they materially reduce repeated effort. Use progressive disclosure for advanced configuration.

## Trust and control

For recommendations, calculations, automation or irreversible actions, clarify what happened and why where needed, when confirmation is required, whether it can be corrected/undone, how uncertainty/stale results appear, whether false precision/guarantees are implied and whether requested data has a clear user benefit.

## Success signals and analytics

Identify activation, successful critical actions, repeat usage when valuable, abandonment/failure and retention proxies only when relevant. Do not invent numeric KPIs. Describe instrumentation through event meaning, trigger point and minimal necessary attributes; never export sensitive data merely for analytics convenience.

## Acceptance criteria

Write observable, testable criteria per critical journey, covering relevant validation, permissions, error recovery, empty states, repeated actions/idempotency, state persistence/recovery, responsive/mobile, accessibility and privacy. Avoid prescribing implementation internals unless they are explicit constraints.

## Sensitive data

For personal, financial, medical, biometric or otherwise sensitive data, define purpose, minimum data, access boundary, retention/deletion, export/account deletion where relevant, telemetry/logging restrictions and abuse risks. Carry them into `$privacy-engineer`, `$security-engineer`, architecture and acceptance criteria.

## Completion

Discovery is sufficient when the team knows whom and what problem it serves, critical path to value, observable success, recoverable errors/limitations, scope boundaries, unvalidated assumptions and design/security/privacy/technical risks. Prefer a short brief over a formal PRD unless necessary.
