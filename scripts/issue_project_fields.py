"""Проверка полей GitHub Project YFC без записи в GitHub и без новых секретов."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Any

PROJECT_ID = "PVT_kwHOAoMKcc4BmnGq"
REPOSITORY = "MikeMoore1337/your-fitness-coach"
ALLOWED_STATUS = frozenset(
    {
        "Backlog",
        "Ready",
        "In Progress",
        "Review",
        "Owner Approval",
        "Release Check",
        "Done",
        "Blocked",
    }
)
ALLOWED_PRIORITY = frozenset({"P0 Critical", "P1 High", "P2 Medium", "P3 Low"})
ALLOWED_EFFORT = frozenset({"XS", "S", "M", "L", "XL"})

PROJECT_QUERY = """
query($projectId: ID!, $after: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      title
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          content {
            __typename
            ... on Issue {
              number
              state
              repository { nameWithOwner }
              issueType { name }
              subIssues(first: 1) { totalCount }
              labels(first: 30) { nodes { name } }
            }
          }
          fieldValues(first: 30) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2SingleSelectField { name } }
              }
            }
          }
        }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class Finding:
    """Одно проверяемое замечание без выгрузки описаний задач."""

    number: int
    severity: str
    reason: str


def _gh_json(*args: str, payload: dict[str, Any] | None = None) -> Any:
    """Вызвать установленный gh; не записывать токены или локальное состояние."""

    command = ["gh", "api", *args]
    input_bytes = None
    if payload is not None:
        command.extend(["--input", "-"])
        input_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        result = subprocess.run(command, input=input_bytes, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("Не найден gh CLI. Установите GitHub CLI и авторизуйтесь.") from exc
    if result.returncode:
        raise RuntimeError(
            "GitHub API недоступен. Проверьте gh auth status, доступ к проекту и scope project."
        )
    try:
        return json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("GitHub API вернул некорректный JSON/UTF-8.") from exc


def load_project_items(project_id: str = PROJECT_ID) -> list[dict[str, Any]]:
    """Постранично прочитать живые значения полей из закрытого пользовательского Project."""

    cursor: str | None = None
    result: list[dict[str, Any]] = []
    seen_cursors: set[str] = set()
    while True:
        response = _gh_json(
            "graphql",
            payload={
                "query": PROJECT_QUERY,
                "variables": {"projectId": project_id, "after": cursor},
            },
        )
        if response.get("errors"):
            raise RuntimeError("GitHub GraphQL отказал в доступе к Project или изменил схему.")
        node = response.get("data", {}).get("node")
        if not isinstance(node, dict) or node.get("title") != "YFC Development":
            raise RuntimeError("Ожидаемый GitHub Project 'YFC Development' недоступен.")
        connection = node["items"]
        result.extend(connection.get("nodes") or [])
        page = connection["pageInfo"]
        if not page["hasNextPage"]:
            return result
        cursor = page["endCursor"]
        if not cursor or cursor in seen_cursors:
            raise RuntimeError("Некорректная пагинация GitHub Projects.")
        seen_cursors.add(cursor)


def load_open_repository_issues(repository: str = REPOSITORY) -> set[int]:
    """Проверить, что все открытые Issues репозитория присутствуют в проекте."""

    numbers: set[int] = set()
    page = 1
    while True:
        response = _gh_json(f"repos/{repository}/issues?state=open&per_page=100&page={page}")
        if not isinstance(response, list):
            raise RuntimeError("Не удалось прочитать Issues репозитория.")
        numbers.update(
            item["number"]
            for item in response
            if isinstance(item, dict) and "pull_request" not in item
        )
        if len(response) < 100:
            return numbers
        page += 1


def _selected_fields(item: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for entry in item.get("fieldValues", {}).get("nodes") or []:
        if not isinstance(entry, dict):
            continue
        field = entry.get("field") or {}
        name = field.get("name")
        if name in {"Status", "Priority", "Effort"} and entry.get("name"):
            values[name] = entry["name"]
    return values


def inspect_items(
    items: list[dict[str, Any]],
    *,
    number: int | None = None,
    strict: bool = False,
    open_numbers: set[int] | None = None,
) -> tuple[list[Finding], int]:
    """Проверять факты; оценку DoR/DoD и решения владельца не подменять."""

    findings: list[Finding] = []
    indexed: dict[int, dict[str, Any]] = {}
    for item in items:
        issue = item.get("content") or {}
        if issue.get("__typename") != "Issue":
            continue
        if issue.get("repository", {}).get("nameWithOwner") != REPOSITORY:
            continue
        issue_number = issue["number"]
        if issue_number in indexed:
            findings.append(
                Finding(issue_number, "error", "Одна Issue присутствует в Project дважды.")
            )
        indexed[issue_number] = item

    if number is not None and number not in indexed:
        return [Finding(number, "error", "Issue отсутствует в YFC Development.")], 0
    if open_numbers is not None:
        for missing_number in sorted(open_numbers - indexed.keys()):
            findings.append(
                Finding(
                    missing_number,
                    "error" if strict else "warning",
                    "Открытая Issue отсутствует в Project.",
                )
            )

    selected = {number: indexed[number]} if number is not None else indexed
    for n, item in sorted(selected.items()):
        issue = item["content"]
        fields = _selected_fields(item)
        state = issue.get("state")
        status = fields.get("Status")
        if status not in ALLOWED_STATUS:
            findings.append(Finding(n, "error", "Отсутствует или неизвестен Status."))
        if state == "CLOSED":
            if status != "Done":
                findings.append(
                    Finding(
                        n, "warning", "Issue закрыта, но статус не Done: проверить DoD вручную."
                    )
                )
            continue

        if status == "Done":
            findings.append(
                Finding(n, "warning", "Issue открыта при статусе Done: проверить завершение.")
            )

        is_epic = (issue.get("issueType") or {}).get("name") == "Epic" or (
            (issue.get("subIssues") or {}).get("totalCount", 0) > 0
        )
        required = {
            "Priority": (fields.get("Priority") in ALLOWED_PRIORITY),
            "Effort": is_epic or (fields.get("Effort") in ALLOWED_EFFORT),
            "area:*": any(
                str(x.get("name", "")).startswith("area:")
                for x in (issue.get("labels") or {}).get("nodes") or []
            ),
        }
        for field, present in required.items():
            if not present:
                severity = "error" if strict or status == "Ready" else "warning"
                findings.append(
                    Finding(n, severity, f"Не заполнено обязательное поле/метка {field}.")
                )

    return findings, len(selected)


def main() -> int:
    """Запустить одиночную или общую read-only проверку полей проекта."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue", type=int, help="Номер Issue для проверки после создания/изменения."
    )
    parser.add_argument(
        "--strict", action="store_true", help="Считать пропуски полей ошибкой, включая Backlog."
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    if args.issue is not None and args.issue < 1:
        parser.error("--issue должен быть положительным номером.")

    try:
        items = load_project_items()
        opened = None if args.issue is not None else load_open_repository_issues()
        findings, inspected = inspect_items(
            items, number=args.issue, strict=args.strict, open_numbers=opened
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    report = {
        "inspected": inspected,
        "errors": sum(f.severity == "error" for f in findings),
        "warnings": sum(f.severity == "warning" for f in findings),
        "findings": [asdict(f) for f in findings],
    }
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"YFC Project: проверено {inspected}; "
            f"ошибок {report['errors']}; предупреждений {report['warnings']}."
        )
        for f in findings:
            print(f"  [{f.severity}] #{f.number}: {f.reason}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
