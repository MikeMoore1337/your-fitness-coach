import json
from pathlib import Path

import pytest
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
