"""Fetch and verify the immutable RapidOCR model bundle during image build."""

from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

MODEL_RELEASE = "v3.9.2"
MODEL_MAX_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class ModelSpec:
    filename: str
    url: str
    sha256: str


MODEL_SPECS = (
    ModelSpec(
        filename="ch_PP-OCRv5_det_mobile.onnx",
        url=(
            "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/"
            f"{MODEL_RELEASE}/onnx/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx"
        ),
        sha256="4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae",
    ),
    ModelSpec(
        filename="cyrillic_PP-OCRv5_rec_mobile.onnx",
        url=(
            "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/"
            f"{MODEL_RELEASE}/onnx/PP-OCRv5/rec/cyrillic_PP-OCRv5_rec_mobile.onnx"
        ),
        sha256="90f761b4bfcce0c8c561c0cb5c887b0971d3ec01c32164bdf7374a35b0982711",
    ),
    ModelSpec(
        filename="ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx",
        url=(
            "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/"
            f"{MODEL_RELEASE}/onnx/PP-OCRv5/cls/"
            "ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx"
        ),
        sha256="54379ae5174d026780215fc748a7f31910dee36818e63d49e17dc598ecc82df7",
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(spec: ModelSpec, output_dir: Path) -> None:
    target = output_dir / spec.filename
    if target.is_file() and _sha256(target) == spec.sha256:
        print(f"verified {spec.filename}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_dir,
            prefix=f".{spec.filename}.",
            suffix=".download",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            request = Request(spec.url, headers={"User-Agent": "yfc-build/128G"})
            with urlopen(request, timeout=120) as response:
                content_length = response.headers.get("Content-Length")
                if content_length is not None and int(content_length) > MODEL_MAX_BYTES:
                    raise RuntimeError(f"model exceeds size budget: {spec.filename}")
                total = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MODEL_MAX_BYTES:
                        raise RuntimeError(f"model exceeds size budget: {spec.filename}")
                    digest.update(chunk)
                    temporary.write(chunk)
            if digest.hexdigest() != spec.sha256:
                raise RuntimeError(f"SHA-256 mismatch: {spec.filename}")
        os.replace(temporary_path, target)
        temporary_path = None
        print(f"downloaded and verified {spec.filename}")
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output_dir = args.output.resolve()
    for spec in MODEL_SPECS:
        _download(spec, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
