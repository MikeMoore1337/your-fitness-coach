from scripts.deployment_scope import classify_paths, main


def test_application_paths_require_deploy() -> None:
    decision = classify_paths(
        [
            "backend/fitminiapp_api/main.py",
            "frontend/src/App.tsx",
            "backend/alembic/versions/0001_example.py",
        ]
    )

    assert decision["deploy_required"] is True
    assert decision["deploy_paths"] == [
        "backend/alembic/versions/0001_example.py",
        "backend/fitminiapp_api/main.py",
        "frontend/src/App.tsx",
    ]


def test_docs_governance_tests_and_ci_only_do_not_deploy() -> None:
    decision = classify_paths(
        [
            "AGENTS.md",
            ".codex/config.toml",
            ".github/workflows/deploy.yml",
            "codex-backlog/GLOBAL_RULES.md",
            "docs/deployment.md",
            "scripts/deployment_scope.py",
            "tests/test_deployment_scope.py",
        ]
    )

    assert decision["deploy_required"] is False
    assert decision["deploy_paths"] == []


def test_make_feature_process_evidence_does_not_deploy() -> None:
    evidence_paths = [
        ".make-feature/issue-848-v11-db-01/00-index.md",
        ".make-feature/issue-848-v11-db-01/01-request.md",
        ".make-feature/issue-848-v11-db-01/02-solution.md",
        ".make-feature/issue-848-v11-db-01/03-verification.md",
    ]

    decision = classify_paths(evidence_paths)

    assert decision["deploy_required"] is False
    assert decision["deploy_paths"] == []
    assert decision["no_deploy_paths"] == evidence_paths


def test_make_feature_evidence_cannot_hide_runtime_changes() -> None:
    decision = classify_paths(
        [
            ".make-feature/issue-848-v11-db-01/03-verification.md",
            "backend/fitminiapp_api/main.py",
        ]
    )

    assert decision["deploy_required"] is True
    assert decision["deploy_paths"] == ["backend/fitminiapp_api/main.py"]


def test_host_delivery_tooling_does_not_redeploy_unchanged_application() -> None:
    decision = classify_paths(
        [
            ".github/workflows/deploy.yml",
            "scripts/deploy_production.sh",
            "scripts/deployment_contract.py",
            "scripts/production_host_cleanup.py",
            "scripts/production_provenance.py",
            "scripts/zero_downtime_deploy.py",
        ]
    )

    assert decision["deploy_required"] is False
    assert decision["deploy_paths"] == []


def test_runtime_scripts_copied_into_images_require_deploy() -> None:
    decision = classify_paths(
        ["backend/Dockerfile", "scripts/check_deployment.py", "scripts/fetch_rapidocr_models.py"]
    )

    assert decision["deploy_required"] is True
    assert decision["deploy_paths"] == [
        "backend/Dockerfile",
        "scripts/check_deployment.py",
        "scripts/fetch_rapidocr_models.py",
    ]


def test_deploy_directory_remains_deployable() -> None:
    decision = classify_paths(["deploy/backup/production-pull.config.json"])

    assert decision["deploy_required"] is True
    assert decision["deploy_paths"] == ["deploy/backup/production-pull.config.json"]


def test_v11_rec_01_full_diff_is_no_deploy() -> None:
    decision = classify_paths(
        [
            "docs/operations/v11-rec-01-off-host-backup-recovery.md",
            "docs/operations/v11-rec-01-off-host-backup-recovery/windows-pull-task.example.xml",
            "docs/operations/v11-rec-01-off-host-backup-recovery/windows-pull.config.example.json",
            "scripts/backup_manifest.py",
            "scripts/ci_contract.py",
            "scripts/db_maintenance.py",
            "scripts/windows_backup_pull.ps1",
            "scripts/windows_backup_pull_selftest.ps1",
            "tests/test_backup_manifest.py",
            "tests/test_ci_contract.py",
            "tests/test_deployment_scope.py",
        ]
    )

    assert decision["deploy_required"] is False
    assert decision["deploy_paths"] == []
    assert decision["no_deploy_paths"] == decision["changed_paths"]


def test_unknown_non_governance_path_is_conservative() -> None:
    decision = classify_paths(["config/production-feature.toml"])

    assert decision["deploy_required"] is True


def test_path_normalization_is_deterministic() -> None:
    decision = classify_paths([r".\docs\deployment.md", "./AGENTS.md", "docs/deployment.md"])

    assert decision["changed_paths"] == ["AGENTS.md", "docs/deployment.md"]


def test_cli_accepts_repeated_stateless_path_inputs(capsys) -> None:
    assert main(["--path", "docs/deployment.md", "--path", "backend/app.py", "--json"]) == 0
    output = capsys.readouterr().out
    assert '"deploy_required": true' in output
