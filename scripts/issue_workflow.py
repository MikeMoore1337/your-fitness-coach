"""Shared contracts for the GitHub Issue-driven bounded delivery mode."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

CONTROL_STATE_VERSION = 1
CONTROL_STATE_MARKER = "<!-- yfc-control-state:v1 -->"
TASK_CONTRACT_VERSION = 1
TASK_CONTRACT_MARKER = "<!-- yfc-task-contract:v1 -->"
QUEUE_BUDGET_REPORT_VERSION = 1
QUEUE_BUDGET_REPORT_MARKER = "<!-- yfc-queue-budget:v1 -->"
CONTINUE_QUEUE_TOKEN = "CONTINUE_QUEUE"
STOP_QUEUE_TOKENS = frozenset({"PAUSE_QUEUE", "STOP_QUEUE"})
CONTROL_STATES = frozenset(
    {
        "queued",
        "in_progress",
        "review_wait",
        "fix_required",
        "ci_wait",
        "merge_ready",
        "merged",
        "deploy_wait",
        "production_verified",
        "human_required",
        "blocked",
        "cleanup_deferred",
    }
)
CONTROL_STATE_TRANSITIONS: dict[str | None, frozenset[str]] = {
    None: frozenset({"queued", "in_progress", "human_required", "blocked"}),
    "queued": frozenset({"in_progress", "human_required", "blocked"}),
    "in_progress": frozenset(
        {
            "review_wait",
            "fix_required",
            "ci_wait",
            "merge_ready",
            "merged",
            "deploy_wait",
            "production_verified",
            "human_required",
            "blocked",
            "cleanup_deferred",
        }
    ),
    "review_wait": frozenset({"fix_required", "merge_ready", "human_required", "blocked"}),
    "fix_required": frozenset({"in_progress", "review_wait", "human_required", "blocked"}),
    "ci_wait": frozenset({"fix_required", "merge_ready", "human_required", "blocked"}),
    "merge_ready": frozenset({"merged", "fix_required", "human_required", "blocked"}),
    "merged": frozenset({"deploy_wait", "production_verified", "human_required", "blocked"}),
    "deploy_wait": frozenset({"production_verified", "fix_required", "human_required", "blocked"}),
    "production_verified": frozenset({"cleanup_deferred", "production_verified", "human_required"}),
    "cleanup_deferred": frozenset({"production_verified", "human_required", "blocked"}),
    "human_required": frozenset({"in_progress", "queued", "human_required"}),
    "blocked": frozenset({"queued", "human_required", "blocked"}),
}
SEVERITY_MAP = {
    "P0": "BLOCKER",
    "P1": "HIGH",
    "P2": "MEDIUM",
    "P3": "LOW",
    "NIT": "LOW",
    "BLOCKER": "BLOCKER",
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
}


class IssueWorkflowError(RuntimeError):
    """A malformed or unsafe Issue/queue contract."""


@dataclass(frozen=True)
class QueueBudget:
    max_tasks_per_batch: int = 4
    max_review_fix_cycles_per_task: int = 3
    max_ci_fix_cycles_per_task: int = 3
    max_scope_expansion: int = 0

    def validate(self) -> None:
        fields = {
            "max_tasks_per_batch": self.max_tasks_per_batch,
            "max_review_fix_cycles_per_task": self.max_review_fix_cycles_per_task,
            "max_ci_fix_cycles_per_task": self.max_ci_fix_cycles_per_task,
            "max_scope_expansion": self.max_scope_expansion,
        }
        if any(isinstance(value, bool) or not isinstance(value, int) for value in fields.values()):
            raise IssueWorkflowError("queue budget values must be integers")
        if self.max_tasks_per_batch < 1:
            raise IssueWorkflowError("max_tasks_per_batch must be positive")
        if self.max_tasks_per_batch > 4:
            raise IssueWorkflowError("max_tasks_per_batch cannot exceed 4")
        if self.max_review_fix_cycles_per_task < 0:
            raise IssueWorkflowError("max_review_fix_cycles_per_task cannot be negative")
        if self.max_ci_fix_cycles_per_task < 0:
            raise IssueWorkflowError("max_ci_fix_cycles_per_task cannot be negative")
        if self.max_scope_expansion != 0:
            raise IssueWorkflowError("max_scope_expansion must remain zero")

    def check_counters(
        self,
        *,
        tasks_started: int,
        review_fix_cycles: int = 0,
        ci_fix_cycles: int = 0,
        scope_expansions: int = 0,
    ) -> None:
        self.validate()
        values = {
            "tasks_started": tasks_started,
            "review_fix_cycles": review_fix_cycles,
            "ci_fix_cycles": ci_fix_cycles,
            "scope_expansions": scope_expansions,
        }
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values.values()):
            raise IssueWorkflowError("queue counters must be integers")
        counters = {
            "tasks_started": (tasks_started, self.max_tasks_per_batch),
            "review_fix_cycles": (review_fix_cycles, self.max_review_fix_cycles_per_task),
            "ci_fix_cycles": (ci_fix_cycles, self.max_ci_fix_cycles_per_task),
            "scope_expansions": (scope_expansions, self.max_scope_expansion),
        }
        for name, (actual, maximum) in counters.items():
            if actual < 0:
                raise IssueWorkflowError(f"{name} cannot be negative")
            if actual > maximum:
                raise IssueWorkflowError(
                    f"HUMAN_REQUIRED: {name} budget exceeded ({actual}>{maximum})"
                )


DEFAULT_QUEUE_BUDGET = QueueBudget()


def _positive_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise IssueWorkflowError(f"{field} must be a positive integer or null")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IssueWorkflowError(f"{field} must be a non-negative integer")
    return value


def _optional_text(value: Any, field: str, *, max_length: int = 4096) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise IssueWorkflowError(f"{field} must be a string or null")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise IssueWorkflowError(f"{field} exceeds the bounded length")
    return normalized or None


def _string_sequence(value: Any, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise IssueWorkflowError(f"{field} must be an array of strings")
    if any(not isinstance(item, str) for item in value):
        raise IssueWorkflowError(f"{field} must be an array of strings")
    return tuple(value)


def render_queue_budget_report(
    *, review_fix_cycles: int, ci_fix_cycles: int, scope_expansions: int = 0
) -> str:
    DEFAULT_QUEUE_BUDGET.check_counters(
        tasks_started=1,
        review_fix_cycles=review_fix_cycles,
        ci_fix_cycles=ci_fix_cycles,
        scope_expansions=scope_expansions,
    )
    payload = {
        "version": QUEUE_BUDGET_REPORT_VERSION,
        "review_fix_cycles": review_fix_cycles,
        "ci_fix_cycles": ci_fix_cycles,
        "scope_expansions": scope_expansions,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{QUEUE_BUDGET_REPORT_MARKER}\n{serialized}\n{QUEUE_BUDGET_REPORT_MARKER}"


def parse_queue_budget_report(body: str) -> dict[str, int] | None:
    if QUEUE_BUDGET_REPORT_MARKER not in body:
        return None
    parts = body.split(QUEUE_BUDGET_REPORT_MARKER)
    if len(parts) != 3:
        raise IssueWorkflowError("Malformed queue-budget markers")
    try:
        payload = json.loads(parts[1].strip())
    except json.JSONDecodeError as error:
        raise IssueWorkflowError("Malformed queue-budget JSON") from error
    if not isinstance(payload, Mapping):
        raise IssueWorkflowError("Queue-budget payload must be an object")
    if payload.get("version") != QUEUE_BUDGET_REPORT_VERSION:
        raise IssueWorkflowError("Unsupported queue-budget version")
    values = {
        "review_fix_cycles": payload.get("review_fix_cycles"),
        "ci_fix_cycles": payload.get("ci_fix_cycles"),
        "scope_expansions": payload.get("scope_expansions"),
    }
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values.values()):
        raise IssueWorkflowError("Queue-budget counters must be integers")
    DEFAULT_QUEUE_BUDGET.check_counters(tasks_started=1, **values)
    return {key: int(value) for key, value in values.items()}


def validate_control_transition(previous: str | None, current: str) -> None:
    old_state = previous.strip().lower() if previous else None
    new_state = current.strip().lower()
    if old_state not in CONTROL_STATE_TRANSITIONS:
        raise IssueWorkflowError(f"Unknown previous control state: {previous!r}")
    if new_state not in CONTROL_STATES:
        raise IssueWorkflowError(f"Unknown control state: {current!r}")
    if new_state not in CONTROL_STATE_TRANSITIONS[old_state]:
        raise IssueWorkflowError(f"Invalid control-state transition: {old_state!r}->{new_state!r}")


def normalize_severity(value: str) -> str:
    normalized = value.strip().upper().replace(" ", "_")
    try:
        return SEVERITY_MAP[normalized]
    except KeyError as error:
        raise IssueWorkflowError(f"Unknown review severity: {value!r}") from error


def _task_id(value: str) -> str:
    if not isinstance(value, str):
        raise IssueWorkflowError(f"Invalid task ID in control state: {value!r}")
    normalized = value.strip().upper()
    if not re.fullmatch(r"[0-9]+[A-Z]?", normalized):
        raise IssueWorkflowError(f"Invalid task ID in control state: {value!r}")
    return normalized


def control_state_payload(
    *,
    task_id: str,
    state: str,
    issue_number: int | None = None,
    branch: str | None = None,
    pr_number: int | None = None,
    head_sha: str | None = None,
    terminal_verdict: str | None = None,
    blocker: str | None = None,
    review_fix_cycles: int = 0,
    ci_fix_cycles: int = 0,
    scope_expansions: int = 0,
    updated_at: str | None = None,
) -> dict[str, Any]:
    normalized_state = state.strip().lower()
    if normalized_state not in CONTROL_STATES:
        raise IssueWorkflowError(f"Unknown control state: {state!r}")
    checked_review_cycles = _nonnegative_int(review_fix_cycles, "review_fix_cycles")
    checked_ci_cycles = _nonnegative_int(ci_fix_cycles, "ci_fix_cycles")
    checked_scope_expansions = _nonnegative_int(scope_expansions, "scope_expansions")
    DEFAULT_QUEUE_BUDGET.check_counters(
        tasks_started=0,
        review_fix_cycles=checked_review_cycles,
        ci_fix_cycles=checked_ci_cycles,
        scope_expansions=checked_scope_expansions,
    )
    payload: dict[str, Any] = {
        "version": CONTROL_STATE_VERSION,
        "task_id": _task_id(task_id),
        "state": normalized_state,
        "issue_number": _positive_int(issue_number, "issue_number"),
        "branch": _optional_text(branch, "branch", max_length=256),
        "pr_number": _positive_int(pr_number, "pr_number"),
        "head_sha": _optional_text(head_sha, "head_sha", max_length=64),
        "terminal_verdict": _optional_text(terminal_verdict, "terminal_verdict"),
        "blocker": _optional_text(blocker, "blocker"),
        "review_fix_cycles": checked_review_cycles,
        "ci_fix_cycles": checked_ci_cycles,
        "scope_expansions": checked_scope_expansions,
    }
    if updated_at is not None:
        normalized_updated_at = _optional_text(updated_at, "updated_at", max_length=64)
        if normalized_updated_at is not None:
            payload["updated_at"] = normalized_updated_at
    return payload


def render_control_state_comment(payload: Mapping[str, Any]) -> str:
    if payload.get("version") != CONTROL_STATE_VERSION:
        raise IssueWorkflowError("Unsupported control state version")
    # Re-validate the public fields before writing a GitHub comment.  Comments are the durable
    # control-plane projection and must never contain an unbounded or ambiguous state payload.
    normalized = control_state_payload(
        task_id=str(payload.get("task_id", "")),
        state=str(payload.get("state", "")),
        issue_number=payload.get("issue_number"),
        branch=payload.get("branch"),
        pr_number=payload.get("pr_number"),
        head_sha=payload.get("head_sha"),
        terminal_verdict=payload.get("terminal_verdict"),
        blocker=payload.get("blocker"),
        review_fix_cycles=payload.get("review_fix_cycles", 0),
        ci_fix_cycles=payload.get("ci_fix_cycles", 0),
        scope_expansions=payload.get("scope_expansions", 0),
        updated_at=payload.get("updated_at"),
    )
    serialized = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{CONTROL_STATE_MARKER}\n{serialized}\n{CONTROL_STATE_MARKER}"


def parse_control_state_comment(body: str) -> dict[str, Any] | None:
    if CONTROL_STATE_MARKER not in body:
        return None
    parts = body.split(CONTROL_STATE_MARKER)
    if len(parts) != 3 or parts[0].strip() or parts[2].strip():
        raise IssueWorkflowError("Malformed control-state comment markers")
    try:
        payload = json.loads(parts[1].strip())
    except json.JSONDecodeError as error:
        raise IssueWorkflowError("Malformed control-state JSON") from error
    if not isinstance(payload, dict):
        raise IssueWorkflowError("Control-state payload must be an object")
    if payload.get("version") != CONTROL_STATE_VERSION:
        raise IssueWorkflowError("Unsupported control state version")
    return control_state_payload(
        task_id=str(payload.get("task_id", "")),
        state=str(payload.get("state", "")),
        issue_number=payload.get("issue_number"),
        branch=payload.get("branch"),
        pr_number=payload.get("pr_number"),
        head_sha=payload.get("head_sha"),
        terminal_verdict=payload.get("terminal_verdict"),
        blocker=payload.get("blocker"),
        review_fix_cycles=payload.get("review_fix_cycles", 0),
        ci_fix_cycles=payload.get("ci_fix_cycles", 0),
        scope_expansions=payload.get("scope_expansions", 0),
        updated_at=payload.get("updated_at"),
    )


def normalize_github_login(value: str) -> str:
    """Normalize GitHub user and connector bot logins for allowlist checks."""

    normalized = value.strip().casefold()
    if normalized.endswith("[bot]"):
        normalized = normalized[: -len("[bot]")].rstrip()
    return normalized


def _authorized_logins(logins: Sequence[str]) -> frozenset[str]:
    normalized = frozenset(
        normalized_login for login in logins if (normalized_login := normalize_github_login(login))
    )
    if not normalized:
        raise IssueWorkflowError(
            "control-state parsing requires an explicit authorized login allowlist"
        )
    return normalized


def _comment_login(comment: Mapping[str, Any]) -> str:
    author = comment.get("user") or comment.get("author") or {}
    if not isinstance(author, Mapping):
        return ""
    return normalize_github_login(str(author.get("login", "")))


def control_states(
    comments: Sequence[Mapping[str, Any]], *, authorized_logins: Sequence[str]
) -> list[dict[str, Any]]:
    allowed = _authorized_logins(authorized_logins)
    parsed: list[tuple[str, int, dict[str, Any]]] = []
    for comment in comments:
        if _comment_login(comment) not in allowed:
            continue
        payload = parse_control_state_comment(str(comment.get("body", "")))
        if payload is None:
            continue
        created_at = str(comment.get("created_at") or comment.get("createdAt") or "")
        raw_id = comment.get("id", 0)
        try:
            comment_id = int(raw_id)
        except TypeError:
            comment_id = 0
        except ValueError:
            comment_id = 0
        parsed.append((created_at, comment_id, payload))
    parsed.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in parsed]


def latest_control_state(
    comments: Sequence[Mapping[str, Any]],
    *,
    task_id: str | None = None,
    authorized_logins: Sequence[str],
) -> dict[str, Any] | None:
    expected = _task_id(task_id) if task_id is not None else None
    states = control_states(comments, authorized_logins=authorized_logins)
    matching = [item for item in states if expected is None or item["task_id"] == expected]
    return matching[-1] if matching else None


def _standalone_token(body: str, token: str) -> bool:
    return re.search(rf"(?im)^\s*{re.escape(token)}\s*$", body) is not None


def queue_authorization(
    issue: Mapping[str, Any],
    comments: Sequence[Mapping[str, Any]],
    *,
    command_activation: bool = False,
    authorized_logins: Sequence[str] = (),
) -> dict[str, Any]:
    if str(issue.get("state", "")).upper() != "OPEN":
        raise IssueWorkflowError("HUMAN_REQUIRED: control Issue is not open")
    body_contract = CONTINUE_QUEUE_TOKEN in str(issue.get("body", ""))
    allowed = _authorized_logins(authorized_logins)
    commands: list[tuple[str, int, str]] = []
    for comment in comments:
        author = comment.get("user") or comment.get("author") or {}
        login = (
            normalize_github_login(str(author.get("login", "")))
            if isinstance(author, Mapping)
            else ""
        )
        if login not in allowed:
            continue
        body = str(comment.get("body", ""))
        created_at = str(comment.get("created_at") or comment.get("createdAt") or "")
        try:
            comment_id = int(comment.get("id", 0))
        except TypeError:
            comment_id = 0
        except ValueError:
            comment_id = 0
        for token in (CONTINUE_QUEUE_TOKEN, *sorted(STOP_QUEUE_TOKENS)):
            if _standalone_token(body, token):
                commands.append((created_at, comment_id, token))
    commands.sort()
    latest_command = commands[-1][2] if commands else None
    active = command_activation and body_contract
    if latest_command == CONTINUE_QUEUE_TOKEN:
        active = True
    if latest_command in STOP_QUEUE_TOKENS:
        active = False
    return {
        "active": active,
        "body_contract": body_contract,
        "command_activation": command_activation,
        "latest_command": latest_command,
        "authorized_comment_count": len(commands),
        "reason": (
            "explicit command and Issue contract"
            if command_activation and body_contract
            else "authorized Issue command"
            if latest_command == CONTINUE_QUEUE_TOKEN
            else "queue is paused by the latest authorized stop command"
            if latest_command in STOP_QUEUE_TOKENS
            else "CONTINUE_QUEUE activation is missing"
        ),
    }


def task_risk_lane(owner_gate: str, *, forbidden: bool = False) -> str:
    gate = owner_gate.strip().lower().replace("-", "_")
    if forbidden or gate in {
        "human_evidence",
        "manual_visual_approval",
        "legal_counsel_required",
        "external_authorization",
        "destructive_action",
        "billing",
        "paid_service",
        "credentials",
    }:
        return "RED"
    if gate not in {"", "none", "explicit_launch", "owner_launch"}:
        return "YELLOW"
    return "GREEN"


def task_contract_payload(
    *,
    task_id: str,
    scope: str,
    acceptance: Sequence[str],
    dependencies: Sequence[str],
    owner_gate: str,
    risk_lane: str,
    source_spec: str,
    issue_state: str = "queued",
) -> dict[str, Any]:
    if not isinstance(scope, str) or not isinstance(source_spec, str):
        raise IssueWorkflowError("Task contract scope and source_spec must be strings")
    if not isinstance(owner_gate, str):
        raise IssueWorkflowError("Task contract owner_gate must be a string")
    if not isinstance(risk_lane, str):
        raise IssueWorkflowError("Task contract risk_lane must be a string")
    if not isinstance(issue_state, str):
        raise IssueWorkflowError("Task contract issue_state must be a string")
    normalized_risk = risk_lane.strip().upper()
    if normalized_risk not in {"GREEN", "YELLOW", "RED"}:
        raise IssueWorkflowError(f"Unknown task risk lane: {risk_lane!r}")
    normalized_issue_state = issue_state.strip().lower()
    if normalized_issue_state not in CONTROL_STATES:
        raise IssueWorkflowError(f"Unknown task issue state: {issue_state!r}")
    normalized_acceptance = _string_sequence(acceptance, "acceptance")
    if len(normalized_acceptance) > 32:
        raise IssueWorkflowError("Task contract acceptance criteria are too numerous")
    normalized_dependencies = tuple(
        _task_id(item) for item in _string_sequence(dependencies, "dependencies")
    )
    if len(normalized_dependencies) > 64:
        raise IssueWorkflowError("Task contract dependencies are too numerous")
    if (
        not scope.strip()
        or len(scope.strip()) > 8192
        or not source_spec.strip()
        or len(source_spec.strip()) > 1024
    ):
        raise IssueWorkflowError("Task contract requires scope and source_spec")
    if not normalized_acceptance or any(
        not item.strip() or len(item.strip()) > 2000 for item in normalized_acceptance
    ):
        raise IssueWorkflowError("Task contract requires non-empty acceptance criteria")
    if not isinstance(owner_gate, str) or not owner_gate.strip():
        raise IssueWorkflowError("Task contract requires owner_gate")
    required_risk = task_risk_lane(owner_gate)
    risk_rank = {"GREEN": 0, "YELLOW": 1, "RED": 2}
    if risk_rank[normalized_risk] < risk_rank[required_risk]:
        raise IssueWorkflowError(
            f"Task risk lane {normalized_risk} is weaker than owner gate {required_risk}"
        )
    return {
        "version": TASK_CONTRACT_VERSION,
        "task_id": _task_id(task_id),
        "scope": scope.strip(),
        "acceptance": [item.strip() for item in normalized_acceptance],
        "dependencies": list(dict.fromkeys(normalized_dependencies)),
        "owner_gate": owner_gate.strip(),
        "risk_lane": normalized_risk,
        "source_spec": source_spec.strip(),
        "issue_state": normalized_issue_state,
    }


def render_task_contract(contract: Mapping[str, Any]) -> str:
    normalized = task_contract_payload(
        task_id=contract.get("task_id", ""),
        scope=contract.get("scope", ""),
        acceptance=contract.get("acceptance", []),
        dependencies=contract.get("dependencies", []),
        owner_gate=contract.get("owner_gate", ""),
        risk_lane=contract.get("risk_lane", ""),
        source_spec=contract.get("source_spec", ""),
        issue_state=contract.get("issue_state", "queued"),
    )
    serialized = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{TASK_CONTRACT_MARKER}\n{serialized}\n{TASK_CONTRACT_MARKER}"


def parse_task_contract(body: str) -> dict[str, Any] | None:
    if TASK_CONTRACT_MARKER not in body:
        return None
    parts = body.split(TASK_CONTRACT_MARKER)
    if len(parts) != 3:
        raise IssueWorkflowError("Malformed task-contract markers")
    try:
        payload = json.loads(parts[1].strip())
    except json.JSONDecodeError as error:
        raise IssueWorkflowError("Malformed task-contract JSON") from error
    if not isinstance(payload, Mapping):
        raise IssueWorkflowError("Task-contract payload must be an object")
    if payload.get("version") != TASK_CONTRACT_VERSION:
        raise IssueWorkflowError("Unsupported task-contract version")
    return task_contract_payload(
        task_id=payload.get("task_id", ""),
        scope=payload.get("scope", ""),
        acceptance=payload.get("acceptance", []),
        dependencies=payload.get("dependencies", []),
        owner_gate=payload.get("owner_gate", ""),
        risk_lane=payload.get("risk_lane", ""),
        source_spec=payload.get("source_spec", ""),
        issue_state=payload.get("issue_state", "queued"),
    )
