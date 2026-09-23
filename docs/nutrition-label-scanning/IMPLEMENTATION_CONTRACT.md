# Task 128C: backend-контракт сканирования этикетки и rollout

Этот документ фиксирует production foundation Task 128B и mobile/TMA integration Task 128C.
Значение `false` в коде и `.env.example` остаётся fail-closed sample default. После обязательной
production validation владелец может включить feature для всех авторизованных пользователей.

## Граница выполнения

Pipeline состоит из четырёх явно разделённых шагов:

1. server-side cohort gate и bounded multipart ingress;
2. локальная нормализация изображения и локальный OCR;
3. детерминированный parser OCR-текста в `nutrition-label-draft-v1`;
4. owner-reviewed `draft -> confirm`, после которого создаётся private food или отдельная
   community contribution.

До `confirm` не создаются `foods`, `nutrition_catalog_contributions` и записи diary. Confirm не
создаёт diary entry автоматически. Пользователь должен отдельно выбрать продукт и явно добавить
его в дневник существующим endpoint.

## Local-only OCR runtime

Task 128G добавляет primary engine `RapidOCR 3.9.2` на `ONNX Runtime 1.30.0` с
`PP-OCRv5` mobile detector, textline classifier и Cyrillic/Russian recognizer. В production image
модели копируются на этапе build только после потоковой SHA-256-проверки; runtime использует
три явных `model_path` и не скачивает модели по пользовательскому запросу. Каталог по умолчанию —
`/opt/rapidocr/models`, разрешённые файлы перечислены в `RAPIDOCR_MODEL_FILES`.

RapidOCR работает CPU-only, с `intra_op_num_threads=2`, `inter_op_num_threads=1`, одним in-flight
inference на singleton engine и явным cleanup OCR buffers после каждого результата. Task 128H
разрешил двум ONNX intra-op threads использовать оба vCPU canonical production host без увеличения
числа одновременных heavy inference; CPU memory
arena отключён: это ограничивает рост RSS на повторных вызовах. Model initialization кэшируется
процессом; timeout остаётся общим bounded OCR budget `8 s`, а отсутствие модели, timeout или
ошибка runtime переводятся в controlled `local_ocr_*` error. `Tesseract 5.5.0` и `rus+eng`
остаются только явным bounded fallback при `NUTRITION_LABEL_SCAN_OCR_ENGINE=tesseract`.

Task 128F использует adaptive bounded набор из пяти вариантов изображения (консервативный ROI,
grayscale, локальный контраст с denoise, inversion, adaptive threshold) и три фиксированных PSM:
`6`, `4`, `11`. Evidence-backed priority начинается с `roi_deskew_minus_1_5_2x` и PSM `6`, затем
идут PSM `4`/`11` и остальные варианты. Каждый pass использует явный `argv`, TSV word-level
output, общий request budget `8 s`; для первого cold/high-resolution pass разрешено до `3.5 s`,
последующие pass используют bounded budget `1.5 s`; число токенов, размер TSV,
pixels preprocessing и суммарное число pass ограничены. После каждого pass candidate проходит
nutrition scoring: strong draft (resolved basis, energy, P/F/C, явные unit associations и без
safety warnings) останавливает pipeline. Optional timeout после reviewable candidate возвращает
лучший draft с warning `ocr_budget_exhausted`, а не удаляет уже полученные результаты. Надёжная
perspective correction и удаление table lines в production pipeline не включены: локальный
synthetic probe не доказал устойчивого улучшения.

Parser использует token text + `left/top/width/height`, block/paragraph/line/word и confidence
для детерминированной строковой/колоночной association. Кандидат выбирается по basis,
unit-qualified value adjacency, required-field completeness, pair consistency, impossible-value
и column-collision checks; длина распознанного текста не является критерием.

RapidOCR и upstream PaddleOCR-модели распространяются под Apache License 2.0, ONNX Runtime —
под MIT; Tesseract core и официальные `tessdata` сохраняют Apache-2.0 fallback-контракт.
Pinned Python dependencies и Debian packages остаются частью обычного dependency/image audit;
новые прямые runtime dependencies — `rapidocr`, `onnxruntime`, их transitive runtime packages,
`opencv-python` и системный `libgl1`. Источники: [RapidOCR repository](https://github.com/RapidAI/RapidOCR),
[RapidOCR model list](https://rapidai.github.io/RapidOCRDocs/main/model_list/),
[ONNX Runtime package](https://pypi.org/project/onnxruntime/),
[Tesseract license](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE) и
[tessdata README](https://github.com/tesseract-ocr/tessdata/blob/main/README.md).

В Windows-разработке наличие CLI не предполагается: unit и integration tests подменяют OCR
детерминированным synthetic engine. Это не является quality run; historical pre-128G status был
`NOT MEASURED`, а Task 128G добавил отдельный locked-corpus bakeoff ниже.

## Image ingress и privacy

- Принимаются только JPEG, PNG и WebP с совпадающими MIME и magic bytes.
- Максимум одного файла — 8 MiB, максимум изображения — 20 megapixels, весь multipart request
  ограничен отдельным body limit.
- Pillow делает `verify`, проверяет decompression-bomb bounds, применяет EXIF orientation и
  пересохраняет только RGB PNG без EXIF/ICC/user metadata.
- Изображение передаётся только локальному OCR subprocess. Raw image, raw OCR и внешние
  provider payload не сохраняются в БД и не попадают в обычные логи.
- Draft имеет короткий TTL (по умолчанию 15 минут) и scope по владельцу. После expiry новый scan
  требует нового idempotency key.

## Canonical facts

`CanonicalDraft` — strict `extra=forbid` DTO, совместимый с
`canonical_draft.schema.json`. Для каждого nutrient отдельно хранятся source cells,
normalized facts, evidence и confidence. Обязательная основа — `per_100_g`, `per_100_ml`,
`per_serving` либо явная `ambiguous`; двусмысленная основа не нормализуется и не подтверждается.
Текущая safety policy revision — `nutrition-label-local-v2`.

Правила parser:

- `%DV` не является массой и не конвертируется в `g`/`mg`;
- salt и sodium — разные поля;
- manufacturer kcal никогда не заменяются расчётом; unitless energy, mismatch пары kJ/kcal,
  outlier и несогласованность с `4P + 9F + 4C` переводят подозрительное поле в `null`/`ambiguous`
  с warning, а не в обычный prefill;
- отсутствующее или нечитаемое значение остаётся `null`;
- serving переводится в per-100 только при известной matching mass/volume;
- плотность и неизвестная масса порции не угадываются.

Legacy food columns `*_per_100g` остаются read-compatible projection. Canonical JSON и поля
`nutrition_basis_*` являются источником истины для новых 100 ml/serving продуктов. Diary хранит
snapshot и рассчитанную сумму на конкретное количество, чтобы последующее изменение каталога не
переписывать историю.

Для online-safe rollout исторический `foods.provenance` остаётся `VARCHAR(16)` и используется
старыми ограничениями и индексами. Additive-поле `foods.canonical_provenance` хранит полный
доменный provenance, включая `user_confirmed_package`; migration 0083 заполняет его из
исторического значения. ORM синхронизирует compatibility-поле при записи, а API и catalog
ranking читают только canonical provenance. Expand не изменяет тип или constraints уже
заполненной таблицы.

Аналогично, исторические `food_diary_entries.weight_g`, `energy_kcal_per_100g`,
`protein_g_per_100g`, `fat_g_per_100g` и `carbs_g_per_100g` остаются `NOT NULL` compatibility-
полями из-за online-safe rollout. Additive-поля `nutrition_weight_g` и
`nutrition_*_per_100g` являются canonical/API-полями и могут быть `NULL`, когда для
`per_100_ml` или `per_serving` соответствующая масса либо 100-граммовая проекция неизвестна.
Для старых полей в таком случае записываются технические compatibility markers, которые не
участвуют в nutrition calculations; все application read paths используют только canonical-
поля и immutable `nutrition_amount`.

## API и lifecycle

| Метод | Endpoint | Назначение |
|---|---|---|
| `POST` | `/api/v1/nutrition/label-scans` | multipart image -> owner draft; обязателен `Idempotency-Key` |
| `GET` | `/api/v1/nutrition/label-scans/{draft_id}` | получить собственный draft |
| `POST` | `/api/v1/nutrition/label-scans/{draft_id}/confirm` | explicit revision-bound confirmation |
| `POST` | `/api/v1/nutrition/label-scans/{draft_id}/cancel?revision=N` | закрыть draft без записи продукта |

Confirm повторно валидирует ownership, revision, TTL, basis и четыре обязательных факта:
`energy_kcal`, `protein_g`, `fat_g`, `carbohydrate_g`.

`visibility=private` создаёт user-owned `food`, невидимый другим пользователям. Его
`catalog_quality=private`, provenance — `user`.

`visibility=share_to_yfc_catalog` допускается только с валидным GTIN. Новый продукт получает
`food_type=branded`, `provenance=user_confirmed_package`, `catalog_quality=community_unverified`,
`trust_level=unverified`. Contributor identity не возвращается в public `FoodResponse`; отдельная
`nutrition_catalog_contributions` хранит state `accepted|duplicate|conflict`. Existing exact
barcode/facts не перезаписываются; mismatch возвращает conflict.

Local YFC catalog checked first. Exact local barcode lookup завершается без external provider call;
внешний food provider остаётся отдельным opt-in fallback существующего каталога и не используется
для label scan/OCR.

## Feature flag и эксплуатация

Доступ определяется только сервером:

- `NUTRITION_LABEL_SCAN_ENABLED=false` по умолчанию;
- `NUTRITION_LABEL_SCAN_KILL_SWITCH=true` немедленно закрывает route;
- `NUTRITION_LABEL_SCAN_INTERNAL_USER_IDS` принимается для обратной совместимости конфигурации,
  но не ограничивает доступ при включённом feature flag;
- production rollout после owner validation означает `NUTRITION_LABEL_SCAN_ENABLED=true` и
  `NUTRITION_LABEL_SCAN_KILL_SWITCH=false` для всех авторизованных пользователей.

Для Task 128G `env change required: yes`: в production `.env` нужно выставить
`NUTRITION_LABEL_SCAN_OCR_ENGINE=rapidocr`, если там сохранено прежнее явное значение
`tesseract`; новых secrets не требуется. `NUTRITION_LABEL_SCAN_OCR_MODEL_DIR` задавать не нужно,
если используется стандартный image path `/opt/rapidocr/models`. Для фактического public rollout
после HUMAN_EVIDENCE также потребуется операционная смена `NUTRITION_LABEL_SCAN_ENABLED=true`
при сохранении `NUTRITION_LABEL_SCAN_KILL_SWITCH=false`; это rollout action, а не новая credential
или provider настройка. Cloud Vision, paid Vision, local LLM и credentials для них не нужны.

## Runtime OCR

Backend runtime устанавливает локальный RapidOCR/ONNX Runtime и pinned PP-OCRv5 model bundle;
проверенная container-сборка использует Python 3.14 на `python:3.14-slim`, CPU-only inference,
read-only model files и `appuser`. Tesseract 5.5.0 с `eng`, `rus`, `osd` остаётся explicit
fallback через явный `argv`, `shell=False`, timeout и ограничение вывода. Raw image/OCR и cloud/
paid Vision payloads в pipeline не сохраняются и не логируются.

## Verification status

- parser/image/API regression tests — deterministic local tests;
- Alembic SQLite replay должен проходить от пустой базы до head;
- `eval_harness.py --self-check` и locked synthetic fixture preflight запускаются без сети;
- Task 128E synthetic-only runtime probe в production-equivalent image: 15 кандидатов (5 × 3),
  стабильный выбор deskew/PSM 11 с `per_100_g`, energy `281.4 kJ`/`66.8 kcal` и P/F/C
  `8/2/4.2`; end-to-end p50 `6600 ms`, p95 `7389 ms`, preprocessing p95 `118 ms`,
  peak RSS `81404 KiB`, Tesseract CPU p50 `18.31 s` и p95 `20.71 s` на десять запусков;
  configured hard timeout — `8 s`. Эти цифры не являются real-label accuracy или device/TMA
  benchmark: production same-photo HUMAN_EVIDENCE остаётся обязательным.
- Task 128F container profile на трёх locked synthetic layouts зафиксировал per-pass p95 до
  `~764 ms`, peak RSS до `~130 MiB` и стабильный fallback в пределах `8 s` для ambiguous/noisy
  candidates; clean strong candidate в deterministic tests завершает pipeline на одном pass.
  Это benchmark bounded runtime, не real-label accuracy и не device/TMA benchmark: production
  same-photo HUMAN_EVIDENCE остаётся обязательным.
- Task 128G сравнил RapidOCR 3.9.2 + PP-OCRv5 Cyrillic/mobile с Tesseract 5.5.0 на одном
  locked corpus из representative label и 31 synthetic PNG. RapidOCR на quality profile
  (`Global/Det.max_side_len=2000`, ONNX threads `1/1`, CPU arena disabled) дал cold init
  `585.9 ms`, warm p50 `1879.9 ms`, p95 `2228.2 ms`, max `2577.4 ms`; Tesseract на том же corpus дал
  p50 `3614.2 ms`, p95 `4409.5 ms`, max `6606.1 ms`. RapidOCR не создал dangerous `2814 kcal`;
  в `14/32` cases не было `missing_required_fact`, в `12/32` одновременно resolved basis и
  все обязательные facts. Target label получил `per_100_g`, `281.4 kJ`, `66.8 kcal`, P/F/C
  `8/2/4.2` без warnings. Quality profile ограничивает inference одним in-flight request;
  container probe зафиксировал peak RSS `1,235,672 KiB` (около `1.18 GiB`), same-label warm p50
  `2560.0 ms`, p95 `3961.2 ms` и CPU `2732.2 ms/request`; поэтому memory/concurrency bound
  является обязательной частью rollout. Профиль `1000 px` был отвергнут:
  peak RSS около `342 MiB`, но только `6/32` cases без missing required fact.
- Task 128G production-like Docker build прошёл с `pip check`; model bundle содержит только три
  pinned ONNX-файла размером `13,912,176 bytes`, скачанных и проверенных во время image build.
  Образ `yfc-backend:128e-final` был `178,398,886 bytes`, образ с RapidOCR — `428,252,871 bytes`,
  delta `+249,853,985 bytes` (`+238.3 MiB`). Runtime smoke от `appuser` подтвердил import,
  read-only model access, explicit inference и target tokens; network/model download в request
  path не используется. Эти цифры synthetic/container evidence, не real-label accuracy и не
  device/TMA benchmark: production same-photo HUMAN_EVIDENCE остаётся обязательным.
- После production HUMAN_EVIDENCE `503 local_ocr_timeout` на high-resolution label replay была
  воспроизведена в constrained `0.5-1 CPU` container: первый deskewed pass превышал старый
  `1.5 s` cap. Remediation оставляет общий request budget `8 s`, разрешает первому cold pass до
  `3.5 s`, а последующим pass оставляет `1.5 s`; локальный replay вернул reviewable draft без
  `503`. Это runtime regression evidence, а не подтверждение production real-label accuracy.
- OCR recognition quality по реальным этикеткам, correction baseline и device/TMA metrics
  остаются `NOT MEASURED` до owner-authorized validation на production representative labels;
  Task 128G synthetic locked-corpus metrics приведены выше и не заменяют HUMAN_EVIDENCE.
