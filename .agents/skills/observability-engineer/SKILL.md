---
name: observability-engineer
description: >
  Design production observability using correlated logs, metrics, traces, health checks,
  SLO-oriented alerts and product-critical signals. Use when a deployed system needs diagnosis,
  monitoring or operational feedback; do not add telemetry without a concrete question it must answer.
---

# observability-engineer

Observability must answer: (1) what broke/degraded; (2) where/why; and (3) how it affects users or critical product journeys. Do not add telemetry merely to produce more dashboards.

## Correlation

Where supported, connect `user action -> frontend/API request -> backend operation -> DB/external dependency -> result`. Use request/correlation IDs and trace/span context to navigate from symptoms to specific operations; never use raw user IDs as high-cardinality metric labels.

## Logs

Use structured logs when supported, including timestamps, severity, service/component, correlation/trace IDs, meaningful error context and machine-readable important events. Never log passwords, tokens, cookies, whole request bodies or unnecessary personal information. Logs should explain events, not mirror all runtime state.

## Metrics

Select small, meaningful sets of request rate, error rate, latency, saturation, queue/jobs, dependency health, resource pressure and critical product successes/failures. Avoid unbounded cardinality such as raw user IDs, UUIDs and dynamic URLs.

## Traces

For critical distributed/integration flows, add traces only when supported. They should expose time spent, failing/delayed dependencies, retries, fanout and async boundaries without sensitive payloads.

## Product-critical signals

Prefer actual success outcomes, such as a saved workout/order/document, completed checkout, processed import or scheduled job producing its promised user result, rather than counting HTTP 2xx alone. Define product metrics from actual semantics, never invented KPIs.

## Frontend/RUM

When available, monitor relevant Core Web Vitals, client exceptions, resource/chunk load failures, navigation/API errors and critical-flow outcomes. Minimize data and coordinate sensitive fields with `$privacy-engineer`.

## Health checks

Distinguish liveness, readiness and dependency health. Do not create heavyweight health endpoints or mark readiness green when a mandatory dependency makes core requests impossible.

## Alerts and SLOs

Alerts must warrant action. Favor symptoms and user/SLO impact over internal noise. Each important alert must explain meaning, urgency, initial investigation, linked dashboards/logs/traces and possible recovery/rollback. Do not alert simply because a metric exists.

## Verification

For a critical incident, trace alert/symptom -> affected journey -> metric/trace -> operation -> correlated logs -> dependency/root cause. If this path is impossible, observability is incomplete.
