"""Run one explicitly registered adapter with operating-system resource limits."""

from __future__ import annotations

import codecs
import importlib
import importlib.util
import json
import sys
from pathlib import Path

MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_ADDRESS_SPACE = 384 * 1024 * 1024


def main() -> None:
    if sys.platform != "linux":
        raise RuntimeError("adapter execution is unavailable")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    resource = importlib.import_module("resource")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_AS, (MAX_ADDRESS_SPACE, MAX_ADDRESS_SPACE))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    spec = importlib.util.spec_from_file_location("nutrition_import_adapter", sys.argv[1])
    if spec is None or spec.loader is None:
        raise ValueError("adapter unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if len(sys.argv) > 2 and sys.argv[2] == "pdf":
        import _strptime  # noqa: F401

        from fitminiapp_api.services.nutrition_import_pdf_sandbox import install_pdf_sandbox

        codecs.lookup("UTF-16BE")
        install_pdf_sandbox()
    result = module.parse(sys.stdin.buffer.read(512 * 1024 + 1))
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode())


if __name__ == "__main__":
    main()
