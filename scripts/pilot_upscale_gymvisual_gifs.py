"""Reproducible non-production GIF upscaling comparison for issue #986.

This tool never updates manifest.json or application media. The provided
Real-ESRGAN ncnn executable and its models stay outside the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "backend/assets/exercise-guides"
MANIFEST = MEDIA / "manifest.json"
DEFAULT_SLUGS = (
    "machine-chest-press",
    "deadlift",
    "russian-twist",
    "walking-lunge",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_gif(slug: str) -> tuple[Path, list[Image.Image], list[int], int]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    item = manifest["exercises"][slug]
    if item["status"] != "approved" or len(item["media"]) != 1:
        raise ValueError(f"{slug}: no current animation")
    media = item["media"][0]
    if media["type"] != "animation" or not str(media["path"]).endswith(".gif"):
        raise ValueError(f"{slug}: source is not a GIF")
    path = MEDIA / media["path"]
    if sha256(path) != media["asset_sha256"]:
        raise ValueError(f"{slug}: input GIF checksum mismatch")
    with Image.open(path) as gif:
        frames = []
        durations = []
        for frame_index in range(gif.n_frames):
            gif.seek(frame_index)
            frames.append(gif.convert("RGBA").copy())
            durations.append(int(gif.info.get("duration") or 100))
        loop = int(gif.info.get("loop", 0))
    if any(frame.size != (180, 180) for frame in frames):
        raise ValueError(f"{slug}: unexpected source dimensions")
    return path, frames, durations, loop


def ffconcat_video(frames: list[Path], durations: list[int], output: Path) -> None:
    """Encode H.264, preserving original GIF per-frame timing via VFR concat."""
    concat = output.with_suffix(".ffconcat")
    rows = ["ffconcat version 1.0"]
    for path, duration in zip(frames, durations, strict=True):
        rows.append("file '" + path.as_posix().replace("'", "'\\''") + "'")
        rows.append(f"duration {duration / 1000:.6f}")
    rows.append("file '" + frames[-1].as_posix() + "'")
    concat.write_text("\n".join(rows) + "\n", encoding="utf-8")
    command = [
        get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-safe",
        "0",
        "-f",
        "concat",
        "-i",
        str(concat),
        "-fps_mode",
        "vfr",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    finally:
        concat.unlink(missing_ok=True)


def ai_frames(
    engine: Path, original_frames: list[Image.Image], folder: Path, model: str
) -> list[Image.Image]:
    source = folder / "input"
    target = folder / "ai"
    source.mkdir()
    target.mkdir()
    for i, frame in enumerate(original_frames):
        frame.save(source / f"{i:04d}.png")
    model_path = engine / "models"
    exe = engine / "realesrgan-ncnn-vulkan.exe"
    if not exe.is_file() or not model_path.is_dir():
        raise FileNotFoundError("Real-ESRGAN executable/models missing; provide --engine")
    cmd = [
        str(exe),
        "-i",
        str(source),
        "-o",
        str(target),
        "-m",
        str(model_path),
        "-n",
        model,
        "-s",
        "4",
        "-f",
        "png",
        "-g",
        "0",
    ]
    subprocess.run(cmd, check=True, cwd=engine, capture_output=True, text=True)
    result = []
    for i in range(len(original_frames)):
        png = target / f"{i:04d}.png"
        if not png.is_file():
            raise FileNotFoundError(f"AI did not produce {png}")
        with Image.open(png) as frame:
            if frame.size != (720, 720):
                raise ValueError(f"AI frame dimensions wrong: {frame.size}")
            result.append(frame.convert("RGB").copy())
    return result


def encode(
    frames: list[Image.Image], durations: list[int], root: Path, name: str, loop: int = 0
) -> tuple[Path, Path, Path]:
    video = root / f"{name}.mp4"
    webp = root / f"{name}.webp"
    gif_preview = root / f"{name.removesuffix('-720')}-360.gif"
    frames[0].save(
        webp,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=loop,
        format="WEBP",
        quality=84,
        method=5,
    )
    preview_frames = [
        frame.convert("RGB").resize((360, 360), Image.Resampling.LANCZOS) for frame in frames
    ]
    preview_frames[0].save(
        gif_preview,
        save_all=True,
        append_images=preview_frames[1:],
        duration=durations,
        loop=loop,
        optimize=True,
        disposal=2,
        format="GIF",
    )
    with tempfile.TemporaryDirectory(prefix="gif-mp4-") as temporary:
        frame_paths = []
        for i, frame in enumerate(frames):
            path = Path(temporary) / f"{i:04d}.png"
            frame.convert("RGB").save(path)
            frame_paths.append(path)
        ffconcat_video(frame_paths, durations, video)
    return video, webp, gif_preview


def contact_sheet(original: list[Image.Image], ai: list[Image.Image], output: Path) -> None:
    positions = [0, len(original) // 2, len(original) - 1]
    width = 1080
    canvas = Image.new("RGB", (width, 3 * 384), "#121822")
    draw = ImageDraw.Draw(canvas)
    for row, index in enumerate(positions):
        xoffset = row * 384
        old = original[index].convert("RGB").resize((360, 360), Image.Resampling.LANCZOS)
        new = ai[index].resize((360, 360), Image.Resampling.LANCZOS)
        # Three columns represent the same animation frame: 180→360 nearest, Lanczos, AI.
        nearest = original[index].convert("RGB").resize((360, 360), Image.Resampling.NEAREST)
        canvas.paste(nearest, (0, xoffset))
        canvas.paste(old, (360, xoffset))
        canvas.paste(new, (720, xoffset))
    draw.rectangle((0, 1120, 1079, 1151), fill="#121822")
    for x, label in (
        (3, "Original (nearest x2)"),
        (363, "Lanczos x2"),
        (723, "Real-ESRGAN x4 -> 360"),
    ):
        draw.text((x, 1125), label, fill="#ffffff")
    canvas.save(output, "JPEG", quality=90)


def run(slugs: list[str], engine: Path, output_dir: Path, *, model: str, label: str) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "method": f"{model} ncnn Vulkan (x4)",
        "source_resolution": [180, 180],
        "ai_resolution": [720, 720],
        "format": ["MP4 (H264)", "animated WebP", "GIF 360x360"],
        "samples": [],
    }
    for slug in slugs:
        path, frames, durations, loop = load_gif(slug)
        with tempfile.TemporaryDirectory(prefix=f"986-{slug}-") as tmp:
            ai = ai_frames(engine, frames, Path(tmp), model)
        lanczos = [
            frame.convert("RGB").resize((720, 720), Image.Resampling.LANCZOS) for frame in frames
        ]
        ai_video, ai_webp, ai_gif = encode(
            ai, durations, output_dir, f"{slug}-{label}-720", loop=loop
        )
        reference_video, reference_webp, reference_gif = encode(
            lanczos, durations, output_dir, f"{slug}-lanczos-720", loop=loop
        )
        sheet = output_dir / f"{slug}-{label}-comparison.jpg"
        contact_sheet(frames, ai, sheet)
        report["samples"].append(
            {
                "slug": slug,
                "input": path.relative_to(ROOT).as_posix(),
                "source_sha256": sha256(path),
                "frames": len(frames),
                "duration_ms": sum(durations),
                "loop": loop,
                "ai_mp4_bytes": ai_video.stat().st_size,
                "ai_webp_bytes": ai_webp.stat().st_size,
                "ai_gif_bytes": ai_gif.stat().st_size,
                "lanczos_mp4_bytes": reference_video.stat().st_size,
                "lanczos_webp_bytes": reference_webp.stat().st_size,
                "lanczos_gif_bytes": reference_gif.stat().st_size,
                "comparison": sheet.name,
            }
        )
        print(
            f"{slug}: {len(frames)} frames, {sum(durations)}ms, "
            f"MP4 AI={ai_video.stat().st_size} B, Lanczos={reference_video.stat().st_size} B",
            flush=True,
        )
    (output_dir / f"results-{label}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine",
        required=True,
        type=Path,
        help="Untracked Real-ESRGAN ncnn directory containing exe and models/",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs/exercises/catalog-v2/evidence/986-gif-upscale-pilot",
    )
    parser.add_argument("--slugs", nargs="+", default=list(DEFAULT_SLUGS))
    parser.add_argument(
        "--model",
        default="realesr-animevideov3",
        choices=["realesr-animevideov3", "realesrgan-x4plus"],
    )
    parser.add_argument("--label", default="ai")
    args = parser.parse_args()
    run(args.slugs, args.engine, args.output, model=args.model, label=args.label)


if __name__ == "__main__":
    main()
