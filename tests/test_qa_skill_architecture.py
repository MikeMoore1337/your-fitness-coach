from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]

QA_SKILLS = {
    "playwright-testing",
    "e2e-review",
    "pytest-test-design",
    "api-testing",
    "database-validation",
    "test-data-management",
    "pydantic-contracts",
    "allure-reporting",
    "failure-triage",
    "flaky-analysis",
    "coverage-analysis",
}

QA_PROFILES = {
    "qa-architect",
    "test-implementer",
    "test-reviewer",
    "ci-investigator",
    "flaky-analyst",
    "coverage-analyst",
}


def test_specialized_qa_skills_are_manifested_and_present() -> None:
    manifest = json.loads((ROOT / ".agents/MANIFEST.json").read_text(encoding="utf-8"))
    assert set(manifest["skills"]) >= QA_SKILLS
    assert manifest["skill_count"] == len(manifest["skills"])
    for skill in QA_SKILLS:
        assert (ROOT / ".agents" / "skills" / skill / "SKILL.md").is_file()


def test_qa_profiles_do_not_duplicate_lifecycle_roles() -> None:
    manifest = json.loads((ROOT / ".agents/MANIFEST.json").read_text(encoding="utf-8"))
    roles = set(manifest["roles"])
    assert QA_PROFILES.isdisjoint(roles)
    assert {"implementer", "qa-verifier", "integration-release"} <= roles


def test_qa_router_and_routing_guide_reference_specialists() -> None:
    qa = (ROOT / ".agents/skills/qa-engineer/SKILL.md").read_text(encoding="utf-8")
    routing = (ROOT / ".agents/references/SKILL_ROUTING_GUIDE.md").read_text(encoding="utf-8")
    architecture = (ROOT / ".agents/references/QA_AUTOMATION_ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )

    for skill in QA_SKILLS:
        assert "$" + skill in qa or skill in qa
        assert "$" + skill in routing or skill in routing

    for profile in QA_PROFILES:
        assert profile in architecture


def test_ui_audit_remains_separate_from_playwright_testing() -> None:
    playwright = (ROOT / ".agents/skills/playwright-testing/SKILL.md").read_text(encoding="utf-8")
    e2e_review = (ROOT / ".agents/skills/e2e-review/SKILL.md").read_text(encoding="utf-8")
    assert "$ui-audit" in e2e_review
    assert "UI aesthetics" in e2e_review
    assert "visual" in playwright.lower()
