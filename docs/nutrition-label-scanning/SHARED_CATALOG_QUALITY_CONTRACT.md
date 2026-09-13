# Shared YFC catalog quality contract

**Версия:** `yfc-shared-food-quality-v1`
**Дата:** 2026-09-12
**Статус:** proposal for `128B`; production schema не меняется в 128A.

## User-visible choice

После редактирования draft пользователь явно выбирает одно из действий:

- `Добавить в каталог YFC` — подтверждённые package facts могут стать shared candidate при
  соблюдении identity/provenance/license rules;
- `Сохранить только для себя` — usable private food, недоступный другим аккаунтам.

Не должно быть скрытого sharing по факту scan, barcode lookup или создания diary entry.

## States and visibility

| State | Owner | Search/diary | Trust | External dependency |
|---|---|---|---|---|
| private user food | one user | only owner | private/unverified | none after save |
| `community_unverified` | shared YFC, contributor identity hidden | exact GTIN + name search; usable with visible warning | below `verified YFC` | none |
| `verified YFC` | shared YFC | normal catalog | reviewed/promotion evidence | none |
| provider-backed result | provider | external review/import path | provider source, not YFC verified | provider may be unavailable |

`community_unverified` — это локальный YFC state, не синоним external provider `unverified` и не
доказательство точности. Один submission никогда не получает `verified YFC` автоматически.

## Identity and conflict invariants

1. Valid GTIN нормализуется и проверяется до recognition и повторно перед confirm.
2. Exact local GTIN lookup завершает основной lookup без внешнего вызова, если карточка
   `sufficient` по [catalog independence contract](CATALOG_GROWTH_PROVIDER_INDEPENDENCE_CONTRACT.md).
3. Shared exact GTIN contribution присоединяется к canonical identity/revision chain, а не создаёт
   новый продукт на каждый scan.
4. Scan не делает silent overwrite verified/provider fact. Новая correction — отдельная
   contribution/revision с source, timestamp и quality state.
5. Без valid GTIN первый shared delivery запрещён по умолчанию; разрешён private save. Name-only
   sharing возможно только после отдельного deterministic identity/dedup contract и owner approval.
6. Другой пользователь может использовать community candidate и предложить correction, но не
   выполняет last-write-wins overwrite.

## Provenance and license

У каждого persisted fact сохраняются: source kind (`user_confirmed_package`, `provider`, `internal`),
source/original basis, normalized/derived markers, confirmation event, model/schema/prompt version
если применимо, quality state и revision link.

Provider-backed nutrition data остаётся provider-backed. Оно не копируется в shared YFC dataset и
не получает YFC attribution автоматически, пока конкретные terms/license не разрешают такую
републикацию. User-confirmed package facts — отдельное происхождение и не должны включать raw
provider response в скрытом виде.

Публичная карточка показывает только quality label вроде `Добавлено пользователем` и проверяемые
nutrition facts; contributor user ID, Telegram ID, raw image и raw OCR другим пользователям не
раскрываются.

## Promotion and lifecycle

- promotion в `verified YFC` требует lightweight review: duplicate/conflict check, valid GTIN,
  visible source evidence, basis/unit validation и минимум двух независимых подтверждений либо
  owner-defined equivalent evidence;
- correction не меняет уже сохранённые diary snapshots;
- private food удаляется владельцем по обычному owner scope; diary snapshot сохраняется по текущему
  contract;
- shared candidate deletion, contributor unlinking, raw image/OCR TTL, export and account deletion
  semantics должны быть атомарно зафиксированы в `128B` до production. Нельзя обещать, что
  пользовательское удаление автоматически переписывает уже использованный diary history;
- persisted image/raw OCR не нужны для searchable catalog и по умолчанию не сохраняются.

## Quality gates

Shared write отклоняется до confirm, если есть invalid GTIN, ambiguous basis, missing mandatory
values, unresolved conflict, unknown unit, hallucinated field, unavailable source evidence или
provider-only data без разрешающей license boundary. Автор всегда получает usable private draft,
если он сам исправил обязательные поля вручную.
