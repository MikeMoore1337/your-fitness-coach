"""Build a review-only comparison of pinned openGym metadata and YFC media IDs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = "7a3ace53c5e910c2185f22df803726c5838a99ae"
SOURCE_PATH = "catalogue/exercises"
sys.path.insert(0, str(ROOT / "backend"))
from fitminiapp_api.services.exercise_catalog_metadata import (  # noqa: E402
    CANONICAL_EXERCISE_REDIRECTS,
    structured_catalog_metadata,
)
from fitminiapp_api.services.program_seed_data import EXERCISE_CATALOG  # noqa: E402


def normalize(value: str) -> str:
    return re.sub(
        r"[^\w]+", " ", unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    ).strip()


def compare(records, blobs, catalog, metadata, redirects, manifest):
    lookup = defaultdict(set)
    canonical = set()
    for slug, title, *_ in catalog:
        slug = redirects.get(slug, slug)
        canonical.add(slug)
        for value in (title, *metadata.get(slug, {}).get("aliases", ())):
            if normalize(value):
                lookup[normalize(value)].add(slug)
    media_ids = defaultdict(set)
    for slug, entry in manifest["exercises"].items():
        for item in entry.get("media", []):
            match = re.fullmatch(r"gymvisual:([0-9]{4}):[^:]+", item.get("asset_id", ""))
            if match:
                media_ids[match.group(1)].add(slug)
    if set(manifest["exercises"]) != canonical:
        raise ValueError("canonical and manifest entries differ")
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)) or set(ids) != set(blobs):
        raise ValueError("duplicate IDs or source tree mismatch")
    ids_set = set(ids)
    if any(record.get("variantOf") and record["variantOf"] not in ids_set for record in records):
        raise ValueError("unresolved variantOf")
    rows = []
    dimensions = {field: Counter() for field in ("bodyPart", "equipment", "target", "textSource")}
    for record in sorted(records, key=lambda item: item["id"]):
        sid = record["id"]
        media = sorted(media_ids.get(sid, ()))
        names = sorted(lookup.get(normalize(record.get("name", "")), ()))
        for field in dimensions:
            dimensions[field][record.get(field) or "UNKNOWN"] += 1
        if media and names and not set(media).intersection(names):
            reason = "NAME_MEDIA_CONFLICT"
        elif len(media) > 1 or len(names) > 1:
            reason = "AMBIGUOUS_CANDIDATES"
        elif record.get("variantOf"):
            reason = "UPSTREAM_VARIANT_IDENTITY_UNVERIFIED"
        elif media or names:
            reason = "CANDIDATE_IDENTITY_UNVERIFIED"
        else:
            reason = "NO_DETERMINISTIC_CANDIDATE"
        rows.append(
            {
                "source_project": "openGym",
                "source_revision": SOURCE_REVISION,
                "source_id": sid,
                "source_blob_sha1": blobs[sid],
                "text_source": record.get("textSource") or "UNKNOWN",
                "variant_of": record.get("variantOf") or "",
                "media_source": "Gym visual (upstream claim)",
                "media_id_candidates": "|".join(media),
                "name_candidates": "|".join(names),
                "status": "REVIEW",
                "reason": reason,
                "evidence": ";".join(
                    x
                    for x, present in (
                        ("media_numeric_id", media),
                        ("normalized_name_or_approved_alias", names),
                        ("variantOf", record.get("variantOf")),
                    )
                    if present
                )
                or "none",
            }
        )
    return rows, sorted(canonical), media_ids, dimensions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="openGym Git checkout at the pinned revision")
    parser.add_argument(
        "output", type=Path, help="empty output directory outside the source checkout"
    )
    args = parser.parse_args()

    def git(*args_):
        return subprocess.check_output(
            ["git", "-C", str(args.source), *args_], text=True, encoding="utf-8"
        )

    if git("rev-parse", "HEAD").strip() != SOURCE_REVISION:
        raise ValueError("unexpected source revision")
    if git("status", "--porcelain", "--untracked-files=all", "--", SOURCE_PATH).strip():
        raise ValueError("source catalogue has local changes")
    tree = git("ls-tree", "-r", SOURCE_REVISION, "--", SOURCE_PATH)
    blobs = {
        Path(line.split("\t", 1)[1]).stem: line.split()[2]
        for line in tree.splitlines()
        if line.endswith(".json")
    }
    if args.output.resolve().is_relative_to(args.source.resolve()):
        raise ValueError("output must be outside source checkout")
    records = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((args.source / SOURCE_PATH).glob("*.json"))
    ]
    if any(
        p.stem != record.get("id")
        for p, record in zip(
            sorted((args.source / SOURCE_PATH).glob("*.json")), records, strict=True
        )
    ):
        raise ValueError("source filename and ID mismatch")
    manifest_path = ROOT / "backend/assets/exercise-guides/manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    rows, canonical, media_ids, dimensions = compare(
        records,
        blobs,
        EXERCISE_CATALOG,
        structured_catalog_metadata(),
        CANONICAL_EXERCISE_REDIRECTS,
        manifest,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError("output directory must be empty")
    with (args.output / "source-review.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with (args.output / "yfc-canonical.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["canonical_slug", "media_status", "gymvisual_numeric_ids"])
        for slug in canonical:
            writer.writerow(
                [
                    slug,
                    manifest["exercises"][slug].get("status", "UNKNOWN"),
                    "|".join(sorted(sid for sid, slugs in media_ids.items() if slug in slugs)),
                ]
            )
    summary = {
        "source_revision": SOURCE_REVISION,
        "yfc_revision": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "canonical_count": len(canonical),
        "source_count": len(rows),
        "status": dict(sorted(Counter(row["status"] for row in rows).items())),
        "reasons": dict(sorted(Counter(row["reason"] for row in rows).items())),
        "dimensions": {key: dict(sorted(value.items())) for key, value in dimensions.items()},
        "licensed_inventory": "UNAVAILABLE_LICENSED_INVENTORY",
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "canonical_count",
                    "source_count",
                    "status",
                    "reasons",
                    "licensed_inventory",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
