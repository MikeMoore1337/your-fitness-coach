from typing import Literal

from pydantic import BaseModel, Field

from fitminiapp_api.schemas.program import (
    ExerciseGuideMedia,
    ProgramRecommendationGoal,
    ProgramSplitType,
)


class PublicExerciseSummary(BaseModel):
    slug: str
    title: str
    primary_muscle: str
    secondary_muscles: list[str]
    equipment: str
    difficulty_level: Literal["beginner", "intermediate", "advanced"]


class PublicExerciseDetail(PublicExerciseSummary):
    technique_steps: list[str]
    breathing: str
    common_mistakes: list[str]
    safety_notes: list[str]
    media: list[ExerciseGuideMedia]
    source_name: str
    source_url: str
    source_license: str
    source_license_url: str | None = None


class PublicProgramExercise(BaseModel):
    slug: str
    title: str
    primary_muscle: str
    equipment: str
    difficulty_level: Literal["beginner", "intermediate", "advanced"]
    prescribed_sets: int = Field(ge=1, le=10)
    prescribed_reps: str = Field(min_length=1, max_length=32)
    rest_seconds: int = Field(ge=0, le=600)


class PublicProgramDay(BaseModel):
    day_number: int = Field(ge=1, le=3)
    title: str = Field(min_length=1, max_length=128)
    exercises: list[PublicProgramExercise] = Field(min_length=1, max_length=20)


class PublicProgramResponse(BaseModel):
    slug: str
    title: str
    goal: ProgramRecommendationGoal
    level: Literal["beginner", "intermediate", "advanced"]
    split_type: ProgramSplitType
    days: list[PublicProgramDay] = Field(min_length=3, max_length=3)
