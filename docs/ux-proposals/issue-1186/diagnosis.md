# Issue #1186: инвентаризация и геометрическая диагностика

Эта записка содержит инвентаризацию и root-cause диагностику. После owner REQUEST CHANGES
contain-вариант заменён на source-aware filled-square framing в Draft PR #1221; merge/deploy не
выполнялись.

## Текущий каталог

На `origin/master` `94a9b5f3875bae858d0ea816cc47fc9d22ae9dd0` пересчитаны источники:

- 207 seed-записей;
- 206 canonical упражнений после redirect `kettlebell-goblet-squat -> goblet-squat`;
- 171 approved media и 35 blocked записей без одобренного source-backed материала;
- 167 первичных GIF-анимаций 180×180, 4 первичных статических изображения 1280×720;
- 81 упражнение с 158 MP4-источниками;
- 77 упражнений с широким poster/source 16:9;
- 881 уникальный файл из manifest: все существуют, размеры совпадают с manifest, SHA-256 совпадают,
  image-header dimensions совпадают.

Полная исходная матрица: [JSON](./media-inventory.json) и [CSV](./media-inventory.csv). Её можно
пересобрать командой `node scripts/build_issue_1186_media_inventory.mjs`.

## Причина дефекта

Дефект воспроизводится на approved упражнении с 16:9 poster, например `incline-bench-press`,
когда video/GIF недоступен или включён reduced motion.

1. `.active-workout-exercise__media` задаёт ширину, а дочерним `img` задаются `width: 100%`,
   `height: 100%`, `aspect-ratio: 1` и `object-fit: contain`.
2. При fallback через `<picture>` сам `.exercise-media-picture` не получает определённых квадратных
   `width` и `height`.
3. В результате intrinsic height 16:9 poster участвует в расчёте wrapper. В минимальном браузерном
   воспроизведении при ширине 280 CSS px получено: `picture/media ≈ 280×828`, внешний блок с
   рамкой `282×830`.
4. Прямой `<video>` при тех же правилах даёт `280×280`, поэтому проблема выглядит зависимой от
   ветки источника, хотя причина находится в геометрическом контракте wrapper.
5. После исправления квадратная surface фиксируется на всех трёх production-поверхностях, а
   широкие источники получают `cover` только после проверки сохранности техники.

Текущая CSS-геометрия thumbnails намеренно не входит в исправление: каталог и picker используют
фиксированные поверхности 52/58 px.

## Визуальная стратегия

### Сравнение A — заполненный квадрат с center cover

Задать квадратный контракт поверхности и квадратные размеры picture-wrapper. Для 16:9
`object-fit: cover` заполняет surface самим изображением, но оставляет только 56.25% исходной
ширины. Center crop безопасен только после проверки конкретного упражнения и трёх кадров.

### Сравнение B — заполненный квадрат с focal cover

Сохранить тот же square + `cover`, но для широкого источника задать source-aware
`object-position` после проверки начала, середины и конца. Это сохраняет пропорции и убирает
пустые полосы, но допускает только доказанный crop. Для квадратного GIF положение остаётся
нативным 1:1 без дополнительной обрезки.

Оба варианта сохраняют текущую priority: MP4 → лицензированный GIF → poster/static → accessible
missing state; reduced motion не создаёт video. Ни один вариант не заменяет исходный media, не
запускает транскодирование и не использует AI-кадрирование.

Реальное сравнение Dark/Light для 320/360/393/430 px и кадры 0%/50%/последний доступны в
[изолированном HTML-прототипе](./visual-prototype.html). Матрица всех 206 упражнений — в
[media-framing-matrix.json](./media-framing-matrix.json) и [CSV](./media-framing-matrix.csv).
Реальные production AFTER для guide/lightbox/Active Workout находятся в
[evidence/after-cover](./evidence/after-cover/).

## Результат и ограничения

В текущем candidate 167 строк проходят source-aware/native framing без ISSUE: 94 native-square и
73 filled-square. Четыре точечных исключения (`plank`, `push-up`, `reverse-crunch`, `side-plank`)
сохраняют `contain-exception`, потому что 56.25% crop удаляет голову, стопы или траекторию в
проверенных кадрах. Это не универсальный contain: остальные 73 wide source используют cover с
индивидуальным focal point там, где это нужно.

35 blocked упражнений остаются отдельными source-gap исключениями: отсутствие source не
компенсируется crop, генерацией или неподтверждённым материалом. Инвентаризация проверяет
metadata и целостность файлов; wide MP4 дополнительно прошли start/middle/end visual sweep.
Геометрия сама по себе не доказывает сохранность техники — для четырёх исключений приложены
контактные листы и требуется отдельное owner решение. До visual approval PR остаётся Draft;
merge/deploy и закрытие Issue не входят в этот этап.
