"""Privacy-safe deterministic guard for Codex worker JSONL activity."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1
TOOL_ITEM_TYPES = frozenset(
    {"command_execution", "mcp_tool_call", "web_search", "collab_tool_call"}
)
PROGRESS_ITEM_TYPE = "file_change"
RUNNING_AGENT_STATES = frozenset({"pending_init", "running"})


class WorkerGuardConfigError(ValueError):
    """Worker guard limits are absent or malformed."""


@dataclass(frozen=True)
class GuardLimits:
    max_completed_tool_actions: int
    max_collab_tool_calls: int
    max_spawned_subagents: int
    max_concurrent_subagents: int
    max_identical_failed_actions: int
    max_identical_actions_without_progress: int
    short_cycle_period_max: int
    short_cycle_repetitions: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GuardLimits":
        names = (
            "max_completed_tool_actions",
            "max_collab_tool_calls",
            "max_spawned_subagents",
            "max_concurrent_subagents",
            "max_identical_failed_actions",
            "max_identical_actions_without_progress",
            "short_cycle_period_max",
            "short_cycle_repetitions",
        )
        parsed: dict[str, int] = {}
        for name in names:
            raw = value.get(name)
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                raise WorkerGuardConfigError(f"Invalid worker guard limit {name}: {raw!r}")
            parsed[name] = raw
        if parsed["max_identical_failed_actions"] < 2:
            raise WorkerGuardConfigError("max_identical_failed_actions must be at least 2")
        if parsed["max_identical_actions_without_progress"] < 3:
            raise WorkerGuardConfigError(
                "max_identical_actions_without_progress must be at least 3"
            )
        if parsed["short_cycle_period_max"] < 2:
            raise WorkerGuardConfigError("short_cycle_period_max must be at least 2")
        if parsed["short_cycle_repetitions"] < 3:
            raise WorkerGuardConfigError("short_cycle_repetitions must be at least 3")
        return cls(**parsed)

    def as_dict(self) -> dict[str, int]:
        return {
            "max_completed_tool_actions": self.max_completed_tool_actions,
            "max_collab_tool_calls": self.max_collab_tool_calls,
            "max_spawned_subagents": self.max_spawned_subagents,
            "max_concurrent_subagents": self.max_concurrent_subagents,
            "max_identical_failed_actions": self.max_identical_failed_actions,
            "max_identical_actions_without_progress": self.max_identical_actions_without_progress,
            "short_cycle_period_max": self.short_cycle_period_max,
            "short_cycle_repetitions": self.short_cycle_repetitions,
        }


@dataclass(frozen=True)
class GuardDecision:
    blocked: bool = False
    reason_code: str | None = None
    signature_hash: str | None = None


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _item(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
    raw = event.get("item")
    return raw if isinstance(raw, Mapping) else None


def _action_payload(item: Mapping[str, Any]) -> dict[str, Any] | None:
    item_type = item.get("type")
    if item_type == "command_execution":
        return {"type": item_type, "command": item.get("command")}
    if item_type == "mcp_tool_call":
        return {
            "type": item_type,
            "server": item.get("server"),
            "tool": item.get("tool"),
            "arguments": item.get("arguments"),
        }
    if item_type == "web_search":
        return {
            "type": item_type,
            "query": item.get("query"),
            "action": item.get("action"),
        }
    if item_type == "collab_tool_call":
        return {
            "type": item_type,
            "tool": item.get("tool"),
            "receiver_thread_ids": item.get("receiver_thread_ids"),
            "prompt_hash": _digest(item.get("prompt")) if item.get("prompt") is not None else None,
        }
    return None


def _result_payload(item: Mapping[str, Any]) -> dict[str, Any]:
    item_type = item.get("type")
    if item_type == "command_execution":
        return {
            "status": item.get("status"),
            "exit_code": item.get("exit_code"),
            "output_hash": _digest(item.get("aggregated_output", "")),
        }
    if item_type == "mcp_tool_call":
        return {
            "status": item.get("status"),
            "error_hash": _digest(item.get("error")) if item.get("error") is not None else None,
            "result_hash": _digest(item.get("result")) if item.get("result") is not None else None,
        }
    if item_type == "collab_tool_call":
        states = item.get("agents_states")
        normalized_states = {}
        if isinstance(states, Mapping):
            normalized_states = {
                str(key): (
                    raw.get("status") if isinstance(raw, Mapping) else None
                )
                for key, raw in states.items()
            }
        return {
            "status": item.get("status"),
            "agents_states": normalized_states,
        }
    return {"status": item.get("status")}


def _is_failed(item: Mapping[str, Any]) -> bool:
    status = str(item.get("status", "")).lower()
    if status in {"failed", "declined", "errored"}:
        return True
    if item.get("type") == "command_execution":
        exit_code = item.get("exit_code")
        return isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0
    return False


def _running_agents(item: Mapping[str, Any]) -> int:
    states = item.get("agents_states")
    if not isinstance(states, Mapping):
        return 0
    count = 0
    for raw in states.values():
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("status", "")).lower() in RUNNING_AGENT_STATES:
            count += 1
    return count


class WorkerEventGuard:
    """Observe Codex JSONL without retaining raw task/tool content."""

    def __init__(self, limits: GuardLimits) -> None:
        self.limits = limits
        window = max(
            limits.max_identical_actions_without_progress,
            limits.short_cycle_period_max * limits.short_cycle_repetitions,
            16,
        )
        self._recent_actions: deque[str] = deque(maxlen=window)
        self._failed_counts: Counter[str] = Counter()
        self._seen_collab_ids: set[str] = set()
        self._warning_codes: set[str] = set()
        self.completed_tool_actions = 0
        self.collab_tool_calls = 0
        self.spawned_subagents = 0
        self.max_observed_concurrent_subagents = 0
        self.progress_events = 0
        self.malformed_lines = 0
        self.block_reason_code: str | None = None
        self.block_signature_hash: str | None = None

    def _block(self, reason: str, signature: str | None = None) -> GuardDecision:
        if self.block_reason_code is None:
            self.block_reason_code = reason
            self.block_signature_hash = signature
        return GuardDecision(True, self.block_reason_code, self.block_signature_hash)

    def _reset_after_progress(self) -> None:
        self._recent_actions.clear()
        self._failed_counts.clear()

    def _check_short_cycle(self) -> GuardDecision:
        values = list(self._recent_actions)
        for period in range(2, self.limits.short_cycle_period_max + 1):
            required = period * self.limits.short_cycle_repetitions
            if len(values) < required:
                continue
            tail = values[-required:]
            pattern = tail[:period]
            if all(tail[index : index + period] == pattern for index in range(0, required, period)):
                return self._block("SHORT_TOOL_CYCLE_WITHOUT_PROGRESS", _digest(pattern))
        return GuardDecision()

    def _observe_collab(self, item: Mapping[str, Any]) -> GuardDecision:
        raw_id = item.get("id")
        item_id = str(raw_id) if raw_id is not None else _digest(_action_payload(item))
        if item_id not in self._seen_collab_ids:
            self._seen_collab_ids.add(item_id)
            self.collab_tool_calls += 1
            if self.collab_tool_calls > self.limits.max_collab_tool_calls:
                return self._block("COLLAB_TOOL_BUDGET_EXCEEDED")

            if str(item.get("tool", "")).lower() == "spawn_agent":
                receivers = item.get("receiver_thread_ids")
                spawned = len(receivers) if isinstance(receivers, list) and receivers else 1
                self.spawned_subagents += spawned
                if self.spawned_subagents > self.limits.max_spawned_subagents:
                    return self._block("SUBAGENT_BUDGET_EXCEEDED")

        running = _running_agents(item)
        self.max_observed_concurrent_subagents = max(
            self.max_observed_concurrent_subagents, running
        )
        if running > self.limits.max_concurrent_subagents:
            return self._block("SUBAGENT_CONCURRENCY_EXCEEDED")
        return GuardDecision()

    def observe_event(self, event: Mapping[str, Any]) -> GuardDecision:
        if self.block_reason_code is not None:
            return GuardDecision(True, self.block_reason_code, self.block_signature_hash)

        event_type = event.get("type")
        item = _item(event)
        if item is None:
            return GuardDecision()

        item_type = item.get("type")
        if item_type == "collab_tool_call" and event_type in {"item.started", "item.updated", "item.completed"}:
            decision = self._observe_collab(item)
            if decision.blocked:
                return decision

        if event_type != "item.completed":
            return GuardDecision()

        if item_type == PROGRESS_ITEM_TYPE:
            if str(item.get("status", "completed")).lower() != "failed":
                changes = item.get("changes")
                if changes is None or (isinstance(changes, list) and changes):
                    self.progress_events += 1
                    self._reset_after_progress()
            return GuardDecision()

        if item_type not in TOOL_ITEM_TYPES:
            return GuardDecision()

        action_payload = _action_payload(item)
        if action_payload is None:
            return GuardDecision()
        action_signature = _digest(action_payload)
        self.completed_tool_actions += 1

        if self.completed_tool_actions > self.limits.max_completed_tool_actions:
            return self._block("TOOL_ACTION_BUDGET_EXCEEDED", action_signature)
        if self.completed_tool_actions * 4 >= self.limits.max_completed_tool_actions * 3:
            self._warning_codes.add("TOOL_ACTION_BUDGET_75_PERCENT")

        self._recent_actions.append(action_signature)

        if _is_failed(item):
            failure_signature = _digest(
                {"action": action_payload, "result": _result_payload(item)}
            )
            self._failed_counts[failure_signature] += 1
            if (
                self._failed_counts[failure_signature]
                >= self.limits.max_identical_failed_actions
            ):
                return self._block("IDENTICAL_FAILED_ACTION_LOOP", failure_signature)

        identical_count = sum(
            1 for signature in self._recent_actions if signature == action_signature
        )
        if identical_count >= self.limits.max_identical_actions_without_progress:
            return self._block("IDENTICAL_ACTION_LOOP_WITHOUT_PROGRESS", action_signature)
        if identical_count >= max(3, self.limits.max_identical_actions_without_progress // 2):
            self._warning_codes.add("REPEATED_ACTION_WITHOUT_PROGRESS")

        return self._check_short_cycle()

    def observe_line(self, line: bytes | str) -> GuardDecision:
        if isinstance(line, bytes):
            text = line.decode("utf-8", errors="replace")
        else:
            text = line
        try:
            raw = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            self.malformed_lines += 1
            return GuardDecision()
        if not isinstance(raw, Mapping):
            return GuardDecision()
        return self.observe_event(raw)

    def report(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "classification": "yfc-worker-guard-report",
            "limits": self.limits.as_dict(),
            "counters": {
                "completed_tool_actions": self.completed_tool_actions,
                "collab_tool_calls": self.collab_tool_calls,
                "spawned_subagents": self.spawned_subagents,
                "max_observed_concurrent_subagents": self.max_observed_concurrent_subagents,
                "progress_events": self.progress_events,
                "malformed_lines": self.malformed_lines,
            },
            "warning_codes": sorted(self._warning_codes),
            "blocked": self.block_reason_code is not None,
            "block_reason_code": self.block_reason_code,
            "block_signature_hash": self.block_signature_hash,
            "recent_signature_hashes": list(self._recent_actions)[-8:],
            "privacy": {
                "raw_prompts_stored": False,
                "raw_commands_stored": False,
                "raw_tool_arguments_stored": False,
                "raw_tool_results_stored": False,
            },
        }
