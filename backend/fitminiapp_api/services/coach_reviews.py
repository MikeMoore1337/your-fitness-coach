from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast
from zoneinfo import ZoneInfo

from sqlalchemy import and_
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import (
    local_naive_to_utc_naive_strict,
    now_msk_naive,
)
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.coach_crm import CoachTask
from fitminiapp_api.models.coach_reviews import CoachCheckInReview
from fitminiapp_api.models.user import CoachClient, User, UserProfile
from fitminiapp_api.schemas.coach_crm import (
    CoachTaskKind,
    CoachTaskResponse,
    CoachTaskSourceKind,
)
from fitminiapp_api.schemas.coach_reviews import (
    CoachCheckInReviewItem,
    CoachCheckInReviewRequest,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.coach_clients import get_client_managed_by_coach
from fitminiapp_api.services.program_common import ProgramError


class CoachReviewError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _client_name(
    user: User,
    private_name: str | None,
    profile: UserProfile | None = None,
) -> str:
    if private_name and private_name.strip():
        return private_name.strip()
    profile = profile or user.profile
    if profile and profile.full_name and profile.full_name.strip():
        return profile.full_name.strip()
    return user.username or f"Клиент #{user.id}"


def _local_response(value: datetime, timezone_name: str) -> datetime:
    return value.replace(tzinfo=UTC).astimezone(ZoneInfo(timezone_name))


def _task_response(task: CoachTask, client_name: str) -> CoachTaskResponse:
    return CoachTaskResponse(
        id=task.id,
        client_id=task.client_user_id,
        client_name=client_name,
        title=task.title,
        due_at=_local_response(task.due_at_utc, task.timezone),
        due_at_utc=task.due_at_utc.replace(tzinfo=UTC),
        timezone=task.timezone,
        kind=cast(CoachTaskKind, task.kind),
        source_kind=cast(CoachTaskSourceKind | None, task.source_kind),
        source_id=task.source_id,
        reason=task.reason,
        state=cast(Literal["open", "completed"], task.state),
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _item(
    check_in: WeeklyCheckIn,
    client: User,
    private_name: str | None,
    profile: UserProfile | None,
    review: CoachCheckInReview | None,
    follow_up: CoachTask | None,
) -> CoachCheckInReviewItem:
    client_name = _client_name(client, private_name, profile)
    return CoachCheckInReviewItem(
        id=check_in.id,
        client_id=client.id,
        client_name=client_name,
        check_in_id=check_in.id,
        week_start=check_in.week_start,
        week_end=check_in.week_end,
        submitted_on=check_in.submitted_on,
        status=cast(Literal["completed", "skipped"], check_in.status),
        training_load=check_in.training_load,
        recovery=check_in.recovery,
        hunger=check_in.hunger,
        adherence_difficulty=check_in.adherence_difficulty,
        note=check_in.note,
        summary=check_in.summary,
        review_status="reviewed" if review is not None else "pending",
        review_response=review.response if review else None,
        reviewed_at=review.reviewed_at if review else None,
        follow_up=_task_response(follow_up, client_name) if follow_up else None,
        created_at=check_in.created_at,
    )


def list_coach_check_in_reviews(
    db: Session,
    coach: User,
    *,
    status: str | None,
    limit: int,
    offset: int,
) -> dict[str, object]:
    review_join = and_(
        CoachCheckInReview.check_in_id == WeeklyCheckIn.id,
        CoachCheckInReview.coach_user_id == coach.id,
    )
    query = (
        db.query(WeeklyCheckIn, User, UserProfile, CoachClient.private_name, CoachCheckInReview)
        .join(User, User.id == WeeklyCheckIn.user_id)
        .join(
            CoachClient,
            and_(
                CoachClient.client_user_id == WeeklyCheckIn.user_id,
                CoachClient.coach_user_id == coach.id,
                CoachClient.status == "active",
            ),
        )
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .outerjoin(CoachCheckInReview, review_join)
        .filter(WeeklyCheckIn.status == "completed", User.is_active.is_(True))
    )
    if status == "pending":
        query = query.filter(CoachCheckInReview.id.is_(None))
    elif status == "reviewed":
        query = query.filter(CoachCheckInReview.id.is_not(None))

    total = query.count()
    rows = (
        query.order_by(WeeklyCheckIn.created_at.desc(), WeeklyCheckIn.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    task_ids = {
        review.follow_up_task_id
        for *_prefix, review in rows
        if review is not None and review.follow_up_task_id is not None
    }
    tasks = (
        {task.id: task for task in db.query(CoachTask).filter(CoachTask.id.in_(task_ids)).all()}
        if task_ids
        else {}
    )
    return {
        "items": [
            _item(
                check_in,
                client,
                private_name,
                _profile,
                review,
                tasks.get(review.follow_up_task_id) if review else None,
            ).model_dump(mode="json")
            for check_in, client, _profile, private_name, review in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def review_coach_check_in(
    db: Session,
    coach: User,
    check_in_id: int,
    payload: CoachCheckInReviewRequest,
) -> CoachCheckInReviewItem:
    check_in = (
        db.query(WeeklyCheckIn)
        .filter(WeeklyCheckIn.id == check_in_id, WeeklyCheckIn.status == "completed")
        .with_for_update()
        .first()
    )
    if check_in is None:
        raise CoachReviewError("Недельный итог не найден", 404)
    try:
        client = get_client_managed_by_coach(db, coach, check_in.user_id)
    except ProgramError as exc:
        raise CoachReviewError("Недельный итог не найден", 404) from exc

    private_name = (
        db.query(CoachClient.private_name)
        .filter(
            CoachClient.coach_user_id == coach.id,
            CoachClient.client_user_id == client.id,
            CoachClient.status == "active",
        )
        .scalar()
    )
    review = (
        db.query(CoachCheckInReview)
        .filter(
            CoachCheckInReview.coach_user_id == coach.id,
            CoachCheckInReview.check_in_id == check_in.id,
        )
        .with_for_update()
        .first()
    )
    now = now_msk_naive()
    if review is None:
        review = CoachCheckInReview(
            coach_user_id=coach.id,
            client_user_id=client.id,
            check_in_id=check_in.id,
            status="reviewed",
            response=payload.response.strip() if payload.response else None,
            reviewed_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(review)
        db.flush()
    else:
        review.status = "reviewed"
        review.response = payload.response.strip() if payload.response else None
        review.reviewed_at = now
        review.updated_at = now

    follow_up = None
    if payload.follow_up_title and review.follow_up_task_id is None:
        if payload.follow_up_due_at is None or payload.follow_up_timezone is None:
            raise CoachReviewError("Для follow-up укажите название, срок и timezone", 422)
        try:
            follow_up_due_at = local_naive_to_utc_naive_strict(
                payload.follow_up_due_at.replace(tzinfo=None),
                payload.follow_up_timezone,
                fold=payload.fold,
            )
        except (AttributeError, ValueError) as exc:
            raise CoachReviewError(
                "Срок follow-up не существует в выбранной timezone", 422
            ) from exc
        follow_up = CoachTask(
            coach_user_id=coach.id,
            client_user_id=client.id,
            idempotency_key=f"coach-review-{coach.id}-{check_in.id}",
            title=payload.follow_up_title.strip(),
            due_at_utc=follow_up_due_at,
            timezone=payload.follow_up_timezone,
            kind="schedule_follow_up",
            source_kind="weekly_check_in",
            source_id=check_in.id,
            reason="Follow-up создан после проверки недельного итога.",
        )
        db.add(follow_up)
        db.flush()
        review.follow_up_task_id = follow_up.id

    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=client.id,
        action="coach.weekly_check_in_reviewed",
        resource_type="weekly_check_in",
        resource_id=check_in.id,
        details={"follow_up_created": follow_up is not None},
    )
    db.commit()
    db.refresh(review)
    return _item(check_in, client, private_name, client.profile, review, follow_up)


__all__ = [
    "CoachReviewError",
    "list_coach_check_in_reviews",
    "review_coach_check_in",
]
