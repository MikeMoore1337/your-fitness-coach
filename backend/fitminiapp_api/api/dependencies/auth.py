from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.services.root_admin import has_verified_root_identity
from fitminiapp_api.services.security import get_current_user


def require_user(user: User = Depends(get_current_user)) -> User:
    return user


def is_ai_coach_cohort_user(user: User) -> bool:
    """Return whether the server-side internal beta boundary admits this account."""

    return bool(settings.ai_coach_ui_enabled and user.id in settings.ai_coach_internal_user_id_set)


def require_ai_coach_cohort(user: User = Depends(require_user)) -> User:
    """Protect every AI Coach generation path, including direct API callers."""

    if not is_ai_coach_cohort_user(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI Coach beta доступна только ограниченной внутренней когорте",
        )
    return user


def is_nutrition_label_scan_available(user: User) -> bool:
    """Apply the server-side feature flag and kill switch to every signed-in account."""

    return bool(
        settings.nutrition_label_scan_enabled and not settings.nutrition_label_scan_kill_switch
    )


def require_nutrition_label_scan(user: User = Depends(require_user)) -> User:
    if not is_nutrition_label_scan_available(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "feature_disabled",
                "message": "Сканирование этикетки пока недоступно",
            },
        )
    return user


def require_coach(user: User = Depends(require_user)) -> User:
    if not user.is_coach:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав тренера",
        )
    return user


def require_root_admin(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> User:
    if not has_verified_root_identity(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуется подтверждённая Root-сессия Telegram",
        )
    return user
