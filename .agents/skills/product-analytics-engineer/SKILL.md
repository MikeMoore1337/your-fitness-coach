---
name: product-analytics-engineer
description: >
  Design, implement or review privacy-safe product event taxonomy, funnel instrumentation,
  activation, retention, identity transitions, event schemas and data-quality checks. Use when
  product behavior must be measured. Do not use for operational logs/metrics or indiscriminate
  every-click tracking.
---

# product-analytics-engineer

Begin with the product question, not a proposed event. Every event must inform a decision.

## Distinction from observability

Product analytics explains where users start, finish, abandon, reach first value, return and respond to product variants. Observability explains service health, errors, latency, throughput and resources. Do not copy operational logs into analytics or raw product content into metrics. Use `$observability-engineer` for runtime signals.

## Before instrumentation

For each feature define product question, decision, journey/states, success/failure/abandonment, event owner (client/server), minimal properties, privacy/consent limits and dashboard/validation plan.

Inspect actual analytics/SEO stack, legal/consent path, environments, accounts, Demo/Web/TMA and existing events. Do not add a parallel pipeline without need. Verify legal requirements against official sources and actual jurisdiction rather than guessing.

## Event taxonomy

Describe stable business occurrences instead of incidental DOM actions. Appropriate levels include landing/demo/login/onboarding, program/workout, nutrition logging, measurements/check-ins, coach/admin flows, suggestion shown/accepted/dismissed, export/delete lifecycle and high-level AI request/outcome without text. Avoid tracking every click/hover/scroll without a clear decision.

For each event define canonical name/version, semantics and trigger, producer, required/optional allowlisted properties, dedupe/idempotency, subject identity class, environment/surface, retention/consent, examples/prohibited payloads and dependent metrics/funnels.

## Neutral event envelope

Use a provider-neutral internal contract with fields as warranted: event ID/name/version, occurred_at/received_at, environment, client surface, scoped anonymous/authenticated subject, optional session/journey/correlation, producer and allowlisted properties. Vendor payload formats must not become the sole source of truth.

## Client versus server events

Client can capture impressions, visible prompts, user intent and relevant validation/abandonment. Server should record completed authentication, real program/workout/food/measurement saves, permission/admin actions, export/deletion jobs and high-level accepted/completed AI requests.

A client click is not success. Avoid client/server double counts without clear ownership and dedupe.

## Identity lifecycle

Distinguish anonymous visitor, pre-auth/demo, authenticated account, device/session, trainer/admin capabilities and Web/TMA. On anonymous -> authenticated, use trusted canonical mapping rather than client-side email/Telegram-ID linking; avoid duplicate conversions, cross-user leakage after logout on shared devices and treating Demo fixtures as real users. Capability is not identity.

Do not send raw DB/user/Telegram IDs externally unless necessary; use policy-approved scoped/pseudonymous identifiers.

## Private fields

Default-prohibited event properties include food/recipe content, exact calories/macros/weight/measurements/HR/distance, trainer comments, notes, support messages, AI prompts/answers/tools, private custom exercise names, tokens/initData/email/phone, secrets/stack traces, file contents and arbitrary URLs/query parameters containing personal information.

An event like `measurement_logged` usually needs no measurement value; `cardio_logged` needs no distance/HR. Use allowlists and sensitive-field regression tests. For privacy review load `$privacy-engineer`.

## Consent and failure

Never enable hidden tracking as a side effect of SEO/UI work. Apply consent/opt-out before external delivery. Analytics outages must not fail product actions. Bound queue/retry, deduplicate safely and limit offline buffer size/age without private content. Observe provider outages but do not block users. Isolate staging/test from production reports.

## Compatibility

Change the event version/name when semantics change. Optional fields must not silently alter meaning. Plan required-field rollout for mixed client/server versions. Version consumers/dashboards; assign owners/removal dates for deprecated events. Never reuse old names for new product questions.

## Dedupe and time

Handle SPA rerenders/route transitions, double clicks, retries/reloads, back/forward, multiple tabs/devices, offline/delayed events, server retries, timezones and clock skew. `occurred_at` and `received_at` are distinct; record funnel windows/reporting timezones. Do not deduplicate two genuinely repeated user actions using only user + event name; use appropriate journey/business keys.

## Funnels, activation, retention

Define populations/denominators, entry, ordered/unordered steps, completion, allowed repeats, windows, cross-device behavior, exclusions, timezone, versions and dates. Activation means first real value, not merely registration. Retention means meaningful return behavior, not any page view. Do not redefine metrics after seeing data to produce attractive numbers.

## Experiments

When explicitly needed, assign variants once at a trusted boundary, keep them stable, record exposure only on actual exposure, exclude sensitive outcome payloads, monitor sample ratio/contamination and predefine stopping rules/primary metrics. Analytics failures must not alter variants. Do not add an experimentation platform speculatively.

## Data-quality checks

Validate schemas, required properties, unknown event/field rate, duplicates, late/out-of-order events, environment contamination, anonymous/auth transitions, client/server reconciliation, provider failures, volume anomalies, funnel invariants and sensitive payloads. Dashboards without data-quality checks create false certainty.

## AI and fitness

AI analytics may record start/completion/failure, generic/personalized class, unavailable/tool-unavailable states, memory/rationale UI interactions and relevant latency buckets/error classes where not duplicated operationally. Never store raw AI conversations, prompts, answers, tool arguments/results or exact user facts. Exact fitness/health measurements remain in authorized canonical product/reporting storage, not analytics event properties.

## Tests

Cover valid/invalid schemas, prohibited-field rejection/redaction, rerender/double-click dedupe, server outcomes versus client intent, anonymous/auth continuity without cross-user merge, Web/TMA/Demo distinctions, environment isolation, consent/opt-out, provider nonblocking outages, late events, version compatibility, funnels and absence of raw AI/support/fitness content.

Use `references/PRODUCT_ANALYTICS_CHECKLIST.md`.

## Deliverable

Document product questions, event-catalog changes, funnel/activation/retention definitions, identity/privacy decisions, implementation ownership, dashboard/validation changes, checks and blind spots.

Never implement indiscriminate click tracking, sensitive session replay, full analytics request/response logging, raw health/PII, domain vendor lock-in, registration-as-activation without rationale, undefined metrics or unverified consent/legal assumptions.
