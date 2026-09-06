from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from fitminiapp_api.schemas.program import (
    ProgramTargetUserResponse,
    ProgramTemplateResponse,
)

ImportFormat = Literal["csv", "xlsx"]
ImportStatus = Literal["pending", "confirmed", "cancelled", "expired"]
ImportIssueSeverity = Literal["blocking", "warning"]
ImportMatchStatus = Literal["matched", "needs_resolution", "invalid"]
ImportMatchType = Literal["id", "slug", "title", "alias", "transliteration", "manual"]
ImportMetricType = Literal["strength", "cardio"]
ImportGoal = Literal["muscle_gain", "fat_loss", "maintenance", "recomposition"]
ImportLevel = Literal["beginner", "intermediate", "advanced"]


class ProgramImportIssue(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    severity: ImportIssueSeverity
    message: str = Field(min_length=1, max_length=500)
    location: str | None = Field(default=None, max_length=128)
    field: str | None = Field(default=None, max_length=64)
    source_sheet: str | None = Field(default=None, max_length=31)
    source_row: int | None = Field(default=None, ge=1)
    source_cell: str | None = Field(default=None, max_length=32)


class ProgramImportCandidate(BaseModel):
    exercise_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=128)
    metric_type: ImportMetricType
    match_type: ImportMatchType


class ProgramImportRow(BaseModel):
    row_number: int = Field(ge=3)
    source_sheet: str | None = Field(default=None, max_length=31)
    source_range: str | None = Field(default=None, max_length=64)
    source_cells: dict[str, str] = Field(default_factory=dict, max_length=18)
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
    resolved_exercise_id: int | None = Field(default=None, ge=1)
    resolved_exercise_title: str | None = Field(default=None, max_length=128)
    match_status: ImportMatchStatus
    match_type: ImportMatchType | None = None
    candidates: list[ProgramImportCandidate] = Field(default_factory=list, max_length=5)
    issues: list[ProgramImportIssue] = Field(default_factory=list, max_length=20)


class ProgramImportSummary(BaseModel):
    row_count: int = Field(ge=0)
    cell_count: int = Field(ge=0)
    matched_row_count: int = Field(ge=0)
    unresolved_row_count: int = Field(ge=0)
    blocking_issue_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)


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
    rows: list[ProgramImportRow]
    issues: list[ProgramImportIssue]
    summary: ProgramImportSummary


class ProgramImportRowResolution(BaseModel):
    row_number: int = Field(ge=3)
    exercise_id: int | None = Field(default=None, ge=1)


class ProgramImportResolveRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=128)
    goal: ImportGoal | None = None
    level: ImportLevel | None = None
    rows: list[ProgramImportRowResolution] = Field(default_factory=list, max_length=500)


class ProgramImportConfirmResponse(BaseModel):
    import_id: str
    template: ProgramTemplateResponse
    assigned_program_id: int | None = None
    workouts_created: int = 0
    target_user: ProgramTargetUserResponse
