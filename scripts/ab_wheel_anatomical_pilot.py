"""Render one layered anatomical character, never interpolated independent poses."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import time
from pathlib import Path

REFERENCE_SHA = "36b689ebab402f65f60a60b1f15240cb60b4feaa"
START_SHA = "62ff6ac8c60d1535e008763641c78f53772150ebd1fff990df7c90166aabb18a"
STORYBOARD_SHA = "8acb7e7a4901bf8d747db602d5c008ca2ba2219af8b428c290e1481dcd6abd5c"
Point = tuple[float, float]
KNEE = (550.0, 972.0)
HIP = (488.0, 667.0)
SHOULDER = (812.0, 483.0)
ELBOW = (862.0, 719.0)
WRIST = (956.0, 951.0)
FPS, FRAMES = 30, 120


def add(a: Point, b: Point) -> Point:
    return a[0] + b[0], a[1] + b[1]


def sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1]


def length(v: Point) -> float:
    return math.hypot(*v)


def rotate(v: Point, angle: float) -> Point:
    c, s = math.cos(angle), math.sin(angle)
    return c * v[0] - s * v[1], s * v[0] + c * v[1]


def solve_arm(shoulder: Point, wrist: Point, upper: float, fore: float) -> Point:
    delta = sub(wrist, shoulder)
    distance = length(delta)
    if not abs(upper - fore) < distance <= upper + fore:
        raise ValueError("Unreachable wrist; do not stretch bones")
    cosine = (upper * upper + distance * distance - fore * fore) / (2 * upper * distance)
    angle = math.atan2(delta[1], delta[0]) + math.acos(max(-1.0, min(1.0, cosine)))
    return add(shoulder, (upper * math.cos(angle), upper * math.sin(angle)))


def pose(phase: float) -> dict[str, Point | float]:
    if not math.isfinite(phase):
        raise ValueError("Phase must be finite")
    u = (1 - math.cos(2 * math.pi * phase)) / 2
    hip = add(KNEE, rotate(sub(HIP, KNEE), math.radians(58) * u))
    shoulder = add(hip, rotate(sub(SHOULDER, HIP), math.radians(17) * u))
    upper, fore = length(sub(ELBOW, SHOULDER)), length(sub(WRIST, ELBOW))
    a, b = sub(ELBOW, SHOULDER), sub(WRIST, ELBOW)
    initial_bend = math.acos((a[0] * b[0] + a[1] * b[1]) / (upper * fore))
    bend = initial_bend * (1 - u) + math.radians(3) * u
    reach = math.sqrt(upper**2 + fore**2 + 2 * upper * fore * math.cos(bend))
    dy = WRIST[1] - shoulder[1]
    if reach < abs(dy):
        raise ValueError("Roller plane is unreachable")
    wrist = (shoulder[0] + math.sqrt(reach**2 - dy**2), WRIST[1])
    elbow = solve_arm(shoulder, wrist, upper, fore)
    return {
        "knee": KNEE,
        "hip": hip,
        "shoulder": shoulder,
        "elbow": elbow,
        "wrist": wrist,
        "wheel_angle": (wrist[0] - WRIST[0]) / 82.5,
        "trunk_angle": math.radians(17) * u,
    }


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sprite_transform(source_a: Point, source_b: Point, target_a: Point, target_b: Point):
    """Inverse similarity transform: one scale and rotation, no shear or morph."""
    sv, tv = sub(source_b, source_a), sub(target_b, target_a)
    if not length(sv) or not length(tv):
        raise ValueError("A sprite bone must have nonzero length")
    angle = math.atan2(tv[1], tv[0]) - math.atan2(sv[1], sv[0])
    scale = length(tv) / length(sv)
    c, s = math.cos(angle) / scale, math.sin(angle) / scale
    return (
        c,
        s,
        source_a[0] - c * target_a[0] - s * target_a[1],
        -s,
        c,
        source_a[1] + s * target_a[0] - c * target_a[1],
    )


class Renderer:
    def __init__(self, reference: Path, atlas: Path, config: dict):
        from PIL import Image, ImageChops, ImageDraw, ImageFilter

        if digest(reference / "pose-01-start.png") != START_SHA:
            raise ValueError("Original pose SHA mismatch")
        if digest(reference / "approved-storyboard.png") != STORYBOARD_SHA:
            raise ValueError("Approved storyboard SHA mismatch")
        if digest(atlas) != config["atlas_sha256"]:
            raise ValueError("Atlas SHA mismatch")
        self.config = config
        self.parts = {}
        sources = {
            "atlas": Image.open(atlas).convert("RGBA"),
            "original": Image.open(reference / "pose-01-start.png").convert("RGBA"),
        }
        for name, item in config["parts"].items():
            image = sources[item["source"]].copy()
            mask = Image.new("L", image.size)
            ImageDraw.Draw(mask).polygon([tuple(v) for v in item["polygon"]], fill=255)
            image.putalpha(ImageChops.multiply(image.getchannel("A"), mask))
            if item["source"] == "atlas":
                # Adjacent disconnected atlas pieces must not bleed into a crop.
                connected = image.getchannel("A").point(lambda a: 255 if a > 128 else 0)
                if connected.getpixel(tuple(item["a"])) != 255:
                    raise ValueError(f"Atlas pivot is outside foreground: {name}")
                ImageDraw.floodfill(connected, tuple(item["a"]), 128)
                connected = connected.point(lambda a: 255 if a == 128 else 0)
                connected = connected.filter(ImageFilter.MaxFilter(3))
                image.putalpha(ImageChops.multiply(image.getchannel("A"), connected))
            self.parts[name] = image

    def project(self, p: Point) -> Point:
        # Render at 2x then downsample once; camera and scale never change.
        return (p[0] * 0.8 + 44, p[1] * 0.8 + 190)

    def part(self, canvas, name: str, a: Point, b: Point):
        from PIL import Image

        config = self.config["parts"][name]
        matrix = sprite_transform(
            tuple(config["a"]), tuple(config["b"]), self.project(a), self.project(b)
        )
        layer = self.parts[name].transform(
            canvas.size, Image.Transform.AFFINE, matrix, resample=Image.Resampling.BICUBIC
        )
        canvas.alpha_composite(layer)

    def frame(self, phase: float):
        from PIL import Image, ImageDraw, ImageFilter

        p = pose(phase)
        hip, shoulder, elbow, wrist = (p[k] for k in ("hip", "shoulder", "elbow", "wrist"))
        canvas = Image.new("RGBA", (1440, 1440), "white")
        shadow = Image.new("RGBA", canvas.size)
        d = ImageDraw.Draw(shadow)
        cx, cy = self.project(wrist)
        floor = self.project((0, 1033.5))[1]
        d.ellipse((95, floor - 5, 520, floor + 10), fill=(80, 80, 80, 28))
        d.ellipse((cx - 95, floor - 3, cx + 100, floor + 11), fill=(80, 80, 80, 30))
        canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(8)))
        self.part(canvas, "lower_legs", KNEE, (190.0, 930.0))
        self.part(canvas, "torso", hip, shoulder)
        self.part(canvas, "thigh", hip, KNEE)
        neck = add(shoulder, rotate((103.0, -76.0), p["trunk_angle"]))
        head_tip = add(neck, rotate((100.0, 0.0), p["trunk_angle"]))
        self.part(canvas, "head", neck, head_tip)
        # Far arm uses the same anatomy, with fixed depth offset; never an extra limb.
        offset = (15.0, -7.0)
        self.part(canvas, "upper_arm", add(shoulder, offset), add(elbow, offset))
        self.part(canvas, "forearm", add(elbow, offset), add(wrist, offset))
        d = ImageDraw.Draw(canvas)
        radius = 66
        for off in (23, 0):
            x = cx + off
            d.ellipse(
                (x - radius, cy - radius, x + radius, cy + radius),
                fill="#1b1b1c",
                outline="#090909",
                width=3,
            )
            d.ellipse(
                (x - 56, cy - 56, x + 56, cy + 56), fill="#ccccce", outline="#666666", width=3
            )
            d.ellipse((x - 49, cy - 49, x + 49, cy + 49), outline="#999999", width=2)
            for spoke in range(6):
                angle = spoke * math.pi / 3 + p["wheel_angle"]
                d.line(
                    (x, cy, x + 51 * math.cos(angle), cy + 51 * math.sin(angle)),
                    fill="#777779",
                    width=4,
                )
            d.ellipse((x - 10, cy - 10, x + 10, cy + 10), fill="#222222")
        self.part(canvas, "upper_arm", shoulder, elbow)
        self.part(canvas, "forearm", elbow, wrist)
        return canvas.convert("RGB").resize((720, 720), Image.Resampling.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--atlas", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--style-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    renderer = Renderer(args.references, args.atlas, config)
    for name, phase in (("start", 0), ("middle", 0.25), ("extended", 0.5)):
        renderer.frame(phase).save(args.output / f"style-{name}.png")
    if args.style_only:
        return
    started = time.monotonic()
    frames = args.output / "frames"
    frames.mkdir(exist_ok=True)
    for frame in range(FRAMES):
        renderer.frame(frame / FRAMES).save(frames / f"frame-{frame:04d}.png")
    subprocess.run(
        [
            str(args.ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(frames / "frame-%04d.png"),
            "-c:v",
            "libx264",
            "-crf",
            "17",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-movflags",
            "+faststart",
            str(args.output / "candidate.mp4"),
        ],
        check=True,
    )
    from PIL import __version__ as pillow_version

    from ab_wheel_review_package import build_package

    metadata = {
        "pipeline": "rigid_anatomical_cutout_v1",
        "python": platform.python_version(),
        "Pillow": pillow_version,
        "reference_commit": REFERENCE_SHA,
        "atlas_sha256": digest(args.atlas),
        # Git stores LF; normalize Windows checkout newlines before recording provenance.
        "config_sha256": hashlib.sha256(
            args.config.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest(),
        "config_sha256_encoding": "UTF-8 LF",
        "generation_seconds": time.monotonic() - started,
        "renderer": "Pillow CPU, 2x supersampled rigid sprites; no optical flow/crossfade",
        "gpu": "RTX 4060 Ti 8 GiB detected; not used by local renderer",
        "style_fidelity": "NEEDS_WORK",
        "technique_qc": "TECHNIQUE_REVIEW",
        "owner_visual_acceptance": "PENDING",
        "final_verdict": "NEEDS_WORK",
    }
    build_package(args.output, args.references, args.baseline, args.ffmpeg, args.ffprobe, metadata)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
