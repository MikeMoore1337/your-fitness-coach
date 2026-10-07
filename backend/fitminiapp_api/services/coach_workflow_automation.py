from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import (
    get_user_timezone_name,
    now_msk_naive,
    today_in_timezone,
)
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.coach_crm import CoachTask
from fitminiapp_api.models.coach_reviews import CoachCheckInReview
from fitminiapp_api.models.program import ProgramRevision, UserProgram, UserWorkout
from fitminiapp_api.models.user import CoachClient, User, UserProfile
from fitminiapp_api.services.audit import record_audit_event

RULESET_VERSION = "coach-workflow-v1"
MAX_PROPOSALS = 100
SOURCE_LOOKBACK_DAYS = 30
REVIEW_DUE_AFTER = timedelta(hours=48)
MAX_SOURCE_ROWS = 500

_PROGRAM_REVISION_KINDS = (
    "plan_updated",
    "block_created",
    "block_updated",
    "block_status_changed",
)


@dataclass(frozen=True)
class _ClientContext:
    client: User
    profile: UserProfile | None
    client_name: str
    local_today: date


@dataclass(frozen=True)
class _WorkflowEvent:
    event_kind: str
    rule_id: str
    client_id: int
    client_name: str
    source_kind: str
    source_id: int
    occurred_at: datetime
    title: str
    reason: str
    priority: str

    @property
    def key(self) -> str:
        return f"{self.event_kind}:{self.client_id}:{self.source_id}:{self.rule_id}"

    @property
    def idempotency_key(self) -> str:
        return f"coach-workflow-v1:{self.client_id}:{self.source_id}:{self.rule_id}"


def _client_name(client: User, relation: CoachClient, profile: UserProfile | None) -> str:
    if relation.private_name and relation.private_name.strip():
        return relation.private_name.strip()
    if profile and profile.full_name and profile.full_name.strip():
        return profile.full_name.strip()
    return client.username or f"Клиент #{client.id}"


def _contexts(db: Session, coach: User) -> dict[int, _ClientContext]:
    rows = (
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
    return {
        int(client.id): _ClientContext(
            client=client,
            profile=profile,
            client_name=_client_name(client, relation, profile),
            local_today=today_in_timezone(profile.timezone if profile else None),
        )
        for relation, client, profile in rows
    }


def _latest_by_client[T](
    rows: list[T],
    client_id: Callable[[T], int],
    occurred_at: Callable[[T], datetime],
) -> dict[int, T]:
    latest: dict[int, T] = {}
    for row in rows:
        client_key = int(client_id(row))
        current = latest.get(client_key)
        if current is None or occurred_at(row) > occurred_at(current):
            latest[client_key] = row
    return latest


def _build_events(db: Session, coach: User) -> list[_WorkflowEvent]:
    contexts = _contexts(db, coach)
    if not contexts:
        return []

    client_ids = list(contexts)
    generated_at = now_msk_naive()
    lookback_start = generated_at - timedelta(days=SOURCE_LOOKBACK_DAYS)
    events: list[_WorkflowEvent] = []

    active_programs = (
        db.query(UserProgram)
        .filter(
            UserProgram.user_id.in_(client_ids),
            UserProgram.is_active.is_(True),
            UserProgram.status.in_(("scheduled", "active")),
        )
        .order_by(UserProgram.user_id.asc(), UserProgram.id.desc())
        .limit(MAX_SOURCE_ROWS)
        .all()
    )
    active_program_by_client = {
        int(program.user_id): program for program in reversed(active_programs)
    }
    active_program_ids = list(active_program_by_client.values())
    active_program_id_set = {int(program.id) for program in active_program_ids}

    missed_workouts = (
        db.query(UserWorkout, UserProgram.user_id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(
            UserProgram.user_id.in_(client_ids),
            UserWorkout.user_program_id.in_(active_program_id_set or [-1]),
            UserWorkout.status.in_(("planned", "in_progress")),
            UserWorkout.scheduled_date
            >= min(context.local_today for context in contexts.values())
            - timedelta(days=SOURCE_LOOKBACK_DAYS),
        )
        .order_by(UserWorkout.scheduled_date.desc(), UserWorkout.id.desc())
        .limit(MAX_SOURCE_ROWS)
        .all()
    )
    latest_missed = _latest_by_client(
        missed_workouts,
        lambda row: row[1],
        lambda row: datetime.combine(row[0].scheduled_date, datetime.min.time()),
    )
    for client_id, (workout, _owner_id) in latest_missed.items():
        context = contexts[client_id]
        if workout.scheduled_date >= context.local_today:
            continue
        events.append(
            _WorkflowEvent(
                event_kind="missed_workout",
                rule_id="missed-workout-v1",
                client_id=client_id,
                client_name=context.client_name,
                source_kind="workout",
                source_id=int(workout.id),
                occurred_at=datetime.combine(workout.scheduled_date, datetime.min.time()),
                title="Проверить пропущенную тренировку",
                reason="Плановая дата прошла, а тренировка ещё не завершена.",
                priority="soon",
            )
        )

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
        .limit(MAX_SOURCE_ROWS)
        .all()
    )
    check_in_ids = [int(check_in.id) for check_in in check_ins]
    reviewed_ids = {
        int(check_in_id)
        for (check_in_id,) in (
            db.query(CoachCheckInReview.check_in_id)
            .filter(
                CoachCheckInReview.coach_user_id == coach.id,
                CoachCheckInReview.check_in_id.in_(check_in_ids or [-1]),
            )
            .all()
        )
    }
    pending_check_ins = _latest_by_client(
        [check_in for check_in in check_ins if int(check_in.id) not in reviewed_ids],
        lambda check_in: check_in.user_id,
        lambda check_in: check_in.created_at,
    )
    for client_id, check_in in pending_check_ins.items():
        context = contexts[int(client_id)]
        is_due = generated_at - check_in.created_at >= REVIEW_DUE_AFTER
        event_kind = "review_due" if is_due else "check_in_submitted"
        rule_id = "review-due-v1" if is_due else "check-in-submitted-v1"
        title = "Проверить просроченный недельный итог" if is_due else "Проверить недельный итог"
        reason = (
            "Недельный итог ожидает проверки тренера больше двух дней."
            if is_due
            else "Клиент отправил недельный итог; проверьте его вручную."
        )
        events.append(
            _WorkflowEvent(
                event_kind=event_kind,
                rule_id=rule_id,
                client_id=int(client_id),
                client_name=context.client_name,
                source_kind="weekly_check_in",
                source_id=int(check_in.id),
                occurred_at=check_in.created_at,
                title=title,
                reason=reason,
                priority="urgent",
            )
        )

    revisions = (
        db.query(ProgramRevision, UserProgram.user_id)
        .join(UserProgram, UserProgram.id == ProgramRevision.user_program_id)
        .filter(
            UserProgram.user_id.in_(client_ids),
            UserProgram.is_active.is_(True),
            ProgramRevision.actor_role == "self",
            ProgramRevision.change_kind.in_(_PROGRAM_REVISION_KINDS),
            ProgramRevision.created_at >= lookback_start,
        )
        .order_by(ProgramRevision.created_at.desc(), ProgramRevision.id.desc())
        .limit(MAX_SOURCE_ROWS)
        .all()
    )
    latest_revisions = _latest_by_client(
        revisions,
        lambda row: row[1],
        lambda row: row[0].created_at,
    )
    for client_id, (revision, _owner_id) in latest_revisions.items():
        context = contexts[int(client_id)]
        events.append(
            _WorkflowEvent(
                event_kind="program_revision_ready",
                rule_id="program-revision-ready-v1",
                client_id=int(client_id),
                client_name=context.client_name,
                source_kind="program",
                source_id=int(revision.id),
                occurred_at=revision.created_at,
                title="Проверить готовую ревизию программы",
                reason="Клиент изменил программу; решение остаётся за тренером.",
                priority="soon",
            )
        )

    priority_order = {"urgent": 0, "soon": 1}
    events.sort(
        key=lambda event: (
            priority_order[event.priority],
            -event.occurred_at.timestamp(),
            event.client_id,
            event.source_id,
            event.rule_id,
        )
    )
    return events[:MAX_PROPOSALS]


def _proposal(
    event: _WorkflowEvent,
    *,
    outcome: str,
    task: CoachTask | None = None,
) -> dict[str, object]:
    return {
        "key": event.key,
        "event_kind": event.event_kind,
        "rule_id": event.rule_id,
        "client_id": event.client_id,
        "client_name": event.client_name,
        "source_kind": event.source_kind,
        "source_id": event.source_id,
        "occurred_at": event.occurred_at,
        "title": event.title,
        "reason": event.reason,
        "priority": event.priority,
        "outcome": outcome,
        "task_id": int(task.id) if task is not None else None,
        "task_state": task.state if task is not None else None,
    }


def _task_kind(event: _WorkflowEvent) -> str:
    return {
        "check_in_submitted": "review_check_in",
        "review_due": "review_check_in",
        "missed_workout": "contact_client",
        "program_revision_ready": "update_program",
    }[event.event_kind]


def evaluate_coach_workflow(
    db: Session,
    coach: User,
    *,
    apply: bool,
) -> dict[str, object]:
    events = _build_events(db, coach)
    idempotency_keys = [event.idempotency_key for event in events]
    existing_by_key = {
        task.idempotency_key: task
        for task in (
            db.query(CoachTask)
            .filter(
                CoachTask.coach_user_id == coach.id,
                CoachTask.idempotency_key.in_(idempotency_keys or ["__none__"]),
            )
            .all()
        )
        if task.idempotency_key is not None
    }

    proposals: list[dict[str, object]] = []
    tasks_created = 0
    tasks_reused = 0
    for event in events:
        existing = existing_by_key.get(event.idempotency_key)
        if existing is not None:
            tasks_reused += 1
            proposals.append(_proposal(event, outcome="already_processed", task=existing))
            continue
        if not apply:
            proposals.append(_proposal(event, outcome="draft"))
            continue

        task: CoachTask | None = None
        try:
            with db.begin_nested():
                task = CoachTask(
                    coach_user_id=coach.id,
                    client_user_id=event.client_id,
                    idempotency_key=event.idempotency_key,
                    title=event.title,
                    due_at_utc=datetime.now(UTC).replace(tzinfo=None),
                    timezone=get_user_timezone_name(coach),
                    kind=_task_kind(event),
                    source_kind=event.source_kind,
                    source_id=event.source_id,
                    reason=event.reason,
                )
                db.add(task)
                db.flush()
        except IntegrityError:
            task = (
                db.query(CoachTask)
                .filter(
                    CoachTask.coach_user_id == coach.id,
                    CoachTask.idempotency_key == event.idempotency_key,
                )
                .first()
            )
            if task is None:
                raise
            tasks_reused += 1
            existing_by_key[event.idempotency_key] = task
            proposals.append(_proposal(event, outcome="already_processed", task=task))
            continue

        if task is None:
            raise RuntimeError("Workflow task was not materialized")
        tasks_created += 1
        existing_by_key[event.idempotency_key] = task
        proposals.append(_proposal(event, outcome="created", task=task))

    if apply:
        record_audit_event(
            db,
            actor_user_id=coach.id,
            target_user_id=coach.id,
            action="coach.workflow_automation_evaluated",
            resource_type="coach_workflow",
            resource_id=coach.id,
            details={
                "ruleset_version": RULESET_VERSION,
                "events_evaluated": len(events),
                "tasks_created": tasks_created,
                "tasks_reused": tasks_reused,
                "reason_codes": sorted({event.rule_id for event in events}),
            },
        )
        db.commit()

    return {
        "ruleset_version": RULESET_VERSION,
        "mode": "evaluated" if apply else "preview",
        "events_evaluated": len(events),
        "proposals": proposals,
        "tasks_created": tasks_created,
        "tasks_reused": tasks_reused,
        "generated_at": now_msk_naive(),
    }


__all__ = ["RULESET_VERSION", "evaluate_coach_workflow"]
