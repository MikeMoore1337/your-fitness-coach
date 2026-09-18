from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.core.timezone import now_msk_naive, today_for_user
from fitminiapp_api.models.user import (
    BodyMeasurement,
    BodyMeasurementCustomValue,
    BodyMeasurementDefinition,
    User,
)
from fitminiapp_api.schemas.workout import (
    BodyMeasurementDefinitionCreate,
    BodyMeasurementDefinitionUpdate,
    BodyMeasurementSave,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.nutrition import NutritionError, recalculate_nutrition_target

MEASUREMENT_FIELDS = (
    "weight_kg",
    "chest_cm",
    "waist_cm",
    "hips_cm",
    "biceps_cm",
    "thigh_cm",
)


class MeasurementError(Exception):
    pass


class MeasurementNotFoundError(MeasurementError):
    pass


class CustomMeasurementDefinitionError(MeasurementError):
    pass


def _normalized_definition_label(label: str) -> str:
    return " ".join(label.strip().split()).casefold()


def serialize_custom_measurement_definition(row: BodyMeasurementDefinition) -> dict:
    return {
        "id": row.id,
        "label": row.label,
        "unit": row.unit,
        "archived": row.archived_at is not None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_custom_measurement_definitions(
    db: Session,
    owner: User,
    *,
    include_archived: bool,
) -> list[BodyMeasurementDefinition]:
    query = db.query(BodyMeasurementDefinition).filter(
        BodyMeasurementDefinition.user_id == owner.id
    )
    if not include_archived:
        query = query.filter(BodyMeasurementDefinition.archived_at.is_(None))
    return query.order_by(
        BodyMeasurementDefinition.archived_at.is_(None).desc(),
        BodyMeasurementDefinition.label,
        BodyMeasurementDefinition.id,
    ).all()


def create_custom_measurement_definition(
    db: Session,
    owner: User,
    payload: BodyMeasurementDefinitionCreate,
) -> BodyMeasurementDefinition:
    label = " ".join(payload.label.strip().split())
    normalized_label = _normalized_definition_label(label)
    if (
        db.query(BodyMeasurementDefinition.id)
        .filter(
            BodyMeasurementDefinition.user_id == owner.id,
            BodyMeasurementDefinition.normalized_label == normalized_label,
        )
        .first()
        is not None
    ):
        raise CustomMeasurementDefinitionError(
            "Показатель с таким названием уже существует. Восстановите его в архиве."
        )
    row = BodyMeasurementDefinition(
        user_id=owner.id,
        label=label,
        normalized_label=normalized_label,
        unit="cm",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CustomMeasurementDefinitionError(
            "Показатель с таким названием уже существует. Восстановите его в архиве."
        ) from exc
    db.refresh(row)
    return row


def _get_custom_measurement_definition(
    db: Session,
    owner: User,
    definition_id: int,
) -> BodyMeasurementDefinition:
    row = (
        db.query(BodyMeasurementDefinition)
        .filter(
            BodyMeasurementDefinition.id == definition_id,
            BodyMeasurementDefinition.user_id == owner.id,
        )
        .first()
    )
    if row is None:
        raise CustomMeasurementDefinitionError("Показатель замера недоступен")
    return row


def update_custom_measurement_definition(
    db: Session,
    owner: User,
    definition_id: int,
    payload: BodyMeasurementDefinitionUpdate,
) -> BodyMeasurementDefinition:
    row = _get_custom_measurement_definition(db, owner, definition_id)
    label = " ".join(payload.label.strip().split())
    normalized_label = _normalized_definition_label(label)
    duplicate = (
        db.query(BodyMeasurementDefinition.id)
        .filter(
            BodyMeasurementDefinition.user_id == owner.id,
            BodyMeasurementDefinition.normalized_label == normalized_label,
            BodyMeasurementDefinition.id != row.id,
        )
        .first()
    )
    if duplicate is not None:
        raise CustomMeasurementDefinitionError("Показатель с таким названием уже существует")
    row.label = label
    row.normalized_label = normalized_label
    row.updated_at = now_msk_naive()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CustomMeasurementDefinitionError(
            "Показатель с таким названием уже существует"
        ) from exc
    db.refresh(row)
    return row


def archive_custom_measurement_definition(
    db: Session,
    owner: User,
    definition_id: int,
) -> BodyMeasurementDefinition:
    row = _get_custom_measurement_definition(db, owner, definition_id)
    if row.archived_at is None:
        row.archived_at = now_msk_naive()
        row.updated_at = now_msk_naive()
        db.commit()
        db.refresh(row)
    return row


def restore_custom_measurement_definition(
    db: Session,
    owner: User,
    definition_id: int,
) -> BodyMeasurementDefinition:
    row = _get_custom_measurement_definition(db, owner, definition_id)
    if row.archived_at is not None:
        row.archived_at = None
        row.updated_at = now_msk_naive()
        db.commit()
        db.refresh(row)
    return row


def serialize_measurement(row: BodyMeasurement) -> dict:
    return {
        "id": row.id,
        "measured_on": row.measured_on,
        "weight_kg": row.weight_kg,
        "chest_cm": row.chest_cm,
        "waist_cm": row.waist_cm,
        "hips_cm": row.hips_cm,
        "biceps_cm": row.biceps_cm,
        "thigh_cm": row.thigh_cm,
        "note": row.note,
        "created_at": row.created_at,
        "custom_values": [
            {
                "definition_id": value.definition_id,
                "label": value.definition.label,
                "unit": value.definition.unit,
                "value": value.value,
                "archived": value.definition.archived_at is not None,
            }
            for value in sorted(
                row.custom_values,
                key=lambda item: (item.definition.label.casefold(), item.definition_id),
            )
        ],
    }


def list_measurements(db: Session, owner: User, *, limit: int) -> list[BodyMeasurement]:
    """Return measurement history, including preserved legacy future-dated rows."""
    return (
        db.query(BodyMeasurement)
        .options(
            selectinload(BodyMeasurement.custom_values).joinedload(
                BodyMeasurementCustomValue.definition
            )
        )
        .filter(BodyMeasurement.user_id == owner.id)
        .order_by(BodyMeasurement.measured_on.desc(), BodyMeasurement.id.desc())
        .limit(limit)
        .all()
    )


def latest_current_weight_measurement(
    db: Session,
    owner: User,
) -> BodyMeasurement | None:
    return (
        db.query(BodyMeasurement)
        .filter(
            BodyMeasurement.user_id == owner.id,
            BodyMeasurement.measured_on <= today_for_user(owner),
            BodyMeasurement.weight_kg.is_not(None),
        )
        .order_by(BodyMeasurement.measured_on.desc(), BodyMeasurement.id.desc())
        .first()
    )


def _lock_owner_measurements(db: Session, owner_user_id: int) -> None:
    """Serialize the owner's chronology mutation and derived-state reconciliation."""
    db.query(User.id).filter(User.id == owner_user_id).with_for_update().one()


def reconcile_current_measurement_state(
    db: Session,
    owner: User,
    *,
    changed_by: User,
) -> bool:
    """Recalculate current derived state from chronology, falling back to profile weight."""
    db.flush()
    latest = latest_current_weight_measurement(db, owner)
    weight_kg = latest.weight_kg if latest is not None else None
    if weight_kg is None and owner.profile is not None:
        weight_kg = owner.profile.weight_kg
    if weight_kg is None:
        return False
    return recalculate_nutrition_target(
        db,
        owner,
        {"weight_kg": weight_kg},
        changed_by,
    )


def _measurement_changes(payload: BodyMeasurementSave) -> dict[str, object]:
    changes = payload.model_dump(exclude_unset=True, exclude={"measured_on"})
    note = changes.get("note")
    if isinstance(note, str):
        changes["note"] = note.strip() or None
    return changes


def _load_measurement_for_date(
    db: Session,
    owner_user_id: int,
    measured_on: date,
) -> BodyMeasurement | None:
    return (
        db.query(BodyMeasurement)
        .options(
            selectinload(BodyMeasurement.custom_values).joinedload(
                BodyMeasurementCustomValue.definition
            )
        )
        .filter(
            BodyMeasurement.user_id == owner_user_id,
            BodyMeasurement.measured_on == measured_on,
        )
        .first()
    )


def _custom_changes(
    db: Session,
    *,
    owner_user_id: int,
    existing: BodyMeasurement | None,
    changes: dict[str, object],
) -> dict[int, float | None]:
    raw_values = changes.get("custom_values")
    if raw_values is None:
        return {}
    if not isinstance(raw_values, list):
        raise MeasurementError("Некорректные пользовательские показатели")

    requested: dict[int, float | None] = {}
    for raw_value in raw_values:
        if not isinstance(raw_value, dict):
            raise MeasurementError("Некорректный пользовательский показатель")
        definition_id = raw_value.get("definition_id")
        if not isinstance(definition_id, int) or definition_id < 1:
            raise MeasurementError("Некорректный идентификатор пользовательского показателя")
        if definition_id in requested:
            raise MeasurementError("Показатель замера указан несколько раз")
        value = raw_value.get("value")
        if value is not None and (not isinstance(value, (int, float)) or value <= 0 or value > 300):
            raise MeasurementError(
                "Значение пользовательского показателя должно быть от 0 до 300 см"
            )
        requested[definition_id] = float(value) if value is not None else None

    definitions = (
        db.query(BodyMeasurementDefinition)
        .filter(
            BodyMeasurementDefinition.user_id == owner_user_id,
            BodyMeasurementDefinition.id.in_(requested),
        )
        .all()
    )
    definitions_by_id = {definition.id: definition for definition in definitions}
    existing_values = {
        value.definition_id: value
        for value in (existing.custom_values if existing is not None else [])
    }
    for definition_id, value in requested.items():
        definition = definitions_by_id.get(definition_id)
        if definition is None:
            raise MeasurementError("Показатель замера недоступен")
        if (
            value is not None
            and definition.archived_at is not None
            and definition_id not in existing_values
        ):
            raise MeasurementError("Восстановите архивный показатель перед новым замером")
    return requested


def _upsert_measurement(
    db: Session,
    *,
    owner_user_id: int,
    measured_on: date,
    changes: dict[str, object],
) -> BodyMeasurement:
    if not changes:
        existing = _load_measurement_for_date(db, owner_user_id, measured_on)
        if existing is not None:
            return existing
        row = BodyMeasurement(user_id=owner_user_id, measured_on=measured_on)
        db.add(row)
        db.flush()
        return row
    values = {"user_id": owner_user_id, "measured_on": measured_on, **changes}
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        postgresql_statement = postgresql_insert(BodyMeasurement).values(**values)
        postgresql_statement = postgresql_statement.on_conflict_do_update(
            constraint="uq_body_measurement_user_date",
            set_={field: getattr(postgresql_statement.excluded, field) for field in changes},
        )
        measurement_id = db.execute(postgresql_statement.returning(BodyMeasurement.id)).scalar_one()
    elif dialect == "sqlite":
        sqlite_statement = sqlite_insert(BodyMeasurement).values(**values)
        sqlite_statement = sqlite_statement.on_conflict_do_update(
            index_elements=[BodyMeasurement.user_id, BodyMeasurement.measured_on],
            set_={field: getattr(sqlite_statement.excluded, field) for field in changes},
        )
        measurement_id = db.execute(sqlite_statement.returning(BodyMeasurement.id)).scalar_one()
    else:
        raise RuntimeError(f"Unsupported measurement upsert dialect: {dialect}")

    return db.execute(
        select(BodyMeasurement)
        .where(BodyMeasurement.id == measurement_id)
        .execution_options(populate_existing=True)
    ).scalar_one()


def save_measurement(
    db: Session,
    owner: User,
    payload: BodyMeasurementSave,
    *,
    changed_by: User,
) -> BodyMeasurement:
    owner_today = today_for_user(owner)
    measured_on = payload.measured_on or owner_today
    if measured_on > owner_today:
        raise MeasurementError("Дата замера не может быть в будущем")
    changes = _measurement_changes(payload)

    try:
        _lock_owner_measurements(db, owner.id)
        existing = _load_measurement_for_date(db, owner.id, measured_on)
        custom_requested = "custom_values" in changes
        custom_changes = _custom_changes(
            db,
            owner_user_id=owner.id,
            existing=existing,
            changes=changes,
        )
        canonical_changes = {
            field: changes[field] for field in MEASUREMENT_FIELDS if field in changes
        }
        effective_canonical = {
            field: canonical_changes[field]
            if field in canonical_changes
            else getattr(existing, field)
            if existing is not None
            else None
            for field in MEASUREMENT_FIELDS
        }
        effective_custom = {
            value.definition_id: value.value
            for value in (existing.custom_values if existing is not None else [])
        }
        effective_custom.update(custom_changes)
        if not any(value is not None for value in effective_canonical.values()) and not any(
            value is not None for value in effective_custom.values()
        ):
            raise MeasurementError("Укажите хотя бы один числовой замер")
        row = _upsert_measurement(
            db,
            owner_user_id=owner.id,
            measured_on=measured_on,
            changes=canonical_changes | ({"note": changes["note"]} if "note" in changes else {}),
        )
        for definition_id, value in custom_changes.items():
            if value is None:
                db.query(BodyMeasurementCustomValue).filter(
                    BodyMeasurementCustomValue.measurement_id == row.id,
                    BodyMeasurementCustomValue.definition_id == definition_id,
                ).delete(synchronize_session=False)
            else:
                current_value = (
                    db.query(BodyMeasurementCustomValue)
                    .filter(
                        BodyMeasurementCustomValue.measurement_id == row.id,
                        BodyMeasurementCustomValue.definition_id == definition_id,
                    )
                    .first()
                )
                if current_value is None:
                    db.add(
                        BodyMeasurementCustomValue(
                            measurement_id=row.id,
                            definition_id=definition_id,
                            value=value,
                        )
                    )
                else:
                    current_value.value = value
        db.flush()
        reconcile_current_measurement_state(db, owner, changed_by=changed_by)
        if changed_by.id != owner.id:
            record_audit_event(
                db,
                actor_user_id=changed_by.id,
                target_user_id=owner.id,
                action="coach.measurement_saved",
                resource_type="body_measurement",
                resource_id=row.id,
                details={
                    "measured_on": measured_on.isoformat(),
                    "fields": sorted(
                        [*canonical_changes, "custom_values"]
                        if custom_requested
                        else canonical_changes
                    ),
                },
            )
        db.commit()
    except NutritionError as exc:
        db.rollback()
        raise MeasurementError(str(exc)) from exc
    return (
        db.query(BodyMeasurement)
        .options(
            selectinload(BodyMeasurement.custom_values).joinedload(
                BodyMeasurementCustomValue.definition
            )
        )
        .filter(BodyMeasurement.id == row.id)
        .one()
    )


def delete_measurement(
    db: Session,
    owner: User,
    measurement_id: int,
    *,
    changed_by: User,
) -> None:
    _lock_owner_measurements(db, owner.id)
    row = (
        db.query(BodyMeasurement)
        .filter(
            BodyMeasurement.id == measurement_id,
            BodyMeasurement.user_id == owner.id,
        )
        .first()
    )
    if row is None:
        raise MeasurementNotFoundError("Запись дневника не найдена")

    measured_on = row.measured_on
    try:
        db.delete(row)
        reconcile_current_measurement_state(db, owner, changed_by=changed_by)
        if changed_by.id != owner.id:
            record_audit_event(
                db,
                actor_user_id=changed_by.id,
                target_user_id=owner.id,
                action="coach.measurement_deleted",
                resource_type="body_measurement",
                resource_id=measurement_id,
                details={"measured_on": measured_on.isoformat()},
            )
        db.commit()
    except NutritionError as exc:
        db.rollback()
        raise MeasurementError(str(exc)) from exc
