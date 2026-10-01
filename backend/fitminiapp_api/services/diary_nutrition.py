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
    exact_entry_count: int = 0
    approximate_entry_count: int = 0
    partial_entry_count: int = 0
    protein_missing: bool = False
    fat_missing: bool = False
    carbs_missing: bool = False
    fiber_missing: bool = False

    def add(self, entry: FoodDiaryEntry) -> None:
        values = diary_entry_nutrition(entry)
        self.has_entries = True
        self.calories = _sum_optional(self.calories, values.energy_kcal)
        self.protein_g, self.protein_missing = _sum_tracked(
            self.protein_g, values.protein_g, self.protein_missing
        )
        self.fat_g, self.fat_missing = _sum_tracked(self.fat_g, values.fat_g, self.fat_missing)
        self.carbs_g, self.carbs_missing = _sum_tracked(
            self.carbs_g, values.carbs_g, self.carbs_missing
        )
        self.fiber_g, self.fiber_missing = _sum_tracked(
            self.fiber_g, values.fiber_g, self.fiber_missing
        )
        self.missing_macros = self.protein_missing or self.fat_missing or self.carbs_missing
        confidence = diary_entry_confidence(entry)
        if confidence == "exact":
            self.exact_entry_count += 1
        elif confidence == "approximate":
            self.approximate_entry_count += 1
        else:
            self.partial_entry_count += 1


def _sum_optional(
    current: Decimal | None,
    value: Decimal | None,
) -> Decimal | None:
    if value is None:
        return current
    return (current if current is not None else ZERO) + value


def _sum_tracked(
    current: Decimal | None,
    value: Decimal | None,
    missing: bool,
) -> tuple[Decimal | None, bool]:
    if missing or value is None:
        return None, True
    return _sum_optional(current, value), False


def diary_entry_source(entry: FoodDiaryEntry) -> str:
    if entry.nutrition_source in {"catalog", "recipe", "manual", "restaurant", "photo"}:
        return entry.nutrition_source
    return {"food": "catalog", "recipe": "recipe"}.get(entry.entry_kind, "manual")


def diary_entry_confidence(entry: FoodDiaryEntry) -> str:
    if entry.entry_kind != "quick_add":
        return "exact"
    values = (entry.quick_protein_g, entry.quick_fat_g, entry.quick_carbs_g)
    return "approximate" if all(value is not None for value in values) else "partial"


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
