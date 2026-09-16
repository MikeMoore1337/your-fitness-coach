# Manual Yandex Wordstat input for Task 241A

Статус на 2026-09-16: `UNKNOWN`. В текущей среде Wordstat перенаправляет на Yandex Passport и
требует owner login; credentials не запрашивались и не вводились. Yandex SERP после нескольких
ручных запросов включил SmartCaptcha, которую research не решает. Числа в этом документе не
выдумываются и не являются placeholder volume.

## Что должен экспортировать владелец

Для каждого keyword из списка ниже сохранить:

- точную введённую фразу;
- тип отчёта: broad и, если интерфейс поддерживает, exact/phrase-normalized;
- регион и выбранный device filter;
- период/дату выгрузки и дату просмотра;
- `base frequency`, `phrase frequency` и связанные queries в отдельных полях;
- экспортированный CSV/XLSX без ручного округления;
- скрин или URL отчёта только если он не содержит credentials/PII.

Не смешивать результаты разных регионов в один показатель и не усреднять региональные volumes.
Не считать related queries независимыми частотами без проверки Wordstat.

## Обязательные region slices

1. Россия в целом.
2. Москва и Московская область.
3. Санкт-Петербург и Ленинградская область.
4. Казахстан.
5. Беларусь.

Device filter: сначала `все устройства`; если данных достаточно, отдельными срезами desktop и
mobile. Date context: зафиксировать полный доступный Wordstat period, не писать «сейчас» без даты.

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

The durable semantic CSV intentionally records `UNKNOWN` until this template is populated. The
owner export can be normalized into a copy/append-only evidence file with these fields:

```csv
cluster_id,keyword,country,region,device,period,wordstat_mode,broad_frequency,exact_frequency,related_query,source_url,exported_at,notes
A,калькулятор 1пм,RU,Россия,all,YYYY-MM-DD..YYYY-MM-DD,broad,,,,https://wordstat.yandex.ru/,YYYY-MM-DD,
A,калькулятор 1пм,RU,Россия,all,YYYY-MM-DD..YYYY-MM-DD,exact,,,,https://wordstat.yandex.ru/,YYYY-MM-DD,
A,калькулятор 1пм,RU,Москва и Московская область,all,YYYY-MM-DD..YYYY-MM-DD,broad,,,,https://wordstat.yandex.ru/,YYYY-MM-DD,
A,калькулятор 1пм,KZ,Казахстан,all,YYYY-MM-DD..YYYY-MM-DD,broad,,,,https://wordstat.yandex.ru/,YYYY-MM-DD,
A,калькулятор 1пм,BY,Беларусь,all,YYYY-MM-DD..YYYY-MM-DD,broad,,,,https://wordstat.yandex.ru/,YYYY-MM-DD,
```

После импорта обновить только demand columns и `source_notes` в
`semantic-core-ru-cis.csv`; не менять SERP observations и opportunity score без отдельного
owner-visible decision log. `UNKNOWN` можно заменить на число только если source URL, region,
mode и export date сохранены.

## Decision rule after export

- **Confirm:** cluster can enter implementation proposal when regional evidence, product fit and
  SERP attainability agree.
- **Hold:** demand is present but product dependency, health risk or cannibalization is unresolved.
- **Drop/defer:** demand is weak/ambiguous or intent is already better served by an existing page.

Wordstat export alone does not authorize production page creation, merge or Task 241B.
