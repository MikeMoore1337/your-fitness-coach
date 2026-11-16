from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fitminiapp_api.schemas.nutrition import (
    NutritionDateOverrideResponse,
    NutritionManualTargetSave,
    NutritionProgramDayResponse,
    NutritionScheduleBindingStatus,
    NutritionScheduleProgramContext,
    NutritionScheduleRuleResponse,
)
from fitminiapp_api.schemas.nutrition_plan import NutritionPlanDayResponse


class CoachNutritionProposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_date: date
    expected_target_id: int | None = Field(ge=1)
    expected_plan_revision: int = Field(ge=0)
    calories: int = Field(ge=800, le=6000)
    protein_g: int = Field(ge=0, le=400)
    fat_g: int = Field(ge=0, le=250)
    carbs_g: int = Field(ge=0, le=800)
    confirm_energy_mismatch: bool = False
    item_id: int | None = Field(default=None, ge=1)
    item_amount: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=3, allow_inf_nan=False
    )
    comment: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_item(self) -> CoachNutritionProposalCreate:
        if (self.item_id is None) != (self.item_amount is None):
            raise ValueError("item_id and item_amount must be provided together")
        return self

    def target(self) -> NutritionManualTargetSave:
        return NutritionManualTargetSave(
            calories=self.calories,
            protein_g=self.protein_g,
            fat_g=self.fat_g,
            carbs_g=self.carbs_g,
            confirm_energy_mismatch=self.confirm_energy_mismatch,
        )


class CoachNutritionProposalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["accept", "reject"]
    version: int = Field(gt=0)


class CoachNutritionPlanPreview(BaseModel):
    target_id: int | None
    day: NutritionPlanDayResponse
    program: NutritionScheduleProgramContext | None
    program_day: NutritionProgramDayResponse | None
    binding: NutritionScheduleBindingStatus | None


class CoachNutritionTargetAssignments(BaseModel):
    dates: list[NutritionDateOverrideResponse]
    schedule: list[NutritionScheduleRuleResponse]


class CoachNutritionProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version: int
    target_date: date
    target_id: int | None
    plan_revision: int
    request: CoachNutritionProposalCreate
    before: dict
    status: Literal["pending", "accepted", "rejected"]
    created_at: datetime
    decided_at: datetime | None
