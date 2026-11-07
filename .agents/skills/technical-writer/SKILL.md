---
name: technical-writer
description: >
  Create or maintain long-term project documentation for setup, architecture, APIs, operations,
  deployment, migrations and contributor workflows. Use when a change makes project documentation
  inaccurate or when durable operational/architectural context is needed; follow repository
  language rules.
---

# technical-writer

Documentation should enable another engineer to perform the work without oral context.

When relevant document prerequisites, local setup, environment variables **without secret values**, run/test/lint/build commands, migrations, architecture, API contracts, integration setup, deployment, troubleshooting, operational runbooks and limitations.

Verify commands against the real repository; never invent them. Do not duplicate library documentation or obvious source code. Update relevant documentation in the same task whenever behavior changes.

## Structure

First inspect and follow the existing documentation structure. Do not add another directory hierarchy unnecessarily. If durable technical docs have no organization, propose a minimal purpose-based structure (architecture, features, operations), but do not impose it on a small change. Check subsystem docs before edits; document significant architecture, nonobvious business rules, security, operations and tradeoffs.

## Language and audience

Follow the root `AGENTS.md` and project language policy. Preserve the existing human-documentation language (Russian) and original API/library/command/identifier names. Write for concrete actions/decisions, not as code narration.

## Audit artifacts

Detailed/raw audit output is internal by default and belongs in the project's configured artifacts/scratch area, not committed documentation. Keep a durable audit document only when explicitly required. Never expose internal audit material through public app pages or published user docs.
