from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import get_user_timezone_name, now_msk_naive
from fitminiapp_api.models.account import AccountDataExport
from fitminiapp_api.models.nutrition_notes import NutritionMealNote, NutritionNotesConsent
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_notes import NutritionMealNoteUpdate

CONSENT_VERSION = "1"


def lock_user(db: Session, user: User) -> None:
    db.query(User.id).filter(User.id == user.id).with_for_update().one()


def get_consent(db: Session, user: User) -> NutritionNotesConsent | None:
    return db.query(NutritionNotesConsent).filter_by(user_id=user.id).one_or_none()


def require_enabled(db: Session, user: User) -> None:
    consent = get_consent(db, user)
    if consent is None or consent.status != "enabled":
        raise HTTPException(status_code=403, detail="Личные отметки не включены")


def invalidate_export(db: Session, user: User) -> None:
    export = db.query(AccountDataExport).filter_by(user_id=user.id).with_for_update().one_or_none()
    if export:
        export.status = "expired"
        export.archive_bytes = None
        export.content_size_bytes = None
        export.download_token_hash = None
        export.download_token_expires_at = None


def set_consent(db: Session, user: User, action: str) -> str:
    lock_user(db, user)
    consent = get_consent(db, user)
    if action == "enable":
        if consent is not None and consent.status == "recovery_hold":
            raise HTTPException(
                status_code=409, detail="Отметки временно недоступны после восстановления"
            )
        if consent is None:
            consent = NutritionNotesConsent(
                user_id=user.id, status="enabled", consent_version=CONSENT_VERSION
            )
            db.add(consent)
        else:
            if consent.status == "revoked":
                consent.granted_at = now_msk_naive()
                consent.revoked_at = None
                consent.consent_version = CONSENT_VERSION
            consent.status = "enabled"
    elif action == "disable":
        if consent is not None and consent.status == "enabled":
            consent.status = "disabled"
    elif action == "revoke":
        if consent is not None:
            consent.status = "revoked"
            consent.revoked_at = now_msk_naive()
        db.query(NutritionMealNote).filter_by(user_id=user.id).delete(synchronize_session=False)
        invalidate_export(db, user)
    db.commit()
    return consent.status if consent else "revoked"


def get_notes(db: Session, user: User, local_date: date) -> list[NutritionMealNote]:
    lock_user(db, user)
    require_enabled(db, user)
    return db.query(NutritionMealNote).filter_by(user_id=user.id, local_date=local_date).all()


def save_note(
    db: Session, user: User, local_date: date, meal_type: str, payload: NutritionMealNoteUpdate
) -> NutritionMealNote | None:
    lock_user(db, user)
    require_enabled(db, user)
    row = (
        db.query(NutritionMealNote)
        .filter_by(user_id=user.id, local_date=local_date, meal_type=meal_type)
        .one_or_none()
    )
    values = {
        key: getattr(row, key) if row else None
        for key in ("hunger_before", "fullness_after", "energy", "note")
    }
    values.update(payload.model_dump(exclude_unset=True))
    values["note"] = values["note"].strip() or None if values["note"] is not None else None
    if not any(value is not None for value in values.values()):
        if row is not None:
            raise HTTPException(
                status_code=422, detail="Чтобы удалить отметку, используйте кнопку удаления"
            )
        db.commit()
        return None
    if row is None:
        row = NutritionMealNote(
            user_id=user.id,
            local_date=local_date,
            meal_type=meal_type,
            timezone_at_entry=get_user_timezone_name(user),
            **values,
        )
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
        invalidate_export(db, user)
    db.commit()
    db.refresh(row)
    return row


def delete_note(db: Session, user: User, local_date: date, meal_type: str) -> None:
    lock_user(db, user)
    row = (
        db.query(NutritionMealNote)
        .filter_by(user_id=user.id, local_date=local_date, meal_type=meal_type)
        .one_or_none()
    )
    if row is not None:
        db.delete(row)
        invalidate_export(db, user)
    db.commit()
