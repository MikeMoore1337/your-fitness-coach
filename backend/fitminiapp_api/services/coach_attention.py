from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, time, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import now_msk_naive, today_in_timezone
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.feedback import WorkoutComment
from fitminiapp_api.models.program import UserProgram, UserWorkout
from fitminiapp_api.models.user import CoachClient, User, UserProfile

ATTENTION_LIMIT = 50
ATTENTION_LOOKBACK_DAYS = 21
FEEDBACK_LOOKBACK_DAYS = 30

_KIND_PRIORITY = {
    "workout_feedback": 0,
    "weekly_check_in": 1,
    "skipped_workout": 2,
    "missed_workout": 3,
    "without_program": 4,
}

_FEEDBACK_LABELS = {
    "easier_than_expected": "легче, чем ожидалось",
    "as_expected": "как ожидалось",
    "harder_than_expected": "тяжелее, чем ожидалось",
}


def _display_name(client: User, relation: CoachClient, profile: UserProfile | None) -> str:
    if relation.private_name and relation.private_name.strip():
        return relation.private_name.strip()
    if profile and profile.full_name and profile.full_name.strip():
        return profile.full_name.strip()
    first_last = " ".join(
        value.strip() for value in (client.first_name, client.last_name) if value and value.strip()
    )
    return first_last or client.username or f"Клиент {client.id}"


def _latest_by_client[AttentionRow](
    rows: Iterable[AttentionRow],
    *,
    client_id_getter: Callable[[AttentionRow], int],
    timestamp_getter: Callable[[AttentionRow], datetime],
    id_getter: Callable[[AttentionRow], int],
) -> dict[int, AttentionRow]:
    latest: dict[int, AttentionRow] = {}
    for row in rows:
        client_id = int(client_id_getter(row))
        current = latest.get(client_id)
        if current is None or (
            timestamp_getter(row),
            id_getter(row),
        ) > (
            timestamp_getter(current),
            id_getter(current),
        ):
            latest[client_id] = row
    return latest


def _event_datetime(workout: UserWorkout) -> datetime:
    return (
        workout.completion_feedback_updated_at
        or workout.completed_at
        or datetime.combine(
            workout.scheduled_date,
            time.min,
        )
    )


def _item(
    *,
    kind: str,
    client_id: int,
    client_name: str,
    title: str,
    reason: str,
    source_kind: str,
    source_id: int,
    source_state: str,
    action: str,
    destination: str,
    created_at: datetime,
) -> dict:
    return {
        "key": f"{kind}:{client_id}:{source_id}",
        "kind": kind,
        "client": {"id": client_id, "name": client_name},
        "title": title,
        "reason": reason,
        "source_kind": source_kind,
        "source_id": source_id,
        "source_state": source_state,
        "action": action,
        "destination": destination,
        "created_at": created_at,
    }


def _sort_key(item: dict) -> tuple[int, float, int, int, str]:
    return (
        _KIND_PRIORITY[item["kind"]],
        -item["created_at"].timestamp(),
        int(item["client"]["id"]),
        int(item["source_id"]),
        item["key"],
    )


def build_coach_attention(
    db: Session,
    coach: User,
    *,
    limit: int = ATTENTION_LIMIT,
) -> dict:
    """Build a bounded, deterministic attention inbox for one coach.

    The query shape is intentionally independent of the number of managed clients.
    Resolution is derived only from authoritative state transitions: a newer
    trainer comment resolves feedback, a new check-in replaces the old one, and
    completed/assigned program state removes the corresponding item.
    """

    relations = (
        db.query(CoachClient, User, UserProfile)
        .join(User, User.id == CoachClient.client_user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .filter(
            CoachClient.coach_user_id == coach.id,
            CoachClient.status == "active",
            User.is_active.is_(True),
        )
        .order_by(CoachClient.client_user_id.asc(), CoachClient.id.asc())
        .all()
    )
    if not relations:
        return {"items": [], "total": 0, "generated_at": now_msk_naive()}

    relation_by_client = {
        int(relation.client_user_id): (relation, user, profile)
        for relation, user, profile in relations
    }
    client_ids = list(relation_by_client)
    generated_at = now_msk_naive()
    lookback_start = generated_at - timedelta(days=ATTENTION_LOOKBACK_DAYS)
    feedback_start = generated_at - timedelta(days=FEEDBACK_LOOKBACK_DAYS)
    local_today = {
        client_id: today_in_timezone(profile.timezone if profile else None)
        for client_id, (_, _, profile) in relation_by_client.items()
    }

    programs = (
        db.query(UserProgram)
        .filter(
            UserProgram.user_id.in_(client_ids),
            UserProgram.is_active.is_(True),
            UserProgram.status.in_(("scheduled", "active")),
        )
        .order_by(UserProgram.user_id.asc(), UserProgram.id.desc())
        .all()
    )
    active_program_ids = {int(program.id) for program in programs}
    active_clients = {int(program.user_id) for program in programs}

    workout_rows = (
        db.query(UserWorkout, UserProgram.user_id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(
            UserProgram.user_id.in_(client_ids),
            or_(
                and_(
                    UserWorkout.scheduled_date
                    >= min(local_today.values()) - timedelta(days=FEEDBACK_LOOKBACK_DAYS),
                    UserWorkout.scheduled_date <= max(local_today.values()),
                ),
                UserWorkout.completion_feedback_updated_at >= feedback_start,
            ),
        )
        .order_by(UserWorkout.scheduled_date.desc(), UserWorkout.id.desc())
        .all()
    )
    workouts = [row[0] for row in workout_rows]
    workout_client_id = {int(workout.id): int(client_id) for workout, client_id in workout_rows}
    workout_ids = list(workout_client_id) or [-1]

    check_ins = (
        db.query(WeeklyCheckIn)
        .filter(
            WeeklyCheckIn.user_id.in_(client_ids),
            WeeklyCheckIn.status == "completed",
            WeeklyCheckIn.created_at >= lookback_start,
        )
        .order_by(
            WeeklyCheckIn.user_id.asc(), WeeklyCheckIn.created_at.desc(), WeeklyCheckIn.id.desc()
        )
        .all()
    )

    comments = (
        db.query(WorkoutComment)
        .filter(
            WorkoutComment.coach_client_id.in_([int(relation.id) for relation, _, _ in relations]),
            WorkoutComment.workout_id.in_(workout_ids),
        )
        .order_by(
            WorkoutComment.workout_id.asc(),
            WorkoutComment.created_at.desc(),
            WorkoutComment.id.desc(),
        )
        .all()
    )
    latest_comment_at: dict[tuple[int, int], datetime] = {}
    relation_client_ids = {
        int(relation.id): int(relation.client_user_id) for relation, _, _ in relations
    }
    for comment in comments:
        client_id = relation_client_ids.get(int(comment.coach_client_id))
        if client_id is None:
            continue
        key = (client_id, int(comment.workout_id))
        latest_comment_at.setdefault(key, comment.created_at)

    items: list[dict] = []
    latest_feedback = _latest_by_client(
        (
            workout
            for workout in workouts
            if workout.status == "completed"
            and (
                workout.completion_feedback
                or (workout.completion_note and workout.completion_note.strip())
            )
            and _event_datetime(workout) >= feedback_start
        ),
        client_id_getter=lambda workout: workout_client_id[int(workout.id)],
        timestamp_getter=_event_datetime,
        id_getter=lambda workout: int(workout.id),
    )
    for client_id, workout in latest_feedback.items():
        relation, client, profile = relation_by_client[client_id]
        event_at = _event_datetime(workout)
        if latest_comment_at.get((client_id, int(workout.id)), datetime.min) >= event_at:
            continue
        reason = (
            "Клиент добавил заметку к завершённой тренировке."
            if workout.completion_note and workout.completion_note.strip()
            else f"Клиент отметил тренировку как «{_FEEDBACK_LABELS.get(workout.completion_feedback, 'завершённую')}»."
        )
        items.append(
            _item(
                kind="workout_feedback",
                client_id=client_id,
                client_name=_display_name(client, relation, profile),
                title="Новая обратная связь по тренировке",
                reason=reason,
                source_kind="workout",
                source_id=int(workout.id),
                source_state=workout.completion_feedback or "note",
                action="review_workout",
                destination=f"/coach?client_id={client_id}&workout_id={workout.id}",
                created_at=event_at,
            )
        )

    latest_check_in = _latest_by_client(
        check_ins,
        client_id_getter=lambda row: row.user_id,
        timestamp_getter=lambda row: row.created_at,
        id_getter=lambda row: int(row.id),
    )
    for client_id, check_in in latest_check_in.items():
        relation, client, profile = relation_by_client[client_id]
        items.append(
            _item(
                kind="weekly_check_in",
                client_id=client_id,
                client_name=_display_name(client, relation, profile),
                title="Новый недельный итог",
                reason="Клиент заполнил недельный итог.",
                source_kind="weekly_check_in",
                source_id=int(check_in.id),
                source_state="completed",
                action="review_check_in",
                destination=f"/coach?client_id={client_id}&focus=weekly_check_in",
                created_at=check_in.created_at,
            )
        )

    latest_skipped = _latest_by_client(
        (
            workout
            for workout in workouts
            if workout.user_program_id in active_program_ids
            and workout.status == "skipped"
            and local_today[workout_client_id[int(workout.id)]]
            - timedelta(days=ATTENTION_LOOKBACK_DAYS)
            <= workout.scheduled_date
            <= local_today[workout_client_id[int(workout.id)]]
        ),
        client_id_getter=lambda workout: workout_client_id[int(workout.id)],
        timestamp_getter=lambda row: datetime.combine(row.scheduled_date, time.min),
        id_getter=lambda row: int(row.id),
    )
    latest_missed = _latest_by_client(
        (
            workout
            for workout in workouts
            if workout.user_program_id in active_program_ids
            and workout.status in {"planned", "in_progress"}
            and workout.scheduled_date < local_today[workout_client_id[int(workout.id)]]
            and workout.scheduled_date
            >= local_today[workout_client_id[int(workout.id)]]
            - timedelta(days=ATTENTION_LOOKBACK_DAYS)
        ),
        client_id_getter=lambda workout: workout_client_id[int(workout.id)],
        timestamp_getter=lambda row: datetime.combine(row.scheduled_date, time.min),
        id_getter=lambda row: int(row.id),
    )
    for kind, candidates, title, reason, state in (
        (
            "skipped_workout",
            latest_skipped,
            "Пропущенная тренировка",
            "Тренировка отмечена как пропущенная.",
            "skipped",
        ),
        (
            "missed_workout",
            latest_missed,
            "Незавершённая тренировка",
            "Плановая дата прошла, а тренировка ещё не завершена.",
            "planned",
        ),
    ):
        for client_id, workout in candidates.items():
            relation, client, profile = relation_by_client[client_id]
            items.append(
                _item(
                    kind=kind,
                    client_id=client_id,
                    client_name=_display_name(client, relation, profile),
                    title=title,
                    reason=reason,
                    source_kind="workout",
                    source_id=int(workout.id),
                    source_state=state,
                    action="review_workout",
                    destination=f"/coach?client_id={client_id}&workout_id={workout.id}",
                    created_at=datetime.combine(workout.scheduled_date, time.min),
                )
            )

    for client_id in sorted(set(client_ids) - active_clients):
        relation, client, profile = relation_by_client[client_id]
        items.append(
            _item(
                kind="without_program",
                client_id=client_id,
                client_name=_display_name(client, relation, profile),
                title="Нет активной программы",
                reason="У клиента сейчас нет назначенной активной программы.",
                source_kind="client",
                source_id=client_id,
                source_state="none",
                action="assign_program",
                destination=f"/coach?client_id={client_id}&focus=program",
                created_at=relation.created_at,
            )
        )

    items.sort(key=_sort_key, reverse=False)
    total = len(items)
    items = items[: max(1, min(limit, 100))]
    return {"items": items, "total": total, "generated_at": generated_at}


__all__ = ["build_coach_attention"]
