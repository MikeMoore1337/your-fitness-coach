from pathlib import Path

import pytest
from scripts import deployment_contract


def test_image_refs_are_derived_from_one_repository_contract() -> None:
    assert (
        deployment_contract.image_ref("MikeMoore1337/Your-Fitness-Coach", "backend", "a" * 40)
        == "ghcr.io/mikemoore1337/your-fitness-coach-backend:" + "a" * 40
    )
    assert deployment_contract.local_tag("bot", "b" * 40) == "yfc-bot:ci-" + "b" * 12
    assert deployment_contract.image_ref("owner/repo", "hermes-worker", "c" * 40) == (
        "ghcr.io/owner/repo-hermes-worker:" + "c" * 40
    )


@pytest.mark.parametrize("kind", ["api", "frontend", ""])
def test_unknown_image_kind_is_rejected(kind: str) -> None:
    with pytest.raises(deployment_contract.DeploymentContractError):
        deployment_contract.image_ref("owner/repo", kind, "a" * 40)


def test_namespace_mismatch_fixture_is_rejected(tmp_path: Path) -> None:
    ci = tmp_path / "ci.yml"
    deploy = tmp_path / "deploy.yml"
    compose = tmp_path / "compose.yml"
    script = tmp_path / "deploy.sh"
    ci.write_text("scripts/deployment_contract.py refs\n", encoding="utf-8")
    deploy.write_text(
        "scripts/deployment_contract.py refs\nGHCR_BACKEND_IMAGE=wrong\n", encoding="utf-8"
    )
    compose.write_text("image: ${BACKEND_IMAGE}\nimage: ${BOT_IMAGE}\n", encoding="utf-8")
    script.write_text("BACKEND_IMAGE BOT_IMAGE\n", encoding="utf-8")
    with pytest.raises(deployment_contract.DeploymentContractError, match="independent"):
        deployment_contract.validate_files(
            ci_workflow=ci,
            deploy_workflow=deploy,
            compose=compose,
            deploy_script=script,
        )


def test_deploy_bundle_includes_migration_sources() -> None:
    root = Path(__file__).resolve().parents[1]
    deploy = (root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    assert "git archive" in deploy
    assert "backend/alembic/versions" in deploy


def test_repair_bundle_includes_the_complete_trusted_capacity_gate() -> None:
    root = Path(__file__).resolve().parents[1]
    deploy = (root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    repair_bundle = deploy.split("tooling_paths=(", 1)[1].split(")", 1)[0]

    # The host orchestrator must never be copied from a newer tooling
    # revision without its trusted collector and preflight implementation.
    for path in (
        "scripts/zero_downtime_deploy.py",
        "scripts/connection_budget_preflight.py",
        "scripts/trusted_runtime_collector.py",
        "scripts/trusted_legacy_pg_snapshot.py",
    ):
        assert path in repair_bundle


def test_trusted_postgres_preflight_runs_before_any_production_config_mutation() -> None:
    root = Path(__file__).resolve().parents[1]
    wrapper = (root / "scripts" / "deploy_production.sh").read_text(encoding="utf-8")
    orchestrator = (root / "scripts" / "zero_downtime_deploy.py").read_text(encoding="utf-8")
    marker = 'python3 scripts/zero_downtime_deploy.py "$capacity_command"'
    assert wrapper.count(marker) == 1
    first_mutation = 'echo "Enabling browser OAuth'
    assert wrapper.index(marker) < wrapper.index(first_mutation)
    assert '"capacity-check-single-slot"' in orchestrator
    assert "capacity_command=capacity-check-single-slot" in wrapper
    assert 'if args.command == "capacity-check":' in orchestrator
    assert 'with _stage(evidence, "connection_budget_preflight"):' in orchestrator
    assert orchestrator.count("_trusted_connection_budget_preflight(config)") >= 4


def test_release_dispatch_keeps_native_concurrency_and_exact_ci_evidence() -> None:
    root = Path(__file__).resolve().parents[1]
    deploy = (root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in deploy
    assert "group: production" in deploy
    assert "cancel-in-progress: false" in deploy
    assert "scripts/deployment_scope.py" in deploy
    assert "github.workflow_sha" not in deploy
    assert "actions/runs/$CI_RUN_ID" in deploy
    assert ".head_sha == $sha" in deploy
    assert '.conclusion == "success"' in deploy
    assert "task_session.py" not in deploy
