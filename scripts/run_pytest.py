"""Run pytest while keeping its generated files under .artifacts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run(
    root: Path,
    *,
    pytest_cache: Path,
    pytest_tmp: Path,
    process_tmp: Path,
) -> int:
    pytest_cache.parent.mkdir(parents=True, exist_ok=True)
    pytest_tmp.parent.mkdir(parents=True, exist_ok=True)
    process_tmp.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMP": str(process_tmp),
        "TEMP": str(process_tmp),
        "TMPDIR": str(process_tmp),
    }
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *sys.argv[1:],
        "-o",
        f"cache_dir={pytest_cache}",
        f"--basetemp={pytest_tmp}",
    ]
    allure_results_dir = os.environ.get("ALLURE_RESULTS_DIR")
    if allure_results_dir:
        result_path = Path(allure_results_dir).resolve()
        if not result_path.is_relative_to((root / ".artifacts").resolve()):
            raise ValueError("ALLURE_RESULTS_DIR must stay under .artifacts")
        cmd.extend(["--alluredir", str(result_path)])
    return subprocess.call(cmd, cwd=root, env=env)


def main() -> int:
    root = Path(__file__).resolve().parent.parent

    artifacts = root / ".artifacts"
    runtime = artifacts / "runtime"
    # Keep every generated path below the repository artifact contract. On
    # Windows a per-run tree still avoids stale ACLs and file-vs-directory
    # collisions, but its parent is now the classified runtime/tmp area.
    if os.name == "nt":
        import tempfile

        temporary_parent = runtime / "tmp"
        temporary_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="fitminiapp-pytest-", dir=temporary_parent
        ) as temp_dir:
            temp_root = Path(temp_dir)
            return _run(
                root,
                pytest_cache=temp_root / "cache",
                pytest_tmp=temp_root / "basetemp",
                process_tmp=temp_root / "python",
            )

    return _run(
        root,
        pytest_cache=runtime / "cache" / "pytest-runner",
        pytest_tmp=runtime / "tests" / "pytest-runner-tmp",
        process_tmp=runtime / "tmp" / "python",
    )


if __name__ == "__main__":
    raise SystemExit(main())
