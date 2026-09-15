"""Fail-closed request and response safety checks for the generic AI route."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from fitminiapp_api.ai_coach.contracts import (
    AiCoachDataClass,
    AiCoachInsightKind,
    AiCoachRequest,
    ChatOutputValidationReason,
    ProviderStructuredResponse,
)


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
            r"клиент(?:а|ские|ских)?|client\s+data|api\s*key|токен|секрет|парол|"
            r"private\s+data|друг(?:ого|их)\s+пользов)",
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
            r"усталост|здоровь(?:я|е)\s*(?:балл|оцен)|прогресси|прогноз|"
            r"предскажи|forecast)|"
            r"(?:\bbmr\b|\btdee\b|кбжу|health\s+score|readiness|recovery|"
            r"fatigue|готовност|восстановлен|усталост|прогресси|прогноз|"
            r"forecast).{0,64}"
            r"(?:мой|моя|мои|мою|моего|моей|моём|моем|моими|мне|у\s+меня|для\s+меня|по\s+моим|my|me)|"
            r"(?:прогноз|forecast|предскажи).{0,64}(?:мой|моя|мои|мою|моего|моей|моём|моем|моими|для\s+меня|my|me))",
            re.IGNORECASE,
        ),
    ),
    (
        SafetyCategory.ACTION_REQUEST,
        re.compile(
            r"(?:\b(?:измени|поменяй|назначь|создай|удали|добавь|перенеси|установи)\s+"
            r"(?:мне|мой|моя|мои|мою|моего|моей|моём|моем|моими|програм|цель|калор|расписан|трениров)|"
            r"сделай\s+мне\s+(?:план|програм)|"
            r"\b(?:change|create|delete|add|assign)\s+(?:my|the))",
            re.IGNORECASE,
        ),
    ),
    (
        SafetyCategory.PERSONAL_DATA,
        re.compile(
            r"(?:(?:мой|моя|мои|мою|моего|моей|моём|моем|моими|мне|у\s+меня|для\s+меня|по\s+моим)\s+"
            r"(?:вес|рост|возраст|пол|калор|ккал|белк|жир|углевод|трениров|"
            r"программ|дневник|цель|прогресс|замер|сон|пульс|нагрузк|подход|"
            r"повтор|weight|height|age|calorie|protein|training|workout|goal|"
            r"progress|sleep)|"
            r"(?:вес|рост|возраст)\s*[:=]?\s*\d+(?:[.,]\d+)?|"
            r"(?:сколько|какой|какие).{0,48}\b(?:мне|мой|моя|мои|мою|моего|моей|моём|моем|моими)\b.{0,48}"
            r"(?:калор|ккал|белк|жир|углевод|трениров|программ|нагрузк|"
            r"weight|calorie|protein|training|workout)|"
            r"\bя\s+(?:вешу|весом|тренируюсь|занимаюсь|бегаю|сплю|"
            r"сделал(?:а)?|выполнил(?:а)?|поднял(?:а)?|пробежал(?:а)?)\b|"
            r"\bмне\s+\d+\s*(?:лет|года|год)\b|"
            r"\b(?:я|i)\b.{0,64}\b\d+(?:[.,]\d+)?\s*"
            r"(?:кг|килограмм(?:а|ов)?|см|сантиметр(?:а|ов)?|лет|года|год|"
            r"ккал|bpm|kg|cm|years?)\b)",
            re.IGNORECASE,
        ),
    ),
)

_OUTPUT_PROMPT_LEAKAGE_BLOCKLIST = re.compile(
    r"(?:chain\s+of\s+thought|hidden\s+reasoning|"
    r"(?:system|developer)\s+(?:prompt|message|instruction)s?|"
    r"(?:reveal|show|print)\s+(?:the\s+)?(?:system\s+prompt|developer\s+message)|"
    r"системн\w*\s+промпт|сообщени\w*\s+разработчика|"
    r"(?:раскр(?:ой|ыть)|покаж(?:и|ите)|вывед(?:и|ите)).{0,32}(?:системн\w*\s+промпт|"
    r"промпт|инструкц|сообщени\w*\s+разработчика)|"
    r"ignore\s+(?:all\s+)?(?:previous|earlier)\s+instructions|"
    r"игнорируй\s+(?:все\s+)?(?:предыдущие|системные)\s+инструкции)",
    re.IGNORECASE,
)
_OUTPUT_SECRET_LEAKAGE_BLOCKLIST = re.compile(
    r"(?:api\s*key|access\s+token|bearer\s+token|private\s+key|"
    r"токен|секрет\w*|парол\w*)",
    re.IGNORECASE,
)
_OUTPUT_PRIVACY_LEAKAGE_BLOCKLIST = re.compile(
    r"(?:чуж(?:ие|ой|ого)\s+(?:данные|профил\w*|трениров\w*|питани\w*)|"
    r"данные\s+(?:другого|других|клиента)|client\s+data|private\s+data|"
    r"(?:user|telegram)_id\s*[:=]|email\s*[:=]|телефон\s*[:=])",
    re.IGNORECASE,
)
_OUTPUT_BLOCKLIST = re.compile(
    "(?:"
    + _OUTPUT_PROMPT_LEAKAGE_BLOCKLIST.pattern
    + "|"
    + _OUTPUT_SECRET_LEAKAGE_BLOCKLIST.pattern
    + "|"
    + _OUTPUT_PRIVACY_LEAKAGE_BLOCKLIST.pattern
    + ")",
    re.IGNORECASE,
)
_OUTPUT_PROHIBITED_CLAIM_BLOCKLIST = re.compile(
    r"(?:"
    r"\b(?:принимай(?:те)?|принимать|назнач(?:ь|ьте|аю)|используй(?:те)?|"
    r"начни(?:те)?|пей(?:те)?|рекоменду(?:ю|ется|йте)?|take|use|start|recommend)\b"
    r".{0,120}(?:\b\d+(?:[.,]\d+)?\s*(?:мг|г|мл|таблет(?:ка|ки|ок)?|mg|g|ml)\b|"
    r"\b(?:креатин|протеин|витамин(?:ы|ов)?|добавк(?:а|и)?|"
    r"ибупрофен|парацетамол|аспирин|антибиотик(?:и|ов)?|"
    r"creatine|protein|vitamin|supplement|medication)\b)|"
    r"\b\d+(?:[.,]\d+)?\s*(?:мг|г|мл)\s+"
    r"(?:креатин|протеин|витамин|добавк|creatine|protein|vitamin|supplement)\b|"
    r"\b(?:у\s+вас|вам|это|похоже\s+на)\s+"
    r"(?:диагноз|заболев\w*|болезн\w*|травм\w*|синдром\w*|симптом\w*)\b|"
    r"\b(?:ваш|ваша|ваше|ваши|твой|твоя|твоё|твои|мой|моя|мои|мою|моего|моей|моём|моем|моими|"
    r"для\s+(?:вас|меня))\b.{0,96}\b"
    r"(?:tdee|bmr|кбжу|калори\w*|health\s+score|readiness|"
    r"пульс\w*|восстановлен\w*|fatigue)\b"
    r")",
    re.IGNORECASE,
)
_OUTPUT_PERSONAL_UNSUPPORTED_CALCULATION_BLOCKLIST = re.compile(
    r"(?:"
    r"\b(?:tdee|bmr|health\s+score|readiness|fatigue)\b|"
    r"\b(?:рассчита\w*|расч[её]т\w*|вычисл\w*|подсчита\w*|определ\w*)\b"
    r".{0,120}\b(?:tdee|bmr|кбжу|калори\w*|health\s+score|readiness|"
    r"восстановлен\w*|fatigue)\b"
    r")",
    re.IGNORECASE,
)
_PERIOD_REPORT_UNSAFE_CLAIM_BLOCKLIST = re.compile(
    r"(?:"
    r"\b(?:диагноз\w*|диагностир\w*|лечени\w*|травм\w*|перетрен\w*|"
    r"бессон\w*|депресс\w*|выгорани\w*|гарант\w*|прогноз\w*|forecast\w*|"
    r"идеальн\w*|состав\s+тела|процент\s+жира|разгрузочн\w*|"
    r"недел\w*\s+отдых\w*|rest\s+week|перерыв\w*|eating[- ]?back|"
    r"(?:плох\w*|хорош\w*|чист\w*|вредн\w*|запрещ\w*)\s+ед\w*|"
    r"cheat\s+meal|доедать|компенсир\w*|медицин\w*|medical)\b|"
    r"\b(?:из-за|из за|потому\s+что|причин\w*|вызыва\w*|привод\w*\s+к|"
    r"связан\w*\s+с|корреляц\w*|влиян\w*|caus\w*)\b|"
    r"\b(?:измен(?:и|ить|ите)|меняй(?:те)?|назнач(?:ь|ить|ьте)|"
    r"пересчит(?:ай|ать|айте)|увелич(?:ь|ить|ьте)|уменьш(?:ь|ить|ьте)|"
    r"добав(?:ь|ить|ьте)|созда(?:й|ть|йте)|удал(?:и|ить|ите)|"
    r"перенес(?:и|ти|ите))\b.{0,80}\b(?:ккал|калори\w*|кбжу|"
    r"цел\w*|программ\w*|трениров\w*|напомин\w*|нагрузк\w*)\b|"
    r"\bчерез\s+.{0,32}\b(?:будет|станет|достигнете|получите)\b|"
    r"\b(?:кардио|cardio).{0,32}\b(?:калори\w*|kcal)\b|"
    r"\b(?:калори\w*|kcal).{0,32}\b(?:кардио|cardio)\b|"
    r"\bпульс\w*.{0,32}\b(?:зон\w*|порог\w*|bpm|удар\w*)\b"
    r")",
    re.IGNORECASE,
)
_URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
_CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")
_LATIN_PATTERN = re.compile(r"[A-Za-z]")
_INTERNAL_ROUTE_PATTERN = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё0-9_])/(?P<route>today|nutrition|progress|training|api|v1)"
    r"(?=[/?#\s).,:]|$)",
    re.IGNORECASE,
)
_INTERNAL_LABEL_PATTERN = re.compile(
    r"(?:"
    r"(?<![A-Za-zА-Яа-яЁё0-9_])/(?:today|nutrition|progress|training|api|v1)"
    r"(?:[/?#\s).,:]|$)|"
    r"\b(?:context_id|context_kind|data_class|tool_name|fallback_path|canonical_url|"
    r"context_refs|prompt_version|output_version|schema_version|citation_ids|"
    r"response_format|structured_output|get_[a-z0-9_]+)\b"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChatOutputInspection:
    """Metadata-only inspection of one untrusted provider text response."""

    normalized: str
    reason: ChatOutputValidationReason | None = None
    safety_category: SafetyCategory | None = None


class ChatOutputValidationError(ValueError):
    """Typed, raw-content-free validation error for conversational output."""

    def __init__(
        self,
        reason: ChatOutputValidationReason,
        *,
        safety_category: SafetyCategory | None = None,
    ) -> None:
        self.reason = reason
        self.safety_category = safety_category
        super().__init__(reason.value)


def normalize_user_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n").strip()


def classify_message(message: str) -> SafetyCategory:
    text = normalize_user_text(message)
    for category, pattern in _PATTERNS:
        if pattern.search(text):
            return category
    return SafetyCategory.CLEAR


def detect_chat_locale(message: str) -> Literal["ru", "en"]:
    """Choose the response language from the current user turn, defaulting to Russian."""

    normalized = normalize_user_text(message)
    cyrillic_count = len(_CYRILLIC_PATTERN.findall(normalized))
    latin_count = len(_LATIN_PATTERN.findall(normalized))
    return "en" if latin_count > cyrillic_count else "ru"


def classify_request(request: AiCoachRequest) -> SafetyCategory:
    category = classify_message(request.message)
    if request.data_class.value == "personalized" and category == SafetyCategory.PERSONAL_DATA:
        return SafetyCategory.CLEAR
    return category


def refusal_text(category: SafetyCategory, *, locale: Literal["ru", "en"] = "ru") -> str:
    if locale == "en":
        if category in {
            SafetyCategory.MEDICAL,
            SafetyCategory.EATING_DISORDER_OR_PREGNANCY,
        }:
            return (
                "I can't diagnose conditions, choose treatment, or give medical instructions. "
                "Please consult a qualified clinician; use local emergency services for an emergency."
            )
        if category == SafetyCategory.DRUGS_PERFORMANCE:
            return "I can't choose drug cycles or dosages. Discuss those questions with a doctor."
        if category == SafetyCategory.PERSONAL_DATA:
            return (
                "AI Coach can use personal training, nutrition, or progress data only in the "
                "explicitly enabled personal mode. I can still explain general information."
            )
        if category == SafetyCategory.UNSUPPORTED_INFERENCE:
            return (
                "Your Fitness Coach does not calculate that personal assessment. I can explain "
                "published definitions and service rules."
            )
        if category == SafetyCategory.ACTION_REQUEST:
            return (
                "AI Coach does not change programs, goals, calories, or schedules. Use the "
                "corresponding app control."
            )
        if category in {
            SafetyCategory.PRIVACY_EXFILTRATION,
            SafetyCategory.PROMPT_INJECTION,
        }:
            return "I can't reveal other people's data, secrets, or internal instructions."
        return "I can't process this request in the current safe mode."
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


def _has_expected_language(answer: str, locale: Literal["ru", "en"]) -> bool:
    pattern = _CYRILLIC_PATTERN if locale == "ru" else _LATIN_PATTERN
    return bool(pattern.search(answer))


def _is_json_container(value: str) -> bool:
    if not value.startswith(("{", "[")):
        return False
    try:
        decoded = json.loads(value)
    except TypeError, ValueError, json.JSONDecodeError:
        return False
    return isinstance(decoded, (dict, list))


def _output_safety_category(
    answer: str,
    *,
    data_class: AiCoachDataClass,
) -> SafetyCategory | None:
    if _OUTPUT_SECRET_LEAKAGE_BLOCKLIST.search(answer) or _OUTPUT_PRIVACY_LEAKAGE_BLOCKLIST.search(
        answer
    ):
        return SafetyCategory.PRIVACY_EXFILTRATION
    if _OUTPUT_PROMPT_LEAKAGE_BLOCKLIST.search(answer):
        return SafetyCategory.PROMPT_INJECTION
    if _OUTPUT_PROHIBITED_CLAIM_BLOCKLIST.search(answer):
        if re.search(
            r"(?:диагноз|диагностир|лечени|лекарств|болезн|травм|симптом|medical|diagnos|treatment|injur)",
            answer,
            re.IGNORECASE,
        ):
            return SafetyCategory.MEDICAL
        return SafetyCategory.DRUGS_PERFORMANCE
    if (
        data_class == AiCoachDataClass.PERSONALIZED
        and _OUTPUT_PERSONAL_UNSUPPORTED_CALCULATION_BLOCKLIST.search(answer)
    ):
        return SafetyCategory.UNSUPPORTED_INFERENCE
    return None


def _output_safety_reason(
    answer: str,
    *,
    data_class: AiCoachDataClass,
) -> ChatOutputValidationReason:
    if (
        _OUTPUT_SECRET_LEAKAGE_BLOCKLIST.search(answer)
        or _OUTPUT_PRIVACY_LEAKAGE_BLOCKLIST.search(answer)
        or _OUTPUT_PROMPT_LEAKAGE_BLOCKLIST.search(answer)
    ):
        return ChatOutputValidationReason.UNSAFE_CONTENT
    if _OUTPUT_PROHIBITED_CLAIM_BLOCKLIST.search(answer) or (
        data_class == AiCoachDataClass.PERSONALIZED
        and _OUTPUT_PERSONAL_UNSUPPORTED_CALCULATION_BLOCKLIST.search(answer)
    ):
        return ChatOutputValidationReason.PROHIBITED_CLAIM
    return ChatOutputValidationReason.UNSAFE_CONTENT


def inspect_chat_output(
    answer: str,
    *,
    data_class: AiCoachDataClass,
    locale: Literal["ru", "en"] = "ru",
) -> ChatOutputInspection:
    """Classify provider text before deciding whether to show, sanitize or repair it."""

    normalized = normalize_user_text(answer)
    output_safety = _output_safety_category(normalized, data_class=data_class)
    if output_safety is not None:
        return ChatOutputInspection(
            normalized=normalized,
            reason=_output_safety_reason(normalized, data_class=data_class),
            safety_category=output_safety,
        )
    if not normalized:
        return ChatOutputInspection(normalized, ChatOutputValidationReason.OTHER)
    if len(normalized) > 1_600:
        return ChatOutputInspection(normalized, ChatOutputValidationReason.TOO_LONG)
    if not _has_expected_language(normalized, locale):
        return ChatOutputInspection(normalized, ChatOutputValidationReason.WRONG_LANGUAGE)
    if _is_json_container(normalized):
        return ChatOutputInspection(normalized, ChatOutputValidationReason.JSON_CONTAINER)
    if _INTERNAL_LABEL_PATTERN.search(normalized):
        return ChatOutputInspection(normalized, ChatOutputValidationReason.INTERNAL_LABEL)
    if _URL_PATTERN.search(normalized):
        return ChatOutputInspection(normalized, ChatOutputValidationReason.URL)
    return ChatOutputInspection(normalized)


def _replace_internal_routes(value: str, *, locale: Literal["ru", "en"]) -> str:
    labels = {
        "today": "экран «Сегодня»" if locale == "ru" else "Today screen",
        "nutrition": "раздел «Питание»" if locale == "ru" else "nutrition section",
        "progress": "раздел «Прогресс»" if locale == "ru" else "progress section",
        "training": "раздел «Тренировки»" if locale == "ru" else "training section",
        "api": "служебный раздел" if locale == "ru" else "internal section",
        "v1": "служебная версия" if locale == "ru" else "internal version",
    }
    return _INTERNAL_ROUTE_PATTERN.sub(
        lambda match: labels[match.group("route").lower()],
        value,
    )


def sanitize_chat_output(
    answer: str,
    *,
    data_class: AiCoachDataClass,
    locale: Literal["ru", "en"] = "ru",
) -> str | None:
    """Apply only deterministic, meaning-preserving presentation cleanup."""

    inspection = inspect_chat_output(answer, data_class=data_class, locale=locale)
    if inspection.reason is None:
        return inspection.normalized
    if inspection.reason not in {
        ChatOutputValidationReason.URL,
        ChatOutputValidationReason.INTERNAL_LABEL,
    }:
        return None
    sanitized = re.sub(
        r"\[([^\]\n]{1,120})\]\(\s*(?:https?://|/)[^)\s]*\)",
        r"\1",
        inspection.normalized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(r"https?://[^\s<>\])}]+", "", sanitized, flags=re.IGNORECASE)
    sanitized = _replace_internal_routes(sanitized, locale=locale)
    sanitized = re.sub(r"[ \t]{2,}", " ", sanitized)
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
    if not sanitized:
        return None
    final = inspect_chat_output(sanitized, data_class=data_class, locale=locale)
    return final.normalized if final.reason is None else None


def bound_safe_chat_output(
    answer: str,
    *,
    data_class: AiCoachDataClass,
    locale: Literal["ru", "en"] = "ru",
) -> str | None:
    """Bound one safe overlong draft without hiding a safety or format failure."""

    inspection = inspect_chat_output(answer, data_class=data_class, locale=locale)
    if (
        inspection.safety_category is not None
        or inspection.reason
        not in {
            ChatOutputValidationReason.TOO_LONG,
            ChatOutputValidationReason.URL,
            ChatOutputValidationReason.INTERNAL_LABEL,
        }
        or _is_json_container(inspection.normalized)
    ):
        return None

    bounded = re.sub(
        r"\[([^\]\n]{1,120})\]\(\s*(?:https?://|/)[^)\s]*\)",
        r"\1",
        inspection.normalized,
        flags=re.IGNORECASE,
    )
    bounded = re.sub(r"https?://[^\s<>\])}]+", "", bounded, flags=re.IGNORECASE)
    bounded = _replace_internal_routes(bounded, locale=locale)
    bounded = re.sub(r"[ \t]{2,}", " ", bounded)
    bounded = re.sub(r"\n{3,}", "\n\n", bounded).strip()
    if len(bounded) > 1_600:
        prefix = bounded[:1_600]
        boundaries = list(
            re.finditer(
                r"(?:\n{2,}|[.!?。！？]+(?=\s|$))",
                prefix,
            )
        )
        if boundaries:
            bounded = prefix[: boundaries[-1].end()].strip()
        else:
            prefix = bounded[:1_599].rstrip()
            cut = prefix.rfind(" ")
            if cut >= 800:
                prefix = prefix[:cut].rstrip()
            bounded = f"{prefix.rstrip(' ,;:-')}…"

    final = inspect_chat_output(bounded, data_class=data_class, locale=locale)
    return final.normalized if final.reason is None else None


def validate_chat_output(
    answer: str,
    *,
    data_class: AiCoachDataClass,
    locale: Literal["ru", "en"] = "ru",
) -> str:
    """Validate plain chat text without turning format failures into safety refusals."""

    inspection = inspect_chat_output(answer, data_class=data_class, locale=locale)
    if inspection.reason is not None:
        raise ChatOutputValidationError(
            inspection.reason,
            safety_category=inspection.safety_category,
        )
    return inspection.normalized


def safe_chat_fallback(
    answer: str,
    *,
    data_class: AiCoachDataClass,
    locale: Literal["ru", "en"] = "ru",
) -> str | None:
    """Backward-compatible name for deterministic chat presentation cleanup."""

    return sanitize_chat_output(answer, data_class=data_class, locale=locale)


def validate_provider_output(
    output: ProviderStructuredResponse,
    *,
    allowed_ref_ids: frozenset[str],
    data_class: AiCoachDataClass = AiCoachDataClass.GENERIC,
    period_report: bool = False,
    allowed_evidence_ids: frozenset[str] = frozenset(),
    allowed_reason_keys: frozenset[str] = frozenset(),
) -> None:
    if not output.answer.strip() or not _CYRILLIC_PATTERN.search(output.answer):
        raise ValueError("answer_language_invalid")
    if _OUTPUT_BLOCKLIST.search(output.answer) or _URL_PATTERN.search(output.answer):
        raise ValueError("answer_contains_untrusted_instruction_or_url")
    if data_class != AiCoachDataClass.PERSONALIZED and _OUTPUT_PROHIBITED_CLAIM_BLOCKLIST.search(
        output.answer
    ):
        raise ValueError("answer_contains_prohibited_claim")
    if (
        data_class == AiCoachDataClass.PERSONALIZED
        and _OUTPUT_PERSONAL_UNSUPPORTED_CALCULATION_BLOCKLIST.search(output.answer)
    ):
        raise ValueError("answer_contains_unsupported_personal_calculation")
    if period_report and _PERIOD_REPORT_UNSAFE_CLAIM_BLOCKLIST.search(output.answer):
        raise ValueError("period_report_answer_contains_unsafe_claim")
    if any(_OUTPUT_BLOCKLIST.search(item) for item in output.limitations):
        raise ValueError("limitation_contains_sensitive_content")
    if data_class != AiCoachDataClass.PERSONALIZED and any(
        _OUTPUT_PROHIBITED_CLAIM_BLOCKLIST.search(item) for item in output.limitations
    ):
        raise ValueError("limitation_contains_prohibited_claim")
    if data_class == AiCoachDataClass.PERSONALIZED and any(
        _OUTPUT_PERSONAL_UNSUPPORTED_CALCULATION_BLOCKLIST.search(item)
        for item in output.limitations
    ):
        raise ValueError("limitation_contains_unsupported_personal_calculation")
    if period_report and any(
        _PERIOD_REPORT_UNSAFE_CLAIM_BLOCKLIST.search(item) for item in output.limitations
    ):
        raise ValueError("period_report_limitation_contains_unsafe_claim")
    if not output.citation_ids or any(
        ref_id not in allowed_ref_ids for ref_id in output.citation_ids
    ):
        raise ValueError("citation_reference_invalid")
    if not period_report:
        if output.insights:
            raise ValueError("unexpected_insights")
        return

    required_sections = (
        "Главное за период",
        "Ограничения данных",
        "Что можно сделать дальше",
        "Почему",
    )
    if any(section not in output.answer for section in required_sections):
        raise ValueError("period_report_sections_missing")
    if not 2 <= len(output.insights) <= 11:
        raise ValueError("period_report_insights_count_invalid")

    fact_count = sum(item.kind == AiCoachInsightKind.FACT for item in output.insights)
    inference_count = sum(item.kind == AiCoachInsightKind.INFERENCE for item in output.insights)
    suggestion_count = sum(item.kind == AiCoachInsightKind.SUGGESTION for item in output.insights)
    if not 2 <= fact_count <= 4:
        raise ValueError("period_report_fact_count_invalid")
    if inference_count > 4 or not 1 <= suggestion_count <= 3:
        raise ValueError("period_report_claim_count_invalid")

    for insight in output.insights:
        if any(anchor not in allowed_evidence_ids for anchor in insight.evidence_ids):
            raise ValueError("period_report_evidence_anchor_invalid")
        if any(reason not in allowed_reason_keys for reason in insight.reason_keys):
            raise ValueError("period_report_reason_key_invalid")
        if _OUTPUT_BLOCKLIST.search(insight.text) or _URL_PATTERN.search(insight.text):
            raise ValueError("period_report_insight_contains_untrusted_content")
        if _OUTPUT_PERSONAL_UNSUPPORTED_CALCULATION_BLOCKLIST.search(insight.text):
            raise ValueError("period_report_insight_contains_unsupported_calculation")
        if _PERIOD_REPORT_UNSAFE_CLAIM_BLOCKLIST.search(insight.text):
            raise ValueError("period_report_insight_contains_unsafe_claim")
