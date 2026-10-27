# Local owner review workflow

## 1. Historical Stage 0 prototype

Подготовка требует только Python stdlib:

```powershell
cd D:\Pet-projects\your-fitness-coach\.artifacts\worktrees\task-386-app-experience-v3-stage0\docs\app-experience-v3\stage-0\prototype
D:\Pet-projects\your-fitness-coach\.venv\Scripts\python.exe -m http.server 4178 --bind 127.0.0.1
```

Открыть `http://127.0.0.1:4178/`. Это только исторический IA/click-path artifact; его visual
language, hero, cards, typography, shell и navigation styling не являются production direction.
Можно сразу получить нужное состояние:

```text
/?role=trainer&workspace=work&screen=today&direction=command&theme=light
/?role=trainer&workspace=personal&screen=personal&direction=radar&theme=dark
/?role=client&workspace=personal&screen=today&direction=stage&theme=light
```

Исторические captures проверены на ширинах `320`, `390`, `1440`; owner review текущего продукта
должен использовать production UI. Для справки prototype имеет narrow/mobile bottom navigation,
role separation и Work/Personal click path.

## 2. Текущий YFC local stack

Для полноценного source/demo review используется существующий stack, а не prototype server:

```powershell
Copy-Item .env.example .env
docker compose config --quiet
docker compose up -d --build backend worker
docker compose ps
```

После readiness текущий продукт открывается на `http://127.0.0.1:8000`, frontend hot reload —
через отдельный запуск:

```powershell
docker compose up -d db
npm --prefix frontend ci
npm --prefix frontend run dev
```

Windows developer environment использует `.venv\Scripts\python.exe`; production `.env`, OAuth
secrets, Telegram tokens и dumps запрещены. Для owner review достаточно static prototype и
существующего `/demo`; backend stack запускайте только с локальным `.env`.

## 3. Existing representative fixtures

- `/demo` использует `demo-curated-v2` и сценарий `trainer`, не записывает production user tables;
- `frontend/tests/e2e/fixtures/demo-session.ts` содержит trainer clients Alexey/Maria/Ivan;
- `frontend/tests/e2e/fixtures/platform-api.ts` поддерживает browser session, `trainerActive`,
  client summaries, attention, programs, nutrition, measurements, progress и workout states;
- новый mock backend для Stage 0 не создаётся.

Targeted existing suites, если запущен соответствующий local stack:

```powershell
npm --prefix frontend run e2e:ci -- demo-mode.spec.ts
npm --prefix frontend run e2e:ci -- app.spec.ts
```

Эти проверки — browser/mock fixture evidence. Они не доказывают real Telegram Android/iOS,
физическое устройство или production deployment.

## 4. Stop conditions

Остановиться и зафиксировать owner checkpoint при любом реальном auth/ownership regression,
production request, горизонтальном overflow, недоступном keyboard focus, смешении Work/Personal
данных или необходимости менять workflow/API/media. Не обходить проблему feature flag, direct
push или ручным deploy.
