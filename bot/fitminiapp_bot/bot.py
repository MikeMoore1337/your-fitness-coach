import asyncio
import contextlib
import hashlib
import logging
import math
import re
from collections.abc import Awaitable, Callable
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, TextIO
from zoneinfo import available_timezones

import httpx
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.dispatcher.dispatcher import DEFAULT_BACKOFF_CONFIG
from aiogram.exceptions import TelegramConflictError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.methods import GetUpdates
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
    WebAppInfo,
)
from aiogram.utils.backoff import Backoff, BackoffConfig

from .config import settings
from .error_codes import safe_error_code
from .feedback import handle_feedback_start_payload, open_feedback_flow
from .feedback import router as feedback_router
from .logging_config import configure_logging
from .news_editorial import router as news_editorial_router
from .polling_health import write_polling_health
from .public_profile import (
    MENU_BUTTON_LABEL,
    canonical_mini_app_url,
    help_text,
    is_valid_public_https_url,
    main_menu_keyboard,
    menu_button,
    menu_button_matches,
    notification_settings_keyboard,
)
from .telegram_client import create_bot_api_session
from .weekly_digest import router as weekly_digest_router
from .weekly_digest import send_digest_settings

try:
    import fcntl
except ImportError:  # pragma: no cover - production container runs Linux
    fcntl = None


logger = logging.getLogger(__name__)

TelegramLinkOutcome = Literal["linked", "already_linked", "invalid", "conflict", "failed"]
TELEGRAM_LINK_PAYLOAD_PATTERN = re.compile(r"link_([A-Za-z0-9_-]{32,128})\Z")


def _polling_evidence(state: str, evidence: str) -> None:
    path = settings.bot_polling_health_path
    if path and not write_polling_health(path, state, evidence):
        logger.warning("polling_health_write_failed")


class PollingConflict(RuntimeError):
    """Another process is already receiving updates for this Telegram bot."""


class StableDispatcher(Dispatcher):
    @classmethod
    async def _listen_updates(
        cls,
        bot: Bot,
        polling_timeout: int = 30,
        backoff_config: BackoffConfig = DEFAULT_BACKOFF_CONFIG,
        allowed_updates: list[str] | None = None,
    ):
        """Retry network errors, but let the supervisor handle polling conflicts."""
        backoff = Backoff(config=backoff_config)
        get_updates = GetUpdates(timeout=polling_timeout, allowed_updates=allowed_updates)
        request_kwargs = {}
        if bot.session.timeout:
            request_kwargs["request_timeout"] = int(bot.session.timeout + polling_timeout)

        # Polling ownership/readiness must not wait for non-critical Telegram
        # metadata/menu synchronization.
        logger.info("telegram_polling_started")
        failed = False
        while True:
            try:
                updates = await bot(get_updates, **request_kwargs)
            except TelegramConflictError as exc:
                _polling_evidence("unhealthy", "polling_conflict")
                raise PollingConflict("telegram_polling_conflict") from exc
            except Exception as exc:
                _polling_evidence("unhealthy", "getupdates_error")
                failed = True
                logger.error(
                    "telegram_polling_failed",
                    extra={"error_code": safe_error_code(exc)},
                )
                logger.warning(
                    "telegram_polling_retry_scheduled",
                    extra={
                        "retry_seconds": backoff.next_delay,
                        "retry_attempt": backoff.counter,
                    },
                )
                await backoff.asleep()
                continue

            _polling_evidence("healthy", "getupdates_success")
            if failed:
                logger.info(
                    "telegram_polling_recovered",
                    extra={"retry_attempt": backoff.counter},
                )
                backoff.reset()
                failed = False

            for update in updates:
                yield update
                get_updates.offset = update.update_id + 1


class PollingFileLock:
    """Cross-container lock backed by a shared Docker volume."""

    def __init__(self, directory: str, bot_token: str) -> None:
        token_hash = hashlib.sha256(bot_token.encode("utf-8")).hexdigest()[:24]
        self.path = Path(directory) / f"polling-{token_hash}.lock"
        self._file: TextIO | None = None

    async def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+", encoding="utf-8")

        if fcntl is None:
            logger.warning("polling_file_lock_unavailable")
            return

        waiting_logged = False
        while True:
            try:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                logger.info("polling_file_lock_acquired")
                return
            except BlockingIOError:
                if not waiting_logged:
                    logger.warning(
                        "polling_file_lock_waiting",
                    )
                    waiting_logged = True
                await asyncio.sleep(5)

    def release(self) -> None:
        if self._file is None:
            return
        if fcntl is not None:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()
        self._file = None


dp = StableDispatcher(events_isolation=SimpleEventIsolation())
public_router = Router()
TIMEZONE_PAGE_SIZE = 8
TIMEZONE_REGIONS = [
    "Europe",
    "Asia",
    "America",
    "Africa",
    "Australia",
    "Pacific",
    "Atlantic",
    "Indian",
    "Antarctica",
    "Etc",
]
TIMEZONE_REGION_LABELS = {
    "Europe": "Европа",
    "Asia": "Азия",
    "America": "Америка",
    "Africa": "Африка",
    "Australia": "Австралия",
    "Pacific": "Тихий океан",
    "Atlantic": "Атлантика",
    "Indian": "Индийский океан",
    "Antarctica": "Антарктика",
    "Etc": "UTC и прочие",
}


def mini_app_url() -> str:
    return canonical_mini_app_url(settings.frontend_base_url)


def is_https_url(url: str) -> bool:
    return is_valid_public_https_url(url)


def web_app_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=MENU_BUTTON_LABEL,
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


@lru_cache(maxsize=len(TIMEZONE_REGIONS))
def region_timezones(region: str) -> tuple[str, ...]:
    if region == "Etc":
        return tuple(
            sorted(
                timezone
                for timezone in available_timezones()
                if timezone == "UTC" or timezone.startswith("Etc/")
            )
        )
    return tuple(
        sorted(timezone for timezone in available_timezones() if timezone.startswith(f"{region}/"))
    )


def timezone_regions_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for region in TIMEZONE_REGIONS:
        current_row.append(
            InlineKeyboardButton(
                text=TIMEZONE_REGION_LABELS.get(region, region),
                callback_data=f"tz:r:{region}:0",
            )
        )
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([InlineKeyboardButton(text="MSK / Москва", callback_data="tz:set:Europe/Moscow")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def timezone_page_keyboard(region: str, page: int = 0) -> InlineKeyboardMarkup:
    timezones = region_timezones(region)
    total_pages = max(1, math.ceil(len(timezones) / TIMEZONE_PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    start = page * TIMEZONE_PAGE_SIZE
    page_timezones = timezones[start : start + TIMEZONE_PAGE_SIZE]

    rows = [
        [InlineKeyboardButton(text=timezone, callback_data=f"tz:set:{timezone}")]
        for timezone in page_timezones
    ]

    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="Назад", callback_data=f"tz:r:{region}:{page - 1}")
        )
    nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="tz:noop"))
    if page + 1 < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="Дальше", callback_data=f"tz:r:{region}:{page + 1}")
        )
    rows.append(nav_row)
    rows.append([InlineKeyboardButton(text="К регионам", callback_data="tz:regions")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def save_timezone_from_bot(telegram_user, timezone: str) -> bool:
    if not telegram_user:
        return False

    payload = {
        "telegram_user_id": telegram_user.id,
        "timezone": timezone,
        "username": telegram_user.username,
        "first_name": telegram_user.first_name,
        "last_name": telegram_user.last_name,
    }
    url = f"{settings.backend_internal_url.rstrip('/')}/api/v1/bot/timezone"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                headers={"X-Bot-Token": settings.bot_internal_token},
                json=payload,
            )
            response.raise_for_status()
        return True
    except Exception as exc:
        logger.error(
            "timezone_backend_update_failed",
            extra={"error_code": safe_error_code(exc)},
        )
        return False


def telegram_link_token(start_payload: str | None) -> str | None:
    match = TELEGRAM_LINK_PAYLOAD_PATTERN.fullmatch((start_payload or "").strip())
    return match.group(1) if match else None


async def link_telegram_from_bot(telegram_user, raw_token: str) -> TelegramLinkOutcome:
    if not telegram_user or not raw_token:
        return "invalid"

    payload = {
        "token": raw_token,
        "telegram_user_id": telegram_user.id,
        "username": telegram_user.username,
        "first_name": telegram_user.first_name,
        "last_name": telegram_user.last_name,
    }
    url = f"{settings.backend_internal_url.rstrip('/')}/api/v1/bot/link-telegram"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                headers={"X-Bot-Token": settings.bot_internal_token},
                json=payload,
            )
            if response.status_code == 400:
                return "invalid"
            if response.status_code == 409:
                return "conflict"
            response.raise_for_status()
            status = response.json().get("status")
            if status == "linked":
                return "linked"
            if status == "already_linked":
                return "already_linked"
            return "failed"
    except Exception as exc:
        logger.error(
            "telegram_account_link_failed",
            extra={"error_code": safe_error_code(exc)},
        )
        return "failed"


async def set_mini_app_menu_button(bot: Bot, chat_id: int | None = None) -> bool:
    url = mini_app_url()
    if not is_https_url(url):
        logger.error("frontend_url_invalid")
        return False

    try:
        current = await bot.get_chat_menu_button(chat_id=chat_id)
        if menu_button_matches(current, settings.frontend_base_url):
            return True
        await bot.set_chat_menu_button(
            chat_id=chat_id,
            menu_button=menu_button(settings.frontend_base_url),
        )
        verified = await bot.get_chat_menu_button(chat_id=chat_id)
        if not menu_button_matches(verified, settings.frontend_base_url):
            logger.error("menu_button_verification_failed")
            return False
        logger.info("menu_button_configured")
        return True
    except Exception as exc:
        logger.error(
            "menu_button_configuration_failed",
            extra={"error_code": safe_error_code(exc)},
        )
        return False


async def sync_default_menu_button_in_background(
    bot: Bot,
    *,
    timeout_seconds: float = 10.0,
) -> None:
    """Keep the default Telegram menu self-healing without blocking polling startup."""

    try:
        async with asyncio.timeout(timeout_seconds):
            await set_mini_app_menu_button(bot)
    except TimeoutError:
        logger.warning(
            "menu_button_configuration_timed_out",
            extra={"timeout_seconds": timeout_seconds},
        )


async def answer_with_open_button(message: Message) -> None:
    url = mini_app_url()

    if is_https_url(url):
        try:
            await message.answer(
                "Открой Your Fitness Coach кнопкой ниже.",
                reply_markup=web_app_keyboard(url),
            )
            return
        except Exception as exc:
            logger.error(
                "open_button_delivery_failed",
                extra={"error_code": safe_error_code(exc)},
            )
    else:
        logger.error("frontend_url_invalid")

    await message.answer(
        "Кнопка Your Fitness Coach временно недоступна. "
        "Попробуйте открыть приложение через меню бота позже."
    )


async def show_main_menu(message: Message, *, unknown_payload: bool = False) -> None:
    prefix = "Параметр запуска не распознан.\n\n" if unknown_payload else ""
    await message.answer(
        f"{prefix}Выберите, что хотите сделать.",
        reply_markup=main_menu_keyboard(settings.frontend_base_url),
    )


class MenuButtonMigrationMiddleware(BaseMiddleware):
    """Replace legacy per-chat cache-versioned menu buttons on the next interaction."""

    def __init__(self) -> None:
        self._checked_chat_ids: set[int] = set()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = getattr(event, "chat", None)
        if chat is None:
            chat = getattr(getattr(event, "message", None), "chat", None)
        bot = data.get("bot")
        if (
            isinstance(bot, Bot)
            and getattr(chat, "type", None) == "private"
            and chat.id not in self._checked_chat_ids
            and await set_mini_app_menu_button(bot, chat_id=chat.id)
        ):
            self._checked_chat_ids.add(chat.id)
        return await handler(event, data)


menu_button_migration = MenuButtonMigrationMiddleware()
dp.message.outer_middleware(menu_button_migration)
dp.callback_query.outer_middleware(menu_button_migration)


@dp.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext) -> None:
    await state.clear()
    raw_token = telegram_link_token(command.args)
    if raw_token is not None:
        outcome = await link_telegram_from_bot(message.from_user, raw_token)
        if outcome in {"linked", "already_linked"}:
            if message.bot is not None:
                await set_mini_app_menu_button(
                    message.bot,
                    chat_id=message.from_user.id if message.from_user else None,
                )
            await message.answer(
                "Telegram успешно привязан к вашему аккаунту. Теперь в браузере и боте доступны одни и те же данные.",
                reply_markup=web_app_keyboard(mini_app_url()),
            )
            return
        if outcome == "conflict":
            await message.answer(
                "Этот Telegram уже связан с другим аккаунтом. Автоматическое объединение данных заблокировано."
            )
            return
        if outcome == "invalid":
            await message.answer(
                "Ссылка привязки недействительна или устарела. Создайте новую ссылку в настройках аккаунта."
            )
            return
        await message.answer("Не удалось привязать Telegram. Попробуйте ещё раз позже.")
        return

    if await handle_feedback_start_payload(message, state, command.args):
        return

    await set_mini_app_menu_button(
        message.bot,
        chat_id=message.from_user.id if message.from_user else None,
    )
    await show_main_menu(message, unknown_payload=bool(command.args and command.args != "app"))


@public_router.message(Command("app"), F.chat.type == "private")
async def app_command(message: Message) -> None:
    await answer_with_open_button(message)


async def answer_settings(message: Message) -> None:
    await message.answer(
        "Настройки уведомлений доступны в приложении. Часовой пояс можно изменить здесь: /timezone",
        reply_markup=notification_settings_keyboard(settings.frontend_base_url),
    )
    await send_digest_settings(message)


@public_router.message(Command("settings"), F.chat.type == "private")
async def settings_command(message: Message) -> None:
    await answer_settings(message)


@public_router.message(Command("help"), F.chat.type == "private")
async def help_command(message: Message) -> None:
    await message.answer(
        help_text(),
        reply_markup=main_menu_keyboard(settings.frontend_base_url),
    )


@public_router.message(Command("privacy"), F.chat.type == "private")
async def privacy_command(message: Message) -> None:
    url = settings.privacy_policy_url.strip()
    if not is_https_url(url):
        await message.answer(
            "Политика конфиденциальности пока недоступна по подтверждённой ссылке. "
            "Попробуйте позже или напишите в поддержку: /support"
        )
        return
    await message.answer(
        "Политика конфиденциальности Your Fitness Coach:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Открыть политику", url=url)],
            ]
        ),
    )


@public_router.callback_query(F.data == "public:support")
async def public_support_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await open_feedback_flow(callback.message, state)


@public_router.callback_query(F.data == "public:settings")
async def public_settings_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await answer_settings(callback.message)


@public_router.callback_query(F.data == "public:help")
async def public_help_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            help_text(),
            reply_markup=main_menu_keyboard(settings.frontend_base_url),
        )


@dp.message(Command("timezone"))
async def timezone_command(message: Message) -> None:
    await message.answer(
        "Выберите регион часового пояса.",
        reply_markup=timezone_regions_keyboard(),
    )


@dp.callback_query(lambda callback: bool(callback.data and callback.data.startswith("tz:")))
async def timezone_callback(callback: CallbackQuery) -> None:
    data = callback.data or ""

    if data == "tz:noop":
        await callback.answer()
        return

    if data == "tz:regions":
        if callback.message:
            await callback.message.edit_text(
                "Выберите регион часового пояса.",
                reply_markup=timezone_regions_keyboard(),
            )
        await callback.answer()
        return

    if data.startswith("tz:r:"):
        _, _, region, page_raw = data.split(":", 3)
        page = int(page_raw) if page_raw.isdigit() else 0
        if callback.message:
            await callback.message.edit_text(
                f"Регион: {TIMEZONE_REGION_LABELS.get(region, region)}. Выберите часовой пояс.",
                reply_markup=timezone_page_keyboard(region, page),
            )
        await callback.answer()
        return

    if data.startswith("tz:set:"):
        timezone = data.removeprefix("tz:set:")
        if not callback.message:
            await callback.answer("Не удалось сохранить часовой пояс", show_alert=True)
            return

        ok = await save_timezone_from_bot(callback.from_user, timezone)
        if ok:
            await callback.message.edit_text(f"Часовой пояс сохранён: {timezone}")
            await callback.answer("Сохранено")
            return

        await callback.answer("Не удалось сохранить часовой пояс", show_alert=True)


@public_router.message(F.chat.type == "private", F.text.startswith("/"))
async def unknown_command(message: Message) -> None:
    await message.answer(
        "Такой команды нет. Откройте главное меню или используйте /help.",
        reply_markup=main_menu_keyboard(settings.frontend_base_url),
    )


dp.include_router(weekly_digest_router)
dp.include_router(news_editorial_router)
dp.include_router(feedback_router)
dp.include_router(public_router)


async def main() -> None:
    configure_logging()
    if not settings.bot_polling_enabled:
        logger.warning("polling_disabled")
        while True:
            await asyncio.sleep(3600)

    if not settings.bot_token or settings.bot_token in {"change-me", "replace-me"}:
        logger.warning("bot_token_not_configured")
        while True:
            await asyncio.sleep(3600)

    polling_lock = PollingFileLock(settings.bot_polling_lock_dir, settings.bot_token)

    while True:
        await polling_lock.acquire()
        bot = Bot(settings.bot_token, session=create_bot_api_session())
        conflict = False
        menu_button_task: asyncio.Task[None] | None = None
        try:
            _polling_evidence("unknown", "polling_starting")
            logger.info("telegram_polling_starting")
            menu_button_task = asyncio.create_task(sync_default_menu_button_in_background(bot))
            await dp.start_polling(bot)
        except PollingConflict:
            conflict = True
            logger.critical(
                "telegram_polling_conflict",
                extra={"retry_seconds": settings.bot_conflict_retry_seconds},
            )
        finally:
            if menu_button_task is not None:
                if not menu_button_task.done():
                    menu_button_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await menu_button_task
            # Keep the observed conflict until a real successful getUpdates;
            # do not overwrite proof with generic shutdown/unknown.
            if not conflict:
                _polling_evidence("unknown", "polling_stopped")
            polling_lock.release()

        if not conflict:
            return
        await asyncio.sleep(settings.bot_conflict_retry_seconds)


if __name__ == "__main__":
    asyncio.run(main())
