from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HistoryImportIssue(BaseModel):
    code: str
    field: str
    message: str


class HistoryImportExerciseCandidate(BaseModel):
    exercise_id: int
    title: str
    metric_type: str
    unsupported_side: bool


class HistoryImportSource(BaseModel):
    workout_ref: str
    completed_at: str
    timezone: str
    workout_title: str
    status: str
    exercise_ref: str
    exercise_name: str
    set_number: str
    set_status: str
    set_kind: str
    reps: str
    weight: str
    weight_unit: str
    rir: str
    rpe: str
    side: str


class HistoryImportRow(BaseModel):
    line: int
    source: HistoryImportSource
    completed_at_utc: str | None
    completed_on: str | None
    set_number: int | None
    reps: int | None
    weight_kg: str | None
    issues: list[HistoryImportIssue]
    blocking_issues: list[HistoryImportIssue]
    exercise_id: int | None
    match_mode: Literal["auto", "manual"] | None
    match_status: Literal["matched", "ambiguous", "unknown"]
    resolved_title: str | None
    candidates: list[HistoryImportExerciseCandidate]
    excluded: bool


HistoryImportSetFact = tuple[int, int, int | None, str | None, str | None, str | None]


class HistoryImportDuplicateCandidate(BaseModel):
    kind: Literal["exact", "source", "possible"]
    workout_id: int | None = None
    source_ref: str | None = None
    title: str
    completed_at_utc: str | None
    sets: list[HistoryImportSetFact]


class HistoryImportDuplicate(BaseModel):
    workout_ref: str
    source_sets: list[HistoryImportSetFact]
    candidates: list[HistoryImportDuplicateCandidate]
    choice: Literal["keep", "skip"] | None


class HistoryImportResult(BaseModel):
    workout_ids: list[int]
    workout_count: int
    set_count: int


class HistoryImportPreview(BaseModel):
    id: str
    version: int
    status: Literal["pending", "confirmed"]
    provider: str | None = None
    schema_version: int | None = None
    parser_version: str | None = None
    expires_at: str | None = None
    rows: list[HistoryImportRow] = Field(default_factory=list)
    duplicates: list[HistoryImportDuplicate] = Field(default_factory=list)
    duplicate_choices: dict[str, Literal["keep", "skip"]] = Field(default_factory=dict)
    preview_signature: str | None = None
    result: HistoryImportResult | None = None


class HistoryImportDraftSummary(BaseModel):
    id: str
    version: int
    status: Literal["pending", "confirmed"]
    created_at: str
    expires_at: str


class HistoryImportResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    exercise_choices: dict[int, int] = Field(default_factory=dict, max_length=5000)
    excluded_lines: list[int] = Field(default_factory=list, max_length=5000)
    duplicate_choices: dict[str, Literal["keep", "skip"]] = Field(
        default_factory=dict, max_length=200
    )


class HistoryImportCatalogSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = Field(min_length=2, max_length=128)


class HistoryImportConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    preview_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
