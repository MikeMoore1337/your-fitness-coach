# Канонический nutrition-facts contract

**Версия:** `nutrition-label-facts-v1`
**Дата:** 2026-09-12
**Назначение:** provider-neutral editable draft; это не production API и не migration.

## Основной принцип

Фотография и ответ Vision считаются недоверенными. Модель может прочитать число, но не имеет
права сама решить его basis, заполнить пропущенный nutrient, заменить значение производителя
расчётом или записать результат без пользовательской проверки.

Каждый nutrient разделяется на три слоя:

1. `source_facts` — что видно на конкретных колонках этикетки: каждая cell хранится как value
   (либо `null`), unit, `basis_ref`, безопасный `column_ref` и собственный `evidence`;
2. `normalized_facts` — детерминированная YFC-нормализация в канонические единицы и basis;
3. `derived_fields` — только явно помеченный вывод с причиной и списком source fields.

`source_facts` и `normalized_facts` не смешиваются. На одном ответе не разрешается скрыто
объединять `per 100 g`, `per serving`, `%DV` или соседние колонки. Для каждого
`source_facts[field]` разрешён `null` либо непустой массив source cells (до 8 элементов) с
уникальным `column_ref`; поэтому одновременно видимые `per 100 g` и `per serving` сохраняются
раздельно. Source cell имеет `evidence=read|ambiguous|unreadable`: при `evidence=read` `value`
обязателен, при `evidence=ambiguous` или `evidence=unreadable` `value` обязан быть `null`. Если OCR уверенно прочитал число,
но basis всей таблицы не определён, source cell сохраняет `value`, `evidence=read` и
`basis_ref=ambiguous`; это промежуточный review fact, а не нормализованное значение. При
неоднозначной колонке конкретное число не выбирается и остаётся `value=null`. `field_evidence[field]`
остаётся консервативным aggregate summary: `read`, только если все source cells прочитаны;
`unreadable`, если все нечитаемы; смешанный или неоднозначный набор получает `ambiguous`.
`normalized_facts[field]` остаётся одной детерминированно выбранной canonical fact и допускается
при смешанном наборе только если существует хотя бы одна readable source cell и basis выбран.

## Schema-equivalent поля

Формальная provider-neutral версия находится в
[`canonical_draft.schema.json`](canonical_draft.schema.json). Все поля обязательны на уровне
strict schema; отсутствие факта выражается `null`, а не отсутствием ключа и не нулём.

| Поле | Допустимые значения / правило |
|---|---|
| `source_language` | `ru`, `en`, `mixed`, `unknown` |
| `label_format` | `ru_standard`, `eu_uk`, `us_nutrition_facts`, `unknown` |
| `source_basis` | `per_100_g`, `per_100_ml`, `per_serving`, `ambiguous` |
| `serving_size` | amount + `g`/`ml`; `null`, если mass/volume неизвестны |
| `servings_per_container` | positive decimal, иначе `null` |
| `package_amount` | amount + `g`/`ml`, только если явно виден на упаковке |
| `source_facts[field]` | `null` либо непустой массив `{value, unit, basis_ref, column_ref, evidence}`; `basis_ref=ambiguous` допустим только у review draft с неопределённым общим basis; `value=null` для `ambiguous`/`unreadable` source-cell evidence, `column_ref` уникален в пределах field |
| `normalized_facts[field]` | canonical unit/basis после deterministic validation; или `null` |
| `derived_fields[field]` | value/reason/source fields только для разрешённого derived fact; иначе `null` |
| `field_evidence[field]` | aggregate: `read`, `ambiguous`, `unreadable`, `absent`, `derived`; source-cell evidence хранится внутри `source_facts` |
| `confidence_kind` | `provider_native`, `calibrated_eval`, `none` |
| `confidence[field]` | `[0,1]` только при documented/calibrated semantics; иначе `null` |
| `warnings` | machine-readable safe warning codes, без raw provider text |
| `requires_user_review` | всегда `true` до отдельного owner-перехода |
| `metadata` | server-known provider/model/prompt/schema/policy versions |

## Nutrient vocabulary

Используется фиксированный набор полей, чтобы unknown output не стал новым canonical nutrient:

`energy_kcal`, `energy_kj`, `protein_g`, `fat_g`, `saturated_fat_g`, `trans_fat_g`,
`carbohydrate_g`, `sugars_g`, `added_sugars_g`, `fiber_g`, `salt_g`, `sodium_mg`,
`cholesterol_mg`.

`%DV` хранится отдельно как `displayed_daily_value_percent[field]`. `%DV` никогда не является
массой и не может попасть в `normalized_facts` как `g` или `mg`.

## Basis и единицы

- Decimal comma и decimal point нормализуются детерминированно после проверки контекста; `1,5`
  не принимается как две колонки.
- Разрешены только явные `g`, `mg`, `ml`, `kcal`, `kJ` в соответствующем поле. Непонятные,
  отрицательные, конфликтующие или переполненные значения становятся warning/blocking
  validation, а не исправляются догадкой.
- `per serving -> per 100 g` разрешён только при известной массе serving в граммах. Аналогично
  для `ml` требуется известный объём serving в миллилитрах.
- Между `ml` и `g` нельзя конвертировать без известной плотности/отношения именно этого продукта.
- `salt_g` и `sodium_mg` — разные source facts. Возможный deterministic salt/sodium relation
  может быть только отдельным `derived` полем с явным reason; он не замещает исходное значение.
- `4P + 9F + 4C` — только advisory warning с учётом округления и fiber/label rules. Manufacturer
  kcal не перезаписываются вычисленным числом.
- Отсутствующий nutrient не равен нулю. Ноль допустим только если ноль виден на source label и
  прошёл unit/basis validation.

## Пользовательское подтверждение и diary

До confirm UI должен показать исходную колонку, normalized value, warning и неизвестные поля.
Пользователь может исправить draft, удалить поле или отказаться от сохранения. В diary попадает
только подтверждённый canonical food через существующую server-side validation; raw image/OCR не
становится diary history.

Историческая запись хранит snapshot, как и текущий food-domain contract. Поздняя correction,
promotion или disable каталожной записи не переписывает уже сохранённые diary facts.

## Confidence policy

Нumeric confidence не считается универсальным показателем качества. До калибровки использовать
`field_evidence` + warnings + явный `requires_user_review=true`. `provider_native` можно показать
только с provider semantics и отдельной проверкой корреляции с ошибками на corpus; оно не заменяет
YFC validation. `calibrated_eval` появляется только после locked-corpus run и versioned report.
