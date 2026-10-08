# Product v10: Multi-Coach discovery recommendation (#757)

**Дата проверки:** 2026-10-08 (Europe/Moscow)
**Проверенный revision:** `44fe348aa5247878d9a5737341bede85ac63d59c`
**Статус:** DISCOVERY COMPLETE; IMPLEMENTATION NOT STARTED

Документ является read-only архитектурным и продуктовым discovery. Он не является
разрешением на создание организации, новой модели ролей, миграции, production
implementation или deployment.

## Итоговое решение

Текущая модель YFC безопасно поддерживает один активный тренерский контур на
клиента и отдельные тренерские ресурсы. Она **недостаточна для неограниченного
multi-coach доступа**: в базе есть уникальное ограничение на одну активную связь
тренер–клиент, а авторизация и данные строятся вокруг конкретной пары
`coach_user_id`/`client_user_id`.

Для будущей версии требуется отдельный проект архитектуры workspace/organization,
permission matrix и миграционный план. Нельзя безопасно получить multi-coach,
просто ослабив это ограничение или заменив один `coach_user_id` на общий идентификатор.

Терминальные границы этой задачи:

- `TASK_757_DISCOVERY=COMPLETE`;
- `MULTI_COACH_IMPLEMENTATION=NOT_STARTED`;
- организации, роли, assignment/transfer и shared templates не реализованы;
- `CONTROLLER=ABSENT`.

## 1. Объём и метод

Проверены текущие исходники, модели, сервисы, API, frontend auth/workspace,
миграции и существующие тестовые контракты для:

- identity и server-side authorization;
- связи тренер–клиент и приглашений;
- организации, ролей и assignment/transfer;
- программ, check-in/workflow templates и версий;
- аудита, аналитики и Client 360 meaningful changes;
- приватности trainer-private notes.

В текущем revision нет runtime-изменений для #757. Выводы ниже разделяют
подтверждённые возможности, требования будущего redesign и непроверенные риски.

## 2. Текущее состояние

| Область | Подтверждённый контракт | Ограничение для multi-coach |
|---|---|---|
| Identity | `User.is_coach`, `User.is_admin`, `User.is_active`; `require_user`, `require_coach`, `require_root_admin` | Нет organization/tenant/workspace ID и таблицы ролей |
| Связь с клиентом | `CoachClient(coach_user_id, client_user_id, status, labels, operational_status)` | PostgreSQL partial unique index `uq_coach_clients_one_active_per_client` разрешает только одну активную связь клиента |
| Приглашение/смена тренера | `confirm_coach_invite_link` завершает прежнюю активную связь и создаёт новую | Это смена текущего тренера, а не совместное ведение или передача с периодом пересечения |
| Авторизация Coach OS | `get_client_managed_by_coach`, `_is_coach_client`, `_coach_client_ids` фильтруют точного текущего тренера и `status=active` | Нет capability scope для Owner/Coach/Assistant/Read-only |
| Frontend workspace | `AuthProvider` и `CoachPage` используют `is_coach` | Нет выбора workspace/роли и нет UI для ограниченных ролей |
| Программы | `ProgramTemplate.owner_user_id`, `created_by_user_id`, `is_public`; `UserProgram.assigned_by_user_id` сохраняет источник назначения | Нет организации, общего каталога или ACL шаблона |
| Check-in templates | Тренер-владелец, версии и назначения с фильтром по coach/client | Модель не описывает публикацию между тренерами |
| Workflow templates (#756) | Тренер-владелец, версии, назначения и draft → edit → explicit confirmation | `coach_user_id` одновременно является владельцем и областью доступа |
| Audit | Append-only `AuditEvent` с actor/target/action/resource/details и bounded retention | Нет workspace/member/permission decision scope; JSON details требует будущей redaction policy |
| Analytics | Сводки строятся по активным клиентам конкретного тренера | Нет workspace attribution, дедупликации и правил видимости между тренерами |
| Client 360 | Meaningful changes считаются из ограниченных check-in snapshots; private notes возвращаются отдельно в coach-only workspace | Нельзя расширять видимость заметок вместе с новой ролью |
| Organization/roles | Runtime-моделей организации, Assistant, Read-only и tenant boundary не найдено | Любое добавление — архитектурная и миграционная задача, а не локальный флаг |

Основные подтверждающие места:

- `backend/fitminiapp_api/models/user.py`;
- `backend/fitminiapp_api/api/dependencies/auth.py`;
- `backend/fitminiapp_api/services/coach_clients.py`;
- `backend/fitminiapp_api/services/programs.py`;
- `backend/fitminiapp_api/models/audit.py` и `services/audit.py`;
- `backend/fitminiapp_api/services/analytics.py`;
- `backend/fitminiapp_api/services/coach_review_workspace.py`;
- `frontend/src/app/AuthProvider.tsx` и `frontend/src/pages/coach/CoachPage.tsx`.

## 3. Что можно переиспользовать

Переиспользование допустимо как foundation, но не означает, что текущая область
доступа уже безопасна для нескольких тренеров.

1. Текущие User/session primitives и server-side dependency chain — как базу
   для будущего вычисления workspace scope. Одного `is_coach` недостаточно.
2. Историю `CoachClient`, статусы, labels и timestamps — как legacy-источник для
   backfill и отображения истории, но не как финальную membership/RBAC модель.
3. `get_client_managed_by_coach` и аналогичные ownership guards — как паттерн
   fail-closed проверки после введения явного scope.
4. Program template ownership, clone flow, immutable-ish version history и
   `assigned_by_user_id` — как baseline для explicit publish/clone/assign.
5. Версии и idempotency contracts #751/#756; draft → edit → explicit trainer
   confirmation для коммуникаций. Автоматическая отправка не добавляется.
6. `record_audit_event` и bounded retention — как транспорт аудита после
   добавления workspace/member/action/before-after semantics и redaction.
7. Существующие progress/meaningful-change calculations и Coach OS surfaces —
   как bounded facts layer после permission filtering. Raw event noise и private
   notes не должны становиться общим feed.

## 4. Что требует redesign

Будущая реализация должна сначала утвердить контракт, а затем менять несколько
границ одновременно:

### Workspace и роли

Нужны явные workspace/organization, membership и capability model для Owner,
Coach, Assistant и Read-only. Роль должна быть scoped к workspace и ресурсам,
а не выводиться из глобального boolean `is_coach`.

Минимально необходимо определить: приглашение и отзыв membership, disabled/active
состояния, наследование прав, resource scope, конфликтующие права, audit actor и
правила для пользователя, состоящего в нескольких workspace.

### Клиент, назначение и передача

Нужна отдельная связь workspace–client–member с явным owner/primary coach,
дополнительными участниками, effective dates, revoke и transfer state. Нужно
задать правила одновременного доступа, конфликтов, pending transfer, повторов и
идемпотентности. Существующую уникальность одной активной связи нельзя снимать
без additive migration и доказанных authz/concurrency контрактов.

### Shared templates

Для программ, check-in и workflow templates нужны owner scope, visibility,
publish/clone/assign semantics, immutable versions, per-client snapshot и
правила отзыва уже назначенной версии. Нельзя давать доступ по совпадению ID или
просто копировать `coach_user_id` между пользователями.

### Аудит и аналитика

Audit должен фиксировать workspace, actor membership, capability, resource,
decision, correlation/idempotency key и безопасные before/after значения без
чувствительных payloads. Analytics должны иметь явную attribution/dedup policy
для нескольких тренеров и ограничение workspace scope до тяжёлых выборок.

### Приватность и клиентские поверхности

`TRAINER_PRIVATE_NOTE_MUST_NEVER_LEAK_TO_CLIENT` остаётся абсолютным инвариантом.
Private notes должны быть исключены из client API/UI, exports, analytics, logs,
AI context и screenshots/artifacts. Assistant и Read-only не получают к ним
доступ по умолчанию; даже Owner/Coach visibility должна быть явно определена и
проверена на сервере. Client-facing meaningful changes должны оставаться
отдельным безопасным представлением, а не побочным эффектом общей ленты аудита.

## 5. Security и privacy review

**Текущий результат:** `NO_CONFIRMED_FINDINGS`. Runtime для #757 не изменялся,
эксплойт или новая поверхность доступа не вводились. Следующие пункты —
обязательные design risks для будущего проекта, а не утверждение о наличии
уязвимости в текущем revision.

- BOLA/IDOR при чтении клиента, шаблона, версии или audit event через другой
  workspace;
- privilege escalation при смешении Owner/Coach/Assistant/Read-only и глобального
  `is_coach`;
- утечка trainer-private notes в client API/UI, export, analytics, logs, AI
  context или evidence artifacts;
- гонка transfer/revoke, orphaned access и stale authorization cache;
- подмена shared template, неожиданное изменение уже назначенной версии и
  cross-workspace template poisoning;
- replay приглашения или повторная обработка transfer/assignment без
  idempotency key;
- чувствительные значения в audit `details`, browser telemetry или product
  analytics;
- cross-tenant aggregation и inference по workspace analytics;
- миграция с default permissions, которая выдаёт избыточный доступ.

До будущего runtime PR обязательны threat model update, permission matrix,
негативные authz-тесты между workspace/ролями и leak tests для всех перечисленных
каналов. Новая чувствительная категория данных, внешний провайдер или внешний
поток не входит в #757.

## 6. Migration risks

Рекомендуется только additive migration:

1. создать workspace/member/resource-scope foundation и явно описать default
   workspace для legacy coach-client данных;
2. backfill текущую связь клиента с сохранением исторических `CoachClient`
   records, labels, timestamps и audit history;
3. ввести compatibility read path и dual-read verification до cutover;
4. перенести ownership/assignment в новую область доступа с deterministic
   idempotency и rollback/forward-fix plan;
5. только после rehearsal, authorization diff и production evidence решить судьбу
   старого partial unique index.

Нельзя удалять старые связи, silently merge workspaces, менять владельца шаблона
или отключать constraint в одной миграции. Нужны backfill counts, orphan checks,
permission reconciliation и восстановление на известный snapshot.

## 7. Performance risks

- scope permission queries должны отфильтровывать workspace/member/client до
  загрузки крупных фактов;
- нужны индексы по workspace/member/client/status/updated_at и измерение plan
  до и после миграции;
- workspace analytics не должны делать fan-out join на каждый raw event в
  synchronous request; materialization/async aggregation допустимы только после
  измеренного bottleneck;
- payload версий template и audit details должны иметь ограниченный размер;
- retention/partitioning audit следует проектировать по фактическому объёму, не
  добавляя преждевременную инфраструктуру.

## 8. Рекомендация для более поздней версии

| Фаза | Результат | Обязательный выход |
|---|---|---|
| 0. Контракт | Permission matrix, threat model, privacy partition, concurrency rules | Owner + architecture + security/privacy decision |
| 1. Foundation | Workspace, membership, scoped capabilities, compatibility boundary | Additive migration rehearsal and cross-scope authz tests |
| 2. Assignment | Multi-coach membership, primary coach, transfer/revoke, idempotency | Concurrency, audit completeness and rollback/forward-fix evidence |
| 3. Templates | Explicit publish/clone/assign, immutable versions, client snapshots | Version isolation, access revocation and history tests |
| 4. Surfaces | Scoped Coach OS, assistant/read-only views, privacy-safe client 360 and analytics | Mobile/TMA accessibility, Russian UI guard and production smoke |

Рекомендуемый порядок — сначала server-side scope и migration safety, затем
ресурсные шаблоны, затем UI. Нельзя начинать с добавления role picker или
ослабления существующего `require_coach`.

## 9. Явные no-go области для #757

В этой задаче запрещены:

- organization/RBAC/membership schema и Alembic migration;
- расширение `is_coach` до скрытой ролевой модели;
- снятие `uq_coach_clients_one_active_per_client`;
- multi-coach assignment/transfer runtime;
- shared template ACL или shared catalog;
- billing/accounting и медицинские cohorts/ranking;
- расширение видимости private notes или AI context;
- внешний календарь, provider или новый сервис;
- Landing implementation, copy, styling, motion или Coach Demo.

## 10. Будущие acceptance criteria

До запуска отдельной реализации должны существовать:

- server-side positive/negative authz tests для каждого role/workspace/resource
  сочетания;
- transfer/assignment concurrency tests, idempotency и deterministic retry;
- private-note leak tests для client API/UI, exports, analytics, logs, AI context
  и screenshots/artifacts;
- immutable template version, revoke, snapshot и history tests;
- audit completeness, redaction и retention checks;
- migration rehearsal, orphan/permission reconciliation и measured query plans;
- mobile Web/TMA role states, keyboard accessibility и русский user-facing UI;
- exact-head CI и production smoke только после отдельного owner/security/privacy
  решения.

## Решение для закрытия discovery

Подтверждено: текущая single-coach relationship architecture недостаточна для
безопасного неограниченного multi-coach режима. Дальнейшая реализация требует
нового owner-approved runtime task; #757 не создаёт такую авторизацию.

`TASK_757_DISCOVERY=COMPLETE`
`MULTI_COACH_IMPLEMENTATION=NOT_STARTED`
`PRODUCT_V10_CONVEYOR=CONTINUING`
`LANDING_IMPLEMENTATION=NOT_STARTED`
