from __future__ import annotations

import hashlib
import json
import secrets

from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.program import (
    ProgramTemplateExerciseWeekPrescription,
)
from fitminiapp_api.models.public_share import PublicShare, PublicShareImport
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.program import ProgramTemplateCreate
from fitminiapp_api.schemas.progress import NutritionReportPeriod
from fitminiapp_api.schemas.public_share import (
    PublicShareOwnerResponse,
    PublicSharePreviewResponse,
    PublicShareProgramSnapshot,
    PublicShareProgressSnapshot,
    PublicShareResponse,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.nutrition_reports import NutritionReportError
from fitminiapp_api.services.program_common import ProgramError, assignment_error_status
from fitminiapp_api.services.programs import (
    assign_template_to_user,
    create_template,
    get_template_for_user,
)
from fitminiapp_api.services.progress_reports import build_progress_report
from fitminiapp_api.services.workout_metrics import exercise_metric_type

PUBLIC_SHARE_ID_LENGTH = 43
PUBLIC_SHARE_PATH_PREFIX = "/share/"


class PublicShareError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _canonical_hash(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _public_url(share_id: str) -> str:
    return f"{settings.frontend_base_url.rstrip('/')}{PUBLIC_SHARE_PATH_PREFIX}{share_id}"


def _new_share_id(db: Session) -> str:
    for _ in range(5):
        candidate = secrets.token_urlsafe(32)
        if len(candidate) != PUBLIC_SHARE_ID_LENGTH:
            continue
        if not db.query(PublicShare.id).filter(PublicShare.share_id == candidate).first():
            return candidate
    raise PublicShareError("Не удалось создать безопасную ссылку", 503)


def _progress_snapshot(report: dict) -> dict:
    training = report["training"]
    sufficiency = report["data_sufficiency"]
    workout_logging = sufficiency["workout_logging"]["status"]
    working_sets = sufficiency["working_sets"]["status"]
    notes = ["Показываются только фактически записанные данные о тренировках."]
    if workout_logging != "sufficient":
        notes.append("Заполнение тренировок за период неполное.")
    if working_sets != "sufficient":
        notes.append("Объём и лучшие нагрузки могут быть неполными.")
    return PublicShareProgressSnapshot.model_validate(
        {
            "period_start": report["period_start"],
            "period_end": report["period_end"],
            "planned_workouts": training["planned_workouts"],
            "completed_workouts": training["completed_workouts"],
            "frequency_per_week": training["frequency_per_week"],
            "completed_working_sets": training["completed_working_sets"],
            "new_personal_records": training["new_personal_records"],
            "external_load_volume_kg": training["external_load_volume_kg"],
            "volume_recorded_sets": training["volume_recorded_sets"],
            "exercises": [
                {
                    "exercise_title": exercise["exercise_title"],
                    "performed_session_count": exercise["performed_session_count"],
                    "completed_set_count": exercise["completed_set_count"],
                    "max_external_load_kg": exercise["max_external_load_kg"],
                    "external_load_volume_kg": exercise["external_load_volume_kg"],
                }
                for exercise in training["exercises"][:3]
            ],
            "data_quality": {
                "workout_logging": workout_logging,
                "working_sets": working_sets,
                "notes": notes[:4],
            },
        }
    ).model_dump(mode="json")


def build_progress_share_preview(
    db: Session,
    current_user: User,
    *,
    period: NutritionReportPeriod,
    date_from,
    date_to,
) -> PublicSharePreviewResponse:
    try:
        report = build_progress_report(
            db,
            current_user,
            period,
            date_from=date_from,
            date_to=date_to,
        )
    except NutritionReportError as exc:
        raise PublicShareError(str(exc), 422) from exc
    snapshot = _progress_snapshot(report)
    return PublicSharePreviewResponse(
        share_type="progress",
        preview_hash=_canonical_hash(snapshot),
        snapshot=snapshot,
    )


def _program_snapshot_and_payload(
    db: Session,
    current_user: User,
    template_id: int,
) -> tuple[dict, dict]:
    try:
        template = get_template_for_user(db, current_user, template_id)
    except ProgramError as exc:
        raise PublicShareError("Программа недоступна для публикации", 404) from exc
    if template.owner_user_id != current_user.id:
        raise PublicShareError("Программа недоступна для публикации", 404)

    days: list[dict] = []
    private_days: list[dict] = []
    for day in sorted(template.days, key=lambda item: item.day_number):
        public_exercises: list[dict] = []
        private_exercises: list[dict] = []
        for exercise in sorted(day.exercises, key=lambda item: item.sort_order):
            if exercise.exercise is None:
                raise PublicShareError("В программе есть недоступное упражнение", 422)
            weekly_rows = sorted(
                exercise.weekly_prescriptions,
                key=lambda item: item.week_number,
            )
            weekly = [
                {
                    "week_number": item.week_number,
                    "prescribed_sets": item.prescribed_sets,
                    "prescribed_reps": item.prescribed_reps,
                    "prescribed_duration_minutes": item.prescribed_duration_minutes,
                    "rest_seconds": item.rest_seconds,
                }
                for item in weekly_rows
            ]
            public_exercises.append(
                {
                    "exercise_title": exercise.exercise.title,
                    "metric_type": exercise_metric_type(exercise.exercise),
                    "prescribed_sets": exercise.prescribed_sets,
                    "prescribed_reps": exercise.prescribed_reps,
                    "prescribed_duration_minutes": exercise.prescribed_duration_minutes,
                    "rest_seconds": exercise.rest_seconds,
                    "weekly_prescriptions": weekly,
                }
            )
            private_exercises.append(
                {
                    "exercise_id": exercise.exercise_id,
                    "prescribed_sets": exercise.prescribed_sets,
                    "prescribed_reps": exercise.prescribed_reps,
                    "prescribed_duration_minutes": exercise.prescribed_duration_minutes,
                    "rest_seconds": exercise.rest_seconds,
                    "notes": None,
                    "superset_group": exercise.superset_group,
                    "superset_order": exercise.superset_order,
                    "group_id": exercise.group_id,
                    "group_kind": exercise.group_kind,
                    "group_order": exercise.group_order,
                    "prescription": exercise.prescription,
                    "weekly_prescriptions": [
                        {
                            **item,
                            "exercise_id": weekly_row.exercise_id,
                            "prescription": weekly_row.prescription,
                        }
                        for item, weekly_row in zip(weekly, weekly_rows, strict=True)
                    ],
                }
            )
        days.append(
            {
                "day_number": day.day_number,
                "title": day.title,
                "exercises": public_exercises,
            }
        )
        private_days.append({"title": day.title, "exercises": private_exercises})

    public_snapshot = PublicShareProgramSnapshot.model_validate(
        {
            "title": template.title,
            "goal": template.goal,
            "level": template.level,
            "duration_weeks": template.effective_duration_weeks,
            "days": days,
        }
    ).model_dump(mode="json")
    create_payload = {
        "title": template.title,
        "goal": template.goal,
        "level": template.level,
        "mode": "self",
        "assign_after_create": False,
        "duration_weeks": template.effective_duration_weeks,
        "days": [
            {
                "title": day["title"],
                "exercises": [
                    {key: value for key, value in exercise.items() if key != "weekly_prescriptions"}
                    for exercise in day["exercises"]
                ],
            }
            for day in private_days
        ],
    }
    private_payload = {
        "source_template_id": template.id,
        "create_payload": create_payload,
        "weekly_prescriptions": [
            [exercise["weekly_prescriptions"] for exercise in day["exercises"]]
            for day in private_days
        ],
    }
    return public_snapshot, private_payload


def build_program_share_preview(
    db: Session,
    current_user: User,
    *,
    template_id: int,
) -> PublicSharePreviewResponse:
    snapshot, private_payload = _program_snapshot_and_payload(db, current_user, template_id)
    return PublicSharePreviewResponse(
        share_type="program",
        preview_hash=_canonical_hash({"snapshot": snapshot, "import": private_payload}),
        snapshot=snapshot,
    )


def _build_program_preview_parts(
    db: Session,
    current_user: User,
    template_id: int,
) -> tuple[dict, dict, str]:
    snapshot, private_payload = _program_snapshot_and_payload(db, current_user, template_id)
    return (
        snapshot,
        private_payload,
        _canonical_hash({"snapshot": snapshot, "import": private_payload}),
    )


def create_progress_share(
    db: Session,
    current_user: User,
    *,
    period: NutritionReportPeriod,
    date_from,
    date_to,
    preview_hash: str,
) -> PublicShare:
    preview = build_progress_share_preview(
        db,
        current_user,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )
    if preview.preview_hash != preview_hash:
        raise PublicShareError("Данные изменились. Сначала обновите предпросмотр", 409)
    row = PublicShare(
        share_id=_new_share_id(db),
        owner_user_id=current_user.id,
        share_type="progress",
        status="active",
        snapshot_hash=preview.preview_hash,
        public_snapshot=preview.snapshot.model_dump(mode="json"),
        private_payload={
            "period": period.value,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    )
    db.add(row)
    db.flush()
    record_audit_event(
        db,
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        action="public_share.created",
        resource_type="public_share",
        resource_id=row.id,
        details={"share_type": row.share_type},
    )
    return row


def create_program_share(
    db: Session,
    current_user: User,
    *,
    template_id: int,
    preview_hash: str,
) -> PublicShare:
    snapshot, private_payload, current_hash = _build_program_preview_parts(
        db, current_user, template_id
    )
    if current_hash != preview_hash:
        raise PublicShareError("Программа изменилась. Сначала обновите предпросмотр", 409)
    row = PublicShare(
        share_id=_new_share_id(db),
        owner_user_id=current_user.id,
        share_type="program",
        status="active",
        snapshot_hash=current_hash,
        public_snapshot=snapshot,
        private_payload=private_payload,
    )
    db.add(row)
    db.flush()
    record_audit_event(
        db,
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        action="public_share.created",
        resource_type="public_share",
        resource_id=row.id,
        details={"share_type": row.share_type},
    )
    return row


def get_active_public_share(db: Session, share_id: str) -> PublicShare | None:
    if not share_id or len(share_id) != PUBLIC_SHARE_ID_LENGTH:
        return None
    if any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
        for character in share_id
    ):
        return None
    return (
        db.query(PublicShare)
        .filter(PublicShare.share_id == share_id, PublicShare.status == "active")
        .one_or_none()
    )


def get_owner_public_share(db: Session, current_user: User, share_id: str) -> PublicShare:
    row = (
        db.query(PublicShare)
        .filter(PublicShare.share_id == share_id, PublicShare.owner_user_id == current_user.id)
        .one_or_none()
    )
    if row is None:
        raise PublicShareError("Ссылка недоступна", 404)
    return row


def serialize_public_share(row: PublicShare) -> dict:
    snapshot_model = (
        PublicShareProgressSnapshot if row.share_type == "progress" else PublicShareProgramSnapshot
    )
    return PublicShareResponse(
        share_id=row.share_id,
        share_type=row.share_type,
        status=row.status,
        created_at=row.created_at,
        public_url=_public_url(row.share_id),
        preview_hash=row.snapshot_hash,
        snapshot=snapshot_model.model_validate(row.public_snapshot),
    ).model_dump(mode="json")


def serialize_public_preview(row: PublicShare) -> dict:
    return serialize_public_share(row)


def list_owner_public_shares(db: Session, current_user: User) -> list[dict]:
    rows = (
        db.query(PublicShare)
        .filter(PublicShare.owner_user_id == current_user.id)
        .order_by(PublicShare.created_at.desc(), PublicShare.id.desc())
        .all()
    )
    return [
        PublicShareOwnerResponse(
            share_id=row.share_id,
            share_type=row.share_type,
            status=row.status,
            created_at=row.created_at,
            revoked_at=row.revoked_at,
            public_url=_public_url(row.share_id),
        ).model_dump(mode="json")
        for row in rows
    ]


def revoke_public_share(db: Session, current_user: User, share_id: str) -> None:
    row = get_owner_public_share(db, current_user, share_id)
    if row.status == "revoked":
        raise PublicShareError("Ссылка недоступна", 404)
    row.status = "revoked"
    row.revoked_at = now_msk_naive()
    record_audit_event(
        db,
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        action="public_share.revoked",
        resource_type="public_share",
        resource_id=row.id,
        details={"share_type": row.share_type},
    )


def import_program_share(
    db: Session,
    current_user: User,
    *,
    share_id: str,
    preview_hash: str,
    replace_active: bool = False,
) -> tuple[str, int, int, int]:
    row = get_active_public_share(db, share_id)
    if row is None or row.share_type != "program":
        raise PublicShareError("Ссылка недоступна", 404)
    if row.snapshot_hash != preview_hash:
        raise PublicShareError("Обновите предпросмотр программы", 409)

    existing = (
        db.query(PublicShareImport)
        .filter(
            PublicShareImport.public_share_id == row.id,
            PublicShareImport.recipient_user_id == current_user.id,
        )
        .one_or_none()
    )
    if existing and existing.template_id and existing.user_program_id:
        return "already_imported", existing.template_id, existing.user_program_id, 0

    private_payload = row.private_payload
    create_payload = ProgramTemplateCreate.model_validate(private_payload["create_payload"])
    create_payload = create_payload.model_copy(
        update={"title": f"{create_payload.title[:120]} (копия)"}
    )
    try:
        template = create_template(db, current_user, create_payload, force_private=True)
        template.provenance_type = "CUSTOM"
        template.provenance = {"source": "public_share_snapshot"}
        db.flush()
        created_days = sorted(template.days, key=lambda item: item.day_number)
        for created_day, weekly_day in zip(
            created_days, private_payload["weekly_prescriptions"], strict=True
        ):
            created_exercises = sorted(created_day.exercises, key=lambda item: item.sort_order)
            for created_exercise, weekly_exercises in zip(
                created_exercises, weekly_day, strict=True
            ):
                for weekly in weekly_exercises:
                    db.add(
                        ProgramTemplateExerciseWeekPrescription(
                            template_exercise_id=created_exercise.id,
                            exercise_id=weekly["exercise_id"],
                            week_number=weekly["week_number"],
                            prescribed_sets=weekly["prescribed_sets"],
                            prescribed_reps=weekly["prescribed_reps"],
                            prescribed_duration_minutes=weekly["prescribed_duration_minutes"],
                            rest_seconds=weekly["rest_seconds"],
                            prescription=weekly["prescription"],
                        )
                    )
        db.flush()
        program, workouts_created = assign_template_to_user(
            db,
            template,
            current_user,
            current_user,
            duration_weeks=create_payload.duration_weeks,
            replace_active=replace_active,
        )
        if existing is None:
            existing = PublicShareImport(
                public_share_id=row.id,
                recipient_user_id=current_user.id,
            )
            db.add(existing)
        existing.template_id = template.id
        existing.user_program_id = program.id
        db.flush()
        record_audit_event(
            db,
            actor_user_id=current_user.id,
            target_user_id=current_user.id,
            action="public_share.program_imported",
            resource_type="public_share",
            resource_id=row.id,
            details={"template_id": template.id, "user_program_id": program.id},
        )
        db.commit()
        return "imported", template.id, program.id, workouts_created
    except ProgramError as exc:
        db.rollback()
        raise PublicShareError(str(exc), assignment_error_status(str(exc))) from exc


def public_share_seo(row: PublicShare) -> tuple[str, str]:
    snapshot = row.public_snapshot
    if row.share_type == "progress":
        title = "Прогресс тренировок — Your Fitness Coach"
        description = (
            f"Фактические данные тренировок за {snapshot['period_start']} — "
            f"{snapshot['period_end']}: {snapshot['completed_workouts']} завершённых тренировок."
        )
    else:
        title = f"{snapshot['title']} — программа тренировок"
        description = (
            f"Публичный снимок программы «{snapshot['title']}»: "
            f"{len(snapshot['days'])} тренировочных дней, версия на момент публикации."
        )
    return title[:160], description[:300]
