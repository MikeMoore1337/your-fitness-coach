# YFC Threat Model

Статус: active living document. Этот файл описывает security boundaries продукта, а не гарантирует
отсутствие уязвимостей. При расхождении с текущим кодом сначала фиксируется реальное поведение.

## Product scope

YFC - один продукт с Web и Telegram Mini App, общим FastAPI backend, Aiogram bot, PostgreSQL,
внешними AI/provider интеграциями и production delivery через GitHub Actions/Docker/VPS.

## Assets

Наиболее значимые активы:

- identity, sessions, access/refresh tokens и OAuth/Telegram credentials;
- пользовательские тренировки, программы, питание, прогресс, комментарии тренера и связанные данные;
- загружаемые изображения и извлечённые из них данные;
- роли/права пользователя, тренера и других privileged surfaces;
- PostgreSQL integrity/confidentiality;
- application/provider/deployment secrets;
- целостность AI Coach/Nutrition Vision policy gates;
- CI artifacts, container images и production deployment state.

## Actors

- неаутентифицированный Internet client;
- аутентифицированный обычный пользователь;
- пользователь, пытающийся выйти за границы собственных объектов;
- privileged/trainer actor с легитимной учётной записью;
- внешние Telegram/GitHub/AI/provider systems;
- CI/deployment automation;
- оператор production.

Компрометация стороннего provider целиком не моделируется как контролируемая YFC защита, но YFC
должен минимизировать отправляемые данные, scopes, lifetime и последствия отказа provider.

## Trust boundaries

### B1. Browser / TMA -> public HTTP edge -> FastAPI

Client полностью недоверенный. Любые identifiers, role flags, ownership hints, MIME, filenames,
query/body/header values должны считаться attacker-controlled до серверной проверки.

Ключевой invariant: авторизация и ownership проверяются на backend для каждого защищённого действия.

### B2. Telegram -> TMA/bot -> backend identity

Telegram initData и связанные identity assertions становятся доверенными только после серверной
проверки подписи и применимых freshness/replay ограничений.

Ключевой invariant: client-provided Telegram user id сам по себе не является доказательством identity.

### B3. GitHub OAuth -> callback -> YFC account/session

OAuth response пересекает внешнюю identity boundary.

Ключевые invariants: state/session binding, ожидаемый callback, ограниченный redirect flow и отсутствие
token leakage в URL/logs/telemetry.

### B4. FastAPI / bot -> PostgreSQL

Backend application identity имеет существенно больше прав, чем внешний client.

Ключевые invariants: parameterized data access, object ownership/role scope, безопасные migrations,
предсказуемые transaction boundaries и отсутствие mass assignment privileged fields.

### B5. Upload -> backend processing -> Nutrition Vision provider

Изображение и его metadata недоверенные. Перед внешним provider появляется privacy boundary.

Ключевые invariants: bounded size/type/path handling; файл не становится local path primitive;
реальные изображения не покидают YFC без активного provider/policy gate; provider response считается
недоверенным input до schema/business validation.

### B6. AI Coach -> external AI provider / proxy-egress

Пользовательский контекст может покидать основной backend через отдельный network/provider boundary.

Ключевые invariants: минимизация sensitive payload; provider output не является authorization
decision; prompt/content не меняет application secrets/config; timeout/retry/logging не раскрывают
чувствительные данные.

### B7. Backend -> arbitrary/external URLs

Любая функция, принимающая URL или косвенно формирующая target из user/external data, создаёт SSRF
boundary.

Ключевые invariants: scheme/host/redirect/IP policy по реальной задаче, bounded timeout/body size,
отсутствие доступа к loopback/link-local/internal metadata/service networks без явного contract.

### B8. GitHub Actions -> registry/artifacts -> production VPS

CI имеет privileged delivery capabilities.

Ключевые invariants: минимальные workflow permissions, секреты только через разрешённые secret stores,
immutable/exact-head provenance, проверяемые images/artifacts, отсутствие production deploy из
непроверенного head.

## Cross-cutting security invariants

1. UI никогда не является единственным authorization control.
2. User-owned resource требует server-side ownership/role scope на read и write.
3. Dev/demo auth и debug defaults не должны тихо становиться production trust path.
4. Secrets/tokens не возвращаются client и не логируются целиком.
5. External provider response, webhook/event и uploaded content остаются untrusted input.
6. Sensitive state changes учитывают replay/idempotency/concurrency там, где повтор опасен.
7. User-controlled network targets не получают unrestricted backend egress.
8. Privacy/security policy gates fail closed, особенно для image/AI flows.
9. Dependency/container finding оценивается по реально используемой версии и reachable surface.
10. CI/deploy не ослабляет runtime security ради удобства release.

## Priority attack paths

| Attack path | Broken property |
| --- | --- |
| подмена user/resource id | cross-user BOLA/IDOR |
| forged/replayed Telegram identity | account impersonation |
| OAuth state/redirect misuse | session/account confusion or token exposure |
| crafted upload/path/oversized input | file/path abuse or resource exhaustion |
| user-controlled URL -> internal target | SSRF/internal service access |
| untrusted fields -> privileged model update | mass assignment/privilege escalation |
| secrets/request bodies in logs | credential or sensitive-data disclosure |
| bypass Vision/AI provider gate | unauthorized external data disclosure |
| AI/provider output used as trusted command | authorization/configuration bypass |
| compromised dependency/image/config | supply-chain/runtime compromise |

## Security Review triggers

Repository-native `diff` review нужен, если изменение затрагивает хотя бы одну из областей:

- auth/authz, roles, sessions, OAuth, Telegram identity;
- secrets/tokens, webhooks, cryptography, CORS/security headers;
- uploads/parsers/images, user-controlled paths or URLs;
- sensitive user data, export/delete, external AI/provider payload;
- trainer/admin/privileged actions;
- dependencies, Docker/runtime privileges, CI/deployment security;
- rate-limit/replay/idempotency на security-sensitive action.

`full` review запускается отдельно перед крупным security hardening/release milestone или по явному
запросу владельца. Он не является автоматическим шагом каждого PR.

## Evidence and maintenance

Finding должен ссылаться на текущий code path/config/test и иметь воспроизводимую проверку либо
оставаться unvalidated concern.

При добавлении новой identity/provider/upload/network/deployment boundary этот файл обновляется в той
же task. Accepted risk фиксируется явно в task/PR evidence; молчаливое принятие риска не считается
решением.
