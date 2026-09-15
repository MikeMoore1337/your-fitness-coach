from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

DemoScenario = Literal["self_training", "nutrition", "trainer"]
DemoTrainerClientId = Literal["alexey", "maria", "ivan"]


class DemoExercise(BaseModel):
    name: str
    prescription: str
    status: Literal["completed", "current", "next"]


class DemoSelfTrainingState(BaseModel):
    kind: Literal["self_training"] = "self_training"
    screen: Literal["today", "active_workout", "summary", "progress"]
    workout_title: str
    workout_subtitle: str
    completed_sets: int = Field(ge=0)
    total_sets: int = Field(ge=1)
    exercises: list[DemoExercise]
    duration_minutes: int = Field(ge=0)
    total_volume_kg: int = Field(ge=0)
    progress_change_percent: float


class DemoNutritionItem(BaseModel):
    name: str
    serving: str
    calories: int = Field(ge=0)
    protein_g: float = Field(ge=0)


class DemoNutritionState(BaseModel):
    kind: Literal["nutrition"] = "nutrition"
    screen: Literal["diary", "report"]
    date_label: str
    item_added: bool
    recent_item: DemoNutritionItem
    calories: int = Field(ge=0)
    calorie_target: int = Field(gt=0)
    protein_g: float = Field(ge=0)
    protein_target_g: float = Field(gt=0)
    meals_logged: int = Field(ge=0)


class DemoTrainerFact(BaseModel):
    label: str
    value: str


class DemoTrainerClient(BaseModel):
    id: DemoTrainerClientId
    name: str
    status_label: str
    context_label: str
    workout_title: str
    facts: list[DemoTrainerFact]
    comment: str | None = None


class DemoTrainerState(BaseModel):
    kind: Literal["trainer"] = "trainer"
    screen: Literal["client"] = "client"
    selected_client_id: DemoTrainerClientId
    clients: list[DemoTrainerClient]


class DemoProgramScheduleDay(BaseModel):
    day_label: str
    workout_title: str
    status: Literal["completed", "planned", "rest"]


class DemoProgramSummary(BaseModel):
    name: str
    current_week: int = Field(ge=1)
    total_weeks: int = Field(ge=1)
    sessions_per_week: int = Field(ge=1, le=7)
    schedule: list[DemoProgramScheduleDay]


class DemoTrainingHistoryItem(BaseModel):
    period_label: str
    workout_title: str
    completed_sets: int = Field(ge=0)
    volume_kg: int = Field(ge=0)


class DemoVolumeHistoryItem(BaseModel):
    period_label: str
    volume_kg: int = Field(ge=0)


class DemoNutritionHistoryDay(BaseModel):
    date_label: str
    status: Literal["complete", "incomplete", "not_logged"]
    calories: int | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)


class DemoMeasurement(BaseModel):
    label: str
    value: str
    date_label: str


class DemoCabinetToday(BaseModel):
    title: str
    summary: str
    status_label: str
    completed_days: int = Field(ge=0, le=7)
    planned_days: int = Field(ge=0, le=7)


class DemoCabinetNutrition(BaseModel):
    calories: int = Field(ge=0)
    calorie_target: int = Field(gt=0)
    protein_g: float = Field(ge=0)
    protein_target_g: float = Field(gt=0)
    meals_logged: int = Field(ge=0)
    item_added: bool
    recent_item: DemoNutritionItem


class DemoCabinetProgress(BaseModel):
    workouts_completed: int = Field(ge=0)
    latest_volume_kg: int = Field(ge=0)
    volume_change_percent: float
    nutrition_days_logged: int = Field(ge=0, le=7)
    nutrition_completion_percent: int = Field(ge=0)
    summary: str
    adherence_percent: int = Field(ge=0, le=100)
    training_history: list[DemoTrainingHistoryItem]
    volume_history: list[DemoVolumeHistoryItem]
    nutrition_history: list[DemoNutritionHistoryDay]
    measurements: list[DemoMeasurement]


class DemoCabinetState(BaseModel):
    program: DemoProgramSummary
    today: DemoCabinetToday
    nutrition: DemoCabinetNutrition
    progress: DemoCabinetProgress
    trainer: DemoTrainerState | None = None
    meaningful_action_completed: bool
    conversion_title: str


DemoScenarioState = Annotated[
    DemoSelfTrainingState | DemoNutritionState | DemoTrainerState,
    Field(discriminator="kind"),
]


class DemoSessionCreateRequest(BaseModel):
    scenario: DemoScenario


class DemoActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    comment: str | None = Field(default=None, max_length=280)
    client_id: DemoTrainerClientId | None = None

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Комментарий не может быть пустым")
        return normalized


class DemoSessionSnapshot(BaseModel):
    capability: Literal["demo"] = "demo"
    scenario: DemoScenario
    fixture_version: Literal["demo-curated-v2"] = "demo-curated-v2"
    revision: int = Field(ge=1)
    expires_at: datetime
    state: DemoScenarioState
    cabinet: DemoCabinetState


class DemoSessionCreated(DemoSessionSnapshot):
    session_token: str
