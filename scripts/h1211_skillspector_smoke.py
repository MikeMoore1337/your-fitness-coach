"""Real pinned SkillSpector compatibility probe on disposable RU/EN skills.

Runs in explicit GitHub Actions compatibility workflow, never product runtime.
No API keys, no source installers and no user-provided private data.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from scripts import skillspector_guard as guard


def main() -> int:
    uvx = shutil.which("uvx")
    if uvx is None:
        raise RuntimeError("uvx absent: cannot claim compatibility")
    with tempfile.TemporaryDirectory(prefix="yfc-h1211-") as temp:
        root = Path(temp)
        results: list[dict[str, object]] = []
        cases = (
            ("en", "Read public documentation and explain the API without modifying files."),
            ("ru", "Прочитай открытую документацию API и объясни её без изменения файлов."),
        )
        for lang, body in cases:
            skill = root / f"synthetic-{lang}"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\n"
                f"name: yfc-h1211-{lang}\n"
                "description: Synthetic and harmless compatibility probe\n"
                "---\n\n"
                f"# Synthetic {lang}\n{body}\n",
                encoding="utf-8",
            )
            # The scanner must create a fresh JSON report and prove no paid LLM calls.
            outcome = guard.scan_skill(
                skill,
                output_root=root / "reports",
                uvx=uvx,
                env=os.environ,
            )
            raw = json.loads(outcome.report_path.read_text(encoding="utf-8"))
            metadata = raw.get("metadata", {})
            if metadata.get("llm_requested") not in (None, False):
                raise RuntimeError("unexpected LLM requested")
            if metadata.get("llm_calls_attempted", 0) != 0:
                raise RuntimeError("unexpected LLM call")
            if outcome.recommendation not in ("SAFE", "CAUTION"):
                raise RuntimeError("unexpected unapproved result")
            results.append({
                "language": lang,
                "recommendation": outcome.recommendation,
                "severity": outcome.severity,
                "static_only": True,
                "scanned_directory": True,
            })
        print(json.dumps({
            "schema": "yfc-h1211-compatibility-v1",
            "source_pin": guard.SKILLSPECTOR_COMMIT,
            "platform": os.name,
            "results": results,
            "paid_api_calls": 0,
            "product_runtime_modified": False,
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
