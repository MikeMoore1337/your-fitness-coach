# #986 — Verified animated HD rollout

## Owner acceptance rule (2026-10-17)

**Motion is mandatory.** Use the semantically verified HD exercise animation
when available, regardless of performer gender; otherwise retain the existing
GymVisual animated 180×180 GIF. Never replace an existing animated demonstration
with a still HD poster. Posters remain previews, reduced-motion alternatives,
and error fallbacks. No substitution by a merely similar exercise is permitted.

## Shipped scope (pending CI and production)

- Canonical catalog: 206 exercises.
- **77 semantically matched exercise videos (HD 1280×720, H.264)**, including
  two previously shipped video pilots (barbell-curl and burpee).
- New conversion: 75 exercises, with 150 H.264 derivatives (854×480 and
  1280×720), sourced from the same pinned male/female candidate identity as
  each already-approved HD poster. Source gender is not a matching constraint.
- All 167 original 180×180 animated GIFs remain present and unmodified.
  Of those, 73 have HD videos; **94 still rely on the existing GIF**.
- Four formerly blocked (no GIF) exercises now have matched HD video plus
  static fallback: battle-rope, machine-glute-kickback, side-plank, woodchopper.
- 35 exercises remain blocked because no suitable legacy animation or verified
  HD animation is currently present. Do not claim their coverage.
- 77 HD posters remain available for display while loading and reduced motion.

## Source and provenance

- https://github.com/akajdid-mostafa/exercises-media
- Pinned source revision: `18742da40b0627c85925c5dd4441dc3eac0594d0`.
- Original MP4 matches the *already accepted* source `gender/slug` of the
  corresponding HD poster. No new fuzzy match is approved by the importer.
- Raw source validated against `986_SOURCE_INVENTORY.csv` for Git blob SHA-1
  and exact byte length; SHA-256 recorded for source and output.
- Owner previously confirmed all necessary rights to publish these derivatives.
- Transcode: H.264, 24 fps, YUV420p, 480p CRF30 and 720p CRF29,
  no audio, faststart, same-origin bundled assets.
- Source downloads and transcoding are **build-time only**. No external CDN or
  network requests are needed to display video in the deployed application.

## Playback behavior

- Guide opens with 480p inline muted autoplay/loop, 720p in expanded mode,
  respecting intersection visibility and prefers-reduced-motion.
- Active workout explicitly receives `media_video_sources` in its API
  payload and plays the 720p animation. On a video failure, the original
  approved GIF animation is used for the 73 previously animated entries.
- Catalog / search / picker use a responsive HD still thumbnail, rather than
  playing dozens of videos simultaneously.
- Under reduced motion, the static poster is shown by design.

## Reproduction / validation

Install the tooling only in a development environment:

```bash
uv pip install --python .venv/Scripts/python.exe imageio-ffmpeg
python scripts/import_verified_hd_exercise_videos.py
python scripts/import_verified_hd_exercise_videos.py --apply
python scripts/validate_exercise_catalog.py
pytest tests/test_verified_hd_animated_media.py backend/tests/test_exercise_domain.py
```

The importer downloads original MP4 files from the exact pinned Git revision,
checks immutable metadata and cached-file integrity, and caches H.264 results in
ignored `.artifacts/runtime`. It will refuse a differing existing output.

The manifest and media assets are committed to the application repository;
the source MP4 cache is not committed. CI must confirm exact-head checks, then
a controlled production deployment must be verified. Physical iPhone/TMA and
exercise-technique visual acceptance remains post-release per the owner.

**Issue #986 stays OPEN:** the 94 GIF-only exercises and 35 blocked records
still need an exact and licensed HD animation if one can be found.
