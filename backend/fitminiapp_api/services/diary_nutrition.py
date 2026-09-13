from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from fitminiapp_api.models.food_diary import FoodDiaryEntry

ZERO = Decimal("0")


@dataclass(frozen=True)
class DiaryEntryNutrition:
    energy_kcal: Decimal | None
    protein_g: Decimal | None
    fat_g: Decimal | None
    carbs_g: Decimal | None
    fiber_g: Decimal | None


@dataclass
class DiaryDayNutrition:
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    fat_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fiber_g: Decimal | None = None
    has_entries: bool = False
    missing_macros: bool = False

    def add(self, entry: FoodDiaryEntry) -> None:
        values = diary_entry_nutrition(entry)
        self.has_entries = True
        self.calories = _sum_optional(self.calories, values.energy_kcal)
        self.protein_g = _sum_optional(self.protein_g, values.protein_g)
        self.fat_g = _sum_optional(self.fat_g, values.fat_g)
        self.carbs_g = _sum_optional(self.carbs_g, values.carbs_g)
        self.fiber_g = _sum_optional(self.fiber_g, values.fiber_g)
        if entry.entry_kind == "quick_add" and values.protein_g is None:
            self.missing_macros = True


def _sum_optional(current: Decimal | None, value: Decimal | None) -> Decimal | None:
    if value is None:
        return current
    return (current if current is not None else ZERO) + value


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation, TypeError, ValueError:
        return None
    return parsed if parsed.is_finite() else None


def _from_nutrition_amount(payload: dict) -> DiaryEntryNutrition:
    return DiaryEntryNutrition(
        energy_kcal=_decimal(payload.get("energy_kcal")),
        protein_g=_decimal(payload.get("protein_g")),
        fat_g=_decimal(payload.get("fat_g")),
        carbs_g=_decimal(payload.get("carbs_g")),
        fiber_g=_decimal(payload.get("fiber_g")),
    )


def diary_entry_nutrition(entry: FoodDiaryEntry) -> DiaryEntryNutrition:
    """Read the immutable amount snapshot, retaining legacy fallback for old rows."""

    if entry.entry_kind == "quick_add":
        return DiaryEntryNutrition(
            energy_kcal=_decimal(entry.quick_energy_kcal),
            protein_g=_decimal(entry.quick_protein_g),
            fat_g=_decimal(entry.quick_fat_g),
            carbs_g=_decimal(entry.quick_carbs_g),
            fiber_g=None,
        )
    if isinstance(entry.nutrition_amount, dict) and "energy_kcal" in entry.nutrition_amount:
        return _from_nutrition_amount(entry.nutrition_amount)
    factor = entry.weight_g / Decimal("100") if entry.weight_g is not None else None

    def legacy_value(value: Decimal | None) -> Decimal | None:
        return value * factor if value is not None and factor is not None else None

    return DiaryEntryNutrition(
        energy_kcal=legacy_value(entry.energy_kcal_per_100g),
        protein_g=legacy_value(entry.protein_g_per_100g),
        fat_g=legacy_value(entry.fat_g_per_100g),
        carbs_g=legacy_value(entry.carbs_g_per_100g),
        fiber_g=legacy_value(entry.fiber_g_per_100g),
    )


def aggregate_diary_entries(
    entries: Iterable[FoodDiaryEntry],
) -> dict[tuple[int, date], DiaryDayNutrition]:
    result: dict[tuple[int, date], DiaryDayNutrition] = {}
    for entry in entries:
        key = (entry.user_id, entry.diary_date)
        result.setdefault(key, DiaryDayNutrition()).add(entry)
    return result
