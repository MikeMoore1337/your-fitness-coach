# Issue #1186: квадратная поверхность медиа

Материалы этого каталога относятся к обязательным этапам инвентаризации и визуального прототипа. Они не изменяют production UI и не являются визуальным одобрением.

Матрица пересобирается на текущем checkout командой:

```powershell
node scripts/build_issue_1186_media_inventory.mjs
```

Источники матрицы:

- `backend/fitminiapp_api/services/program_seed_data.py` — актуальный seed-каталог;
- `backend/fitminiapp_api/services/exercise_catalog_metadata.py` — canonical redirects;
- `backend/assets/exercise-guides/manifest.json` — runtime-approved media, provenance, размеры и хэши.

`media-inventory.json` содержит матрицу упражнений, `media-file-checks.json` — проверку каждого уникального source-файла, а `media-inventory.csv` — плоскую таблицу для фильтрации. Визуальные варианты находятся в `visual-prototype.html`; PNG-материалы генерируются отдельным воспроизводимым renderer-скриптом.

Текущий этап: `WAITING_FOR_OWNER_VISUAL_APPROVAL`. До явного `APPROVE` или `REQUEST CHANGES` изменения в `TodayWorkout.tsx`, `ExerciseMediaAsset.tsx` и `ExerciseGuideMedia.tsx` не вносятся.
