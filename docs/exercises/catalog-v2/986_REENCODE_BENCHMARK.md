# Issue #986 — bounded deterministic re-encode benchmark

Статус: `RESEARCH_ONLY / 2-SLUG LOCAL ENCODE MEASURED; REAL-DEVICE/RIGHTS GATES OPEN`
Дата проверки: `2026-10-16`
Исходник: [`akajdid-mostafa/exercises-media@18742da40b0627c85925c5dd4441dc3eac0594d0`](https://github.com/akajdid-mostafa/exercises-media/tree/18742da40b0627c85925c5dd4441dc3eac0594d0)
YFC worktree HEAD: `fa31a21382440bc8015086cfdd1e64704a3c2ecf`

## Итог

На первом, sandbox-only этапе перекодирование имело статус **NOT_RUN**: `ffmpeg` и
`ffprobe` отсутствовали в стандартном `PATH`, а поиск в проверенных локальных каталогах установки
не дал исполняемых файлов. В этом первом запуске инструменты не устанавливались, а поля baseline не заполнялись догадками. **Позднее отдельным контролируемым запуском получены реальные метрики на двух других verified-slug — см. приложение ниже.** В первоначальном отчёте нет
придуманных значений для encoded bytes, codec/container, quality metrics, frame
count, encoded FPS или playback.

Исходные candidate MP4 и текущие 180px GIF доступны локально и проверены по
размеру и SHA-256. Никакие MP4, JPG, WebM, MP4 derivative или poster derivative
не создавались и не добавлялись в Git. Воспроизводимые команды для отдельной
машины с FFmpeg приведены ниже; их результаты нужно сохранить как приватные
локальные данные и перенести в отчёт только метаданными.

## Границы выборки

Выбраны четыре уже существующие строки `VERIFIED_SEMANTIC` из 13 подтверждённых
candidate slug. Они покрывают короткое силовое движение, полное движение тела,
циклическое быстрое движение и длинное cardio-движение. `REVIEW`-строки не
перепроверялись и не разблокировались.

Исходные candidate bytes лежат только в ignored-каталоге
`.artifacts/tasks/986/pilot/raw/videos/female/`; current GIF — tracked asset YFC.
Ниже приведены фактические локальные метаданные из bounded pilot и повторной
проверки SHA-256.

| slug | candidate source | source SHA-256 | source bytes | source video | source frames / duration / FPS | current GIF | GIF SHA-256 | GIF bytes | GIF dimensions / frames / duration | source/GIF bytes |
|---|---|---|---:|---|---:|---|---|---:|---:|---:|
| `barbell-curl` | `public/videos/female/barbell-curl.mp4` | `9114a62db52ad88c31bc4e32cf566c6778b5af613c9bb313def0f26131a2d4d8` | 693,100 | 1920×1080 / H.264 `avc1` | 197 / 6.566667 s / 30.0 | `gymvisual/barbell-curl-0031-25GPyDY.gif` | `3907d2a2561b7afa76a5b8c4af4237b5f424b11bb8a350175ae73aaaf532021a` | 106,020 | 180×180 / 12 / 3.0 s | 6.5374× |
| `burpee` | `public/videos/female/burpee.mp4` | `9b67d7c02c21baed696ceeb3e4525c3697b42282f8bf1295d7b7394cb154443b` | 803,161 | 1920×1080 / H.264 `avc1` | 227 / 7.566667 s / 30.0 | `gymvisual/burpee-1160-dK9394r.gif` | `d2e45138b446c4c7eced4496554736068ef66a61bd553c5fe284e3ed8aa44c53` | 100,254 | 180×180 / 30 / 5.5 s | 8.0113× |
| `jump-rope` | `public/videos/female/jump-rope.mp4` | `7d67e293bf40158d7cda110630f2e5a7430309e1528017508f576f35d6696c81` | 557,510 | 1920×1080 / H.264 `avc1` | 148 / 4.933333 s / 30.0 | `gymvisual/jump-rope-2612-e1e76I2.gif` | `4590924327d2689fb2d8419e93f8485438031812767a14684dece560ca3f77b1` | 62,427 | 180×180 / 12 / 3.0 s | 8.9306× |
| `stationary-bike` | `public/videos/female/stationary-bike.mp4` | `8cba417644d4b371938b5c40e0b9064980868c9f8575748eb774f97b58f705ee` | 1,667,626 | 1920×1080 / H.264 `avc1` | 591 / 19.7 s / 30.0 | `gymvisual/stationary-bike-2138-H1PESYI.gif` | `9ddd3ef3fd2cb138df8f427435baacc73d838ff47c2363ea2c4ffa81e0d13a5f` | 99,975 | 180×180 / 12 / 3.0 s | 16.6804× |

`source/GIF bytes` — это только отношение локальных файлов. Это не network
waterfall, не фактически переданные HTTP bytes и не оценка RAM/CPU.

## Blocker и незаполненные поля

Проверки 2026-10-16:

| Поле | Результат |
|---|---|
| `ffmpeg` version | `NOT_AVAILABLE` — команда не найдена |
| `ffprobe` version | `NOT_AVAILABLE` — команда не найдена |
| H.264 MP4 output bytes/hash | `NOT_RUN` |
| VP9 WebM output bytes/hash | `NOT_RUN` |
| Encoded resolution, duration, frame count, FPS | `NOT_RUN` |
| PSNR / SSIM | `NOT_RUN` |
| VMAF | `NOT_RUN` и требует отдельной проверки наличия фильтра |
| Perceptual fidelity | `NOT_RUN` |
| Technique/equipment fidelity after encode | `NOT_RUN`; codec metric это не доказывает |
| Browser decode/compatibility | `NOT_VERIFIED` |
| Network waterfall, CPU/RAM, physical iPhone/Safari/TMA | `NOT_MEASURED` / `NOT_VERIFIED` |

## Offline benchmark instructions

Команды ниже предназначены для отдельной машины, где FFmpeg уже установлен и
допущен владельцем. Они используют только четыре уже скачанных female MP4,
создают результаты в ignored-каталоге и фиксируют одинаковые целевые параметры:
`640×360`, `15 FPS`, без звука, `threads=1`. Эти параметры — benchmark profile,
а не одобренный production budget.

```powershell
$bench = '.artifacts/tasks/986/pilot/codec-benchmark-20261016'
New-Item -ItemType Directory -Force $bench | Out-Null
$slugs = @('barbell-curl', 'burpee', 'jump-rope', 'stationary-bike')

ffmpeg -hide_banner -version
ffprobe -hide_banner -version

foreach ($slug in $slugs) {
  $src = ".artifacts/tasks/986/pilot/raw/videos/female/$slug.mp4"

  ffmpeg -hide_banner -y -i $src -an `
    -vf "scale=640:360:flags=lanczos,fps=15" `
    -c:v libx264 -preset medium -crf 23 -profile:v main -level:v 3.1 `
    -pix_fmt yuv420p -movflags +faststart -threads 1 `
    "$bench/$slug-h264.mp4"

  ffmpeg -hide_banner -y -i $src -an `
    -vf "scale=640:360:flags=lanczos,fps=15" `
    -c:v libvpx-vp9 -b:v 0 -crf 34 -deadline good -cpu-used 0 `
    -row-mt 0 -tile-columns 0 -frame-parallel 0 -threads 1 `
    "$bench/$slug-vp9.webm"
}
```

Для каждого output зафиксировать команду из shell history, полную версию
FFmpeg, локальный file size и SHA-256:

```powershell
Get-ChildItem $bench -File | Select-Object Name,Length
Get-ChildItem $bench -File | Get-FileHash -Algorithm SHA256

foreach ($file in (Get-ChildItem $bench -File)) {
  ffprobe -v error -count_frames -select_streams v:0 `
    -show_entries stream=codec_name,width,height,avg_frame_rate,nb_read_frames,duration `
    -show_entries format=duration,size -of json $file.FullName
}
```

Для качества сравнивать source и его own encoded output после приведения source к
тому же `640×360`, `15 FPS` и `yuv420p`; не сравнивать candidate MP4 напрямую с
180px GIF как будто это один и тот же reference timeline. Если фильтры собраны,
сохранить PSNR и SSIM; наличие `libvmaf` сначала проверить через
`ffmpeg -filters`. При отсутствии фильтра записать `NOT_AVAILABLE`, а не
подменять результат субъективной оценкой.

```powershell
$src = '.artifacts/tasks/986/pilot/raw/videos/female/barbell-curl.mp4'
$enc = "$bench/barbell-curl-h264.mp4"
ffmpeg -hide_banner -i $src -i $enc `
  -filter_complex "[0:v]scale=640:360:flags=lanczos,fps=15,format=yuv420p,setpts=PTS-STARTPTS[ref];[1:v]format=yuv420p,setpts=PTS-STARTPTS[test];[ref][test]ssim=stats_file=$bench/barbell-curl-h264-ssim.log" `
  -f null NUL

ffmpeg -hide_banner -i $src -i $enc `
  -filter_complex "[0:v]scale=640:360:flags=lanczos,fps=15,format=yuv420p,setpts=PTS-STARTPTS[ref];[1:v]format=yuv420p,setpts=PTS-STARTPTS[test];[ref][test]psnr=stats_file=$bench/barbell-curl-h264-psnr.log" `
  -f null NUL
```

Perceptual/technique fidelity проверять отдельно: сделать локальный contact sheet
одинаковых временных точек source/output и вручную отметить `PRESERVED` либо
`REVIEW` для identity, equipment, orientation, movement phases и loop boundary.
PSNR/SSIM/VMAF не заменяют semantic/domain review и не разрешают автоматический
перевод строки в `VERIFIED`.

## Практический mobile/browser вывод

- В этой выборке source MP4 занимают 557,510–1,667,626 B, а текущие GIF —
  62,427–106,020 B. Это измеренный локальный payload signal: полный source file
  заметно тяжелее текущего GIF для каждого выбранного slug.
- Candidate poster bytes для этих четырёх female rows: 67,951 B, 49,580 B,
  60,002 B и 91,556 B соответственно. Это размер локальных JPG, а не доказанная
  browser transfer cost или разрешение для bundling.
- Если media contract когда-либо будет одобрен, poster-first и загрузка видео
  только по явному намерению — необходимая проверяемая гипотеза для ограничения
  initial transfer. `preload`, cache и range behavior здесь не измерялись.
- Для `prefers-reduced-motion` результатом должен быть статический poster без
  воспроизведения; текстовая техника и доступный fallback должны оставаться.
  Ошибка decode/network должна возвращать approved fallback, а не пустой блок.
- Browser codec matrix, Chromium/WebKit playback, Telegram Mini App и физический
  iPhone/Safari в этом run не проверялись. Нельзя выводить из локальных bytes
  совместимость, RAM, network time или native-device experience.

## Права и отдельные gates

Эти вопросы не объединяются в один общий «разрешено»:

1. **Создание derivative:** owner подтвердил конкретное использование указанного
   source candidate для исследования. Это не доказывает отдельное право
   транскодировать, менять размер, извлекать poster или создавать derivative для
   production distribution. В этой сессии derivative не создавались.
2. **Redistribution/bundling:** public GitHub source без `LICENSE`, `NOTICE` или
   file-level terms не доказывает право публично включать candidate или derivative
   в YFC. Owner permission для исследования не является подтверждением public
   redistribution; этот gate остаётся `REVIEW`.
3. **Caching/serving:** хранение и раздача derivative через same-origin static
   assets, browser cache, CDN или range requests — отдельная operational/product
   модель. Текущая GIF cache policy не является разрешением на новый media type и
   не подтверждает права на candidate files.
4. **Commercial use:** commercial bundling, paid product use и sublicensing не
   подтверждены. Публичность репозитория и отсутствие видимой лицензии не дают
   основания считать commercial use разрешённым.

## Сохранённые статусы и решение владельца

В этом исследовании не менялись `986_COVERAGE_MATRIX.csv`, manifest, API или
production assets. Сохранены:

- `13 VERIFIED` (из них техническая выборка выше — только 4);
- `94 REVIEW` без автоматической разблокировки;
- `99 NO_MATCH`;
- все `39 blocked` без media и без назначения похожего упражнения.

До следующего шага владельцу нужно отдельно решить:

1. разрешены ли deterministic derivative operations для точной ревизии source;
2. разрешены ли bundling, redistribution, caching/serving и commercial use;
3. какой media contract и mobile quality/byte budget допустим;
4. нужна ли повторная visual/domain review после фактического encode.

До этих решений benchmark остаётся `BLOCKED_FFMPEG_UNAVAILABLE / REVIEW`, а
production implementation, merge, deploy и Issue close не следуют из этого отчёта.


---

## Дополнение: фактическое локальное перекодирование двух VERIFIED candidate — 16.10.2026

После первоначального `NOT_RUN` получен отдельный FFmpeg через изолированный `uv run --no-project --with imageio-ffmpeg --python 3.14`. Исполняемый файл FFmpeg v7.1 из пакета `imageio-ffmpeg` доступен на авторизованном Windows-компьютере; глобальный Python и проектные зависимости не менялись. Исполнены только локальные конверсии двух уже скачанных candidate videos `female/squat.mp4` и `female/cable-lateral-raise.mp4`, оба из закреплённого источника `18742da40b0627c85925c5dd4441dc3eac0594d0`.

Все выходные MP4/WebM находятся **только в игнорируемом локальном каталоге** `.artifacts/tasks/986/pilot/reencoded/`. Ни один исходный или производный медиафайл не включён в Git, PR, сборку, продакшен или внешнюю публикацию.

### Воспроизводимые параметры

- H.264 MP4: `-nostdin -i SOURCE -map 0:v:0 -vf scale=854:480:flags=lanczos -an -c:v libx264 -preset veryfast -crf 28 -threads 2 -pix_fmt yuv420p -movflags +faststart OUTPUT.mp4`.
- VP9 WebM: `-nostdin -i SOURCE -map 0:v:0 -vf scale=854:480:flags=lanczos -an -c:v libvpx-vp9 -deadline good -cpu-used 4 -b:v 0 -crf 36 -threads 2 -pix_fmt yuv420p OUTPUT.webm`.
- SSIM: `ffmpeg -i SOURCE -i ENCODED -filter_complex '[0:v]fps=30,scale=854:480:flags=lanczos,format=yuv420p,settb=AVTB,setpts=N/(30*TB)[ref];[1:v]fps=30,format=yuv420p,settb=AVTB,setpts=N/(30*TB)[dist];[ref][dist]ssim' -an -f null NUL`. Это синхронизированное сравнение *одного и того же candidate-видео* после ресемплинга, а **не сравнение с другим по сюжету GymVisual GIF**.

| Verified slug (female) | Original MP4 bytes | H.264 480p bytes | H.264 / original | SSIM H.264 | VP9 480p bytes | VP9 / original | SSIM VP9 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `squat` | 737,304 | 82,199 | 11.1% | 0.996780 | 214,239 | 29.1% | 0.998827 |
| `cable-lateral-raise` | 545,513 | 77,573 | 14.2% | 0.995777 | 196,729 | 36.1% | 0.998783 |

SSIM получен с нормализацией timebase/fps обеих сторон; предварительное сравнение VP9 без нормализации имело предупреждение `not matching timebases` и **не используется**. Оба набора созданы с разными параметрами качества, поэтому это **bounded comparison настроек**, а не доказательство того, что H.264 объективно лучше VP9 при равном perceptual quality. При этих конкретных настройках H.264 значительно компактнее, VP9 имеет более высокий SSIM к ресайзнутому источнику.

### Что доказано и что НЕ доказано

- **MEASURED**: реальное перекодирование 2 движений × 2 профиля, фактический размер локальных файлов, кодек и одинаковое разрешение цели 854×480; численный SSIM относительно исходного candidate-видео в том же пространственном/временном представлении.
- **NOT VERIFIED**: сопоставимость техники с упражнением YFC по полным фазам движения (нужна отдельная ручная визуальная экспертиза); точность/фактическая HD-детализация исходного движения; реальный mobile Safari/WebKit/TMA decode, network waterfall, RAM/CPU, батарея, poster/reduced-motion и пользовательская плавность.
- **LEGAL OWNER GATE**: право исследовать и локально конвертировать данные подтверждено пользователем для этого пилота, но разрешение на публичное распространение производных MP4/WebM, включение в открытый YFC repo, коммерческий production bundling, CDN/кеширование и предоставление файлов третьим сторонам должно быть подтверждено отдельно. Отсутствие LICENSE/NOTICE в candidate GitHub repo не равно разрешению на redistribution.
- **PRODUCTION GATE**: контракт GIF-only остаётся. Все 39 blocked остаются blocked; `REVIEW`-кандидаты не включены. Нельзя автоматически переключать контент на video/VP9 без отдельного schema/API/frontend и visual/performance доказательства, разрешения владельца и CI.

Следующий честный этап: на выбранных кандидатах провести ручную покадровую проверку identity/equipment/range/side, браузерные измерения transfer/decode на реальных телефонах, сравнить poster/reduced-motion и подтвердить отдельные права на использование производных файлов. Эксперимент сам по себе **не разрешает** merge/deploy.
