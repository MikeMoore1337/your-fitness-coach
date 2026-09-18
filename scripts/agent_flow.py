"""Deterministic role routing for the YFC task delivery lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

AGENT_FLOW_SCHEMA_VERSION = 1
PONYTAIL_TESTED_VERSION = "4.10.0"
PONYTAIL_MODES = frozenset({"off", "lite", "full", "ultra"})

ORDINARY_TOOL_ACTION_BUDGET = 160
EXPANDED_TOOL_ACTION_BUDGET = 240
READ_ONLY_SUBAGENT_BUDGET = 2
READ_ONLY_COLLAB_TOOL_BUDGET = 10
LOOP_IDENTICAL_FAILURE_LIMIT = 4
LOOP_IDENTICAL_ACTION_LIMIT = 8
LOOP_SHORT_CYCLE_PERIOD_MAX = 3
LOOP_SHORT_CYCLE_REPETITIONS = 4

WORKER_ROLES = (
    "orchestrator",
    "researcher",
    "product-lawyer",
    "implementer",
    "qa-verifier",
)
CONTROLLER_ROLE = "integration-release"
ROLE_ORDER = {role: index for index, role in enumerate(WORKER_ROLES)}

ROLE_PATTERNS: dict[str, tuple[str, ...]] = {
    "orchestrator": (r"\borchestrator\b",),
    "researcher": (r"\bresearcher\b",),
    "product-lawyer": (r"\bproduct[- ]lawyer\b",),
    "implementer": (r"\bimplementer\b",),
    "qa-verifier": (r"\bqa[- ]verifier\b", r"\bqa verifier\b"),
    "integration-release": (r"\bintegration[- ]release\b",),
}

SURFACE_PATTERNS: dict[str, re.Pattern[str]] = {
    "backend": re.compile(r"\bbackend\b|fastapi|sqlalchemy|pydantic", re.IGNORECASE),
    "frontend": re.compile(
        r"\bfrontend\b|react|typescript|\bui\b|\bux\b|лендинг|веб-прилож",
        re.IGNORECASE,
    ),
    "tma": re.compile(r"telegram mini app|\btma\b", re.IGNORECASE),
    "bot": re.compile(r"aiogram|telegram bot|телеграм[- ]бот|\bбот\b", re.IGNORECASE),
    "database": re.compile(
        r"postgres|alembic|миграц|\bdatabase\b|\bdb\b|баз[аеы] данных",
        re.IGNORECASE,
    ),
    "deployment": re.compile(
        r"\bdeploy\b|deployment|production|docker|caddy|ci/cd|github actions",
        re.IGNORECASE,
    ),
    "security": re.compile(
        r"auth|oauth|security|authorization|authentication|секрет|безопасност",
        re.IGNORECASE,
    ),
    "ai": re.compile(r"ai coach|\bllm\b|provider|модел[ьи]|inference", re.IGNORECASE),
}
CORE_CROSS_CUTTING_SURFACES = frozenset({"backend", "frontend", "tma", "bot", "database"})

ARCHITECTURE_PATTERN = re.compile(
    r"architecture|архитектур|impact analysis|dependency|cross[- ]cutting|"
    r"multi[- ]stream|сквозн",
    re.IGNORECASE,
)
MULTI_STREAM_PATTERN = re.compile(
    r"multi[- ]stream|несколько поток|independent streams", re.IGNORECASE
)
USER_FACING_PATTERN = re.compile(
    r"user[- ]facing|пользователь|\bui\b|\bux\b|visual|responsive|mobile|"
    r"лендинг|интерфейс",
    re.IGNORECASE,
)
RESEARCH_PATTERN = re.compile(
    r"research|discovery|feasibility|spike|исслед|research[_ -]first",
    re.IGNORECASE,
)
LEGAL_PATTERN = re.compile(r"legal|правов|юрид|compliance", re.IGNORECASE)


class AgentFlowError(RuntimeError):
    """The deterministic task routing contract cannot be built safely."""


def _extract_bold_field(text: str, name: str) -> str:
    pattern = re.compile(rf"^- \*\*{re.escape(name)}:\*\*\s*(.+)$", re.MULTILINE)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _roles_from_value(value: str) -> tuple[str, ...]:
    normalized = value.strip().lower()
    if not normalized:
        return ()
    roles: list[str] = []
    for role, patterns in ROLE_PATTERNS.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            roles.append(role)
    return tuple(roles)


def _task_type(text: str) -> str:
    return _extract_bold_field(text, "Тип") or _extract_bold_field(text, "Type")


def _explicit_ponytail_mode(text: str) -> str | None:
    raw = _extract_bold_field(text, "Ponytail") or _extract_bold_field(text, "Ponytail mode")
    if not raw:
        return None
    mode = raw.strip().lower()
    if mode not in PONYTAIL_MODES:
        raise AgentFlowError(
            f"Unsupported Ponytail mode {raw!r}; expected one of {sorted(PONYTAIL_MODES)}"
        )
    return mode


def _explicit_role_contract(text: str) -> tuple[str, tuple[str, ...], bool, bool]:
    primary_raw = _extract_bold_field(text, "Основная роль") or _extract_bold_field(
        text, "Primary role"
    )
    additional_raw = _extract_bold_field(
        text, "Дополнительные роли lifecycle"
    ) or _extract_bold_field(text, "Lifecycle roles")
    primary_roles = _roles_from_value(primary_raw)
    additional_roles = _roles_from_value(additional_raw)
    primary = primary_roles[0] if primary_roles else ""
    contract_present = bool(primary_raw or additional_raw)
    has_unrecognized = bool(primary_raw and not primary_roles)
    return primary, additional_roles, contract_present, has_unrecognized


def _detected_surfaces(text: str) -> tuple[str, ...]:
    return tuple(name for name, pattern in SURFACE_PATTERNS.items() if pattern.search(text))


def _ordered_roles(roles: Sequence[str]) -> tuple[str, ...]:
    unique = {role for role in roles if role in ROLE_ORDER}
    return tuple(sorted(unique, key=ROLE_ORDER.__getitem__))


def _role_reason(
    role: str,
    *,
    explicit: bool,
    research: bool,
    inferred_orchestrator: bool,
    inferred_qa: bool,
) -> str:
    if explicit:
        return "declared by the task role contract"
    if role == "researcher" and research:
        return "inferred from research/discovery task type"
    if role == "orchestrator" and inferred_orchestrator:
        return "inferred from genuine multi-surface/multi-stream scope"
    if role == "qa-verifier" and inferred_qa:
        return "inferred for user-facing behavior without an explicit role contract"
    if role == "implementer":
        return "default production writer for an ordinary executable task"
    if role == "product-lawyer":
        return "inferred only for a dedicated legal/compliance task"
    return "selected by deterministic routing"


def build_agent_flow(
    task_id: str,
    task_text: str,
    *,
    issue_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a bounded machine-readable role plan without copying private task prose."""

    normalized_id = str(task_id).strip().upper()
    if not re.fullmatch(r"[0-9]+[A-Z]?", normalized_id):
        raise AgentFlowError(f"Invalid task id: {task_id!r}")
    if not task_text.strip():
        raise AgentFlowError("Task document is empty")

    primary, additional, explicit_contract, unrecognized_primary = _explicit_role_contract(
        task_text
    )
    surfaces = _detected_surfaces(task_text)
    core_surfaces = tuple(surface for surface in surfaces if surface in CORE_CROSS_CUTTING_SURFACES)
    architecture_signal = bool(ARCHITECTURE_PATTERN.search(task_text))
    cross_cutting = len(core_surfaces) >= 2
    research = bool(RESEARCH_PATTERN.search(_task_type(task_text) or task_text[:2000]))
    legal = bool(LEGAL_PATTERN.search(_task_type(task_text) or task_text[:2000]))
    user_facing = bool(USER_FACING_PATTERN.search(task_text))

    inferred_orchestrator = False
    inferred_qa = False
    inferred_roles: list[str] = []
    declared_roles = [role for role in (primary, *additional) if role]
    declared_controller_role = CONTROLLER_ROLE in declared_roles
    declared_worker_roles = [role for role in declared_roles if role in WORKER_ROLES]

    if explicit_contract:
        selected_roles = declared_worker_roles or ["implementer"]
    elif research:
        selected_roles = ["researcher"]
    elif legal:
        selected_roles = ["product-lawyer"]
    else:
        selected_roles = ["implementer"]
        if len(core_surfaces) >= 3 or (
            cross_cutting and bool(MULTI_STREAM_PATTERN.search(task_text))
        ):
            selected_roles.insert(0, "orchestrator")
            inferred_orchestrator = True
            inferred_roles.append("orchestrator")
        if user_facing and any(surface in {"frontend", "tma"} for surface in surfaces):
            selected_roles.append("qa-verifier")
            inferred_qa = True
            inferred_roles.append("qa-verifier")

    selected = _ordered_roles(selected_roles)
    graphify_required = bool(cross_cutting or architecture_signal or "orchestrator" in selected)

    explicit_ponytail_mode = _explicit_ponytail_mode(task_text)
    if explicit_ponytail_mode is not None:
        ponytail_mode = explicit_ponytail_mode
        ponytail_source = "explicit-task-field"
        ponytail_reason = "explicit Ponytail task override"
    elif "implementer" not in selected:
        ponytail_mode = "off"
        ponytail_source = "deterministic-inference"
        ponytail_reason = "no production implementation pass"
    elif (
        cross_cutting
        or architecture_signal
        or any(surface in {"security", "deployment"} for surface in surfaces)
    ):
        ponytail_mode = "lite"
        ponytail_source = "deterministic-inference"
        ponytail_reason = "complex or sensitive implementation keeps minimalism advisory"
    else:
        ponytail_mode = "full"
        ponytail_source = "deterministic-inference"
        ponytail_reason = "ordinary implementation uses the full minimalism ladder"

    read_only_parallelism = bool(
        "implementer" in selected
        and any(role in selected for role in {"researcher", "orchestrator"})
    )
    expanded_tool_budget = bool(
        research
        or cross_cutting
        or architecture_signal
        or graphify_required
        or any(surface in {"security", "deployment"} for surface in surfaces)
    )
    subagent_budget = READ_ONLY_SUBAGENT_BUDGET if read_only_parallelism else 0
    collab_budget = READ_ONLY_COLLAB_TOOL_BUDGET if read_only_parallelism else 0
    agent_budget = {
        "max_completed_tool_actions": (
            EXPANDED_TOOL_ACTION_BUDGET
            if expanded_tool_budget
            else ORDINARY_TOOL_ACTION_BUDGET
        ),
        "max_collab_tool_calls": collab_budget,
        "max_spawned_subagents": subagent_budget,
        "max_concurrent_subagents": subagent_budget,
        "max_identical_failed_actions": LOOP_IDENTICAL_FAILURE_LIMIT,
        "max_identical_actions_without_progress": LOOP_IDENTICAL_ACTION_LIMIT,
        "short_cycle_period_max": LOOP_SHORT_CYCLE_PERIOD_MAX,
        "short_cycle_repetitions": LOOP_SHORT_CYCLE_REPETITIONS,
        "subagent_mode": (
            "read-only-only-when-host-collab-is-already-available"
            if read_only_parallelism
            else "disabled"
        ),
        "parallel_production_writers": False,
        "enforcement": "live-codex-jsonl-worker-guard",
    }

    roles = [
        {
            "name": role,
            "mode": (
                "production-writer"
                if role == "implementer"
                else "read-only-verification"
                if role == "qa-verifier"
                else "read-only-planning"
            ),
            "reason": _role_reason(
                role,
                explicit=role in declared_worker_roles,
                research=research,
                inferred_orchestrator=inferred_orchestrator,
                inferred_qa=inferred_qa,
            ),
        }
        for role in selected
    ]
    skipped = tuple(role for role in WORKER_ROLES if role not in selected)

    return {
        "schema_version": AGENT_FLOW_SCHEMA_VERSION,
        "classification": "yfc-agent-flow-plan",
        "task_id": normalized_id,
        "task_fingerprint_sha256": hashlib.sha256(task_text.encode("utf-8")).hexdigest(),
        "routing": {
            "source": "explicit-task-contract" if explicit_contract else "deterministic-inference",
            "task_type_present": bool(_task_type(task_text)),
            "explicit_role_contract": explicit_contract,
            "unrecognized_primary_role": unrecognized_primary,
            "inferred_roles": sorted(inferred_roles),
            "detected_surfaces": list(surfaces),
            "cross_cutting": cross_cutting,
            "architecture_signal": architecture_signal,
            "issue_contract_present": issue_contract is not None,
        },
        "graphify": {
            "bootstrap_required": graphify_required,
            "command": ("python scripts/graphify_yfc.py bootstrap" if graphify_required else None),
            "failure_policy": "fallback-to-direct-source-inspection",
        },
        "ponytail": {
            "mode": ponytail_mode,
            "source": ponytail_source,
            "reason": ponytail_reason,
            "tested_version": PONYTAIL_TESTED_VERSION,
            "environment_variable": "PONYTAIL_DEFAULT_MODE",
            "install_policy": "never-auto-install",
            "review_policy": "never-auto-run-review-or-audit",
            "fallback_policy": "use-yfc-minimalism-ladder",
            "required": False,
        },
        "agent_budget": agent_budget,
        "worker_role_passes": roles,
        "skipped_worker_roles": list(skipped),
        "controller_managed_roles": [
            {
                "name": CONTROLLER_ROLE,
                "reason": (
                    "explicit task declaration; execution remains controller-managed"
                    if declared_controller_role
                    else "normal YFC delivery convergence is controller-managed"
                ),
            }
        ],
        "execution": {
            "mode": "single-worker-role-passes",
            "single_production_writer": True,
            "production_writer": "implementer" if "implementer" in selected else None,
            "parallel_writers_within_task": False,
            "read_only_parallelism_allowed": read_only_parallelism,
            "spawn_extra_codex_processes": False,
            "new_agent_framework": False,
        },
        "prohibited_automatic_roles": ["reviewer", "security-reviewer", "adversarial-auditor"],
        "source_of_truth": [
            "current source",
            "tests",
            "migrations",
            "git history",
            "active documentation",
        ],
    }


def build_agent_flow_from_path(
    task_id: str,
    task_path: Path,
    *,
    issue_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        text = task_path.read_text(encoding="utf-8")
    except OSError as error:
        raise AgentFlowError(f"Cannot read task document {task_path}") from error
    return build_agent_flow(task_id, text, issue_contract=issue_contract)


def render_agent_flow_prompt(plan: Mapping[str, Any]) -> str:
    """Render the bounded routing plan for the single delivery worker."""

    return (
        "Agent Flow v1 routing contract (deterministic, bounded):\n"
        + json.dumps(dict(plan), ensure_ascii=False, sort_keys=True)
        + "\n"
        "Execute only the listed worker role passes, in their listed order, inside the current "
        "worker. If the environment already provides a safe collab/subagent mechanism, use it only "
        "within agent_budget and only for read-only planning/research work; never create another "
        "production writer. Do not install or invent an agent framework. Only implementer may write "
        "production code. "
        "qa-verifier stays read-only and returns blocking defects to implementer. "
        "Do not synthesize reviewer/security-review agents. "
        "If graphify.bootstrap_required is true, run its command once before broad architecture "
        "inspection; a tooling-only bootstrap failure falls back to direct source inspection when "
        "safe. Ponytail is optional host tooling: use the planned mode if the plugin is already "
        "available, never install it automatically, and never start ponytail-review/audit loops. "
        "If it is unavailable, apply the YFC minimalism ladder from AGENTS.md directly. "
        "Always verify source/tests/migrations/docs before writes.\n"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id")
    parser.add_argument("task_path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        plan = build_agent_flow_from_path(args.task_id, args.task_path)
    except AgentFlowError as error:
        print(str(error))
        return 1
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
