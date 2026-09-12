# Eval results: nutrition-label-corpus-v1

**Дата отчёта:** 2026-09-12
**Contract:** `nutrition-label-eval-v1`
**Итог:** `NOT_RUN`
**Recommendation:** `DEFER`

## Что реально проверено

| Проверка | Результат | Ограничение |
|---|---|---|
| Current YFC food/diary/provider baseline | PASS | read-only code/docs inspection |
| Task 114 and 87–90B factual boundary | PASS | `90B` не считалась Vision evidence |
| Official provider capability/privacy/cost docs | PASS/PARTIAL | published contracts checked; account-specific settings не подтверждены |
| Corpus case matrix and pre-registered thresholds | PASS | manifest IDs/rules fixed |
| Bounded stdlib contract harness | PASS | `eval_harness.py --self-check`; deterministic synthetic payloads only |
| Binary licensed image fixtures | NOT READY | no real-user photos and no approved fixture upload |
| Provider quality run | NOT RUN | no credentials/terms acceptance/live call authorization |
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
| Schema validity | `N/A` for provider payloads; schema document and critical-invariant self-check pass locally |
| p50/p95 latency | `N/A` |
| Cost/request | `N/A` |
| Scan correction time vs manual | `N/A` |

Self-check запускается без зависимостей и сети:
`python docs/nutrition-label-scanning/eval_harness.py --self-check`.
Это не заменяет полный JSON Schema validator или provider-quality run; он лишь защищает
воспроизводимые structural/critical инварианты до появления утверждённого eval environment.

Любой production claim на основании этого отчёта был бы недоказанным. Следующий run требует
owner-authorized provider and licensed fixtures, а затем выполняется строго по
[`EVAL_CONTRACT.md`](EVAL_CONTRACT.md).
