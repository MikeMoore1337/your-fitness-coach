"""Offline #986 poster benchmark; no upload, network access, or source media checkout.

Usage (from repository root, with pinned poster files already in the ignored raw tree):
    uv run --no-project --with pillow python scripts/research_exercise_poster_bench.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/exercises/catalog-v2/986_PILOT_RESULTS.csv"
DEFAULT_RAW = ROOT / ".artifacts/tasks/986/pilot/raw"
DEFAULT_OUTPUT = ROOT / ".artifacts/tasks/986/pilot/poster-transcoded"
DEFAULT_REPORT = DEFAULT_OUTPUT / "reproduced-poster-bench.csv"

VARIANTS = (
    (854, 480, "jpeg", 83),
    (854, 480, "webp", 80),
    (1280, 720, "jpeg", 83),
    (1280, 720, "webp", 80),
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def relative_poster(raw_root: Path, candidate: str) -> Path:
    if not candidate.startswith("public/thumbnails/"):
        raise ValueError("Unexpected poster source prefix")
    result = (raw_root / candidate.removeprefix("public/")).resolve()
    if not result.is_relative_to(raw_root.resolve()) or result.suffix.lower() != ".jpg":
        raise ValueError("Unsafe input path")
    return result


def metadata_only(path: Path, photo: Image.Image) -> dict[str, int | bool]:
    # Counts/flags only, never persist EXIF payloads (GPS values, identifiers, comments).
    original = path.read_bytes()
    exif = photo.getexif()
    return {
        "source_exif_tag_count": len(exif),
        "source_gps_present": 34853 in exif,
        "source_icc_present": bool(photo.info.get("icc_profile")),
        "source_xmp_present": b"http://ns.adobe.com/xap/1.0/" in original,
        "source_iptc_present": b"Photoshop 3.0" in original,
    }


def psnr_against_normalized(original: Image.Image, encoded: Image.Image) -> float:
    difference = ImageChops.difference(original, encoded)
    mse = sum(channel**2 for channel in ImageStat.Stat(difference).rms[:3]) / 3
    return round(10 * math.log10(255**2 / mse), 2) if mse else float("inf")


def benchmark(manifest: Path, raw: Path, output_dir: Path, report: Path) -> list[dict[str, object]]:
    entries = list(csv.DictReader(manifest.open(encoding="utf-8-sig", newline="")))
    if len(entries) != 16:
        raise ValueError("Pinned #986 pilot must contain exactly 16 poster rows")
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    for entry in entries:
        gender, slug = entry["gender"], entry["slug"]
        if gender not in ("male", "female") or not slug.replace("-", "").isalnum():
            raise ValueError("Invalid poster inventory identity")
        source = relative_poster(raw, entry["candidate_poster_path"])
        if not source.is_file():
            raise FileNotFoundError("Pinned poster missing locally; no automatic download")
        source_sha256 = digest(source)
        if source_sha256 != entry["candidate_poster_sha256"]:
            raise ValueError("Poster SHA-256 mismatch; refusing to benchmark substituted media")
        with Image.open(source) as image:
            if image.format != "JPEG" or image.size != (1920, 1080):
                raise ValueError("Unexpected poster format/dimensions")
            metadata = metadata_only(source, image)
            normalized = ImageOps.exif_transpose(image).convert("RGB")

        for width, height, extension, quality in VARIANTS:
            resized = normalized.resize((width, height), Image.Resampling.LANCZOS)
            destination = output_dir / f"{gender}-{slug}-{width}x{height}-q{quality}.{extension}"
            if extension == "jpeg":
                resized.save(destination, "JPEG", quality=quality, optimize=True, subsampling=0)
            else:
                resized.save(destination, "WEBP", quality=quality, method=6)
            with Image.open(destination) as encoded:
                if encoded.getexif() or any(
                    key in encoded.info for key in ("icc_profile", "exif", "xmp")
                ):
                    raise ValueError("Encoded poster still has disallowed metadata")
                quality_psnr = psnr_against_normalized(resized, encoded.convert("RGB"))
            record: dict[str, object] = {
                "gender": gender,
                "slug": slug,
                "source_sha256": source_sha256,
                "source_bytes": source.stat().st_size,
                "source_dimensions": "1920x1080",
                **metadata,
                "variant": f"{extension}_{width}x{height}_q{quality}",
                "output_bytes": destination.stat().st_size,
                "bytes_ratio_vs_source": round(
                    destination.stat().st_size / source.stat().st_size, 4
                ),
                "psnr_db_against_resized_source": quality_psnr,
                "output_sha256": digest(destination),
                "output_exif_tag_count": 0,
                "user_visual_technique_review": "NOT_VERIFIED",
                "rights_to_public_redistribute_derivatives": "NOT_DOCUMENTED",
            }
            results.append(record)
    if len(results) != len(entries) * len(VARIANTS):
        raise RuntimeError("Incomplete local poster variant matrix")
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(f"RESEARCH_ONLY=1 POSTER_VARIANTS={len(results)}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="No-network, pinned poster privacy/size bench")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--encoded-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    options = parser.parse_args()
    benchmark(options.manifest, options.raw_root, options.encoded_dir, options.report)


if __name__ == "__main__":
    main()
