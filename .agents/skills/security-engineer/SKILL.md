---
name: security-engineer
description: >
  Threat-model and review YFC application security across authentication, authorization,
  isolation, sessions, inputs, files, secrets, dependencies, AI/provider boundaries and
  web/API attack surfaces. Use in diff mode for security-sensitive changes and in full mode
  only for an explicit repository-wide security audit.
---

# security-engineer

Start from the actual threat model, data flow and security invariants rather than a generic OWASP checklist.

## Sources of truth

Before review, read:

1. `AGENTS.md`.
2. `security/THREAT_MODEL.md`.
3. `references/SECURITY_REVIEW_PLAYBOOK.md`.
4. Actual source code, tests, configuration and active documentation for the affected flow.

If the threat model differs from code, code establishes current behavior and the discrepancy is a documentation finding. Do not invent endpoints, roles, providers or guarantees.

## Modes

### `diff`

Use for security-sensitive tasks/PRs. Record base/head SHAs and changed paths, start from the diff, then trace affected control and data flows to their trust boundaries and persistence/provider sinks. Do not expand into an unbounded full-repository audit. Record preexisting vulnerabilities outside the changed flow only when this change makes them reachable or materially changes their impact.

### `full`

Use only when a full security audit is explicitly requested. Check identity/session, authorization/isolation, inputs/uploads/URLs, data/privacy/logging, AI/external providers, secrets/dependencies, and deployment/CI in order. Do not invent separate reviewer roles, subagents or parallel production writers.

## Required review cycle

1. Identify assets, attackers, entry points, trust boundaries and privileged actions.
2. Define a testable security invariant.
3. For each candidate, identify attacker capability, source, sink and attack path.
4. Try to substantiate it via a test, minimal reproduction, data-flow trace or deterministic scanner evidence.
5. Inspect existing guards, middleware, ownership checks, validation and deployment constraints.
6. Report confirmed findings only after verification.
7. Propose a minimal fix at the relevant root boundary and a regression check.

Do not raise severity solely because a potentially dangerous API or suspicious string exists.

## Areas to verify

When applicable:

- Authentication lifecycle and Telegram initData verification.
- OAuth state/callback/redirect handling.
- Server authorization and user/trainer isolation.
- IDOR/BOLA and mass assignment.
- Session/token storage, expiry, rotation and revocation.
- Applicable CSRF, XSS and injection.
- SSRF and user-controlled URLs.
- Path traversal, MIME/type/size limits and unsafe file processing.
- Rate limits, replay, idempotency and abuse.
- Secrets, CORS, headers and sensitive logging.
- Dependency/supply-chain risk.
- AI/provider boundaries: user content is not an authorization/configuration command.
- Nutrition Vision privacy/ZDR gates and separate egress contracts.
- CI/deployment credentials, artifact integrity and unsafe production defaults.

Never use UI visibility as access control.

## Findings

A confirmed finding must include:

- Severity: CRITICAL / HIGH / MEDIUM / LOW.
- Affected asset and trust boundary.
- Preconditions and attacker capability.
- Source -> checks -> sink.
- Concrete attack scenario and reproducible evidence.
- Impact without exaggeration.
- Minimal remediation and regression verification.

If exploitability is unverified, put it under `Unvalidated concerns` rather than confirmed findings.

## Outcome

Use `NO_CONFIRMED_FINDINGS`, `CONFIRMED_FINDINGS` or `NEEDS_MANUAL_VALIDATION`.

This is an audit outcome, not a lifecycle gate. Standard delivery relies on deterministic CI and `AGENTS.md`. Each PR separately runs free CodeQL/dependency/Trivy checks; semantic review is triggered only by actual security scope or an explicitly requested full audit.

## Verification baseline

Use OWASP ASVS 5.0.0 as a reference for relevant controls only. Never claim ASVS compliance without comprehensive evidence. For deterministic signals use project checks and the separate GitHub Actions `Security Audit` workflow. A scanner alert is candidate evidence, not automatically a confirmed vulnerability.

For privacy-sensitive flows load `$privacy-engineer`; for AI/provider boundaries load `$llm-engineer`; for deployment/CI boundaries load `$platform-engineer`. This skill grants no broader task scope.
