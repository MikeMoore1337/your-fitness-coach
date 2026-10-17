"""Owner-approved #986 RealESRGAN pilot: genuine-motion fallback and source integrity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "backend/assets/exercise-guides"
MANIFEST = json.loads((MEDIA / "manifest.json").read_text(encoding="utf-8"))
APPROVED = {"deadlift", "machine-chest-press", "russian-twist", "walking-lunge"}


def test_ai_derived_videos_have_approved_provenance_and_preserve_original_gif() -> None:
    reviewed = {}
    for slug, item in MANIFEST["exercises"].items():
        media = (item.get("media") or [None])[0]
        if (
            not media
            or media.get("video_provenance", {}).get("source_kind") != "ai_upscaled_gymvisual"
        ):
            continue
        reviewed[slug] = media
    assert set(reviewed) == APPROVED
    assert MANIFEST["ai_upscaled_video_count"] == len(APPROVED)
    assert MANIFEST["hq_video_count"] == 77  # Native HD is tracked separately.

    total = 0
    for slug, media in reviewed.items():
        gif = MEDIA / media["path"]
        assert gif.suffix == ".gif" and gif.is_file()
        assert hashlib.sha256(gif.read_bytes()).hexdigest() == media["asset_sha256"]
        assert media["width"] == media["height"] == 180
        assert media["type"] == "animation"
        provenance = media["video_provenance"]
        assert provenance["source_path"] == media["path"]
        assert provenance["source_sha256"] == media["asset_sha256"]
        assert provenance["source_asset_id"] == media["asset_id"]
        assert provenance["model"] == "RealESRGAN_x4plus"
        assert provenance["native_hd"] is False
        assert provenance["owner_visual_approval"] == "2026-10-17 #1073 four-sample review"

        (video,) = media["video_sources"]
        assert (video["width"], video["height"]) == (720, 720)
        assert video["mime_type"] == "video/mp4"
        assert video["path"] == f"gymvisual/ai-reviewed/{slug}-x4plus-720.mp4"
        payload = (MEDIA / video["path"]).read_bytes()
        assert payload[4:8] == b"ftyp"
        assert len(payload) == video["byte_size"]
        assert hashlib.sha256(payload).hexdigest() == video["sha256"]
        total += len(payload)
    assert total == MANIFEST["ai_upscaled_video_total_bytes"] == 614973
