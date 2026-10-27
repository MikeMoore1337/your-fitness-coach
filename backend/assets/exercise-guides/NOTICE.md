# Источник иллюстраций

Активный каталог использует только source-backed Gym visual assets из
[проверенного dataset mirror](https://github.com/hasaneyldrm/exercises-dataset).
Manifest фиксирует owner-purchased GymVisual license, source revision
`7455efae41b330c265e7cd4b78dfa848e7ce5ebd`, exact asset hashes и нулевой remote
runtime. Эти сведения являются частью authoritative schema-3 manifest.

Исторические `free-exercise-db`, `*-technique.jpg`, `human-v1` и generated-media
описания относятся к устаревшим pipeline stages и не являются источником active
production media. AI-generated exercise media не допускается.

`manifest.json` schema v3 является authoritative production manifest: он содержит
206 canonical exercises, 167 approved animated Gym visual assets, 39 blocked entries,
нулевой remote runtime и проверяемые hashes/provenance. Старый
`scripts/build_exercise_guide_media_manifest.py` выведен из эксплуатации и намеренно
не записывает manifest, поскольку он относится к retired schema v2.

Проверяйте активный manifest командой
`python scripts/validate_exercise_catalog.py`. AI-generated exercise media не является
допустимым источником для активного каталога.

Быстрый catalog-wide gate `python scripts/validate_exercise_catalog.py` дополнительно
проверяет required fields, taxonomy, aliases/redirect, media references, SHA-256 и exact
cross-canonical duplicates.
