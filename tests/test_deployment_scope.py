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
            ".github/workflows/deploy.yml",
            "codex-backlog/GLOBAL_RULES.md",
            "docs/deployment.md",
            "scripts/deployment_scope.py",
            "tests/test_deployment_scope.py",
        ]
    )

    assert decision["deploy_required"] is False
    assert decision["deploy_paths"] == []


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
