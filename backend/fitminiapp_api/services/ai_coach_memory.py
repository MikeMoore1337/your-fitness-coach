"""User-controlled, bounded AI Coach continuity memory.

This module deliberately exposes structured writes only. It never accepts a generic
memory string from a model and never stores prompts, answers or conversation history.
"""

from __future__ import annotations

import re
import unicodedata
from typing import cast

from sqlalchemy.orm import Session

from fitminiapp_api.ai_coach.contracts import (
    AiCoachMemoryCategory,
    AiCoachMemoryContext,
    AiCoachMemoryOrigin,
)
from fitminiapp_api.ai_coach.safety import SafetyCategory, classify_message
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.ai_coach import AiCoachMemory, AiCoachMemoryConsent
from fitminiapp_api.models.user import User

AI_COACH_MEMORY_CONSENT_VERSION = "ai-coach-memory-v1"
AI_COACH_MEMORY_SCOPE = "ai_coach_memory_v1"
AI_COACH_MEMORY_SOURCE = "ai_coach_memory_settings"
AI_COACH_MEMORY_MAX_ITEMS = 20
AI_COACH_MEMORY_MAX_VALUE_LENGTH = 240
AI_COACH_MEMORY_CATEGORIES = (
    "preferred_explanation_style",
    "ai_interaction_preferences",
    "stable_non_medical_preferences",
    "explicit_ai_context",
)
AI_COACH_MEMORY_CATEGORY_LABELS = {
    "preferred_explanation_style": "Стиль объяснений",
    "ai_interaction_preferences": "Предпочтения общения",
    "stable_non_medical_preferences": "Стабильные немедицинские предпочтения",
    "explicit_ai_context": "Явный контекст для AI Coach",
}
AI_COACH_MEMORY_PURPOSE = (
    "Небольшой набор явно подтверждённых предпочтений для более последовательного стиля "
    "объяснений AI Coach."
)
AI_COACH_MEMORY_RETENTION_NOTICE = (
    "Память хранится до удаления вами или удаления аккаунта. Пауза и отзыв сразу "
    "исключают её из новых запросов; prompt, ответ и история диалога не сохраняются."
)

_URL_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_FORBIDDEN_MEMORY_PATTERN = re.compile(
    r"(?:"
    r"диагноз\w*|диагностир\w*|лечени\w*|лекарств\w*|препарат\w*|"
    r"боль\w*|болит|травм\w*|перелом\w*|операци\w*|симптом\w*|"
    r"врач\w*|медицин\w*|беремен\w*|аллерг\w*|реабилитац\w*|"
    r"стероид\w*|анабол\w*|тестостерон\w*|sarm\w*|aas|допинг\w*|"
    r"наркот\w*|гормон\w*|инъекц\w*|антибиот\w*|"
    r"диабет\w*|гипертон\w*|астм\w*|эпилеп\w*|артрит\w*|артроз\w*|"
    r"сколиоз\w*|грыж\w*|заболев\w*|болезн\w*|синдром\w*|инвалид\w*|"
    r"онколог\w*|рак\b|давлен\w*|"
    r"депресс\w*|тревож\w*|псих\w*|ментальн\w*|самооцен\w*|"
    r"мотивац\w*|стресс\w*|эмоцион\w*|личност\w*|"
    r"расстройств\w*|выгорани\w*|паническ\w*|"
    r"тренер\w*|coach\s+data|клиент\w*|trainer\w*|"
    r"парол\w*|токен\w*|секрет\w*|api\s*key|private\s+key|"
    r"реклам\w*|продаж\w*|купи\w*|промокод\w*|"
    r"дневник\w*|истори\w*|съел\w*|питался\w*|"
    r"вчера|сегодня|завтра|за\s+(?:недел\w*|месяц\w*|период\w*)|"
    r"цель\w*|похуде\w*|набор\s+массы|вес\w*|рост\w*|возраст\w*|"
    r"калори\w*|ккал|кбжу|белк\w*|жир\w*|углевод\w*|"
    r"\bвод(?:а|у|ы|ой|е|ою)?\b|гидратац\w*|программ\w*|план\s+трениров\w*|"
    r"упражнен\w*|подход\w*|повтор\w*|сет\w*|кардио\w*|пульс\w*|"
    r"прогресс\w*|нагрузк\w*|оборудован\w*|инвентар\w*|"
    r"профил\w*|настройк\w*|замер\w*|сон\w*|настроен\w*|"
    r"(?:email|e-mail|телефон|phone|адрес|паспорт|снилс|инн)\b|"
    r"(?:password|token|secret|api[_ -]?key)\b"
    r")",
    re.IGNORECASE,
)
_SENSITIVE_IDENTIFIER_PATTERN = re.compile(
    r"(?:\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|\b\+?\d[\d ()-]{8,}\d\b)",
    re.IGNORECASE,
)


class AiCoachMemoryValidationError(ValueError):
    """A user-facing value failed the memory allowlist."""


def _validate_category(category: str) -> str:
    if category not in AI_COACH_MEMORY_CATEGORIES:
        raise AiCoachMemoryValidationError("Недопустимая категория памяти")
    return category


def normalize_memory_value(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized or len(normalized) > AI_COACH_MEMORY_MAX_VALUE_LENGTH:
        raise AiCoachMemoryValidationError(
            f"Значение памяти должно содержать от 1 до {AI_COACH_MEMORY_MAX_VALUE_LENGTH} символов"
        )
    if any(ord(character) < 0x20 for character in normalized):
        raise AiCoachMemoryValidationError("Значение памяти должно быть одной строкой")
    if _URL_PATTERN.search(normalized) or _SENSITIVE_IDENTIFIER_PATTERN.search(normalized):
        raise AiCoachMemoryValidationError(
            "Ссылки, контакты и идентификаторы нельзя сохранять в памяти"
        )
    safety_category = classify_message(normalized)
    if safety_category != SafetyCategory.CLEAR:
        raise AiCoachMemoryValidationError("Это значение нельзя сохранять в AI Coach memory")
    if _FORBIDDEN_MEMORY_PATTERN.search(normalized):
        raise AiCoachMemoryValidationError(
            "Сохраняйте только стиль общения и немедицинский контекст; канонические факты "
            "остаются в профиле и разделах приложения"
        )
    return normalized


def get_ai_coach_memory_consent(db: Session, user_id: int) -> AiCoachMemoryConsent | None:
    return (
        db.query(AiCoachMemoryConsent).filter(AiCoachMemoryConsent.user_id == user_id).one_or_none()
    )


def has_active_ai_coach_memory_consent(
    consent: AiCoachMemoryConsent | None,
) -> bool:
    return bool(
        consent
        and consent.status == "enabled"
        and consent.scope == AI_COACH_MEMORY_SCOPE
        and consent.consent_version == AI_COACH_MEMORY_CONSENT_VERSION
        and consent.granted_at is not None
        and consent.paused_at is None
        and consent.revoked_at is None
    )


def set_ai_coach_memory_consent(
    db: Session,
    *,
    user_id: int,
    status: str,
) -> AiCoachMemoryConsent:
    if status not in {"enabled", "paused", "revoked"}:
        raise ValueError("Недопустимый статус memory consent")
    db.query(User.id).filter(User.id == user_id).with_for_update().one()
    consent = (
        db.query(AiCoachMemoryConsent)
        .filter(AiCoachMemoryConsent.user_id == user_id)
        .with_for_update()
        .one_or_none()
    )
    now = now_msk_naive()
    if consent is None:
        consent = AiCoachMemoryConsent(
            user_id=user_id,
            status="revoked",
            scope=AI_COACH_MEMORY_SCOPE,
            consent_version=AI_COACH_MEMORY_CONSENT_VERSION,
            consent_source=AI_COACH_MEMORY_SOURCE,
            created_at=now,
            updated_at=now,
        )
        db.add(consent)
    consent.status = status
    consent.scope = AI_COACH_MEMORY_SCOPE
    consent.consent_version = AI_COACH_MEMORY_CONSENT_VERSION
    consent.consent_source = AI_COACH_MEMORY_SOURCE
    if status == "enabled":
        consent.granted_at = now
        consent.paused_at = None
        consent.revoked_at = None
    elif status == "paused":
        consent.paused_at = now
        consent.revoked_at = None
    else:
        consent.paused_at = None
        consent.revoked_at = now
    consent.updated_at = now
    db.flush()
    return consent


def serialize_ai_coach_memory(memory: AiCoachMemory) -> dict[str, object]:
    return {
        "id": memory.id,
        "category": memory.category,
        "category_label": AI_COACH_MEMORY_CATEGORY_LABELS[memory.category],
        "value": memory.value_text,
        "source_kind": memory.source_kind,
        "confidence": memory.confidence,
        "status": memory.status,
        "version": memory.version,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
        "expires_at": memory.expires_at,
    }


def serialize_ai_coach_memory_consent(
    consent: AiCoachMemoryConsent | None,
) -> dict[str, object]:
    status = (
        consent.status
        if consent
        and consent.scope == AI_COACH_MEMORY_SCOPE
        and consent.consent_version == AI_COACH_MEMORY_CONSENT_VERSION
        else "revoked"
    )
    return {
        "status": status,
        "scope": AI_COACH_MEMORY_SCOPE,
        "consent_version": AI_COACH_MEMORY_CONSENT_VERSION,
        "categories": AI_COACH_MEMORY_CATEGORIES,
        "category_labels": AI_COACH_MEMORY_CATEGORY_LABELS,
        "purpose": AI_COACH_MEMORY_PURPOSE,
        "retention_notice": AI_COACH_MEMORY_RETENTION_NOTICE,
        "max_items": AI_COACH_MEMORY_MAX_ITEMS,
        "consent_source": consent.consent_source if consent else AI_COACH_MEMORY_SOURCE,
        "granted_at": consent.granted_at if consent and status == "enabled" else None,
        "paused_at": consent.paused_at if consent and status == "paused" else None,
        "revoked_at": consent.revoked_at if consent and status == "revoked" else None,
    }


def list_ai_coach_memories(db: Session, user_id: int) -> list[AiCoachMemory]:
    return (
        db.query(AiCoachMemory)
        .filter(
            AiCoachMemory.user_id == user_id,
            AiCoachMemory.status.in_(("active", "superseded", "conflicted")),
        )
        .order_by(AiCoachMemory.created_at.asc(), AiCoachMemory.id.asc())
        .all()
    )


def create_ai_coach_memory(
    db: Session,
    *,
    user_id: int,
    category: str,
    value: str,
) -> AiCoachMemory:
    category = _validate_category(category)
    normalized = normalize_memory_value(value)
    db.query(User.id).filter(User.id == user_id).with_for_update().one()
    active_count = (
        db.query(AiCoachMemory.id)
        .filter(AiCoachMemory.user_id == user_id, AiCoachMemory.status == "active")
        .count()
    )
    if active_count >= AI_COACH_MEMORY_MAX_ITEMS:
        raise AiCoachMemoryValidationError("Достигнут лимит элементов AI Coach memory")
    now = now_msk_naive()
    memory = AiCoachMemory(
        user_id=user_id,
        category=category,
        value_text=normalized,
        source_kind="explicit_user",
        confidence="explicit",
        status="active",
        source_ref=AI_COACH_MEMORY_SOURCE,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(memory)
    db.flush()
    return memory


def get_owned_ai_coach_memory(db: Session, *, user_id: int, memory_id: int) -> AiCoachMemory | None:
    return (
        db.query(AiCoachMemory)
        .filter(
            AiCoachMemory.id == memory_id,
            AiCoachMemory.user_id == user_id,
            AiCoachMemory.status != "deleted",
        )
        .one_or_none()
    )


def update_ai_coach_memory(
    db: Session,
    *,
    memory: AiCoachMemory,
    value: str,
) -> AiCoachMemory:
    memory.value_text = normalize_memory_value(value)
    memory.version += 1
    memory.updated_at = now_msk_naive()
    db.flush()
    return memory


def delete_ai_coach_memory(db: Session, *, memory: AiCoachMemory) -> None:
    db.delete(memory)
    db.flush()


def clear_ai_coach_memories(db: Session, *, user_id: int) -> int:
    return (
        db.query(AiCoachMemory)
        .filter(AiCoachMemory.user_id == user_id)
        .delete(synchronize_session=False)
    )


def get_ai_coach_memory_context(db: Session, *, user_id: int) -> tuple[AiCoachMemoryContext, ...]:
    consent = get_ai_coach_memory_consent(db, user_id)
    if not has_active_ai_coach_memory_consent(consent):
        return ()
    now = now_msk_naive()
    memories = (
        db.query(AiCoachMemory)
        .filter(
            AiCoachMemory.user_id == user_id,
            AiCoachMemory.status == "active",
            (AiCoachMemory.expires_at.is_(None) | (AiCoachMemory.expires_at > now)),
        )
        .order_by(AiCoachMemory.updated_at.desc(), AiCoachMemory.id.desc())
        .limit(AI_COACH_MEMORY_MAX_ITEMS)
        .all()
    )
    return tuple(
        AiCoachMemoryContext(
            category=cast(AiCoachMemoryCategory, memory.category),
            value=memory.value_text,
            origin=cast(AiCoachMemoryOrigin, memory.source_kind),
            updated_at=memory.updated_at.isoformat(),
        )
        for memory in memories
    )


__all__ = [
    "AI_COACH_MEMORY_CATEGORIES",
    "AI_COACH_MEMORY_CATEGORY_LABELS",
    "AI_COACH_MEMORY_CONSENT_VERSION",
    "AI_COACH_MEMORY_MAX_ITEMS",
    "AI_COACH_MEMORY_MAX_VALUE_LENGTH",
    "AI_COACH_MEMORY_PURPOSE",
    "AI_COACH_MEMORY_RETENTION_NOTICE",
    "AI_COACH_MEMORY_SCOPE",
    "AI_COACH_MEMORY_SOURCE",
    "AiCoachMemoryValidationError",
    "clear_ai_coach_memories",
    "create_ai_coach_memory",
    "delete_ai_coach_memory",
    "get_ai_coach_memory_consent",
    "get_ai_coach_memory_context",
    "get_owned_ai_coach_memory",
    "has_active_ai_coach_memory_consent",
    "list_ai_coach_memories",
    "normalize_memory_value",
    "serialize_ai_coach_memory",
    "serialize_ai_coach_memory_consent",
    "set_ai_coach_memory_consent",
    "update_ai_coach_memory",
]
