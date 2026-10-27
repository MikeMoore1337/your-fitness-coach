from __future__ import annotations

import hashlib
import json
from datetime import date
from urllib.parse import urlencode

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from fitminiapp_api.core.timezone import (
    get_user_timezone_name,
    now_for_user_naive,
    user_local_naive_to_utc_naive,
)
from fitminiapp_api.models.notification import Notification
from fitminiapp_api.models.report_handoff import ReportHandoff
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.schemas.progress import NutritionReportPeriod
from fitminiapp_api.schemas.report_handoff import (
    ReportHandoffCreateRequest,
    ReportHandoffProgressReport,
    ReportHandoffResponse,
    ReportHandoffViewResponse,
)
from fitminiapp_api.services.period_bounds import PeriodBoundsError, resolve_report_bounds
from fitminiapp_api.services.progress_reports import build_progress_report

REPORT_HANDOFF_CONTRACT_VERSION = "progress-report-v1"
NOTIFICATION_RETURN_TO = "/app?section=profile#profile-notifications"
HANDOFF_SECTION_IDS = (
    "overview",
    "training",
    "cardio",
    "body",
    "nutrition",
    "adherence",
    "data_sufficiency",
    "check_ins",
    "methodology",
)


class ReportHandoffError(ValueError):
    def __init__(self, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _trainer_summary(trainer: User) -> dict[str, object]:
    profile_name = trainer.profile.full_name if trainer.profile else None
    name_parts = [trainer.first_name, trainer.last_name]
    full_name = profile_name or " ".join(part for part in name_parts if part) or trainer.username
    return {
        "id": trainer.id,
        "full_name": full_name,
        "username": trainer.username,
    }


def _active_relationship_for_sender(
    db: Session,
    sender: User,
    *,
    lock: bool,
) -> tuple[CoachClient, User] | None:
    query = (
        db.query(CoachClient, User)
        .join(User, User.id == CoachClient.coach_user_id)
        .options(joinedload(User.profile))
        .filter(
            CoachClient.client_user_id == sender.id,
            CoachClient.status == "active",
            User.is_active.is_(True),
            User.is_coach.is_(True),
        )
        .order_by(CoachClient.id.desc())
    )
    if lock:
        query = query.with_for_update(of=CoachClient)
    return query.first()


def _active_handoff_context(
    db: Session,
    handoff: ReportHandoff,
    *,
    lock: bool = False,
) -> tuple[User, CoachClient, User] | None:
    sender = (
        db.query(User)
        .options(joinedload(User.profile))
        .filter(User.id == handoff.sender_user_id, User.is_active.is_(True))
        .first()
    )
    if sender is None:
        return None

    query = (
        db.query(CoachClient, User)
        .join(User, User.id == CoachClient.coach_user_id)
        .options(joinedload(User.profile))
        .filter(
            CoachClient.id == handoff.relationship_id,
            CoachClient.coach_user_id == handoff.trainer_user_id,
            CoachClient.client_user_id == handoff.sender_user_id,
            CoachClient.status == "active",
            User.is_active.is_(True),
            User.is_coach.is_(True),
        )
    )
    if lock:
        query = query.with_for_update(of=CoachClient)
    relation_and_trainer = query.first()
    if relation_and_trainer is None:
        return None
    relation, trainer = relation_and_trainer
    return sender, relation, trainer


def _sanitize_report(payload: dict, *, period: NutritionReportPeriod) -> dict:
    sanitized = dict(payload)
    sanitized["period"] = period
    nutrition = payload.get("nutrition")
    if isinstance(nutrition, dict):
        sanitized["nutrition"] = {**nutrition, "period": period}
    sanitized["check_ins"] = [
        {key: value for key, value in check_in.items() if key != "note"}
        for check_in in payload.get("check_ins", [])
    ]
    return ReportHandoffProgressReport.model_validate(sanitized).model_dump(mode="json")


def _build_handoff_report(
    db: Session,
    sender: User,
    *,
    period: NutritionReportPeriod,
    period_start: date,
    period_end: date,
) -> dict:
    payload = build_progress_report(
        db,
        sender,
        NutritionReportPeriod.CUSTOM,
        date_from=period_start,
        date_to=period_end,
        subject_role="client",
    )
    return _sanitize_report(payload, period=period)


def _report_revision(report: dict, client_comment: str | None = None) -> str:
    revision_payload = {key: value for key, value in report.items() if key != "generated_at"}
    if client_comment is not None:
        revision_payload["client_comment"] = client_comment
    return _hash_payload(revision_payload)


def _request_fingerprint(
    *,
    sender_id: int,
    trainer_id: int,
    relationship_id: int,
    period: NutritionReportPeriod,
    period_start: date,
    period_end: date,
    timezone: str,
    client_comment: str | None,
) -> str:
    fingerprint_payload = {
        "sender_user_id": sender_id,
        "trainer_user_id": trainer_id,
        "relationship_id": relationship_id,
        "period": period.value,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "timezone": timezone,
        "report_contract_version": REPORT_HANDOFF_CONTRACT_VERSION,
    }
    if client_comment is not None:
        fingerprint_payload["client_comment"] = client_comment
    return _hash_payload(fingerprint_payload)


def _section_ids(report: dict) -> list[str]:
    sections = list(HANDOFF_SECTION_IDS)
    if report.get("program") is not None:
        sections.insert(2, "program")
    if report.get("wellbeing") is not None:
        sections.insert(sections.index("check_ins"), "wellbeing")
    return sections


def _notification_delivery_status(db: Session, handoff: ReportHandoff) -> str:
    if handoff.notification_id is None:
        return handoff.delivery_status
    notification = db.get(Notification, handoff.notification_id)
    if notification is None:
        return handoff.delivery_status
    if notification.status in {"sent", "succeeded"}:
        return "delivered"
    if notification.status in {"queued", "processing"}:
        return "pending"
    return "failed"


def _handoff_response(
    db: Session,
    handoff: ReportHandoff,
    trainer: User,
) -> ReportHandoffResponse:
    return ReportHandoffResponse.model_validate(
        {
            "id": handoff.id,
            "trainer": _trainer_summary(trainer),
            "period": handoff.period,
            "period_start": handoff.period_start,
            "period_end": handoff.period_end,
            "timezone": handoff.timezone,
            "report_contract_version": handoff.report_contract_version,
            "included_section_ids": list(handoff.included_section_ids),
            "created_at": handoff.created_at,
            "delivery_status": _notification_delivery_status(db, handoff),
            "delivery_attempt": handoff.delivery_attempt,
            "client_comment": handoff.client_comment,
            "live": True,
        }
    )


def _notification_action_url(handoff_id: int) -> str:
    query = urlencode(
        {
            "section": "progress",
            "report_handoff_id": handoff_id,
            "return_to": NOTIFICATION_RETURN_TO,
        }
    )
    return f"/app?{query}"


def _new_in_app_notification(
    trainer: User,
    handoff_id: int,
    attempt: int,
) -> Notification:
    scheduled_for = now_for_user_naive(trainer)
    return Notification(
        user_id=trainer.id,
        channel="in_app",
        category="report_handoff",
        event_kind="transactional",
        title="Новый отчёт от клиента",
        body="Клиент отправил вам отчёт за выбранный период. Откройте приложение, чтобы посмотреть фактические данные.",
        scheduled_for=scheduled_for,
        scheduled_for_utc=user_local_naive_to_utc_naive(scheduled_for, trainer),
        status="sent",
        sent_at=scheduled_for,
        attempt_count=1,
        dedupe_key=f"report_handoff:{handoff_id}:{attempt}",
        action_url=_notification_action_url(handoff_id),
    )


def _find_existing_handoff(
    db: Session,
    *,
    sender_id: int,
    idempotency_key: str,
    trainer_id: int,
    relationship_id: int,
    period_start: date,
    period_end: date,
    report_revision: str,
) -> ReportHandoff | None:
    by_key = (
        db.query(ReportHandoff)
        .filter(
            ReportHandoff.sender_user_id == sender_id,
            ReportHandoff.idempotency_key == idempotency_key,
        )
        .first()
    )
    if by_key is not None:
        return by_key
    return (
        db.query(ReportHandoff)
        .filter(
            ReportHandoff.sender_user_id == sender_id,
            ReportHandoff.trainer_user_id == trainer_id,
            ReportHandoff.relationship_id == relationship_id,
            ReportHandoff.period_start == period_start,
            ReportHandoff.period_end == period_end,
            ReportHandoff.report_contract_version == REPORT_HANDOFF_CONTRACT_VERSION,
            ReportHandoff.report_revision == report_revision,
        )
        .first()
    )


def create_report_handoff(
    db: Session,
    sender: User,
    payload: ReportHandoffCreateRequest,
    idempotency_key: str,
) -> ReportHandoffResponse:
    normalized_key = idempotency_key.strip()
    if len(normalized_key) < 8:
        raise ReportHandoffError(
            "Idempotency-Key должен содержать не менее 8 символов", status_code=422
        )

    relation_and_trainer = _active_relationship_for_sender(db, sender, lock=True)
    if relation_and_trainer is None:
        raise ReportHandoffError("Нет доступного текущего тренера")
    relation, trainer = relation_and_trainer
    try:
        bounds = resolve_report_bounds(
            sender,
            payload.period,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
    except PeriodBoundsError as exc:
        raise ReportHandoffError(str(exc), status_code=422) from exc

    timezone = get_user_timezone_name(sender)
    fingerprint = _request_fingerprint(
        sender_id=sender.id,
        trainer_id=trainer.id,
        relationship_id=relation.id,
        period=payload.period,
        period_start=bounds.start,
        period_end=bounds.end,
        timezone=timezone,
        client_comment=payload.client_comment,
    )
    existing_by_key = (
        db.query(ReportHandoff)
        .filter(
            ReportHandoff.sender_user_id == sender.id,
            ReportHandoff.idempotency_key == normalized_key,
        )
        .first()
    )
    if existing_by_key is not None:
        if existing_by_key.request_fingerprint != fingerprint:
            raise ReportHandoffError("Этот ключ уже использован для другого периода или тренера")
        return _handoff_response(db, existing_by_key, trainer)

    report = _build_handoff_report(
        db,
        sender,
        period=payload.period,
        period_start=bounds.start,
        period_end=bounds.end,
    )
    revision = _report_revision(report, payload.client_comment)
    existing = _find_existing_handoff(
        db,
        sender_id=sender.id,
        idempotency_key=normalized_key,
        trainer_id=trainer.id,
        relationship_id=relation.id,
        period_start=bounds.start,
        period_end=bounds.end,
        report_revision=revision,
    )
    if existing is not None:
        return _handoff_response(db, existing, trainer)

    handoff = ReportHandoff(
        sender_user_id=sender.id,
        trainer_user_id=trainer.id,
        relationship_id=relation.id,
        period=payload.period.value,
        period_start=bounds.start,
        period_end=bounds.end,
        timezone=timezone,
        report_contract_version=REPORT_HANDOFF_CONTRACT_VERSION,
        included_section_ids=_section_ids(report),
        report_revision=revision,
        client_comment=payload.client_comment,
        idempotency_key=normalized_key,
        request_fingerprint=fingerprint,
        delivery_status="pending",
        delivery_attempt=1,
    )
    db.add(handoff)
    try:
        db.flush()
        notification = _new_in_app_notification(trainer, handoff.id, handoff.delivery_attempt)
        db.add(notification)
        db.flush()
        handoff.notification_id = notification.id
        handoff.delivery_status = "delivered"
        db.commit()
        db.refresh(handoff)
    except IntegrityError:
        db.rollback()
        existing = _find_existing_handoff(
            db,
            sender_id=sender.id,
            idempotency_key=normalized_key,
            trainer_id=trainer.id,
            relationship_id=relation.id,
            period_start=bounds.start,
            period_end=bounds.end,
            report_revision=revision,
        )
        if existing is None:
            raise ReportHandoffError("Не удалось зарегистрировать отправку отчёта") from None
        if existing.request_fingerprint != fingerprint:
            raise ReportHandoffError("Этот ключ уже использован для другого периода или тренера")
        return _handoff_response(db, existing, trainer)
    return _handoff_response(db, handoff, trainer)


def list_report_handoffs(
    db: Session,
    sender: User,
    *,
    limit: int = 50,
) -> list[ReportHandoffResponse]:
    rows = (
        db.query(ReportHandoff, User)
        .join(User, User.id == ReportHandoff.trainer_user_id)
        .options(joinedload(User.profile))
        .filter(ReportHandoff.sender_user_id == sender.id)
        .order_by(ReportHandoff.created_at.desc(), ReportHandoff.id.desc())
        .limit(limit)
        .all()
    )
    return [_handoff_response(db, handoff, trainer) for handoff, trainer in rows]


def list_trainer_report_handoffs(
    db: Session,
    trainer: User,
    client_id: int,
    *,
    limit: int = 5,
) -> list[ReportHandoffResponse]:
    """Return only the metadata a coach needs for a managed client's latest handoffs.

    The report payload is intentionally not duplicated here. The existing handoff view and
    progress-report routes remain the authoritative report surfaces; this projection only makes
    the already-authorized client comment discoverable inside the coach workspace.
    """
    relation = (
        db.query(CoachClient)
        .filter(
            CoachClient.coach_user_id == trainer.id,
            CoachClient.client_user_id == client_id,
            CoachClient.status == "active",
        )
        .first()
    )
    if relation is None:
        raise ReportHandoffError("Отчёт недоступен", status_code=404)
    handoffs = (
        db.query(ReportHandoff)
        .filter(
            ReportHandoff.trainer_user_id == trainer.id,
            ReportHandoff.sender_user_id == client_id,
            ReportHandoff.relationship_id == relation.id,
        )
        .order_by(ReportHandoff.created_at.desc(), ReportHandoff.id.desc())
        .limit(limit)
        .all()
    )
    return [_handoff_response(db, handoff, trainer) for handoff in handoffs]


def get_report_handoff_view(
    db: Session,
    actor: User,
    handoff_id: int,
) -> ReportHandoffViewResponse:
    handoff = db.get(ReportHandoff, handoff_id)
    if handoff is None or actor.id not in {handoff.sender_user_id, handoff.trainer_user_id}:
        raise ReportHandoffError("Отчёт недоступен", status_code=404)
    context = _active_handoff_context(db, handoff)
    if context is None:
        raise ReportHandoffError("Отчёт недоступен", status_code=404)
    sender, _relation, trainer = context
    report = _build_handoff_report(
        db,
        sender,
        period=NutritionReportPeriod(handoff.period),
        period_start=handoff.period_start,
        period_end=handoff.period_end,
    )
    return ReportHandoffViewResponse(
        handoff=_handoff_response(db, handoff, trainer),
        report=report,
        data_changed_since_send=_report_revision(report, handoff.client_comment)
        != handoff.report_revision,
    )


def retry_report_handoff(
    db: Session,
    actor: User,
    handoff_id: int,
    retry_idempotency_key: str,
) -> ReportHandoffResponse:
    normalized_key = retry_idempotency_key.strip()
    if len(normalized_key) < 8:
        raise ReportHandoffError(
            "Idempotency-Key должен содержать не менее 8 символов", status_code=422
        )
    handoff = (
        db.query(ReportHandoff).filter(ReportHandoff.id == handoff_id).with_for_update().first()
    )
    if handoff is None or handoff.sender_user_id != actor.id:
        raise ReportHandoffError("Отчёт недоступен", status_code=404)
    context = _active_handoff_context(db, handoff, lock=True)
    if context is None:
        raise ReportHandoffError("Отчёт недоступен", status_code=404)
    _sender, _relation, trainer = context
    if handoff.last_retry_idempotency_key == normalized_key:
        return _handoff_response(db, handoff, trainer)

    current_notification = (
        db.get(Notification, handoff.notification_id)
        if handoff.notification_id is not None
        else None
    )
    if current_notification is None and handoff.delivery_status != "failed":
        return _handoff_response(db, handoff, trainer)
    if current_notification is not None and current_notification.status not in {
        "failed",
        "cancelled",
    }:
        return _handoff_response(db, handoff, trainer)

    next_attempt = handoff.delivery_attempt + 1
    notification = _new_in_app_notification(trainer, handoff.id, next_attempt)
    db.add(notification)
    try:
        db.flush()
        handoff.notification_id = notification.id
        handoff.delivery_status = "delivered"
        handoff.delivery_attempt = next_attempt
        handoff.last_retry_idempotency_key = normalized_key
        db.commit()
        db.refresh(handoff)
    except IntegrityError:
        db.rollback()
        existing = db.get(ReportHandoff, handoff_id)
        if existing is None:
            raise ReportHandoffError("Не удалось повторить отправку отчёта") from None
        return _handoff_response(db, existing, trainer)
    return _handoff_response(db, handoff, trainer)
