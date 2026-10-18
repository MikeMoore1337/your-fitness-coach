"""Run a reproducible, non-production RIFE frame-interpolation pilot.

The tool consumes an approved AI-upscaled MP4 described by a manifest, keeps
the original GIF/MP4 untouched, and writes all generated material to an
explicit artifact directory.  It uses the portable RIFE ncnn Vulkan CLI one
pair at a time so variable-duration source frames keep their real timestamps.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageStat

ROOT = Path(__file__).resolve().parents[1]
PILOT_SLUGS = (
    "ab-wheel",
    "leg-press",
    "romanian-deadlift",
    "kettlebell-swing",
    "treadmill-walk",
    "assault-bike",
    "turkish-get-up",
    "dragon-flag",
)
TARGET_FPS = (8, 12, 16)
SCHEMA_VERSION = 1
TIMESTAMP_EPSILON = 1e-6


class InterpolationError(ValueError):
    """Raised when a source, model, output or resume record is unsafe."""


@dataclass(frozen=True)
class SourceSpec:
    slug: str
    source_video: Path
    source_video_sha256: str
    source_gif: Path
    source_gif_sha256: str
    duration_ms: int
    source_frame_count: int
    loop: int


@dataclass(frozen=True)
class SourceFrame:
    index: int
    timestamp: float
    path: Path


@dataclass(frozen=True)
class FramePlan:
    index: int
    timestamp: float
    kind: str
    source_index: int | None = None
    left_index: int | None = None
    right_index: int | None = None
    timestep: float | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_fraction(value: str | None) -> float | None:
    if not value or value in {"N/A", "0/0"}:
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        if float(denominator) == 0:
            return None
        return float(numerator) / float(denominator)
    return float(value)


def ffprobe_json(ffprobe: Path, path: Path, *, frames: bool = False) -> dict[str, Any]:
    entries = "frame=best_effort_timestamp_time,pts_time,pkt_duration_time,pict_type"
    if frames:
        command = [
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_frames",
            "-show_entries",
            entries,
            "-of",
            "json",
            str(path),
        ]
    else:
        command = [
            str(ffprobe),
            "-v",
            "error",
            "-count_frames",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise InterpolationError(f"ffprobe failed for {path.name}: {result.stderr.strip()[-1000:]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InterpolationError(f"ffprobe returned invalid JSON for {path.name}") from exc


def frame_timestamps(ffprobe: Path, path: Path) -> list[float]:
    payload = ffprobe_json(ffprobe, path, frames=True)
    timestamps: list[float] = []
    for item in payload.get("frames", []):
        timestamp = parse_fraction(item.get("best_effort_timestamp_time"))
        if timestamp is None:
            timestamp = parse_fraction(item.get("pts_time"))
        if timestamp is None:
            raise InterpolationError(f"Missing frame PTS in {path.name}")
        if timestamps and timestamp + TIMESTAMP_EPSILON < timestamps[-1]:
            raise InterpolationError(f"Non-monotonic source PTS in {path.name}")
        timestamps.append(timestamp)
    if not timestamps or abs(timestamps[0]) > 0.01:
        raise InterpolationError(f"Source PTS must start at zero: {path.name}")
    return timestamps


def _media_entry(manifest: dict[str, Any], slug: str) -> tuple[dict[str, Any], dict[str, Any]]:
    entry = manifest.get("exercises", {}).get(slug)
    if not isinstance(entry, dict):
        raise InterpolationError(f"Unknown canonical exercise ID: {slug}")
    media = entry.get("media")
    if not isinstance(media, list) or len(media) != 1 or not isinstance(media[0], dict):
        raise InterpolationError(f"{slug}: expected one canonical media record")
    return entry, media[0]


def resolve_source(manifest_path: Path, source_root: Path, slug: str) -> SourceSpec:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry, media = _media_entry(manifest, slug)
    provenance = media.get("video_provenance") or {}
    if entry.get("status") != "approved":
        raise InterpolationError(f"{slug}: source exercise is not approved")
    if media.get("type") != "animation" or not str(media.get("path", "")).endswith(".gif"):
        raise InterpolationError(f"{slug}: source GIF fallback is missing")
    if provenance.get("source_kind") != "ai_upscaled_gymvisual":
        raise InterpolationError(f"{slug}: native HD or unknown media is excluded from the pilot")
    sources = media.get("video_sources")
    if not isinstance(sources, list) or len(sources) != 1 or not isinstance(sources[0], dict):
        raise InterpolationError(f"{slug}: expected exactly one AI-upscaled MP4")
    video = sources[0]
    if (video.get("width"), video.get("height")) != (720, 720):
        raise InterpolationError(f"{slug}: AI source must be 720x720")
    source_video = source_root / str(video["path"])
    source_gif = source_root / str(media["path"])
    if not source_video.is_file() or not source_gif.is_file():
        raise InterpolationError(f"{slug}: manifest source files are unavailable")
    source_video_sha256 = sha256_file(source_video)
    source_gif_sha256 = sha256_file(source_gif)
    if source_video_sha256 != video.get("sha256"):
        raise InterpolationError(f"{slug}: AI source MP4 SHA-256 mismatch")
    if source_gif_sha256 != media.get("asset_sha256"):
        raise InterpolationError(f"{slug}: original GIF SHA-256 mismatch")
    if provenance.get("source_sha256") != source_gif_sha256:
        raise InterpolationError(f"{slug}: provenance does not point to the original GIF")
    duration_ms = int(
        provenance.get("source_animation_duration_ms") or media.get("duration_ms") or 0
    )
    source_frame_count = int(
        provenance.get("source_animation_frames") or media.get("frame_count") or 0
    )
    if duration_ms <= 0 or source_frame_count < 2:
        raise InterpolationError(f"{slug}: invalid source duration/frame count")
    return SourceSpec(
        slug=slug,
        source_video=source_video,
        source_video_sha256=source_video_sha256,
        source_gif=source_gif,
        source_gif_sha256=source_gif_sha256,
        duration_ms=duration_ms,
        source_frame_count=source_frame_count,
        loop=int(media.get("loop") or 0),
    )


def inspect_source(ffprobe: Path, spec: SourceSpec) -> dict[str, Any]:
    payload = ffprobe_json(ffprobe, spec.source_video)
    streams = payload.get("streams") or []
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    if len(streams) != 1 or len(video_streams) != 1:
        raise InterpolationError(
            f"{spec.slug}: source must contain exactly one video stream and no audio"
        )
    stream = video_streams[0]
    if (stream.get("codec_name"), stream.get("width"), stream.get("height")) != (
        "h264",
        720,
        720,
    ):
        raise InterpolationError(f"{spec.slug}: source is not H.264 720x720")
    frames = int(stream.get("nb_read_frames") or 0)
    duration = float((payload.get("format") or {}).get("duration") or 0)
    return {
        "codec": stream.get("codec_name"),
        "pix_fmt": stream.get("pix_fmt"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "encoded_frames": frames,
        "encoded_duration_s": duration,
        "avg_frame_rate": stream.get("avg_frame_rate"),
        "r_frame_rate": stream.get("r_frame_rate"),
        "time_base": stream.get("time_base"),
    }


def extract_source_frames(
    ffmpeg: Path, ffprobe: Path, spec: SourceSpec, destination: Path
) -> list[SourceFrame]:
    metadata_path = destination / "source-frames.json"
    source_signature = {
        "source_sha256": spec.source_video_sha256,
        "duration_ms": spec.duration_ms,
        "source_frame_count": spec.source_frame_count,
    }
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("signature") != source_signature:
            raise InterpolationError(f"{spec.slug}: refusing to reuse mismatched extracted frames")
        paths = [destination / item["file"] for item in metadata.get("frames", [])]
        if not paths or any(not path.is_file() for path in paths):
            raise InterpolationError(f"{spec.slug}: extracted frame set is incomplete")
        return [
            SourceFrame(
                index=item["index"], timestamp=item["timestamp"], path=destination / item["file"]
            )
            for item in metadata["frames"]
        ]
    existing = list(destination.glob("frame-*.png")) if destination.exists() else []
    if existing:
        raise InterpolationError(
            f"{spec.slug}: untracked extracted frames found; refusing overwrite"
        )
    destination.mkdir(parents=True, exist_ok=True)
    timestamps = frame_timestamps(ffprobe, spec.source_video)
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(spec.source_video),
        "-map",
        "0:v:0",
        "-fps_mode",
        "passthrough",
        "-start_number",
        "0",
        str(destination / "frame-%06d.png"),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise InterpolationError(f"ffmpeg frame extraction failed: {result.stderr.strip()[-1000:]}")
    extracted = sorted(destination.glob("frame-*.png"))
    if len(extracted) != len(timestamps):
        raise InterpolationError(
            f"{spec.slug}: extracted {len(extracted)} frames but ffprobe reported {len(timestamps)}"
        )
    duration_s = spec.duration_ms / 1000
    valid = [
        (index, timestamp, path)
        for index, (timestamp, path) in enumerate(zip(timestamps, extracted, strict=True))
        if timestamp < duration_s - TIMESTAMP_EPSILON
    ]
    if len(valid) != spec.source_frame_count:
        raise InterpolationError(
            f"{spec.slug}: {len(valid)} source frames before duration, expected {spec.source_frame_count}"
        )
    frames = [
        SourceFrame(index=index, timestamp=timestamp, path=path) for index, timestamp, path in valid
    ]
    write_json_atomic(
        metadata_path,
        {
            "signature": source_signature,
            "frames": [
                {"index": frame.index, "timestamp": frame.timestamp, "file": frame.path.name}
                for frame in frames
            ],
        },
    )
    return frames


def target_times(duration_ms: int, fps: int) -> list[float]:
    if fps not in TARGET_FPS:
        raise InterpolationError(f"Unsupported target FPS: {fps}")
    total = Fraction(duration_ms, 1000)
    count = max(2, math.floor(float(total * fps) + 0.5))
    return [float(Fraction(index, fps)) for index in range(count)]


def build_frame_plan(frames: Sequence[SourceFrame], duration_ms: int, fps: int) -> list[FramePlan]:
    if not frames:
        raise InterpolationError("Cannot build a plan without source frames")
    duration_s = duration_ms / 1000
    plan: list[FramePlan] = []
    for index, timestamp in enumerate(target_times(duration_ms, fps)):
        if timestamp >= duration_s:
            break
        exact = next(
            (frame for frame in frames if abs(frame.timestamp - timestamp) <= TIMESTAMP_EPSILON),
            None,
        )
        if exact:
            plan.append(
                FramePlan(index=index, timestamp=timestamp, kind="anchor", source_index=exact.index)
            )
            continue
        if timestamp < frames[0].timestamp:
            plan.append(
                FramePlan(
                    index=index, timestamp=timestamp, kind="anchor", source_index=frames[0].index
                )
            )
            continue
        pair = next(
            (
                (left, right)
                for left, right in pairwise(frames)
                if left.timestamp < timestamp < right.timestamp
            ),
            None,
        )
        if pair is None:
            # Do not interpolate across the loop boundary without evidence.
            plan.append(
                FramePlan(
                    index=index, timestamp=timestamp, kind="anchor", source_index=frames[-1].index
                )
            )
            continue
        left, right = pair
        timestep = (timestamp - left.timestamp) / (right.timestamp - left.timestamp)
        plan.append(
            FramePlan(
                index=index,
                timestamp=timestamp,
                kind="rife",
                left_index=left.index,
                right_index=right.index,
                timestep=timestep,
            )
        )
    if len(plan) < 2 or not any(item.kind == "rife" for item in plan):
        raise InterpolationError(f"{fps} FPS plan has no genuine intermediate frames")
    return plan


def plan_payload(plan: Sequence[FramePlan]) -> list[dict[str, Any]]:
    return [
        {
            "index": item.index,
            "timestamp": item.timestamp,
            "kind": item.kind,
            "source_index": item.source_index,
            "left_index": item.left_index,
            "right_index": item.right_index,
            "timestep": item.timestep,
        }
        for item in plan
    ]


def timestep_argument(value: float, *, windows: bool | None = None) -> str:
    formatted = f"{value:.6f}".rstrip("0").rstrip(".")
    if not formatted:
        formatted = "0"
    if windows if windows is not None else sys.platform.startswith("win"):
        # The official Windows binary parses decimals through the active CRT locale.
        return formatted.replace(".", ",")
    return formatted


def model_fingerprint(model: Path) -> dict[str, Any]:
    if not model.is_dir() or model.name not in {"rife-v4", "rife-v4.6"}:
        raise InterpolationError("RIFE arbitrary-timestep pilot requires a rife-v4 model directory")
    files = sorted(path for path in model.rglob("*") if path.is_file())
    if not files:
        raise InterpolationError(f"RIFE model directory is empty: {model}")
    return {
        "name": model.name,
        "files": [
            {
                "path": path.relative_to(model).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ],
    }


def run_rife(
    rife: Path,
    model: Path,
    left: Path,
    right: Path,
    output: Path,
    timestep: float,
    gpu: int,
) -> float:
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    command = [
        str(rife),
        "-m",
        str(model),
        "-0",
        str(left),
        "-1",
        str(right),
        "-o",
        str(output),
        "-s",
        timestep_argument(timestep),
        "-g",
        str(gpu),
        "-j",
        "1:1:1",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode or not output.is_file():
        raise InterpolationError(
            f"RIFE failed at timestep {timestep_argument(timestep)}: {result.stderr.strip()[-1000:]}"
        )
    return time.perf_counter() - started


def frame_is_black(path: Path) -> bool:
    with Image.open(path) as image:
        image = image.convert("RGB")
        mean = ImageStat.Stat(image).mean
        return max(mean) < 1.0


def encode_video(ffmpeg: Path, frames: Sequence[Path], fps: int, output: Path) -> None:
    if not frames:
        raise InterpolationError("Cannot encode an empty frame schedule")
    frame_dir = frames[0].parent
    expected = [frame_dir / f"frame-{index:06d}.png" for index in range(len(frames))]
    if list(frames) != expected:
        raise InterpolationError("Frame schedule is not a contiguous numbered sequence")
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        str(fps),
        "-start_number",
        "0",
        "-i",
        str(frame_dir / "frame-%06d.png"),
        "-frames:v",
        str(len(frames)),
        "-fps_mode",
        "cfr",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise InterpolationError(f"FFmpeg encode failed: {result.stderr.strip()[-1000:]}")


def output_probe(ffprobe: Path, output: Path) -> dict[str, Any]:
    payload = ffprobe_json(ffprobe, output)
    streams = payload.get("streams") or []
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    if len(streams) != 1 or len(videos) != 1:
        raise InterpolationError(f"{output.name}: output contains audio or an unexpected stream")
    stream = videos[0]
    if (
        stream.get("codec_name"),
        stream.get("pix_fmt"),
        stream.get("width"),
        stream.get("height"),
    ) != ("h264", "yuv420p", 720, 720):
        raise InterpolationError(f"{output.name}: output is not H.264/yuv420p/720x720")
    return {
        "codec": stream.get("codec_name"),
        "pix_fmt": stream.get("pix_fmt"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "frames": int(stream.get("nb_read_frames") or 0),
        "avg_frame_rate": stream.get("avg_frame_rate"),
        "r_frame_rate": stream.get("r_frame_rate"),
        "time_base": stream.get("time_base"),
        "duration_s": float((payload.get("format") or {}).get("duration") or 0),
    }


def decode_check(ffmpeg: Path, output: Path) -> None:
    result = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(output), "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise InterpolationError(
            f"{output.name}: full decode failed: {result.stderr.strip()[-1000:]}"
        )


def existing_variant_is_valid(
    output: Path, state_path: Path, signature: dict[str, Any], ffprobe: Path, expected_frames: int
) -> dict[str, Any] | None:
    if not output.exists() and not state_path.exists():
        return None
    if not output.is_file() or not state_path.is_file():
        raise InterpolationError(f"{output.name}: partial output cannot be overwritten")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("signature") != signature or state.get("output_sha256") != sha256_file(output):
        raise InterpolationError(f"{output.name}: existing output provenance/checksum mismatch")
    probe = output_probe(ffprobe, output)
    if probe["frames"] != expected_frames:
        raise InterpolationError(f"{output.name}: existing output frame count mismatch")
    return state


def _copy_or_refuse(source: Path, target: Path) -> None:
    if target.exists():
        if sha256_file(source) != sha256_file(target):
            raise InterpolationError(f"Refusing to overwrite artifact {target.name}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def create_contact_sheet(
    slug: str,
    sources: dict[str, list[Path]],
    output: Path,
    labels: Sequence[str],
    indices: Sequence[int],
) -> None:
    width, height = 220, 250
    canvas = Image.new("RGB", (width * len(labels), height * len(indices)), "#111820")
    draw = ImageDraw.Draw(canvas)
    for row, index in enumerate(indices):
        for column, label in enumerate(labels):
            path = sources[label][min(index, len(sources[label]) - 1)]
            with Image.open(path) as image:
                if path.suffix.lower() == ".gif":
                    image.seek(min(index, getattr(image, "n_frames", 1) - 1))
                image = image.convert("RGB").resize((width, 220), Image.Resampling.LANCZOS)
                canvas.paste(image, (column * width, row * height))
            draw.text((column * width + 5, row * height + 224), label, fill="#f3f6f7")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=90)


def motion_indices(frames: Sequence[Path], limit: int = 3) -> list[int]:
    if len(frames) < 2:
        return [0]
    scores: list[tuple[float, int]] = []
    for index, (left, right) in enumerate(pairwise(frames)):
        with Image.open(left) as left_image, Image.open(right) as right_image:
            difference = ImageChops.difference(
                left_image.convert("RGB"), right_image.convert("RGB")
            )
            scores.append((sum(ImageStat.Stat(difference).mean), index))
    return [index for _score, index in sorted(scores, reverse=True)[:limit]]


def build_gallery(
    output: Path,
    report: dict[str, Any],
    specs: Sequence[SourceSpec],
    source_frames: dict[str, list[SourceFrame]],
) -> Path:
    gallery = output / "gallery"
    media_dir = gallery / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    for spec in specs:
        slug_report = report["exercises"][spec.slug]
        _copy_or_refuse(spec.source_gif, media_dir / f"{spec.slug}-original.gif")
        _copy_or_refuse(spec.source_video, media_dir / f"{spec.slug}-baseline.mp4")
        variants = [
            ("Original GIF", f"media/{spec.slug}-original.gif", "gif", None),
            (
                "AI-upscale",
                f"media/{spec.slug}-baseline.mp4",
                "video",
                slug_report["source"]["nominal_fps"],
            ),
        ]
        for fps, item in slug_report["variants"].items():
            source_name = Path(item["output"]).name
            _copy_or_refuse(output / item["output"], media_dir / source_name)
            variants.append((f"RIFE {fps} FPS", f"media/{source_name}", "video", int(fps)))
        cards = []
        for label, path, kind, fps in variants:
            if kind == "gif":
                cards.append(
                    f'<figure><figcaption>{html.escape(label)}</figcaption><img src="{path}" alt="{html.escape(label)} {slug_report["slug"]}"></figure>'
                )
            else:
                cards.append(
                    f'<figure><figcaption>{html.escape(label)} · {fps or "source"} FPS</figcaption><video src="{path}" muted loop playsinline preload="metadata" controls></video></figure>'
                )
        rows.append(
            "<section class=exercise>"
            f"<h2>{html.escape(spec.slug)}</h2>"
            f"<p>Источник: {slug_report['source']['frames']} опорных кадров, {slug_report['source']['duration_ms']} мс. Состояние: {html.escape(slug_report['qc'])}.</p>"
            f"<div class=variants data-slug={html.escape(spec.slug)}>{''.join(cards)}</div>"
            f"<p><a href=../{html.escape(slug_report['contact_sheets']['phases'])}>Фазы</a> · <a href=../{html.escape(slug_report['contact_sheets']['motion'])}>Участки с наибольшим межкадровым изменением</a></p>"
            "</section>"
        )
    document = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Frame interpolation pilot</title>
<style>
body{{margin:0;background:#111820;color:#f3f6f7;font:16px system-ui,sans-serif}}main{{max-width:1500px;margin:auto;padding:24px}}h1{{color:#c6ff00}}.exercise{{border:1px solid #40505b;border-radius:12px;padding:16px;margin:20px 0}}.variants{{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:12px}}figure{{margin:0;min-width:0}}figcaption{{font-size:13px;margin-bottom:6px;color:#c9d2d8}}img,video{{display:block;width:100%;aspect-ratio:1;object-fit:contain;background:white;border-radius:8px}}a{{color:#c6ff00}}button{{background:#c6ff00;border:0;border-radius:6px;padding:8px 12px;margin-right:8px;font-weight:700}}@media(max-width:800px){{.variants{{grid-template-columns:repeat(2,minmax(130px,1fr))}}}}@media(prefers-reduced-motion:reduce){{video{{animation:none}}}}
</style></head><body><main><h1>AI frame interpolation pilot</h1><p>Локальная галерея реальных результатов. Автоматический QC не подтверждает точность техники; ручная приёмка владельца остаётся отдельным gate.</p><p><button id="play">Воспроизвести все</button><button id="pause">Пауза</button><button id="reset">Сбросить</button></p>{"".join(rows)}</main>
<script>
const videos=()=>[...document.querySelectorAll('video')];
document.querySelector('#play').onclick=()=>{{const all=videos();all.forEach(v=>v.currentTime=0);all.forEach(v=>v.play().catch(()=>{{}}));}};
document.querySelector('#pause').onclick=()=>videos().forEach(v=>v.pause());
document.querySelector('#reset').onclick=()=>videos().forEach(v=>{{v.pause();v.currentTime=0;}});
if(window.matchMedia('(prefers-reduced-motion: reduce)').matches) videos().forEach(v=>v.pause());
videos().forEach(v=>v.addEventListener('error',()=>{{const p=document.createElement('p');p.textContent='Не удалось загрузить локальный файл.';v.replaceWith(p);}}));
</script></body></html>
"""
    path = gallery / "gallery.html"
    path.write_text(document, encoding="utf-8")
    return path


def process_variant(
    spec: SourceSpec,
    source_frames: Sequence[SourceFrame],
    fps: int,
    output: Path,
    rife: Path,
    model: Path,
    ffmpeg: Path,
    ffprobe: Path,
    gpu: int,
    model_signature: dict[str, Any],
    runtime_version: str,
) -> dict[str, Any]:
    plan = build_frame_plan(source_frames, spec.duration_ms, fps)
    variant_dir = output / spec.slug / f"{fps}fps"
    frame_dir = variant_dir / "frames"
    variant_dir.mkdir(parents=True, exist_ok=True)
    output_video = variant_dir / f"{spec.slug}-rife-{fps}fps.mp4"
    state_path = variant_dir / "variant.json"
    signature = {
        "schema_version": SCHEMA_VERSION,
        "slug": spec.slug,
        "source_video_sha256": spec.source_video_sha256,
        "source_gif_sha256": spec.source_gif_sha256,
        "duration_ms": spec.duration_ms,
        "fps": fps,
        "runtime_version": runtime_version,
        "model": model_signature,
        "plan_sha256": json_hash(plan_payload(plan)),
    }
    plan_path = variant_dir / "plan.json"
    reused = existing_variant_is_valid(output_video, state_path, signature, ffprobe, len(plan))
    if reused:
        return reused | {
            "plan": plan_path.relative_to(output).as_posix(),
            "reused": True,
        }
    if output_video.exists() or state_path.exists():
        raise InterpolationError(f"{output_video.name}: refusing to overwrite an incomplete result")
    if plan_path.exists():
        existing_plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if existing_plan.get("signature") != signature:
            raise InterpolationError(
                f"{output_video.name}: existing plan belongs to another source/model"
            )
    else:
        write_json_atomic(plan_path, {"signature": signature, "frames": plan_payload(plan)})
    by_index = {frame.index: frame for frame in source_frames}
    output_frames: list[Path] = []
    generated = 0
    gpu_seconds = 0.0
    frame_records: list[dict[str, Any]] = []
    for item in plan:
        frame_path = frame_dir / f"frame-{item.index:06d}.png"
        if item.kind == "anchor":
            source = by_index[item.source_index or 0].path
            _copy_or_refuse(source, frame_path)
        else:
            left = by_index[item.left_index or 0].path
            right = by_index[item.right_index or 0].path
            if frame_path.exists():
                if frame_is_black(frame_path):
                    raise InterpolationError(
                        f"{output_video.name}: existing generated frame is black"
                    )
            else:
                gpu_seconds += run_rife(
                    rife,
                    model,
                    left,
                    right,
                    frame_path,
                    item.timestep or 0.5,
                    gpu,
                )
            if sha256_file(frame_path) in {sha256_file(left), sha256_file(right)}:
                raise InterpolationError(
                    f"{output_video.name}: RIFE produced a duplicate anchor frame"
                )
            if frame_is_black(frame_path):
                raise InterpolationError(f"{output_video.name}: RIFE produced a black frame")
            generated += 1
        output_frames.append(frame_path)
        frame_records.append(
            {"index": item.index, "sha256": sha256_file(frame_path), "kind": item.kind}
        )
    if generated == 0:
        raise InterpolationError(f"{output_video.name}: no genuine interpolated frames")
    encode_video(ffmpeg, output_frames, fps, output_video)
    probe = output_probe(ffprobe, output_video)
    decode_check(ffmpeg, output_video)
    pts = frame_timestamps(ffprobe, output_video)
    expected_duration = len(plan) / fps
    duration_tolerance = max(0.05, 0.5 / fps + 0.005)
    if (
        probe["frames"] != len(plan)
        or len(pts) != len(plan)
        or abs(probe["duration_s"] - expected_duration) > 0.01
        or abs(probe["duration_s"] - spec.duration_ms / 1000) > duration_tolerance
        or any(right <= left for left, right in pairwise(pts))
    ):
        raise InterpolationError(f"{output_video.name}: output timing/frame count failed QC")
    result = {
        "signature": signature,
        "output": output_video.relative_to(output).as_posix(),
        "plan": plan_path.relative_to(output).as_posix(),
        "output_sha256": sha256_file(output_video),
        "bytes": output_video.stat().st_size,
        "frames": len(plan),
        "nominal_fps": fps,
        "duration_s": probe["duration_s"],
        "duration_delta_ms": round((probe["duration_s"] - spec.duration_ms / 1000) * 1000, 3),
        "pts_monotonic": True,
        "generated_intermediate_frames": generated,
        "gpu_seconds": round(gpu_seconds, 3),
        "probe": probe,
        "frame_records": frame_records,
        "reused": False,
    }
    write_json_atomic(state_path, result)
    return result


def run_pilot(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.source_manifest.resolve()
    source_root = (args.source_root or manifest_path.parent).resolve()
    output = args.output.resolve()
    specs = [resolve_source(manifest_path, source_root, slug) for slug in args.slugs]
    model_signature = model_fingerprint(args.model.resolve())
    report_path = output / "processing-report.json"
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "method": "RIFE ncnn Vulkan arbitrary-timestep pair interpolation",
        "runtime_version": args.runtime_version,
        "model": model_signature,
        "gpu": args.gpu,
        "target_fps": list(args.fps),
        "source_manifest": str(manifest_path),
        "source_manifest_sha256": sha256_file(manifest_path),
        "exercises": {},
    }
    if report_path.exists():
        existing = json.loads(report_path.read_text(encoding="utf-8"))
        if (
            existing.get("schema_version") != SCHEMA_VERSION
            or existing.get("model") != model_signature
            or existing.get("target_fps") != list(args.fps)
        ):
            raise InterpolationError(
                "Existing processing report uses a different model or target set"
            )
        report = existing
    for spec in specs:
        source_info = inspect_source(args.ffprobe, spec)
        frames = extract_source_frames(
            args.ffmpeg, args.ffprobe, spec, output / spec.slug / "source-frames"
        )
        entry = report["exercises"].setdefault(
            spec.slug,
            {
                "slug": spec.slug,
                "source": {
                    "video": str(spec.source_video),
                    "video_sha256": spec.source_video_sha256,
                    "gif": str(spec.source_gif),
                    "gif_sha256": spec.source_gif_sha256,
                    "frames": len(frames),
                    "duration_ms": spec.duration_ms,
                    "loop": spec.loop,
                    "nominal_fps": source_info.get("avg_frame_rate"),
                    "probe": source_info,
                    "frame_metadata": (output / spec.slug / "source-frames" / "source-frames.json")
                    .relative_to(output)
                    .as_posix(),
                    "frame_timestamps_s": [round(frame.timestamp, 6) for frame in frames],
                },
                "variants": {},
                "qc": "TECHNICAL_PASS_VISUAL_PENDING",
            },
        )
        entry["source"].update(
            {
                "frame_metadata": (output / spec.slug / "source-frames" / "source-frames.json")
                .relative_to(output)
                .as_posix(),
                "frame_timestamps_s": [round(frame.timestamp, 6) for frame in frames],
            }
        )
        if entry["source"]["video_sha256"] != spec.source_video_sha256:
            raise InterpolationError(f"{spec.slug}: existing report source SHA mismatch")
        for fps in args.fps:
            entry["variants"][str(fps)] = process_variant(
                spec,
                frames,
                fps,
                output,
                args.rife.resolve(),
                args.model.resolve(),
                args.ffmpeg.resolve(),
                args.ffprobe.resolve(),
                args.gpu,
                model_signature,
                args.runtime_version,
            )
        phases = [0, max(0, len(frames) // 2), len(frames) - 1]
        motion = motion_indices([frame.path for frame in frames])
        contact_sources: dict[str, list[Path]] = {
            "Original GIF": [spec.source_gif] * len(frames),
            "AI-upscale": [frame.path for frame in frames],
        }
        for fps in args.fps:
            frame_paths = sorted((output / spec.slug / f"{fps}fps" / "frames").glob("frame-*.png"))
            contact_sources[f"RIFE {fps} FPS"] = frame_paths
        phases_path = output / spec.slug / "contact-sheet-phases.jpg"
        motion_path = output / spec.slug / "contact-sheet-motion.jpg"
        create_contact_sheet(spec.slug, contact_sources, phases_path, list(contact_sources), phases)
        create_contact_sheet(spec.slug, contact_sources, motion_path, list(contact_sources), motion)
        entry["contact_sheets"] = {
            "phases": phases_path.relative_to(output).as_posix(),
            "motion": motion_path.relative_to(output).as_posix(),
            "motion_indices": motion,
        }
        write_json_atomic(report_path, report)
    if not args.skip_gallery:
        build_gallery(
            output,
            report,
            specs,
            {
                spec.slug: extract_source_frames(
                    args.ffmpeg, args.ffprobe, spec, output / spec.slug / "source-frames"
                )
                for spec in specs
            },
        )
    write_json_atomic(report_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--rife", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--slugs", nargs="+", default=list(PILOT_SLUGS))
    parser.add_argument("--fps", nargs="+", type=int, choices=TARGET_FPS, default=list(TARGET_FPS))
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--runtime-version", default="rife-ncnn-vulkan-20221029")
    parser.add_argument("--skip-gallery", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = run_pilot(args)
    except (InterpolationError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    variants = sum(len(item["variants"]) for item in report["exercises"].values())
    print(f"Ready: {len(report['exercises'])} exercises, {variants} variants")
    print(f"Report: {args.output / 'processing-report.json'}")
    if not args.skip_gallery:
        print(f"Gallery: {args.output / 'gallery' / 'gallery.html'}")


if __name__ == "__main__":
    main()
