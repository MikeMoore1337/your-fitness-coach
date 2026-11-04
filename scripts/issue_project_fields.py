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
PROJECT_TITLES = {"YFC Development", "Your Fitness Coach - Delivery Board"}
ALLOWED_STATUS = frozenset({"Backlog", "Ready", "In progress", "In review", "Blocked", "Done"})
ALLOWED_PRIORITY = frozenset({"P0", "P1", "P2", "P3"})
ALLOWED_AREA = frozenset(
    {
        "Workout",
        "Programs",
        "Nutrition",
        "Progress",
        "Coach OS",
        "UI & Accessibility",
        "Backend & Database",
        "Infrastructure & CI",
        "Security",
        "Growth",
        "Other",
    }
)
LEGACY_STATUS = frozenset(
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
LEGACY_PRIORITY = frozenset({"P0 Critical", "P1 High", "P2 Medium", "P3 Low"})
ALLOWED_EFFORT = frozenset({"XS", "S", "M", "L", "XL"})

PROJECT_QUERY = """
query($projectId: ID!, $after: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      id
      title
      url
      owner { ... on User { login } ... on Organization { login } }
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          isArchived
          content {
            __typename
            ... on Issue {
              number
              state
              stateReason
              title
              repository { nameWithOwner }
              issueType { name }
              subIssues(first: 1) { totalCount }
              labels(first: 30) { nodes { name } }
            }
            ... on PullRequest {
              number
              state
              title
              isDraft
              repository { nameWithOwner }
            }
          }
          fieldValues(first: 100) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2SingleSelectField { name } }
              }
              ... on ProjectV2ItemFieldTextValue {
                text
                field { ... on ProjectV2Field { name } }
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
        if (
            not isinstance(node, dict)
            or node.get("id") != project_id
            or node.get("title") not in PROJECT_TITLES
            or (node.get("owner") or {}).get("login", "").lower() != "mikemoore1337"
        ):
            raise RuntimeError("Ожидаемый GitHub Project YFC недоступен.")
        connection = node["items"]
        result.extend(connection.get("nodes") or [])
        page = connection["pageInfo"]
        if not page["hasNextPage"]:
            return result
        cursor = page["endCursor"]
        if not cursor or cursor in seen_cursors:
            raise RuntimeError("Некорректная пагинация GitHub Projects.")
        seen_cursors.add(cursor)


def load_open_repository_items(repository: str = REPOSITORY) -> dict[int, str]:
    """Прочитать все открытые Issues и PR без подмены одного типа другим."""

    numbers: dict[int, str] = {}
    page = 1
    while True:
        response = _gh_json(f"repos/{repository}/issues?state=open&per_page=100&page={page}")
        if not isinstance(response, list):
            raise RuntimeError("Не удалось прочитать Issues репозитория.")
        for item in response:
            if not isinstance(item, dict) or not isinstance(item.get("number"), int):
                raise RuntimeError("GitHub вернул некорректный элемент очереди.")
            numbers[item["number"]] = "PullRequest" if "pull_request" in item else "Issue"
        if len(response) < 100:
            return numbers
        page += 1


def load_open_repository_issues(repository: str = REPOSITORY) -> set[int]:
    """Совместимый read-only вызов для старого аудита только Issues."""

    return {
        number for number, kind in load_open_repository_items(repository).items() if kind == "Issue"
    }


def _selected_fields(item: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for entry in item.get("fieldValues", {}).get("nodes") or []:
        if not isinstance(entry, dict):
            continue
        field = entry.get("field") or {}
        name = field.get("name")
        if name in {"Status", "Priority", "Effort", "Area"} and entry.get("name"):
            values[name] = entry["name"]
        elif name == "Release" and isinstance(entry.get("text"), str):
            values[name] = entry["text"]
    return values


def inspect_items(
    items: list[dict[str, Any]],
    *,
    number: int | None = None,
    strict: bool = False,
    open_numbers: set[int] | None = None,
    open_items: dict[int, str] | None = None,
    schema: str = "delivery",
) -> tuple[list[Finding], int]:
    """Проверять факты; оценку DoR/DoD и решения владельца не подменять."""

    if schema not in {"delivery", "legacy"}:
        raise ValueError("Неизвестная схема Project.")
    allowed_status = LEGACY_STATUS if schema == "legacy" else ALLOWED_STATUS
    allowed_priority = LEGACY_PRIORITY if schema == "legacy" else ALLOWED_PRIORITY
    findings: list[Finding] = []
    indexed: dict[int, dict[str, Any]] = {}
    for item in items:
        issue = item.get("content") or {}
        kind = issue.get("__typename")
        if kind not in ({"Issue"} if schema == "legacy" else {"Issue", "PullRequest"}):
            continue
        if issue.get("repository", {}).get("nameWithOwner") != REPOSITORY:
            continue
        issue_number = issue["number"]
        if issue_number in indexed:
            findings.append(
                Finding(issue_number, "error", "Один объект присутствует в Project дважды.")
            )
        indexed[issue_number] = item

    if number is not None and number not in indexed:
        return [Finding(number, "error", "Issue/PR отсутствует в Project YFC.")], 0
    if open_numbers is not None:
        for missing_number in sorted(open_numbers - indexed.keys()):
            findings.append(
                Finding(
                    missing_number,
                    "error" if strict else "warning",
                    "Открытая Issue отсутствует в Project.",
                )
            )

    if open_items is not None:
        for missing_number in sorted(open_items.keys() - indexed.keys()):
            kind = "PR" if open_items[missing_number] == "PullRequest" else "Issue"
            findings.append(
                Finding(
                    missing_number,
                    "error" if strict else "warning",
                    f"Открытый объект {kind} отсутствует в Project.",
                )
            )
        for shared_number in sorted(open_items.keys() & indexed.keys()):
            content = indexed[shared_number]["content"]
            if (
                content.get("__typename") != open_items[shared_number]
                or content.get("state") != "OPEN"
            ):
                findings.append(
                    Finding(
                        shared_number,
                        "error",
                        "Снимки Project и открытой очереди расходятся; повторите чтение.",
                    )
                )

    selected = {number: indexed[number]} if number is not None else indexed
    for n, item in sorted(selected.items()):
        issue = item["content"]
        fields = _selected_fields(item)
        state = issue.get("state")
        is_pr = issue.get("__typename") == "PullRequest"
        status = fields.get("Status")
        if state not in ({"OPEN", "CLOSED", "MERGED"} if is_pr else {"OPEN", "CLOSED"}):
            findings.append(Finding(n, "error", "Отсутствует или неизвестно состояние Issue/PR."))
        if status not in allowed_status:
            findings.append(Finding(n, "error", "Отсутствует или неизвестен Status."))
        if state == "MERGED" and is_pr:
            if status != "Done":
                findings.append(Finding(n, "warning", "PR объединён, но статус не Done."))
            continue
        if state == "CLOSED":
            if status == "Done" and (is_pr or issue.get("stateReason") == "NOT_PLANNED"):
                findings.append(
                    Finding(
                        n,
                        "error" if schema == "delivery" else "warning",
                        "Закрытие без выполнения не доказывает Done; проверить причину.",
                    )
                )
            if status != "Done":
                findings.append(
                    Finding(
                        n, "warning", "Объект закрыт, но статус не Done: проверить DoD вручную."
                    )
                )
            continue

        if status == "Done":
            findings.append(Finding(n, "error", "Открытый Issue/PR имеет ложный статус Done."))
        if item.get("isArchived"):
            findings.append(Finding(n, "error", "Открытый объект скрыт в архиве Project."))
        if schema == "delivery":
            if fields.get("Release") in {"V13", "V14"} and status not in {"Backlog", "Blocked"}:
                findings.append(Finding(n, "error", "Неактивная версия V13/V14 попала в работу."))
            if "[HOLD]" in issue.get("title", "").upper() and status != "Blocked":
                findings.append(Finding(n, "error", "HOLD должен оставаться в Blocked."))

        is_epic = (issue.get("issueType") or {}).get("name") == "Epic" or (
            (issue.get("subIssues") or {}).get("totalCount", 0) > 0
        )
        required = {
            "Priority": fields.get("Priority") in allowed_priority,
        }
        if schema == "legacy":
            required["Effort"] = is_epic or fields.get("Effort") in ALLOWED_EFFORT
            required["area:*"] = any(
                str(x.get("name", "")).startswith("area:")
                for x in (issue.get("labels") or {}).get("nodes") or []
            )
        else:
            required["Area"] = fields.get("Area") in ALLOWED_AREA
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
        "--issue",
        "--item",
        dest="issue",
        type=int,
        help="Номер Issue или PR для проверки после создания/изменения.",
    )
    parser.add_argument(
        "--strict", action="store_true", help="Считать пропуски полей ошибкой, включая Backlog."
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--schema", choices=("delivery", "legacy"), default="delivery")
    args = parser.parse_args()
    if args.issue is not None and args.issue < 1:
        parser.error("--issue должен быть положительным номером.")

    try:
        items = load_project_items()
        opened = None if args.issue is not None else load_open_repository_items()
        if opened is not None and args.schema == "legacy":
            opened = {n: kind for n, kind in opened.items() if kind == "Issue"}
        findings, inspected = inspect_items(
            items, number=args.issue, strict=args.strict, open_items=opened, schema=args.schema
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    report = {
        "schema": args.schema,
        "project_id": PROJECT_ID,
        "live_items_read": len(items),
        "open_repository_issues": None
        if opened is None
        else sum(kind == "Issue" for kind in opened.values()),
        "open_repository_prs": None
        if opened is None
        else sum(kind == "PullRequest" for kind in opened.values()),
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
