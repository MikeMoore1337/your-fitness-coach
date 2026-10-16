---
name: performance-engineer
description: >
  Measure and improve backend, database and frontend performance using reproducible baselines,
  profiling, realistic load and field metrics. Use for material latency, throughput, resource,
  bundle or Core Web Vitals risks; do not optimize from intuition alone.
---

# performance-engineer

Не оптимизируй по ощущениям.

## Сначала baseline

Определи измеримый показатель:

- p50/p95/p99 latency;
- throughput;
- CPU;
- memory;
- query count/time;
- bundle/load metrics;
- startup;
- job duration.

Профилируй bottleneck.

## Backend

Проверь:

- N+1;
- query plans;
- connection pools;
- serialization;
- sync blocking in async code;
- unbounded concurrency;
- inefficient retries;
- cache suitability;
- memory growth.

## Frontend

Проверь:

- bundle;
- network waterfall;
- LCP/INP/CLS;
- heavy JS;
- image/font loading;
- render churn;
- virtualization для больших списков при необходимости.

## Mobile Web/TMA performance

Для client-facing YFC flow измеряй отдельно Mobile Web и TMA:

- initial/core-flow JS/CSS/media cost;
- low-end device main-thread blocking и memory;
- keyboard/sheet/open-close jank;
- foreground resume;
- slow/unstable network;
- duplicate platform bundles;
- eager charts/exercise media;
- fixed/sticky layout work при viewport/safe-area events.

Не считай desktop localhost достаточным baseline. Используй task `50A` smoke и `references/MOBILE_TMA_ACCEPTANCE_MATRIX.md`. Telegram client performance и browser mobile lab data фиксируй отдельно.

## Web performance budget

Для публичного или пользовательского web-интерфейса, если проект не задаёт другой budget, используй
текущие Core Web Vitals "good" thresholds как ориентир для field data на 75-м перцентиле отдельно для
mobile и desktop:

- LCP <= 2.5 s;
- INP <= 200 ms;
- CLS <= 0.1.

Lab-метрики нужны для диагностики, но не подменяют реальные пользовательские данные. Если field data
ещё нет, зафиксируй это как ограничение, а не выдавай локальный benchmark за production experience.

## Нагрузка

Для критических сервисов проверь:

- realistic load profile;
- saturation point;
- graceful degradation;
- dependency limits;
- rate limits;
- recovery after spike.

После изменения повтори тот же benchmark и зафиксируй разницу.

## Внешние ссылки по узкому performance-scope

После baseline при React/motion проблеме используй
`../../references/external-quality/vercel/react-best-practices/SKILL.md` и/или
`../../references/external-quality/ui-skills/fixing-motion-performance.md`.
Не переносить Next.js-специфичные советы в Vite без технической проверки.
