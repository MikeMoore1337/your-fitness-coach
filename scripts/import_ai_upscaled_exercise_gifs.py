"""Import owner-approved Real-ESRGAN x4 MP4s, preserving canonical GIF fallbacks.

Generation is deliberately offline: use pilot_upscale_gymvisual_gifs.py with the
licensed GIFs and a locally installed official Real-ESRGAN engine. This importer
never downloads media, invents native HD, or authorizes an unverified mapping.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEDIA_ROOT = ROOT / "backend/assets/exercise-guides"
MANIFEST_PATH = MEDIA_ROOT / "manifest.json"
BULK_APPROVAL = "2026-10-18 #986 owner bulk approval; per-movement QA post-release"
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pending_exercises(manifest: dict) -> dict[str, dict]:
    """Only approved, original 180px GIFs without any existing video."""
    pending: dict[str, dict] = {}
    for slug, entry in manifest["exercises"].items():
        if entry.get("status") != "approved" or len(entry.get("media", [])) != 1:
            continue
        media = entry["media"][0]
        if media.get("type") != "animation" or media.get("video_sources"):
            continue
        if not SLUG_PATTERN.fullmatch(slug):
            raise ValueError(f"Invalid canonical slug: {slug}")
        if (media.get("width"), media.get("height")) != (180, 180):
            raise ValueError(f"Unexpected source dimensions: {slug}")
        if entry.get("source", {}).get("rights_basis") != "owner_purchased_gymvisual_license":
            raise ValueError(f"Unapproved source rights: {slug}")
        pending[slug] = media
    return dict(sorted(pending.items()))


def inspect_h264(video: Path, *, ffprobe: str, original_duration_ms: int) -> None:
    """Reject incorrect, static, long, audio-bearing or unsupported derivatives."""
    probe = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-count_frames",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,pix_fmt,nb_read_frames:"
            "format=duration",
            "-of", "json",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(probe.stdout)
    streams = info.get("streams", [])
    if len(streams) != 1:
        raise ValueError(f"Expected exactly one video stream: {video.name}")
    stream = streams[0]
    if (
        stream.get("codec_type") != "video"
        or stream.get("codec_name") != "h264"
        or stream.get("pix_fmt") != "yuv420p"
        or (stream.get("width"), stream.get("height")) != (720, 720)
    ):
        raise ValueError(f"Not H.264 720x720 yuv420p: {video.name}")
    if int(stream.get("nb_read_frames") or 0) < 2:
        raise ValueError(f"MP4 has no animated movement: {video.name}")
    duration = float(info["format"]["duration"])
    expected = original_duration_ms / 1000
    if not (expected - 0.15 <= duration <= expected + max(0.75, expected * 0.15)):
        raise ValueError(f"Animation duration mismatch: {video.name}: {duration}s")


def make_derivatives(
    manifest: dict,
    *,
    source_dir: Path,
    slugs: list[str],
    ffprobe: str = "ffprobe",
) -> list[tuple[str, dict, Path, bytes]]:
    """Validate every item before permitting any on-disk mutation."""
    pending = pending_exercises(manifest)
    if not slugs or len(set(slugs)) != len(slugs):
        raise ValueError("Specify one or more distinct pending slugs")
    unknown = sorted(set(slugs) - set(pending))
    if unknown:
        raise ValueError(f"Non-pending or unknown exercise slugs: {unknown}")
    report_file = source_dir / "results-general.json"
    report = json.loads(report_file.read_text(encoding="utf-8"))
    if (
        report.get("method") != "realesrgan-x4plus ncnn Vulkan (x4)"
        or report.get("source_resolution") != [180, 180]
        or report.get("ai_resolution") != [720, 720]
    ):
        raise ValueError("Not an approved Real-ESRGAN_x4plus x4 batch")
    samples = report.get("samples", [])
    if len({item["slug"] for item in samples}) != len(samples):
        raise ValueError("Duplicate samples in processing report")
    indexed = {item["slug"]: item for item in samples}
    verified: list[tuple[str, dict, Path, bytes]] = []
    for slug in slugs:
        media = pending[slug]
        sample = indexed.get(slug)
        if not sample:
            raise ValueError(f"Missing Real-ESRGAN output metadata: {slug}")
        gif_path = MEDIA_ROOT / media["path"]
        source_bytes = gif_path.read_bytes()
        expected_source = f"backend/assets/exercise-guides/{media['path']}"
        if (
            sha256(source_bytes) != media["asset_sha256"]
            or sample["source_sha256"] != media["asset_sha256"]
            or sample["input"] != expected_source
            or sample["frames"] != media["frame_count"]
            or sample["duration_ms"] != media["duration_ms"]
        ):
            raise ValueError(f"GIF identity/frame timing mismatch: {slug}")
        video = source_dir / f"{slug}-general-720.mp4"
        data = video.read_bytes()
        if (
            data[4:8] != b"ftyp"
            or len(data) < 1024
            or len(data) > 10_000_000
            or len(data) != sample["ai_mp4_bytes"]
        ):
            raise ValueError(f"Invalid, truncated or oversized MP4: {slug}")
        if sample.get("ai_mp4_sha256") and sha256(data) != sample["ai_mp4_sha256"]:
            raise ValueError(f"AI MP4 checksum mismatch: {slug}")
        inspect_h264(video, ffprobe=ffprobe, original_duration_ms=media["duration_ms"])
        verified.append((slug, media, video, data))
    return verified


def apply(manifest: dict, checked: list[tuple[str, dict, Path, bytes]]) -> None:
    """Commit assets and manifest after the complete batch passes all checks."""
    import copy

    changed = copy.deepcopy(manifest)
    entries = changed["exercises"]
    for slug, _media, _video, data in checked:
        media = entries[slug]["media"][0]
        relative = f"gymvisual/ai-reviewed/{slug}-x4plus-720.mp4"
        media["video_sources"] = [
            {
                "path": relative,
                "mime_type": "video/mp4",
                "width": 720,
                "height": 720,
                "byte_size": len(data),
                "sha256": sha256(data),
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
            "owner_visual_approval": BULK_APPROVAL,
            "transformation": "RealESRGAN-x4plus-720x720-H264",
            "rights_basis": "owner_confirmed_GymVisual_usage_and_derivatives",
        }
    changed["asset_count"] += len(checked)
    changed["total_bytes"] += sum(len(data) for _, _, _, data in checked)
    changed["ai_upscaled_video_count"] += len(checked)
    changed["ai_upscaled_video_total_bytes"] += sum(
        len(data) for _, _, _, data in checked
    )
    # Each target was checked as absent at planning time: refuse overwrites.
    targets = [
        MEDIA_ROOT / f"gymvisual/ai-reviewed/{slug}-x4plus-720.mp4"
        for slug, _, _, _ in checked
    ]
    if any(target.exists() for target in targets):
        raise FileExistsError("Existing AI video target; no overwrite allowed")
    for target, (_, _, _video, data) in zip(targets, checked, strict=True):
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(data)
    temporary = MANIFEST_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(changed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, MANIFEST_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, help="Pilot output containing MP4 and JSON")
    parser.add_argument("--slugs", nargs="+", help="Optional batch subset; defaults to all pending")
    parser.add_argument("--ffprobe", default=shutil.which("ffprobe") or "ffprobe")
    parser.add_argument("--apply", action="store_true", help="Explicitly write verified assets")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    pending = pending_exercises(manifest)
    slugs = args.slugs or list(pending)
    if not args.source_dir:
        if args.apply:
            parser.error("--apply requires --source-dir")
        print(json.dumps({"pending_count": len(pending), "slugs": slugs}, indent=2))
        return
    verified = make_derivatives(
        manifest, source_dir=args.source_dir, slugs=slugs, ffprobe=args.ffprobe
    )
    if args.apply:
        apply(manifest, verified)
    print(
        json.dumps(
            {
                "verified_count": len(verified),
                "bytes": sum(len(data) for _, _, _, data in verified),
                "applied": args.apply,
                "slugs": [slug for slug, _, _, _ in verified],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
