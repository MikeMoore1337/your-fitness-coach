"""Import only pinned, browser-verified MP4 derivatives for two #986 matches.

No network calls. Fails closed if any source bytes or catalog association drift.
License and derivative hosting rights were explicitly confirmed by project owner.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "backend/assets/exercise-guides"
MANIFEST = ASSET_ROOT / "manifest.json"
REPORT = ROOT / "docs/exercises/catalog-v2/986_TRANSCODE_BENCH.csv"
DEFAULT_INPUT = ROOT / ".artifacts/tasks/986/pilot/transcoded"
VIDEOS = ASSET_ROOT / "exercises-media/videos"
SOURCE_REVISION = "18742da40b0627c85925c5dd4441dc3eac0594d0"
CANDIDATES = ("barbell-curl", "burpee")
PROFILES = {
    "480p_24fps_h264_crf29": (480, 854, 480, 29),
    "720p_24fps_h264_crf28": (720, 1280, 720, 28),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(input_dir: Path) -> dict[str, list[tuple[dict, bytes]]]:
    with REPORT.open(encoding="utf-8-sig", newline="") as file:
        records = list(csv.DictReader(file))
    result: dict[str, list[tuple[dict, bytes]]] = {slug: [] for slug in CANDIDATES}
    for slug in CANDIDATES:
        for variant, (quality, width, height, crf) in PROFILES.items():
            matches = [
                row
                for row in records
                if row["slug"] == slug and row["gender"] == "male" and row["variant"] == variant
            ]
            if len(matches) != 1:
                raise ValueError("Pinned media profile missing or ambiguous")
            row = matches[0]
            basename = f"male-{slug}-{quality}p-crf{crf}.mp4"
            source = input_dir / basename
            if not source.is_file() or not source.resolve().is_relative_to(input_dir.resolve()):
                raise FileNotFoundError("Pinned local transcoded file missing")
            data = source.read_bytes()
            if len(data) != int(row["output_bytes"]) or digest(data) != row["output_sha256"]:
                raise ValueError("Pinned media checksum/length mismatch")
            output_name = f"{slug}-{quality}p-h264.mp4"
            metadata = {
                "path": f"exercises-media/videos/{output_name}",
                "mime_type": "video/mp4",
                "width": width,
                "height": height,
                "byte_size": len(data),
                "sha256": digest(data),
            }
            result[slug].append((metadata, data))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    videos = prepare(args.input_dir)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 3 or manifest.get("counts", {}).get("blocked") != 39:
        raise ValueError("Unexpected production manifest")
    for slug, profiles in videos.items():
        entry = manifest["exercises"].get(slug)
        if not entry or entry.get("status") != "approved" or len(entry.get("media", [])) != 1:
            raise ValueError("Only approved single-GIF exercise allowed")
        media = entry["media"][0]
        if media["type"] != "animation" or not media["path"].endswith(".gif"):
            raise ValueError("Legacy GIF fallback not preserved")
        if media.get("video_sources"):
            raise ValueError("Media already has video variants")
        media["video_sources"] = [profile for profile, _ in profiles]
        media["video_provenance"] = {
            "source_name": "Exercises Media",
            "source_revision": SOURCE_REVISION,
            "source_path": f"public/videos/male/{slug}.mp4",
            "rights_basis": "owner_confirmed_unrestricted_use_2026-10-16",
            "transformation": "ffmpeg-7.1-h264-24fps-crf29-480-crf28-720",
        }
    manifest["hq_video_count"] = len(CANDIDATES)
    manifest["hq_video_total_bytes"] = sum(
        len(data) for profiles in videos.values() for _, data in profiles
    )
    if args.apply:
        VIDEOS.mkdir(parents=True, exist_ok=True)
        for profiles in videos.values():
            for profile, data in profiles:
                target = ASSET_ROOT / profile["path"]
                if target.exists():
                    raise FileExistsError("Video import must never overwrite an existing asset")
                target.write_bytes(data)
        MANIFEST.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(
        f"VERIFIED_H264_PILOT={len(videos)} PROFILES={sum(map(len, videos.values()))} APPLY={args.apply}"
    )


if __name__ == "__main__":
    main()
