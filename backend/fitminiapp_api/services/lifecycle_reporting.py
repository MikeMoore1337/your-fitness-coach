from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import TypedDict
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import (
    DEFAULT_TIMEZONE,
    get_timezone,
    is_valid_timezone,
    local_naive_to_utc_naive,
    now_msk_naive,
)
from fitminiapp_api.models.food_diary import FoodDiaryCopyOperation, FoodDiaryRepeatPreview
from fitminiapp_api.models.lifecycle_milestone import (
    LIFECYCLE_MILESTONE_TYPES,
    LifecycleMilestone,
)
from fitminiapp_api.models.program import UserProgram, UserWorkout
from fitminiapp_api.models.user import User
from fitminiapp_api.services.lifecycle_milestones import (
    MEANINGFUL_MILESTONE_TYPES,
)
from fitminiapp_api.services.workout_recovery import (
    missed_at_for_workout,
    recoverable_missed_workouts,
)

LIFECYCLE_KPI_KEYS = (
    "activation_rate",
    "time_to_first_useful_action",
    "first_workout_completion_rate",
    "first_week_value_rate",
    "d1_meaningful_return",
    "d7_meaningful_return",
    "d30_meaningful_return",
    "missed_workout_recovery_conversion",
    "recovery_to_completion_rate",
    "time_to_recovery",
    "nutrition_repeat_rate",
    "progress_next_action_completion_rate",
    "weekly_loop_completion",
)


_UserEvents = dict[str, list[datetime]]


class _RecoveryMetrics(TypedDict):
    missed_denominator: int
    missed_numerator: int
    completion_denominator: int
    completion_numerator: int
    recovery_count: int
    median_recovery_seconds: float | None


class _NutritionRepeatMetrics(TypedDict):
    eligible_opportunities: int
    confirmed_repeats: int
    repeat_rate_percent: float | None
    preview_count: int
    confirmed_preview_count: int
    preview_to_confirmed_percent: float | None
    median_seconds: float | None
    persistence_failures: int
    persistence_failure_rate_percent: float | None
    duplicate_prevention_count: int


def _empty_events() -> _UserEvents:
    return {milestone_type: [] for milestone_type in LIFECYCLE_MILESTONE_TYPES}


def _as_utc_naive(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def _report_timezone(user: User) -> tuple[ZoneInfo, bool]:
    raw_timezone = getattr(getattr(user, "profile", None), "timezone", None)
    if raw_timezone and is_valid_timezone(raw_timezone):
        return get_timezone(raw_timezone), False
    return ZoneInfo("UTC"), True


def _registration_at_utc(user: User) -> datetime:
    # User.created_at predates this ledger and is stored as Moscow wall time in
    # the current account contract. Keep that conversion explicit at the report
    # boundary; milestone evidence itself is UTC-naive.
    return local_naive_to_utc_naive(user.created_at, DEFAULT_TIMEZONE)


def _local_date(value: datetime, zone: ZoneInfo) -> date:
    return value.replace(tzinfo=UTC).astimezone(zone).date()


def _in_window(value: datetime, start: datetime, end: datetime) -> bool:
    return start <= value < end


def _first_after(values: list[datetime], start: datetime) -> datetime | None:
    return next((value for value in values if value >= start), None)


def _first_program_backed_start(
    events: _UserEvents,
    *,
    not_before: datetime,
) -> datetime | None:
    for started_at in events["workout_started"]:
        if started_at >= not_before and any(
            not_before <= activated_at <= started_at for activated_at in events["program_activated"]
        ):
            return started_at
    return None


def _window_dates(
    events: _UserEvents,
    *,
    registration_at: datetime,
    zone: ZoneInfo,
    duration_days: int,
) -> set[date]:
    end = registration_at + timedelta(days=duration_days)
    return {
        _local_date(value, zone)
        for milestone_type in MEANINGFUL_MILESTONE_TYPES
        for value in events[milestone_type]
        if _in_window(value, registration_at, end)
    }


def _kpi(
    *,
    key: str,
    numerator: int,
    denominator: int,
    cohort_size: int,
    window: str,
    median_seconds: float | None = None,
    include_rate: bool = True,
) -> dict[str, object]:
    return {
        "key": key,
        "numerator": numerator,
        "denominator": denominator,
        "cohort_size": cohort_size,
        "rate_percent": (
            round(numerator * 100 / denominator, 1) if denominator and include_rate else None
        ),
        "median_seconds": round(median_seconds, 1) if median_seconds is not None else None,
        "window": window,
    }


def _recovery_timezone_name(user: User) -> str:
    raw_timezone = getattr(getattr(user, "profile", None), "timezone", None)
    return raw_timezone if raw_timezone and is_valid_timezone(raw_timezone) else "UTC"


def _nutrition_repeat_metrics(
    db: Session,
    *,
    eligible_users: list[User],
    period_start: datetime,
    period_end: datetime,
) -> _NutritionRepeatMetrics:
    user_ids = [user.id for user in eligible_users]
    if not user_ids:
        return {
            "eligible_opportunities": 0,
            "confirmed_repeats": 0,
            "repeat_rate_percent": None,
            "preview_count": 0,
            "confirmed_preview_count": 0,
            "preview_to_confirmed_percent": None,
            "median_seconds": None,
            "persistence_failures": 0,
            "persistence_failure_rate_percent": None,
            "duplicate_prevention_count": 0,
        }

    previews = (
        db.query(FoodDiaryRepeatPreview)
        .filter(
            FoodDiaryRepeatPreview.user_id.in_(user_ids),
            FoodDiaryRepeatPreview.created_at >= period_start,
            FoodDiaryRepeatPreview.created_at <= period_end,
        )
        .all()
    )
    preview_by_id = {preview.id: preview for preview in previews}
    operations = (
        db.query(FoodDiaryCopyOperation)
        .filter(
            FoodDiaryCopyOperation.user_id.in_(user_ids),
            FoodDiaryCopyOperation.preview_id.in_(list(preview_by_id)),
            FoodDiaryCopyOperation.created_at >= period_start,
            FoodDiaryCopyOperation.created_at <= period_end,
        )
        .all()
        if preview_by_id
        else []
    )
    durations = [
        (operation.created_at - preview_by_id[operation.preview_id].created_at).total_seconds()
        for operation in operations
        if operation.preview_id in preview_by_id
        and operation.created_at >= preview_by_id[operation.preview_id].created_at
    ]
    confirmed_repeats = len(operations)
    eligible_opportunities = len(previews)
    persistence_failures = sum(preview.persistence_failure_count for preview in previews)
    persistence_attempts = confirmed_repeats + persistence_failures
    duplicate_prevention_count = sum(operation.replay_count or 0 for operation in operations)
    return {
        "eligible_opportunities": eligible_opportunities,
        "confirmed_repeats": confirmed_repeats,
        "repeat_rate_percent": (
            round(confirmed_repeats * 100 / eligible_opportunities, 1)
            if eligible_opportunities
            else None
        ),
        "preview_count": eligible_opportunities,
        "confirmed_preview_count": confirmed_repeats,
        "preview_to_confirmed_percent": (
            round(confirmed_repeats * 100 / eligible_opportunities, 1)
            if eligible_opportunities
            else None
        ),
        "median_seconds": median(durations) if durations else None,
        "persistence_failures": persistence_failures,
        "persistence_failure_rate_percent": (
            round(persistence_failures * 100 / persistence_attempts, 1)
            if persistence_attempts
            else None
        ),
        "duplicate_prevention_count": duplicate_prevention_count,
    }


def _recovery_metrics(
    db: Session,
    *,
    eligible_users: list[User],
    period_start: datetime,
    now: datetime,
) -> _RecoveryMetrics:
    """Calculate instance-level recovery facts without exposing identifiers."""

    user_by_id = {user.id: user for user in eligible_users}
    missed_instances: dict[int, tuple[int, datetime]] = {}
    missed_rows = (
        db.query(LifecycleMilestone)
        .filter(
            LifecycleMilestone.user_id.in_(user_by_id),
            LifecycleMilestone.milestone_type == "workout_missed",
            LifecycleMilestone.workout_id.is_not(None),
            LifecycleMilestone.missed_at.is_not(None),
            LifecycleMilestone.missed_at >= period_start,
            LifecycleMilestone.missed_at <= now,
        )
        .order_by(LifecycleMilestone.missed_at.asc(), LifecycleMilestone.id.asc())
        .all()
        if user_by_id
        else []
    )
    for row in missed_rows:
        if row.workout_id is not None and row.missed_at is not None:
            missed_instances.setdefault(row.workout_id, (row.user_id, row.missed_at))

    # A currently outstanding missed workout has no ledger row until the user
    # confirms an action, so derive it from the authoritative schedule too.
    for user in eligible_users:
        for workout in recoverable_missed_workouts(db, user):
            if workout.id in missed_instances:
                continue
            missed_at = missed_at_for_workout(workout, user)
            if period_start <= missed_at <= now:
                missed_instances[workout.id] = (user.id, missed_at)

    recovery_rows = (
        db.query(LifecycleMilestone)
        .filter(
            LifecycleMilestone.user_id.in_(user_by_id),
            LifecycleMilestone.milestone_type == "recovery_action_confirmed",
            LifecycleMilestone.workout_id.is_not(None),
            LifecycleMilestone.missed_at.is_not(None),
            LifecycleMilestone.occurred_at >= period_start,
            LifecycleMilestone.occurred_at <= now,
        )
        .order_by(LifecycleMilestone.occurred_at.asc(), LifecycleMilestone.id.asc())
        .all()
        if user_by_id
        else []
    )
    confirmed_recoveries: dict[int, LifecycleMilestone] = {}
    for row in recovery_rows:
        if row.workout_id is None or row.missed_at is None:
            continue
        if not row.missed_at <= row.occurred_at <= row.missed_at + timedelta(days=7):
            continue
        confirmed_recoveries.setdefault(row.workout_id, row)

    recovery_workout_ids = set(confirmed_recoveries)
    workout_rows = (
        db.query(UserWorkout, UserProgram)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(UserWorkout.id.in_(recovery_workout_ids))
        .all()
        if recovery_workout_ids
        else []
    )
    completed_by_id: dict[int, datetime] = {}
    for workout, program in workout_rows:
        account = user_by_id.get(program.user_id)
        if account is None or workout.status != "completed" or workout.completed_at is None:
            continue
        completed_by_id[workout.id] = local_naive_to_utc_naive(
            workout.completed_at,
            _recovery_timezone_name(account),
        )

    recovered_missed_instances = set(confirmed_recoveries).intersection(missed_instances)
    completion_denominator = len(confirmed_recoveries)
    completion_numerator = sum(
        1
        for workout_id, recovery in confirmed_recoveries.items()
        if workout_id in completed_by_id
        and recovery.occurred_at
        <= completed_by_id[workout_id]
        <= recovery.occurred_at + timedelta(days=7)
    )
    recovery_durations = [
        (recovery.occurred_at - recovery.missed_at).total_seconds()
        for recovery in confirmed_recoveries.values()
        if recovery.missed_at is not None
    ]
    return {
        "missed_denominator": len(missed_instances),
        "missed_numerator": len(recovered_missed_instances),
        "completion_denominator": completion_denominator,
        "completion_numerator": completion_numerator,
        "recovery_count": len(confirmed_recoveries),
        "median_recovery_seconds": median(recovery_durations) if recovery_durations else None,
    }


def _quality_report(
    db: Session,
    *,
    eligible_users: list[User],
    rows: list[LifecycleMilestone],
    events: dict[int, _UserEvents],
    cohort_since_msk: datetime,
    now: datetime,
) -> dict[str, object]:
    duplicate_counts = Counter((row.user_id, row.milestone_type, row.occurred_at) for row in rows)
    duplicate_milestones = sum(count - 1 for count in duplicate_counts.values() if count > 1)
    invalid_milestones = sum(
        1
        for row in rows
        if row.milestone_type not in LIFECYCLE_MILESTONE_TYPES
        or row.surface != "server"
        or not row.server_confirmed
        or row.authoritative_outcome_status != "confirmed"
    )
    impossible_order = 0
    for user in eligible_users:
        user_events = events[user.id]
        registration_at = _registration_at_utc(user)
        first_program = (
            user_events["program_activated"][0] if user_events["program_activated"] else None
        )
        first_start = user_events["workout_started"][0] if user_events["workout_started"] else None
        first_complete = (
            user_events["workout_completed"][0] if user_events["workout_completed"] else None
        )
        impossible_order += sum(
            1
            for values in user_events.values()
            for value in values
            if value < registration_at or value > now + timedelta(minutes=5)
        )
        if first_program is not None and first_program < registration_at:
            impossible_order += 1
        if first_start is not None and (
            first_start < registration_at
            or (first_program is not None and first_start < first_program)
        ):
            impossible_order += 1
        if first_complete is not None and (
            first_complete < registration_at
            or (first_start is not None and first_complete < first_start)
        ):
            impossible_order += 1

    excluded_role_accounts = (
        db.query(User.id)
        .filter(
            User.created_at >= cohort_since_msk,
            User.created_at <= now_msk_naive(),
            (User.is_coach.is_(True) | User.is_admin.is_(True)),
        )
        .count()
    )
    timezone_fallback_accounts = sum(1 for user in eligible_users if _report_timezone(user)[1])
    client_success_without_server = sum(
        1 for row in rows if row.surface != "server" or not row.server_confirmed
    )
    status = (
        "attention"
        if any(
            (
                duplicate_milestones,
                invalid_milestones,
                impossible_order,
                client_success_without_server,
            )
        )
        else "clean"
    )
    return {
        "status": status,
        "duplicate_milestones": duplicate_milestones,
        "impossible_order": impossible_order,
        "client_success_without_server": client_success_without_server,
        "invalid_milestones": invalid_milestones,
        "excluded_role_accounts": excluded_role_accounts,
        "timezone_fallback_accounts": timezone_fallback_accounts,
    }


def lifecycle_funnel_report(db: Session, *, period_days: int) -> dict[str, object]:
    if period_days < 7 or period_days > 730:
        raise ValueError("period_days must be between 7 and 730")

    now_aware = datetime.now(UTC)
    now = now_aware.replace(tzinfo=None)
    cohort_since_msk = now_msk_naive() - timedelta(days=period_days)
    users = (
        db.query(User)
        .options(joinedload(User.profile))
        .filter(
            User.created_at >= cohort_since_msk,
            User.created_at <= now_msk_naive(),
            User.is_coach.is_(False),
            User.is_admin.is_(False),
        )
        .order_by(User.created_at.asc(), User.id.asc())
        .all()
        if settings.app_env == "prod"
        else []
    )
    user_ids = [user.id for user in users]
    rows = (
        db.query(LifecycleMilestone)
        .filter(LifecycleMilestone.user_id.in_(user_ids))
        .order_by(LifecycleMilestone.user_id.asc(), LifecycleMilestone.occurred_at.asc())
        .all()
        if user_ids
        else []
    )
    events: dict[int, _UserEvents] = defaultdict(_empty_events)
    for row in rows:
        if row.user_id in user_ids and row.milestone_type in LIFECYCLE_MILESTONE_TYPES:
            events[row.user_id][row.milestone_type].append(row.occurred_at)

    activation_count = 0
    first_useful_times: list[float] = []
    first_useful_users: set[int] = set()
    first_workout_completed = 0
    first_week_users: list[int] = []
    first_week_value = 0
    d1_denominator = d1_return = 0
    d7_denominator = d7_return = 0
    d30_denominator = d30_return = 0
    nutrition_denominator = nutrition_repeat = 0
    weekly_denominator = weekly_loop = 0
    progress_action_denominator = progress_action_completed = 0
    progress_action_times: list[float] = []
    complete_week_starts: set[date] = set()

    for user in users:
        user_events = events[user.id]
        registration_at = _registration_at_utc(user)
        zone, _timezone_fallback = _report_timezone(user)
        registration_day = _local_date(registration_at, zone)
        now_local_day = now_aware.astimezone(zone).date()

        onboarding_at = _first_after(user_events["onboarding_completed"], registration_at)
        program_at = _first_after(user_events["program_activated"], registration_at)
        useful_at = _first_program_backed_start(user_events, not_before=registration_at)
        activation_ready = (
            onboarding_at is not None
            and program_at is not None
            and useful_at is not None
            and onboarding_at <= registration_at + timedelta(hours=24)
            and program_at <= registration_at + timedelta(hours=24)
            and useful_at <= registration_at + timedelta(hours=24)
        )
        if activation_ready:
            activation_count += 1

        if useful_at is not None:
            first_useful_users.add(user.id)
            first_useful_times.append((useful_at - registration_at).total_seconds())
            completed_at = _first_after(user_events["workout_completed"], useful_at)
            if completed_at is not None and completed_at <= useful_at + timedelta(hours=72):
                first_workout_completed += 1

        first_week_matured = registration_at + timedelta(days=7) <= now
        if first_week_matured:
            first_week_users.append(user.id)
            complete_week_starts.add(registration_day - timedelta(days=registration_day.weekday()))
            week_end = registration_at + timedelta(days=7)
            completed_workout = any(
                _in_window(value, registration_at, week_end)
                for value in user_events["workout_completed"]
            )
            additional_action = any(
                _in_window(value, registration_at, week_end)
                for milestone_type in (
                    "nutrition_entry_confirmed",
                    "weekly_review_completed",
                    "recovery_action_confirmed",
                    "progress_next_action_completed",
                )
                for value in user_events[milestone_type]
            )
            meaningful_days = _window_dates(
                user_events,
                registration_at=registration_at,
                zone=zone,
                duration_days=7,
            )
            if completed_workout and additional_action and len(meaningful_days) >= 2:
                first_week_value += 1

        for offset, target in ((1, "d1"), (7, "d7"), (30, "d30")):
            if registration_day + timedelta(days=offset) > now_local_day:
                continue
            target_day = registration_day + timedelta(days=offset)
            returned = any(
                _local_date(value, zone) == target_day
                for milestone_type in MEANINGFUL_MILESTONE_TYPES
                for value in user_events[milestone_type]
            )
            if target == "d1":
                d1_denominator += 1
                d1_return += int(returned)
            elif target == "d7":
                d7_denominator += 1
                d7_return += int(returned)
            else:
                d30_denominator += 1
                d30_return += int(returned)

        nutrition_dates = {
            _local_date(value, zone)
            for value in user_events["nutrition_entry_confirmed"]
            if _in_window(value, registration_at, registration_at + timedelta(days=7))
        }
        if nutrition_dates:
            nutrition_denominator += 1
            nutrition_repeat += int(len(nutrition_dates) >= 2)

        if first_week_matured:
            weekly_denominator += 1
            week_end = registration_at + timedelta(days=7)
            review_at = _first_after(user_events["weekly_review_completed"], registration_at)
            if review_at is not None and _in_window(review_at, registration_at, week_end):
                progress_action_denominator += 1
                action_at = _first_after(user_events["progress_next_action_completed"], review_at)
                if action_at is not None and _in_window(action_at, review_at, week_end):
                    progress_action_completed += 1
                    progress_action_times.append((action_at - review_at).total_seconds())
                    weekly_loop += 1

    cohort_size = len(users)
    recovery_accounts = (
        db.query(User)
        .options(joinedload(User.profile))
        .filter(
            User.created_at <= now_msk_naive(),
            User.is_coach.is_(False),
            User.is_admin.is_(False),
        )
        .order_by(User.id.asc())
        .all()
        if settings.app_env == "prod"
        else []
    )
    recovery_metrics = _recovery_metrics(
        db,
        eligible_users=recovery_accounts,
        period_start=now - timedelta(days=period_days),
        now=now,
    )
    repeat_metrics = _nutrition_repeat_metrics(
        db,
        eligible_users=users,
        period_start=cohort_since_msk,
        period_end=now_msk_naive(),
    )
    quality = _quality_report(
        db,
        eligible_users=users,
        rows=rows,
        events=events,
        cohort_since_msk=cohort_since_msk,
        now=now,
    )
    complete_weekly_cohorts = len(complete_week_starts)
    effect_status = "NOT_YET_PROVEN"
    effect_note = (
        "Эффект можно оценивать только после baseline и минимум четырёх полных недельных когорт; "
        "текущий отчёт показывает факты без проверки значимости."
    )

    kpis = [
        _kpi(
            key="activation_rate",
            numerator=activation_count,
            denominator=cohort_size,
            cohort_size=cohort_size,
            window="после регистрации, первые 24 часа",
        ),
        _kpi(
            key="time_to_first_useful_action",
            numerator=len(first_useful_times),
            denominator=cohort_size,
            cohort_size=cohort_size,
            window="от регистрации до первой начатой тренировки",
            median_seconds=median(first_useful_times) if first_useful_times else None,
        ),
        _kpi(
            key="first_workout_completion_rate",
            numerator=first_workout_completed,
            denominator=len(first_useful_users),
            cohort_size=cohort_size,
            window="первая начатая тренировка, завершение до 72 часов",
        ),
        _kpi(
            key="first_week_value_rate",
            numerator=first_week_value,
            denominator=len(first_week_users),
            cohort_size=cohort_size,
            window="первые 7 дней, только полные окна",
        ),
        _kpi(
            key="d1_meaningful_return",
            numerator=d1_return,
            denominator=d1_denominator,
            cohort_size=cohort_size,
            window="следующий календарный день",
        ),
        _kpi(
            key="d7_meaningful_return",
            numerator=d7_return,
            denominator=d7_denominator,
            cohort_size=cohort_size,
            window="седьмой календарный день",
        ),
        _kpi(
            key="d30_meaningful_return",
            numerator=d30_return,
            denominator=d30_denominator,
            cohort_size=cohort_size,
            window="тридцатый календарный день",
        ),
        _kpi(
            key="missed_workout_recovery_conversion",
            numerator=recovery_metrics["missed_numerator"],
            denominator=recovery_metrics["missed_denominator"],
            cohort_size=len(recovery_accounts),
            window="тот же пропущенный экземпляр, подтверждение в течение 7 дней после missed_at",
        ),
        _kpi(
            key="recovery_to_completion_rate",
            numerator=recovery_metrics["completion_numerator"],
            denominator=recovery_metrics["completion_denominator"],
            cohort_size=len(recovery_accounts),
            window="тот же восстановленный экземпляр, завершение в течение 7 дней",
        ),
        _kpi(
            key="time_to_recovery",
            numerator=recovery_metrics["recovery_count"],
            denominator=recovery_metrics["recovery_count"],
            cohort_size=len(recovery_accounts),
            window="от missed_at до серверного подтверждения восстановления",
            median_seconds=(
                float(recovery_metrics["median_recovery_seconds"])
                if recovery_metrics["median_recovery_seconds"] is not None
                else None
            ),
            include_rate=False,
        ),
        _kpi(
            key="nutrition_repeat_rate",
            numerator=nutrition_repeat,
            denominator=nutrition_denominator,
            cohort_size=cohort_size,
            window="минимум два календарных дня записи питания в первые 7 дней",
        ),
        _kpi(
            key="progress_next_action_completion_rate",
            numerator=progress_action_completed,
            denominator=progress_action_denominator,
            cohort_size=cohort_size,
            window="серверное подтверждение выбранного шага после недельного обзора, первые 7 дней",
            median_seconds=median(progress_action_times) if progress_action_times else None,
        ),
        _kpi(
            key="weekly_loop_completion",
            numerator=weekly_loop,
            denominator=weekly_denominator,
            cohort_size=cohort_size,
            window="недельный обзор и выбранный шаг подтверждены в первые 7 дней",
        ),
    ]

    coverage_note = (
        "Когортные KPI считают серверно подтверждённые агрегаты по новым аккаунтам-клиентам; "
        "показатели восстановления — по всем доступным клиентским аккаунтам за период. Демо-сессии не создают "
        "аккаунты и события; root- и trainer-аккаунты исключены. D1/D7/D30 и recovery используют "
        "часовой пояс профиля, а при его отсутствии — UTC. Raw events, идентификаторы и данные "
        "питания в отчёт не попадают. Repeat-метрики используют только серверные preview/confirmation "
        "факты и не включают названия, количества или nutrient payload."
    )
    exclusions = [
        "root/admin и trainer-аккаунты",
        "demo/test/staging/synthetic/load/technical данные вне production client-когорты",
        "просмотры, открытия, показы, неуспешные отправки и неподтверждённые preview",
    ]
    if settings.app_env != "prod":
        coverage_note = (
            "Отчёт доступен только в production: non-production окружение исключено fail-closed, "
            "чтобы demo/test/staging данные не попали в KPI."
        )
        exclusions.insert(0, "любые аккаунты и события non-production окружений")

    return {
        "period_days": period_days,
        "cohort_since": now_aware - timedelta(days=period_days),
        "cohort_until": now_aware,
        "as_of": now_aware,
        "cohort_size": cohort_size,
        "complete_weekly_cohorts": complete_weekly_cohorts,
        "eligible_real_account_count": cohort_size,
        "recovery_eligible_real_account_count": len(recovery_accounts),
        "nutrition_repeat_metrics": repeat_metrics,
        "analytics_provider_status": "not_connected",
        "effect_status": effect_status,
        "effect_note": effect_note,
        "coverage_note": coverage_note,
        "exclusions": exclusions,
        "data_quality": quality,
        "kpis": kpis,
    }
