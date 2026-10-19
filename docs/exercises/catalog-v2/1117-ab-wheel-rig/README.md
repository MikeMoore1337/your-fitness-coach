# Ab Wheel: анатомический видеопилот #1117

**NEEDS_WORK. Профессиональное визуальное качество не достигнуто.** Получен настоящий MP4 с движением одного послойного персонажа, но стыки плеча/таза, пропорции корпуса и наклонная исходная поза не соответствуют всему контракту владельца. Это исследовательский результат, не финальный пакет для визуального одобрения.

## Что воспроизводится

`scripts/ab_wheel_anatomical_pilot.py` рассчитывает кинематику выката с колен: фиксированное колено, постоянные длины сегментов, двухзвенную IK руки, фиксированную высоту оси ролика и вращение по перемещению. Pillow рисует одинаковые текстурированные части с равномерным масштабом и вращением, без деформации сетки, optical flow, crossfade и независимой генерации кадров. Камера постоянна; рендер 1440×1440 уменьшается до 720×720 один раз.

Лицо, шея, голени и стопы взяты из `pose-01-start.png`. Остальные части — из единого анатомического атласа, подготовленного встроенным ImageGen по утверждённым референсам. Атлас получен один раз, не генерируется заново для каждого кадра. Две руки используют одинаковую анатомию с фиксированным смещением глубины. Новый ролик рисуется как жёсткая пара колёс. Это **2.5D cutout**, не полноценная 3D-анатомическая модель. Утверждённая внешность служит ориентиром, точное совпадение не заявлено.

Ранний вариант skinning одной текстуры отклонён до полного рендера из-за растяжения мышц. После него проверен послойный вариант. Известные ограничения сохранены явно; увеличение FPS их не исправляет.

## Зависимость от референсов

Оригиналы находятся в отдельном [Draft PR #1121](https://github.com/MikeMoore1337/your-fitness-coach/pull/1121). Исходники зафиксированы на commit `36b689ebab402f65f60a60b1f15240cb60b4feaa`; изображения не считаются частью `master` до слияния #1121.

- [Утверждённый storyboard](https://github.com/MikeMoore1337/your-fitness-coach/blob/36b689ebab402f65f60a60b1f15240cb60b4feaa/docs/exercises/catalog-v2/1117-ab-wheel-anatomical-reference/approved-storyboard.png)
- [Manifest всех восьми PNG](https://github.com/MikeMoore1337/your-fitness-coach/blob/36b689ebab402f65f60a60b1f15240cb60b4feaa/docs/exercises/catalog-v2/1117-ab-wheel-anatomical-reference/manifest.json)

Первичный ZIP проверен: CRC, отсутствие выхода путей и symlink, 8 PNG, полное декодирование, разрешения, байты и SHA. После загрузки все восемь PNG повторно скачаны с GitHub и SHA сверены. Renderer отдельно отклоняет замену использованных pose/storyboard/atlas по SHA до рендера.

## Повторный запуск

Проверенная среда: Python 3.14, Pillow 12.3.0, FFmpeg/FFprobe 9.0.2, Windows. Рендер CPU; RTX 4060 Ti 8 GiB обнаружена, но локальным renderer не используется. OpenAI API key, платный video API, GPU-модели, Blender и Unreal для запуска не нужны.

Из корня checkout с этим PR:

```powershell
git fetch origin assets/1117-ab-wheel-anatomical-reference
New-Item -ItemType Directory -Force .artifacts/runtime/tmp | Out-Null
git archive --format=zip --output=.artifacts/runtime/tmp/ab-wheel-reference.zip 36b689ebab402f65f60a60b1f15240cb60b4feaa docs/exercises/catalog-v2/1117-ab-wheel-anatomical-reference
Expand-Archive -LiteralPath .artifacts/runtime/tmp/ab-wheel-reference.zip -DestinationPath .artifacts/runtime/tmp/ab-wheel-reference

$rig = 'docs/exercises/catalog-v2/1117-ab-wheel-rig'
$mediaTools = 'D:/Pet-projects/your-fitness-coach/.artifacts/runtime/986-upscale-tools/ffmpeg-release-essentials/ffmpeg-9.0.2-essentials_build/bin'
python scripts/ab_wheel_anatomical_pilot.py `
  --references .artifacts/runtime/tmp/ab-wheel-reference/docs/exercises/catalog-v2/1117-ab-wheel-anatomical-reference `
  --atlas "$rig/anatomical-atlas-source.webp" --config "$rig/rig.json" `
  --output .artifacts/tasks/1117-anatomical-video/deliverables `
  --ffmpeg "$mediaTools/ffmpeg.exe" --ffprobe "$mediaTools/ffprobe.exe" `
  --baseline backend/assets/exercise-guides/gymvisual/ab-wheel-0857-NAgVB3t.gif
```

`$mediaTools` — фактический локальный путь использованного FFmpeg; на другой машине укажите установленный FFmpeg/FFprobe. Python/Pillow должны быть доступны в выбранном окружении. `--style-only` создаёт три фазы для проверки до полного рендера. Процесс перезаписывает файлы только в явно указанной директории output; используйте отдельную директорию для нового эксперимента.

В output сохраняются 120 PNG, MP4, три styleframe, contact sheet, gallery и `qc.json`. Для просмотра можно открыть локальный `index.html` как файл. Проверенный HTTP-вариант использует уже установленный Vite: `node frontend/node_modules/vite/bin/vite.js .artifacts/tasks/1117-anatomical-video/deliverables --host 127.0.0.1 --port 8769 --strictPort`, затем откройте `http://127.0.0.1:8769/index.html`. Нужен сервер с HTTP Range: у обычного `python -m http.server` в проверенном браузере диапазон seek был 0..0 и покадровое управление не работало; через Vite проверены диапазон 0..4 с, кадр 61 = 2,033332 с, воспроизведение 0,25× и ширина 390×844 без горизонтального переполнения. В [review/index.html](review/index.html) сохранена готовая галерея текущего результата; её reference загружается с SHA-pinned GitHub, поэтому нужен доступ в сеть. GitHub показывает HTML как исходник: для просмотра скачайте/клонируйте каталог и откройте его локально.

## QC и приёмка

[Технический отчёт](review/qc.json), [MP4](review/candidate.mp4), [12 фаз](review/contact-sheet.png), [styleframe выката](review/style-extended.png).

Автоматический QC проверяет H.264/yuv420p, 720×720, 30 FPS, 120 кадров/4 секунды, отсутствие audio, монотонные PTS с шагом 1/30 и полный decode. SHA, версия encoder, время рендера и разность кадров сохранены в отчёте. SHA конфигурации считается по UTF-8 с LF, чтобы Windows CRLF не менял provenance; генерируемые HTML/JSON записываются с LF. Разность первого/последнего кадра — измерение, не автоматическое одобрение loop. По циклу соседние декодированные кадры меняются; обратный ход закономерно повторяет позы выката.

Тесты:

```powershell
python -m pytest tests/test_ab_wheel_anatomical_pilot.py tests/test_ab_wheel_review_package.py -q
python -m ruff check scripts/ab_wheel_anatomical_pilot.py scripts/ab_wheel_review_package.py tests/test_ab_wheel_anatomical_pilot.py tests/test_ab_wheel_review_package.py
```

Независимый просмотр подтвердил `NEEDS_WORK`: видны наложения у плеча, резкий переход у таза/шорт, другие пропорции корпуса; старт и финиш наклонены сильнее storyboard. `TECHNIQUE_REVIEW`: фиксация IK-костей не доказывает видимый контакт каждой кисти/колена, физиологию суставов и правильность рисунка мышц. Владелец не принимал новый атлас, движение или видео. Не запрашивается принятие заведомо незавершённого варианта.

## Источники и права

См. [provenance.json](provenance.json) и [описание генерации атласа](ATLAS_PROMPT.md). Восемь оригинальных PNG остаются неизменными. Новые изображения созданы встроенным ImageGen по переданным владельцем ChatGPT-референсам; внешняя 3D-модель не использовалась. Новый атлас не является подтверждённой медицинской/анатомической моделью. Подтверждённое отдельное коммерческое разрешение для нового итогового видео: `NOT_VERIFIED`.

Baseline — существующий canonical GIF; основание прав взято из текущего production manifest (`Owner-purchased GymVisual license`). Здесь он только материал сравнения; новая лицензия или дополнительное разрешение на распространение не выдумываются. Метаданные установленного Pillow указывают `MIT-CMU` (PIL license); `ffmpeg -L` использованного build подтверждает GPL version 3 or later. Версии и конфигурацию конкретного encoder можно получить через `ffmpeg -version`/`-L`; исполняемые файлы не включены в PR.

Runtime, production manifest, исходные GIF/MP4, CI-контракты и deployment не меняются. **env change required: no.** Merge, deploy и закрытие #1117 не разрешены этим пакетом.
