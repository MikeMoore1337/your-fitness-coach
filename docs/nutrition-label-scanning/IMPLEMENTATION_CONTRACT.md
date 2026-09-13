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

В production image добавлены Debian-пакеты `tesseract-ocr`, `tesseract-ocr-eng` и
`tesseract-ocr-rus`. Python-код запускает только allowlisted executable `tesseract` через явный
`argv`, `shell=False`, `stdin=DEVNULL`, timeout и bounded stdout. Поддерживаемые языки —
`rus+eng`; текущая адаптерная версия — `tesseract-structured-multipass-v2`.

Task 128E запускает bounded набор из пяти вариантов изображения (консервативный ROI, grayscale,
локальный контраст с denoise, adaptive threshold, inversion и один фиксированный малый deskew)
и три фиксированных PSM: `6`, `4`, `11`. Каждый pass использует явный `argv`, TSV word-level
output и общий timeout; число токенов, размер TSV, pixels preprocessing и суммарное число pass
ограничены. Надёжная perspective correction и удаление table lines в production pipeline не
включены: локальный synthetic probe не доказал устойчивого улучшения.

Parser использует token text + `left/top/width/height`, block/paragraph/line/word и confidence
для детерминированной строковой/колоночной association. Кандидат выбирается по basis,
unit-qualified value adjacency, required-field completeness, pair consistency, impossible-value
и column-collision checks; длина распознанного текста не является критерием.

Tesseract core распространяется под Apache License 2.0; репозиторий официальных `tessdata`
указывает Apache-2.0 для training data. В образе нужно сохранять package/license manifest
конкретного Debian release и отдельно учитывать лицензии транзитивных библиотек (в частности
Leptonica). Источники: [Tesseract license](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE)
и [tessdata README](https://github.com/tesseract-ocr/tessdata/blob/main/README.md).

В Windows-разработке наличие CLI не предполагается: unit и integration tests подменяют OCR
детерминированным synthetic engine. Это не является quality run. Результаты качества OCR остаются
`NOT MEASURED` до owner-authorized runtime validation на locked corpus.

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

Для текущего кода environment change required: `no`; OCR limits и runtime contract не меняются.
Для фактического public production rollout после прохождения gate потребуется операционная смена
`NUTRITION_LABEL_SCAN_ENABLED=true` в deployment contract при сохранении
`NUTRITION_LABEL_SCAN_KILL_SWITCH=false`; это rollout action, а не новая credential или provider
настройка. Cloud Vision, paid Vision, local LLM и credentials для них не нужны и не добавляются.

## Runtime OCR

Backend runtime устанавливает локальный Tesseract OCR и языковые данные `eng`, `rus`, `osd`;
проверенная container-сборка использует Tesseract 5.5.0. Вызов выполняется через явный `argv`
с `shell=False`, явным `--dpi 300`, timeout и ограничением вывода. Tesseract и официальный `tessdata` распространяются
под Apache-2.0; cloud/paid Vision и локальная LLM в этом pipeline не используются.

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
- OCR recognition quality по реальным этикеткам, correction baseline и full corpus metrics
  остаются `NOT MEASURED` до owner-authorized validation на production representative labels.
