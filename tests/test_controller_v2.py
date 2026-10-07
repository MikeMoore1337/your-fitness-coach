from __future__ import annotations

from collections.abc import Mapping

import pytest
from scripts.controller_v2 import (
    APPLICATION_DEPLOY_JOB_NAME,
    AUTHORIZATION_JOB_NAME,
    ControllerV2Error,
    TaskSnapshot,
    contract_fingerprint,
    parse_manual_release_markers,
    verify_controller_drift,
    verify_production_evidence,
)

TARGET_SHA = "050bbd3f80aac0b8e84389fa3c4c28875df89066"
RUN_HEAD_SHA = "44e4b64e7de269ab1870c0f75cf4a4cdcd66c2fe"
CURRENT_MASTER_SHA = "2c6ee548a02ca06d4b33fed6cf0d6b2251aeb457"


def _run(*, head_sha: str, event: str = "workflow_dispatch", branch: str = "master") -> dict:
    return {
        "id": 37590644059,
        "html_url": "https://github.invalid/run/37590644059",
        "name": "Release production",
        "head_sha": head_sha,
        "head_branch": branch,
        "event": event,
        "status": "completed",
        "conclusion": "success",
    }


def _jobs(*, deploy_conclusion: str = "success") -> list[dict]:
    return [
        {"id": 1, "name": AUTHORIZATION_JOB_NAME, "conclusion": "success"},
        {"id": 2, "name": APPLICATION_DEPLOY_JOB_NAME, "conclusion": deploy_conclusion},
    ]


def _manual_logs(sha: str = TARGET_SHA) -> str:
    return f"DEPLOY_SHA={sha}\nProduction deployment completed: {sha}\n"


def _ancestor(left: str, right: str) -> bool:
    return (left, right) in {
        (TARGET_SHA, RUN_HEAD_SHA),
        (RUN_HEAD_SHA, CURRENT_MASTER_SHA),
    }


def test_manual_release_evidence_accepts_owner_recovery_without_deployment_object() -> None:
    evidence = verify_production_evidence(
        _run(head_sha=RUN_HEAD_SHA),
        _jobs(),
        TARGET_SHA,
        current_master_sha=CURRENT_MASTER_SHA,
        is_ancestor=_ancestor,
        deployment_api_success=False,
        deploy_logs=_manual_logs(),
    )

    assert evidence.verification_mode == "owner-authorized-manual-release-log"
    assert evidence.deployment_success_verified is True
    assert evidence.as_dict()["deployed_sha"] == TARGET_SHA
    assert "Production deployment completed" not in str(evidence.as_dict())


def test_automatic_release_requires_exact_deployment_api_evidence() -> None:
    evidence = verify_production_evidence(
        _run(head_sha=TARGET_SHA, event="push"),
        [],
        TARGET_SHA,
        deployment_api_success=True,
    )

    assert evidence.verification_mode == "automatic-release-deployment-api"
    assert evidence.as_legacy_dict()["head_sha"] == TARGET_SHA


@pytest.mark.parametrize(
    ("run", "jobs", "kwargs", "message"),
    [
        (
            _run(head_sha=RUN_HEAD_SHA),
            _jobs(),
            {
                "current_master_sha": CURRENT_MASTER_SHA,
                "is_ancestor": lambda _left, _right: False,
                "deploy_logs": _manual_logs(),
            },
            "ancestry",
        ),
        (
            _run(head_sha=RUN_HEAD_SHA),
            _jobs(deploy_conclusion="failure"),
            {
                "current_master_sha": CURRENT_MASTER_SHA,
                "is_ancestor": _ancestor,
                "deploy_logs": _manual_logs(),
            },
            "successful",
        ),
        (
            _run(head_sha=RUN_HEAD_SHA),
            _jobs(),
            {
                "current_master_sha": CURRENT_MASTER_SHA,
                "is_ancestor": _ancestor,
                "deploy_logs": _manual_logs("1111111111111111111111111111111111111111"),
            },
            "exact",
        ),
    ],
)
def test_manual_release_evidence_fails_closed(
    run: Mapping[str, object],
    jobs: list[dict],
    kwargs: dict,
    message: str,
) -> None:
    with pytest.raises(ControllerV2Error, match=message):
        verify_production_evidence(run, jobs, TARGET_SHA, **kwargs)


def test_automatic_release_does_not_accept_missing_deployment_api_status() -> None:
    with pytest.raises(ControllerV2Error, match="deployment API"):
        verify_production_evidence(
            _run(head_sha=TARGET_SHA, event="push"),
            [],
            TARGET_SHA,
            deployment_api_success=False,
        )


def test_manual_markers_reject_contradictory_sha_without_exposing_logs() -> None:
    other = "1111111111111111111111111111111111111111"
    with pytest.raises(ControllerV2Error, match="exact DEPLOY_SHA") as error:
        parse_manual_release_markers(f"DEPLOY_SHA={TARGET_SHA}\nDEPLOY_SHA={other}", TARGET_SHA)
    assert other not in str(error.value)


def test_task_snapshot_reuses_logical_contract_identity() -> None:
    contract = {
        "task_id": "747",
        "scope": "bounded",
        "acceptance": ["deterministic"],
        "dependencies": ["746"],
        "owner_gate": "none",
        "risk_lane": "GREEN",
        "source_spec": "github-issue:747",
        "issue_state": "queued",
    }
    snapshot = TaskSnapshot.from_contract("747", contract, issue_number=747)

    assert snapshot.source_spec == "github-issue:747"
    assert snapshot.spec_fingerprint == contract_fingerprint(contract)
    assert snapshot.dependencies == ("746",)
    assert snapshot.as_dict()["issue_number"] == 747


def test_controller_drift_requires_allowlisted_paths_and_provenance() -> None:
    record = {
        "commit_sha": CURRENT_MASTER_SHA,
        "pr_number": 777,
        "changed_paths": ["scripts/task_session.py"],
        "same_repository": True,
        "merged_to_protected_master": True,
        "controller_provenance": True,
        "exact_head_ci": True,
        "deploy_skipped": True,
    }

    evidence = verify_controller_drift([record], allowlisted_paths={"scripts/task_session.py"})

    assert evidence[0].classification == "controller-only"
    record["changed_paths"] = ["backend/app.py"]
    with pytest.raises(ControllerV2Error, match="non-allowlisted"):
        verify_controller_drift([record], allowlisted_paths={"scripts/task_session.py"})
