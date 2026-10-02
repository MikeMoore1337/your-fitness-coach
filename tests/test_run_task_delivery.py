from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from scripts.issue_workflow import (
    control_state_payload,
    render_control_state_comment,
    render_task_contract,
)


def _load_module():
    script = Path(__file__).parents[1] / "scripts" / "run_task_delivery.py"
    spec = importlib.util.spec_from_file_location("run_task_delivery", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


delivery = _load_module()


def _agent_budget() -> dict[str, int | str | bool]:
    return {
        "max_completed_tool_actions": 160,
        "max_collab_tool_calls": 0,
        "max_spawned_subagents": 0,
        "max_concurrent_subagents": 0,
        "max_identical_failed_actions": 4,
        "max_identical_actions_without_progress": 8,
        "short_cycle_period_max": 3,
        "short_cycle_repetitions": 4,
        "subagent_mode": "disabled",
        "parallel_production_writers": False,
        "enforcement": "live-codex-jsonl-worker-guard",
    }


def _claim_process_instance(*, boot_id: str = "a" * 32, start_ticks: str = "1") -> dict[str, str]:
    return {"kind": "linux-proc", "boot_id": boot_id, "start_ticks": start_ticks}


@pytest.mark.parametrize(
    ("exit_after_polls", "expected_events"),
    (
        (
            1,
            ["launch-claimed", "supervisor-started", "codex-started", "reconciled"],
        ),
        (
            3,
            ["launch-claimed", "supervisor-started", "codex-started", "polled", "reconciled"],
        ),
    ),
)
def test_resumed_worker_claims_before_supervisor_and_records_only_after_codex_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    exit_after_polls: int,
    expected_events: list[str],
) -> None:
    artifacts = tmp_path / "delivery"
    artifacts.mkdir()
    worker_state_path = artifacts / "worker-state.json"
    events: list[str] = []

    class _Process:
        pid = 501
        returncode: int | None = None

        def __init__(self) -> None:
            self.poll_count = 0

        def poll(self) -> int | None:
            self.poll_count += 1
            if self.poll_count >= exit_after_polls:
                self.returncode = 0
            return self.returncode

    process = _Process()

    def fake_popen(command: list[str], **kwargs: Any) -> _Process:
        assert "--worker-supervisor" in command
        assert "codex.exe" in command
        assert "--check" not in kwargs
        events.append("supervisor-started")
        identity = _claim_process_instance()
        worker_state_path.write_text(
            json.dumps(
                {
                    "version": delivery.WORKER_STATE_VERSION,
                    "pid": 502,
                    "process_group_id": None,
                    "process_instance": identity,
                    "started_at": "2026-09-27T00:00:00+00:00",
                    "command_process": {"pid": 503, "process_instance": identity},
                    "command_started_at": "2026-09-27T00:00:01+00:00",
                }
            ),
            encoding="utf-8",
        )
        return process

    monkeypatch.setattr(delivery.shutil, "which", lambda name: "codex.exe")
    monkeypatch.setattr(
        delivery,
        "_current_process_instance_identity",
        lambda: _claim_process_instance(start_ticks="10"),
    )
    monkeypatch.setattr(delivery.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        delivery, "_reconcile_worker_state", lambda path: events.append("reconciled")
    )
    monkeypatch.setattr(delivery.time, "sleep", lambda seconds: events.append("polled"))

    result = delivery._launch_worker(
        "504",
        {
            "lease": {
                "worktree": str(tmp_path),
                "canonical_task_path": "codex-backlog/tasks/504-task.md",
            }
        },
        artifacts,
        worker_state_path=worker_state_path,
        on_launch_claim=lambda: events.append("launch-claimed") or "test-launch-id",
        on_command_started=lambda path: events.append(
            "codex-started" if path == worker_state_path else "wrong-state-path"
        ),
        on_precommand_failure=lambda *_args: pytest.fail(
            "pre-command failure callback must not run after a Codex start marker"
        ),
    )

    assert result == 0
    assert events == expected_events


def test_resumed_worker_releases_claim_when_supervisor_process_never_starts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifacts = tmp_path / "delivery"
    artifacts.mkdir()
    worker_state_path = artifacts / "worker-state.json"
    events: list[str] = []
    monkeypatch.setattr(delivery.shutil, "which", lambda name: "codex.exe")
    monkeypatch.setattr(
        delivery,
        "_current_process_instance_identity",
        lambda: _claim_process_instance(start_ticks="10"),
    )

    def failed_popen(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("synthetic supervisor startup failure")

    monkeypatch.setattr(delivery.subprocess, "Popen", failed_popen)

    with pytest.raises(delivery.DeliveryError, match="no Codex worker was launched"):
        delivery._launch_worker(
            "504",
            {
                "lease": {
                    "worktree": str(tmp_path),
                    "canonical_task_path": "codex-backlog/tasks/504-task.md",
                }
            },
            artifacts,
            worker_state_path=worker_state_path,
            on_launch_claim=lambda: "test-launch-id",
            on_command_started=lambda _path: pytest.fail("Codex must not start"),
            on_precommand_failure=lambda path, launch_id, reason: events.append(
                "released"
                if path == worker_state_path
                and launch_id == "test-launch-id"
                and "could not be started" in reason
                and not path.exists()
                else "invalid-release"
            ),
        )

    assert events == ["released"]


def test_resume_launcher_uses_owner_authorized_controller_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = delivery._parser().parse_args(
        [
            "504",
            "--control-issue",
            "504",
            "--resume-preimplementation",
            "--resume-reason",
            "owner-authorized controller retry",
        ]
    )
    observed: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps({"lease": {"branch": "task/504-test"}}), stderr=""
        )

    monkeypatch.setattr(delivery, "_run", fake_run)
    started = delivery._start(
        args.task_id,
        session_label="test",
        poll_seconds=10,
        max_wait_minutes=1,
        offline=args.offline,
        resume_control_issue=args.control_issue,
        resume_reason=args.resume_reason,
    )

    command = observed["command"]
    assert started["lease"]["branch"] == "task/504-test"
    assert command[command.index("resume-preimplementation") + 1] == "504"
    assert "--owner-authorize" in command
    assert "--control-issue" in command
    assert "--reason" in command
    assert "start" not in command


def test_noop_retry_launcher_uses_dedicated_controller_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = delivery._parser().parse_args(
        [
            "508",
            "--control-issue",
            "508",
            "--retry-noop-worker",
            "--resume-reason",
            "retry after corrected Agent Flow routing",
        ]
    )
    observed: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps({"lease": {"branch": "task/508-test"}}), stderr=""
        )

    monkeypatch.setattr(delivery, "_run", fake_run)
    delivery._start(
        args.task_id,
        session_label="test",
        poll_seconds=10,
        max_wait_minutes=1,
        offline=args.offline,
        resume_control_issue=args.control_issue,
        resume_reason=args.resume_reason,
        retry_noop_worker=args.retry_noop_worker,
    )
    command = observed["command"]
    assert command[command.index("retry-noop-worker") + 1] == "508"
    assert "--owner-authorize" in command
    assert "resume-preimplementation" not in command


def test_parser_exposes_generic_worker_resume() -> None:
    args = delivery._parser().parse_args(
        ["508", "--control-issue", "508", "--resume-worker", "--resume-reason", "retry"]
    )

    assert args.resume_worker is True
    assert args.control_issue == 508
    assert args.resume_reason == "retry"


def test_guard_resume_launcher_uses_dedicated_controller_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = delivery._parser().parse_args(
        [
            "504",
            "--control-issue",
            "504",
            "--resume-guard-interrupted",
            "--resume-reason",
            "owner-authorized one-time guard recovery",
        ]
    )
    observed: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps({"lease": {"branch": "task/504-test"}}), stderr=""
        )

    monkeypatch.setattr(delivery, "_run", fake_run)
    delivery._start(
        args.task_id,
        session_label="test",
        poll_seconds=10,
        max_wait_minutes=1,
        offline=args.offline,
        resume_control_issue=args.control_issue,
        resume_reason=args.resume_reason,
        resume_guard_interrupted=args.resume_guard_interrupted,
    )

    command = observed["command"]
    assert command[command.index("resume-guard-interrupted") + 1] == "504"
    assert "--owner-authorize" in command
    assert "--control-issue" in command
    assert "--reason" in command
    assert "resume-preimplementation" not in command


def test_transport_resume_launcher_uses_dedicated_controller_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = delivery._parser().parse_args(
        [
            "504",
            "--control-issue",
            "504",
            "--resume-transport-interrupted",
            "--resume-reason",
            "owner-authorized one-time post-start transport recovery",
        ]
    )
    observed: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps({"lease": {"branch": "task/504-test"}}), stderr=""
        )

    monkeypatch.setattr(delivery, "_run", fake_run)
    delivery._start(
        args.task_id,
        session_label="test",
        poll_seconds=10,
        max_wait_minutes=1,
        offline=args.offline,
        resume_control_issue=args.control_issue,
        resume_reason=args.resume_reason,
        resume_transport_interrupted=args.resume_transport_interrupted,
    )

    command = observed["command"]
    assert command[command.index("resume-transport-interrupted") + 1] == "504"
    assert "--owner-authorize" in command
    assert "resume-guard-interrupted" not in command


def test_post_start_transport_blocker_requires_started_evidence(tmp_path: Path) -> None:
    artifacts = tmp_path / "delivery"
    attempt = artifacts / "20260927T160806015014Z-delivery"
    attempt.mkdir(parents=True)
    worker_state = attempt / "worker-state.json"
    worker_state.write_text("{}", encoding="utf-8")
    (attempt / "events.jsonl").write_text(
        "Connection failed: error sending request (os error 11001)\n", encoding="utf-8"
    )
    (attempt / "worker-guard.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "classification": "yfc-worker-guard-report",
                "blocked": False,
                "block_reason_code": None,
                "counters": {"completed_tool_actions": 1, "progress_events": 1},
                "privacy": {
                    "raw_prompts_stored": False,
                    "raw_commands_stored": False,
                    "raw_tool_arguments_stored": False,
                    "raw_tool_results_stored": False,
                },
            }
        ),
        encoding="utf-8",
    )
    started = {
        "preimplementation_resume": {
            "state": "worker-started",
            "worker_state_path": str(worker_state),
        }
    }

    blocker = delivery._post_start_transport_blocker(started, artifacts)

    assert blocker is not None
    assert delivery.POST_START_TRANSPORT_FAILURE_KIND in blocker
    assert str(attempt / "events.jsonl") in blocker


def test_guard_resume_prompt_requires_full_wip_audit_before_edits_or_tests() -> None:
    started = {
        "lease": {"canonical_task_path": "codex-backlog/tasks/504-task.md"},
        "preimplementation_resume": {
            "guard_budget_recovery": {
                "checkpoint_ref": "refs/codex/task-wip-checkpoints/task-504/attempt",
                "checkpoint_commit": "a" * 40,
                "changed_paths": ["backend/service.py", "backend/migrations/001.py"],
            }
        },
    }

    prompt = delivery._worker_prompt("504", started)

    assert "Before editing source files or running tests" in prompt
    assert "migrations" in prompt
    assert "frontend/API type parity" in prompt
    assert "Do not treat prior worker output or checks as passed evidence" in prompt
    assert "refs/codex/task-wip-checkpoints/task-504/attempt" in prompt


def test_transport_resume_prompt_requires_full_wip_audit_before_edits_or_tests() -> None:
    started = {
        "lease": {"canonical_task_path": "codex-backlog/tasks/504-task.md"},
        "preimplementation_resume": {
            "transport_interruption_recovery": {
                "checkpoint_ref": "refs/codex/task-wip-checkpoints/task-504/attempt",
                "checkpoint_commit": "a" * 40,
                "changed_paths": ["backend/service.py"],
            }
        },
    }

    prompt = delivery._worker_prompt("504", started)

    assert "external post-start transport interruption" in prompt
    assert "Before editing source files or running tests" in prompt


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
    monkeypatch.setattr(
        delivery,
        "_reconcile_worker_state",
        lambda path: observed.setdefault("worker_state_path", path),
    )

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
    assert observed["args"][:2] == [sys.executable, str(delivery.SCRIPT_PATH)]
    assert "--worker-supervisor" in observed["args"]
    assert "--worker-state-path" in observed["args"]
    command_index = observed["args"].index("--worker-command")
    assert observed["args"][command_index + 1 : command_index + 3] == ["codex", "exec"]
    worker_command = observed["args"][command_index + 1 :]
    assert worker_command[2:5] == [
        "--approve-for-me",
        "-C",
        str(worktree),
    ]
    assert "--sandbox" not in worker_command
    assert observed["worker_state_path"].name == "worker-state.json"
    assert observed["kwargs"]["shell"] is False
    if delivery.os.name != "nt" and delivery.sys.platform == "linux":
        assert callable(observed["kwargs"]["preexec_fn"])


def test_windows_worker_launch_uses_native_codex_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "worktree"
    artifacts = tmp_path / "artifacts"
    worktree.mkdir()
    artifacts.mkdir()
    observed: dict[str, Any] = {}

    monkeypatch.setattr(delivery.os, "name", "nt")
    monkeypatch.setattr(delivery, "_worker_prompt", lambda *args, **kwargs: "prompt")
    monkeypatch.setattr(delivery, "_reconcile_worker_state", lambda path: None)
    monkeypatch.setattr(
        delivery,
        "_current_process_instance_identity",
        lambda: {"kind": "windows", "creation_time_100ns": "1"},
    )

    def fake_which(name: str) -> str:
        observed["which"] = name
        return "C:/Codex/codex.exe"

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(delivery.shutil, "which", fake_which)
    monkeypatch.setattr(delivery.subprocess, "run", fake_run)

    assert (
        delivery._launch_worker(
            "504",
            {"lease": {"worktree": str(worktree)}},
            artifacts,
        )
        == 0
    )

    assert observed["which"] == "codex.exe"
    command_index = observed["args"].index("--worker-command")
    assert observed["args"][command_index + 1] == "C:/Codex/codex.exe"


@pytest.mark.parametrize(
    ("platform", "expected_executable"),
    (("nt", "base-python.exe"), ("posix", "venv-python")),
)
def test_worker_bootstrap_uses_process_identity_stable_interpreter(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    expected_executable: str,
) -> None:
    monkeypatch.setattr(delivery.os, "name", platform)
    monkeypatch.setattr(delivery.sys, "executable", "venv-python")
    monkeypatch.setattr(delivery.sys, "_base_executable", "base-python.exe", raising=False)

    command = delivery._worker_bootstrap_command(
        ["codex", "--version"],
        parent_pid=42,
        parent_identity={"kind": "windows", "creation_time_100ns": "123"},
        worker_state_path=None,
    )

    assert command[0] == expected_executable


def test_worker_launch_sets_ponytail_mode_from_agent_flow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    worktree = tmp_path / "worktree"
    artifacts = tmp_path / "artifacts"
    worktree.mkdir()
    artifacts.mkdir()
    observed: dict[str, Any] = {}

    monkeypatch.setenv("PONYTAIL_DEFAULT_MODE", "ultra")
    monkeypatch.setattr(delivery.shutil, "which", lambda name: "codex")
    monkeypatch.setattr(delivery, "_worker_prompt", lambda *args, **kwargs: "prompt")
    monkeypatch.setattr(delivery, "_reconcile_worker_state", lambda path: None)

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["env"] = kwargs["env"]
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(delivery.subprocess, "run", fake_run)

    assert (
        delivery._launch_worker(
            "357",
            {"lease": {"worktree": str(worktree)}},
            artifacts,
            agent_flow={"ponytail": {"mode": "lite"}, "agent_budget": _agent_budget()},
        )
        == 0
    )
    assert observed["env"]["PONYTAIL_DEFAULT_MODE"] == "lite"
    assert (
        json.loads(observed["env"]["YFC_WORKER_GUARD_CONFIG"])["max_completed_tool_actions"] == 160
    )
    assert observed["env"]["YFC_WORKER_GUARD_REPORT"] == str(
        (artifacts / "worker-guard.json").resolve()
    )


def test_prepare_skill_safety_blocks_critical_findings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = tmp_path / "skill-safety.json"

    class _FakeArtifactManager:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def allocate(self, *args: Any, **kwargs: Any) -> Path:
            return evidence

    monkeypatch.setattr(delivery, "ArtifactManager", _FakeArtifactManager)
    monkeypatch.setattr(
        delivery,
        "scan_repository_skills",
        lambda root: {
            "skills_scanned": 1,
            "external_skills": 1,
            "critical_findings": 1,
            "warning_findings": 0,
            "blocked": True,
            "results": [{"findings": [{"severity": "CRITICAL", "code": "NETWORK_TO_SHELL_PIPE"}]}],
        },
    )

    with pytest.raises(delivery.DeliveryError, match="NETWORK_TO_SHELL_PIPE"):
        delivery._prepare_skill_safety("362", tmp_path)

    assert evidence.is_file()


class _FakeSupervisedWorker:
    pid = 700

    def __init__(self, *, exit_after_polls: int | None = None) -> None:
        self.returncode: int | None = None
        self.exit_after_polls = exit_after_polls
        self.poll_count = 0
        self.terminated = False
        self.stdin = _FakeWorkerStdin()

    def poll(self) -> int | None:
        self.poll_count += 1
        if (
            self.returncode is None
            and self.exit_after_polls is not None
            and self.poll_count > self.exit_after_polls
        ):
            self.returncode = 0
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def wait(self, *, timeout: float) -> int:
        assert timeout == delivery.WORKER_TERMINATION_TIMEOUT_SECONDS
        return self.returncode or 0


class _FakeWorkerStdin:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, value: bytes) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _FakeWindowsWorkerJob:
    def __init__(self, process: _FakeSupervisedWorker) -> None:
        self.process = process
        self.closed = False

    def close(self) -> None:
        self.closed = True
        self.process.returncode = -9


def test_worker_supervisor_terminates_codex_when_parent_instance_is_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery.os, "name", "posix")
    monkeypatch.setattr(delivery.sys, "platform", "linux")
    process = _FakeSupervisedWorker()
    observed: dict[str, Any] = {}
    killpg_calls: list[tuple[int, int]] = []

    def fake_killpg(process_group_id: int, signal_number: int) -> None:
        killpg_calls.append((process_group_id, signal_number))
        process.returncode = -signal_number

    def fake_popen(command: list[str], **kwargs: Any) -> _FakeSupervisedWorker:
        observed["command"] = command
        observed["kwargs"] = kwargs
        return process

    monkeypatch.setattr(delivery.os, "getpgid", lambda pid: 1700, raising=False)
    monkeypatch.setattr(delivery.os, "killpg", fake_killpg, raising=False)

    result = delivery._run_worker_supervisor(
        ["codex", "exec"],
        parent_pid=42,
        parent_identity=_claim_process_instance(),
        popen=fake_popen,
        owner_probe=lambda pid, identity: False,
        sleeper=lambda seconds: pytest.fail("parent loss must terminate without polling sleep"),
        job_factory=lambda process: None,
    )

    assert result == delivery.WORKER_PARENT_LOST_EXIT_CODE
    assert process.terminated is False
    assert killpg_calls == [(1700, delivery.signal.SIGTERM)]
    assert observed["command"][:3] == [
        sys.executable,
        str(delivery.SCRIPT_PATH),
        "--worker-bootstrap",
    ]
    command_index = observed["command"].index("--worker-command")
    assert observed["command"][command_index + 1 :] == ["codex", "exec"]
    assert observed["kwargs"]["shell"] is False
    assert observed["kwargs"]["start_new_session"] is True
    assert callable(observed["kwargs"]["preexec_fn"])


def test_worker_supervisor_returns_codex_exit_code_when_parent_stays_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery.os, "name", "posix")
    monkeypatch.setattr(delivery.sys, "platform", "linux")
    process = _FakeSupervisedWorker(exit_after_polls=1)
    sleeps: list[float] = []

    result = delivery._run_worker_supervisor(
        ["codex", "exec"],
        parent_pid=42,
        parent_identity=_claim_process_instance(),
        popen=lambda command, **kwargs: process,
        owner_probe=lambda pid, identity: True,
        sleeper=sleeps.append,
        job_factory=lambda process: None,
    )

    assert result == 0
    assert process.terminated is False
    assert sleeps == [delivery.WORKER_SUPERVISOR_POLL_SECONDS]


def test_worker_supervisor_uses_windows_job_for_process_tree_termination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(delivery.os, "name", "nt")
    process = _FakeSupervisedWorker()
    job = _FakeWindowsWorkerJob(process)
    state_path = tmp_path / "worker-state.json"
    observed: dict[str, Any] = {}
    monkeypatch.setattr(
        delivery,
        "_current_process_instance_identity",
        lambda: {"kind": "windows", "creation_time_100ns": "111"},
    )
    monkeypatch.setattr(
        delivery,
        "_queue_owner_process_instance",
        lambda pid: {"kind": "windows", "creation_time_100ns": str(pid)},
    )
    release_worker = delivery._release_windows_worker

    def release_after_durable_state(worker: _FakeSupervisedWorker) -> None:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["pid"] == worker.pid
        observed["released_after_state"] = True
        release_worker(worker)

    def fake_popen(command: list[str], **kwargs: Any) -> _FakeSupervisedWorker:
        observed["command"] = command
        observed["kwargs"] = kwargs
        return process

    monkeypatch.setattr(delivery, "_release_windows_worker", release_after_durable_state)

    result = delivery._run_worker_supervisor(
        ["codex", "exec"],
        parent_pid=42,
        parent_identity={"kind": "windows", "creation_time_100ns": "123"},
        worker_state_path=state_path,
        popen=fake_popen,
        owner_probe=lambda pid, identity: False,
        sleeper=lambda seconds: pytest.fail("parent loss must terminate without polling sleep"),
        job_factory=lambda worker: job,
    )

    assert result == delivery.WORKER_PARENT_LOST_EXIT_CODE
    assert job.closed is True
    assert process.terminated is False
    assert observed["released_after_state"] is True
    assert json.loads(state_path.read_text(encoding="utf-8"))["process_instance"] == {
        "kind": "windows",
        "creation_time_100ns": str(process.pid),
    }
    assert process.stdin.writes == [b"\n"]
    assert process.stdin.closed is True
    assert observed["command"][:3] == [
        getattr(sys, "_base_executable", sys.executable),
        str(delivery.SCRIPT_PATH),
        "--worker-bootstrap",
    ]
    assert observed["kwargs"]["creationflags"] == getattr(
        delivery.subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )


def test_windows_worker_parent_accepts_mismatched_immediate_parent_with_matching_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery.os, "name", "nt")
    monkeypatch.setattr(delivery.os, "getppid", lambda: 99)
    identity = {"kind": "windows", "creation_time_100ns": "123"}
    monkeypatch.setattr(delivery, "_queue_owner_process_instance", lambda pid: identity)

    assert delivery._worker_parent_is_alive(42, identity) is True


def test_windows_bootstrap_runs_command_when_supervisor_identity_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(delivery.os, "name", "nt")
    monkeypatch.setattr(delivery.os, "getppid", lambda: 99)
    monkeypatch.setattr(delivery, "_wait_for_windows_worker_release", lambda: None)
    supervisor_identity = {"kind": "windows", "creation_time_100ns": "123"}
    bootstrap_identity = {"kind": "windows", "creation_time_100ns": "456"}
    monkeypatch.setattr(
        delivery,
        "_queue_owner_process_instance",
        lambda pid: supervisor_identity if pid == 42 else bootstrap_identity,
    )
    monkeypatch.setattr(delivery, "_current_process_instance_identity", lambda: bootstrap_identity)
    state_path = tmp_path / "worker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "version": delivery.WORKER_STATE_VERSION,
                "pid": delivery.os.getpid(),
                "process_group_id": None,
                "process_instance": bootstrap_identity,
                "started_at": "2026-09-26T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    process = _FakeSupervisedWorker(exit_after_polls=0)
    starts: list[list[str]] = []

    result = delivery._run_worker_bootstrap(
        ["codex", "--version"],
        parent_pid=42,
        parent_identity=supervisor_identity,
        worker_state_path=state_path,
        popen=lambda command, **kwargs: starts.append(command) or process,
        sleeper=lambda seconds: pytest.fail("already exited harmless command must not sleep"),
    )

    assert result == 0
    assert starts == [["codex", "--version"]]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["pid"] == delivery.os.getpid()
    assert state["command_process"]["pid"] == process.pid
    assert state["command_started_at"]


def test_windows_worker_parent_fails_closed_when_supervisor_is_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery.os, "name", "nt")
    monkeypatch.setattr(delivery.os, "getppid", lambda: 99)
    monkeypatch.setattr(delivery, "_queue_owner_process_instance", lambda pid: None)

    assert (
        delivery._worker_parent_is_alive(42, {"kind": "windows", "creation_time_100ns": "123"})
        is False
    )


def test_windows_worker_parent_fails_closed_when_supervisor_pid_was_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery.os, "name", "nt")
    monkeypatch.setattr(delivery.os, "getppid", lambda: 99)
    monkeypatch.setattr(
        delivery,
        "_queue_owner_process_instance",
        lambda pid: {"kind": "windows", "creation_time_100ns": "456"},
    )

    assert (
        delivery._worker_parent_is_alive(42, {"kind": "windows", "creation_time_100ns": "123"})
        is False
    )


@pytest.mark.parametrize("identity_json", [None, "{", "{}"])
def test_windows_worker_bootstrap_rejects_missing_or_malformed_parent_identity(
    monkeypatch: pytest.MonkeyPatch, identity_json: str | None
) -> None:
    monkeypatch.setattr(delivery.os, "name", "nt")

    with pytest.raises(delivery.DeliveryError, match="supervisor process identity"):
        delivery._worker_bootstrap_from_args(
            parent_pid=42,
            parent_identity_json=identity_json,
            command=["codex", "--version"],
            worker_state_path_value="C:/artifacts/worker-state.json",
        )


def test_windows_worker_bootstrap_does_not_start_command_without_durable_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(delivery.os, "name", "nt")
    monkeypatch.setattr(delivery, "_wait_for_windows_worker_release", lambda: None)
    starts: list[list[str]] = []

    with pytest.raises(delivery.DeliveryError, match="worker state is missing"):
        delivery._run_worker_bootstrap(
            ["codex", "--version"],
            parent_pid=42,
            parent_identity={"kind": "windows", "creation_time_100ns": "123"},
            worker_state_path=tmp_path / "worker-state.json",
            popen=lambda command, **kwargs: starts.append(command),
        )

    assert starts == []


def test_posix_worker_parent_keeps_direct_parent_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery.os, "name", "posix")
    monkeypatch.setattr(delivery.os, "getppid", lambda: 42)

    assert delivery._worker_parent_is_alive(42) is True
    assert delivery._worker_parent_is_alive(43) is False


def test_linux_worker_supervisor_binds_codex_to_supervisor_lifetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery.os, "name", "posix")
    monkeypatch.setattr(delivery.sys, "platform", "linux")
    process = _FakeSupervisedWorker(exit_after_polls=0)
    observed: dict[str, Any] = {}
    bound_parent_pids: list[int] = []
    supervisor_pid = delivery.os.getpid()

    def fake_popen(command: list[str], **kwargs: Any) -> _FakeSupervisedWorker:
        observed["command"] = command
        observed["kwargs"] = kwargs
        return process

    monkeypatch.setattr(
        delivery,
        "_linux_worker_parent_death_signal",
        lambda parent_pid: bound_parent_pids.append(parent_pid),
    )

    result = delivery._run_worker_supervisor(
        ["codex", "exec"],
        parent_pid=42,
        parent_identity=_claim_process_instance(),
        popen=fake_popen,
        owner_probe=lambda pid, identity: True,
        sleeper=lambda seconds: pytest.fail("already exited worker must not sleep"),
    )

    assert result == 0
    preexec_fn = observed["kwargs"]["preexec_fn"]
    assert callable(preexec_fn)
    preexec_fn()
    assert bound_parent_pids == [supervisor_pid]


def test_posix_worker_bootstrap_terminates_complete_worker_group_on_parent_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery.os, "name", "posix")
    monkeypatch.setattr(delivery.sys, "platform", "darwin")
    process = _FakeSupervisedWorker()
    killpg_calls: list[tuple[int, int]] = []
    parent_results = iter((True, False))

    def fake_killpg(process_group_id: int, signal_number: int) -> None:
        killpg_calls.append((process_group_id, signal_number))
        if signal_number == delivery.WORKER_KILL_SIGNAL:
            process.returncode = -signal_number

    monkeypatch.setattr(delivery.os, "getpgid", lambda pid: 1700, raising=False)
    monkeypatch.setattr(delivery.os, "killpg", fake_killpg, raising=False)

    result = delivery._run_worker_bootstrap(
        ["codex", "exec"],
        parent_pid=42,
        worker_state_path=None,
        popen=lambda command, **kwargs: process,
        parent_probe=lambda pid: next(parent_results),
        sleeper=lambda seconds: pytest.fail("parent loss must terminate without polling sleep"),
    )

    assert result == delivery.WORKER_PARENT_LOST_EXIT_CODE
    assert killpg_calls == [(1700, delivery.WORKER_KILL_SIGNAL)]
    assert process.terminated is False


def test_posix_worker_bootstrap_persists_worker_group_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(delivery.os, "name", "posix")
    monkeypatch.setattr(delivery.sys, "platform", "darwin")
    process = _FakeSupervisedWorker(exit_after_polls=0)
    state_path = tmp_path / "worker-state.json"

    monkeypatch.setattr(delivery.os, "getpgid", lambda pid: 1700, raising=False)
    monkeypatch.setattr(
        delivery, "_queue_owner_process_instance", lambda pid: _claim_process_instance()
    )
    monkeypatch.setattr(delivery, "_posix_worker_group_is_alive", lambda process_group_id: False)

    result = delivery._run_worker_bootstrap(
        ["codex", "exec"],
        parent_pid=42,
        worker_state_path=state_path,
        popen=lambda command, **kwargs: process,
        parent_probe=lambda pid: True,
        sleeper=lambda seconds: pytest.fail("already exited worker must not sleep"),
    )

    assert result == 0
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["pid"] == process.pid
    assert state["process_group_id"] == 1700
    assert state["process_instance"] == _claim_process_instance()
    assert state["command_process"]["pid"] == process.pid
    assert state["command_started_at"]


def test_posix_worker_bootstrap_publishes_identity_before_unblocking_parent_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery.os, "name", "posix")
    monkeypatch.setattr(delivery.sys, "platform", "linux")
    process = _FakeSupervisedWorker(exit_after_polls=0)
    events: list[str] = []

    def fake_pthread_sigmask(how: int, mask: set[int]) -> set[int]:
        del mask
        events.append("block" if how == delivery.signal.SIG_BLOCK else "unblock")
        return set()

    monkeypatch.setattr(delivery.signal, "pthread_sigmask", fake_pthread_sigmask, raising=False)
    monkeypatch.setattr(delivery.signal, "SIG_BLOCK", 0, raising=False)
    monkeypatch.setattr(delivery.signal, "SIG_SETMASK", 1, raising=False)
    monkeypatch.setattr(
        delivery,
        "_linux_set_parent_death_signal",
        lambda parent_pid, death_signal: events.append("pdeath") or True,
    )
    monkeypatch.setattr(
        delivery,
        "_posix_worker_group_is_alive",
        lambda process_group_id: events.append("group-check") or False,
    )
    monkeypatch.setattr(
        delivery.os,
        "getpgid",
        lambda pid: events.append("getpgid") or 1700,
        raising=False,
    )

    def parent_probe(parent_pid: int) -> bool:
        del parent_pid
        events.append("parent-probe")
        return True

    def fake_popen(command: list[str], **kwargs: Any) -> _FakeSupervisedWorker:
        del command, kwargs
        events.append("popen")
        return process

    result = delivery._run_worker_bootstrap(
        ["codex", "exec"],
        parent_pid=42,
        worker_state_path=None,
        popen=fake_popen,
        parent_probe=parent_probe,
        sleeper=lambda seconds: pytest.fail("already exited worker must not sleep"),
    )

    assert result == 0
    assert events == [
        "block",
        "pdeath",
        "parent-probe",
        "popen",
        "getpgid",
        "unblock",
        "group-check",
    ]


def test_linux_worker_parent_death_binding_fails_closed_on_parent_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ctypes

    calls: list[tuple[int, int]] = []
    exits: list[int] = []
    linux_sigkill = getattr(delivery.signal, "SIGKILL", 9)

    class _FakePrctl:
        argtypes: list[Any] | None = None
        restype: Any = None

        def __call__(self, option: int, death_signal: int, *args: int) -> int:
            del args
            calls.append((option, death_signal))
            return 0

    class _FakeLibc:
        prctl = _FakePrctl()

    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: _FakeLibc())
    monkeypatch.setattr(delivery.os, "getppid", lambda: 99)
    monkeypatch.setattr(delivery.os, "_exit", exits.append)
    monkeypatch.setattr(delivery.signal, "SIGKILL", linux_sigkill, raising=False)

    delivery._linux_worker_parent_death_signal(42)

    assert calls == [(1, linux_sigkill)]
    assert exits == [delivery.WORKER_PARENT_LOST_EXIT_CODE]


def test_reconcile_worker_state_terminates_live_posix_group_before_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(delivery.os, "name", "posix")
    monkeypatch.setattr(delivery.sys, "platform", "linux")
    process_state = tmp_path / "worker-state.json"
    process_state.write_text(
        json.dumps(
            {
                "version": delivery.WORKER_STATE_VERSION,
                "pid": 700,
                "process_group_id": 1700,
                "process_instance": _claim_process_instance(),
                "started_at": "2026-09-09T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        delivery, "_queue_owner_process_instance", lambda pid: _claim_process_instance()
    )
    killpg_calls: list[tuple[int, int]] = []

    def fake_killpg(process_group_id: int, signal_number: int) -> None:
        killpg_calls.append((process_group_id, signal_number))
        if signal_number == delivery.WORKER_KILL_SIGNAL:
            return None

    group_checks = iter((True, False))
    monkeypatch.setattr(delivery.os, "killpg", fake_killpg, raising=False)
    monkeypatch.setattr(
        delivery,
        "_posix_worker_group_is_alive",
        lambda process_group_id: next(group_checks),
    )

    delivery._reconcile_worker_state(process_state)

    assert killpg_calls == [(1700, delivery.WORKER_KILL_SIGNAL)]
    assert not process_state.exists()


def test_worker_prompt_includes_agent_flow_contract() -> None:
    started = {
        "lease": {
            "canonical_task_path": "D:/repo/codex-backlog/tasks/355-agent-flow.md",
            "branch": "task/355-agent-flow",
            "worktree": "D:/repo/.artifacts/worktrees/355-agent-flow",
        },
        "prompt": "controller evidence",
    }
    plan = {
        "schema_version": 1,
        "worker_role_passes": [{"name": "implementer"}],
        "graphify": {"bootstrap_required": False},
        "execution": {"single_production_writer": True},
    }

    prompt = delivery._worker_prompt("355", started, agent_flow=plan)

    assert "Agent Flow v1 routing contract" in prompt
    assert '"single_production_writer": true' in prompt
    assert "Only implementer may write production code" in prompt


def test_prepare_agent_flow_writes_durable_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    task = tmp_path / "codex-backlog" / "tasks" / "355-agent-flow.md"
    task.parent.mkdir(parents=True)
    task.write_text(
        """
# Task

- **Тип:** Feature
- **Основная роль:** implementer

Change a small helper.
""",
        encoding="utf-8",
    )
    artifacts = delivery._artifact_root("355")
    started = {"lease": {"canonical_task_path": str(task)}}

    plan, evidence = delivery._prepare_agent_flow("355", started, artifacts)

    assert evidence.is_file()
    relative = evidence.relative_to(tmp_path / ".artifacts")
    assert relative.parts[:4] == ("tasks", "355", "evidence", "agent-flow")
    assert relative.name == artifacts.name + ".json"
    persisted = json.loads(evidence.read_text(encoding="utf-8"))
    assert persisted == plan
    assert [item["name"] for item in plan["worker_role_passes"]] == ["implementer"]


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
        "task branch -> relevant local checks -> commit/push -> PR master -> exact GitHub CI"
        in prompt
    )
    assert "do not run a full local regression gate" in prompt
    assert "create local release evidence" in prompt
    assert "BLOCKER/HIGH/MEDIUM" in prompt
    assert "Не запрашивай generic approval" in prompt
    assert "без поля concurrency в metadata считается independent-write" in prompt
    assert "refresh-canonical-master" in prompt
    assert "branch-safety check, not a release gate" in prompt
    assert "Не запускай следующую product task" in prompt
    assert "Codex Code Review отключён" in prompt
    assert "не публикуй `@codex review`" in prompt
    assert "request-codex-review" not in prompt
    assert "validate-codex-review" not in prompt
    assert "exact-head CI GREEN" in prompt
    assert "aggregate checks GREEN" in prompt
    assert "validate-pr-review --pr <N> --head-sha <SHA>" not in prompt
    assert "3 review-fix cycles" in prompt
    assert "3 CI-fix cycles" in prompt
    assert "reviewer/subagent/adversarial audit" in prompt


def test_issue_authorization_accepts_owner_and_rejects_codex_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delivery, "_github_slug", lambda: "MikeMoore1337/your-fitness-coach")
    owner_issue = {"user": {"login": "MikeMoore1337"}}
    connector_issue = {"user": {"login": "chatgpt-codex-connector[bot]"}}

    assert delivery._issue_authorized(owner_issue) is True
    assert delivery._issue_authorized(connector_issue) is False
    assert "chatgpt-codex-connector" not in delivery._trusted_issue_logins(connector_issue)


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


def test_queue_inventory_skips_closed_legacy_completed_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks_root = tmp_path / "codex-backlog" / "tasks"
    tasks_root.mkdir(parents=True)
    (tasks_root / "505-progression.md").write_text("task", encoding="utf-8")
    legacy_body = """<!-- yfc-task-contract:v1 -->
{"version":1,"task_id":"494","scope":"legacy completed task","acceptance":["historical completion is preserved"],"dependencies":[],"owner_gate":"none","risk_lane":"YELLOW","issue_state":"completed"}
<!-- yfc-task-contract:v1 -->"""
    current_body = render_task_contract(
        {
            "task_id": "505",
            "scope": "progression",
            "acceptance": ["deterministic proposals"],
            "dependencies": ["504"],
            "owner_gate": "none",
            "risk_lane": "GREEN",
            "source_spec": "codex-backlog/tasks/505-progression.md",
            "issue_state": "queued",
        }
    )
    issues = [
        {
            "number": 494,
            "title": "[Task 494] legacy",
            "body": legacy_body,
            "state": "closed",
            "user": {"login": "owner"},
        },
        {
            "number": 505,
            "title": "[Task 505] progression",
            "body": current_body,
            "state": "open",
            "user": {"login": "owner"},
        },
    ]

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
            return {"504"}

    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(delivery, "GitRepository", lambda root: object())
    monkeypatch.setattr(delivery, "TaskController", FakeController)
    monkeypatch.setattr(
        delivery,
        "find_task_document",
        lambda root, task_id: SimpleNamespace(
            task_id=task_id,
            executable=True,
            slug="progression",
            path=root / "codex-backlog" / "tasks" / "505-progression.md",
        ),
    )
    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: issues)
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("owner",))
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue: (issue, []))

    candidates = delivery._queue_candidates()

    assert [candidate["task_id"] for candidate in candidates] == ["505"]


def test_legacy_completed_contract_requires_closed_github_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_body = """<!-- yfc-task-contract:v1 -->
{"version":1,"task_id":"494","scope":"legacy completed task","acceptance":["historical completion is preserved"],"dependencies":[],"owner_gate":"none","risk_lane":"YELLOW","issue_state":"completed"}
<!-- yfc-task-contract:v1 -->"""
    issue = {
        "number": 494,
        "title": "[Task 494] legacy",
        "body": legacy_body,
        "state": "open",
        "user": {"login": "owner"},
    }

    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda item: True)

    with pytest.raises(delivery.DeliveryError, match="requires a closed GitHub Issue"):
        delivery._task_issue_contracts()


def test_legacy_completed_contract_rejects_conflicting_control_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_body = """<!-- yfc-task-contract:v1 -->
{"version":1,"task_id":"494","scope":"legacy completed task","acceptance":["historical completion is preserved"],"dependencies":[],"owner_gate":"none","risk_lane":"YELLOW","issue_state":"completed"}
<!-- yfc-task-contract:v1 -->"""
    issue = {
        "number": 494,
        "title": "[Task 494] legacy",
        "body": legacy_body,
        "state": "closed",
        "user": {"login": "owner"},
    }
    conflicting_state = control_state_payload(
        task_id="494",
        state="in_progress",
        issue_number=494,
        branch="task/494-legacy",
    )

    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda item: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda item: ("owner",))
    monkeypatch.setattr(
        delivery,
        "_control_issue_snapshot",
        lambda issue_number: (
            issue,
            [
                {
                    "id": 1,
                    "user": {"login": "owner"},
                    "body": render_control_state_comment(conflicting_state),
                }
            ],
        ),
    )

    with pytest.raises(delivery.DeliveryError, match="conflicts with control state"):
        delivery._task_issue_contracts()


def _legacy_active_body(task_id: str, *, source_spec: str | None = None) -> str:
    source = f',"source_spec":"{source_spec}"' if source_spec is not None else ""
    return f"""<!-- yfc-task-contract:v1 -->
{{"version":1,"task_id":"{task_id}","scope":"legacy active task","acceptance":["terminal evidence is required"],"dependencies":[],"owner_gate":"none","risk_lane":"YELLOW"{source},"issue_state":"active"}}
<!-- yfc-task-contract:v1 -->"""


def _legacy_control_snapshot(
    issue: dict[str, Any], *, task_id: str, state: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = control_state_payload(
        task_id=task_id,
        state=state,
        issue_number=issue["number"],
        branch=f"task/{task_id.lower()}-legacy",
    )
    return issue, [
        {
            "id": 1,
            "user": {"login": "owner"},
            "created_at": "2026-09-28T00:00:00Z",
            "body": render_control_state_comment(payload),
        }
    ]


def test_legacy_active_contract_requires_closed_github_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = {
        "number": 448,
        "title": "[Task 346A] legacy active",
        "body": _legacy_active_body(
            "346A", source_spec="codex-backlog/tasks/346A-production-log-retention.md"
        ),
        "state": "open",
        "user": {"login": "owner"},
    }

    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda item: True)

    with pytest.raises(delivery.DeliveryError, match="legacy active contract requires a closed"):
        delivery._task_issue_contracts(terminal_task_ids={"346A"})


@pytest.mark.parametrize("state", ["in_progress", "blocked", "human_required"])
def test_legacy_active_contract_rejects_closed_issue_without_terminal_control_state(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    issue = {
        "number": 448,
        "title": "[Task 346A] legacy active",
        "body": _legacy_active_body(
            "346A", source_spec="codex-backlog/tasks/346A-production-log-retention.md"
        ),
        "state": "closed",
        "user": {"login": "owner"},
    }
    snapshot = _legacy_control_snapshot(issue, task_id="346A", state=state)

    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda item: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda item: ("owner",))
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue_number: snapshot)

    with pytest.raises(delivery.DeliveryError, match="legacy active contract conflicts"):
        delivery._task_issue_contracts(terminal_task_ids={"346A"})


def test_legacy_active_contract_requires_terminal_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = {
        "number": 310,
        "title": "[Task 128H] legacy active",
        "body": _legacy_active_body("128H"),
        "state": "closed",
        "user": {"login": "owner"},
    }

    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda item: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda item: ("owner",))
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue_number: (issue, []))

    with pytest.raises(delivery.DeliveryError, match="requires terminal evidence"):
        delivery._task_issue_contracts()


def test_legacy_active_contract_uses_completed_dependency_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = {
        "number": 310,
        "title": "[Task 128H] legacy active",
        "body": _legacy_active_body("128H"),
        "state": "closed",
        "user": {"login": "owner"},
    }

    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda item: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda item: ("owner",))
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue_number: (issue, []))

    contracts = delivery._task_issue_contracts(terminal_task_ids={"128H"})

    assert contracts["128H"]["issue_state"] == "closed"
    assert contracts["128H"]["latest_control_state"] is None
    assert contracts["128H"]["legacy_issue_state"] == "active"
    assert contracts["128H"]["legacy_terminal_evidence"] == "completed_dependency_record"


def test_closed_historical_incomplete_contract_is_terminal_with_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = {
        "number": 301,
        "title": "[Task 279] historical visual audit",
        "body": """<!-- yfc-task-contract:v1 -->
{"version":1,"task_id":"279","scope":"historical visual audit","acceptance":["terminal evidence is preserved"],"dependencies":["276"],"owner_gate":"none","risk_lane":"GREEN","issue_state":"queued"}
<!-- yfc-task-contract:v1 -->""",
        "state": "closed",
        "user": {"login": "owner"},
    }

    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda item: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda item: ("owner",))
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue_number: (issue, []))

    contracts = delivery._task_issue_contracts(terminal_task_ids={"279"})
    contract = contracts["279"]

    assert contract is not None
    assert contract["issue_state"] == "closed"
    assert contract["legacy_contract"] is True
    assert contract["legacy_raw_issue_state"] == "queued"
    assert contract["legacy_source_spec_missing"] is True
    assert contract["legacy_terminal_evidence"] == "completed_dependency_record"
    assert "source_spec" not in contract


def test_closed_historical_incomplete_contract_uses_production_verified_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = {
        "number": 301,
        "title": "[Task 279] historical visual audit",
        "body": """<!-- yfc-task-contract:v1 -->
{"version":1,"task_id":"279","scope":"historical visual audit","acceptance":["terminal evidence is preserved"],"dependencies":["276"],"owner_gate":"none","risk_lane":"GREEN","issue_state":"queued"}
<!-- yfc-task-contract:v1 -->""",
        "state": "closed",
        "user": {"login": "owner"},
    }
    snapshot = _legacy_control_snapshot(issue, task_id="279", state="production_verified")

    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda item: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda item: ("owner",))
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue_number: snapshot)

    contracts = delivery._task_issue_contracts()

    assert contracts["279"]["legacy_terminal_evidence"] == (
        "latest_control_state:production_verified"
    )


def test_open_incomplete_contract_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = {
        "number": 301,
        "title": "[Task 279] historical visual audit",
        "body": """<!-- yfc-task-contract:v1 -->
{"version":1,"task_id":"279","scope":"historical visual audit","acceptance":["must remain blocked"],"dependencies":["276"],"owner_gate":"none","risk_lane":"GREEN","issue_state":"queued"}
<!-- yfc-task-contract:v1 -->""",
        "state": "open",
        "user": {"login": "owner"},
    }

    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda item: True)

    with pytest.raises(delivery.DeliveryError, match="Task 279 Issue contract is malformed"):
        delivery._task_issue_contracts(terminal_task_ids={"279"})


def test_inventory_reaches_queued_task_after_closed_historical_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks_root = tmp_path / "codex-backlog" / "tasks"
    tasks_root.mkdir(parents=True)
    (tasks_root / "279-historical.md").write_text("historical", encoding="utf-8")
    (tasks_root / "505-progression.md").write_text("progression", encoding="utf-8")
    issue_279 = {
        "number": 301,
        "title": "[Task 279] historical visual audit",
        "body": """<!-- yfc-task-contract:v1 -->
{"version":1,"task_id":"279","scope":"historical visual audit","acceptance":["terminal evidence is preserved"],"dependencies":["276"],"owner_gate":"none","risk_lane":"GREEN","issue_state":"queued"}
<!-- yfc-task-contract:v1 -->""",
        "state": "closed",
        "user": {"login": "owner"},
    }
    issue_505 = {
        "number": 505,
        "title": "[Task 505] progression",
        "body": render_task_contract(
            {
                "task_id": "505",
                "scope": "progression",
                "acceptance": ["deterministic proposals"],
                "dependencies": ["504"],
                "owner_gate": "behavior_contract",
                "risk_lane": "YELLOW",
                "source_spec": "codex-backlog/tasks/505-progression.md",
                "issue_state": "queued",
            }
        ),
        "state": "open",
        "user": {"login": "owner"},
    }
    issues = [issue_279, issue_505]

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
            return {"279", "504"}

    def fake_find_task_document(root: Path, task_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            task_id=task_id,
            executable=True,
            slug=f"task-{task_id}",
            path=root / "codex-backlog" / "tasks" / f"{task_id}-fixture.md",
        )

    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(delivery, "GitRepository", lambda root: object())
    monkeypatch.setattr(delivery, "TaskController", FakeController)
    monkeypatch.setattr(delivery, "find_task_document", fake_find_task_document)
    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: issues)
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("owner",))
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue: (issue, []))

    candidates = delivery._queue_candidates()

    assert [candidate["task_id"] for candidate in candidates] == ["505"]


@pytest.mark.parametrize(
    ("task_id", "dependencies", "owner_gate", "risk_lane"),
    [
        ("505", ["504"], "behavior_contract", "YELLOW"),
        ("506", ["505"], "none", "YELLOW"),
        ("507", ["504", "506"], "owner_visual_acceptance", "RED"),
        ("508", ["507"], "safety_and_prompt_contract", "YELLOW"),
        ("509", ["508"], "final_acceptance", "RED"),
    ],
)
def test_canonical_product_v4_contracts_preserve_dependency_chain_and_gates(
    task_id: str, dependencies: list[str], owner_gate: str, risk_lane: str
) -> None:
    contract = render_task_contract(
        {
            "task_id": task_id,
            "scope": f"Product v4 stage {task_id}",
            "acceptance": ["existing Issue acceptance remains authoritative"],
            "dependencies": dependencies,
            "owner_gate": owner_gate,
            "risk_lane": risk_lane,
            "source_spec": f"codex-backlog/tasks/{task_id}-product-v4.md",
            "issue_state": "queued",
        }
    )

    parsed = delivery.parse_task_contract(contract)

    assert parsed is not None
    assert parsed["task_id"] == task_id
    assert parsed["dependencies"] == dependencies
    assert parsed["owner_gate"] == owner_gate
    assert parsed["risk_lane"] == risk_lane
    assert parsed["issue_state"] == "queued"


def test_queue_blocks_product_v4_stage_two_until_stage_one_completes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks_root = tmp_path / "codex-backlog" / "tasks"
    tasks_root.mkdir(parents=True)
    (tasks_root / "506-lifecycle.md").write_text("lifecycle", encoding="utf-8")
    issue_506 = {
        "number": 506,
        "title": "[Task 506] lifecycle",
        "body": render_task_contract(
            {
                "task_id": "506",
                "scope": "Product v4 stage 2",
                "acceptance": ["lifecycle remains deterministic"],
                "dependencies": ["505"],
                "owner_gate": "none",
                "risk_lane": "YELLOW",
                "source_spec": "codex-backlog/tasks/506-lifecycle.md",
                "issue_state": "queued",
            }
        ),
        "state": "open",
        "user": {"login": "owner"},
    }

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
            return {"504"}

    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(delivery, "GitRepository", lambda root: object())
    monkeypatch.setattr(delivery, "TaskController", FakeController)
    monkeypatch.setattr(
        delivery,
        "find_task_document",
        lambda root, task_id: SimpleNamespace(
            task_id=task_id,
            executable=True,
            slug="lifecycle",
            path=root / "codex-backlog" / "tasks" / "506-lifecycle.md",
        ),
    )
    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue_506])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("owner",))
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue: (issue, []))

    candidates = delivery._queue_candidates()

    assert candidates[0]["task_id"] == "506"
    assert candidates[0]["state"] == "blocked"
    assert candidates[0]["risk_lane"] == "RED"
    assert "505" in candidates[0]["blocker"]


def _configure_queue_lease_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    leases: list[dict[str, Any]],
    completed: set[str],
    delivery_owner: dict[str, Any] | None = None,
) -> None:
    tasks_root = tmp_path / "codex-backlog" / "tasks"
    tasks_root.mkdir(parents=True)
    (tasks_root / "403-superseded.md").write_text("superseded", encoding="utf-8")
    (tasks_root / "506-lifecycle.md").write_text("lifecycle", encoding="utf-8")
    issues = [
        {
            "number": 403,
            "title": "[Task 403] superseded",
            "body": render_task_contract(
                {
                    "task_id": "403",
                    "scope": "legacy task",
                    "acceptance": ["legacy state is preserved"],
                    "dependencies": [],
                    "owner_gate": "none",
                    "risk_lane": "GREEN",
                    "source_spec": "codex-backlog/tasks/403-superseded.md",
                    "issue_state": "queued",
                }
            ),
            "state": "open",
            "user": {"login": "owner"},
        },
        {
            "number": 506,
            "title": "[Task 506] lifecycle",
            "body": render_task_contract(
                {
                    "task_id": "506",
                    "scope": "Product v4 stage 2",
                    "acceptance": ["lifecycle remains deterministic"],
                    "dependencies": ["505"],
                    "owner_gate": "none",
                    "risk_lane": "GREEN",
                    "source_spec": "codex-backlog/tasks/506-lifecycle.md",
                    "issue_state": "queued",
                }
            ),
            "state": "open",
            "user": {"login": "owner"},
        },
    ]

    class FakeStore:
        def delivery_state(self) -> dict[str, Any]:
            return {"owner": delivery_owner}

        def all_leases(self) -> list[dict[str, Any]]:
            return leases

    class FakeController:
        def __init__(self, repository: object) -> None:
            del repository
            self.store = FakeStore()

        def _completed_dependency_ids(self) -> set[str]:
            return completed

    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(delivery, "GitRepository", lambda root: object())
    monkeypatch.setattr(delivery, "TaskController", FakeController)
    monkeypatch.setattr(
        delivery,
        "find_task_document",
        lambda root, task_id: SimpleNamespace(
            task_id=task_id,
            executable=True,
            slug=f"task-{task_id}",
            path=root / "codex-backlog" / "tasks" / f"{task_id}-fixture.md",
        ),
    )
    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: issues)
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("owner",))
    monkeypatch.setattr(
        delivery,
        "_control_issue_snapshot",
        lambda issue_number: (next(item for item in issues if item["number"] == issue_number), []),
    )


@pytest.mark.parametrize(
    ("lease_state", "completed", "expected_state"),
    [
        ("review", set(), "human_required"),
        ("implementation", set(), "human_required"),
        ("superseded", {"505"}, "queued"),
        ("production-success", {"403", "505"}, "queued"),
    ],
)
def test_queue_lease_semantics_keep_superseded_nonblocking_and_nonrunnable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    lease_state: str,
    completed: set[str],
    expected_state: str,
) -> None:
    _configure_queue_lease_fixture(
        monkeypatch,
        tmp_path,
        leases=[{"task_id": "403", "mode": "write", "lifecycle_state": lease_state}],
        completed=completed,
    )

    candidates = delivery._queue_candidates()

    if lease_state in {"review", "implementation"}:
        assert candidates[0]["task_id"] == "403"
        assert candidates[0]["state"] == expected_state
        assert "active controller lease" in candidates[0]["blocker"]
    else:
        assert [candidate["task_id"] for candidate in candidates] == ["506"]
        assert candidates[0]["state"] == expected_state


def test_superseded_lease_does_not_satisfy_dependency_or_delivery_owner_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_queue_lease_fixture(
        monkeypatch,
        tmp_path,
        leases=[{"task_id": "403", "mode": "write", "lifecycle_state": "superseded"}],
        completed={"505"},
        delivery_owner={"task_id": "403"},
    )

    candidates = delivery._queue_candidates()

    assert candidates[0]["task_id"] == "403"
    assert candidates[0]["state"] == "human_required"
    assert "still owns the delivery lane" in candidates[0]["blocker"]


def test_queue_retains_product_v4_visual_acceptance_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks_root = tmp_path / "codex-backlog" / "tasks"
    tasks_root.mkdir(parents=True)
    (tasks_root / "507-operations.md").write_text("operations", encoding="utf-8")
    issue_507 = {
        "number": 507,
        "title": "[Task 507] operations",
        "body": render_task_contract(
            {
                "task_id": "507",
                "scope": "Product v4 stage 3",
                "acceptance": ["owner visual acceptance remains required"],
                "dependencies": ["504", "506"],
                "owner_gate": "owner_visual_acceptance",
                "risk_lane": "RED",
                "source_spec": "codex-backlog/tasks/507-operations.md",
                "issue_state": "queued",
            }
        ),
        "state": "open",
        "user": {"login": "owner"},
    }

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
            return {"504", "505", "506"}

    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(delivery, "GitRepository", lambda root: object())
    monkeypatch.setattr(delivery, "TaskController", FakeController)
    monkeypatch.setattr(
        delivery,
        "find_task_document",
        lambda root, task_id: SimpleNamespace(
            task_id=task_id,
            executable=True,
            slug="operations",
            path=root / "codex-backlog" / "tasks" / "507-operations.md",
        ),
    )
    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue_507])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("owner",))
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue: (issue, []))

    candidates = delivery._queue_candidates()

    assert candidates[0]["task_id"] == "507"
    assert candidates[0]["state"] == "human_required"
    assert candidates[0]["risk_lane"] == "RED"
    assert "declared RED gate" in candidates[0]["blocker"]


def test_noncanonical_open_evidence_gated_issues_are_excluded_from_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issues = [
        {
            "number": 320,
            "title": "[Task 287 / SEO Growth Stage 2] evidence",
            "body": '<!-- yfc-task-contract:v1 -->\n{"version":1,"task_id":"287","scope":"evidence","acceptance":["remain blocked"],"dependencies":[],"owner_gate":"evidence_gate","risk_lane":"RED","issue_state":"blocked_on_evidence"}\n<!-- yfc-task-contract:v1 -->',
            "state": "open",
            "user": {"login": "owner"},
        },
        {
            "number": 323,
            "title": "[Task 290 / SEO Growth Stage 5] evidence",
            "body": '<!-- yfc-task-contract:v1 -->\n{"version":1,"task_id":"290","scope":"evidence","acceptance":["remain blocked"],"dependencies":[],"owner_gate":"evidence_gate","risk_lane":"RED","issue_state":"blocked_on_evidence"}\n<!-- yfc-task-contract:v1 -->',
            "state": "open",
            "user": {"login": "owner"},
        },
    ]

    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: issues)
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)

    assert delivery._task_issue_contracts() == {}


def test_queue_ignores_unbacked_local_specs_and_selects_issue_backed_product_task(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks_root = tmp_path / "codex-backlog" / "tasks"
    tasks_root.mkdir(parents=True)
    (tasks_root / "138-unbacked.md").write_text("unbacked", encoding="utf-8")
    (tasks_root / "505-progression.md").write_text("progression", encoding="utf-8")
    issue_505 = {
        "number": 505,
        "title": "[Task 505] progression",
        "body": render_task_contract(
            {
                "task_id": "505",
                "scope": "progression",
                "acceptance": ["deterministic proposals"],
                "dependencies": ["504"],
                "owner_gate": "behavior_contract",
                "risk_lane": "YELLOW",
                "source_spec": "codex-backlog/tasks/505-progression.md",
                "issue_state": "queued",
            }
        ),
        "state": "open",
        "user": {"login": "owner"},
    }

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
            return {"504"}

    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(delivery, "GitRepository", lambda root: object())
    monkeypatch.setattr(delivery, "TaskController", FakeController)
    monkeypatch.setattr(
        delivery,
        "find_task_document",
        lambda root, task_id: SimpleNamespace(
            task_id=task_id,
            executable=True,
            slug=f"task-{task_id}",
            path=root / "codex-backlog" / "tasks" / f"{task_id}-fixture.md",
        ),
    )
    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue_505])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("owner",))
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue: (issue, []))

    candidates = delivery._queue_candidates()

    assert [candidate["task_id"] for candidate in candidates] == ["505"]


def test_queue_inventory_skips_verified_legacy_active_contracts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks_root = tmp_path / "codex-backlog" / "tasks"
    tasks_root.mkdir(parents=True)
    (tasks_root / "505-progression.md").write_text("task", encoding="utf-8")
    current_body = render_task_contract(
        {
            "task_id": "505",
            "scope": "progression",
            "acceptance": ["deterministic proposals"],
            "dependencies": ["504"],
            "owner_gate": "none",
            "risk_lane": "GREEN",
            "source_spec": "codex-backlog/tasks/505-progression.md",
            "issue_state": "queued",
        }
    )
    issue_494 = {
        "number": 494,
        "title": "[Task 494] legacy completed",
        "body": """<!-- yfc-task-contract:v1 -->
{"version":1,"task_id":"494","scope":"legacy completed task","acceptance":["historical completion is preserved"],"dependencies":[],"owner_gate":"none","risk_lane":"YELLOW","issue_state":"completed"}
<!-- yfc-task-contract:v1 -->""",
        "state": "closed",
        "user": {"login": "owner"},
    }
    issue_448 = {
        "number": 448,
        "title": "[Task 346A] legacy active",
        "body": _legacy_active_body(
            "346A", source_spec="codex-backlog/tasks/346A-production-log-retention.md"
        ),
        "state": "closed",
        "user": {"login": "owner"},
    }
    issue_310 = {
        "number": 310,
        "title": "[Task 128H] legacy active",
        "body": _legacy_active_body("128H"),
        "state": "closed",
        "user": {"login": "owner"},
    }
    issue_505 = {
        "number": 505,
        "title": "[Task 505] progression",
        "body": current_body,
        "state": "open",
        "user": {"login": "owner"},
    }
    issues = [issue_494, issue_448, issue_310, issue_505]
    snapshots = {
        448: _legacy_control_snapshot(issue_448, task_id="346A", state="production_verified"),
        494: (issue_494, []),
        310: (issue_310, []),
        505: (issue_505, []),
    }

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
            return {"504", "128H"}

    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(delivery, "GitRepository", lambda root: object())
    monkeypatch.setattr(delivery, "TaskController", FakeController)
    monkeypatch.setattr(
        delivery,
        "find_task_document",
        lambda root, task_id: SimpleNamespace(
            task_id=task_id,
            executable=True,
            slug="progression",
            path=root / "codex-backlog" / "tasks" / "505-progression.md",
        ),
    )
    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: issues)
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("owner",))
    monkeypatch.setattr(
        delivery,
        "_control_issue_snapshot",
        lambda issue_number: snapshots[issue_number],
    )

    candidates = delivery._queue_candidates()

    assert [candidate["task_id"] for candidate in candidates] == ["505"]


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
        lambda **kwargs: {
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


def test_continuous_queue_claim_persists_active_task_until_delivery_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_dir = tmp_path / "git-common"
    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_dir)
    monkeypatch.setattr(delivery, "_current_process_instance_identity", _claim_process_instance)
    claim_path = common_dir / "codex-task-sessions-v1" / "continuous-queue.lock"

    with delivery._continuous_queue_claim(218) as queue_claim:
        initial = json.loads(claim_path.read_text(encoding="utf-8"))
        assert initial["queue_phase"] == "idle"
        assert initial["task_id"] is None
        assert initial["worker_state"] == "idle"

        queue_claim.mark_task("91", 219)
        active = json.loads(claim_path.read_text(encoding="utf-8"))
        assert active["queue_phase"] == "task_running"
        assert active["task_id"] == "91"
        assert active["task_issue"] == 219
        assert active["worker_state"] == "running"

        queue_claim.clear_task()
        cleared = json.loads(claim_path.read_text(encoding="utf-8"))
        assert cleared["queue_phase"] == "idle"
        assert cleared["task_id"] is None
        assert cleared["task_issue"] is None
        assert cleared["worker_state"] == "idle"

    assert not claim_path.exists()


def test_continuous_queue_claim_preserves_active_task_after_worker_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_dir = tmp_path / "git-common"
    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_dir)
    monkeypatch.setattr(delivery, "_current_process_instance_identity", _claim_process_instance)
    claim_path = common_dir / "codex-task-sessions-v1" / "continuous-queue.lock"

    with (
        pytest.raises(delivery.DeliveryError, match="worker failed"),
        delivery._continuous_queue_claim(218) as queue_claim,
    ):
        queue_claim.mark_task("91", 219)
        raise delivery.DeliveryError("worker failed")

    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    assert claim["queue_phase"] == "task_running"
    assert claim["task_id"] == "91"
    assert claim["worker_state"] == "running"
    claim_path.unlink()


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
                "queue_phase": "idle",
                "task_id": None,
                "task_issue": None,
                "worker_state": "idle",
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


def test_continuous_queue_claim_refuses_reclaim_of_interrupted_task(
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
                "queue_phase": "task_running",
                "task_id": "91",
                "task_issue": 219,
                "worker_state": "running",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_dir)
    monkeypatch.setattr(delivery, "_queue_owner_process_instance", lambda pid: None)
    monkeypatch.setattr(delivery, "_current_process_instance_identity", _claim_process_instance)

    with (
        pytest.raises(delivery.DeliveryError, match="interrupted Task 91"),
        delivery._continuous_queue_claim(218),
    ):
        pass

    assert claim_path.is_file()
    assert not list(claim_path.parent.glob("continuous-queue.lock.stale-*"))


def test_continuous_queue_claim_auto_reclaims_finished_task_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_dir = tmp_path / "git-common"
    state_root = common_dir / "codex-task-sessions-v1"
    claim_path = state_root / "continuous-queue.lock"
    history_path = state_root / "history" / "task-91.json"
    history_path.parent.mkdir(parents=True)
    old_claim = {
        "control_issue": 218,
        "pid": 424242,
        "process_instance": _claim_process_instance(),
        "started_at": "2026-09-09T08:00:00+00:00",
        "queue_phase": "task_running",
        "task_id": "91",
        "task_issue": 219,
        "worker_state": "running",
        "worker_state_path": str(tmp_path / "old-worker-state.json"),
    }
    claim_path.write_text(json.dumps(old_claim, sort_keys=True) + "\n", encoding="utf-8")
    history_path.write_text(
        json.dumps({"version": 2, "task_id": "91", "state": "finished"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_dir)
    monkeypatch.setattr(delivery, "_queue_owner_process_instance", lambda pid: None)
    monkeypatch.setattr(delivery, "_current_process_instance_identity", _claim_process_instance)
    monkeypatch.setattr(delivery, "_live_continuous_queue_supervisors", lambda: [])
    monkeypatch.setattr(delivery, "_live_task_workers", lambda: [])

    with delivery._continuous_queue_claim(218):
        current = json.loads(claim_path.read_text(encoding="utf-8"))
        assert current["queue_phase"] == "idle"
        assert current["task_id"] is None
        assert current["pid"] != 424242

    assert not claim_path.exists()
    assert not list(state_root.glob("continuous-queue.lock.stale-*"))


def test_continuous_queue_claim_keeps_finished_claim_when_other_worker_is_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common_dir = tmp_path / "git-common"
    state_root = common_dir / "codex-task-sessions-v1"
    claim_path = state_root / "continuous-queue.lock"
    history_path = state_root / "history" / "task-91.json"
    history_path.parent.mkdir(parents=True)
    claim_path.write_text(
        json.dumps(
            {
                "control_issue": 218,
                "pid": 424242,
                "process_instance": _claim_process_instance(),
                "started_at": "2026-09-09T08:00:00+00:00",
                "queue_phase": "task_running",
                "task_id": "91",
                "task_issue": 219,
                "worker_state": "running",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    history_path.write_text(
        json.dumps({"version": 2, "task_id": "91", "state": "finished"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_dir)
    monkeypatch.setattr(delivery, "_queue_owner_process_instance", lambda pid: None)
    monkeypatch.setattr(delivery, "_current_process_instance_identity", _claim_process_instance)
    monkeypatch.setattr(delivery, "_live_continuous_queue_supervisors", lambda: [])
    monkeypatch.setattr(delivery, "_live_task_workers", lambda: [(777, "live worker")])

    with (
        pytest.raises(delivery.DeliveryError, match="already has an active owner"),
        delivery._continuous_queue_claim(218),
    ):
        pass

    assert claim_path.is_file()


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
                "queue_phase": "idle",
                "task_id": None,
                "task_issue": None,
                "worker_state": "idle",
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
                "queue_phase": "idle",
                "task_id": None,
                "task_issue": None,
                "worker_state": "idle",
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
                "queue_phase": "idle",
                "task_id": None,
                "task_issue": None,
                "worker_state": "idle",
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
                args, 0, stdout="S<+ Wed Sep  9 10:00:00 2026\n", stderr=""
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
        ["ps", "-p", "424242", "-o", "state=", "-o", "lstart="],
        ["sysctl", "-n", "kern.boottime"],
    ]
    assert all(
        call[1]["shell"] is False and call[1]["timeout"] == 5 and call[1]["env"]["TZ"] == "UTC"
        for call in calls
    )


def test_queue_owner_identity_treats_macos_zombie_as_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout="Z Wed Sep  9 10:00:00 2026\n", stderr=""
        )

    monkeypatch.setattr(delivery.os, "name", "posix")
    monkeypatch.setattr(delivery.sys, "platform", "darwin")
    monkeypatch.setattr(delivery.subprocess, "run", fake_run)

    assert delivery._queue_owner_process_instance(424242) is None
    assert calls == [["ps", "-p", "424242", "-o", "state=", "-o", "lstart="]]


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
    monkeypatch.setattr(
        delivery,
        "_prepare_agent_flow",
        lambda *args, **kwargs: (
            {
                "worker_role_passes": [{"name": "implementer"}],
                "graphify": {"bootstrap_required": False},
                "agent_budget": _agent_budget(),
            },
            tmp_path / "agent-flow.json",
        ),
    )
    monkeypatch.setattr(
        delivery,
        "_prepare_skill_safety",
        lambda *args, **kwargs: ({}, tmp_path / "skill-safety.json"),
    )
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


def test_resumed_cli_failure_returns_to_human_required_before_worker_claim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifacts = tmp_path / "delivery"
    artifacts.mkdir()
    started = {
        "lease": {
            "branch": "task/504-program-import-coaching-rules-foundation",
            "worktree": str(tmp_path / "worktree"),
        },
        "control_state": {"state": "blocked", "blocker": "worker exited with code 2"},
        "preimplementation_resume": {
            "state": "prepared",
            "last_preimplementation_failure": {
                "kind": "codex_cli_argument_conflict_before_implementation"
            },
        },
    }
    status_updates: list[dict[str, Any]] = []
    monkeypatch.setattr(delivery, "_start", lambda *args, **kwargs: started)
    monkeypatch.setattr(delivery, "_artifact_root", lambda task_id: artifacts)
    monkeypatch.setattr(
        delivery,
        "_prepare_agent_flow",
        lambda *args, **kwargs: (
            {
                "worker_role_passes": [{"name": "implementer"}],
                "graphify": {"bootstrap_required": False},
                "agent_budget": _agent_budget(),
            },
            tmp_path / "agent-flow.json",
        ),
    )
    monkeypatch.setattr(
        delivery,
        "_prepare_skill_safety",
        lambda *args, **kwargs: ({}, tmp_path / "skill-safety.json"),
    )
    monkeypatch.setattr(delivery, "_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        delivery,
        "_post_control_state",
        lambda _issue, payload: status_updates.append(dict(payload)),
    )

    def launch(*args: Any, **kwargs: Any) -> int:
        del args, kwargs
        assert status_updates[-1]["state"] == "human_required"
        assert "before implementation" in status_updates[-1]["blocker"]
        assert "worker-state" in status_updates[-1]["blocker"]
        return 23

    monkeypatch.setattr(delivery, "_launch_worker", launch)
    monkeypatch.setattr(delivery, "_history", lambda task_id: None)

    with pytest.raises(delivery.DeliveryError, match="Worker exited with code 23"):
        delivery._deliver_one(
            "504",
            session_label="test",
            poll_seconds=10,
            max_wait_minutes=1,
            offline=False,
            control_issue=504,
            resume_reason="owner-authorized retry after merged controller CLI fix",
        )

    assert status_updates[0]["state"] == "human_required"


def test_second_guard_budget_failure_exhausts_one_time_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifacts = tmp_path / "delivery"
    artifacts.mkdir()
    (artifacts / "worker-guard.json").write_text(
        json.dumps({"block_reason_code": "TOOL_ACTION_BUDGET_EXCEEDED"}),
        encoding="utf-8",
    )
    started = {
        "lease": {
            "branch": "task/504-program-import-coaching-rules-foundation",
            "worktree": str(tmp_path / "worktree"),
        },
        "control_state": {
            "state": "blocked",
            "blocker": "worker guard blocked execution (TOOL_ACTION_BUDGET_EXCEEDED)",
        },
        "preimplementation_resume": {
            "state": "prepared",
            "guard_budget_recovery": {"recovery_attempt_number": 1},
        },
    }
    status_updates: list[dict[str, Any]] = []
    monkeypatch.setattr(delivery, "_start", lambda *args, **kwargs: started)
    monkeypatch.setattr(delivery, "_artifact_root", lambda task_id: artifacts)
    monkeypatch.setattr(
        delivery,
        "_prepare_agent_flow",
        lambda *args, **kwargs: (
            {
                "worker_role_passes": [{"name": "implementer"}],
                "graphify": {"bootstrap_required": False},
                "agent_budget": _agent_budget(),
            },
            tmp_path / "agent-flow.json",
        ),
    )
    monkeypatch.setattr(
        delivery, "_prepare_skill_safety", lambda *args, **kwargs: ({}, tmp_path / "skills.json")
    )
    monkeypatch.setattr(delivery, "_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        delivery,
        "_controller_payload",
        lambda *args, **kwargs: {"preimplementation_resume": {"state": "worker-started"}},
    )
    monkeypatch.setattr(
        delivery,
        "_post_control_state",
        lambda _issue, payload: status_updates.append(dict(payload)),
    )

    def guard_stop(*args: Any, **kwargs: Any) -> int:
        del args
        kwargs["on_command_started"](artifacts / "worker-state.json")
        return delivery.WORKER_GUARD_EXIT_CODE

    monkeypatch.setattr(delivery, "_launch_worker", guard_stop)
    monkeypatch.setattr(delivery, "_history", lambda task_id: None)

    with pytest.raises(delivery.DeliveryError, match="one-time guard-budget recovery"):
        delivery._deliver_one(
            "504",
            session_label="test",
            poll_seconds=10,
            max_wait_minutes=1,
            offline=False,
            control_issue=504,
            resume_reason="owner-authorized one-time guard recovery",
            resume_guard_interrupted=True,
        )

    assert [item["state"] for item in status_updates] == [
        "human_required",
        "in_progress",
        "human_required",
    ]
    assert "no further automatic guard recovery is allowed" in status_updates[-1]["blocker"]


def test_second_post_start_transport_failure_exhausts_one_time_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifacts = tmp_path / "delivery"
    artifacts.mkdir()
    started = {
        "lease": {
            "branch": "task/504-program-import-coaching-rules-foundation",
            "worktree": str(tmp_path / "worktree"),
        },
        "control_state": {
            "state": "human_required",
            "blocker": "worker stopped after post_start_external_transport_interruption",
        },
        "preimplementation_resume": {
            "state": "prepared",
            "transport_interruption_recovery": {"recovery_attempt_number": 1},
        },
    }
    status_updates: list[dict[str, Any]] = []
    monkeypatch.setattr(delivery, "_start", lambda *args, **kwargs: started)
    monkeypatch.setattr(delivery, "_artifact_root", lambda task_id: artifacts)
    monkeypatch.setattr(
        delivery,
        "_prepare_agent_flow",
        lambda *args, **kwargs: (
            {
                "worker_role_passes": [{"name": "implementer"}],
                "graphify": {"bootstrap_required": False},
                "agent_budget": _agent_budget(),
            },
            tmp_path / "agent-flow.json",
        ),
    )
    monkeypatch.setattr(
        delivery, "_prepare_skill_safety", lambda *args, **kwargs: ({}, tmp_path / "skills.json")
    )
    monkeypatch.setattr(delivery, "_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        delivery,
        "_controller_payload",
        lambda *args, **kwargs: {"preimplementation_resume": {"state": "worker-started"}},
    )
    monkeypatch.setattr(
        delivery,
        "_post_control_state",
        lambda _issue, payload: status_updates.append(dict(payload)),
    )
    monkeypatch.setattr(delivery, "_launch_worker", lambda *args, **kwargs: 23)
    monkeypatch.setattr(delivery, "_history", lambda task_id: None)

    with pytest.raises(delivery.DeliveryError, match="one-time post-start transport recovery"):
        delivery._deliver_one(
            "504",
            session_label="test",
            poll_seconds=10,
            max_wait_minutes=1,
            offline=False,
            control_issue=504,
            resume_reason="owner-authorized one-time post-start transport recovery",
            resume_transport_interrupted=True,
        )

    assert [item["state"] for item in status_updates] == ["human_required", "human_required"]
    assert "no further automatic transport recovery is allowed" in status_updates[-1]["blocker"]


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
    monkeypatch.setattr(
        delivery,
        "_prepare_agent_flow",
        lambda *args, **kwargs: (
            {
                "worker_role_passes": [{"name": "implementer"}],
                "graphify": {"bootstrap_required": False},
                "agent_budget": _agent_budget(),
            },
            tmp_path / "agent-flow.json",
        ),
    )
    monkeypatch.setattr(
        delivery,
        "_prepare_skill_safety",
        lambda *args, **kwargs: ({}, tmp_path / "skill-safety.json"),
    )
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
    monkeypatch.setattr(
        delivery,
        "_prepare_agent_flow",
        lambda *args, **kwargs: (
            {
                "worker_role_passes": [{"name": "implementer"}],
                "graphify": {"bootstrap_required": False},
                "agent_budget": _agent_budget(),
            },
            tmp_path / "agent-flow.json",
        ),
    )
    monkeypatch.setattr(
        delivery,
        "_prepare_skill_safety",
        lambda *args, **kwargs: ({}, tmp_path / "skill-safety.json"),
    )
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


def _owner_reconcile_claim(
    common_dir: Path,
    *,
    task_id: str = "506",
    task_issue: int = 506,
    control_issue: int = 550,
    queue_phase: str = "task_running",
) -> tuple[Path, str]:
    claim_path = common_dir / "codex-task-sessions-v1" / "continuous-queue.lock"
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    claim = {
        "control_issue": control_issue,
        "pid": 424242,
        "process_instance": _claim_process_instance(),
        "started_at": "2026-09-28T18:42:33.740847+00:00",
        "queue_phase": queue_phase,
        "task_id": task_id if queue_phase == "task_running" else None,
        "task_issue": task_issue if queue_phase == "task_running" else None,
        "worker_state": "running" if queue_phase == "task_running" else "idle",
        "worker_state_path": None,
    }
    content = json.dumps(claim, ensure_ascii=True, sort_keys=True) + "\n"
    claim_path.write_text(content, encoding="utf-8")
    return claim_path, content


def _configure_owner_reconcile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    leases: list[dict[str, Any]] | None = None,
    process_lines: list[tuple[int, str]] | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    common_root = tmp_path / "git-common"
    worktree = tmp_path / ".artifacts" / "worktrees" / "506-program-lifecycle"
    worktree.mkdir(parents=True)
    branch = "task/506-product-v4-stage-2-program-lifecycle"
    lease = {
        "task_id": "506",
        "mode": "write",
        "lifecycle_state": "implementation",
        "queue_mode": True,
        "queue_budget": {
            "review_fix_cycles": 0,
            "ci_fix_cycles": 0,
            "scope_expansions": 0,
            "events": [],
        },
        "branch": branch,
        "worktree": str(worktree),
    }
    current_leases = leases if leases is not None else [lease]

    class FakeRepository:
        def __init__(self, root: Path) -> None:
            del root

        def worktrees(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(path=worktree.resolve(), branch=branch)]

        def local_branches(self) -> list[dict[str, str]]:
            return [{"branch": branch}]

        def current_branch(self, *, cwd: Path | None = None) -> str:
            del cwd
            return branch

    FakeRepository.common_dir = common_root
    FakeRepository.repository_root = tmp_path
    FakeRepository.current_worktree = tmp_path

    class FakeStore:
        def all_leases(self) -> list[dict[str, Any]]:
            return current_leases

        def delivery_state(self) -> dict[str, Any]:
            return {"owner": None}

        def lock(self) -> Any:
            return nullcontext()

    class FakeController:
        def __init__(self, repository: object) -> None:
            del repository
            self.store = FakeStore()

    task_issue = {
        "number": 506,
        "state": "OPEN",
        "title": "[Task 506] Product v4",
        "user": {"login": "MikeMoore1337"},
    }
    task_state = delivery.control_state_payload(
        task_id="506",
        state="human_required",
        issue_number=506,
        branch=branch,
        blocker="worker returned before terminal controller finish",
    )
    comments = [
        {
            "id": 1,
            "created_at": "2026-09-28T20:12:46Z",
            "user": {"login": "MikeMoore1337"},
            "body": delivery.render_control_state_comment(task_state),
        }
    ]
    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_root)
    monkeypatch.setattr(delivery, "GitRepository", FakeRepository)
    monkeypatch.setattr(delivery, "TaskController", FakeController)
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("MikeMoore1337",))
    monkeypatch.setattr(
        delivery,
        "_queue_authorization_snapshot",
        lambda issue: ({"number": issue, "state": "OPEN"}, [], {"active": True}),
    )
    monkeypatch.setattr(
        delivery,
        "_control_issue_snapshot",
        lambda issue: (task_issue, comments) if issue == 506 else ({"number": issue}, []),
    )
    monkeypatch.setattr(delivery, "_queue_owner_is_alive", lambda pid, identity: False)
    monkeypatch.setattr(
        delivery,
        "_running_process_command_lines",
        lambda: process_lines or [],
        raising=False,
    )
    monkeypatch.setattr(
        delivery,
        "_record_queue_reconciliation_evidence",
        lambda **kwargs: None,
        raising=False,
    )
    claim_path, _ = _owner_reconcile_claim(common_root)
    return claim_path, worktree, lease


def _configure_prelease_reconcile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    leases: list[dict[str, Any]] | None = None,
    process_lines: list[tuple[int, str]] | None = None,
) -> tuple[Path, Any, dict[str, Any]]:
    common_root = tmp_path / "git-common"
    current_leases = leases if leases is not None else []
    history_root = common_root / "codex-task-sessions-v1" / "history"

    class FakeRepository:
        def __init__(self, root: Path) -> None:
            del root

        def worktrees(self) -> list[SimpleNamespace]:
            return []

        def local_branches(self) -> list[dict[str, str]]:
            return []

        def operation_issues(self, path: Path) -> list[str]:
            del path
            return []

        def git(self, *args: str, **kwargs: Any) -> str:
            del args, kwargs
            return ""

    FakeRepository.common_dir = common_root
    FakeRepository.repository_root = tmp_path
    FakeRepository.current_worktree = tmp_path

    class FakeStore:
        history = history_root

        def all_leases(self) -> list[dict[str, Any]]:
            return current_leases

        def delivery_state(self) -> dict[str, Any]:
            return {"owner": None}

        def lock(self) -> Any:
            return nullcontext()

    class FakeController:
        def __init__(self, repository: object) -> None:
            del repository
            self.store = FakeStore()

    task_issue = {
        "number": 507,
        "state": "OPEN",
        "title": "[Task 507] Product v4",
        "user": {"login": "MikeMoore1337"},
    }
    task_state = delivery.control_state_payload(task_id="507", state="queued", issue_number=507)
    comments = [
        {
            "id": 1,
            "created_at": "2026-09-29T10:03:00Z",
            "user": {"login": "MikeMoore1337"},
            "body": delivery.render_control_state_comment(task_state),
        }
    ]
    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(delivery, "_git_common_dir", lambda: common_root)
    monkeypatch.setattr(delivery, "GitRepository", FakeRepository)
    monkeypatch.setattr(delivery, "TaskController", FakeController)
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("MikeMoore1337",))
    monkeypatch.setattr(
        delivery,
        "_queue_authorization_snapshot",
        lambda issue: ({"number": issue, "state": "OPEN"}, [], {"active": True}),
    )
    monkeypatch.setattr(
        delivery,
        "_control_issue_snapshot",
        lambda issue: (task_issue, comments) if issue == 507 else ({"number": issue}, []),
    )
    monkeypatch.setattr(delivery, "_open_task_pull_requests", lambda task_id: [])
    monkeypatch.setattr(delivery, "_queue_owner_is_alive", lambda pid, identity: False)
    monkeypatch.setattr(
        delivery,
        "_running_process_command_lines",
        lambda: process_lines or [],
        raising=False,
    )
    monkeypatch.setattr(
        delivery,
        "_record_queue_reconciliation_evidence",
        lambda **kwargs: kwargs,
        raising=False,
    )
    claim_path, _ = _owner_reconcile_claim(
        common_root, task_id="507", task_issue=507, control_issue=567
    )
    return claim_path, FakeStore(), current_leases


def test_owner_reconcile_cli_contract_is_explicit() -> None:
    args = delivery._parser().parse_args(
        [
            "506",
            "--reconcile-interrupted-queue-claim",
            "--control-issue",
            "550",
            "--reconcile-reason",
            "owner-authorized stale claim recovery",
            "--owner-authorize",
        ]
    )

    assert args.task_id == "506"
    assert args.reconcile_interrupted_queue_claim is True
    assert args.control_issue == 550
    assert args.reconcile_reason == "owner-authorized stale claim recovery"
    assert args.owner_authorize is True


def test_owner_reconcile_requires_explicit_authorization_and_preserves_claim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    claim_path, _, _ = _configure_owner_reconcile(monkeypatch, tmp_path)
    original = claim_path.read_bytes()

    with pytest.raises(delivery.DeliveryError, match="explicit owner authorization"):
        delivery._reconcile_interrupted_queue_claim(
            "506", control_issue=550, reason="resume stale queue", owner_authorize=False
        )

    assert claim_path.read_bytes() == original


def test_owner_reconcile_refuses_live_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    claim_path, _, _ = _configure_owner_reconcile(monkeypatch, tmp_path)
    monkeypatch.setattr(delivery, "_queue_owner_is_alive", lambda pid, identity: True)

    with pytest.raises(delivery.DeliveryError, match="owner PID 424242 is still live"):
        delivery._reconcile_interrupted_queue_claim(
            "506", control_issue=550, reason="resume stale queue", owner_authorize=True
        )

    assert claim_path.is_file()


@pytest.mark.parametrize(
    ("task_id", "control_issue", "message"),
    (
        ("505", 550, "task identity"),
        ("506", 551, "control Issue"),
    ),
)
def test_owner_reconcile_refuses_claim_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    task_id: str,
    control_issue: int,
    message: str,
) -> None:
    claim_path, _, _ = _configure_owner_reconcile(monkeypatch, tmp_path)

    with pytest.raises(delivery.DeliveryError, match=message):
        delivery._reconcile_interrupted_queue_claim(
            task_id, control_issue=control_issue, reason="resume stale queue", owner_authorize=True
        )

    assert claim_path.is_file()


@pytest.mark.parametrize(
    "leases",
    (
        [],
        [
            {
                "task_id": "506",
                "mode": "write",
                "lifecycle_state": "implementation",
                "queue_mode": True,
                "branch": "task/506-product-v4-stage-2-program-lifecycle",
                "worktree": "C:/one",
            },
            {
                "task_id": "506",
                "mode": "write",
                "lifecycle_state": "implementation",
                "queue_mode": True,
                "branch": "task/506-product-v4-stage-2-program-lifecycle",
                "worktree": "C:/two",
            },
        ],
    ),
)
def test_owner_reconcile_refuses_missing_or_ambiguous_lease(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, leases: list[dict[str, Any]]
) -> None:
    claim_path, _, _ = _configure_owner_reconcile(monkeypatch, tmp_path, leases=leases)

    with pytest.raises(delivery.DeliveryError, match="exactly one task lease"):
        delivery._reconcile_interrupted_queue_claim(
            "506", control_issue=550, reason="resume stale queue", owner_authorize=True
        )

    assert claim_path.is_file()


def test_owner_reconcile_refuses_ambiguous_lease_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lease = {
        "task_id": "506",
        "mode": "write",
        "lifecycle_state": "magic-state",
        "queue_mode": True,
        "branch": "task/506-product-v4-stage-2-program-lifecycle",
        "worktree": str(tmp_path / ".artifacts" / "worktrees" / "506-program-lifecycle"),
    }
    claim_path, _, _ = _configure_owner_reconcile(monkeypatch, tmp_path, leases=[lease])

    with pytest.raises(delivery.DeliveryError, match="ambiguous lifecycle"):
        delivery._reconcile_interrupted_queue_claim(
            "506", control_issue=550, reason="resume stale queue", owner_authorize=True
        )

    assert claim_path.is_file()


@pytest.mark.parametrize(
    "process_lines",
    (
        [(3101, "python scripts/run_task_delivery.py --continue-queue --control-issue 550")],
        [(3102, "python scripts/run_task_delivery.py --worker-supervisor --task 504")],
    ),
)
def test_owner_reconcile_refuses_live_queue_or_task_worker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    process_lines: list[tuple[int, str]],
) -> None:
    claim_path, _, _ = _configure_owner_reconcile(
        monkeypatch, tmp_path, process_lines=process_lines
    )

    with pytest.raises(delivery.DeliveryError, match="live"):
        delivery._reconcile_interrupted_queue_claim(
            "506", control_issue=550, reason="resume stale queue", owner_authorize=True
        )

    assert claim_path.is_file()


def test_owner_reconcile_refuses_claim_drift_before_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    claim_path, _, _ = _configure_owner_reconcile(monkeypatch, tmp_path)
    original_read = delivery._read_queue_claim
    calls = 0

    def changed_read(path: Path) -> tuple[str, dict[str, Any]] | None:
        nonlocal calls
        calls += 1
        snapshot = original_read(path)
        if snapshot is None or calls != 2:
            return snapshot
        content, claim = snapshot
        return content + "drift", claim

    monkeypatch.setattr(delivery, "_read_queue_claim", changed_read)
    with pytest.raises(delivery.DeliveryError, match="changed before owner-authorized"):
        delivery._reconcile_interrupted_queue_claim(
            "506", control_issue=550, reason="resume stale queue", owner_authorize=True
        )

    assert claim_path.is_file()


def test_owner_reconcile_task_506_preserves_lease_and_reclaims_claim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    claim_path, worktree, lease = _configure_owner_reconcile(monkeypatch, tmp_path)
    before_lease = json.loads(json.dumps(lease))
    evidence: list[dict[str, Any]] = []
    monkeypatch.setattr(
        delivery,
        "_record_queue_reconciliation_evidence",
        lambda **kwargs: evidence.append(kwargs) or None,
    )

    result = delivery._reconcile_interrupted_queue_claim(
        "506",
        control_issue=550,
        reason="owner-authorized resume after stale interrupted queue worker",
        owner_authorize=True,
    )

    assert result["task_id"] == "506"
    assert result["control_issue"] == 550
    assert not claim_path.exists()
    assert lease == before_lease
    assert worktree.is_dir()
    assert evidence and evidence[0]["task_id"] == "506"


def test_owner_reconcile_allows_fresh_queue_claim_after_reclaim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    claim_path, _, _ = _configure_owner_reconcile(monkeypatch, tmp_path)
    delivery._reconcile_interrupted_queue_claim(
        "506", control_issue=550, reason="owner-authorized resume", owner_authorize=True
    )
    monkeypatch.setattr(delivery, "_current_process_instance_identity", _claim_process_instance)

    with delivery._continuous_queue_claim(550):
        assert claim_path.is_file()
        assert json.loads(claim_path.read_text(encoding="utf-8"))["queue_phase"] == "idle"

    assert not claim_path.exists()


def test_owner_reconcile_recovers_verified_prelease_start_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    claim_path, _, leases = _configure_prelease_reconcile(monkeypatch, tmp_path)
    evidence: list[dict[str, Any]] = []
    monkeypatch.setattr(
        delivery,
        "_record_queue_reconciliation_evidence",
        lambda **kwargs: evidence.append(kwargs) or "prelease-evidence.json",
    )

    result = delivery._reconcile_interrupted_queue_claim(
        "507",
        control_issue=567,
        reason="reconcile verified pre-lease start failure",
        owner_authorize=True,
    )

    assert result["classification"] == "pre_lease_start_failure"
    assert not claim_path.exists()
    assert leases == []
    assert evidence[0]["classification"] == "pre_lease_start_failure"
    assert evidence[0]["reconciliation"]["lease_count"] == 0


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("lease", "acquired"),
        ("history", "production/history"),
        ("worker_state", "worker-state"),
        ("branch", "local branch"),
        ("delivery", "delivery lane"),
    ),
)
def test_owner_reconcile_prelease_rereads_all_safety_evidence_before_reclaim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    claim_path, store, leases = _configure_prelease_reconcile(monkeypatch, tmp_path)
    original_all_leases = store.all_leases
    calls = 0

    if mutation == "lease":
        lease = {
            "task_id": "507",
            "mode": "write",
            "lifecycle_state": "implementation",
            "queue_mode": True,
        }

        def lease_after_first() -> list[dict[str, Any]]:
            nonlocal calls
            calls += 1
            return [] if calls == 1 else [lease]

        monkeypatch.setattr(type(store), "all_leases", lambda self: lease_after_first())
    elif mutation == "history":
        history_path = (
            tmp_path / "git-common" / "codex-task-sessions-v1" / "history" / "task-507.json"
        )
        history_path.parent.mkdir(parents=True)
        history_path.write_text("{}", encoding="utf-8")
    elif mutation == "worker_state":
        monkeypatch.setattr(
            delivery,
            "_task_worker_state_evidence",
            lambda task_id: [str(tmp_path / "worker-state.json")],
        )
    elif mutation == "branch":
        fake_branch = {"branch": "task/507-product-v4"}
        monkeypatch.setattr(
            delivery.GitRepository,
            "local_branches",
            lambda self: [fake_branch],
        )
    elif mutation == "delivery":
        monkeypatch.setattr(
            type(store),
            "delivery_state",
            lambda self: {"owner": {"task_id": "507"}},
        )
    else:
        raise AssertionError(mutation)

    with pytest.raises(delivery.DeliveryError, match=message):
        delivery._reconcile_interrupted_queue_claim(
            "507",
            control_issue=567,
            reason="reconcile verified pre-lease start failure",
            owner_authorize=True,
        )

    assert claim_path.exists()
    assert original_all_leases() == leases


def test_owner_reconcile_prelease_refuses_live_worker_and_nonqueued_task(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    claim_path, _, _ = _configure_prelease_reconcile(
        monkeypatch,
        tmp_path,
        process_lines=[
            (3102, "python scripts/run_task_delivery.py --worker-supervisor --task 507")
        ],
    )

    with pytest.raises(delivery.DeliveryError, match="live"):
        delivery._reconcile_interrupted_queue_claim(
            "507", control_issue=567, reason="resume stale queue", owner_authorize=True
        )
    assert claim_path.exists()

    claim_path.unlink()
    claim_path, _, _ = _configure_prelease_reconcile(monkeypatch, tmp_path)
    task_issue, comments = delivery._control_issue_snapshot(507)
    in_progress = delivery.control_state_payload(
        task_id="507", state="in_progress", issue_number=507
    )
    comments[:] = [
        {
            "id": 2,
            "created_at": "2026-09-29T10:04:00Z",
            "user": {"login": "MikeMoore1337"},
            "body": delivery.render_control_state_comment(in_progress),
        }
    ]
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue: (task_issue, comments))

    with pytest.raises(delivery.DeliveryError, match="latest state queued"):
        delivery._reconcile_interrupted_queue_claim(
            "507", control_issue=567, reason="resume stale queue", owner_authorize=True
        )
    assert claim_path.exists()


def test_owner_reconcile_prelease_refuses_live_queue_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    claim_path, _, _ = _configure_prelease_reconcile(monkeypatch, tmp_path)
    monkeypatch.setattr(delivery, "_queue_owner_is_alive", lambda pid, identity: True)

    with pytest.raises(delivery.DeliveryError, match="owner PID 424242 is still live"):
        delivery._reconcile_interrupted_queue_claim(
            "507", control_issue=567, reason="resume stale queue", owner_authorize=True
        )
    assert claim_path.exists()


def test_owner_reconcile_prelease_refuses_open_task_pull_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    claim_path, _, _ = _configure_prelease_reconcile(monkeypatch, tmp_path)
    monkeypatch.setattr(
        delivery,
        "_open_task_pull_requests",
        lambda task_id: [{"number": 577, "head": {"ref": "task/507-product-v4"}}],
    )

    with pytest.raises(delivery.DeliveryError, match="open task pull request"):
        delivery._reconcile_interrupted_queue_claim(
            "507", control_issue=567, reason="resume stale queue", owner_authorize=True
        )
    assert claim_path.exists()


def test_queue_allows_yellow_visual_gate_to_enter_implementation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tasks_root = tmp_path / "codex-backlog" / "tasks"
    tasks_root.mkdir(parents=True)
    (tasks_root / "520-workout.md").write_text("workout", encoding="utf-8")
    issue = {
        "number": 616,
        "title": "[Task 520] workout",
        "body": render_task_contract(
            {
                "task_id": "520",
                "scope": "Workout execution v2",
                "acceptance": ["owner visual acceptance remains required before rollout"],
                "dependencies": ["519"],
                "owner_gate": "owner_visual_acceptance",
                "risk_lane": "YELLOW",
                "source_spec": "codex-backlog/tasks/520-workout.md",
                "issue_state": "queued",
            }
        ),
        "state": "open",
        "user": {"login": "owner"},
    }

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
            return {"519"}

    monkeypatch.setattr(delivery, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(delivery, "GitRepository", lambda root: object())
    monkeypatch.setattr(delivery, "TaskController", FakeController)
    monkeypatch.setattr(
        delivery,
        "find_task_document",
        lambda root, task_id: SimpleNamespace(
            task_id=task_id,
            executable=True,
            slug="workout",
            path=root / "codex-backlog" / "tasks" / "520-workout.md",
        ),
    )
    monkeypatch.setattr(delivery, "_github_json", lambda endpoint: [issue])
    monkeypatch.setattr(delivery, "_issue_authorized", lambda issue: True)
    monkeypatch.setattr(delivery, "_trusted_issue_logins", lambda issue: ("owner",))
    monkeypatch.setattr(delivery, "_control_issue_snapshot", lambda issue: (issue, []))

    candidates = delivery._queue_candidates()

    assert candidates[0]["task_id"] == "520"
    assert candidates[0]["state"] == "queued"
    assert candidates[0]["risk_lane"] == "YELLOW"


def test_resolve_codex_cli_prefers_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delivery.shutil, "which", lambda name: "C:/tools/codex.exe")

    assert delivery._resolve_codex_cli() == "C:/tools/codex.exe"


def test_windows_codex_desktop_fallback_chooses_newest_candidate(tmp_path: Path) -> None:
    root = tmp_path / "OpenAI" / "Codex" / "bin"
    old = root / "old" / "codex.exe"
    new = root / "new" / "codex.exe"
    old.parent.mkdir(parents=True)
    new.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    delivery.os.utime(old, ns=(100, 100))
    delivery.os.utime(new, ns=(200, 200))

    resolved = delivery._windows_codex_desktop_fallback(str(tmp_path))

    assert resolved == str(new.resolve())


def test_windows_codex_desktop_fallback_fails_closed_without_candidate(tmp_path: Path) -> None:
    (tmp_path / "OpenAI" / "Codex" / "bin").mkdir(parents=True)

    assert delivery._windows_codex_desktop_fallback(str(tmp_path)) is None


def test_main_uses_shared_codex_resolver_before_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: list[str] = []

    monkeypatch.setattr(delivery.shutil, "which", lambda name: None)
    monkeypatch.setattr(delivery, "_resolve_codex_cli", lambda: "C:/native/codex.exe")
    monkeypatch.setattr(
        delivery,
        "_deliver_one",
        lambda task_id, **kwargs: delivered.append(task_id),
    )

    assert delivery.main(["520", "--offline"]) == 0
    assert delivered == ["520"]
