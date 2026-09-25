from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

MEDIA_ROOT = Path(__file__).resolve().parents[2] / "assets" / "exercise-guides"
MANIFEST_PATH = MEDIA_ROOT / "manifest.json"


@lru_cache(maxsize=1)
def _manifest() -> dict:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") not in {1, 2, 3}:
        raise RuntimeError("Unsupported exercise guide media manifest version")
    return payload


def _public_url(path: str) -> str:
    return f"/static/exercise-guides/{path}"


def _image_mime_type(path: str) -> str:
    if path.endswith(".gif"):
        return "image/gif"
    if path.endswith(".jpg"):
        return "image/jpeg"
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".webp"):
        return "image/webp"
    return "image/svg+xml"


def resolve_guide_source(
    slug: str,
    *,
    source_name: str,
    source_url: str,
    source_license: str,
    source_license_url: str | None,
) -> tuple[str, str, str, str | None]:
    source = (_manifest().get("exercises", {}).get(slug) or {}).get("source")
    if not source:
        return source_name, source_url, source_license, source_license_url
    return (
        str(source.get("name") or source_name),
        str(source.get("url") or source_url),
        str(source.get("license") or source_license),
        source.get("license_url") or source_license_url,
    )


def get_guide_media_preview(slug: str) -> dict[str, str | None]:
    item = _manifest().get("exercises", {}).get(slug) or {}
    media = (item.get("media") or [None])[0]
    if item.get("status") != "approved" or not media:
        return {
            "state": "blocked",
            "thumbnail_url": None,
            "animation_url": None,
        }
    return {
        "state": "approved_animated",
        "thumbnail_url": _public_url(str(media["poster_path"])),
        "animation_url": _public_url(str(media["path"])),
    }


def get_guide_media(
    slug: str,
    *,
    exercise_title: str,
    source_name: str,
    source_url: str,
    source_license: str,
    source_license_url: str | None,
) -> list[dict]:
    item = _manifest().get("exercises", {}).get(slug)
    if item is None or item.get("status") != "approved":
        return []
    result = []
    manifest_source = item.get("source") or {}
    for media in sorted(item["media"], key=lambda value: value["sort_order"]):
        sources = media.get("sources") or [
            {
                "path": media["path"],
                "mime_type": _image_mime_type(media["path"]),
                "width": media["width"],
                "height": media["height"],
                "byte_size": media["byte_size"],
            }
        ]
        media_source = media.get("source") or manifest_source
        result.append(
            {
                "type": media["type"],
                "url": _public_url(media["path"]),
                "poster": _public_url(media["poster_path"]),
                "phase_id": media["phase_id"],
                "phase": media["phase"],
                "alt": media.get("alt", f"{exercise_title}: {media['phase'].lower()}"),
                "asset_id": media.get("asset_id"),
                "asset_version": media.get("asset_version"),
                "variant_key": media.get("variant_key"),
                "source_name": media_source.get("name", source_name),
                "source_url": media_source.get("url", source_url),
                "source_license": media_source.get("license", source_license),
                "source_license_url": media_source.get("license_url", source_license_url),
                "width": media["width"],
                "height": media["height"],
                "byte_size": media["byte_size"],
                "sort_order": media["sort_order"],
                "sources": [
                    {
                        "url": _public_url(source["path"]),
                        "mime_type": source["mime_type"],
                        "width": source["width"],
                        "height": source["height"],
                        "byte_size": source["byte_size"],
                    }
                    for source in sorted(sources, key=lambda value: value["width"])
                ],
            }
        )
    return result
