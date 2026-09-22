from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
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


def _install_args(*extra: str):
    return hermes._parser().parse_args(
        [
            "install",
            "--source-root",
            "source",
            "--source-definitions",
            "definitions",
            "--worker-env",
            "worker.env",
            "--yfc-sha",
            "a" * 40,
            "--discovery-image",
            "registry.invalid/hermes-discovery@sha256:" + "a" * 64,
            "--worker-image",
            "registry.invalid/hermes-worker@sha256:" + "b" * 64,
            *extra,
        ]
    )


@pytest.mark.parametrize("value", ["registry.invalid/hermes-worker@sha256:" + "b" * 64])
def test_colocation_accepts_only_registry_content_addressed_images(value: str) -> None:
    assert hermes.validate_image_ref(value) == value


def test_colocation_rejects_local_image_ids() -> None:
    with pytest.raises(hermes.ColocationError):
        hermes.validate_image_ref("sha256:" + "a" * 64)


@pytest.mark.parametrize(
    "value", ["registry.invalid/hermes-worker:latest", "registry.invalid/hermes-worker:stable"]
)
def test_colocation_rejects_floating_images(value: str) -> None:
    with pytest.raises(hermes.ColocationError):
        hermes.validate_image_ref(value)


def test_install_defaults_to_separate_vm_without_a_yfc_deployment_lock() -> None:
    args = _install_args()

    assert args.mode == "separate-vm"
    assert args.deployment_lock is None


def test_colocation_requires_an_explicit_deployment_lock() -> None:
    args = _install_args("--mode", "colocated-isolated")

    with pytest.raises(hermes.ColocationError, match="explicit --deployment-lock"):
        hermes.install(args)


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


def test_separate_vm_unit_rendering_does_not_embed_yfc_deployment_target(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    target = tmp_path / "systemd"
    image = "registry.invalid/hermes-discovery@sha256:" + "d" * 64

    hermes._render_units(
        root,
        target,
        definitions_digest="e" * 64,
        discovery_image=image,
        mode="separate-vm",
        deployment_lock="none",
    )

    rendered = (target / "hermes-discovery.service").read_text(encoding="utf-8")
    assert "HERMES_DEPLOYMENT_MODE=separate-vm" in rendered
    assert "COLOCATED_ISOLATED_HERMES=no" in rendered
    assert "HERMES_YFC_DEPLOYMENT_LOCK=none" in rendered
    assert "/srv/yfc" not in rendered
    assert "hermes_egress.py refresh" in rendered
    assert "--mode ${HERMES_DEPLOYMENT_MODE}" in rendered


def test_separate_vm_retires_legacy_host_dns_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], bool, bool]] = []

    class Result:
        returncode = 1
        stdout = "inactive\n"

    def fake_run(args: list[str], *, check: bool = True, capture: bool = False) -> Result:
        calls.append((args, check, capture))
        return Result()

    monkeypatch.setattr(hermes, "_run", fake_run)

    hermes._retire_legacy_egress()

    assert calls == [
        (["systemctl", "disable", "--now", "hermes-egress-refresh.timer"], False, False),
        (["systemctl", "is-active", "hermes-egress-refresh.timer"], False, True),
        (["nft", "delete", "table", "inet", "hermes_guard"], False, False),
        (["nft", "list", "table", "inet", "hermes_guard"], False, True),
    ]


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
    assert schema["properties"]["mode"]["default"] == "separate-vm"
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
        hermes.ensure_network(mode="colocated-isolated")


def test_separate_vm_rejects_a_yfc_compose_network(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 0
        stdout = "fit-mini-app_default\n"

    monkeypatch.setattr(hermes, "_run", lambda *args, **kwargs: Result())

    with pytest.raises(hermes.ColocationError, match="explicit colocated-isolated"):
        hermes.ensure_network()


def test_network_subnets_tolerate_builtin_networks_without_ipam_config() -> None:
    assert hermes._network_subnets({"IPAM": {"Config": None}}) == []


def test_release_manifest_is_immutable_and_self_validating(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    definitions = tmp_path / "source-definitions.json"
    definitions.write_text(
        json.dumps(
            {
                "schema_version": "hermes-source-definitions-v1",
                "source_registry_sha256": "a" * 64,
                "definitions_version": "yfc-news-sources:" + "a" * 64,
                "sources": [{"id": "source"}],
            }
        ),
        encoding="utf-8",
    )
    manifest = hermes.build_manifest(
        source_root=root,
        source_definitions=definitions,
        worker_env_sha256="f" * 64,
        yfc_sha="b" * 40,
        discovery_image="registry.invalid/hermes-discovery@sha256:" + "c" * 64,
        worker_image="registry.invalid/hermes-worker@sha256:" + "d" * 64,
        mode="colocated-isolated",
        deployment_lock="/srv/yfc/deployment.lock",
    )

    assert hermes.validate_manifest(manifest) == manifest
    tampered = {**manifest, "yfc_sha": "e" * 40}
    with pytest.raises(hermes.ReleaseManifestError):
        hermes.validate_manifest(tampered)


def test_staged_release_components_must_match_manifest(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    definitions = tmp_path / "source-definitions.json"
    definitions.write_text(
        json.dumps(
            {
                "schema_version": "hermes-source-definitions-v1",
                "source_registry_sha256": "a" * 64,
                "definitions_version": "yfc-news-sources:" + "a" * 64,
                "sources": [{"id": "source"}],
            }
        ),
        encoding="utf-8",
    )
    manifest = hermes.build_manifest(
        source_root=root,
        source_definitions=definitions,
        worker_env_sha256="f" * 64,
        yfc_sha="b" * 40,
        discovery_image="registry.invalid/hermes-discovery@sha256:" + "c" * 64,
        worker_image="registry.invalid/hermes-worker@sha256:" + "d" * 64,
        mode="colocated-isolated",
        deployment_lock="/srv/yfc/deployment.lock",
    )
    release = tmp_path / "release"
    for source, target in {
        "deploy/hermes-discovery/discovery_runner.py": "discovery_runner.py",
        "deploy/hermes-discovery/hermes_worker_drain.py": "hermes_worker_drain.py",
        "deploy/hermes-discovery/hermes_resource_guard.py": "hermes_resource_guard.py",
        "deploy/hermes-discovery/hermes_egress.py": "hermes_egress.py",
        "deploy/hermes-discovery/hermes_health.py": "hermes_health.py",
        "deploy/hermes-discovery/hermes-discovery-provenance.json": "hermes-discovery-provenance.json",
        "deploy/hermes-editorial-worker/editorial_worker.py": "editorial-worker/editorial_worker.py",
        "deploy/hermes-editorial-worker/hermes-provenance.json": "editorial-worker/hermes-provenance.json",
    }.items():
        destination = release / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / source, destination)
    definitions_target = release / "config" / "source-definitions.json"
    definitions_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(definitions, definitions_target)

    hermes._validate_staged_release(release, manifest)
    (release / "hermes_health.py").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(hermes.ColocationError, match="does not match manifest"):
        hermes._validate_staged_release(release, manifest)
