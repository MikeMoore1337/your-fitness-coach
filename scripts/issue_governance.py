"""Read-only проверки заголовков и аудит Issues (без изменения GitHub)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

TITLE_PREFIX = re.compile(
    r"^\[(?:Product V[1-9]\d*|Bug|UI Backlog|Improvement|Engineering|Operations|Growth)\]\s+"
)
VERSION_PREFIX = re.compile(r"(?:^|\[)(?:Product\s+v?|V)(1[123])\b", re.IGNORECASE)
VERSION_CODE = re.compile(r"^V(11|12|13)-\d+\b", re.IGNORECASE)
LABEL_OPTIONS = frozenset(
    {
        "area:workout",
        "area:programs",
        "area:nutrition",
        "area:progress",
        "area:coach-os",
        "area:profile",
        "area:landing",
        "area:telegram",
        "area:demo",
        "area:backend",
        "area:database",
        "area:infrastructure",
        "gate:visual-approval",
        "gate:legal-review",
        "gate:security-review",
        "gate:owner-decision",
        "spike",
        "regression",
    }
)


def title_errors(title: str) -> list[str]:
    """Проверка формы, не значения и приоритета задачи."""
    if not isinstance(title, str) or not title.strip():
        return ["Заголовок не задан."]
    match = TITLE_PREFIX.match(title)
    if match is None:
        return ["Нужен ровно один утверждённый префикс в начале названия."]
    description = title[match.end() :].strip()
    if description.startswith("["):
        return ["Не объединяйте несколько префиксов."]
    if len(description) < 5:
        return ["Название после префикса слишком короткое."]
    return []


def suggested_prefix(title: str) -> str | None:
    """Подсказка для версии, без автоматического назначения Bug или UI."""
    match = TITLE_PREFIX.match(title)
    if match:
        return match.group(0).strip()
    version = VERSION_PREFIX.search(title) or VERSION_CODE.search(title)
    if version:
        return f"[Product V{version.group(1)}]"
    if re.search(r"\b(?:SEO|organic growth|конверсии|индексаци)\b", title, re.IGNORECASE):
        return "[Growth]"
    return None


def audit_items(payload: list[dict[str, Any]]) -> str:
    """Читаемый предварительный снимок, игнорирующий записи Pull Request."""
    issues = [
        item
        for item in payload
        if isinstance(item, dict)
        and "number" in item
        and "title" in item
        and "pull_request" not in item
    ]
    lines = [
        "# Read-only Issue governance audit",
        "",
        f"Количество Issues: {len(issues)}. Существующие данные не изменены.",
        "Подсказка не является разрешением на переименование.",
        "Priority, Effort, Status и зависимости требуют отдельной проверки.",
        "",
        "| Issue | Название | Подсказка | Проверка |",
        "|---|---|---|---|",
    ]
    for item in sorted(issues, key=lambda row: int(row["number"])):
        title = str(item["title"]).replace("|", r"\|").replace("\n", " ")
        url = f"https://github.com/MikeMoore1337/your-fitness-coach/issues/{item['number']}"
        suggestion = suggested_prefix(str(item["title"])) or "Решение владельца"
        state = "OK" if not title_errors(str(item["title"])) else "Нужна миграция"
        lines.append(f"| [#{item['number']}]({url}) | {title} | {suggestion} | {state} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Проверить одну Issue или сформировать read-only inventory из JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--input", required=True, type=Path)
    check.add_argument("--strict", action="store_true")
    inventory = subparsers.add_parser("inventory")
    inventory.add_argument("--input", required=True, type=Path)
    inventory.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))

    if args.command == "check":
        if not isinstance(payload, dict) or not isinstance(payload.get("title"), str):
            print("::warning::Не найден заголовок GitHub Issue.")
            return int(args.strict)
        errors = title_errors(payload["title"])
        for error in errors:
            # Никогда не выводить сырые пользовательские заголовки в Actions annotations.
            print(f"::warning::Issue governance: {error}")
        if not errors:
            print("Issue title prefix: OK.")
        return int(bool(errors) and args.strict)

    if not isinstance(payload, list):
        parser.error("Для inventory нужен JSON-массив.")
    report = audit_items(payload)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
