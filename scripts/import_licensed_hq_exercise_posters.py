"""Offline SHA-verified import of semantically approved high-resolution exercise posters.

Owner-authorized source: akajdid-mostafa/exercises-media pinned to exact commit.
No network access in this command. Supply authentic JPEG files in --input-dir.
This is a bounded 13-exercise pilot, not an all-catalog replacement.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "backend/assets/exercise-guides/manifest.json"
ASSETS = MANIFEST.parent
COVERAGE = ROOT / "docs/exercises/catalog-v2/986_COVERAGE_MATRIX.csv"
SOURCE = ROOT / "docs/exercises/catalog-v2/986_SOURCE_INVENTORY.csv"
DEFAULT_INPUT = ROOT / ".artifacts/runtime/986-hq-posters/inputs"
DEST_DIR = ASSETS / "exercises-media"
SOURCE_REVISION = "18742da40b0627c85925c5dd4441dc3eac0594d0"
SOURCE_URL = "https://github.com/akajdid-mostafa/exercises-media"
EXPECTED_COUNT = 13


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def plan(input_dir: Path) -> list[dict[str, object]]:
    with COVERAGE.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        inventory = list(csv.DictReader(stream))
    index = {(row["gender"], row["slug"], row["asset_type"]): row for row in inventory}
    selected = [
        row for row in rows if row["status"] == "VERIFIED" and row["current_status"] == "approved"
    ]
    if len(selected) != EXPECTED_COUNT:
        raise ValueError("Verified candidate coverage changed: refuse silent import expansion")
    result = []
    for row in selected:
        canonical = row["canonical_slug"]
        candidate = row["candidate_slug"]
        if not canonical.replace("-", "").isalnum() or not candidate.replace("-", "").isalnum():
            raise ValueError("Unsafe catalog media slug")
        record = index.get(("male", candidate, "poster"))
        if not record or record["path"] != f"public/thumbnails/male/{candidate}.jpg":
            raise ValueError("Pinned source inventory poster missing")
        path = input_dir / f"{candidate}.jpg"
        if not path.is_file() or not path.resolve().is_relative_to(input_dir.resolve()):
            raise FileNotFoundError("Expected locally pinned JPG; never fetch implicitly")
        data = path.read_bytes()
        if git_blob_sha1(data) != record["git_blob_sha1"] or len(data) != int(record["bytes"]):
            raise ValueError("Candidate source SHA-1/size mismatch")
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG" or ImageOps.exif_transpose(image).size != (1920, 1080):
                raise ValueError("Unexpected candidate format/resolution")
            converted = ImageOps.exif_transpose(image).convert("RGB")
            canvas = ImageOps.pad(
                converted, (720, 720), color=(247, 247, 247), method=Image.Resampling.LANCZOS
            )
            buffer = io.BytesIO()
            canvas.save(buffer, format="JPEG", optimize=True, quality=88, subsampling=0)
            encoded = buffer.getvalue()
        result.append(
            {
                "canonical": canonical,
                "candidate": candidate,
                "original_asset": row["current_media_source"],
                "poster_source_path": record["path"],
                "source_git_blob_sha1": record["git_blob_sha1"],
                "bytes": encoded,
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify & import owner-licensed HQ exercise posters"
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--apply", action="store_true", help="Modify manifest and assets; dry-run by default"
    )
    options = parser.parse_args()
    assets = plan(options.input_dir)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != 3
        or manifest.get("counts", {}).get("approved_animated") != 167
    ):
        raise ValueError("Unrecognized active media manifest, aborting")
    total_delta = 0
    changed = []
    for item in assets:
        canonical = str(item["canonical"])
        media = manifest["exercises"][canonical]["media"][0]
        expected_animation = str(item["original_asset"])
        if (
            media["path"] != expected_animation
            or media["poster_path"] != expected_animation.removesuffix(".gif") + ".jpg"
        ):
            raise ValueError("Active media differs from frozen verified coverage")
        output_path = f"exercises-media/{canonical}-hq720.jpg"
        encoded = bytes(item["bytes"])
        total_delta += len(encoded) - int(media["poster_byte_size"])
        if options.apply:
            output = ASSETS / output_path
            if output.exists():
                raise FileExistsError(
                    "Output already exists; refuse overwriting existing imported assets"
                )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(encoded)
            old_poster = ASSETS / media["poster_path"]
            old_poster.unlink()
            media["poster_path"] = output_path
            media["poster_byte_size"] = len(encoded)
            media["poster_sha256"] = sha256(encoded)
            media["poster_dimensions"] = {"width": 720, "height": 720}
            media["poster_source"] = {
                "name": "Exercises Media",
                "url": SOURCE_URL,
                "source_revision": SOURCE_REVISION,
                "source_path": item["poster_source_path"],
                "git_blob_sha1": item["source_git_blob_sha1"],
                "rights_basis": "owner_confirmed_hq_media_usage_and_derivatives_2026-10-16",
                "transformation": "pillow-lanczos-pad-720-jpeg-q88-no-metadata",
            }
        changed.append(canonical)
    if options.apply:
        manifest["total_bytes"] += total_delta
        manifest["hq_poster_count"] = EXPECTED_COUNT
        MANIFEST.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(
        f"HQ_POSTER_IMPORT_VERIFIED={len(changed)} APPLY={options.apply} (no network; no animation replacement)"
    )


if __name__ == "__main__":
    main()
