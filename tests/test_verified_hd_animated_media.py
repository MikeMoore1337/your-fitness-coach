"""Issue #986: every approved HD video must pair with a verified poster and fallback."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "backend/assets/exercise-guides"
MANIFEST = json.loads((ASSET_ROOT / "manifest.json").read_text(encoding="utf8"))


def test_verified_animated_hd_video_coverage() -> None:
    entries = MANIFEST["exercises"]
    assert len(entries) == 206
    animated = [
        (slug, entry["media"][0])
        for slug, entry in entries.items()
        if entry.get("media") and entry["media"][0].get("video_sources")
    ]
    assert len(animated) == MANIFEST["hq_video_count"] == 77
    assert sum(len(media["video_sources"]) for _, media in animated) == 154
    for slug, media in animated:
        video = media["video_sources"]
        assert [(source["width"], source["height"]) for source in video] == [
            (854, 480),
            (1280, 720),
        ], slug
        assert media["poster_path"]
        assert (ASSET_ROOT / media["poster_path"]).is_file()
        if media["type"] == "animation":
            assert media["path"].endswith(".gif"), slug
            assert (ASSET_ROOT / media["path"]).is_file()
        else:
            assert media["type"] == "image", slug
            assert media["poster_source"], slug
        for src in video:
            p = ASSET_ROOT / src["path"]
            data = p.read_bytes()
            assert data[4:8] == b"ftyp", slug
            assert src["mime_type"] == "video/mp4"
            assert src["byte_size"] == len(data)
            assert src["sha256"] == hashlib.sha256(data).hexdigest()
    assert (
        sum(src["byte_size"] for _, media in animated for src in media["video_sources"])
        == MANIFEST["hq_video_total_bytes"]
    )


def test_unverified_exercises_keep_legacy_media_untouched() -> None:
    for slug, entry in MANIFEST["exercises"].items():
        media = entry.get("media") or []
        if not media:
            assert entry["status"] == "blocked", slug
            continue
        if media[0].get("video_sources"):
            continue
        assert not media[0].get("poster_source"), slug
        assert media[0]["type"] == "animation", slug
        assert media[0]["path"].endswith(".gif"), slug
