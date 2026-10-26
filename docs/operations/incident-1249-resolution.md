# Incident #1249 — Production recovery and retirement (26 October 2026)

## Verified recovery

- Production stopped after attempted V12 deployment due to bot handoff/provenance failure.
- The verified baseline was recovered with [guarded restore run #40376876175](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/40376876175) (SUCCESS).
- All three app consumers, Alembic consistency, uniform revision and Telegram bot polling ownership were checked.
- [Master CI #40380287963](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/40380287963) and [production release #40380847479](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/40380847479) both finished SUCCESS for deployed revision b72270e64ef42e38ab922480028307a5a579413e.
- Related product issues #1228, #1229 and #1230 were closed after verified release.
- The apparent loss of account data was traced to a different login account; no database recovery or restoration was performed.

## Permanent operating rule

Production .env is a **Docker Compose environment file**, not a Bash script. Unquoted values such as a user-agent may be accepted by Compose while failing shell source or bash -n. Never evaluate, print, or shell-source production .env; use the documented Compose/deployment contract instead. The emergency raw-file syntax-repair workflow was intentionally not used to change real production credentials. Only rerun a rollback through the ordinary guarded Release production workflow after checking active revision, database compatibility and bot ownership. Do not bypass single-slot provenance gates.

## Retired incident access

The three incident-1249-*.yml workflows that could open owner-gated SSH sessions or recreate emergency baseline consumers, their two helper scripts, and their incident-specific tests are removed in the cleanup PR. Permanent regression tests now reject reintroduction of the retired workflow/script entry points or shell-sourcing .env in main release/rollback entry points.

History and logs remain available through Git and GitHub Actions; no production secrets, database records, runtime processes or backups are modified by this documentation/governance change. The cleanup is no-deploy and should not trigger another application rollout.
