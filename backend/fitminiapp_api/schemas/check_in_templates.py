from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CheckInFieldKey = Literal[
    "recovery",
    "hunger",
    "training_load",
    "adherence_difficulty",
]
CheckInCadence = Literal["weekly", "biweekly", "monthly"]


class CheckInFieldDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: CheckInFieldKey
    required: bool = True


class CheckInTemplateFieldsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[CheckInFieldDefinition] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_unique_fields(self) -> CheckInTemplateFieldsRequest:
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Поля проверки не должны повторяться")
        return self


class CheckInTemplateCreate(CheckInTemplateFieldsRequest):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    cadence: CheckInCadence


class CheckInTemplateVersionCreate(CheckInTemplateFieldsRequest):
    pass


class CheckInTemplateStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class CheckInTemplateAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(gt=0)
    version: int | None = Field(default=None, ge=1)
    due_on: date | None = None


class CheckInFieldCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: CheckInFieldKey
    label: str
    value_type: Literal["score"]
    min_value: int = Field(ge=1, le=5)
    max_value: int = Field(ge=1, le=5)


class CheckInFieldResponseDefinition(CheckInFieldCatalogItem):
    required: bool


class CheckInTemplateVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    version: int = Field(ge=1)
    fields: list[CheckInFieldResponseDefinition] = Field(min_length=1, max_length=4)
    created_at: datetime


class CheckInTemplateAssignmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    client_id: int = Field(gt=0)
    client_name: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    status: Literal["active", "revoked"]
    next_due_on: date
    last_response_at: datetime | None = None


class CheckInTemplateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    description: str | None = None
    cadence: CheckInCadence
    is_active: bool
    current_version: CheckInTemplateVersionResponse | None = None
    assignments: list[CheckInTemplateAssignmentResponse] = Field(
        default_factory=list, max_length=500
    )
    created_at: datetime
    updated_at: datetime


class CheckInTemplateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CheckInTemplateResponse] = Field(default_factory=list, max_length=100)
    field_catalog: list[CheckInFieldCatalogItem] = Field(min_length=1, max_length=4)


class AssignedCheckInTemplateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: int
    template_id: int
    name: str
    description: str | None = None
    cadence: CheckInCadence
    version: int = Field(ge=1)
    fields: list[CheckInFieldResponseDefinition] = Field(min_length=1, max_length=4)
    next_due_on: date
    status: Literal["active"]


class AssignedCheckInTemplateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AssignedCheckInTemplateResponse] = Field(default_factory=list, max_length=100)


class CheckInTemplateResponseSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, int] = Field(default_factory=dict, max_length=4)


class CheckInTemplateResponseItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    assignment_id: int
    template_id: int
    template_name: str
    version: int = Field(ge=1)
    due_on: date
    values: dict[str, int]
    submitted_at: datetime
    replayed: bool = False


class CheckInTemplateResponseHistoryItem(CheckInTemplateResponseItem):
    client_id: int = Field(gt=0)
    client_name: str = Field(min_length=1, max_length=128)


class CheckInTemplateResponseHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CheckInTemplateResponseHistoryItem] = Field(default_factory=list, max_length=100)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


__all__ = [
    "AssignedCheckInTemplateListResponse",
    "AssignedCheckInTemplateResponse",
    "CheckInCadence",
    "CheckInFieldCatalogItem",
    "CheckInFieldDefinition",
    "CheckInFieldKey",
    "CheckInFieldResponseDefinition",
    "CheckInTemplateAssignmentCreate",
    "CheckInTemplateAssignmentResponse",
    "CheckInTemplateCreate",
    "CheckInTemplateFieldsRequest",
    "CheckInTemplateListResponse",
    "CheckInTemplateResponse",
    "CheckInTemplateResponseHistory",
    "CheckInTemplateResponseHistoryItem",
    "CheckInTemplateResponseItem",
    "CheckInTemplateResponseSubmit",
    "CheckInTemplateStateUpdate",
    "CheckInTemplateVersionCreate",
    "CheckInTemplateVersionResponse",
]
