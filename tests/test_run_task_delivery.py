from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
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


def _claim_process_instance(*, boot_id: str = "a" * 32, start_ticks: str = "1") -> dict[str, str]:
    return {"kind": "linux-proc", "boot_id": boot_id, "start_ticks": start_ticks}


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


def test_worker_launch_passes_active_delivery_artifacts_to_child(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "worktree"
    artifacts = tmp_path / "artifacts"
    worktree.mkdir()
    artifacts.mkdir()
    observed: dict[str, Any] = {}

    monkeypatch.setenv("YFC_ACTIVE_DELIVERY_ARTIFACTS", "C:/untrusted/stale-path")
    monkeypatch.setattr(delivery.shutil, "which", lambda name: "codex")
    monkeypatch.setattr(delivery, "_worker_prompt", lambda *args, **kwargs: "prompt")

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["args"] = args
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(delivery.subprocess, "run", fake_run)

    assert (
        delivery._launch_worker(
            "150",
            {"lease": {"worktree": str(worktree)}},
            artifacts,
        )
        == 0
    )
    assert observed["kwargs"]["env"]["YFC_ACTIVE_DELIVERY_ARTIFACTS"] == str(artifacts.resolve())


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


def test_issue_authorization_normalizes_connector_bot_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery, "_github_slug", lambda: "MikeMoore1337/your-fitness-coach")
    issue = {"user": {"login": "chatgpt-codex-connector[bot]"}}

    assert delivery._issue_authorized(issue) is True
    assert "chatgpt-codex-connector" in delivery._trusted_issue_logins(issue)


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


def test_queue_candidates_excludes_pending_bug_documents(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks_root = tmp_path / "codex-backlog" / "tasks"
    bugs_root = tmp_path / "codex-backlog" / "bugs" / "pending"
    tasks_root.mkdir(parents=True)
    bugs_root.mkdir(parents=True)
    (tasks_root / "1-product-task.md").write_text("product", encoding="utf-8")
    (bugs_root / "2-pending-bug.md").write_text("bug", encoding="utf-8")

    class FakeStore:
        def delivery_state(self) -> dict[str, Any]:
            return {}

        def all_leases(self) -> list[dict[str, Any]]:
            return []

    class FakeController:
        def __init__(self, repository: object) -> None:
            del repository
            self.store = FakeStore()

        def _completed_dependency_ids(self) -> set[str]:
            return set()

    documents_seen: list[str] = []

    def fake_find_task_document(root: Path, task_id: str) -> SimpleNamespace:
        documents_seen.append(task_id)
        return SimpleNamespace(
            task_id=task_id,
            executable=True,
            slug=f"task-{task_id}",
            path=root / "codex-backlog" / "tasks" / f"{task_id}-product-task.md",
        )

    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(delivery, "GitRepository", lambda root: object())
    monkeypatch.setattr(delivery, "TaskController", FakeController)
    monkeypatch.setattr(delivery, "find_task_document", fake_find_task_document)
    monkeypatch.setattr(
        delivery,
        "_task_issue_contracts",
        lambda: {
            "1": {
                "task_id": "1",
                "issue_number": 101,
                "issue_state": "open",
                "latest_control_state": {"state": "queued"},
                "dependencies": [],
                "risk_lane": "GREEN",
                "owner_gate": "none",
            }
        },
    )

    candidates = delivery._queue_candidates()

    assert documents_seen == ["1"]
    assert [candidate["task_id"] for candidate in candidates] == ["1"]


def test_queue_parser_requires_control_issue_and_bounds_batch() -> None:
    args = delivery._parser().parse_args(["--continue-queue", "--control-issue", "218"])
    assert args.continue_queue is True
    assert args.control_issue == 218
    assert args.max_tasks == 4


def test_continuous_queue_claim_serializes_the_whole_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_dir = tmp_path / "git-common"
    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_dir)
    claim_path = common_dir / "codex-task-sessions-v1" / "continuous-queue.lock"

    with delivery._continuous_queue_claim(218):
        assert claim_path.is_file()
        with (
            pytest.raises(delivery.DeliveryError, match="already has an active owner"),
            delivery._continuous_queue_claim(218),
        ):
            pass

    assert not claim_path.exists()


def test_continuous_queue_claim_recovers_dead_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_dir = tmp_path / "git-common"
    claim_path = common_dir / "codex-task-sessions-v1" / "continuous-queue.lock"
    claim_path.parent.mkdir(parents=True)
    claim_path.write_text(
        json.dumps(
            {
                "control_issue": 218,
                "pid": 424242,
                "process_instance": _claim_process_instance(),
                "started_at": "2026-09-09T08:00:00+00:00",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_dir)
    monkeypatch.setattr(delivery, "_queue_owner_process_instance", lambda pid: None)
    monkeypatch.setattr(delivery, "_current_process_instance_identity", _claim_process_instance)

    with delivery._continuous_queue_claim(218):
        assert claim_path.is_file()
        assert "424242" not in claim_path.read_text(encoding="utf-8")

    assert not claim_path.exists()


def test_continuous_queue_claim_reclaims_dead_owner_via_atomic_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_dir = tmp_path / "git-common"
    claim_path = common_dir / "codex-task-sessions-v1" / "continuous-queue.lock"
    claim_path.parent.mkdir(parents=True)
    claim_path.write_text(
        json.dumps(
            {
                "control_issue": 218,
                "pid": 424242,
                "process_instance": _claim_process_instance(),
                "started_at": "2026-09-09T08:00:00+00:00",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    renames: list[tuple[Path, Path]] = []
    real_rename = delivery.os.rename

    def record_rename(source: str | Path, destination: str | Path) -> None:
        renames.append((Path(source), Path(destination)))
        real_rename(source, destination)

    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_dir)
    monkeypatch.setattr(delivery, "_queue_owner_process_instance", lambda pid: None)
    monkeypatch.setattr(delivery, "_current_process_instance_identity", _claim_process_instance)
    monkeypatch.setattr(delivery.os, "rename", record_rename)

    with delivery._continuous_queue_claim(218):
        assert claim_path.is_file()

    assert len(renames) == 1
    assert renames[0][0] == claim_path
    assert renames[0][1].name.startswith("continuous-queue.lock.stale-")
    assert not claim_path.exists()
    assert not renames[0][1].exists()


def test_continuous_queue_claim_reclaims_pid_reuse_with_different_process_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_dir = tmp_path / "git-common"
    claim_path = common_dir / "codex-task-sessions-v1" / "continuous-queue.lock"
    claim_path.parent.mkdir(parents=True)
    claim_path.write_text(
        json.dumps(
            {
                "control_issue": 218,
                "pid": 424242,
                "process_instance": _claim_process_instance(),
                "started_at": "2026-09-09T08:00:00+00:00",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_dir)
    monkeypatch.setattr(
        delivery,
        "_queue_owner_process_instance",
        lambda pid: _claim_process_instance(boot_id="b" * 32, start_ticks="2"),
    )

    with delivery._continuous_queue_claim(218):
        assert claim_path.is_file()
        assert "424242" not in claim_path.read_text(encoding="utf-8")

    assert not claim_path.exists()


def test_continuous_queue_claim_keeps_corrupted_claim_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_dir = tmp_path / "git-common"
    claim_path = common_dir / "codex-task-sessions-v1" / "continuous-queue.lock"
    claim_path.parent.mkdir(parents=True)
    claim_path.write_text("partial claim", encoding="utf-8")
    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_dir)

    with (
        pytest.raises(delivery.DeliveryError, match="claim is corrupted"),
        delivery._continuous_queue_claim(218),
    ):
        pass

    assert claim_path.read_text(encoding="utf-8") == "partial claim"


def test_continuous_queue_claim_rejects_missing_process_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_dir = tmp_path / "git-common"
    claim_path = common_dir / "codex-task-sessions-v1" / "continuous-queue.lock"
    claim_path.parent.mkdir(parents=True)
    claim_path.write_text(
        json.dumps(
            {
                "control_issue": 218,
                "pid": 424242,
                "started_at": "2026-09-09T08:00:00+00:00",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_dir)
    monkeypatch.setattr(delivery, "_current_process_instance_identity", _claim_process_instance)

    with (
        pytest.raises(delivery.DeliveryError, match="invalid process identity"),
        delivery._continuous_queue_claim(218),
    ):
        pass

    assert "process_instance" not in json.loads(claim_path.read_text(encoding="utf-8"))


def test_queue_owner_liveness_rejects_ambiguous_os_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_ambiguous_error(pid: int, signal: int) -> None:
        raise OSError("ambiguous liveness result")

    monkeypatch.setattr(delivery.os, "name", "posix")
    monkeypatch.setattr(delivery.os, "kill", raise_ambiguous_error)

    with pytest.raises(delivery.DeliveryError, match="cannot verify continuous queue owner PID"):
        delivery._queue_owner_is_alive(424242)


def test_queue_owner_liveness_uses_non_destructive_windows_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[int] = []

    monkeypatch.setattr(delivery.os, "name", "nt")
    monkeypatch.setattr(
        delivery,
        "_windows_queue_owner_is_alive",
        lambda pid: observed.append(pid) or True,
    )

    def unexpected_signal_probe(pid: int, signal: int) -> None:
        raise AssertionError("Windows liveness must not call os.kill")

    monkeypatch.setattr(delivery.os, "kill", unexpected_signal_probe)

    assert delivery._queue_owner_is_alive(424242) is True
    assert observed == [424242]


def test_queue_owner_identity_supports_macos_without_proc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        if args[0] == "ps":
            return subprocess.CompletedProcess(
                args, 0, stdout="Wed Sep  9 10:00:00 2026\n", stderr=""
            )
        assert args == ["sysctl", "-n", "kern.boottime"]
        return subprocess.CompletedProcess(args, 0, stdout="{ sec = 123, usec = 456 }\n", stderr="")

    monkeypatch.setattr(delivery.os, "name", "posix")
    monkeypatch.setattr(delivery.sys, "platform", "darwin")
    monkeypatch.setattr(delivery.subprocess, "run", fake_run)

    assert delivery._queue_owner_process_instance(424242) == {
        "kind": "macos",
        "boot_time": "{ sec = 123, usec = 456 }",
        "start_time": "Wed Sep 9 10:00:00 2026",
    }
    assert [call[0] for call in calls] == [
        ["ps", "-p", "424242", "-o", "lstart="],
        ["sysctl", "-n", "kern.boottime"],
    ]
    assert all(call[1]["shell"] is False and call[1]["timeout"] == 5 for call in calls)


def test_queue_rejects_batch_larger_than_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue: ({"state": "open"}, []))
    with pytest.raises(delivery.DeliveryError, match="between 1 and 4"):
        delivery._run_continuous_queue(
            control_issue=218,
            max_tasks=5,
            poll_seconds=10,
            max_wait_minutes=1,
        )


def test_queue_honors_durable_queue_stop_before_candidate_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = delivery.control_state_payload(
        task_id="150",
        state="human_required",
        issue_number=219,
        terminal_verdict="queue_stop",
        blocker="Task 91: worker budget mismatch after finish",
    )
    monkeypatch.setattr(
        delivery,
        "_control_issue_snapshot",
        lambda issue: (
            {
                "state": "open",
                "body": "CONTINUE_QUEUE",
                "user": {"login": "owner"},
                "title": "[Task 150] queue control",
            },
            [
                {
                    "id": 1,
                    "created_at": "2026-09-09T06:00:00Z",
                    "user": {"login": "owner"},
                    "body": delivery.render_control_state_comment(stop),
                }
            ],
        ),
    )
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("owner",))
    monkeypatch.setattr(
        delivery,
        "_queue_candidates",
        lambda: (_ for _ in ()).throw(AssertionError("candidate scan must not run")),
    )

    with pytest.raises(delivery.DeliveryError, match="durably stopped"):
        delivery._run_continuous_queue(
            control_issue=218,
            max_tasks=1,
            poll_seconds=10,
            max_wait_minutes=1,
        )


def test_queue_stop_requires_authenticated_continue_to_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = delivery.control_state_payload(
        task_id="150",
        state="human_required",
        issue_number=219,
        terminal_verdict="queue_stop",
        blocker="Task 91: cleanup failed",
    )
    resumed = delivery.control_state_payload(
        task_id="150",
        state="in_progress",
        issue_number=218,
    )
    monkeypatch.setattr(
        delivery,
        "_control_issue_snapshot",
        lambda issue: (
            {
                "state": "open",
                "body": "The control contract supports CONTINUE_QUEUE.",
                "user": {"login": "owner"},
                "title": "[Task 150] queue control",
            },
            [
                {
                    "id": 1,
                    "created_at": "2026-09-09T06:00:00Z",
                    "user": {"login": "owner"},
                    "body": delivery.render_control_state_comment(stop),
                },
                {
                    "id": 2,
                    "created_at": "2026-09-09T07:00:00Z",
                    "user": {"login": "owner"},
                    "body": "CONTINUE_QUEUE",
                },
                {
                    "id": 3,
                    "created_at": "2026-09-09T07:01:00Z",
                    "user": {"login": "owner"},
                    "body": delivery.render_control_state_comment(resumed),
                },
            ],
        ),
    )
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("owner",))

    _, _, authorization = delivery._queue_authorization_snapshot(218)

    assert authorization["active"] is True
    assert "queue_stop" not in authorization


def test_post_queue_stop_projects_failure_to_central_control_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_payloads: list[tuple[int, dict[str, object]]] = []
    monkeypatch.setattr(
        delivery,
        "_control_issue_snapshot",
        lambda issue: (
            {"title": "[Task 150] queue control", "state": "open"},
            [],
        ),
    )
    monkeypatch.setattr(
        delivery,
        "_post_control_state",
        lambda issue, payload: stop_payloads.append((issue, dict(payload))),
    )

    delivery._post_queue_stop(
        218,
        task_id="91",
        status_issue=219,
        branch="task/91-period-report-insights",
        blocker="HUMAN_REQUIRED: worker budget mismatch after finish",
    )

    assert stop_payloads == [
        (
            218,
            {
                "version": 1,
                "task_id": "150",
                "state": "human_required",
                "issue_number": 219,
                "branch": "task/91-period-report-insights",
                "pr_number": None,
                "head_sha": None,
                "terminal_verdict": "queue_stop",
                "blocker": ("Task 91: HUMAN_REQUIRED: worker budget mismatch after finish"),
                "review_fix_cycles": 0,
                "ci_fix_cycles": 0,
                "scope_expansions": 0,
            },
        )
    ]


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


def test_continuous_cleanup_failure_posts_central_queue_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifacts = tmp_path / "delivery"
    artifacts.mkdir()
    (artifacts / "final.md").write_text(
        delivery.render_queue_budget_report(
            review_fix_cycles=0, ci_fix_cycles=0, scope_expansions=0
        ),
        encoding="utf-8",
    )
    started = {
        "lease": {
            "branch": "task/91-synthetic-task",
            "worktree": str(tmp_path / "worktree"),
        }
    }
    history = {
        "state": "finished",
        "pr_number": 223,
        "deployed_sha": "a" * 40,
        "queue_budget": {
            "review_fix_cycles": 0,
            "ci_fix_cycles": 0,
            "scope_expansions": 0,
            "events": [],
        },
    }
    queue_stops: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(delivery, "_start", lambda *args, **kwargs: started)
    monkeypatch.setattr(delivery, "_artifact_root", lambda task_id: artifacts)
    monkeypatch.setattr(delivery, "_launch_worker", lambda *args, **kwargs: 0)
    monkeypatch.setattr(delivery, "_history", lambda task_id: history)
    monkeypatch.setattr(delivery, "_verify_closeout", lambda started: None)
    monkeypatch.setattr(
        delivery,
        "_cleanup_delivery_artifacts",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            delivery.DeliveryError("cleanup could not remove delivery artifacts")
        ),
    )
    monkeypatch.setattr(delivery, "_post_control_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        delivery,
        "_post_queue_stop",
        lambda *args, **kwargs: queue_stops.append((args, kwargs)),
    )

    with pytest.raises(delivery.DeliveryError, match="cleanup could not"):
        delivery._deliver_one(
            "91",
            session_label="test",
            poll_seconds=10,
            max_wait_minutes=1,
            offline=False,
            control_issue=218,
            state_issue=219,
            issue_contract={"dependencies": []},
        )

    assert queue_stops
    assert queue_stops[0][0] == (218,)
    assert queue_stops[0][1]["task_id"] == "91"


def test_continuous_worker_exit_after_finish_posts_central_queue_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifacts = tmp_path / "delivery"
    artifacts.mkdir()
    started = {
        "lease": {
            "branch": "task/91-synthetic-task",
            "worktree": str(tmp_path / "worktree"),
        }
    }
    history = {"state": "finished"}
    queue_stops: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    status_updates: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(delivery, "_start", lambda *args, **kwargs: started)
    monkeypatch.setattr(delivery, "_artifact_root", lambda task_id: artifacts)
    monkeypatch.setattr(delivery, "_launch_worker", lambda *args, **kwargs: 23)
    monkeypatch.setattr(delivery, "_history", lambda task_id: history)
    monkeypatch.setattr(
        delivery,
        "_post_queue_stop",
        lambda *args, **kwargs: queue_stops.append((args, kwargs)),
    )
    monkeypatch.setattr(
        delivery,
        "_post_control_state",
        lambda *args, **kwargs: status_updates.append((args, kwargs)),
    )

    with pytest.raises(delivery.DeliveryError, match="Worker exited with code 23"):
        delivery._deliver_one(
            "91",
            session_label="test",
            poll_seconds=10,
            max_wait_minutes=1,
            offline=False,
            control_issue=218,
            state_issue=219,
            issue_contract={"dependencies": []},
        )

    assert queue_stops == [
        (
            (218,),
            {
                "task_id": "91",
                "status_issue": 219,
                "branch": "task/91-synthetic-task",
                "blocker": "worker exited with code 23 after controller finish",
            },
        )
    ]
    assert status_updates[-1][0][1]["state"] == "blocked"


def test_terminal_state_publication_failure_posts_central_queue_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifacts = tmp_path / "delivery"
    artifacts.mkdir()
    started = {
        "lease": {
            "branch": "task/91-synthetic-task",
            "worktree": str(tmp_path / "worktree"),
        }
    }
    history = {
        "state": "finished",
        "pr_number": 223,
        "deployed_sha": "a" * 40,
    }
    queue_stops: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    status_updates: list[dict[str, Any]] = []

    monkeypatch.setattr(delivery, "_start", lambda *args, **kwargs: started)
    monkeypatch.setattr(delivery, "_artifact_root", lambda task_id: artifacts)
    monkeypatch.setattr(delivery, "_launch_worker", lambda *args, **kwargs: 0)
    monkeypatch.setattr(delivery, "_history", lambda task_id: history)
    monkeypatch.setattr(delivery, "_queue_budget_from_controller_history", lambda history: {})
    monkeypatch.setattr(delivery, "_queue_budget_from_worker", lambda artifacts: {})
    monkeypatch.setattr(delivery, "_verify_closeout", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        delivery,
        "_cleanup_delivery_artifacts",
        lambda *args, **kwargs: {"status": "completed"},
    )
    monkeypatch.setattr(
        delivery,
        "_post_queue_stop",
        lambda *args, **kwargs: queue_stops.append((args, kwargs)),
    )

    def fail_terminal_state(issue: int, payload: dict[str, Any]) -> None:
        del issue
        status_updates.append(payload)
        if payload["state"] == "production_verified":
            raise delivery.DeliveryError("terminal state publication failed")

    monkeypatch.setattr(delivery, "_post_control_state", fail_terminal_state)

    with pytest.raises(delivery.DeliveryError, match="terminal state publication failed"):
        delivery._deliver_one(
            "91",
            session_label="test",
            poll_seconds=10,
            max_wait_minutes=1,
            offline=False,
            control_issue=218,
            state_issue=219,
            issue_contract={"dependencies": []},
        )

    assert status_updates[-1]["state"] == "production_verified"
    assert queue_stops == [
        (
            (218,),
            {
                "task_id": "91",
                "status_issue": 219,
                "branch": "task/91-synthetic-task",
                "blocker": "terminal state publication failed",
            },
        )
    ]


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
