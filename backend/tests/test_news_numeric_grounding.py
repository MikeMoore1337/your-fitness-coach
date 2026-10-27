from datetime import datetime

from fitminiapp_api.services.news_drafts import grounded_number_tokens, quality_warnings
from fitminiapp_api.services.news_hermes import _source_grounding_context


def test_numeric_grounding_normalizes_decimal_spacing_and_equivalent_units() -> None:
    fields = {
        "headline": "Разбор протокола исследования",
        "summary": "Авторы описали протокол с 1,5 г вещества и ограничения исследования.",
        "why_it_matters": "Материал требует редакторской проверки.",
    }

    warnings = quality_warnings(
        fields,
        source_title="Исследование протокола",
        source_summary="Описание протокола.",
        source_context="В протоколе использовали 1.5 g вещества.",
    )

    assert "unsupported_number" not in warnings
    assert grounded_number_tokens(
        source_title="Исследование протокола",
        source_summary="Описание протокола.",
        source_context="В протоколе использовали 1.5 g вещества.",
    ) == ("1.5г",)


def test_numeric_grounding_normalizes_percent_spacing() -> None:
    fields = {
        "headline": "Разбор результатов исследования",
        "summary": "В источнике указано изменение на 12 %.",
        "why_it_matters": "Материал требует редакторской проверки.",
    }

    warnings = quality_warnings(
        fields,
        source_title="Исследование результатов",
        source_summary="Источник сообщает об изменении на 12%.",
    )

    assert "unsupported_number" not in warnings


def test_hermes_grounding_includes_trusted_publisher_and_publication_date() -> None:
    source_context = _source_grounding_context(
        "Публичный источник без числовых утверждений.",
        publisher="Journal 7",
        published_at=datetime(2026, 9, 22),
    )
    fields = {
        "headline": "Исследование 2026 года",
        "summary": "Авторы описали результаты исследования.",
        "why_it_matters": "Материал из Journal 7 требует редакторской проверки.",
    }

    warnings = quality_warnings(
        fields,
        source_title="Исследование состава тела",
        source_summary="Описание исследования.",
        source_context=source_context,
    )
    tokens = grounded_number_tokens(
        source_title="Исследование состава тела",
        source_summary="Описание исследования.",
        source_context=source_context,
    )

    assert "unsupported_number" not in warnings
    assert "2026" in tokens
    assert "7" in tokens
