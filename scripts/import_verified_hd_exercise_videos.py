"""Pinned, reproducible animated HD exercise video import for Issue #986.

Read approved HQ poster source identity, fetch its matching original MP4 from the
same immutable upstream revision, verify Git blob SHA-1 and byte count, produce
local 480p/720p H.264 derivatives, and preserve original GIFs. No runtime CDN.
Do not infer semantic equivalence from filenames: only already-approved posters
are eligible. Works with source female or male regardless of performer gender.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen

from imageio_ffmpeg import get_ffmpeg_exe

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "backend/assets/exercise-guides"
MANIFEST = ASSETS / "manifest.json"
INVENTORY = ROOT / "docs/exercises/catalog-v2/986_SOURCE_INVENTORY.csv"
CACHE = ROOT / ".artifacts/runtime/986-source-videos"
OUTPUT_CACHE = ROOT / ".artifacts/runtime/986-transcoded-videos"
REVISION = "18742da40b0627c85925c5dd4441dc3eac0594d0"
RIGHTS = "owner_confirmed_unrestricted_use_2026-10-16"
PROFILES = ((480, 854, 480, 30), (720, 1280, 720, 29))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob_digest(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def read_inventory() -> dict[tuple[str, str, str], dict[str, str]]:
    with INVENTORY.open(encoding="utf-8-sig", newline="") as handle:
        return {
            (row["gender"], row["slug"], row["asset_type"]): row for row in csv.DictReader(handle)
        }


def planned(manifest: dict, inventory: dict) -> list[tuple[str, dict, dict]]:
    result = []
    for slug, item in sorted(manifest["exercises"].items()):
        if item.get("status") != "approved" or len(item.get("media", [])) != 1:
            continue
        media = item["media"][0]
        source = media.get("poster_source")
        if not source or media.get("video_sources"):
            continue
        if source.get("source_revision") != REVISION:
            raise ValueError(f"Unrecognized image provenance: {slug}")
        if source.get("canonical_slug") != slug:
            raise ValueError(f"Canonical provenance mismatch: {slug}")
        gender, source_slug = source["source_gender"], source["source_slug"]
        video = inventory.get((gender, source_slug, "video"))
        expected = f"public/videos/{gender}/{source_slug}.mp4"
        if not video or video["path"] != expected:
            raise ValueError(f"Missing exact video matching VERIFIED image: {slug}")
        result.append((slug, media, video))
    return result


def retrieve_verified(row: dict) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / row["path"].removeprefix("public/").replace("/", "_")
    if not path.exists():
        url = f"https://raw.githubusercontent.com/akajdid-mostafa/exercises-media/{REVISION}/{row['path']}"
        with urlopen(url, timeout=45) as response:
            source = response.read()
        if len(source) != int(row["bytes"]) or blob_digest(source) != row["git_blob_sha1"]:
            raise ValueError(f"Upstream MP4 SHA/byte count drift: {row['path']}")
        path.write_bytes(source)
    data = path.read_bytes()
    if len(data) != int(row["bytes"]) or blob_digest(data) != row["git_blob_sha1"]:
        raise ValueError(f"Cached MP4 SHA/byte count drift: {row['path']}")
    return path


def convert(source: Path, slug: str, width: int, height: int, crf: int) -> tuple[dict, bytes]:
    OUTPUT_CACHE.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_CACHE / f"{slug}-{height}p-h264.mp4"
    if not path.exists():
        with tempfile.NamedTemporaryFile(suffix=".mp4", dir=OUTPUT_CACHE, delete=False) as temp:
            temporary = Path(temp.name)
        try:
            command = [
                get_ffmpeg_exe(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-threads",
                "2",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                f"fps=24,scale={width}:{height}:flags=lanczos",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                str(crf),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-y",
                str(temporary),
            ]
            subprocess.run(command, check=True, timeout=150)
            if temporary.stat().st_size < 1000:
                raise ValueError(f"Encoded video suspiciously small: {slug}/{height}")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    data = path.read_bytes()
    relative = f"exercises-media/videos/{slug}-{height}p-h264.mp4"
    return {
        "path": relative,
        "mime_type": "video/mp4",
        "width": width,
        "height": height,
        "byte_size": len(data),
        "sha256": digest(data),
    }, data


def referenced_paths(manifest: dict) -> set[str]:
    result: set[str] = set()
    for item in manifest["exercises"].values():
        for media in item.get("media", []):
            for key in ("path", "poster_path"):
                if media.get(key):
                    result.add(media[key])
            for key in ("sources", "poster_sources", "video_sources"):
                result.update(obj["path"] for obj in media.get(key, []))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 3:
        raise ValueError("Unexpected manifest schema")
    inventory = read_inventory()
    items = planned(manifest, inventory)
    if args.limit:
        items = items[: args.limit]
    new_manifest = copy.deepcopy(manifest)
    created: dict[str, bytes] = {}
    for index, (slug, _media, row) in enumerate(items, 1):
        source_file = retrieve_verified(row)
        video_sources = []
        for _quality, width, height, crf in PROFILES:
            descriptor, data = convert(source_file, slug, width, height, crf)
            target = ASSETS / descriptor["path"]
            if target.is_file() and target.read_bytes() != data:
                raise ValueError(f"Existing asset conflicts with source: {target}")
            created[descriptor["path"]] = data
            video_sources.append(descriptor)
        out_media = new_manifest["exercises"][slug]["media"][0]
        out_media["video_sources"] = video_sources
        out_media["video_provenance"] = {
            "source_name": "Exercises Media",
            "source_revision": REVISION,
            "source_path": row["path"],
            "source_gender": row["gender"],
            "source_slug": row["slug"],
            "source_git_blob_sha1": row["git_blob_sha1"],
            "source_byte_size": int(row["bytes"]),
            "source_sha256": digest(source_file.read_bytes()),
            "rights_basis": RIGHTS,
            "transformation": "ffmpeg-h264-24fps-yuv420p-480p-crf30-720p-crf29",
        }
        print(f"ENCODED {index}/{len(items)} {slug}", flush=True)
    video_items = [
        media
        for item in new_manifest["exercises"].values()
        for media in item.get("media", [])
        if media.get("video_sources")
    ]
    new_manifest["hq_video_count"] = len(video_items)
    new_manifest["hq_video_total_bytes"] = sum(
        src["byte_size"] for m in video_items for src in m["video_sources"]
    )
    assets = referenced_paths(new_manifest)
    new_manifest["asset_count"] = len(assets)
    new_manifest["total_bytes"] = sum(
        len(created[p]) if p in created else (ASSETS / p).stat().st_size for p in assets
    )
    print(
        f"VERIFIED_ANIMATED_HQ={new_manifest['hq_video_count']} "
        f"VIDEO_NEW={len(items)} FILES={len(created)} "
        f"TOTAL_BYTES={new_manifest['hq_video_total_bytes']} APPLY={args.apply}",
        flush=True,
    )
    if not args.apply:
        return
    for name, data in created.items():
        target = ASSETS / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
    MANIFEST.write_text(
        json.dumps(new_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
