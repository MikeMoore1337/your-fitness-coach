from __future__ import annotations

import json

from scripts.worker_guard import GuardLimits, WorkerEventGuard


def _limits(**overrides: int) -> GuardLimits:
    values = {
        "max_completed_tool_actions": 50,
        "max_collab_tool_calls": 4,
        "max_spawned_subagents": 2,
        "max_concurrent_subagents": 2,
        "max_identical_failed_actions": 4,
        "max_identical_actions_without_progress": 8,
        "short_cycle_period_max": 3,
        "short_cycle_repetitions": 4,
    }
    values.update(overrides)
    return GuardLimits.from_mapping(values)


def _command(command: str, *, exit_code: int = 0, output: str = "ok") -> dict[str, object]:
    return {
        "type": "item.completed",
        "item": {
            "id": f"cmd-{command}-{exit_code}",
            "type": "command_execution",
            "command": command,
            "aggregated_output": output,
            "exit_code": exit_code,
            "status": "completed" if exit_code == 0 else "failed",
        },
    }


def _file_change() -> dict[str, object]:
    return {
        "type": "item.completed",
        "item": {
            "id": "patch-1",
            "type": "file_change",
            "status": "completed",
            "changes": [{"path": "x.py", "kind": "update"}],
        },
    }


def _collab(
    item_id: str,
    *,
    tool: str = "spawn_agent",
    receivers: list[str] | None = None,
    states: dict[str, dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "type": "item.started",
        "item": {
            "id": item_id,
            "type": "collab_tool_call",
            "tool": tool,
            "receiver_thread_ids": receivers or [],
            "prompt": "private subagent prompt",
            "agents_states": states or {},
            "status": "in_progress",
        },
    }


def test_normal_worker_activity_passes() -> None:
    guard = WorkerEventGuard(_limits())

    assert guard.observe_event(_command("pytest tests/test_x.py -q")).blocked is False
    assert guard.observe_event(_file_change()).blocked is False
    assert guard.observe_event(_command("pytest tests/test_x.py -q")).blocked is False

    report = guard.report()
    assert report["blocked"] is False
    assert report["counters"]["completed_tool_actions"] == 2
    assert report["counters"]["progress_events"] == 1


def test_file_change_progress_resets_repeated_failure_history() -> None:
    guard = WorkerEventGuard(_limits())

    for _ in range(3):
        assert (
            guard.observe_event(_command("pytest", exit_code=1, output="same failure")).blocked
            is False
        )
    assert guard.observe_event(_file_change()).blocked is False
    for _ in range(3):
        assert (
            guard.observe_event(_command("pytest", exit_code=1, output="same failure")).blocked
            is False
        )

    assert guard.report()["blocked"] is False


def test_repeated_identical_failed_action_blocks() -> None:
    guard = WorkerEventGuard(_limits())

    decision = None
    for _ in range(4):
        decision = guard.observe_event(_command("pytest", exit_code=1, output="same failure"))

    assert decision is not None
    assert decision.blocked is True
    assert decision.reason_code == "IDENTICAL_FAILED_ACTION_LOOP"
    report = guard.report()
    assert report["blocked"] is True
    assert isinstance(report["block_signature_hash"], str)
    serialized = json.dumps(report)
    assert "same failure" not in serialized
    assert "pytest" not in serialized


def test_short_abab_cycle_blocks_after_bounded_repetition() -> None:
    guard = WorkerEventGuard(_limits())

    decision = None
    for command in ["a", "b"] * 4:
        decision = guard.observe_event(_command(command))

    assert decision is not None
    assert decision.blocked is True
    assert decision.reason_code == "SHORT_TOOL_CYCLE_WITHOUT_PROGRESS"


def test_malformed_non_json_line_is_non_blocking() -> None:
    guard = WorkerEventGuard(_limits())

    decision = guard.observe_line(b"ordinary stderr text\n")

    assert decision.blocked is False
    assert guard.report()["counters"]["malformed_lines"] == 1


def test_subagent_spawn_budget_is_enforced() -> None:
    guard = WorkerEventGuard(
        _limits(
            max_collab_tool_calls=2,
            max_spawned_subagents=1,
            max_concurrent_subagents=1,
        )
    )

    first = guard.observe_event(
        _collab(
            "collab-1",
            receivers=["thread-a"],
            states={"thread-a": {"status": "running"}},
        )
    )
    second = guard.observe_event(
        _collab(
            "collab-2",
            receivers=["thread-b"],
            states={"thread-b": {"status": "running"}},
        )
    )

    assert first.blocked is False
    assert second.blocked is True
    assert second.reason_code == "SUBAGENT_BUDGET_EXCEEDED"


def test_zero_collab_budget_blocks_first_spawn() -> None:
    guard = WorkerEventGuard(
        _limits(
            max_collab_tool_calls=0,
            max_spawned_subagents=0,
            max_concurrent_subagents=0,
        )
    )

    decision = guard.observe_event(_collab("collab-1", receivers=["thread-a"]))

    assert decision.blocked is True
    assert decision.reason_code == "COLLAB_TOOL_BUDGET_EXCEEDED"
