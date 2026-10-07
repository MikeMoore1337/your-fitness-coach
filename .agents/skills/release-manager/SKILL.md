---
name: release-manager
description: >
  Prepare and verify a production release: migration order, rollout, smoke checks, success
  criteria, monitoring, rollback or forward-fix and post-deploy validation. Use for release
  readiness or deployment planning; actual production deployment requires explicit authorization.
---

# release-manager

Перед релизом собери release checklist, соответствующий типу продукта.

Проверь:

- build artifact воспроизводим;
- нужные tests/checks green;
- migrations проверены;
- configuration/secrets готовы;
- backward compatibility;
- external dependencies;
- feature flags, если есть;
- rollback/forward-fix path;
- backup, если изменение может повредить данные;
- smoke tests;
- monitoring/alerts готовы наблюдать изменение.

## Release success criteria

До deployment определи несколько проверяемых сигналов успешного релиза, соответствующих изменению:

- критический user flow проходит;
- error rate/latency не деградировали существенно;
- migration/background processing завершены;
- нет всплеска client/server exceptions;
- product-critical success signal работает, если он инструментирован.

Не ограничивай success criteria фразой "deployment succeeded".

После deployment:

- health/readiness;
- error rate;
- latency;
- critical user flow;
- background jobs/queues;
- migration completion;
- новые логи/метрики/traces;
- release success criteria и product-critical signals, если они определены.

Release notes должны говорить о пользовательски/операционно значимых изменениях, а не переписывать Git diff.
## Адаптация к проекту

Собирай порядок релиза из фактических компонентов проекта: services/apps, migrations, generated
contracts, background jobs, feature flags и external dependencies. Не предполагай конкретную
схему deployment. Авторизация production deployment определяется repository-wide правилами;
подготовка и локальная проверка сами по себе её не создают. В этом репозитории новая production
revision входит в remote `master` только через merged PR с green check `checks`. GitHub Actions
проверяет merge SHA, определяет changed-path scope и запускает production workflow для application
changes. Direct/force push, history rewrite и manual production actions вне этого normal path
требуют отдельного owner approval, backup и preflight.
