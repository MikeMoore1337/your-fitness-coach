"""Run one explicitly selected backlog task to its terminal delivery state.

The user-facing contract is one launch.  The worker keeps pull requests, checks,
release, deployment monitoring and safe closeout inside
the canonical task lifecycle.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.artifact_manager import ArtifactError, ArtifactManager
except ModuleNotFoundError:
    from artifact_manager import ArtifactError, ArtifactManager

SCRIPT_PATH = Path(__file__).resolve()
REPOSITORY_ROOT = SCRIPT_PATH.parents[1]
CONTROLLER_PATH = REPOSITORY_ROOT / "scripts" / "task_session.py"
ARCHIVE_HELPER_PATH = REPOSITORY_ROOT / "scripts" / "archive_backlog_task.py"
TASK_ID_RE = re.compile(r"^[0-9]+[A-Z]?$", re.IGNORECASE)
TRANSIENT_START_MARKERS = ("coordination state is locked",)


class DeliveryError(RuntimeError):
    """A terminal delivery refusal with a concise recovery pointer."""


def _event(stage: str, **payload: Any) -> None:
    print(json.dumps({"stage": stage, **payload}, ensure_ascii=False), flush=True)


def _run(
    args: Sequence[str], *, cwd: Path = REPOSITORY_ROOT, check: bool = True
) -> subprocess.CompletedProcess[str]:
    command = list(args)
    if command and command[0] == "git":
        git_config = ["-c", f"safe.directory={cwd.resolve().as_posix()}"]
        if os.name == "nt":
            git_config.extend(["-c", "core.longpaths=true"])
        command = ["git", *git_config, *command[1:]]
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise DeliveryError(detail)
    return completed


def _normalize_task_id(value: str) -> str:
    task_id = value.strip().upper()
    if not TASK_ID_RE.fullmatch(task_id):
        raise DeliveryError(f"Invalid task ID: {value!r}")
    return task_id


def _git_common_dir() -> Path:
    output = _run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"]).stdout.strip()
    return Path(output).resolve()


def _history(task_id: str) -> dict[str, Any] | None:
    path = _git_common_dir() / "codex-task-sessions-v1" / "history" / f"task-{task_id}.json"
    if not path.is_file():
        return None
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as error:
        raise DeliveryError(f"Cannot read controller history {path}: {error}") from error


def _archive_contract(canonical_task_path: str) -> tuple[Path, Path, Path]:
    source = Path(canonical_task_path).resolve()
    if source.parent.name == "tasks":
        backlog_root = source.parent.parent
        destination = source.parent / "done" / source.name
    elif source.parent.name == "pending" and source.parent.parent.name == "bugs":
        backlog_root = source.parent.parent.parent
        destination = source.parent.parent / "done" / source.name
    else:
        raise DeliveryError(f"Unsupported task archive path: {source}")
    return source, destination, backlog_root


def _verify_closeout(started: dict[str, Any]) -> None:
    source, destination, backlog_root = _archive_contract(
        str(started["lease"]["canonical_task_path"])
    )
    if source.exists():
        raise DeliveryError(f"Task was not archived after controller finish: {source}")
    if not destination.is_file():
        raise DeliveryError(f"Archived task is missing after controller finish: {destination}")
    _run(
        [
            sys.executable,
            str(ARCHIVE_HELPER_PATH),
            "check",
            "--backlog",
            str(backlog_root),
        ]
    )


def _is_transient_start_error(detail: str) -> bool:
    lowered = detail.lower()
    return any(marker in lowered for marker in TRANSIENT_START_MARKERS)


def _start(
    task_id: str,
    *,
    session_label: str,
    poll_seconds: int,
    max_wait_minutes: int,
    offline: bool,
) -> dict[str, Any]:
    deadline = time.monotonic() + max_wait_minutes * 60
    command = [
        sys.executable,
        str(CONTROLLER_PATH),
        "--repo",
        str(REPOSITORY_ROOT),
        "start",
        task_id,
        "--owner-launch",
        "--session-label",
        session_label,
    ]
    if offline:
        command.append("--offline")

    while True:
        completed = _run(command, check=False)
        if completed.returncode == 0:
            try:
                return dict(json.loads(completed.stdout))
            except json.JSONDecodeError as error:
                raise DeliveryError("Controller returned invalid start JSON") from error
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown start error"
        if not _is_transient_start_error(detail):
            raise DeliveryError(detail)
        if time.monotonic() >= deadline:
            raise DeliveryError(f"Timed out waiting for coordination state lock: {detail}")
        _event("WAITING_FOR_IMPLEMENTATION_STATE", task_id=task_id, retry_in_seconds=poll_seconds)
        time.sleep(poll_seconds)


def _worker_prompt(task_id: str, started: dict[str, Any]) -> str:
    return (
        f"Выполни только Task {task_id}: {started['lease']['canonical_task_path']}.\n"
        "Один исходный owner launch является standing authorization для normal delivery path: "
        "task branch -> local PRE_PUSH_CI_PASS -> PR master -> exact master CI -> production -> safe closeout.\n"
        "Controller автоматически выполняет idempotent refresh-canonical-master перед start/adopt "
        "и перед refresh-delivery: только verified fast-forward canonical master, с явными "
        "ALIGNED/REFRESHED/WAITING/BLOCKED; canonical checkpoint не заменяет refresh task branch "
        "и не является PRE_PUSH_CI_PASS evidence.\n"
        "Не запрашивай generic approval для commit, push, PR, merge, normal release, deploy "
        "monitoring, finish, cleanup или archive. Внутренние controller stages "
        "выполняй автоматически и сообщай только компактный status или точный terminal blocker.\n"
        "Все BLOCKER/HIGH/MEDIUM должны быть исправлены и пройти required targeted recheck до "
        "release. LOW не расширяет scope. Реальный HUMAN_EVIDENCE, LEGAL, EXTERNAL, DESTRUCTIVE "
        "или task-specific owner gate не подменяй; остановись только на таком точном gate.\n"
        "Обычная executable task без поля concurrency в metadata считается independent-write; "
        "exclusive-write указывай только для реально global/coordination-sensitive изменений.\n"
        "Implementation независимых compatible independent-write tasks может идти параллельно в "
        "отдельных worktree. После review/QA и commit переведи текущую task в READY_FOR_DELIVERY; "
        "если delivery lane занята, используй acquire-delivery и WAITING_FOR_DELIVERY. Это ожидание "
        "не terminal blocker и не должно останавливать implementation или commit. READY_FOR_DELIVERY, "
        "WAITING_FOR_DELIVERY, active CI и production deployment не удерживают implementation exclusion; "
        "только delivery owner сериализует refresh/final gate/PR/merge/deploy.\n"
        "Только один worker владеет delivery lane одновременно. После acquisition выполни "
        "refresh-delivery: fetch latest origin/master, безопасно обнови branch, считай старое "
        "PRE_PUSH_CI_PASS недействительным и выполни validate-delivery с final applicable gate на "
        "новом exact HEAD перед PR/CI/merge. После rebase/conflict resolution выполни только "
        "targeted recheck изменённой поверхности; полный independent review повторяй только при "
        "существенном изменении поведения. Merge master и production deploy строго serial.\n"
        "Не делай commit поверх READY_FOR_DELIVERY: если после readiness нужен review-fix, сначала "
        "освободи delivery ownership через reopen-for-review, затем повтори review/QA и mark-ready.\n"
        "Не запускай следующую product task.\n\n"
        f"Controller context:\n{started.get('prompt', '')}"
    )


def _artifact_root(task_id: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        return ArtifactManager(
            REPOSITORY_ROOT / ".artifacts", repo_root=REPOSITORY_ROOT
        ).allocate_directory(
            task_id,
            "temporary",
            Path("temporary") / "delivery" / f"{stamp}-delivery",
            purpose="one-command task delivery worker output",
            command="scripts/run_task_delivery.py",
            owner="run_task_delivery",
        )
    except ArtifactError as error:
        raise DeliveryError(f"Cannot allocate delivery artifacts: {error}") from error


def _cleanup_delivery_artifacts(task_id: str, artifacts: Path) -> dict[str, Any]:
    manager = ArtifactManager(REPOSITORY_ROOT / ".artifacts", repo_root=REPOSITORY_ROOT)
    task_root = manager.task_root(task_id)
    try:
        relative = artifacts.resolve().relative_to(task_root.resolve())
    except ValueError as error:
        raise DeliveryError(
            f"Delivery artifacts are outside exact task root: {artifacts}"
        ) from error
    if relative.parts[:2] != ("temporary", "delivery"):
        raise DeliveryError(f"Delivery artifacts are outside temporary/delivery: {artifacts}")
    final = artifacts / "final.md"
    if final.exists():
        try:
            if not final.is_file():
                raise DeliveryError(f"Delivery final result is not a regular file: {final}")
            manager.promote_file(
                final,
                task_id,
                Path("evidence") / "delivery" / f"{relative.name}-final.md",
                purpose="terminal one-command delivery result",
                command="scripts/run_task_delivery.py",
                owner="run_task_delivery",
            )
        except ArtifactError as error:
            raise DeliveryError(f"Cannot preserve terminal delivery result: {error}") from error
    try:
        result = manager.cleanup_task(
            task_id,
            terminal_state="finished",
            include_prefixes=(relative.as_posix(),),
        )
    except ArtifactError as error:
        raise DeliveryError(f"Delivery artifact cleanup failed closed: {error}") from error
    if result["status"] not in {"completed", "noop"} or result.get("cleanup_errors"):
        errors = "; ".join(
            f"{item.get('path', relative.as_posix())}: {item.get('reason', 'unknown error')}"
            for item in result.get("cleanup_errors", [])
        )
        raise DeliveryError(
            "Delivery artifact cleanup stopped fail-closed" + (f": {errors}" if errors else "")
        )
    result["delivery_path"] = relative.as_posix()
    return result


def _launch_worker(task_id: str, started: dict[str, Any], artifacts: Path) -> int:
    codex = shutil.which("codex")
    if codex is None:
        raise DeliveryError("Codex CLI is not available in PATH")
    worktree = Path(str(started["lease"]["worktree"]))
    result_path = artifacts / "final.md"
    log_path = artifacts / "events.jsonl"
    with log_path.open("wb") as log:
        completed = subprocess.run(
            [
                codex,
                "exec",
                "--approve-for-me",
                "-s",
                "workspace-write",
                "-C",
                str(worktree),
                "--add-dir",
                str(REPOSITORY_ROOT),
                "--json",
                "-o",
                str(result_path),
                _worker_prompt(task_id, started),
            ],
            cwd=worktree,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return completed.returncode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id")
    parser.add_argument("--session-label")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--max-wait-minutes", type=int, default=1440)
    parser.add_argument("--offline", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        task_id = _normalize_task_id(args.task_id)
        if args.poll_seconds < 10:
            raise DeliveryError("poll-seconds must be at least 10")
        if args.max_wait_minutes < 1:
            raise DeliveryError("max-wait-minutes must be at least 1")
        if shutil.which("codex") is None:
            raise DeliveryError("Codex CLI is not available in PATH")
        session_label = args.session_label or f"delivery-task-{task_id.lower()}"
        started = _start(
            task_id,
            session_label=session_label,
            poll_seconds=args.poll_seconds,
            max_wait_minutes=args.max_wait_minutes,
            offline=args.offline,
        )
        artifacts = _artifact_root(task_id)
        _event(
            "STARTED",
            task_id=task_id,
            branch=started["lease"]["branch"],
            worktree=started["lease"]["worktree"],
            artifacts=str(artifacts),
        )
        worker_exit = _launch_worker(task_id, started, artifacts)
        history = _history(task_id)
        if worker_exit != 0:
            raise DeliveryError(
                f"Worker exited with code {worker_exit}; inspect {artifacts / 'events.jsonl'}"
            )
        if history is None or history.get("state") != "finished":
            state = history.get("state") if history else "missing"
            raise DeliveryError(
                f"Worker returned before terminal controller finish (state={state}); "
                f"inspect {artifacts}"
            )
        _verify_closeout(started)
        delivery_cleanup = _cleanup_delivery_artifacts(task_id, artifacts)
        _event(
            "DONE",
            task_id=task_id,
            merge_sha=history.get("merge_sha"),
            finished_at=history.get("finished_at"),
            artifacts=str(artifacts),
            artifact_cleanup=delivery_cleanup,
        )
        return 0
    except (DeliveryError, OSError) as error:
        _event("BLOCKED", error=str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
