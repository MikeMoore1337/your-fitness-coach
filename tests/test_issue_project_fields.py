"""Проверка полей GitHub Project без сетевых запросов и записи в GitHub."""

from __future__ import annotations

from scripts import issue_project_fields as audit


def issue(
    number: int = 123,
    *,
    status: str | None = "Backlog",
    priority: str | None = "P2 Medium",
    effort: str | None = "S",
    state: str = "OPEN",
    labels: list[str] | None = None,
    children: int = 0,
    issue_type: str | None = None,
    repo: str = audit.REPOSITORY,
) -> dict:
    values = {
        "Status": status,
        "Priority": priority,
        "Effort": effort,
    }
    return {
        "content": {
            "__typename": "Issue",
            "number": number,
            "state": state,
            "repository": {"nameWithOwner": repo},
            "issueType": {"name": issue_type} if issue_type else None,
            "subIssues": {"totalCount": children},
            "labels": {
                "nodes": [
                    {"name": label} for label in (["area:nutrition"] if labels is None else labels)
                ]
            },
        },
        "fieldValues": {
            "nodes": [
                {"name": value, "field": {"name": field}}
                for field, value in values.items()
                if value is not None
            ]
        },
    }


def test_complete_new_issue_passes_strict() -> None:
    findings, count = audit.inspect_items([issue()], number=123, strict=True)
    assert count == 1
    assert findings == []


def test_missing_fields_backlog_warns_but_strict_fails() -> None:
    item = issue(priority=None, effort=None, labels=[])
    advisory, count = audit.inspect_items([item])
    assert count == 1
    assert [finding.reason for finding in advisory] == [
        "Не заполнено обязательное поле/метка Priority.",
        "Не заполнено обязательное поле/метка Effort.",
        "Не заполнено обязательное поле/метка area:*.",
    ]
    assert {finding.severity for finding in advisory} == {"warning"}
    strict, _ = audit.inspect_items([item], number=123, strict=True)
    assert len(strict) == 3
    assert {finding.severity for finding in strict} == {"error"}


def test_ready_is_invalid_if_any_required_field_missing() -> None:
    findings, _ = audit.inspect_items([issue(status="Ready", effort=None)])
    assert findings == [audit.Finding(123, "error", "Не заполнено обязательное поле/метка Effort.")]


def test_epic_with_children_can_have_no_effort() -> None:
    findings, _ = audit.inspect_items([issue(children=2, effort=None)], strict=True)
    assert findings == []


def test_epic_by_issue_type_can_have_no_effort() -> None:
    findings, _ = audit.inspect_items([issue(issue_type="Epic", effort=None)], strict=True)
    assert findings == []


def test_closed_issue_requires_human_acceptance_not_automatic_done() -> None:
    findings, _ = audit.inspect_items([issue(state="CLOSED", status="Review")], strict=True)
    assert findings == [
        audit.Finding(
            123,
            "warning",
            "Issue закрыта, но статус не Done: проверить DoD вручную.",
        )
    ]


def test_closed_and_done_is_not_flagged_even_with_legacy_metadata() -> None:
    findings, _ = audit.inspect_items(
        [issue(state="CLOSED", status="Done", effort=None, priority=None)],
        strict=True,
    )
    assert findings == []


def test_open_done_is_reported() -> None:
    findings, _ = audit.inspect_items([issue(status="Done")])
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_unknown_status_is_error() -> None:
    findings, _ = audit.inspect_items([issue(status="Automatic")])
    assert findings == [audit.Finding(123, "error", "Отсутствует или неизвестен Status.")]


def test_issue_missing_from_project_fails() -> None:
    findings, count = audit.inspect_items([issue()], number=456, strict=True)
    assert count == 0
    assert findings == [audit.Finding(456, "error", "Issue отсутствует в YFC Development.")]


def test_all_mode_detects_new_issue_not_yet_added_to_project() -> None:
    findings, count = audit.inspect_items([issue()], open_numbers={123, 456})
    assert count == 1
    assert findings == [audit.Finding(456, "warning", "Открытая Issue отсутствует в Project.")]


def test_other_repositories_ignored() -> None:
    findings, count = audit.inspect_items(
        [issue(repo="example/unrelated")], open_numbers={123}, strict=True
    )
    assert count == 0
    assert findings == [audit.Finding(123, "error", "Открытая Issue отсутствует в Project.")]


def test_graphql_pagination_reads_all_pages(monkeypatch) -> None:
    calls = []

    def fake_api(*args, payload=None):
        calls.append(payload["variables"]["after"])
        assert args == ("graphql",)
        return {
            "data": {
                "node": {
                    "title": "YFC Development",
                    "items": {
                        "nodes": [issue(number=len(calls))],
                        "pageInfo": {
                            "hasNextPage": len(calls) == 1,
                            "endCursor": "next-page" if len(calls) == 1 else None,
                        },
                    },
                }
            }
        }

    monkeypatch.setattr(audit, "_gh_json", fake_api)
    items = audit.load_project_items()
    assert len(items) == 2
    assert calls == [None, "next-page"]


def test_graphql_error_does_not_claim_success(monkeypatch) -> None:
    monkeypatch.setattr(
        audit, "_gh_json", lambda *args, **kwargs: {"errors": [{"message": "Denied"}]}
    )
    try:
        audit.load_project_items()
    except RuntimeError as exc:
        assert "GitHub GraphQL" in str(exc)
    else:
        raise AssertionError("Access errors must not be treated as successful checks")


def test_issue_list_ignores_pull_requests_and_paginates(monkeypatch) -> None:
    calls = []

    def fake_api(path):
        calls.append(path)
        return [{"number": 7}, {"number": 8, "pull_request": {"url": "x"}}]

    monkeypatch.setattr(audit, "_gh_json", fake_api)
    assert audit.load_open_repository_issues() == {7}
    assert len(calls) == 1
