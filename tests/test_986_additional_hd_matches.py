"""Exercise #986: extra evidence-backed poster imports preserve animation fallback."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "backend/assets/exercise-guides"
MATCHES = {
    "t-bar-row": "lever-t-bar-row",
    "lying-dumbbell-triceps-extension": "dumbbell-lying-triceps-extension",
}


def test_extra_match_decisions_are_verified_and_imported() -> None:
    with (ROOT / "docs/exercises/catalog-v2/986_FULL_HD_COVERAGE.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = {row["canonical_slug"]: row for row in csv.DictReader(stream)}
    assert len(rows) == 206
    for slug, source in MATCHES.items():
        row = rows[slug]
        assert row["semantic_status"] == "VERIFIED_SEMANTIC"
        assert row["source_slug"] == source
        assert row["source_gender"] == "male"
        assert row["confidence"] == "high"
        assert row["import_status"] == "imported_replaced"
        assert row["previous_media_source"].startswith("gymvisual/")


def test_extra_poster_derivatives_and_gif_fallback_are_intact() -> None:
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    for slug, source in MATCHES.items():
        entry = manifest["exercises"][slug]
        assert entry["status"] == "approved"
        media = entry["media"][0]
        assert media["type"] == "animation"
        assert media["path"].startswith("gymvisual/")
        assert media["poster_path"] == f"exercises-media/{slug}/poster-1280.jpg"
        assert media["poster_source"]["source_slug"] == source
        assert media["poster_source"]["source_gender"] == "male"
        sources = media["poster_sources"]
        assert len(sources) == 6
        assert {(item["width"], item["mime_type"]) for item in sources} == {
            (width, mime) for width in (640, 1280, 1920) for mime in ("image/webp", "image/jpeg")
        }
        for item in sources:
            path = ASSETS / item["path"]
            payload = path.read_bytes()
            assert len(payload) == item["byte_size"]
            assert hashlib.sha256(payload).hexdigest() == item["sha256"]
