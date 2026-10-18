from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from scripts.motion_first_pilot import (
    CROSSFADE_SOURCE,
    MOTION_SOURCE_REVIEW,
    MOTION_SOURCE_VERIFIED,
    SOURCE_REJECTED,
    STATIC_POSE_SEQUENCE,
    build_gallery,
    classify_source,
    plan_processing,
    validate_cycle,
    validate_output_metadata,
    validate_provenance,
    validate_pts,
)


def candidate(slug: str = "kettlebell-swing") -> dict:
    return {
        "canonical_slug": slug,
        "source_url": "https://example.test/source",
        "source_revision": "retrieved-2026-10-18",
        "source_sha256": "a" * 64,
        "rights": {
            "commercial_use_verified": True,
            "redistribution_verified": True,
        },
        "motion_continuity": True,
        "ghosting": False,
        "technique_qc": "pass",
        "output_file": f"{slug}.mp4",
    }


def test_source_classification_is_conservative() -> None:
    assert classify_source(candidate()) == MOTION_SOURCE_VERIFIED
    assert classify_source({**candidate(), "static_pose_sequence": True}) == STATIC_POSE_SEQUENCE
    assert classify_source({**candidate(), "crossfade": True}) == CROSSFADE_SOURCE
    assert classify_source({**candidate(), "ghosting": None}) == MOTION_SOURCE_REVIEW
    assert classify_source({**candidate(), "explicit_rejection": True}) == SOURCE_REJECTED
    assert classify_source({**candidate(), "canonical_slug": "similar-exercise"}) == SOURCE_REJECTED


def test_provenance_requires_exact_sha_and_rights() -> None:
    validate_provenance(candidate())
    with pytest.raises(ValueError, match="SHA-256"):
        validate_provenance({**candidate(), "source_sha256": "unknown"})
    with pytest.raises(ValueError, match="redistribution"):
        validate_provenance(
            {
                **candidate(),
                "rights": {"commercial_use_verified": True, "redistribution_verified": None},
            }
        )


def test_processing_scope_resume_and_no_overwrite(tmp_path: Path) -> None:
    records = [candidate(slug) for slug in ("ab-wheel", "kettlebell-swing", "romanian-deadlift")]
    plan = plan_processing(records, tmp_path)
    assert {item["state"] for item in plan} == {"new"}

    output = tmp_path / "kettlebell-swing.mp4"
    output.write_bytes(b"existing")
    with pytest.raises(FileExistsError, match="overwrite"):
        plan_processing(records, tmp_path)

    resumed = [
        {
            **item,
            "output_sha256": hashlib.sha256(b"existing").hexdigest(),
        }
        if item["canonical_slug"] == "kettlebell-swing"
        else item
        for item in records
    ]
    plan = plan_processing(resumed, tmp_path)
    assert (
        next(item for item in plan if item["canonical_slug"] == "kettlebell-swing")["state"]
        == "resume"
    )

    for blocked in ({"explicit_rejection": True}, {"owner_visual_status": "pending"}):
        blocked_records = [
            {**item, **blocked} if item["canonical_slug"] == "kettlebell-swing" else item
            for item in records
        ]
        with pytest.raises(ValueError, match="blocked"):
            plan_processing(blocked_records, tmp_path)


def test_pts_cycle_and_output_contract() -> None:
    validate_pts([0, 1, 2, 3])
    with pytest.raises(ValueError, match="timestamps"):
        validate_pts([0, 1, 1])
    validate_cycle([0, 10, 20], [1, 9, 19], 2)
    with pytest.raises(ValueError, match="seam"):
        validate_cycle([0, 0], [20, 20], 2)
    validate_output_metadata(
        {
            "width": 720,
            "height": 720,
            "fps": 25,
            "codec": "h264",
            "pix_fmt": "yuv420p",
            "has_audio": False,
            "duration_sec": 4.0,
            "frames": 100,
            "decode_ok": True,
            "pts_monotonic": True,
            "cycle_seam_pass": True,
        }
    )
    with pytest.raises(ValueError, match="audio"):
        validate_output_metadata(
            {
                "width": 720,
                "height": 720,
                "fps": 25,
                "codec": "h264",
                "pix_fmt": "yuv420p",
                "has_audio": True,
                "duration_sec": 4.0,
                "frames": 100,
                "decode_ok": True,
                "pts_monotonic": True,
                "cycle_seam_pass": True,
            }
        )


def test_gallery_escapes_labels_and_keeps_media_local(tmp_path: Path) -> None:
    output = tmp_path / "gallery.html"
    build_gallery(
        [
            {
                "canonical_slug": "kettlebell-swing",
                "source_status": MOTION_SOURCE_REVIEW,
                "media": [{"kind": "image", "label": "<unsafe>", "path": "image.jpg"}],
            }
        ],
        output,
    )
    rendered = output.read_text(encoding="utf-8")
    assert "&lt;unsafe&gt;" in rendered
    assert "<unsafe>" not in rendered
