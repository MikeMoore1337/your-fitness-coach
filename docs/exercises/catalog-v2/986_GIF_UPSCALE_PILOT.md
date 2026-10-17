# Issue #986 — animated GIF 180×180 AI-upscaling pilot

Status: **visual review / research only**. This pilot does **not** update the production manifest, API, catalog, or fallback policy. Originals stay unchanged. Tested on a local NVIDIA GeForce RTX 4060 Ti.

## Purpose

Test real frame-based GPU inference (not Lanczos-only enlargement) on exercise animations for which no semantically verified HD MP4 is available. The owner requires **motion**, with actual matching HD video preferred, and unchanged legacy 180×180 GIF if upgrading would distort the exercise.

Pipeline: Pillow GIF composited frames → Real-ESRGAN ncnn Vulkan ×4 to 720×720 → animated WebP (720×720), H.264 MP4 (720×720), and review GIF (360×360) using original per-frame durations and loop. Compare against simple Lanczos 720×720 from the same GIF. Contact sheets include nearest-neighbor enlarged original / Lanczos / AI at identical pose indexes.

Upstream GPU tool: [Real-ESRGAN release v0.2.5.0](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0) (portable NCNN executable with models, **not checked into YFC**). Models: `realesr-animevideov3` and `realesrgan-x4plus`. Inference uses Vulkan on the local RTX 4060 Ti. Source GIFs remain under `backend/assets/exercise-guides/gymvisual/` with existing owner-purchased GymVisual rights; source checksums are checked before processing.

## Reproduce

Extract the official `realesrgan-ncnn-vulkan-20220424-windows.zip` into a local directory outside the repo (contains executable and `models/`). Use the existing YFC Python environment with `Pillow` and `imageio_ffmpeg`.

```powershell
python scripts/pilot_upscale_gymvisual_gifs.py --engine 'D:\tools\realesrgan' --model realesr-animevideov3 --label ai
python scripts/pilot_upscale_gymvisual_gifs.py --engine 'D:\tools\realesrgan' --model realesrgan-x4plus --label general
```

Outputs default to [evidence/986-gif-upscale-pilot](./evidence/986-gif-upscale-pilot) and include comparisons plus metadata in `results-ai.json` / `results-general.json`. This tool is **explicitly opt-in**, writes only comparison evidence, never updates production manifests, and never substitutes an unrelated movement.

## Four tested movements

| YFC canonical exercise | Source frames | Source duration | AI x4plus MP4 / 720×720 | Comparative finding |
| --- | ---: | ---: | ---: | --- |
| `machine-chest-press` | 12 | 3 s | 147,140 bytes | AI improves line contrast, can alter face/equipment micro-detail |
| `deadlift` | 12 | 3 s | 111,130 bytes | Linework looks clearer; small anatomical features simplified |
| `russian-twist` | 24 | 5 s | 196,448 bytes | Sharper figure silhouette; verify twisting motion in animation |
| `walking-lunge` | 24 | 5 s | 160,255 bytes | Thigh-muscle outlines clearer, small stroke pattern changed |

Both tested AI models generally produce clearer contours than Lanczos, but they **hallucinate/regularize some fine detail** in anatomical drawings. On visible samples, `realesrgan-x4plus` retains facial/hair detail more faithfully than `realesr-animevideov3`; it is the **tentative** preferred AI candidate, **not an automatic production approval**.

In all tests the source exercise and phase frames remain from the same GymVisual animation. Nevertheless, individual limbs, grip, cables, joint lines and movement phases need visual acceptance. Frame index/timing metadata is recorded; check actual video playback on mobile Safari and Telegram Mini App before substituting existing GIFs.

## Review

Comparison screenshots for each slug are directly in the evidence folder:
- `machine-chest-press-general-comparison.jpg`
- `deadlift-general-comparison.jpg`
- `russian-twist-general-comparison.jpg`
- `walking-lunge-general-comparison.jpg`

The same folder contains `*-ai-720.mp4` (`AnimeVideoV3`), `*-general-720.mp4` (`x4plus`), `*-lanczos-720.mp4` (deterministic baseline), matching animated WebP and `*-360.gif` for direct playback comparison.

## Release gate

Do not merge AI media into `manifest.json`, count them as **genuine HD source assets**, or roll them out across the remaining low-resolution exercises merely because dimensions are 720×720. **Owner visual acceptance** of anatomy, equipment and timing (plus performance and iPhone/TMA playback) is required first. If not accepted, keep unchanged 180×180 GIF. This pilot can be merged as docs/tests/evidence only; it should not trigger a production asset switch. Main Issue #986 stays open.
