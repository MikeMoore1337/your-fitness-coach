"""Provider-neutral contracts for advisory program-import assistance.

The import pipeline owns parsing, validation, matching and canonical writes.  This
module only describes a bounded proposal port.  A provider implementation, when
eventually approved, must return proposals linked to source evidence; it never
gets a write-capable object or permission to resolve an exercise automatically.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROGRAM_IMPORT_AI_CONTRACT_VERSION = "program-import-ai-v1"
PROGRAM_IMPORT_AI_PROMPT_VERSION = "program-import-ai-prompt-v1"

ProgramImportAiStatus = Literal[
    "disabled",
    "policy_blocked",
    "unavailable",
    "no_change",
    "proposed",
    "invalid_output",
]
ProgramImportAiField = Literal[
    "program_title",
    "goal",
    "level",
    "day_number",
    "day_title",
    "prescribed_sets",
    "prescribed_reps",
    "prescribed_duration_minutes",
    "rest_seconds",
    "notes",
    "exercise_mapping",
]


def _normalize_text(value: str, *, max_length: int) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized or len(normalized) > max_length:
        raise ValueError("AI import text is outside the allowed bounds")
    if any(ord(character) < 0x20 and character not in "\t\n\r" for character in normalized):
        raise ValueError("AI import text contains a control character")
    return normalized


class ProgramImportAiSourceSpan(BaseModel):
    """A source fragment selected by the deterministic parser."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^source:[A-Za-z0-9_.:/-]+$",
    )
    location: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=512)

    _safe_text = field_validator("location", "text")(
        lambda value: _normalize_text(value, max_length=512)
    )


class ProgramImportAiRowContext(BaseModel):
    """Only unresolved normalized fields and bounded candidates cross the port."""

    model_config = ConfigDict(extra="forbid")

    row_number: int = Field(ge=3, le=50_002)
    unresolved_fields: tuple[str, ...] = Field(default=(), max_length=12)
    fields: dict[str, str] = Field(default_factory=dict, max_length=16)
    candidate_exercise_ids: tuple[int, ...] = Field(default=(), max_length=5)

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, item in value.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key):
                raise ValueError("AI import row field has an invalid name")
            normalized[key] = _normalize_text(item, max_length=512)
        return normalized


class ProgramImportAiRequest(BaseModel):
    """Provider-neutral request with no raw archive, user id or canonical model."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["program-import-ai-v1"] = "program-import-ai-v1"
    prompt_version: Literal["program-import-ai-prompt-v1"] = "program-import-ai-prompt-v1"
    source_format: Literal["csv", "xlsx", "txt", "docx"]
    data_class: Literal["user_uploaded_program_document"] = "user_uploaded_program_document"
    sensitivity: Literal["personalized"] = "personalized"
    locale: Literal["ru", "en", "mixed"] = "mixed"
    source_spans: tuple[ProgramImportAiSourceSpan, ...] = Field(default=(), max_length=32)
    rows: tuple[ProgramImportAiRowContext, ...] = Field(default=(), max_length=500)


class ProgramImportAiProposal(BaseModel):
    """One source-grounded suggestion; exercise mappings remain manual."""

    model_config = ConfigDict(extra="forbid")

    row_number: int = Field(ge=3, le=50_002)
    field: ProgramImportAiField
    value: str = Field(min_length=1, max_length=512)
    evidence_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^source:[A-Za-z0-9_.:/-]+$",
    )
    rationale: str = Field(default="", max_length=240)

    _safe_value = field_validator("value", "rationale")(
        lambda value: _normalize_text(value, max_length=512)
    )


class ProgramImportAiCandidateRerank(BaseModel):
    """An advisory candidate order.  It cannot change match_status or resolution."""

    model_config = ConfigDict(extra="forbid")

    row_number: int = Field(ge=3, le=50_002)
    candidate_ids: tuple[int, ...] = Field(min_length=1, max_length=5)
    rationale: str = Field(default="", max_length=240)

    _safe_rationale = field_validator("rationale")(
        lambda value: _normalize_text(value, max_length=240) if value else ""
    )


class ProgramImportAiResponse(BaseModel):
    """Strict output accepted by the import service."""

    model_config = ConfigDict(extra="forbid")

    status: ProgramImportAiStatus
    attempts: int = Field(default=0, ge=0, le=1)
    proposals: tuple[ProgramImportAiProposal, ...] = Field(default=(), max_length=100)
    candidate_reranks: tuple[ProgramImportAiCandidateRerank, ...] = Field(
        default=(), max_length=500
    )

    @model_validator(mode="after")
    def validate_status_payload(self) -> ProgramImportAiResponse:
        if self.status != "proposed" and (self.proposals or self.candidate_reranks):
            raise ValueError("AI proposals require the proposed response status")
        return self


class ProgramImportAiPort(Protocol):
    """Synchronous provider-neutral port used after deterministic extraction."""

    def propose(self, request: ProgramImportAiRequest) -> ProgramImportAiResponse: ...


class DisabledProgramImportAiPort:
    """Fail-closed port used by production until a separate provider decision."""

    def __init__(self, status: Literal["disabled", "policy_blocked", "unavailable"] = "disabled"):
        self.status = status

    def propose(self, request: ProgramImportAiRequest) -> ProgramImportAiResponse:
        del request
        return ProgramImportAiResponse(status=self.status, attempts=0)
