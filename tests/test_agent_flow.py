from __future__ import annotations

import json

from scripts.agent_flow import build_agent_flow, render_agent_flow_prompt


def test_ordinary_explicit_task_uses_only_declared_implementer() -> None:
    plan = build_agent_flow(
        "355",
        """
# Task

- **Тип:** Feature
- **Основная роль:** implementer
- **Дополнительные роли lifecycle:** integration-release

Change a small Python helper with targeted tests.
""",
    )

    assert [item["name"] for item in plan["worker_role_passes"]] == ["implementer"]
    assert plan["routing"]["source"] == "explicit-task-contract"
    assert plan["graphify"]["bootstrap_required"] is False
    assert plan["ponytail"]["mode"] == "full"
    assert plan["ponytail"]["source"] == "deterministic-inference"
    assert plan["execution"]["single_production_writer"] is True
    assert plan["agent_budget"]["max_spawned_subagents"] == 0
    assert plan["agent_budget"]["max_collab_tool_calls"] == 0
    assert plan["agent_budget"]["max_completed_tool_actions"] == 160
    assert plan["controller_managed_roles"][0]["name"] == "integration-release"


def test_research_discovery_without_role_contract_routes_to_researcher() -> None:
    plan = build_agent_flow(
        "96",
        """
# Task

- **Тип:** Research / Discovery

Assess wearable platform feasibility and document evidence. Do not implement product code.
""",
    )

    assert [item["name"] for item in plan["worker_role_passes"]] == ["researcher"]
    assert plan["execution"]["production_writer"] is None
    assert plan["ponytail"]["mode"] == "off"
    assert plan["agent_budget"]["max_spawned_subagents"] == 0
    assert plan["agent_budget"]["max_completed_tool_actions"] == 240
    assert plan["execution"]["spawn_extra_codex_processes"] is False


def test_cross_cutting_multi_surface_task_adds_orchestrator_and_graphify() -> None:
    plan = build_agent_flow(
        "292",
        """
# Task

- **Тип:** Feature

Implement a multi-stream trainer CRM change spanning FastAPI backend,
React frontend, and a PostgreSQL/Alembic migration.
""",
    )

    assert [item["name"] for item in plan["worker_role_passes"]] == [
        "orchestrator",
        "implementer",
    ]
    assert plan["routing"]["cross_cutting"] is True
    assert plan["routing"]["detected_surfaces"] == ["backend", "frontend", "database"]
    assert plan["graphify"]["bootstrap_required"] is True
    assert plan["ponytail"]["mode"] == "lite"
    assert plan["agent_budget"]["max_spawned_subagents"] == 2
    assert plan["agent_budget"]["max_concurrent_subagents"] == 2
    assert plan["agent_budget"]["max_collab_tool_calls"] == 10
    assert plan["agent_budget"]["max_completed_tool_actions"] == 240


def test_explicit_roles_override_inferred_orchestrator_and_qa() -> None:
    plan = build_agent_flow(
        "300",
        """
# Task

- **Тип:** Feature
- **Основная роль:** implementer
- **Дополнительные роли lifecycle:** qa-verifier, integration-release

Change FastAPI backend, React UI and PostgreSQL migration for a user-facing workflow.
""",
    )

    assert [item["name"] for item in plan["worker_role_passes"]] == [
        "implementer",
        "qa-verifier",
    ]
    assert plan["routing"]["inferred_roles"] == []
    assert plan["graphify"]["bootstrap_required"] is True


def test_user_facing_task_without_role_contract_infers_bounded_qa() -> None:
    plan = build_agent_flow(
        "301",
        """
# Task

- **Тип:** Feature

Update the React UI and responsive mobile UX for the progress screen.
""",
    )

    assert [item["name"] for item in plan["worker_role_passes"]] == [
        "implementer",
        "qa-verifier",
    ]
    assert plan["routing"]["inferred_roles"] == ["qa-verifier"]


def test_agent_flow_never_allows_parallel_production_writers() -> None:
    plan = build_agent_flow(
        "302",
        """
# Task

- **Тип:** Feature

Multi-stream FastAPI backend + React frontend + PostgreSQL migration.
""",
    )

    assert plan["execution"]["single_production_writer"] is True
    assert plan["execution"]["parallel_writers_within_task"] is False
    assert plan["execution"]["production_writer"] == "implementer"
    assert plan["execution"]["new_agent_framework"] is False


def test_plan_does_not_copy_private_task_content() -> None:
    secret_marker = "PRIVATE-CUSTOMER-NAME-DO-NOT-COPY"
    plan = build_agent_flow(
        "303",
        f"""
# Task

- **Тип:** Feature
- **Основная роль:** implementer

Change a helper. Private note: {secret_marker}
""",
        issue_contract={"scope": f"also-private-{secret_marker}"},
    )

    serialized = json.dumps(plan, ensure_ascii=False)
    assert secret_marker not in serialized
    assert plan["routing"]["issue_contract_present"] is True
    assert len(plan["task_fingerprint_sha256"]) == 64


def test_explicit_ponytail_ultra_override_is_respected() -> None:
    plan = build_agent_flow(
        "305",
        """
# Task

- **Тип:** Feature
- **Основная роль:** implementer
- **Ponytail:** ultra

Change one isolated helper.
""",
    )

    assert plan["ponytail"]["mode"] == "ultra"
    assert plan["ponytail"]["source"] == "explicit-task-field"


def test_explicit_ponytail_off_override_is_respected() -> None:
    plan = build_agent_flow(
        "306",
        """
# Task

- **Тип:** Feature
- **Основная роль:** implementer
- **Ponytail mode:** off

Change one isolated helper.
""",
    )

    assert plan["ponytail"]["mode"] == "off"
    assert plan["ponytail"]["source"] == "explicit-task-field"


def test_ultra_is_never_inferred() -> None:
    ordinary = build_agent_flow(
        "307",
        """
# Task

- **Тип:** Feature

Change a small Python helper.
""",
    )
    cross_cutting = build_agent_flow(
        "308",
        """
# Task

- **Тип:** Feature

Cross-cutting architecture change in FastAPI backend and React frontend.
""",
    )

    assert ordinary["ponytail"]["mode"] == "full"
    assert cross_cutting["ponytail"]["mode"] == "lite"
    assert ordinary["ponytail"]["mode"] != "ultra"
    assert cross_cutting["ponytail"]["mode"] != "ultra"


def test_rendered_prompt_contains_bounded_contract_and_graphify_rule() -> None:
    plan = build_agent_flow(
        "304",
        """
# Task

- **Тип:** Feature

Cross-cutting architecture change in FastAPI backend and React frontend.
""",
    )

    prompt = render_agent_flow_prompt(plan)

    assert "Agent Flow v1 routing contract" in prompt
    assert '"bootstrap_required": true' in prompt
    assert "Only implementer may write production code" in prompt
    assert "Do not synthesize reviewer/security-review agents" in prompt
    assert "never install it automatically" in prompt
    assert "ponytail-review/audit loops" in prompt
    assert "within agent_budget" in prompt
    assert "@ponytail-review" not in prompt
