"""Small, source-backed evidence primitives for the v2 lifecycle controller.

This module deliberately contains no task-specific IDs or local-state writes.  Git,
GitHub and the deployment workflow remain the evidence sources; callers decide when
to persist a verified snapshot through the existing lifecycle.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

try:
    from scripts.issue_workflow import normalize_task_contract, task_contract_fingerprint
except ModuleNotFoundError:
    from issue_workflow import normalize_task_contract, task_contract_fingerprint


SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
PRODUCTION_WORKFLOW_NAME = "Release production"
PRODUCTION_ENVIRONMENT = "production"
AUTHORIZATION_JOB_NAME = "Authorize exact merged master revision"
APPLICATION_DEPLOY_JOB_NAME = "Deploy immutable tested bundle"
DEPLOY_SHA_RE = re.compile(r"\bDEPLOY_SHA\s*(?:=|:)\s*([0-9a-f]{40})\b", re.IGNORECASE)
DEPLOYMENT_MARKER_RE = re.compile(
    r"\bProduction deployment completed:\s*([0-9a-f]{40})\b", re.IGNORECASE
)


class ControllerV2Error(ValueError):
    """Raised when source evidence cannot prove a controller invariant."""


def _sha(value: Any, label: str) -> str:
    normalized = str(value or "").lower()
    if SHA_RE.fullmatch(normalized) is None:
        raise ControllerV2Error(f"{label} is not a full commit SHA")
    return normalized


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_value(item) for item in value)
    return value


def contract_fingerprint(contract: Mapping[str, Any]) -> str:
    """Use the existing owner-authored contract normalization and hash."""

    return task_contract_fingerprint(contract)


@dataclass(frozen=True)
class ProductionEvidence:
    """Compact proof that one immutable revision reached production."""

    run_id: int
    run_url: str | None
    requested_sha: str
    run_head_sha: str
    run_head_branch: str | None
    run_event: str | None
    run_conclusion: str
    environment: str
    authorization_job: str
    application_deploy_job: str
    deployment_success_verified: bool
    verification_mode: str
    deploy_sha_marker_count: int = 0
    completion_marker_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_url": self.run_url,
            "requested_sha": self.requested_sha,
            "head_sha": self.run_head_sha,
            "run_head_branch": self.run_head_branch,
            "run_event": self.run_event,
            "run_conclusion": self.run_conclusion,
            "environment": self.environment,
            "authorization_job": self.authorization_job,
            "application_deploy_job": self.application_deploy_job,
            "deployed_sha": self.requested_sha,
            "deployment_success_verified": self.deployment_success_verified,
            "verification_mode": self.verification_mode,
            "deploy_sha_marker_count": self.deploy_sha_marker_count,
            "completion_marker_count": self.completion_marker_count,
        }

    def as_legacy_dict(self) -> dict[str, Any]:
        """Return the pre-v2 production shape used by existing history validators."""

        return {
            "run_id": self.run_id,
            "run_url": self.run_url,
            "head_sha": self.requested_sha,
            "run_conclusion": self.run_conclusion,
            "environment": self.environment,
            "deployed_sha": self.requested_sha,
            "deployment_success_verified": self.deployment_success_verified,
        }


@dataclass(frozen=True)
class TaskSnapshot:
    """Read-only derived view of task, Git and GitHub evidence."""

    task_id: str
    issue_number: int | None = None
    issue_state: str | None = None
    contract: Mapping[str, Any] | None = None
    source_spec: str | None = None
    spec_fingerprint: str | None = None
    dependencies: tuple[str, ...] = ()
    branch: str | None = None
    worktree: str | None = None
    task_head: str | None = None
    pr_number: int | None = None
    pr_state: str | None = None
    pr_head: str | None = None
    pr_base: str | None = None
    exact_head_ci: bool | None = None
    merge_sha: str | None = None
    production: ProductionEvidence | None = None
    deployed_sha: str | None = None
    current_master: str | None = None
    ancestry: Mapping[str, Any] | None = None
    active_writer: bool = False
    delivery_owner: str | None = None
    dirty_wip: bool = False
    unique_wip: bool = False
    terminal_classification: str | None = None
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    @classmethod
    def from_contract(
        cls,
        task_id: str,
        contract: Mapping[str, Any],
        **evidence: Any,
    ) -> TaskSnapshot:
        normalized = normalize_task_contract(contract)
        dependencies = tuple(str(item) for item in normalized.get("dependencies", []))
        return cls(
            task_id=str(task_id),
            contract=normalized,
            source_spec=str(normalized.get("source_spec", "")),
            spec_fingerprint=task_contract_fingerprint(normalized),
            dependencies=dependencies,
            **evidence,
        )

    def as_dict(self) -> dict[str, Any]:
        result = {
            "task_id": self.task_id,
            "issue_number": self.issue_number,
            "issue_state": self.issue_state,
            "contract": self.contract,
            "source_spec": self.source_spec,
            "spec_fingerprint": self.spec_fingerprint,
            "dependencies": self.dependencies,
            "branch": self.branch,
            "worktree": self.worktree,
            "task_head": self.task_head,
            "pr_number": self.pr_number,
            "pr_state": self.pr_state,
            "pr_head": self.pr_head,
            "pr_base": self.pr_base,
            "exact_head_ci": self.exact_head_ci,
            "merge_sha": self.merge_sha,
            "production": self.production.as_dict() if self.production else None,
            "deployed_sha": self.deployed_sha,
            "current_master": self.current_master,
            "ancestry": self.ancestry,
            "active_writer": self.active_writer,
            "delivery_owner": self.delivery_owner,
            "dirty_wip": self.dirty_wip,
            "unique_wip": self.unique_wip,
            "terminal_classification": self.terminal_classification,
            "warnings": self.warnings,
            "blockers": self.blockers,
        }
        return _json_value(result)


@dataclass(frozen=True)
class ControllerDrift:
    """One independently verified controller-only master merge."""

    commit_sha: str
    pr_number: int
    changed_paths: tuple[str, ...]
    exact_head_ci: bool
    deploy_skipped: bool
    classification: str = "controller-only"

    def as_dict(self) -> dict[str, Any]:
        return _json_value(
            {
                "commit_sha": self.commit_sha,
                "pr_number": self.pr_number,
                "changed_paths": self.changed_paths,
                "exact_head_ci": self.exact_head_ci,
                "deploy_skipped": self.deploy_skipped,
                "classification": self.classification,
            }
        )


def verify_controller_drift(
    records: Sequence[Mapping[str, Any]],
    *,
    allowlisted_paths: Iterable[str],
) -> tuple[ControllerDrift, ...]:
    """Verify a supplied drift inventory without trusting local labels."""

    allowed = {str(path).replace("\\", "/") for path in allowlisted_paths}
    verified: list[ControllerDrift] = []
    for record in records:
        commit_sha = _sha(record.get("commit_sha"), "controller drift commit")
        pr_number = record.get("pr_number")
        changed_paths = tuple(
            sorted(str(path).replace("\\", "/") for path in record.get("changed_paths", ()))
        )
        if type(pr_number) is not int or pr_number <= 0:
            raise ControllerV2Error("controller drift PR number is invalid")
        if not changed_paths or set(changed_paths) - allowed:
            raise ControllerV2Error("controller drift contains a non-allowlisted path")
        if record.get("same_repository") is not True:
            raise ControllerV2Error("controller drift lacks same-repository provenance")
        if record.get("merged_to_protected_master") is not True:
            raise ControllerV2Error("controller drift lacks protected-master merge provenance")
        if record.get("controller_provenance") is not True:
            raise ControllerV2Error("controller drift lacks controller provenance")
        if record.get("exact_head_ci") is not True:
            raise ControllerV2Error("controller drift lacks exact-head CI evidence")
        if record.get("deploy_skipped") is not True:
            raise ControllerV2Error("controller drift lacks deploy-skip evidence")
        verified.append(
            ControllerDrift(
                commit_sha=commit_sha,
                pr_number=pr_number,
                changed_paths=changed_paths,
                exact_head_ci=True,
                deploy_skipped=True,
            )
        )
    return tuple(verified)


def parse_manual_release_markers(logs: str | Iterable[str], requested_sha: str) -> dict[str, Any]:
    """Extract only immutable deployment markers; never return raw log content."""

    expected = _sha(requested_sha, "requested deployment SHA")
    chunks = [logs] if isinstance(logs, str) else [str(chunk) for chunk in logs]
    text = "\n".join(chunks)
    deploy_markers = [value.lower() for value in DEPLOY_SHA_RE.findall(text)]
    completion_markers = [value.lower() for value in DEPLOYMENT_MARKER_RE.findall(text)]
    if not deploy_markers or set(deploy_markers) != {expected}:
        raise ControllerV2Error("manual release logs do not contain one exact DEPLOY_SHA")
    if not completion_markers or set(completion_markers) != {expected}:
        raise ControllerV2Error(
            "manual release logs do not contain one exact production completion marker"
        )
    return {
        "deploy_sha": expected,
        "deploy_sha_marker_count": len(deploy_markers),
        "completion_marker_count": len(completion_markers),
    }


def _successful_job(jobs: Sequence[Mapping[str, Any]], name: str) -> Mapping[str, Any]:
    matches = [job for job in jobs if job.get("name") == name]
    if len(matches) != 1 or matches[0].get("conclusion") != "success":
        raise ControllerV2Error(f"production run does not have one successful {name} job")
    return matches[0]


def verify_production_evidence(
    run: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
    requested_sha: str,
    *,
    current_master_sha: str | None = None,
    is_ancestor: Callable[[str, str], bool] | None = None,
    deployment_api_success: bool | None = None,
    deploy_logs: str | Iterable[str] | None = None,
    environment: str = PRODUCTION_ENVIRONMENT,
) -> ProductionEvidence:
    """Verify automatic release evidence or the supported manual recovery contract."""

    expected = _sha(requested_sha, "requested deployment SHA")
    run_id = run.get("id")
    if type(run_id) is not int or run_id <= 0:
        raise ControllerV2Error("production run ID is invalid")
    run_head_sha = _sha(run.get("head_sha"), "production run head SHA")
    if (
        run.get("name") != PRODUCTION_WORKFLOW_NAME
        or run.get("status") != "completed"
        or str(run.get("conclusion", "")).lower() != "success"
    ):
        raise ControllerV2Error("production run is not a completed successful release")

    event = str(run.get("event", "")) or None
    branch = str(run.get("head_branch", "")) or None
    if run_head_sha == expected and event != "workflow_dispatch":
        if deployment_api_success is not True:
            raise ControllerV2Error(
                "automatic production evidence requires a successful deployment API status"
            )
        return ProductionEvidence(
            run_id=run_id,
            run_url=run.get("html_url") if isinstance(run.get("html_url"), str) else None,
            requested_sha=expected,
            run_head_sha=run_head_sha,
            run_head_branch=branch,
            run_event=event,
            run_conclusion="success",
            environment=environment,
            authorization_job=AUTHORIZATION_JOB_NAME,
            application_deploy_job=APPLICATION_DEPLOY_JOB_NAME,
            deployment_success_verified=True,
            verification_mode="automatic-release-deployment-api",
        )

    if event != "workflow_dispatch":
        raise ControllerV2Error("non-dispatch production run does not match requested SHA")
    if branch != "master":
        raise ControllerV2Error("manual production recovery must run from protected master")
    if current_master_sha is None or is_ancestor is None:
        raise ControllerV2Error("manual production recovery requires current-master ancestry")
    current_master = _sha(current_master_sha, "current protected master SHA")
    try:
        target_ancestor = is_ancestor(expected, run_head_sha)
        run_ancestor = is_ancestor(run_head_sha, current_master)
    except Exception as error:
        raise ControllerV2Error("manual production ancestry could not be verified") from error
    if target_ancestor is not True or run_ancestor is not True:
        raise ControllerV2Error("manual production run is outside the protected-master ancestry")
    if deploy_logs is None:
        raise ControllerV2Error("manual production recovery requires deploy job logs")

    authorize = _successful_job(jobs, AUTHORIZATION_JOB_NAME)
    deploy = _successful_job(jobs, APPLICATION_DEPLOY_JOB_NAME)
    markers = parse_manual_release_markers(deploy_logs, expected)
    return ProductionEvidence(
        run_id=run_id,
        run_url=run.get("html_url") if isinstance(run.get("html_url"), str) else None,
        requested_sha=expected,
        run_head_sha=run_head_sha,
        run_head_branch=branch,
        run_event=event,
        run_conclusion="success",
        environment=environment,
        authorization_job=str(authorize.get("name")),
        application_deploy_job=str(deploy.get("name")),
        deployment_success_verified=True,
        verification_mode="owner-authorized-manual-release-log",
        deploy_sha_marker_count=int(markers["deploy_sha_marker_count"]),
        completion_marker_count=int(markers["completion_marker_count"]),
    )
