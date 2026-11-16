---
name: python-engineer
description: >
  Implement or refactor Python code using the repository's supported Python version, typing,
  tests, linting, async conventions and project tooling. Use whenever Python source is materially
  changed; pair with domain-specific skills when the task is primarily backend, data or QA.
---

# python-engineer

Use this skill when changing Python code.

## Inspect the project first

Identify the supported Python version, package/dependency manager, `pyproject.toml` and tool configurations, test runner/project wrappers, lint/format/type-check tools, async/sync model and module/package conventions.

Do not replace established project commands with familiar generic commands when wrappers/scripts already exist.

## Implementation

- Use features supported by the project's actual Python version.
- Preserve meaningful typing; do not widen to `Any` without justification.
- Prefer explicit error handling and deterministic resource release.
- Do not block an async event loop with synchronous I/O without a concrete reason.
- Follow existing framework/ORM/library patterns instead of parallel abstractions.
- Do not add dependencies when the current stack reasonably supports the requirement.

## Verification

Run existing project commands. At each stage use the smallest relevant checks; before completing a substantial Python task, run broader checks covering affected areas.

Typical configured checks include unit/integration tests, lint, formatting, static type checking and package/build verification.

Never report a check as passed unless the command actually ran.

## Artifacts

Follow repository-wide rules for caches, coverage, test artifacts and temporary files. Do not invent new scratch directories at repository root when an artifact location already exists.
