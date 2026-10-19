# Make Feature solution — Product V11-03 / Issue #818

Status: NEEDS_WORK for release approval; the scoped chunk-graph fix is implemented and verified.
Context: existing Draft PR #1126, measured application head `b516f9ca`; the security follow-up is lockfile-only.

## Requirements

The Issue requires a faster existing Web/PWA/TMA experience without visual redesign, business-logic changes, security weakening, HD-media degradation or production changes. Only measured bottlenecks are in scope.

## Basis and choice

The matched current-master build was 310,971 raw / 97,485 gzip for the entry JS and failed the existing 96,000-byte gzip budget. Source tracing showed eager demo-session code and authenticated route internals in the public bootstrap. The smallest fixes were existing dynamic imports and one auth-only route module. The final profiling also showed that nesting `MiniAppPage` under that auth module inflated `CoachPage` from 186.51 kB raw / 45.77 kB gzip to 386.98 kB / 97.80 kB; moving the existing `MiniAppPage` lazy import back to the top-level route graph restored 186.59 kB / 45.80 kB without changing route behavior.

The source audit found no defensible evidence for global Query cache changes, broad render memoization, router replacement, or media re-encoding. Those candidates remain deferred rather than optimized by intuition. A required audit failure was fixed with the smallest compatible lockfile-only `aiohttp` refresh; backend source was not changed.

## Contract

- Public routes do not load demo-only session code or authenticated route internals eagerly.
- Telegram `/demo` clears stored demo tokens before React renders.
- Exercise guide video remains lazy, uses the approved HD source/poster, pauses when offscreen or document-hidden, and resumes without replacing the source.
- `perf:check` remains strict and runs after the frontend build in the existing CI group.
- Auth, navigation, API and user data contracts stay unchanged.
- `AuthenticatedAppRoute` receives the existing `MiniAppPage` child; it does not own or eagerly import the page.
- The locked runtime dependency set uses an `aiohttp` version with the CI-reported advisories fixed.

## Plan and checks

1. Build and run `perf:check` on `42a75a5f` and final application source `b516f9ca`.
2. Run typecheck, lint, CI-compatible Prettier and full Vitest on AFTER.
3. Run the existing performance-hardening Playwright scenario on both revisions with the same mocked fixtures, then run the bounded cold/warm route and transition profiler.
4. Re-read the exact PR checks and leave merge/deploy to the owner.
5. Run the locked Python dependency audit after the security refresh.
6. Keep production/field/device claims as `NO_DATA` where the source is unavailable.

Evidence and command results are in [the implementation report](../../docs/development/product-v11-03-frontend-performance-2026-10-19.md). The report records the remaining synthetic mobile private-route cost as a release residual rather than inventing field evidence.
