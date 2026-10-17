# Issue #986 — полное HD-покрытие каталога

Отчёт построен универсальным импортёром из закреплённой матрицы `986_HD_MAPPING.csv`.
Импорт выполняется без сетевых запросов и записывает только `VERIFIED_SEMANTIC` / `high` сопоставления; `REVIEW` остаются без импорта.

## Итог

- Canonical exercises: **206**.
- HD-покрытие по подтверждённой матрице: **73/206 (35.44%)**.
- Подтверждённых HD-постеров для существующего media: **69**.
- Новых статических изображений для ранее пустых записей: **4**.
- Осталось без подтверждённого HD: **133**.
- Из них `REVIEW`: **39**, `NO_MATCH`: **94**.
- После импорта approved animated: **167**.
- После импорта approved static: **4**.
- После импорта blocked: **35**.
- Runtime assets: **707 файлов / 35,592,679 байт** (origin/master до импорта: 334 файлов / 18,352,704 байт; изменение: +17,239,975 байт).

## Контракт обработки

- Источник: `https://github.com/akajdid-mostafa/exercises-media` at `18742da40b0627c85925c5dd4441dc3eac0594d0`.
- `previous_*` берутся из неизменяемой исходной матрицы до импорта; `current_*` — из текущего результата.
- Проверены source path, размер, Git blob SHA-1, JPEG 1920×1080 и контрольная сумма SHA-256.
- Производные: 640/1280/1920 px, WebP и JPEG fallback, RGB, без EXIF/GPS; пропорция 16:9 сохранена.
- Для существующих GIF/H.264 сохранён текущий animated/video путь; HD-постер становится предпочтительным статическим fallback.
- Для новых записей используется `type=image`; MP4 не записывается в image-поля API.

## Ограничения и риски

`REVIEW` и `NO_MATCH` из полной исторической матрицы не были повышены автоматически. Наличие изображения в источнике само по себе не считается доказательством техники. Проверка физического iPhone/TMA, production smoke и визуальная приёмка владельца остаются post-release gates.

## Пропущенные записи

- `dumbbell-bench-press` — Источник не подтверждён семантически; оставить текущий media/fallback
- `low-to-high-cable-fly` — Источник не подтверждён семантически; оставить текущий media/fallback
- `machine-chest-press` — Источник не подтверждён семантически; оставить текущий media/fallback
- `independent-lever-chest-press` — Источник не подтверждён семантически; оставить текущий media/fallback
- `machine-decline-chest-press` — Источник не подтверждён семантически; оставить текущий media/fallback
- `smith-bench-press` — Источник не подтверждён семантически; оставить текущий media/fallback
- `weighted-dip` — Источник не подтверждён семантически; оставить текущий media/fallback
- `chest-dip` — Источник не подтверждён семантически; оставить текущий media/fallback
- `dumbbell-pullover` — Источник не подтверждён семантически; оставить текущий media/fallback
- `deadlift` — Источник не подтверждён семантически; оставить текущий media/fallback
- `rack-pull` — Источник не подтверждён семантически; оставить текущий media/fallback
- `pull-up` — Источник не подтверждён семантически; оставить текущий media/fallback
- `chin-up` — REVIEW: источник обозначает chin-up/pull-up; канонический хват chin-up не подтверждён
- `barbell-row` — Источник не подтверждён семантически; оставить текущий media/fallback
- `pendlay-row` — Источник не подтверждён семантически; оставить текущий media/fallback
- `t-bar-row` — Источник не подтверждён семантически; оставить текущий media/fallback
- `one-arm-dumbbell-row` — Источник не подтверждён семантически; оставить текущий media/fallback
- `chest-supported-row` — Подходящий HD-источник не подтверждён; blocked не снимать
- `seated-cable-row` — Источник не подтверждён семантически; оставить текущий media/fallback
- `machine-row` — Источник не подтверждён семантически; оставить текущий media/fallback
- `lever-low-row` — Подходящий HD-источник не подтверждён; blocked не снимать
- `independent-lever-lat-pulldown` — Подходящий HD-источник не подтверждён; blocked не снимать
- `machine-pullover` — Источник не подтверждён семантически; оставить текущий media/fallback
- `chest-supported-dumbbell-row` — Источник не подтверждён семантически; оставить текущий media/fallback
- `inverted-row` — Источник не подтверждён семантически; оставить текущий media/fallback
- `meadows-row` — Подходящий HD-источник не подтверждён; blocked не снимать
- `cable-row-one-arm` — Источник не подтверждён семантически; оставить текущий media/fallback
- `good-morning` — Источник не подтверждён семантически; оставить текущий media/fallback
- `smith-squat` — Источник не подтверждён семантически; оставить текущий media/fallback
- `belt-squat` — Подходящий HD-источник не подтверждён; blocked не снимать
- `leg-press` — Источник не подтверждён семантически; оставить текущий media/fallback
- `pendulum-squat` — Подходящий HD-источник не подтверждён; blocked не снимать
- `plate-loaded-leg-press` — Источник не подтверждён семантически; оставить текущий media/fallback
- `unilateral-leg-press` — Источник не подтверждён семантически; оставить текущий media/fallback
- `v-squat-machine` — Подходящий HD-источник не подтверждён; blocked не снимать
- `lunge` — Источник не подтверждён семантически; оставить текущий media/fallback
- `walking-lunge` — Источник не подтверждён семантически; оставить текущий media/fallback
- `reverse-lunge` — Источник не подтверждён семантически; оставить текущий media/fallback
- `bulgarian-split-squat` — Источник не подтверждён семантически; оставить текущий media/fallback
- `split-squat` — Источник не подтверждён семантически; оставить текущий media/fallback
- `smith-split-squat` — Источник не подтверждён семантически; оставить текущий media/fallback
- `step-up` — Источник не подтверждён семантически; оставить текущий media/fallback
- `sissy-squat` — Источник не подтверждён семантически; оставить текущий media/fallback
- `wall-sit` — Подходящий HD-источник не подтверждён; blocked не снимать
- `romanian-deadlift` — Источник не подтверждён семантически; оставить текущий media/fallback
- `single-leg-rdl` — Источник не подтверждён семантически; оставить текущий media/fallback
- `standing-leg-curl` — Подходящий HD-источник не подтверждён; blocked не снимать
- `nordic-curl` — Источник не подтверждён семантически; оставить текущий media/fallback
- `glute-ham-raise` — Источник не подтверждён семантически; оставить текущий media/fallback
- `hip-thrust` — Источник не подтверждён семантически; оставить текущий media/fallback
- `single-leg-hip-thrust` — Подходящий HD-источник не подтверждён; blocked не снимать
- `bodyweight-glute-bridge` — Источник не подтверждён семантически; оставить текущий media/fallback
- `barbell-glute-bridge` — Источник не подтверждён семантически; оставить текущий media/fallback
- `machine-hip-thrust` — Подходящий HD-источник не подтверждён; blocked не снимать
- `cable-pull-through` — Источник не подтверждён семантически; оставить текущий media/fallback
- `kettlebell-swing` — Источник не подтверждён семантически; оставить текущий media/fallback
- `cable-kickback` — Источник не подтверждён семантически; оставить текущий media/fallback
- `sumo-deadlift` — Источник не подтверждён семантически; оставить текущий media/fallback
- `overhead-press` — Источник не подтверждён семантически; оставить текущий media/fallback
- `machine-shoulder-press` — Источник не подтверждён семантически; оставить текущий media/fallback
- `independent-lever-shoulder-press` — Источник не подтверждён семантически; оставить текущий media/fallback
- `landmine-press` — Подходящий HD-источник не подтверждён; blocked не снимать
- `rear-delt-fly` — Источник не подтверждён семантически; оставить текущий media/fallback
- `face-pull` — Подходящий HD-источник не подтверждён; blocked не снимать
- `upright-row` — Источник не подтверждён семантически; оставить текущий media/fallback
- `y-raise` — Источник не подтверждён семантически; оставить текущий media/fallback
- `hammer-curl` — Источник не подтверждён семантически; оставить текущий media/fallback
- `cable-curl` — Источник не подтверждён семантически; оставить текущий media/fallback
- `reverse-curl` — Источник не подтверждён семантически; оставить текущий media/fallback
- `spider-curl` — Источник не подтверждён семантически; оставить текущий media/fallback
- `machine-biceps-curl` — Источник не подтверждён семантически; оставить текущий media/fallback
- `skull-crusher` — Источник не подтверждён семантически; оставить текущий media/fallback
- `dumbbell-overhead-extension` — Источник не подтверждён семантически; оставить текущий media/fallback
- `lying-dumbbell-triceps-extension` — Источник не подтверждён семантически; оставить текущий media/fallback
- `bench-dip` — Источник не подтверждён семантически; оставить текущий media/fallback
- `triceps-kickback` — Источник не подтверждён семантически; оставить текущий media/fallback
- `machine-dip` — Источник не подтверждён семантически; оставить текущий media/fallback
- `single-leg-calf-raise` — Источник не подтверждён семантически; оставить текущий media/fallback
- `crunch` — Источник не подтверждён семантически; оставить текущий media/fallback
- `dead-hang` — Подходящий HD-источник не подтверждён; blocked не снимать
- `captain-chair-leg-raise` — Источник не подтверждён семантически; оставить текущий media/fallback
- `ab-wheel` — Источник не подтверждён семантически; оставить текущий media/fallback
- `russian-twist` — REVIEW: вариант с другим оборудованием; сохранить исходный GIF до отдельного подтверждения
- `pallof-press` — Подходящий HD-источник не подтверждён; blocked не снимать
- `mountain-climber` — Источник не подтверждён семантически; оставить текущий media/fallback
- `hollow-hold` — Подходящий HD-источник не подтверждён; blocked не снимать
- `dead-bug` — Источник не подтверждён семантически; оставить текущий media/fallback
- `bird-dog` — Подходящий HD-источник не подтверждён; blocked не снимать
- `box-jump` — Подходящий HD-источник не подтверждён; blocked не снимать
- `rowing-machine` — Подходящий HD-источник не подтверждён; blocked не снимать
- `treadmill-run` — Источник не подтверждён семантически; оставить текущий media/fallback
- `assault-bike` — Источник не подтверждён семантически; оставить текущий media/fallback
- `outdoor-run` — Источник не подтверждён семантически; оставить текущий media/fallback
- `outdoor-cycling` — Подходящий HD-источник не подтверждён; blocked не снимать
- `recumbent-bike` — Подходящий HD-источник не подтверждён; blocked не снимать
- `outdoor-walk` — Подходящий HD-источник не подтверждён; blocked не снимать
- `treadmill-walk` — Источник не подтверждён семантически; оставить текущий media/fallback
- `stair-climber` — Источник не подтверждён семантически; оставить текущий media/fallback
- `swimming` — Подходящий HD-источник не подтверждён; blocked не снимать
- `ski-erg` — Источник не подтверждён семантически; оставить текущий media/fallback
- `sled-push` — Подходящий HD-источник не подтверждён; blocked не снимать
- `sled-pull` — Подходящий HD-источник не подтверждён; blocked не снимать
- `farmer-walk` — Источник не подтверждён семантически; оставить текущий media/fallback
- `suitcase-carry` — Подходящий HD-источник не подтверждён; blocked не снимать
- `medicine-ball-slam` — Источник не подтверждён семантически; оставить текущий media/fallback
- `wall-ball` — Подходящий HD-источник не подтверждён; blocked не снимать
- `thruster` — Источник не подтверждён семантически; оставить текущий media/fallback
- `kettlebell-clean` — Источник не подтверждён семантически; оставить текущий media/fallback
- `kettlebell-snatch` — Источник не подтверждён семантически; оставить текущий media/fallback
- `turkish-get-up` — Источник не подтверждён семантически; оставить текущий media/fallback
- `renegade-row` — Источник не подтверждён семантически; оставить текущий media/fallback
- `bear-crawl` — Источник не подтверждён семантически; оставить текущий media/fallback
- `floor-press` — Подходящий HD-источник не подтверждён; blocked не снимать
- `push-press` — Подходящий HD-источник не подтверждён; blocked не снимать
- `assisted-pull-ups` — Источник не подтверждён семантически; оставить текущий media/fallback
- `decline-crunch` — Источник не подтверждён семантически; оставить текущий media/fallback
- `pistol-squat` — Источник не подтверждён семантически; оставить текущий media/fallback
- `overhead-squat` — Источник не подтверждён семантически; оставить текущий media/fallback
- `cable-external-rotation` — Источник не подтверждён семантически; оставить текущий media/fallback
- `hanging-knee-raise` — Источник не подтверждён семантически; оставить текущий media/fallback
- `trap-bar-deadlift` — Источник не подтверждён семантически; оставить текущий media/fallback
- `safety-bar-squat` — Подходящий HD-источник не подтверждён; blocked не снимать
- `negative-pull-ups` — Подходящий HD-источник не подтверждён; blocked не снимать
- `scapular-pull-ups` — Источник не подтверждён семантически; оставить текущий media/fallback
- `muscle-ups` — Источник не подтверждён семантически; оставить текущий media/fallback
- `band-pull-apart` — Подходящий HD-источник не подтверждён; blocked не снимать
- `kettlebell-overhead-carry` — Подходящий HD-источник не подтверждён; blocked не снимать
- `dragon-flag` — Источник не подтверждён семантически; оставить текущий media/fallback
- `l-sit` — Источник не подтверждён семантически; оставить текущий media/fallback
- `clean-and-jerk` — Подходящий HD-источник не подтверждён; blocked не снимать
- `hang-power-clean` — Подходящий HD-источник не подтверждён; blocked не снимать
- `wrist-roller` — Источник не подтверждён семантически; оставить текущий media/fallback
- `rope-climb` — Источник не подтверждён семантически; оставить текущий media/fallback
