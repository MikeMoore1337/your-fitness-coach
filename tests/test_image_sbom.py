import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from scripts.validate_image_sbom import (
    ImageSbomValidationError,
    validate_and_write_provenance,
)


def _write_sboms(root: Path) -> tuple[Path, Path]:
    cyclonedx = root / "image.cyclonedx.json"
    cyclonedx.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "metadata": {"timestamp": "2026-10-20T00:00:00Z"},
                "components": [{"type": "library", "name": "synthetic", "version": "1.0"}],
            }
        ),
        encoding="utf-8",
    )
    spdx = root / "image.spdx.json"
    spdx.write_text(
        json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "SPDXID": "SPDXRef-DOCUMENT",
                "name": "synthetic-image",
                "documentNamespace": "https://example.invalid/synthetic-image",
                "creationInfo": {"created": "2026-10-20T00:00:00Z"},
                "packages": [{"SPDXID": "SPDXRef-Package", "name": "synthetic"}],
            }
        ),
        encoding="utf-8",
    )
    return cyclonedx, spdx


def _validate(root: Path, **overrides: str) -> dict:
    cyclonedx, spdx = _write_sboms(root)
    values = {
        "cyclonedx": cyclonedx,
        "spdx": spdx,
        "image_ref": "ghcr.io/example/yfc-backend:abc123",
        "image_digest": "sha256:" + "a" * 64,
        "local_image_id": "sha256:" + "b" * 64,
        "source_revision": "c" * 40,
        "oci_revision": "c" * 40,
        "architecture": "linux/amd64",
        "output": root / "provenance.json",
    }
    values.update(overrides)
    return validate_and_write_provenance(**values)


def test_sboms_are_validated_and_linked_to_image_provenance(tmp_path: Path) -> None:
    provenance = _validate(tmp_path)

    assert provenance["image"]["digest"] == "sha256:" + "a" * 64
    assert provenance["image"]["source_revision"] == "c" * 40
    assert provenance["sboms"]["cyclonedx"]["sha256"]
    assert json.loads((tmp_path / "provenance.json").read_text(encoding="utf-8")) == provenance


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("image_digest", "not-a-digest", "image digest"),
        ("oci_revision", "d" * 40, "OCI revision"),
        ("architecture", "windows/amd64", "architecture"),
    ],
)
def test_provenance_mismatches_fail_closed(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    with pytest.raises(ImageSbomValidationError, match=message):
        _validate(tmp_path, **{field: value})


def test_secret_shaped_sbom_content_is_rejected(tmp_path: Path) -> None:
    cyclonedx, spdx = _write_sboms(tmp_path)
    cyclonedx.write_text(
        cyclonedx.read_text(encoding="utf-8").replace(
            '"name": "synthetic"', '"telegram_bot_token": "synthetic-secret"'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ImageSbomValidationError, match="secret-shaped"):
        validate_and_write_provenance(
            cyclonedx=cyclonedx,
            spdx=spdx,
            image_ref="ghcr.io/example/yfc-backend:abc123",
            image_digest="sha256:" + "a" * 64,
            local_image_id="sha256:" + "b" * 64,
            source_revision="c" * 40,
            oci_revision="c" * 40,
            architecture="linux/amd64",
            output=tmp_path / "provenance.json",
        )


@pytest.mark.skipif(os.name == "nt", reason="Executes the Linux Actions bash step")
@pytest.mark.parametrize("failure", [None, "image_id", "revision", "digest", "pull"])
def test_published_sbom_binds_registry_digest_to_scanned_image(tmp_path: Path, failure: str | None):
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    step = next(
        step
        for step in workflow["jobs"]["containers"]["steps"]
        if step.get("name") == "Verify published application image digest"
    )
    built = _validate(tmp_path)
    for source, target in (
        ("image.cyclonedx.json", "sbom.cyclonedx.json"),
        ("image.spdx.json", "sbom.spdx.json"),
    ):
        (tmp_path / target).write_bytes((tmp_path / source).read_bytes())
    docker = tmp_path / "docker"
    docker.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
failure = os.environ['FAILURE']
digest = 'sha256:' + 'd' * 64
if args[:3] == ['buildx', 'imagetools', 'inspect']:
    if args[-1] == '--raw':
        print(json.dumps({'config': {'digest': 'sha256:' + ('e' if failure == 'image_id' else 'b') * 64}}))
    else:
        print('invalid' if failure == 'digest' else digest)
elif args[0] == 'pull':
    assert args[1] == 'ghcr.io/example/yfc@' + digest
    sys.exit(1 if failure == 'pull' else 0)
elif args[:2] == ['image', 'inspect']:
    assert args[2] == 'ghcr.io/example/yfc@' + digest
    if args[-1] == '{{.Os}}/{{.Architecture}}':
        print('linux/amd64')
    else:
        print(('e' if failure == 'revision' else 'c') * 40)
else:
    raise AssertionError(args)
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=root,
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "PUBLISHED_REF": "ghcr.io/example/yfc:" + "c" * 40,
            "EXPECTED_IMAGE_ID": built["image"]["local_image_id"],
            "SOURCE_REVISION": "c" * 40,
            "SBOM_DIR": str(tmp_path),
            "FAILURE": failure or "",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    published = json.loads((tmp_path / "provenance.json").read_text(encoding="utf-8"))
    if failure:
        assert result.returncode != 0
        assert published == built
    else:
        assert result.returncode == 0, result.stderr
        assert published["image"]["digest"] == "sha256:" + "d" * 64
        assert published["image"]["ref"].endswith("@sha256:" + "d" * 64)
        assert published["image"]["local_image_id"] == built["image"]["local_image_id"]
        assert published["sboms"] == built["sboms"] | {
            "cyclonedx": {**built["sboms"]["cyclonedx"], "path": "sbom.cyclonedx.json"},
            "spdx_json": {**built["sboms"]["spdx_json"], "path": "sbom.spdx.json"},
        }
        assert json.loads((tmp_path / "build-provenance.json").read_text()) == built
