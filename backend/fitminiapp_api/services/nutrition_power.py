from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Literal, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.nutrition_power import (
    FoodSearchAlias,
    NutritionMealTemplate,
    NutritionMealTemplateItem,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.food import FoodNutrientsInput
from fitminiapp_api.schemas.food_diary import FoodDiaryNutrition
from fitminiapp_api.schemas.nutrition_power import (
    FoodDiaryBatchItem,
    FoodDiaryBatchResponse,
    FoodSearchAliasCreate,
    FoodSearchAliasListResponse,
    FoodSearchAliasResponse,
    FoodSearchAliasUpdate,
    NaturalFoodCandidate,
    NaturalInputCommitRequest,
    NaturalInputPreviewResponse,
    NaturalInputRowResponse,
    NutritionMealTemplateCreate,
    NutritionMealTemplateInsertRequest,
    NutritionMealTemplateItemInput,
    NutritionMealTemplateItemResponse,
    NutritionMealTemplateListResponse,
    NutritionMealTemplateResponse,
    NutritionMealTemplateUpdate,
)
from fitminiapp_api.services.food_diary import (
    FoodDiaryError,
    create_food_diary_batch,
)
from fitminiapp_api.services.food_search_aliases import normalize_food_search_query
from fitminiapp_api.services.foods import (
    FoodError,
    FoodNutrition,
    calculate_food_amount,
    calculate_food_nutrition,
    get_food_response,
    get_visible_food,
    search_foods,
)
from fitminiapp_api.services.recipes import (
    RecipeError,
    calculate_recipe,
    get_owned_recipe,
)

TemplateKind = Literal["food", "recipe"]
BatchKind = Literal["meal_template", "natural_input"]
ZERO = Decimal("0")
MAX_NATURAL_INPUT_LENGTH = 2000


class NutritionPowerError(ValueError):
    pass


class NutritionPowerNotFoundError(NutritionPowerError):
    pass


class NutritionPowerConflictError(NutritionPowerError):
    pass


def _normalized_name(value: str) -> str:
    return " ".join(value.split())


def _required_nutrition(calculation: FoodNutrition) -> FoodDiaryNutrition:
    if calculation.energy_kcal is None:
        raise NutritionPowerError("nutrition for this item is incomplete")
    return FoodDiaryNutrition(
        energy_kcal=calculation.energy_kcal,
        protein_g=calculation.protein_g,
        fat_g=calculation.fat_g,
        carbs_g=calculation.carbs_g,
        fiber_g=calculation.fiber_g,
    )


def _sum_nutrition(values: list[FoodDiaryNutrition]) -> FoodDiaryNutrition:
    if not values:
        return FoodDiaryNutrition(
            energy_kcal=ZERO,
            protein_g=ZERO,
            fat_g=ZERO,
            carbs_g=ZERO,
            fiber_g=ZERO,
        )

    def optional_sum(items: list[Decimal | None]) -> Decimal | None:
        if any(item is None for item in items):
            return None
        return sum((cast(Decimal, item) for item in items), start=ZERO)

    fiber = optional_sum([value.fiber_g for value in values])
    return FoodDiaryNutrition(
        energy_kcal=sum((value.energy_kcal for value in values), start=ZERO),
        protein_g=optional_sum([value.protein_g for value in values]),
        fat_g=optional_sum([value.fat_g for value in values]),
        carbs_g=optional_sum([value.carbs_g for value in values]),
        fiber_g=fiber,
    )


def _template_item_calculation(
    db: Session,
    user: User,
    item: NutritionMealTemplateItem,
) -> tuple[str, str | None, Decimal | None, FoodDiaryNutrition | None, bool, str | None]:
    if item.item_kind == "food":
        if item.food_id is None:
            return (
                item.source_name,
                item.source_brand,
                None,
                None,
                False,
                "Исходный продукт больше недоступен; удалите его из шаблона.",
            )
        try:
            food = get_visible_food(db, user, item.food_id)
            calculation = calculate_food_amount(food, item.amount, item.amount_unit)
            return (
                food.name,
                food.brand,
                calculation.weight_g,
                _required_nutrition(calculation),
                True,
                None,
            )
        except (FoodError, NutritionPowerError) as exc:
            return (
                item.source_name,
                item.source_brand,
                None,
                None,
                False,
                f"Продукт нельзя использовать сейчас: {exc}",
            )

    if item.recipe_id is None:
        return (
            item.source_name,
            None,
            None,
            None,
            False,
            "Исходный рецепт больше недоступен; удалите его из шаблона.",
        )
    try:
        recipe = get_owned_recipe(db, user, item.recipe_id)
        recipe_calculation = calculate_recipe(recipe)
        nutrients = recipe_calculation.nutrients_per_100g
        calculation = calculate_food_nutrition(
            FoodNutrientsInput(
                energy_kcal_per_100g=nutrients.energy_kcal_per_100g,
                protein_g_per_100g=nutrients.protein_g_per_100g,
                fat_g_per_100g=nutrients.fat_g_per_100g,
                carbs_g_per_100g=nutrients.carbs_g_per_100g,
                fiber_g_per_100g=nutrients.fiber_g_per_100g,
            ),
            item.amount,
        )
        return (
            recipe.name,
            None,
            item.amount,
            _required_nutrition(calculation),
            True,
            None,
        )
    except (RecipeError, NutritionPowerError, FoodDiaryError) as exc:
        return (
            item.source_name,
            None,
            None,
            None,
            False,
            f"Рецепт нельзя использовать сейчас: {exc}",
        )


def _serialize_template_item(
    db: Session,
    user: User,
    item: NutritionMealTemplateItem,
) -> NutritionMealTemplateItemResponse:
    name, brand, weight_g, nutrition, available, message = _template_item_calculation(
        db, user, item
    )
    return NutritionMealTemplateItemResponse(
        id=item.id,
        position=item.position,
        item_kind=cast(TemplateKind, item.item_kind),
        food_id=item.food_id,
        recipe_id=item.recipe_id,
        name=name,
        brand=brand,
        amount=item.amount,
        amount_unit=cast(Literal["g", "ml", "serving"], item.amount_unit),
        weight_g=weight_g,
        nutrition=nutrition,
        available=available,
        message=message,
    )


def serialize_meal_template(
    db: Session,
    user: User,
    template: NutritionMealTemplate,
) -> NutritionMealTemplateResponse:
    items = [_serialize_template_item(db, user, item) for item in template.items]
    available_items = [item for item in items if item.available and item.nutrition is not None]
    total_weight = (
        sum((cast(Decimal, item.weight_g) for item in available_items), start=ZERO)
        if len(available_items) == len(items)
        else None
    )
    return NutritionMealTemplateResponse(
        id=template.id,
        name=template.name,
        items=items,
        total_weight_g=total_weight,
        totals=_sum_nutrition(
            [cast(FoodDiaryNutrition, item.nutrition) for item in available_items]
        ),
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def _template_or_404(db: Session, user: User, template_id: int) -> NutritionMealTemplate:
    template = (
        db.query(NutritionMealTemplate)
        .options(selectinload(NutritionMealTemplate.items))
        .filter(
            NutritionMealTemplate.id == template_id,
            NutritionMealTemplate.owner_user_id == user.id,
        )
        .first()
    )
    if template is None:
        raise NutritionPowerNotFoundError("meal template not found")
    return template


def _build_template_item(
    db: Session,
    user: User,
    template: NutritionMealTemplate,
    position: int,
    payload: NutritionMealTemplateItemInput,
) -> NutritionMealTemplateItem:
    if payload.food_id is not None:
        try:
            food = get_visible_food(db, user, payload.food_id)
            calculation = calculate_food_amount(food, payload.amount, payload.amount_unit)
            if calculation.energy_kcal is None:
                raise NutritionPowerError("food nutrition is incomplete")
        except FoodError as exc:
            raise NutritionPowerNotFoundError("food not found") from exc
        return NutritionMealTemplateItem(
            template=template,
            position=position,
            item_kind="food",
            food_id=food.id,
            recipe_id=None,
            amount=payload.amount,
            amount_unit=payload.amount_unit,
            source_name=food.name,
            source_brand=food.brand,
        )

    try:
        recipe = get_owned_recipe(db, user, cast(int, payload.recipe_id))
        calculate_recipe(recipe)
    except RecipeError as exc:
        raise NutritionPowerNotFoundError("recipe not found or has invalid nutrition") from exc
    return NutritionMealTemplateItem(
        template=template,
        position=position,
        item_kind="recipe",
        food_id=None,
        recipe_id=recipe.id,
        amount=payload.amount,
        amount_unit="g",
        source_name=recipe.name,
        source_brand=None,
    )


def create_meal_template(
    db: Session,
    user: User,
    payload: NutritionMealTemplateCreate,
) -> NutritionMealTemplateResponse:
    template = NutritionMealTemplate(owner_user_id=user.id, name=payload.name)
    db.add(template)
    try:
        db.flush()
        template.items.extend(
            _build_template_item(db, user, template, position, item)
            for position, item in enumerate(payload.items)
        )
        db.commit()
    except NutritionPowerError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise NutritionPowerConflictError("meal template could not be saved") from exc
    return serialize_meal_template(db, user, _template_or_404(db, user, template.id))


def list_meal_templates(
    db: Session,
    user: User,
    *,
    limit: int,
    offset: int,
) -> NutritionMealTemplateListResponse:
    query = db.query(NutritionMealTemplate).filter(NutritionMealTemplate.owner_user_id == user.id)
    total = query.count()
    templates = (
        query.options(selectinload(NutritionMealTemplate.items))
        .order_by(NutritionMealTemplate.updated_at.desc(), NutritionMealTemplate.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return NutritionMealTemplateListResponse(
        items=[serialize_meal_template(db, user, template) for template in templates],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_meal_template_response(
    db: Session,
    user: User,
    template_id: int,
) -> NutritionMealTemplateResponse:
    return serialize_meal_template(db, user, _template_or_404(db, user, template_id))


def update_meal_template(
    db: Session,
    user: User,
    template_id: int,
    payload: NutritionMealTemplateUpdate,
) -> NutritionMealTemplateResponse:
    template = _template_or_404(db, user, template_id)
    if "name" in payload.model_fields_set:
        template.name = cast(str, payload.name)
    try:
        if "items" in payload.model_fields_set:
            template.items.clear()
            db.flush()
            template.items.extend(
                _build_template_item(db, user, template, position, item)
                for position, item in enumerate(
                    cast(list[NutritionMealTemplateItemInput], payload.items)
                )
            )
        template.updated_at = now_msk_naive()
        db.commit()
    except NutritionPowerError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise NutritionPowerConflictError("meal template could not be saved") from exc
    return serialize_meal_template(db, user, _template_or_404(db, user, template.id))


def delete_meal_template(db: Session, user: User, template_id: int) -> None:
    template = _template_or_404(db, user, template_id)
    db.delete(template)
    db.commit()


def insert_meal_template(
    db: Session,
    user: User,
    template_id: int,
    payload: NutritionMealTemplateInsertRequest,
    idempotency_key: str,
) -> FoodDiaryBatchResponse:
    template = _template_or_404(db, user, template_id)
    items: list[FoodDiaryBatchItem] = []
    for item in template.items:
        if item.item_kind == "food":
            if item.food_id is None:
                raise NutritionPowerConflictError(
                    f"Шаблон содержит недоступный продукт: {item.source_name}"
                )
            items.append(
                FoodDiaryBatchItem(
                    food_id=item.food_id,
                    amount=item.amount,
                    amount_unit=cast(Literal["g", "ml", "serving"], item.amount_unit),
                )
            )
        else:
            if item.recipe_id is None:
                raise NutritionPowerConflictError(
                    f"Шаблон содержит недоступный рецепт: {item.source_name}"
                )
            items.append(
                FoodDiaryBatchItem(
                    recipe_id=item.recipe_id,
                    amount=item.amount,
                    amount_unit="g",
                )
            )
    return create_food_diary_batch(
        db,
        user,
        diary_date=payload.diary_date,
        meal_type=payload.meal_type,
        items=items,
        idempotency_key=idempotency_key,
        operation_kind="meal_template",
        template_id=template.id,
    )


_NUMBER_RE = re.compile(r"(?<![\w])(?P<amount>\d+(?:[.,]\d+)?)")
_UNIT_RE = re.compile(r"^[ \t]*(?P<unit>[A-Za-zА-Яа-яЁё]+)")
_UNIT_ALIASES: dict[str, Literal["g", "ml", "serving"]] = {
    "g": "g",
    "гр": "g",
    "г": "g",
    "грамм": "g",
    "грамма": "g",
    "граммов": "g",
    "ml": "ml",
    "мл": "ml",
    "миллилитр": "ml",
    "миллилитра": "ml",
    "миллилитров": "ml",
    "serving": "serving",
    "порция": "serving",
    "порции": "serving",
    "порций": "serving",
}
_UNSUPPORTED_UNIT_TOKENS = {
    "kg",
    "кг",
    "л",
    "литр",
    "литра",
    "литров",
    "шт",
    "штука",
    "штуки",
    "piece",
    "pieces",
    "oz",
    "lb",
}


def _row(
    index: int,
    raw_text: str,
    name: str,
    *,
    amount: Decimal | None = None,
    amount_unit: Literal["g", "ml", "serving"] | None = None,
    unit_inferred: bool = False,
    status: Literal["matched", "ambiguous", "unresolved", "excluded"] = "unresolved",
    message: str | None = None,
) -> NaturalInputRowResponse:
    return NaturalInputRowResponse(
        row_id=f"row-{index}",
        raw_text=raw_text,
        name=name,
        amount=amount,
        amount_unit=amount_unit,
        unit_inferred=unit_inferred,
        status=status,
        selected_food_id=None,
        selected_food=None,
        nutrition=None,
        candidates=[],
        message=message,
    )


def _parse_amount(raw: str) -> Decimal | None:
    try:
        value = Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return None
    if not value.is_finite() or value <= 0 or value > Decimal("9999999"):
        return None
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -3:
        return None
    return value


def parse_natural_food_input(text: str) -> list[NaturalInputRowResponse]:
    if len(text) > MAX_NATURAL_INPUT_LENGTH:
        raise NutritionPowerError("natural input is too long")
    source = text.strip()
    if not source:
        raise NutritionPowerError("natural input must not be blank")
    matches = list(_NUMBER_RE.finditer(source))
    if not matches:
        chunks = [chunk.strip(" ,;\n\t") for chunk in re.split(r"[,;\n]+", source)]
        return [
            _row(
                index,
                chunk,
                _normalized_name(chunk),
                status=(
                    "excluded" if normalize_food_search_query(chunk) == "вода" else "unresolved"
                ),
                message=(
                    "Вода не добавляется в дневник питания."
                    if normalize_food_search_query(chunk) == "вода"
                    else "Укажите количество, например: 180 г"
                ),
            )
            for index, chunk in enumerate(chunk for chunk in chunks if chunk)
        ]

    rows: list[NaturalInputRowResponse] = []
    cursor = 0
    for index, match in enumerate(matches):
        raw_name = _normalized_name(source[cursor : match.start()].strip(" ,;\n\t"))
        amount_raw = match.group("amount")
        amount = _parse_amount(amount_raw)
        unit_match = _UNIT_RE.match(source[match.end() :])
        token = normalize_food_search_query(unit_match.group("unit")) if unit_match else ""
        amount_unit = _UNIT_ALIASES.get(token)
        unsupported_unit = bool(
            unit_match and amount_unit is None and token in _UNSUPPORTED_UNIT_TOKENS
        )
        consumed_end = match.end() + (
            unit_match.end() if unit_match and (amount_unit or unsupported_unit) else 0
        )
        raw_text = source[cursor:consumed_end].strip(" ,;\n\t")
        message: str | None = None
        if not raw_name:
            raw_name = "Неизвестный продукт"
            message = "Укажите название продукта перед количеством."
        if amount is None:
            message = (
                "Количество должно быть положительным числом с максимумом 3 знаков после запятой."
            )
        if unsupported_unit:
            unknown = token
            message = (
                f"Единица «{unknown}» не поддерживается; выберите граммы, миллилитры или порции."
            )
            amount = None
            amount_unit = None
        next_number = matches[index + 1] if index + 1 < len(matches) else None
        trailing = source[consumed_end : next_number.start() if next_number else len(source)]
        trailing_clean = trailing.strip(" ,;\n\t")
        if amount_unit is None and trailing_clean:
            first_token_match = re.match(r"([A-Za-zА-Яа-яЁё]+)", trailing_clean)
            first_token = (
                normalize_food_search_query(first_token_match.group(1)) if first_token_match else ""
            )
            if first_token in _UNSUPPORTED_UNIT_TOKENS:
                message = f"Единица «{first_token}» не поддерживается; выберите граммы, миллилитры или порции."
            elif next_number is None:
                message = "После количества укажите только единицу измерения."
                amount = None
                amount_unit = None
        normalized_name = normalize_food_search_query(raw_name)
        if normalized_name == "вода":
            rows.append(
                _row(
                    index,
                    raw_text,
                    raw_name,
                    amount=amount,
                    amount_unit=amount_unit,
                    unit_inferred=amount_unit is None,
                    status="excluded",
                    message="Вода не добавляется в дневник питания.",
                )
            )
        else:
            rows.append(
                _row(
                    index,
                    raw_text,
                    raw_name,
                    amount=amount,
                    amount_unit=amount_unit or "g" if amount is not None else None,
                    unit_inferred=amount_unit is None and amount is not None,
                    message=message,
                )
            )
        cursor = consumed_end
    return rows


def _candidate_source(
    food: object,
) -> Literal["alias", "personal", "favorite", "frequent", "recent", "shared", "local"]:
    if getattr(food, "food_type", None) == "user":
        return "personal"
    if getattr(food, "catalog_quality", None) == "community_unverified":
        return "shared"
    return "local"


def _food_matches_name(food_name: str, brand: str | None, query: str) -> bool:
    normalized_query = normalize_food_search_query(query)
    return normalize_food_search_query(food_name) == normalized_query or (
        brand is not None
        and normalize_food_search_query(f"{food_name} {brand}") == normalized_query
    )


def _natural_food_nutrition(
    db: Session,
    user: User,
    row: NaturalInputRowResponse,
    food_id: int,
) -> FoodDiaryNutrition:
    if row.amount is None or row.amount_unit is None:
        raise NutritionPowerError("food amount requires an explicit unit")
    food = get_visible_food(db, user, food_id)
    return _required_nutrition(calculate_food_amount(food, row.amount, row.amount_unit))


def _resolve_natural_row(
    db: Session,
    user: User,
    row: NaturalInputRowResponse,
) -> NaturalInputRowResponse:
    if row.status == "excluded" or row.amount is None:
        return row
    normalized = normalize_food_search_query(row.name)
    alias = (
        db.query(FoodSearchAlias)
        .filter(FoodSearchAlias.user_id == user.id, FoodSearchAlias.normalized_alias == normalized)
        .first()
    )
    if alias is not None and alias.food_id is not None:
        try:
            food = get_visible_food(db, user, alias.food_id)
            response = get_food_response(db, user, food.id)
            nutrition = _natural_food_nutrition(db, user, row, food.id)
            return row.model_copy(
                update={
                    "status": "matched",
                    "selected_food_id": food.id,
                    "selected_food": response,
                    "nutrition": nutrition,
                    "candidates": [NaturalFoodCandidate(food=response, source="alias")],
                    "message": "Выбран сохранённый вами алиас; проверьте строку перед записью.",
                }
            )
        except FoodError, NutritionPowerError:
            pass

    try:
        local = search_foods(db, user, row.name, limit=20, offset=0)
    except FoodError:
        local = None
    candidates = [
        item
        for item in (local.items if local is not None else [])
        if _food_matches_name(item.name, item.brand, row.name)
    ]
    if candidates:
        preferred = [item for item in candidates if item.food_type == "user"]
        ordered = preferred or candidates
        if len(ordered) == 1:
            item = ordered[0]
            try:
                nutrition = _natural_food_nutrition(db, user, row, item.id)
            except FoodError, NutritionPowerError:
                return row.model_copy(
                    update={
                        "candidates": [
                            NaturalFoodCandidate(food=item, source=_candidate_source(item))
                        ],
                        "message": "У продукта неполная питательность; выберите другой продукт или создайте свой.",
                    }
                )
            return row.model_copy(
                update={
                    "status": "matched",
                    "selected_food_id": item.id,
                    "selected_food": item,
                    "nutrition": nutrition,
                    "candidates": [NaturalFoodCandidate(food=item, source=_candidate_source(item))],
                    "message": "Проверьте найденный продукт перед записью.",
                }
            )
        return row.model_copy(
            update={
                "status": "ambiguous",
                "candidates": [
                    NaturalFoodCandidate(food=item, source=_candidate_source(item))
                    for item in ordered[:8]
                ],
                "message": "Найдено несколько точных продуктов; выберите один.",
            }
        )

    fallback = (local.items if local is not None else [])[:8]
    return row.model_copy(
        update={
            "status": "unresolved",
            "candidates": [
                NaturalFoodCandidate(food=item, source=_candidate_source(item)) for item in fallback
            ],
            "message": (
                "Проверьте совпадение и выберите продукт."
                if fallback
                else "Продукт не найден. Найдите его в каталоге или удалите строку."
            ),
        }
    )


def preview_natural_input(
    db: Session,
    user: User,
    text: str,
) -> NaturalInputPreviewResponse:
    return NaturalInputPreviewResponse(
        rows=[_resolve_natural_row(db, user, row) for row in parse_natural_food_input(text)]
    )


def commit_natural_input(
    db: Session,
    user: User,
    payload: NaturalInputCommitRequest,
    idempotency_key: str,
) -> FoodDiaryBatchResponse:
    row_ids = [item.row_id for item in payload.items]
    if len(row_ids) != len(set(row_ids)):
        raise NutritionPowerError("natural input rows must be unique")
    items = [
        FoodDiaryBatchItem(
            food_id=item.food_id,
            amount=item.amount,
            amount_unit=item.amount_unit,
        )
        for item in payload.items
    ]
    return create_food_diary_batch(
        db,
        user,
        diary_date=payload.diary_date,
        meal_type=payload.meal_type,
        items=items,
        idempotency_key=idempotency_key,
        operation_kind="natural_input",
    )


def _alias_response(db: Session, user: User, alias: FoodSearchAlias) -> FoodSearchAliasResponse:
    food_name = food_brand = None
    available = False
    if alias.food_id is not None:
        try:
            food = get_visible_food(db, user, alias.food_id)
            food_name, food_brand, available = food.name, food.brand, True
        except FoodError:
            pass
    return FoodSearchAliasResponse(
        id=alias.id,
        alias=alias.alias,
        food_id=alias.food_id,
        food_name=food_name,
        food_brand=food_brand,
        available=available,
        created_at=alias.created_at,
        updated_at=alias.updated_at,
    )


def list_food_search_aliases(db: Session, user: User) -> FoodSearchAliasListResponse:
    aliases = (
        db.query(FoodSearchAlias)
        .filter(FoodSearchAlias.user_id == user.id)
        .order_by(FoodSearchAlias.alias.asc(), FoodSearchAlias.id.asc())
        .all()
    )
    return FoodSearchAliasListResponse(
        items=[_alias_response(db, user, alias) for alias in aliases]
    )


def _alias_food(db: Session, user: User, food_id: int) -> Food:
    try:
        return get_visible_food(db, user, food_id)
    except FoodError as exc:
        raise NutritionPowerNotFoundError("food not found") from exc


def create_food_search_alias(
    db: Session,
    user: User,
    payload: FoodSearchAliasCreate,
) -> FoodSearchAliasResponse:
    food = _alias_food(db, user, payload.food_id)
    normalized_alias = normalize_food_search_query(payload.alias)
    alias = (
        db.query(FoodSearchAlias)
        .filter(
            FoodSearchAlias.user_id == user.id, FoodSearchAlias.normalized_alias == normalized_alias
        )
        .first()
    )
    if alias is None:
        alias = FoodSearchAlias(
            user_id=user.id,
            alias=payload.alias,
            normalized_alias=normalized_alias,
            food_id=food.id,
        )
        db.add(alias)
    else:
        alias.alias = payload.alias
        alias.food_id = food.id
        alias.updated_at = now_msk_naive()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise NutritionPowerConflictError("alias could not be saved") from exc
    db.refresh(alias)
    return _alias_response(db, user, alias)


def update_food_search_alias(
    db: Session,
    user: User,
    alias_id: int,
    payload: FoodSearchAliasUpdate,
) -> FoodSearchAliasResponse:
    alias = (
        db.query(FoodSearchAlias)
        .filter(FoodSearchAlias.id == alias_id, FoodSearchAlias.user_id == user.id)
        .first()
    )
    if alias is None:
        raise NutritionPowerNotFoundError("food alias not found")
    if "food_id" in payload.model_fields_set:
        _alias_food(db, user, cast(int, payload.food_id))
        alias.food_id = payload.food_id
    if "alias" in payload.model_fields_set:
        alias.alias = cast(str, payload.alias)
        alias.normalized_alias = normalize_food_search_query(cast(str, payload.alias))
    alias.updated_at = now_msk_naive()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise NutritionPowerConflictError("another alias already uses this name") from exc
    db.refresh(alias)
    return _alias_response(db, user, alias)


def delete_food_search_alias(db: Session, user: User, alias_id: int) -> None:
    alias = (
        db.query(FoodSearchAlias)
        .filter(FoodSearchAlias.id == alias_id, FoodSearchAlias.user_id == user.id)
        .first()
    )
    if alias is None:
        raise NutritionPowerNotFoundError("food alias not found")
    db.delete(alias)
    db.commit()
