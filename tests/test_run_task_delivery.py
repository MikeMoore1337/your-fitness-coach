from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


def _load_module():
    script = Path(__file__).parents[1] / "scripts" / "run_task_delivery.py"
    spec = importlib.util.spec_from_file_location("run_task_delivery", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


delivery = _load_module()


def test_run_scopes_git_safety_to_exact_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["args"] = args[0]
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(delivery.subprocess, "run", fake_run)

    delivery._run(["git", "rev-parse", "--git-common-dir"], cwd=tmp_path)

    command = observed["args"]
    assert command[:3] == ["git", "-c", f"safe.directory={tmp_path.resolve().as_posix()}"]
    if delivery.os.name == "nt":
        assert command[3:5] == ["-c", "core.longpaths=true"]


def test_worker_prompt_carries_one_launch_delivery_contract() -> None:
    started = {
        "lease": {
            "canonical_task_path": "D:/repo/codex-backlog/tasks/131-delivery.md",
            "branch": "task/131-delivery",
            "worktree": "D:/repo/.artifacts/worktrees/131-delivery",
        },
        "prompt": "controller evidence",
    }

    prompt = delivery._worker_prompt("131", started)

    assert "standing authorization" in prompt
    assert (
        "task branch -> local PRE_PUSH_CI_PASS -> PR master -> exact master CI -> production"
        in prompt
    )
    assert "BLOCKER/HIGH/MEDIUM" in prompt
    assert "Не запрашивай generic approval" in prompt
    assert "READY_FOR_DELIVERY" in prompt
    assert "WAITING_FOR_DELIVERY" in prompt
    assert "refresh-canonical-master" in prompt
    assert "canonical checkpoint не заменяет refresh task branch" in prompt
    assert "refresh-delivery" in prompt
    assert "final applicable gate" in prompt
    assert "reopen-for-review" in prompt
    assert "Не запускай следующую product task" in prompt


def test_only_live_lane_contention_is_retried() -> None:
    assert delivery._is_transient_start_error("task session error: Coordination state is locked")
    assert not delivery._is_transient_start_error(
        "task session error: delivery lane is occupied by Task 140"
    )
    assert not delivery._is_transient_start_error(
        "task session error: active production deployment occupies the delivery lane"
    )
    assert not delivery._is_transient_start_error("main dev worktree is dirty")
    assert not delivery._is_transient_start_error("missing task document")


def test_launcher_starts_without_waiting_for_busy_delivery_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        args: list[str], *, cwd: Path = delivery.REPOSITORY_ROOT, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        del cwd, check
        calls.append(args)
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "lease": {
                        "canonical_task_path": "D:/repo/codex-backlog/tasks/240-task.md",
                        "branch": "task/240-task",
                        "worktree": "D:/repo/.artifacts/worktrees/240-task",
                    }
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(delivery, "_run", fake_run)

    started = delivery._start(
        "240",
        session_label="parallel-start",
        poll_seconds=10,
        max_wait_minutes=1,
        offline=True,
    )

    assert started["lease"]["branch"] == "task/240-task"
    assert len(calls) == 1
    assert "--offline" in calls[0]


def test_task_id_normalization_is_strict() -> None:
    assert delivery._normalize_task_id("110a") == "110A"

    try:
        delivery._normalize_task_id("task-110A")
    except delivery.DeliveryError as error:
        assert "Invalid task ID" in str(error)
    else:
        raise AssertionError("invalid task ID was accepted")


def test_verify_closeout_requires_archive_and_manifest_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backlog = tmp_path / "codex-backlog"
    source = backlog / "tasks" / "131-delivery.md"
    destination = backlog / "tasks" / "done" / source.name
    destination.parent.mkdir(parents=True)
    destination.write_text("done", encoding="utf-8")
    started = {"lease": {"canonical_task_path": str(source)}}
    observed: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["args"] = args[0]
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(delivery, "_run", fake_run)

    delivery._verify_closeout(started)

    assert observed["args"][-2:] == ["--backlog", str(backlog)]


def test_verify_closeout_rejects_finished_but_unarchived_task(tmp_path: Path) -> None:
    source = tmp_path / "codex-backlog" / "tasks" / "131-delivery.md"
    source.parent.mkdir(parents=True)
    source.write_text("pending", encoding="utf-8")

    with pytest.raises(delivery.DeliveryError, match="was not archived"):
        delivery._verify_closeout({"lease": {"canonical_task_path": str(source)}})


def test_delivery_artifacts_are_task_scoped_and_final_result_is_preserved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)

    artifacts = delivery._artifact_root("133")
    assert artifacts.relative_to(tmp_path / ".artifacts").parts[:4] == (
        "tasks",
        "133",
        "temporary",
        "delivery",
    )
    (artifacts / "events.jsonl").write_text('{"stage":"worker"}\n', encoding="utf-8")
    (artifacts / "final.md").write_text("terminal result\n", encoding="utf-8")

    result = delivery._cleanup_delivery_artifacts("133", artifacts)

    assert result["status"] == "completed"
    assert result["removed_count"] == 1
    assert not artifacts.exists()
    evidence = tmp_path / ".artifacts" / "tasks" / "133" / "evidence" / "delivery"
    assert [path.read_text(encoding="utf-8") for path in evidence.glob("*-final.md")] == [
        "terminal result\n"
    ]


def test_delivery_cleanup_refuses_artifacts_outside_exact_task_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    outside = tmp_path / ".artifacts" / "temporary" / "delivery"
    outside.mkdir(parents=True)

    with pytest.raises(delivery.DeliveryError, match="outside exact task root"):
        delivery._cleanup_delivery_artifacts("133", outside)
