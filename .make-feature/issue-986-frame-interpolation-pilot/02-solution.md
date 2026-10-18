# Solution

## Scope and input contract

The pilot reads the canonical `manifest.json` from the local checkout of PR #1109 and accepts
only `status=approved`, one GIF fallback, one `ai_upscaled_gymvisual` 720×720 MP4 and matching
provenance SHA-256. Native HD and unknown media are rejected. The eight fixed candidates are:

`ab-wheel`, `leg-press`, `romanian-deadlift`, `kettlebell-swing`, `treadmill-walk`,
`assault-bike`, `turkish-get-up`, `dragon-flag`.

The input checkout was `origin` branch head `a1755e1c6bde5dff03b8f2b3ea370e0f700948e0` in
`.artifacts/worktrees/1094-ai-assets`; it remained clean and all 16 source-file hashes matched
the processing report after the run.

## Runtime choice

The implementation uses the official portable RIFE ncnn Vulkan executable and `rife-v4` model.
The runtime reported the NVIDIA GeForce RTX 4060 Ti (driver 617.42) and completed real GPU
inference. Runtime archive SHA-256:

`D8E4D772D26CD8006EF0AD0BC82EB191B53C68677D1AE2F42506D74CBBBEA606`.

Model fingerprint:

- `flownet.bin` — 10,340,416 bytes — `f307230e32bffeaef5d27a1ea48ec4a67371f99e363ffde1f0f62016a1f725b4`;
- `flownet.param` — 12,999 bytes — `8698b5a482922817ff2be3cd1dbe77dbe39eb7a8ddb2c6d7c0f27b9373bc870a`.

The CLI is invoked one source-frame pair at a time with a real fractional timestep. The Windows
CRT decimal separator is handled explicitly because the official binary rejected `0.5` but
accepted `0,5` on this host. FFmpeg 9.0.2 encodes the numbered output frame schedule as CFR
H.264/yuv420p with no audio.

## Provenance, resume and QC

- `source-frames.json` records the accepted source frame set and real `best_effort_timestamp`;
  frames at or beyond the manifest duration are excluded, which removes the trailing concat
  duplicate present in some AI-upscaled MP4s.
- `plan.json` records each anchor/interpolated output frame, source pair and timestep.
- `variant.json` records the source/model/runtime signature, output SHA-256, probe, PTS result,
  generated-frame count and GPU seconds.
- All JSON writes are atomic. Existing outputs are reused only when signature, output SHA,
  frame count and probe still match; mismatches or partial files are refused.
- QC rejects unexpected streams/audio, non-H.264, non-yuv420p, non-720×720 output, black or
  duplicate intermediate frames, decode errors, wrong frame count, and non-monotonic PTS.

The short `dragon-flag` source is 2.1 seconds, so CFR necessarily quantizes it: 17/25/34 frames
at 8/12/16 FPS produce +25/−16.67/+25 ms versus the source duration. The delta is surfaced in
the report; it is not silently presented as an exact source-duration match.

## Files

- `scripts/interpolate_exercise_videos.py` — bounded local pilot CLI and gallery generator.
- `tests/test_interpolate_exercise_videos.py` — source/model/timestep/planning/resume guard tests.
- `docs/exercises/catalog-v2/986_FRAME_INTERPOLATION_PILOT.md` — human-readable pilot report.
- `.make-feature/issue-986-frame-interpolation-pilot/` — implementation and verification record.

No production manifest, catalog media, model, binary or dependency was added.
