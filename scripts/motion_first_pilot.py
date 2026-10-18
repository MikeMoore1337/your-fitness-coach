"""Fail-closed helpers for the #1110 motion-first exercise-media pilot.

This module describes reviewable candidates and validates offline processing
metadata. It does not edit the production catalog and it never downloads or
overwrites media.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import Any

PILOT_EXERCISES = ("ab-wheel", "kettlebell-swing", "romanian-deadlift")

MOTION_SOURCE_VERIFIED = "MOTION_SOURCE_VERIFIED"
STATIC_POSE_SEQUENCE = "STATIC_POSE_SEQUENCE"
CROSSFADE_SOURCE = "CROSSFADE_SOURCE"
MOTION_SOURCE_REVIEW = "MOTION_SOURCE_REVIEW"
SOURCE_REJECTED = "SOURCE_REJECTED"
VISUAL_PENDING = "VISUAL_PENDING"

HARD_BLOCKED_STATUSES = frozenset(
    {STATIC_POSE_SEQUENCE, CROSSFADE_SOURCE, SOURCE_REJECTED, VISUAL_PENDING}
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def classify_source(candidate: Mapping[str, Any]) -> str:
    """Classify source evidence without guessing unknown facts."""

    if candidate.get("canonical_slug") not in PILOT_EXERCISES:
        return SOURCE_REJECTED
    if candidate.get("explicit_rejection") is True:
        return SOURCE_REJECTED
    if candidate.get("static_pose_sequence") is True:
        return STATIC_POSE_SEQUENCE
    if candidate.get("crossfade") is True:
        return CROSSFADE_SOURCE
    if candidate.get("owner_visual_status") == "pending":
        return VISUAL_PENDING
    rights = candidate.get("rights")
    if not isinstance(rights, Mapping) or any(
        rights.get(key) is not True
        for key in ("commercial_use_verified", "redistribution_verified")
    ):
        return MOTION_SOURCE_REVIEW
    if candidate.get("motion_continuity") is not True:
        return MOTION_SOURCE_REVIEW
    if candidate.get("ghosting") is not False:
        return MOTION_SOURCE_REVIEW
    if candidate.get("technique_qc") != "pass":
        return MOTION_SOURCE_REVIEW
    if not candidate.get("source_url") or not candidate.get("source_revision"):
        return MOTION_SOURCE_REVIEW
    return MOTION_SOURCE_VERIFIED


def validate_provenance(candidate: Mapping[str, Any]) -> None:
    """Validate the minimum file-level provenance required by the pilot."""

    slug = candidate.get("canonical_slug")
    if slug not in PILOT_EXERCISES:
        raise ValueError(f"Unsupported canonical exercise: {slug!r}")
    for key in ("source_url", "source_revision", "source_sha256"):
        if not candidate.get(key):
            raise ValueError(f"Missing provenance field: {key}")
    source_sha = str(candidate["source_sha256"]).lower()
    if not SHA256_PATTERN.fullmatch(source_sha):
        raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
    rights = candidate.get("rights")
    if not isinstance(rights, Mapping):
        raise ValueError("Rights evidence is missing")
    if any(
        rights.get(key) is not True
        for key in ("commercial_use_verified", "redistribution_verified")
    ):
        raise ValueError("Commercial use and redistribution must be explicitly verified")
    output_file = candidate.get("output_file")
    if not isinstance(output_file, str) or not output_file:
        raise ValueError("output_file is required")


def safe_output_path(output_root: Path, relative_path: str) -> Path:
    """Resolve a pilot output while preventing path escape and production writes."""

    root = output_root.resolve()
    output = (root / relative_path).resolve()
    if not output.is_relative_to(root):
        raise ValueError("Output path escapes the pilot artifact root")
    normalized = output.as_posix().lower()
    if "/backend/assets/exercise-guides/" in normalized or normalized.endswith(
        "/backend/assets/exercise-guides/manifest.json"
    ):
        raise ValueError("Pilot cannot write production media or manifest")
    return output


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def plan_processing(
    records: Iterable[Mapping[str, Any]], output_root: Path
) -> list[dict[str, Any]]:
    """Plan only the three named candidates and fail closed on collisions."""

    records = list(records)
    slugs = [record.get("canonical_slug") for record in records]
    if len(records) != len(PILOT_EXERCISES) or set(slugs) != set(PILOT_EXERCISES):
        raise ValueError("The pilot scope must contain exactly the three named exercises")

    plan: list[dict[str, Any]] = []
    for record in records:
        validate_provenance(record)
        status = classify_source(record)
        if status in HARD_BLOCKED_STATUSES:
            raise ValueError(f"Candidate {record['canonical_slug']} is blocked: {status}")
        output = safe_output_path(output_root, str(record["output_file"]))
        expected_sha = record.get("output_sha256")
        if output.exists():
            if not expected_sha or file_sha256(output) != expected_sha:
                raise FileExistsError(f"Refusing to overwrite existing output: {output}")
            state = "resume"
        else:
            state = "new"
        plan.append(
            {
                "canonical_slug": record["canonical_slug"],
                "source_status": status,
                "output": output,
                "state": state,
            }
        )
    return plan


def validate_pts(pts: Sequence[int | float]) -> None:
    if len(pts) < 2 or any(current <= previous for previous, current in pairwise(pts)):
        raise ValueError("Presentation timestamps must be strictly increasing")


def validate_cycle(
    first_pixel: Sequence[int], last_pixel: Sequence[int], max_mean_abs: float
) -> None:
    if len(first_pixel) != len(last_pixel) or not first_pixel:
        raise ValueError("Cycle samples must have equal non-empty dimensions")
    mean_abs = sum(
        abs(left - right) for left, right in zip(first_pixel, last_pixel, strict=True)
    ) / len(first_pixel)
    if mean_abs > max_mean_abs:
        raise ValueError(f"Loop seam exceeds threshold: {mean_abs:.3f} > {max_mean_abs:.3f}")


def validate_output_metadata(metadata: Mapping[str, Any]) -> None:
    required = (
        "width",
        "height",
        "fps",
        "codec",
        "pix_fmt",
        "has_audio",
        "duration_sec",
        "frames",
        "decode_ok",
    )
    missing = [key for key in required if key not in metadata]
    if missing:
        raise ValueError(f"Missing output metadata: {', '.join(missing)}")
    if int(metadata["width"]) < 720 or int(metadata["height"]) < 720:
        raise ValueError("Output must be at least 720x720")
    fps = float(metadata["fps"])
    if not 24 <= fps <= 30:
        raise ValueError("Output FPS must be between 24 and 30")
    if metadata["codec"] != "h264" or metadata["pix_fmt"] != "yuv420p":
        raise ValueError("Output must be H.264 yuv420p")
    if metadata["has_audio"] is not False:
        raise ValueError("Output must not contain an audio stream")
    if float(metadata["duration_sec"]) <= 0 or int(metadata["frames"]) < 2:
        raise ValueError("Output must contain a non-empty video")
    if metadata["decode_ok"] is not True:
        raise ValueError("Output decode evidence is missing or failed")
    if metadata.get("pts_monotonic") is not True:
        raise ValueError("Output PTS evidence is missing or failed")
    if metadata.get("cycle_seam_pass") is not True:
        raise ValueError("Output loop seam evidence is missing or failed")


def build_gallery(records: Iterable[Mapping[str, Any]], output_file: Path) -> None:
    """Build a local-only comparison gallery from a reviewed artifact manifest."""

    cards: list[str] = []
    for record in records:
        slug = html.escape(str(record.get("canonical_slug", "")))
        status = html.escape(str(record.get("source_status", "Нет данных")))
        media_items: list[str] = []
        for media in record.get("media", []):
            if not isinstance(media, Mapping):
                raise ValueError("Gallery media entry must be an object")
            label = html.escape(str(media.get("label", "Материал")))
            relative = html.escape(str(media.get("path", "")), quote=True)
            kind = media.get("kind")
            if kind == "video":
                element = f'<video controls muted loop playsinline preload="metadata" src="{relative}"></video>'
            elif kind == "image":
                element = f'<img loading="lazy" alt="{label}" src="{relative}">'
            else:
                raise ValueError(f"Unsupported gallery media kind: {kind!r}")
            media_items.append(f"<figure>{element}<figcaption>{label}</figcaption></figure>")
        cards.append(
            f'<section><h2>{slug}</h2><p class="status">Статус источника: {status}</p>'
            f'<div class="media">{"".join(media_items)}</div></section>'
        )
    payload = (
        """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Motion-first pilot #1110</title><style>
body{font:16px system-ui,sans-serif;background:#111;color:#eee;margin:2rem}section{border:1px solid #444;padding:1rem;margin:1rem 0}h1,h2{margin-top:0}.status{color:#b8f36b}.media{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem}figure{margin:0}video,img{display:block;width:100%;aspect-ratio:1;object-fit:contain;background:#000}figcaption{padding-top:.4rem;font-size:.9rem}
</style></head><body><h1>Motion-first pilot #1110</h1>
<p>Локальная галерея сравнения; материалы не являются production-доказательством и не меняют manifest.</p>
"""
        + "\n".join(cards)
        + "\n</body></html>\n"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(payload, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gallery-manifest", type=Path)
    parser.add_argument("--gallery-output", type=Path)
    args = parser.parse_args()
    if bool(args.gallery_manifest) != bool(args.gallery_output):
        parser.error("--gallery-manifest and --gallery-output must be supplied together")
    if args.gallery_manifest:
        records = json.loads(args.gallery_manifest.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("Gallery manifest must be a list")
        build_gallery(records, args.gallery_output)


if __name__ == "__main__":
    main()
