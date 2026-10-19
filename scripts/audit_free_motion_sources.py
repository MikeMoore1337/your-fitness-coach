#!/usr/bin/env python3
"""Review-only YFC exercise video candidate inventory (no network / spending / writes to app)."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

SOURCE_REVISION = "18742da40b0627c85925c5dd4441dc3eac0594d0"
SOURCE_REPO = "https://github.com/akajdid-mostafa/exercises-media"
ALIASES = {
    "db": "dumbbell",
    "dumbbells": "dumbbell",
    "dumbbell": "dumbbell",
    "seated": "seat",
    "seating": "seat",
    "standing": "stand",
    "pullups": "pullup",
}
IGNORE = {"with", "and", "on", "to", "the", "of"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def tokens(slug: str) -> set[str]:
    return {ALIASES.get(token, token) for token in slug.split("-") if token not in IGNORE}


def name_similarity(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    return round(2 * len(a & b) / (len(a) + len(b)), 4) if a and b else 0.0


def build_matrix(
    yfc: list[dict[str, str]], source: list[dict[str, str]]
) -> tuple[list[dict[str, str]], dict[str, object]]:
    if len(yfc) != 206 or len({r["canonical_slug"] for r in yfc}) != 206:
        raise ValueError(
            "YFC canonical input is not the expected 206 unique exercises; refresh audit"
        )
    video_rows = [s for s in source if s["asset_type"] == "video"]
    if len(video_rows) != 593:
        raise ValueError(
            "Pinned source inventory is no longer 593 video files; audit revision manually"
        )
    source_by_slug: dict[str, list[dict[str, str]]] = defaultdict(list)
    for source_row in video_rows:
        if not (
            source_row["path"].startswith("public/videos/") and source_row["path"].endswith(".mp4")
        ):
            raise ValueError("Unexpected source video path")
        source_by_slug[source_row["slug"]].append(source_row)
    approved = [r for r in yfc if r["semantic_status"] == "VERIFIED_SEMANTIC"]
    if len(approved) != 77:
        raise ValueError("Expected 77 previously approved mappings; review changed baseline")
    results: list[dict[str, str]] = []
    for row in yfc:
        slug = row["canonical_slug"]
        if row["semantic_status"] == "VERIFIED_SEMANTIC":
            decision = "ALREADY_APPROVED_HD"
            candidates = [row["source_slug"]]
        elif slug in source_by_slug:
            decision = "EXACT_FILENAME_REVIEW"
            candidates = [slug]
        else:
            # Suggestions never acquire a verified status, even at similarity 1.0.
            ranked = sorted(
                ((name_similarity(slug, candidate), candidate) for candidate in source_by_slug),
                key=lambda pair: (-pair[0], pair[1]),
            )
            candidates = [name for score, name in ranked[:3] if score >= 0.5]
            decision = "NAME_ONLY_REVIEW" if candidates else "NO_SAFE_FILENAME_CANDIDATE"
        candidate_rows = [s for name in candidates for s in source_by_slug.get(name, [])]
        gender_paths = {
            gender: next((s["path"] for s in candidate_rows if s["gender"] == gender), "")
            for gender in ("male", "female")
        }
        results.append(
            {
                "yfc_slug": slug,
                "yfc_english_title": row["english_title"],
                "yfc_equipment": row["equipment"],
                "yfc_current_media_status": row["current_status"],
                "yfc_prior_semantic_status": row["semantic_status"],
                "decision": decision,
                "source_slugs_to_review": " | ".join(candidates),
                "source_male_mp4": gender_paths["male"],
                "source_female_mp4": gender_paths["female"],
                "source_revision": SOURCE_REVISION,
                "production_approved": "YES" if decision == "ALREADY_APPROVED_HD" else "NO",
                "review_gate": "Not a new mapping approval; confirm technique/equipment/rights and visual QC",
            }
        )
    stats = dict(Counter(r["decision"] for r in results))
    return results, {
        "yfc_total": len(yfc),
        "source_mp4": len(video_rows),
        "source_unique_slug": len(source_by_slug),
        "source_revision": SOURCE_REVISION,
        "decision_counts": stats,
        "additional_verified_for_release": 0,
    }


def run(yfc_path: Path, source_path: Path, output_dir: Path) -> dict[str, object]:
    rows, summary = build_matrix(read_csv(yfc_path), read_csv(source_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "free_motion_candidates.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "free_motion_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--yfc", type=Path, default=Path("docs/exercises/catalog-v2/986_FULL_HD_COVERAGE.csv")
    )
    p.add_argument(
        "--source", type=Path, default=Path("docs/exercises/catalog-v2/986_SOURCE_INVENTORY.csv")
    )
    p.add_argument("--out", type=Path, default=Path(".artifacts/tasks/986-free-motion-audit"))
    args = p.parse_args()
    print(json.dumps(run(args.yfc, args.source, args.out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
