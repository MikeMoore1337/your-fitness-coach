# Dependency updates and vulnerability alerts

No automated version-update PR bot is configured. Dependency changes are manual, reviewed as
ordinary pull requests, and subject to the repository's existing lockfile, CI and security gates.

## Repository policy

- `.github/dependabot.yml` is intentionally absent; Dependabot version-update configuration is not
  enabled.
- `.github/renovate.json` is intentionally absent; no repository integration is configured.
- `Dependabot alerts` may remain enabled for passive vulnerability visibility.
- `Dependabot security updates` and automatic security PRs remain disabled, so no automated
  dependency PR stream is created by this repository policy.
- Major dependency upgrades require explicit manual review.

## Python dependencies

Python dependencies are managed from the root `pyproject.toml`. Every dependency change must keep
`pyproject.toml` and `uv.lock` consistent and must preserve the pinned project policy in
`pyproject.toml`.

CI remains fail-closed: `uv sync --locked` rejects a stale or inconsistent `uv.lock`. Do not bypass
that check or regenerate the lockfile under a different Python/uv project policy.

For a development dependency, make the manifest and lockfile change together, then verify the
locked environment from the repository root:

```bash
uv add --group dev "<package>==<version-or-range>"
uv lock
uv sync --locked --no-default-groups --group dev
```

For an existing dependency whose declared range already permits the intended update, use the
repository's pinned uv version to refresh only that package and then run the same locked sync:

```bash
uv lock --upgrade-package <package>
uv sync --locked --no-default-groups --extra backend --extra bot --group dev
```

Review the resulting `pyproject.toml` and `uv.lock` diff together. A major upgrade needs explicit
human review of compatibility, security findings and affected CI/runtime paths.

## Frontend npm dependencies

Frontend dependency changes must keep `frontend/package.json` and
`frontend/package-lock.json` consistent. Use npm to update both files, then verify the exact
lockfile install and the existing frontend checks:

```bash
npm --prefix frontend install --save <package>@<version-or-range>
npm --prefix frontend ci
npm --prefix frontend run check
```

For a development-only package, use `--save-dev` instead of `--save`. Do not commit a
`package.json` change without its matching `package-lock.json` update, and do not replace `npm ci`
with an unlocked install in CI.

## Review and release

Every manual dependency PR must:

- explain the reason for the update and any major-version compatibility impact;
- preserve `uv.lock` or `package-lock.json` integrity as applicable;
- pass the relevant Python/frontend checks, dependency audit and security scans;
- receive explicit review for major upgrades or changes that affect runtime, CI or deployment.

The repository does not create a dependency dashboard or automated version-update schedule. GitHub
issues or alerts can be used for manual tracking, but they do not replace the lockfile and CI gates.
