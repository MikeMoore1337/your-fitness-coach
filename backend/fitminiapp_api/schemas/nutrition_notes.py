from typing import Literal

from pydantic import BaseModel, Field

MealFeeling = Literal["none", "low", "medium", "high"]
MealEnergy = Literal["low", "normal", "high"]


class NutritionMealNoteUpdate(BaseModel):
    hunger_before: MealFeeling | None = None
    fullness_after: MealFeeling | None = None
    energy: MealEnergy | None = None
    note: str | None = Field(default=None, max_length=500)
