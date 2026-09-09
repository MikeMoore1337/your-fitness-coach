from __future__ import annotations

import re
import time
from io import BytesIO
from typing import Literal

import httpx
from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .config import settings

router = Router()
NEWS_CALLBACK_PATTERN = re.compile(r"news:([sdra]):([0-9a-f]{32})\Z")
PUBLISHING_CALLBACK_PATTERN = re.compile(
    r"newsp:([pcesiunvxqz]):([0-9a-f]{32}):(\d{1,5})(?::([0-9a-f]{16}))?\Z"
)
POST_CALLBACK_PATTERN = re.compile(r"newspost:([edc]):([0-9a-f]{32})\Z")
RECONCILE_CALLBACK_PATTERN = re.compile(r"newsrec:([rt]):([0-9a-f]{32})\Z")
SCHEDULE_INPUT_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) ([A-Za-z_+-]+(?:/[A-Za-z0-9_+-]+)+)\Z"
)
NEWS_INPUT_TTL_SECONDS = 15 * 60
ACTION_BY_CODE: dict[str, Literal["skip", "defer", "regenerate", "accept_for_design"]] = {
    "s": "skip",
    "d": "defer",
    "r": "regenerate",
    "a": "accept_for_design",
}
STATUS_TEXT = {
    "accepted": "Решение сохранено",
    "queued": "Новая revision поставлена в очередь",
    "deferred": "Черновик отложен",
    "already_processed": "Это действие уже учтено",
    "stale": "Revision уже устарела",
    "limit_reached": "Лимит перегенераций исчерпан",
    "unavailable": "Черновик недоступен",
    "scheduled": "Публикация запланирована",
    "already_queued": "Эта revision уже поставлена на публикацию",
    "publishing_disabled": "Публикация отключена или канал не настроен",
    "quality_blocked": "Проверка качества не пройдена",
    "schedule_invalid": "Дата, время или часовой пояс недопустимы",
}


class NewsEditorialStates(StatesGroup):
    awaiting_text = State()
    awaiting_schedule = State()
    awaiting_schedule_confirmation = State()
    awaiting_publish_confirmation = State()
    awaiting_image = State()
    awaiting_post_text = State()
    awaiting_reconcile_message_id = State()


async def moderate_news_draft(
    *,
    draft_id: str,
    admin_telegram_user_id: int,
    action: str,
) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.backend_internal_url.rstrip('/')}/api/v1/bot/news/drafts/"
                f"{draft_id}/moderate",
                headers={"X-Bot-Token": settings.bot_internal_token},
                json={
                    "admin_telegram_user_id": admin_telegram_user_id,
                    "action": action,
                },
            )
    except httpx.HTTPError:
        return "unavailable"
    if response.status_code == 403:
        return "forbidden"
    if not response.is_success:
        return "unavailable"
    try:
        status = response.json().get("status")
    except ValueError:
        return "unavailable"
    return status if status in STATUS_TEXT else "unavailable"


async def revision_action(
    *,
    draft_id: str,
    admin_telegram_user_id: int,
    action: str,
    image_revision: int,
    artifact_hash: str | None = None,
    scheduled_local: str | None = None,
    timezone: str | None = None,
) -> tuple[str, list[str]]:
    body: dict[str, object] = {
        "admin_telegram_user_id": admin_telegram_user_id,
        "action": action,
        "expected_image_revision": image_revision,
    }
    if artifact_hash is not None:
        body["expected_artifact_hash"] = artifact_hash
    if scheduled_local is not None:
        body["scheduled_local"] = scheduled_local
    if timezone is not None:
        body["timezone"] = timezone
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{settings.backend_internal_url.rstrip('/')}/api/v1/bot/news/drafts/"
                f"{draft_id}/actions",
                headers={"X-Bot-Token": settings.bot_internal_token},
                json=body,
            )
        payload = response.json() if response.is_success else {}
    except httpx.HTTPError, ValueError:
        return "unavailable", []
    status = payload.get("status")
    blockers = payload.get("blockers", [])
    return (
        status if isinstance(status, str) and status in STATUS_TEXT else "unavailable",
        [value for value in blockers if isinstance(value, str)]
        if isinstance(blockers, list)
        else [],
    )


async def post_action(
    *,
    snapshot_id: str,
    admin_telegram_user_id: int,
    action: str,
    text: str | None = None,
) -> str:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{settings.backend_internal_url.rstrip('/')}/api/v1/bot/news/publications/"
                f"{snapshot_id}/post-action",
                headers={"X-Bot-Token": settings.bot_internal_token},
                json={
                    "admin_telegram_user_id": admin_telegram_user_id,
                    "action": action,
                    "text": text,
                },
            )
        payload = response.json() if response.is_success else {}
    except httpx.HTTPError, ValueError:
        return "unavailable"
    status = payload.get("status")
    return status if status in {"updated", "deleted", "stale", "invalid"} else "unavailable"


async def retry_uncertain_publication(
    *,
    snapshot_id: str,
    admin_telegram_user_id: int,
) -> str:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{settings.backend_internal_url.rstrip('/')}/api/v1/bot/news/publications/"
                f"{snapshot_id}/retry",
                headers={"X-Bot-Token": settings.bot_internal_token},
                json={"admin_telegram_user_id": admin_telegram_user_id},
            )
        payload = response.json() if response.is_success else {}
    except httpx.HTTPError, ValueError:
        return "unavailable"
    status = payload.get("status")
    return status if status in {"queued", "cancelled"} else "unavailable"


def _state_expired(data: dict[str, object]) -> bool:
    started_at = data.get("started_at")
    return not isinstance(started_at, (int, float)) or time.monotonic() - started_at > (
        NEWS_INPUT_TTL_SECONDS
    )


def _control_channel_line(message: Message) -> str:
    text = getattr(message, "text", None) or getattr(message, "caption", None)
    if isinstance(text, str):
        for line in text.splitlines():
            if line.startswith("Канал: "):
                return line
    return "Канал: server-side config"


def _control_revision_line(message: Message, *, draft_id: str, image_revision: int) -> str:
    text = getattr(message, "text", None) or getattr(message, "caption", None)
    if isinstance(text, str):
        for line in text.splitlines():
            if line.startswith("Материал ") and " · text r" in line and " · image r" in line:
                return line
    return f"Материал {draft_id[:8]} · image r{image_revision}"


def _publish_confirmation_markup(
    *, draft_id: str, image_revision: int, artifact_hash: str
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить публикацию",
                    callback_data=f"newsp:c:{draft_id}:{image_revision}:{artifact_hash}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=f"newsp:n:{draft_id}:{image_revision}:{artifact_hash}",
                )
            ],
        ]
    )


def _restore_publish_actions_markup(
    *, draft_id: str, image_revision: int, artifact_hash: str
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Опубликовать сейчас",
                    callback_data=f"newsp:p:{draft_id}:{image_revision}:{artifact_hash}",
                ),
                InlineKeyboardButton(
                    text="Запланировать",
                    callback_data=f"newsp:s:{draft_id}:{image_revision}:{artifact_hash}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Изменить текст",
                    callback_data=f"newsp:e:{draft_id}:{image_revision}",
                ),
                InlineKeyboardButton(
                    text="Перегенерировать текст",
                    callback_data=f"news:r:{draft_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Перегенерировать изображение",
                    callback_data=f"newsp:i:{draft_id}:{image_revision}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Заменить изображение",
                    callback_data=f"newsp:u:{draft_id}:{image_revision}",
                ),
                InlineKeyboardButton(
                    text="Убрать изображение",
                    callback_data=f"newsp:n:{draft_id}:{image_revision}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=f"newsp:x:{draft_id}:{image_revision}",
                ),
                InlineKeyboardButton(
                    text="Отложить рассмотрение",
                    callback_data=f"news:d:{draft_id}",
                ),
            ],
        ]
    )


async def _edit_card_status(message: Message, status_text: str) -> None:
    """Keep the original card and add only an outcome line after the exact action."""

    current_text = getattr(message, "text", None)
    if isinstance(current_text, str):
        await message.edit_text(f"{current_text.rstrip()}\n\nСтатус: {status_text}")
        return
    current_caption = getattr(message, "caption", None)
    if isinstance(current_caption, str):
        await message.edit_caption(caption=f"{current_caption.rstrip()}\n\nСтатус: {status_text}")


@router.callback_query(F.data.startswith("news:"))
async def news_editorial_callback(callback: CallbackQuery) -> None:
    telegram_user_id = callback.from_user.id
    if telegram_user_id not in settings.admin_telegram_id_set:
        await callback.answer("Действие доступно только редактору", show_alert=True)
        return
    if not isinstance(callback.message, Message) or callback.message.chat.type != "private":
        await callback.answer("Черновик доступен только в личном чате", show_alert=True)
        return
    match = NEWS_CALLBACK_PATTERN.fullmatch(callback.data or "")
    if match is None:
        await callback.answer("Некорректное действие", show_alert=True)
        return
    action = ACTION_BY_CODE[match.group(1)]
    status = await moderate_news_draft(
        draft_id=match.group(2),
        admin_telegram_user_id=telegram_user_id,
        action=action,
    )
    if status == "forbidden":
        await callback.answer("Действие недоступно", show_alert=True)
        return
    if status in {
        "accepted",
        "queued",
        "deferred",
        "already_processed",
        "stale",
        "limit_reached",
    }:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(
        STATUS_TEXT.get(status, STATUS_TEXT["unavailable"]), show_alert=status == "unavailable"
    )


@router.callback_query(F.data.startswith("newsp:"))
async def news_publishing_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_telegram_id_set:
        await callback.answer("Действие доступно только редактору", show_alert=True)
        return
    if not isinstance(callback.message, Message) or callback.message.chat.type != "private":
        await callback.answer("Редактура доступна только в личном чате", show_alert=True)
        return
    match = PUBLISHING_CALLBACK_PATTERN.fullmatch(callback.data or "")
    if match is None:
        await callback.answer("Некорректное действие", show_alert=True)
        return
    action, draft_id, revision_text, artifact_hash = match.groups()
    image_revision = int(revision_text)
    if action in {"p", "s", "c", "z"} and artifact_hash is None:
        await callback.answer("Preview устарел: откройте новую карточку", show_alert=True)
        return

    if action == "p":
        assert artifact_hash is not None
        markup = _publish_confirmation_markup(
            draft_id=draft_id,
            image_revision=image_revision,
            artifact_hash=artifact_hash,
        )
        await state.set_state(NewsEditorialStates.awaiting_publish_confirmation)
        await state.set_data(
            {
                "mode": "publish_confirmation",
                "draft_id": draft_id,
                "image_revision": image_revision,
                "artifact_hash": artifact_hash,
                "channel_line": _control_channel_line(callback.message),
                "revision_line": _control_revision_line(
                    callback.message,
                    draft_id=draft_id,
                    image_revision=image_revision,
                ),
                "started_at": time.monotonic(),
            }
        )
        # The preview text/caption is deliberately untouched. Only the original card's markup
        # changes, so Telegram keeps the same message_id and exact artifact preview.
        await callback.message.edit_reply_markup(reply_markup=markup)
        await callback.answer()
        return
    if action in {"s", "e", "u"}:
        target_state = {
            "s": NewsEditorialStates.awaiting_schedule,
            "e": NewsEditorialStates.awaiting_text,
            "u": NewsEditorialStates.awaiting_image,
        }[action]
        await state.set_state(target_state)
        await state.set_data(
            {
                "draft_id": draft_id,
                "image_revision": image_revision,
                "artifact_hash": artifact_hash,
                "channel_line": _control_channel_line(callback.message),
                "revision_line": _control_revision_line(
                    callback.message,
                    draft_id=draft_id,
                    image_revision=image_revision,
                ),
                "started_at": time.monotonic(),
            }
        )
        prompt = {
            "s": "Введите дату, время и IANA timezone: 2026-08-26 12:00 Europe/Moscow. /cancel — отмена.",
            "e": "Пришлите полный исправленный текст публикации. /cancel — отмена.",
            "u": "Пришлите JPEG/PNG как фото или документ. /cancel — отмена.",
        }[action]
        await callback.message.answer(prompt)
        await callback.answer()
        return
    if action == "z":
        data = await state.get_data()
        if (
            _state_expired(data)
            or data.get("draft_id") != draft_id
            or data.get("image_revision") != image_revision
            or data.get("artifact_hash") != artifact_hash
        ):
            await state.clear()
            await callback.answer("Подтверждение устарело", show_alert=True)
            return
        status, blockers = await revision_action(
            draft_id=draft_id,
            admin_telegram_user_id=callback.from_user.id,
            action="schedule",
            image_revision=image_revision,
            artifact_hash=artifact_hash,
            scheduled_local=str(data["scheduled_local"]),
            timezone=str(data["timezone"]),
        )
        await state.clear()
        message = STATUS_TEXT.get(status, STATUS_TEXT["unavailable"])
        if blockers:
            message += ": " + ", ".join(blockers[:5])
        if status in {"scheduled", "already_queued"}:
            await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer(message, show_alert=status in {"unavailable", "quality_blocked"})
        return
    if action == "c":
        data = await state.get_data()
        if not (
            isinstance(data, dict)
            and data.get("mode") == "publish_confirmation"
            and data.get("draft_id") == draft_id
            and data.get("image_revision") == image_revision
            and data.get("artifact_hash") == artifact_hash
            and not _state_expired(data)
        ):
            await callback.answer("Подтверждение устарело", show_alert=True)
            return
    if action == "n" and artifact_hash is not None:
        data = await state.get_data()
        if (
            data.get("mode") == "publish_confirmation"
            and data.get("draft_id") == draft_id
            and data.get("image_revision") == image_revision
            and data.get("artifact_hash") == artifact_hash
            and not _state_expired(data)
        ):
            await state.clear()
            await callback.message.edit_reply_markup(
                reply_markup=_restore_publish_actions_markup(
                    draft_id=draft_id,
                    image_revision=image_revision,
                    artifact_hash=artifact_hash,
                )
            )
            await callback.answer("Отменено")
            return
        await callback.answer("Подтверждение устарело", show_alert=True)
        return
    if action == "n" and image_revision == 99999:
        await state.clear()
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Отменено")
        return
    if action in {"n", "x"}:
        confirmation_action = "v" if action == "n" else "q"
        label = "Подтвердить удаление изображения" if action == "n" else "Подтвердить отклонение"
        await callback.message.answer(
            "Это действие изменит редакционную карточку. Подтвердить?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=label,
                            callback_data=(
                                f"newsp:{confirmation_action}:{draft_id}:{image_revision}"
                            ),
                        )
                    ]
                ]
            ),
        )
        await callback.answer()
        return
    if action == "q":
        status = await moderate_news_draft(
            draft_id=draft_id,
            admin_telegram_user_id=callback.from_user.id,
            action="skip",
        )
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer(STATUS_TEXT.get(status, STATUS_TEXT["unavailable"]))
        return
    api_action = {"c": "publish", "i": "regenerate_image", "v": "remove_image"}[action]
    status, blockers = await revision_action(
        draft_id=draft_id,
        admin_telegram_user_id=callback.from_user.id,
        action=api_action,
        image_revision=image_revision,
        artifact_hash=artifact_hash,
    )
    message = (
        "Публикация поставлена в очередь"
        if action == "c" and status == "queued"
        else STATUS_TEXT.get(status, STATUS_TEXT["unavailable"])
    )
    if blockers:
        message += ": " + ", ".join(blockers[:5])
    if status in {"queued", "scheduled", "already_queued"}:
        await callback.message.edit_reply_markup(reply_markup=None)
        await state.clear()
        await _edit_card_status(callback.message, message)
    await callback.answer(message, show_alert=status in {"unavailable", "quality_blocked"})


@router.callback_query(F.data.startswith("newspost:"))
async def news_post_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_telegram_id_set:
        await callback.answer("Действие доступно только редактору", show_alert=True)
        return
    if not isinstance(callback.message, Message) or callback.message.chat.type != "private":
        await callback.answer("Действие доступно только в личном чате", show_alert=True)
        return
    match = POST_CALLBACK_PATTERN.fullmatch(callback.data or "")
    if match is None:
        await callback.answer("Некорректное действие", show_alert=True)
        return
    action, snapshot_id = match.groups()
    if action == "e":
        await state.set_state(NewsEditorialStates.awaiting_post_text)
        await state.set_data({"snapshot_id": snapshot_id, "started_at": time.monotonic()})
        await callback.message.answer(
            "Пришлите полный новый текст опубликованного поста. /cancel — отмена."
        )
        await callback.answer()
        return
    if action == "d":
        await callback.message.answer(
            "Удаление необратимо. Подтвердить?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Подтвердить удаление",
                            callback_data=f"newspost:c:{snapshot_id}",
                        )
                    ]
                ]
            ),
        )
        await callback.answer()
        return
    status = await post_action(
        snapshot_id=snapshot_id,
        admin_telegram_user_id=callback.from_user.id,
        action="delete",
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(
        {"deleted": "Публикация удалена", "stale": "Публикация уже недоступна"}.get(
            status, "Не удалось удалить публикацию"
        ),
        show_alert=status not in {"deleted", "stale"},
    )


@router.callback_query(F.data.startswith("newsrec:"))
async def news_reconcile_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_telegram_id_set:
        await callback.answer("Действие доступно только редактору", show_alert=True)
        return
    if not isinstance(callback.message, Message) or callback.message.chat.type != "private":
        await callback.answer("Действие доступно только в личном чате", show_alert=True)
        return
    match = RECONCILE_CALLBACK_PATTERN.fullmatch(callback.data or "")
    if match is None:
        await callback.answer("Некорректное действие", show_alert=True)
        return
    action, snapshot_id = match.groups()
    if action == "t":
        status = await retry_uncertain_publication(
            snapshot_id=snapshot_id,
            admin_telegram_user_id=callback.from_user.id,
        )
        await callback.message.edit_reply_markup(reply_markup=None)
        retry_feedback = {
            "queued": ("Повтор поставлен в очередь", False),
            "cancelled": ("Устаревшая публикация отменена", True),
        }
        feedback_text, show_alert = retry_feedback.get(status, ("Повтор недоступен", True))
        await callback.answer(feedback_text, show_alert=show_alert)
        return
    await state.set_state(NewsEditorialStates.awaiting_reconcile_message_id)
    await state.set_data({"snapshot_id": snapshot_id, "started_at": time.monotonic()})
    await callback.message.answer(
        "После ручной проверки канала пришлите message ID найденной публикации. /cancel — отмена."
    )
    await callback.answer()


@router.message(NewsEditorialStates.awaiting_schedule, F.text, ~F.text.startswith("/"))
async def news_schedule_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user = message.from_user
    if _state_expired(data) or user is None or user.id not in settings.admin_telegram_id_set:
        await state.clear()
        await message.answer("Время редактирования истекло")
        return
    match = SCHEDULE_INPUT_PATTERN.fullmatch(message.text or "")
    if match is None:
        await message.answer("Формат: 2026-08-26 12:00 Europe/Moscow")
        return
    local_value = f"{match.group(1)}T{match.group(2)}:00"
    artifact_hash = data.get("artifact_hash")
    if not isinstance(artifact_hash, str) or not re.fullmatch(r"[0-9a-f]{16}", artifact_hash):
        await state.clear()
        await message.answer("Preview устарел: откройте новую карточку")
        return
    timezone = match.group(3)
    await state.set_state(NewsEditorialStates.awaiting_schedule_confirmation)
    await state.set_data(
        {
            **data,
            "scheduled_local": local_value,
            "timezone": timezone,
            "started_at": time.monotonic(),
        }
    )
    revision_line = data.get("revision_line")
    if not isinstance(revision_line, str):
        revision_line = f"Материал {str(data['draft_id'])[:8]} · image r{data['image_revision']}"

    await message.answer(
        "Подтвердите публикацию точного preview по расписанию.\n"
        f"{data.get('channel_line', 'Канал: server-side config')}\n"
        f"Время: {match.group(1)} {match.group(2)}\n"
        f"Timezone: {timezone}\n"
        f"{revision_line}\n"
        f"Artifact: {artifact_hash}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Подтвердить расписание",
                        callback_data=(
                            f"newsp:z:{data['draft_id']}:{data['image_revision']}:{artifact_hash}"
                        ),
                    )
                ]
            ]
        ),
    )


@router.message(NewsEditorialStates.awaiting_text, F.text, ~F.text.startswith("/"))
async def news_text_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user = message.from_user
    if _state_expired(data) or user is None or user.id not in settings.admin_telegram_id_set:
        await state.clear()
        await message.answer("Сессия редактирования недоступна")
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{settings.backend_internal_url.rstrip('/')}/api/v1/bot/news/drafts/"
                f"{data['draft_id']}/text",
                headers={"X-Bot-Token": settings.bot_internal_token},
                json={
                    "admin_telegram_user_id": user.id,
                    "expected_image_revision": data["image_revision"],
                    "draft_text": message.text,
                },
            )
        status = response.json().get("status") if response.is_success else "unavailable"
    except httpx.HTTPError, ValueError:
        status = "unavailable"
    await state.clear()
    await message.answer(STATUS_TEXT.get(status, STATUS_TEXT["unavailable"]))


@router.message(NewsEditorialStates.awaiting_image, F.photo | F.document)
async def news_image_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user = message.from_user
    if _state_expired(data) or user is None or user.id not in settings.admin_telegram_id_set:
        await state.clear()
        await message.answer("Сессия загрузки недоступна")
        return
    media = message.photo[-1] if message.photo else message.document
    if media is None or media.file_size is None or media.file_size > 8_388_608:
        await message.answer("Файл недоступен или превышает 8 МБ")
        return
    buffer = BytesIO()
    if message.bot is None:
        await state.clear()
        await message.answer("Сессия загрузки недоступна")
        return
    await message.bot.download(media, destination=buffer)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.backend_internal_url.rstrip('/')}/api/v1/bot/news/drafts/"
                f"{data['draft_id']}/image",
                headers={
                    "X-Bot-Token": settings.bot_internal_token,
                    "X-Admin-Telegram-User-Id": str(user.id),
                    "X-Expected-Image-Revision": str(data["image_revision"]),
                    "Content-Type": "application/octet-stream",
                },
                content=buffer.getvalue(),
            )
        status = response.json().get("status") if response.is_success else "unavailable"
    except httpx.HTTPError, ValueError:
        status = "unavailable"
    await state.clear()
    await message.answer(STATUS_TEXT.get(status, STATUS_TEXT["unavailable"]))


@router.message(NewsEditorialStates.awaiting_post_text, F.text, ~F.text.startswith("/"))
async def news_post_text_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user = message.from_user
    if _state_expired(data) or user is None or user.id not in settings.admin_telegram_id_set:
        await state.clear()
        await message.answer("Сессия редактирования недоступна")
        return
    status = await post_action(
        snapshot_id=str(data["snapshot_id"]),
        admin_telegram_user_id=user.id,
        action="edit",
        text=message.text,
    )
    await state.clear()
    await message.answer(
        {
            "updated": "Опубликованный текст обновлён",
            "invalid": "Текст не прошёл проверку формата и качества",
            "stale": "Публикация уже недоступна",
        }.get(status, "Не удалось обновить публикацию")
    )


@router.message(
    NewsEditorialStates.awaiting_reconcile_message_id,
    F.text.regexp(r"^[1-9]\d{0,18}$"),
)
async def news_reconcile_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user = message.from_user
    if _state_expired(data) or user is None or user.id not in settings.admin_telegram_id_set:
        await state.clear()
        await message.answer("Сессия reconciliation недоступна")
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{settings.backend_internal_url.rstrip('/')}/api/v1/bot/news/publications/"
                f"{data['snapshot_id']}/reconcile",
                headers={"X-Bot-Token": settings.bot_internal_token},
                json={
                    "admin_telegram_user_id": user.id,
                    "channel_message_id": int(message.text or ""),
                },
            )
        status = response.json().get("status") if response.is_success else "unavailable"
    except httpx.HTTPError, ValueError:
        status = "unavailable"
    await state.clear()
    await message.answer(
        "Публикация сопоставлена" if status == "updated" else "Не удалось сопоставить публикацию"
    )


@router.message(StateFilter(NewsEditorialStates), Command("cancel"))
async def cancel_news_input(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Редактирование новости отменено")
