from fitminiapp_api.services.news_sources import parse_source_definition
from fitminiapp_api.services.news_taxonomy import (
    EDITORIAL_TOPICS,
    classify_editorial_text,
    evaluate_editorial_relevance,
    evaluate_publication_policy,
    style_checklist_warnings,
)


def test_taxonomy_keeps_sports_nutrition_separate_from_dietary_supplements() -> None:
    sports = classify_editorial_text(
        "Creatine and protein powder after resistance training",
        "The study compared sports nutrition products and hydration.",
        source_type="primary_research",
    )
    supplements = classify_editorial_text(
        "Vitamin D, omega-3 and probiotic supplement safety",
        "The review discusses dietary supplements and labeling.",
        source_type="systematic_review",
    )

    assert "sports_nutrition" in sports.topics
    assert sports.product_class == "sports_nutrition"
    assert "dietary_supplements" in supplements.topics
    assert supplements.product_class == "dietary_supplement"
    assert set(EDITORIAL_TOPICS) >= {"sports_nutrition", "dietary_supplements"}


def test_research_axis_does_not_replace_subject_topics() -> None:
    classification = classify_editorial_text(
        "Randomized trial of interval training and sleep recovery",
        "The research measured endurance and sleep outcomes.",
        source_type="primary_research",
    )

    assert classification.content_type == "research"
    assert "training" in classification.topics
    assert "cardio_endurance" in classification.topics
    assert "mobility_recovery_sleep" in classification.topics


def test_unknown_or_sensitive_material_is_never_auto_eligible() -> None:
    unknown = classify_editorial_text("A new report", "The report contains no clear topic.")
    unknown_policy = evaluate_publication_policy(
        unknown,
        auto_publish_enabled=True,
    )
    sensitive = classify_editorial_text(
        "Peptide dosage protocol",
        "Take a prescribed cycle for treatment.",
        source_type="primary_research",
    )
    sensitive_policy = evaluate_publication_policy(sensitive, auto_publish_enabled=True)

    assert unknown.primary_topic == "unknown"
    assert unknown_policy.publication_policy == "manual_required"
    assert sensitive_policy.publication_policy in {"manual_required", "blocked"}
    assert "sensitive_product_class" in sensitive_policy.risk_reasons


def test_relevance_requires_a_strong_subject_signal_and_allows_narrow_sports_pharmacology() -> None:
    weak = evaluate_editorial_relevance(
        "Muscle pain in patients",
        "A clinical medicine report.",
        "The article mentions muscle once in a long general medical context.",
    )
    training = evaluate_editorial_relevance(
        "Resistance training and muscle hypertrophy",
        "A controlled study measured strength outcomes in trained adults.",
    )
    pharmacology = evaluate_editorial_relevance(
        "Anabolic steroid use in bodybuilders",
        "A sports pharmacology review discusses performance-enhancing drug risks.",
    )
    generic_pharmacology = evaluate_editorial_relevance(
        "Testosterone treatment in patients",
        "A clinical medicine report on disease treatment.",
    )

    assert weak.allowed is False
    assert weak.reason_code == "topic_rejected:weak_or_context_only"
    assert training.allowed is True
    assert pharmacology.allowed is True
    assert generic_pharmacology.allowed is False


def test_style_checklist_is_deterministic_and_does_not_use_ai_detector() -> None:
    warnings = style_checklist_warnings("Я считаю: это гарантированный результат! Важно отметить!")

    assert "fake_personal_voice" in warnings
    assert "clickbait_or_guarantee" in warnings
    assert "excessive_exclamation" in warnings


def test_source_definition_persists_coverage_and_jurisdiction_metadata() -> None:
    source = parse_source_definition(
        {
            "id": "supplement-source",
            "name": "Supplement source",
            "type": "official_organization",
            "fetch_kind": "html_metadata",
            "url": "https://example.com/news",
            "topics": ["sports_nutrition", "dietary_supplements"],
            "authoritative": True,
            "freshness_policy": "current_month",
            "jurisdiction": ["RU"],
            "health_claim_limitations": "Market-specific.",
        }
    )

    assert source.topics == ("sports_nutrition", "dietary_supplements")
    assert source.authoritative is True
    assert source.jurisdiction == ("RU",)
