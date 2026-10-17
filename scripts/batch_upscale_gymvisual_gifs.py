"""Render remaining licensed GymVisual GIFs with the owner-approved Real-ESRGAN model.

Requires the official portable ncnn Vulkan engine and a working Vulkan GPU.
Produces only AI 720p H.264 MP4s and a checksummed processing report in an
untracked output directory. Does not change app assets or production manifest.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from PIL import Image

from scripts.import_ai_upscaled_exercise_gifs import MANIFEST_PATH, pending_exercises, sha256
from scripts.pilot_upscale_gymvisual_gifs import ai_frames, ffconcat_video, load_gif

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".artifacts/runtime/986-ai-batch"


def render_one(slug: str, *, engine: Path, output_dir: Path) -> dict:
    source, frames, durations, loop = load_gif(slug)
    with tempfile.TemporaryDirectory(prefix=f"986-ai-{slug}-") as temporary:
        temp = Path(temporary)
        improved = ai_frames(engine, frames, temp, "realesrgan-x4plus")
        png_files = []
        for index, frame in enumerate(improved):
            if frame.size != (720, 720):
                raise ValueError(f"Incorrect AI resolution: {slug}")
            image_path = temp / f"frame-{index:04d}.png"
            frame.convert("RGB").save(image_path)
            png_files.append(image_path)
        output = output_dir / f"{slug}-general-720.mp4"
        ffconcat_video(png_files, durations, output)
    data = output.read_bytes()
    return {
        "slug": slug,
        "input": source.relative_to(ROOT).as_posix(),
        "source_sha256": sha256(source.read_bytes()),
        "frames": len(frames),
        "duration_ms": sum(durations),
        "loop": loop,
        "ai_mp4_bytes": len(data),
        "ai_mp4_sha256": sha256(data),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--slugs", nargs="+")
    parser.add_argument(
        "--all-pending",
        action="store_true",
        help="Render all approved 180x180 source animations still lacking HD/AI video",
    )
    args = parser.parse_args()
    pending = pending_exercises(
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    )
    if args.all_pending == bool(args.slugs):
        parser.error("Choose exactly one of --all-pending or --slugs")
    slugs = sorted(pending) if args.all_pending else args.slugs
    if len(set(slugs)) != len(slugs) or any(slug not in pending for slug in slugs):
        parser.error("All requested slugs must be unique, approved and still GIF-only")
    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / "results-general.json"
    existing = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    if existing and (
        existing.get("method") != "realesrgan-x4plus ncnn Vulkan (x4)"
        or existing.get("source_resolution") != [180, 180]
        or existing.get("ai_resolution") != [720, 720]
    ):
        raise ValueError("Existing batch report uses an incompatible model")
    report = existing or {
        "method": "realesrgan-x4plus ncnn Vulkan (x4)",
        "source_resolution": [180, 180],
        "ai_resolution": [720, 720],
        "format": ["MP4 (H264)"],
        "samples": [],
    }
    completed = {item["slug"]: item for item in report["samples"]}
    if len(completed) != len(report["samples"]):
        raise ValueError("Duplicate slugs in existing batch report")
    for index, slug in enumerate(slugs, start=1):
        target = args.output / f"{slug}-general-720.mp4"
        if slug in completed:
            sample = completed[slug]
            source = ROOT / sample["input"]
            if (
                not target.is_file()
                or sha256(target.read_bytes()) != sample["ai_mp4_sha256"]
                or sha256(source.read_bytes()) != pending[slug]["asset_sha256"]
            ):
                raise ValueError(f"Invalid resumable output: {slug}")
            print(f"[{index}/{len(slugs)}] Reused verified {slug}", flush=True)
            continue
        if target.exists():
            raise ValueError(f"Orphan output, refusing overwrite: {slug}")
        sample = render_one(slug, engine=args.engine, output_dir=args.output)
        completed[slug] = sample
        report["samples"] = [completed[key] for key in sorted(completed)]
        temporary_report = report_path.with_suffix(".json.tmp")
        temporary_report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_report.replace(report_path)
        print(f"[{index}/{len(slugs)}] Rendered {slug} ({sample['ai_mp4_bytes']} B)", flush=True)
    print(f"Ready: {len(slugs)} requested animations; report: {report_path}")


if __name__ == "__main__":
    main()
