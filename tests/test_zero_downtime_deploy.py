from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import zero_downtime_deploy as deploy

OLD_SHA = "a" * 40
NEW_SHA = "b" * 40


class FakeProbe:
    def poll(self):
        return None


def _config(tmp_path: Path) -> deploy.DeployConfig:
    environment_file = tmp_path / ".env"
    if not environment_file.exists():
        environment_file.write_text(
            "# preserved deployment settings\n"
            "POSTGRES_IMAGE=registry/postgres@sha256:"
            + "e"
            * 64
            + "\nBACKEND_IMAGE=registry/backend:legacy\n"
            "BOT_IMAGE=registry/bot:legacy\n",
            encoding="utf-8",
        )
    return deploy.DeployConfig(
        target_revision=NEW_SHA,
        base_url="https://app.example.test",
        public_base_url="https://example.test",
        backend_image=f"registry/backend:{NEW_SHA}",
        bot_image=f"registry/bot:{NEW_SHA}",
        root=tmp_path,
        state_root=tmp_path / ".artifacts" / "operations" / "deployments",
        observation_seconds=1,
        readiness_timeout_seconds=5,
        probe_interval_seconds=0.1,
        probe_timeout_seconds=1,
        seo_timeout_seconds=20,
        backend_drain_seconds=45,
        worker_drain_seconds=120,
        bot_drain_seconds=60,
        bot_polling_enabled=True,
    )


def _state(config: deploy.DeployConfig, *, revision: str = OLD_SHA) -> None:
    state = deploy.ReleaseState(
        version=1,
        active_slot="blue",
        active_revision=revision,
        active_backend_image="registry/backend@sha256:" + "1" * 64,
        active_bot_image="registry/bot@sha256:" + "2" * 64,
    )
    deploy._atomic_json(config.state_root / "state.json", asdict(state))


def test_production_migration_command_uses_immutable_manifest(monkeypatch) -> None:
    monkeypatch.setenv("DEPLOY_MIGRATION_MANIFEST", "deployment-migration-manifest.json")

    command = deploy._online_migration_command(OLD_SHA, NEW_SHA)

    assert command[-2:] == ["--manifest", "deployment-migration-manifest.json"]


def test_image_digest_resolves_repo_digest_from_immutable_image_id(monkeypatch) -> None:
    repo_digest = "registry/backend@sha256:" + "d" * 64
    monkeypatch.setattr(
        deploy,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, stdout=f"[{json.dumps(repo_digest)}]|{OLD_SHA}\n"
        ),
    )

    assert deploy._image_digest("sha256:" + "c" * 64, OLD_SHA) == repo_digest


def test_persist_application_image_refs_replaces_duplicates_and_preserves_file_contract(
    tmp_path: Path,
) -> None:
    environment_file = tmp_path / ".env"
    environment_file.write_text(
        "# keep this comment\n"
        "APP_ENV=prod\n"
        "BACKEND_IMAGE=registry/backend:old\n"
        "BACKEND_IMAGE=registry/backend:duplicate\n"
        "BOT_IMAGE=registry/bot:old\n"
        "OTHER=value\n",
        encoding="utf-8",
    )
    os.chmod(environment_file, 0o640)
    expected_mode = os.stat(environment_file).st_mode & 0o777
    backend_image = "registry/backend@sha256:" + "1" * 64
    bot_image = "registry/bot@sha256:" + "2" * 64

    deploy._persist_application_image_refs(
        environment_file,
        backend_image=backend_image,
        bot_image=bot_image,
    )

    assert environment_file.read_text(encoding="utf-8") == (
        "# keep this comment\n"
        "APP_ENV=prod\n"
        f"BACKEND_IMAGE={backend_image}\n"
        f"BOT_IMAGE={bot_image}\n"
        "OTHER=value\n"
    )
    assert os.stat(environment_file).st_mode & 0o777 == expected_mode


def test_persist_application_image_refs_appends_missing_keys_without_final_newline(
    tmp_path: Path,
) -> None:
    environment_file = tmp_path / ".env"
    environment_file.write_text("APP_ENV=prod", encoding="utf-8")

    deploy._persist_application_image_refs(
        environment_file,
        backend_image="registry/backend@sha256:" + "1" * 64,
        bot_image="registry/bot@sha256:" + "2" * 64,
    )

    assert environment_file.read_text(encoding="utf-8") == (
        "APP_ENV=prod\n"
        "BACKEND_IMAGE=registry/backend@sha256:" + "1" * 64 + "\n"
        "BOT_IMAGE=registry/bot@sha256:" + "2" * 64
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("BACKEND_IMAGE", "registry/backend:tag"),
        ("BOT_IMAGE", "registry/bot@sha256:" + "A" * 64),
        ("BOT_IMAGE", "registry/bot@sha256:" + "1" * 63),
    ],
)
def test_persist_application_image_refs_rejects_non_immutable_values(
    tmp_path: Path, key: str, value: str
) -> None:
    environment_file = tmp_path / ".env"
    environment_file.write_text("APP_ENV=prod\n", encoding="utf-8")
    values = {
        "BACKEND_IMAGE": "registry/backend@sha256:" + "1" * 64,
        "BOT_IMAGE": "registry/bot@sha256:" + "2" * 64,
    }
    values[key] = value

    with pytest.raises(deploy.DeploymentError, match=key):
        deploy._persist_application_image_refs(
            environment_file,
            backend_image=values["BACKEND_IMAGE"],
            bot_image=values["BOT_IMAGE"],
        )


def test_legacy_image_digest_accepts_exact_tag_when_oci_label_is_missing(monkeypatch) -> None:
    image_id = "sha256:" + "c" * 64
    configured_image = f"registry/backend:{OLD_SHA}"
    repo_digest = "registry/backend@sha256:" + "d" * 64

    monkeypatch.setattr(deploy, "_legacy_running_image", lambda _service: image_id)
    monkeypatch.setattr(deploy, "_legacy_configured_image", lambda _service: configured_image)

    def missing_label_digest(image: str, revision: str) -> str:
        raise deploy.DeploymentError(f"image {image} revision '' does not match {revision}")

    monkeypatch.setattr(deploy, "_image_digest", missing_label_digest)
    monkeypatch.setattr(
        deploy,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args,
            0,
            stdout=(f"{json.dumps([repo_digest])}|{json.dumps([configured_image])}|\n"),
        ),
    )

    assert deploy._legacy_image_digest("backend", OLD_SHA) == repo_digest


def test_legacy_image_digest_rejects_mutable_tag_when_oci_label_is_missing(monkeypatch) -> None:
    image_id = "sha256:" + "c" * 64
    configured_image = "registry/backend:latest"
    repo_digest = "registry/backend@sha256:" + "d" * 64

    monkeypatch.setattr(deploy, "_legacy_running_image", lambda _service: image_id)
    monkeypatch.setattr(deploy, "_legacy_configured_image", lambda _service: configured_image)

    def missing_label_digest(image: str, revision: str) -> str:
        raise deploy.DeploymentError(f"image {image} revision '' does not match {revision}")

    monkeypatch.setattr(
        deploy,
        "_image_digest",
        missing_label_digest,
    )
    monkeypatch.setattr(
        deploy,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args,
            0,
            stdout=f"{json.dumps([repo_digest])}|{json.dumps([configured_image])}|\n",
        ),
    )

    with pytest.raises(deploy.DeploymentError, match="exact revision tag"):
        deploy._legacy_image_digest("backend", OLD_SHA)


def test_config_can_keep_rollout_state_outside_immutable_release(
    tmp_path: Path, monkeypatch
) -> None:
    state_root = tmp_path / "persistent-deployments"
    monkeypatch.setenv("DEPLOY_STATE_ROOT", str(state_root))
    monkeypatch.setenv("BACKEND_IMAGE", f"registry/backend:{NEW_SHA}")
    monkeypatch.setenv("BOT_IMAGE", f"registry/bot:{NEW_SHA}")

    parser = SimpleNamespace(
        target_revision=NEW_SHA,
        base_url="https://app.example.test",
        public_base_url="https://example.test",
    )
    config = deploy._config(parser)

    assert config.state_root == state_root.resolve()


def test_public_smoke_uses_bounded_seo_timeout(tmp_path: Path, monkeypatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(deploy, "_run", lambda command, **kwargs: commands.append(command))

    deploy._public_smoke(_config(tmp_path))

    assert commands[-1] == [
        deploy.sys.executable,
        "scripts/check_seo_surface.py",
        "https://example.test",
        "--timeout",
        "20",
    ]


def test_registry_pull_retries_transient_failures_with_bounded_backoff(monkeypatch) -> None:
    attempts = 0
    sleeps: list[int] = []

    def compose(*args, **kwargs):
        nonlocal attempts
        del kwargs
        attempts += 1
        if attempts < 3:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(deploy, "_compose", compose)
    monkeypatch.setattr(deploy.time, "sleep", sleeps.append)

    deploy._pull_images_with_retry("backend", "bot", env={"BACKEND_IMAGE": "image"})

    assert attempts == 3
    assert sleeps == [10, 20]


def test_registry_pull_fails_after_bounded_attempts(monkeypatch) -> None:
    attempts = 0

    def compose(*args, **kwargs):
        nonlocal attempts
        del kwargs
        attempts += 1
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(deploy, "_compose", compose)
    monkeypatch.setattr(deploy, "REGISTRY_PULL_ATTEMPTS", 3)
    monkeypatch.setattr(deploy, "REGISTRY_PULL_BASE_DELAY_SECONDS", 0)
    monkeypatch.setattr(deploy.time, "sleep", lambda _delay: None)

    with pytest.raises(subprocess.CalledProcessError):
        deploy._pull_images_with_retry("backend", env={"BACKEND_IMAGE": "image"})

    assert attempts == 3


def _patch_runtime(monkeypatch, *, fail_at: str | None = None):
    calls: dict[str, list] = {
        "compose": [],
        "switch": [],
        "run": [],
        "consumer_start": [],
        "consumer_stop": [],
    }

    def compose(*args, **kwargs):
        del kwargs
        calls["compose"].append(args)
        if fail_at == "candidate_start" and "backend-green" in args and "up" in args:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0, stdout="backend-green\n", stderr="")

    public_smoke_count = 0

    def public_smoke(_config, **kwargs):
        del kwargs
        nonlocal public_smoke_count
        public_smoke_count += 1
        if fail_at == "external_smoke" and public_smoke_count == 2:
            raise deploy.DeploymentError("external smoke failed")

    def run(args, **kwargs):
        del kwargs
        calls["run"].append(args)
        if fail_at == "migration" and "scripts/check_online_migrations.py" in args:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    def switch(active, fallback):
        calls["switch"].append((active, fallback))
        if fail_at == "gateway" and active == "green":
            raise deploy.DeploymentError("invalid gateway config")

    def candidate_smoke(slot, **kwargs):
        del kwargs
        if fail_at == "candidate_smoke":
            raise deploy.DeploymentError(f"{slot} smoke failed")

    def start_consumers(slot, **kwargs):
        del kwargs
        calls["consumer_start"].append(slot)
        if fail_at == "consumer" and slot == "green":
            raise deploy.DeploymentError("consumer ownership failed")

    def stop_consumers(slot, config, **kwargs):
        del kwargs
        assert config.worker_drain_seconds == 120
        calls["consumer_stop"].append(slot)

    monkeypatch.setattr(deploy, "_capacity", lambda: {"cpu_count": 4})
    monkeypatch.setattr(deploy, "_compose", compose)
    monkeypatch.setattr(deploy, "_run", run)
    monkeypatch.setattr(deploy, "_public_smoke", public_smoke)
    monkeypatch.setattr(deploy, "_switch_gateway", switch)
    monkeypatch.setattr(deploy, "_candidate_smoke", candidate_smoke)
    monkeypatch.setattr(
        deploy,
        "_image_digest",
        lambda image, revision: (
            image.split("@", maxsplit=1)[0].rsplit(":", maxsplit=1)[0] + "@sha256:" + "3" * 64
        ),
    )
    monkeypatch.setattr(deploy, "_start_probe", lambda *args: FakeProbe())
    monkeypatch.setattr(deploy, "_finish_probe", lambda *args: {"failure_count": 0})

    def wait_observation(*args):
        del args
        if fail_at == "interrupt":
            raise KeyboardInterrupt

    monkeypatch.setattr(deploy, "_wait_observation", wait_observation)
    monkeypatch.setattr(deploy, "_stop_slot_consumers", stop_consumers)
    monkeypatch.setattr(deploy, "_start_slot_consumers", start_consumers)
    return calls


def test_successful_rollout_updates_state_only_after_observation(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    _state(config)
    calls = _patch_runtime(monkeypatch)

    evidence = deploy.deploy(config)

    state = deploy.ReleaseState.from_path(config.state_root / "state.json")
    assert evidence.verdict == "active"
    assert state.active_slot == "green"
    assert state.active_revision == NEW_SHA
    assert state.rollback_revision == OLD_SHA
    environment_file = config.root / ".env"
    assert f"BACKEND_IMAGE=registry/backend@sha256:{'3' * 64}" in environment_file.read_text(
        encoding="utf-8"
    )
    assert f"BOT_IMAGE=registry/bot@sha256:{'3' * 64}" in environment_file.read_text(
        encoding="utf-8"
    )
    assert calls["switch"] == [("blue", "blue"), ("green", "blue"), ("green", "green")]


@pytest.mark.parametrize("fail_at", ["candidate_start", "candidate_smoke", "gateway", "migration"])
def test_pre_switch_failure_preserves_active_state(
    tmp_path: Path, monkeypatch, fail_at: str
) -> None:
    config = _config(tmp_path)
    _state(config)
    calls = _patch_runtime(monkeypatch, fail_at=fail_at)

    with pytest.raises((deploy.DeploymentError, subprocess.CalledProcessError)):
        deploy.deploy(config)

    state = deploy.ReleaseState.from_path(config.state_root / "state.json")
    assert state.active_revision == OLD_SHA
    assert ("green", "blue") not in calls["switch"] or fail_at == "gateway"


def test_post_switch_failure_reloads_verified_old_route(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    _state(config)
    calls = _patch_runtime(monkeypatch, fail_at="external_smoke")

    with pytest.raises(deploy.DeploymentError, match="external smoke"):
        deploy.deploy(config)

    assert calls["switch"][-1] == ("blue", "blue")
    assert (
        deploy.ReleaseState.from_path(config.state_root / "state.json").active_revision == OLD_SHA
    )


def test_partial_consumer_handoff_restores_the_previous_single_owner(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    _state(config)
    calls = _patch_runtime(monkeypatch, fail_at="consumer")

    with pytest.raises(deploy.DeploymentError, match="consumer ownership"):
        deploy.deploy(config)

    assert calls["switch"][-1] == ("blue", "blue")
    assert calls["consumer_stop"] == ["blue", "green"]
    assert calls["consumer_start"] == ["green", "blue"]


def test_interrupted_post_switch_rollout_restores_state_and_route(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    _state(config)
    calls = _patch_runtime(monkeypatch, fail_at="interrupt")

    with pytest.raises(KeyboardInterrupt):
        deploy.deploy(config)

    assert calls["switch"][-1] == ("blue", "blue")
    assert (
        deploy.ReleaseState.from_path(config.state_root / "state.json").active_revision == OLD_SHA
    )


def test_repeated_same_sha_is_a_verified_no_op(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    _state(config, revision=NEW_SHA)
    calls = _patch_runtime(monkeypatch)
    smoke = []
    monkeypatch.setattr(
        deploy,
        "_public_smoke",
        lambda value, **_kwargs: smoke.append(value.base_url),
    )

    evidence = deploy.deploy(config)

    assert evidence.verdict == "active"
    assert smoke == [config.base_url]
    assert calls["switch"] == [("blue", "blue")]


def test_gateway_switch_validates_before_atomic_reload(monkeypatch) -> None:
    commands = []
    reloaded = False

    def compose(*args, **kwargs):
        nonlocal reloaded
        commands.append(args)
        if "reload" in args:
            reloaded = True
        if "adapt" in args:
            output = '{"apps":{"dial":"backend-green:8000"}}'
        elif any("reverse_proxy/upstreams" in part for part in args):
            output = '[{"num_requests":0}]'
        elif any("2019/config/" in part for part in args):
            dial = "backend-green:8000" if reloaded else "backend-blue:8000"
            output = f'{{"apps":{{"dial":"{dial}"}}}}'
        else:
            output = ""
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    monkeypatch.setattr(deploy, "_compose", compose)

    deploy._switch_gateway("green", "blue")

    assert "validate" in commands[0]
    assert any("reload" in command for command in commands)
    assert commands.index(
        next(command for command in commands if "validate" in command)
    ) < commands.index(next(command for command in commands if "reload" in command))
    assert any("YFC_ASSET_FALLBACK_UPSTREAM=backend-blue:8000" in part for part in commands[0])


def test_current_run_logs_use_the_container_start_boundary(monkeypatch) -> None:
    commands = []

    def compose(*args, **kwargs):
        del kwargs
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="current run\n", stderr="")

    monkeypatch.setattr(deploy, "_compose", compose)
    lease = deploy.ConsumerLease(
        service="bot-green",
        container_id="container-new",
        started_at="2026-08-28T12:00:00.000000000Z",
        required_markers=("polling_file_lock_acquired", "telegram_polling_started"),
    )

    assert deploy._current_run_logs(lease) == "current run\n"
    assert commands == [
        (
            "logs",
            "--no-color",
            "--since",
            "2026-08-28T12:00:00.000000000Z",
            "bot-green",
        )
    ]


def test_bot_lease_requires_lock_and_polling_markers_from_current_run(monkeypatch) -> None:
    lease = deploy.ConsumerLease(
        service="bot-green",
        container_id="container-new",
        started_at="2026-08-28T12:00:00Z",
        required_markers=("polling_file_lock_acquired", "telegram_polling_started"),
    )
    monkeypatch.setattr(deploy, "_service_is_running", lambda service: service == "bot-green")
    monkeypatch.setattr(
        deploy,
        "_compose",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, stdout="container-new\n", stderr=""
        ),
    )
    monkeypatch.setattr(
        deploy,
        "_run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args,
            0,
            stdout=("2026-08-28T12:00:00Z\n" if "{{.State.StartedAt}}" in args else "running\n"),
            stderr="",
        ),
    )
    monkeypatch.setattr(deploy, "_current_run_logs", lambda value: "telegram_polling_started\n")

    assert deploy._lease_is_current_and_healthy(lease) is False


def test_consumer_lease_rejects_restart_with_same_container_id(monkeypatch) -> None:
    lease = deploy.ConsumerLease(
        service="worker-green",
        container_id="container-same",
        started_at="2026-08-28T12:00:00Z",
        required_markers=("worker_started",),
    )
    monkeypatch.setattr(deploy, "_service_is_running", lambda service: True)
    monkeypatch.setattr(
        deploy,
        "_compose",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, stdout="container-same\n", stderr=""
        ),
    )
    monkeypatch.setattr(
        deploy,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, stdout="2026-08-28T12:05:00Z\n", stderr=""
        ),
    )
    monkeypatch.setattr(
        deploy,
        "_current_run_logs",
        lambda value: "worker_started\nworker_stopped\nworker_started\n",
    )

    assert deploy._lease_is_current_and_healthy(lease) is False


def test_config_reads_drain_and_polling_values_from_compose_dotenv(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".env").write_text(
        "DEPLOY_WORKER_DRAIN_SECONDS=300s\nBOT_POLLING_ENABLED=false\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BACKEND_IMAGE", "registry/backend:" + NEW_SHA)
    monkeypatch.setenv("BOT_IMAGE", "registry/bot:" + NEW_SHA)
    monkeypatch.delenv("DEPLOY_WORKER_DRAIN_SECONDS", raising=False)
    monkeypatch.delenv("BOT_POLLING_ENABLED", raising=False)

    config = deploy._config(
        SimpleNamespace(
            target_revision=NEW_SHA,
            base_url="https://app.example.test",
            public_base_url="https://example.test",
        )
    )

    assert config.worker_drain_seconds == 300
    assert config.bot_polling_enabled is False


def test_consumer_stop_uses_configured_drain_and_requires_worker_ack(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    commands = []
    lease = deploy.ConsumerLease(
        service="worker-blue",
        container_id="worker-current",
        started_at="2026-08-28T12:00:00Z",
        required_markers=("worker_started",),
    )
    monkeypatch.setattr(deploy, "_consumer_lease", lambda *args: lease)
    monkeypatch.setattr(deploy, "_service_is_running", lambda service: True)
    monkeypatch.setattr(deploy, "_current_run_logs", lambda value: "worker_stopped\n")
    monkeypatch.setattr(
        deploy,
        "_compose",
        lambda *args, **kwargs: (
            commands.append(args) or subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        ),
    )

    deploy._stop_slot_consumers("blue", config)

    assert commands == [
        ("stop", "-t", "120", "worker-blue"),
        ("stop", "-t", "60", "bot-blue"),
    ]


def test_consumer_stop_fails_closed_when_worker_drain_is_unconfirmed(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    commands = []
    lease = deploy.ConsumerLease(
        service="worker-blue",
        container_id="worker-current",
        started_at="2026-08-28T12:00:00Z",
        required_markers=("worker_started",),
    )
    monkeypatch.setattr(deploy, "_consumer_lease", lambda *args: lease)
    monkeypatch.setattr(deploy, "_service_is_running", lambda service: True)
    monkeypatch.setattr(deploy, "_current_run_logs", lambda value: "worker_drain_requested\n")
    monkeypatch.setattr(deploy, "_container_exited_cleanly", lambda value: False)
    monkeypatch.setattr(
        deploy,
        "_compose",
        lambda *args, **kwargs: (
            commands.append(args) or subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        ),
    )

    with pytest.raises(deploy.DeploymentError, match="consumer state is uncertain"):
        deploy._stop_slot_consumers("blue", config)

    assert commands == [("stop", "-t", "120", "worker-blue")]


def test_consumer_stop_accepts_exact_container_clean_exit_without_legacy_marker(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    lease = deploy.ConsumerLease(
        service="worker-blue",
        container_id="worker-current",
        started_at="2026-08-28T12:00:00Z",
        required_markers=("worker_started",),
    )
    commands = []
    monkeypatch.setattr(deploy, "_consumer_lease", lambda *args: lease)
    monkeypatch.setattr(deploy, "_service_is_running", lambda service: True)
    monkeypatch.setattr(deploy, "_current_run_logs", lambda value: "application_log\n")
    monkeypatch.setattr(deploy, "_container_exited_cleanly", lambda value: True)
    monkeypatch.setattr(
        deploy,
        "_compose",
        lambda *args, **kwargs: (
            commands.append(args) or subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        ),
    )

    deploy._stop_slot_consumers("blue", config)

    assert commands == [
        ("stop", "-t", "120", "worker-blue"),
        ("stop", "-t", "60", "bot-blue"),
    ]


def test_manual_rollback_swaps_only_verified_revisions(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    state = deploy.ReleaseState(
        version=1,
        active_slot="green",
        active_revision=NEW_SHA,
        active_backend_image="registry/backend@sha256:" + "3" * 64,
        active_bot_image="registry/bot@sha256:" + "4" * 64,
        rollback_slot="blue",
        rollback_revision=OLD_SHA,
        rollback_backend_image="registry/backend@sha256:" + "1" * 64,
        rollback_bot_image="registry/bot@sha256:" + "2" * 64,
    )
    deploy._atomic_json(config.state_root / "state.json", asdict(state))
    calls = _patch_runtime(monkeypatch)

    deploy.rollback(config)

    restored = deploy.ReleaseState.from_path(config.state_root / "state.json")
    assert restored.active_revision == OLD_SHA
    assert restored.rollback_revision == NEW_SHA
    assert calls["switch"] == [("blue", "green")]
    environment = config.root.joinpath(".env").read_text(encoding="utf-8")
    assert "BACKEND_IMAGE=registry/backend@sha256:" + "1" * 64 in environment
    assert "BOT_IMAGE=registry/bot@sha256:" + "2" * 64 in environment


def _patch_single_slot_runtime(tmp_path: Path, monkeypatch) -> dict[str, list]:
    calls: dict[str, list] = {
        "compose": [],
        "stops": [],
        "backend_starts": [],
        "consumer_starts": [],
    }
    config = _config(tmp_path)
    active_revision_path = config.state_root / "last-successful-revision"
    active_revision_path.parent.mkdir(parents=True)
    active_revision_path.write_text(OLD_SHA + "\n", encoding="utf-8")
    monkeypatch.setenv("DEPLOY_SINGLE_SLOT_CONFIRMED_SHA", NEW_SHA)
    monkeypatch.setattr(deploy, "_reclaim_single_slot_docker_space", lambda: None)
    monkeypatch.setattr(
        deploy,
        "_single_slot_capacity",
        lambda: {"cpu_count": 1, "memory_available_mb": 128, "disk_available_mb": 4096},
    )
    monkeypatch.setattr(
        deploy,
        "_compose",
        lambda *args, **kwargs: (
            calls["compose"].append((args, kwargs))
            or subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        ),
    )
    monkeypatch.setattr(deploy, "_switch_gateway", lambda *args: None)
    monkeypatch.setattr(deploy, "_public_smoke", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        deploy,
        "_legacy_running_image",
        lambda service: f"registry/{'bot' if service == 'bot' else 'backend'}:{OLD_SHA}",
    )
    monkeypatch.setattr(
        deploy,
        "_image_digest",
        lambda image, revision: f"{image.split(':', maxsplit=1)[0]}@sha256:{revision[0] * 64}",
    )
    monkeypatch.setattr(
        deploy,
        "_run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="", stderr=""),
    )
    monkeypatch.setattr(
        deploy,
        "_stop_legacy_services",
        lambda value: calls["stops"].append(value.target_revision),
    )
    monkeypatch.setattr(
        deploy,
        "_start_legacy_backend",
        lambda env, value: calls["backend_starts"].append(env["BACKEND_IMAGE"]),
    )

    def start_consumers(env, evidence, value, *, require_markers, best_effort=False):
        del evidence, value
        del best_effort
        calls["consumer_starts"].append((env["BOT_IMAGE"], require_markers))
        markers = ("worker_started",) if require_markers else ()
        return (
            deploy.ConsumerLease("worker", "worker-id", "now", markers),
            deploy.ConsumerLease("bot", "bot-id", "now", markers),
        )

    monkeypatch.setattr(deploy, "_start_legacy_consumers", start_consumers)
    monkeypatch.setattr(deploy, "_lease_is_current_and_healthy", lambda lease: True)
    return calls


def test_single_slot_rollout_requires_exact_one_shot_confirmation(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    monkeypatch.delenv("DEPLOY_SINGLE_SLOT_CONFIRMED_SHA", raising=False)

    with pytest.raises(deploy.DeploymentError, match="exact target revision"):
        deploy.single_slot_deploy(config)


def test_single_slot_refuses_initialized_blue_green_host(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    _state(config)
    monkeypatch.setenv("DEPLOY_SINGLE_SLOT_CONFIRMED_SHA", NEW_SHA)

    with pytest.raises(deploy.DeploymentError, match="before blue/green state initialization"):
        deploy.single_slot_deploy(config)


def test_single_slot_rollout_replaces_legacy_services_and_records_success(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    calls = _patch_single_slot_runtime(tmp_path, monkeypatch)

    evidence = deploy.single_slot_deploy(config)

    assert evidence.verdict == "active"
    assert calls["stops"] == [NEW_SHA]
    assert calls["backend_starts"] == ["registry/backend@sha256:" + "b" * 64]
    assert calls["consumer_starts"] == [("registry/bot@sha256:" + "b" * 64, True)]
    assert (
        config.state_root.joinpath("last-successful-revision").read_text(encoding="utf-8").strip()
        == NEW_SHA
    )
    environment = config.root.joinpath(".env").read_text(encoding="utf-8")
    assert "BACKEND_IMAGE=registry/backend@sha256:" + "b" * 64 in environment
    assert "BOT_IMAGE=registry/bot@sha256:" + "b" * 64 in environment
    assert not config.state_root.joinpath("state.json").exists()


def test_single_slot_docker_reclaim_never_removes_container_data_or_volumes(
    monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        deploy,
        "_run",
        lambda args, **kwargs: (
            calls.append((args, kwargs))
            or subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        ),
    )

    deploy._reclaim_single_slot_docker_space()

    assert calls == [
        (["docker", "image", "prune", "--all", "--force"], {}),
        (["docker", "builder", "prune", "--all", "--force"], {}),
    ]
    assert all("volume" not in args and "container" not in args for args, _ in calls)


def test_legacy_running_image_uses_immutable_container_image_id(monkeypatch) -> None:
    image_id = "sha256:" + "c" * 64
    monkeypatch.setattr(
        deploy,
        "_compose",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="container-id\n"),
    )
    commands = []

    def run(args, **kwargs):
        del kwargs
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=image_id + "\n")

    monkeypatch.setattr(deploy, "_run", run)
    monkeypatch.setattr(deploy, "_service_is_running", lambda _service: True)

    assert deploy._legacy_running_image("backend") == image_id
    assert commands == [["docker", "inspect", "--format", "{{.Image}}", "container-id"]]


def test_single_slot_snapshots_legacy_provenance_before_reclaim(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_single_slot_runtime(tmp_path, monkeypatch)
    events: list[str] = []

    def running_image(service: str) -> str:
        events.append(f"running:{service}")
        return f"sha256:{'a' * 64}"

    def image_digest(image: str, revision: str) -> str:
        events.append(f"digest:{image}")
        return f"registry/backend@sha256:{revision[0] * 64}"

    monkeypatch.setattr(deploy, "_legacy_running_image", running_image)
    monkeypatch.setattr(deploy, "_image_digest", image_digest)
    monkeypatch.setattr(
        deploy,
        "_reclaim_single_slot_docker_space",
        lambda: events.append("reclaim"),
    )

    deploy.single_slot_deploy(_config(tmp_path))

    assert events.index("digest:sha256:" + "a" * 64) < events.index("reclaim")
    assert events.index("running:edge") < events.index("reclaim")


def test_single_slot_reclaims_docker_space_before_capacity_gate(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_single_slot_runtime(tmp_path, monkeypatch)
    events = []
    monkeypatch.setattr(
        deploy,
        "_reclaim_single_slot_docker_space",
        lambda: events.append("reclaim"),
    )
    monkeypatch.setattr(
        deploy,
        "_single_slot_capacity",
        lambda: (
            events.append("capacity")
            or {"cpu_count": 1, "memory_available_mb": 128, "disk_available_mb": 4096}
        ),
    )

    deploy.single_slot_deploy(_config(tmp_path))

    assert events[:2] == ["reclaim", "capacity"]


def test_single_slot_failure_after_stop_restores_previous_images(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    calls = _patch_single_slot_runtime(tmp_path, monkeypatch)
    starts = 0

    def fail_target_once(env, value):
        nonlocal starts
        del value
        starts += 1
        calls["backend_starts"].append(env["BACKEND_IMAGE"])
        if starts == 1:
            raise deploy.DeploymentError("new backend failed")

    monkeypatch.setattr(deploy, "_start_legacy_backend", fail_target_once)
    monkeypatch.setattr(deploy, "_service_is_running", lambda service: False)

    with pytest.raises(deploy.DeploymentError, match="new backend failed"):
        deploy.single_slot_deploy(config)

    assert calls["backend_starts"] == [
        "registry/backend@sha256:" + "b" * 64,
        "registry/backend@sha256:" + "a" * 64,
    ]
    assert calls["consumer_starts"] == [("registry/bot@sha256:" + "a" * 64, True)]
    summaries = list(config.state_root.glob("single-slot-*/summary.json"))
    assert len(summaries) == 1
    assert json.loads(summaries[0].read_text(encoding="utf-8"))["verdict"] == "rolled back"


def test_single_slot_rollback_requires_verified_consumer_ownership(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    calls = _patch_single_slot_runtime(tmp_path, monkeypatch)
    starts = 0

    def fail_target_once(env, value):
        nonlocal starts
        del value
        starts += 1
        calls["backend_starts"].append(env["BACKEND_IMAGE"])
        if starts == 1:
            raise deploy.DeploymentError("new backend failed")

    def fail_consumer_ownership(env, evidence, value, *, require_markers, best_effort=False):
        del env, evidence, value
        assert require_markers is True
        assert best_effort is True
        raise deploy.DeploymentError("bot ownership confirmation timed out")

    monkeypatch.setattr(deploy, "_start_legacy_backend", fail_target_once)
    monkeypatch.setattr(deploy, "_start_legacy_consumers", fail_consumer_ownership)
    monkeypatch.setattr(deploy, "_service_is_running", lambda service: False)

    with pytest.raises(deploy.DeploymentError, match="new backend failed"):
        deploy.single_slot_deploy(config)

    summaries = list(config.state_root.glob("single-slot-*/summary.json"))
    assert len(summaries) == 1
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert summary["verdict"] == "manual intervention required"
    rollback = next(stage for stage in summary["stages"] if stage["name"] == "single_slot_rollback")
    assert rollback["status"] == "failed"
    assert "ownership confirmation timed out" in rollback["reason"]


def test_single_slot_rollback_attempts_consumers_after_backend_smoke_failure(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    calls = _patch_single_slot_runtime(tmp_path, monkeypatch)
    starts = 0

    def fail_target_and_rollback_smoke(env, value):
        nonlocal starts
        del value
        starts += 1
        calls["backend_starts"].append(env["BACKEND_IMAGE"])
        if starts == 1:
            raise deploy.DeploymentError("new backend failed")
        raise deploy.DeploymentError("rollback smoke timed out")

    monkeypatch.setattr(deploy, "_start_legacy_backend", fail_target_and_rollback_smoke)
    monkeypatch.setattr(deploy, "_service_is_running", lambda service: False)

    with pytest.raises(deploy.DeploymentError, match="new backend failed"):
        deploy.single_slot_deploy(config)

    assert calls["consumer_starts"] == [("registry/bot@sha256:" + "a" * 64, True)]
    summaries = list(config.state_root.glob("single-slot-*/summary.json"))
    assert len(summaries) == 1
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert summary["verdict"] == "manual intervention required"
    rollback = next(stage for stage in summary["stages"] if stage["name"] == "single_slot_rollback")
    assert "rollback smoke timed out" in rollback["reason"]


def test_legacy_consumer_restore_attempts_bot_after_worker_failure(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    evidence = deploy.Evidence(
        deployment_id="test",
        target_revision=NEW_SHA,
        previous_revision=OLD_SHA,
        active_slot="legacy",
        candidate_slot="legacy",
        started_at=0,
    )
    started_services = []

    def compose(*args, **kwargs):
        del kwargs
        if args[0] == "up":
            started_services.append(args[-1])
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    def consumer_lease(service, markers):
        return deploy.ConsumerLease(
            service=service,
            container_id=f"{service}-current",
            started_at="2026-08-28T12:00:00Z",
            required_markers=markers,
        )

    def wait_for_ownership(lease, timeout):
        del timeout
        if lease.service == "worker":
            raise deploy.DeploymentError("worker ownership failed")

    monkeypatch.setattr(deploy, "_compose", compose)
    monkeypatch.setattr(deploy, "_consumer_lease", consumer_lease)
    monkeypatch.setattr(deploy, "_wait_for_ownership", wait_for_ownership)

    with pytest.raises(deploy.DeploymentError, match="worker ownership failed"):
        deploy._start_legacy_consumers({}, evidence, config, require_markers=True, best_effort=True)

    assert started_services == ["worker", "bot"]


def test_forward_consumer_start_is_fail_fast_after_worker_failure(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    evidence = deploy.Evidence(
        deployment_id="test",
        target_revision=NEW_SHA,
        previous_revision=OLD_SHA,
        active_slot="legacy",
        candidate_slot="legacy",
        started_at=0,
    )
    started_services = []

    def compose(*args, **kwargs):
        del kwargs
        if args[0] == "up":
            started_services.append(args[-1])
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    def consumer_lease(service, markers):
        return deploy.ConsumerLease(
            service=service,
            container_id=f"{service}-current",
            started_at="2026-08-28T12:00:00Z",
            required_markers=markers,
        )

    def wait_for_ownership(lease, timeout):
        del timeout
        if lease.service == "worker":
            raise deploy.DeploymentError("worker ownership failed")

    monkeypatch.setattr(deploy, "_compose", compose)
    monkeypatch.setattr(deploy, "_consumer_lease", consumer_lease)
    monkeypatch.setattr(deploy, "_wait_for_ownership", wait_for_ownership)

    with pytest.raises(deploy.DeploymentError, match="worker ownership failed"):
        deploy._start_legacy_consumers({}, evidence, config, require_markers=True)

    assert started_services == ["worker"]


def test_single_slot_rechecks_capacity_after_pull_and_backup(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    calls = _patch_single_slot_runtime(tmp_path, monkeypatch)
    capacity_checks = 0

    def capacity():
        nonlocal capacity_checks
        capacity_checks += 1
        if capacity_checks == 2:
            raise deploy.DeploymentError("single-slot capacity gate failed after pull")
        return {"cpu_count": 1, "memory_available_mb": 128, "disk_available_mb": 4096}

    monkeypatch.setattr(deploy, "_single_slot_capacity", capacity)

    with pytest.raises(deploy.DeploymentError, match="failed after pull"):
        deploy.single_slot_deploy(config)

    assert capacity_checks == 2
    assert calls["stops"] == []


def test_single_slot_rejects_backend_worker_image_drift(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    calls = _patch_single_slot_runtime(tmp_path, monkeypatch)

    def running_image(service):
        if service == "worker":
            return f"registry/worker-drift:{OLD_SHA}"
        return f"registry/{'bot' if service == 'bot' else 'backend'}:{OLD_SHA}"

    monkeypatch.setattr(deploy, "_legacy_running_image", running_image)

    with pytest.raises(deploy.DeploymentError, match="same verified image digest"):
        deploy.single_slot_deploy(config)

    assert calls["stops"] == []


def test_single_slot_stop_is_ordered_and_uses_bounded_timeouts(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    running = {"worker", "bot", "backend"}
    commands = []
    worker_lease = deploy.ConsumerLease(
        service="worker",
        container_id="worker-current",
        started_at="2026-08-28T12:00:00Z",
        required_markers=("worker_started",),
    )

    monkeypatch.setattr(deploy, "_service_is_running", lambda service: service in running)
    monkeypatch.setattr(deploy, "_consumer_lease", lambda *args: worker_lease)
    monkeypatch.setattr(deploy, "_current_run_logs", lambda lease: "worker_stopped\n")

    def compose(*args, **kwargs):
        del kwargs
        commands.append(args)
        if args[0] == "stop":
            running.remove(args[-1])
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(deploy, "_compose", compose)

    deploy._stop_legacy_services(config)

    assert commands == [
        ("stop", "-t", "120", "worker"),
        ("stop", "-t", "60", "bot"),
        ("stop", "-t", "45", "backend"),
    ]


def test_single_slot_stop_fails_closed_when_worker_drain_is_unconfirmed(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    running = {"worker", "bot", "backend"}
    commands = []
    worker_lease = deploy.ConsumerLease(
        service="worker",
        container_id="worker-current",
        started_at="2026-08-28T12:00:00Z",
        required_markers=("worker_started",),
    )

    monkeypatch.setattr(deploy, "_service_is_running", lambda service: service in running)
    monkeypatch.setattr(deploy, "_consumer_lease", lambda *args: worker_lease)
    monkeypatch.setattr(deploy, "_current_run_logs", lambda lease: "worker_drain_requested\n")
    monkeypatch.setattr(deploy, "_container_exited_cleanly", lambda lease: False)

    def compose(*args, **kwargs):
        del kwargs
        commands.append(args)
        if args[0] == "stop":
            running.remove(args[-1])
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(deploy, "_compose", compose)

    with pytest.raises(deploy.DeploymentError, match="consumer state is uncertain"):
        deploy._stop_legacy_services(config)

    assert commands == [("stop", "-t", "120", "worker")]
    assert running == {"bot", "backend"}


def test_clean_exit_evidence_requires_exited_zero(monkeypatch) -> None:
    lease = deploy.ConsumerLease(
        service="worker",
        container_id="worker-current",
        started_at="2026-08-28T12:00:00Z",
        required_markers=("worker_started",),
    )

    for state, expected in (("exited 0\n", True), ("exited 137\n", False), ("running 0\n", False)):
        monkeypatch.setattr(
            deploy,
            "_run",
            lambda *args, output=state, **kwargs: subprocess.CompletedProcess(
                args, 0, stdout=output, stderr=""
            ),
        )
        assert deploy._container_exited_cleanly(lease) is expected
