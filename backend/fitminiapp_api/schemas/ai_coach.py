"""HTTP schemas for the authenticated, generic-only AI Coach endpoint."""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    """A server-selected read-only tool and one of three bounded periods."""

    model_config = ConfigDict(extra="forbid")

    tool: AiCoachPersonalTool
    period_days: Literal[7, 30, 90] = 30
    message: str = Field(..., min_length=1, max_length=320)

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


__all__ = [
    "AiCoachConsentResponse",
    "AiCoachConsentUpdateRequest",
    "AiCoachGenerateRequest",
    "AiCoachPersonalGenerateRequest",
    "AiCoachResponse",
]
