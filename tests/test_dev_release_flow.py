"""Two-stage YFC release governance contracts."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from scripts import ci_contract

ROOT = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = ROOT / "scripts/update_dev.ps1"


@pytest.mark.parametrize(
    "scenario", ["valid", "reviewed", "unsafe", "modified", "deleted", "renamed", "not_ancestor"]
)
def test_dev_migration_preflight_uses_immutable_target_without_child_git(
    tmp_path: Path, scenario: str
) -> None:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell is not available on this runner")
    repo = tmp_path / "old checkout"
    repo.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.name=Contract", "-c", "user.email=contract@example.invalid", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "--quiet")
    checker = repo / "scripts/check_online_migrations.py"
    checker.parent.mkdir()
    checker.write_text('raise SystemExit("installed checker must not run")\n', encoding="utf-8")
    migration = repo / "backend/alembic/versions/9999_test_expand.py"
    migration.parent.mkdir(parents=True)
    (migration.parent / "__init__.py").write_text("", encoding="utf-8")
    valid = (
        'online_rollout_phase = "expand"\n'
        'online_rollout_notes = "Nullable additive column; metadata-only lock."\n'
        "def upgrade():\n"
        '    op.add_column("users", sa.Column("nickname", sa.String(), nullable=True))\n'
    )
    reviewed_old = valid + "\ndef downgrade():\n    pass\n"
    reviewed_new = reviewed_old.replace("    pass\n", '    raise RuntimeError("guard")\n')
    if scenario in {"modified", "deleted", "renamed", "reviewed"}:
        migration.write_text(reviewed_old if scenario == "reviewed" else valid, encoding="utf-8")
    git("add", ".")
    git("commit", "--quiet", "-m", "installed version")
    source = git("rev-parse", "HEAD")
    if scenario == "not_ancestor":
        git("checkout", "--orphan", "unrelated")
    checker.write_bytes((ROOT / "scripts/check_online_migrations.py").read_bytes())
    if scenario == "reviewed":
        hashes = tuple(
            hashlib.sha256(value.encode()).hexdigest() for value in (reviewed_old, reviewed_new)
        )
        source_text = checker.read_text(encoding="utf-8")
        marker = "DEV_DOWNGRADE_TRANSITIONS = {"
        assert source_text.count(marker) == 1
        checker.write_text(
            source_text.replace(
                marker,
                f'{marker}\n    "{migration.relative_to(repo).as_posix()}": {hashes!r},',
                1,
            ),
            encoding="utf-8",
        )
    if scenario == "deleted":
        migration.unlink()
    elif scenario == "renamed":
        migration.rename(migration.with_name("9998_renamed.py"))
    elif scenario == "reviewed":
        migration.write_text(reviewed_new, encoding="utf-8")
    else:
        migration.write_text(
            valid.replace("op.add_column", "op.drop_table")
            if scenario == "unsafe"
            else valid + "\n",
            encoding="utf-8",
        )
    git("add", ".")
    git("commit", "--quiet", "-m", "target version")
    target = git("rev-parse", "HEAD")
    git("checkout", "--quiet", source)
    installed = checker.read_bytes()
    status_before = git("status", "--porcelain")

    def ps(value: Path | str) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    harness = tmp_path / "preflight.ps1"
    harness.write_text(
        "$ErrorActionPreference='Stop'\n"
        f"$script:RepoRoot={ps(repo)}; $script:StateRoot={ps(tmp_path / 'evidence')}\n"
        "$script:CurrentResult=@{migration='NOT_RUN'}; $script:FailureCode=''\n"
        "$tokens=$null; $errors=$null\n"
        f"$ast=[System.Management.Automation.Language.Parser]::ParseFile({ps(UPDATE_SCRIPT)},[ref]$tokens,[ref]$errors)\n"
        "if ($errors.Count) { throw 'parse failure' }\n"
        "$names=@('Invoke-Git','Get-GitValue','Get-ChangedMigrations','Stop-Update','Test-MigrationCompatibility')\n"
        "$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false) | "
        "Where-Object {$_.Name -in $names} | ForEach-Object {. ([scriptblock]::Create($_.Extent.Text))}\n"
        f"function py {{ & {ps(sys.executable)} @($args | Select-Object -Skip 1) }}\n"
        f"try {{ Test-MigrationCompatibility -Source {ps(source)} -Target {ps(target)}; Write-Output 'VALIDATED' }}\n"
        "catch { Write-Output ('GATE_REJECTED='+$script:FailureCode); exit 17 }\n",
        encoding="utf-8-sig",
    )
    # Reset inherited trusted paths only in this disposable fixture's child processes.
    env = {
        **os.environ,
        "GIT_TEST_ASSUME_DIFFERENT_OWNER": "1",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": "",
    }
    env.pop("GIT_CONFIG_PARAMETERS", None)
    raw = subprocess.run(["git", "status", "--porcelain"], cwd=repo, env=env, capture_output=True)
    assert raw.returncode != 0, "exercise Git's actual dubious-ownership boundary"
    result = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(harness)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if scenario in {"valid", "reviewed"}:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "VALIDATED" in result.stdout
        manifest = next((tmp_path / "evidence").glob("*/manifest.json"))
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        assert (saved["active_revision"], saved["target_revision"]) == (source, target)
        expected_status = "A" if scenario == "valid" else "M"
        assert saved["changes"] == [
            {"status": expected_status, "path": migration.relative_to(repo).as_posix()}
        ]
    else:
        assert result.returncode == 17, result.stdout + result.stderr
        assert "GATE_REJECTED=MIGRATION_REVIEW_REQUIRED" in result.stdout
    if scenario != "not_ancestor":
        log = next((tmp_path / "evidence").glob("*/validation.log")).read_text(encoding="utf-8-sig")
        if scenario == "valid":
            assert "Online migration gate passed: 1 added migration(s)" in log
        elif scenario == "reviewed":
            assert "DEV-only reviewed downgrade change:" in log
            assert "Online migration gate passed: 0 added migration(s)" in log
        elif scenario == "unsafe":
            assert "Online migration gate failed:" in log and "drop_table" in log
        else:
            assert "applied migration history is immutable" in log
    assert git("rev-parse", "HEAD") == source
    assert git("status", "--porcelain") == status_before
    assert checker.read_bytes() == installed


def test_dev_push_runs_ci_but_cannot_start_production_deploy() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    assert "--dev-reviewed-source" not in deploy

    assert "branches: [master, dev]" in ci
    # Retargeting must rerun the target-branch promotion guard and exact diff.
    assert "types: [opened, reopened, ready_for_review, synchronize, edited]" in ci
    assert "Require accepted dev promotion for master PR" in ci
    assert "PR_HEAD_REF: ${{ github.event.pull_request.head.ref }}" in ci
    assert "PR_HEAD_REPO: ${{ github.event.pull_request.head.repo.full_name }}" in ci
    assert '[ "$PR_HEAD_REF" != dev ] || [ "$PR_HEAD_REPO" != "$REPOSITORY" ]' in ci

    # The preexisting release trigger must remain master-only.
    assert "branches: [master]" in deploy
    assert "github.event.workflow_run.head_branch == 'master'" in deploy
    assert "environment: production" in deploy


def test_initial_master_to_dev_large_diff_does_not_overflow_ci_outputs(tmp_path: Path) -> None:
    paths = [f"backend/tests/fixture_{index:07d}.py" for index in range(15_000)]
    decision = ci_contract.classify_scope(paths)
    assert len(decision["paths"]) == len(paths)
    assert "python-tests" in decision["required_groups"]

    path = tmp_path / "gh-output"
    ci_contract.write_router_outputs(decision, path)
    content = path.read_text(encoding="utf-8")
    assert len(content.encode("utf-16-le")) < 20_000
    serialized = next(
        line.split("=", 1)[1] for line in content.splitlines() if line.startswith("changed_paths=")
    )
    assert json.loads(serialized) == [f"__paths_truncated__:{len(paths)}"]


def test_normal_pull_request_outputs_preserve_exact_paths(tmp_path: Path) -> None:
    decision = ci_contract.classify_scope(["frontend/package.json"])
    path = tmp_path / "gh-output"
    ci_contract.write_router_outputs(decision, path)
    assert 'changed_paths=["frontend/package.json"]' in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("head_ref", "head_repo", "allowed"),
    [
        ("dev", "MikeMoore1337/your-fitness-coach", True),
        ("feature/direct-master", "MikeMoore1337/your-fitness-coach", False),
        ("dev", "another-user/your-fitness-coach", False),
    ],
)
def test_master_promotion_guard_rejects_feature_and_fork(
    head_ref: str, head_repo: str, allowed: bool
) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("Bash is not available on this runner")
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    guard = next(
        step
        for step in workflow["jobs"]["checks"]["steps"]
        if step.get("name") == "Require accepted dev promotion for master PR"
    )
    assert guard["if"] == (
        "github.event_name == 'pull_request' && github.event.pull_request.base.ref == 'master'"
    )
    result = subprocess.run(
        [bash, "-e", "-o", "pipefail", "-c", guard["run"]],
        env={
            **os.environ,
            "PR_HEAD_REF": head_ref,
            "PR_HEAD_REPO": head_repo,
            "REPOSITORY": "MikeMoore1337/your-fitness-coach",
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert (result.returncode == 0) is allowed, result.stdout + result.stderr
    if not allowed:
        assert "Direct PR to master forbidden" in result.stdout + result.stderr


def test_retired_bootstrap_cannot_override_normal_frontend_lint() -> None:
    source = (ROOT / "scripts/ci_contract.py").read_text(encoding="utf-8")
    workflow_source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_source)
    steps = workflow["jobs"]["frontend"]["steps"]

    assert "bootstrap-lime-base" not in source
    assert "bootstrap_lime_edge_base" not in source
    assert "DEV_BOOTSTRAP_BASE_SHA" not in source
    assert "DEV_BOOTSTRAP_MASTER_SHA" not in source
    assert "bootstrap-lime-base" not in workflow_source
    assert "Validate one-time dev bootstrap lime baseline" not in workflow_source
    assert "LIME_EDGE_BASE_SHA" not in workflow.get("env", {})
    assert "LIME_EDGE_BASE_SHA" not in workflow["jobs"]["frontend"].get("env", {})

    checks = next(step for step in steps if step.get("name") == "Run shared frontend checks group")
    assert checks["if"] == "matrix.lane == 'checks'"
    assert "continue-on-error" not in checks
    assert "tests/test_dev_release_flow.py" in ci_contract.COMMAND_GROUPS["policy"].commands[0].argv


def test_local_dev_updater_is_fail_closed_and_reuses_project_launcher() -> None:
    source = UPDATE_SCRIPT.read_text(encoding="utf-8-sig")
    check_body = source.split("function Invoke-Check", 1)[1].split("function Get-AvailableSha", 1)[
        0
    ]

    for forbidden in (
        "git reset --hard",
        "docker compose down --volumes",
        "-Action reset",
        "production.env",
        "docker-compose.yml",
    ):
        assert forbidden not in source

    for required in (
        "scripts\\dev.ps1",
        "-Action start",
        "safe.directory=",
        "dev:refs/remotes/origin/dev",
        "merge', '--ff-only', $context.Target",
        "head_sha",
        "branch-checks",
        "check_online_migrations.py",
        "verify_dev_roles.py",
        "Global\\YFC_DEV_UPDATE",
        "MultipleInstances IgnoreNew",
        "manual-acceptance.lock",
        "auto-apply.enabled",
        "dev_postgres_data",
        "VOLUME_CHECK_FAILED",
        "dockerBefore",
    ):
        assert required in source
    assert "result = 'NO_UPDATE'" in check_body
    assert "Invoke-DevStart" not in check_body
    assert "$script:ExitCode = 2" in check_body


@pytest.mark.parametrize(
    ("scenario", "marker"),
    [
        ("no update", "NO_UPDATE"),
        ("successful update", "result = 'PASS'"),
        ("dirty repository", "GIT_DIRTY"),
        ("divergent repository", "DIVERGENT"),
        ("pending or failed CI", "CI_{0}"),
        ("Docker unavailable", "DOCKER_UNAVAILABLE"),
        ("health failure", "HEALTH_READY_FAILED"),
        ("RBAC failure", "RBAC_FAILED"),
        ("incomplete or parallel update", "UPDATE_IN_PROGRESS"),
        ("volume changed", "VOLUME_CHANGED"),
    ],
)
def test_local_dev_updater_records_required_safety_scenarios(scenario: str, marker: str) -> None:
    source = UPDATE_SCRIPT.read_text(encoding="utf-8-sig")
    assert marker in source, scenario


def test_local_dev_updater_parser_and_scheduler_contract() -> None:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell is not available on this runner")

    parser = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-Command",
            (
                "$tokens=$null; $errors=$null; "
                "[System.Management.Automation.Language.Parser]::ParseFile("
                "(Resolve-Path 'scripts/update_dev.ps1'), [ref]$tokens, [ref]$errors) > $null; "
                "if ($errors.Count) { exit 1 }"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert parser.returncode == 0, parser.stderr or parser.stdout

    source = UPDATE_SCRIPT.read_text(encoding="utf-8-sig")
    assert "New-ScheduledTaskTrigger" in source
    assert "New-TimeSpan -Minutes 5" in source
    assert "New-SilentUpdaterAction" in source
    launcher = (ROOT / "scripts/dev_update_silent.pyw").read_text(encoding="utf-8")
    assert '"-Mode",' in launcher and '"Check",' in launcher and '"-Automatic",' in launcher
    assert "Remove-Item -LiteralPath $script:AutoApplyPath" in source


def test_local_dev_updater_registration_uses_supported_interactive_logon_and_safe_errors() -> None:
    source = UPDATE_SCRIPT.read_text(encoding="utf-8-sig")

    assert "-LogonType Interactive" in source
    assert "-LogonType InteractiveToken" not in source
    assert "-UserId $env:USERNAME" in source
    assert "-RunLevel Limited" in source
    assert "TASK_REGISTER_FAILED" in source
    assert "error_id=" in source
    assert "hresult=" in source
    assert "[REDACTED]" in source
