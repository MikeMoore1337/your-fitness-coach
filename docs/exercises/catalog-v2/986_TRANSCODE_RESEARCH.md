# Issue #986 — локальный H.264 transcode + browser playback pilot

Статус: **RESEARCH_ONLY / no production media rollout**. Дата: 2026-10-16. YFC branch `codex/issue-986-hd-media-inventory` (base `8a5c9554`); исходный media source commit `18742da40b0627c85925c5dd4441dc3eac0594d0`. Файлы исходных MP4 и производные videos остаются только в `.artifacts/tasks/986/pilot/` (ignored), **НЕ коммитятся** и не публикуются.

## Воспроизводимые входы и метод

Взяты четыре файла из проверенного candidate subset `986_PILOT_RESULTS.csv`, перед обработкой **полностью сверен SHA-256 каждого MP4** с source inventory: `male/barbell-curl`, `female/barbell-curl`, `male/burpee`, `female/stationary-bike`. Матрица сравнения: 480p, 24fps, H.264 `libx264 -preset medium -crf 29`; 720p, 24fps, `-crf 28`. Без звука; `yuv420p`; progressive MP4 `+faststart`; Lanczos scaler. Не используется генеративный AI, не меняется семантика упражнения.

- Исполнитель: `imageio-ffmpeg` FFmpeg Windows binary `ffmpeg-win-x86_64-v7.1.exe`, SHA-256 `2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3`.
- Пример контролируемого воспроизведения с локальным разрешённым input (вне Git):
  ```bash
  ffmpeg -hide_banner -nostdin -y -i SOURCE.mp4 -an \
    -vf "fps=24,scale=854:480:flags=lanczos,format=yuv420p" \
    -c:v libx264 -preset medium -crf 29 -pix_fmt yuv420p \
    -movflags +faststart -threads 2 OUTPUT-480.mp4
  ```
  Для 720p: `scale=1280:720`, `-crf 28`. Стабильность SHA результатов зависит от точно закреплённой сборки FFmpeg/libx264; output SHA-256 и source SHA-256 для каждой строки заданы в [986_TRANSCODE_BENCH.csv](./986_TRANSCODE_BENCH.csv). Пример запуска через `uv run --no-project --with imageio-ffmpeg python` с `imageio_ffmpeg.get_ffmpeg_exe()`.
- SSIM рассчитан FFmpeg `ssim` после приведения source и result к **одинаковым разрешению и частоте кадров**, поэтому это сравнение качества кодирования **относительно уменьшенного original**, а не доказательство отсутствия потерь от даунскейла относительно 1080p, пригодности техники/амплитуды или человеческой визуальной оценки. Скрипт использовал нормализацию `fps=24,scale=W:H:flags=lanczos,format=yuv420p` для обеих дорожек. Full 1080p source canvas не равнозначен genuine photographic detail.

## Измерения (локальные, raw assets не включены)

| Source | 480p bytes | 480p к GIF | 720p bytes | 720p к GIF | SSIM 480p / 720p |
|---|---:|---:|---:|---:|---:|
| Male barbell-curl | 80 755 | 0.76× | 140 896 | 1.33× | 0.997416 / 0.997958 |
| Female barbell-curl | 82 137 | 0.77× | 146 411 | 1.38× | 0.997752 / 0.998254 |
| Male burpee | 109 332 | 1.09× | 200 132 | 2.00× | 0.997297 / 0.998142 |
| Female stationary-bike | 219 550 | 2.20× | 386 367 | 3.86× | 0.996920 / 0.997746 |

На этих четырёх sample одинакового gender/slug source: суммарно **3 374 151 B raw candidate MP4**, `491 774 B` 480p (**85.4% меньше source**), `873 806 B` 720p (**74.1% меньше source**). Но текущие четыре GIF baseline суммарно `412 269 B`: 480p **1.19×**, 720p **2.12×** их суммарного размера. Это НЕ обосновывает замену всех GIF на видео; длительность исходных роликов отличается, фреймрейт сокращён до 24fps.

## Проверка воспроизведения (headless local desktop only)

Использованы локальные `file://` HTML-video (`muted playsinline preload=auto`), Chromium и WebKit Playwright на Windows (390×844 viewport), для **всех восьми output files**. Ждали metadata, `video.play()` и продвижения playhead `currentTime >= 0.2 sec`. **16/16 PASS**: обе браузерные движки фактически декодировали, нет playback error, оба output profile резолюций прочитаны. Детали: [986_BROWSER_COMPAT.csv](./986_BROWSER_COMPAT.csv). `latency_ms` в CSV — грубое время *до 0.2 секунды playhead*, НЕ network/startup latency (само по себе включает ~200ms воспроизведения). Эти результаты **не подтверждают** физический iPhone/Safari, Telegram WebView/TMA, CPU/battery, first-frame on 3G, RAM, accessibility, poster quality или 2×-retina sharpness. Браузерный тест использовал реальные локально перекодированные файлы, а не видео из текущего production UI.

## Права и владельческие решения

В Issue #986 уже записано owner-confirmed permission **использовать именно `akajdid-mostafa/exercises-media` в YFC**. Повторно просить разрешение *на само использование* не нужно. При этом в публичном source отсутствуют `LICENSE/NOTICE/README` с текстом условий; это не равнозначно доказанным правам на **публичную републикацию оригинальных бинарников, изменённых/перекодированных производных файлов, CDN-хостинг и передачу пользователям приложения**. До выбора конкретного способа распространения документировать подтверждённый scope правообладателя/согласование владельца; не публиковать raw/encoded binaries при `REVIEW`.

## Решение по производству

- **Не включать MP4 в current image/GIF-only manifest v3/API**: потребуется отдельная спецификация v4 или совместимый `<video>` контракт, poster fallback, content hash/same-origin, CSP/cache, lazy playback, reduced motion, error paths, TMA/iOS.
- Дальнейший пилот — локальная device/WebKit/TMA батарея и network/bandwidth/CPU, visual side-by-side с original (без утраты техники/оборудования и off-by-one frames); только семантически проверенные файлы. Остальные 94 review и 99 no-match автоматически не заменять; 39 blocked не разблокировать.
- При текущих размерах 480p — возможный кандидат лишь выборочно по результатам network/performance и реальному визуальному review; 720p существенно тяжелее соответствующего GIF-set. Любое изменение визуального контракта требует отдельно owner design + AFTER и merge/deploy approval.

Никакие production code/assets, manifest/API, environment и CI snapshot этим исследованием не изменены.
