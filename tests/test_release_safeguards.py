import ast
import json
import os
import re
import textwrap
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import cast

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
        "dependency_doc": (root / "docs" / "dependency-automation.md").read_text(encoding="utf-8"),
    }


def _embedded_function(workflow_text: str, name: str, **globals_: object) -> Callable[..., object]:
    match = re.search(
        r"(?ms)^[ \t]+exec python3 - <<'REMOTE_PYTHON'\r?\n"
        r"(?P<script>.*?)^[ \t]+REMOTE_PYTHON$",
        workflow_text,
    )
    assert match is not None
    tree = ast.parse(textwrap.dedent(match.group("script")))
    function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, object] = {"__builtins__": __builtins__, **globals_}
    exec(compile(module, "<embedded-capacity-probe>", "exec"), namespace)
    return cast(Callable[..., object], namespace[name])


def test_ci_runs_application_checks_without_controller_gates() -> None:
    ci = _sources()["ci"]

    assert "branches: [master]" in ci
    assert "branches: [dev" not in ci
    assert "if: github.event_name == 'pull_request'" in ci
    assert "task-provenance:" not in ci
    assert "review-contract:" not in ci
    assert "pull_request_review:" not in ci
    assert "merge-provenance:" not in ci
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

    for job_name in ("containers",):
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
    assert "branches: [master]" in deploy
    assert "sync-dev:" not in deploy
    assert "actions/create-github-app-token" not in deploy
    assert "deployment_contract.py refs" in deploy
    assert "bundle" in deploy.lower()
    assert "deployment_scope.py" in deploy
    assert "deploy=false" in deploy
    assert "if: needs.authorize.outputs.deploy == 'true'" in deploy
    assert "git fetch" not in deploy_script
    assert "git reset" not in deploy_script
    assert "git rev-parse" not in deploy_script
    assert ".git" not in deploy_script
    assert "scripts/zero_downtime_deploy.py" in deploy_script


def test_deploy_reads_active_revision_before_migration_and_rollout() -> None:
    deploy = _sources()["deploy"]

    assert "scripts/production_provenance.py" in deploy
    assert "python3 - snapshot --app-root" in deploy
    assert "Production provenance mismatch before transfer" in deploy
    assert "ACTIVE_REVISION: ${{ steps.migration.outputs.active_revision }}" in deploy
    assert "active_marker" in deploy
    assert "last-successful-revision" in deploy
    assert 'test -f \\"\\$active_marker\\"' in deploy
    assert 'install -d -m 700 \\"\\$(dirname \\"\\$active_marker\\")\\"' not in deploy


def test_manual_rollback_uses_native_actions_and_existing_production_safety() -> None:
    deploy = _sources()["deploy"]

    assert "operation:" in deploy
    assert "options: [deploy, repair, reconcile, rollback]" in deploy
    assert "rollback:" in deploy
    assert "owner-authorized rollback" in deploy
    assert "python3 scripts/zero_downtime_deploy.py rollback" in deploy
    assert "scripts/task_session.py" not in deploy
    assert "delivery owner" not in deploy


def test_manual_repair_is_native_ancestor_checked_and_reuses_single_slot_rollout() -> None:
    deploy = _sources()["deploy"]

    assert "if: needs.authorize.outputs.operation == 'repair'" in deploy
    assert 'git merge-base --is-ancestor "$DEPLOY_SHA" "$current_master"' in deploy
    assert "name: Repair known production release" in deploy
    assert "BASELINE_REVISION: 050bbd3f80aac0b8e84389fa3c4c28875df89066" in deploy
    assert "Read-only production repair preflight" in deploy
    assert "Verify target images and OCI provenance before transfer" in deploy
    assert "check_online_migrations.py" in deploy
    assert "DEPLOY_REPAIR_MODE=true" in deploy
    assert "DEPLOY_REPAIR_BASELINE_SHA" in deploy
    assert "single-slot" in deploy
    assert "Verify repaired production provenance" in deploy
    assert "services.bot.runtime_markers.telegram_polling_started" in deploy
    assert "last-successful-revision" in deploy
    assert "operation=reconcile" not in deploy
    assert "repair database" not in deploy.lower()
    assert "deployment.lock" not in deploy


def test_repair_preflight_uses_symbolic_alembic_revision_parser() -> None:
    deploy = _sources()["deploy"]

    assert "parse_alembic_revisions" in deploy
    assert "alembic_revisions_are_consistent" in deploy
    assert 're.findall(r"\\b[0-9a-f]{8,40}\\b"' not in deploy


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
        "RAM_AVAILABLE_MIN_MIB=",
        "RAM_AVAILABLE_AVG_MIB=",
        "RAM_AVAILABLE_MAX_MIB=",
        "DOCKER_TOTAL_MEMORY_USED_MIB=",
        "DOCKER_MEMORY_MAX_MIB=",
        "DOCKER_MEMORY_AVG_MIB=",
        "POSTGRES_MAX_CONNECTIONS=",
        "POSTGRES_CURRENT_CONNECTIONS=",
        "POSTGRES_CONNECTION_HEADROOM=",
        "PORT_5678=",
        "BACKEND_MODE=",
        "WORKER_MODE=",
        "BOT_MODE=",
        "HISTORICAL_CAPACITY=",
        "HISTORICAL_SAMPLE_COUNT=",
        "HISTORICAL_CPU_COUNT_MIN=",
        "HISTORICAL_RAM_AVAILABLE_MIN_MIB=",
        "HISTORICAL_DISK_FREE_MIN_MIB=",
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
    for legacy_field in (
        "RAM_AVAILABLE_MIN=",
        "RAM_AVAILABLE_AVG=",
        "RAM_AVAILABLE_MAX=",
    ):
        assert legacy_field not in workflow_text


def test_capacity_audit_preserves_docker_min_avg_max_semantics() -> None:
    workflow_text = _sources()["capacity_audit"]
    aggregate_mib = _embedded_function(workflow_text, "aggregate_mib")
    samples_mib = [400, 450, 600, 500, 550, 480]

    assert aggregate_mib([value * 1024**2 for value in samples_mib], 1024**2) == (
        "400",
        "497",
        "600",
    )
    assert re.search(
        r"docker_memory_avg_mib,\s*docker_memory_max_mib\s*=\s*aggregate_mib\(\s*"
        r"docker_memory_samples,\s*1024\*\*2\s*\)",
        workflow_text,
    )
    assert 'f"DOCKER_MEMORY_MAX_MIB={docker_memory_max_mib}"' in workflow_text
    assert 'f"DOCKER_MEMORY_AVG_MIB={docker_memory_avg_mib}"' in workflow_text


def test_capacity_audit_historical_metrics_are_bounded_allowlisted_and_worst_case(
    tmp_path: Path,
) -> None:
    workflow_text = _sources()["capacity_audit"]
    historical_capacity_metrics = _embedded_function(
        workflow_text,
        "historical_capacity_metrics",
        DEPLOYMENT_ROOT=tmp_path,
        json=json,
    )
    summaries = (
        {"capacity": {"cpu_count": 2, "memory_available_mb": 1600, "disk_available_mb": 5000}},
        {"capacity": {"cpu_count": 2, "memory_available_mb": 1200, "disk_available_mb": 4300}},
        {"capacity": {"cpu_count": 2, "memory_available_mb": 1450, "disk_available_mb": 4700}},
        {"capacity": {"cpu_count": 2, "memory_available_mb": 1500}},
        {"capacity": {"cpu_count": True, "memory_available_mb": 1000, "disk_available_mb": 4000}},
        {
            "capacity": {
                "cpu_count": 99,
                "memory_available_mb": 1,
                "disk_available_mb": 1,
                "secret": "must-not-be-read-or-printed",
            },
            "metadata": {"revision": "must-not-be-read-or-printed"},
        },
    )
    for index, summary in enumerate(summaries):
        summary_path = tmp_path / f"deployment-{index}" / "summary.json"
        summary_path.parent.mkdir()
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        timestamp = 100 + len(summaries) - index
        os.utime(summary_path, (timestamp, timestamp))

    assert historical_capacity_metrics() == ("AVAILABLE", "3", "2", "1200", "4300")
    assert "must-not-be-read-or-printed" not in str(historical_capacity_metrics())
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    unavailable_metrics = _embedded_function(
        workflow_text,
        "historical_capacity_metrics",
        DEPLOYMENT_ROOT=empty_root,
        json=json,
    )
    assert unavailable_metrics() == (
        "UNAVAILABLE",
        "0",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "UNAVAILABLE",
    )
    assert 'fields = ("cpu_count", "memory_available_mb", "disk_available_mb")' in workflow_text
    assert "records.append(tuple(capacity[field] for field in fields))" in workflow_text
    assert "str(min(record[0] for record in records))" in workflow_text
    assert "str(min(record[1] for record in records))" in workflow_text
    assert "str(min(record[2] for record in records))" in workflow_text


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


def test_delivery_contract_is_github_flow_and_native_concurrency() -> None:
    sources = _sources()
    deploy = yaml.safe_load(sources["deploy"])
    assert deploy["concurrency"] == {"group": "production", "cancel-in-progress": False}
    assert "GitHub Issue" in sources["agents"]
    assert "protected `master`" in sources["global_rules"]
    assert "local state machine" in sources["lifecycle"]


def test_production_workflow_uses_native_concurrency() -> None:
    workflow = yaml.safe_load(_sources()["deploy"])
    assert workflow["concurrency"]["group"] == "production"
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_controller_entrypoints_and_host_lock_are_removed() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "scripts/task_session.py",
        "scripts/run_task_delivery.py",
        "scripts/controller_v2.py",
        "scripts/issue_workflow.py",
        "scripts/worker_guard.py",
    ):
        assert not (root / relative).exists(), relative
    deploy = _sources()["deploy"]
    rollout = (root / "scripts/zero_downtime_deploy.py").read_text(encoding="utf-8")
    assert "task_session.py" not in deploy
    assert "classify-controller-release" not in deploy
    assert "_deployment_lock" not in rollout
    assert "import fcntl" not in rollout


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
