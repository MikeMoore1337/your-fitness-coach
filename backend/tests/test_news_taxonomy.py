from fitminiapp_api.services.news_sources import parse_source_definition
from fitminiapp_api.services.news_taxonomy import (
    EDITORIAL_TOPICS,
    OWNER_EDITORIAL_TOPICS,
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
    assert weak.reason_code == "topic_rejected:generic_clinical_medicine"
    assert training.allowed is True
    assert pharmacology.allowed is True
    assert generic_pharmacology.allowed is False


def test_owner_taxonomy_is_the_eight_agreed_editorial_domains() -> None:
    assert OWNER_EDITORIAL_TOPICS == (
        "fitness_training",
        "bodybuilding",
        "sports_bodybuilding_pharmacology",
        "peptides",
        "nutrition",
        "sports_nutrition",
        "dietary_supplements",
        "healthy_lifestyle",
    )


def test_relevance_rejects_production_false_positive_food_extraction() -> None:
    relevance = evaluate_editorial_relevance(
        "Multi-objective optimization of ultrasound-assisted extraction for enhanced "
        "bioactive recovery from bee bread",
        "The study improved phenolic extraction and measured amino acid concentration.",
    )

    assert relevance.allowed is False
    assert relevance.reason_code == "topic_rejected:generic_food_or_product"


def test_relevance_rejects_production_false_positive_clinical_knee_oa() -> None:
    relevance = evaluate_editorial_relevance(
        "Diagnostic agreement of nutritional screening tools in obesity-related "
        "knee osteoarthritis",
        "Patients were screened for malnutrition; low muscle mass was associated "
        "with concealed malnutrition.",
    )

    assert relevance.allowed is False
    assert relevance.reason_code == "topic_rejected:generic_clinical_medicine"


def test_relevance_rejects_unrelated_clinical_body_composition_population() -> None:
    relevance = evaluate_editorial_relevance(
        "Nutritional status, body composition and bone health in treatment-naive "
        "transgender and gender-diverse adolescents",
        "A clinical cohort assessed bone density, nutrition and body composition before treatment.",
    )

    assert relevance.allowed is False
    assert relevance.reason_code == "topic_rejected:generic_clinical_medicine"


def test_relevance_rejects_generic_caffeine_cognition_without_fitness_context() -> None:
    relevance = evaluate_editorial_relevance(
        "Acute caffeine intervention and cognitive performance in young people",
        "A systematic review evaluated attention and memory outcomes.",
    )

    assert relevance.allowed is False


def test_relevance_rejects_animal_or_food_supplementation_without_fitness_context() -> None:
    animal = evaluate_editorial_relevance(
        "Effects of in ovo supplementation of glucose and vitamin D3",
        "The poultry study measured eggshell temperature and embryonic development.",
    )

    assert animal.allowed is False
    assert animal.reason_code == "topic_rejected:generic_food_or_product"


def test_relevance_covers_all_missing_agreed_domains() -> None:
    peptide = evaluate_editorial_relevance(
        "Semaglutide and body composition during weight management",
        "The study measured fat loss and muscle preservation.",
    )
    nutrition = evaluate_editorial_relevance(
        "Dietary pattern and body composition during fat loss",
        "Energy intake and appetite were tracked during weight management.",
    )
    lifestyle = evaluate_editorial_relevance(
        "Sleep quality and recovery in resistance-trained athletes",
        "Sleep duration was associated with training recovery.",
    )
    supplement = evaluate_editorial_relevance(
        "Omega-3 dietary supplement safety and efficacy",
        "A systematic review evaluated supplementation outcomes.",
    )

    assert peptide.allowed is True
    assert "peptides" in peptide.topics
    assert nutrition.allowed is True
    assert "nutrition" in nutrition.topics
    assert lifestyle.allowed is True
    assert "healthy_lifestyle" in lifestyle.topics
    assert supplement.allowed is True
    assert "dietary_supplements" in supplement.topics


def test_clinical_context_can_be_rescued_only_by_direct_target_audience_relevance() -> None:
    sarcopenic = evaluate_editorial_relevance(
        "Sarcopenic obesity and muscle preservation during weight loss",
        "The review discusses body composition and resistance-training implications.",
    )
    athlete = evaluate_editorial_relevance(
        "Nutrition and recovery in medical student-athletes",
        "Training load, sleep and nutrition were monitored in athletes.",
    )

    assert sarcopenic.allowed is True
    assert athlete.allowed is True


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