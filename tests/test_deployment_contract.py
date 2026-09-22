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
