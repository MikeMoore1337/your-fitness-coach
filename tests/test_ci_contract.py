from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import ci_contract, pre_push_gate


def test_ci_contract_is_valid_and_profiles_are_non_empty() -> None:
    ci_contract.validate_contract()
    assert ci_contract.contract_digest()
    assert all(ci_contract.PROFILE_GROUPS.values())


def test_profiles_reference_shared_command_groups() -> None:
    for groups in ci_contract.PROFILE_GROUPS.values():
        assert set(groups) <= set(ci_contract.COMMAND_GROUPS)


def test_commands_are_stable_and_have_unique_names() -> None:
    for spec in ci_contract.COMMAND_GROUPS.values():
        assert len({command.name for command in spec.commands}) == len(spec.commands)
        assert all(command.argv for command in spec.commands)


def test_contract_digest_changes_when_contract_changes(monkeypatch) -> None:
    original_digest = ci_contract.contract_digest()
    original = ci_contract.COMMAND_GROUPS["quality"]
    monkeypatch.setitem(
        ci_contract.COMMAND_GROUPS,
        "quality",
        ci_contract.GroupSpec(
            name=original.name,
            commands=(*original.commands, ci_contract.CommandSpec("sentinel", ("true",))),
            prerequisites=original.prerequisites,
        ),
    )
    assert ci_contract.contract_digest() != original_digest


def test_shards_parse_and_select_deterministically() -> None:
    assert ci_contract.parse_shard("1/4") == (0, 4)
    assert ci_contract.parse_shard("4/4") == (3, 4)
    nodes = tuple(f"test_{index}" for index in range(8))
    assert ci_contract.select_shard(nodes, shard_index=0, shard_count=4) == (
        "test_0",
        "test_4",
    )
    assert ci_contract.select_shard(nodes, shard_index=3, shard_count=4) == (
        "test_3",
        "test_7",
    )
    with pytest.raises(ci_contract.CIContractError):
        ci_contract.parse_shard("5/4")


def test_python_node_normalization_preserves_escaped_parameter_ids() -> None:
    assert (
        ci_contract._normalize_python_test_node(
            r"backend\tests\test_app.py::test_public_content[\u041e]"
        )
        == r"backend/tests/test_app.py::test_public_content[\u041e]"
    )


def test_frontend_e2e_shard_is_forwarded_to_playwright(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        ci_contract,
        "missing_prerequisites",
        lambda group, *, root, env: [],
    )

    def fake_run(argv, **kwargs):
        del kwargs
        calls.append(list(argv))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ci_contract.subprocess, "run", fake_run)
    ci_contract.run_group("frontend-e2e", root=tmp_path, env={}, shard="2/4")

    assert calls[0][-2:] == ["--", "--shard=2/4"]


def test_python_shard_collects_and_runs_only_its_node_ids(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        ci_contract,
        "missing_prerequisites",
        lambda group, *, root, env: [],
    )
    collected = "\n".join(
        [
            "backend/tests/test_a.py::test_a",
            "backend/tests/test_b.py::test_b",
            "bot/tests/test_c.py::test_c",
            "bot/tests/test_d.py::test_d",
            "backend/tests/test_e.py::test_e",
            "bot/tests/test_f.py::test_f",
        ]
    )

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        if "--collect-only" in argv:
            return SimpleNamespace(returncode=0, stdout=collected, stderr="")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ci_contract.subprocess, "run", fake_run)
    ci_contract.run_group(
        "python-tests",
        root=tmp_path,
        env={"TEST_DATABASE_URL": "postgresql://test"},
        shard="2/4",
    )

    assert calls[1][-2:] == ["--collect-only", "-q"]
    assert calls[2][2:4] == [
        "backend/tests/test_b.py::test_b",
        "bot/tests/test_f.py::test_f",
    ]


def test_windows_node_commands_use_cmd_wrappers(monkeypatch) -> None:
    monkeypatch.setattr(ci_contract.os, "name", "nt")
    assert ci_contract._resolve_argv(("npm", "run", "test"))[0] == "npm.cmd"
    assert ci_contract._resolve_argv(("npx", "vite", "build"))[0] == "npx.cmd"


def test_migrations_use_the_selected_python_interpreter() -> None:
    commands = ci_contract.COMMAND_GROUPS["migrated-stack"].commands
    assert commands[0].argv[:3] == ("python", "-m", "alembic")
    assert commands[1].argv[:3] == ("python", "-m", "alembic")


def test_workflow_calls_group_entrypoint_instead_of_inline_command_copy() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for group in (
        "quality",
        "policy",
        "frontend-checks",
        "frontend-e2e",
        "frontend-mobile-regression",
        "frontend-mobile-regression-extended",
        "frontend-cross-browser",
        "python-tests",
        "migrated-stack",
        "dependency-audit",
        "frontend-dependency-audit",
        "python-dependency-audit",
        "critical-smoke",
        "workflow-config",
        "image-contract",
        "deployment-contract",
        "container-contract",
    ):
        assert f"scripts/ci_contract.py run-group {group}" in workflow
    assert "npm run typecheck" not in workflow
    assert "npm run e2e:ci" not in workflow
    assert "scripts/run_pytest.py backend/tests" not in workflow


def test_pr_ci_requires_exact_head_review_before_aggregate_checks() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    required = ci_contract.expected_jobs_for_groups(("quality",), event="pull_request")
    assert "review-contract" in required
    assert "pull_request_review:" in workflow
    assert "review-contract:" in workflow
    assert 'validate-pr-review --event "$GITHUB_EVENT_PATH"' in workflow
    assert "review-contract" in workflow[workflow.index("  checks:") :]


def test_workflow_uses_lockfile_download_cache_without_audit_installation() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    audit_start = workflow.index("  dependency-audit:")
    audit_end = workflow.index("  critical-smoke:", audit_start)
    audit_job = workflow[audit_start:audit_end]

    assert "NPM_CONFIG_CACHE" not in workflow
    assert "cache: npm" in workflow
    assert "cache-dependency-path: frontend/package-lock.json" in workflow
    assert "node_modules" not in audit_job
    assert "npm ci" not in audit_job
    assert "run-group frontend-dependency-audit" in audit_job


def test_allure_dependencies_are_scheduled_only() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    package = (root / "frontend" / "package.json").read_text(encoding="utf-8")
    scheduled_package = (root / "frontend" / "scheduled-report" / "package.json").read_text(
        encoding="utf-8"
    )
    development_requirements = (root / "backend" / "requirements-dev.in").read_text(
        encoding="utf-8"
    )
    scheduled_requirements = (root / "backend" / "requirements-scheduled-report.in").read_text(
        encoding="utf-8"
    )

    assert '"allure-vitest"' not in package
    assert '"allure-playwright"' not in package
    assert '"allure-commandline"' not in package
    assert "allure-pytest" not in development_requirements
    assert '"allure-vitest": "3.12.0"' in scheduled_package
    assert '"allure-playwright": "3.12.0"' in scheduled_package
    assert '"allure-commandline": "2.43.0"' in scheduled_package
    assert "allure-pytest==2.16.0" in scheduled_requirements
    assert workflow.count("npm ci --prefix scheduled-report") == 7
    assert workflow.count("--omit=peer") == 7
    assert workflow.count("requirements-scheduled-report.txt") == 4
    assert "./scheduled-report/node_modules/.bin/allure generate" in workflow
    assert "python scripts/publish_allure_report.py publish" in workflow
    assert "ALLURE_REPORT_SSH_PRIVATE_KEY" in workflow
    assert "ALLURE_REPORT_SSH_KNOWN_HOSTS" in workflow
    assert "ALLURE_R2" not in workflow
    assert "allure-report-worker" not in workflow
    python_job_start = workflow.index("  python-tests:")
    python_steps_start = workflow.index("    steps:", python_job_start)
    assert "ALLURE_RESULTS_DIR:" in workflow[python_job_start:python_steps_start]


def test_workflow_keeps_four_way_smoke_and_python_shards_independent() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "name: Frontend smoke (${{ matrix.shard }}/4)" in workflow
    assert "name: Python tests (${{ matrix.shard }}/4)" in workflow
    assert workflow.count("        shard: [1, 2, 3, 4]") == 2
    assert 'run-group frontend-e2e --shard "${{ matrix.shard }}/4"' in workflow
    assert 'run-group python-tests --shard "${{ matrix.shard }}/4"' in workflow
    assert workflow.count("          path: ~/.cache/ms-playwright") == 5
    assert (
        workflow.count(
            "          key: playwright-${{ runner.os }}-${{ hashFiles('frontend/package-lock.json') }}"
        )
        == 2
    )
    assert (
        "  frontend-smoke:\n    name: Frontend smoke (${{ matrix.shard }}/4)\n    needs: scope-router\n    if:"
        in workflow
    )
    assert (
        "  migrated-stack:\n    name: Migrated PostgreSQL stack\n    needs: scope-router\n    if:"
        in workflow
    )
    assert "run-group frontend-mobile-regression" in workflow
    assert "run-group frontend-mobile-regression-extended" in workflow
    assert "run-group frontend-cross-browser" in workflow
    assert 'cron: "17 2 * * *"' in workflow
    assert 'cron: "43 3 * * 0"' in workflow
    assert "run_kind:" in workflow
    assert (
        "playwright-mobile-${{ runner.os }}-${{ hashFiles('frontend/package-lock.json') }}"
        in workflow
    )


def test_cross_stack_profile_includes_delivery_policy_gates() -> None:
    groups = set(ci_contract.PROFILE_GROUPS["cross-stack"])
    assert {"policy", "workflow-config", "deployment-contract"} <= groups
    assert "frontend-mobile-regression" in groups
    assert "frontend-mobile-regression-extended" not in groups


def test_policy_group_executes_ci_timing_regressions() -> None:
    policy_commands = ci_contract.COMMAND_GROUPS["policy"].commands
    policy_argv = {argument for command in policy_commands for argument in command.argv}

    assert "tests/test_ci_timing.py" in policy_argv


def test_daily_and_weekly_profiles_have_bounded_expansion() -> None:
    daily = set(ci_contract.PROFILE_GROUPS["daily-regression"])
    weekly = set(ci_contract.PROFILE_GROUPS["weekly-exhaustive"])

    assert set(ci_contract.PROFILE_GROUPS["cross-stack"]) - daily
    assert daily < weekly
    assert {"frontend-mobile-regression-extended", "frontend-cross-browser"} <= weekly


@pytest.mark.parametrize(
    ("paths", "profile", "required_groups", "forbidden_groups"),
    [
        (
            ["docs/release-flow.md", "codex-backlog/tasks/140-scope.md"],
            "documentation",
            {"quality", "workflow-config"},
            {
                "frontend-e2e",
                "python-tests",
                "migrated-stack",
                "dependency-audit",
                "container-contract",
            },
        ),
        (
            ["security/README.md"],
            "documentation",
            {"quality", "workflow-config"},
            {"container-contract", "dependency-audit", "frontend-e2e", "python-tests"},
        ),
        (
            ["frontend/src/App.tsx"],
            "frontend",
            {"frontend-checks", "frontend-e2e", "critical-smoke"},
            {"python-tests", "migrated-stack", "dependency-audit", "container-contract"},
        ),
        (
            ["backend/fitminiapp_api/services/example.py"],
            "backend",
            {"python-tests", "critical-smoke"},
            {
                "frontend-checks",
                "frontend-e2e",
                "migrated-stack",
                "dependency-audit",
                "container-contract",
            },
        ),
        (
            ["backend/fitminiapp_api/schemas/example.py"],
            "cross-stack",
            {
                "frontend-e2e",
                "python-tests",
                "migrated-stack",
                "dependency-audit",
                "container-contract",
            },
            set(),
        ),
        (
            ["backend/alembic/versions/0040_feature.py"],
            "migration",
            {"python-tests", "migrated-stack", "critical-smoke", "deployment-contract"},
            {"frontend-e2e", "dependency-audit", "container-contract"},
        ),
        (
            ["frontend/package-lock.json"],
            "frontend",
            {"frontend-dependency-audit"},
            {"python-dependency-audit", "container-contract"},
        ),
        (
            ["backend/requirements-runtime.txt"],
            "backend",
            {"python-dependency-audit", "container-contract"},
            {"frontend-e2e", "migrated-stack"},
        ),
        (
            [".github/workflows/ci.yml"],
            "workflow-platform",
            {"policy", "workflow-config", "image-contract", "deployment-contract"},
            {
                "frontend-e2e",
                "python-tests",
                "migrated-stack",
                "dependency-audit",
                "container-contract",
            },
        ),
        (
            ["bot/.dockerignore"],
            "cross-stack",
            {"container-contract", "frontend-e2e", "python-tests", "migrated-stack"},
            set(),
        ),
        (
            [".trivyignore.yaml"],
            "workflow-platform",
            {"container-contract", "workflow-config", "image-contract", "deployment-contract"},
            {"frontend-e2e", "python-tests", "migrated-stack"},
        ),
        (
            ["scripts/ci_contract.py"],
            "cross-stack",
            {
                "frontend-e2e",
                "python-tests",
                "migrated-stack",
                "dependency-audit",
                "container-contract",
            },
            set(),
        ),
        (
            ["unknown/build-input.bin"],
            "cross-stack",
            {
                "frontend-e2e",
                "python-tests",
                "migrated-stack",
                "dependency-audit",
                "container-contract",
            },
            set(),
        ),
    ],
)
def test_scope_router_is_conservative_and_profile_specific(
    paths: list[str],
    profile: str,
    required_groups: set[str],
    forbidden_groups: set[str],
) -> None:
    decision = ci_contract.classify_scope(paths)

    assert decision["profile"] == profile
    groups = set(decision["required_groups"])
    assert required_groups <= groups
    assert not forbidden_groups & groups


def test_scope_router_preserves_dot_prefixed_workflow_paths() -> None:
    decision = ci_contract.classify_scope(["./.github/workflows/ci.yml"])

    assert decision["paths"] == [".github/workflows/ci.yml"]
    assert decision["profile"] == "workflow-platform"


def test_scope_router_writes_machine_readable_outputs(tmp_path: Path) -> None:
    destination = tmp_path / "github-output"
    decision = ci_contract.classify_scope(["frontend/package.json"])

    ci_contract.write_router_outputs(decision, destination)

    output = destination.read_text(encoding="utf-8")
    assert "profile=frontend" in output
    assert "run_frontend_dependency_audit=true" in output
    assert 'required_jobs=["' in output


def test_repository_router_uses_exact_pull_request_diff(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ci_contract,
        "_git_changed_paths",
        lambda root, base_sha, head_sha: ["backend/fitminiapp_api/main.py"],
    )

    decision = ci_contract.route_repository(
        tmp_path,
        event="pull_request",
        base_sha="base",
        head_sha="head",
    )

    assert decision["profile"] == "backend"
    assert decision["base_sha"] == "base"
    assert decision["head_sha"] == "head"


def test_scheduled_and_manual_routes_resolve_distinct_regression_profiles() -> None:
    daily = ci_contract.route_repository(Path.cwd(), event="schedule", schedule_cron="17 2 * * *")
    weekly = ci_contract.route_repository(Path.cwd(), event="schedule", schedule_cron="43 3 * * 0")
    manual = ci_contract.route_repository(Path.cwd(), event="workflow_dispatch", run_kind="weekly")

    assert daily["profile"] == "daily-regression"
    assert weekly["profile"] == "weekly-exhaustive"
    assert manual["profile"] == weekly["profile"]
    assert daily["outputs"]["run_full_dependency_audit"] is False
    assert weekly["outputs"]["run_full_dependency_audit"] is True
    assert daily["outputs"]["run_frontend_mobile_regression_extended"] is False
    assert weekly["outputs"]["run_frontend_mobile_regression_extended"] is True
    assert daily["outputs"]["run_scheduled_report"] is True


def test_push_route_keeps_merge_provenance_and_container_delivery() -> None:
    decision = ci_contract.route_repository(Path.cwd(), event="push")

    assert decision["required_jobs"] == ["containers", "merge-provenance", "scope-router"]
    assert decision["outputs"]["run_merge_provenance"] is True
    assert decision["outputs"]["run_containers"] is True


def test_expected_result_set_rejects_missing_or_skipped_required_jobs() -> None:
    expected = ["scope-router", "quality"]
    ci_contract.verify_results(expected, {"scope-router": "success", "quality": "success"})

    with pytest.raises(ci_contract.CIContractError, match="did not succeed"):
        ci_contract.verify_results(expected, {"scope-router": "success"})
    with pytest.raises(ci_contract.CIContractError, match="did not succeed"):
        ci_contract.verify_results(expected, {"scope-router": "success", "quality": "skipped"})
    with pytest.raises(ci_contract.CIContractError, match="outside the router result set"):
        ci_contract.verify_results(
            expected,
            {"scope-router": "success", "quality": "success", "policy": "success"},
        )


def test_transient_dependency_failure_retries_with_bounded_backoff(
    monkeypatch, tmp_path: Path
) -> None:
    calls = 0
    sleeps: list[int] = []
    command = ci_contract.CommandSpec(
        name="audit",
        argv=("audit",),
        retry_on_transient=True,
        retry_max_attempts=3,
        retry_delays_seconds=(2, 10),
    )

    def fake_run(argv, **kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(returncode=1, stdout="HTTP 503", stderr="")

    monkeypatch.setattr(ci_contract.subprocess, "run", fake_run)
    monkeypatch.setattr(ci_contract.time, "sleep", sleeps.append)

    with pytest.raises(ci_contract.CIContractError, match="BLOCKED_INFRASTRUCTURE"):
        ci_contract._run_command(command, argv=command.argv, cwd=tmp_path, env={}, group="audit")

    assert calls == 3
    assert sleeps == [2, 10]


def test_dependency_vulnerability_failure_is_not_retried(monkeypatch, tmp_path: Path) -> None:
    calls = 0
    command = ci_contract.CommandSpec(
        name="audit",
        argv=("audit",),
        retry_on_transient=True,
        retry_max_attempts=3,
        retry_delays_seconds=(2, 10),
    )

    def fake_run(argv, **kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(returncode=1, stdout="high severity vulnerability", stderr="")

    monkeypatch.setattr(ci_contract.subprocess, "run", fake_run)

    with pytest.raises(ci_contract.CIContractError, match="failed at audit"):
        ci_contract._run_command(command, argv=command.argv, cwd=tmp_path, env={}, group="audit")

    assert calls == 1
    assert not ci_contract._is_transient_failure("CWE-500: high severity vulnerability")
    assert not ci_contract._is_transient_failure("npm error CWE-500: high severity vulnerability")
    assert ci_contract._is_transient_failure("npm error code E503")


def test_workflow_routes_scope_cancels_only_pull_request_runs() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    deploy = (root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    assert "scripts/ci_contract.py route" in workflow
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
    assert "schedule:" in workflow
    assert "workflow_dispatch:" in workflow
    assert 'test "$TARGET_REF" = refs/heads/master' in workflow
    assert "group: production" in deploy
    assert "cancel-in-progress: false" in deploy


def test_local_gate_and_ci_router_share_the_same_decision() -> None:
    fixtures = [
        ["frontend/src/App.tsx"],
        ["backend/fitminiapp_api/schemas/example.py"],
        [".github/workflows/ci.yml"],
        ["docs/release-flow.md"],
        ["unknown/input.bin"],
    ]

    for paths in fixtures:
        assert pre_push_gate.classify_scope(paths) == ci_contract.classify_scope(paths)
