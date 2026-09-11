"""HTTP schemas for the authenticated, generic-only AI Coach endpoint."""

from __future__ import annotations

import unicodedata
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fitminiapp_api.ai_coach.contracts import (
    AiCoachJob,
    AiCoachPersonalTool,
    AiCoachResponse,
)


class AiCoachGenerateRequest(BaseModel):
    """A bounded intent plus a server-known public context id.

    The model intentionally has no provider, model, system prompt, URL, account
    data, file or arbitrary context field.
    """

    model_config = ConfigDict(extra="forbid")

    job: AiCoachJob
    context_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:/-]+$",
    )
    message: str = Field(..., min_length=1, max_length=320)

    @field_validator("context_id")
    @classmethod
    def validate_context_id(cls, value: str) -> str:
        normalized = value.strip()
        if "://" in normalized or "?" in normalized or "#" in normalized:
            raise ValueError("context_id must be a server-known public id, not a URL")
        return normalized

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).strip()
        if not normalized or any(ord(char) < 0x20 and char not in "\t" for char in normalized):
            raise ValueError("message must be a single safe text value")
        return normalized


class AiCoachPersonalGenerateRequest(BaseModel):
    """A server-selected read-only tool and a bounded report period."""

    model_config = ConfigDict(extra="forbid")

    tool: AiCoachPersonalTool
    period_days: Literal[7, 30, 90] = 30
    period: Literal["days_7", "days_30", "days_90", "custom"] | None = None
    date_from: date | None = None
    date_to: date | None = None
    message: str = Field(..., min_length=1, max_length=320)

    @model_validator(mode="after")
    def validate_period(self) -> AiCoachPersonalGenerateRequest:
        if self.period is None:
            if self.date_from is not None or self.date_to is not None:
                raise ValueError("Произвольные даты требуют period=custom")
            return self
        if self.period == "custom":
            if self.date_from is None or self.date_to is None:
                raise ValueError("Для произвольного периода укажите обе даты")
            return self
        if self.date_from is not None or self.date_to is not None:
            raise ValueError("Даты можно передавать только для period=custom")
        return self

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).strip()
        if not normalized or any(ord(char) < 0x20 and char not in "\t" for char in normalized):
            raise ValueError("message must be a single safe text value")
        return normalized


class AiCoachConsentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class AiCoachConsentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["granted", "revoked"]
    scope: str
    consent_version: str
    categories: tuple[str, ...]
    purpose: str
    provider_name: str
    provider_policy_revision: str
    retention_notice: str
    consent_source: str
    granted_at: datetime | None = None
    revoked_at: datetime | None = None


class AiCoachMemoryConsentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["enabled", "paused", "revoked"]


class AiCoachMemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "preferred_explanation_style",
        "ai_interaction_preferences",
        "stable_non_medical_preferences",
        "explicit_ai_context",
    ]
    value: str = Field(..., min_length=1, max_length=240)
    confirmation: Literal[True]


class AiCoachMemoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(..., min_length=1, max_length=240)
    confirmation: Literal[True]


class AiCoachMemoryItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    category: str
    category_label: str
    value: str
    source_kind: Literal["explicit_user", "confirmed_candidate"]
    confidence: Literal["explicit", "confirmed"]
    status: Literal["active", "superseded", "conflicted", "deleted"]
    version: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None


class AiCoachMemoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["enabled", "paused", "revoked"]
    scope: str
    consent_version: str
    categories: tuple[str, ...]
    category_labels: dict[str, str]
    purpose: str
    retention_notice: str
    max_items: int
    consent_source: str
    granted_at: datetime | None = None
    paused_at: datetime | None = None
    revoked_at: datetime | None = None
    items: tuple[AiCoachMemoryItemResponse, ...] = ()


class AiCoachMemoryClearResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted_count: int


class AiCoachStatusResponse(BaseModel):
    """Safe server-authoritative state for the internal beta UI."""

    model_config = ConfigDict(extra="forbid")

    ui_enabled: bool
    generic_available: bool
    personal_available: bool


__all__ = [
    "AiCoachConsentResponse",
    "AiCoachConsentUpdateRequest",
    "AiCoachGenerateRequest",
    "AiCoachMemoryClearResponse",
    "AiCoachMemoryConsentUpdateRequest",
    "AiCoachMemoryCreateRequest",
    "AiCoachMemoryItemResponse",
    "AiCoachMemoryResponse",
    "AiCoachMemoryUpdateRequest",
    "AiCoachPersonalGenerateRequest",
    "AiCoachResponse",
    "AiCoachStatusResponse",
]
