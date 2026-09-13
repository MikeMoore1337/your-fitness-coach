from typing import Literal, cast

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value
from starlette.concurrency import run_in_threadpool

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.rate_limit import limiter
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.account import AccountDataExport
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.program import UserProgram, UserWorkout
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.schemas.acquisition import FirstTouchAttributionRequest
from fitminiapp_api.schemas.invite import CoachInvitePreviewResponse, CoachInviteTokenRequest
from fitminiapp_api.schemas.trainer_capability import (
    TrainerCapabilityActivateRequest,
    TrainerCapabilityResponse,
)
from fitminiapp_api.schemas.user import (
    AccountDeleteRequest,
    AccountExportDownloadLinkResponse,
    AccountExportStatusResponse,
    AvatarMetadataResponse,
    BodyPriorityOptionsResponse,
    BodyPriorityPreference,
    HeartRatePreviewRequest,
    HeartRatePreviewResponse,
    HeartRateRangeResponse,
    HeartRateZoneResponse,
    OAuthLinkCreateResponse,
    TelegramLinkCreateResponse,
    TrainerResponse,
    UserProfileResponse,
    UserProfileUpdate,
    UserResponse,
)
from fitminiapp_api.services.account_exports import (
    AccountExportError,
    account_export_by_download_token,
    build_account_export_archive,
    complete_account_export,
    create_account_export_download_token,
    expire_account_export,
    fail_account_export,
    lock_account_export_generation,
    start_account_export,
)
from fitminiapp_api.services.account_identities import (
    IdentityNotFoundError,
    LastIdentityError,
    ProtectedIdentityError,
    unlink_auth_identity,
)
from fitminiapp_api.services.account_linking import (
    OAUTH_LINK_PROVIDERS,
    OAuthLinkConflictError,
    OAuthLinkError,
    TelegramLinkConflictError,
    TelegramLinkError,
    create_oauth_link_url,
    create_telegram_link_url,
)
from fitminiapp_api.services.accounts import build_account_export, delete_user_cascade
from fitminiapp_api.services.acquisition import save_first_touch_attribution
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.avatars import (
    AVATAR_UPLOAD_MAX_BYTES,
    AvatarValidationError,
    delete_user_avatar,
    process_avatar_image,
    save_user_avatar,
)
from fitminiapp_api.services.coach_clients import (
    confirm_coach_invite_link,
    get_current_trainer,
    preview_coach_invite_link,
    remove_current_trainer,
)
from fitminiapp_api.services.exercise_domain import BODY_PRIORITY_TAXONOMY
from fitminiapp_api.services.nutrition import (
    NutritionError,
    build_nutrition_target_response_for_user,
    get_current_nutrition_target,
)
from fitminiapp_api.services.onboarding import build_onboarding_state
from fitminiapp_api.services.profile import (
    ProfileError,
    calculate_profile_heart_rates,
    serialize_body_priority,
    update_profile,
)
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.root_admin import has_verified_root_identity, is_root_user
from fitminiapp_api.services.security import get_current_user
from fitminiapp_api.services.trainer_capability import (
    activate_trainer_capability,
    deactivate_trainer_capability,
    trainer_capability_state,
)
from fitminiapp_api.services.training_preferences import serialize_training_preferences

router = APIRouter()


def _account_export_status(row: AccountDataExport | None) -> AccountExportStatusResponse:
    if row is None:
        return AccountExportStatusResponse(status="none")
    return AccountExportStatusResponse(
        status=cast(
            Literal["none", "generating", "ready", "expired", "error"],
            row.status,
        ),
        export_id=row.export_id,
        created_at=row.created_at,
        completed_at=row.completed_at,
        expires_at=row.expires_at,
        filename=row.filename,
        content_size_bytes=row.content_size_bytes,
        error_code=row.error_code,
    )


def _account_export_file_response(row: AccountDataExport) -> Response:
    if row.archive_bytes is None or row.filename is None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Архив больше недоступен")
    archive_bytes = bytes(row.archive_bytes)
    return Response(
        content=archive_bytes,
        media_type="application/zip",
        headers={
            "Cache-Control": "no-store, private",
            "Content-Disposition": f'attachment; filename="{row.filename}"',
            "Content-Length": str(len(archive_bytes)),
        },
    )


def _heart_rate_response(heart_rates) -> HeartRatePreviewResponse:
    return HeartRatePreviewResponse(
        estimated_max_heart_rate=heart_rates.maximum,
        heart_rate_reserve=heart_rates.reserve,
        heart_rate_calculation_method=(
            "heart_rate_reserve" if heart_rates.is_personalized else "percent_maximum"
        ),
        heart_rate_zones=[HeartRateZoneResponse(**vars(zone)) for zone in heart_rates.zones],
        recommended_cardio_range=(
            HeartRateRangeResponse(**vars(heart_rates.recommended_cardio_range))
            if heart_rates.recommended_cardio_range
            else None
        ),
    )


def _build_user_response(db: Session, user) -> UserResponse:
    active_program_exists = db.query(UserProgram.id).filter(
        UserProgram.user_id == user.id,
        UserProgram.is_active.is_(True),
    )
    workout_history_exists = (
        db.query(UserWorkout.id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(UserProgram.user_id == user.id, UserWorkout.status == "completed")
    )
    food_history_exists = db.query(FoodDiaryEntry.id).filter(FoodDiaryEntry.user_id == user.id)
    has_active_program, has_workout_history, has_food_history, profile = (
        db.query(
            active_program_exists.exists(),
            workout_history_exists.exists(),
            food_history_exists.exists(),
            UserProfile,
        )
        .select_from(User)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .filter(User.id == user.id)
        .one()
    )
    set_committed_value(user, "profile", profile)
    target = get_current_nutrition_target(db, user.id)
    kbju = build_nutrition_target_response_for_user(db, target, user)
    trainer = get_current_trainer(db, user)
    heart_rates = calculate_profile_heart_rates(
        user.profile.birth_date if user.profile else None,
        user.profile.resting_heart_rate if user.profile else None,
        user.profile.goal if user.profile else None,
    )
    return UserResponse(
        id=user.id,
        telegram_user_id=user.telegram_user_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        photo_url=user.photo_url,
        custom_avatar=(
            AvatarMetadataResponse(
                content_type="image/webp",
                byte_size=user.custom_avatar_byte_size,
                width=512,
                height=512,
                updated_at=user.custom_avatar_updated_at,
            )
            if user.custom_avatar_updated_at is not None
            else None
        ),
        is_coach=user.is_coach,
        is_admin=user.is_admin,
        is_root=has_verified_root_identity(db, user),
        has_active_program=has_active_program,
        has_workout_history=has_workout_history,
        has_food_history=has_food_history,
        auth_providers=sorted(identity.provider for identity in user.auth_identities),
        onboarding=build_onboarding_state(user.profile),
        profile=UserProfileResponse(
            full_name=user.profile.full_name if user.profile else None,
            birth_date=user.profile.birth_date if user.profile else None,
            sex=user.profile.sex if user.profile else None,
            goal=user.profile.goal if user.profile else None,
            level=user.profile.level if user.profile else None,
            height_cm=user.profile.height_cm if user.profile else None,
            weight_kg=user.profile.weight_kg if user.profile else None,
            workouts_per_week=user.profile.workouts_per_week if user.profile else None,
            cardio_trainings_per_week=(
                user.profile.cardio_trainings_per_week if user.profile else None
            ),
            resting_heart_rate=user.profile.resting_heart_rate if user.profile else None,
            body_priority=(
                BodyPriorityPreference.model_validate(body_priority)
                if (body_priority := serialize_body_priority(user.profile)) is not None
                else None
            ),
            training_preferences=(
                serialize_training_preferences(db, user, user.profile) if user.profile else None
            ),
            timezone=user.profile.timezone if user.profile else "Europe/Moscow",
            estimated_max_heart_rate=heart_rates.maximum if heart_rates else None,
            heart_rate_reserve=heart_rates.reserve if heart_rates else None,
            heart_rate_calculation_method=(
                "heart_rate_reserve"
                if heart_rates and heart_rates.is_personalized
                else "percent_maximum"
                if heart_rates
                else None
            ),
            heart_rate_zones=(
                [HeartRateZoneResponse(**vars(zone)) for zone in heart_rates.zones]
                if heart_rates
                else []
            ),
            recommended_cardio_range=(
                HeartRateRangeResponse(**vars(heart_rates.recommended_cardio_range))
                if heart_rates and heart_rates.recommended_cardio_range
                else None
            ),
            kbju=kbju,
        )
        if user.profile or kbju
        else None,
        trainer=TrainerResponse(**trainer) if trainer else None,
    )


@router.get("", response_model=UserResponse)
def read_me(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return _build_user_response(db, user)


@router.post("/acquisition", status_code=status.HTTP_204_NO_CONTENT)
def save_acquisition(
    payload: FirstTouchAttributionRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    save_first_touch_attribution(db, user, payload)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/avatar")
def read_avatar(user=Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    avatar = (
        db.query(
            User.custom_avatar_image_bytes,
            User.custom_avatar_content_type,
            User.custom_avatar_byte_size,
            User.custom_avatar_sha256,
        )
        .filter(User.id == user.id, User.custom_avatar_updated_at.is_not(None))
        .first()
    )
    if avatar is None or any(value is None for value in avatar):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Свой аватар не установлен"
        )
    image_bytes, content_type, byte_size, sha256 = avatar
    return Response(
        content=bytes(image_bytes),
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Length": str(byte_size),
            "ETag": f'"{sha256}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.put("/avatar", response_model=UserResponse)
@limiter.limit("10/hour")
async def replace_avatar(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    del request
    try:
        source = await file.read(AVATAR_UPLOAD_MAX_BYTES + 1)
    finally:
        await file.close()
    try:
        processed = await run_in_threadpool(process_avatar_image, source)
    except AvatarValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    replacing = user.custom_avatar_updated_at is not None
    current = save_user_avatar(db, user.id, processed)
    record_audit_event(
        db,
        action="account.avatar_replaced" if replacing else "account.avatar_created",
        resource_type="user_avatar",
        actor_user_id=user.id,
        target_user_id=user.id,
        resource_id=str(user.id),
        details={
            "content_type": current.custom_avatar_content_type,
            "byte_size": current.custom_avatar_byte_size,
            "width": current.custom_avatar_width,
            "height": current.custom_avatar_height,
        },
    )
    db.commit()
    return _build_user_response(db, user)


@router.delete("/avatar", response_model=UserResponse)
def remove_avatar(user=Depends(get_current_user), db: Session = Depends(get_db)) -> UserResponse:
    deleted = delete_user_avatar(db, user.id)
    if deleted:
        record_audit_event(
            db,
            action="account.avatar_deleted",
            resource_type="user_avatar",
            actor_user_id=user.id,
            target_user_id=user.id,
            resource_id=str(user.id),
        )
    db.commit()
    return _build_user_response(db, user)


@router.get("/trainer-capability", response_model=TrainerCapabilityResponse)
def read_trainer_capability(user=Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return trainer_capability_state(db, user)


@router.post("/trainer-capability", response_model=TrainerCapabilityResponse)
def enable_trainer_capability(
    _: TrainerCapabilityActivateRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return activate_trainer_capability(db, user)


@router.delete("/trainer-capability", response_model=TrainerCapabilityResponse)
def disable_trainer_capability(
    user=Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return deactivate_trainer_capability(db, user)


@router.post("/auth/telegram-link", response_model=TelegramLinkCreateResponse)
def create_telegram_link(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramLinkCreateResponse:
    try:
        telegram_url, expires_in_seconds = create_telegram_link_url(
            db,
            user,
            settings.telegram_bot_username,
            session_family_id=request.state.session_family_id,
        )
    except TelegramLinkConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TelegramLinkError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()
    return TelegramLinkCreateResponse(
        telegram_url=telegram_url,
        expires_in_seconds=expires_in_seconds,
    )


@router.post("/auth/oauth-link/{provider}", response_model=OAuthLinkCreateResponse)
def create_oauth_link(
    request: Request,
    provider: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OAuthLinkCreateResponse:
    normalized_provider = provider.strip().lower()
    if (
        not settings.enable_web_auth
        or normalized_provider not in OAUTH_LINK_PROVIDERS
        or normalized_provider not in settings.oauth_provider_names
    ):
        raise HTTPException(status_code=404, detail="Провайдер входа не настроен")
    try:
        oauth_url, expires_in_seconds = create_oauth_link_url(
            db,
            user,
            normalized_provider,
            session_family_id=request.state.session_family_id,
        )
    except OAuthLinkConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OAuthLinkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return OAuthLinkCreateResponse(
        oauth_url=oauth_url,
        expires_in_seconds=expires_in_seconds,
    )


@router.delete("/auth/identities/{provider}", response_model=UserResponse)
def unlink_login_method(
    provider: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> UserResponse:
    try:
        unlink_auth_identity(db, user, provider)
    except IdentityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LastIdentityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ProtectedIdentityError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    db.commit()
    db.refresh(user)
    return _build_user_response(db, user)


@router.patch("/profile", response_model=UserResponse)
def patch_profile(
    payload: UserProfileUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    try:
        user = update_profile(db, user, payload)
    except (NutritionError, ProfileError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _build_user_response(db, user)


@router.get("/profile/body-priority-options", response_model=BodyPriorityOptionsResponse)
def body_priority_options(_user=Depends(get_current_user)) -> dict:
    return {
        "items": [{"id": identifier, "name": name} for identifier, name in BODY_PRIORITY_TAXONOMY]
    }


@router.post("/profile/heart-rates/preview", response_model=HeartRatePreviewResponse)
def preview_heart_rates(
    payload: HeartRatePreviewRequest,
    _user=Depends(get_current_user),
) -> HeartRatePreviewResponse:
    try:
        heart_rates = calculate_profile_heart_rates(
            payload.birth_date,
            payload.resting_heart_rate,
            payload.goal,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if heart_rates is None:  # The request schema requires birth_date.
        raise HTTPException(status_code=422, detail="Birth date is required")
    return _heart_rate_response(heart_rates)


@router.get("/export")
def export_account_data(
    user=Depends(get_current_user), db: Session = Depends(get_db)
) -> JSONResponse:
    payload = jsonable_encoder(build_account_export(db, user))
    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="fitmini-account-{user.id}.json"',
        },
    )


@router.get("/exports/current", response_model=AccountExportStatusResponse)
def current_account_export(
    user=Depends(get_current_user), db: Session = Depends(get_db)
) -> AccountExportStatusResponse:
    row = db.query(AccountDataExport).filter(AccountDataExport.user_id == user.id).first()
    if row is not None and expire_account_export(row):
        db.commit()
    return _account_export_status(row)


@router.post(
    "/exports",
    response_model=AccountExportStatusResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/hour")
def create_account_export(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountExportStatusResponse:
    del request
    row = start_account_export(db, user)
    generation_id = row.export_id
    db.commit()
    try:
        archive_bytes, filename = build_account_export_archive(db, user)
        current_row = lock_account_export_generation(db, user.id, generation_id)
        if current_row is None:
            latest = db.query(AccountDataExport).filter(AccountDataExport.user_id == user.id).one()
            return _account_export_status(latest)
        complete_account_export(current_row, archive_bytes, filename)
        record_audit_event(
            db,
            action="account.export_created",
            resource_type="account_data_export",
            actor_user_id=user.id,
            target_user_id=user.id,
            resource_id=current_row.export_id,
            details={"content_size_bytes": len(archive_bytes)},
        )
    except AccountExportError as exc:
        current_row = lock_account_export_generation(db, user.id, generation_id)
        if current_row is None:
            latest = db.query(AccountDataExport).filter(AccountDataExport.user_id == user.id).one()
            return _account_export_status(latest)
        fail_account_export(current_row, exc.error_code)
        record_audit_event(
            db,
            action="account.export_failed",
            resource_type="account_data_export",
            actor_user_id=user.id,
            target_user_id=user.id,
            resource_id=current_row.export_id,
            details={"error_code": exc.error_code},
        )
    except Exception as exc:
        db.rollback()
        current_row = lock_account_export_generation(db, user.id, generation_id)
        if current_row is None:
            latest = db.query(AccountDataExport).filter(AccountDataExport.user_id == user.id).one()
            return _account_export_status(latest)
        fail_account_export(current_row, "generation_failed")
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось подготовить архив данных",
        ) from exc
    db.commit()
    db.refresh(current_row)
    return _account_export_status(current_row)


@router.get("/exports/{export_id}/download")
def download_account_export(
    export_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    row = (
        db.query(AccountDataExport)
        .filter(
            AccountDataExport.user_id == user.id,
            AccountDataExport.export_id == export_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Архив не найден")
    if expire_account_export(row):
        db.commit()
    if row.status == "expired":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Срок хранения архива истёк")
    if row.status != "ready":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Архив ещё не готов")
    return _account_export_file_response(row)


@router.post(
    "/exports/{export_id}/download-link",
    response_model=AccountExportDownloadLinkResponse,
)
def create_account_export_download_link(
    export_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountExportDownloadLinkResponse:
    row = (
        db.query(AccountDataExport)
        .filter(
            AccountDataExport.user_id == user.id,
            AccountDataExport.export_id == export_id,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Архив не найден")
    if expire_account_export(row):
        db.commit()
    if row.status != "ready" or row.filename is None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Архив больше недоступен")
    token, expires_at = create_account_export_download_token(row)
    db.commit()
    return AccountExportDownloadLinkResponse(
        url=f"{settings.frontend_base_url.rstrip('/')}/api/v1/me/exports/file/{token}",
        filename=row.filename,
        expires_at=expires_at,
    )


@router.get("/exports/file/{download_token}")
def download_account_export_by_token(
    download_token: str,
    db: Session = Depends(get_db),
) -> Response:
    row = account_export_by_download_token(db, download_token)
    if row is None:
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка недействительна")
    response = _account_export_file_response(row)
    response.headers["Access-Control-Allow-Origin"] = "https://web.telegram.org"
    return response


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_own_account(
    payload: AccountDeleteRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    if is_root_user(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Удаление Root-аккаунта запрещено",
        )
    record_audit_event(
        db,
        action="account.self_deleted",
        resource_type="user",
        actor_user_id=user.id,
        target_user_id=user.id,
    )
    db.flush()
    delete_user_cascade(db, user)
    db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path="/api/v1/auth",
        secure=settings.app_env == "prod",
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.delete("/trainer", status_code=status.HTTP_204_NO_CONTENT)
def detach_trainer(db: Session = Depends(get_db), user=Depends(get_current_user)):
    remove_current_trainer(db, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/coach-invites/link/preview",
    response_model=CoachInvitePreviewResponse,
)
def preview_invite_link(
    payload: CoachInviteTokenRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> CoachInvitePreviewResponse:
    try:
        return CoachInvitePreviewResponse(**preview_coach_invite_link(db, user, payload.token))
    except ProgramError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/coach-invites/link/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
)
def confirm_invite_link(
    payload: CoachInviteTokenRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> Response:
    try:
        confirm_coach_invite_link(db, user, payload.token)
    except ProgramError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
