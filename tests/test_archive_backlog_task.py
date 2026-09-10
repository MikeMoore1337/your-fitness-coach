from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


def _load_module():
    script = Path(__file__).parents[1] / "scripts" / "archive_backlog_task.py"
    spec = importlib.util.spec_from_file_location("archive_backlog_task", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


archive_backlog_task = _load_module()


def _manifest(path: Path) -> None:
    path.write_text(
        json.dumps({"package": path.parent.name, "validation_errors": [], "files": []}) + "\n",
        encoding="utf-8",
    )


def _nested_backlog(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-b", "dev"],
        cwd=repository,
        check=True,
        text=True,
        capture_output=True,
    )
    parent = repository / "codex-backlog"
    backlog = parent / "telegram-core-release-backlog"
    tasks = backlog / "tasks"
    (tasks / "done").mkdir(parents=True)
    _manifest(parent / "MANIFEST.json")
    _manifest(backlog / "MANIFEST.json")
    (backlog / "GLOBAL_RULES.md").write_text("rules\n", encoding="utf-8")
    (tasks / "README.md").write_text(
        "# Tasks\n\n- [ ] `03` [Telegram task](03-notifications.md)\n", encoding="utf-8"
    )
    (tasks / "done" / "README.md").write_text("# Done\n", encoding="utf-8")
    (tasks / "03-notifications.md").write_text("task body\n", encoding="utf-8")
    archive_backlog_task.rebuild_manifests(backlog)
    return parent, backlog


def test_archive_task_updates_nested_and_parent_manifests(tmp_path: Path) -> None:
    parent, backlog = _nested_backlog(tmp_path)

    destination = archive_backlog_task.archive_task(backlog, "03-notifications.md")

    assert destination.read_text(encoding="utf-8") == "task body\n"
    assert not (backlog / "tasks" / "03-notifications.md").exists()
    index = (backlog / "tasks" / "README.md").read_text(encoding="utf-8")
    assert "- [x] `03` [Telegram task](done/03-notifications.md)" in index
    assert archive_backlog_task.validate_manifests(backlog) == []
    parent_paths = {
        entry["path"]
        for entry in json.loads((parent / "MANIFEST.json").read_text(encoding="utf-8"))["files"]
    }
    assert "telegram-core-release-backlog/tasks/done/03-notifications.md" in parent_paths
    assert "telegram-core-release-backlog/MANIFEST.json" in parent_paths


def test_archive_task_rejects_missing_index_link_without_moving_file(tmp_path: Path) -> None:
    _, backlog = _nested_backlog(tmp_path)
    (backlog / "tasks" / "README.md").write_text("# Tasks\n", encoding="utf-8")

    with pytest.raises(archive_backlog_task.ArchiveError, match="Expected one"):
        archive_backlog_task.archive_task(backlog, "03-notifications.md")

    assert (backlog / "tasks" / "03-notifications.md").is_file()
    assert not (backlog / "tasks" / "done" / "03-notifications.md").exists()


def test_archive_task_requires_finished_controller_history_when_contract_is_active(
    tmp_path: Path,
) -> None:
    parent, backlog = _nested_backlog(tmp_path)
    state_root = parent.parent / ".git" / "codex-task-sessions-v1"
    history = state_root / "history"
    history.mkdir(parents=True)
    (state_root / "contract.json").write_text('{"version": 1}\n', encoding="utf-8")

    with pytest.raises(archive_backlog_task.ArchiveError, match="controller finish"):
        archive_backlog_task.archive_task(backlog, "03-notifications.md")

    (history / "task-03.json").write_text(
        json.dumps({"task_id": "03", "state": "finished"}) + "\n",
        encoding="utf-8",
    )
    destination = archive_backlog_task.archive_task(backlog, "03-notifications.md")

    assert destination.is_file()


def test_archive_task_accepts_owner_authorized_superseded_lease(tmp_path: Path) -> None:
    parent, backlog = _nested_backlog(tmp_path)
    state_root = parent.parent / ".git" / "codex-task-sessions-v1"
    leases = state_root / "leases"
    leases.mkdir(parents=True)
    (state_root / "contract.json").write_text('{"version": 2}\n', encoding="utf-8")
    (leases / "task-03.json").write_text(
        json.dumps(
            {
                "task_id": "03",
                "mode": "write",
                "lifecycle_state": "superseded",
                "owner_authorized": True,
                "superseded_at": "2026-09-10T10:00:00Z",
                "superseded_reason": "owner selected a canonical replacement",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    destination = archive_backlog_task.archive_task(backlog, "03-notifications.md")

    assert destination.is_file()
    assert archive_backlog_task.validate_manifests(backlog) == []
