"""#1211 isolated *real* pinned SkillSpector CLI smoke on Linux and Windows.

Requires 'uvx' but no model/API credentials, host data or external skill installs.
It is intentionally separate from policy CI's mocked negative-contract suite.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from scripts import skillspector_guard as guard

FIXTURES = {
    "english": (
        "safe-evidence-en",
        "Generate a textual summary of a synthetic repository without editing files.",
        "Read the synthetic fixture and summarize the known statements. "
        "Do not run commands, fetch secrets, write files, or access a network.",
    ),
    "russian": (
        "safe-evidence-ru",
        "Опиши синтетическую структуру репозитория без изменений файлов.",
        "Прочитай синтетический пример и кратко опиши факты. "
        "Не запускай команды и не отправляй данные по сети.",
    ),
}


def create_fixture(root: Path, slug: str, name: str, description: str, body: str) -> Path:
    directory = root / slug
    directory.mkdir()
    # Descriptions are synthetic, not third-party skills. No external source metadata.
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n"
        f"# {name}\n\n{body}\n",
        encoding="utf-8",
    )
    return directory


def main() -> int:
    uvx = shutil.which("uvx")
    if not uvx:
        raise RuntimeError("REAL_SKILLSPECTOR_NOT_RUN: uvx is unavailable")
    # Safe-mode invocation cannot inherit an actual bearer key from the job.
    env = {name: value for name, value in os.environ.items() if "TOKEN" not in name.upper()}
    env["YFC_SYNTHETIC_API_KEY"] = "synthetic-fake-value"
    assert "YFC_SYNTHETIC_API_KEY" not in guard._safe_env(env)
    with tempfile.TemporaryDirectory(prefix="yfc1211-real-") as dirname:
        root = Path(dirname)
        for slug, (name, description, body) in FIXTURES.items():
            candidate = create_fixture(root, slug, name, description, body)
            verdict = guard.scan_skill(
                candidate,
                output_root=root / "reports",
                uvx=uvx,
                env=env,
            )
            report = json.loads(verdict.report_path.read_text(encoding="utf-8"))
            if not report.get("analysis_completeness", {}).get("is_complete"):
                raise AssertionError("REAL_SKILLSPECTOR_INCOMPLETE")
            if report.get("metadata", {}).get("llm_calls_attempted", 1) != 0:
                raise AssertionError("REAL_SKILLSPECTOR_LLM_USED")
            if report.get("metadata", {}).get("llm_requested") is True:
                raise AssertionError("REAL_SKILLSPECTOR_LLM_REQUESTED")
            if verdict.recommendation not in {"SAFE", "CAUTION"}:
                raise AssertionError("REAL_SKILLSPECTOR_UNSAFE_VERDICT")
            print(f"REAL_SKILLSPECTOR_{slug.upper()}=PASS recommendation={verdict.recommendation}")
    print(f"YFC1211_REAL_OS_SCAN=PASS platform={sys.platform} commit={guard.SKILLSPECTOR_COMMIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
