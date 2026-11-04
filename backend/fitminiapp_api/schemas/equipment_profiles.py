from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

EquipmentProfileIdentifier = Literal[
    "bodyweight",
    "dumbbell",
    "barbell",
    "bench",
    "cable",
    "machine",
    "kettlebell",
    "cardio",
    "other",
    "rack",
    "pullup_bar",
    "dip_bars",
]


class EquipmentProfileInput(BaseModel):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=64)
    equipment_ids: list[EquipmentProfileIdentifier] = Field(default_factory=list, max_length=12)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("equipment_ids")
    @classmethod
    def unique_equipment(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("equipment_ids must be unique")
        return value


class EquipmentProfile(EquipmentProfileInput):
    id: UUID


class EquipmentProfilesUpdate(BaseModel):
    revision: int = Field(ge=0)
    active_profile_id: UUID | None = None
    profiles: list[EquipmentProfileInput] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_profiles(self):
        ids = [profile.id for profile in self.profiles if profile.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("profile ids must be unique")
        if self.active_profile_id is not None and self.active_profile_id not in ids:
            raise ValueError("active profile must be included in profiles")
        return self


class EquipmentProfilesResponse(BaseModel):
    revision: int
    active_profile_id: UUID | None = None
    profiles: list[EquipmentProfile] = Field(default_factory=list)
