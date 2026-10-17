# #986 - Continue approved GIF animations to AI MP4

On 2026-10-18 the owner accepted the quality of 77 native HD videos and four
RealESRGAN_x4plus pilot animations, and authorized improving the remaining GIFs.

## Baseline

- 206 canonical exercises; 167 have approved animated media.
- 77 native HD videos: retain them byte-identical.
- Four pilot AI 720x720 H.264 clips: retain them byte-identical.
- **86 approved animated exercises still have only 180x180 GIFs**.
- 35 blocked and four static-only entries must not be counted as AI candidates.

AI upscaling improves rendering without adding genuine source resolution. Never
mislabel AI video as native HD. Keep movement, apparatus, angle and frame timing
by processing only the exercise's existing licensed GymVisual GIF. Retain the
original GIF as playback fallback. Reduced-motion thumbnails stay unchanged.

## Offline GPU batch processing

Use the official Real-ESRGAN NCNN Vulkan portable release v0.2.5.0 installed
outside the repository (https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0).
The approved inference model is realesrgan-x4plus, not animevideov3. The renderer
is resumable, writes only untracked artifacts, and does not change production.

From the YFC repo root, with Python environment, FFmpeg, FFprobe and Vulkan GPU:

~~~powershell
# List all pending exercise slugs (expected 86 at baseline).
python -m scripts.import_ai_upscaled_exercise_gifs

# Windows example: process all pending movements using the portable GPU engine.
python -m scripts.batch_upscale_gymvisual_gifs --engine "D:\tools\realesrgan" --all-pending

# Verify every resulting MP4, original GIF hash and the processing report.
python -m scripts.import_ai_upscaled_exercise_gifs --source-dir ".artifacts/runtime/986-ai-batch"

# Only then stage approved animation derivatives and manifest changes locally.
python -m scripts.import_ai_upscaled_exercise_gifs --source-dir ".artifacts/runtime/986-ai-batch" --apply

python scripts/validate_exercise_catalog.py
python -m pytest tests/test_ai_exercise_gif_batch.py tests/test_verified_hd_animated_media.py
~~~

To process small groups, specify --slugs for both render and import commands.
The renderer verifies resume artifacts and refuses to overwrite unknown files.
The importer checks original source SHA, model, animation frame timing, H.264,
dimensions, pixel format, decoded frame count, audio absence and byte limits.
The catalog validator authenticates per-exercise provenance and hashes.

## Release requirements

1. Run actual GPU inference and check first/middle/last frames, continuous
   motion, equipment and limb movements. Physical mobile WebKit/TMA acceptance
   remains a post-release owner verification.
2. Import actual binary outputs in a separate media PR, retaining GIF fallbacks.
   A preparation-only PR must never be mistaken for the produced media release.
3. Require successful CI, mandatory checks, master CI, production deploy with
   exact SHA/smoke and confirmed source provenance.
4. Keep issue #986 open for 35 blocked / four static-only and source-quality gaps.

The missing 86 MP4 binaries are NOT present in this preparation change.
Creating them requires the separately installed GPU engine; never substitute
plain image enlargement or misstate production status.
