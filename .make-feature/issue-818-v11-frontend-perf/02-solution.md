# Make Feature solution — Product V11-03 / Issue #818

Status: accepted for this implementation pass.
Context: existing Draft PR #1126, application head `4e6b85235bb425ab7bcbcc81659149fa2af244d3`.

## Requirements

The Issue requires a faster existing Web/PWA/TMA experience without visual redesign, business-logic changes, security weakening, HD-media degradation or production changes. Only measured bottlenecks are in scope.

## Basis and choice

The matched current-master build was 310,971 raw / 97,485 gzip for the entry JS and failed the existing 96,000-byte gzip budget. Source tracing showed eager demo-session code and authenticated route internals in the public bootstrap. The smallest fixes were existing dynamic imports and one auth-only route module.

The source audit found no defensible evidence for global Query cache changes, broad render memoization, router replacement, or media re-encoding. Those candidates remain deferred rather than optimized by intuition.

## Contract

- Public routes do not load demo-only session code or authenticated route internals eagerly.
- Telegram `/demo` clears stored demo tokens before React renders.
- Exercise guide video remains lazy, uses the approved HD source/poster, pauses when offscreen or document-hidden, and resumes without replacing the source.
- `perf:check` remains strict and runs after the frontend build in the existing CI group.
- Auth, navigation, API and user data contracts stay unchanged.

## Plan and checks

1. Build and run `perf:check` on `42a75a5f` and PR code head `4e6b8523`.
2. Run typecheck, lint, CI-compatible Prettier and full Vitest on AFTER.
3. Run the existing performance-hardening Playwright scenario on both revisions with the same mocked fixtures.
4. Re-read the exact PR checks and leave merge/deploy to the owner.
5. Keep production/field/device claims as `NO_DATA` where the source is unavailable.

Evidence and command results are in [the implementation report](../../docs/development/product-v11-03-frontend-performance-2026-10-19.md).
