# #986: additional semantically checked HD posters (2026-10-17)

This follow-up is based on the corrected 73/206 master after PR #1066.
Source revision: `18742da40b0627c85925c5dd4441dc3eac0594d0`.
All original GymVisual GIF animations remain; this import upgrades only still-poster variants.

| YFC canonical slug | Pinned candidate | Equipment / movement | Evidence | Decision |
| --- | --- | --- | --- | --- |
| `t-bar-row` | `male/lever-t-bar-row` | T-bar lever machine, standing bent-over supported-stance row; same figure, exercise, equipment and position as original 180px GymVisual poster | [Before/after](evidence/986-t-bar-row-before-after.jpg) | VERIFIED_SEMANTIC, replace static poster |
| `lying-dumbbell-triceps-extension` | `male/dumbbell-lying-triceps-extension` | Lying flat on a bench, two dumbbells, elbow extension; same pose, movement and equipment as original GymVisual poster | [Before/after](evidence/986-lying-dumbbell-triceps-extension-before-after.jpg) | VERIFIED_SEMANTIC, replace static poster |

Contact sheet: the **left** tile is the pre-import 180x180 GymVisual poster enlarged for comparison only. The **right** tile is the authorized 1920x1080 candidate reduced to 640x360 for convenient review. Do not mistake the enlarged 180px comparison for native HD. These proof images are not production assets.

The importer verifies the exact pinned Git revision and Git blob SHA-1/byte size of the 1920x1080 source image and creates responsive 640/1280/1920 JPEG/WebP derivatives with SHA-256 integrity metadata. Source rights and published derivatives are authorized by the project owner.

Post-release owner visual validation and physical iPhone/Telegram Mini App checks remain open under Issue #986. No attempt is made to upgrade either exercise's GIF to video. Other REVIEW/NO_MATCH records are retained until semantic evidence supports them.

Target after this patch: **75/206 HD posters**, **71** replacements, **4** newly populated static-only exercises, **37 REVIEW**, **94 NO_MATCH**. The two disputed entries from PR #1066 (`chin-up`, `russian-twist`) stay unverified and display their original GIF/poster.
