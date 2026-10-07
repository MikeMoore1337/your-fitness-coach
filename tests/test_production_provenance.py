import json
from pathlib import Path

import pytest
from scripts import production_provenance as provenance

SHA_A = "a" * 40
SHA_B = "b" * 40
IMAGE_REPOSITORY = "ghcr.io/example/your-fitness-coach-backend"
IMAGE_DIGEST = "sha256:" + "d" * 64


@pytest.mark.parametrize(
    ("image_ref", "repo_digests"),
    [
        (f"{IMAGE_REPOSITORY}:{SHA_A}", [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"]),
        (f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}", [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"]),
    ],
)
def test_validate_image_reference_accepts_verified_tag_or_digest(
    image_ref: str, repo_digests: list[str]
) -> None:
    provenance._validate_image_reference(
        image_ref,
        revision=SHA_A,
        repo_digests=repo_digests,
    )


@pytest.mark.parametrize(
    ("image_ref", "repo_digests", "revision"),
    [
        (f"{IMAGE_REPOSITORY}:{SHA_B}", [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"], SHA_A),
        (f"{IMAGE_REPOSITORY}:latest", [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"], SHA_A),
        (f"{IMAGE_REPOSITORY}@sha256:{'e' * 63}", [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"], SHA_A),
        (f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}", [], SHA_A),
        (
            f"ghcr.io/other/repository@{IMAGE_DIGEST}",
            [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"],
            SHA_A,
        ),
        (IMAGE_REPOSITORY, [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"], SHA_A),
        (f"{IMAGE_REPOSITORY}:{SHA_A}", [f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"], ""),
    ],
)
def test_validate_image_reference_rejects_unverified_forms(
    image_ref: str, repo_digests: list[str], revision: str
) -> None:
    with pytest.raises(provenance.ProvenanceError):
        provenance._validate_image_reference(
            image_ref,
            revision=revision,
            repo_digests=repo_digests,
        )


def test_service_snapshot_accepts_production_digest_reference(monkeypatch) -> None:
    image_ref = f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"
    image_id = "sha256:" + "i" * 64
    responses = {
        ("docker", "ps"): "backend-container\n",
        ("docker", "inspect", "backend-container"): json.dumps(
            [
                {
                    "Config": {"Image": image_ref},
                    "State": {"Status": "running", "Health": {"Status": "healthy"}},
                    "Image": image_id,
                }
            ]
        ),
        ("docker", "image", "inspect", image_ref): json.dumps(
            [
                {
                    "Config": {"Labels": {provenance.REVISION_LABEL: SHA_A}},
                    "Id": image_id,
                    "RepoDigests": [image_ref],
                }
            ]
        ),
    }

    def run(command: list[str]) -> str:
        if command[:2] == ["docker", "ps"]:
            return responses[("docker", "ps")]
        return responses[tuple(command[:4])]

    monkeypatch.setattr(provenance, "_run", run)

    result = provenance._service_snapshot("backend")

    assert result["image_ref"] == image_ref
    assert result["revision"] == SHA_A
    assert result["immutable_image"] is True


def test_service_snapshot_rejects_container_image_id_mismatch(monkeypatch) -> None:
    image_ref = f"{IMAGE_REPOSITORY}@{IMAGE_DIGEST}"
    responses = {
        ("docker", "ps"): "backend-container\n",
        ("docker", "inspect", "backend-container"): json.dumps(
            [
                {
                    "Config": {"Image": image_ref},
                    "State": {"Status": "running", "Health": {"Status": "healthy"}},
                    "Image": "sha256:" + "c" * 64,
                }
            ]
        ),
        ("docker", "image", "inspect", image_ref): json.dumps(
            [
                {
                    "Config": {"Labels": {provenance.REVISION_LABEL: SHA_A}},
                    "Id": "sha256:" + "i" * 64,
                    "RepoDigests": [image_ref],
                }
            ]
        ),
    }

    def run(command: list[str]) -> str:
        if command[:2] == ["docker", "ps"]:
            return responses[("docker", "ps")]
        return responses[tuple(command[:4])]

    monkeypatch.setattr(provenance, "_run", run)

    with pytest.raises(provenance.ProvenanceError, match="immutable image ID"):
        provenance._service_snapshot("backend")


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("0126_plan_source_constraint (head)", {"0126_plan_source_constraint"}),
        ("0125_grocery_lists (head)", {"0125_grocery_lists"}),
        ("abcdef1234567890 (head)", {"abcdef1234567890"}),
        ("", set()),
        ("not a revision line", set()),
        (
            "0126_plan_source_constraint (head)\n0127_another_head (head)",
            {"0126_plan_source_constraint", "0127_another_head"},
        ),
    ],
)
def test_parse_alembic_revisions_supports_symbolic_hex_like_and_multiple_heads(
    output: str, expected: set[str]
) -> None:
    assert provenance.parse_alembic_revisions(output) == expected


@pytest.mark.parametrize(
    ("current", "heads", "expected"),
    [
        ({"0126_plan_source_constraint"}, {"0126_plan_source_constraint"}, True),
        (
            {"0125_grocery_lists", "0126_plan_source_constraint"},
            {"0126_plan_source_constraint"},
            True,
        ),
        (set(), {"0126_plan_source_constraint"}, False),
        ({"0126_plan_source_constraint"}, set(), False),
        ({"not a revision line"}, {"0126_plan_source_constraint"}, False),
        ({"0125_grocery_lists"}, {"0126_plan_source_constraint"}, False),
    ],
)
def test_alembic_revision_consistency_is_fail_closed(
    current: set[str], heads: set[str], expected: bool
) -> None:
    assert provenance.alembic_revisions_are_consistent(current, heads) is expected


def test_database_snapshot_parses_symbolic_revision_output(monkeypatch) -> None:
    outputs = iter(
        [
            "INFO [alembic.runtime.migration] Context impl PostgresqlImpl.\n"
            "0126_plan_source_constraint (head)\n",
            "0126_plan_source_constraint (head)\n",
        ]
    )
    monkeypatch.setattr(provenance, "_run", lambda _command: next(outputs))

    result = provenance._database_snapshot("backend-container")

    assert result["current_revisions"] == ["0126_plan_source_constraint"]
    assert result["head_revisions"] == ["0126_plan_source_constraint"]
    assert result["consistent"] is True


@pytest.mark.parametrize(
    ("recorded", "runtime", "expected"),
    [
        (SHA_A, [SHA_A, SHA_A, SHA_A], "OK"),
        (SHA_A, [SHA_B, SHA_B, SHA_B], "PROVENANCE_RECONCILIATION_REQUIRED"),
        (SHA_A, [SHA_A, SHA_B, SHA_A], "MIXED_RUNTIME"),
        ("invalid", [SHA_A, SHA_A, SHA_A], "INVALID_MARKER"),
        (SHA_A, [SHA_A, None, SHA_A], "INVALID_RUNTIME"),
    ],
)
def test_marker_runtime_classification_is_fail_closed(recorded, runtime, expected) -> None:
    assert provenance.classify_marker_runtime(recorded, runtime) == expected


def _verified_snapshot(runtime_revision: str = SHA_B) -> dict[str, object]:
    services = {
        service: {
            "revision": runtime_revision,
            "immutable_image": True,
            "error": None,
        }
        for service in provenance.SERVICES
    }
    return {
        "status": "PROVENANCE_RECONCILIATION_REQUIRED",
        "recorded_revision": SHA_A,
        "runtime_revision": runtime_revision,
        "runtime_uniform": True,
        "services": services,
        "release": {
            "path": f"/srv/yfc/fit-mini-app/releases/{runtime_revision}",
            "exists_and_matches": True,
        },
        "current": {"target": f"/srv/yfc/fit-mini-app/releases/{SHA_A}"},
        "database": {"consistent": True},
        "errors": [],
    }


def test_verification_rejects_runtime_revision_not_expected() -> None:
    snapshot = _verified_snapshot(runtime_revision=SHA_B)

    errors = provenance._verification_errors(snapshot, SHA_A)

    assert any("runtime revision" in error for error in errors)


def test_reconcile_changes_only_existing_metadata(monkeypatch, tmp_path: Path) -> None:
    snapshot = _verified_snapshot()
    writes: list[tuple[Path, str]] = []
    links: list[tuple[Path, Path]] = []

    monkeypatch.setattr(provenance, "inspect_production", lambda _root: snapshot)
    monkeypatch.setattr(
        provenance,
        "_atomic_text",
        lambda path, value: writes.append((path, value)),
    )

    def record_link(link: Path, target: Path) -> None:
        links.append((link, target))
        link.write_text(str(target), encoding="utf-8")

    monkeypatch.setattr(provenance, "_atomic_symlink", record_link)
    monkeypatch.setattr(provenance, "_read_revision", lambda _path: SHA_B)

    result = provenance.reconcile(tmp_path, SHA_B)

    assert result["status"] == "RECONCILED"
    assert result["application_mutation"] is False
    assert writes == [
        (tmp_path / ".artifacts/operations/deployments/last-successful-revision", f"{SHA_B}\n")
    ]
    assert links == [
        (tmp_path / "current", Path("/srv/yfc/fit-mini-app/releases") / SHA_B),
    ]


def test_reconcile_rejects_mixed_runtime_before_any_metadata_write(
    monkeypatch, tmp_path: Path
) -> None:
    snapshot = _verified_snapshot()
    snapshot["status"] = "MIXED_RUNTIME"
    snapshot["runtime_revision"] = None
    snapshot["runtime_uniform"] = False
    writes: list[object] = []
    monkeypatch.setattr(provenance, "inspect_production", lambda _root: snapshot)
    monkeypatch.setattr(provenance, "_atomic_text", lambda *args: writes.append(args))

    with pytest.raises(provenance.ProvenanceError, match=r"does not match|not uniform"):
        provenance.reconcile(tmp_path, SHA_B)

    assert writes == []


def test_deploy_preflight_is_before_bundle_transfer_and_reconcile_is_metadata_only() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    assert (
        workflow.index("Read the active deployed revision")
        < workflow.index("Build immutable deployment bundle")
        < workflow.index("Transfer immutable bundle to production")
    )
    assert "Production provenance mismatch before transfer" in workflow
    assert "options: [deploy, repair, verify, reconcile, rollback]" in workflow
    reconcile = workflow.split("\n  reconcile:\n", maxsplit=1)[1].split(
        "\n  rollback:", maxsplit=1
    )[0]
    assert "python3 - reconcile" in reconcile
    assert "application_mutation == false" in reconcile
    assert "deploy_production.sh" not in reconcile
    assert "docker compose" not in reconcile
