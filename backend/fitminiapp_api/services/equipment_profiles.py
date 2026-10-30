from uuid import uuid4

from sqlalchemy.orm import Session

from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.schemas.equipment_profiles import EquipmentProfilesUpdate


class EquipmentProfilesConflict(ValueError):
    pass


def equipment_profiles_state(profile: UserProfile | None) -> dict:
    if profile is None:
        return {"revision": 0, "active_profile_id": None, "profiles": []}
    return {
        "revision": profile.equipment_profiles_revision,
        "active_profile_id": profile.active_equipment_profile_id,
        "profiles": list(profile.equipment_profiles or []),
    }


def active_equipment_profile(profile: UserProfile | None) -> dict | None:
    state = equipment_profiles_state(profile)
    return next(
        (item for item in state["profiles"] if item["id"] == state["active_profile_id"]),
        None,
    )


def load_active_equipment_profile(db: Session, user_id: int) -> tuple[dict | None, int]:
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.user_id == user_id)
        .populate_existing()
        .one_or_none()
    )
    return active_equipment_profile(profile), equipment_profiles_state(profile)["revision"]


def save_equipment_profiles(db: Session, user: User, payload: EquipmentProfilesUpdate) -> dict:
    # Serialize profile creation, changes and adaptation apply on the same owner row.
    db.query(User).filter(User.id == user.id).with_for_update().one()
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.user_id == user.id)
        .populate_existing()
        .one_or_none()
    )
    if profile is None:
        profile = UserProfile(user_id=user.id, equipment_profiles=[], equipment_profiles_revision=0)
        db.add(profile)
        db.flush()
    if profile.equipment_profiles_revision != payload.revision:
        raise EquipmentProfilesConflict("Профили оборудования изменились. Обновите их и повторите.")

    existing_ids = {item["id"] for item in profile.equipment_profiles or []}
    if any(item.id is not None and str(item.id) not in existing_ids for item in payload.profiles):
        raise ValueError("Профиль оборудования не найден")
    profiles = [
        {
            "id": str(item.id or uuid4()),
            "name": item.name,
            "equipment_ids": sorted(item.equipment_ids),
        }
        for item in payload.profiles
    ]
    active_id = str(payload.active_profile_id) if payload.active_profile_id else None
    if (
        profiles != (profile.equipment_profiles or [])
        or active_id != profile.active_equipment_profile_id
    ):
        profile.equipment_profiles = profiles
        profile.active_equipment_profile_id = active_id
        profile.equipment_profiles_revision += 1
    db.commit()
    return equipment_profiles_state(profile)
