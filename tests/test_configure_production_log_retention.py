from __future__ import annotations

import io
import json
import os
import stat
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml
from scripts import configure_production_log_retention as retention

ROOT = Path(__file__).resolve().parents[1]
APP_SERVICES = retention.APPLICATION_SERVICES
PROTECTED_SERVICES = {
    "db",
    "caddy",
    "edge",
    "cloudflared",
    "allure-report-origin",
    "cloudflared-allure",
}


def _host_root(tmp_path: Path) -> Path:
    root = tmp_path / "host"
    (root / "etc" / "systemd").mkdir(parents=True)
    return root


def _source(tmp_path: Path, content: bytes = retention.EXPECTED_POLICY) -> Path:
    source = tmp_path / retention.POLICY_SOURCE.name
    source.write_bytes(content)
    return source


def _completed(arguments: list[str], stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(arguments, 0, stdout, "")


class _HostCommands:
    def __init__(
        self,
        root: Path,
        *,
        usage: list[str] | None = None,
        config_override: str | None = None,
    ) -> None:
        self.root = root
        self.usage = list(usage or ["56M"])
        self.config_override = config_override
        self.calls: list[list[str]] = []
        self.usage_index = 0

    def __call__(self, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        command = list(arguments)
        self.calls.append(command)
        if command[:3] == ["systemd-analyze", "cat-config", "systemd/journald.conf"]:
            if self.config_override is not None:
                return _completed(command, self.config_override)
            drop_in_dir = self.root / "etc/systemd/journald.conf.d"
            content = "".join(
                path.read_text(encoding="utf-8")
                for path in sorted(drop_in_dir.glob("*.conf"), key=lambda item: item.name)
                if path.is_file()
            )
            return _completed(command, "[Journal]\n" + content)
        if command == ["journalctl", "--disk-usage"]:
            value = self.usage[min(self.usage_index, len(self.usage) - 1)]
            self.usage_index += 1
            return _completed(
                command, f"Archived and active journals take up {value} in the file system.\n"
            )
        if command == ["systemctl", "is-active", "systemd-journald"]:
            return _completed(command, "active\n")
        if command[:2] == ["docker", "info"]:
            return _completed(command, "json-file\n")
        if command[:2] == ["docker", "ps"]:
            return _completed(command, "backend-id\nworker-id\nbot-id\ndb-id\n")
        if command[:2] == ["docker", "inspect"]:
            service = {
                "backend-id": "backend",
                "worker-id": "worker",
                "bot-id": "bot",
                "db-id": "db",
            }[command[-1]]
            options = json.dumps(retention.APPLICATION_LOG_OPTIONS)
            if service == "db":
                options = "{}"
            return _completed(
                command,
                f"/fit-mini-app-{service}-1|{service}|json-file|{options}\n",
            )
        return _completed(command)


def test_journald_policy_is_exact() -> None:
    policy = (ROOT / "deploy/production/journald/90-yfc-retention.conf").read_bytes()

    assert policy == retention.EXPECTED_POLICY
    assert retention.EXPECTED_SETTINGS == {
        "SystemMaxUse": "256M",
        "SystemKeepFree": "3G",
        "RuntimeMaxUse": "64M",
        "MaxRetentionSec": "14day",
        "Compress": "yes",
    }


def test_source_policy_is_validated_before_system_paths_are_created(tmp_path: Path) -> None:
    root = tmp_path / "host"
    source = _source(tmp_path, b"[Journal]\nSystemMaxUse=unbounded\n")

    with pytest.raises(retention.RetentionError, match="does not match"):
        retention._configure_journald(source=source, root=root, effective_uid=0)

    assert not root.exists()


def test_parent_symlink_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "host"
    outside = tmp_path / "outside"
    outside.mkdir()
    root.mkdir()
    source = _source(tmp_path)
    original_lstat = Path.lstat
    symlink_metadata = os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))

    def lstat(path: Path) -> os.stat_result:
        if path == root / "etc":
            return symlink_metadata
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat)

    with pytest.raises(retention.RetentionError, match="Unsafe systemd directory"):
        retention._configure_journald(source=source, root=root, effective_uid=0)

    assert not (outside / "systemd").exists()


def test_symlink_drop_in_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _host_root(tmp_path)
    drop_in_dir = root / "etc/systemd/journald.conf.d"
    drop_in_dir.mkdir()
    outside = tmp_path / "outside.conf"
    outside.write_text("[Journal]\n", encoding="utf-8")
    target = drop_in_dir / retention.DROP_IN_NAME
    original_lstat = Path.lstat
    symlink_metadata = os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))

    def lstat(path: Path) -> os.stat_result:
        if path == target:
            return symlink_metadata
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat)

    with pytest.raises(retention.RetentionError, match="regular non-symlink"):
        retention._configure_journald(
            source=_source(tmp_path), root=root, run=_HostCommands(root), effective_uid=0
        )

    assert outside.read_text(encoding="utf-8") == "[Journal]\n"


def test_unexpected_drop_in_type_is_rejected(tmp_path: Path) -> None:
    root = _host_root(tmp_path)
    (root / retention.DROP_IN_RELATIVE).mkdir(parents=True)

    with pytest.raises(retention.RetentionError, match="regular non-symlink"):
        retention._configure_journald(
            source=_source(tmp_path), root=root, run=_HostCommands(root), effective_uid=0
        )


def test_atomic_install_is_idempotent_and_restarts_only_on_change(tmp_path: Path) -> None:
    root = _host_root(tmp_path)
    source = _source(tmp_path)
    commands = _HostCommands(root)

    first = retention._configure_journald(source=source, root=root, run=commands, effective_uid=0)
    second = retention._configure_journald(source=source, root=root, run=commands, effective_uid=0)

    target = root / retention.DROP_IN_RELATIVE
    assert target.read_bytes() == retention.EXPECTED_POLICY
    assert first["changed"] is True
    assert first["services_restarted"] == ["systemd-journald"]
    assert second["changed"] is False
    assert second["services_restarted"] == []
    assert sum(call == ["systemctl", "restart", "systemd-journald"] for call in commands.calls) == 1
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_source_policy_overrides_existing_later_named_yfc_limits_drop_in(tmp_path: Path) -> None:
    root = _host_root(tmp_path)
    drop_in_dir = root / "etc/systemd/journald.conf.d"
    drop_in_dir.mkdir()
    existing = drop_in_dir / "99-yfc-limits.conf"
    existing.write_text(
        "[Journal]\nSystemMaxUse=500M\nRuntimeMaxUse=200M\nMaxRetentionSec=14day\n",
        encoding="utf-8",
    )
    commands = _HostCommands(root)

    result = retention._configure_journald(
        source=_source(tmp_path), root=root, run=commands, effective_uid=0
    )

    target = root / retention.DROP_IN_RELATIVE
    assert existing.name < target.name
    assert result["desired_settings"] == retention.EXPECTED_SETTINGS
    assert result["services_restarted"] == ["systemd-journald"]


def test_changed_policy_restarts_journald_after_effective_config_passes(tmp_path: Path) -> None:
    root = _host_root(tmp_path)
    target = root / retention.DROP_IN_RELATIVE
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(b"[Journal]\nSystemMaxUse=500M\n")
    commands = _HostCommands(root)

    result = retention._configure_journald(
        source=_source(tmp_path), root=root, run=commands, effective_uid=0
    )

    assert result["changed"] is True
    assert commands.calls.index(
        ["systemd-analyze", "cat-config", "systemd/journald.conf"]
    ) < commands.calls.index(["systemctl", "restart", "systemd-journald"])


def test_effective_config_failure_restores_the_previous_drop_in(tmp_path: Path) -> None:
    root = _host_root(tmp_path)
    target = root / retention.DROP_IN_RELATIVE
    target.parent.mkdir(exist_ok=True)
    old_content = b"[Journal]\nSystemMaxUse=500M\n"
    target.write_bytes(old_content)
    wrong_effective = retention.EXPECTED_POLICY.decode().replace(
        "SystemMaxUse=256M", "SystemMaxUse=1G"
    )
    commands = _HostCommands(root, config_override=wrong_effective)

    with pytest.raises(retention.RetentionError, match="Merged journald settings"):
        retention._configure_journald(
            source=_source(tmp_path), root=root, run=commands, effective_uid=0
        )

    assert target.read_bytes() == old_content
    assert not any(call[:2] == ["systemctl", "restart"] for call in commands.calls)


def test_restart_failure_restores_the_previous_drop_in_and_journald(tmp_path: Path) -> None:
    root = _host_root(tmp_path)
    target = root / retention.DROP_IN_RELATIVE
    target.parent.mkdir(exist_ok=True)
    old_content = b"[Journal]\nSystemMaxUse=500M\n"
    target.write_bytes(old_content)
    commands = _HostCommands(root)
    restart_count = 0

    def fail_first_restart(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        nonlocal restart_count
        if list(arguments) == ["systemctl", "restart", "systemd-journald"]:
            restart_count += 1
            if restart_count == 1:
                raise retention.RetentionError("systemd-journald restart failed")
        return commands(arguments)

    with pytest.raises(retention.RetentionError, match="restart failed"):
        retention._configure_journald(
            source=_source(tmp_path), root=root, run=fail_first_restart, effective_uid=0
        )

    assert target.read_bytes() == old_content
    assert restart_count == 2


@pytest.mark.parametrize(
    ("usage", "expected_vacuum"),
    [(["500M", "100M"], False), (["56M", "300M", "200M"], True)],
)
def test_bounded_vacuum_runs_only_when_post_activation_usage_exceeds_cap(
    tmp_path: Path, usage: list[str], expected_vacuum: bool
) -> None:
    root = _host_root(tmp_path)
    commands = _HostCommands(root, usage=usage)

    result = retention._configure_journald(
        source=_source(tmp_path), root=root, run=commands, effective_uid=0
    )

    vacuum_calls = [
        call for call in commands.calls if call[:2] == ["journalctl", "--vacuum-time=14days"]
    ]
    assert bool(vacuum_calls) is expected_vacuum
    if expected_vacuum:
        effective_check = commands.calls.index(
            ["systemd-analyze", "cat-config", "systemd/journald.conf"]
        )
        rotate = commands.calls.index(["journalctl", "--rotate"])
        vacuum = commands.calls.index(["journalctl", "--vacuum-time=14days", "--vacuum-size=256M"])
        assert effective_check < rotate < vacuum
        assert result["vacuumed"] is True
    else:
        assert result["vacuumed"] is False


def test_unprivileged_deploy_only_verifies_existing_journald_policy(tmp_path: Path) -> None:
    root = _host_root(tmp_path)
    target = root / retention.DROP_IN_RELATIVE
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(retention.EXPECTED_POLICY)
    commands = _HostCommands(root)

    result = retention._verify_installed_journald(root=root, run=commands)

    assert result["changed"] is False
    assert result["services_restarted"] == []
    assert not any(call[:2] == ["systemctl", "restart"] for call in commands.calls)


def test_unprivileged_journald_verification_validates_source_before_host_access(
    tmp_path: Path,
) -> None:
    root = _host_root(tmp_path)
    commands = _HostCommands(root)
    source = _source(tmp_path, b"[Journal]\nSystemMaxUse=unbounded\n")

    with pytest.raises(retention.RetentionError, match="does not match"):
        retention._verify_installed_journald(source=source, root=root, run=commands)

    assert commands.calls == []


def test_application_log_verification_is_limited_to_backend_worker_and_bot(
    tmp_path: Path,
) -> None:
    commands = _HostCommands(_host_root(tmp_path))

    result = retention._verify_application_logs(commands)

    assert [container["service"] for container in result["application_containers"]] == [
        "backend",
        "worker",
        "bot",
    ]
    assert all(container["max-size"] == "10m" for container in result["application_containers"])
    assert all(container["max-file"] == "5" for container in result["application_containers"])
    encoded = json.dumps(result)
    assert "db" not in encoded
    assert "TELEGRAM_BOT_TOKEN" not in encoded
    assert "dummy-test-value" not in encoded


def test_application_log_verification_fails_on_unbounded_container(tmp_path: Path) -> None:
    commands = _HostCommands(_host_root(tmp_path))
    original = commands.__call__

    def with_unbounded_bot(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        result = original(arguments)
        if arguments[:2] == ["docker", "inspect"] and arguments[-1] == "bot-id":
            return _completed(
                list(arguments), '/fit-mini-app-bot-1|bot|json-file|{"max-file":"3"}\n'
            )
        return result

    with pytest.raises(retention.RetentionError, match="policy is incorrect for service bot"):
        retention._verify_application_logs(with_unbounded_bot)


def test_application_log_verification_rejects_a_changed_default_driver(
    tmp_path: Path,
) -> None:
    commands = _HostCommands(_host_root(tmp_path))
    original = commands.__call__

    def with_changed_default(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if arguments[:2] == ["docker", "info"]:
            return _completed(list(arguments), "journald\n")
        return original(arguments)

    with pytest.raises(retention.RetentionError, match="default logging driver changed"):
        retention._verify_application_logs(with_changed_default)


def test_production_cli_fails_clearly_outside_linux_systemd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retention, "_production_systemd_host", lambda: False)

    with pytest.raises(SystemExit, match="requires a Linux host running systemd"):
        retention.main(["--revision", "a" * 40], output=io.StringIO())


def test_compose_render_has_only_application_logging_limits(tmp_path: Path) -> None:
    compose_path = ROOT / "docker-compose.yml"
    raw_compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    env_file = tmp_path / "compose.env"
    env_file.write_text(
        "POSTGRES_DB=test_db\n"
        "POSTGRES_USER=test_user\n"
        "POSTGRES_PASSWORD=dummy-test-value\n"
        "TELEGRAM_BOT_TOKEN=dummy-test-value\n"
        "BOT_INTERNAL_TOKEN=dummy-test-value\n",
        encoding="utf-8",
    )
    rendered_source = tmp_path / "docker-compose.yml"
    text = compose_path.read_text(encoding="utf-8").replace(
        "env_file: .env", f"env_file: {env_file.as_posix()}"
    )
    rendered_source.write_text(text, encoding="utf-8")

    completed = subprocess.run(
        [
            "docker",
            "compose",
            "--profile",
            "*",
            "--project-directory",
            str(ROOT),
            "--env-file",
            str(env_file),
            "-f",
            str(rendered_source),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, "Docker Compose could not render the production topology"
    rendered = json.loads(completed.stdout)
    services = raw_compose["services"]
    for service in APP_SERVICES:
        assert services[service]["logging"] == {
            "driver": "json-file",
            "options": {"max-size": "10m", "max-file": "5"},
        }
        assert rendered["services"][service]["logging"] == services[service]["logging"]
    for service in PROTECTED_SERVICES | {"setup"}:
        assert "logging" not in services[service]
        assert "logging" not in rendered["services"][service]
    assert set(raw_compose["volumes"]) == {
        "postgres_data",
        "caddy_data",
        "caddy_config",
        "edge_config",
        "bot_polling_lock",
    }
    assert services["db"]["volumes"] == ["postgres_data:/var/lib/postgresql/data"]
    assert all(
        "bot_polling_lock:/var/lock/fitminiapp-bot" in services[name]["volumes"]
        for name in ("bot", "bot-blue", "bot-green")
    )


def test_logging_scope_matches_normal_rollout_ownership() -> None:
    deployment = (ROOT / "scripts/zero_downtime_deploy.py").read_text(encoding="utf-8")
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    single_slot = deployment[deployment.index("def single_slot_deploy(") :]
    blue_green = deployment[
        deployment.index("def deploy(config: DeployConfig)") : deployment.index(
            "def _legacy_running_image"
        )
    ]

    assert "_stop_legacy_services(config)" in single_slot
    assert "_start_legacy_backend(target_env, config)" in single_slot
    assert "_start_legacy_consumers(" in single_slot
    assert '_slot_service("backend", candidate_slot)' in blue_green
    assert "_start_slot_consumers(" in blue_green
    assert '"--rm", "--no-deps", "setup"' in single_slot
    assert all("logging" not in services[name] for name in PROTECTED_SERVICES)


def test_deploy_runs_journald_before_compose_and_checks_app_logs_after_rollout() -> None:
    deploy_script = (ROOT / "scripts/deploy_production.sh").read_text(encoding="utf-8")
    journald_call = "scripts/configure_production_log_retention.py --revision"
    ensure = deploy_script.index(journald_call)
    compose_validation = deploy_script.index("docker compose config --quiet")
    rollout = deploy_script.index("python3 scripts/zero_downtime_deploy.py")
    post_journald = deploy_script.index(journald_call, ensure + len(journald_call))
    post_check = deploy_script.index("--verify-application-logs")
    bot_smoke = deploy_script.index('echo "Checking the public Telegram bot profile"')

    assert ensure < compose_validation < rollout < post_journald < post_check < bot_smoke
    assert (
        'scripts/configure_production_nutrition_label_scan.py .env "$NUTRITION_LABEL_SCAN_ROLLOUT_MARKER"'
        in deploy_script
    )
