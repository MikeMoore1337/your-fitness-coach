"""Regression guards for owner-approved bulk AI animation rollout (#986)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from scripts import import_ai_upscaled_exercise_gifs as batch


def fixture_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, Path]:
    assets = tmp_path / "media"
    assets.mkdir()
    gif = assets / "gymvisual" / "ab-wheel.gif"
    gif.parent.mkdir()
    gif.write_bytes(b"GIF89a-original-canonical-animation-12-frames")
    source_hash = hashlib.sha256(gif.read_bytes()).hexdigest()
    media = {
        "type": "animation",
        "path": "gymvisual/ab-wheel.gif",
        "asset_sha256": source_hash,
        "asset_id": "gymvisual:ab-wheel",
        "width": 180,
        "height": 180,
        "frame_count": 12,
        "duration_ms": 3000,
    }
    manifest = {
        "exercises": {
            "ab-wheel": {
                "status": "approved",
                "source": {"rights_basis": "owner_purchased_gymvisual_license"},
                "media": [media],
            },
            "already-hd": {
                "status": "approved",
                "source": {"rights_basis": "owner_purchased_gymvisual_license"},
                "media": [
                    {
                        "type": "animation",
                        "width": 180,
                        "height": 180,
                        "video_sources": [{"path": "verified.mp4"}],
                    }
                ],
            },
            "blocked": {"status": "blocked", "media": []},
        },
        "asset_count": 10,
        "total_bytes": 2000,
        "ai_upscaled_video_count": 0,
        "ai_upscaled_video_total_bytes": 0,
    }
    monkeypatch.setattr(batch, "MEDIA_ROOT", assets)
    monkeypatch.setattr(batch, "MANIFEST_PATH", assets / "manifest.json")
    return manifest, gif


def make_report(directory: Path, manifest: dict, *, model: str = "realesrgan-x4plus") -> bytes:
    directory.mkdir(parents=True, exist_ok=True)
    payload = b"\x00\x00\x00\x18ftyp" + (b"animated-source-h264" * 80)
    (directory / "ab-wheel-general-720.mp4").write_bytes(payload)
    media = manifest["exercises"]["ab-wheel"]["media"][0]
    report = {
        "method": f"{model} ncnn Vulkan (x4)",
        "source_resolution": [180, 180],
        "ai_resolution": [720, 720],
        "samples": [
            {
                "slug": "ab-wheel",
                "input": "backend/assets/exercise-guides/gymvisual/ab-wheel.gif",
                "source_sha256": media["asset_sha256"],
                "frames": 12,
                "duration_ms": 3000,
                "ai_mp4_bytes": len(payload),
                "ai_mp4_sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
    }
    (directory / "results-general.json").write_text(json.dumps(report), encoding="utf-8")
    return payload


def test_plan_excludes_existing_native_and_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, _gif = fixture_manifest(tmp_path, monkeypatch)
    assert list(batch.pending_exercises(manifest)) == ["ab-wheel"]


def test_rollout_requires_model_source_identity_and_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, gif = fixture_manifest(tmp_path, monkeypatch)
    output = tmp_path / "processed"
    data = make_report(output, manifest)
    monkeypatch.setattr(batch, "inspect_h264", lambda *args, **kwargs: None)

    verified = batch.make_derivatives(manifest, source_dir=output, slugs=["ab-wheel"])
    assert len(verified) == 1
    batch.apply(manifest, verified)
    fresh = json.loads(batch.MANIFEST_PATH.read_text(encoding="utf-8"))
    media = fresh["exercises"]["ab-wheel"]["media"][0]
    assert media["video_provenance"]["native_hd"] is False
    assert media["video_provenance"]["model"] == "RealESRGAN_x4plus"
    assert media["video_provenance"]["owner_visual_approval"] == batch.BULK_APPROVAL
    assert media["video_sources"][0]["sha256"] == hashlib.sha256(data).hexdigest()
    assert fresh["ai_upscaled_video_count"] == 1
    assert fresh["asset_count"] == 11
    assert fresh["total_bytes"] == 2000 + len(data)
    assert gif.read_bytes() == b"GIF89a-original-canonical-animation-12-frames"
    with pytest.raises(ValueError, match="Non-pending"):
        batch.make_derivatives(manifest, source_dir=output, slugs=["already-hd"])
    with pytest.raises(FileExistsError):
        batch.apply(manifest, verified)


def test_rollout_rejects_wrong_model_tampering_and_duplicate_slugs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, gif = fixture_manifest(tmp_path, monkeypatch)
    directory = tmp_path / "processed"
    make_report(directory, manifest, model="realesr-animevideov3")
    monkeypatch.setattr(batch, "inspect_h264", lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match="approved Real-ESRGAN"):
        batch.make_derivatives(manifest, source_dir=directory, slugs=["ab-wheel"])
    make_report(directory, manifest)
    with pytest.raises(ValueError, match="distinct"):
        batch.make_derivatives(manifest, source_dir=directory, slugs=["ab-wheel", "ab-wheel"])
    gif.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="GIF identity"):
        batch.make_derivatives(manifest, source_dir=directory, slugs=["ab-wheel"])


def test_ffprobe_gate_rejects_static_audio_and_wrong_codec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"invalid-bytes")
    stream = {
        "codec_type": "video",
        "codec_name": "h264",
        "pix_fmt": "yuv420p",
        "width": 720,
        "height": 720,
        "nb_read_frames": "12",
    }

    def mock_probe(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"streams": [stream], "format": {"duration": "3.25"}}),
            stderr="",
        )

    monkeypatch.setattr(batch.subprocess, "run", mock_probe)
    batch.inspect_h264(video, ffprobe="ffprobe", original_duration_ms=3000)
    stream["nb_read_frames"] = "1"
    with pytest.raises(ValueError, match="no animated movement"):
        batch.inspect_h264(video, ffprobe="ffprobe", original_duration_ms=3000)
    stream["nb_read_frames"] = "12"
    stream["codec_name"] = "hevc"
    with pytest.raises(ValueError, match=r"Not H\.264"):
        batch.inspect_h264(video, ffprobe="ffprobe", original_duration_ms=3000)
