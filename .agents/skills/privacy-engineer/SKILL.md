---
name: privacy-engineer
description: >
  Review and design privacy behavior for personal, health, financial, biometric or otherwise
  sensitive data: minimization, purpose, access, retention, deletion, export, telemetry, third-party
  sharing and lifecycle. Use when sensitive user data is collected or its lifecycle changes. Pair
  with security-engineer; privacy is not a substitute for application security.
---

# privacy-engineer

Privacy and security are related but different: security prevents unauthorized access; privacy determines what data is needed, why and for how long.

Do not impersonate legal counsel or invent legal obligations without verifying jurisdiction. Produce engineering privacy requirements and flag legal matters for jurisdiction-specific review.

## Inventory

For each affected flow identify data collected/created, source, purpose, owner/subject, storage/transfers, accessible roles/services, sensitivity and any copies in logs, analytics, traces, backups, caches or external platforms.

## Minimization

For each field/event ask whether the feature truly needs it, whether less detail or transient computation would suffice and whether collection can be deferred. Never collect speculative "future use" data.

## Purpose and access boundaries

Define primary purpose, genuinely needed secondary uses, forbidden cross-context reuse, user/role/tenant boundaries, limited support/admin access and analytics eligibility. Do not repurpose sensitive data silently.

## Retention and deletion

Define duration/ending event, justified hard/soft deletion, dependent records, account deletion, cache/session cleanup, queues/jobs, backup lifecycle limits and separately retained security/audit records when required. Verify deletions and avoid orphan copies in the primary system.

## Export and control

For meaningful stored user data assess view/correction/export, record deletion, account deletion and optional integration/permission revocation. UI controls must work across all dependent layers, not just look functional.

## Telemetry, logs and analytics

Minimize sensitive fields. Do not unnecessarily transmit credentials, tokens, session cookies, full request/response bodies, health/financial details, user-generated text, photos/files or precise identifiers when aggregate/pseudonymous signals suffice. Prefer event names like `workout_saved` and `flow_completed` to copying user data into properties.

## Third parties

Document actual external payload, reduction/surrogates, retry duplication risk, local data cleanup on disconnection and adapter logging. Never assert contractual/legal guarantees about a provider without verifiable evidence.

## Privacy UX

Explain why sensitive input/permission is needed, request it at the relevant moment, make destructive deletion clear and avoid deceptive defaults or mislabeling mandatory versus optional collection.

## Verification and findings

For significant changes trace UI/API -> storage -> external services; verify authorization with `$security-engineer`, export/deletion, log/metric/trace leaks, migrations/backfills, backups and fixtures/debug artifacts.

Findings must identify data/flow, privacy risk, source of unnecessary retention/sharing, minimal fix and verification.

## Project adaptation

Inspect actual data models, observability/analytics, backups, object storage, integrations and privacy policies first. Do not impose consent banners, retention periods or legal text without a verified requirement.
