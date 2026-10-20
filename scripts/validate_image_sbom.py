"""Validate image SBOM documents and write their immutable provenance sidecar."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
ARCHITECTURE_RE = re.compile(r"^linux/[a-z0-9_./-]+$")
SECRET_FIELD_RE = re.compile(
    r'"[^"\n]*(?:token|secret|password|api[_-]?key|private[_-]?key|database[_-]?url)'
    r'[^"\n]*"\s*:\s*"[^"\n]+"',
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"(?:ghp_|github_pat_|glpat-|xox[baprs]-|sk-[A-Za-z0-9]{20,})[A-Za-z0-9._-]*"
    r"|-----BEGIN [A-Z ]+PRIVATE KEY-----",
    re.IGNORECASE,
)


class ImageSbomValidationError(ValueError):
    """The generated SBOM or its provenance contract is invalid."""


def _read_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    if not raw.strip():
        raise ImageSbomValidationError(f"SBOM is empty: {path}")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ImageSbomValidationError(f"SBOM is not valid JSON: {path}") from error
    if not isinstance(document, dict) or not document:
        raise ImageSbomValidationError(f"SBOM root must be a non-empty JSON object: {path}")
    text = raw.decode("utf-8")
    if SECRET_FIELD_RE.search(text) or SECRET_VALUE_RE.search(text):
        raise ImageSbomValidationError(f"SBOM contains a secret-shaped field or value: {path}")
    return raw, document


def _validate_cyclonedx(document: dict[str, Any], path: Path) -> None:
    if document.get("bomFormat") != "CycloneDX":
        raise ImageSbomValidationError(f"not a CycloneDX document: {path}")
    spec_version = document.get("specVersion")
    if not isinstance(spec_version, str) or not re.fullmatch(r"1\.\d+", spec_version):
        raise ImageSbomValidationError(f"CycloneDX specVersion is invalid: {path}")
    components = document.get("components")
    if not isinstance(components, list) or not components:
        raise ImageSbomValidationError(f"CycloneDX components are empty: {path}")
    metadata = document.get("metadata")
    if not isinstance(metadata, dict) or not metadata:
        raise ImageSbomValidationError(f"CycloneDX metadata is missing: {path}")


def _validate_spdx(document: dict[str, Any], path: Path) -> None:
    spdx_version = document.get("spdxVersion")
    if not isinstance(spdx_version, str) or not spdx_version.startswith("SPDX-"):
        raise ImageSbomValidationError(f"SPDX version is invalid: {path}")
    for field in ("SPDXID", "name", "documentNamespace", "creationInfo"):
        if not document.get(field):
            raise ImageSbomValidationError(f"SPDX field is missing: {field} ({path})")
    packages = document.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ImageSbomValidationError(f"SPDX packages are empty: {path}")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_and_write_provenance(
    *,
    cyclonedx: Path,
    spdx: Path,
    image_ref: str,
    image_digest: str,
    local_image_id: str,
    source_revision: str,
    oci_revision: str,
    architecture: str,
    output: Path,
) -> dict[str, Any]:
    if not image_ref.strip():
        raise ImageSbomValidationError("image reference is empty")
    if not DIGEST_RE.fullmatch(image_digest):
        raise ImageSbomValidationError("image digest must be a lowercase sha256 digest")
    if not DIGEST_RE.fullmatch(local_image_id):
        raise ImageSbomValidationError("local image id must be a lowercase sha256 digest")
    if not REVISION_RE.fullmatch(source_revision) or source_revision != oci_revision:
        raise ImageSbomValidationError("OCI revision must equal the full source Git SHA")
    if not ARCHITECTURE_RE.fullmatch(architecture):
        raise ImageSbomValidationError("image architecture must use the linux/<arch> form")

    cyclonedx_raw, cyclonedx_document = _read_json(cyclonedx)
    spdx_raw, spdx_document = _read_json(spdx)
    _validate_cyclonedx(cyclonedx_document, cyclonedx)
    _validate_spdx(spdx_document, spdx)

    provenance: dict[str, Any] = {
        "schema_version": 1,
        "image": {
            "ref": image_ref,
            "digest": image_digest,
            "local_image_id": local_image_id,
            "architecture": architecture,
            "oci_revision": oci_revision,
            "source_revision": source_revision,
        },
        "sboms": {
            "cyclonedx": {"path": cyclonedx.name, "sha256": _sha256(cyclonedx_raw)},
            "spdx_json": {"path": spdx.name, "sha256": _sha256(spdx_raw)},
        },
    }
    serialized = json.dumps(provenance, ensure_ascii=False, sort_keys=True)
    if SECRET_FIELD_RE.search(serialized) or SECRET_VALUE_RE.search(serialized):
        raise ImageSbomValidationError("SBOM provenance contains a secret-shaped field or value")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized + "\n", encoding="utf-8")
    return provenance


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cyclonedx", type=Path, required=True)
    parser.add_argument("--spdx", type=Path, required=True)
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--local-image-id", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--oci-revision", required=True)
    parser.add_argument("--architecture", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        provenance = validate_and_write_provenance(
            cyclonedx=args.cyclonedx,
            spdx=args.spdx,
            image_ref=args.image_ref,
            image_digest=args.image_digest,
            local_image_id=args.local_image_id,
            source_revision=args.source_revision,
            oci_revision=args.oci_revision,
            architecture=args.architecture,
            output=args.output,
        )
    except (ImageSbomValidationError, OSError) as error:
        print(f"image SBOM validation error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(provenance, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
