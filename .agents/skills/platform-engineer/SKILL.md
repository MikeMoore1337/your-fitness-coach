---
name: platform-engineer
description: >
  Build or change the reproducible path from commit to deployed environments: CI/CD, containers,
  configuration, secrets, supply-chain controls, health checks and infrastructure. Use for
  build/deploy/runtime platform concerns, not application business logic.
---

# platform-engineer

Build a reproducible path from commit to production.

## CI

Typically include lockfile-based dependency installation, lint, type checking, tests, build and security/dependency checks proportionate to risk. Do not hide failing checks.

## Supply chain

For production pipelines, where practical ensure reproducible/pinned dependencies, verifiable CI action/image/tool versions, risk-appropriate scanning, least-privileged and short-lived credentials where supported, and no secrets in build logs or artifacts. Add provenance/SBOM only when justified by requirements or threat modeling.

## Containers

Use a minimal base image, pinned/reproducible dependencies, non-root users when feasible, `.dockerignore`, no secrets in images, meaningful health/readiness and graceful shutdown.

## Environments

Separate configuration from code; keep secrets in environment/secret storage, never Git.

## Deployment

Consider migration order, backward compatibility, rolling/blue-green/canary only when justified, rollback, startup/readiness and graceful shutdown.

## Infrastructure as code

Keep code-managed infrastructure versioned and reviewable. Do not adopt Kubernetes or Terraform merely because they are fashionable.

## Project adaptation

Inspect the actual container/orchestration/deployment stack and CI/CD before proposing changes. Do not add Docker, Kubernetes, Terraform or another layer solely by convention. Production-affecting operations require an explicit request and repository-wide approval gates.

A new production revision reaches remote `master` only via a merged PR with required green `checks`. Direct/force pushes and deletion of `master` are forbidden. GitHub Actions validates PR/merge SHA, identifies changed paths and performs production deployment/smoke for application changes. History rewrites, manual production commands, infrastructure recovery and deployment of a SHA outside current merged `master` are exceptional operations needing separate owner approval, backup and preflight.
