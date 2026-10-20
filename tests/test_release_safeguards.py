import ast
import json
import os
import re
import textwrap
import tomllib
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
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
    assert "options: [deploy, repair, verify, reconcile, rollback]" in deploy
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


def test_manual_verify_is_read_only_and_runs_provenance_and_smoke() -> None:
    deploy = _sources()["deploy"]
    verify = deploy.split("  verify:\n", 1)[1].split("  reconcile:\n", 1)[0]

    assert "if: needs.authorize.outputs.operation == 'verify'" in verify
    assert "ref: ${{ needs.authorize.outputs.current_master }}" in verify
    assert "python3 - verify --app-root" in verify
    assert "python scripts/check_deployment.py" in verify
    assert "python scripts/check_seo_surface.py" in verify
    assert "VERIFY_MUTATION=false" in verify
    for forbidden in (
        "deploy_production.sh",
        "zero_downtime_deploy.py",
        "docker compose",
        "python3 - reconcile",
        "alembic upgrade",
    ):
        assert forbidden not in verify


def test_manual_repair_always_executes_fresh_current_tooling() -> None:
    deploy = _sources()["deploy"]
    repair = deploy.split("  repair:\n", 1)[1].split("  reconcile:\n", 1)[0]

    assert "TOOLING_REVISION: ${{ needs.authorize.outputs.current_master }}" in repair
    assert "ref: ${{ needs.authorize.outputs.current_master }}" in repair
    assert 'git archive --format=tar "$REVISION"' in repair
    assert 'git archive --format=tar "$TOOLING_REVISION"' in repair
    assert repair.index('git archive --format=tar "$REVISION"') < repair.index(
        'git archive --format=tar "$TOOLING_REVISION"'
    )
    for path in (
        "scripts/deploy_production.sh",
        "scripts/zero_downtime_deploy.py",
        "scripts/production_host_cleanup.py",
        "scripts/check_online_migrations.py",
        "scripts/continuous_deployment_probe.py",
        "scripts/db_maintenance.py",
        "scripts/check_deployment.py",
        "scripts/check_seo_surface.py",
    ):
        assert path in repair
    assert "REPAIR_TARGET_REVISION=$REVISION" in repair
    assert "REPAIR_TOOLING_REVISION=$TOOLING_REVISION" in repair
    assert r"echo \"REPAIR_EXECUTION_ROOT=\$STAGING_PATH\"" in repair
    assert r"cd \"\$STAGING_PATH\"" in repair
    assert r"rm -rf \"\$STAGING_PATH\"" not in repair
    staging_absence_check = r"test ! -e \"\$STAGING_PATH\""
    staging_create = r"install -d -m 700 \"\$STAGING_PATH\""
    extraction = r"tar -xzf '/tmp/$BUNDLE_NAME' -C \"\$STAGING_PATH\""
    assert staging_absence_check in repair
    assert staging_create in repair
    assert extraction in repair
    assert (
        repair.index(staging_absence_check)
        < repair.index(staging_create)
        < repair.index(extraction)
    )
    assert r"test \"\$current_target\" = \"\$RELEASE_ROOT/$BASELINE_REVISION\"" in repair
    assert r"mv \"\$STAGING_PATH\" \"\$RELEASE_PATH\"" in repair
    assert "QUARANTINE_PATH" in repair


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
        "POSTGRES_SUPERUSER_RESERVED_CONNECTIONS=",
        "POSTGRES_RESERVED_CONNECTIONS=",
        "POSTGRES_USABLE_NON_RESERVED_CONNECTIONS=",
        "POSTGRES_CURRENT_CONNECTIONS=",
        "POSTGRES_CONNECTION_HEADROOM=",
        "POSTGRES_UNRESERVED_HEADROOM=",
        "POSTGRES_DECLARED_YFC_SESSIONS=",
        "POSTGRES_NON_YFC_SESSIONS=",
        "POSTGRES_UNATTRIBUTED_SESSIONS=",
        "POSTGRES_METRICS=",
        "POSTGRES_DIAGNOSTIC_CODE=",
        "POSTGRES_CONFIG_SOURCE=",
        "POSTGRES_BUDGET_VERDICT=NOT_VERIFIED",
        "AUDIT_WORKFLOW=",
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
    assert "SELECT 'superuser_reserved_connections='" in workflow_text
    assert "SELECT 'reserved_connections='" in workflow_text
    assert "SELECT 'session_counts='" in workflow_text
    assert "{{range .Config.Env}}" in workflow_text
    assert 'f"--username={db_user}"' in workflow_text
    assert 'f"--dbname={db_name}"' in workflow_text
    assert "POSTGRES_PASSWORD" not in workflow_text
    assert "DATABASE_URL" not in workflow_text
    assert "raise SystemExit(2)" in workflow_text
    assert 'DEPLOYMENT_ROOT.glob("*/summary.json")' in workflow_text
    assert ")[:5]" in workflow_text
    for legacy_field in (
        "RAM_AVAILABLE_MIN=",
        "RAM_AVAILABLE_AVG=",
        "RAM_AVAILABLE_MAX=",
    ):
        assert legacy_field not in workflow_text


def test_capacity_audit_session_counts_fail_closed_without_revealing_identity() -> None:
    workflow_text = _sources()["capacity_audit"]
    read_session_counts = _embedded_function(workflow_text, "read_session_counts")

    assert read_session_counts("20,8,3") == ("8", "12", "3")
    assert read_session_counts("0,0,0") == ("0", "0", "0")
    unknown = ("UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE")
    for invalid in (
        "",
        "20,8",
        "20,8,3,2",
        "20,21,0",
        "20,8,13",
        "20,-1,0",
        "20,3,∞",
        "20, 3,1",
    ):
        assert read_session_counts(invalid) == unknown
    assert "POSTGRES_BUDGET_VERDICT=NOT_VERIFIED" in workflow_text
    assert "application_name IN" in workflow_text
    assert "FROM pg_stat_activity" in workflow_text


def test_capacity_audit_uses_running_container_database_identity() -> None:
    workflow_text = _sources()["capacity_audit"]
    select_db_container = _embedded_function(workflow_text, "select_db_container")
    parse_runtime_env = _embedded_function(workflow_text, "parse_postgres_runtime_env")
    build_psql_command = _embedded_function(workflow_text, "build_psql_command")

    assert select_db_container("") == (None, "POSTGRES_DB_CONTAINER_NOT_FOUND")
    assert select_db_container("db-a\ndb-b\n") == (None, "POSTGRES_DB_CONTAINER_MULTIPLE")
    assert select_db_container("db-a\n") == ("db-a", "OK")

    assert parse_runtime_env(
        "POSTGRES_USER=reporter\nPOSTGRES_DB=production\nPOSTGRES_PASSWORD=secret"
    ) == {"POSTGRES_USER": "reporter", "POSTGRES_DB": "production"}
    assert parse_runtime_env("POSTGRES_USER=reporter") == {"POSTGRES_USER": "reporter"}
    assert parse_runtime_env("POSTGRES_DB=production") == {"POSTGRES_DB": "production"}
    assert parse_runtime_env("POSTGRES_USER=\nPOSTGRES_DB=production") is None

    command = build_psql_command("db-a", "reporter", "production", "SELECT 1")
    assert "--username=reporter" in command
    assert "--dbname=production" in command
    assert "--username=postgres" not in command
    assert "--dbname=postgres" not in command
    assert "-w" in command


@pytest.mark.parametrize(
    ("stderr", "expected"),
    (
        ("psql: command not found", "POSTGRES_CLIENT_UNAVAILABLE"),
        ("Error: No such container: db-a", "POSTGRES_DOCKER_EXEC_FAILED"),
        ("FATAL: password authentication failed", "POSTGRES_AUTHENTICATION_FAILED"),
        ("permission denied", "POSTGRES_PERMISSION_DENIED"),
        ("could not connect to server: Connection refused", "POSTGRES_CONNECTION_FAILED"),
        ("ERROR: syntax error", "POSTGRES_SQL_EXECUTION_FAILED"),
    ),
)
def test_capacity_audit_postgres_errors_are_allowlisted_and_secret_safe(
    stderr: str, expected: str
) -> None:
    classify_postgres_error = _embedded_function(
        _sources()["capacity_audit"], "classify_postgres_error"
    )
    secret = "password=must-not-be-printed"
    code = classify_postgres_error(SimpleNamespace(returncode=1, stderr=f"{stderr} {secret}"))

    assert code == expected
    assert secret not in code
    assert classify_postgres_error(None) == "POSTGRES_CLIENT_UNAVAILABLE"
    assert classify_postgres_error(SimpleNamespace(returncode=0, stderr="")) == "OK"


def test_capacity_audit_validates_pg15_pg16_counts_and_rejects_false_success() -> None:
    workflow_text = _sources()["capacity_audit"]
    parse_response = _embedded_function(workflow_text, "parse_postgres_response")
    read_session_counts = _embedded_function(workflow_text, "read_session_counts")
    validate_metrics = _embedded_function(
        workflow_text,
        "validate_postgres_metrics",
        read_session_counts=read_session_counts,
    )
    metrics_state = _embedded_function(workflow_text, "postgres_metrics_state")
    audit_status = _embedded_function(workflow_text, "audit_workflow_status")

    def response(version: str, reserved: str, current: str = "20") -> str:
        return "\n".join(
            (
                f"version_major={version}",
                "max_connections=100",
                "superuser_reserved_connections=10",
                f"reserved_connections={reserved}",
                f"current_connections={current}",
                "session_counts=20,8,3",
                "total_database_size_bytes=2097152",
                "shared_buffers=128MB",
            )
        )

    parsed15, parse_code15 = parse_response(response("15", "UNAVAILABLE"))
    metrics15, validation15 = validate_metrics(parsed15)
    assert parse_code15 == "OK"
    assert validation15 == "OK"
    assert metrics15["reserved_connections"] == "0"
    assert metrics15["usable_non_reserved_connections"] == "90"

    parsed16, parse_code16 = parse_response(response("16", "5"))
    metrics16, validation16 = validate_metrics(parsed16)
    assert parse_code16 == "OK"
    assert validation16 == "OK"
    assert metrics16["reserved_connections"] == "5"
    assert metrics16["usable_non_reserved_connections"] == "85"

    partial, partial_parse_code = parse_response("version_major=16\nmax_connections=100")
    partial_metrics, partial_code = validate_metrics(partial)
    assert partial_parse_code == "OK"
    assert partial_code == "POSTGRES_REQUIRED_METRIC_UNAVAILABLE"
    assert metrics_state(partial_metrics, partial_code) == "PARTIAL"
    assert audit_status("PARTIAL") == "NEEDS_WORK"

    malformed, malformed_parse_code = parse_response("version_major=16\nsecret=not-output")
    assert malformed == {}
    assert malformed_parse_code == "POSTGRES_MALFORMED_SQL_RESPONSE"

    contradictory, contradictory_parse_code = parse_response(response("16", "5", current="21"))
    contradictory_metrics, contradictory_code = validate_metrics(contradictory)
    assert contradictory_parse_code == "OK"
    assert contradictory_code == "POSTGRES_METRIC_CONFLICT"
    assert metrics_state(contradictory_metrics, contradictory_code) == "PARTIAL"
    assert audit_status("NO_DATA") == "NEEDS_WORK"
    assert audit_status("VERIFIED") == "PASS"
    assert "AUDIT_WORKFLOW=" in workflow_text
    assert "POSTGRES_BUDGET_VERDICT=PASS" not in workflow_text


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


def test_capacity_audit_postgres_reserved_and_attribution_diagnostics_are_read_only() -> None:
    workflow_text = _sources()["capacity_audit"]

    for field in (
        "POSTGRES_SUPERUSER_RESERVED_CONNECTIONS=",
        "POSTGRES_RESERVED_CONNECTIONS=",
        "POSTGRES_USABLE_NON_RESERVED_CONNECTIONS=",
        "POSTGRES_UNRESERVED_HEADROOM=",
        "POSTGRES_DECLARED_YFC_SESSIONS=",
        "POSTGRES_NON_YFC_SESSIONS=",
        "POSTGRES_UNATTRIBUTED_SESSIONS=",
        "POSTGRES_BUDGET_VERDICT=NOT_VERIFIED",
    ):
        assert field in workflow_text

    assert "current_setting('superuser_reserved_connections')" in workflow_text
    assert "current_setting('reserved_connections', true)" in workflow_text
    assert "SELECT 'session_counts='" in workflow_text
    assert "FROM pg_stat_activity;" in workflow_text
    assert "SELECT application_name" not in workflow_text
    assert "pg_stat_activity.client_addr" not in workflow_text
    assert "pg_stat_activity.query" not in workflow_text
    assert "docker exec" not in workflow_text
    assert '"docker",\n                  "exec",' in workflow_text
    # Counts are diagnostics; the owner-only read probe is not the deployment gate.
    assert "POSTGRES_BUDGET_VERDICT=PASS" not in workflow_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("20,8,3", ("8", "12", "3")),
        ("0,0,0", ("0", "0", "0")),
        ("2,3,0", ("UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE")),
        ("2,1,2", ("UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE")),
        ("2,-1,0", ("UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE")),
        ("2,0", ("UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE")),
        ("", ("UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE")),
        ("2,0,0,0", ("UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE")),
        ("1,0,٠", ("UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE")),
        ("1,0,0;select", ("UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE")),
    ),
)
def test_capacity_audit_session_counts_fail_closed_on_invalid_data(
    raw: str, expected: tuple[str, str, str]
) -> None:
    fn = _embedded_function(_sources()["capacity_audit"], "read_session_counts")
    assert fn(raw) == expected


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
