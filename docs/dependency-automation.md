# Dependency automation

Routine dependency updates are owned by Renovate. Dependabot version-update configuration is intentionally absent.

## Repository contract

- Renovate branches use `renovate/`.
- Python dependencies are managed from the root `pyproject.toml` with `uv.lock` as the required lockfile artifact.
- Renovate's PEP 621 manager must update `pyproject.toml` and `uv.lock` together.
- CI stays fail-closed: any stale `uv.lock` fails `uv sync --locked` / `uv lock --check`.
- npm PRs must pass `npm ci`, typecheck, lint, unit tests and the routed frontend regression lanes.
- Major dependency upgrades never auto-merge and require explicit approval in the Renovate Dependency Dashboard.
- Minor, patch, pin and digest updates may auto-merge only after the repository's required checks are green.
- Security fixes are surfaced by Renovate and never auto-merge.

## Update cadence

- Python / uv: Monday.
- npm frontend: Tuesday.
- Docker: Wednesday.
- GitHub Actions: Thursday.
- uv lockfile maintenance: Monday.

A 7-day minimum release age is used for the scheduled ecosystems. This avoids immediately consuming freshly published packages and keeps uv's resolver behavior aligned with the bot policy.

## One-time GitHub setup

The repository configuration file alone cannot install a GitHub App or change Advanced Security account settings. An owner must perform these one-time settings:

1. Install the Mend Renovate GitHub App for `MikeMoore1337/your-fitness-coach`.
2. In **Settings -> Security -> Advanced Security**, keep **Dependency graph** and **Dependabot alerts** enabled.
3. Disable **Dependabot security updates** so GitHub does not create a second, competing dependency PR stream. Alerts stay enabled because Renovate can consume them.
4. Confirm that the Renovate App has read access to Dependabot alerts and write access required to create/update branches and pull requests.

Repository-native GitHub auto-merge is not required. `platformAutomerge` is disabled, so Renovate itself merges eligible non-major PRs only after it observes required status checks passing.

## Recovery

If a Renovate PR fails:

- do not bypass `checks`;
- inspect the failing dependency lane;
- if the update is incompatible, close it or keep it pending in the Dependency Dashboard;
- never regenerate `uv.lock` with a different project policy just to make CI green.

If Renovate stops creating PRs, first verify the GitHub App installation/permissions and the Dependency Dashboard issue before changing repository policy.
