from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from bot.fitminiapp_bot import bot as bot_runtime
from bot.fitminiapp_bot import feedback, news_editorial


class FakeMessage:
    def __init__(self, *, chat_type: str = "private") -> None:
        self.chat = SimpleNamespace(type=chat_type)
        self.text = (
            "Материал aaaaaaaa · text r7 · image r2\n"
            "Канал: @yfc_test_news (staging)\n\n"
            "Служебное представление text revision (не финальный preview канала)"
        )
        self.caption = None
        self.edit_reply_markup = AsyncMock()
        self.edit_text = AsyncMock()
        self.edit_caption = AsyncMock()
        self.answer = AsyncMock()


def _callback(*, user_id: int, data: str = f"news:a:{'a' * 32}"):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        message=FakeMessage(),
        data=data,
        answer=AsyncMock(),
    )


def test_generic_user_cannot_forge_news_callback(monkeypatch) -> None:
    callback = _callback(user_id=7999)
    backend_call = AsyncMock()
    monkeypatch.setattr(news_editorial, "moderate_news_draft", backend_call)
    monkeypatch.setattr(news_editorial, "Message", FakeMessage)

    asyncio.run(news_editorial.news_editorial_callback(callback))

    backend_call.assert_not_awaited()
    callback.answer.assert_awaited_once_with("Действие доступно только редактору", show_alert=True)


def test_admin_callback_is_private_revision_bound_and_removes_stale_buttons(monkeypatch) -> None:
    callback = _callback(user_id=7001)
    backend_call = AsyncMock(return_value="queued")
    monkeypatch.setattr(news_editorial, "moderate_news_draft", backend_call)
    monkeypatch.setattr(news_editorial, "Message", FakeMessage)

    asyncio.run(news_editorial.news_editorial_callback(callback))

    backend_call.assert_awaited_once_with(
        draft_id="a" * 32,
        admin_telegram_user_id=7001,
        action="accept_for_design",
    )
    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    callback.answer.assert_awaited_once_with(
        "Новая revision поставлена в очередь", show_alert=False
    )


def test_malformed_news_callback_never_calls_backend(monkeypatch) -> None:
    callback = _callback(user_id=7001, data="news:publish:anything")
    backend_call = AsyncMock()
    monkeypatch.setattr(news_editorial, "moderate_news_draft", backend_call)
    monkeypatch.setattr(news_editorial, "Message", FakeMessage)

    asyncio.run(news_editorial.news_editorial_callback(callback))

    backend_call.assert_not_awaited()
    callback.answer.assert_awaited_once_with("Некорректное действие", show_alert=True)


def test_destructive_news_action_requires_confirmation(monkeypatch) -> None:
    callback = _callback(user_id=7001, data=f"newsp:x:{'a' * 32}:2")
    backend_call = AsyncMock()
    state = AsyncMock()
    monkeypatch.setattr(news_editorial, "moderate_news_draft", backend_call)
    monkeypatch.setattr(news_editorial, "Message", FakeMessage)

    asyncio.run(news_editorial.news_publishing_callback(callback, state))

    backend_call.assert_not_awaited()
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


def test_publish_confirmation_stays_on_same_card_and_keeps_exact_preview(monkeypatch) -> None:
    artifact_hash = "f" * 16
    callback = _callback(user_id=7001, data=f"newsp:p:{'a' * 32}:2:{artifact_hash}")
    state = AsyncMock()
    monkeypatch.setattr(news_editorial, "Message", FakeMessage)

    asyncio.run(news_editorial.news_publishing_callback(callback, state))

    callback.message.answer.assert_not_awaited()
    state.set_state.assert_awaited_once_with(
        news_editorial.NewsEditorialStates.awaiting_publish_confirmation
    )
    markup = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    callback_values = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert f"newsp:c:{'a' * 32}:2:{artifact_hash}" in callback_values
    assert f"newsp:n:{'a' * 32}:2:{artifact_hash}" in callback_values
    assert all(value is not None and len(value.encode()) <= 64 for value in callback_values)
    callback.answer.assert_awaited_once_with()


def test_schedule_parser_accepts_nested_iana_timezone() -> None:
    match = news_editorial.SCHEDULE_INPUT_PATTERN.fullmatch(
        "2026-08-27 12:30 America/Argentina/Buenos_Aires"
    )
    assert match is not None
    assert match.group(3) == "America/Argentina/Buenos_Aires"


def test_hashless_publish_callback_is_rejected_as_stale(monkeypatch) -> None:
    callback = _callback(user_id=7001, data=f"newsp:p:{'a' * 32}:2")
    state = AsyncMock()
    backend_call = AsyncMock()
    monkeypatch.setattr(news_editorial, "Message", FakeMessage)
    monkeypatch.setattr(news_editorial, "revision_action", backend_call)

    asyncio.run(news_editorial.news_publishing_callback(callback, state))

    backend_call.assert_not_awaited()
    callback.answer.assert_awaited_once_with(
        "Preview устарел: откройте новую карточку", show_alert=True
    )


def test_confirmed_publish_calls_exact_hash_bound_revision(monkeypatch) -> None:
    artifact_hash = "d" * 16
    callback = _callback(user_id=7001, data=f"newsp:c:{'a' * 32}:2:{artifact_hash}")
    state = AsyncMock()
    state.get_data.return_value = {
        "mode": "publish_confirmation",
        "draft_id": "a" * 32,
        "image_revision": 2,
        "artifact_hash": artifact_hash,
        "started_at": news_editorial.time.monotonic(),
    }
    backend_call = AsyncMock(return_value=("queued", []))
    monkeypatch.setattr(news_editorial, "Message", FakeMessage)
    monkeypatch.setattr(news_editorial, "revision_action", backend_call)

    asyncio.run(news_editorial.news_publishing_callback(callback, state))

    backend_call.assert_awaited_once_with(
        draft_id="a" * 32,
        admin_telegram_user_id=7001,
        action="publish",
        image_revision=2,
        artifact_hash=artifact_hash,
    )
    callback.answer.assert_awaited_once_with("Публикация поставлена в очередь", show_alert=False)


def test_publish_confirmation_cancel_restores_actions_on_same_card(monkeypatch) -> None:
    artifact_hash = "d" * 16
    callback = _callback(user_id=7001, data=f"newsp:n:{'a' * 32}:2:{artifact_hash}")
    state = AsyncMock()
    state.get_data.return_value = {
        "mode": "publish_confirmation",
        "draft_id": "a" * 32,
        "image_revision": 2,
        "artifact_hash": artifact_hash,
        "started_at": news_editorial.time.monotonic(),
    }
    monkeypatch.setattr(news_editorial, "Message", FakeMessage)

    asyncio.run(news_editorial.news_publishing_callback(callback, state))

    state.clear.assert_awaited_once_with()
    callback.message.answer.assert_not_awaited()
    restored = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert restored.inline_keyboard[0][0].callback_data == (f"newsp:p:{'a' * 32}:2:{artifact_hash}")
    callback.answer.assert_awaited_once_with("Отменено")


def test_schedule_input_requires_explicit_channel_time_and_hash_confirmation(monkeypatch) -> None:
    artifact_hash = "e" * 16
    state = AsyncMock()
    state.get_data.return_value = {
        "draft_id": "a" * 32,
        "image_revision": 3,
        "artifact_hash": artifact_hash,
        "channel_line": "Канал: @yfc_test_news (staging)",
        "started_at": news_editorial.time.monotonic(),
    }
    message = FakeMessage()
    message.from_user = SimpleNamespace(id=7001)
    message.text = "2026-08-27 12:30 Europe/Moscow"
    backend_call = AsyncMock()
    monkeypatch.setattr(news_editorial, "revision_action", backend_call)

    asyncio.run(news_editorial.news_schedule_input(message, state))

    backend_call.assert_not_awaited()
    state.set_state.assert_awaited_once_with(
        news_editorial.NewsEditorialStates.awaiting_schedule_confirmation
    )
    saved = state.set_data.await_args.args[0]
    assert saved["scheduled_local"] == "2026-08-27T12:30:00"
    assert saved["timezone"] == "Europe/Moscow"
    confirmation = message.answer.await_args.args[0]
    assert "Канал: @yfc_test_news (staging)" in confirmation
    assert "2026-08-27 12:30" in confirmation
    assert "Europe/Moscow" in confirmation
    assert artifact_hash in confirmation
    markup = message.answer.await_args.kwargs["reply_markup"]
    callback_values = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callback_values == [f"newsp:z:{'a' * 32}:3:{artifact_hash}"]


def test_confirmed_schedule_calls_exact_hash_bound_revision(monkeypatch) -> None:
    artifact_hash = "e" * 16
    callback = _callback(user_id=7001, data=f"newsp:z:{'a' * 32}:3:{artifact_hash}")
    state = AsyncMock()
    state.get_data.return_value = {
        "draft_id": "a" * 32,
        "image_revision": 3,
        "artifact_hash": artifact_hash,
        "scheduled_local": "2026-08-27T12:30:00",
        "timezone": "Europe/Moscow",
        "started_at": news_editorial.time.monotonic(),
    }
    backend_call = AsyncMock(return_value=("scheduled", []))
    monkeypatch.setattr(news_editorial, "Message", FakeMessage)
    monkeypatch.setattr(news_editorial, "revision_action", backend_call)

    asyncio.run(news_editorial.news_publishing_callback(callback, state))

    backend_call.assert_awaited_once_with(
        draft_id="a" * 32,
        admin_telegram_user_id=7001,
        action="schedule",
        image_revision=3,
        artifact_hash=artifact_hash,
        scheduled_local="2026-08-27T12:30:00",
        timezone="Europe/Moscow",
    )
    state.clear.assert_awaited_once_with()
    callback.answer.assert_awaited_once_with("Публикация запланирована", show_alert=False)


def test_uncertain_reconcile_keeps_exact_snapshot_id(monkeypatch) -> None:
    callback = _callback(user_id=7001, data=f"newsrec:r:{'b' * 32}")
    state = AsyncMock()
    monkeypatch.setattr(news_editorial, "Message", FakeMessage)

    asyncio.run(news_editorial.news_reconcile_callback(callback, state))

    state.set_state.assert_awaited_once_with(
        news_editorial.NewsEditorialStates.awaiting_reconcile_message_id
    )
    saved = state.set_data.await_args.args[0]
    assert saved["snapshot_id"] == "b" * 32
    callback.answer.assert_awaited_once_with()


def test_uncertain_retry_calls_exact_owner_bound_snapshot(monkeypatch) -> None:
    callback = _callback(user_id=7001, data=f"newsrec:t:{'c' * 32}")
    state = AsyncMock()
    retry = AsyncMock(return_value="queued")
    monkeypatch.setattr(news_editorial, "Message", FakeMessage)
    monkeypatch.setattr(news_editorial, "retry_uncertain_publication", retry)

    asyncio.run(news_editorial.news_reconcile_callback(callback, state))

    retry.assert_awaited_once_with(
        snapshot_id="c" * 32,
        admin_telegram_user_id=7001,
    )
    state.set_state.assert_not_awaited()
    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    callback.answer.assert_awaited_once_with("Повтор поставлен в очередь", show_alert=False)


def test_retry_client_preserves_cancelled_status(monkeypatch) -> None:
    real_async_client = httpx.AsyncClient

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json={"status": "cancelled"})

    transport = httpx.MockTransport(respond)

    def client_factory(*, timeout: int):
        return real_async_client(timeout=timeout, transport=transport)

    monkeypatch.setattr(news_editorial.httpx, "AsyncClient", client_factory)

    status = asyncio.run(
        news_editorial.retry_uncertain_publication(
            snapshot_id="c" * 32,
            admin_telegram_user_id=7001,
        )
    )

    assert status == "cancelled"


def test_uncertain_retry_reports_retired_snapshot_cancellation(monkeypatch) -> None:
    callback = _callback(user_id=7001, data=f"newsrec:t:{'c' * 32}")
    state = AsyncMock()
    retry = AsyncMock(return_value="cancelled")
    monkeypatch.setattr(news_editorial, "Message", FakeMessage)
    monkeypatch.setattr(news_editorial, "retry_uncertain_publication", retry)

    asyncio.run(news_editorial.news_reconcile_callback(callback, state))

    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    callback.answer.assert_awaited_once_with("Устаревшая публикация отменена", show_alert=True)


def test_news_fsm_router_precedes_generic_support_handlers() -> None:
    assert bot_runtime.dp.sub_routers.index(news_editorial.router) < (
        bot_runtime.dp.sub_routers.index(feedback.router)
    )
