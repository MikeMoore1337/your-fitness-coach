"""Backward-compatible H.264 pilot contract for approved #986 exercises."""

from __future__ import annotations

from fitminiapp_api.schemas.program import ExerciseGuideMedia
from fitminiapp_api.services.exercise_guide_media import (
    get_guide_media,
    get_guide_media_preview,
)


def guide(slug: str) -> list[dict]:
    return get_guide_media(
        slug,
        exercise_title=slug,
        source_name="Gym visual",
        source_url="https://github.com/hasaneyldrm/exercises-dataset",
        source_license="Owner-purchased GymVisual license",
        source_license_url=None,
    )


def test_video_profiles_are_additive_and_keep_original_gif() -> None:
    for slug in ("barbell-curl", "burpee"):
        (item,) = guide(slug)
        source = ExerciseGuideMedia.model_validate(item)
        assert source.type == "animation"
        assert source.url.endswith(".gif")
        assert source.poster.endswith("/poster-1280.jpg")
        assert source.poster_preferred is True
        assert len(source.poster_sources) == 6
        assert source.sources[0].mime_type == "image/gif"
        assert [(variant.width, variant.height) for variant in source.video_sources] == [
            (854, 480),
            (1280, 720),
        ]
        assert all(variant.mime_type == "video/mp4" for variant in source.video_sources)
        assert all(
            variant.url.startswith("/static/exercise-guides/") for variant in source.video_sources
        )
        assert get_guide_media_preview(slug)["animation_url"] == source.url


def test_ai_upscaled_exercises_retain_legacy_gif() -> None:
    (item,) = guide("ab-wheel")
    media = ExerciseGuideMedia.model_validate(item)
    assert media.url.endswith(".gif")
    assert media.sources[0].mime_type == "image/gif"
    assert [(variant.width, variant.height) for variant in media.video_sources] == [(720, 720)]
    assert media.video_sources[0].url.endswith("/ab-wheel-x4plus-720.mp4")
    assert guide("unknown-slug") == []


def test_verified_static_media_plays_hd_video_and_keeps_responsive_poster() -> None:
    (source,) = guide("machine-glute-kickback")
    media = ExerciseGuideMedia.model_validate(source)
    assert media.type == "image"
    assert media.url.endswith("/poster-1280.jpg")
    assert [(variant.width, variant.height) for variant in media.video_sources] == [
        (854, 480),
        (1280, 720),
    ]
    assert get_guide_media_preview("machine-glute-kickback")["video_sources"]
    assert [(variant.width, variant.mime_type) for variant in media.sources] == [
        (640, "image/jpeg"),
        (640, "image/webp"),
        (1280, "image/jpeg"),
        (1280, "image/webp"),
        (1920, "image/jpeg"),
        (1920, "image/webp"),
    ]


def test_ai_upscaled_media_uses_video_and_falls_back_to_source_gif() -> None:
    for slug in ("machine-chest-press", "deadlift", "russian-twist", "walking-lunge"):
        (item,) = guide(slug)
        media = ExerciseGuideMedia.model_validate(item)
        assert media.type == "animation"
        assert media.url.endswith(".gif")
        assert media.sources[0].mime_type == "image/gif"
        assert [(s.width, s.height) for s in media.video_sources] == [(720, 720)]
        assert media.video_sources[0].url.endswith(f"/{slug}-x4plus-720.mp4")
        preview = get_guide_media_preview(slug)
        assert preview["animation_url"] == media.url
        assert preview["video_sources"][0]["mime_type"] == "video/mp4"
