# Issue #1186: квадратная поверхность медиа

Материалы фиксируют пересчитанную инвентаризацию, source-aware framing и браузерские AFTER для
Issue #1186. Production implementation находится в Draft PR #1221; эти материалы не заменяют
отдельные owner visual acceptance и release approval.

Инвентаризация пересобирается на текущем checkout командой:

```powershell
node scripts/build_issue_1186_media_inventory.mjs
```

Источники матрицы:

- `backend/fitminiapp_api/services/program_seed_data.py` — актуальный seed-каталог;
- `backend/fitminiapp_api/services/exercise_catalog_metadata.py` — canonical redirects;
- `backend/assets/exercise-guides/manifest.json` — runtime-approved media, provenance, размеры и хэши.

`media-inventory.json` содержит матрицу упражнений, `media-file-checks.json` — проверку каждого уникального source-файла, а `media-inventory.csv` — плоскую таблицу для фильтрации. Визуальные варианты находятся в `visual-prototype.html`; PNG-материалы генерируются отдельным воспроизводимым renderer-скриптом.

После owner REQUEST CHANGES прежний contain-вариант удалён из production framing. Для 77 широких
источников проверены start/middle/end MP4-кадры: 73 получают заполненный квадрат через
`object-fit: cover` и source-aware focal point, 4 body-spanning источника остаются точечными
`contain-exception`, потому что безопасный crop удаляет существенную часть техники. 94 квадратных
источника сохраняют native 1:1 отображение. 35 blocked-записей не получают неподтверждённое
медиа. Priority/provenance/license/fallback источников сохранены; thumbnails не менялись.

Source-aware framing: [JSON](./media-framing-matrix.json), [CSV](./media-framing-matrix.csv),
конфигурация [exerciseMediaFraming.json](../../../frontend/src/features/exercises/exerciseMediaFraming.json).
Воспроизводимая сборка матрицы:

```powershell
node scripts/build_issue_1186_framing_matrix.mjs
```

Прототип стратегии: [visual-prototype.html](./visual-prototype.html). Реальные AFTER для guide
card, lightbox и Active Workout находятся в [evidence/after-cover](./evidence/after-cover/):
Chromium, 320/360/393/430 px, Light/Dark, реальный MP4 16:9 и native square GIF. Полные
контактные листы 77 wide sources и start/middle/end проверка находятся в
[evidence/motion-review](./evidence/motion-review/).

Текущий этап: `IMPLEMENTED_AWAITING_OWNER_VISUAL_APPROVAL`. PR остаётся Draft; merge, deploy и
закрытие Issue не выполнялись и ждут отдельного owner approval и очереди релизов.
