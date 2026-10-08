from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.check_in_templates import CoachCheckInTemplate
from fitminiapp_api.models.coach_workflow_templates import (
    CoachCommunicationDraft,
    CoachWorkflowAssignment,
    CoachWorkflowTemplate,
    CoachWorkflowTemplateVersion,
)
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.schemas.coach_workflow_templates import (
    CommunicationDraftCreate,
    CommunicationDraftUpdate,
    CommunicationTemplateCreate,
    CommunicationTemplateVersionCreate,
    OnboardingTemplateCreate,
    OnboardingTemplateVersionCreate,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.coach_clients import get_client_managed_by_coach
from fitminiapp_api.services.notifications import queue_notification
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.programs import get_template_for_user


class CoachWorkflowTemplateError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_key(idempotency_key: str | None) -> str:
    if not idempotency_key or not 8 <= len(idempotency_key) <= 128:
        raise CoachWorkflowTemplateError(
            "Требуется Idempotency-Key длиной от 8 до 128 символов",
            422,
        )
    return idempotency_key


def _display_name(user: User, profile: UserProfile | None = None) -> str:
    profile = profile or user.profile
    return (profile.full_name if profile else None) or user.username or f"Клиент {user.id}"


def _template_or_404(
    db: Session,
    coach: User,
    template_id: int,
    kind: str,
    *,
    lock: bool = False,
) -> CoachWorkflowTemplate:
    query = db.query(CoachWorkflowTemplate).filter(
        CoachWorkflowTemplate.id == template_id,
        CoachWorkflowTemplate.coach_user_id == coach.id,
        CoachWorkflowTemplate.kind == kind,
    )
    if lock:
        query = query.with_for_update()
    template = query.first()
    if not template:
        raise CoachWorkflowTemplateError("Шаблон рабочего процесса не найден", 404)
    return template


def _version_or_404(
    db: Session,
    template_id: int,
    version_number: int,
) -> CoachWorkflowTemplateVersion:
    version = (
        db.query(CoachWorkflowTemplateVersion)
        .filter(
            CoachWorkflowTemplateVersion.template_id == template_id,
            CoachWorkflowTemplateVersion.version == version_number,
        )
        .first()
    )
    if not version:
        raise CoachWorkflowTemplateError("Версия шаблона не найдена", 404)
    return version


def _latest_versions(
    db: Session,
    template_ids: list[int],
) -> dict[int, CoachWorkflowTemplateVersion]:
    if not template_ids:
        return {}
    rows = (
        db.query(CoachWorkflowTemplateVersion)
        .filter(CoachWorkflowTemplateVersion.template_id.in_(template_ids))
        .order_by(
            CoachWorkflowTemplateVersion.template_id,
            CoachWorkflowTemplateVersion.version.desc(),
        )
        .all()
    )
    latest: dict[int, CoachWorkflowTemplateVersion] = {}
    for row in rows:
        latest.setdefault(row.template_id, row)
    return latest


def _version_number(db: Session, template_id: int) -> int:
    return int(
        db.query(func.max(CoachWorkflowTemplateVersion.version))
        .filter(CoachWorkflowTemplateVersion.template_id == template_id)
        .scalar()
        or 0
    )


def _validate_onboarding_references(
    db: Session,
    coach: User,
    payload: OnboardingTemplateCreate | OnboardingTemplateVersionCreate,
) -> None:
    if payload.program_template_id is not None:
        try:
            get_template_for_user(db, coach, payload.program_template_id)
        except ProgramError as exc:
            raise CoachWorkflowTemplateError("Программа для шаблона не найдена", 404) from exc
    if payload.check_in_template_id is not None:
        exists = (
            db.query(CoachCheckInTemplate.id)
            .filter(
                CoachCheckInTemplate.id == payload.check_in_template_id,
                CoachCheckInTemplate.coach_user_id == coach.id,
            )
            .first()
        )
        if exists is None:
            raise CoachWorkflowTemplateError("Проверка для шаблона не найдена", 404)


def _onboarding_payload(
    payload: OnboardingTemplateCreate | OnboardingTemplateVersionCreate,
) -> dict:
    return {
        "steps": list(payload.steps),
        "program_template_id": payload.program_template_id,
        "check_in_template_id": payload.check_in_template_id,
    }


def _communication_payload(
    payload: CommunicationTemplateCreate | CommunicationTemplateVersionCreate,
) -> dict[str, str]:
    subject = payload.subject.strip()
    body = payload.body.strip()
    if not subject or not body:
        raise CoachWorkflowTemplateError("Тема и текст сообщения не могут быть пустыми", 422)
    return {"subject": subject, "body": body}


def _template_version_payload(version: CoachWorkflowTemplateVersion) -> dict[str, object]:
    payload = version.payload
    return {
        "id": version.id,
        "version": version.version,
        **payload,
        "created_at": version.created_at,
    }


def _assignment_payload(
    assignment: CoachWorkflowAssignment,
    client: User,
    version: CoachWorkflowTemplateVersion,
) -> dict[str, object]:
    return {
        "id": assignment.id,
        "client_id": assignment.client_user_id,
        "client_name": _display_name(client),
        "version": version.version,
        "status": assignment.status,
        "created_at": assignment.created_at,
    }


def _draft_payload(
    draft: CoachCommunicationDraft,
    client: User,
    version: CoachWorkflowTemplateVersion,
) -> dict[str, object]:
    return {
        "id": draft.id,
        "template_id": draft.template_id,
        "client_id": draft.client_user_id,
        "client_name": _display_name(client),
        "version": version.version,
        "subject": draft.subject,
        "body": draft.body,
        "status": draft.status,
        "notification_id": draft.notification_id,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
        "confirmed_at": draft.confirmed_at,
    }


def _template_payload(
    template: CoachWorkflowTemplate,
    current_version: CoachWorkflowTemplateVersion | None,
    assignments: list[dict[str, object]] | None = None,
    drafts: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "is_active": template.is_active,
        "current_version": (
            _template_version_payload(current_version) if current_version else None
        ),
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }
    if template.kind == "onboarding":
        result["assignments"] = assignments or []
    else:
        result["drafts"] = drafts or []
    return result


def _workflow_rows(
    db: Session,
    coach: User,
    kind: str,
) -> tuple[list[CoachWorkflowTemplate], dict[int, CoachWorkflowTemplateVersion]]:
    templates = (
        db.query(CoachWorkflowTemplate)
        .filter(
            CoachWorkflowTemplate.coach_user_id == coach.id,
            CoachWorkflowTemplate.kind == kind,
        )
        .order_by(CoachWorkflowTemplate.updated_at.desc(), CoachWorkflowTemplate.id.desc())
        .all()
    )
    return templates, _latest_versions(db, [template.id for template in templates])


def list_onboarding_templates(db: Session, coach: User) -> dict[str, object]:
    templates, latest = _workflow_rows(db, coach, "onboarding")
    template_ids = [template.id for template in templates]
    rows = (
        db.query(CoachWorkflowAssignment, User, UserProfile)
        .join(User, User.id == CoachWorkflowAssignment.client_user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .filter(
            CoachWorkflowAssignment.coach_user_id == coach.id,
            CoachWorkflowAssignment.template_id.in_(template_ids),
        )
        .order_by(CoachWorkflowAssignment.id.desc())
        .all()
        if template_ids
        else []
    )
    versions = (
        {
            version.id: version
            for version in db.query(CoachWorkflowTemplateVersion)
            .filter(CoachWorkflowTemplateVersion.template_id.in_(template_ids))
            .all()
        }
        if template_ids
        else {}
    )
    assignments_by_template: dict[int, list[dict[str, object]]] = {}
    for assignment, client, profile in rows:
        version = versions.get(assignment.template_version_id)
        if version is None:
            continue
        assignments_by_template.setdefault(assignment.template_id, []).append(
            {
                "id": assignment.id,
                "client_id": assignment.client_user_id,
                "client_name": _display_name(client, profile),
                "version": version.version,
                "status": assignment.status,
                "created_at": assignment.created_at,
            }
        )
    return {
        "items": [
            _template_payload(
                template,
                latest.get(template.id),
                assignments=assignments_by_template.get(template.id),
            )
            for template in templates
        ]
    }


def list_communication_templates(db: Session, coach: User) -> dict[str, object]:
    templates, latest = _workflow_rows(db, coach, "communication")
    template_ids = [template.id for template in templates]
    rows = (
        db.query(CoachCommunicationDraft, User, UserProfile, CoachWorkflowTemplateVersion)
        .join(User, User.id == CoachCommunicationDraft.client_user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .join(
            CoachWorkflowTemplateVersion,
            CoachWorkflowTemplateVersion.id == CoachCommunicationDraft.template_version_id,
        )
        .filter(
            CoachCommunicationDraft.coach_user_id == coach.id,
            CoachCommunicationDraft.template_id.in_(template_ids),
        )
        .order_by(CoachCommunicationDraft.id.desc())
        .all()
        if template_ids
        else []
    )
    drafts_by_template: dict[int, list[dict[str, object]]] = {}
    for draft, client, profile, version in rows:
        drafts_by_template.setdefault(draft.template_id, []).append(
            {
                "id": draft.id,
                "client_id": draft.client_user_id,
                "client_name": _display_name(client, profile),
                "version": version.version,
                "status": draft.status,
                "updated_at": draft.updated_at,
                "confirmed_at": draft.confirmed_at,
            }
        )
    return {
        "items": [
            _template_payload(
                template,
                latest.get(template.id),
                drafts=drafts_by_template.get(template.id),
            )
            for template in templates
        ]
    }


def create_onboarding_template(
    db: Session,
    coach: User,
    payload: OnboardingTemplateCreate,
    idempotency_key: str | None,
) -> dict[str, object]:
    key = _require_key(idempotency_key)
    _validate_onboarding_references(db, coach, payload)
    name = payload.name.strip()
    if not name:
        raise CoachWorkflowTemplateError("Название шаблона не может быть пустым", 422)
    version_payload = _onboarding_payload(payload)
    fingerprint = _fingerprint(payload.model_dump(mode="json"))
    existing = (
        db.query(CoachWorkflowTemplate)
        .filter(
            CoachWorkflowTemplate.coach_user_id == coach.id,
            CoachWorkflowTemplate.kind == "onboarding",
            CoachWorkflowTemplate.idempotency_key == key,
        )
        .with_for_update()
        .first()
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise CoachWorkflowTemplateError(
                "Idempotency-Key уже использован для другого шаблона",
                409,
            )
        return _template_payload(existing, _latest_versions(db, [existing.id]).get(existing.id))

    template = CoachWorkflowTemplate(
        coach_user_id=coach.id,
        kind="onboarding",
        name=name,
        description=payload.description.strip() if payload.description else None,
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    db.add(template)
    db.flush()
    version = CoachWorkflowTemplateVersion(
        template_id=template.id,
        version=1,
        payload=version_payload,
        idempotency_key=f"{key}:v1"[:128],
        request_fingerprint=fingerprint,
    )
    db.add(version)
    record_audit_event(
        db,
        actor_user_id=coach.id,
        action="coach.onboarding_template_created",
        resource_type="coach_workflow_template",
        resource_id=template.id,
        details={"step_count": len(payload.steps)},
    )
    db.commit()
    db.refresh(template)
    db.refresh(version)
    return _template_payload(template, version)


def create_onboarding_template_version(
    db: Session,
    coach: User,
    template_id: int,
    payload: OnboardingTemplateVersionCreate,
    idempotency_key: str | None,
) -> dict[str, object]:
    key = _require_key(idempotency_key)
    _validate_onboarding_references(db, coach, payload)
    template = _template_or_404(db, coach, template_id, "onboarding", lock=True)
    version_payload = _onboarding_payload(payload)
    fingerprint = _fingerprint({"template_id": template.id, "payload": version_payload})
    existing = (
        db.query(CoachWorkflowTemplateVersion)
        .filter(
            CoachWorkflowTemplateVersion.template_id == template.id,
            CoachWorkflowTemplateVersion.idempotency_key == key,
        )
        .first()
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise CoachWorkflowTemplateError(
                "Idempotency-Key уже использован для другой версии",
                409,
            )
        return _template_version_payload(existing)
    version = CoachWorkflowTemplateVersion(
        template_id=template.id,
        version=_version_number(db, template.id) + 1,
        payload=version_payload,
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    template.updated_at = now_msk_naive()
    db.add(version)
    record_audit_event(
        db,
        actor_user_id=coach.id,
        action="coach.onboarding_template_version_created",
        resource_type="coach_workflow_template",
        resource_id=template.id,
        details={"version": version.version, "step_count": len(payload.steps)},
    )
    db.commit()
    db.refresh(version)
    return _template_version_payload(version)


def assign_onboarding_template(
    db: Session,
    coach: User,
    template_id: int,
    client_id: int,
    version_number: int | None,
    idempotency_key: str | None,
) -> dict[str, object]:
    key = _require_key(idempotency_key)
    template = _template_or_404(db, coach, template_id, "onboarding", lock=True)
    if not template.is_active:
        raise CoachWorkflowTemplateError("Нельзя назначить неактивный шаблон", 409)
    try:
        client = get_client_managed_by_coach(db, coach, client_id)
    except ProgramError as exc:
        raise CoachWorkflowTemplateError(
            "Клиент не находится под управлением тренера", 404
        ) from exc
    fingerprint = _fingerprint(
        {"template_id": template.id, "client_id": client.id, "version": version_number}
    )
    existing_key = (
        db.query(CoachWorkflowAssignment)
        .filter(
            CoachWorkflowAssignment.coach_user_id == coach.id,
            CoachWorkflowAssignment.idempotency_key == key,
        )
        .with_for_update()
        .first()
    )
    if existing_key:
        if existing_key.request_fingerprint != fingerprint:
            raise CoachWorkflowTemplateError(
                "Idempotency-Key уже использован для другого назначения",
                409,
            )
        version = db.get(CoachWorkflowTemplateVersion, existing_key.template_version_id)
        if version is None:
            raise CoachWorkflowTemplateError("Версия назначения не найдена", 404)
        return _assignment_payload(existing_key, client, version)
    version = (
        _latest_versions(db, [template.id]).get(template.id)
        if version_number is None
        else _version_or_404(db, template.id, version_number)
    )
    if version is None:
        raise CoachWorkflowTemplateError("У шаблона нет версии для назначения", 409)
    assignment = CoachWorkflowAssignment(
        template_id=template.id,
        template_version_id=version.id,
        coach_user_id=coach.id,
        client_user_id=client.id,
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    db.add(assignment)
    db.flush()
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=client.id,
        action="coach.onboarding_template_assigned",
        resource_type="coach_workflow_assignment",
        resource_id=assignment.id,
        details={"template_id": template.id, "version": version.version},
    )
    db.commit()
    db.refresh(assignment)
    return _assignment_payload(assignment, client, version)


def create_communication_template(
    db: Session,
    coach: User,
    payload: CommunicationTemplateCreate,
    idempotency_key: str | None,
) -> dict[str, object]:
    key = _require_key(idempotency_key)
    content = _communication_payload(payload)
    name = payload.name.strip()
    if not name:
        raise CoachWorkflowTemplateError("Название шаблона не может быть пустым", 422)
    fingerprint = _fingerprint(payload.model_dump(mode="json"))
    existing = (
        db.query(CoachWorkflowTemplate)
        .filter(
            CoachWorkflowTemplate.coach_user_id == coach.id,
            CoachWorkflowTemplate.kind == "communication",
            CoachWorkflowTemplate.idempotency_key == key,
        )
        .with_for_update()
        .first()
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise CoachWorkflowTemplateError(
                "Idempotency-Key уже использован для другого шаблона",
                409,
            )
        return _template_payload(existing, _latest_versions(db, [existing.id]).get(existing.id))

    template = CoachWorkflowTemplate(
        coach_user_id=coach.id,
        kind="communication",
        name=name,
        description=payload.description.strip() if payload.description else None,
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    db.add(template)
    db.flush()
    version = CoachWorkflowTemplateVersion(
        template_id=template.id,
        version=1,
        payload=content,
        idempotency_key=f"{key}:v1"[:128],
        request_fingerprint=fingerprint,
    )
    db.add(version)
    record_audit_event(
        db,
        actor_user_id=coach.id,
        action="coach.communication_template_created",
        resource_type="coach_workflow_template",
        resource_id=template.id,
        details={"subject_length": len(content["subject"])},
    )
    db.commit()
    db.refresh(template)
    db.refresh(version)
    return _template_payload(template, version)


def create_communication_template_version(
    db: Session,
    coach: User,
    template_id: int,
    payload: CommunicationTemplateVersionCreate,
    idempotency_key: str | None,
) -> dict[str, object]:
    key = _require_key(idempotency_key)
    content = _communication_payload(payload)
    template = _template_or_404(db, coach, template_id, "communication", lock=True)
    fingerprint = _fingerprint({"template_id": template.id, "payload": content})
    existing = (
        db.query(CoachWorkflowTemplateVersion)
        .filter(
            CoachWorkflowTemplateVersion.template_id == template.id,
            CoachWorkflowTemplateVersion.idempotency_key == key,
        )
        .first()
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise CoachWorkflowTemplateError(
                "Idempotency-Key уже использован для другой версии",
                409,
            )
        return _template_version_payload(existing)
    version = CoachWorkflowTemplateVersion(
        template_id=template.id,
        version=_version_number(db, template.id) + 1,
        payload=content,
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    template.updated_at = now_msk_naive()
    db.add(version)
    record_audit_event(
        db,
        actor_user_id=coach.id,
        action="coach.communication_template_version_created",
        resource_type="coach_workflow_template",
        resource_id=template.id,
        details={"version": version.version, "subject_length": len(content["subject"])},
    )
    db.commit()
    db.refresh(version)
    return _template_version_payload(version)


def create_communication_draft(
    db: Session,
    coach: User,
    template_id: int,
    payload: CommunicationDraftCreate,
    idempotency_key: str | None,
) -> dict[str, object]:
    key = _require_key(idempotency_key)
    template = _template_or_404(db, coach, template_id, "communication", lock=True)
    if not template.is_active:
        raise CoachWorkflowTemplateError("Нельзя создать черновик неактивного шаблона", 409)
    try:
        client = get_client_managed_by_coach(db, coach, payload.client_id)
    except ProgramError as exc:
        raise CoachWorkflowTemplateError(
            "Клиент не находится под управлением тренера", 404
        ) from exc
    version = (
        _latest_versions(db, [template.id]).get(template.id)
        if payload.version is None
        else _version_or_404(db, template.id, payload.version)
    )
    if version is None:
        raise CoachWorkflowTemplateError("У шаблона нет версии для черновика", 409)
    defaults = version.payload
    subject = (payload.subject or str(defaults.get("subject", ""))).strip()
    body = (payload.body or str(defaults.get("body", ""))).strip()
    if not subject or not body:
        raise CoachWorkflowTemplateError("Тема и текст сообщения не могут быть пустыми", 422)
    fingerprint = _fingerprint(
        {
            "template_id": template.id,
            "client_id": client.id,
            "version": version.version,
            "subject": subject,
            "body": body,
        }
    )
    existing = (
        db.query(CoachCommunicationDraft)
        .filter(
            CoachCommunicationDraft.coach_user_id == coach.id,
            CoachCommunicationDraft.idempotency_key == key,
        )
        .with_for_update()
        .first()
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise CoachWorkflowTemplateError(
                "Idempotency-Key уже использован для другого черновика",
                409,
            )
        existing_version = db.get(
            CoachWorkflowTemplateVersion,
            existing.template_version_id,
        )
        if existing_version is None:
            raise CoachWorkflowTemplateError("Версия черновика не найдена", 404)
        return _draft_payload(existing, client, existing_version)
    draft = CoachCommunicationDraft(
        template_id=template.id,
        template_version_id=version.id,
        coach_user_id=coach.id,
        client_user_id=client.id,
        subject=subject,
        body=body,
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    db.add(draft)
    db.flush()
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=client.id,
        action="coach.communication_draft_created",
        resource_type="coach_communication_draft",
        resource_id=draft.id,
        details={"template_id": template.id, "version": version.version},
    )
    db.commit()
    db.refresh(draft)
    return _draft_payload(draft, client, version)


def update_communication_draft(
    db: Session,
    coach: User,
    draft_id: int,
    payload: CommunicationDraftUpdate,
) -> dict[str, object]:
    draft = (
        db.query(CoachCommunicationDraft)
        .filter(
            CoachCommunicationDraft.id == draft_id,
            CoachCommunicationDraft.coach_user_id == coach.id,
        )
        .with_for_update()
        .first()
    )
    if draft is None:
        raise CoachWorkflowTemplateError("Черновик сообщения не найден", 404)
    if draft.status != "draft":
        raise CoachWorkflowTemplateError("Подтверждённый черновик нельзя изменять", 409)
    subject = payload.subject.strip()
    body = payload.body.strip()
    if not subject or not body:
        raise CoachWorkflowTemplateError("Тема и текст сообщения не могут быть пустыми", 422)
    draft.subject = subject
    draft.body = body
    draft.updated_at = now_msk_naive()
    client = db.get(User, draft.client_user_id)
    version = db.get(CoachWorkflowTemplateVersion, draft.template_version_id)
    if client is None or version is None:
        raise CoachWorkflowTemplateError("Данные черновика недоступны", 404)
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=client.id,
        action="coach.communication_draft_updated",
        resource_type="coach_communication_draft",
        resource_id=draft.id,
        details={"subject_length": len(subject), "body_length": len(body)},
    )
    db.commit()
    db.refresh(draft)
    return _draft_payload(draft, client, version)


def get_communication_draft(
    db: Session,
    coach: User,
    draft_id: int,
) -> dict[str, object]:
    draft = (
        db.query(CoachCommunicationDraft)
        .filter(
            CoachCommunicationDraft.id == draft_id,
            CoachCommunicationDraft.coach_user_id == coach.id,
        )
        .first()
    )
    if draft is None:
        raise CoachWorkflowTemplateError("Черновик сообщения не найден", 404)
    client = db.get(User, draft.client_user_id)
    version = db.get(CoachWorkflowTemplateVersion, draft.template_version_id)
    if client is None or version is None:
        raise CoachWorkflowTemplateError("Данные черновика недоступны", 404)
    return _draft_payload(draft, client, version)


def confirm_communication_draft(
    db: Session,
    coach: User,
    draft_id: int,
    idempotency_key: str | None,
) -> dict[str, object]:
    key = _require_key(idempotency_key)
    existing_key = (
        db.query(CoachCommunicationDraft)
        .filter(
            CoachCommunicationDraft.coach_user_id == coach.id,
            CoachCommunicationDraft.confirm_idempotency_key == key,
            CoachCommunicationDraft.id != draft_id,
        )
        .first()
    )
    if existing_key:
        raise CoachWorkflowTemplateError(
            "Idempotency-Key уже использован для другого подтверждения",
            409,
        )
    draft = (
        db.query(CoachCommunicationDraft)
        .filter(
            CoachCommunicationDraft.id == draft_id,
            CoachCommunicationDraft.coach_user_id == coach.id,
        )
        .with_for_update()
        .first()
    )
    if draft is None:
        raise CoachWorkflowTemplateError("Черновик сообщения не найден", 404)
    client = db.get(User, draft.client_user_id)
    version = db.get(CoachWorkflowTemplateVersion, draft.template_version_id)
    if client is None or version is None:
        raise CoachWorkflowTemplateError("Данные черновика недоступны", 404)
    if draft.status == "confirmed":
        return _draft_payload(draft, client, version)
    try:
        get_client_managed_by_coach(db, coach, draft.client_user_id)
    except ProgramError as exc:
        raise CoachWorkflowTemplateError(
            "Клиент больше не находится под управлением тренера", 409
        ) from exc
    notification = queue_notification(
        db,
        client,
        category="coach_message",
        title=draft.subject,
        body=draft.body,
        dedupe_key=f"coach_message:{draft.id}",
        action_url="/app?section=profile",
    )
    db.flush()
    draft.status = "confirmed"
    draft.notification_id = notification.id
    draft.confirm_idempotency_key = key
    draft.confirm_request_fingerprint = _fingerprint({"draft_id": draft.id})
    draft.confirmed_at = now_msk_naive()
    draft.updated_at = now_msk_naive()
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=client.id,
        action="coach.communication_draft_confirmed",
        resource_type="coach_communication_draft",
        resource_id=draft.id,
        details={"notification_id": notification.id},
    )
    db.commit()
    db.refresh(draft)
    return _draft_payload(draft, client, version)


__all__ = [
    "CoachWorkflowTemplateError",
    "assign_onboarding_template",
    "confirm_communication_draft",
    "create_communication_draft",
    "create_communication_template",
    "create_communication_template_version",
    "create_onboarding_template",
    "create_onboarding_template_version",
    "get_communication_draft",
    "list_communication_templates",
    "list_onboarding_templates",
    "update_communication_draft",
]
