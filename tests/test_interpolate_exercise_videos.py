from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.interpolate_exercise_videos import (
    InterpolationError,
    SourceFrame,
    _copy_or_refuse,
    build_frame_plan,
    model_fingerprint,
    resolve_source,
    target_times,
    timestep_argument,
)


def test_target_times_keep_the_last_partial_interval_without_looping() -> None:
    times = target_times(2100, 8)

    assert len(times) == 17
    assert times[0] == 0
    assert times[-1] == 2
    assert 2.1 - times[-1] == pytest.approx(0.1)


def test_target_times_round_duration_to_the_nearest_cfr_frame() -> None:
    assert len(target_times(2100, 12)) == 25
    assert target_times(2100, 12)[-1] == pytest.approx(2.0)


def test_frame_plan_uses_real_anchors_and_never_wraps_the_cycle() -> None:
    frames = [
        SourceFrame(index=index, timestamp=timestamp, path=Path(f"frame-{index}.png"))
        for index, timestamp in enumerate((0.0, 1.0, 1.1, 1.2, 2.0))
    ]

    plan = build_frame_plan(frames, 3000, 8)

    assert any(item.kind == "rife" for item in plan)
    assert any(item.kind == "anchor" and item.source_index == 1 for item in plan)
    assert all(not (item.left_index == 4 and item.right_index == 0) for item in plan)
    assert plan[-1].kind == "anchor"
    assert plan[-1].source_index == 4


def test_windows_rife_argument_uses_active_crt_decimal_separator() -> None:
    assert timestep_argument(1 / 3, windows=True) == "0,333333"
    assert timestep_argument(0.5, windows=False) == "0.5"


def test_resolve_source_rejects_native_hd_and_unknown_canonical_ids(tmp_path: Path) -> None:
    gif = tmp_path / "gymvisual" / "demo.gif"
    video = tmp_path / "gymvisual" / "demo.mp4"
    gif.parent.mkdir()
    gif.write_bytes(b"gif-source")
    video.write_bytes(b"mp4-source")
    gif_sha = hashlib.sha256(gif.read_bytes()).hexdigest()
    video_sha = hashlib.sha256(video.read_bytes()).hexdigest()
    media = {
        "type": "animation",
        "path": "gymvisual/demo.gif",
        "asset_sha256": gif_sha,
        "frame_count": 2,
        "duration_ms": 1000,
        "video_sources": [
            {"path": "gymvisual/demo.mp4", "width": 720, "height": 720, "sha256": video_sha}
        ],
        "video_provenance": {
            "source_kind": "ai_upscaled_gymvisual",
            "source_sha256": gif_sha,
            "source_animation_frames": 2,
            "source_animation_duration_ms": 1000,
        },
    }
    manifest = {"exercises": {"demo": {"status": "approved", "media": [media]}}}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert resolve_source(manifest_path, tmp_path, "demo").source_video_sha256 == video_sha
    with pytest.raises(InterpolationError, match="native HD"):
        media["video_provenance"]["source_kind"] = "native_hd"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        resolve_source(manifest_path, tmp_path, "demo")
    with pytest.raises(InterpolationError, match="Unknown canonical exercise ID"):
        resolve_source(manifest_path, tmp_path, "missing")


def test_model_fingerprint_requires_arbitrary_timestep_model(tmp_path: Path) -> None:
    wrong = tmp_path / "rife-v3"
    wrong.mkdir()
    (wrong / "flownet.bin").write_bytes(b"model")
    with pytest.raises(InterpolationError, match="rife-v4"):
        model_fingerprint(wrong)

    right = tmp_path / "rife-v4"
    right.mkdir()
    (right / "flownet.bin").write_bytes(b"model")
    fingerprint = model_fingerprint(right)
    assert fingerprint["name"] == "rife-v4"
    assert fingerprint["files"][0]["sha256"] == hashlib.sha256(b"model").hexdigest()


def test_artifact_copy_is_idempotent_but_never_overwrites_different_data(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    target = tmp_path / "target.bin"
    source.write_bytes(b"source")
    _copy_or_refuse(source, target)
    _copy_or_refuse(source, target)

    target.write_bytes(b"tampered")
    with pytest.raises(InterpolationError, match="Refusing to overwrite"):
        _copy_or_refuse(source, target)
