"""Skeletal constraints do not substitute for visible anatomy review."""

import math

import pytest
from scripts.ab_wheel_anatomical_pilot import (
    ELBOW,
    HIP,
    KNEE,
    SHOULDER,
    WRIST,
    Renderer,
    length,
    pose,
    solve_arm,
    sprite_transform,
    sub,
)


def test_entire_cycle_preserves_bone_lengths_ground_and_rolling():
    lengths = (
        ("knee", "hip", length(sub(HIP, KNEE))),
        ("hip", "shoulder", length(sub(SHOULDER, HIP))),
        ("shoulder", "elbow", length(sub(ELBOW, SHOULDER))),
        ("elbow", "wrist", length(sub(WRIST, ELBOW))),
    )
    for index in range(241):
        p = pose(index / 240)
        assert p["knee"] == KNEE
        assert p["wrist"][1] == WRIST[1]
        for a, b, expected in lengths:
            assert length(sub(p[a], p[b])) == pytest.approx(expected, abs=1e-8)
        assert p["wheel_angle"] * 82.5 == pytest.approx(p["wrist"][0] - WRIST[0])
    for name in ("hip", "shoulder", "elbow", "wrist"):
        assert pose(0)[name] == pytest.approx(pose(1)[name], abs=1e-8)
    assert pose(0)["wrist"] == pytest.approx(WRIST, abs=1e-8)
    assert pose(0.5)["wrist"][0] > pose(0)["wrist"][0] + 500


@pytest.mark.parametrize("phase", [math.nan, math.inf, -math.inf])
def test_invalid_phase_fails(phase):
    with pytest.raises(ValueError, match="finite"):
        pose(phase)


def test_unreachable_hand_is_rejected_instead_of_stretching():
    with pytest.raises(ValueError, match="Unreachable"):
        solve_arm((0, 0), (3, 0), 1, 1)


def test_sprite_transform_maps_both_pivots_without_shear():
    matrix = sprite_transform((10, 20), (10, 120), (100, 200), (300, 200))
    a, b, c, d, e, f = matrix
    assert (a * 100 + b * 200 + c, d * 100 + e * 200 + f) == pytest.approx((10, 20))
    assert (a * 300 + b * 200 + c, d * 300 + e * 200 + f) == pytest.approx((10, 120))
    assert a * b + d * e == pytest.approx(0)
    assert a * a + d * d == pytest.approx(b * b + e * e)


def test_changed_reference_stops_before_rendering(tmp_path):
    (tmp_path / "pose-01-start.png").write_bytes(b"untrusted replacement")
    with pytest.raises(ValueError, match="Original pose SHA mismatch"):
        Renderer(tmp_path, tmp_path / "absent-atlas.webp", {})
