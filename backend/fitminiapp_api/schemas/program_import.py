from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fitminiapp_api.schemas.program import (
    ExercisePrescriptionPlan,
    ProgramCoachingRule,
    ProgramTargetUserResponse,
    ProgramTemplateResponse,
)

ImportFormat = Literal["csv", "xlsx", "txt", "docx"]
ImportStatus = Literal["pending", "confirmed", "cancelled", "expired"]
ImportIssueSeverity = Literal["blocking", "warning"]
ImportMatchStatus = Literal["matched", "needs_resolution", "invalid"]
ImportMatchType = Literal["id", "slug", "title", "alias", "transliteration", "manual"]
ImportMetricType = Literal["strength", "cardio"]
ImportGoal = Literal["muscle_gain", "fat_loss", "maintenance", "recomposition"]
ImportLevel = Literal["beginner", "intermediate", "advanced"]
ImportAiField = Literal[
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


class ProgramImportIssue(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    severity: ImportIssueSeverity
    message: str = Field(min_length=1, max_length=500)
    location: str | None = Field(default=None, max_length=128)
    field: str | None = Field(default=None, max_length=64)
    source_sheet: str | None = Field(default=None, max_length=31)
    source_row: int | None = Field(default=None, ge=1)
    source_cell: str | None = Field(default=None, max_length=32)


class ProgramImportProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provenance_type: Literal["CUSTOM", "SOURCE_ADAPTATION"] = "CUSTOM"
    source_name: str | None = Field(default=None, max_length=128)
    creator: str | None = Field(default=None, max_length=128)
    organization: str | None = Field(default=None, max_length=128)
    source_reference: str | None = Field(default=None, max_length=500)
    source_version: str | None = Field(default=None, max_length=64)
    source_date: date | None = None
    adaptation_notes: str | None = Field(default=None, max_length=1_000)

    @field_validator("source_reference")
    @classmethod
    def validate_source_reference(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else value
        if (
            normalized is not None
            and "://" in normalized
            and not normalized.casefold().startswith("https://")
        ):
            raise ValueError("source references must use HTTPS")
        return normalized


class ProgramImportBlock(BaseModel):
    block_number: int = Field(ge=1, le=24)
    title: str = Field(min_length=1, max_length=128)
    week_start: int = Field(ge=1, le=24)
    week_end: int = Field(ge=1, le=24)
    is_deload: bool = False

    @model_validator(mode="after")
    def validate_weeks(self):
        if self.week_end < self.week_start:
            raise ValueError("week_end must not precede week_start")
        return self


class ProgramImportTarget(BaseModel):
    program_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=128)
    owner_name: str | None = Field(default=None, max_length=128)
    duration_weeks: int = Field(ge=1, le=24)
    current_revision_number: int = Field(ge=0)
    status: Literal["scheduled", "active"]
    day_numbers: list[int] = Field(min_length=1, max_length=8)


class ProgramImportCandidate(BaseModel):
    exercise_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=128)
    metric_type: ImportMetricType
    match_type: ImportMatchType


class ProgramImportAiProposal(BaseModel):
    field: ImportAiField
    value: str = Field(min_length=1, max_length=512)
    evidence_id: str = Field(min_length=1, max_length=64)
    source_location: str = Field(min_length=1, max_length=128)
    source_text: str = Field(min_length=1, max_length=512)
    rationale: str = Field(default="", max_length=240)
    applied: bool = False


class ProgramImportRow(BaseModel):
    row_number: int = Field(ge=3)
    source_sheet: str | None = Field(default=None, max_length=31)
    source_range: str | None = Field(default=None, max_length=64)
    source_cells: dict[str, str] = Field(default_factory=dict, max_length=24)
    week_number: int | None = Field(default=None, ge=1, le=24)
    day_number: int | None = Field(default=None, ge=1, le=8)
    day_title: str | None = Field(default=None, max_length=128)
    exercise_name: str | None = Field(default=None, max_length=512)
    exercise_id: int | None = Field(default=None, ge=1)
    exercise_slug: str | None = Field(default=None, max_length=128)
    metric_type: ImportMetricType | None = None
    prescribed_sets: int | None = Field(default=None, ge=1, le=10)
    prescribed_reps: str | None = Field(default=None, max_length=32)
    prescribed_duration_minutes: int | None = Field(default=None, ge=1, le=600)
    rest_seconds: int | None = Field(default=None, ge=0, le=600)
    notes: str | None = Field(default=None, max_length=2_000)
    source_auxiliary: str | None = Field(default=None, max_length=512)
    superset_group: int | None = Field(default=None, ge=1)
    superset_order: int | None = Field(default=None, ge=1, le=2)
    prescription: ExercisePrescriptionPlan | None = None
    block_number: int | None = Field(default=None, ge=1, le=24)
    block_title: str | None = Field(default=None, max_length=128)
    block_is_deload: bool = False
    coaching_rule: ProgramCoachingRule | None = None
    resolved_exercise_id: int | None = Field(default=None, ge=1)
    resolved_exercise_title: str | None = Field(default=None, max_length=128)
    match_status: ImportMatchStatus
    match_type: ImportMatchType | None = None
    candidates: list[ProgramImportCandidate] = Field(default_factory=list, max_length=5)
    ai_proposals: list[ProgramImportAiProposal] = Field(default_factory=list, max_length=20)
    ai_rerank_reason: str | None = Field(default=None, max_length=240)
    issues: list[ProgramImportIssue] = Field(default_factory=list, max_length=20)


class ProgramImportSummary(BaseModel):
    row_count: int = Field(ge=0)
    cell_count: int = Field(ge=0)
    matched_row_count: int = Field(ge=0)
    unresolved_row_count: int = Field(ge=0)
    blocking_issue_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)


class ProgramImportAiInfo(BaseModel):
    contract_version: str = Field(min_length=1, max_length=64)
    prompt_version: str = Field(min_length=1, max_length=64)
    status: Literal[
        "disabled",
        "policy_blocked",
        "unavailable",
        "no_change",
        "proposed",
        "invalid_output",
        "not_needed",
    ]
    attempts: int = Field(ge=0, le=1)
    proposal_count: int = Field(ge=0)
    candidate_rerank_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)
    fallback: Literal["deterministic_manual"] = "deterministic_manual"


class ProgramImportResponse(BaseModel):
    id: str
    status: ImportStatus
    source_format: ImportFormat
    schema_version: int
    parser_version: str
    layout_version: str | None = None
    duration_weeks: int | None = Field(default=None, ge=1, le=24)
    expires_at: datetime
    program_title: str | None = None
    goal: ImportGoal | None = None
    level: ImportLevel | None = None
    provenance: ProgramImportProvenance = Field(default_factory=ProgramImportProvenance)
    blocks: list[ProgramImportBlock] = Field(default_factory=list, max_length=24)
    coaching_rules: list[ProgramCoachingRule] = Field(default_factory=list, max_length=500)
    rows: list[ProgramImportRow]
    issues: list[ProgramImportIssue]
    summary: ProgramImportSummary
    ai: ProgramImportAiInfo | None = None


class ProgramImportRowResolution(BaseModel):
    row_number: int = Field(ge=3)
    exercise_id: int | None = Field(default=None, ge=1)


class ProgramImportResolveRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=128)
    goal: ImportGoal | None = None
    level: ImportLevel | None = None
    provenance: ProgramImportProvenance | None = None
    rows: list[ProgramImportRowResolution] = Field(default_factory=list, max_length=500)


class ProgramImportConfirmRequest(BaseModel):
    target_program_id: int | None = Field(default=None, ge=1)
    expected_revision_number: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_revision_target(self):
        if (self.target_program_id is None) != (self.expected_revision_number is None):
            raise ValueError("target program and expected revision must be provided together")
        return self


class ProgramImportConfirmResponse(BaseModel):
    import_id: str
    template: ProgramTemplateResponse
    assigned_program_id: int | None = None
    revision_number: int | None = Field(default=None, ge=1)
    workouts_created: int = 0
    workouts_updated: int = 0
    target_user: ProgramTargetUserResponse
