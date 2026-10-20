"""Guard the read-only UX/UI orchestra routing contract from accidental deletion."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_orchestra_skill_registered_and_read_only():
    manifest = json.loads((ROOT / ".agents/MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["skill_count"] == len(manifest["skills"])
    assert "ux-ui-design-orchestra" in manifest["skills"]
    skill = (ROOT / ".agents/skills/ux-ui-design-orchestra/SKILL.md").read_text(encoding="utf-8")
    assert "name: ux-ui-design-orchestra" in skill
    assert "READ_ONLY" in skill
    assert "SEQUENTIAL" in skill
    assert "Принимаю" in skill
    assert (
        "до моего"
        in (ROOT / "docs/development/ux-ui-design-orchestra.md").read_text(encoding="utf-8").lower()
    )
