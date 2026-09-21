from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


def _load_module():
    path = Path(__file__).parents[1] / "scripts" / "hermes_colocation.py"
    spec = importlib.util.spec_from_file_location("hermes_colocation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hermes = _load_module()


@pytest.mark.parametrize(
    "value",
    ["sha256:" + "a" * 64, "registry.invalid/hermes-worker@sha256:" + "b" * 64],
)
def test_colocation_accepts_only_content_addressed_images(value: str) -> None:
    assert hermes.validate_image_ref(value) == value


@pytest.mark.parametrize(
    "value", ["registry.invalid/hermes-worker:latest", "registry.invalid/hermes-worker:stable"]
)
def test_colocation_rejects_floating_images(value: str) -> None:
    with pytest.raises(hermes.ColocationError):
        hermes.validate_image_ref(value)


def test_image_inspection_must_match_the_pinned_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    pinned = "sha256:" + "a" * 64

    class Result:
        returncode = 0
        stdout = json.dumps({"Id": "sha256:" + "b" * 64, "RepoDigests": []})

    monkeypatch.setattr(hermes, "_run", lambda *args, **kwargs: Result())

    with pytest.raises(hermes.ColocationError, match="does not match"):
        hermes.verify_image(pinned, role="worker")


def test_unit_rendering_preserves_repository_digest_separator(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    target = tmp_path / "systemd"
    image = "registry.invalid/hermes-discovery@sha256:" + "d" * 64

    hermes._render_units(
        root,
        target,
        definitions_digest="e" * 64,
        discovery_image=image,
        mode="colocated-isolated",
        deployment_lock="/srv/yfc/fit-mini-app/.artifacts/operations/deployments/deployment.lock",
    )

    rendered = (target / "hermes-discovery.service").read_text(encoding="utf-8")
    assert image in rendered
    assert "COLOCATED_ISOLATED_HERMES=yes" in rendered
    assert "hermes_egress.py refresh" in rendered
    assert "@DISCOVERY_IMAGE@" not in rendered


def test_definitions_provenance_is_content_addressed(tmp_path: Path) -> None:
    registry_hash = "a" * 64
    path = tmp_path / "source-definitions.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "hermes-source-definitions-v1",
                "source_registry_sha256": registry_hash,
                "definitions_version": f"yfc-news-sources:{registry_hash}",
                "sources": [{"id": "source"}],
            }
        ),
        encoding="utf-8",
    )

    digest = hermes.validate_definitions(path)

    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()


def test_worker_env_names_are_required_and_image_is_checked(tmp_path: Path) -> None:
    image = "registry.invalid/hermes-worker@sha256:" + "c" * 64
    path = tmp_path / "worker.env"
    path.write_text(
        "\n".join(
            [
                f"HERMES_WORKER_IMAGE={image}",
                *(
                    f"{name}=test-value"
                    for name in sorted(hermes.WORKER_ENV_NAMES - {"HERMES_WORKER_IMAGE"})
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if os.name == "posix":
        path.chmod(0o600)

    assert hermes.validate_worker_env(path) == hermes.WORKER_ENV_NAMES
    assert hermes._env_values(path)["HERMES_WORKER_IMAGE"] == image


def test_worker_env_rejects_unexpected_names(tmp_path: Path) -> None:
    path = tmp_path / "worker.env"
    path.write_text(
        "\n".join(
            [
                "HERMES_WORKER_IMAGE=registry.invalid/hermes-worker@sha256:" + "a" * 64,
                *(
                    f"{name}=value"
                    for name in sorted(hermes.WORKER_ENV_NAMES - {"HERMES_WORKER_IMAGE"})
                ),
                "TELEGRAM_BOT_TOKEN=must-not-be-present",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if os.name == "posix":
        path.chmod(0o600)

    with pytest.raises(hermes.ColocationError, match="unexpected variable names"):
        hermes.validate_worker_env(path)


def test_mode_schema_declares_both_supported_topologies() -> None:
    schema = json.loads(
        (
            Path(__file__).parents[1]
            / "deploy"
            / "hermes-discovery"
            / "deployment-mode.schema.json"
        ).read_text(encoding="utf-8")
    )

    assert schema["properties"]["mode"]["enum"] == ["separate-vm", "colocated-isolated"]
    assert schema["properties"]["network"]["properties"]["public_ports"]["const"] == []


def test_network_guard_rejects_yfc_container_attachment(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 0
        stdout = "hermes-net\n"

    monkeypatch.setattr(hermes, "_run", lambda *args, **kwargs: Result())
    monkeypatch.setattr(
        hermes,
        "_docker_inspect",
        lambda name: [
            {
                "Driver": "bridge",
                "Containers": {"id": {"Name": "fit-mini-app-db-1"}},
                "IPAM": {"Config": [{"Subnet": "172.30.0.0/24"}]},
            }
        ],
    )

    with pytest.raises(hermes.ColocationError, match="YFC container"):
        hermes.ensure_network()
