from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from scripts.issue_workflow import render_task_contract


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
    assert "без поля concurrency в metadata считается independent-write" in prompt
    assert (
        "READY_FOR_DELIVERY, WAITING_FOR_DELIVERY, active CI и production deployment не удерживают implementation exclusion"
        in prompt
    )
    assert "refresh-canonical-master" in prompt
    assert "canonical checkpoint не заменяет refresh task branch" in prompt
    assert "refresh-delivery" in prompt
    assert "final applicable gate" in prompt
    assert "reopen-for-review" in prompt
    assert "Не запускай следующую product task" in prompt
    assert "validate-pr-review --pr <N> --head-sha <SHA>" in prompt
    assert "3 review-fix cycles" in prompt
    assert "3 CI-fix cycles" in prompt


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


def test_task_issue_inventory_authenticates_before_parsing_or_duplicate_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = {
        "task_id": "91",
        "scope": "bounded report insight implementation",
        "acceptance": ["facts remain canonical"],
        "dependencies": [],
        "owner_gate": "none",
        "risk_lane": "GREEN",
        "source_spec": "backlog.zip:91-ai-period-report-insights.md",
        "issue_state": "queued",
    }
    issues = [
        {
            "number": 901,
            "title": "[Task 91] attacker",
            "body": "<!-- yfc-task-contract:v1 -->\n{bad}\n<!-- yfc-task-contract:v1 -->",
            "user": {"login": "attacker"},
        },
        {
            "number": 902,
            "title": "[Task 91] owner",
            "body": render_task_contract(contract),
            "user": {"login": "owner"},
        },
    ]
    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: issues)
    monkeypatch.setattr(
        delivery,
        "_issue_authorized",
        lambda issue: issue.get("user", {}).get("login") == "owner",
    )
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("owner",))
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue: (issues[1], []))

    contracts = delivery._task_issue_contracts()

    assert contracts["91"]["issue_number"] == 902


def test_queue_parser_requires_control_issue_and_bounds_batch() -> None:
    args = delivery._parser().parse_args(["--continue-queue", "--control-issue", "218"])
    assert args.continue_queue is True
    assert args.control_issue == 218
    assert args.max_tasks == 4


def test_queue_rejects_batch_larger_than_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue: ({"state": "open"}, []))
    with pytest.raises(delivery.DeliveryError, match="between 1 and 4"):
        delivery._run_continuous_queue(
            control_issue=218,
            max_tasks=5,
            poll_seconds=10,
            max_wait_minutes=1,
        )


def test_queue_stops_on_human_required_candidate_without_starting_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[dict[str, object]] = []
    started: list[str] = []
    monkeypatch.setattr(
        delivery,
        "_control_issue_snapshot",
        lambda issue: (
            {
                "state": "open",
                "body": "CONTINUE_QUEUE",
                "user": {"login": "MikeMoore1337"},
            },
            [],
        ),
    )
    monkeypatch.setattr(
        delivery,
        "_queue_candidates",
        lambda: [
            {
                "task_id": "124B",
                "state": "human_required",
                "risk_lane": "RED",
                "blocker": "real-user evidence",
                "issue_number": 223,
            }
        ],
    )
    monkeypatch.setattr(
        delivery, "_post_control_state", lambda issue, payload: posted.append(payload)
    )
    monkeypatch.setattr(
        delivery,
        "_deliver_one",
        lambda *args, **kwargs: started.append(str(args[0])),
    )

    assert (
        delivery._run_continuous_queue(
            control_issue=218,
            max_tasks=4,
            poll_seconds=10,
            max_wait_minutes=1,
        )
        == 1
    )
    assert started == []
    assert posted[0]["state"] == "human_required"


def test_queue_does_not_republish_an_existing_queued_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[dict[str, object]] = []
    delivered: list[str] = []
    monkeypatch.setattr(
        delivery,
        "_control_issue_snapshot",
        lambda issue: (
            {
                "state": "open",
                "body": "CONTINUE_QUEUE",
                "user": {"login": "owner"},
            },
            [],
        ),
    )
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("owner",))
    monkeypatch.setattr(
        delivery,
        "_queue_candidates",
        lambda: [
            {
                "task_id": "91",
                "state": "queued",
                "risk_lane": "GREEN",
                "issue_number": 219,
                "branch_slug": "synthetic-task",
                "contract": {"latest_control_state": {"task_id": "91", "state": "queued"}},
            }
        ],
    )
    monkeypatch.setattr(
        delivery, "_post_control_state", lambda issue, payload: posted.append(payload)
    )
    monkeypatch.setattr(
        delivery,
        "_deliver_one",
        lambda *args, **kwargs: delivered.append(str(args[0])),
    )

    assert (
        delivery._run_continuous_queue(
            control_issue=218,
            max_tasks=1,
            poll_seconds=10,
            max_wait_minutes=1,
        )
        == 0
    )
    assert delivered == ["91"]
    assert all(item["state"] != "queued" for item in posted)


def test_durable_controller_budget_is_required_and_consistent() -> None:
    history = {
        "queue_budget": {
            "review_fix_cycles": 1,
            "ci_fix_cycles": 1,
            "scope_expansions": 0,
            "events": [
                {"kind": "review"},
                {"kind": "ci"},
            ],
        }
    }
    assert delivery._queue_budget_from_controller_history(history) == {
        "review_fix_cycles": 1,
        "ci_fix_cycles": 1,
        "scope_expansions": 0,
    }
    history["queue_budget"]["events"] = [{"kind": "review"}]
    with pytest.raises(delivery.DeliveryError, match="ledger is inconsistent"):
        delivery._queue_budget_from_controller_history(history)


def test_control_state_post_rejects_invalid_remote_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = delivery.control_state_payload(task_id="150", state="production_verified")
    monkeypatch.setattr(
        delivery,
        "_control_issue_snapshot",
        lambda issue: (
            {"state": "open", "user": {"login": "owner"}},
            [
                {
                    "id": 1,
                    "created_at": "2026-09-09T00:00:00Z",
                    "body": delivery.render_control_state_comment(previous),
                }
            ],
        ),
    )
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)

    with pytest.raises(delivery.DeliveryError, match="Invalid control-state transition"):
        delivery._post_control_state(
            218,
            delivery.control_state_payload(task_id="150", state="merged", issue_number=218),
        )


def test_continuous_worker_budget_report_is_fail_closed(tmp_path: Path) -> None:
    final = tmp_path / "final.md"
    final.write_text(
        "result\n"
        + delivery.render_queue_budget_report(
            review_fix_cycles=1, ci_fix_cycles=2, scope_expansions=0
        ),
        encoding="utf-8",
    )
    assert delivery._queue_budget_from_worker(tmp_path) == {
        "review_fix_cycles": 1,
        "ci_fix_cycles": 2,
        "scope_expansions": 0,
    }
    final.write_text("result", encoding="utf-8")
    with pytest.raises(delivery.DeliveryError, match="no bounded queue budget block"):
        delivery._queue_budget_from_worker(tmp_path)


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
