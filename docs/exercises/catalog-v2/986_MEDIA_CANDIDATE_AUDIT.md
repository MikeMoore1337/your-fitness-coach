# Issue #986 — аудит candidate media для упражнений

Статус: `RESEARCH_ONLY`. Production UI, runtime media contract, manifest и локальные
медиа-файлы YFC не изменялись. Merge, deploy и release не выполнялись.

## Зафиксированные ревизии и границы прав

- YFC baseline: [`474d920d29e373043d4216586095ad7c90f7eb2e`](https://github.com/MikeMoore1337/your-fitness-coach/commit/474d920d29e373043d4216586095ad7c90f7eb2e), актуальный `origin/master` на момент аудита.
- Issue: [#986](https://github.com/MikeMoore1337/your-fitness-coach/issues/986).
- Candidate: [`akajdid-mostafa/exercises-media`](https://github.com/akajdid-mostafa/exercises-media/tree/18742da40b0627c85925c5dd4441dc3eac0594d0).
- Candidate exact `main` SHA: [`18742da40b0627c85925c5dd4441dc3eac0594d0`](https://github.com/akajdid-mostafa/exercises-media/commit/18742da40b0627c85925c5dd4441dc3eac0594d0).
- В Issue зафиксировано owner permission использовать именно этот source-кандидат.
- Это permission не распространяет исходный HD-архив, не подтверждает публичную
  redistribution-модель для каждого файла и не разрешает generative AI. Исходные файлы
  в YFC не добавлялись и для переработки не использовались.
- В candidate tree не найдено `LICENSE`, `NOTICE` или `README` с file-level license terms.
  Поэтому provenance verdict для bundling/redistribution остаётся `REVIEW`, даже при
  подтверждённом владельцем разрешении для дальнейшего исследования.

## Итог

На актуальном YFC master пересчитано 206 canonical exercises:

| Результат сопоставления | Количество | Что это означает |
|---|---:|---|
| `VERIFIED` | 13 | exact candidate slug и ручная проверка пары candidate posters на identity/equipment; не production approval |
| `REVIEW` | 94 | filename similarity либо exact slug без полной semantic review; автоматическая замена запрещена |
| `NO_MATCH` | 99 | безопасного кандидата по инвентарю нет; текущий media сохраняется |

Из 206 строк 167 имеют текущий approved GymVisual GIF, 39 остаются `blocked`. Все
39 blocked вошли в `NO_MATCH` и не были разблокированы. Среди approved: 13 `VERIFIED`,
94 `REVIEW`, 60 `NO_MATCH`.

Подтверждённые 13 candidate slug:
`barbell-curl`, `barbell-shrug`, `burpee`, `cable-lateral-raise`,
`donkey-calf-raise`, `dumbbell-fly`, `dumbbell-front-raise`,
`dumbbell-lateral-raise`, `dumbbell-shrug`, `jump-rope`, `lever-high-row`,
`squat`, `stationary-bike`.

Полная строка для каждого canonical exercise находится в
[`986_COVERAGE_MATRIX.csv`](./986_COVERAGE_MATRIX.csv). В матрице сохранены current
asset ID/path/bytes, candidate male/female paths и размеры, Git blob SHA-1 source
tree, poster presence, evidence scope, technical constraints, recommendation и
status.

Полная metadata-only инвентаризация candidate media находится в
[`986_SOURCE_INVENTORY.csv`](./986_SOURCE_INVENTORY.csv): 1,186 строк для 593 MP4 и
593 JPG poster. В ней нет бинарных данных; для нескачанных файлов технические поля
явно отмечены `NOT_MEASURED`.

## Текущий YFC baseline

`backend/assets/exercise-guides/manifest.json` имеет schema v3 и на этом SHA содержит:

| Показатель | Значение |
|---|---:|
| Canonical records | 206 |
| Approved animated | 167 |
| Blocked | 39 |
| Static-only | 0 |
| Remote runtime assets | 0 |
| Manifest assets | 334 |
| Manifest total | 18,137,868 B |

Все 167 текущих GIF и 167 poster-файлов имеют `180×180`. Фактический GIF-set —
16,962,687 B; posters — 1,175,181 B. Frame counts: 153 файлов по 12 кадров,
7 по 24, 5 по 18, один по 30, один по 54. Durations находятся в диапазоне
2.1–9.5 s, основная масса — 3.0 s.

Текущий контракт Issue #390 остаётся image/GIF-only:

- manifest требует локальный same-origin path, SHA-256, dimensions, byte size,
  animation metadata и единственный `image/gif` source;
- API schema допускает `image` и `animation`, но не `video`;
- `StaticFiles` раздаёт `/static/exercise-guides/...` same-origin;
- `ExerciseGuideMedia` и `ExerciseMediaAsset` используют poster, error fallback и
  `prefers-reduced-motion`; animation при reduced motion показывает poster;
- `<img>` использует reserved dimensions, `loading="lazy"` и `decoding="async"`;
- current cache policy: `public,max-age=2592000, stale-while-revalidate=86400`.

Следовательно, MP4 нельзя подменить в manifest одной заменой расширения: потребуется
отдельное решение по контракту, валидатору, API/frontend fallback и performance budget.

## Candidate inventory

Pinned source tree был прочитан рекурсивно через Git tree API. Получено 1,202 entries:
1,194 blobs и 8 directories; tree не truncated.

| Путь | MP4 | JPG poster | Tree bytes |
|---|---:|---:|---:|
| `public/videos/male` | 290 | — | входит в total |
| `public/videos/female` | 303 | — | входит в total |
| `public/thumbnails/male` | — | 290 | входит в total |
| `public/thumbnails/female` | — | 303 | входит в total |
| Всего | 593 | 593 | MP4 623,578,487 B; JPG 48,445,475 B |

В source tree нет `.webm` и GIF. Для всех 1,186 media blobs tree API даёт
path/size/Git blob SHA-1 и парный poster по slug. Это воспроизводимая полная
структурная инвентаризация, но Git blob SHA-1 не является SHA-256 файла.

Чтобы не скачивать и не хранить публично весь исходный архив, технические поля
проверены на минимальной выборке 16 MP4 (8 slug × male/female):

- H.264/AVC sample entry `avc1`;
- 1920×1080;
- примерно 29.97–30 FPS;
- duration 4.93–19.77 s, 148–593 frames;
- каждый скачанный файл получил фактический SHA-256.

Полные результаты этой выборки с `bytes`, `sha256`, codec, dimensions, duration,
frames и FPS: [`986_TECHNICAL_SAMPLE.csv`](./986_TECHNICAL_SAMPLE.csv). Для остальных
файлов duration/FPS/codec/dimensions/SHA-256 помечены как `NOT_MEASURED`, а не
выводятся по имени или разрешению.

26 sampled posters (male/female для 13 `VERIFIED` slug) фактически имеют 1920×1080.
Это доказывает размер контейнера poster, но не естественную детализацию исходного
изображения и не заменяет visual/domain review.

## Сопоставление и качество

Методика была консервативной:

1. current canonical slug и current manifest status были источником полного набора;
2. candidate slug ранжировались по нормализованным filename tokens только как
   discovery-подсказка;
3. exact slug не считался достаточным сам по себе;
4. `VERIFIED` получил только 13 exact slug после ручного просмотра poster sheet с
   совпадением exercise identity, оборудования и общей демонстрационной сцены;
5. для всех остальных candidate-пар semantic equivalence не заявляется;
6. blocked entries не открывались автоматически и похожие упражнения не назначались.

Candidate sample выглядит технически более детализированным по размеру контейнера и
разрешению, чем 180×180 GIF. Это не означает, что каждый кадр качественнее: natural
detail, anatomy, movement phases, compression artifacts и exact equipment требуют
отдельной проверки. Размеры также несопоставимы напрямую из-за разной длительности,
codec и frame rate.

Для 13 exact pairs сумма текущих GIF — 1,320,146 B, sample candidate MP4 —
17,535,114 B: в среднем около 101.5 KB против 674.4 KB на файл. Candidate
`jump-rope` достигает 2,199,174 B, `stationary-bike` — 1,667,626 B; это уже
существенный mobile transfer risk до lazy/poster strategy и оптимизации.

## Технический пилот

### A — self-hosted MP4/WebM

Потенциально совместимо с текущей архитектурой только как отдельный validated
contract:

- same-origin local file, poster-first и `preload="none"`/lazy intent;
- `prefers-reduced-motion` показывает poster и сохраняет текстовую технику;
- poster при network/decode/error, dimensions и contain сохраняются;
- no autoplay со звуком; catalog remains compact, media opens by intent;
- проверяются Chromium/WebKit/TMA, 320–430 px, cache, transfer, CPU/RAM и
  accessibility.

Преимущества: не требуется GIF-таймлайн, вероятно меньший payload после
контролируемого encode, лучшее качество на исходном 16:9 canvas. Риски: новый API/
frontend media type, browser codec matrix, mobile decode/CPU, poster/fallback и
контракт cache/hash.

### B — deterministic re-encode

Не выполнялся. Это допустимо только после отдельного решения о разрешённом способе
обработки и о том, какие derivative files можно bundling/redistribute. AI и
генеративная переработка не использовались. При принятии решения сравнить минимум
H.264 MP4 и WebM/animated derivative на одной и той же короткой выборке с locked
dimensions, duration, FPS, quality target и SHA-256.

### Что реально проверено

- source tree, candidate paths, file sizes, posters, Git revision — `PASS`;
- current manifest/validator/runtime consumers — `PASS`;
- 26 posters и 16 MP4 скачаны в отдельный временный каталог для bounded sample —
  `PASS` по фактическим локальным probes;
- Chromium browser run — `NOT_VERIFIED`: установленная Chromium distribution не
  найдена;
- WebKit browser run — `NOT_VERIFIED`: WebKit не установлен;
- Edge fallback — `NOT_VERIFIED`: isolated launch не поднялся;
- real Chromium/WebKit compatibility, network waterfall, CPU/RAM и physical mobile
  traffic — `NOT_VERIFIED`;
- full 593-file SHA-256/codec/duration inventory — `NOT_MEASURED`, так как это
  потребовало бы скачать весь source package и не было необходимо для bounded pilot.

## Рекомендуемый план миграции

1. Owner отдельно выбирает media contract: self-hosted MP4, WebM/MP4 pair либо
   сохранение GIF. Зафиксировать допустимые derivative operations и redistribution
   scope для exact source revision.
2. Domain/visual reviewer вручную разбирает 94 `REVIEW` rows; filename similarity
   не становится identity proof. При споре — `NO_MATCH`, current media сохраняется.
3. Для 13 `VERIFIED` выбрать 5–8 representative exercises, включая короткое,
   циклическое и длинное cardio движение, и сделать технический pilot без изменения
   production runtime.
4. Только после pilot gate подготовить отдельный implementation PR: versioned local
   assets, explicit provenance/NOTICE, validator, API/frontend contract, poster,
   reduced-motion, fallback, cache и negative tests.
5. Провести real AFTER package в Chromium/WebKit и на доступных mobile/TMA
   окружениях; synthetic/local pilot не выдавать за real device proof.
6. Отдельно получить owner visual acceptance, затем отдельное merge/release approval.
   Этот audit сам по себе не разрешает замену, merge, deploy или Issue close.

## Regression criteria для будущего implementation PR

- exact candidate revision и file-level SHA-256 locked in manifest;
- no untracked/raw HD originals, hotlinks, external runtime CDN or unknown remote
  source;
- current approved and blocked semantics preserved; no automatic unlock or fuzzy
  substitution;
- API/frontend types agree on media type, poster, dimensions, byte size and sources;
- poster, reduced-motion, decode/network error and text-technique fallback remain
  accessible;
- Chromium/WebKit/TMA and narrow mobile layout checked with measured transfer and
  decode cost;
- validator rejects wrong codec/extension, missing poster, missing hash, unexpected
  files and mismatched exercise identity evidence;
- existing catalog compactness, same-origin cache policy and no-sound behavior remain
  intact.

## Решения, которые ещё требуются от владельца

1. Выбрать допустимый production media contract и подтвердить, что он покрывает
   bundling/redistribution конкретных derivative files, а не только исследование
   source repository.
2. Разрешить или запретить deterministic re-encoding и определить format/quality/
   mobile budget после bounded pilot.
3. Одобрить semantic mapping для спорных `REVIEW` rows после ручной domain review.
4. После реализации отдельно принять полный visual AFTER package. Это не merge/deploy
   approval.
