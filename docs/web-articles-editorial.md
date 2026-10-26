# Публичные Web-статьи и SEO-контур

Статус документа: Task 130, локальный/mock-контур. Документ описывает канонический
жизненный цикл статьи, границу Hermes → YFC и правила публикации. Наличие кода и
локальных тестов не означает, что production-индексация, Search Console или живой
Hermes/provider уже подключены.

## Граница продукта

Публичная статья — отдельный индексируемый раздел, а не продолжение продающего
лендинга. Лендинг может показывать не более трёх опубликованных curated-карточек;
полный каталог живёт на `/articles`.

| Путь | Назначение | Публичный статус |
| --- | --- | --- |
| `/articles` | индекс статей | 200 даже при пустом каталоге |
| `/articles/<slug>` | каноническая статья | только `published`, иначе 404 |
| `/api/v1/public/articles` | карточки для Web/лендинга | только `published` |
| `/api/v1/public/articles/<slug>` | полный read model | только `published` |
| `/sitemap.xml` | discovery поисковыми роботами | только `published` |
| `/api/v1/hermes/articles/intake` | узкий вход исследовательского draft | не публикует |

Источник истины — `WebArticle` и неизменяемые `WebArticleRevision` в базе. Backend
рендерит содержательный HTML-fallback для crawler/readability, а React после загрузки
гидратирует тот же контракт через public API. Frontend не создаёт статью и не может
обойти backend-статус.

## Жизненный цикл и ручные ворота

Допустимые статусы: `candidate → researching → draft → review → approved → published`.
Отдельные состояния: `update_required`, `archived`, `retracted`.

- `candidate` — возможность для редакции, не обещание публикации.
- `draft` — Hermes или другой исследователь подготовил материал; он не индексируется.
- `review` — редактор проверяет русский текст, intent, источники и внутренние ссылки.
- `approved` — редактор явно одобрил конкретную версию.
- `published` — отдельное owner/editor-действие `publish_web_article`; только эта
  операция открывает URL, API, sitemap и landing-card.
- `update_required` — опубликованная версия временно закрыта после изменения источника
  или обнаружения проблемы. Предыдущий revision сохраняется; новая версия проходит
  тот же review → approval → publish путь.
- `archived`/`retracted` — материал снят с публичного контура. Ретракция не удаляет
  аудит и причину исправления.

Hermes intake всегда создаёт только `draft`. В endpoint нет операции publish, deploy,
Telegram-send или произвольного shell/provider tool call.

## Кандидаты и приоритизация

Кандидат может прийти из трёх allowlisted-контуров: `manual`, `seo_import` или
`news_handoff` (из Task 129). Для `news_handoff` сохраняется ссылка на исходный
news-cluster/revision, но Web-статья получает отдельное решение о публикации.

`score_article_candidate` оценивает opportunity, а не качество и не approval. В расчёт
входят независимые сигналы: поисковый спрос, ясность intent, тематическая и продуктовая
релевантность, польза аудитории, evergreen-потенциал, наличие evidence, overlap с
текущим контентом, потенциал внутренних ссылок, стоимость risk-review, потребность в
свежести и news opportunity. Overlap, risk и freshness не сворачиваются в ложное
«разрешение на публикацию».

`sports_nutrition` и `dietary_supplements` — разные topic-классы. Оба относятся к
чувствительному контуру и требуют более строгой проверки; нельзя маскировать обзор
добавок под обычную evergreen-статью.

## Решение владельца о публикации без внешней экспертизы

Для **только подтверждённого Root-владельца** действует отдельная команда
`POST /api/v1/admin/articles/publish` с `HermesWebArticleProposal`,
`acknowledge_unverified_evidence=true` и точным флагом
`generated_with_ai`. Результат — **публикация за одно аутентифицированное
действие**, без дополнительного кандидата в БД, Hermes HMAC, внешнего
экспертного заключения или нового публикационного сервиса.

Это осознанное полномочие владельца продукта. Оно **не меняет** статусы
`claim_source_matrix[].review_status`: `pending` остаётся `pending`;
`evidence_level=limited` и исходные ограничения остаются видимыми в публичном
API. Ответ содержит `scientific_verification=not_attested`, а immutable
revision и audit записывают `root_owner_publication` и реального root-actor.
Однотипная повторная отправка exact того же материала не создаёт новую
версию. Existing Hermes-draft с тем же `slug` и content hash публикуется
без повторного intake; несовпадающее содержимое возвращает конфликт и не
перетирает чужую редакцию.

Граница безопасности: требуется реальная verified Root Telegram-сессия,
валидный полный article contract, HTTPS-источники, точная матрица утверждений;
явно `blocked` или `does_not_support` не публикуются как поддержанный факт,
а `high/critical` остаются под проверкой `domain_reviewer` при валидации
схемы. Никаких поддельных рецензентов, подписей и `verified`.
Обычный Hermes ingress продолжает создавать **только draft** и не получил
больших полномочий.

Root может использовать собственную проверку и утвердить нейтральный
образовательный обзор в обход **внешних организационных** gate; это не
медицинское заключение, не персональная рекомендация и не разрешение
на нарушение авторского права/закона. Публикацию нельзя выдавать за
независимую научную сертификацию.

## Hermes → YFC

Hermes рассматривается как недоверенный внешний worker. На вход принимается ограниченный
research packet и Russian draft proposal со следующими обязательными частями:

- `candidate_id`, `research_version`, `schema_version`, `provenance`;
- slug, title, description, lead, секции тела и search intent;
- claims, sources и полная `claim_source_matrix`;
- author/editor, при необходимости domain reviewer;
- allowlisted CTA без произвольного URL и SEO-полей;
- source URL только по HTTPS.

Аутентификация и эксплуатационные ограничения переиспользуют Task 129:
`X-Hermes-Key-Id`, `X-Hermes-Timestamp`, `X-Hermes-Nonce`, `X-Hermes-Signature`;
подпись — HMAC-SHA256 от `timestamp + "\n" + nonce + "\n" + raw_body`. Проверяются
key id, clock skew, размер тела, nonce replay, idempotency key и rate limit. Ошибки
наружу нормализуются; секреты, raw body, Telegram IDs и персональные данные не попадают
в аналитику или audit details.

Hermes может использовать CLI/gateway и messaging/scheduled-job интеграции согласно
[официальному репозиторию Hermes](https://github.com/NousResearch/hermes-agent) и
[официальной документации Hermes](https://hermes-agent.nousresearch.com/docs/), но
конкретный provider, outbound account, live Telegram и расписание не являются частью
этой задачи. В YFC флаги intake по умолчанию выключены. Включение требует отдельного
owner gate на выбранную версию Hermes, изоляцию, retention, outbound domains, ротацию
ключа и rollback.

## Evidence и редакционная проверка

Каждое существенное утверждение получает стабильный `claim_id`, одну или несколько
ссылок на source и статус матрицы `pending | verified | blocked`. `evidence_review`
требует несколько источников. Для `high`/`critical` risk и для sensitive topics нужен
`domain_reviewer`. Не используется AI-detector как автоматический gate: проверяется
смысл, происхождение, источники, ограничения, русский язык и польза читателю.

Верификация не превращает исследовательский результат в медицинскую рекомендацию.
Ограничения источника хранятся рядом с ним и с claim; числа без проверенной поддержки
блокируются для следующего ручного шага.

## SEO и публичный read model

Для опубликованной статьи backend формирует:

- уникальный slug и canonical на `public_origin()/articles/<slug>`;
- title, description, Open Graph metadata и `og:type=article`;
- JSON-LD `Article` с author/editor/reviewer, `datePublished` и `dateModified`;
- server-readable H1, lead, секции, источники, related links и CTA;
- запись в sitemap с `lastmod`.

Draft, review, approved, update_required, archived и retracted не появляются в sitemap,
public API или indexable HTML. Публичный маршрут не использует framework rewrite как
единственный источник SEO-содержимого: первоначальный ответ backend уже содержит
заголовок и текст статьи.

При изменении источника сначала ставится `update_required`, затем создаётся новый
immutable revision. Публикация новой версии меняет `content_version` и `dateModified`,
а прошлый snapshot и audit reason остаются доступными для проверки и rollback-решения.

## Аналитика и воронка

Контракт добавляет только privacy-safe события:

- `article_viewed` с allowlisted slug в `content_key`;
- `article_cta_clicked` с allowlisted slug и destination `tma | web | landing`.

Событие CTA — это intent, а не lead. В отчётах отдельно различаются view, CTA intent,
qualified lead, server-confirmed conversion и activation. Не передаются raw query,
поисковый текст, тело статьи, URL с токенами, user ID, Telegram ID, health data или
контент формы. Недоступный analytics provider не блокирует чтение статьи или редакционный
pipeline.

## Локальная проверка и release gates

Минимальная проверка Task 130 выполняется в worktree:

```powershell
D:\Pet-projects\your-fitness-coach\.venv\Scripts\python.exe -m pytest backend/tests/test_web_articles.py backend/tests/test_web_public.py -q
Set-Location frontend
npm run typecheck
npm run lint -- --quiet
npm run test -- --run tests/unit/shared/analytics/productEvents.test.ts
npm run build
```

Перед owner approval нельзя считать локальный/mock HTML доказательством live search
indexing, реального Telegram Mini App, физического устройства, live Hermes/provider,
внешней SEO-учётной записи или production публикации. Эти проверки выполняются только
отдельным явно разрешённым release-процессом.


## I4 #599: резервирование кандидата из того же подписанного draft intake

HMAC `POST /api/v1/hermes/articles/intake` не расширяет привилегий.
Если заранее созданного `candidate_id` ещё нет, **только** полноценный
валидированный `HermesWebArticleProposal` научного формата
`evidence_review/research_update` с минимум двумя **разными**
allowlisted HTTPS-первоисточниками может создать candidate **атомарно**
с первым `draft` через тот же существующий endpoint/DB transaction.
Отдельного публичного endpoint кандидатов, нового ключа или пути
публикации не добавляется. Предыдущие Root/manual кандидаты сохраняют
совместимость. Изменённые slug/version, повтор с другим nonce,
неизвестные подписи и непроверенные ссылки отклоняются.

Идентификатор для нового signed-auto кандидата должен совпадать с
проверяемым сервером SHA-256, первые 32 hex-символа:

```text
json_string = JSON(sorted_keys, compact_separators) {
    "schema": "hermes-i4-autocandidate-v1",
    "slug": proposal.slug,
    "source_urls": sorted([str(source.url) for source in proposal.sources])
}
candidate_id = SHA256(UTF8(json_string))[:32]
source_ref = "i4:" + SHA256(UTF8(json_string))
```

Существующий allowlisted `source_kind=news_handoff` используется как
внешний research/news handoff, без миграции БД. Появившийся кандидат
остаётся только в `draft`, а ревизия в Root editorial inbox.
Список доменов для этого узкого режима:
`pmc.ncbi.nlm.nih.gov`, `pubmed.ncbi.nlm.nih.gov`,
`europepmc.org`, `www.mdpi.com`; без userinfo, query, fragment,
нестандартных портов и повторов. Наличие ссылки **не доказывает**
качество источника: научные замечания и фактическая публикация
остаются исключительно за человеком.

HMAC-отправитель не имеет права представляться квалифицированным
рецензентом и повышать `review_status=verified` самостоятельно:
такие запросы отвергаются даже с валидной подписью. Статусы
`pending` не меняются. Для auto-candidate также запрещены
`high/critical`, искусственные `domain_reviewer`, заявленные
`high/moderate` certainty и публикация. Невалидные попытки дают
ограниченный 422/409, без привилегий. Автозапуск/подписание реальных
материалов без проверенного полного текста и разрешения на deployment
по-прежнему запрещены.
