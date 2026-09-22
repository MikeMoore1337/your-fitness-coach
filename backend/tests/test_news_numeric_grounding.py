from fitminiapp_api.services.news_drafts import grounded_number_tokens, quality_warnings


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
