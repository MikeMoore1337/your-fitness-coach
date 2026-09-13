# Eval results: nutrition-label-corpus-v1

**Дата отчёта:** 2026-09-12
**Contract:** `nutrition-label-eval-v1`
**Итог:** `PARTIAL_PRE_PROVIDER_RUN`
**Recommendation:** `NARROW GO - IMPLEMENTATION + OWNER-ONLY PRODUCTION VALIDATION`
**Owner decision (2026-09-13):** `NARROW GO`; pre-production quality remains `NOT MEASURED`.
**Public rollout:** `BLOCKED`; next task `128B` permitted but not launched.

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
| Local PaddleOCR/Tesseract hybrid | local image/OCR route, no provider transfer | YFC must build/validate parser itself | Russian/English support documented; table/layout and device cost not measured | narrow local spike candidate |

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
| Local live blocker | `LOCAL_OCR_RUNTIME_UNAVAILABLE`; no approved OCR runtime is installed in the task environment |

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
Следующая validation run разрешена только в owner/internal allowlist после реализации `128B` и
`128C`; для cloud по-прежнему нужны совместимый terms/privacy режим и approved credential.
Пороговые значения не изменены и применяются строго по
[`EVAL_CONTRACT.md`](EVAL_CONTRACT.md).
