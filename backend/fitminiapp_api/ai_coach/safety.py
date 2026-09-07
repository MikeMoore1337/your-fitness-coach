"""Fail-closed request and response safety checks for the generic AI route."""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum

from fitminiapp_api.ai_coach.contracts import AiCoachRequest, ProviderStructuredResponse


class SafetyCategory(StrEnum):
    CLEAR = "clear"
    MEDICAL = "medical"
    DRUGS_PERFORMANCE = "drugs_performance"
    EATING_DISORDER_OR_PREGNANCY = "eating_disorder_or_pregnancy"
    PERSONAL_DATA = "personal_data"
    UNSUPPORTED_INFERENCE = "unsupported_inference"
    ACTION_REQUEST = "action_request"
    PRIVACY_EXFILTRATION = "privacy_exfiltration"
    PROMPT_INJECTION = "prompt_injection"


class SafetyDecision(StrEnum):
    ALLOW = "allow"
    REFUSE = "refuse"


_PATTERNS: tuple[tuple[SafetyCategory, re.Pattern[str]], ...] = (
    (
        SafetyCategory.PROMPT_INJECTION,
        re.compile(
            r"(?:ignore\s+(?:all\s+)?(?:previous|earlier)\s+instructions|"
            r"игнорируй\s+(?:все\s+)?(?:предыдущие|системные)\s+инструкции|"
            r"(?:reveal|show|print)\s+(?:the\s+)?(?:system\s+)?prompt|"
            r"(?:раскрой|покажи|выведи)\s+(?:системный\s+)?промпт|"
            r"(?:developer|system)\s+(?:message|instruction)|"
            r"вызови\s+инструмент|use\s+tools?)",
            re.IGNORECASE,
        ),
    ),
    (
        SafetyCategory.PRIVACY_EXFILTRATION,
        re.compile(
            r"(?:чуж(?:ой|ие|ого)|тренерск(?:ие|их)\s+замет|"
            r"api\s*key|токен|секрет|парол|private\s+data|друг(?:ого|их)\s+пользов)",
            re.IGNORECASE,
        ),
    ),
    (
        SafetyCategory.DRUGS_PERFORMANCE,
        re.compile(
            r"(?:\baas\b|\bsarm(?:s)?\b|стероид|анабол|тестостерон|"
            r"дозиров|курс(?:а|ом)?\s+(?:препарат|стероид)|prescription)",
            re.IGNORECASE,
        ),
    ),
    (
        SafetyCategory.EATING_DISORDER_OR_PREGNANCY,
        re.compile(
            r"(?:беремен|расстройств(?:о|а)\s+пищев|пищев(?:ое|ого)\s+поведени|"
            r"eating\s+disorder|pregnan)",
            re.IGNORECASE,
        ),
    ),
    (
        SafetyCategory.MEDICAL,
        re.compile(
            r"(?:диагноз|диагностир|лечени|лекарств|боль|болит|травм|перелом|"
            r"операци|скорая|неотложн|симптом|disease|diagnos|treatment|injur|emergency)",
            re.IGNORECASE,
        ),
    ),
    (
        SafetyCategory.UNSUPPORTED_INFERENCE,
        re.compile(
            r"(?:(?:рассчитай|посчитай|вычисли|оцени|определи|подбери|"
            r"calculate|compute|estimate).{0,64}(?:\bbmr\b|\btdee\b|кбжу|"
            r"health\s+score|readiness|recovery|fatigue|готовност|восстановлен|"
            r"усталост|здоровь(?:я|е)\s*(?:балл|оцен)|прогресси)|"
            r"(?:\bbmr\b|\btdee\b|кбжу|health\s+score|readiness|recovery|"
            r"fatigue|готовност|восстановлен|усталост|прогресси).{0,64}"
            r"(?:мой|моя|мои|мне|у\s+меня|для\s+меня|по\s+моим|my|me))",
            re.IGNORECASE,
        ),
    ),
    (
        SafetyCategory.ACTION_REQUEST,
        re.compile(
            r"(?:\b(?:измени|поменяй|назначь|создай|удали|добавь|перенеси|установи)\s+"
            r"(?:мне|мой|моя|мои|програм|цель|калор|расписан|трениров)|"
            r"сделай\s+мне\s+(?:план|програм)|"
            r"\b(?:change|create|delete|add|assign)\s+(?:my|the))",
            re.IGNORECASE,
        ),
    ),
    (
        SafetyCategory.PERSONAL_DATA,
        re.compile(
            r"(?:(?:мой|моя|мои|мне|у\s+меня|для\s+меня|по\s+моим)\s+"
            r"(?:вес|рост|возраст|пол|калор|ккал|белк|жир|углевод|трениров|"
            r"программ|дневник|цель|прогресс|замер|сон|пульс|нагрузк|подход|"
            r"повтор|weight|height|age|calorie|protein|training|workout|goal|"
            r"progress|sleep)|"
            r"(?:вес|рост|возраст)\s*[:=]?\s*\d+(?:[.,]\d+)?|"
            r"(?:сколько|какой|какие).{0,48}\b(?:мне|мой|моя|мои)\b.{0,48}"
            r"(?:калор|ккал|белк|жир|углевод|трениров|программ|нагрузк|"
            r"weight|calorie|protein|training|workout))",
            re.IGNORECASE,
        ),
    ),
)

_OUTPUT_BLOCKLIST = re.compile(
    r"(?:chain\s+of\s+thought|hidden\s+reasoning|reasoning|"
    r"скрыт(?:ые|ых)?\s+рассужд|рассужд|системный\s+промпт|"
    r"api\s*key|токен|секрет|ignore\s+(?:all\s+)?previous\s+instructions|"
    r"игнорируй\s+(?:все\s+)?предыдущие\s+инструкции|developer\s+message)",
    re.IGNORECASE,
)
_URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
_CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")


def normalize_user_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def classify_request(request: AiCoachRequest) -> SafetyCategory:
    text = normalize_user_text(request.message)
    for category, pattern in _PATTERNS:
        if pattern.search(text):
            return category
    return SafetyCategory.CLEAR


def refusal_text(category: SafetyCategory) -> str:
    if category in {
        SafetyCategory.MEDICAL,
        SafetyCategory.EATING_DISORDER_OR_PREGNANCY,
    }:
        return (
            "Я не могу ставить диагнозы, подбирать лечение или давать медицинские назначения. "
            "По вопросам здоровья обратитесь к квалифицированному специалисту; при экстренной "
            "ситуации используйте местную экстренную помощь."
        )
    if category == SafetyCategory.DRUGS_PERFORMANCE:
        return "Я не могу подбирать схемы, циклы или дозировки препаратов. Обсудите такие вопросы с врачом."
    if category == SafetyCategory.PERSONAL_DATA:
        return (
            "AI Coach не получает и не передаёт персональные данные о теле, питании или "
            "тренировках. Я могу объяснить только опубликованные общие сведения и правила "
            "сервиса."
        )
    if category == SafetyCategory.UNSUPPORTED_INFERENCE:
        return (
            "Your Fitness Coach не рассчитывает такую персональную оценку. Я могу объяснить "
            "только опубликованные определения и фактические правила сервиса."
        )
    if category == SafetyCategory.ACTION_REQUEST:
        return (
            "AI Coach не изменяет программы, цели, калории или расписание. Используйте "
            "соответствующий управляемый экран приложения."
        )
    if category == SafetyCategory.PRIVACY_EXFILTRATION:
        return "Я не могу раскрывать чужие данные, секреты или внутренние инструкции."
    if category == SafetyCategory.PROMPT_INJECTION:
        return "Я могу отвечать только на вопрос по опубликованному контексту и не меняю эти ограничения."
    return "Я не могу обработать этот запрос в текущем безопасном режиме."


def validate_provider_output(
    output: ProviderStructuredResponse,
    *,
    allowed_ref_ids: frozenset[str],
) -> None:
    if not output.answer.strip() or not _CYRILLIC_PATTERN.search(output.answer):
        raise ValueError("answer_language_invalid")
    if _OUTPUT_BLOCKLIST.search(output.answer) or _URL_PATTERN.search(output.answer):
        raise ValueError("answer_contains_untrusted_instruction_or_url")
    if any(_OUTPUT_BLOCKLIST.search(item) for item in output.limitations):
        raise ValueError("limitation_contains_sensitive_content")
    if not output.citation_ids or any(
        ref_id not in allowed_ref_ids for ref_id in output.citation_ids
    ):
        raise ValueError("citation_reference_invalid")
