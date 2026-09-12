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
        "controller": (root / "scripts" / "task_session.py").read_text(encoding="utf-8"),
        "launcher": (root / "scripts" / "run_task_delivery.py").read_text(encoding="utf-8"),
        "dependabot": (root / ".github" / "dependabot.yml").read_text(encoding="utf-8"),
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
    assert "Validate task provenance or trusted Dependabot identity" in ci
    assert "TASK_PROVENANCE_RESULT: ${{ needs.task-provenance.result }}" in ci
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


def test_dependabot_allows_only_patch_minor_version_updates() -> None:
    sources = _sources()
    config = yaml.safe_load(sources["dependabot"])

    assert config["version"] == 2
    updates = config["updates"]
    assert len(updates) == 5
    expected_update_types = {
        "version-update:semver-minor",
        "version-update:semver-patch",
    }

    for update in updates:
        assert update["allow"] == [
            {"dependency-name": "*", "update-types": sorted(expected_update_types)}
        ]
        for group in update.get("groups", {}).values():
            if group.get("applies-to", "version-updates") == "version-updates":
                assert set(group.get("update-types", ())) <= {"minor", "patch"}
        assert "ignore" not in update

    root = Path(__file__).resolve().parents[1]
    dev_lock = root / "backend" / "requirements-dev.txt"
    assert dev_lock.is_file()
    assert not (root / "backend" / "requirements.txt").exists()
    dev_lock_text = dev_lock.read_text(encoding="utf-8")
    for package in ("pytest==", "mypy==", "ruff==", "pre-commit=="):
        assert package in dev_lock_text


def test_deploy_is_master_only_immutable_bundle_flow_without_vps_git_checkout() -> None:
    sources = _sources()
    deploy = sources["deploy"]
    deploy_script = (
        Path(__file__).resolve().parents[1] / "scripts" / "deploy_production.sh"
    ).read_text(encoding="utf-8")

    assert "workflows: [CI]" in deploy
    assert "branches: [master]" in deploy
    assert "sync-dev:" not in deploy
    assert "actions/create-github-app-token" not in deploy
    assert "git fetch" not in deploy
    assert "git reset" not in deploy
    assert "git rev-parse" not in deploy
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
    assert "request_codex_review" in controller
    assert "validate_codex_review" in controller
    assert "CODEX_REVIEW_MAX_ROUNDS = 2" in controller
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
    assert "Codex review" in launcher
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
