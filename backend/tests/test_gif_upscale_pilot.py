"""Regression checks for the non-production animated GIF upscale pilot (#986)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/pilot_upscale_gymvisual_gifs.py"


def _module():
    spec = importlib.util.spec_from_file_location("gif_upscale_pilot", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_selected_sources_are_animation_gifs_with_valid_source_hash() -> None:
    module = _module()
    for slug in module.DEFAULT_SLUGS:
        path, frames, durations, loop = module.load_gif(slug)
        assert path.is_file()
        assert path.suffix == ".gif"
        assert len(frames) == len(durations) >= 2
        assert all(frame.size == (180, 180) for frame in frames)
        assert sum(durations) >= 2000
        assert all(duration > 0 for duration in durations)
        assert loop >= 0


def test_local_encoder_preserves_gif_timing_and_creates_real_video(tmp_path: Path) -> None:
    module = _module()
    frames = [
        Image.new("RGB", (32, 32), "#de3322"),
        Image.new("RGB", (32, 32), "#3288dd"),
    ]
    duration = [200, 300]
    video, webp, gif = module.encode(frames, duration, tmp_path, "synthetic-720")
    assert video.is_file() and video.stat().st_size > 400
    assert webp.is_file() and webp.stat().st_size > 100
    assert gif.is_file() and gif.stat().st_size > 100
    with Image.open(gif) as animation:
        assert animation.size == (360, 360)
        assert animation.n_frames == 2
        observed = []
        for index in range(animation.n_frames):
            animation.seek(index)
            observed.append(animation.info["duration"])
        assert observed == duration
    with Image.open(webp) as animation:
        assert animation.n_frames == 2
