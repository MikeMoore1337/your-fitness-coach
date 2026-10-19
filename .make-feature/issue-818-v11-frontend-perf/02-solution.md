# Make Feature solution — Product V11-03 / Issue #818

Status: NEEDS_WORK pending final exact-head required CI after reduced-motion test correction; the remaining runtime threshold is a
proposed diagnostic convention, not an owner approval.
Context: existing Draft PR #1126; final application code `415b4e720fe0bb1c51784c40f43a3d9558fd92bd`.

## Confirmed cause and selected fix

The PR-before-fix `/app` route loaded the authenticated boundary first and only then started
the `MiniAppPage` dynamic import. The 10-run mobile profile reproduced the effect for Today
(`3,113 -> 3,482 ms` p50) and Programs (`2,979 -> 3,096 ms` p50). Auth checks and API counts
were unchanged.

The selected fix adds one private-only `AuthenticatedAppPage` lazy entry. It composes the
existing `AuthenticatedRoute`, `AuthenticatedAppRoute` and `MiniAppPage`, allowing the auth
dependencies and the app page graph to start together. It does not bypass AuthGate, show
private data early, move private code to public entry, or alter route decisions.

The isolated private-only preload experiment was rejected: it started more requests but did
not improve Today under the throttled connection. No Query, render, router, media or backend
change was justified.

## Contract

- Public routes do not load demo-only session code or authenticated route internals eagerly.
- `/app` keeps AuthProvider, AuthGate, OnboardingGate and trainer-intent behavior.
- Telegram `/demo` cleanup remains before React renders.
- Exercise guide video keeps its approved HD source/poster and visibility behavior.
- `perf:check` remains strict at `entryJsGzip: 96_000`.
- CoachPage remains `186,590 raw / 45,800 gzip`; no CoachPage graph regression returned.
- Existing API, authorization, navigation, TMA and user-data contracts stay unchanged.

## Evidence and checks

The exact 10-run cold, five-run warm, five-run transition and isolated experiment results are
in [the implementation report](../../../docs/development/product-v11-03-frontend-performance-2026-10-19.md).
The opt-in profilers are `frontend/tests/e2e/*profile.ts`; the ordinary E2E glob does not run
them. Exact-head GitHub checks must be re-read after the final documentation commit.
The previous PR-head evidence run [39324048719](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39324048719)
failed only the unchanged reduced-motion assertion (`progress-experience.spec.ts:2992`, `0s`
vs `1e-05s`). The selected continuation fix parses the existing CSS contract numerically,
keeps a `0.01ms` upper bound, rejects unknown units and visible durations, and adds regression
cases for `0s`, `1e-05s`, `0.01ms`, `150ms` and malformed values. It does not change production
CSS. Final exact-head CI is pending after the documentation commit.
