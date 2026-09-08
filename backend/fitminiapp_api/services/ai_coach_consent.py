from __future__ import annotations

from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.ai_coach import AiCoachConsent
from fitminiapp_api.models.user import User

AI_COACH_PERSONAL_CONSENT_VERSION = "ai-coach-personal-v1"
AI_COACH_PERSONAL_SCOPE = "personal_readonly_tools_v1"
AI_COACH_PERSONAL_PROVIDER = "groq"
AI_COACH_PERSONAL_CONSENT_SOURCE = "ai_coach_settings"
AI_COACH_PERSONAL_CATEGORIES = (
    "personal_progress",
    "training_history",
    "nutrition_summary",
)
AI_COACH_PERSONAL_PURPOSE = (
    "Одноразовое объяснение выбранных вами сводок прогресса, тренировок или питания."
)
AI_COACH_PERSONAL_RETENTION_NOTICE = (
    "Промпт, ответ и данные инструмента не сохраняются в истории; провайдер получает "
    "только ограниченный контекст текущего запроса по действующей политике сервиса."
)


def get_ai_coach_consent(db: Session, user_id: int) -> AiCoachConsent | None:
    return db.query(AiCoachConsent).filter(AiCoachConsent.user_id == user_id).one_or_none()


def has_active_ai_coach_consent(consent: AiCoachConsent | None) -> bool:
    return bool(
        consent
        and consent.status == "granted"
        and consent.scope == AI_COACH_PERSONAL_SCOPE
        and consent.consent_version == AI_COACH_PERSONAL_CONSENT_VERSION
        and consent.provider_name == AI_COACH_PERSONAL_PROVIDER
        and consent.provider_policy_revision == settings.ai_coach_policy_revision
        and consent.granted_at is not None
        and consent.revoked_at is None
    )


def set_ai_coach_consent(
    db: Session,
    *,
    user_id: int,
    enabled: bool,
) -> AiCoachConsent:
    # Lock the stable parent row first: FOR UPDATE cannot lock an absent consent
    # row, so two first-time grants would otherwise race on the unique user_id.
    db.query(User.id).filter(User.id == user_id).with_for_update().one()
    consent = (
        db.query(AiCoachConsent)
        .filter(AiCoachConsent.user_id == user_id)
        .with_for_update()
        .one_or_none()
    )
    now = now_msk_naive()
    if consent is None:
        consent = AiCoachConsent(
            user_id=user_id,
            status="revoked",
            scope=AI_COACH_PERSONAL_SCOPE,
            consent_version=AI_COACH_PERSONAL_CONSENT_VERSION,
            provider_name=AI_COACH_PERSONAL_PROVIDER,
            provider_policy_revision=settings.ai_coach_policy_revision,
            consent_source=AI_COACH_PERSONAL_CONSENT_SOURCE,
            created_at=now,
            updated_at=now,
        )
        db.add(consent)

    consent.scope = AI_COACH_PERSONAL_SCOPE
    consent.consent_version = AI_COACH_PERSONAL_CONSENT_VERSION
    consent.provider_name = AI_COACH_PERSONAL_PROVIDER
    consent.provider_policy_revision = settings.ai_coach_policy_revision
    consent.consent_source = AI_COACH_PERSONAL_CONSENT_SOURCE
    consent.status = "granted" if enabled else "revoked"
    consent.granted_at = now if enabled else consent.granted_at
    consent.revoked_at = None if enabled else now
    consent.updated_at = now
    db.flush()
    return consent


def serialize_ai_coach_consent(consent: AiCoachConsent | None) -> dict[str, object]:
    status = "granted" if has_active_ai_coach_consent(consent) else "revoked"
    return {
        "status": status,
        "scope": AI_COACH_PERSONAL_SCOPE,
        "consent_version": AI_COACH_PERSONAL_CONSENT_VERSION,
        "categories": AI_COACH_PERSONAL_CATEGORIES,
        "purpose": AI_COACH_PERSONAL_PURPOSE,
        "provider_name": AI_COACH_PERSONAL_PROVIDER,
        "provider_policy_revision": settings.ai_coach_policy_revision,
        "retention_notice": AI_COACH_PERSONAL_RETENTION_NOTICE,
        "consent_source": consent.consent_source if consent else AI_COACH_PERSONAL_CONSENT_SOURCE,
        "granted_at": consent.granted_at if consent and status == "granted" else None,
        "revoked_at": consent.revoked_at if consent and status == "revoked" else None,
    }


__all__ = [
    "AI_COACH_PERSONAL_CATEGORIES",
    "AI_COACH_PERSONAL_CONSENT_SOURCE",
    "AI_COACH_PERSONAL_CONSENT_VERSION",
    "AI_COACH_PERSONAL_PROVIDER",
    "AI_COACH_PERSONAL_PURPOSE",
    "AI_COACH_PERSONAL_RETENTION_NOTICE",
    "AI_COACH_PERSONAL_SCOPE",
    "get_ai_coach_consent",
    "has_active_ai_coach_consent",
    "serialize_ai_coach_consent",
    "set_ai_coach_consent",
]
