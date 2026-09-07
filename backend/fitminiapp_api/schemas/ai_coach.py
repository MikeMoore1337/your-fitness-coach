"""HTTP schemas for the authenticated, generic-only AI Coach endpoint."""

from __future__ import annotations

import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fitminiapp_api.ai_coach.contracts import AiCoachJob, AiCoachResponse


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


__all__ = ["AiCoachGenerateRequest", "AiCoachResponse"]
