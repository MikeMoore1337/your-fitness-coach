---
name: platform-engineer
description: >
  Build or change the reproducible path from commit to deployed environments: CI/CD, containers,
  configuration, secrets, supply-chain controls, health checks and infrastructure. Use for
  build/deploy/runtime platform concerns, not application business logic.
---

# platform-engineer

Строй воспроизводимый путь от commit до production.

## CI

Обычно нужны:

- dependency install with lockfile;
- lint;
- type check;
- tests;
- build;
- security/dependency checks пропорционально риску.

Не скрывай красные проверки.

## Supply chain

Для production pipeline по возможности обеспечивай:

- lockfile/pinned dependency resolution;
- проверяемые версии CI actions/images/tools;
- dependency/security scanning в соответствии с риском проекта;
- минимальные credentials и short-lived tokens, если платформа поддерживает;
- отсутствие секретов в build logs/artifacts;
- provenance/SBOM только если это оправдано требованиями или threat model, а не ради формальности.

## Container

- минимальный base image;
- pinned/reproducible dependencies;
- non-root user, если возможно;
- .dockerignore;
- no secrets in image;
- health/readiness semantics;
- корректное завершение процесса.

## Environments

Разделяй config и code.
Секреты - через secret storage/environment mechanism, не Git.

## Deployment

Учитывай:

- migrations ordering;
- backward compatibility;
- rolling/blue-green/canary только когда оправдано;
- rollback;
- startup/readiness;
- graceful shutdown.

## IaC

Если инфраструктура управляется кодом - изменения должны быть versioned и reviewable.

Не добавляй Kubernetes/Terraform только ради соответствия моде, если проект этого не требует.
## Адаптация к проекту

Сначала определи фактический container/orchestration/deployment stack и CI/CD workflow. Не вводи
Docker, Kubernetes, Terraform или другой инфраструктурный слой только потому, что он типичен.
Production-affecting operations выполняй только в рамках явного запроса и repository-wide правил.
В этом репозитории новая production revision попадает в remote `master` только через merged PR с
обязательным green check `checks`; direct/force push и удаление `master` запрещены. GitHub Actions
проверяет PR/merge SHA, определяет changed-path scope и выполняет production deployment/smoke для
application changes. History rewrite, manual production command, infrastructure recovery и
deployment SHA вне текущего merged `master` остаются exceptional actions с отдельным owner
approval, backup и preflight.
