from __future__ import annotations

import sys
from pathlib import Path

import pytest

DISCOVERY_ROOT = Path(__file__).parents[1] / "deploy" / "hermes-discovery"
sys.path.insert(0, str(DISCOVERY_ROOT))

import hermes_resource_guard as guard  # noqa: E402


def _facts(**overrides: int | float) -> guard.HostFacts:
    values: dict[str, int | float] = {
        "memory_available_mib": guard.MIN_MEMORY_AVAILABLE_MIB,
        "swap_used_mib": guard.MAX_SWAP_USED_MIB,
        "load1": guard.MAX_LOAD1,
        "disk_free_mib": guard.MIN_DISK_FREE_MIB,
    }
    values.update(overrides)
    return guard.HostFacts(**values)


def test_threshold_boundaries_are_allowed() -> None:
    decision = guard.evaluate_facts(_facts())

    assert decision.allowed is True
    assert decision.reason_code is None


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"memory_available_mib": guard.MIN_MEMORY_AVAILABLE_MIB - 1}, "insufficient_memory"),
        ({"swap_used_mib": guard.MAX_SWAP_USED_MIB + 1}, "swap_pressure"),
        ({"load1": guard.MAX_LOAD1 + 0.01}, "high_load"),
        ({"disk_free_mib": guard.MIN_DISK_FREE_MIB - 1}, "insufficient_disk"),
    ],
)
def test_capacity_failures_have_stable_reason_codes(
    override: dict[str, int | float], reason: str
) -> None:
    decision = guard.evaluate_facts(_facts(**override))

    assert decision.allowed is False
    assert decision.reason_code == reason


def test_deployment_lock_failure_has_priority_over_capacity() -> None:
    decision = guard.evaluate_facts(_facts(memory_available_mib=1), deployment_active=True)

    assert decision.reason_code == "yfc_deploy_active"


def test_guard_defaults_to_separate_vm_without_an_implicit_yfc_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HERMES_YFC_DEPLOYMENT_LOCK", raising=False)
    args = guard._parser().parse_args(["check", "--phase", "discovery"])

    assert args.mode == "separate-vm"
    assert args.deployment_lock is None


def test_decision_output_contains_thresholds_without_environment_values() -> None:
    output = guard.evaluate_facts(_facts()).as_dict(phase="discovery", mode="colocated-isolated")

    assert output["status"] == "ready"
    assert output["thresholds"]["memory_available_min_mib"] == 768
    assert output["privacy"] == {"secrets_read": False, "secrets_logged": False}


def test_transition_probe_is_bounded_and_uses_explicit_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> object:
        calls.append((command, kwargs))
        return type("Completed", (), {"returncode": 0, "stdout": "backend-blue\tfalse\n"})()

    monkeypatch.setattr(guard.subprocess, "run", fake_run)

    assert guard._docker_transition_active() is False
    assert calls[0][0][:3] == ["docker", "ps", "--filter"]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["timeout"] == 3
