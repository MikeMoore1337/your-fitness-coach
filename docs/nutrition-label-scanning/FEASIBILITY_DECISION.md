# 128A: feasibility decision для nutrition-label Vision

**Версия:** `nutrition-label-vision-decision-v1`
**Дата проверки:** 2026-09-12 (Europe/Moscow)
**Статус:** `OWNER_DECISION_REQUIRED`
**Рекомендация implementer/researcher:** `DEFER`
**Owner decision:** `PENDING` (`GO` / `NARROW GO` / `DEFER` / `NO-GO`)

## Краткий вывод

Технически production-suitable путь возможен, но эта task не доказала его для YFC. Официальные
контракты подтверждают, что несколько внешних моделей принимают изображения и могут вернуть
структурированный ответ. Synthetic corpus preflight теперь фактически доказал безопасную
локальную проверку bytes, но ни один provider/local OCR engine не выполнил extraction run.
Поэтому качество на русских/английских этикетках, нулевой critical-error rate, подходящая
region/retention policy и допустимая стоимость для YFC всё ещё не доказаны.

Решение `DEFER` рекомендовано по пяти конкретным причинам:

1. Provider-quality run на зафиксированном image corpus не выполнен: текущая project policy не
   даёт approved Vision credential, а paid calls, новый account/secret и новые provider terms не
   разрешены. Это точный access/policy blocker, а не `FAIL` качества.
2. Текущий YFC AI route — generic text-only Groq adapter; `90B` доказывает только ограниченный
   text beta, а не распознавание фотографий этикеток.
3. Local OCR quality run также не выполнен: PaddleOCR, Tesseract и проверенные альтернативные
   runtime отсутствуют в task environment. Это точный `LOCAL_OCR_RUNTIME_UNAVAILABLE`, а не
   `FAIL` качества.
4. Для cloud Vision обнаружены существенные policy gates: Groq хранит customer data в US GCP
   при соответствующих режимах; OpenAI имеет default abuse-monitoring retention и отдельные
   ограничения для image/file inputs; Gemini unpaid tier допускает использование input/output
   для улучшения продуктов и human review. Это требует отдельного owner/legal decision, а не
   скрытой настройки в `128B`.
5. Не измерены baseline ручного ввода, correction time, provider p50/p95 latency, quota behavior и
   стоимость одной принятой карточки. Без них нельзя честно выбрать provider или объявить GO.

## Что считается доказанным

- Task `114` и текущий food-domain contract уже дают local-first lookup, ручной user-food editor,
  GTIN validation, provenance/license metadata и diary snapshots. Внешний provider является
  fallback и не нужен для повторного использования достаточного local result.
- В current code нет image upload/label scan endpoint, Vision adapter, OCR service или
  photo-to-food write path.
- Task `87`–`90B` закрепили provider-neutral generic AI boundary, strict validation, default-off
  flags, bounded quota и отсутствие raw prompt/output в обычных логах. `90B` — limited beta для
  текста, не Vision evidence.
- Канонические nutrition facts в YFC сейчас нормализуются на 100 г; diary хранит snapshot на
  момент записи. `ml`, `serving` и неизвестные значения не дают права придумывать плотность,
  массу порции или нулевое значение.
- 32 synthetic-owned corpus entries реально собраны; preflight принял 31 PNG и отклонил 4
  malformed/oversized boundary cases, включая `NEG-08` до decode/provider. Это доказывает только
  input-safety boundary, не OCR/модельную точность.
- База decision packet, включающая local-first persistent catalog, source-vs-derived facts,
  `community_unverified`, explicit sharing и privacy gates, подготовлена в соседних документах
  этой папки.

## Фактические результаты bounded evaluation

- `schema validity`: synthetic valid draft принят, unknown field, `%DV` как mass, ambiguous basis,
  unreadable value, undocumented confidence и zero serving amount отклонены; provider payloads не
  получены.
- `required-field/basis/column/hallucination/null/salt-sodium/%DV/RU/EU-UK/US/rotation/glare/
  small/multi-column`: quality metrics `N/A`, потому что extraction engine не запускался.
- `fixture preflight`: `PASS`, `entries=32`, `accepted_images=31`, `rejected_boundaries=4`,
  observed local `elapsed_ms=8.025` in the latest run; это не provider latency.
- `provider/model/prompt`: `NOT_RUN`; `schema_version=nutrition-label-draft-v1`,
  `policy_revision=nutrition-label-vision-decision-v1`.
- `quota/errors/cost/correction/retake`: provider values `N/A`; only deterministic boundary
  errors were exercised (`oversized_image`, `oversized_pixels`, malformed/unsupported input).

## Proposed route, cost и privacy contract (не owner approval)

Proposed disposition после этой итерации — `DEFER`. Если owner позже выберет `NARROW GO`, первым
кандидатом предлагается local-only OCR/preprocessing + deterministic table parser/validator;
cloud provider не выбирается и automatic paid fallback запрещён.

Для этого narrow spike зафиксирована следующая граница: external calls `0`, provider token cost
`$0/request`, image не покидает YFC-controlled runtime, training/analytics/subprocessors/region
transfer у provider отсутствуют, raw image/OCR не сохраняются в catalog, diary, logs или
analytics, а user-confirmed facts сохраняются с provenance. Temporary raw image/OCR удаляются при
cancel/expiry; точный runtime TTL, OCR package license и device-resource budget ещё не утверждены
и должны быть gate в `128B/128C`. Поэтому этот контракт не является production approval.

Cloud route остаётся `NOT_APPROVED`: no approved credential, no account-specific retention/region
proof, no live quality/cost/quota evidence. Любой будущий cloud route потребует одного
owner-approved provider, current legal/privacy review, explicit consent/revocation, pinned model,
hard budget/kill switch и отсутствие automatic paid fallback.

## Поддерживаемый scope только после owner `GO`/`NARROW GO`

### Минимальный `128B`

- один still-image upload или выбранный файл; continuous video и отправка camera frames
  запрещены;
- provider-neutral draft по [канонической schema](CANONICAL_NUTRITION_FACTS_CONTRACT.md), всегда
  `requires_user_review=true`;
- draft — недоверенный input для детерминированной YFC validation, не nutrition calculation и
  не автоматическая запись в diary/catalog;
- readable source facts сохраняют исходные basis/column/unit; `per-serving -> per-100` только
  при известной matching mass/volume;
- unknown/unreadable/ambiguous остаются `null` с явным warning/evidence status;
- одна bounded attempt, controlled timeout/quota/unavailable state, manual entry/retake fallback;
- provider/model/prompt/schema/policy versions и normalized error code — server metadata, без
  raw image/OCR/provider payload в логах;
- local YFC lookup выполняется до любого food provider и до Vision, если exact GTIN или
  sufficient local result уже известен.

### Разрешённый `128C` после отдельной проверки

Только capture/retake/manual fallback UX для Web/TMA, с реальной browser/device проверкой по
своему gate. Physical-device evidence, iOS/TMA camera behavior и permission UX не подтверждены в
этой task.

## Что прямо запрещено до следующего owner decision

- production endpoint, migration, schema/API/UI/runtime change или provider activation;
- выбор Groq/OpenAI/Gemini как YFC default без corpus result и policy approval;
- Cloudflare Workers AI как Vision fallback (он зарезервирован текущим news-image contract);
- отправка real-user package photos, принятие новых provider terms, создание account/secret или
  paid calls. Разрешён только явно bounded synthetic/public/legal live eval на существующем
  approved режиме, если его terms/privacy совместимы с eval;
- автоматическое сохранение model output в diary или shared catalog;
- numeric confidence, если semantics не откалиброваны на locked corpus;
- превращение external provider data в shared YFC facts без разрешающей license/terms boundary.

## Gate, после которого можно переоткрыть решение

Owner должен выбрать disposition и, если он не `NO-GO`/`DEFER`, отдельно утвердить:

1. provider route или local-only/OCR route, pinned model/version и allowed cost class;
2. data-flow: purpose/notice, region, retention/deletion, subprocessors/upstream, legal counsel
   disposition и consent/revocation behavior;
3. locked image corpus v1 с human ground truth и license/ownership evidence;
4. запуск bounded eval по [EVAL_CONTRACT.md](EVAL_CONTRACT.md) и закрытие всех critical failures;
5. baseline ручного ввода и критерий correction-time improvement;
6. exact approved scope `128B` и `128C`.

`128B` заблокирована до этого owner decision. Даже owner `GO` не запускает `128B` автоматически.

## Privacy/legal options for the owner

Это engineering decision aid, а не юридическое заключение. Для любого external image provider
выставлен `LEGAL_COUNSEL_REQUIRED: YES`, пока не подтверждены фактический оператор, страны
передачи/обработки, retention, subprocessors, лицензия на пользовательское изображение и
обязательства по удалению.

| Вариант | Что меняется | Остаточный риск | Сложность |
|---|---|---|---|
| `SAFE` | local-only OCR/preprocessing; cloud Vision не используется; private/shared writes только после user review | quality/coverage и device resource risk; external transfer risk минимален | high |
| `BALANCED` | один owner-approved paid/provider route, strict no-context payload, ephemeral YFC TTL, explicit consent/revocation, hard budget/kill switch, current legal/provider review | provider outage, residual transfer/retention and model error risk remain | high |
| `ACCEPT_RISK` | external unpaid/promo/unknown route или не подтверждённая region/retention policy | formal privacy/licensing/cost risk remains; owner acceptance не делает несоответствие законным | low-to-medium implementation, unacceptable for production default |
| `AVOID` | не запускать photo-to-food route; сохранить barcode/manual flow и local catalog growth | no scan convenience; no new image data flow | low |

Практическая рекомендация — `SAFE` для первого reproducible spike либо `BALANCED` только после
явного owner/legal disposition. `ACCEPT_RISK` для real-user photos не рекомендуется. Recheck
требуется при новом provider/model, изменении страны/terms/retention, появлении paid plan,
несовершеннолетних пользователей, shared user-generated content или новой редакции закона.
