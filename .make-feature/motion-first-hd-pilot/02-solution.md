# Solution

`scripts/motion_first_pilot.py` содержит минимальный offline contract:

1. `classify_source` различает непрерывное движение, static-pose sequence, crossfade, review и reject.
2. `validate_provenance` требует exact SHA-256, URL/revision и явные commercial-use/redistribution flags.
3. `plan_processing` ограничивает scope тремя canonical IDs, запрещает запись в production paths и не перезаписывает существующие outputs; известный checksum поддерживает resume.
4. `validate_output_metadata`, `validate_pts` и `validate_cycle` проверяют H.264/yuv420p, 720x720+, 24–30 FPS, отсутствие audio, monotonic PTS и seam evidence.
5. `build_gallery` создаёт local-only HTML comparison gallery; escaped labels не превращаются в HTML.

Модель/AI-interpolation не является доказательством техники: RIFE допускается только как comparison output, если source classification уже разрешает review pipeline.
