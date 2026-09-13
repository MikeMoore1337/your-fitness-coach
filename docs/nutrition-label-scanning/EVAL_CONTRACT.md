# Eval contract: nutrition-label-corpus-v1

**Версия:** `nutrition-label-eval-v1`
**Дата регистрации thresholds:** 2026-09-12
**Статус:** pre-registered; provider run не выполнен.

## Принцип сравнения

Оценивается не одна aggregate accuracy, а каждая cell `case × field × source column`. Readable,
ambiguous, unreadable и absent cases имеют разные знаменатели. Ошибка в `salt/sodium`, `%DV`,
basis или отсутствующем поле важнее красивого среднего по простым строкам.

## Hard gates

Любое из условий ниже означает `FAIL` кандидата независимо от среднего score:

- один уверенно выдуманный nutrient, включая absent/unreadable field;
- `%DV` принят за `g`/`mg` либо использован как mass conversion;
- guessed serving mass/basis или смешение двух nutrition columns;
- manufacturer kcal заменён расчётом `4P + 9F + 4C`;
- malformed/oversized/decompression-bomb-like image дошёл до provider;
- schema output содержит unknown field или `requires_user_review != true`;
- raw image/OCR/provider payload, user ID, Telegram initData или diary/history попали в normal
  logs/analytics;
- provider timeout/quota/429/error показан как успешный draft или приводит к silent retry loop.

## Pre-registered quality thresholds

Порог считается только на `readable`/`expected-read` cells, если не указано иначе:

| Metric | Gate |
|---|---:|
| Value + unit + source basis/column exact/within declared label rounding | ≥98% mandatory, ≥95% optional |
| Language/format/basis classification | ≥98% per class, с минимумом 5 cases/class |
| Hallucination on absent/unreadable fields | 0% |
| Wrong column/basis | 0% |
| Salt↔sodium semantic swap | 0% |
| `%DV` false mass conversion | 0% |
| Eligible serving-to-100 conversion without known matching mass/volume | 0% |
| `null`/warning calibration on unreadable/absent | ≥95% cases correctly marked |
| Ambiguity detection recall | ≥95%; false confident-read ≤5% |
| Retake/manual fallback correctness | 100% negative/edge cases |
| Strict schema validity and unknown-field rejection | 100% accepted provider payloads |
| Privacy boundary and local payload rejection | 100% boundary tests |

Performance/economics are gates only after owner records a budget:

- one still image, one normal attempt; retry only for explicitly retryable transport failure;
- p95 end-to-end draft latency target ≤8 s and hard timeout ≤15 s;
- scan correction p50 ≤ manual baseline p50, with no higher confirmed-field error rate;
- provisional cost target ≤$0.05 per accepted draft at p50 and ≤$0.10 including one retry; owner
  may replace these before live run, but the selected value must be recorded before comparison;
- route must be `recurring_free` or explicitly owner-approved paid; promo/trial/unknown is not
  treated as free.

## Scoring

1. Validate provider JSON against `canonical_draft.schema.json`.
2. Validate domain invariants deterministically: units, ranges, basis, column id, decimal comma,
   null semantics, salt/sodium separation and `%DV` separation.
3. Score source facts before normalized/derived facts; a correct numeric value in the wrong column
   is wrong.
4. Count critical failures separately and stop candidate promotion on the first one.
5. Report macro average and per-class/per-field confusion; never hide negative cases in an average.
6. Run the same pinned prompt/schema/model twice only when repeatability is part of the approved
   test plan; record drift, not just the best run.

## Error taxonomy

`invalid_image`, `unsupported_mime`, `oversized_image`, `decode_failed`, `nonlabel`,
`unreadable`, `ambiguous_basis`, `ambiguous_column`, `missing_field`, `hallucinated_field`,
`wrong_unit`, `wrong_basis`, `dv_as_mass`, `salt_sodium_swap`, `invalid_schema`,
`unknown_field`, `provider_timeout`, `provider_rate_limited`, `provider_unavailable`,
`policy_blocked`, `cost_blocked`, `manual_required`.

## Required run record

Run record stores only synthetic case ID, fixture hash, model/provider/prompt/schema/policy
versions, request/response byte buckets, latency bucket, safe error code, field scores and
aggregate cost. It must not store raw image, raw OCR, raw provider response, user identifiers or
full label text unless a separately approved research vault exists.
