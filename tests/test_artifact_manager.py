from __future__ import annotations

import importlib.util
import json
import os
import struct
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest


def _load_module():
    script = Path(__file__).parents[1] / "scripts" / "artifact_manager.py"
    spec = importlib.util.spec_from_file_location("artifact_manager", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


artifact_manager = _load_module()


def _manager(tmp_path: Path):
    return artifact_manager.ArtifactManager(tmp_path / ".artifacts")


def _create_windows_junction_or_skip(link: Path, target: Path) -> None:
    command = f'mklink /J "{link}" "{target}"'
    created = subprocess.run(
        ["cmd.exe", "/d", "/c", command], capture_output=True, text=True, check=False
    )
    if created.returncode:
        ps_path = str(link).replace("'", "''")
        ps_target = str(target).replace("'", "''")
        created = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"New-Item -ItemType Junction -Path '{ps_path}' -Target '{ps_target}' | Out-Null",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    if created.returncode:
        pytest.skip(f"junction creation unavailable: {created.stderr or created.stdout}")


def test_safe_relative_rejects_traversal_and_reparse_points(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.ensure_layout("133")
    with pytest.raises(artifact_manager.ArtifactSafetyError):
        artifact_manager._safe_relative(manager.root, "../outside.txt")

    outside = tmp_path / "outside"
    outside.mkdir()
    link = manager.root / "runtime" / "link"
    if os.name == "nt":
        _create_windows_junction_or_skip(link, outside)
    else:
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            pytest.skip(f"symlink creation unavailable: {error}")
    with pytest.raises(artifact_manager.ArtifactSafetyError, match="Reparse point"):
        artifact_manager._safe_relative(manager.root, "runtime/link/file.txt")


def test_allocate_writes_task_manifest_and_rejects_wrong_task_class(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    target = manager.allocate_directory(
        "133",
        "temporary",
        "temporary/run-1",
        purpose="test output",
        command="pytest",
        owner="test",
    )
    assert target.is_dir()
    manifest = json.loads(
        (manager.root / "tasks" / "133" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["task_id"] == "133"
    assert manifest["entries"][0]["classification"] == "temporary"
    assert manager.validate(task_id="133")["ok"]
    with pytest.raises(artifact_manager.ArtifactError, match="must begin"):
        manager.allocate(
            "133",
            "evidence",
            "temporary/wrong-class",
            purpose="bad",
            command="test",
        )


def test_cli_allocate_records_provenance_command(tmp_path: Path, capsys) -> None:
    root = tmp_path / ".artifacts"

    exit_code = artifact_manager.main(
        [
            "--root",
            str(root),
            "allocate",
            "133",
            "temporary",
            "temporary/cli-run",
            "--purpose",
            "CLI test",
            "--command",
            "pytest -q",
            "--directory",
        ]
    )

    assert exit_code == 0
    assert "cli-run" in capsys.readouterr().out
    manifest = json.loads((root / "tasks" / "133" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["entries"][0]["command"] == "pytest -q"


def test_cleanup_task_is_exact_idempotent_and_preserves_evidence(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    temporary = manager.allocate_directory(
        "133",
        "temporary",
        "temporary/run-1",
        purpose="test output",
        command="pytest",
    )
    (temporary / "generated.txt").write_text("reproducible\n", encoding="utf-8")
    evidence = manager.allocate(
        "133",
        "evidence",
        "evidence/selected.json",
        purpose="selected evidence",
        command="pytest",
    )
    evidence.write_text("keep\n", encoding="utf-8")

    result = manager.cleanup_task("133", terminal_state="finished")
    assert result["status"] == "completed"
    assert result["removed_count"] == 1
    assert not (temporary / "generated.txt").exists()
    assert evidence.exists()
    second = manager.cleanup_task("133", terminal_state="finished")
    assert second["status"] == "completed"
    assert second["removed_count"] == 0


def test_cleanup_task_blocks_non_terminal_target_lease(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
    )
    state = tmp_path / "state"
    (state / "leases").mkdir(parents=True)
    (state / "leases" / "task-133.json").write_text(
        json.dumps({"task_id": "133", "mode": "write", "lifecycle_state": "implementation"}),
        encoding="utf-8",
    )
    manager.controller_state_dir = state
    target = manager.allocate_directory(
        "133",
        "temporary",
        "temporary/run",
        purpose="active output",
        command="test",
    )
    (target / "open.txt").write_text("keep\n", encoding="utf-8")
    result = manager.cleanup_task("133", terminal_state="finished")
    assert result["status"] == "blocked"
    assert (target / "open.txt").exists()
    assert result["cleanup_errors"]
    assert result["preserved"] == ["tasks/133/temporary/run/open.txt"]


def test_cleanup_task_allows_production_success_target_lease(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    state = tmp_path / "state"
    (state / "leases").mkdir(parents=True)
    (state / "leases" / "task-133.json").write_text(
        json.dumps({"task_id": "133", "mode": "write", "lifecycle_state": "production-success"}),
        encoding="utf-8",
    )
    manager.controller_state_dir = state
    target = manager.allocate_directory(
        "133",
        "temporary",
        "temporary/run",
        purpose="terminal closeout output",
        command="test",
    )
    artifact = target / "closeout.txt"
    artifact.write_text("remove after production success\n", encoding="utf-8")

    result = manager.cleanup_task("133", terminal_state="finished")

    assert result["status"] == "completed"
    assert result["removed_count"] == 1
    assert not artifact.exists()


def test_shared_cleanup_blocks_parallel_lease_and_unfinished_task_132(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    state = tmp_path / "state"
    (state / "leases").mkdir(parents=True)
    (state / "history").mkdir()
    (state / "leases" / "task-134.json").write_text(
        json.dumps({"task_id": "134", "mode": "write", "lifecycle_state": "implementation"}),
        encoding="utf-8",
    )
    (state / "history" / "task-132.json").write_text(
        json.dumps({"state": "integration"}), encoding="utf-8"
    )
    manager.controller_state_dir = state
    runtime = manager.root / "runtime" / "cache"
    runtime.mkdir(parents=True, exist_ok=True)
    target = runtime / "cache.bin"
    target.write_bytes(b"cache")

    plan = manager.dry_run()

    assert plan["summary"]["counts"]["DELETE"] == 0
    assert any("active task leases" in issue for issue in plan["safety"]["issues"])
    assert any("Task 132" in issue for issue in plan["safety"]["issues"])
    with pytest.raises(artifact_manager.ArtifactSafetyError, match="Cleanup blocked"):
        manager.apply_plan(plan, approved_plan_sha256=plan["plan_sha256"])


def test_dry_run_apply_requires_exact_unchanged_plan_and_is_idempotent(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    runtime = manager.root / "cache"
    runtime.mkdir(parents=True)
    target = runtime / "cache.bin"
    target.write_bytes(b"cache")
    plan = manager.dry_run()
    assert plan["plan_sha256"]
    with pytest.raises(artifact_manager.ArtifactSafetyError, match="owner-approved"):
        manager.apply_plan(plan, approved_plan_sha256=None)
    changed = target.with_name("cache-changed.bin")
    target.replace(changed)
    with pytest.raises(artifact_manager.ArtifactSafetyError, match="drift"):
        manager.apply_plan(plan, approved_plan_sha256=plan["plan_sha256"])

    fresh = manager.dry_run()
    result = manager.apply_plan(fresh, approved_plan_sha256=fresh["plan_sha256"])
    assert result["status"] == "completed"
    assert not changed.exists()
    repeat = manager.apply_plan(fresh, approved_plan_sha256=fresh["plan_sha256"])
    assert repeat["status"] == "completed"


def test_validate_detects_new_top_level_and_source_path(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    (manager.root / "new-ad-hoc").mkdir(parents=True)
    manager.repo_root.mkdir(parents=True, exist_ok=True)
    scripts = manager.repo_root / "scripts"
    scripts.mkdir()
    (scripts / "producer.py").write_text(
        "OUTPUT = '.artifacts/' + 'new-ad-hoc/output.json'\n", encoding="utf-8"
    )
    result = manager.validate()
    assert not result["ok"]
    assert any("new-ad-hoc" in error for error in result["errors"])


def test_runtime_cleanup_is_bounded_and_requires_plan_hash(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    old = manager.root / "runtime" / "cache"
    old.mkdir(parents=True)
    target = old / "old.bin"
    target.write_bytes(b"old")
    timestamp = target.stat().st_mtime - 10_000
    os.utime(target, (timestamp, timestamp))
    plan = manager.cleanup_runtime(ttl=timedelta(seconds=1), max_entries=1, max_bytes=10)
    assert plan["summary"]["counts"]["DELETE"] == 1
    with pytest.raises(artifact_manager.ArtifactSafetyError):
        manager.cleanup_runtime(
            ttl=timedelta(seconds=1),
            max_entries=1,
            max_bytes=10,
            apply=True,
            approved_plan_sha256="wrong",
        )
    result = manager.cleanup_runtime(
        ttl=timedelta(seconds=1),
        max_entries=1,
        max_bytes=10,
        apply=True,
        approved_plan_sha256=plan["plan_sha256"],
    )
    assert result["status"] == "completed"


def test_ensure_layout_refuses_canonical_reparse_point(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = manager.root / "runtime"
    if os.name == "nt":
        _create_windows_junction_or_skip(link, outside)
    else:
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(artifact_manager.ArtifactSafetyError, match="Reparse point"):
        manager.ensure_layout()


def test_artifact_manager_refuses_reparse_artifact_root(tmp_path: Path) -> None:
    root = tmp_path / ".artifacts"
    target = tmp_path / "outside-root"
    target.mkdir()
    if os.name == "nt":
        _create_windows_junction_or_skip(root, target)
    else:
        try:
            root.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(artifact_manager.ArtifactSafetyError, match="Artifact root"):
        artifact_manager.ArtifactManager(root)


def test_manifest_validation_rejects_unregistered_durable_artifact(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.ensure_layout("133")
    durable = manager.root / "tasks" / "133" / "evidence" / "unregistered.json"
    durable.write_text("{}\n", encoding="utf-8")

    result = manager.validate(task_id="133")

    assert not result["ok"]
    assert any("unregistered.json" in error for error in result["errors"])


def test_audit_keeps_worktrees_and_operations_protected(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.ensure_layout()
    worktree_file = manager.root / "worktrees" / "registered" / "file.bin"
    backup_file = manager.root / "operations" / "backups" / "database.dump"
    worktree_file.parent.mkdir(parents=True)
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    worktree_file.write_bytes(b"worktree")
    backup_file.write_bytes(b"backup")

    entries = manager.audit()["entries"]

    by_path = {entry["path"]: entry for entry in entries}
    assert by_path["worktrees/registered/file.bin"]["disposition"] == "KEEP"
    assert by_path["operations/backups/database.dump"]["disposition"] == "KEEP"


def test_cleanup_task_counts_only_selected_scope(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    worker = manager.allocate_directory(
        "133",
        "temporary",
        "temporary/worker",
        purpose="worker output",
        command="test",
    )
    delivery = manager.allocate_directory(
        "133",
        "temporary",
        "temporary/delivery",
        purpose="delivery output",
        command="test",
    )
    worker_file = worker / "worker.bin"
    delivery_file = delivery / "delivery.bin"
    worker_file.write_bytes(b"worker")
    delivery_file.write_bytes(b"delivery")

    result = manager.cleanup_task(
        "133", terminal_state="finished", exclude_prefixes=("temporary/delivery",)
    )

    assert result["status"] == "completed"
    assert result["removed_bytes"] == len(b"worker")
    assert delivery_file.exists()


def test_cleanup_task_stops_on_target_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path)
    temporary = manager.allocate_directory(
        "133",
        "temporary",
        "temporary/worker",
        purpose="worker output",
        command="test",
    )
    target = temporary / "generated.bin"
    target.write_bytes(b"original")
    original_fingerprint = artifact_manager._file_fingerprint

    def change_before_fingerprint(path: Path) -> dict[str, object]:
        if path == target:
            target.write_bytes(b"changed")
        return original_fingerprint(path)

    monkeypatch.setattr(artifact_manager, "_file_fingerprint", change_before_fingerprint)
    drift = manager.cleanup_task("133", terminal_state="finished")
    assert drift["status"] == "partial-failure"
    assert drift["cleanup_errors"]
    assert target.exists()


def _create_symlink_or_simulate(
    link: Path,
    target_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[bool, list[str]]:
    try:
        link.symlink_to(target_text)
        return True, [target_text]
    except OSError, NotImplementedError:
        link.write_text("simulated reparse entry\n", encoding="utf-8")
        target_ref = [target_text]
        original_iter_entries = artifact_manager._iter_entries

        def iter_entries(root: Path):
            for item in original_iter_entries(root):
                if item["path"] == link:
                    yield {**item, "kind": "reparse"}
                else:
                    yield item

        def reparse_fingerprint(path: Path, temporary_root: Path) -> dict[str, object]:
            if path != link:
                raise artifact_manager.ArtifactSafetyError("unexpected fake reparse path")
            metadata = path.lstat()
            _target, relative, target_kind = artifact_manager._contained_temporary_target(
                temporary_root, path, target_ref[0]
            )
            return {
                "kind": "reparse",
                "device": int(metadata.st_dev),
                "inode": int(metadata.st_ino),
                "mode": int(metadata.st_mode),
                "size_bytes": int(metadata.st_size),
                "mtime_ns": int(metadata.st_mtime_ns),
                "ctime_ns": int(metadata.st_ctime_ns),
                "attributes": artifact_manager.FILE_ATTRIBUTE_REPARSE_POINT,
                "directory_entry": False,
                "target": target_ref[0],
                "target_relative": relative.as_posix(),
                "target_kind": target_kind,
                "containment": "task-temporary",
            }

        monkeypatch.setattr(artifact_manager, "_iter_entries", iter_entries)
        monkeypatch.setattr(artifact_manager, "_reparse_fingerprint", reparse_fingerprint)
        return False, target_ref


def test_cleanup_task_removes_only_contained_relative_symlink_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path)
    manager.ensure_layout("133")
    temporary = manager.root / "tasks" / "133" / "temporary"
    target = temporary / "target" / "payload.txt"
    target.parent.mkdir()
    target.write_text("keep target contents\n", encoding="utf-8")
    link = temporary / "links" / "payload-link"
    link.parent.mkdir()
    _native_symlink, _target_ref = _create_symlink_or_simulate(
        link,
        os.path.relpath(target, link.parent),
        monkeypatch,
    )
    ordinary = temporary / "ordinary.txt"
    ordinary.write_text("remove ordinary file\n", encoding="utf-8")

    result = manager.cleanup_task(
        "133", terminal_state="finished", exclude_prefixes=("temporary/target",)
    )

    assert result["status"] == "completed"
    assert result["removed_count"] == 2
    assert result["removed_reparse_count"] == 1
    assert not os.path.lexists(link)
    assert not ordinary.exists()
    assert target.read_text(encoding="utf-8") == "keep target contents\n"
    second = manager.cleanup_task(
        "133", terminal_state="finished", exclude_prefixes=("temporary/target",)
    )
    assert second["status"] == "completed"
    assert second["removed_count"] == 0
    assert second["removed_reparse_count"] == 0


@pytest.mark.parametrize("target_area", ["outside", "other-task", "runtime", "evidence", "source"])
def test_cleanup_task_blocks_reparse_targets_outside_exact_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target_area: str
) -> None:
    manager = _manager(tmp_path)
    manager.ensure_layout("133")
    temporary = manager.root / "tasks" / "133" / "temporary"
    target_roots = {
        "outside": tmp_path / "outside",
        "other-task": manager.root / "tasks" / "134" / "temporary",
        "runtime": manager.root / "runtime" / "cache",
        "evidence": manager.root / "tasks" / "133" / "evidence",
        "source": tmp_path / "backend",
    }
    target = target_roots[target_area] / "target.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("must not be reached\n", encoding="utf-8")
    link = temporary / "z-link"
    _create_symlink_or_simulate(link, str(target), monkeypatch)
    ordinary = temporary / "a-ordinary.txt"
    ordinary.write_text("blocked with unsafe link\n", encoding="utf-8")

    result = manager.cleanup_task("133", terminal_state="finished")

    assert result["status"] == "blocked"
    assert result["cleanup_errors"]
    assert os.path.lexists(link)
    assert ordinary.exists()
    assert target.read_text(encoding="utf-8") == "must not be reached\n"


@pytest.mark.parametrize("target_text", ["", "../../outside", "../../../runtime/cache"])
def test_contained_temporary_target_rejects_ambiguous_or_escaping_target(
    tmp_path: Path, target_text: str
) -> None:
    manager = _manager(tmp_path)
    manager.ensure_layout("133")
    temporary = manager.root / "tasks" / "133" / "temporary"
    with pytest.raises(artifact_manager.ArtifactSafetyError):
        artifact_manager._contained_temporary_target(
            temporary, temporary / "nested" / "candidate", target_text
        )


def test_contained_temporary_target_accepts_relative_target_in_same_tree(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path)
    manager.ensure_layout("133")
    temporary = manager.root / "tasks" / "133" / "temporary"
    target = temporary / "target" / "payload.txt"
    target.parent.mkdir()
    target.write_text("preserved\n", encoding="utf-8")

    resolved, relative, kind = artifact_manager._contained_temporary_target(
        temporary, temporary / "links" / "payload-link", "../target/payload.txt"
    )

    assert resolved == target
    assert relative == Path("target") / "payload.txt"
    assert kind == "file"


def test_cleanup_task_blocks_unreadable_reparse_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path)
    manager.ensure_layout("133")
    temporary = manager.root / "tasks" / "133" / "temporary"
    target = temporary / "target.txt"
    target.write_text("preserved\n", encoding="utf-8")
    link = temporary / "z-link"
    native_symlink, _target_ref = _create_symlink_or_simulate(link, "target.txt", monkeypatch)
    later_file = temporary / "a-later.txt"
    later_file.write_text("preserved after inventory refusal\n", encoding="utf-8")
    if native_symlink:

        def unreadable(_path: Path) -> str:
            raise artifact_manager.ArtifactSafetyError("target cannot be inspected")

        monkeypatch.setattr(artifact_manager, "_read_reparse_target", unreadable)
    else:

        def unreadable(_path: Path, _root: Path) -> dict[str, object]:
            raise artifact_manager.ArtifactSafetyError("target cannot be inspected")

        monkeypatch.setattr(artifact_manager, "_reparse_fingerprint", unreadable)

    result = manager.cleanup_task("133", terminal_state="finished")

    assert result["status"] == "blocked"
    assert result["cleanup_errors"]
    assert os.path.lexists(link)
    assert later_file.exists()
    assert target.read_text(encoding="utf-8") == "preserved\n"


def test_cleanup_task_blocks_inaccessible_parent_of_selected_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path)
    manager.ensure_layout("133")
    temporary = manager.root / "tasks" / "133" / "temporary"
    monkeypatch.setattr(
        artifact_manager,
        "_iter_entries",
        lambda _root: iter(
            [
                {
                    "path": temporary / "worker",
                    "relative": Path("worker"),
                    "kind": "inaccessible",
                    "error": "access denied",
                }
            ]
        ),
    )

    result = manager.cleanup_task(
        "133",
        terminal_state="finished",
        include_prefixes=("temporary/worker/generated",),
    )

    assert result["status"] == "blocked"
    assert result["cleanup_errors"]


def test_lx_symlink_reparse_parser_checks_version_and_target() -> None:
    target = b"../target/file.txt"
    data = (
        struct.pack(
            "<IHHI",
            artifact_manager.WINDOWS_LX_SYMLINK_TAG,
            len(target) + 4,
            0,
            artifact_manager.WINDOWS_LX_SYMLINK_VERSION,
        )
        + target
    )

    assert artifact_manager._decode_lx_symlink_reparse_data(data) == target.decode()
    with pytest.raises(artifact_manager.ArtifactSafetyError, match="version"):
        artifact_manager._decode_lx_symlink_reparse_data(data[:8] + struct.pack("<I", 1) + target)


@pytest.mark.skipif(os.name != "nt", reason="Windows directory junction behavior")
def test_cleanup_task_removes_contained_junction_entry_only(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.ensure_layout("133")
    temporary = manager.root / "tasks" / "133" / "temporary"
    target = temporary / "junction-target"
    target.mkdir()
    payload = target / "keep.txt"
    payload.write_text("keep through junction removal\n", encoding="utf-8")
    junction = temporary / "z-junction"
    _create_windows_junction_or_skip(junction, target)

    with pytest.raises(artifact_manager.ArtifactSafetyError):
        artifact_manager._contained_temporary_target(
            temporary, temporary / "candidate", "z-junction/keep.txt"
        )
    with pytest.raises(artifact_manager.ArtifactSafetyError, match="Reparse point"):
        artifact_manager._safe_relative(
            manager.root, Path("tasks/133/temporary/z-junction/keep.txt")
        )

    result = manager.cleanup_task(
        "133", terminal_state="finished", exclude_prefixes=("temporary/junction-target",)
    )

    assert result["status"] == "completed"
    assert result["removed_reparse_count"] == 1
    assert not junction.exists()
    assert payload.read_text(encoding="utf-8") == "keep through junction removal\n"


@pytest.mark.parametrize("replacement", ["different-target", "regular-file"])
def test_cleanup_task_stops_when_reparse_entry_changes_after_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replacement: str
) -> None:
    manager = _manager(tmp_path)
    manager.ensure_layout("133")
    temporary = manager.root / "tasks" / "133" / "temporary"
    original_target = temporary / "target-a.txt"
    changed_target = temporary / "target-b.txt"
    original_target.write_text("target a\n", encoding="utf-8")
    changed_target.write_text("target b\n", encoding="utf-8")
    link = temporary / "z-link"
    native_symlink, target_ref = _create_symlink_or_simulate(link, "target-a.txt", monkeypatch)
    later_file = temporary / "a-later.txt"
    later_file.write_text("must remain after failure\n", encoding="utf-8")
    calls = 0
    if native_symlink:
        read_target = artifact_manager._read_reparse_target

        def change_entry(path: Path) -> str:
            nonlocal calls
            calls += 1
            if path == link and calls == 2:
                path.unlink()
                if replacement == "regular-file":
                    path.write_text("replacement\n", encoding="utf-8")
                else:
                    path.symlink_to(Path("target-b.txt"))
            return read_target(path)

        monkeypatch.setattr(artifact_manager, "_read_reparse_target", change_entry)
    else:
        reparse_fingerprint = artifact_manager._reparse_fingerprint

        def change_fake_entry(path: Path, temporary_root: Path) -> dict[str, object]:
            nonlocal calls
            calls += 1
            if path == link and calls == 2:
                if replacement == "regular-file":
                    path.write_text("replacement\n", encoding="utf-8")
                    raise artifact_manager.ArtifactSafetyError(
                        "Task cleanup entry is no longer a reparse point"
                    )
                target_ref[0] = "target-b.txt"
                path.write_text("changed simulated reparse entry\n", encoding="utf-8")
            return reparse_fingerprint(path, temporary_root)

        monkeypatch.setattr(artifact_manager, "_reparse_fingerprint", change_fake_entry)

    result = manager.cleanup_task("133", terminal_state="finished")

    assert result["status"] == "partial-failure"
    assert result["cleanup_errors"]
    assert later_file.exists()
    assert changed_target.read_text(encoding="utf-8") == "target b\n"
    if replacement == "regular-file":
        assert link.read_text(encoding="utf-8") == "replacement\n"
    elif native_symlink:
        assert link.is_symlink()


def test_runtime_cleanup_applies_the_saved_exact_plan(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    target = manager.root / "runtime" / "cache" / "old.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"old")
    old_timestamp = target.stat().st_mtime - 10_000
    os.utime(target, (old_timestamp, old_timestamp))

    plan = manager.cleanup_runtime(ttl=timedelta(seconds=1), max_entries=1, max_bytes=10)
    result = manager.cleanup_runtime(
        ttl=timedelta(seconds=1),
        max_entries=1,
        max_bytes=10,
        apply=True,
        approved_plan_sha256=plan["plan_sha256"],
        plan=plan,
    )

    assert result["status"] == "completed"
    assert not target.exists()
