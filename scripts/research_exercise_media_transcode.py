"""Offline, SHA-gated #986 research; never publishes third-party media.

Run from repository root:
  uv run --no-project --with imageio-ffmpeg python scripts/research_exercise_media_transcode.py
The pinned input assets must already be present locally in the ignored pilot/raw folder.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import subprocess
import time
from pathlib import Path

DEFAULT_SELECTION = (
    "male:barbell-curl",
    "female:barbell-curl",
    "male:burpee",
    "female:stationary-bike",
)
VARIANTS = ((480, 854, 29), (720, 1280, 28))
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = ROOT / ".artifacts/tasks/986/pilot/raw"
DEFAULT_ENCODED = ROOT / ".artifacts/tasks/986/pilot/transcoded"
DEFAULT_MANIFEST = ROOT / "docs/exercises/catalog-v2/986_PILOT_RESULTS.csv"
DEFAULT_REPORT = DEFAULT_ENCODED / "reproduced-transcode-bench.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=True)


def safe_source(raw: Path, candidate: str) -> Path:
    """Prevent an inventory path from reaching outside the ignored input directory."""
    if not candidate.startswith("public/videos/"):
        raise ValueError(f"Unexpected inventory source path: {candidate}")
    path = (raw / candidate.removeprefix("public/")).resolve()
    if not path.is_relative_to(raw.resolve()) or path.suffix.lower() != ".mp4":
        raise ValueError(f"Unsafe media input: {candidate}")
    return path


def run_pilot(
    manifest: Path, raw: Path, encoded: Path, report: Path, ffmpeg: str, selection: tuple[str, ...]
) -> list[dict[str, object]]:
    inventory = list(csv.DictReader(manifest.open(encoding="utf-8-sig", newline="")))
    selected = {tuple(item.split(":", 1)) for item in selection}
    if len(selected) != len(selection) or any(len(item) != 2 for item in selected):
        raise ValueError("Duplicate or invalid gender:slug selection")
    actual = {(item["gender"], item["slug"]) for item in inventory}
    if not selected.issubset(actual):
        raise ValueError(f"Selection not present in pinned manifest: {selected - actual}")
    encoder_list = run([ffmpeg, "-hide_banner", "-encoders"]).stdout
    if "libx264" not in encoder_list:
        raise RuntimeError("Required H.264 libx264 encoder not available")

    encoded.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    for item in inventory:
        pair = (item["gender"], item["slug"])
        if pair not in selected:
            continue
        source = safe_source(raw, item["candidate_video_path"])
        if not source.is_file():
            raise FileNotFoundError(f"Pinned input missing (do not download implicitly): {source}")
        digest = sha256(source)
        if digest != item["candidate_video_sha256"]:
            raise ValueError(f"Input SHA-256 mismatch: {pair}, got {digest}")
        for height, width, crf in VARIANTS:
            output = encoded / f"{pair[0]}-{pair[1]}-{height}p-crf{crf}.mp4"
            size = f"{width}:{height}"
            start = time.monotonic()
            run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-nostdin",
                    "-y",
                    "-i",
                    str(source),
                    "-an",
                    "-vf",
                    f"fps=24,scale={size}:flags=lanczos,format=yuv420p",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    str(crf),
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-threads",
                    "2",
                    str(output),
                ]
            )
            seconds = round(time.monotonic() - start, 2)
            filters = (
                f"[0:v]fps=24,scale={size}:flags=lanczos,format=yuv420p[ref];"
                f"[1:v]fps=24,scale={size}:flags=lanczos,format=yuv420p[encoded];"
                "[ref][encoded]ssim"
            )
            comparison = run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-nostdin",
                    "-i",
                    str(source),
                    "-i",
                    str(output),
                    "-filter_complex",
                    filters,
                    "-an",
                    "-f",
                    "null",
                    "-",
                ]
            )
            values = re.findall(r"All:([0-9.]+)", comparison.stderr)
            ssim: float | str = round(float(values[-1]), 6) if values else "NOT_MEASURED"
            record: dict[str, object] = {
                "gender": pair[0],
                "slug": pair[1],
                "source_sha256": digest,
                "source_bytes": source.stat().st_size,
                "candidate_gif_bytes": item["current_gif_bytes"],
                "variant": f"{height}p_24fps_h264_crf{crf}",
                "output_bytes": output.stat().st_size,
                "bytes_ratio_vs_raw": round(output.stat().st_size / source.stat().st_size, 4),
                "bytes_ratio_vs_gif": round(
                    output.stat().st_size / int(item["current_gif_bytes"]), 4
                ),
                "ssim_vs_normalized_source": ssim,
                "encoder_seconds": seconds,
                "output_sha256": sha256(output),
                "browser_playback": "NOT_VERIFIED",
                "rights_to_public_redistribute_derivatives": "NOT_DOCUMENTED",
            }
            results.append(record)
            print(
                f"MEASURED={pair[0]}:{pair[1]}:{height}p bytes={record['output_bytes']} ssim={ssim}"
            )
    if len(results) != 2 * len(selected):
        raise RuntimeError(f"Expected {2 * len(selected)} rows, got {len(results)}")
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(f"RESEARCH_ONLY=1 ROWS={len(results)} REPORT={report}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline, pinned SHA-verified YFC #986 media pilot"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--encoded-dir", type=Path, default=DEFAULT_ENCODED)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--selection", nargs="+", default=list(DEFAULT_SELECTION))
    parser.add_argument(
        "--ffmpeg", help="Path to a pinned FFmpeg executable (default: imageio-ffmpeg)"
    )
    options = parser.parse_args()
    if options.ffmpeg:
        ffmpeg = options.ffmpeg
    else:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    run_pilot(
        options.manifest,
        options.raw_root,
        options.encoded_dir,
        options.report,
        ffmpeg,
        tuple(options.selection),
    )


if __name__ == "__main__":
    main()
