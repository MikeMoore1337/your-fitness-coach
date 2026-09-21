"""Build and validate the immutable Hermes host release manifest."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

RELEASE_SCHEMA_VERSION = "hermes-release-v1"
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
IMAGE_REF_PATTERN = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
JOB_SCHEMA_VERSION = "hermes-editorial-job-v1"
INTAKE_SCHEMA_VERSION = "hermes-editorial-intake-v2"
PROMPT_VERSION = "task403-editorial-worker-v1"
SKILL_VERSION = "yfc-hermes-editorial-v1"
STATE_SCHEMA_VERSION = "hermes-discovery-state-v1"

COMPONENT_PATHS = (
    "deploy/hermes-discovery/discovery_runner.py",
    "deploy/hermes-discovery/hermes_worker_drain.py",
    "deploy/hermes-discovery/hermes_resource_guard.py",
    "deploy/hermes-discovery/hermes_egress.py",
    "deploy/hermes-discovery/hermes_health.py",
    "deploy/hermes-discovery/hermes-discovery-provenance.json",
    "deploy/hermes-editorial-worker/editorial_worker.py",
    "deploy/hermes-editorial-worker/hermes-provenance.json",
    "deploy/hermes-discovery/systemd/hermes-discovery.service.template",
    "deploy/hermes-discovery/systemd/hermes-worker-drain.service.template",
    "deploy/hermes-discovery/systemd/hermes-discovery.timer",
)


class ReleaseManifestError(ValueError):
    """The release identity is incomplete or internally inconsistent."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ReleaseManifestError(f"release component is not a regular file: {path}")
    return sha256_bytes(path.read_bytes())


def validate_image_ref(value: str) -> str:
    if not isinstance(value, str) or IMAGE_REF_PATTERN.fullmatch(value) is None:
        raise ReleaseManifestError("Hermes production images must use registry@sha256 references")
    return value


def _canonical(document: dict[str, Any]) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def build_manifest(
    *,
    source_root: Path,
    source_definitions: Path,
    worker_env_sha256: str,
    yfc_sha: str,
    discovery_image: str,
    worker_image: str,
    mode: str,
    deployment_lock: str,
    release_parent: str | None = None,
) -> dict[str, Any]:
    if FULL_SHA_PATTERN.fullmatch(yfc_sha) is None:
        raise ReleaseManifestError("yfc_sha must be a full lowercase Git SHA")
    if re.fullmatch(r"[0-9a-f]{64}", worker_env_sha256) is None:
        raise ReleaseManifestError("worker_env_sha256 must be a lowercase SHA-256 digest")
    if mode not in {"separate-vm", "colocated-isolated"}:
        raise ReleaseManifestError("Hermes deployment mode is invalid")
    discovery_image = validate_image_ref(discovery_image)
    worker_image = validate_image_ref(worker_image)
    root = source_root.resolve(strict=True)
    components = {relative: sha256_file(root / relative) for relative in COMPONENT_PATHS}
    components["source-definitions.json"] = sha256_file(source_definitions.resolve(strict=True))
    core: dict[str, Any] = {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "yfc_sha": yfc_sha,
        "worker_env_sha256": worker_env_sha256,
        "images": {"discovery": discovery_image, "worker": worker_image},
        "compatibility": {
            "job_schema": JOB_SCHEMA_VERSION,
            "intake_schema": INTAKE_SCHEMA_VERSION,
            "state_schema": STATE_SCHEMA_VERSION,
            "prompt_version": PROMPT_VERSION,
            "skill_version": SKILL_VERSION,
        },
        "components": components,
        "host": {
            "mode": mode,
            "network": "hermes-net",
            "runtime_uid_gid": "10000:10000",
            "public_ports": [],
            "deployment_lock": deployment_lock if mode == "colocated-isolated" else "none",
        },
    }
    release_digest = sha256_bytes(_canonical(core))
    release_id = f"hermes-{yfc_sha[:12]}-{release_digest[:16]}"
    document = {**core, "release_id": release_id, "release_parent": release_parent}
    return {**document, "manifest_sha256": sha256_bytes(_canonical(document))}


def validate_manifest(document: object) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ReleaseManifestError("release manifest must be an object")
    required = {
        "schema_version",
        "release_id",
        "release_parent",
        "manifest_sha256",
        "yfc_sha",
        "worker_env_sha256",
        "images",
        "compatibility",
        "components",
        "host",
    }
    if not required.issubset(document):
        raise ReleaseManifestError("release manifest is incomplete")
    if document.get("schema_version") != RELEASE_SCHEMA_VERSION:
        raise ReleaseManifestError("release manifest schema is unsupported")
    yfc_sha = document.get("yfc_sha")
    if not isinstance(yfc_sha, str) or FULL_SHA_PATTERN.fullmatch(yfc_sha) is None:
        raise ReleaseManifestError("release manifest YFC SHA is invalid")
    worker_env_sha256 = document.get("worker_env_sha256")
    if (
        not isinstance(worker_env_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", worker_env_sha256) is None
    ):
        raise ReleaseManifestError("release manifest worker environment digest is invalid")
    images = document.get("images")
    if not isinstance(images, dict):
        raise ReleaseManifestError("release manifest images are invalid")
    validate_image_ref(images.get("discovery", ""))
    validate_image_ref(images.get("worker", ""))
    compatibility = document.get("compatibility")
    if compatibility != {
        "job_schema": JOB_SCHEMA_VERSION,
        "intake_schema": INTAKE_SCHEMA_VERSION,
        "state_schema": STATE_SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "skill_version": SKILL_VERSION,
    }:
        raise ReleaseManifestError("release compatibility contract is unsupported")
    components = document.get("components")
    if not isinstance(components, dict) or any(
        not isinstance(key, str)
        or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", key)
        or not isinstance(value, str)
        or not re.fullmatch(r"[0-9a-f]{64}", value)
        for key, value in components.items()
    ):
        raise ReleaseManifestError("release component hashes are invalid")
    core = dict(document)
    core.pop("release_id", None)
    core.pop("manifest_sha256", None)
    expected_digest = sha256_bytes(
        _canonical({key: value for key, value in core.items() if key != "release_parent"})
    )
    expected_release_id = f"hermes-{yfc_sha[:12]}-{expected_digest[:16]}"
    if document.get("release_id") != expected_release_id:
        raise ReleaseManifestError("release ID does not match the manifest contents")
    manifest_document = dict(document)
    manifest_document.pop("manifest_sha256", None)
    if document.get("manifest_sha256") != sha256_bytes(_canonical(manifest_document)):
        raise ReleaseManifestError("release manifest digest does not match its contents")
    return document
