from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from typing import Literal, cast

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import (
    local_naive_to_utc_naive,
    now_for_user_naive,
    to_user_timezone_naive,
)
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.hydration import HydrationEntry
from fitminiapp_api.models.notification import Notification, NotificationSetting
from fitminiapp_api.models.reminder_template import ReminderTemplateSchedule
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.schemas.notification import ReminderTemplateUpdate
from fitminiapp_api.services.notifications import can_scheduler_reactivate_cancelled_notification

ReminderTemplateKey = Literal["meal_logging", "hydration", "movement_break"]
ScheduleKind = Literal["times", "interval"]

CONTEXTUAL_NOTIFICATION_PREFIX = "contextual:"
CONTEXTUAL_TEMPLATE_CATEGORY = {
    "meal_logging": "meal_logging_reminder",
    "hydration": "hydration_reminder",
    "movement_break": "movement_break_reminder",
}
TEMPLATE_FLAG = {
    "meal_logging": "meal_reminders_enabled",
    "hydration": "hydration_reminders_enabled",
    "movement_break": "movement_reminders_enabled",
}
MEAL_SLOT_TYPES = ("breakfast", "lunch", "dinner")
REMINDER_HORIZON_DAYS = 7


@dataclass(frozen=True)
class ReminderTemplateDefinition:
    key: ReminderTemplateKey
    version: str
    label: str
    purpose: str
    schedule_kind: ScheduleKind
    allowed_schedule: str
    quiet_hours_behavior: str
    deep_link: str
    suppression: str
    neutral_copy: str
    default_weekdays: tuple[int, ...]
    default_times: tuple[str, ...]
    default_window_start: time | None
    default_window_end: time | None
    default_interval_minutes: int | None
    default_max_per_day: int
    default_minimum_spacing_minutes: int
    notification_title: str
    notification_body: str


TEMPLATE_DEFINITIONS: tuple[ReminderTemplateDefinition, ...] = (
    ReminderTemplateDefinition(
        key="meal_logging",
        version="v1",
        label="Записать приём пищи",
        purpose="Мягко напомнить добавить запись, когда выбранное окно ещё пусто.",
        schedule_kind="times",
        allowed_schedule="До трёх выбранных окон в выбранные дни недели.",
        quiet_hours_behavior="Окно внутри тихих часов пропускается без переноса на утро.",
        deep_link="Питание → быстрый ввод за выбранный приём пищи.",
        suppression="Пропускается, если в этом окне уже есть сохранённая запись питания.",
        neutral_copy="Можно записать приём пищи. Подробности — в приложении.",
        default_weekdays=tuple(range(7)),
        default_times=("08:00:00", "13:00:00", "19:00:00"),
        default_window_start=None,
        default_window_end=None,
        default_interval_minutes=None,
        default_max_per_day=3,
        default_minimum_spacing_minutes=120,
        notification_title="Записать приём пищи",
        notification_body="Добавьте запись за выбранный приём пищи, если он ещё не отмечен.",
    ),
    ReminderTemplateDefinition(
        key="hydration",
        version="v1",
        label="Выпить воду",
        purpose="Напомнить отметить воду или другой напиток в дневнике.",
        schedule_kind="interval",
        allowed_schedule="Повтор в выбранном рабочем окне с ограничением числа напоминаний в день.",
        quiet_hours_behavior="Слоты внутри тихих часов пропускаются без catch-up серии.",
        deep_link="Питание → быстрый ввод воды за текущую дату.",
        suppression="Ближайший слот пропускается после недавней записи гидратации.",
        neutral_copy="Можно выпить воды. Подробности — в приложении.",
        default_weekdays=tuple(range(7)),
        default_times=(),
        default_window_start=time(9),
        default_window_end=time(21),
        default_interval_minutes=120,
        default_max_per_day=6,
        default_minimum_spacing_minutes=120,
        notification_title="Время отметить напиток",
        notification_body="Отметьте воду или другой напиток в приложении, если это актуально.",
    ),
    ReminderTemplateDefinition(
        key="movement_break",
        version="v1",
        label="Разминка / перерыв от сидения",
        purpose="Предложить короткий перерыв и немного подвигаться по расписанию.",
        schedule_kind="interval",
        allowed_schedule="Плановые слоты в выбранном рабочем окне; приложение не измеряет сидение.",
        quiet_hours_behavior="Слоты внутри тихих часов пропускаются без catch-up серии.",
        deep_link="Сегодня → контекст приложения для короткого перерыва.",
        suppression="Слот не переносится автоматически, если он был пропущен.",
        neutral_copy="Пора сделать короткий перерыв и немного подвигаться. Подробности — в приложении.",
        default_weekdays=tuple(range(5)),
        default_times=(),
        default_window_start=time(10),
        default_window_end=time(18),
        default_interval_minutes=120,
        default_max_per_day=5,
        default_minimum_spacing_minutes=120,
        notification_title="Короткая разминка",
        notification_body="Сделайте короткий перерыв и немного подвигайтесь.",
    ),
)
TEMPLATES_BY_KEY = {definition.key: definition for definition in TEMPLATE_DEFINITIONS}


class ReminderTemplateError(ValueError):
    pass


def get_template_definition(template_key: str) -> ReminderTemplateDefinition:
    try:
        return TEMPLATES_BY_KEY[cast(ReminderTemplateKey, template_key)]
    except KeyError as exc:
        raise ReminderTemplateError("Неизвестный шаблон напоминания") from exc


def _time_value(value: str | time) -> time:
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    try:
        return time.fromisoformat(value).replace(tzinfo=None)
    except (TypeError, ValueError) as exc:
        raise ReminderTemplateError("Некорректное время в расписании") from exc


def _time_string(value: time) -> str:
    return value.replace(tzinfo=None).strftime("%H:%M:%S")


def _default_values(definition: ReminderTemplateDefinition) -> dict[str, object]:
    return {
        "weekdays": list(definition.default_weekdays),
        "times": [_time_value(value) for value in definition.default_times],
        "window_start": definition.default_window_start,
        "window_end": definition.default_window_end,
        "interval_minutes": definition.default_interval_minutes,
        "max_per_day": definition.default_max_per_day,
        "minimum_spacing_minutes": definition.default_minimum_spacing_minutes,
    }


def _stored_values(schedule: ReminderTemplateSchedule) -> dict[str, object]:
    return {
        "weekdays": list(schedule.weekdays or []),
        "times": [_time_value(value) for value in (schedule.schedule_times or [])],
        "window_start": schedule.window_start,
        "window_end": schedule.window_end,
        "interval_minutes": schedule.interval_minutes,
        "max_per_day": schedule.max_per_day,
        "minimum_spacing_minutes": schedule.minimum_spacing_minutes,
    }


def _validate_values(
    definition: ReminderTemplateDefinition,
    values: dict[str, object],
) -> dict[str, object]:
    weekdays = list(cast(list[int], values["weekdays"] or []))
    if not weekdays or any(
        not isinstance(day, int) or isinstance(day, bool) or day not in range(7) for day in weekdays
    ):
        raise ReminderTemplateError("Выберите хотя бы один день недели")
    if weekdays != sorted(set(weekdays)):
        raise ReminderTemplateError("Дни недели должны быть выбраны без повторов")

    times = [_time_value(value) for value in cast(list[str | time], values["times"] or [])]
    window_start = values["window_start"]
    window_end = values["window_end"]
    interval_minutes = values["interval_minutes"]
    max_per_day = values["max_per_day"]
    minimum_spacing_minutes = values["minimum_spacing_minutes"]
    if (
        not isinstance(max_per_day, int)
        or isinstance(max_per_day, bool)
        or not 1 <= max_per_day <= 8
    ):
        raise ReminderTemplateError("Число напоминаний в день должно быть от 1 до 8")
    if (
        not isinstance(minimum_spacing_minutes, int)
        or isinstance(minimum_spacing_minutes, bool)
        or not 15 <= minimum_spacing_minutes <= 720
    ):
        raise ReminderTemplateError("Минимальный интервал должен быть от 15 до 720 минут")

    if definition.schedule_kind == "times":
        if not 1 <= len(times) <= 3:
            raise ReminderTemplateError("Для приёма пищи выберите от одного до трёх окон")
        if times != sorted(set(times)):
            raise ReminderTemplateError("Времена приёмов пищи должны быть уникальными и по порядку")
        if any(
            (later.hour * 60 + later.minute) - (earlier.hour * 60 + earlier.minute)
            < minimum_spacing_minutes
            for earlier, later in pairwise(times)
        ):
            raise ReminderTemplateError(
                "Окна приёма пищи должны быть разделены минимальным интервалом"
            )
        if window_start is not None or window_end is not None or interval_minutes is not None:
            raise ReminderTemplateError("Для этого шаблона доступны только выбранные времена")
        if max_per_day != len(times):
            raise ReminderTemplateError("Число напоминаний должно совпадать с числом окон")
    else:
        if times:
            raise ReminderTemplateError("Для интервального шаблона отдельные времена не задаются")
        if not isinstance(window_start, time) or not isinstance(window_end, time):
            raise ReminderTemplateError("Укажите начало и конец рабочего окна")
        if window_start >= window_end:
            raise ReminderTemplateError("Рабочее окно должно заканчиваться позже начала")
        if not isinstance(interval_minutes, int) or isinstance(interval_minutes, bool):
            raise ReminderTemplateError("Укажите интервал повторения")
        if not 30 <= interval_minutes <= 360:
            raise ReminderTemplateError("Интервал повторения должен быть от 30 до 360 минут")
        if minimum_spacing_minutes > interval_minutes:
            raise ReminderTemplateError("Минимальный интервал не может быть больше повтора")

    return {
        "weekdays": weekdays,
        "times": times,
        "window_start": _time_value(window_start) if window_start is not None else None,
        "window_end": _time_value(window_end) if window_end is not None else None,
        "interval_minutes": interval_minutes,
        "max_per_day": max_per_day,
        "minimum_spacing_minutes": minimum_spacing_minutes,
    }


def _schedule_from_values(
    schedule: ReminderTemplateSchedule,
    definition: ReminderTemplateDefinition,
    values: dict[str, object],
) -> None:
    validated = _validate_values(definition, values)
    schedule.template_version = definition.version
    schedule.weekdays = cast(list[int], validated["weekdays"])
    schedule.schedule_times = [
        _time_string(value) for value in cast(list[time], validated["times"])
    ]
    schedule.window_start = cast(time | None, validated["window_start"])
    schedule.window_end = cast(time | None, validated["window_end"])
    schedule.interval_minutes = cast(int | None, validated["interval_minutes"])
    schedule.max_per_day = cast(int, validated["max_per_day"])
    schedule.minimum_spacing_minutes = cast(int, validated["minimum_spacing_minutes"])


def _get_or_create_schedule(
    db: Session,
    user: User,
    definition: ReminderTemplateDefinition,
) -> ReminderTemplateSchedule:
    schedule = (
        db.query(ReminderTemplateSchedule)
        .filter(
            ReminderTemplateSchedule.user_id == user.id,
            ReminderTemplateSchedule.template_key == definition.key,
        )
        .first()
    )
    if schedule is not None:
        return schedule
    values = _default_values(definition)
    schedule = ReminderTemplateSchedule(
        user_id=user.id,
        template_key=definition.key,
        template_version=definition.version,
    )
    db.add(schedule)
    _schedule_from_values(schedule, definition, values)
    return schedule


def _channel_note(settings: NotificationSetting, user: User) -> str:
    if user.telegram_user_id is None:
        return "В приложении доступно всегда; Telegram появится после связывания аккаунта."
    if not settings.telegram_enabled:
        return "В приложении доступно всегда; Telegram сейчас выключен в настройках каналов."
    return "Событие появится в приложении; в Telegram придёт нейтральный текст."


def serialize_template(
    schedule: ReminderTemplateSchedule,
    definition: ReminderTemplateDefinition,
    settings: NotificationSetting,
    user: User,
) -> dict[str, object]:
    values = _validate_values(definition, _stored_values(schedule))
    return {
        "template_key": definition.key,
        "version": definition.version,
        "label": definition.label,
        "purpose": definition.purpose,
        "schedule_kind": definition.schedule_kind,
        "allowed_schedule": definition.allowed_schedule,
        "quiet_hours_behavior": definition.quiet_hours_behavior,
        "deep_link": definition.deep_link,
        "suppression": definition.suppression,
        "neutral_copy": definition.neutral_copy,
        "default_enabled": False,
        "enabled": bool(getattr(settings, TEMPLATE_FLAG[definition.key])),
        "weekdays": values["weekdays"],
        "times": values["times"],
        "window_start": values["window_start"],
        "window_end": values["window_end"],
        "interval_minutes": values["interval_minutes"],
        "max_per_day": values["max_per_day"],
        "minimum_spacing_minutes": values["minimum_spacing_minutes"],
        "telegram_linked": user.telegram_user_id is not None,
        "telegram_enabled": settings.telegram_enabled,
        "channel_note": _channel_note(settings, user),
    }


def list_reminder_templates(
    db: Session,
    user: User,
    settings: NotificationSetting,
) -> list[dict[str, object]]:
    schedules = [
        _get_or_create_schedule(db, user, definition) for definition in TEMPLATE_DEFINITIONS
    ]
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        schedules = [
            _get_or_create_schedule(db, user, definition) for definition in TEMPLATE_DEFINITIONS
        ]
    return [
        serialize_template(schedule, definition, settings, user)
        for schedule, definition in zip(schedules, TEMPLATE_DEFINITIONS, strict=True)
    ]


def update_reminder_template(
    db: Session,
    user: User,
    settings: NotificationSetting,
    template_key: str,
    payload: ReminderTemplateUpdate,
) -> dict[str, object]:
    definition = get_template_definition(template_key)
    schedule = _get_or_create_schedule(db, user, definition)
    values = _stored_values(schedule)
    fields = payload.model_fields_set
    for field in (
        "weekdays",
        "times",
        "window_start",
        "window_end",
        "interval_minutes",
        "max_per_day",
        "minimum_spacing_minutes",
    ):
        if field in fields:
            values[field] = getattr(payload, field)
    _schedule_from_values(schedule, definition, values)
    if "enabled" in fields:
        setattr(settings, TEMPLATE_FLAG[definition.key], bool(payload.enabled))
    if not bool(getattr(settings, TEMPLATE_FLAG[definition.key])):
        _cancel_user_template_notifications(
            db,
            user.id,
            template_key=definition.key,
            reason="contextual_reminder_disabled",
        )
    db.commit()
    db.refresh(schedule)
    return serialize_template(schedule, definition, settings, user)


def _is_quiet_local(setting: NotificationSetting, local_value: datetime) -> bool:
    start = setting.quiet_hours_start
    end = setting.quiet_hours_end
    if start is None or end is None or start == end:
        return False
    local_time = local_value.time().replace(tzinfo=None)
    if start < end:
        return start <= local_time < end
    return local_time >= start or local_time < end


def _candidate_values(
    definition: ReminderTemplateDefinition,
    schedule: ReminderTemplateSchedule,
    local_date: date,
) -> list[tuple[datetime, int]]:
    if local_date.weekday() not in set(schedule.weekdays or []):
        return []
    candidates: list[tuple[datetime, int]] = []
    if definition.schedule_kind == "times":
        for slot_index, raw_time in enumerate(schedule.schedule_times or []):
            candidates.append((datetime.combine(local_date, _time_value(raw_time)), slot_index))
        return candidates

    start = schedule.window_start
    end = schedule.window_end
    interval = schedule.interval_minutes
    if start is None or end is None or interval is None:
        return []
    current = datetime.combine(local_date, start)
    end_value = datetime.combine(local_date, end)
    for slot_index in range(schedule.max_per_day):
        if current > end_value:
            break
        candidates.append((current, slot_index))
        current += timedelta(minutes=interval)
    return candidates


def _local_hydration_times(
    entries: list[HydrationEntry],
    user: User,
) -> list[datetime]:
    local_times: list[datetime] = []
    for entry in entries:
        occurred_at = entry.occurred_at
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        local_times.append(to_user_timezone_naive(occurred_at, user))
    return local_times


def _has_recent_hydration(
    candidate: datetime,
    local_entries: list[datetime],
    minimum_spacing_minutes: int,
) -> bool:
    return any(
        timedelta(0) <= candidate - entry <= timedelta(minutes=minimum_spacing_minutes)
        for entry in local_entries
    )


def _notification_action_url(
    definition: ReminderTemplateDefinition,
    local_date: date,
    slot_index: int,
) -> str:
    date_value = local_date.isoformat()
    if definition.key == "meal_logging":
        meal_type = MEAL_SLOT_TYPES[min(slot_index, len(MEAL_SLOT_TYPES) - 1)]
        return f"/app?section=nutrition&date={date_value}&meal={meal_type}"
    if definition.key == "hydration":
        return f"/app?section=nutrition&date={date_value}&hydration=quick"
    return "/app?section=today"


def _cancel_user_template_notifications(
    db: Session,
    user_id: int,
    *,
    template_key: str | None = None,
    reason: str,
) -> int:
    key_pattern = (
        f"{CONTEXTUAL_NOTIFICATION_PREFIX}{user_id}:{template_key}:%"
        if template_key is not None
        else f"{CONTEXTUAL_NOTIFICATION_PREFIX}{user_id}:%"
    )
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.dedupe_key.like(key_pattern),
            Notification.status == "queued",
        )
        .update(
            {
                Notification.status: "cancelled",
                Notification.last_error: reason,
                Notification.processing_started_at: None,
                Notification.next_attempt_at: None,
            },
            synchronize_session=False,
        )
    )


def sync_contextual_reminders(db: Session) -> int:
    """Materialize opt-in template occurrences in the canonical notification queue."""
    rows = (
        db.query(NotificationSetting, User, UserProfile.timezone)
        .join(User, User.id == NotificationSetting.user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .filter(User.is_active.is_(True))
        .all()
    )
    if not rows:
        return 0

    user_ids = [user.id for _settings, user, _timezone in rows]
    today_by_user = {user.id: now_for_user_naive(user).date() for _s, user, _tz in rows}
    horizon_end = max(today_by_user.values()) + timedelta(days=REMINDER_HORIZON_DAYS - 1)
    first_day = min(today_by_user.values())
    food_entries = (
        db.query(FoodDiaryEntry.user_id, FoodDiaryEntry.diary_date, FoodDiaryEntry.meal_type)
        .filter(
            FoodDiaryEntry.user_id.in_(user_ids),
            FoodDiaryEntry.diary_date >= first_day,
            FoodDiaryEntry.diary_date <= horizon_end,
        )
        .all()
    )
    food_entry_keys = {
        (user_id, diary_date, meal_type) for user_id, diary_date, meal_type in food_entries
    }
    hydration_entries = (
        db.query(HydrationEntry)
        .filter(
            HydrationEntry.user_id.in_(user_ids),
            HydrationEntry.diary_date >= first_day,
            HydrationEntry.diary_date <= horizon_end,
        )
        .all()
    )
    hydration_by_user_day: dict[tuple[int, date], list[HydrationEntry]] = {}
    for entry in hydration_entries:
        hydration_by_user_day.setdefault((entry.user_id, entry.diary_date), []).append(entry)

    schedules = (
        db.query(ReminderTemplateSchedule)
        .filter(ReminderTemplateSchedule.user_id.in_(user_ids))
        .all()
    )
    schedules_by_user_key = {
        (schedule.user_id, schedule.template_key): schedule for schedule in schedules
    }
    active_keys: set[str] = set()
    candidates: list[tuple[str, User, str | None, ReminderTemplateDefinition, datetime, int]] = []
    for settings, user, timezone in rows:
        local_now = now_for_user_naive(user)
        for definition in TEMPLATE_DEFINITIONS:
            if not bool(getattr(settings, TEMPLATE_FLAG[definition.key])):
                continue
            schedule = schedules_by_user_key.get((user.id, definition.key))
            if schedule is None:
                schedule = ReminderTemplateSchedule(
                    user_id=user.id,
                    template_key=definition.key,
                    template_version=definition.version,
                )
                _schedule_from_values(schedule, definition, _default_values(definition))
            try:
                _validate_values(definition, _stored_values(schedule))
            except ReminderTemplateError:
                # A malformed legacy row must fail closed instead of generating an unsafe burst.
                continue
            for offset in range(REMINDER_HORIZON_DAYS):
                local_date = local_now.date() + timedelta(days=offset)
                local_entries = _local_hydration_times(
                    hydration_by_user_day.get((user.id, local_date), []), user
                )
                for scheduled_for, slot_index in _candidate_values(
                    definition, schedule, local_date
                ):
                    if scheduled_for <= local_now or _is_quiet_local(settings, scheduled_for):
                        continue
                    if definition.key == "meal_logging":
                        meal_type = MEAL_SLOT_TYPES[min(slot_index, len(MEAL_SLOT_TYPES) - 1)]
                        if (user.id, local_date, meal_type) in food_entry_keys:
                            continue
                    if definition.key == "hydration" and _has_recent_hydration(
                        scheduled_for,
                        local_entries,
                        schedule.minimum_spacing_minutes,
                    ):
                        continue
                    dedupe_key = (
                        f"{CONTEXTUAL_NOTIFICATION_PREFIX}{user.id}:{definition.key}:"
                        f"{local_date.isoformat()}:{slot_index}"
                    )
                    active_keys.add(dedupe_key)
                    candidates.append(
                        (dedupe_key, user, timezone, definition, scheduled_for, slot_index)
                    )

    existing = (
        db.query(Notification)
        .filter(
            Notification.user_id.in_(user_ids),
            Notification.dedupe_key.like(f"{CONTEXTUAL_NOTIFICATION_PREFIX}%"),
            or_(
                Notification.status == "queued",
                Notification.dedupe_key.in_(active_keys),
            ),
        )
        .all()
    )
    existing_by_user_key = {(row.user_id, row.dedupe_key): row for row in existing}
    created = 0
    for dedupe_key, user, timezone, definition, scheduled_for, slot_index in candidates:
        existing_row = existing_by_user_key.get((user.id, dedupe_key))
        scheduled_for_utc = local_naive_to_utc_naive(scheduled_for, timezone)
        if existing_row is not None:
            if existing_row.status == "queued" or (
                existing_row.status == "cancelled"
                and can_scheduler_reactivate_cancelled_notification(existing_row)
            ):
                was_cancelled = existing_row.status == "cancelled"
                existing_row.status = "queued"
                existing_row.scheduled_for = scheduled_for
                existing_row.scheduled_for_utc = scheduled_for_utc
                if was_cancelled:
                    existing_row.attempt_count = 0
                    existing_row.last_error = None
                    existing_row.next_attempt_at = None
                    existing_row.processing_started_at = None
            continue
        db.add(
            Notification(
                user_id=user.id,
                channel="telegram",
                category=CONTEXTUAL_TEMPLATE_CATEGORY[definition.key],
                event_kind="reminder",
                title=definition.notification_title,
                body=definition.notification_body,
                scheduled_for=scheduled_for,
                scheduled_for_utc=scheduled_for_utc,
                status="queued",
                dedupe_key=dedupe_key,
                action_url=_notification_action_url(definition, scheduled_for.date(), slot_index),
            )
        )
        created += 1

    active_by_user_key = active_keys
    for row in existing:
        if row.status == "queued" and row.dedupe_key not in active_by_user_key:
            row.status = "cancelled"
            row.last_error = "contextual_reminder_not_due"
            row.processing_started_at = None
            row.next_attempt_at = None

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return 0
    return created
