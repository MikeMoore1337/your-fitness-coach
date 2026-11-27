import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import allure_quarantine as quarantine

OWNER = "MikeMoore1337"
SHA = "a" * 40


def _environment():
    return {
        "id": 123,
        "name": "allure-review",
        "can_admins_bypass": False,
        "deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": False},
        "protection_rules": [
            {
                "type": "required_reviewers",
                "reviewers": [{"type": "User", "reviewer": {"login": OWNER}}],
            }
        ],
    }


def _bundles(root: Path, kind: str = "weekly") -> None:
    for name in quarantine.expected_bundles(kind):
        (root / name).write_bytes(("encrypted fixture " + name).encode())


def test_manifest_binds_every_bundle_to_commit_run_and_attempt(tmp_path: Path) -> None:
    _bundles(tmp_path)
    manifest = quarantine.make_manifest(tmp_path, kind="weekly", run_id="42", attempt="1", sha=SHA)
    data = json.loads(manifest)
    assert len(data["bundles"]) == len(quarantine.expected_bundles("weekly"))
    assert data["sha"] == SHA
    original = hashlib.sha256(manifest).hexdigest()
    assert (
        original
        != hashlib.sha256(
            quarantine.make_manifest(tmp_path, kind="weekly", run_id="42", attempt="2", sha=SHA)
        ).hexdigest()
    )
    (tmp_path / "frontend-checks.enc").write_bytes(b"changed")
    assert (
        original
        != hashlib.sha256(
            quarantine.make_manifest(tmp_path, kind="weekly", run_id="42", attempt="1", sha=SHA)
        ).hexdigest()
    )


def test_quarantine_rejects_missing_or_extra_bundles(tmp_path: Path) -> None:
    _bundles(tmp_path, "daily")
    (tmp_path / "frontend-checks.enc").unlink()
    with pytest.raises(quarantine.QuarantineError, match="bundle set"):
        quarantine.make_manifest(tmp_path, kind="daily", run_id="42", attempt="1", sha=SHA)
    (tmp_path / "frontend-checks.enc").write_bytes(b"fixture")
    (tmp_path / "unexpected.enc").write_bytes(b"fixture")
    with pytest.raises(quarantine.QuarantineError, match="bundle set"):
        quarantine.make_manifest(tmp_path, kind="daily", run_id="42", attempt="1", sha=SHA)


def test_weekly_quarantine_requires_every_browser_shard(tmp_path: Path) -> None:
    _bundles(tmp_path)
    expected = quarantine.expected_bundles("weekly")
    assert len([name for name in expected if name.startswith("frontend-cross-browser-")]) == 15
    (tmp_path / "frontend-cross-browser-webkit-shard-5.enc").unlink()
    with pytest.raises(quarantine.QuarantineError, match="bundle set"):
        quarantine.make_manifest(tmp_path, kind="weekly", run_id="42", attempt="1", sha=SHA)


def test_cli_rejects_changed_bundle_before_decryption(tmp_path: Path) -> None:
    root = tmp_path / "bundles"
    root.mkdir()
    _bundles(root, "daily")
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(
        quarantine.make_manifest(root, kind="daily", run_id="42", attempt="1", sha=SHA)
    )
    checksum = hashlib.sha256(manifest.read_bytes()).hexdigest()
    script = Path(__file__).parents[1] / "scripts" / "allure_quarantine.py"
    command = [
        sys.executable,
        str(script),
        "verify",
        "--root",
        str(root),
        "--manifest",
        str(manifest),
        "--kind",
        "daily",
        "--run-id",
        "42",
        "--attempt",
        "1",
        "--sha",
        SHA,
        "--digest",
        checksum,
    ]
    assert subprocess.run(command, capture_output=True, check=False).returncode == 0
    (root / "frontend-checks.enc").write_bytes(b"tampered")
    assert subprocess.run(command, capture_output=True, check=False).returncode != 0


def test_review_environment_requires_owner_no_bypass_and_branch_policy() -> None:
    assert quarantine.verify_environment(_environment(), OWNER) == 123
    for field, value in (
        ("can_admins_bypass", True),
        ("deployment_branch_policy", None),
        ("protection_rules", []),
        ("name", "production"),
    ):
        altered = _environment()
        altered[field] = value
        with pytest.raises(quarantine.QuarantineError):
            quarantine.verify_environment(altered, OWNER)
    with pytest.raises(quarantine.QuarantineError):
        quarantine.verify_environment(_environment(), "another-owner")


def test_approval_must_match_owner_environment_run_attempt_and_digest() -> None:
    checksum = "b" * 64
    review = {
        "state": "approved",
        "comment": f"allure-review:42:1:{checksum}",
        "user": {"login": OWNER},
        "environments": [{"id": 123}],
    }
    args = {
        "env_id": 123,
        "owner": OWNER,
        "run_id": "42",
        "attempt": "1",
        "manifest_digest": checksum,
    }
    quarantine.verify_approval([review], **args)
    for modified in (
        {"attempt": "2"},
        {"run_id": "43"},
        {"manifest_digest": "c" * 64},
        {"env_id": 124},
        {"owner": "another-owner"},
    ):
        with pytest.raises(quarantine.QuarantineError):
            quarantine.verify_approval([review], **(args | modified))
    with pytest.raises(quarantine.QuarantineError):
        quarantine.verify_approval([review, review | {"state": "rejected"}], **args)


def test_scheduled_publication_requires_quarantine_and_verified_approval() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    quarantine_job = workflow.split("  allure-quarantine:\n", 1)[1].split(
        "\n  scheduled-report:\n", 1
    )[0]
    publisher_job = workflow.split("  scheduled-report:\n", 1)[1].split(
        "\n  codeql-security:\n", 1
    )[0]
    assert "retention-days: 3" in quarantine_job
    assert "scripts/allure_quarantine.py environment" in quarantine_job
    assert "name: ${{ needs.allure-quarantine.outputs.environment_name }}" in publisher_job
    assert "needs.allure-quarantine.result == 'success'" in publisher_job
    assert "scripts/allure_quarantine.py approval" in publisher_job
    assert "scripts/allure_quarantine.py verify" in publisher_job
    decrypt_step = publisher_job.split("- name: Decrypt only current-run result bundles", 1)[
        1
    ].split("- name: Aggregate and enrich Allure results", 1)[0]
    assert "if: always() && steps.quarantine-verified.outcome == 'success'" in decrypt_step
    assert "if: always() && steps.quarantine-verified.outcome == 'success'" in publisher_job
    assert "python scripts/publish_allure_report.py publish" not in quarantine_job
