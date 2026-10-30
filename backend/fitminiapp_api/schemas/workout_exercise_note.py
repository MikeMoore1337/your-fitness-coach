from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ExerciseNoteTag = Literal["easy", "hard", "increase_weight"]


class ExerciseNoteVersion(BaseModel):
    expected_version: int = Field(ge=0)
    mutation_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class ExerciseNoteIdentity(ExerciseNoteVersion):
    exercise_id: int = Field(gt=0)
    source_template_exercise_id: int | None = Field(default=None, gt=0)
    plan_revision_number: int | None = Field(default=None, ge=0)
    week_number: int = Field(ge=1)
    day_number: int = Field(ge=1)
    source_cycle_week: int | None = Field(default=None, ge=1)
    cycle_iteration: int | None = Field(default=None, ge=1)


class ExerciseNoteContent(BaseModel):
    body: str | None = Field(default=None, max_length=500)
    tags: list[ExerciseNoteTag] = Field(default_factory=list, max_length=3)

    @field_validator("body", mode="before")
    @classmethod
    def trim_body(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("tags must be unique")
        return value

    @model_validator(mode="after")
    def require_content(self):
        if not self.body and not self.tags:
            raise ValueError("text or at least one tag is required")
        return self


class ExerciseNoteWrite(ExerciseNoteIdentity, ExerciseNoteContent):
    pass


class ExerciseNoteHistoryWrite(ExerciseNoteVersion, ExerciseNoteContent):
    pass


class ExerciseNoteValue(BaseModel):
    id: int
    body: str | None
    tags: list[ExerciseNoteTag]
    version: int


class ExerciseNoteHistoryItem(ExerciseNoteValue):
    workout_id: int
    workout_exercise_id: int
    exercise_id: int
    exercise_title: str | None


class ExerciseNoteHistoryResult(BaseModel):
    version: int
    current_note: ExerciseNoteValue | None


class ExerciseNoteLoad(BaseModel):
    set_number: int
    actual_weight: float | None
    actual_reps: int | None
    duration_minutes: int | None
    distance_km: float | None


class PreviousExerciseNote(ExerciseNoteValue):
    workout_id: int
    workout_exercise_id: int
    completed_on: date
    week_type: Literal["light", "medium", "heavy"] | None
    load: ExerciseNoteLoad | None


class ExerciseNoteResponse(BaseModel):
    workout_id: int
    workout_exercise_id: int
    exercise_id: int
    source_template_exercise_id: int | None
    plan_revision_number: int | None
    week_number: int
    day_number: int
    source_cycle_week: int | None
    cycle_iteration: int | None
    version: int
    current_note: ExerciseNoteValue | None
    previous_note: PreviousExerciseNote | None
