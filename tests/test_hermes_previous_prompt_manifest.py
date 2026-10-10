"""Регрессия криптографической проверки предыдущих Hermes release manifests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"


def _module(filename: str, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = _module("hermes_release.py", "hermes_release")
host = _module("hermes_colocation.py", "hermes_colocation")


def _signed_manifest(
    *,
    prompt: str,
    intake: str = release.INTAKE_SCHEMA_VERSION,
    parent: str | None = None,
) -> dict[str, Any]:
    core: dict[str, Any] = {
        "schema_version": release.RELEASE_SCHEMA_VERSION,
        "yfc_sha": "a" * 40,
        "worker_env_sha256": "b" * 64,
        "images": {
            "discovery": "registry.invalid/hermes-discovery@sha256:" + "c" * 64,
            "worker": "registry.invalid/hermes-worker@sha256:" + "d" * 64,
        },
        "compatibility": {
            "job_schema": release.JOB_SCHEMA_VERSION,
            "intake_schema": intake,
            "state_schema": release.STATE_SCHEMA_VERSION,
            "prompt_version": prompt,
            "skill_version": release.SKILL_VERSION,
        },
        "components": {"deploy/hermes-editorial-worker/editorial_worker.py": "e" * 64},
        "host": {"mode": "separate-vm", "network": "hermes-net"},
    }
    canonical = lambda obj: json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(canonical(core)).hexdigest()
    document = {
        **core,
        "release_id": f"hermes-{'a' * 12}-{digest[:16]}",
        "release_parent": parent,
    }
    document["manifest_sha256"] = hashlib.sha256(canonical(document)).hexdigest()
    return document


@pytest.mark.parametrize(
    "previous",
    ["task403-editorial-worker-v1", "task403-editorial-worker-v2-human-writing"],
)
def test_known_previous_prompt_is_accepted_only_as_predecessor(previous: str) -> None:
    manifest = _signed_manifest(prompt=previous)
    with pytest.raises(release.ReleaseManifestError, match="compatibility"):
        release.validate_manifest(manifest)
    assert release.validate_manifest(manifest, allow_previous_prompt_version=True) == manifest


def test_new_manifest_remains_strict_and_accepts_current_prompt() -> None:
    manifest = _signed_manifest(prompt=release.PROMPT_VERSION)
    assert release.validate_manifest(manifest) == manifest


@pytest.mark.parametrize(
    ("prompt", "intake"),
    [
        ("unknown-prompt-v100", release.INTAKE_SCHEMA_VERSION),
        ("task403-editorial-worker-v1", "wrong-intake-v0"),
    ],
)
def test_predecessor_rejects_unknown_or_incompatible_contract(prompt: str, intake: str) -> None:
    manifest = _signed_manifest(prompt=prompt, intake=intake)
    with pytest.raises(release.ReleaseManifestError, match="compatibility"):
        release.validate_manifest(manifest, allow_previous_prompt_version=True)


def test_predecessor_rejects_tampering_without_valid_manifest_digest() -> None:
    manifest = _signed_manifest(prompt="task403-editorial-worker-v1")
    manifest["components"]["deploy/hermes-editorial-worker/editorial_worker.py"] = "f" * 64
    with pytest.raises(release.ReleaseManifestError, match="release ID|digest"):
        release.validate_manifest(manifest, allow_previous_prompt_version=True)


def test_installer_reads_cryptographically_valid_previous_release(tmp_path: Path) -> None:
    manifest = _signed_manifest(prompt="task403-editorial-worker-v1")
    parent = tmp_path / "releases" / manifest["release_id"]
    parent.mkdir(parents=True)
    (parent / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "current").symlink_to(parent, target_is_directory=True)

    assert host._current_manifest(tmp_path) == manifest


def test_rollback_accepts_only_validated_previous_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_manifest = _signed_manifest(prompt="task403-editorial-worker-v1")
    parent = tmp_path / "releases" / parent_manifest["release_id"]
    parent.mkdir(parents=True)
    (parent / "manifest.json").write_text(json.dumps(parent_manifest), encoding="utf-8")

    current_manifest = _signed_manifest(
        prompt=release.PROMPT_VERSION, parent=parent_manifest["release_id"]
    )
    current = tmp_path / "releases" / current_manifest["release_id"]
    current.mkdir(parents=True)
    (current / "manifest.json").write_text(json.dumps(current_manifest), encoding="utf-8")
    (tmp_path / "current").symlink_to(current, target_is_directory=True)

    switched: list[Path] = []

    def record_switch(**kwargs: Any) -> None:
        switched.append(kwargs["release_dir"])

    monkeypatch.setattr(host, "_switch_release_links", record_switch)
    args = host._parser().parse_args(["rollback", "--runtime-root", str(tmp_path)])
    result = host.rollback(args)
    assert switched == [parent]
    assert result["release_id"] == parent_manifest["release_id"]
    assert result["timer_enabled"] is False
