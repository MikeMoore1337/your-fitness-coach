from pathlib import Path

import pytest
import yaml

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


@pytest.mark.parametrize(
    "name",
    [
        "backend",
        "backend-blue",
        "backend-green",
        "setup",
        "worker",
        "worker-blue",
        "worker-green",
        "bot",
        "bot-blue",
        "bot-green",
    ],
)
def test_application_services_cannot_gain_linux_privileges(name: str) -> None:
    service = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"][name]

    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]


def test_edge_preserves_caddy_file_capabilities_and_deployment_scratch_path() -> None:
    service = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]["edge"]

    assert service["security_opt"] == ["no-new-privileges:true"]
    assert "cap_drop" not in service
    assert not service.get("read_only", False)
    assert "edge_config:/config" in service["volumes"]


@pytest.mark.parametrize("name", ["bot", "bot-blue", "bot-green"])
def test_read_only_bot_keeps_shared_writable_lock_and_state_volume(name: str) -> None:
    service = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"][name]

    assert service["read_only"] is True
    assert "bot_polling_lock:/var/lock/fitminiapp-bot" in service["volumes"]
    assert service["environment"]["BOT_POLLING_LOCK_DIR"] == "/var/lock/fitminiapp-bot"
    assert (
        "/var/lock/fitminiapp-bot/profile-sync-state.json"
        in service["environment"]["BOT_PROFILE_SYNC_STATE_PATH"]
    )


def test_ci_exercises_read_only_bot_and_writable_volume_before_scan() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["containers"]["steps"]
    probe = next(
        step["run"] for step in steps if step.get("name") == "Verify bot runtime image contract"
    )

    assert "--read-only --cap-drop ALL --security-opt no-new-privileges:true" in probe
    assert "--mount type=volume,destination=/var/lock/fitminiapp-bot" in probe
    assert "errno.EROFS" in probe
    assert "_write_avatar_state" in probe
    assert "fcntl.flock" in probe
    assert "await standby.acquire()" in probe
