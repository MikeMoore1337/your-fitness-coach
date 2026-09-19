"""Bounded post-deploy cleanup for the production host.

The cleanup runs only after the immutable release became current. It deliberately
avoids Docker volumes, database data, recovery evidence and non-standard backup
files. Every destructive target is constrained to a known production directory
and validated before removal.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - production host is Linux.
    fcntl = None

MIB = 1024 * 1024
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
BACKUP_RE = re.compile(r"^fitminiapp-\d{8}T\d{6}Z\.dump$")


class CleanupError(RuntimeError):
    """Raised when cleanup cannot prove that a destructive target is safe."""


@dataclass
class CleanupReport:
    removed_backups: list[str] = field(default_factory=list)
    removed_releases: list[str] = field(default_factory=list)
    removed_staging: list[str] = field(default_factory=list)
    removed_bundles: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    free_before_mb: int = 0
    free_after_mb: int = 0


@contextlib.contextmanager
def _deployment_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is None:
            yield
            return
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CleanupError("another production operation owns the host lock") from exc
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _free_mb(path: Path) -> int:
    return shutil.disk_usage(path).free // MIB


def _is_child(path: Path, root: Path) -> bool:
    return path.is_relative_to(root)


def _validated_current(app_root: Path, target_revision: str) -> tuple[Path, Path]:
    if not REVISION_RE.fullmatch(target_revision):
        raise CleanupError("target revision must be a full lowercase Git SHA")

    releases_entry = app_root / "releases"
    if releases_entry.is_symlink() or not releases_entry.is_dir():
        raise CleanupError(f"releases root is unsafe: {releases_entry}")
    releases_root = releases_entry.resolve(strict=True)
    if not _is_child(releases_root, app_root):
        raise CleanupError(f"releases root escapes application root: {releases_root}")
    current_link = app_root / "current"
    if not current_link.is_symlink():
        raise CleanupError(f"current release pointer is not a symlink: {current_link}")

    current = current_link.resolve(strict=True)
    if not current.is_dir() or not _is_child(current, releases_root):
        raise CleanupError(f"current release escapes releases root: {current}")
    if current.name != target_revision:
        raise CleanupError(
            f"current release {current.name!r} does not match target {target_revision!r}"
        )

    marker = current / ".deployment-sha"
    if not marker.is_file() or marker.is_symlink():
        raise CleanupError(f"current release marker is missing or unsafe: {marker}")
    if marker.read_text(encoding="utf-8").strip() != target_revision:
        raise CleanupError("current release marker does not match target revision")
    return releases_root, current


def _prune_backups(app_root: Path, keep: int, report: CleanupReport) -> None:
    if keep < 1:
        raise CleanupError("backup retention must keep at least one dump")
    backup_root = app_root / ".artifacts" / "operations" / "backups"
    if not backup_root.exists():
        return
    if backup_root.is_symlink() or not backup_root.is_dir():
        raise CleanupError(f"backup root is unsafe: {backup_root}")

    dumps = [
        item
        for item in backup_root.iterdir()
        if item.is_file() and not item.is_symlink() and BACKUP_RE.fullmatch(item.name)
    ]
    dumps.sort(key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True)
    for dump in dumps[keep:]:
        dump.unlink()
        report.removed_backups.append(str(dump))


def _prune_releases(
    releases_root: Path,
    current: Path,
    previous_releases: int,
    report: CleanupReport,
) -> None:
    if previous_releases < 0:
        raise CleanupError("previous release retention cannot be negative")

    releases: list[Path] = []
    for item in releases_root.iterdir():
        if item.is_symlink() or not item.is_dir() or not REVISION_RE.fullmatch(item.name):
            continue
        marker = item / ".deployment-sha"
        if not marker.is_file() or marker.is_symlink():
            report.warnings.append(f"preserving release without safe marker: {item}")
            continue
        if marker.read_text(encoding="utf-8").strip() != item.name:
            report.warnings.append(f"preserving release with mismatched marker: {item}")
            continue
        releases.append(item)

    previous = [item for item in releases if item != current]
    previous.sort(key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True)
    preserved = {current, *previous[:previous_releases]}
    for release in releases:
        if release in preserved:
            continue
        shutil.rmtree(release)
        report.removed_releases.append(str(release))


def _prune_staging(releases_root: Path, report: CleanupReport, *, stale_before: float) -> None:
    for item in releases_root.iterdir():
        if not item.name.startswith(".staging-"):
            continue
        if item.is_symlink():
            report.warnings.append(f"preserving staging symlink: {item}")
            continue
        if not item.is_dir():
            report.warnings.append(f"preserving unexpected staging entry: {item}")
            continue
        if item.stat().st_mtime > stale_before:
            report.warnings.append(f"preserving recent staging directory: {item}")
            continue
        shutil.rmtree(item)
        report.removed_staging.append(str(item))


def _prune_bundles(tmp_root: Path, report: CleanupReport, *, stale_before: float) -> None:
    if tmp_root.is_symlink() or not tmp_root.is_dir():
        raise CleanupError(f"temporary bundle root is unsafe: {tmp_root}")
    for item in tmp_root.glob("yfc-deploy-*.tar.gz"):
        if not item.is_file() or item.is_symlink():
            report.warnings.append(f"preserving unsafe temporary bundle entry: {item}")
            continue
        if item.stat().st_mtime > stale_before:
            continue
        item.unlink()
        report.removed_bundles.append(str(item))


def _docker_prune(report: CleanupReport) -> None:
    commands = (
        ["docker", "image", "prune", "--all", "--force"],
        ["docker", "builder", "prune", "--all", "--force"],
    )
    for command in commands:
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            report.warnings.append(
                f"Docker cleanup failed ({result.returncode}): {' '.join(command)}"
            )


def cleanup(
    *,
    app_root: Path,
    target_revision: str,
    backup_keep: int,
    previous_releases: int,
    tmp_root: Path,
    warning_free_mb: int,
    stale_ttl_hours: int,
    docker_prune: bool,
) -> CleanupReport:
    if app_root.is_symlink():
        raise CleanupError(f"application root must not be a symlink: {app_root}")
    app_root = app_root.resolve(strict=True)
    if not app_root.is_dir():
        raise CleanupError(f"application root is unsafe: {app_root}")

    if tmp_root.is_symlink():
        raise CleanupError(f"temporary bundle root must not be a symlink: {tmp_root}")
    tmp_root = tmp_root.resolve(strict=True)

    if stale_ttl_hours < 1:
        raise CleanupError("stale retention must be at least one hour")

    lock_path = app_root / ".artifacts" / "operations" / "deployments" / "deployment.lock"
    with _deployment_lock(lock_path):
        releases_root, current = _validated_current(app_root, target_revision)
        report = CleanupReport(free_before_mb=_free_mb(app_root))
        stale_before = time.time() - stale_ttl_hours * 60 * 60

        _prune_backups(app_root, backup_keep, report)
        _prune_releases(releases_root, current, previous_releases, report)
        _prune_staging(releases_root, report, stale_before=stale_before)
        _prune_bundles(tmp_root, report, stale_before=stale_before)
        if docker_prune:
            _docker_prune(report)

        report.free_after_mb = _free_mb(app_root)
    if report.free_after_mb < warning_free_mb:
        report.warnings.append(
            f"production free disk is {report.free_after_mb} MiB, below warning threshold "
            f"{warning_free_mb} MiB"
        )
    return report


def _print_report(report: CleanupReport) -> None:
    print("Production host cleanup completed")
    print(f"free_disk_mb: {report.free_before_mb} -> {report.free_after_mb}")
    print(f"removed_backups: {len(report.removed_backups)}")
    print(f"removed_releases: {len(report.removed_releases)}")
    print(f"removed_staging: {len(report.removed_staging)}")
    print(f"removed_bundles: {len(report.removed_bundles)}")
    for warning in report.warnings:
        print(f"WARNING: {warning}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target_revision")
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--backup-keep", type=int, default=5)
    parser.add_argument("--previous-releases", type=int, default=2)
    parser.add_argument("--tmp-root", type=Path, default=Path("/tmp"))
    parser.add_argument("--warning-free-mb", type=int, default=3072)
    parser.add_argument("--stale-ttl-hours", type=int, default=24)
    parser.add_argument("--docker-prune", action="store_true")
    args = parser.parse_args()

    try:
        report = cleanup(
            app_root=args.app_root,
            target_revision=args.target_revision,
            backup_keep=args.backup_keep,
            previous_releases=args.previous_releases,
            tmp_root=args.tmp_root,
            warning_free_mb=args.warning_free_mb,
            stale_ttl_hours=args.stale_ttl_hours,
            docker_prune=args.docker_prune,
        )
    except (CleanupError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
