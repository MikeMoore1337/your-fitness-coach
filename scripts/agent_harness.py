"""Deterministic, repository-local harness for YFC agent workflow quality.

The harness deliberately does not create a second lifecycle. Agent evals reuse
existing pytest regressions, checkpoints are derived from TaskController
recovery state, and learning output is only an owner-review candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.artifact_manager import ArtifactError, ArtifactManager, normalize_task_id
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from artifact_manager import ArtifactError, ArtifactManager, normalize_task_id

EVAL_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1
CHECKPOINT_SCHEMA_VERSION = 1
LEARNING_SCHEMA_VERSION = 1
EVAL_KINDS = {"capability", "regression"}
LEARNING_ACTIONS = {"UPDATE_EXISTING", "NEW_SKILL", "DOC_ONLY", "REJECT"}
LEARNING_RISKS = {"low", "medium", "high"}
SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[_-])(password|passwd|token|secret|api[_-]?key|authorization|cookie)(?:$|[_-])",
    re.IGNORECASE,
)
SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:password|passwd|token|secret|api[_-]?key)\b\s*[:=]\s*[^\s,;]{8,}"),
)
CANONICAL_INSTRUCTION_PATHS = (
    "AGENTS.md",
    ".agents/README.md",
    "codex-backlog/TASK_EXECUTION_LIFECYCLE.md",
    "codex-backlog/GLOBAL_RULES.md",
)
CHECKPOINT_LEASE_FIELDS = (
    "branch",
    "worktree",
    "base_sha",
    "head_sha",
    "ready_head_sha",
    "pr_number",
    "delivery_owner",
    "deployed_sha",
    "production_run_id",
    "updated_at",
)


class AgentHarnessError(RuntimeError):
    """Fail-closed error for invalid or unsafe harness input."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _timestamp_slug() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _atomic_write_json(path: Path, payload: Mapping[str, Any] | Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _safe_repo_relative_path(repo_root: Path, value: str) -> Path:
    raw = Path(value.strip())
    if raw.is_absolute() or not raw.parts or any(part in {"", ".", ".."} for part in raw.parts):
        raise AgentHarnessError(f"Repository-relative path is invalid: {value!r}")
    root = repo_root.resolve()
    candidate = (root / raw).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise AgentHarnessError(f"Path escapes repository root: {value!r}") from error
    return candidate


def _normalized_text(value: str) -> str:
    return " ".join(re.findall(r"[a-zа-яё0-9]+", value.casefold()))


def _token_set(value: str) -> set[str]:
    return {token for token in _normalized_text(value).split() if len(token) >= 4}


def _assert_secret_free(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if SENSITIVE_KEY_RE.search(key_text) and item not in (None, "", [], {}):
                raise AgentHarnessError(
                    f"Sensitive field is not allowed in harness artifact: {path}.{key_text}"
                )
            _assert_secret_free(item, path=f"{path}.{key_text}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_secret_free(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        for pattern in SECRET_PATTERNS:
            if pattern.search(value):
                raise AgentHarnessError(
                    f"Secret-like content is not allowed in harness artifact: {path}"
                )


def _validate_nodeid(repo_root: Path, nodeid: str) -> None:
    if not isinstance(nodeid, str) or "::" not in nodeid:
        raise AgentHarnessError(f"Eval pytest nodeid is invalid: {nodeid!r}")
    path_text, test_name = nodeid.split("::", maxsplit=1)
    if not path_text.startswith("tests/") or not path_text.endswith(".py"):
        raise AgentHarnessError(f"Eval nodeid must target tests/*.py: {nodeid}")
    if not test_name.startswith("test_"):
        raise AgentHarnessError(f"Eval nodeid must target a test_* function: {nodeid}")
    path = _safe_repo_relative_path(repo_root, path_text)
    if not path.is_file():
        raise AgentHarnessError(f"Eval test file does not exist: {path_text}")
    source = path.read_text(encoding="utf-8")
    function_name = test_name.split("[", maxsplit=1)[0]
    if re.search(rf"^def {re.escape(function_name)}\s*\(", source, flags=re.MULTILINE) is None:
        raise AgentHarnessError(f"Eval test function does not exist: {nodeid}")


def validate_eval_manifest(
    payload: Any,
    *,
    repo_root: Path,
    source: str,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise AgentHarnessError(f"Eval manifest must be a JSON object: {source}")
    if payload.get("schema_version") != EVAL_SCHEMA_VERSION:
        raise AgentHarnessError(
            f"Eval manifest {source} schema_version must be {EVAL_SCHEMA_VERSION}"
        )
    suite = payload.get("suite")
    if not isinstance(suite, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", suite):
        raise AgentHarnessError(f"Eval manifest {source} has invalid suite")
    description = payload.get("description")
    if not isinstance(description, str) or not description.strip():
        raise AgentHarnessError(f"Eval manifest {source} requires description")
    evals = payload.get("evals")
    if not isinstance(evals, list) or not evals:
        raise AgentHarnessError(f"Eval manifest {source} requires non-empty evals")

    normalized_evals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in evals:
        if not isinstance(item, Mapping):
            raise AgentHarnessError(f"Eval manifest {source} contains a non-object eval")
        eval_id = item.get("id")
        kind = item.get("kind")
        eval_description = item.get("description")
        nodeids = item.get("pytest_nodeids")
        if not isinstance(eval_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", eval_id):
            raise AgentHarnessError(f"Eval manifest {source} contains invalid eval id")
        if eval_id in seen:
            raise AgentHarnessError(f"Eval manifest {source} contains duplicate eval id {eval_id}")
        seen.add(eval_id)
        if kind not in EVAL_KINDS:
            raise AgentHarnessError(f"Eval {suite}/{eval_id} has invalid kind {kind!r}")
        if not isinstance(eval_description, str) or not eval_description.strip():
            raise AgentHarnessError(f"Eval {suite}/{eval_id} requires description")
        if not isinstance(nodeids, list) or not nodeids:
            raise AgentHarnessError(f"Eval {suite}/{eval_id} requires pytest_nodeids")
        normalized_nodeids: list[str] = []
        for nodeid in nodeids:
            _validate_nodeid(repo_root, nodeid)
            normalized_nodeids.append(str(nodeid))
        normalized_evals.append(
            {
                "id": eval_id,
                "kind": kind,
                "description": eval_description.strip(),
                "pytest_nodeids": normalized_nodeids,
            }
        )
    return {
        "schema_version": EVAL_SCHEMA_VERSION,
        "suite": suite,
        "description": description.strip(),
        "evals": normalized_evals,
        "source": source,
    }


def load_eval_manifests(repo_root: Path, eval_root: Path | None = None) -> list[dict[str, Any]]:
    root = eval_root or repo_root / ".agents" / "evals"
    if not root.is_dir():
        raise AgentHarnessError(f"Eval directory does not exist: {root}")
    manifests: list[dict[str, Any]] = []
    suites: set[str] = set()
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise AgentHarnessError(f"Cannot read eval manifest {path}: {error}") from error
        manifest = validate_eval_manifest(payload, repo_root=repo_root, source=str(path))
        if manifest["suite"] in suites:
            raise AgentHarnessError(f"Duplicate eval suite: {manifest['suite']}")
        suites.add(manifest["suite"])
        manifests.append(manifest)
    if not manifests:
        raise AgentHarnessError(f"No eval manifests found in {root}")
    return manifests


def select_evals(
    manifests: Sequence[Mapping[str, Any]],
    *,
    suite: str | None = None,
    eval_id: str | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for manifest in manifests:
        if suite is not None and manifest["suite"] != suite:
            continue
        for item in manifest["evals"]:
            if eval_id is not None and item["id"] != eval_id:
                continue
            selected.append({"suite": manifest["suite"], **dict(item)})
    if not selected:
        selector = f"suite={suite!r}, eval_id={eval_id!r}"
        raise AgentHarnessError(f"No agent evals matched {selector}")
    return selected


def _trim_process_output(value: str, *, limit: int = 6000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def run_evals(
    repo_root: Path,
    selected: Sequence[Mapping[str, Any]],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for item in selected:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *[str(nodeid) for nodeid in item["pytest_nodeids"]],
        ]
        started = time.monotonic()
        completed = runner(
            command,
            cwd=repo_root,
            check=False,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        duration_seconds = round(time.monotonic() - started, 3)
        results.append(
            {
                "suite": item["suite"],
                "id": item["id"],
                "kind": item["kind"],
                "status": "PASS" if completed.returncode == 0 else "FAIL",
                "returncode": completed.returncode,
                "duration_seconds": duration_seconds,
                "pytest_nodeids": list(item["pytest_nodeids"]),
                "stdout": _trim_process_output(completed.stdout or ""),
                "stderr": _trim_process_output(completed.stderr or ""),
            }
        )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "classification": "agent-eval-report",
        "overall": "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL",
        "evals": results,
    }


def write_eval_report(
    repo_root: Path,
    task_id: str,
    report: Mapping[str, Any],
    *,
    artifact_root: Path | None = None,
) -> Path:
    normalized = normalize_task_id(task_id)
    _assert_secret_free(report)
    manager = ArtifactManager(artifact_root or repo_root / ".artifacts", repo_root=repo_root)
    suites = sorted(
        {str(item["suite"]) for item in report.get("evals", []) if isinstance(item, Mapping)}
    )
    suffix = "-".join(suites) if suites else "selected"
    target = manager.allocate(
        normalized,
        "evidence",
        f"evidence/agent-evals/{_timestamp_slug()}-{suffix}.json",
        purpose="deterministic agent lifecycle eval report",
        command="scripts/agent_harness.py eval run",
        owner="agent-harness",
    )
    payload = dict(report)
    payload["artifact_path"] = target.relative_to(repo_root).as_posix()
    _atomic_write_json(target, payload)
    return target


def recover_task_state(
    repo_root: Path,
    task_id: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    normalized = normalize_task_id(task_id)
    command = [
        sys.executable,
        str(repo_root / "scripts" / "task_session.py"),
        "--repo",
        str(repo_root),
        "recover",
        normalized,
    ]
    completed = runner(
        command,
        cwd=repo_root,
        check=False,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise AgentHarnessError(f"Task recovery snapshot failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AgentHarnessError("Task recovery returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise AgentHarnessError("Task recovery snapshot must be a JSON object")
    return payload


def build_checkpoint(recovery: Mapping[str, Any]) -> dict[str, Any]:
    if recovery.get("mutation_performed") is not False:
        raise AgentHarnessError("Checkpoint requires read-only recovery state")
    task_id = normalize_task_id(str(recovery.get("task_id", "")))
    lease = recovery.get("lease")
    lease_map = lease if isinstance(lease, Mapping) else {}
    delivery = recovery.get("delivery")
    delivery_map = delivery if isinstance(delivery, Mapping) else {}
    owner = delivery_map.get("owner")
    owner_map = owner if isinstance(owner, Mapping) else {}

    anchors = {
        key: lease_map[key]
        for key in CHECKPOINT_LEASE_FIELDS
        if key in lease_map and lease_map[key] not in (None, "", [], {})
    }
    checkpoint = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "classification": "derived-agent-checkpoint",
        "generated_at": utc_now(),
        "source": "scripts/task_session.py recover",
        "source_of_truth": False,
        "task_id": task_id,
        "lifecycle_state": recovery.get("lifecycle_state"),
        "recovery_classification": recovery.get("classification"),
        "anchors": anchors,
        "branches": list(recovery.get("branches") or []),
        "issues": list(recovery.get("issues") or []),
        "delivery": {
            "owner_task_id": owner_map.get("task_id"),
            "owner_branch": owner_map.get("branch"),
        },
        "mutation_performed": False,
    }
    _assert_secret_free(checkpoint)
    return checkpoint


def write_checkpoint(
    repo_root: Path,
    task_id: str,
    checkpoint: Mapping[str, Any],
    *,
    artifact_root: Path | None = None,
) -> Path:
    normalized = normalize_task_id(task_id)
    if checkpoint.get("task_id") != normalized:
        raise AgentHarnessError("Checkpoint task ID does not match requested task")
    manager = ArtifactManager(artifact_root or repo_root / ".artifacts", repo_root=repo_root)
    target = manager.allocate(
        normalized,
        "temporary",
        "temporary/agent-harness/checkpoint.json",
        purpose="derived read-only task checkpoint for session recovery",
        command="scripts/agent_harness.py checkpoint",
        owner="agent-harness",
    )
    _atomic_write_json(target, checkpoint)
    return target


def _instruction_sources(repo_root: Path) -> list[Path]:
    paths = [
        repo_root / relative
        for relative in CANONICAL_INSTRUCTION_PATHS
        if (repo_root / relative).is_file()
    ]
    roles = repo_root / ".agents" / "roles"
    skills = repo_root / ".agents" / "skills"
    if roles.is_dir():
        paths.extend(sorted(roles.glob("*.md")))
    if skills.is_dir():
        paths.extend(sorted(skills.glob("*/SKILL.md")))
    return paths


def find_instruction_overlap(repo_root: Path, pattern: str) -> list[dict[str, Any]]:
    pattern_tokens = _token_set(pattern)
    if not pattern_tokens:
        return []
    normalized_pattern = _normalized_text(pattern)
    matches: list[dict[str, Any]] = []
    for path in _instruction_sources(repo_root):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError, UnicodeError:
            continue
        normalized_content = _normalized_text(content)
        content_tokens = _token_set(content)
        overlap = len(pattern_tokens & content_tokens) / len(pattern_tokens)
        exact = normalized_pattern in normalized_content
        if exact or overlap >= 0.5:
            matches.append(
                {
                    "path": path.relative_to(repo_root).as_posix(),
                    "token_overlap": round(overlap, 3),
                    "exact_normalized_match": exact,
                }
            )
    matches.sort(
        key=lambda item: (
            bool(item["exact_normalized_match"]),
            float(item["token_overlap"]),
        ),
        reverse=True,
    )
    return matches[:8]


def _validate_learning_destination(repo_root: Path, destination: str) -> str:
    path = _safe_repo_relative_path(repo_root, destination)
    relative = path.relative_to(repo_root).as_posix()
    allowed = (
        relative in CANONICAL_INSTRUCTION_PATHS
        or relative.startswith(".agents/roles/")
        or relative.startswith(".agents/skills/")
        or relative.startswith("docs/")
    )
    if not allowed or not relative.endswith(".md"):
        raise AgentHarnessError(
            "Learning destination must be an instruction/role/skill/docs Markdown path"
        )
    return relative


def propose_learning_candidate(
    repo_root: Path,
    task_id: str,
    *,
    pattern: str,
    evidence: Sequence[str],
    why_reusable: str,
    destination: str,
    conflict_analysis: str,
    risk: str,
    action: str,
    artifact_root: Path | None = None,
) -> tuple[dict[str, Any], Path, bool]:
    normalized_task = normalize_task_id(task_id)
    if action not in LEARNING_ACTIONS:
        raise AgentHarnessError(f"Unknown learning action: {action}")
    if risk not in LEARNING_RISKS:
        raise AgentHarnessError(f"Unknown learning risk: {risk}")
    if not pattern.strip() or not why_reusable.strip() or not conflict_analysis.strip():
        raise AgentHarnessError(
            "Learning candidate requires pattern, reuse rationale and conflict analysis"
        )
    if not evidence or any(not item.strip() for item in evidence):
        raise AgentHarnessError("Learning candidate requires non-empty evidence")
    relative_destination = _validate_learning_destination(repo_root, destination)
    raw = {
        "pattern": pattern.strip(),
        "evidence": [item.strip() for item in evidence],
        "why_reusable": why_reusable.strip(),
        "destination": relative_destination,
        "conflict_analysis": conflict_analysis.strip(),
        "risk": risk,
        "action": action,
    }
    _assert_secret_free(raw)
    normalized_pattern = _normalized_text(raw["pattern"])
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "pattern": normalized_pattern,
                "destination": relative_destination,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:20]

    manager = ArtifactManager(artifact_root or repo_root / ".artifacts", repo_root=repo_root)
    target = manager.allocate(
        normalized_task,
        "deliverables",
        f"deliverables/agent-learning/{fingerprint}.json",
        purpose="owner-reviewable reusable agent learning candidate",
        command="scripts/agent_harness.py learn propose",
        owner="agent-harness",
    )
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise AgentHarnessError(f"Cannot read existing learning candidate: {error}") from error
        if isinstance(existing, Mapping) and existing.get("fingerprint") == fingerprint:
            return dict(existing), target, True
        raise AgentHarnessError(
            "Learning candidate fingerprint collision or corrupt existing artifact"
        )

    candidate = {
        "schema_version": LEARNING_SCHEMA_VERSION,
        "classification": "agent-learning-candidate",
        "created_at": utc_now(),
        "task_id": normalized_task,
        "fingerprint": fingerprint,
        **raw,
        "overlap": find_instruction_overlap(repo_root, raw["pattern"]),
        "promotion": {
            "required": "explicit-owner/manual",
            "auto_promotion_supported": False,
        },
    }
    _assert_secret_free(candidate)
    _atomic_write_json(target, candidate)
    return candidate, target, False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    root = parser.add_subparsers(dest="command", required=True)

    eval_parser = root.add_parser("eval")
    eval_commands = eval_parser.add_subparsers(dest="eval_command", required=True)
    eval_validate = eval_commands.add_parser("validate")
    eval_validate.add_argument("--eval-root", type=Path)
    eval_run = eval_commands.add_parser("run")
    eval_run.add_argument("--eval-root", type=Path)
    eval_run.add_argument("--suite")
    eval_run.add_argument("--eval-id")
    eval_run.add_argument("--task-id")

    checkpoint = root.add_parser("checkpoint")
    checkpoint.add_argument("task_id")

    learn = root.add_parser("learn")
    learn_commands = learn.add_subparsers(dest="learn_command", required=True)
    propose = learn_commands.add_parser("propose")
    propose.add_argument("task_id")
    propose.add_argument("--pattern", required=True)
    propose.add_argument("--evidence", action="append", required=True)
    propose.add_argument("--why-reusable", required=True)
    propose.add_argument("--destination", required=True)
    propose.add_argument("--conflict-analysis", required=True)
    propose.add_argument("--risk", choices=sorted(LEARNING_RISKS), required=True)
    propose.add_argument("--action", choices=sorted(LEARNING_ACTIONS), required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = args.repo.resolve()
    try:
        if args.command == "eval" and args.eval_command == "validate":
            manifests = load_eval_manifests(repo_root, args.eval_root)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "suite_count": len(manifests),
                        "eval_count": sum(len(item["evals"]) for item in manifests),
                        "suites": [item["suite"] for item in manifests],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "eval" and args.eval_command == "run":
            manifests = load_eval_manifests(repo_root, args.eval_root)
            selected = select_evals(
                manifests,
                suite=args.suite,
                eval_id=args.eval_id,
            )
            report = run_evals(repo_root, selected)
            if args.task_id:
                target = write_eval_report(repo_root, args.task_id, report)
                report = {
                    **report,
                    "artifact_path": target.relative_to(repo_root).as_posix(),
                }
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["overall"] == "PASS" else 1

        if args.command == "checkpoint":
            recovery = recover_task_state(repo_root, args.task_id)
            checkpoint_payload = build_checkpoint(recovery)
            target = write_checkpoint(repo_root, args.task_id, checkpoint_payload)
            print(
                json.dumps(
                    {
                        **checkpoint_payload,
                        "artifact_path": target.relative_to(repo_root).as_posix(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "learn" and args.learn_command == "propose":
            candidate, target, duplicate = propose_learning_candidate(
                repo_root,
                args.task_id,
                pattern=args.pattern,
                evidence=args.evidence,
                why_reusable=args.why_reusable,
                destination=args.destination,
                conflict_analysis=args.conflict_analysis,
                risk=args.risk,
                action=args.action,
            )
            print(
                json.dumps(
                    {
                        **candidate,
                        "artifact_path": target.relative_to(repo_root).as_posix(),
                        "duplicate": duplicate,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        raise AssertionError("Unhandled agent harness command")
    except (AgentHarnessError, ArtifactError, OSError, json.JSONDecodeError) as error:
        print(f"agent harness error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
