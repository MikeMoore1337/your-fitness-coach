from __future__ import annotations

import pytest
from scripts.issue_workflow import (
    CONTROL_STATE_MARKER,
    DEFAULT_QUEUE_BUDGET,
    IssueWorkflowError,
    QueueBudget,
    control_state_payload,
    latest_control_state,
    parse_control_state_comment,
    parse_queue_budget_report,
    parse_task_contract,
    queue_authorization,
    render_control_state_comment,
    render_queue_budget_report,
    render_task_contract,
    task_contract_payload,
    task_risk_lane,
    validate_control_transition,
)


def test_control_state_round_trip_is_machine_readable_and_latest_is_deterministic() -> None:
    first = control_state_payload(task_id="150", state="queued", issue_number=218)
    second = control_state_payload(
        task_id="150", state="in_progress", issue_number=218, updated_at="2026-09-09T01:00:00Z"
    )
    comments = [
        {
            "id": 2,
            "created_at": "2026-09-09T01:00:00Z",
            "body": render_control_state_comment(second),
        },
        {
            "id": 1,
            "created_at": "2026-09-09T00:00:00Z",
            "body": render_control_state_comment(first),
        },
    ]

    assert parse_control_state_comment(render_control_state_comment(first)) == first
    assert latest_control_state(comments, task_id="150") == second
    assert CONTROL_STATE_MARKER in render_control_state_comment(second)


def test_control_state_rejects_unknown_or_malformed_payload() -> None:
    with pytest.raises(IssueWorkflowError, match="Unknown control state"):
        control_state_payload(task_id="150", state="magic")
    with pytest.raises(IssueWorkflowError, match="Malformed control-state JSON"):
        parse_control_state_comment(f"{CONTROL_STATE_MARKER}\n{{bad}}\n{CONTROL_STATE_MARKER}")
    with pytest.raises(IssueWorkflowError, match="Unsupported control state version"):
        parse_control_state_comment(
            f'{CONTROL_STATE_MARKER}\n{{"version": 2}}\n{CONTROL_STATE_MARKER}'
        )


def test_control_state_transition_rehearsal_covers_green_delivery_path() -> None:
    path = (
        "queued",
        "in_progress",
        "review_wait",
        "merge_ready",
        "merged",
        "deploy_wait",
        "production_verified",
    )
    previous = None
    for current in path:
        validate_control_transition(previous, current)
        previous = current

    with pytest.raises(IssueWorkflowError, match="Invalid control-state transition"):
        validate_control_transition("review_wait", "production_verified")


def test_queue_authorization_requires_explicit_activation_and_honors_owner_stop() -> None:
    issue = {"state": "open", "body": "The control contract supports CONTINUE_QUEUE."}
    comments = [{"id": 1, "user": {"login": "owner"}, "body": "CONTINUE_QUEUE"}]
    active = queue_authorization(
        issue, comments, command_activation=False, authorized_logins=("owner",)
    )
    assert active["active"] is True

    paused = queue_authorization(
        issue,
        [*comments, {"id": 2, "user": {"login": "owner"}, "body": "STOP_QUEUE"}],
        command_activation=True,
        authorized_logins=("owner",),
    )
    assert paused["active"] is False

    with pytest.raises(IssueWorkflowError, match="control Issue is not open"):
        queue_authorization({"state": "closed", "body": "CONTINUE_QUEUE"}, [])


def test_queue_budget_is_bounded_and_excess_becomes_human_required() -> None:
    DEFAULT_QUEUE_BUDGET.check_counters(tasks_started=4, review_fix_cycles=3, ci_fix_cycles=3)
    with pytest.raises(IssueWorkflowError, match="HUMAN_REQUIRED"):
        DEFAULT_QUEUE_BUDGET.check_counters(tasks_started=5)
    with pytest.raises(IssueWorkflowError, match="HUMAN_REQUIRED"):
        DEFAULT_QUEUE_BUDGET.check_counters(tasks_started=0, review_fix_cycles=4)
    with pytest.raises(IssueWorkflowError, match="cannot exceed 4"):
        QueueBudget(max_tasks_per_batch=5).validate()


def test_worker_budget_report_is_required_and_bounded() -> None:
    report = render_queue_budget_report(review_fix_cycles=2, ci_fix_cycles=1, scope_expansions=0)
    assert parse_queue_budget_report(report) == {
        "review_fix_cycles": 2,
        "ci_fix_cycles": 1,
        "scope_expansions": 0,
    }
    with pytest.raises(IssueWorkflowError, match="HUMAN_REQUIRED"):
        render_queue_budget_report(review_fix_cycles=4, ci_fix_cycles=0)
    with pytest.raises(IssueWorkflowError, match="Unsupported queue-budget version"):
        parse_queue_budget_report(report.replace('"version":1', '"version":2'))


def test_severity_and_risk_mapping_preserve_stricter_gates() -> None:
    assert task_risk_lane("none") == "GREEN"
    assert task_risk_lane("manual-visual-approval") == "RED"
    assert task_risk_lane("owner-checkpoint") == "YELLOW"


def test_task_issue_contract_round_trip_preserves_dependencies_and_acceptance() -> None:
    contract = task_contract_payload(
        task_id="91",
        scope="bounded report insight implementation",
        acceptance=("facts remain canonical", "no proactive generation"),
        dependencies=("90B", "67"),
        owner_gate="explicit-launch",
        risk_lane="GREEN",
        source_spec="codex-backlog/tasks/91-ai-coach-period-report-insights.md",
    )
    assert parse_task_contract(render_task_contract(contract)) == contract
    assert parse_task_contract("ordinary issue body") is None


def test_machine_contracts_reject_unsafe_shapes_and_weaker_gate_lane() -> None:
    with pytest.raises(IssueWorkflowError, match="array of strings"):
        task_contract_payload(
            task_id="91",
            scope="scope",
            acceptance="not-an-array",
            dependencies=(),
            owner_gate="none",
            risk_lane="GREEN",
            source_spec="spec.md",
        )
    with pytest.raises(IssueWorkflowError, match="weaker than owner gate"):
        task_contract_payload(
            task_id="91",
            scope="scope",
            acceptance=("criterion",),
            dependencies=(),
            owner_gate="manual-visual-approval",
            risk_lane="GREEN",
            source_spec="spec.md",
        )
    with pytest.raises(IssueWorkflowError, match="Unsupported task-contract version"):
        parse_task_contract(
            '<!-- yfc-task-contract:v1 -->\n{"version": 2}\n<!-- yfc-task-contract:v1 -->'
        )
