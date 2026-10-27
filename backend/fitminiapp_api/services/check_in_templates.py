from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import now_msk_naive, today_for_user
from fitminiapp_api.models.check_in_templates import (
    CoachCheckInAssignment,
    CoachCheckInResponse,
    CoachCheckInTemplate,
    CoachCheckInTemplateVersion,
)
from fitminiapp_api.models.user import CoachClient, User, UserProfile
from fitminiapp_api.schemas.check_in_templates import (
    CheckInTemplateAssignmentCreate,
    CheckInTemplateCreate,
    CheckInTemplateResponseSubmit,
    CheckInTemplateVersionCreate,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.coach_clients import get_client_managed_by_coach
from fitminiapp_api.services.program_common import ProgramError

CHECK_IN_FIELD_CATALOG: dict[str, dict[str, object]] = {
    "recovery": {
        "label": "Восстановление",
        "value_type": "score",
        "min_value": 1,
        "max_value": 5,
    },
    "hunger": {
        "label": "Голод",
        "value_type": "score",
        "min_value": 1,
        "max_value": 5,
    },
    "training_load": {
        "label": "Тренировочная нагрузка",
        "value_type": "score",
        "min_value": 1,
        "max_value": 5,
    },
    "adherence_difficulty": {
        "label": "Сложность следования плану",
        "value_type": "score",
        "min_value": 1,
        "max_value": 5,
    },
}
CADENCE_DAYS = {"weekly": 7, "biweekly": 14, "monthly": 30}


class CheckInTemplateError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_key(idempotency_key: str | None) -> str:
    if not idempotency_key or not 8 <= len(idempotency_key) <= 128:
        raise CheckInTemplateError("Требуется Idempotency-Key длиной от 8 до 128 символов", 422)
    return idempotency_key


def _validate_fields(fields: list[dict[str, object]]) -> list[dict[str, object]]:
    keys = [str(field.get("key", "")) for field in fields]
    if not fields or len(fields) > 4 or len(keys) != len(set(keys)):
        raise CheckInTemplateError("Укажите от одного до четырех уникальных полей", 422)
    if any(key not in CHECK_IN_FIELD_CATALOG for key in keys):
        raise CheckInTemplateError("Выбрано неподдерживаемое поле проверки", 422)
    return [
        {"key": str(field["key"]), "required": bool(field.get("required", True))}
        for field in fields
    ]


def _fields_from_version(version: CoachCheckInTemplateVersion) -> list[dict[str, object]]:
    return [
        {
            "key": definition["key"],
            **CHECK_IN_FIELD_CATALOG[str(definition["key"])],
            "required": bool(definition.get("required", True)),
        }
        for definition in version.field_definitions
    ]


def field_catalog() -> list[dict[str, object]]:
    return [{"key": key, **definition} for key, definition in CHECK_IN_FIELD_CATALOG.items()]


def _display_name(user: User, profile: UserProfile | None = None) -> str:
    profile = profile or user.profile
    return (profile.full_name if profile else None) or user.username or f"Клиент {user.id}"


def _template_or_404(db: Session, coach: User, template_id: int, *, lock: bool = False):
    query = db.query(CoachCheckInTemplate).filter(
        CoachCheckInTemplate.id == template_id,
        CoachCheckInTemplate.coach_user_id == coach.id,
    )
    if lock:
        query = query.with_for_update()
    template = query.first()
    if not template:
        raise CheckInTemplateError("Шаблон проверки не найден", 404)
    return template


def _version_or_404(db: Session, template_id: int, version_number: int):
    version = (
        db.query(CoachCheckInTemplateVersion)
        .filter(
            CoachCheckInTemplateVersion.template_id == template_id,
            CoachCheckInTemplateVersion.version == version_number,
        )
        .first()
    )
    if not version:
        raise CheckInTemplateError("Версия шаблона не найдена", 404)
    return version


def _latest_versions(
    db: Session, template_ids: list[int]
) -> dict[int, CoachCheckInTemplateVersion]:
    if not template_ids:
        return {}
    rows = (
        db.query(CoachCheckInTemplateVersion)
        .filter(CoachCheckInTemplateVersion.template_id.in_(template_ids))
        .order_by(
            CoachCheckInTemplateVersion.template_id,
            CoachCheckInTemplateVersion.version.desc(),
        )
        .all()
    )
    latest: dict[int, CoachCheckInTemplateVersion] = {}
    for row in rows:
        latest.setdefault(row.template_id, row)
    return latest


def _template_payload(
    template: CoachCheckInTemplate,
    current_version: CoachCheckInTemplateVersion | None,
    assignments: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "cadence": template.cadence,
        "is_active": template.is_active,
        "current_version": (
            {
                "id": current_version.id,
                "version": current_version.version,
                "fields": _fields_from_version(current_version),
                "created_at": current_version.created_at,
            }
            if current_version
            else None
        ),
        "assignments": assignments,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def list_templates(db: Session, coach: User) -> dict[str, object]:
    templates = (
        db.query(CoachCheckInTemplate)
        .filter(CoachCheckInTemplate.coach_user_id == coach.id)
        .order_by(CoachCheckInTemplate.updated_at.desc(), CoachCheckInTemplate.id.desc())
        .all()
    )
    template_ids = [template.id for template in templates]
    latest = _latest_versions(db, template_ids)
    version_rows = (
        db.query(CoachCheckInTemplateVersion)
        .filter(CoachCheckInTemplateVersion.template_id.in_(template_ids))
        .all()
        if template_ids
        else []
    )
    versions_by_id = {version.id: version for version in version_rows}
    assignment_rows = (
        db.query(CoachCheckInAssignment, User, UserProfile)
        .join(User, User.id == CoachCheckInAssignment.client_user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .join(
            CoachClient,
            and_(
                CoachClient.coach_user_id == CoachCheckInAssignment.coach_user_id,
                CoachClient.client_user_id == CoachCheckInAssignment.client_user_id,
                CoachClient.status == "active",
            ),
        )
        .filter(
            CoachCheckInAssignment.coach_user_id == coach.id,
            CoachCheckInAssignment.template_id.in_(template_ids),
        )
        .order_by(CoachCheckInAssignment.id.desc())
        .all()
        if template_ids
        else []
    )
    assignments_by_template: dict[int, list[dict[str, object]]] = {}
    for assignment, client, profile in assignment_rows:
        version = versions_by_id.get(assignment.template_version_id)
        if not version:
            continue
        assignments_by_template.setdefault(assignment.template_id, []).append(
            {
                "id": assignment.id,
                "client_id": assignment.client_user_id,
                "client_name": _display_name(client, profile),
                "version": version.version,
                "status": assignment.status,
                "next_due_on": assignment.next_due_on,
                "last_response_at": assignment.last_response_at,
            }
        )
    return {
        "items": [
            _template_payload(
                template,
                latest.get(template.id),
                assignments_by_template.get(template.id, []),
            )
            for template in templates
        ],
        "field_catalog": field_catalog(),
    }


def create_template(
    db: Session,
    coach: User,
    payload: CheckInTemplateCreate,
    idempotency_key: str | None,
) -> dict[str, object]:
    key = _require_key(idempotency_key)
    fields = _validate_fields([field.model_dump() for field in payload.fields])
    name = payload.name.strip()
    if not name:
        raise CheckInTemplateError("Название шаблона не может быть пустым", 422)
    fingerprint = _fingerprint(payload.model_dump(mode="json"))
    existing = (
        db.query(CoachCheckInTemplate)
        .filter(
            CoachCheckInTemplate.coach_user_id == coach.id,
            CoachCheckInTemplate.idempotency_key == key,
        )
        .with_for_update()
        .first()
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise CheckInTemplateError("Idempotency-Key уже использован для другого шаблона", 409)
        current = _latest_versions(db, [existing.id]).get(existing.id)
        return _template_payload(existing, current, [])

    template = CoachCheckInTemplate(
        coach_user_id=coach.id,
        name=name,
        description=payload.description.strip() if payload.description else None,
        cadence=payload.cadence,
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    db.add(template)
    db.flush()
    version = CoachCheckInTemplateVersion(
        template_id=template.id,
        version=1,
        field_definitions=fields,
        idempotency_key=f"{key}:v1"[:128],
        request_fingerprint=fingerprint,
    )
    db.add(version)
    record_audit_event(
        db,
        actor_user_id=coach.id,
        action="coach.check_in_template_created",
        resource_type="coach_check_in_template",
        resource_id=template.id,
        details={"cadence": template.cadence, "field_keys": [field["key"] for field in fields]},
    )
    db.commit()
    db.refresh(template)
    db.refresh(version)
    return _template_payload(template, version, [])


def create_template_version(
    db: Session,
    coach: User,
    template_id: int,
    payload: CheckInTemplateVersionCreate,
    idempotency_key: str | None,
) -> dict[str, object]:
    key = _require_key(idempotency_key)
    fields = _validate_fields([field.model_dump() for field in payload.fields])
    template = _template_or_404(db, coach, template_id, lock=True)
    fingerprint = _fingerprint(
        {"template_id": template.id, "payload": payload.model_dump(mode="json")}
    )
    existing = (
        db.query(CoachCheckInTemplateVersion)
        .filter(
            CoachCheckInTemplateVersion.template_id == template.id,
            CoachCheckInTemplateVersion.idempotency_key == key,
        )
        .first()
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise CheckInTemplateError("Idempotency-Key уже использован для другой версии", 409)
        return {
            "id": existing.id,
            "version": existing.version,
            "fields": _fields_from_version(existing),
            "created_at": existing.created_at,
        }
    latest = (
        db.query(func.max(CoachCheckInTemplateVersion.version))
        .filter(CoachCheckInTemplateVersion.template_id == template.id)
        .scalar()
        or 0
    )
    version = CoachCheckInTemplateVersion(
        template_id=template.id,
        version=int(latest) + 1,
        field_definitions=fields,
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    template.updated_at = now_msk_naive()
    db.add(version)
    record_audit_event(
        db,
        actor_user_id=coach.id,
        action="coach.check_in_template_version_created",
        resource_type="coach_check_in_template",
        resource_id=template.id,
        details={"version": version.version, "field_keys": [field["key"] for field in fields]},
    )
    db.commit()
    db.refresh(version)
    return {
        "id": version.id,
        "version": version.version,
        "fields": _fields_from_version(version),
        "created_at": version.created_at,
    }


def set_template_active(
    db: Session,
    coach: User,
    template_id: int,
    is_active: bool,
) -> dict[str, object]:
    template = _template_or_404(db, coach, template_id, lock=True)
    template.is_active = is_active
    template.updated_at = now_msk_naive()
    record_audit_event(
        db,
        actor_user_id=coach.id,
        action="coach.check_in_template_state_changed",
        resource_type="coach_check_in_template",
        resource_id=template.id,
        details={"is_active": is_active},
    )
    db.commit()
    db.refresh(template)
    current = _latest_versions(db, [template.id]).get(template.id)
    return _template_payload(template, current, [])


def assign_template(
    db: Session,
    coach: User,
    template_id: int,
    payload: CheckInTemplateAssignmentCreate,
    idempotency_key: str | None,
) -> dict[str, object]:
    key = _require_key(idempotency_key)
    template = _template_or_404(db, coach, template_id, lock=True)
    if not template.is_active:
        raise CheckInTemplateError("Нельзя назначить неактивный шаблон", 409)
    try:
        client = get_client_managed_by_coach(db, coach, payload.client_id)
    except ProgramError as exc:
        raise CheckInTemplateError("Клиент не находится под управлением тренера", 404) from exc
    fingerprint = _fingerprint(
        {"template_id": template.id, "payload": payload.model_dump(mode="json")}
    )
    existing_key = (
        db.query(CoachCheckInAssignment)
        .filter(
            CoachCheckInAssignment.coach_user_id == coach.id,
            CoachCheckInAssignment.idempotency_key == key,
        )
        .with_for_update()
        .first()
    )
    if existing_key:
        if existing_key.request_fingerprint != fingerprint:
            raise CheckInTemplateError(
                "Idempotency-Key уже использован для другого назначения", 409
            )
        version = (
            db.query(CoachCheckInTemplateVersion)
            .filter(CoachCheckInTemplateVersion.id == existing_key.template_version_id)
            .first()
        )
        if not version:
            raise CheckInTemplateError("Версия назначения не найдена", 404)
        return _assignment_payload(existing_key, client, version)

    version_number = payload.version
    if version_number is None:
        version = _latest_versions(db, [template.id]).get(template.id)
    else:
        version = _version_or_404(db, template.id, version_number)
    if not version:
        raise CheckInTemplateError("У шаблона нет версии для назначения", 409)
    assignment = (
        db.query(CoachCheckInAssignment)
        .filter(
            CoachCheckInAssignment.template_id == template.id,
            CoachCheckInAssignment.client_user_id == client.id,
        )
        .with_for_update()
        .first()
    )
    due_on = payload.due_on or today_for_user(client)
    if assignment:
        assignment.template_version_id = version.id
        assignment.status = "active"
        assignment.next_due_on = due_on
        assignment.idempotency_key = key
        assignment.request_fingerprint = fingerprint
        assignment.updated_at = now_msk_naive()
    else:
        assignment = CoachCheckInAssignment(
            template_id=template.id,
            template_version_id=version.id,
            coach_user_id=coach.id,
            client_user_id=client.id,
            next_due_on=due_on,
            idempotency_key=key,
            request_fingerprint=fingerprint,
        )
        db.add(assignment)
        db.flush()
    record_audit_event(
        db,
        actor_user_id=coach.id,
        target_user_id=client.id,
        action="coach.check_in_template_assigned",
        resource_type="coach_check_in_assignment",
        resource_id=assignment.id,
        details={"template_id": template.id, "version": version.version},
    )
    db.commit()
    db.refresh(assignment)
    return _assignment_payload(assignment, client, version)


def _assignment_payload(
    assignment: CoachCheckInAssignment,
    client: User,
    version: CoachCheckInTemplateVersion,
) -> dict[str, object]:
    return {
        "id": assignment.id,
        "client_id": assignment.client_user_id,
        "client_name": _display_name(client),
        "version": version.version,
        "status": assignment.status,
        "next_due_on": assignment.next_due_on,
        "last_response_at": assignment.last_response_at,
    }


def list_assigned_templates(db: Session, client: User) -> dict[str, object]:
    rows = (
        db.query(CoachCheckInAssignment, CoachCheckInTemplate, CoachCheckInTemplateVersion)
        .join(
            CoachCheckInTemplate,
            CoachCheckInTemplate.id == CoachCheckInAssignment.template_id,
        )
        .join(
            CoachCheckInTemplateVersion,
            CoachCheckInTemplateVersion.id == CoachCheckInAssignment.template_version_id,
        )
        .join(
            CoachClient,
            (CoachClient.coach_user_id == CoachCheckInAssignment.coach_user_id)
            & (CoachClient.client_user_id == client.id)
            & (CoachClient.status == "active"),
        )
        .filter(
            CoachCheckInAssignment.client_user_id == client.id,
            CoachCheckInAssignment.status == "active",
            CoachCheckInTemplate.is_active.is_(True),
        )
        .order_by(CoachCheckInAssignment.next_due_on.asc(), CoachCheckInAssignment.id.asc())
        .all()
    )
    return {
        "items": [
            {
                "assignment_id": assignment.id,
                "template_id": template.id,
                "name": template.name,
                "description": template.description,
                "cadence": template.cadence,
                "version": version.version,
                "fields": _fields_from_version(version),
                "next_due_on": assignment.next_due_on,
                "status": "active",
            }
            for assignment, template, version in rows
        ]
    }


def submit_response(
    db: Session,
    client: User,
    assignment_id: int,
    payload: CheckInTemplateResponseSubmit,
    idempotency_key: str | None,
) -> dict[str, object]:
    key = _require_key(idempotency_key)
    assignment_row = (
        db.query(CoachCheckInAssignment, CoachCheckInTemplate, CoachCheckInTemplateVersion)
        .join(
            CoachCheckInTemplate,
            CoachCheckInTemplate.id == CoachCheckInAssignment.template_id,
        )
        .join(
            CoachCheckInTemplateVersion,
            CoachCheckInTemplateVersion.id == CoachCheckInAssignment.template_version_id,
        )
        .filter(
            CoachCheckInAssignment.id == assignment_id,
            CoachCheckInAssignment.client_user_id == client.id,
            CoachCheckInAssignment.status == "active",
            CoachCheckInTemplate.is_active.is_(True),
        )
        .with_for_update()
        .first()
    )
    if not assignment_row:
        raise CheckInTemplateError("Назначенная проверка не найдена", 404)
    assignment, template, version = assignment_row
    if not (
        db.query(CoachClient)
        .filter(
            CoachClient.coach_user_id == assignment.coach_user_id,
            CoachClient.client_user_id == client.id,
            CoachClient.status == "active",
        )
        .first()
    ):
        raise CheckInTemplateError("Назначенная проверка больше недоступна", 404)

    values = dict(payload.values)
    fingerprint = _fingerprint({"assignment_id": assignment.id, "values": values})
    existing_key = (
        db.query(CoachCheckInResponse)
        .filter(
            CoachCheckInResponse.client_user_id == client.id,
            CoachCheckInResponse.idempotency_key == key,
        )
        .first()
    )
    if existing_key:
        if existing_key.request_fingerprint != fingerprint:
            raise CheckInTemplateError("Idempotency-Key уже использован для другого ответа", 409)
        original_version = (
            db.query(CoachCheckInTemplateVersion)
            .filter(CoachCheckInTemplateVersion.id == existing_key.template_version_id)
            .first()
        )
        if not original_version:
            raise CheckInTemplateError("Версия сохраненного ответа не найдена", 409)
        return _response_payload(existing_key, template, original_version, replayed=True)

    definitions = {str(item["key"]): item for item in version.field_definitions}
    unknown = set(values).difference(definitions)
    if unknown:
        raise CheckInTemplateError("Ответ содержит неподдерживаемое поле", 422)
    missing = {
        key_name
        for key_name, definition in definitions.items()
        if bool(definition.get("required", True)) and key_name not in values
    }
    if missing:
        raise CheckInTemplateError("Заполните обязательные поля проверки", 422)
    if any(
        isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5
        for value in values.values()
    ):
        raise CheckInTemplateError("Значения проверки должны быть целыми числами от 1 до 5", 422)

    due_on = assignment.next_due_on
    if today_for_user(client) < due_on:
        raise CheckInTemplateError("Проверка еще недоступна по расписанию", 409)
    if (
        db.query(CoachCheckInResponse)
        .filter(
            CoachCheckInResponse.assignment_id == assignment.id,
            CoachCheckInResponse.due_on == due_on,
        )
        .first()
    ):
        raise CheckInTemplateError("Ответ за текущий период уже сохранен", 409)

    response = CoachCheckInResponse(
        assignment_id=assignment.id,
        template_id=template.id,
        template_version_id=version.id,
        coach_user_id=assignment.coach_user_id,
        client_user_id=client.id,
        due_on=due_on,
        values=values,
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    db.add(response)
    submitted_at = now_msk_naive()
    assignment.last_response_at = submitted_at
    assignment.next_due_on = due_on + timedelta(days=CADENCE_DAYS[template.cadence])
    assignment.updated_at = submitted_at
    record_audit_event(
        db,
        actor_user_id=client.id,
        target_user_id=client.id,
        action="client.check_in_template_completed",
        resource_type="coach_check_in_response",
        resource_id=assignment.id,
        details={"template_id": template.id, "version": version.version},
    )
    db.commit()
    db.refresh(response)
    return _response_payload(response, template, version, replayed=False)


def _response_payload(
    response: CoachCheckInResponse,
    template: CoachCheckInTemplate,
    version: CoachCheckInTemplateVersion,
    *,
    replayed: bool,
) -> dict[str, object]:
    return {
        "id": response.id,
        "assignment_id": response.assignment_id,
        "template_id": response.template_id,
        "template_name": template.name,
        "version": version.version,
        "due_on": response.due_on,
        "values": response.values,
        "submitted_at": response.submitted_at,
        "replayed": replayed,
    }


def list_response_history(
    db: Session,
    coach: User,
    template_id: int,
    client_id: int | None,
    *,
    limit: int,
) -> dict[str, object]:
    template = _template_or_404(db, coach, template_id)
    if client_id is not None:
        try:
            get_client_managed_by_coach(db, coach, client_id)
        except ProgramError as exc:
            raise CheckInTemplateError("Клиент не находится под управлением тренера", 404) from exc
    query = (
        db.query(
            CoachCheckInResponse,
            CoachCheckInTemplateVersion,
            User,
            UserProfile,
        )
        .join(
            CoachCheckInTemplateVersion,
            CoachCheckInTemplateVersion.id == CoachCheckInResponse.template_version_id,
        )
        .join(User, User.id == CoachCheckInResponse.client_user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .join(
            CoachClient,
            and_(
                CoachClient.coach_user_id == CoachCheckInResponse.coach_user_id,
                CoachClient.client_user_id == CoachCheckInResponse.client_user_id,
                CoachClient.status == "active",
            ),
        )
        .filter(
            CoachCheckInResponse.coach_user_id == coach.id,
            CoachCheckInResponse.template_id == template.id,
        )
    )
    if client_id is not None:
        query = query.filter(CoachCheckInResponse.client_user_id == client_id)
    total = query.count()
    rows = query.order_by(CoachCheckInResponse.submitted_at.desc()).limit(limit).all()
    return {
        "items": [
            {
                **_response_payload(response, template, version, replayed=False),
                "client_id": response.client_user_id,
                "client_name": _display_name(client, profile),
            }
            for response, version, client, profile in rows
        ],
        "total": total,
        "limit": limit,
    }


__all__ = [
    "CHECK_IN_FIELD_CATALOG",
    "CheckInTemplateError",
    "assign_template",
    "create_template",
    "create_template_version",
    "field_catalog",
    "list_assigned_templates",
    "list_response_history",
    "list_templates",
    "set_template_active",
    "submit_response",
]
