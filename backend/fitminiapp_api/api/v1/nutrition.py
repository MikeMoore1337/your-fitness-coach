from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_nutrition_label_scan, require_user
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.nutrition_label.meal_vision import build_meal_vision_adapter
from fitminiapp_api.nutrition_label.vision import build_vision_fallback_adapter
from fitminiapp_api.schemas.food import (
    FoodBarcodeLookupResponse,
    FoodListResponse,
    FoodResponse,
    FoodSearchResponse,
    UserFoodCreate,
    UserFoodUpdate,
    validate_gtin,
)
from fitminiapp_api.schemas.food_diary import (
    FoodDiaryCopyDay,
    FoodDiaryCopyDayPreview,
    FoodDiaryCopyMeal,
    FoodDiaryCopyMealPreview,
    FoodDiaryCopyPreviewResponse,
    FoodDiaryCopyProduct,
    FoodDiaryCopyProductPreview,
    FoodDiaryCopyResponse,
    FoodDiaryDayResponse,
    FoodDiaryDayStatusUpdate,
    FoodDiaryEntryCreate,
    FoodDiaryEntryResponse,
    FoodDiaryEntryUpdate,
    MealType,
)
from fitminiapp_api.schemas.grocery_list import (
    GroceryListGenerateRequest,
    GroceryListItemUpdate,
    GroceryListManualItemCreate,
    GroceryListResponse,
)
from fitminiapp_api.schemas.hydration import (
    HydrationDayResponse,
    HydrationEntryCreate,
    HydrationEntryResponse,
    HydrationEntryUpdate,
    HydrationGoalResponse,
    HydrationGoalSave,
    HydrationPresetResponse,
    HydrationPresetSave,
)
from fitminiapp_api.schemas.nutrition import (
    EnergyCalibrationDecision,
    EnergyCalibrationHistoryResponse,
    EnergyCalibrationResponse,
    NutritionManualTargetSave,
    NutritionTargetHistoryResponse,
    NutritionTargetResponse,
    NutritionTargetSave,
)
from fitminiapp_api.schemas.nutrition_label import (
    NutritionLabelConfirmRequest,
    NutritionLabelConfirmResponse,
    NutritionLabelDraftResponse,
)
from fitminiapp_api.schemas.nutrition_plan import (
    NutritionPlanCopyRequest,
    NutritionPlanDayResponse,
    NutritionPlanFillRequest,
    NutritionPlanItemActionRequest,
    NutritionPlanItemActionResponse,
    NutritionPlanItemCreate,
    NutritionPlanItemUpdate,
    NutritionPlanWeekResponse,
)
from fitminiapp_api.schemas.nutrition_power import (
    FoodDiaryBatchResponse,
    FoodSearchAliasCreate,
    FoodSearchAliasListResponse,
    FoodSearchAliasResponse,
    FoodSearchAliasUpdate,
    NaturalInputCommitRequest,
    NaturalInputPreviewRequest,
    NaturalInputPreviewResponse,
    NutritionMealTemplateCreate,
    NutritionMealTemplateInsertRequest,
    NutritionMealTemplateListResponse,
    NutritionMealTemplateResponse,
    NutritionMealTemplateUpdate,
    NutritionSuggestionCommitRequest,
    NutritionSuggestionsResponse,
)
from fitminiapp_api.schemas.photo_meal import (
    PhotoMealConfirmRequest,
    PhotoMealConfirmResponse,
    PhotoMealDraftResponse,
)
from fitminiapp_api.schemas.recipe import (
    RecipeCreate,
    RecipeListResponse,
    RecipeResponse,
    RecipeUpdate,
)
from fitminiapp_api.services.energy_calibration import (
    EnergyCalibrationConflictError,
    EnergyCalibrationNotFoundError,
    decide_energy_calibration,
    list_energy_calibrations,
    preview_energy_calibration,
)
from fitminiapp_api.services.food_catalog import (
    get_food_catalog_item_by_barcode,
    search_food_catalog,
)
from fitminiapp_api.services.food_diary import (
    FoodDiaryConflictError,
    FoodDiaryError,
    FoodDiaryNotFoundError,
    copy_diary_day,
    copy_diary_meal,
    copy_diary_product,
    create_food_diary_entry,
    delete_food_diary_entry,
    get_food_diary_day,
    preview_diary_day,
    preview_diary_meal,
    preview_diary_product,
    set_food_diary_day_status,
    update_food_diary_entry,
)
from fitminiapp_api.services.food_provider import (
    FoodProviderRegistry,
    get_food_provider_registry,
)
from fitminiapp_api.services.foods import (
    FoodConflictError,
    FoodError,
    FoodNotFoundError,
    create_user_food_response,
    delete_user_food,
    get_food_response,
    list_favorite_foods,
    list_frequent_foods,
    list_personal_foods,
    list_recent_foods,
    set_food_favorite,
    update_user_food,
)
from fitminiapp_api.services.grocery_list import (
    GroceryListConflictError,
    GroceryListError,
    GroceryListNotFoundError,
    add_manual_item,
    delete_grocery_item,
    generate_grocery_list,
    get_grocery_list,
    update_grocery_item,
)
from fitminiapp_api.services.hydration import (
    HydrationConflictError,
    HydrationError,
    create_hydration_entry,
    delete_hydration_entry,
    delete_hydration_preset,
    list_hydration_day,
    save_hydration_goal,
    save_hydration_preset,
    update_hydration_entry,
)
from fitminiapp_api.services.nutrition import (
    NutritionConflictError,
    NutritionEnergyMismatchError,
    NutritionError,
    build_nutrition_target_response_for_user,
    get_current_nutrition_target,
    list_nutrition_target_history,
    save_manual_nutrition_target,
    save_nutrition_target,
)
from fitminiapp_api.services.nutrition_label import (
    NutritionLabelError,
    cancel_label_draft,
    confirm_label_draft,
    create_label_draft,
    get_label_draft,
)
from fitminiapp_api.services.nutrition_plan import (
    NutritionPlanConflictError,
    NutritionPlanError,
    NutritionPlanNotFoundError,
    add_plan_item,
    copy_plan_day,
    delete_plan_item,
    fill_plan_from_suggestion,
    get_plan_day,
    get_plan_fill_suggestions,
    get_plan_week,
    perform_plan_item_action,
    update_plan_item,
)
from fitminiapp_api.services.nutrition_power import (
    NutritionPowerConflictError,
    NutritionPowerError,
    NutritionPowerNotFoundError,
    commit_natural_input,
    create_food_search_alias,
    create_meal_template,
    delete_food_search_alias,
    delete_meal_template,
    get_meal_template_response,
    insert_meal_template,
    list_food_search_aliases,
    list_meal_templates,
    preview_natural_input,
    update_food_search_alias,
    update_meal_template,
)
from fitminiapp_api.services.nutrition_suggestions import (
    commit_nutrition_suggestion,
    get_nutrition_suggestions,
)
from fitminiapp_api.services.photo_meal import (
    PhotoMealError,
    cancel_photo_meal_draft,
    confirm_photo_meal_draft,
    create_photo_meal_draft,
    get_photo_meal_draft,
)
from fitminiapp_api.services.recipes import (
    RecipeError,
    RecipeNotFoundError,
    create_recipe,
    delete_recipe,
    get_recipe_response,
    list_recipes,
    update_recipe,
)

router = APIRouter()


def _raise_food_http_error(exc: FoodError) -> None:
    if isinstance(exc, FoodNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, FoodConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _raise_diary_http_error(exc: FoodDiaryError) -> None:
    if isinstance(exc, FoodDiaryNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, FoodDiaryConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _raise_recipe_http_error(exc: RecipeError) -> None:
    if isinstance(exc, RecipeNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _raise_nutrition_power_http_error(exc: NutritionPowerError) -> None:
    if isinstance(exc, NutritionPowerNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, NutritionPowerConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _raise_nutrition_plan_http_error(exc: NutritionPlanError) -> None:
    if isinstance(exc, NutritionPlanNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, NutritionPlanConflictError):
        if exc.code is not None:
            raise HTTPException(
                status_code=409,
                detail={"code": exc.code, "message": str(exc), **exc.details},
            ) from exc
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _raise_grocery_list_http_error(exc: GroceryListError) -> None:
    if isinstance(exc, GroceryListNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, GroceryListConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _raise_nutrition_label_http_error(exc: NutritionLabelError) -> None:
    messages = {
        "feature_disabled": "Сканирование этикетки пока недоступно",
        "unsupported_mime": "Поддерживаются только JPEG, PNG и WebP",
        "invalid_image": "Файл не является допустимым изображением",
        "decode_failed": "Изображение не удалось безопасно прочитать",
        "oversized_image": "Изображение слишком большое",
        "retake_required": "Нужен более чёткий снимок этикетки",
        "local_ocr_unavailable": "Локальный OCR сейчас недоступен",
        "local_ocr_timeout": "Локальный OCR не завершился вовремя",
        "local_ocr_failed": "Локальный OCR не смог обработать изображение",
        "local_ocr_output_too_large": "Локальный OCR вернул слишком большой результат",
        "incomplete_required_facts": "Заполните обязательные значения перед подтверждением",
        "ambiguous_basis": "Уточните основу расчёта: 100 г, 100 мл или порция",
        "draft_expired": "Черновик истёк; начните сканирование заново",
        "draft_not_active": "Черновик уже закрыт",
        "stale_draft_revision": "Черновик изменился; обновите его перед подтверждением",
        "contribution_conflict": "Найден конфликт фактов продукта; данные не перезаписаны",
        "duplicate_barcode": "Продукт с этим штрихкодом уже существует",
        "sharing_requires_valid_gtin": "Для общего каталога нужен корректный GTIN",
    }
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": messages.get(exc.code, "Не удалось обработать черновик"),
        },
    ) from exc


def _raise_photo_meal_http_error(exc: PhotoMealError) -> None:
    messages = {
        "feature_disabled": "Фото блюда пока недоступно",
        "vision_unavailable": "Распознавание фото блюда сейчас недоступно; добавьте запись приблизительно",
        "vision_timeout": "Распознавание фото не завершилось вовремя; добавьте запись приблизительно",
        "vision_invalid_response": "Не удалось безопасно проверить результат распознавания",
        "vision_failed": "Распознавание фото временно недоступно; добавьте запись приблизительно",
        "manual_fallback_required": "На фото не удалось надёжно определить блюдо; добавьте его вручную",
        "draft_expired": "Черновик истёк; начните распознавание заново",
        "draft_not_active": "Черновик уже закрыт",
        "stale_draft_revision": "Черновик изменился; обновите его перед подтверждением",
        "unknown_candidate": "Изменённый состав блюда больше не соответствует черновику",
        "future_diary_date": "Нельзя добавить запись на будущую дату",
        "invalid_persisted_draft": "Черновик больше недоступен; начните заново",
    }
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": messages.get(exc.code, "Не удалось обработать фото блюда"),
        },
    ) from exc


IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]
OptionalIdempotencyKey = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]


@router.post(
    "/label-scans",
    response_model=NutritionLabelDraftResponse,
    status_code=status.HTTP_201_CREATED,
)
def recognize_nutrition_label(
    idempotency_key: IdempotencyKey,
    image: UploadFile = File(...),
    current_user: User = Depends(require_nutrition_label_scan),
    db: Session = Depends(get_db),
):
    try:
        image_bytes = image.file.read()
        return create_label_draft(
            db,
            current_user,
            image_bytes=image_bytes,
            content_type=image.content_type,
            idempotency_key=idempotency_key,
            vision_adapter=build_vision_fallback_adapter(),
        )
    except NutritionLabelError as exc:
        _raise_nutrition_label_http_error(exc)


@router.get("/label-scans/{draft_id}", response_model=NutritionLabelDraftResponse)
def read_nutrition_label_draft(
    draft_id: str,
    current_user: User = Depends(require_nutrition_label_scan),
    db: Session = Depends(get_db),
):
    try:
        return get_label_draft(db, current_user, draft_id)
    except NutritionLabelError as exc:
        _raise_nutrition_label_http_error(exc)


@router.post(
    "/label-scans/{draft_id}/confirm",
    response_model=NutritionLabelConfirmResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm_nutrition_label_draft(
    draft_id: str,
    payload: NutritionLabelConfirmRequest,
    current_user: User = Depends(require_nutrition_label_scan),
    db: Session = Depends(get_db),
):
    try:
        return confirm_label_draft(db, current_user, draft_id, payload)
    except NutritionLabelError as exc:
        _raise_nutrition_label_http_error(exc)


@router.post("/label-scans/{draft_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_nutrition_label_draft(
    draft_id: str,
    revision: int = Query(gt=0),
    current_user: User = Depends(require_nutrition_label_scan),
    db: Session = Depends(get_db),
):
    try:
        cancel_label_draft(db, current_user, draft_id, revision)
    except NutritionLabelError as exc:
        _raise_nutrition_label_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/photo-meals",
    response_model=PhotoMealDraftResponse,
    status_code=status.HTTP_201_CREATED,
)
def recognize_photo_meal(
    idempotency_key: IdempotencyKey,
    image: UploadFile = File(...),
    current_user: User = Depends(require_nutrition_label_scan),
    db: Session = Depends(get_db),
):
    try:
        return create_photo_meal_draft(
            db,
            current_user,
            image_bytes=image.file.read(),
            content_type=image.content_type,
            idempotency_key=idempotency_key,
            vision_adapter=build_meal_vision_adapter(),
        )
    except PhotoMealError as exc:
        _raise_photo_meal_http_error(exc)


@router.get("/photo-meals/{draft_id}", response_model=PhotoMealDraftResponse)
def read_photo_meal_draft(
    draft_id: str,
    current_user: User = Depends(require_nutrition_label_scan),
    db: Session = Depends(get_db),
):
    try:
        return get_photo_meal_draft(db, current_user, draft_id)
    except PhotoMealError as exc:
        _raise_photo_meal_http_error(exc)


@router.post(
    "/photo-meals/{draft_id}/confirm",
    response_model=PhotoMealConfirmResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm_photo_meal(
    draft_id: str,
    payload: PhotoMealConfirmRequest,
    current_user: User = Depends(require_nutrition_label_scan),
    db: Session = Depends(get_db),
):
    try:
        return confirm_photo_meal_draft(db, current_user, draft_id, payload)
    except PhotoMealError as exc:
        _raise_photo_meal_http_error(exc)


@router.post("/photo-meals/{draft_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_photo_meal(
    draft_id: str,
    revision: int = Query(gt=0),
    current_user: User = Depends(require_nutrition_label_scan),
    db: Session = Depends(get_db),
):
    try:
        cancel_photo_meal_draft(db, current_user, draft_id, revision)
    except PhotoMealError as exc:
        _raise_photo_meal_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _raise_hydration_http_error(exc: HydrationError) -> None:
    if isinstance(exc, HydrationConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if str(exc) in {"Запись не найдена", "Сосуд не найден"}:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/hydration", response_model=HydrationDayResponse)
def hydration_day(
    diary_date: date,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return list_hydration_day(db, current_user, diary_date)


@router.post(
    "/hydration/entries",
    response_model=HydrationEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_hydration_entry(
    payload: HydrationEntryCreate,
    idempotency_key: IdempotencyKey,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return create_hydration_entry(db, current_user, payload, idempotency_key)
    except HydrationError as exc:
        _raise_hydration_http_error(exc)


@router.patch("/hydration/entries/{entry_id}", response_model=HydrationEntryResponse)
def edit_hydration_entry(
    entry_id: int,
    payload: HydrationEntryUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return update_hydration_entry(db, current_user, entry_id, payload)
    except HydrationError as exc:
        _raise_hydration_http_error(exc)


@router.delete("/hydration/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_hydration_entry(
    entry_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        delete_hydration_entry(db, current_user, entry_id)
    except HydrationError as exc:
        _raise_hydration_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/hydration/goal", response_model=HydrationGoalResponse)
def save_goal_hydration(
    payload: HydrationGoalSave,
    idempotency_key: IdempotencyKey,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return save_hydration_goal(db, current_user, payload, idempotency_key)
    except HydrationError as exc:
        _raise_hydration_http_error(exc)


@router.post("/hydration/presets", response_model=HydrationPresetResponse)
def save_preset_hydration(
    payload: HydrationPresetSave,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return save_hydration_preset(db, current_user, payload)
    except HydrationError as exc:
        _raise_hydration_http_error(exc)


@router.delete("/hydration/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_preset_hydration(
    preset_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        delete_hydration_preset(db, current_user, preset_id)
    except HydrationError as exc:
        _raise_hydration_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/energy-calibration/preview",
    response_model=EnergyCalibrationResponse,
)
def preview_calibration(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return preview_energy_calibration(db, current_user)


@router.get(
    "/energy-calibration/history",
    response_model=EnergyCalibrationHistoryResponse,
)
def calibration_history(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return {"items": list_energy_calibrations(db, current_user)}


@router.post(
    "/energy-calibration/{calibration_id}/decision",
    response_model=EnergyCalibrationResponse,
)
def decide_calibration(
    calibration_id: int,
    payload: EnergyCalibrationDecision,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return decide_energy_calibration(
            db,
            current_user,
            calibration_id,
            payload.decision,
        )
    except EnergyCalibrationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except EnergyCalibrationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post(
    "/foods",
    response_model=FoodResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_food(
    payload: UserFoodCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return create_user_food_response(db, current_user, payload)
    except FoodError as exc:
        _raise_food_http_error(exc)


@router.get("/foods/search", response_model=FoodSearchResponse)
def search_food_library(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10_000),
    include_external: bool = False,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
    registry: FoodProviderRegistry = Depends(get_food_provider_registry),
):
    try:
        return search_food_catalog(
            db,
            current_user,
            q,
            limit=limit,
            offset=offset,
            include_external=include_external,
            registry=registry,
        )
    except FoodError as exc:
        _raise_food_http_error(exc)


@router.get("/foods/barcode/{barcode}", response_model=FoodBarcodeLookupResponse)
def get_food_by_barcode(
    barcode: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
    registry: FoodProviderRegistry = Depends(get_food_provider_registry),
):
    try:
        normalized = validate_gtin(barcode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if normalized is None:
        raise HTTPException(status_code=422, detail="barcode is required")
    return get_food_catalog_item_by_barcode(
        db,
        current_user,
        normalized,
        registry=registry,
    )


@router.get("/foods/recent", response_model=FoodListResponse)
def get_recent_foods(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10_000),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return list_recent_foods(db, current_user, limit=limit, offset=offset)


@router.get("/foods/frequent", response_model=FoodListResponse)
def get_frequent_foods(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10_000),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return list_frequent_foods(db, current_user, limit=limit, offset=offset)


@router.get("/foods/mine", response_model=FoodListResponse)
def get_personal_foods(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10_000),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return list_personal_foods(db, current_user, limit=limit, offset=offset)


@router.get("/foods/favorites", response_model=FoodListResponse)
def get_favorite_foods(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10_000),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return list_favorite_foods(db, current_user, limit=limit, offset=offset)


@router.get("/foods/{food_id}", response_model=FoodResponse)
def get_food(
    food_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return get_food_response(db, current_user, food_id)
    except FoodError as exc:
        _raise_food_http_error(exc)


@router.patch("/foods/{food_id}", response_model=FoodResponse)
def update_food(
    food_id: int,
    payload: UserFoodUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return update_user_food(db, current_user, food_id, payload)
    except FoodError as exc:
        _raise_food_http_error(exc)


@router.delete("/foods/{food_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_food(
    food_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        delete_user_food(db, current_user, food_id)
    except FoodError as exc:
        _raise_food_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/foods/{food_id}/favorite", response_model=FoodResponse)
def add_food_favorite(
    food_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return set_food_favorite(db, current_user, food_id, favorite=True)
    except FoodError as exc:
        _raise_food_http_error(exc)


@router.delete("/foods/{food_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
def remove_food_favorite(
    food_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        set_food_favorite(db, current_user, food_id, favorite=False)
    except FoodError as exc:
        _raise_food_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/recipes",
    response_model=RecipeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user_recipe(
    payload: RecipeCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return create_recipe(db, current_user, payload)
    except RecipeError as exc:
        _raise_recipe_http_error(exc)


@router.get("/recipes", response_model=RecipeListResponse)
def get_recipes(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10_000),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return list_recipes(db, current_user, limit=limit, offset=offset)


@router.get("/recipes/{recipe_id}", response_model=RecipeResponse)
def get_recipe(
    recipe_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return get_recipe_response(db, current_user, recipe_id)
    except RecipeError as exc:
        _raise_recipe_http_error(exc)


@router.patch("/recipes/{recipe_id}", response_model=RecipeResponse)
def patch_recipe(
    recipe_id: int,
    payload: RecipeUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return update_recipe(db, current_user, recipe_id, payload)
    except RecipeError as exc:
        _raise_recipe_http_error(exc)


@router.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_recipe(
    recipe_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        delete_recipe(db, current_user, recipe_id)
    except RecipeError as exc:
        _raise_recipe_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/templates",
    response_model=NutritionMealTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_nutrition_meal_template(
    payload: NutritionMealTemplateCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return create_meal_template(db, current_user, payload)
    except NutritionPowerError as exc:
        _raise_nutrition_power_http_error(exc)


@router.get("/templates", response_model=NutritionMealTemplateListResponse)
def get_nutrition_meal_templates(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return list_meal_templates(db, current_user, limit=limit, offset=offset)


@router.get("/templates/{template_id}", response_model=NutritionMealTemplateResponse)
def get_nutrition_meal_template(
    template_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return get_meal_template_response(db, current_user, template_id)
    except NutritionPowerError as exc:
        _raise_nutrition_power_http_error(exc)


@router.patch("/templates/{template_id}", response_model=NutritionMealTemplateResponse)
def patch_nutrition_meal_template(
    template_id: int,
    payload: NutritionMealTemplateUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return update_meal_template(db, current_user, template_id, payload)
    except NutritionPowerError as exc:
        _raise_nutrition_power_http_error(exc)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_nutrition_meal_template(
    template_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        delete_meal_template(db, current_user, template_id)
    except NutritionPowerError as exc:
        _raise_nutrition_power_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/templates/{template_id}/entries",
    response_model=FoodDiaryBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_nutrition_meal_template(
    template_id: int,
    payload: NutritionMealTemplateInsertRequest,
    idempotency_key: IdempotencyKey,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return insert_meal_template(db, current_user, template_id, payload, idempotency_key)
    except NutritionPowerError as exc:
        _raise_nutrition_power_http_error(exc)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.get("/food-aliases", response_model=FoodSearchAliasListResponse)
def get_food_search_aliases(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return list_food_search_aliases(db, current_user)


@router.post(
    "/food-aliases",
    response_model=FoodSearchAliasResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_food_search_alias(
    payload: FoodSearchAliasCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return create_food_search_alias(db, current_user, payload)
    except NutritionPowerError as exc:
        _raise_nutrition_power_http_error(exc)


@router.patch("/food-aliases/{alias_id}", response_model=FoodSearchAliasResponse)
def patch_food_search_alias(
    alias_id: int,
    payload: FoodSearchAliasUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return update_food_search_alias(db, current_user, alias_id, payload)
    except NutritionPowerError as exc:
        _raise_nutrition_power_http_error(exc)


@router.delete("/food-aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_food_search_alias(
    alias_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        delete_food_search_alias(db, current_user, alias_id)
    except NutritionPowerError as exc:
        _raise_nutrition_power_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/plans/day", response_model=NutritionPlanDayResponse)
def nutrition_plan_day(
    plan_date: date | None = Query(default=None),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return get_plan_day(db, current_user, plan_date)


@router.get("/grocery-list", response_model=GroceryListResponse)
def nutrition_grocery_list(
    week_start: date = Query(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return get_grocery_list(db, current_user, week_start)


@router.put("/grocery-list", response_model=GroceryListResponse)
def generate_nutrition_grocery_list(
    payload: GroceryListGenerateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return generate_grocery_list(db, current_user, payload.week_start)
    except GroceryListError as exc:
        _raise_grocery_list_http_error(exc)


@router.post(
    "/grocery-list/items",
    response_model=GroceryListResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_nutrition_grocery_item(
    payload: GroceryListManualItemCreate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return add_manual_item(db, current_user, payload)
    except GroceryListError as exc:
        _raise_grocery_list_http_error(exc)


@router.patch("/grocery-list/items/{item_id}", response_model=GroceryListResponse)
def patch_nutrition_grocery_item(
    item_id: int,
    payload: GroceryListItemUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return update_grocery_item(db, current_user, item_id, payload)
    except GroceryListError as exc:
        _raise_grocery_list_http_error(exc)


@router.delete("/grocery-list/items/{item_id}", response_model=GroceryListResponse)
def remove_nutrition_grocery_item(
    item_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return delete_grocery_item(db, current_user, item_id)
    except GroceryListError as exc:
        _raise_grocery_list_http_error(exc)


@router.get("/plans/week", response_model=NutritionPlanWeekResponse)
def nutrition_plan_week(
    week_start: date | None = Query(default=None),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return get_plan_week(db, current_user, week_start)


@router.get("/plans/suggestions", response_model=NutritionSuggestionsResponse)
def get_plan_suggestions(
    plan_date: date | None = Query(default=None),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return get_plan_fill_suggestions(db, current_user, plan_date)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.post(
    "/plans/fill",
    response_model=NutritionPlanDayResponse,
    status_code=status.HTTP_201_CREATED,
)
def fill_nutrition_plan(
    payload: NutritionPlanFillRequest,
    idempotency_key: IdempotencyKey,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return fill_plan_from_suggestion(db, current_user, payload, idempotency_key)
    except NutritionPlanError as exc:
        _raise_nutrition_plan_http_error(exc)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.post(
    "/plans/items",
    response_model=NutritionPlanDayResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_nutrition_plan_item(
    payload: NutritionPlanItemCreate,
    idempotency_key: IdempotencyKey,
    plan_date: date,
    meal_type: MealType,
    expected_revision: int = Query(ge=0),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return add_plan_item(
            db,
            current_user,
            payload,
            plan_date=plan_date,
            meal_type=meal_type,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )
    except NutritionPlanError as exc:
        _raise_nutrition_plan_http_error(exc)


@router.patch("/plans/items/{item_id}", response_model=NutritionPlanDayResponse)
def patch_nutrition_plan_item(
    item_id: int,
    payload: NutritionPlanItemUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return update_plan_item(db, current_user, item_id, payload)
    except NutritionPlanError as exc:
        _raise_nutrition_plan_http_error(exc)


@router.post(
    "/plans/items/{item_id}/action",
    response_model=NutritionPlanItemActionResponse,
)
def action_nutrition_plan_item(
    item_id: int,
    payload: NutritionPlanItemActionRequest,
    idempotency_key: IdempotencyKey,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return perform_plan_item_action(db, current_user, item_id, payload, idempotency_key)
    except NutritionPlanError as exc:
        _raise_nutrition_plan_http_error(exc)


@router.delete("/plans/items/{item_id}", response_model=NutritionPlanDayResponse)
def remove_nutrition_plan_item(
    item_id: int,
    expected_revision: int = Query(ge=0),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return delete_plan_item(db, current_user, item_id, expected_revision)
    except NutritionPlanError as exc:
        _raise_nutrition_plan_http_error(exc)


@router.post("/plans/copy", response_model=NutritionPlanDayResponse)
def copy_nutrition_plan_day(
    payload: NutritionPlanCopyRequest,
    idempotency_key: IdempotencyKey,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return copy_plan_day(db, current_user, payload, idempotency_key)
    except NutritionPlanError as exc:
        _raise_nutrition_plan_http_error(exc)


@router.get("/diary", response_model=FoodDiaryDayResponse)
def get_diary_day(
    diary_date: date | None = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return get_food_diary_day(db, current_user, diary_date)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.get("/diary/suggestions", response_model=NutritionSuggestionsResponse)
def get_diary_suggestions(
    diary_date: date | None = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return get_nutrition_suggestions(db, current_user, diary_date)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.post(
    "/diary/suggestions/commit",
    response_model=FoodDiaryBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def commit_diary_suggestion(
    payload: NutritionSuggestionCommitRequest,
    idempotency_key: IdempotencyKey,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return commit_nutrition_suggestion(db, current_user, payload, idempotency_key)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.post(
    "/diary/natural-input/preview",
    response_model=NaturalInputPreviewResponse,
)
def preview_nutrition_natural_input(
    payload: NaturalInputPreviewRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return preview_natural_input(db, current_user, payload.text)
    except NutritionPowerError as exc:
        _raise_nutrition_power_http_error(exc)


@router.post(
    "/diary/natural-input/commit",
    response_model=FoodDiaryBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def commit_nutrition_natural_input(
    payload: NaturalInputCommitRequest,
    idempotency_key: IdempotencyKey,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return commit_natural_input(db, current_user, payload, idempotency_key)
    except NutritionPowerError as exc:
        _raise_nutrition_power_http_error(exc)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.post(
    "/diary/entries",
    response_model=FoodDiaryEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_diary_entry(
    payload: FoodDiaryEntryCreate,
    idempotency_key: OptionalIdempotencyKey = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return create_food_diary_entry(db, current_user, payload, idempotency_key)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.put("/diary/status", response_model=FoodDiaryDayResponse)
def update_diary_day_status(
    payload: FoodDiaryDayStatusUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return set_food_diary_day_status(db, current_user, payload)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.patch("/diary/entries/{entry_id}", response_model=FoodDiaryEntryResponse)
def update_diary_entry(
    entry_id: int,
    payload: FoodDiaryEntryUpdate,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return update_food_diary_entry(db, current_user, entry_id, payload)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.delete("/diary/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_diary_entry(
    entry_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        delete_food_diary_entry(db, current_user, entry_id)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/diary/copy/product/preview",
    response_model=FoodDiaryCopyPreviewResponse,
)
def preview_copy_product(
    payload: FoodDiaryCopyProductPreview,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return preview_diary_product(db, current_user, payload)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.post(
    "/diary/copy/meal/preview",
    response_model=FoodDiaryCopyPreviewResponse,
)
def preview_copy_meal(
    payload: FoodDiaryCopyMealPreview,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return preview_diary_meal(db, current_user, payload)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.post(
    "/diary/copy/day/preview",
    response_model=FoodDiaryCopyPreviewResponse,
)
def preview_copy_day(
    payload: FoodDiaryCopyDayPreview,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return preview_diary_day(db, current_user, payload)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.post(
    "/diary/copy/product",
    response_model=FoodDiaryCopyResponse,
    status_code=status.HTTP_201_CREATED,
)
def copy_product(
    payload: FoodDiaryCopyProduct,
    idempotency_key: IdempotencyKey,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return copy_diary_product(db, current_user, payload, idempotency_key)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.post(
    "/diary/copy/meal",
    response_model=FoodDiaryCopyResponse,
    status_code=status.HTTP_201_CREATED,
)
def copy_meal(
    payload: FoodDiaryCopyMeal,
    idempotency_key: IdempotencyKey,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return copy_diary_meal(db, current_user, payload, idempotency_key)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.post(
    "/diary/copy/day",
    response_model=FoodDiaryCopyResponse,
    status_code=status.HTTP_201_CREATED,
)
def copy_day(
    payload: FoodDiaryCopyDay,
    idempotency_key: IdempotencyKey,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return copy_diary_day(db, current_user, payload, idempotency_key)
    except FoodDiaryError as exc:
        _raise_diary_http_error(exc)


@router.post("/targets", response_model=NutritionTargetResponse)
def save_target(
    payload: NutritionTargetSave,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return save_nutrition_target(db, current_user, payload)
    except NutritionError as exc:
        detail = str(exc)
        if detail == "Target user not found":
            raise HTTPException(status_code=404, detail=detail)
        if detail == "No permission to manage this user":
            raise HTTPException(status_code=403, detail=detail)
        if isinstance(exc, NutritionConflictError):
            raise HTTPException(status_code=409, detail=detail)
        raise HTTPException(status_code=400, detail=detail)


@router.post("/targets/manual", response_model=NutritionTargetResponse)
def save_manual_target(
    payload: NutritionManualTargetSave,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return save_manual_nutrition_target(db, current_user, payload)
    except NutritionError as exc:
        detail = str(exc)
        if detail == "Target user not found":
            raise HTTPException(status_code=404, detail=detail)
        if detail == "No permission to manage this user":
            raise HTTPException(status_code=403, detail=detail)
        if isinstance(exc, NutritionEnergyMismatchError):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "nutrition_energy_mismatch",
                    "message": detail,
                    "implied_energy_kcal": exc.implied_energy_kcal,
                    "difference_kcal": exc.difference_kcal,
                },
            )
        if isinstance(exc, NutritionConflictError):
            raise HTTPException(status_code=409, detail=detail)
        raise HTTPException(status_code=400, detail=detail)


@router.get("/targets/current", response_model=NutritionTargetResponse | None)
def current_target(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    target = get_current_nutrition_target(db, current_user.id)
    return build_nutrition_target_response_for_user(db, target, current_user)


@router.get("/targets/history", response_model=NutritionTargetHistoryResponse)
def target_history(
    target_telegram_user_id: int | None = Query(default=None, ge=1),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return {
            "items": list_nutrition_target_history(
                db,
                current_user,
                target_telegram_user_id,
            )
        }
    except NutritionError as exc:
        detail = str(exc)
        if detail == "Target user not found":
            raise HTTPException(status_code=404, detail=detail)
        if detail == "No permission to manage this user":
            raise HTTPException(status_code=403, detail=detail)
        raise HTTPException(status_code=400, detail=detail)
