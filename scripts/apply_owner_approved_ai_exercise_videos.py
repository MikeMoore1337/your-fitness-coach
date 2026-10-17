"""Apply four owner-reviewed RealESRGAN-x4plus GIF animations without touching legacy media.

Requires the immutable #1073 evidence files, not an AI service or remote CDN.
Only the four reviewed canonical exercise IDs are permitted. Running --apply is
idempotent and validates all input/output hashes and manifest identities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "backend/assets/exercise-guides"
MANIFEST = MEDIA / "manifest.json"
EVIDENCE = ROOT / "docs/exercises/catalog-v2/evidence/986-gif-upscale-pilot"
SAMPLES = {
    "deadlift": ("afd8eedcefe2075cbf1bafb146876c9d04bfceb12bcb17038ed998446cd938bb", 111130),
    "machine-chest-press": (
        "3b7f1a72870c55858996da96736c1271dd8ff2bf7140716770dde5d321125614",
        147140,
    ),
    "russian-twist": ("a1fa19b9906701d2eea055dcc539e6f9ae24341e5ce37293b1f2ddbf1bd29c73", 196448),
    "walking-lunge": ("a74a9a92deac7134ff1ef68ad80b658b32321163924b642bdf4994e2364cc0f0", 160255),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(evidence: Path, *, write: bool) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    total_new_bytes = 0
    total_new_files = 0
    approved_bytes = 0
    for slug, (expected_sha, expected_size) in SAMPLES.items():
        entry = manifest["exercises"][slug]
        if entry["status"] != "approved" or len(entry["media"]) != 1:
            raise ValueError(f"Unapproved canonical item: {slug}")
        media = entry["media"][0]
        original = MEDIA / media["path"]
        if media["type"] != "animation" or original.suffix.lower() != ".gif":
            raise ValueError(f"Missing authentic original GIF: {slug}")
        if sha256(original) != media["asset_sha256"]:
            raise ValueError(f"Original GIF checksum mismatch: {slug}")
        if media.get("poster_source"):
            raise ValueError(f"Native HD poster already mapped: {slug}")
        source = evidence / f"{slug}-general-720.mp4"
        if (
            not source.is_file()
            or source.stat().st_size != expected_size
            or sha256(source) != expected_sha
        ):
            raise ValueError(f"Owner-reviewed AI pilot binary missing or tampered: {slug}")
        if source.read_bytes()[4:8] != b"ftyp":
            raise ValueError(f"Invalid MP4 binary: {slug}")
        relpath = f"gymvisual/ai-reviewed/{slug}-x4plus-720.mp4"
        dest = MEDIA / relpath
        already = bool(media.get("video_sources"))
        if (
            already
            and media.get("video_provenance", {}).get("source_kind") != "ai_upscaled_gymvisual"
        ):
            raise ValueError(f"Refusing to replace an actual HD video: {slug}")
        if dest.exists() and sha256(dest) != expected_sha:
            raise ValueError(f"Existing derivative differs: {slug}")
        if not already:
            total_new_files += 1
            total_new_bytes += expected_size
        approved_bytes += expected_size
        media["video_sources"] = [
            {
                "path": relpath,
                "mime_type": "video/mp4",
                "width": 720,
                "height": 720,
                "byte_size": expected_size,
                "sha256": expected_sha,
            }
        ]
        media["video_provenance"] = {
            "source_kind": "ai_upscaled_gymvisual",
            "source_name": "GymVisual",
            "source_path": media["path"],
            "source_sha256": media["asset_sha256"],
            "source_asset_id": media["asset_id"],
            "source_dimensions": {"width": 180, "height": 180},
            "source_animation_frames": media["frame_count"],
            "source_animation_duration_ms": media["duration_ms"],
            "model": "RealESRGAN_x4plus",
            "scale": 4,
            "native_hd": False,
            "owner_visual_approval": "2026-10-17 #1073 four-sample review",
            "transformation": "RealESRGAN-x4plus-720x720-H264-MP4-preserve-source-motion",
            "rights_basis": "owner-confirmed-GymVisual-commercial-and-derived-use",
        }
        if write:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
    if not write:
        print(
            f"Validated {len(SAMPLES)} owner-reviewed AI videos ({approved_bytes} bytes); dry run"
        )
        return
    manifest["ai_upscaled_video_count"] = len(SAMPLES)
    manifest["ai_upscaled_video_total_bytes"] = approved_bytes
    manifest["asset_count"] += total_new_files
    manifest["total_bytes"] += total_new_bytes
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Applied {len(SAMPLES)} approved AI videos, {total_new_files} new assets ({total_new_bytes} bytes)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    apply(args.evidence, write=args.apply)


if __name__ == "__main__":
    main()
