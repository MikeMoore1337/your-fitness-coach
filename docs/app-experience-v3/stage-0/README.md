# App Experience v3 · Stage 0

Это локальный owner-facing пакет Issue #386. Он содержит аудит текущего authenticated UX,
зафиксированную target IA, deployment-isolation contract и исторический isolated static prototype.
Текущий production UI/components остаётся source of truth; prototype не является будущим дизайном.

## Быстрый просмотр прототипа

Из task worktree:

```powershell
cd D:\Pet-projects\your-fitness-coach\.artifacts\worktrees\task-386-app-experience-v3-stage0\docs\app-experience-v3\stage-0\prototype
D:\Pet-projects\your-fitness-coach\.venv\Scripts\python.exe -m http.server 4178 --bind 127.0.0.1
```

Откройте <http://127.0.0.1:4178/>. Сервер использует только Python stdlib; API, БД, auth,
Telegram и production не вызываются.

## Что смотреть владельцу

- роль `Тренер` и `Клиент`;
- в роли тренера переключатель `Work · Тренер` / `Personal · Для себя`;
- исторический click-path artifact с тремя rejected visual explorations;
- `Сегодня`, `Клиенты`, `Для себя`, `Каталог`, `Тренировка`;
- theme toggle Light/Dark;
- narrow/mobile bottom navigation и desktop rail.

Состояние можно открыть детерминированно через query string, например:

```text
http://127.0.0.1:4178/?role=trainer&workspace=work&screen=today&direction=command&theme=dark
```

Не использовать его hero, typography, cards, navigation styling или shell как design input для
#387. Для production review открывайте текущий `/demo` и существующие authenticated surfaces.

## Пакет документов

- [Аудит текущего authenticated UX](CURRENT_AUTHENTICATED_UX_AUDIT.md)
- [Target IA и контекст Work/Personal](APP_EXPERIENCE_V3_TARGET_IA.md)
- [Integration и release contract](INTEGRATION_BRANCH_AND_RELEASE_CONTRACT.md)
- [Local owner review workflow](LOCAL_OWNER_REVIEW_WORKFLOW.md)
- [Stage 0 prototype evidence](STAGE0_PROTOTYPE_EVIDENCE.md)
- [Future stages contract check](FUTURE_STAGE_CONTRACT_CHECK.md)
