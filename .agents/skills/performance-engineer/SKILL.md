---
name: performance-engineer
description: >
  Measure and improve backend, database and frontend performance using reproducible baselines,
  profiling, realistic load and field metrics. Use for material latency, throughput, resource,
  bundle or Core Web Vitals risks; do not optimize from intuition alone.
---

# performance-engineer

Do not optimize by intuition.

## Establish a baseline

Measure p50/p95/p99 latency, throughput, CPU, memory, query count/duration, bundle/loading metrics, startup and job duration as applicable. Profile the actual bottleneck.

## Backend

Check N+1 queries, plans, pools, serialization, blocking sync code in async flows, unbounded concurrency, inefficient retries, caching suitability and memory growth.

## Frontend

Check bundle, network waterfalls, LCP/INP/CLS, heavy JavaScript, images/fonts, render churn and virtualization when large lists justify it.

## Mobile Web/TMA

Measure Mobile Web and TMA separately for client-facing YFC flows:

- Initial/core-flow JavaScript, CSS and media cost.
- Low-end device main-thread blocking and memory.
- Keyboard/sheet/open-close stutter.
- Foreground resume and slow/unstable networks.
- Duplicate platform bundles.
- Eager charts/exercise media.
- Fixed/sticky layout work during viewport/safe-area changes.

Desktop localhost is not a sufficient baseline. Use task `50A` smoke and `references/MOBILE_TMA_ACCEPTANCE_MATRIX.md`, keeping browser mobile lab measurements separate from Telegram client data.

## Web performance budget

For public/user-facing web UI without an explicit project budget, use current Core Web Vitals good field thresholds at the 75th percentile, separately for mobile and desktop:

- LCP <= 2.5 s.
- INP <= 200 ms.
- CLS <= 0.1.

Lab measurements aid diagnosis, but never represent actual field experience. Report missing field data as a limitation rather than claiming localhost benchmarks measure production UX.

## Load

For critical services verify a realistic load profile, saturation, graceful degradation, dependency/rate limits and recovery after spikes. Repeat the same benchmark after changes and record the difference.

## Narrow external references

After baseline, use `../../references/external-quality/vercel/react-best-practices/SKILL.md` and/or `../../references/external-quality/ui-skills/fixing-motion-performance.md` for related React/motion concerns. Verify applicability before importing Next.js-specific advice into Vite.
