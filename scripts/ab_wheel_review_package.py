"""Build an offline review package without promoting a candidate to production."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from fractions import Fraction
from itertools import pairwise
from pathlib import Path


def validate_probe(probe: dict) -> dict:
    """Reject videos outside the fixed pilot delivery contract."""
    try:
        streams = probe["streams"]
        if len(streams) != 1:
            raise ValueError("Expected one video stream and no audio")
        stream = streams[0]
        expected = {
            "codec_type": "video",
            "codec_name": "h264",
            "pix_fmt": "yuv420p",
            "width": 720,
            "height": 720,
        }
        if any(stream.get(key) != value for key, value in expected.items()):
            raise ValueError("Expected H.264/yuv420p 720x720 video")
        if Fraction(stream["avg_frame_rate"]) != 30:
            raise ValueError("Expected 30 FPS")
        if Fraction(stream["r_frame_rate"]) != 30 or int(stream["nb_frames"]) != 120:
            raise ValueError("Expected 120 frames at 30 FPS")
        if not math.isclose(float(stream["duration"]), 4, abs_tol=0.001):
            raise ValueError("Expected four seconds")
        pts = [float(frame["best_effort_timestamp_time"]) for frame in probe["frames"]]
        if len(pts) != 120 or any(not math.isfinite(value) for value in pts):
            raise ValueError("Expected 120 finite frame timestamps")
        if any(later <= earlier for earlier, later in pairwise(pts)):
            raise ValueError("Frame timestamps must strictly increase")
        if any(abs(value - index / 30) > 0.001 for index, value in enumerate(pts)):
            raise ValueError("Frame timestamps must follow the 30 FPS timeline from zero")
    except (KeyError, TypeError, ZeroDivisionError, OverflowError) as error:
        raise ValueError("Missing or malformed probe metadata") from error
    return {"technical_status": "PASS", "frame_count": 120, "duration_seconds": 4, "fps": 30}


def _run(executable: Path, *arguments: str) -> bytes:
    result = subprocess.run([str(executable), *arguments], capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-6000:])
    return result.stdout


def _file_record(path: Path) -> dict:
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def build_package(
    output_dir: Path,
    reference_dir: Path,
    baseline_gif: Path,
    ffmpeg: Path,
    ffprobe: Path,
    metadata: dict,
) -> dict:
    """Validate the actual candidate and write review media plus factual QC."""
    from PIL import Image, ImageDraw

    candidate = output_dir / "candidate.mp4"
    reference = reference_dir / "approved-storyboard.png"
    frame_paths = [output_dir / "frames" / f"frame-{index:04d}.png" for index in range(120)]
    for required in [candidate, reference, baseline_gif, ffmpeg, ffprobe, *frame_paths]:
        if not required.is_file():
            raise FileNotFoundError(required)
    probe = json.loads(
        _run(ffprobe, "-v", "error", "-show_streams", "-show_frames", "-of", "json", str(candidate))
    )
    technical = validate_probe(probe)
    _run(ffmpeg, "-v", "error", "-xerror", "-i", str(candidate), "-f", "null", "-")
    decoded = _run(
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(candidate),
        "-vf",
        "scale=64:64",
        "-pix_fmt",
        "gray",
        "-f",
        "rawvideo",
        "-",
    )
    if len(decoded) != 120 * 64 * 64:
        raise ValueError("Decoded frame count does not match the probe")
    decoded_frames = [decoded[index * 4096 : (index + 1) * 4096] for index in range(120)]

    def difference(first: bytes, second: bytes) -> float:
        return sum(abs(a - b) for a, b in zip(first, second, strict=True)) / len(first)

    differences = [difference(a, b) for a, b in pairwise(decoded_frames)]
    baseline = output_dir / "baseline.mp4"
    _run(
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-ignore_loop",
        "1",
        "-i",
        str(baseline_gif),
        "-an",
        "-fps_mode",
        "vfr",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(baseline),
    )
    shutil.copyfile(reference, output_dir / "approved-storyboard.png")
    sheet = Image.new("RGB", (960, 3 * 270), "white")
    draw = ImageDraw.Draw(sheet)
    sample_indices = [round(index * 119 / 11) for index in range(12)]
    for position, index in enumerate(sample_indices):
        with Image.open(frame_paths[index]) as source:
            thumbnail = source.convert("RGB")
            thumbnail.thumbnail((240, 240))
            left, top = (position % 4) * 240, (position // 4) * 270
            sheet.paste(thumbnail, (left, top))
            draw.text((left + 8, top + 244), f"{index:03d} / {index / 30:.3f} s", fill="black")
    sheet.save(output_dir / "contact-sheet.png")
    (output_dir / "index.html").write_text(_HTML, encoding="utf-8")
    baseline_probe = json.loads(
        _run(ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(baseline))
    )
    report = {
        "status": "NEEDS_WORK",
        "visual_status": "NOT_APPROVED",
        "anatomy_status": "NOT_VERIFIED",
        "technique_status": "NOT_VERIFIED",
        "metadata": metadata,
        "technical": technical,
        "candidate_probe": probe,
        "baseline_probe": baseline_probe,
        "decode": "PASS",
        "motion_statistics": {
            "method": "Decoded 64x64 grayscale mean absolute pixel difference, range 0..255",
            "adjacent_mean": sum(differences) / len(differences),
            "adjacent_min": min(differences),
            "adjacent_max": max(differences),
            "first_last": difference(decoded_frames[0], decoded_frames[-1]),
            "limitation": "Motion statistics do not establish anatomy, technique or visual quality",
        },
        "versions": {
            "ffmpeg": _run(ffmpeg, "-version").decode().splitlines()[0],
            "ffprobe": _run(ffprobe, "-version").decode().splitlines()[0],
        },
        "sources": {
            str(reference): _file_record(reference),
            str(baseline_gif): _file_record(baseline_gif),
            "rendered_frames": {path.name: _file_record(path) for path in frame_paths},
        },
        "outputs": {
            name: _file_record(output_dir / name)
            for name in [
                "candidate.mp4",
                "baseline.mp4",
                "approved-storyboard.png",
                "contact-sheet.png",
                "index.html",
            ]
        },
        "contact_sheet_frame_indices": sample_indices,
    }
    (output_dir / "qc.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


_HTML = """<!doctype html>
<html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ролик для пресса — проверка анимации</title>
<style>
*{box-sizing:border-box}body{font:16px/1.5 system-ui,sans-serif;margin:0;background:#f4f4f4;color:#191919}
main{max-width:1300px;margin:auto;padding:20px}h1{font-size:1.6rem}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px}
figure{margin:0;background:white;padding:12px;border:1px solid #bbb;border-radius:8px}video,img{width:100%;display:block;object-fit:contain}video{aspect-ratio:1;background:white}
button,select,input{font:inherit}button,select{min-height:44px;padding:8px 14px}button{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #005fcc;outline-offset:3px}
.controls{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}input[type=range]{width:100%;min-height:44px}figcaption{font-weight:600}output{font-variant-numeric:tabular-nums}
</style><main>
<h1>Ролик для пресса: проверка движения и стиля</h1>
<p><strong>NEEDS_WORK — требуется проверка.</strong> Анатомия, техника и визуальное соответствие не одобрены. Технические показатели не заменяют решение владельца.</p>
<div class="gallery">
<figure><figcaption>Утверждённый референс стиля</figcaption><img src="approved-storyboard.png" alt="Исходная раскадровка: анатомический персонаж и выкаты с колен"></figure>
<figure><figcaption>Исходная анимация — ориентир движения</figcaption><video id="baseline" src="baseline.mp4" preload="metadata" muted playsinline loop aria-label="Исходная анимация"></video></figure>
<figure><figcaption>Кандидат — 120 кадров, 4 секунды</figcaption><video id="candidate" src="candidate.mp4" preload="metadata" muted playsinline loop aria-label="Кандидат для проверки"></video></figure>
</div>
<div class="controls" role="group" aria-label="Общее управление видео">
<button id="play" type="button">Воспроизвести</button><button id="restart" type="button">С начала</button>
<button id="previous" type="button">Предыдущий кадр</button><button id="next" type="button">Следующий кадр</button>
<label>Скорость <select id="speed"><option value="0.25">0,25×</option><option value="0.5">0,5×</option><option value="1" selected>1×</option></select></label>
</div>
<label for="phase">Фаза цикла: <output id="position">0 / 119</output></label><input id="phase" type="range" min="0" max="119" value="0" step="1">
<div class="controls" role="group" aria-label="Критические фазы">
<button type="button" data-frame="0">Старт</button><button type="button" data-frame="15">Начало выката</button>
<button type="button" data-frame="30">Середина выката</button><button type="button" data-frame="60">Дальняя точка</button>
<button type="button" data-frame="90">Возврат</button><button type="button" data-frame="119">Финиш</button>
<button id="seam" type="button">Стык: последний → первый кадр</button></div>
<p>Видео синхронизированы по доле цикла. Шаг равен одному кадру кандидата. В исходной анимации длительность и частота кадров могут отличаться. Для проверки стыка кнопка попеременно показывает последний и первый кадры.</p>
<figure><figcaption>12 фаз кандидата</figcaption><img src="contact-sheet.png" alt="Контактный лист с номерами и временем двенадцати равномерно выбранных кадров"></figure>
<p><a href="qc.json">Технический отчёт и SHA-256</a> · <a href="candidate.mp4" download>Скачать кандидат MP4</a></p>
</main><script>
const candidate=document.querySelector('#candidate'),baseline=document.querySelector('#baseline');
const phase=document.querySelector('#phase'),position=document.querySelector('#position'),play=document.querySelector('#play');
let playing=false,frame=0,speed=1,seamEnd=true;
function stop(){playing=false;candidate.pause();baseline.pause();play.textContent='Воспроизвести';}
function display(value){frame=Math.max(0,Math.min(119,value));phase.value=String(Math.round(frame));position.value=`${Math.round(frame)} / 119`;}
function show(value){display(value);
 if(Number.isFinite(candidate.duration))candidate.currentTime=Math.min(frame/30,candidate.duration-0.001);
 if(Number.isFinite(baseline.duration))baseline.currentTime=Math.min(frame/120*baseline.duration,baseline.duration-0.001);}
function seek(value){stop();show(value);}
function rates(){candidate.playbackRate=speed;if(Number.isFinite(baseline.duration)&&Number.isFinite(candidate.duration))baseline.playbackRate=speed*baseline.duration/candidate.duration;}
play.onclick=()=>{if(playing){stop();return;}show(frame);rates();playing=true;play.textContent='Пауза';Promise.all([candidate.play(),baseline.play()]).catch(()=>stop());};
document.querySelector('#restart').onclick=()=>seek(0);
document.querySelector('#previous').onclick=()=>seek(Math.round(frame)-1);
document.querySelector('#next').onclick=()=>seek(Math.round(frame)+1);
document.querySelector('#speed').onchange=event=>{speed=Number(event.target.value);rates();};
phase.oninput=()=>seek(Number(phase.value));
document.querySelectorAll('[data-frame]').forEach(button=>button.onclick=()=>seek(Number(button.dataset.frame)));
document.querySelector('#seam').onclick=()=>{seek(seamEnd?119:0);seamEnd=!seamEnd;};
for(const video of [candidate,baseline])video.addEventListener('loadedmetadata',()=>show(frame));
function tick(){if(playing)display(candidate.currentTime*30);requestAnimationFrame(tick);}
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});requestAnimationFrame(tick);
</script></html>
"""
