"""Тесты необязательных проверок классификации Issues."""

from __future__ import annotations

from scripts.issue_governance import LABEL_OPTIONS, audit_items, suggested_prefix, title_errors


def test_approved_prefixes() -> None:
    cases = [
        "[Product V13] V13-01 - Массовый ввод",
        "[Bug] Клавиатура закрывает поиск",
        "[UI Backlog] Сделать карточки компактнее",
        "[Improvement] Ускорить поиск продуктов",
        "[Engineering] Оптимизировать фикстуры",
        "[Operations] Проверить резервные копии",
        "[Growth] Улучшить SEO",
    ]
    assert all(not title_errors(title) for title in cases)


def test_rejects_legacy_and_multiple_prefixes() -> None:
    cases = [
        "[Product v13] Старый формат",
        "[Product Vxx] Без номера",
        "[Fix] Исправить поиск",
        "[Bug][Mobile] Поиск перекрыт",
        "[Bug] [Mobile] Поиск перекрыт",
        "[Bug]   ",
        "Заголовок без префикса",
        "[Bug] Да",
    ]
    assert all(title_errors(title) for title in cases)


def test_version_hint_is_conservative() -> None:
    assert suggested_prefix("V13-01 - Справочник") == "[Product V13]"
    assert suggested_prefix("[Product v12][V12-02] Экспорт") == "[Product V12]"
    assert suggested_prefix("[V11-REC-01][P0] Резервные копии") == "[Product V11]"
    assert suggested_prefix("[Mobile] Таймер переключает подход") is None
    assert suggested_prefix("[Bug] Таймер переключает подход") == "[Bug]"


def test_inventory_does_not_consider_pr_or_invent_priority() -> None:
    result = audit_items(
        [
            {"number": 5, "title": "V13-01 - Функция"},
            {"number": 6, "title": "[Mobile] Сбой"},
            {"number": 7, "title": "[Bug] Сбой", "pull_request": {"url": "x"}},
        ]
    )
    assert "Количество Issues: 2" in result
    assert "[Product V13]" in result
    assert "Решение владельца" in result
    assert "#7" not in result
    assert "Priority, Effort, Status" in result


def test_label_contract() -> None:
    assert len(LABEL_OPTIONS) == 18
    assert {"area:nutrition", "gate:visual-approval", "spike", "regression"} <= LABEL_OPTIONS
