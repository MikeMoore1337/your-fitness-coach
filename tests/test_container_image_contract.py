from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_rebuilds_and_verifies_bot_runtime_sources_before_publish() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "no_cache: true" in workflow
    assert "no-cache: ${{ matrix.no_cache }}" in workflow
    assert "Verify bot runtime image contract" in workflow
    assert "import fitminiapp_bot.profile_sync" in workflow
    assert workflow.index("Verify bot runtime image contract") < workflow.index("Scan image")
    assert workflow.index("Verify bot runtime image contract") < workflow.index(
        "Publish scanned image"
    )


def test_ci_publishes_verified_backend_and_bot_sbom_provenance() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "steps.build.outputs.digest" in workflow
    assert "org.opencontainers.image.revision=${{ github.sha }}" in workflow
    assert "python scripts/validate_image_sbom.py" in workflow
    assert "format: cyclonedx" in workflow
    assert "format: spdx-json" in workflow
    assert "retention-days: 14" in workflow
    assert "Verify published application image digest" in workflow
    assert workflow.index("Scan image") < workflow.index("Generate CycloneDX SBOM")
    assert workflow.index("Generate CycloneDX SBOM") < workflow.index(
        "Validate image SBOM provenance"
    )
    assert workflow.index("Validate image SBOM provenance") < workflow.index("Upload image SBOMs")
    assert workflow.index("Upload image SBOMs") < workflow.index("Publish scanned image")
