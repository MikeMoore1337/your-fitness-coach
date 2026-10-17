# #986 - approved AI GIF fallback rollout (4 exercises)

Owner visual approval: **2026-10-17**, PR #1073 comparisons. Applies only to
`machine-chest-press`, `deadlift`, `russian-twist` and `walking-lunge`
with `RealESRGAN_x4plus`. These were unverified for native HD video.

- Native, semantically VERIFIED HD videos retain higher priority. The 77 native
  HD videos from PR #1070 remain unchanged and separately counted.
- The four **AI-upscaled** MP4s are 720x720 (not native HD). They are explicitly
  marked in `video_provenance.source_kind=ai_upscaled_gymvisual` and in separate
  manifest counters. Do not count them toward `hq_video_count`.
- All four original 180x180 GymVisual GIFs remain byte-for-byte intact as
  animation fallbacks. The canonical exercise IDs, phase sequence, frame
  timing and source hashes are inherited from the approved research pilot.
- Responsive static posters and `prefers-reduced-motion` behavior stay intact.
- The runtime uses the existing `video_sources` contract, with no new CDN,
  AI inference or paid calls during playback.
- The approved asset binaries are pinned by SHA-256 and size. Only samples
  listed in the importer are eligible. Native HD-video mappings cannot be
  overwritten with an AI derivative.

To reproduce after the evidence-only PR #1073 lands:

```bash
python scripts/apply_owner_approved_ai_exercise_videos.py
python scripts/apply_owner_approved_ai_exercise_videos.py --apply
python scripts/validate_exercise_catalog.py
pytest tests/test_ai_reviewed_exercise_video.py tests/test_verified_hd_animated_media.py backend/tests/test_exercise_video_delivery.py
```

The default evidence path is
`docs/exercises/catalog-v2/evidence/986-gif-upscale-pilot`. Use
`--evidence PATH` for an immutable external check-out of PR #1073.

**Delivery gates:** this branch is stacked on PR #1070. Do not merge into
production until #1070 is independently merged and deployed, then rebase or
merge from current `master`, retarget to `master`, run exact-head required
CI, and perform a controlled production deployment. The original owner
approval covers the four observed AI animations, not the other unreviewed GIFs.
Issue #986 remains open for full coverage and post-release iPhone/TMA checks.
