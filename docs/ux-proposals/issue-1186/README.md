# Issue #1186: квадратная поверхность медиа

Материалы этого каталога фиксируют инвентаризацию, визуальный прототип и проверку approved A для
Issue #1186. Production implementation находится в PR #1221; эти материалы не заменяют
отдельные owner visual acceptance и release approval.

Матрица пересобирается на текущем checkout командой:

```powershell
node scripts/build_issue_1186_media_inventory.mjs
```

Источники матрицы:

- `backend/fitminiapp_api/services/program_seed_data.py` — актуальный seed-каталог;
- `backend/fitminiapp_api/services/exercise_catalog_metadata.py` — canonical redirects;
- `backend/assets/exercise-guides/manifest.json` — runtime-approved media, provenance, размеры и хэши.

`media-inventory.json` содержит матрицу упражнений, `media-file-checks.json` — проверку каждого уникального source-файла, а `media-inventory.csv` — плоскую таблицу для фильтрации. Визуальные варианты находятся в `visual-prototype.html`; PNG-материалы генерируются отдельным воспроизводимым renderer-скриптом.

После owner-направления по приложенному референсу реализован вариант A: квадратная surface,
полный кадр через `object-fit: contain`, нейтральная matte-поверхность без видимой рамки.
Priority/provenance/license/fallback источников сохранены; thumbnails не менялись.

Реальные AFTER для guide card, lightbox и Active Workout: [evidence/after](./evidence/after/). Они сняты в
Chromium на 320/360/393/430 px в Light/Dark; geometry-проверка также проходит в Firefox и WebKit.
Текущий этап: `IMPLEMENTED_AWAITING_AFTER_ACCEPTANCE`. Merge, deploy и закрытие Issue остаются
отдельными owner gates.
