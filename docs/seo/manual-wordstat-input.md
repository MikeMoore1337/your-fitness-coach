# Manual Yandex Wordstat input for Task 241A

Статус на 2026-09-16: `OWNER_EXPORT_INTEGRATED`. Владелец предоставил результаты Yandex Wordstat
за период `15.08.2026–15.09.2026`, через `Regions`, для фильтра `все устройства`. Основной срез —
Россия; региональные строки для Москвы/МО, Санкт-Петербурга/ЛО, Казахстана, Беларуси и СНГ без
России сохранены в semantic-core matrix. Первоначальная среда по-прежнему не имела owner login:
credentials не запрашивались и не вводились, а Yandex SERP после нескольких ручных запросов
включил SmartCaptcha. Числа ниже — owner evidence, не placeholder volume.

## Что должен экспортировать владелец

Для каждого keyword из списка ниже сохранить:

- точную введённую фразу;
- тип отчёта: broad и quoted/fixed-word-count;
- регион и выбранный device filter;
- период/дату выгрузки и дату просмотра;
- `broad frequency`, `quoted/fixed-word-count frequency` и связанные queries в отдельных полях;
- экспортированный CSV/XLSX без ручного округления;
- скрин или URL отчёта только если он не содержит credentials/PII.

Оператор `"..."` фиксирует количество слов, но не обязательно порядок и словоформу. Поэтому
`quoted/fixed-word-count frequency` не называется exact match в смысле Google Ads. Не смешивать
результаты разных регионов в один показатель и не усреднять regional volumes. Не считать related
queries независимыми частотами без проверки Wordstat. Отсутствующий результат обозначать
`NO_DATA` или `no_export_available`, но не `0`.

## Обязательные region slices

1. Россия в целом.
2. Москва и Московская область.
3. Санкт-Петербург и Ленинградская область.
4. Казахстан.
5. Беларусь.

Device filter: сначала `все устройства`; если данных достаточно, отдельными срезами desktop и
mobile. Date context: зафиксировать полный доступный Wordstat period, не писать «сейчас» без даты.

## Полученный owner export

Основные Russia rows, использованные для обновления `semantic-core-ru-cis.csv`:

| Seed | Broad | Quoted/fixed-word-count | Ratio | Status |
| --- | ---: | ---: | ---: | --- |
| `калькулятор 1пм` | 363 | 261 | 71.9% | `observed_broad_and_quoted` |
| `программа тренировок 3 раза в неделю` | 1351 | 32 | 2.4% | `observed_broad_and_quoted` |
| `full body 3 раза в неделю` | 20 | `NO_DATA` | `NO_DATA` | `observed_broad_only` |
| `дневник тренировок` | 3038 | 456 | 15.0% | `observed_broad_and_quoted` |
| `калькулятор кбжу` | 16127 | 4763 | 29.5% | `observed_broad_and_quoted` |
| `жим лежа техника` | 2943 | 528 | 17.9% | `observed_broad_and_quoted` |
| `программа тренировок для новичка` | 604 | 34 | 5.6% | `observed_broad_and_quoted` |
| `тоннаж тренировки` | 181 | 2 | 1.1% | `observed_broad_and_quoted` |
| `калькулятор объёма тренировки` | 5 | `NO_DATA` | `NO_DATA` | `observed_broad_only` |
| `приложение для фитнес-тренера` | `NO_DATA` | `NO_DATA` | `NO_DATA` | `no_export_available` |

Regional evidence is kept as separate values in the matrix in `semantic-core-ru-cis.md`; it is not
averaged into the Russia values. Kazakhstan and Belarus have smaller but real Russian-language
signals in major clusters such as KBJU, diary and programs. This supports one RU/CIS canonical
surface and does not support `/kz` or `/by` SEO clones.

## Query input list

### A — 1ПМ / working weights

```text
калькулятор 1пм
расчет 1пм
рассчитать 1пм
одноповторный максимум
максимум на одно повторение
рабочий вес калькулятор
проценты от 1пм
1rm calculator русский
рассчитать рабочий вес
калькулятор тренировочных весов
70 процентов от максимума
80 процентов от 1пм
85 процентов от 1пм
расчет веса по повторениям
формула 1пм
```

### B — training volume

```text
объем тренировки
объем силовой тренировки
тренировочный объем
тоннаж тренировки
рассчитать тоннаж тренировки
калькулятор объема тренировки
количество подходов на мышечную группу
недельный объем тренировки
```

### C — programs

```text
программа тренировок 3 раза в неделю
программа тренировок в зале 3 раза в неделю
full body 3 раза в неделю
фулбоди 3 раза в неделю
фулбоди для новичка
программа тренировок для новичка
программа тренировок для новичка в тренажерном зале
программа на массу 3 раза в неделю
программа на похудение в тренажерном зале
upper lower программа
верх низ программа тренировок
push pull legs программа
программа тренировок 4 раза в неделю
```

### D — trainer / B2B

```text
приложение для фитнес тренера
приложение для персонального тренера
программа для фитнес тренера
crm для фитнес тренера
crm фитнес тренер
вести клиентов фитнес тренеру
учет клиентов фитнес тренера
программа для тренера и клиентов
приложение тренер клиент
онлайн ведение клиентов фитнес тренером
дневник клиента фитнес тренера
составление программ клиентам
контроль прогресса клиентов тренера
```

### E — exercise technique

```text
жим лежа техника
приседания со штангой техника
тяга верхнего блока
горизонтальная тяга
румынская тяга
жим ногами
жим гантелей лежа
подтягивания техника
махи гантелями в стороны
подъем гантелей на бицепс
```

### F — nutrition tools

```text
калькулятор кбжу
расчет кбжу
рассчитать кбжу
калькулятор калорий
сколько калорий нужно в день
дефицит калорий калькулятор
калькулятор белка
сколько белка нужно в день
белок на кг веса
расчет белка в день
```

### G — cardio / heart rate

```text
калькулятор пульсовых зон
пульсовые зоны
зоны пульса для кардио
расчет максимального пульса
пульс для жиросжигания
зона 2 пульс
пульс при кардио
```

### H — workout diary / fitness app

```text
дневник тренировок
приложение дневник тренировок
приложение для тренировок
приложение для тренировок в зале
учет тренировок
запись рабочих весов
трекер тренировок
планировщик тренировок
```

## Import template

The durable semantic CSV now contains the integrated Russia owner evidence. Use this template for a
future append-only export or a new owner refresh. Keep broad and quoted values in separate fields:

```csv
cluster_id,keyword,country,region,device,period,wordstat_mode,broad_frequency,quoted_frequency,quoted_broad_ratio,related_query,source_url,exported_at,notes
A,калькулятор 1пм,RU,Россия,all,2026-08-15..2026-09-15,broad,363,,,https://wordstat.yandex.ru/,2026-09-16,owner Regions export
A,калькулятор 1пм,RU,Россия,all,2026-08-15..2026-09-15,quoted_fixed_word_count,,261,71.9%,,https://wordstat.yandex.ru/,2026-09-16,operator "..."; not Google Ads exact match
A,калькулятор 1пм,RU,Москва и Московская область,all,2026-08-15..2026-09-15,broad,90,,,,https://wordstat.yandex.ru/,2026-09-16,regional row
A,калькулятор 1пм,KZ,Казахстан,all,2026-08-15..2026-09-15,broad,1,,,,https://wordstat.yandex.ru/,2026-09-16,regional row; quoted NO_DATA
A,калькулятор 1пм,BY,Беларусь,all,2026-08-15..2026-09-15,broad,NO_DATA,,,,https://wordstat.yandex.ru/,2026-09-16,no regional result supplied
```

После импорта обновлять только demand columns, Wordstat metadata и `source_notes` в
`semantic-core-ru-cis.csv`; не менять SERP observations и opportunity score без отдельного
owner-visible decision log. Число можно записать только если сохранены source URL, region, mode,
device filter и export period. Если broad или quoted result отсутствует, записывать `NO_DATA`, а
не ноль. `priority_score` остаётся отдельным product/opportunity proxy и не заменяется volume.

## Decision rule after export

- **Confirm:** cluster can enter implementation proposal when regional evidence, product fit and
  SERP attainability agree.
- **Hold:** demand is present but product dependency, health risk or cannibalization is unresolved.
- **Drop/defer:** demand is weak/ambiguous or intent is already better served by an existing page.

Wordstat export alone does not authorize production page creation, merge or Task 241B. Current
Task 241A remains `OWNER_REVIEW_REQUIRED` after the research update.
