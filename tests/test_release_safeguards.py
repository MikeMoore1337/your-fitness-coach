import re
import tomllib
from pathlib import Path

import yaml


def _sources() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    return {
        "agents": (root / "AGENTS.md").read_text(encoding="utf-8"),
        "global_rules": (root / "codex-backlog" / "GLOBAL_RULES.md").read_text(encoding="utf-8"),
        "lifecycle": (root / "codex-backlog" / "TASK_EXECUTION_LIFECYCLE.md").read_text(
            encoding="utf-8"
        ),
        "ci": (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
        "deploy": (root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8"),
        "capacity_audit": (
            root / ".github" / "workflows" / "production-capacity-audit.yml"
        ).read_text(encoding="utf-8"),
        "controller": (root / "scripts" / "task_session.py").read_text(encoding="utf-8"),
        "launcher": (root / "scripts" / "run_task_delivery.py").read_text(encoding="utf-8"),
        "dependency_doc": (root / "docs" / "dependency-automation.md").read_text(encoding="utf-8"),
    }


def test_ci_runs_full_regression_on_task_pr_and_only_provenance_on_master_push() -> None:
    ci = _sources()["ci"]

    assert "branches: [master]" in ci
    assert "branches: [dev" not in ci
    assert "if: github.event_name == 'pull_request'" in ci
    assert "task-provenance:" in ci
    assert "review-contract:" not in ci
    assert "pull_request_review:" not in ci
    assert "merge-provenance:" in ci
    assert "Validate task provenance or trusted dependency bot identity" in ci
    assert "TASK_PROVENANCE_RESULT: ${{ needs.task-provenance.result }}" in ci
    assert "CODEQL_SECURITY_RESULT: ${{ needs.codeql-security.result }}" in ci
    assert "SECURITY_AUDIT_RESULT: ${{ needs.security-audit.result }}" in ci
    assert "codeql-security:" in ci
    assert "security-audit:" in ci
    assert "github/codeql-action/init@v4" in ci
    assert "github/codeql-action/analyze@v4" in ci
    assert "python3 scripts/codeql_sarif_gate.py" in ci
    assert "scanners: vuln,misconfig,secret" in ci
    assert "openai/codex-action" not in ci
    assert "python scripts/ci_contract.py run-group" in ci
    assert "frontend-checks" in ci
    assert "frontend-e2e" in ci
    assert "python-tests" in ci
    assert "migrated-stack" in ci
    assert "dependency-audit" in ci
    assert "if: github.event_name == 'push' && github.ref == 'refs/heads/master'" in ci
    assert "release-sequence:" not in ci
    assert "verify-dev-provenance" not in ci
    assert "sync-dev" not in ci
    assert "dev-release" not in ci


def test_python_script_ci_jobs_pin_supported_python_runtime() -> None:
    workflow = yaml.safe_load(_sources()["ci"])
    jobs = workflow["jobs"]

    for job_name in ("task-provenance", "merge-provenance", "containers"):
        setup_python = next(
            step
            for step in jobs[job_name]["steps"]
            if step.get("uses") == "actions/setup-python@v5"
        )
        assert setup_python["with"]["python-version"] == "3.14"


def test_dependency_automation_policy_is_manual_and_fail_closed() -> None:
    sources = _sources()

    root = Path(__file__).resolve().parents[1]
    assert not (root / ".github" / "dependabot.yml").exists()
    assert not (root / ".github" / "renovate.json").exists()
    assert (root / "docs" / "dependency-automation.md").is_file()

    dependency_doc = sources["dependency_doc"]
    assert "No automated version-update PR bot is configured." in dependency_doc
    assert ".github/dependabot.yml" in dependency_doc
    assert ".github/renovate.json" in dependency_doc
    assert "Dependabot alerts" in dependency_doc
    assert "Dependabot security updates" in dependency_doc
    assert "automatic security PRs" in dependency_doc
    assert "Major dependency upgrades require explicit manual review." in dependency_doc
    assert "uv.lock" in dependency_doc
    assert "uv sync --locked" in dependency_doc
    assert "npm ci" in dependency_doc

    uv_lock = root / "uv.lock"
    assert uv_lock.is_file()
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["tool"]["uv"]["package"] is False
    assert project["tool"]["uv"]["default-groups"] == []
    assert project["tool"]["uv"]["required-version"] == ">=0.11.32,<0.12"
    assert {"backend", "bot"} <= set(project["project"]["optional-dependencies"])
    dev = project["dependency-groups"]["dev"]
    for package in ("pytest>=9.1", "mypy>=2.3", "ruff>=0.16.1", "pre-commit>=4.6"):
        assert package in dev
    for legacy in (
        root / "backend" / "requirements.in",
        root / "backend" / "requirements-runtime.txt",
        root / "backend" / "requirements-dev.in",
        root / "backend" / "requirements-dev.txt",
        root / "backend" / "requirements-scheduled-report.in",
        root / "backend" / "requirements-scheduled-report.txt",
        root / "bot" / "requirements.in",
        root / "bot" / "requirements.txt",
    ):
        assert not legacy.exists()


def test_deploy_is_master_only_immutable_bundle_flow_without_vps_git_checkout() -> None:
    sources = _sources()
    deploy = sources["deploy"]
    deploy_script = (
        Path(__file__).resolve().parents[1] / "scripts" / "deploy_production.sh"
    ).read_text(encoding="utf-8")

    assert "workflows: [CI]" in deploy
    assert "branches:" in deploy
    assert "- master" in deploy
    assert "sync-dev:" not in deploy
    assert "actions/create-github-app-token" not in deploy
    assert "deployment_contract.py refs" in deploy
    assert "bundle" in deploy.lower()
    assert "controller-only governance merge" in deploy
    assert "deploy=false" in deploy
    assert "if: needs.authorize.outputs.deploy == 'true'" in deploy
    assert "git fetch" not in deploy_script
    assert "git reset" not in deploy_script
    assert "git rev-parse" not in deploy_script
    assert ".git" not in deploy_script
    assert "scripts/zero_downtime_deploy.py" in deploy_script


def test_controller_release_skip_uses_exact_provenance_and_full_changed_file_inventory() -> None:
    sources = _sources()
    deploy = sources["deploy"]
    controller = sources["controller"]
    docs = Path(__file__).resolve().parents[1] / "docs" / "task-branch-integration.md"

    assert "workflow_run.head_sha" in deploy
    assert "actions/checkout@v4" in deploy
    assert "ref: ${{ env.DEPLOY_SHA }}" in deploy
    assert "classify-controller-release" in deploy
    assert "CONTROLLER_ROWS" not in deploy
    assert "codex/controller-[a-z0-9-]+" not in deploy
    assert "controller-source" in deploy
    assert "git rev-list --first-parent --no-merges" in deploy
    assert "git rev-list --first-parent --merges --reverse" in deploy
    assert "workflow_runs" in deploy
    assert "pull_requests[]" in deploy
    assert "/pulls/$pr_number" in deploy
    assert "commits/$pr_head_sha/check-runs" in deploy
    assert '"Deploy immutable tested bundle"' in deploy
    assert '"skipped"' in deploy
    assert "CONTROLLER_ALLOWED_PATHS" in controller
    assert "pulls/{number}/files?per_page=100&page={page}" in controller
    assert "len(files) != declared_count" in controller
    assert "defaulting to application deployment" in controller
    assert "verified provenance + exact changed-file allowlist" in docs.read_text(encoding="utf-8")
    assert "Task-bound controller change" in docs.read_text(encoding="utf-8")


def test_deploy_recovers_legacy_revision_before_migration_and_rollout() -> None:
    deploy = _sources()["deploy"]

    assert "latest_summary" in deploy
    assert "com.docker.compose.service=\\$service" in deploy
    assert "org.opencontainers.image.revision" in deploy
    assert "ACTIVE_REVISION: ${{ steps.migration.outputs.active_revision }}" in deploy
    assert "active_marker" in deploy
    assert "last-successful-revision" in deploy
    assert 'if [ -f \\"\\$active_marker\\" ]; then' in deploy
    assert 'install -d -m 700 \\"\\$(dirname \\"\\$active_marker\\")\\"' in deploy


def test_deploy_bounds_transient_production_ssh_failures() -> None:
    deploy = _sources()["deploy"]

    assert "for attempt in 1 2 3; do" in deploy
    assert "ConnectTimeout=10" in deploy
    assert "ConnectionAttempts=1" in deploy
    assert "Unable to read active production revision after 3 SSH attempts" in deploy
    assert 'sleep "$delay"' in deploy


def test_capacity_audit_is_manual_owner_only_and_uses_strict_ssh() -> None:
    workflow_text = _sources()["capacity_audit"]
    workflow = yaml.safe_load(workflow_text)

    assert re.search(r"(?m)^on:\s*$", workflow_text)
    assert re.search(r"(?m)^\s+workflow_dispatch:\s*$", workflow_text)
    assert not re.search(r"(?m)^\s+(push|pull_request|workflow_run|schedule):", workflow_text)
    assert workflow["permissions"] == {"contents": "read"}
    assert "owner-gate:" in workflow_text
    assert "if: needs.owner-gate.result == 'success'" in workflow_text
    assert "environment: production" in workflow_text
    assert workflow["jobs"]["audit"]["timeout-minutes"] == 10
    assert "uses:" not in workflow_text
    owner_gate = workflow_text.split("  audit:", 1)[0]
    assert "ssh" not in owner_gate.lower()
    assert "PROD_SSH_KEY" not in owner_gate
    assert "refs/heads/master" in owner_gate
    assert "PROD_HOST: 77.91.90.171" in workflow_text
    assert 'PROD_PORT: "1337"' in workflow_text
    assert "PROD_USER: yfc-deploy" in workflow_text
    assert "PROD_PATH: /srv/yfc/fit-mini-app" in workflow_text
    for option in (
        "BatchMode=yes",
        "IdentitiesOnly=yes",
        "StrictHostKeyChecking=yes",
        "ConnectTimeout=10",
        "ConnectionAttempts=1",
        "UserKnownHostsFile=",
        "IdentityFile=",
    ):
        assert option in workflow_text
    assert "StrictHostKeyChecking=no" not in workflow_text
    assert "ssh-keyscan" not in workflow_text


def test_capacity_audit_has_bounded_safe_output_and_no_production_mutation_path() -> None:
    workflow_text = _sources()["capacity_audit"]

    for output in (
        "PRODUCTION_CAPACITY_PROBE=PASS",
        "CPU_COUNT=",
        "ARCH=",
        "RAM_AVAILABLE_MIN=",
        "RAM_AVAILABLE_AVG=",
        "RAM_AVAILABLE_MAX=",
        "DOCKER_TOTAL_MEMORY_USED_MIB=",
        "DOCKER_MEMORY_MAX_MIB=",
        "POSTGRES_MAX_CONNECTIONS=",
        "POSTGRES_CURRENT_CONNECTIONS=",
        "POSTGRES_CONNECTION_HEADROOM=",
        "PORT_5678=",
        "BACKEND_MODE=",
        "WORKER_MODE=",
        "BOT_MODE=",
        "HISTORICAL_CAPACITY=",
        "NO_PRODUCTION_MUTATIONS=true",
    ):
        assert output in workflow_text

    for forbidden in (
        "env\n",
        "printenv",
        "docker compose",
        "docker pull",
        "docker build",
        "docker prune",
        "docker kill",
        "docker stop",
        "docker rm",
        "docker logs",
        "hostname",
        "ip addr",
        "ifconfig",
        ".NetworkSettings",
        ".Mounts",
        "CREATE DATABASE",
        "CREATE ROLE",
        "ALTER ROLE",
        "GRANT ",
        "REVOKE ",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "DROP ",
        "TRUNCATE ",
    ):
        assert forbidden not in workflow_text

    assert '"inspect",' in workflow_text
    assert '"--format",\n                          "{{.HostConfig.Memory}}",' in workflow_text
    assert '"stats",' in workflow_text
    assert '"--no-stream",' in workflow_text
    assert "for sample_index in range(6)" in workflow_text
    assert "time.sleep(10)" in workflow_text
    assert "SELECT 'version_major='" in workflow_text
    assert "SELECT 'current_connections='" in workflow_text
    assert "POSTGRES_USER" not in workflow_text
    assert "POSTGRES_DB" not in workflow_text
    assert 'DEPLOYMENT_ROOT.glob("*/summary.json")' in workflow_text
    assert ")[:5]" in workflow_text


def test_capacity_audit_cleans_ephemeral_ssh_material_on_every_exit() -> None:
    workflow_text = _sources()["capacity_audit"]

    cleanup_start = workflow_text.index("- name: Remove ephemeral SSH material")
    cleanup = workflow_text[cleanup_start:]
    assert "if: always()" in cleanup
    assert 'shred -u "$SSH_DIR/id_ed25519" "$SSH_DIR/known_hosts"' in cleanup
    assert 'rm -rf -- "$SSH_DIR"' in cleanup
    assert (
        'rm -f -- "$RUNNER_TEMP/yfc-capacity-probe.sh" "$RUNNER_TEMP/yfc-capacity-ssh.err"'
        in cleanup
    )
    assert 'printf \'%s\\n\' "$PROD_SSH_KEY" > "$ssh_dir/id_ed25519"' in workflow_text
    assert 'printf \'%s\\n\' "$PROD_SSH_KNOWN_HOSTS" > "$ssh_dir/known_hosts"' in workflow_text


def test_delivery_contract_is_master_only_and_github_gate_driven() -> None:
    sources = _sources()
    controller = sources["controller"]
    launcher = sources["launcher"]

    assert 'TARGET_BASE_BRANCH = "master"' in controller
    assert "base_origin_master_sha" in controller
    assert "delivery_anchor" in controller
    assert "PRE_PUSH_CI_PASS" not in controller
    assert "delivery_generation" not in controller
    assert "local_evidence" not in controller
    assert "production-success" in controller
    assert '"ready-for-delivery"' in controller
    assert "delivery.json" in controller
    assert "refresh_for_delivery" in controller
    assert "GitHub" in controller or "github" in controller
    assert "resolve-recovery" in controller
    assert "owner_authorize" in controller
    assert "request_codex_review" not in controller
    assert "validate_codex_review" not in controller
    assert "CODEX_REVIEW_MAX_ROUNDS" not in controller
    assert "review_contract = validate_pull_request_review_contract" not in controller
    assert "validate-pr-review" not in launcher
    assert "--continue-queue" in launcher
    assert "enqueue_integration" not in controller
    assert "release_freeze" not in controller
    assert "verify_dev_provenance" not in controller
    assert "canonical_dev_worktree" not in controller
    assert '"--owner-launch"' in launcher
    assert '"--approve-for-me"' in launcher
    assert "Do not merge" in controller
    assert "Codex Code Review отключён" in launcher
    assert "request-codex-review" not in launcher
    assert "validate-codex-review" not in launcher
    assert "Не запускай следующую product task" in launcher


def test_policy_docs_remove_dev_from_normal_delivery_and_keep_human_gates() -> None:
    sources = _sources()
    agents = sources["agents"]
    global_rules = sources["global_rules"]
    lifecycle = sources["lifecycle"]

    assert "AUTO_RELEASE_ELIGIBLE" in agents
    assert "AUTO_RELEASE_ELIGIBLE" in global_rules
    assert "AUTO_RELEASE_ELIGIBLE" in lifecycle
    assert "Direct push в `master` запрещён" in global_rules
    assert "required check `checks`" in lifecycle
    assert "PR master" in lifecycle
    assert "implementation lane" in lifecycle
    assert "delivery lane" in lifecycle
    assert "Busy delivery/CI/production" in lifecycle
    assert "Обычная task без `concurrency`" in lifecycle
    assert "implementation exclusion" in lifecycle
    assert "independent-write" in global_rules
    assert "active `exclusive-write` несовместим" not in global_rules
    assert "fast-forward/sync `dev`" not in lifecycle
    assert "serial merge в `dev`" not in global_rules
    assert "явно обязательный owner checkpoint/approve, human/device evidence" in lifecycle
    assert "failure/rollback/manual-intervention verdict" in lifecycle.lower()


def test_existing_compact_and_slot_contracts_remain_intact() -> None:
    root = Path(__file__).resolve().parents[1]
    plain_language = (root / "codex-backlog" / "PLAIN_LANGUAGE_UX.md").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    edge = (root / "deploy" / "Caddyfile.edge").read_text(encoding="utf-8")
    orchestrator = (root / "scripts" / "zero_downtime_deploy.py").read_text(encoding="utf-8")

    assert "COMPACT_FIRST_UX_CONTRACT.md" in plain_language
    assert "backend-blue:" in compose and "backend-green:" in compose
    assert "worker-blue:" in compose and "worker-green:" in compose
    assert "bot-blue:" in compose and "bot-green:" in compose
    assert "edge_config:/config" in compose
    assert "handle_response @asset_missing" in edge
    assert "lb_retries" not in edge
    assert orchestrator.index('"validate"') < orchestrator.index('"reload"')


def test_edge_serves_canonical_robots_without_backend_dependency() -> None:
    root = Path(__file__).resolve().parents[1]
    edge = (root / "deploy" / "Caddyfile.edge").read_text(encoding="utf-8")

    assert "@robots path /robots.txt" in edge
    assert 'header Cache-Control "public, max-age=3600"' in edge
    assert 'header Content-Type "text/plain; charset=utf-8"' in edge
    for directive in (
        "User-agent: *",
        "Allow: /",
        "Allow: /api/v1/public/",
        "Disallow: /api/",
        "Sitemap: https://your-fitness-coach.ru/sitemap.xml",
    ):
        assert directive in edge
    assert "respond <<ROBOTS" in edge
    assert "ROBOTS 200" in edge
