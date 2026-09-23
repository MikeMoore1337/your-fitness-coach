# Eval results: nutrition-label-corpus-v1

**Дата отчёта:** 2026-09-12
**Contract:** `nutrition-label-eval-v1`
**Итог:** `PARTIAL_PRE_PROVIDER_RUN`
**Recommendation:** `NARROW GO - IMPLEMENTATION + OWNER-ONLY PRODUCTION VALIDATION`
**Owner decision (2026-09-13):** `NARROW GO`; pre-production quality remains `NOT MEASURED`.
**Public rollout:** `BLOCKED`; Task `128B` implementation is now present, but owner-only validation
and a separate quality run are still required before any rollout decision.

## Что реально проверено

| Проверка | Результат | Ограничение |
|---|---|---|
| Current YFC food/diary/provider baseline | PASS | read-only code/docs inspection |
| Task 114 and 87–90B factual boundary | PASS | `90B` не считалась Vision evidence |
| Official provider capability/privacy/cost docs | PASS/PARTIAL | published contracts checked; account-specific settings не подтверждены |
| Corpus case matrix and pre-registered thresholds | PASS | manifest IDs/rules fixed |
| Bounded stdlib contract harness | PASS | `eval_harness.py --self-check`; deterministic synthetic payloads only |
| Synthetic locked image fixtures | PASS | 31 PNG + 1 oversized boundary; recipe oracle; no user data/external assets; human review pending |
| Fixture/input-safety preflight | PASS | 32 manifest entries; 31 accepted images; 4 malformed/oversized boundaries rejected |
| Provider quality run | NOT RUN | exact blocker: `NO_APPROVED_VISION_CREDENTIAL`; no provider request was made |
| Local OCR quality run | NOT RUN | exact blocker: `LOCAL_OCR_RUNTIME_UNAVAILABLE`; PaddleOCR/Tesseract/alternative runtimes absent |
| Task 128B parser/image/API regression suite | PASS | synthetic OCR seam, strict canonical parser, local image bounds, draft/confirm/privacy/diary boundaries |
| Task 128B local OCR runtime quality | NOT MEASURED | production image contains Tesseract, but unit tests do not make a recognition-quality claim |
| p50/p95 latency, quota and cost | NOT MEASURED | no live requests |
| Manual correction baseline | NOT MEASURED | no user study/instrumentation authorized |
| Production/provider activation | NOT PERFORMED | outside scope |

## Candidate evidence matrix

| Candidate | Image input | Structured output | Current evidence | Decision status |
|---|---|---|---|---|
| Existing YFC Groq `openai/gpt-oss-120b` | no image capability in current route | current text strict contract | existing generic text beta only | not a Vision candidate |
| Groq Qwen Vision | official docs: Qwen 3.6/3.8 27B, image URL/base64, JSON mode | strict outputs only on supported-model allowlist; vision+strict combination not proven by local run | preview model/cost/rate/data location require account/policy review | research candidate, not approved |
| OpenAI GPT-4o snapshot | official image input and text output including Structured Outputs | supported | paid token pricing; default abuse monitoring retention; ZDR/MAM eligibility/account setup to verify | paid candidate, owner/legal gate |
| Google Gemini API | official image input formats | JSON Schema subset; application semantic validation still required | unpaid tier may use/review submitted content; available-region/account path needs verification | not acceptable as free/private default |
| Local RapidOCR + ONNX Runtime | local image/OCR route, no provider transfer | positioned tokens -> existing strict parser | Task 128G: PP-OCRv5 Cyrillic quality/resource bakeoff passed on locked synthetic corpus; real-label proof still pending | selected primary, production HUMAN_EVIDENCE pending |
| Local Tesseract 5.5.0 | local image/OCR fallback, no provider transfer | positioned TSV tokens -> existing strict parser | Task 128E/128G: safety preserved, materially slower and slightly weaker on the same corpus | explicit bounded fallback |

## Why no quality numbers are reported

`0%` in the metric columns below means **not measured**, not success:

| Metric | Result |
|---|---|
| Mandatory value/unit/basis accuracy | `N/A` |
| Hallucination rate | `N/A` |
| Wrong basis / column | `N/A` |
| Salt/sodium swap | `N/A` |
| `%DV` false conversion | `N/A` |
| Null/ambiguity calibration | `N/A` |
| Schema validity | `PARTIAL` | synthetic valid/invalid payloads pass/reject, including column-addressable source facts, per-column null/evidence states and duplicate-column rejection; no provider payloads |
| p50/p95 latency | `N/A` |
| Cost/request | `N/A` |
| Scan correction time vs manual | `N/A` |

## Run metadata and exact blockers

| Metadata | Value |
|---|---|
| Corpus / eval / schema versions | `nutrition-label-corpus-v1` / `nutrition-label-eval-v1` / `nutrition-label-draft-v1` |
| Policy revision | `nutrition-label-vision-decision-v1` (`OWNER_DECISION_REQUIRED`) |
| Provider / model / prompt | `NOT_RUN` / `NOT_RUN` / `NOT_RUN` (no request was authorized by available project policy) |
| Local fixture generator | `build_synthetic_fixtures.py`, Python 3.14 + Pillow 12.3.0; synthetic-owned only |
| Fixture preflight limit | max 8 MiB, max 20 megapixels; observed local preflight `elapsed_ms=7.489` in the latest recorded run |
| Cloud live blocker | `NO_APPROVED_VISION_CREDENTIAL`; current YFC AI Coach policy is disabled/generic/free-only and no Vision key is available |
| Local live blocker | `LOCAL_OCR_RUNTIME_UNAVAILABLE` on the development host; the Task 128B production image contains bounded Tesseract, but no quality run was authorized or completed |

The preflight latency is input-boundary latency, not provider end-to-end latency and not a
production SLO measurement. `NOT_RUN` is intentionally distinct from `FAIL`: no candidate was
allowed to produce a quality result under the current credential, terms and privacy gates.

Self-check и fixture preflight запускаются без сети; self-check не требует зависимостей:
`python docs/nutrition-label-scanning/eval_harness.py --self-check`.
`python docs/nutrition-label-scanning/eval_harness.py --fixture-preflight <fixture-manifest.json>`.
Это не заменяет полный JSON Schema validator или provider-quality run; он защищает
воспроизводимые structural/critical инварианты и image-boundary checks до появления утверждённого
eval environment.

Любой recognition-quality или public-rollout claim на основании этого отчёта был бы недоказанным.
Task 128B добавляет production-equivalent parser, ingress и confirm boundaries, но это не превращает
synthetic OCR seam в measured recognition quality.
Следующая validation run разрешена только в owner/internal allowlist после реализации `128B` и
`128C`; для cloud по-прежнему нужны совместимый terms/privacy режим и approved credential.
Пороговые значения не изменены и применяются строго по
[`EVAL_CONTRACT.md`](EVAL_CONTRACT.md).

## Addendum Task 128E (2026-09-13)

В production-equivalent Docker image выполнен локальный synthetic-only runtime probe для
нового bounded OCR pipeline. Tesseract 5.5.0 обработал 5 вариантов preprocessing в режимах
PSM 6/4/11: всего 15 кандидатов, выбор стабилен. На десяти запусках end-to-end latency составила
p50 6600 ms и p95 7389 ms, preprocessing — p95 118 ms, peak RSS — 81404 KiB, дочерний CPU
Tesseract — p50 18.31 s и p95 20.71 s; configured hard timeout — 8 s.

Это подтверждает только bounded resource behavior и parser safety на synthetic fixture. Это не
измерение real-label accuracy, device/TMA latency или correction baseline. Production
HUMAN_EVIDENCE по той же оригинальной фотографии остаётся обязательным; до него public rollout
не считается подтверждённым.

## Addendum Task 128G (2026-09-14)

Task 128G выполнил isolated local bakeoff и production integration без cloud/paid OCR. Сравнение
проводилось на одном locked corpus: representative synthetic label + 31 PNG из
`nutrition-label-corpus-v1`; oversized boundary fixture не передавался OCR engine. В corpus есть
RU 100 g/100 ml, EU/UK, US Nutrition Facts, mixed RU/Latin, decimal comma, dark/white table,
small text, rotation/perspective и partial/unreadable cases.

### Candidate и compatibility

- Primary candidate: `RapidOCR 3.9.2` + `ONNX Runtime 1.30.0` + `PP-OCRv5` mobile detector,
  textline classifier и `cyrillic_PP-OCRv5_rec_mobile.onnx` recognizer. `rapidocr` требует
  Python `>=3.8,<4`; locked wheels для Python 3.14 и Linux `manylinux_2_28` были доступны.
- YFC runtime: Python `3.14.6`, `python:3.14-slim`, Debian image build PASS, `pip check` PASS,
  CPU-only runtime smoke от non-root `appuser` PASS.
- RapidOCR/PaddleOCR model license — Apache-2.0; ONNX Runtime — MIT; Tesseract fallback и
  official `tessdata` остаются Apache-2.0. Pinned transitive Python dependencies и Debian
  packages остаются в dependency/image audit; реальные user images, OCR text и credentials в
  evidence не использовались.
- Зафиксированный license inventory новых/активированных transitive packages: `opencv-python`
  Apache-2.0, `numpy` BSD-3-Clause, `omegaconf` BSD-3-Clause, `protobuf` 3-Clause BSD,
  `pyclipper` MIT, `shapely` BSD-3-Clause, `flatbuffers` Apache-2.0, `antlr4-python3-runtime`
  BSD, `six` MIT, `tqdm` MPL-2.0/MIT и `colorlog` MIT. Это package/license evidence для
  dependency review, а не замена итогов registry/SBOM-проверки конкретного Debian release.

Model bundle скачивается только на этапе image build скриптом
[`fetch_rapidocr_models.py`](../../scripts/fetch_rapidocr_models.py), проверяется SHA-256 и
делается read-only для runtime. В production bundle входят только:

| Model | SHA-256 | Размер |
|---|---|---:|
| `ch_PP-OCRv5_det_mobile.onnx` | `4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae` | 4,819,576 B |
| `cyrillic_PP-OCRv5_rec_mobile.onnx` | `90f761b4bfcce0c8c561c0cb5c887b0971d3ec01c32164bdf7374a35b0982711` | 8,074,092 B |
| `ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx` | `54379ae5174d026780215fc748a7f31910dee36818e63d49d17dc598ecc82df7` | 1,018,508 B |

Итого production model bundle — `13,912,176 bytes`. Runtime model download не выполняется.

### Same-corpus comparison

| Метрика | RapidOCR 3.9.2, PP-OCRv5 Cyrillic | Tesseract 5.5.0 |
|---|---:|---:|
| Cold init | 585.9 ms | included in first bounded run |
| Warm p50 | 1,879.9 ms | 3,614.2 ms |
| Warm p95 | 2,228.2 ms | 4,409.5 ms |
| Max | 2,577.4 ms | 6,606.1 ms |
| Cases без `missing_required_fact` | 14/32 | 13/32 |
| Fully resolved basis + energy + P/F/C | 12/32 | not separately recorded |
| Dangerous `2814 kcal` | 0 | 0 |

На representative label оба required quality paths дали `per_100_g`, `281.4 kJ`, `66.8 kcal`,
protein `8.0 g`, fat `2.0 g`, carbohydrate `4.2 g`; RapidOCR candidate не имел warnings.
US `%DV` и неуверенные/неполные строки остаются reviewable/null по существующему parser safety
contract; Task 128G parser не переписывал.

### Resource profile

RapidOCR primary использует singleton process engine, ONNX `intra_op=1`/`inter_op=1`, отключённый
CPU memory arena, `gc.collect()` после обработки результата и `BoundedSemaphore(1)`. Это даёт
один тяжёлый OCR inference одновременно на process, model initialization не повторяется на
каждый request, а timeout и controlled errors сохраняются. Quality profile с max side `2000`
зафиксировал peak RSS `1,235,672 KiB` (около `1.18 GiB`), same-label warm p50 `2560.0 ms`,
p95 `3961.2 ms` и CPU `2732.2 ms/request`; это release operational constraint, а не приглашение
увеличивать concurrency. Профиль max side `1000` был отклонён: peak RSS около `342 MiB`, но
только `6/32` cases без `missing_required_fact`.

Docker size comparison на локальном BuildKit:

- baseline `yfc-backend:128e-final`: `178,398,886 bytes`;
- RapidOCR image: `428,252,871 bytes`;
- delta: `+249,853,985 bytes` (`+238.3 MiB`), включая Python wheels, `libgl1` и 13.9 MB models.

### Decision and limitations

RapidOCR выбран primary, потому что на том же corpus он быстрее Tesseract и даёт небольшое,
измеримое улучшение полноты, при этом не создаёт unsafe `2814 kcal`, сохраняет positioned
evidence и existing deterministic parser. Tesseract остаётся только explicit fallback и не
запускается безусловно вместе с RapidOCR. Это не доказывает real-label accuracy: после deploy
нужна HUMAN_EVIDENCE на том же исходном фото, без коммита изображения и EXIF в repository.

## Addendum Task 128H (2026-09-23)

Post-migration validation was repeated on the canonical YFC production host with 2 vCPU,
1962 MiB RAM and 2047 MiB swap. Production remained configured for local RapidOCR,
`Global.max_side_len=2000`, one heavy inference at a time and an 8 s OCR timeout; public
nutrition-label scanning remained disabled during validation.

On the same reproducible clean representative label, the deployed 1-thread ONNX profile produced
first inference `7399.6 ms`, warm p50 `6034.3 ms`, warm p95 `6495.2 ms` and peak RSS
`1,167,276 KiB`. The draft preserved `per_100_g`, `281.4 kJ`, `66.8 kcal` and P/F/C
`8.0/2.0/4.2` without warnings, but failed the Task 128H latency targets.

A bounded 2-thread intra-op profile kept `inter_op=1`, CPU memory arena disabled, the same models,
`max_side_len=2000` and `BoundedSemaphore(1)`. On clean representative inputs it preserved all
mandatory facts without warnings and reduced p95 below 5 s: the 1200x1600 case measured first
`4672.6 ms`, warm p50 `4147.4 ms`, p95 `4627.7 ms`; the 1800x2400 case measured first
`4318.2 ms`, warm p50 `3385.9 ms`, p95 `3612.6 ms`. Peak RSS remained about `1.11 GiB`.

Enabling the ONNX CPU memory arena was explicitly rejected: the diagnostic process was OOM-killed
(exit 137, about `1.36 GiB` anonymous RSS) on this 2 GiB host. Reducing the diagnostic input to a
1000-1600 px long side did not meet the 3 s p50 target and is not accepted as a quality tradeoff;
the earlier Task 128G 1000 px corpus profile also had materially worse completeness.

Task 128H therefore permits only the evidence-backed `intra_op_num_threads=2` tuning while keeping
single-inference concurrency, the quality profile and 8 s timeout unchanged. The rollout verdict
remains **NO-GO for public enablement**: warm p95 is within the target, but warm p50 remains above
3 s on the canonical 2-vCPU host, and the original raw same-photo HUMAN_EVIDENCE image is not
available for a valid final replay. `NUTRITION_LABEL_SCAN_ENABLED=false` must remain in production
until both gates are satisfied; synthetic or screenshot-derived evidence must not be substituted
for the required original-photo validation.
