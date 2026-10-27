import asyncio
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram.exceptions import TelegramConflictError
from aiogram.types import MenuButtonCommands
from bot.fitminiapp_bot import bot as bot_module
from bot.fitminiapp_bot.bot import PollingConflict, PollingFileLock, StableDispatcher
from bot.fitminiapp_bot.config import Settings as BotSettings
from bot.fitminiapp_bot.logging_config import JsonFormatter
from bot.fitminiapp_bot.public_profile import HIDDEN_COMMANDS, PUBLIC_COMMANDS

BOT_TOKEN = "123456:telegram-bot-secret"
INTERNAL_TOKEN = "backend-internal-secret"


class _FakeSession:
    timeout = 10


class _ConflictingBot:
    id = 123
    session = _FakeSession()

    async def __call__(self, method, **kwargs):
        raise TelegramConflictError(method=method, message="terminated by other getUpdates request")


def test_successful_real_getupdates_iteration_marks_polling_healthy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Only a completed getUpdates round-trip, not Docker Up, proves health."""
    path = tmp_path / "polling.json"
    monkeypatch.setattr(bot_module.settings, "bot_polling_health_path", str(path))

    class ReturnedUpdatesBot:
        id = 123
        session = _FakeSession()

        async def __call__(self, method, **kwargs):
            return [SimpleNamespace(update_id=7)]

    async def run() -> None:
        listener = StableDispatcher._listen_updates(ReturnedUpdatesBot())
        try:
            assert (await anext(listener)).update_id == 7
        finally:
            await listener.aclose()

    asyncio.run(run())
    payload = json.loads(path.read_text())
    assert payload["state"] == "healthy"
    assert payload["evidence"] == "getupdates_success"


def test_polling_conflict_reports_unhealthy_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "polling.json"
    monkeypatch.setattr(bot_module.settings, "bot_polling_health_path", str(path))

    async def run() -> None:
        listener = StableDispatcher._listen_updates(_ConflictingBot())
        with pytest.raises(PollingConflict):
            await anext(listener)

    asyncio.run(run())
    payload = json.loads(path.read_text())
    assert payload["state"] == "unhealthy"
    assert payload["evidence"] == "polling_conflict"


def test_dispatcher_escalates_polling_conflict_without_retrying():
    async def consume_updates() -> None:
        updates = StableDispatcher._listen_updates(_ConflictingBot())

        with pytest.raises(PollingConflict, match="telegram_polling_conflict"):
            await anext(updates)

    asyncio.run(consume_updates())


def test_bot_formatter_preserves_polling_conflict_marker() -> None:
    record = logging.LogRecord(
        name="bot.fitminiapp_bot.bot",
        level=logging.CRITICAL,
        pathname=__file__,
        lineno=1,
        msg="telegram_polling_conflict",
        args=(),
        exc_info=None,
    )
    record.retry_seconds = 300

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "telegram_polling_conflict"
    assert payload["retry_seconds"] == 300


def test_polling_lock_filename_is_stable_and_does_not_expose_token(tmp_path: Path):
    first = PollingFileLock(str(tmp_path), "secret-token")
    second = PollingFileLock(str(tmp_path), "secret-token")

    assert first.path == second.path
    assert "secret-token" not in first.path.name


def test_polling_lock_waiter_takes_over_after_release(tmp_path: Path, monkeypatch):
    if bot_module.fcntl is None:
        pytest.skip("fcntl is only available in the Linux production environment")

    async def exercise_takeover() -> None:
        leader = PollingFileLock(str(tmp_path), "shared-token")
        standby = PollingFileLock(str(tmp_path), "shared-token")
        await leader.acquire()

        async def release_leader(_seconds: float) -> None:
            leader.release()

        monkeypatch.setattr(bot_module.asyncio, "sleep", release_leader)
        try:
            await standby.acquire()
            assert standby._file is not None
        finally:
            leader.release()
            standby.release()

    asyncio.run(exercise_takeover())


@pytest.mark.parametrize("status_code", [429, 500])
def test_timezone_delivery_reports_backend_http_errors(
    status_code: int,
    monkeypatch,
    caplog,
):
    real_async_client = httpx.AsyncClient

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request, json={"detail": "temporary"})

    transport = httpx.MockTransport(respond)

    def client_factory(*, timeout: int):
        return real_async_client(timeout=timeout, transport=transport)

    monkeypatch.setattr(bot_module.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(
        bot_module.settings,
        "backend_internal_url",
        "https://backend.example/raw-url-secret",
    )
    monkeypatch.setattr(bot_module.settings, "bot_internal_token", INTERNAL_TOKEN)
    telegram_user = SimpleNamespace(id=123, username="tester", first_name="Test", last_name="User")

    with caplog.at_level(logging.ERROR, logger=bot_module.__name__):
        result = asyncio.run(bot_module.save_timezone_from_bot(telegram_user, "Europe/Moscow"))

    assert result is False
    record = caplog.records[-1]
    rendered = JsonFormatter().format(record)
    payload = json.loads(rendered)
    assert record.exc_info is None
    assert payload["message"] == "timezone_backend_update_failed"
    assert payload["error_code"] == f"http_status:{status_code}"
    assert INTERNAL_TOKEN not in rendered
    assert "backend.example" not in rendered
    assert "raw-url-secret" not in rendered


def test_timezone_delivery_reports_backend_timeout(monkeypatch):
    real_async_client = httpx.AsyncClient

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("backend timed out", request=request)

    transport = httpx.MockTransport(timeout)

    def client_factory(*, timeout: int):
        return real_async_client(timeout=timeout, transport=transport)

    monkeypatch.setattr(bot_module.httpx, "AsyncClient", client_factory)
    telegram_user = SimpleNamespace(id=123, username=None, first_name="Test", last_name=None)

    assert asyncio.run(bot_module.save_timezone_from_bot(telegram_user, "Europe/Moscow")) is False


def test_link_telegram_delivery_sends_identity_to_internal_api(monkeypatch):
    real_async_client = httpx.AsyncClient
    captured: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, request=request, json={"status": "linked"})

    transport = httpx.MockTransport(respond)

    def client_factory(*, timeout: int):
        return real_async_client(timeout=timeout, transport=transport)

    monkeypatch.setattr(bot_module.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(bot_module.settings, "bot_internal_token", INTERNAL_TOKEN)
    telegram_user = SimpleNamespace(
        id=12345,
        username="linked_user",
        first_name="Linked",
        last_name="User",
    )

    outcome = asyncio.run(bot_module.link_telegram_from_bot(telegram_user, "a" * 43))

    assert outcome == "linked"
    assert captured["payload"] == {
        "token": "a" * 43,
        "telegram_user_id": 12345,
        "username": "linked_user",
        "first_name": "Linked",
        "last_name": "User",
    }
    assert captured["headers"]["x-bot-token"] == INTERNAL_TOKEN


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(400, "invalid"), (409, "conflict"), (500, "failed")],
)
def test_link_telegram_delivery_maps_safe_outcomes(status_code, expected, monkeypatch):
    real_async_client = httpx.AsyncClient

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request, json={"detail": "hidden"})

    transport = httpx.MockTransport(respond)

    def client_factory(*, timeout: int):
        return real_async_client(timeout=timeout, transport=transport)

    monkeypatch.setattr(bot_module.httpx, "AsyncClient", client_factory)
    telegram_user = SimpleNamespace(id=12345, username=None, first_name="Test", last_name=None)

    assert asyncio.run(bot_module.link_telegram_from_bot(telegram_user, "b" * 43)) == expected


def test_start_link_payload_is_validated_and_reports_success(monkeypatch):
    assert bot_module.telegram_link_token("trainer_other") is None
    assert bot_module.telegram_link_token("link_short") is None
    assert bot_module.telegram_link_token(f"link_{'c' * 43}") == "c" * 43

    message = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        bot=object(),
        answer=AsyncMock(),
    )
    monkeypatch.setattr(bot_module, "link_telegram_from_bot", AsyncMock(return_value="linked"))
    monkeypatch.setattr(bot_module, "set_mini_app_menu_button", AsyncMock(return_value=True))
    feedback_start = AsyncMock(return_value=True)
    monkeypatch.setattr(bot_module, "handle_feedback_start_payload", feedback_start)

    asyncio.run(
        bot_module.start(
            message,
            SimpleNamespace(args=f"link_{'c' * 43}"),
            SimpleNamespace(clear=AsyncMock()),
        )
    )

    assert message.answer.await_count == 1
    assert "одни и те же данные" in message.answer.await_args.args[0]
    feedback_start.assert_not_awaited()


def test_public_menu_uses_stable_https_url_and_mobile_friendly_plain_labels(monkeypatch):
    monkeypatch.setattr(
        bot_module.settings,
        "frontend_base_url",
        "https://app.your-fitness-coach.ru",
    )

    assert bot_module.mini_app_url() == "https://app.your-fitness-coach.ru/app"
    assert "?" not in bot_module.mini_app_url()
    keyboard = bot_module.main_menu_keyboard(bot_module.settings.frontend_base_url)
    labels = [row[0].text for row in keyboard.inline_keyboard]
    assert labels == [
        "Открыть приложение",
        "Помощь и обратная связь",
        "Настройки",
        "Что умеет бот",
    ]
    assert all(len(label) <= 32 for label in labels)


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/app",
        "https://127.0.0.1/app",
        "https://10.0.0.5/app",
        "https://app.your-fitness-coach.ru/app?preview=1",
        "https://app.your-fitness-coach.ru:8443/app",
        "https://app.internal/app",
    ],
)
def test_public_urls_reject_noncanonical_or_private_targets(url: str) -> None:
    assert bot_module.is_https_url(url) is False


def test_public_command_source_excludes_hidden_commands() -> None:
    visible = [item.command for item in PUBLIC_COMMANDS]

    assert visible == ["start", "app", "support", "settings", "help", "privacy"]
    assert set(HIDDEN_COMMANDS) == {
        "feedback",
        "cancel",
        "timezone",
        "digest_review",
        "news_off",
        "unsubscribe",
        "stop_news",
    }
    assert "news" not in visible
    settings_command = next(item for item in PUBLIC_COMMANDS if item.command == "settings")
    assert settings_command.description == "Настройки и уведомления"


def test_settings_command_opens_canonical_preferences_and_preserves_timezone_access(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        bot_module.settings,
        "frontend_base_url",
        "https://app.your-fitness-coach.ru",
    )
    digest_settings = AsyncMock()
    monkeypatch.setattr(bot_module, "send_digest_settings", digest_settings)
    message = SimpleNamespace(answer=AsyncMock())

    asyncio.run(bot_module.settings_command(message))

    assert "/timezone" in message.answer.await_args.args[0]
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    button = keyboard.inline_keyboard[0][0]
    assert button.text == "Открыть настройки уведомлений"
    assert button.web_app.url == (
        "https://app.your-fitness-coach.ru/app?section=profile#profile-notifications"
    )
    digest_settings.assert_awaited_once_with(message)


def test_unknown_start_payload_returns_main_menu_without_raw_error(monkeypatch):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        bot=object(),
        answer=AsyncMock(),
    )
    monkeypatch.setattr(bot_module, "handle_feedback_start_payload", AsyncMock(return_value=False))
    monkeypatch.setattr(bot_module, "set_mini_app_menu_button", AsyncMock(return_value=True))

    asyncio.run(
        bot_module.start(
            message,
            SimpleNamespace(args="unexpected_raw_payload"),
            SimpleNamespace(clear=AsyncMock()),
        )
    )

    text = message.answer.await_args.args[0]
    assert "не распознан" in text
    assert "unexpected_raw_payload" not in text
    assert (
        message.answer.await_args.kwargs["reply_markup"]
        .inline_keyboard[0][0]
        .web_app.url.endswith("/app")
    )


def test_app_command_uses_canonical_https_button(monkeypatch):
    monkeypatch.setattr(
        bot_module.settings,
        "frontend_base_url",
        "https://app.your-fitness-coach.ru",
    )
    message = SimpleNamespace(answer=AsyncMock())

    asyncio.run(bot_module.app_command(message))

    keyboard = message.answer.await_args.kwargs["reply_markup"]
    button = keyboard.inline_keyboard[0][0]
    assert button.text == "Открыть приложение"
    assert button.web_app.url == "https://app.your-fitness-coach.ru/app"


def test_unknown_command_returns_recovery_menu_without_echo() -> None:
    message = SimpleNamespace(text="/unknown secret", answer=AsyncMock())

    asyncio.run(bot_module.unknown_command(message))

    assert "Такой команды нет" in message.answer.await_args.args[0]
    assert "secret" not in message.answer.await_args.args[0]
    assert message.answer.await_args.kwargs["reply_markup"] is not None


def test_privacy_command_uses_valid_config_or_controlled_unavailable_state(monkeypatch):
    message = SimpleNamespace(answer=AsyncMock())
    monkeypatch.setattr(bot_module.settings, "privacy_policy_url", "http://invalid.example/privacy")
    asyncio.run(bot_module.privacy_command(message))
    assert "недоступна" in message.answer.await_args.args[0]

    message.answer.reset_mock()
    monkeypatch.setattr(
        bot_module.settings,
        "privacy_policy_url",
        "https://your-fitness-coach.ru/privacy",
    )
    asyncio.run(bot_module.privacy_command(message))
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].url == "https://your-fitness-coach.ru/privacy"


def test_menu_button_migration_updates_legacy_override_and_verifies(monkeypatch):
    target = bot_module.menu_button(bot_module.settings.frontend_base_url)
    fake_bot = SimpleNamespace(
        get_chat_menu_button=AsyncMock(side_effect=[MenuButtonCommands(), target]),
        set_chat_menu_button=AsyncMock(),
    )

    assert asyncio.run(bot_module.set_mini_app_menu_button(fake_bot, chat_id=101)) is True
    fake_bot.set_chat_menu_button.assert_awaited_once()
    assert fake_bot.set_chat_menu_button.await_args.kwargs["chat_id"] == 101


def test_menu_button_api_timeout_is_bounded(monkeypatch):
    fake_bot = SimpleNamespace(
        get_chat_menu_button=AsyncMock(side_effect=TimeoutError("telegram timed out")),
        set_chat_menu_button=AsyncMock(),
    )

    assert asyncio.run(bot_module.set_mini_app_menu_button(fake_bot, chat_id=101)) is False
    fake_bot.set_chat_menu_button.assert_not_awaited()


def test_support_start_payload_runs_before_generic_product_entry(monkeypatch):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        bot=object(),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(clear=AsyncMock())
    feedback_start = AsyncMock(return_value=True)
    menu_button = AsyncMock(return_value=True)
    monkeypatch.setattr(bot_module, "handle_feedback_start_payload", feedback_start)
    monkeypatch.setattr(bot_module, "set_mini_app_menu_button", menu_button)

    asyncio.run(bot_module.start(message, SimpleNamespace(args="support_bug"), state))

    feedback_start.assert_awaited_once_with(message, state, "support_bug")
    menu_button.assert_not_awaited()


def test_runtime_supports_one_active_bot_owner_across_deployment_slots() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    deploy_script = (root / "scripts" / "deploy_production.sh").read_text(encoding="utf-8")
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    assert compose.count("TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}") == 3
    assert compose.count("TELEGRAM_BOT_PROXY_URL: ${TELEGRAM_BOT_PROXY_URL:-}") == 3
    assert compose.count("BOT_POLLING_LOCK_DIR: /var/lock/fitminiapp-bot") == 3
    assert "bot-blue:" in compose
    assert "bot-green:" in compose
    assert "name: fitminiapp_bot_polling_lock" in compose
    assert 'profiles: ["production-slots"]' in compose
    assert "support-bot" not in compose
    assert "support-bot" not in deploy_script
    assert "scripts/zero_downtime_deploy.py" in deploy_script
    assert deploy_script.count("python -m fitminiapp_bot.profile_sync check") == 1
    assert deploy_script.count("python -m fitminiapp_bot.profile_sync apply") == 1
    assert deploy_script.count("docker compose run --rm --no-deps") == 2
    assert (
        deploy_script.count(
            "BOT_PROFILE_SYNC_TOTAL_TIMEOUT_SECONDS=$PROFILE_SYNC_TOTAL_TIMEOUT_SECONDS"
        )
        == 2
    )
    assert deploy_script.index("profile_sync check") > deploy_script.index(
        "scripts/zero_downtime_deploy.py"
    )
    assert "Public Telegram Bot API fields were applied and read back" in deploy_script
    assert 'profile_sync_result="pending"' in deploy_script
    assert 'if [[ "$profile_apply_status" -eq 0 ]]' in deploy_script
    assert 'identity_status == "API_ERROR"' in deploy_script
    assert '"API_ERROR" in field_statuses' in deploy_script
    assert 'exit "$profile_check_status"' in deploy_script
    assert "Telegram Bot API is unavailable; metadata remains pending" in deploy_script
    assert "SUPPORT_BOT_" not in env_example
    assert "SUPPORT_ADMIN_TELEGRAM_USER_IDS" not in compose
    assert (
        type(bot_module.settings).model_fields["bot_token"].validation_alias == "TELEGRAM_BOT_TOKEN"
    )


def test_production_bot_config_fails_closed_on_placeholder_credentials() -> None:
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        BotSettings(
            app_env="prod",
            TELEGRAM_BOT_TOKEN="change-me",
            bot_internal_token="a-valid-internal-token-that-is-long-enough",
        )

    with pytest.raises(ValueError, match="BOT_INTERNAL_TOKEN"):
        BotSettings(
            app_env="prod",
            TELEGRAM_BOT_TOKEN="123456:configured-token",
            bot_internal_token="replace-with-a-token",
        )


def test_production_bot_config_requires_https_public_origin() -> None:
    with pytest.raises(ValueError, match="FRONTEND_BASE_URL"):
        BotSettings(
            app_env="prod",
            TELEGRAM_BOT_TOKEN="123456:configured-token",
            bot_internal_token="a-valid-internal-token-that-is-long-enough",
            frontend_base_url="http://app.example.test",
        )


def test_json_formatter_excludes_arbitrary_message_and_exception_values() -> None:
    try:
        raise RuntimeError(
            f"request to https://api.telegram.org/bot{BOT_TOKEN}/getUpdates "
            f"used header {INTERNAL_TOKEN}"
        )
    except RuntimeError:
        record = logging.LogRecord(
            name="aiogram.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg=f"failed https://api.telegram.org/bot{BOT_TOKEN}/getUpdates with {INTERNAL_TOKEN}",
            args=(),
            exc_info=sys.exc_info(),
        )

    rendered = JsonFormatter().format(record)
    payload = json.loads(rendered)

    assert payload["message"] == "application_log"
    assert payload["exception_type"] == "RuntimeError"
    assert "exception" not in payload
    assert BOT_TOKEN not in rendered
    assert INTERNAL_TOKEN not in rendered
    assert "api.telegram.org" not in rendered
