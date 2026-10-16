# Issue #873 — Progress: компактная навигация и видимое добавление замера

Статус пакета: `PROPOSED / OWNER DESIGN APPROVAL REQUIRED`.

Это законченный пакет макетов для ревизии текущего Progress. Он не меняет продуктовый UI,
компоненты, CSS, API, расчёты, фикстуры или snapshot baseline. Реализация до явного owner
design approval не начиналась.

Пакет пересмотрен после owner feedback: в `PROPOSED` сохранена исходная информационная
иерархия, но визуальные значения приведены к текущей production baseline на `origin/master`.
CTA и график используют lime, остальные поверхности — канонические нейтральные токены; lavender/
purple palette из предыдущего кандидата удалена из предложенного режима. Файлы `BEFORE` не
перегенерировались и остаются byte-identical.

## Контекст и границы

- Issue: [#873](https://github.com/MikeMoore1337/your-fitness-coach/issues/873)
- Базовый SHA ревизии: `8a5c955400de87eed8c92974bd196a8343c6cd35`
- Предлагаемая ветка: `codex/issue-873-progress-design`
- Проверенная база: `origin/master` на 2026-10-16
- Текущий раздел `Progress` на проверенной базе уже использует общий `SegmentedControl`
  после PR #1000; перенос основных разделов в начало страницы не повторяется.
- Визуальная сверка `PROPOSED` выполнена с `frontend/src/shared/ui/common.tsx`
  (`Button`, `Card`, `SegmentedControl`) и токенами `frontend/src/styles/design-system.css`:
  `--v2-lime`, `--v2-surface*`, `--v2-border*`, `--font-body`, `--font-display`, 44px target,
  14px control radius и selected capsule с `data-yfc-choice="capsule"`.
- Для точной сверки использованы production-источники `design-system.css:4-72` (цвета,
  радиусы и spacing), `design-system.css:93-106` (типографическая шкала),
  `design-system.css:604-684` (общий `SegmentedControl` и selected state), а также
  `legacy.css:450-583` (тематические surface/button/segment aliases),
  `common.tsx#Button`, `common.tsx#Card` и `common.tsx#SegmentedControl`. В `PROPOSED`
  значения light/dark токенов зафиксированы локальными alias-ами без подключения runtime CSS.
- `PROPOSED` загружает source-controlled Inter/Oswald из `frontend/public/assets/fonts/`;
  это только локальная часть статического mockup и не меняет runtime bundle.
- Повторяющаяся семипунктная grid из исторических снимков Issue не считается текущим
  initial state. Раскрытия, которые владелец открывал вручную для демонстрации, не считаются
  постоянной вложенностью по умолчанию.
- AI Coach в макете отсутствует полностью: после PR #1021 пользовательский UI его не
  восстанавливает и не оставляет пустого места.
- #1002 не входит в пакет: `design-v2.css`, селекторы `progress-report-*` и общие baseline
  остаются нетронутыми до последовательной интеграции после #1002.

## Что предлагается утвердить

1. Сохранить уже внедрённую компактную peer-навигацию в начале Progress: `Обзор`, `Тело`,
   `Тренировки`, `Питание`, `Кардио`, `Самочувствие`, `История`. Историческая повторяющаяся
   сетка из семи двустрочных пунктов не возвращается; на review отдельно подтвердить, можно ли
   убрать только дублирующий `Обзор` из detail-header, сохранив URL, deep links, Back и focus.
2. В `Тело` рядом с фактическими значениями появляется заметное действие `Добавить замер`
   (touch target не менее 44 CSS px). Оно вызывает существующую форму и её валидацию;
   `История замеров` и редактирование остаются отдельными явными действиями.
3. `Тренировки` показывает ключевые числа в коротком snapshot-блоке, а детали упражнений и
   методика раскрываются по запросу. Статистика не меняется: в примере сохранены
   `27 подходов`, `13 948 кг`, `286 повторений` и PR.
4. `Питание` явно различает `нет данных`, `неполный день` и реальный ноль. В пустом
   состоянии используется `Записано 0 из 30 дней` и `30 дней без данных`, а не подмена
   пропусков нулевыми расчётами. Цели, гидратация и отчёт раскрываются без изменения
   текущих формул.
5. `Кардио` показывает компактные факты строки; вторичные действия находятся в безопасном
   раскрытии. Удаление остаётся только через существующее подтверждение, без свайпа или
   жеста удаления.
6. `Самочувствие` сохраняет последовательность `Факты → Уточнения → Решение`, а `История`
   сохраняет минимум две тренировки и исходные события. Убирается только постоянная тяжёлая
   вложенность.

## Комплект доказательств

Открыть интерактивный пакет: [gallery.html](./gallery.html).

В gallery доступны `BEFORE` и `PROPOSED`, светлая/тёмная темы и состояния:

- `Тело`: пусто, один замер, несколько замеров;
- `Тренировки`: сохранённый snapshot и раскрываемые детали;
- `Питание`: нет данных и заполненный период;
- `Кардио`: одна и несколько сессий;
- `Самочувствие`: факты, уточнения и решение;
- `История`: минимум две тренировки.

Скриншоты из `visuals/` покрывают обе темы, режимы `BEFORE/PROPOSED`, мобильные ширины
`320/360/393/430` и desktop `1440`. `BEFORE` показывает текущую проверенную базу с общим
`SegmentedControl` и существующим detail-back; `PROPOSED` сохраняет этот nav и меняет только
согласуемую иерархию деталей и заметность CTA. Данные синтетические: `Тестовый спортсмен`,
без реальных пользовательских скриншотов или приватных переписок.

| Файл | Назначение |
| --- | --- |
| `visuals/before-*-*.png` | текущая композиция на проверенной базе, representative states |
| `visuals/proposed-*-*.png` | пересобранные предложенные макеты по матрице размеров и тем |
| `manifest.json` | SHA, состояния, размеры, режимы и уровень доказательства |
| `future-test-map.md` | карта будущих Vitest/Playwright проверок и рисков |

Уровень этих PNG: `BROWSER_STATIC_MOCKUP`, не runtime-регрессия. Mobile WebKit, физический
iPhone/Safari, реальный Telegram Mini App, VoiceOver и нативная клавиатура — `NOT_VERIFIED`.

## Воспроизводимая генерация и проверки

Из корня репозитория, при уже установленном `frontend/node_modules`, команда ниже пересобирает
только 28 файлов `PROPOSED` в Chromium. Она не трогает `BEFORE` и использует локальный HTML,
source-controlled шрифты и `full-page` captures без сетевых запросов:

```powershell
$repo = (Resolve-Path .).Path
$gallery = (Resolve-Path docs/ux/issue-873-progress-design-20261016/gallery.html).Path.Replace('\', '/')
$out = Join-Path $repo 'docs/ux/issue-873-progress-design-20261016/visuals'
$cli = Join-Path $repo 'frontend/node_modules/playwright/cli.js'
$base = "file:///${gallery}"
$themes = @('light', 'dark')
$widths = @(1440, 320, 360, 430)
$states = @('body-empty', 'body-many', 'body-one', 'cardio-many', 'cardio-one', 'history', 'nutrition-empty', 'nutrition-filled', 'training', 'wellbeing')

foreach ($theme in $themes) {
  foreach ($width in $widths) {
    $url = "${base}?mode=proposed&theme=${theme}&state=body-many"
    $file = Join-Path $out "proposed-${theme}-${width}.png"
    node $cli screenshot --browser chromium --full-page --wait-for-timeout 300 --viewport-size "${width},900" --color-scheme $theme $url $file
  }
  foreach ($state in $states) {
    $url = "${base}?mode=proposed&theme=${theme}&state=${state}"
    $file = Join-Path $out "proposed-${theme}-393-${state}.png"
    node $cli screenshot --browser chromium --full-page --wait-for-timeout 300 --viewport-size '393,900' --color-scheme $theme $url $file
  }
}
```

После генерации выполняются bounded checks:

```powershell
$manifest = Get-Content docs/ux/issue-873-progress-design-20261016/manifest.json -Raw | ConvertFrom-Json
foreach ($entry in $manifest.preserved_before_sha256.psobject.Properties) {
  $actual = (Get-FileHash (Join-Path $out $entry.Name) -Algorithm SHA256).Hash
  if ($actual -ne $entry.Value) { throw "BEFORE changed: $($entry.Name)" }
}
$proposed = @(Get-ChildItem (Join-Path $out 'proposed-*.png'))
if ($proposed.Count -ne 28) { throw "Expected 28 PROPOSED PNGs, got $($proposed.Count)" }
$frontendDiff = @(git -c safe.directory=$repo diff --name-only -- frontend/src)
if ($frontendDiff.Count -ne 0) { throw "frontend/src changed: $($frontendDiff -join ', ')" }
```

Эти проверки подтверждают сохранение BEFORE, полноту предложенной матрицы и отсутствие
изменений production frontend; они не являются runtime, real-device или owner approval.

Результат последнего capture/self-check (`2026-10-16T11:31:50Z`): `28/28` URL/viewport
комбинаций прошли в headless Chromium. Проверены отсутствие горизонтального overflow,
lime CTA и график, canonical selected capsule, `missing != 0`, наличие подтверждения перед
удалением и отсутствие AI Coach UI. Контрольный SHA gallery: `AE0913861585E28635E04E43E093A859EB5963FC7E81594FAE41BF5B333AB113`.

## Карта принятия

До реализации нужен один явный owner design approval по всему пакету одновременно:

- одна навигация и поведение deep link/back/focus;
- размещение CTA `Добавить замер` и отдельное действие истории;
- иерархия раскрытий для тренировок, питания, кардио, самочувствия и истории;
- сохранение отличий `missing`/`0`, подтверждения удаления и всех исходных событий;
- отсутствие AI Coach и отсутствие изменений, связанных с #1002.

После approval возможна отдельная реализация 1:1. Затем обязательны реальные AFTER Dark/Light,
owner visual acceptance и отдельное разрешение на merge/release. Ни один из этих gates этим
пакетом не считается выполненным.
