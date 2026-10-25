"""Offline structural tests for context-safe stop-slop adaptation (#1143).

Synthetic fixtures do not prove model-output quality, medical claims or a live release.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAR_VOICE = ROOT / ".agents/skills/clear-voice"
SCRIPT = CLEAR_VOICE / "evals/validate_package.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("clear_voice_validation_1143", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_package_and_synthetic_context_cases_validate_offline():
    errors, cases = load_validator().validate_package()
    assert not errors, errors
    assert len(cases) >= 71
    by_id = {case["id"]: case for case in cases}
    for case_id, (profile, mode) in load_validator().STOP_SLOP_PROFILE_MODES.items():
        assert by_id[case_id]["profile"] == profile
        assert by_id[case_id]["mode"] == mode
        if mode == "unchanged":
            assert by_id[case_id]["must_avoid"] == []


def test_adapted_skill_keeps_runtime_and_publication_boundaries():
    skill = (CLEAR_VOICE / "SKILL.md").read_text(encoding="utf-8")
    source = (CLEAR_VOICE / "SOURCES.md").read_text(encoding="utf-8")
    patterns = (CLEAR_VOICE / "references/patterns.md").read_text(encoding="utf-8")
    adapter = (CLEAR_VOICE / "adapters/hermes/EDITORIAL_STYLE_PROMPT.txt").read_text(
        encoding="utf-8"
    )
    assert "hardikpandya/stop-slop" in source
    assert "8da1f030185bdfe8471220585162991eaeb970e9" in source
    assert "D01" in patterns and "D08" in patterns
    assert "не публикует" in skill or "не публикует" in patterns
    assert "1.0.0" in adapter
