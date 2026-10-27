from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OnboardingStepKey = Literal[
    "invite",
    "questionnaire",
    "goals",
    "equipment",
    "restrictions",
    "measurements",
    "program",
    "first_check_in",
    "agenda",
]


class OnboardingTemplateFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[OnboardingStepKey] = Field(min_length=1, max_length=9)
    program_template_id: int | None = Field(default=None, gt=0)
    check_in_template_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_steps(self) -> OnboardingTemplateFields:
        if len(self.steps) != len(set(self.steps)):
            raise ValueError("Этапы подключения не должны повторяться")
        if ("program" in self.steps) != (self.program_template_id is not None):
            raise ValueError("Для этапа программы выберите существующую программу")
        if ("first_check_in" in self.steps) != (self.check_in_template_id is not None):
            raise ValueError("Для первой проверки выберите существующий шаблон")
        return self


class OnboardingTemplateCreate(OnboardingTemplateFields):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)


class OnboardingTemplateVersionCreate(OnboardingTemplateFields):
    pass


class OnboardingTemplateAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(gt=0)
    version: int | None = Field(default=None, ge=1)


class CommunicationTemplateFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=128)
    body: str = Field(min_length=1, max_length=4000)


class CommunicationTemplateCreate(CommunicationTemplateFields):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)


class CommunicationTemplateVersionCreate(CommunicationTemplateFields):
    pass


class WorkflowAssignmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    client_id: int = Field(gt=0)
    client_name: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    status: Literal["assigned", "completed", "revoked"]
    created_at: datetime


class OnboardingTemplateVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    version: int = Field(ge=1)
    steps: list[OnboardingStepKey] = Field(min_length=1, max_length=9)
    program_template_id: int | None = Field(default=None, gt=0)
    check_in_template_id: int | None = Field(default=None, gt=0)
    created_at: datetime


class OnboardingTemplateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    description: str | None = None
    is_active: bool
    current_version: OnboardingTemplateVersionResponse | None = None
    assignments: list[WorkflowAssignmentResponse] = Field(default_factory=list, max_length=500)
    created_at: datetime
    updated_at: datetime


class OnboardingTemplateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OnboardingTemplateResponse] = Field(default_factory=list, max_length=100)


class CommunicationTemplateVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    version: int = Field(ge=1)
    subject: str
    body: str
    created_at: datetime


class CommunicationDraftSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    client_id: int = Field(gt=0)
    client_name: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    status: Literal["draft", "confirmed"]
    updated_at: datetime
    confirmed_at: datetime | None = None


class CommunicationTemplateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    description: str | None = None
    is_active: bool
    current_version: CommunicationTemplateVersionResponse | None = None
    drafts: list[CommunicationDraftSummary] = Field(default_factory=list, max_length=500)
    created_at: datetime
    updated_at: datetime


class CommunicationTemplateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CommunicationTemplateResponse] = Field(default_factory=list, max_length=100)


class CommunicationDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(gt=0)
    version: int | None = Field(default=None, ge=1)
    subject: str | None = Field(default=None, min_length=1, max_length=128)
    body: str | None = Field(default=None, min_length=1, max_length=4000)


class CommunicationDraftUpdate(CommunicationTemplateFields):
    pass


class CommunicationDraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    template_id: int
    client_id: int = Field(gt=0)
    client_name: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    subject: str
    body: str
    status: Literal["draft", "confirmed"]
    notification_id: int | None = None
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None = None


__all__ = [
    "CommunicationDraftCreate",
    "CommunicationDraftResponse",
    "CommunicationDraftSummary",
    "CommunicationDraftUpdate",
    "CommunicationTemplateCreate",
    "CommunicationTemplateFields",
    "CommunicationTemplateListResponse",
    "CommunicationTemplateResponse",
    "CommunicationTemplateVersionCreate",
    "CommunicationTemplateVersionResponse",
    "OnboardingStepKey",
    "OnboardingTemplateAssignmentCreate",
    "OnboardingTemplateCreate",
    "OnboardingTemplateFields",
    "OnboardingTemplateListResponse",
    "OnboardingTemplateResponse",
    "OnboardingTemplateVersionCreate",
    "OnboardingTemplateVersionResponse",
    "WorkflowAssignmentResponse",
]
