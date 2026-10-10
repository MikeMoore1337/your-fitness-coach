"""Автономная проверка структуры Clear Voice и синтетических сценариев."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "SKILL.md"
EXPECTED_PROFILES = {"general", "yfc", "second-brain", "hermes"}
EXPECTED_MODES = {"draft", "edit", "audit", "unchanged", "targeted"}
REQUIRED_FILES = (
    "SKILL.md",
    "README.md",
    "INSTALL.md",
    "SOURCES.md",
    "THIRD_PARTY_NOTICES.md",
    "CHANGELOG.md",
    "LICENSE",
    "licenses/human-writing-LICENSE",
    "licenses/humanizer-LICENSE",
    "profiles/general.md",
    "profiles/yfc.md",
    "profiles/second-brain.md",
    "profiles/hermes.md",
    "references/fidelity.md",
    "references/russian-style.md",
    "references/english-style.md",
    "references/sensitive-text.md",
    "references/patterns.md",
    "adapters/hermes/EDITORIAL_STYLE_PROMPT.txt",
    "adapters/hermes/README.md",
    "examples/AGENTS.snippet.md",
    "evals/README.md",
    "evals/cases.json",
    "evals/SCORECARD.md",
)


def validate_package() -> tuple[list[str], list[dict[str, object]]]:
    """Проверяет только файловые инварианты, без сетевого доступа и записи."""
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"Отсутствует: {relative}")

    if not SKILL.exists():
        return errors, []
    text = SKILL.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        errors.append("Неверный frontmatter SKILL.md")
    else:
        header = text.split("\n---\n", 1)[0][4:]
        if not re.search(r"(?m)^name: clear-voice$", header):
            errors.append("Неверное имя скилла")
        if not re.search(r'(?m)^description: "(.+)"$', header):
            errors.append("Описание должно быть простой строкой в кавычках")
        else:
            description = re.search(r'(?m)^description: "(.+)"$', header).group(1)
            if not (1 <= len(description) <= 1024):
                errors.append("Описание за пределами Agent Skills (1-1024 символа)")
        if not re.search(r'(?m)^  version: "1\.0\.0"$', header):
            errors.append("Некорректная версия")
    if len(text.splitlines()) > 500:
        errors.append("SKILL.md слишком длинный")
    if ROOT.name != "clear-voice":
        errors.append("Имя директории должно совпадать с именем скилла")
    if len(list(ROOT.rglob("SKILL.md"))) != 1:
        errors.append("Должен быть один канонический SKILL.md")
    for relative in ("references/fidelity.md", "references/patterns.md", "profiles/hermes.md", "profiles/second-brain.md"):
        if relative not in text:
            errors.append(f"SKILL.md не содержит путь {relative}")
    adapter = ROOT / "adapters/hermes/EDITORIAL_STYLE_PROMPT.txt"
    if adapter.exists():
        prompt = adapter.read_text(encoding="utf-8")
        if len(prompt) > 2500:
            errors.append("Hermes adapter больше 2500 символов")
        for phrase in ("Russian", "source", "uncertainties", "schema", "safety", "untrusted"):
            if phrase not in prompt:
                errors.append(f"Hermes adapter не содержит {phrase}")
    try:
        cases = json.loads((ROOT / "evals/cases.json").read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        errors.append(f"Сценарии не прочитаны: {error}")
        return errors, []
    if not isinstance(cases, list) or len(cases) < 48:
        errors.append("Нужно минимум 48 кейсов")
        return errors, []
    names: set[str] = set()
    profiles: set[str] = set()
    for item in cases:
        if not isinstance(item, dict):
            errors.append("Кейс должен быть JSON object")
            continue
        case_id = item.get("id")
        profile = item.get("profile")
        mode = item.get("mode")
        source = item.get("input")
        if not isinstance(case_id, str) or not re.fullmatch(r"[a-z0-9-]+", case_id):
            errors.append(f"Некорректный id: {case_id}")
        elif case_id in names:
            errors.append(f"Повтор id: {case_id}")
        else:
            names.add(case_id)
        if profile not in EXPECTED_PROFILES:
            errors.append(f"Неизвестный профиль: {case_id}")
        else:
            profiles.add(profile)
        if mode not in EXPECTED_MODES or not isinstance(source, str) or len(source) < 12:
            errors.append(f"Некорректный режим/вход: {case_id}")
        for key in ("must_keep", "must_avoid"):
            fragments = item.get(key)
            if not isinstance(fragments, list) or any(not isinstance(s, str) or not s for s in fragments):
                errors.append(f"Некорректный {key}: {case_id}")
            elif key == "must_keep":
                for fragment in fragments:
                    if fragment not in source:
                        errors.append(f"'{fragment}' не встречается во входе: {case_id}")
    if profiles != EXPECTED_PROFILES:
        errors.append("Сценарии не покрывают все профили")
    return errors, cases


def check_outputs(cases: list[dict[str, object]], path: Path) -> list[str]:
    """Примитивная лексическая проверка; не заменяет семантический review."""
    errors: list[str] = []
    try:
        outputs = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"Результаты не прочитаны: {error}"]
    if not isinstance(outputs, dict):
        return ["Результаты должны быть объектом {id: output_text}"]
    cases_by_id = {str(case["id"]): case for case in cases}
    for case_id, result in outputs.items():
        if case_id not in cases_by_id:
            errors.append(f"Неизвестный кейс: {case_id}")
            continue
        case = cases_by_id[case_id]
        if not isinstance(result, str):
            errors.append(f"Результат не строка: {case_id}")
            continue
        if case["mode"] == "unchanged" and result != case["input"]:
            errors.append(f"Изменён хороший текст: {case_id}")
        for fragment in case["must_keep"]:
            if fragment not in result:
                errors.append(f"Возможно потерян фрагмент '{fragment}': {case_id}")
        for fragment in case["must_avoid"]:
            if fragment.lower() in result.lower():
                errors.append(f"Сохранился шаблон '{fragment}': {case_id}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", type=Path, help="Локальный JSON результатов модели")
    args = parser.parse_args()
    errors, cases = validate_package()
    if not errors and args.outputs:
        errors.extend(check_outputs(cases, args.outputs))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    print(f"PASS: Clear Voice 1.0.0, {len(cases)} синтетических сценариев, четыре профиля")
    if args.outputs:
        print("NOTE: лексические проверки не заменяют ручную оценку смысловой точности")


if __name__ == "__main__":
    main()
