"""Regression checks for the fixed pilot video contract."""

import copy

import pytest
from scripts.ab_wheel_review_package import validate_probe


@pytest.fixture
def valid_probe():
    return {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "pix_fmt": "yuv420p",
                "width": 720,
                "height": 720,
                "avg_frame_rate": "30/1",
                "r_frame_rate": "30/1",
                "nb_frames": "120",
                "duration": "4.000000",
            }
        ],
        "frames": [{"best_effort_timestamp_time": f"{index / 30:.6f}"} for index in range(120)],
    }


def test_accepts_fixed_delivery_contract(valid_probe):
    assert validate_probe(valid_probe)["technical_status"] == "PASS"


@pytest.mark.parametrize(
    "field,value",
    [
        ("codec_name", "hevc"),
        ("pix_fmt", "yuv444p"),
        ("width", 1080),
        ("avg_frame_rate", "24/1"),
        ("nb_frames", "119"),
        ("duration", "4.1"),
    ],
)
def test_rejects_wrong_video_metadata(valid_probe, field, value):
    valid_probe["streams"][0][field] = value
    with pytest.raises(ValueError):
        validate_probe(valid_probe)


def test_rejects_audio_stream(valid_probe):
    valid_probe["streams"].append({"codec_type": "audio"})
    with pytest.raises(ValueError, match="no audio"):
        validate_probe(valid_probe)


@pytest.mark.parametrize("timestamp", ["0.000000", "nan", "inf", "0.1"])
def test_rejects_broken_frame_timeline(valid_probe, timestamp):
    valid_probe["frames"][1]["best_effort_timestamp_time"] = timestamp
    with pytest.raises(ValueError):
        validate_probe(valid_probe)


def test_missing_probe_data_fails_closed(valid_probe):
    broken = copy.deepcopy(valid_probe)
    del broken["streams"][0]["nb_frames"]
    with pytest.raises(ValueError, match="Missing or malformed"):
        validate_probe(broken)
