"""Provider-neutral taxonomy and deterministic editorial risk policy.

This module deliberately contains no model/provider calls.  Classification is a recall-oriented
discovery hint; publication eligibility is a separate, fail-closed YFC decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

TAXONOMY_VERSION = "news-taxonomy-v1"
RISK_POLICY_VERSION = "news-risk-v1"
VOICE_PROFILE_VERSION = "yfc-news-voice-v1"
RELEVANCE_VERSION = "news-relevance-v2"

OWNER_EDITORIAL_TOPICS = (
    "fitness_training",
    "bodybuilding",
    "sports_bodybuilding_pharmacology",
    "peptides",
    "nutrition",
    "sports_nutrition",
    "dietary_supplements",
    "healthy_lifestyle",
)

EDITORIAL_TOPICS = (
    "sports_bodybuilding_pharmacology",
    "medicine",
    "health",
    "public_health",
    "fitness",
    "exercise",
    "training",
    "strength_hypertrophy",
    "cardio_endurance",
    "mobility_recovery_sleep",
    "bodybuilding",
    "nutrition",
    "food_products",
    "sports_nutrition",
    "dietary_supplements",
    "peptides",
    "healthy_lifestyle",
    "sports_medicine_injuries",
    "fitness_technology",
)
CONTENT_TYPES = (
    "research",
    "systematic_review",
    "guideline",
    "regulation",
    "safety_notice",
    "product_news",
    "explainer",
    "practical_guide",
    "industry_news",
)
PRODUCT_CLASSES = (
    "food",
    "sports_nutrition",
    "dietary_supplement",
    "medicine",
    "peptide",
    "fitness_product",
    "none",
    "unknown",
)
EVIDENCE_LEVELS = ("high", "moderate", "limited", "preliminary", "conflicting", "unknown")
RISK_LEVELS = ("low", "moderate", "high", "critical", "unknown")
PUBLICATION_POLICIES = ("blocked", "manual_required", "auto_eligible")

Topic = Literal[
    "sports_bodybuilding_pharmacology",
    "medicine",
    "health",
    "public_health",
    "fitness",
    "exercise",
    "training",
    "strength_hypertrophy",
    "cardio_endurance",
    "mobility_recovery_sleep",
    "bodybuilding",
    "nutrition",
    "food_products",
    "sports_nutrition",
    "dietary_supplements",
    "peptides",
    "healthy_lifestyle",
    "sports_medicine_injuries",
    "fitness_technology",
]


def _pattern(*parts: str) -> re.Pattern[str]:
    return re.compile("|".join(re.escape(part) for part in parts), re.IGNORECASE)


TOPIC_MARKERS: dict[str, tuple[str, ...]] = {
    "sports_bodybuilding_pharmacology": (
        "anabolic steroid",
        "anabolic-androgenic",
        "performance-enhancing drug",
        "performance enhancing drug",
        "ped use",
        "aas",
        "sarm",
        "selective androgen receptor",
        "testosterone",
        "growth hormone",
        "bodybuilding pharmacology",
        "анабол",
        "стероид",
        "допинг",
        "тестостерон",
        "сарм",
        "гормон роста",
        "фармаколог",
    ),
    "medicine": (
        "medicine",
        "medical",
        "clinical",
        "medication",
        "drug",
        "therapy",
        "patient",
        "disease",
        "медицин",
        "клиническ",
        "лекарств",
        "терапи",
        "пациент",
        "заболеван",
    ),
    "health": (
        "health",
        "wellbeing",
        "prevention",
        "здоров",
        "самочувств",
        "профилакти",
    ),
    "public_health": (
        "public health",
        "population health",
        "health authority",
        "общественн здоровье",
        "здравоохранен",
        "эпидеми",
    ),
    "fitness": (
        "fitness",
        "physical activity",
        "workout",
        "фитнес",
        "физическ актив",
    ),
    "exercise": (
        "exercise",
        "movement technique",
        "упражнен",
        "техник",
    ),
    "training": (
        "training",
        "training load",
        "workout program",
        "трениров",
        "нагрузк",
        "программ трениров",
    ),
    "strength_hypertrophy": (
        "strength",
        "resistance training",
        "hypertrophy",
        "muscle growth",
        "силов",
        "гипертроф",
        "рост мышц",
    ),
    "cardio_endurance": (
        "cardio",
        "aerobic",
        "endurance",
        "running",
        "cycling",
        "кардио",
        "вынослив",
        "бег",
        "велотрен",
    ),
    "mobility_recovery_sleep": (
        "mobility",
        "flexibility",
        "recovery",
        "sleep",
        "мобильност",
        "гибкост",
        "восстанов",
        "сон",
    ),
    "bodybuilding": (
        "bodybuilding",
        "bodybuilder",
        "physique competition",
        "bodybuilding",
        "бодибилд",
        "соревновательн подготовк",
    ),
    "nutrition": (
        "nutrition",
        "diet",
        "dietary pattern",
        "питани",
        "диет",
        "рацион",
    ),
    "food_products": (
        "food",
        "food science",
        "food product",
        "пищев",
        "продукт питания",
    ),
    "sports_nutrition": (
        "protein powder",
        "protein product",
        "creatine",
        "amino acid",
        "eaa",
        "bcaa",
        "carbohydrate gel",
        "electrolyte",
        "hydration product",
        "pre-workout",
        "preworkout",
        "recovery product",
        "спортивн питани",
        "протеин",
        "креатин",
        "аминокислот",
        "электролит",
        "изотоник",
        "предтренировоч",
    ),
    "dietary_supplements": (
        "dietary supplement",
        "vitamin",
        "mineral supplement",
        "omega-3",
        "omega 3",
        "probiotic",
        "prebiotic",
        "botanical extract",
        "herbal extract",
        "sleep supplement",
        "stress supplement",
        "weight-management supplement",
        "бад",
        "витамин",
        "минеральн добавк",
        "омега-3",
        "пробиотик",
        "пребиотик",
        "растительн экстракт",
        "добавк для сна",
    ),
    "peptides": (
        "peptide",
        "glp-1",
        "semaglutide",
        "tirzepatide",
        "пептид",
        "семаглутид",
        "тирзепатид",
    ),
    "healthy_lifestyle": (
        "healthy lifestyle",
        "habit",
        "behavior change",
        "образ жизни",
        "привычк",
        "поведенческ измен",
    ),
    "sports_medicine_injuries": (
        "sports medicine",
        "sports injury",
        "injury prevention",
        "rehabilitation",
        "спортивн медицин",
        "травм",
        "реабилитац",
    ),
    "fitness_technology": (
        "wearable",
        "fitness tracker",
        "fitness app",
        "training app",
        "gym equipment",
        "fitness technology",
        "носим устройств",
        "фитнес-трекер",
        "приложени для трениров",
        "тренажер",
    ),
}

CONTENT_MARKERS: dict[str, tuple[str, ...]] = {
    "systematic_review": (
        "systematic review",
        "meta-analysis",
        "метаанализ",
        "систематическ обзор",
    ),
    "research": (
        "randomized",
        "clinical trial",
        "cohort",
        "study",
        "research",
        "исследован",
        "испытан",
    ),
    "guideline": (
        "guideline",
        "consensus",
        "recommendation",
        "руководств",
        "консенсус",
        "рекомендац",
    ),
    "regulation": (
        "regulation",
        "regulatory",
        "approval",
        "законодательств",
        "регулятор",
        "одобрил",
    ),
    "safety_notice": (
        "recall",
        "safety alert",
        "contamination",
        "adverse event",
        "отзыв",
        "загрязнен",
        "нежелательн явлен",
    ),
    "product_news": ("launch", "new product", "product news", "запуск продукт", "новый продукт"),
    "practical_guide": ("how to", "guide", "применять", "как выбрать", "практическ руководств"),
    "industry_news": ("industry", "company", "market", "индустри", "рынок", "компани"),
}

PRODUCT_MARKERS: dict[str, tuple[str, ...]] = {
    "medicine": TOPIC_MARKERS["medicine"] + ("prescription", "рецептурн"),
    "peptide": TOPIC_MARKERS["peptides"],
    "sports_nutrition": TOPIC_MARKERS["sports_nutrition"],
    "dietary_supplement": TOPIC_MARKERS["dietary_supplements"],
    "fitness_product": TOPIC_MARKERS["fitness_technology"],
    "food": TOPIC_MARKERS["food_products"],
}

PRESCRIPTIVE_RISK_MARKERS = (
    "dosage",
    "dose",
    "cycle",
    "protocol",
    "prescribe",
    "take ",
    "дозиров",
    "курс ",
    "схем прием",
    "назначь",
    "принимайте",
)
CRITICAL_RISK_MARKERS = (
    "ignore previous instructions",
    "system prompt",
    "игнорируй предыдущие инструкции",
    "системный промпт",
    "guaranteed result",
    "гарантированн результат",
    "miracle cure",
    "чудо-средств",
)
PRELIMINARY_MARKERS = (
    "preclinical",
    "animal study",
    "in vitro",
    "pilot study",
    "preliminary",
    "предклиническ",
    "на животных",
    "in vitro",
    "пилотн исследован",
    "предварительн",
)
CONFLICT_MARKERS = ("conflicting", "mixed results", "противоречив", "неоднозначн")


@dataclass(frozen=True)
class EditorialClassification:
    primary_topic: str
    topics: tuple[str, ...]
    content_type: str
    product_class: str
    evidence_level: str
    risk_level: str
    audience: str
    geography: tuple[str, ...]
    classification_version: str
    classification_reasons: tuple[str, ...]
    risk_reasons: tuple[str, ...]


@dataclass(frozen=True)
class PublicationPolicy:
    publication_policy: str
    risk_reasons: tuple[str, ...]
    risk_policy_version: str = RISK_POLICY_VERSION


@dataclass(frozen=True)
class EditorialRelevance:
    allowed: bool
    reason_code: str
    strength: str
    topics: tuple[str, ...]
    relevance_version: str = RELEVANCE_VERSION


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


_RELEVANCE_MARKERS: dict[str, tuple[str, ...]] = {
    "fitness_training": (
        "strength training",
        "resistance training",
        "resistance exercise",
        "hypertrophy",
        "muscle growth",
        "powerlifting",
        "weightlifting",
        "training load",
        "training volume",
        "periodization",
        "workout program",
        "interval training",
        "endurance training",
        "endurance performance",
        "aerobic training",
        "athletic performance",
        "sports performance",
        "sports injury",
        "injury prevention",
        "sports rehabilitation",
        "силов трен",
        "гипертроф",
        "рост мышц",
        "пауэрлифт",
        "тренировочн нагрузк",
        "объем трениров",
        "периодизац",
        "программ трениров",
        "спортивн травм",
        "реабилитац спортсмен",
    ),
    "bodybuilding": (
        "bodybuilding",
        "bodybuilder",
        "physique competition",
        "physique athlete",
        "contest preparation",
        "contest prep",
        "бодибилд",
        "соревновательн подготовк",
    ),
    "sports_bodybuilding_pharmacology": TOPIC_MARKERS["sports_bodybuilding_pharmacology"],
    "peptides": (
        "peptide",
        "glp-1",
        "glp 1",
        "semaglutide",
        "tirzepatide",
        "retatrutide",
        "пептид",
        "гпп-1",
        "семаглутид",
        "тирзепатид",
        "ретатрутид",
    ),
    "nutrition": (
        "sports nutrition",
        "nutrition",
        "dietary pattern",
        "diet quality",
        "energy intake",
        "calorie intake",
        "energy balance",
        "body composition",
        "weight management",
        "weight loss",
        "fat loss",
        "muscle preservation",
        "sarcopenic obesity",
        "appetite",
        "питани",
        "рацион",
        "энергетическ баланс",
        "состав тел",
        "снижен веса",
        "снижен жира",
        "контроль веса",
        "аппетит",
        "саркопеническ ожирен",
    ),
    "sports_nutrition": (
        "sports nutrition",
        "sport nutrition",
        "protein powder",
        "protein supplement",
        "dietary protein",
        "protein intake",
        "creatine",
        "bcaa",
        "eaa",
        "carbohydrate gel",
        "electrolyte",
        "pre-workout",
        "preworkout",
        "спортивн питани",
        "протеин",
        "креатин",
        "электролит",
        "изотоник",
        "предтренировоч",
    ),
    "dietary_supplements": (
        "dietary supplement",
        "supplement use",
        "supplementation",
        "supplement safety",
        "supplement efficacy",
        "omega-3",
        "omega 3",
        "probiotic",
        "prebiotic",
        "vitamin d supplement",
        "mineral supplement",
        "бад",
        "пищев добавк",
        "безопасност добавк",
        "эффективност добавк",
        "омега-3",
        "пробиотик",
        "пребиотик",
    ),
    "healthy_lifestyle": (
        "physical activity",
        "sleep quality",
        "sleep duration",
        "sleep and recovery",
        "exercise recovery",
        "training recovery",
        "healthy lifestyle",
        "behavior change",
        "habit formation",
        "sedentary behavior",
        "физическ актив",
        "качество сна",
        "продолжительност сна",
        "восстановлени после трениров",
        "здоров образ жизни",
        "изменен привыч",
        "малоподвижн",
    ),
}

_GENERIC_REJECTION_MARKERS = {
    "generic_clinical_medicine": (
        "clinical",
        "clinic",
        "clinical treatment",
        "clinical care",
        "patient",
        "patients",
        "hospital",
        "diagnostic",
        "diagnosis",
        "disease treatment",
        "therapy",
        "treatment-naïve",
        "treatment-naive",
        "treatment naive",
        "osteoarthritis",
        "oncology",
        "cancer",
        "клиническ лечен",
        "пациент",
        "диагност",
        "терапи",
        "лечение",
        "заболеван",
    ),
    "generic_public_health": (
        "public health",
        "population health",
        "epidemiology",
        "общественн здравоохран",
        "эпидеми",
    ),
    "generic_cognition": (
        "cognitive performance",
        "cognitive function",
        "attention and memory",
        "memory outcomes",
        "attention outcomes",
        "когнитивн функц",
        "когнитивн результат",
        "памят",
        "внимани",
    ),
    "generic_food_or_product": (
        "food science",
        "food technology",
        "food processing",
        "food extraction",
        "ultrasound-assisted extraction",
        "phenolic compound",
        "antiradical",
        "food industry",
        "agricultural",
        "poultry",
        "chicken",
        "broiler",
        "egg",
        "eggshell",
        "embryo",
        "in ovo",
        "bee bread",
        "company launch",
        "пищев технолог",
        "экстракц",
        "фенольн соединен",
        "пищев промышлен",
        "новый продукт",
    ),
}

_DIRECT_RESCUE_MARKERS = (
    "athlete",
    "athletic",
    "sport performance",
    "sports performance",
    "exercise performance",
    "resistance training",
    "strength training",
    "hypertrophy",
    "bodybuilding",
    "bodybuilder",
    "physique athlete",
    "training load",
    "workout",
    "sarcopenic obesity",
    "muscle preservation",
    "fat loss",
    "contest preparation",
    "спортсмен",
    "спортивн результат",
    "силов трен",
    "гипертроф",
    "бодибилд",
    "тренировочн нагрузк",
    "саркопеническ ожирен",
    "сохранен мышц",
    "снижен жира",
)

_WEIGHT_MANAGEMENT_CONTEXT = (
    "body composition",
    "weight management",
    "weight loss",
    "fat loss",
    "obesity treatment",
    "appetite",
    "sarcopenic obesity",
    "muscle preservation",
    "состав тел",
    "контроль веса",
    "снижен веса",
    "снижен жира",
    "аппетит",
    "саркопеническ ожирен",
    "сохранен мышц",
)

_SUPPLEMENT_CONTEXT = (
    *_WEIGHT_MANAGEMENT_CONTEXT,
    "athlete",
    "sport",
    "exercise",
    "training",
    "performance",
    "recovery",
    "bodybuilding",
    "physique",
    "muscle",
    "strength",
    "dietary supplement",
    "supplement safety",
    "supplement efficacy",
    "athletic",
    "спортсмен",
    "трениров",
    "результат",
    "восстанов",
    "бодибилд",
    "мышц",
    "силов",
    "бад",
    "безопасност добавк",
    "эффективност добавк",
)

_NUTRITION_CONTEXT = (
    *_WEIGHT_MANAGEMENT_CONTEXT,
    "athlete",
    "sport",
    "exercise",
    "training",
    "performance",
    "recovery",
    "healthy lifestyle",
    "спортсмен",
    "трениров",
    "результат",
    "восстанов",
    "здоров образ жизни",
)

_PEPTIDE_CONTEXT = (
    *_WEIGHT_MANAGEMENT_CONTEXT,
    "performance",
    "athlete",
    "bodybuilding",
    "physique",
    "спортсмен",
    "бодибилд",
)

_HEALTHY_LIFESTYLE_CONTEXT = (
    "physical activity",
    "exercise",
    "training",
    "athlete",
    "recovery",
    "sleep",
    "sedentary",
    "habit",
    "физическ актив",
    "трениров",
    "спортсмен",
    "восстанов",
    "сон",
    "малоподвиж",
    "привыч",
)


def _matched_relevance_topics(subject: str, normalized: str) -> tuple[str, ...]:
    return tuple(
        topic
        for topic in OWNER_EDITORIAL_TOPICS
        if _contains_any(
            normalized,
            tuple(marker.casefold() for marker in _RELEVANCE_MARKERS[topic]),
        )
        and _contains_any(
            subject,
            tuple(marker.casefold() for marker in _RELEVANCE_MARKERS[topic]),
        )
    )


def evaluate_editorial_relevance(
    title: str,
    summary: str = "",
    content: str = "",
) -> EditorialRelevance:
    """Allow only direct, owner-relevant fitness/bodybuilding candidates."""

    subject = f"{title} {summary}".casefold()
    normalized = f"{subject} {content[:32_000]}".casefold()
    matched = _matched_relevance_topics(subject, normalized)
    direct_context = _contains_any(
        subject,
        tuple(marker.casefold() for marker in _DIRECT_RESCUE_MARKERS),
    )

    rejection = next(
        (
            code
            for code, markers in _GENERIC_REJECTION_MARKERS.items()
            if _contains_any(subject, tuple(marker.casefold() for marker in markers))
        ),
        None,
    )
    if rejection and not direct_context:
        return EditorialRelevance(False, f"topic_rejected:{rejection}", "none", ())

    if not matched:
        return EditorialRelevance(
            False,
            "topic_rejected:no_relevant_training_domain",
            "none",
            (),
        )

    if "peptides" in matched and not _contains_any(
        subject,
        tuple(marker.casefold() for marker in _PEPTIDE_CONTEXT),
    ):
        matched = tuple(topic for topic in matched if topic != "peptides")

    if "nutrition" in matched and not _contains_any(
        subject,
        tuple(marker.casefold() for marker in _NUTRITION_CONTEXT),
    ):
        matched = tuple(topic for topic in matched if topic != "nutrition")

    if "dietary_supplements" in matched and not _contains_any(
        subject,
        tuple(marker.casefold() for marker in _SUPPLEMENT_CONTEXT),
    ):
        matched = tuple(topic for topic in matched if topic != "dietary_supplements")

    if "healthy_lifestyle" in matched and not _contains_any(
        subject,
        tuple(marker.casefold() for marker in _HEALTHY_LIFESTYLE_CONTEXT),
    ):
        matched = tuple(topic for topic in matched if topic != "healthy_lifestyle")

    # Generic amino-acid/extraction or incidental "recovery" wording must not create
    # sports-nutrition/training eligibility on its own.
    if "sports_nutrition" in matched and any(
        marker in subject for marker in ("extraction", "phenolic", "antiradical", "bee bread")
    ):
        matched = tuple(topic for topic in matched if topic != "sports_nutrition")

    if not matched:
        return EditorialRelevance(
            False,
            "topic_rejected:weak_or_context_only",
            "none",
            (),
        )

    strong_topics = {
        "fitness_training",
        "bodybuilding",
        "sports_bodybuilding_pharmacology",
        "peptides",
        "sports_nutrition",
        "dietary_supplements",
    }
    strength = "strong" if any(topic in strong_topics for topic in matched) else "moderate"
    return EditorialRelevance(
        True,
        f"topic_allowed:{matched[0]}",
        strength,
        matched,
    )


def classify_editorial_text(
    title: str,
    summary: str = "",
    *,
    source_type: str | None = None,
    geography: tuple[str, ...] = (),
) -> EditorialClassification:
    normalized = f"{title} {summary}".casefold()
    topics = tuple(
        topic
        for topic in EDITORIAL_TOPICS
        if _contains_any(normalized, tuple(marker.casefold() for marker in TOPIC_MARKERS[topic]))
    )
    reasons = tuple(f"topic_marker:{topic}" for topic in topics)
    primary_topic = topics[0] if topics else "unknown"
    content_type = next(
        (
            content_type
            for content_type in CONTENT_TYPES
            if _contains_any(
                normalized,
                tuple(marker.casefold() for marker in CONTENT_MARKERS.get(content_type, ())),
            )
        ),
        "explainer",
    )
    product_class = next(
        (
            product_class
            for product_class in PRODUCT_CLASSES
            if product_class not in {"none", "unknown"}
            and _contains_any(
                normalized,
                tuple(marker.casefold() for marker in PRODUCT_MARKERS[product_class]),
            )
        ),
        "none" if topics else "unknown",
    )
    if source_type in {"systematic_review", "primary_research"} and content_type == "explainer":
        content_type = "research"
    if source_type == "systematic_review":
        content_type = "systematic_review"
    if source_type in {"official_organization", "official_product"} and content_type == "explainer":
        content_type = "guideline" if "guideline" in normalized else "product_news"

    evidence_level = "unknown"
    if content_type == "systematic_review" or source_type == "systematic_review":
        evidence_level = "high"
    elif (
        source_type == "primary_research"
        or content_type == "research"
        or source_type in {"official_organization", "official_product"}
    ):
        evidence_level = "moderate"
    if _contains_any(normalized, PRELIMINARY_MARKERS):
        evidence_level = "preliminary"
    if _contains_any(normalized, CONFLICT_MARKERS):
        evidence_level = "conflicting"

    risk_reasons: list[str] = []
    if not topics:
        risk_reasons.append("ambiguous_taxonomy")
    if _contains_any(normalized, PRESCRIPTIVE_RISK_MARKERS):
        risk_reasons.append("prescriptive_or_individualized_language")
    if _contains_any(normalized, CRITICAL_RISK_MARKERS):
        risk_reasons.append("unsafe_or_prompt_injection_content")
    if evidence_level in {"preliminary", "conflicting"}:
        risk_reasons.append(f"evidence_{evidence_level}")
    if any(
        topic in topics
        for topic in (
            "medicine",
            "peptides",
            "sports_medicine_injuries",
            "sports_bodybuilding_pharmacology",
        )
    ):
        risk_reasons.append("sensitive_health_topic")
    if product_class in {"medicine", "peptide"}:
        risk_reasons.append("sensitive_product_class")
    risk_level = (
        "critical"
        if "unsafe_or_prompt_injection_content" in risk_reasons
        else (
            "high"
            if any(
                reason in risk_reasons
                for reason in (
                    "prescriptive_or_individualized_language",
                    "sensitive_health_topic",
                    "sensitive_product_class",
                )
            )
            else ("moderate" if risk_reasons else ("low" if topics else "unknown"))
        )
    )
    audience = (
        "practitioners"
        if any(topic in topics for topic in ("medicine", "sports_medicine_injuries"))
        else "general"
    )
    return EditorialClassification(
        primary_topic=primary_topic,
        topics=topics,
        content_type=content_type,
        product_class=product_class,
        evidence_level=evidence_level,
        risk_level=risk_level,
        audience=audience,
        geography=tuple(dict.fromkeys(geography)),
        classification_version=TAXONOMY_VERSION,
        classification_reasons=reasons or ("no_topic_marker:manual_classification",),
        risk_reasons=tuple(dict.fromkeys(risk_reasons)),
    )


def evaluate_publication_policy(
    classification: EditorialClassification,
    *,
    quality_warnings: tuple[str, ...] = (),
    source_provenance_valid: bool = True,
    exact_snapshot_valid: bool = True,
    kill_switch_active: bool = True,
    auto_publish_enabled: bool = False,
) -> PublicationPolicy:
    reasons = list(classification.risk_reasons)
    reasons.extend(quality_warnings)
    if not source_provenance_valid:
        reasons.append("source_provenance_invalid")
    if not exact_snapshot_valid:
        reasons.append("exact_snapshot_invalid")
    if not kill_switch_active:
        reasons.append("kill_switch_inactive")
    reasons = list(dict.fromkeys(reasons))
    if any(
        reason in {"unsafe_or_prompt_injection_content", "critical_warning", "unsupported_number"}
        for reason in reasons
    ):
        policy = "blocked"
    elif (
        reasons
        or classification.primary_topic == "unknown"
        or classification.product_class == "unknown"
    ):
        policy = "manual_required"
    elif not auto_publish_enabled:
        policy = "manual_required"
        reasons.append("auto_publish_disabled")
    elif not kill_switch_active or not source_provenance_valid or not exact_snapshot_valid:
        policy = "manual_required"
    elif (
        classification.risk_level == "low"
        and classification.evidence_level in {"high", "moderate"}
        and classification.content_type
        in {"research", "systematic_review", "guideline", "explainer", "product_news"}
        and classification.product_class not in {"medicine", "peptide"}
    ):
        policy = "auto_eligible"
    else:
        policy = "manual_required"
        reasons.append("low_risk_gate_not_satisfied")
    return PublicationPolicy(
        publication_policy=policy,
        risk_reasons=tuple(dict.fromkeys(reasons)),
    )


def style_checklist_warnings(text: str) -> tuple[str, ...]:
    """Deterministic editorial lint; it is not an authorship or AI-detector check."""

    normalized = text.casefold()
    warnings: list[str] = []
    if _contains_any(
        normalized, ("как ии", "как искусственный интеллект", "в этом материале мы рассмотрим")
    ):
        warnings.append("ai_meta_or_template_language")
    if _contains_any(
        normalized, ("я считаю", "по моему опыту", "мы лично рекомендуем", "мой опыт")
    ):
        warnings.append("fake_personal_voice")
    if text.count("!") > 1:
        warnings.append("excessive_exclamation")
    if re.search(
        r"(?:\bважно отметить\b|\bследует подчеркнуть\b).*(?:\bважно отметить\b|\bследует подчеркнуть\b)",
        normalized,
    ):
        warnings.append("mechanical_repetition")
    if _contains_any(
        normalized, ("100% гарант", "гарантированный результат", "результат без усилий")
    ):
        warnings.append("clickbait_or_guarantee")
    if re.search(r"[«\"](?:я|мы)\s+(?:говорит|считает|рекомендует)", normalized):
        warnings.append("invented_quote_or_voice")
    return tuple(dict.fromkeys(warnings))
