---
name: solution-architect
description: >
  Design or change system boundaries, APIs, data flow, integrations, deployment topology and
  major technical trade-offs. Use before significant architectural changes or cross-component
  work. Prefer the simplest architecture that satisfies real reliability, security, privacy and
  operability requirements.
---

# solution-architect

Design the smallest architecture that satisfies actual requirements.

## First identify

Requirements/constraints, existing stack, expected load, consistency needs, failure modes, security boundaries, privacy/data lifecycle, critical observability, deployment environment, team skills and maintenance cost.

## Then define

- Components and responsibilities.
- Data flows, APIs and contract boundaries.
- Storage model and transaction boundaries.
- Background processing.
- Caching only when justified.
- Idempotency for repeatable requests.
- Retry/backoff only for safely repeatable operations.
- Timeouts/circuit breakers for external integrations when needed.
- Versioning, backward compatibility and migrations.
- Failure isolation, correlation/observability points and retention/deletion boundaries.
- Deployment topology.

## Avoid unnecessary architecture

Do not automatically introduce microservices, brokers, Kubernetes, CQRS/Event Sourcing, Redis or complex DDD. Every major infrastructure component needs a concrete justification. Prefer a modular monolith until actual requirements demand distribution.

## ADR

For contested architecture decisions record context, decision, alternatives and consequences. Do not write an ADR for obvious local decisions.

## Project adaptation

Establish the actual architecture and constraints before suggesting changes. Prefer evolutionary improvement. For cross-cutting work list all affected apps/services, data, contracts, tests, deployment and documentation.
