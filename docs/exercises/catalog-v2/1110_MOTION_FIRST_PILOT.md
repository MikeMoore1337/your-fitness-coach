# #1110 Motion-first HD pilot

**Статус:** `BLOCKED_SOURCE`

Это отдельный review-only пилот после визуально неуспешного RIFE baseline. Он не меняет `backend/assets/exercise-guides/manifest.json`, production media или PR #1111/#1094/#1109. Существующие GIF, AI-upscaled и RIFE MP4 собраны в локальной галерее только для сравнения.

## Результат по трём canonical ID

| Упражнение | Классификация источника | Итог | Причина блокировки |
| --- | --- | --- | --- |
| `ab-wheel` | `STATIC_POSE_SEQUENCE` | `BLOCKED_SOURCE` | Exact continuous-motion source с безопасной provenance не найден; похожий rollout запрещён. |
| `kettlebell-swing` | `MOTION_SOURCE_REVIEW` | `BLOCKED_SOURCE` | Получен реальный непрерывный ролик, но это one-arm/overhead variant; canonical technique, loop seam и owner visual approval ещё не подтверждены. |
| `romanian-deadlift` | `MOTION_SOURCE_REVIEW` | `BLOCKED_SOURCE` | Exact DVIDS candidate найден, но локальное получение файла не завершено; source SHA и derivative поэтому отсутствуют. |

## Реальный motion candidate

Для `kettlebell-swing` локально обработан только один derivative, без RIFE и без аудио:

| Поле | Значение |
| --- | --- |
| Source | [Wikimedia Commons — Kettlebell Swings AKA Conventional Swings](https://commons.wikimedia.org/wiki/File:Kettlebell_Swings_AKA_Conventional_Swings.webm) |
| License | CC BY-SA 4.0; attribution/share-alike обязательны |
| Source SHA-256 | `4237273b39fc8d9acb97b86457a7b938481450c02f54c9a5bdf49761ff22c869` |
| Source | 640×480, 50 fps, 24.387 s, 1,216 frames, WebM VP8 + Vorbis |
| Derivative | 720×720, H.264, yuv420p, 25 fps, 24.320 s, 608 frames, 2,394,472 bytes, no audio |
| Derivative SHA-256 | `b96d2942ebc1f9b97f02c453c11c3ba1e7cac7926c5ae15763a807647bcdbe1` |
| Transformation | center crop 480×480 → Lanczos 720×720, 25 fps, no interpolation |
| AI interpolation | `no` |
| PTS | `monotonic` по ffprobe |
| Loop seam | `NOT_PASSED`; diagnostic SSIM All=`0.815484`, требуется отдельный visual review |

Производный файл находится только в ignored evidence: `.artifacts/runtime/motion-first-pilot/outputs/kettlebell-swing-wikimedia-720.mp4`. Он не является approved production asset.

## Источник для RDL и почему он не импортирован

[DVIDS — Barbell Romanian Deadlift, video 548437](https://www.dvidshub.net/video/548437/barbell-romanian-deadlift) семантически соответствует упражнению и содержит технику hinge с близким к телу грифом. На странице указано public-domain notice с дополнительными copyright restrictions; это требует сохранить exact page/file evidence. Доступный MP4 endpoint вернул `403`, а неполный 8 KiB response не используется как media и не получает SHA/provenance.

`ab-wheel` не получил замену через похожий rollout, static frame или другой slug. `exercises-media` и OpenGym3D оставлены как исследованные, но не импортированные кандидаты: exact rendered asset и достаточный file-level release evidence для текущего пилота не подтверждены.

## Галерея и проверки

- Локальная HTML-галерея: `.artifacts/runtime/motion-first-pilot/gallery/gallery.html`.
- Контактные листы: `.artifacts/runtime/motion-first-pilot/gallery/contact-sheets/`.
- Машиночитаемая матрица: `1110_MOTION_FIRST_SOURCE_MATRIX.csv`.
- Offline contract: `scripts/motion_first_pilot.py`.
- Unit: `tests/test_motion_first_pilot.py` — 5 passed.

До exact sources для всех трёх ID, technique/anatomy review, seam review и owner visual approval нельзя объявлять пилот готовым, менять production manifest, merge или deploy.
