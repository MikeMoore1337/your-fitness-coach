# Пилот RIFE-интерполяции кадров для анимаций упражнений

Статус: технический пилот завершён; ручная визуальная приёмка владельца, PR CI, merge и release
не выполнены.

## Цель и границы

Проверить на реальном GPU, можно ли повысить плавность восьми AI-upscaled анимаций из контекста
Issue #986, не меняя production catalog. Пилот не публикует новые MP4, не меняет `manifest.json`,
не добавляет модели/бинарные файлы и не заменяет ручную проверку корректности техники.

Кандидаты: `ab-wheel`, `leg-press`, `romanian-deadlift`, `kettlebell-swing`, `treadmill-walk`,
`assault-bike`, `turkish-get-up`, `dragon-flag`.

## Метод

- Источник: локальный checkout PR #1109, commit
  `a1755e1c6bde5dff03b8f2b3ea370e0f700948e0`; принимаются только approved
  `ai_upscaled_gymvisual` MP4 с provenance на исходный GIF.
- Runtime: официальный `rife-ncnn-vulkan` `20221029`, модель `rife-v4`, NVIDIA GeForce RTX 4060 Ti,
  driver `617.42`, FFmpeg `9.0.2`.
- Для каждого кандидата построены варианты `8`, `12` и `16 FPS`. План использует реальные PTS
  source MP4, сохраняет anchor-кадры и вызывает RIFE для промежуточных пар с дробным timestep.
  Циклическое соединение последнего кадра с первым не выполняется.
- Выход: H.264, `yuv420p`, `720×720`, без аудио. Все записи и исходные SHA защищены resume-проверкой.

## Результаты

| Кандидат | Источник | 8 FPS | 12 FPS | 16 FPS | delta длительности |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ab-wheel` | 12 кадров / 3,0 с | 24 | 36 | 48 | 0 мс |
| `leg-press` | 12 / 3,0 с | 24 | 36 | 48 | 0 мс |
| `romanian-deadlift` | 12 / 3,0 с | 24 | 36 | 48 | 0 мс |
| `kettlebell-swing` | 12 / 3,0 с | 24 | 36 | 48 | 0 мс |
| `treadmill-walk` | 24 / 5,0 с | 40 | 60 | 80 | 0 мс |
| `assault-bike` | 24 / 5,0 с | 40 | 60 | 80 | 0 мс |
| `turkish-get-up` | 54 / 9,5 с | 76 | 114 | 152 | 0 мс |
| `dragon-flag` | 12 / 2,1 с | 17 | 25 | 34 | +25 / −16,67 / +25 мс |

Итого: 24 варианта, 1 117 сгенерированных промежуточных кадров. Все 24 прошли технический QC:
полный decode, ожидаемое число кадров, монотонные PTS, один видеопоток без аудио, H.264/yuv420p и
720×720. SHA-256 всех 16 исходных GIF/MP4 после прогона совпали с manifest/report.

Округление `dragon-flag` явно отражено в отчёте: CFR не позволяет одновременно сохранить
2,1 секунды и целое число кадров на 8/12/16 FPS. Это техническая delta, а не утверждение о
точной длительности исходной GIF-анимации.

## Локальные артефакты

После запуска команды из `scripts/interpolate_exercise_videos.py` результаты находятся в
`.artifacts/runtime/986-frame-interpolation-pilot-rife-v1/`:

- `processing-report.json` — сводный отчёт, provenance и SHA;
- `<slug>/source-frames/source-frames.json` — реальные source PTS;
- `<slug>/<fps>fps/plan.json` и `variant.json` — план, runtime/model signature и QC;
- `gallery/gallery.html` — локальное сравнение исходной GIF, AI-upscale и трёх RIFE-вариантов;
- `contact-sheet-phases.jpg` и `contact-sheet-motion.jpg` — 16 contact sheets.

Артефакты ignored и намеренно не входят в PR. Скрипт отказывается перезаписывать несовпадающие
или частичные результаты.

## Приёмка и следующие gates

Локальные pytest/Ruff и технический GPU-QC пройдены. Визуальная оценка каждого кандидата и
частоты, особенно на участках с ghosting/warping, остаётся отдельным owner gate. До неё нельзя
считать результат production-ready; физический iPhone/Safari, native Telegram Mini App,
VoiceOver и production smoke этим пилотом не проверялись.

Официальные ссылки на выбранный runtime: [ECCV2022-RIFE](https://github.com/hzwer/ECCV2022-RIFE),
[rife-ncnn-vulkan README](https://github.com/nihui/rife-ncnn-vulkan/blob/master/README.md?plain=1),
[rife-ncnn-vulkan `main.cpp`](https://github.com/nihui/rife-ncnn-vulkan/blob/master/src/main.cpp).
