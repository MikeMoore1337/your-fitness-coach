import os
import sys
from pathlib import Path

import pytest
from scripts import ci_contract, local_checks


def test_child_environment_is_shared_and_uses_the_active_python(tmp_path: Path) -> None:
    environment = local_checks.child_environment(
        tmp_path,
        base={
            "PATH": "original-path",
            "PYTHONPATH": "original-pythonpath",
            "TEST_DATABASE_URL": "postgresql://isolated-test",
        },
    )

    path_entries = environment["PATH"].split(os.pathsep)
    assert path_entries[0] == str(Path(sys.executable).resolve().parent)
    assert environment["PYTHONPATH"].split(os.pathsep)[:2] == [
        str(tmp_path / "backend"),
        str(tmp_path / "bot"),
    ]
    assert environment["DATABASE_URL"] == "postgresql://isolated-test"
    assert environment["CI"] == "1"
    assert environment["APP_ENV"] == "test"
    assert Path(environment["TMP"]).is_relative_to(tmp_path / ".artifacts")


def test_child_environment_provisions_isolated_sqlite_when_no_test_database_is_given(
    tmp_path: Path,
) -> None:
    environment = local_checks.child_environment(tmp_path, base={})

    assert environment["DATABASE_URL"] == environment["TEST_DATABASE_URL"]
    assert environment["DATABASE_URL"].startswith("sqlite:///")
    assert (tmp_path / ".artifacts" / "runtime" / "tmp" / "local-checks").as_posix() in environment[
        "DATABASE_URL"
    ]


def test_child_environment_uses_a_distinct_runtime_directory_per_invocation(
    tmp_path: Path,
) -> None:
    first = local_checks.child_environment(tmp_path, base={})
    second = local_checks.child_environment(tmp_path, base={})

    assert first["DATABASE_URL"] != second["DATABASE_URL"]
    assert Path(first["TMP"]).parent == Path(second["TMP"]).parent
    assert Path(first["TMP"]).parent.name == "local-checks"


def test_child_environment_rejects_production_mode(tmp_path: Path) -> None:
    with pytest.raises(local_checks.LocalChecksError, match="APP_ENV=prod"):
        local_checks.child_environment(tmp_path, base={"APP_ENV": "production"})


def test_current_route_includes_staged_unstaged_and_untracked_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_git(root: Path, *args: str) -> str:
        del root
        if args == ("rev-parse", "origin/master"):
            return "base-sha"
        if args == ("rev-parse", "HEAD"):
            return "head-sha"
        if args == ("diff", "--name-only", "base-sha"):
            return "frontend/src/App.tsx\n"
        if args == ("ls-files", "--others", "--exclude-standard"):
            return "frontend/src/new-feature.tsx\n"
        raise AssertionError(args)

    monkeypatch.setattr(local_checks, "_git", fake_git)

    route = local_checks._current_route(tmp_path)

    assert route["paths"] == ["frontend/src/App.tsx", "frontend/src/new-feature.tsx"]
    assert route["profile"] == "frontend"
    assert "frontend-checks" in route["required_groups"]


def test_explicit_groups_do_not_require_git_routing(tmp_path: Path) -> None:
    assert local_checks.selected_groups(tmp_path, requested=("quality", "workflow-config")) == (
        "quality",
        "workflow-config",
    )


def test_full_route_is_explicit_and_fast_frontend_route_omits_expensive_groups(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    route = {
        "profile": "frontend",
        "required_groups": ["quality", "frontend-checks", "frontend-e2e"],
    }
    monkeypatch.setattr(local_checks, "_current_route", lambda root: route)

    assert local_checks.selected_groups(tmp_path) == ("quality", "frontend-checks")
    assert local_checks.selected_groups(tmp_path, full=True) == (
        "quality",
        "frontend-checks",
        "frontend-e2e",
    )
    assert "frontend-e2e" not in local_checks.FAST_GROUPS_BY_PROFILE["frontend"]
    assert ci_contract.COMMAND_GROUPS["frontend-e2e"].name == "frontend-e2e"


def test_explicit_and_full_route_cannot_be_combined(tmp_path: Path) -> None:
    with pytest.raises(local_checks.LocalChecksError, match="not both"):
        local_checks.selected_groups(tmp_path, requested=("quality",), full=True)
