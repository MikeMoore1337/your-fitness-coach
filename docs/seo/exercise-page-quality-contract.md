# Контракт качества публичной карточки упражнения

Документ задаёт минимальный gate для публикации и индексации публичной карточки упражнения.
Он создан на примере `/exercises/bench-press` в рамках Task 241C. Контракт не означает, что
каждое упражнение из внутреннего каталога автоматически становится публичным.

## 1. Каноническая запись и allowlist

Публичная карточка допускается только при наличии всех элементов ниже:

- стабильный `Exercise.id` и канонический `slug` из доменного каталога;
- явная запись в `frontend/src/content/publicContent.json` со статусом `published`;
- точное соответствие страницы и записи в `backend/fitminiapp_api/services/public_exercises.py`;
- успешный ответ существующего `GET /api/v1/public/exercises/{slug}`;
- одна каноническая URL без вариантов написания, региона, пола, страны или variant-doorway;
- запись в sitemap только через опубликованный content manifest.

Текущий публичный allowlist намеренно мал: `bench-press`, `lat-pulldown`, `squat`, `deadlift`,
`overhead-press`. Добавление упражнения в базу или наличие guide-профиля само по себе не включает
его в public API, маршрут, sitemap или индексацию. Вторая волна добавила только эти две записи,
потому что для них уже существуют канонический каталог, guide-профиль, проверенные media и
лицензионная provenance; новые production media не создавались.

## 2. Источник фактов

Домен остаётся единственным источником механики упражнения:

- `EXERCISE_CATALOG` задаёт канонические название, основную группу мышц и оборудование;
- `exercise_guides.PROFILES` задаёт проверенный доменный guide-профиль: шаги, дыхание, ошибки и
  вторичные мышцы;
- `DEFAULT_SAFETY_NOTES` задаёт консервативную общую заметку по безопасности;
- `public_exercises()` собирает из этих источников API DTO и проверяет quality gate;
- публичный React-экран и серверный SEO fallback используют один и тот же public API record.

`publicContent` владеет только редакционными полями: title, description, intro, контекстом,
related-ссылками, CTA и breadcrumbs. В него нельзя копировать шаги техники, дыхание, ошибки,
мышцы или safety notes для увеличения SEO-текста.

## 3. Минимальное содержимое

Индексируемая карточка должна иметь непустые и осмысленные:

- title и естественный H1 с понятным поисковым намерением;
- primary и secondary muscles, equipment и difficulty;
- ordered technique steps, достаточные для базового понимания setup и execution;
- breathing;
- common mistakes;
- safety notes без диагноза, лечения, гарантии или универсального обещания отсутствия травм.

Техника должна быть видна без входа в аккаунт и не прятаться за обязательным accordion. Детали
можно раскрывать прогрессивно только если основной ответ остаётся доступен обычным чтением.
Варианты и альтернативы добавляются только при наличии канонической связи или проверенной
каталожной записи; общая похожесть мышц не является достаточным основанием.

## 4. Происхождение и лицензия

Для самой карточки обязательны `source_name`, `source_url`, `source_license` и, если применимо,
`source_license_url`. Для опубликованного media обязательны same-origin asset URL, meaningful
alt, размеры, порядок фаз, source/license provenance и запись в
`backend/assets/exercise-guides/manifest.json`.

Текущие изображения bench press — существующие локальные JPEG-фазы из `free-exercise-db`,
лицензия `Unlicense (общественное достояние)`. Их происхождение зафиксировано в
`backend/assets/exercise-guides/NOTICE.md` и manifest. Нельзя использовать hotlink, случайный
stock, скриншот конкурента, неподтверждённую технику или защищённый материал без прав.

## 5. Visual и responsive gate

Если media публикуется, на изображении должен быть человек, выполняющий именно это упражнение;
абстрактная иконка или stick figure не заменяют демонстрацию. Изображения должны иметь
responsive sources либо явные размеры/aspect ratio, не вызывать horizontal overflow и не
загружать тяжёлое необязательное видео автоматически. Новая owner-reviewable визуальная asset
останавливает lifecycle на `OWNER_VISUAL_APPROVAL_REQUIRED`; переиспользование уже проверенного
локального media такого checkpoint не создаёт.

До merge проверяются desktop и mobile, light и dark темы, читаемость текста, wrapping,
контраст, focus, sticky header и отсутствие clipping/overflow.

## 6. SEO и fallback gate

До hydration HTML public route должен содержать:

- уникальные title и meta description;
- один H1 и краткий полезный intro;
- факты/технику или достаточный правдивый контекст намерения;
- crawlable breadcrumbs и существующие internal links;
- canonical ровно на текущую публичную URL;
- точную sitemap-запись без spelling/region/variant duplicates.

Fallback не может содержать независимую копию доменной механики. При отсутствии или нарушении
качества canonical record маршрут не получает indexable metadata и не должен молча проходить
как опубликованная тонкая страница.

Разрешены только truthful `WebPage` и `BreadcrumbList` (и уже существующие общие схемы, когда
они совпадают с видимым содержимым). Не добавляются фиктивные `FAQ`, `HowTo`, `Review`,
`AggregateRating` или `MedicalWebPage`.

## 7. UX, accessibility и product handoff

Проверяются heading order, breadcrumb navigation, meaningful image alt, `ol` для шагов, списки
для ошибок и безопасности, keyboard/focus для ссылок и media controls/lightbox, контраст и
skip-link. Чтение техники не требует login.

CTA описывает существующее действие. Разрешён handoff вроде `Открыть тренировки в Your Fitness
Coach` с объяснением, что в приложении можно выбрать/создать программу, работать с упражнениями
и провести тренировку. Нельзя обещать автоматическое добавление текущего упражнения и нельзя
передавать персональное состояние через небезопасные query parameters. Событие
`exercise_added_from_public_page` остаётся future-only, пока реальный add flow не появится.

## 8. Проверка перед публикацией

Для каждого нового allowlisted exercise проходят deterministic tests на domain/API, required
arrays и provenance; HTML/React tests на metadata, fallback, sitemap, loading/error/success,
accessibility и truthful CTA; regression для `/exercises`, `/exercises/squat` и
`/exercises/lat-pulldown`; lint/typecheck/build; browser visual QA. `public_exercise_quality_errors`
и `validate_public_exercise_quality` блокируют запись с отсутствующими `technique_steps`,
`common_mistakes`, `safety_notes`, source или license.

Последовательность допуска:

`canonical domain record → explicit allowlist → quality gate → public API/rendering → SEO/fallback →
responsive/accessibility QA → sitemap/indexability`.

Ни один последующий catalog import или DB seed не должен обходить эту последовательность.
