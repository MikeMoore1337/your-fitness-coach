# I3 — финальная Root-публикация образовательной статьи

**Контекст:** [Hermes #558](https://github.com/MikeMoore1337/hermes/issues/558), YFC #1216, #1219, #1220. Дата: 25.10.2026.

**Production:** существующий owner-only `POST /api/v1/admin/articles/publish` уже доставлен, commit `119131f1cec004fae0eb6c0c2625e33f46888ee2`, [deploy #40216776830](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/40216776830) SUCCESS. Этот endpoint публикует без обязательной внешней аттестации, но только с настоящим access token пользователя `is_root`, проверенным по Telegram identity.

**Статус этой инструкции — выполнение живой статьи не подтверждено.** Код в GitHub или прохождение интеграционных тестов не являются фактом `POST` в production.

## Одноразовый локальный запуск на компьютере владельца

Сначала зайти в [YFC Admin](https://app.your-fitness-coach.ru/admin) через свою подтверждённую Root-сессию. Страница должна показывать полноценный административный кабинет, а профиль `/api/v1/me` — `is_root=true`. Без этого защищённый API обязан вернуть HTTP 403.

При необходимости получить *свой* краткоживущий access token **локально из той же авторизованной вкладки**: DevTools → Console → `sessionStorage.getItem('fit_access_token')`. Никуда его не отправлять, не сохранять в репозитории, Issues, скриншотах и переписке. Другие формы авторизации не подменяют Root.

В репозитории YFC на Windows PowerShell:

```powershell
git switch master
git pull --ff-only
py -3.14 -B scripts/publish_i3_owner_article.py
py -3.14 -B scripts/publish_i3_owner_article.py --publish
```

Последняя команда один раз запрашивает токен без отображения ввода. Веб-запрос уходит **только** к `https://app.your-fitness-coach.ru/api/v1/admin/articles/publish` и только при `--publish`; обычный запуск — чистый `DRY_RUN` без сети.

Скрипт загружает exact [I3 article fixture](../../backend/tests/fixtures/i3_plant_recovery_editorial_draft.json) с тремя научными источниками, без добавления рецензента, изменения `pending` или дозировок. Публикация одобрена владельцем на уровне продукта и явно помечается `scientific_verification=not_attested`.

**Квитанция:** `.artifacts/operations/i3-plant-recovery-publication.json` создаётся только после ответа `article_status=published` от живого Root API. Она содержит article ID, digest точной редакции, canonical URL, content version и флаг `public_api_verified` (отдельная повторная проверка статьи через public API). Секреты туда не записываются. Файл не является частью Git.

**Коды завершения:** 0 — Root POST и публичный API подтверждены; 4 — Root POST вернул published, но публичное чтение не подтверждено (квитанция сохранена); 2 — публикацию доказать не удалось, выполнить расследование без обхода авторизации. Повторный `--publish` с тем же контентом и slug безопасен: существующий endpoint возвращает опубликованную статью, а несовпадающее содержимое отклоняет как `slug_conflict`.

### Требование к финальной приёмке

Нужно сохранить обезличенную квитанцию успешного `--publish` (без bearer token и личных сведений) в Hermes #558 и проверить canonical URL, public API, sitemap и видимый текст. Только после этого допустимо отметить `I3_ARTICLE_PUBLISHED=VERIFIED` и закрыть интеграционный Issue.

**Не требуются:** HMAC Hermes, создание кандидата, научная подпись, подключение платных API, ручное изменение БД, повторное исследование всего пакета или Second Brain. Существующий Hermes intake независимо остаётся draft-only. Все источниковые ограничения публичной статьи должны сохраняться; медицинские назначения или гарантии эффекта недопустимы.
