# Catalog growth и provider independence contract

**Версия:** `yfc-catalog-independence-v1`
**Дата:** 2026-09-12
**Назначение:** approved design boundary for `128B`; routing/runtime не реализуется.

## Target flow

```text
barcode/name lookup
  -> persistent YFC catalog first
     -> sufficient local result: use local, external call = 0
     -> local miss/incomplete: bounded external fallback/enrichment
        -> optional scan/manual confirmation
           -> explicit share_to_yfc_catalog
              -> persistent private or community YFC product
```

Local YFC catalog — долгосрочный primary source уже известных приложению продуктов. Open Food
Facts, USDA, FatSecret и любой будущий provider — bootstrap/fallback/enrichment only. Provider
availability не может быть необходимым условием diary use для уже сохранённой YFC карточки.

## Sufficient local result

### Exact GTIN

Local result sufficient, если:

- запрос — valid normalized GTIN;
- найден ровно один active local YFC item с тем же GTIN;
- item видим текущему пользователю (private owner) или shared catalog;
- item имеет valid name, provenance/trust state и обязательные diary nutrients;
- basis/serving metadata не противоречит canonical contract.

В этом случае не запускаются external lookup и Vision только ради повторной сверки. Пользователь
может явно открыть `Проверить упаковку`, но это отдельное действие и не меняет карточку молча.

### Name search

Name result sufficient, если local ranking вернул usable item с canonical required nutrients,
видимой provenance/trust label и достаточно точным name/brand match. Если есть только неполная
карточка, ambiguous basis или отсутствует обязательный nutrient, local result не sufficient;
external fallback разрешён как non-blocking enrichment.

External fallback не должен блокировать ручной product editor/Quick Add и не должен дёргаться при
заполненном local result budget. Ошибка, timeout, `429` и disabled state — controlled non-fatal
status.

## Persistence boundary

- package facts после user review сохраняются в собственной YFC DB с distinct provenance;
- existing shared YFC product usable при provider disabled/unavailable/rate-limited;
- provider response остаётся source-attributed external snapshot, если user не подтвердил source
  facts с упаковки и license не разрешает shared copy;
- exact GTIN contribution идёт в одну canonical identity/revision chain;
- no valid GTIN => private-by-default;
- local catalog promotion не зависит от того, доступен ли исходный provider.

## Privacy-safe metrics

Metrics — aggregate counters/buckets без barcode, product name, user ID, photo hash, OCR text,
diary fact или provider payload:

| Event | Definition |
|---|---|
| `yfc_catalog_local_hit` | lookup завершён sufficient local item; external calls = 0 |
| `external_fallback` | local miss/incomplete разрешил хотя бы одну bounded provider attempt |
| `scan_to_shared_confirm` | scan draft был подтверждён в shared YFC choice |
| `community_product_reused` | shared community candidate выбран для diary/use |
| `duplicate_detected` | exact GTIN/name identity conflict остановил новый write |
| `catalog_conflict` | новая contribution не прошла auto-promotion из-за conflicting fact |
| `scan_correction_state` | bucket: no_edit / edited / manual_required / abandoned |

Каждое событие содержит только schema version, coarse outcome, source class, basis class,
provider status, latency bucket и optional cost class. Raw request/response не логируются.

## Baseline and success definition

До feature launch собрать denominator из существующего flow `unknown barcode -> provider miss ->
manual own food` и `Добавить продукт -> ручной ввод КБЖУ`, без user identifiers. Для каждой версии
считать:

```text
local_hit_rate = yfc_catalog_local_hit / all eligible lookup attempts
external_fallback_rate = external_fallback / all eligible lookup attempts
shared_confirm_rate = scan_to_shared_confirm / completed reviewed scan drafts
community_reuse_rate = community_product_reused / visible community candidate selections
```

Периоды, eligibility, missing telemetry и denominator changes фиксируются в versioned report.
Нельзя объявлять provider independence по росту общего request volume; нужна устойчивая динамика
local hit rate вверх и external fallback rate вниз при неухудшении correction/error metrics.
