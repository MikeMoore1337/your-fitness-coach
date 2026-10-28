"""Two-stage YFC release governance contracts."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from scripts import ci_contract

ROOT = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = ROOT / "scripts/update_dev.ps1"


def test_dev_push_runs_ci_but_cannot_start_production_deploy() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

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


@pytest.fixture
def bootstrap_repo(tmp_path: Path, monkeypatch):
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.name=Contract", "-c", "user.email=contract@example.invalid", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "--quiet")
    revisions = []
    for name in ("dev", "master", "head"):
        git("commit", "--quiet", "--allow-empty", "-m", name)
        revisions.append(git("rev-parse", "HEAD"))
    base, master, head = revisions
    git("update-ref", "refs/remotes/origin/dev", base)
    git("update-ref", "refs/remotes/origin/master", master)
    monkeypatch.setattr(ci_contract, "DEV_BOOTSTRAP_BASE_SHA", base)
    monkeypatch.setattr(ci_contract, "DEV_BOOTSTRAP_MASTER_SHA", master)
    env = {
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_REPOSITORY": "MikeMoore1337/your-fitness-coach",
        "PR_NUMBER": "1267",
        "PR_BASE_REF": "dev",
        "PR_BASE_SHA": base,
        "PR_HEAD_REF": "feat/1266-dev-promotion-gate",
        "PR_HEAD_REPO": "MikeMoore1337/your-fitness-coach",
        "PR_HEAD_SHA": head,
    }
    return tmp_path, env, git, master


def test_bootstrap_accepts_only_verified_master_in_actual_pr_head(bootstrap_repo) -> None:
    root, env, _, master = bootstrap_repo
    assert ci_contract.bootstrap_lime_edge_base(root, env) == master


@pytest.mark.parametrize(
    "key,value",
    [
        ("GITHUB_EVENT_NAME", "push"),
        ("GITHUB_REPOSITORY", "fork/your-fitness-coach"),
        ("PR_NUMBER", "1268"),
        ("PR_BASE_REF", "master"),
        ("PR_BASE_SHA", "0" * 40),
        ("PR_HEAD_REF", "dev"),
        ("PR_HEAD_REPO", "fork/your-fitness-coach"),
        ("PR_HEAD_SHA", "HEAD"),
        ("PR_HEAD_SHA", ""),
        ("PR_HEAD_SHA", "f" * 40),
    ],
)
def test_bootstrap_identity_and_missing_commit_fail_closed(bootstrap_repo, key, value) -> None:
    root, env, _, _ = bootstrap_repo
    env[key] = value
    with pytest.raises(ci_contract.CIContractError):
        ci_contract.bootstrap_lime_edge_base(root, env)


@pytest.mark.parametrize("ref", ["dev", "master"])
def test_bootstrap_changed_remote_ref_fails_closed(bootstrap_repo, ref) -> None:
    root, env, git, _ = bootstrap_repo
    git("update-ref", f"refs/remotes/origin/{ref}", env["PR_HEAD_SHA"])
    with pytest.raises(ci_contract.CIContractError, match="exact ref mismatch"):
        ci_contract.bootstrap_lime_edge_base(root, env)


@pytest.mark.parametrize("missing", ["dev", "master"])
def test_bootstrap_missing_remote_ref_fails_closed(bootstrap_repo, missing) -> None:
    root, env, git, _ = bootstrap_repo
    git("update-ref", "-d", f"refs/remotes/origin/{missing}")
    with pytest.raises(ci_contract.CIContractError, match="Git validation failed"):
        ci_contract.bootstrap_lime_edge_base(root, env)


def test_bootstrap_synthetic_merge_cannot_mask_master_missing_from_pr_head(bootstrap_repo) -> None:
    root, env, _, _ = bootstrap_repo
    # The checkout has master, but the advertised feature head does not.
    env["PR_HEAD_SHA"] = env["PR_BASE_SHA"]
    with pytest.raises(ci_contract.CIContractError, match="merge-base"):
        ci_contract.bootstrap_lime_edge_base(root, env)


def test_bootstrap_rejects_checkout_without_pr_head(bootstrap_repo) -> None:
    root, env, git, master = bootstrap_repo
    git("checkout", "--detach", master)
    with pytest.raises(ci_contract.CIContractError, match="merge-base"):
        ci_contract.bootstrap_lime_edge_base(root, env)


def test_bootstrap_requires_original_dev_ancestor_of_master(bootstrap_repo, monkeypatch) -> None:
    root, env, git, _ = bootstrap_repo
    git("checkout", "--orphan", "unrelated")
    git("commit", "--quiet", "--allow-empty", "-m", "unrelated")
    unrelated = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/dev", unrelated)
    monkeypatch.setattr(ci_contract, "DEV_BOOTSTRAP_BASE_SHA", unrelated)
    env["PR_BASE_SHA"] = unrelated
    with pytest.raises(ci_contract.CIContractError, match="merge-base"):
        ci_contract.bootstrap_lime_edge_base(root, env)


def test_bootstrap_cli_emits_no_environment_override_on_failure(
    bootstrap_repo, monkeypatch, capsys
) -> None:
    root, env, _, _ = bootstrap_repo
    monkeypatch.chdir(root)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PR_HEAD_SHA", "f" * 40)
    assert ci_contract.main(["bootstrap-lime-base"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Git validation failed" in output.err


def test_workflow_does_not_override_lime_base_for_other_prs_or_skip_checks() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["frontend"]["steps"]
    baseline = next(
        step
        for step in steps
        if step.get("name") == "Validate one-time dev bootstrap lime baseline"
    )
    assert baseline["if"] == (
        "matrix.lane == 'checks' && github.event_name == 'pull_request' "
        "&& github.event.pull_request.number == 1267"
    )
    assert baseline["run"] == 'python scripts/ci_contract.py bootstrap-lime-base >> "$GITHUB_ENV"'
    assert "continue-on-error" not in baseline
    for key, field in {
        "PR_NUMBER": "number",
        "PR_BASE_REF": "base.ref",
        "PR_BASE_SHA": "base.sha",
        "PR_HEAD_REF": "head.ref",
        "PR_HEAD_REPO": "head.repo.full_name",
        "PR_HEAD_SHA": "head.sha",
    }.items():
        assert baseline["env"][key] == "${{ github.event.pull_request." + field + " }}"
    checks = next(step for step in steps if step.get("name") == "Run shared frontend checks group")
    assert checks["if"] == "matrix.lane == 'checks'"
    assert "continue-on-error" not in checks
    assert "tests/test_dev_release_flow.py" in ci_contract.COMMAND_GROUPS["policy"].commands[0].argv
    assert "LIME_EDGE_BASE_SHA" not in workflow["env"]
    assert "LIME_EDGE_BASE_SHA" not in workflow["jobs"]["frontend"]["env"]


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
        "merge', '--ff-only', 'origin/dev",
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
