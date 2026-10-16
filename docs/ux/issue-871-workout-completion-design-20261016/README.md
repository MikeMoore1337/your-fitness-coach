# Issue #871 — итоги тренировки, справочник и даты напоминаний

Статус этого пакета: **DESIGN_ONLY**. Это воспроизведение текущего экрана, один согласованный вариант финального макета и план проверки. Production JSX, production CSS, API, миграции и тестовые фикстуры не изменялись.

Проверенная база: `origin/master` SHA `8a5c955400de87eed8c92974bd196a8343c6cd35` от 16.10.2026. Рабочая ветка: `codex/issue-871-workout-completion-design`. Пакет подготовлен по текущему `frontend/src/features/workouts/WorkoutCompletionSummary.tsx`, а не по исторической цепочке JSX из Issue.

## Решение для проверки владельцем

Единый предложенный порядок в DOM и на экране:

`Тренировка завершена` → метрики (`Длительность` / `Упражнений` / `Подходов` или `Этапов`) → нативный `<details>` `Записанные результаты` → подтверждённые `Личные результаты` → feedback и заметка → `Следующий шаг`.

`AI Coach` не входит в предложение: в текущем продукте он скрыт feature-gate после PR #1021, поэтому в макете нет ни карточки, ни CTA, ни пустого места под него.

Для пустых результатов `<details>` сохраняется непосредственно после метрик. Внутри показывается только честное сообщение `Подтверждённых результатов нет.` — без вымышленных значений. Блок личных результатов отсутствует, если подтверждённых рекордов нет.

## Фактический DOM и сопоставление

В текущем браузерном synthetic capture при выключенном AI Coach фактические прямые дети `.workout-completion` идут так:

`hero → facts → next → records → results → demo-capability-fieldset`.

Это подтверждает, что текущая реализация опирается не только на CSS: `Следующий шаг` и личные результаты находятся перед раскрытием записанных результатов. Для нового порядка потребуется отдельная согласованная реализация перестановки JSX; в этом пакете она намеренно не выполняется.

Детальный машиночитаемый контракт — [`dom-contract.json`](dom-contract.json). В proposed-прототипе [`prototype.html`](prototype.html) порядок уже задан физическим порядком узлов:

`hero → facts → results/details → records (если есть) → feedback → next`.

Селекторы и данные сохраняются в терминах текущего компонента: `.workout-completion__hero`, `.workout-completion__facts`, `.workout-completion__results`, `.workout-completion__records`, `.workout-completion__feedback`, `.workout-completion__next`. Native `<summary>` остаётся клавиатурно и семантически раскрываемым; `aria-expanded` синхронизируется в прототипе с состоянием `<details>`.

## Evidence-пакет

Все данные synthetic, без production credentials и приватных пользовательских скриншотов.

- BEFORE текущего runtime: [`evidence/before`](evidence/before) — Chromium, Dark/Light, `320×800`, `360×800`, `393×844`, `430×932`, `1280×720`; AI Coach в DOM отсутствует при provider-off.
- Один окончательный PROPOSED: [`evidence/proposed`](evidence/proposed) — те же пять размеров и две темы.
- Сценарии: [`evidence/states`](evidence/states) — `strength`, `cardio`, `mixed`, `empty`, `many`, `long`, а также focus на раскрытии и ввод заметки при условной клавиатуре.
- Проверки макета: [`evidence/prototype-checks.json`](evidence/prototype-checks.json) — отсутствие горизонтального overflow на пяти размерах, прямой порядок `facts → results`, наличие feedback note, `aria-expanded` и сохранение заметки при раскрытии результатов и сохранении feedback.

Сценарии покрывают силовую, кардио и смешанную тренировку, отсутствие записанных результатов, большое число упражнений и длинные подписи. В long-сценарии есть duration `5 ч 24 мин`; на узкой ширине proposed-прототип держит метрику целиком, не подменяя значение сокращением.

## Отдельная классификация наблюдений

| Область | Результат | Граница этого пакета |
| --- | --- | --- |
| Длительность вроде `5 ч 24 мин` | **INTENDED / подтверждённой ошибки нет.** Форматтер возвращает полное русское значение; текущие Issue-доказательства классифицируют перенос как читаемый вариант, а не потерю данных. | Проверить после возможной реализации на 320/360/393/430 и desktop; не менять смысл форматтера. |
| Контекст названия справочника упражнений и back-route | **INTENDED / ошибка не подтверждена.** В shared app header виден контекст `Упражнения`; отдельный доказанный дефект маршрута в этом прогоне не получен. | Только documented evidence и regression test на заголовок, back-route и сохранение контекста; код не менялся. |
| Дата напоминания в прошлом | **CONFIRMED, уже закрыто технически.** Guard прошлого дня реализован и вошёл в PR #911 (`578f5704cac780c02720e84cff2a96cdb7dd481e`). | В этот пакет не входит повторная реализация; нужен regression run. |
| Сегодня после `reminder_hour` в часовом поясе профиля | **CONFIRMED policy B, уже реализовано.** Валидация отклоняет прошедшее время, просит выбрать будущее время сегодня, не переносит автоматически на завтра и не создаёт запись в прошлом; реализация вошла в PR #963 (`c32df59cd47983895fd004c626d40bebe21edf17`). | Проверить API/client race, timezone и dedupe на тестовых часовых поясах. |
| Историческое фото даты в прошлом | **NOT_PROOF.** Само фото не используется как доказательство бага. | Нужна воспроизводимая API/browser проверка с точным timezone и результатом POST. |
| Перекрытие fixed dock в capture | **OUT OF SCOPE.** Это контекст существующего #867; CSS нижней навигации не менялся. | Отдельный #867 AFTER/real-device gate, не часть #871. |

## Проверки, выполненные в этой ветке

- `npm run build` в `frontend`: **PASS**.
- `vitest run tests/unit/features/workouts/WorkoutCompletionSummary.test.tsx`: **4/4 PASS**.
- Existing mocked demo smoke на текущем runtime: Dark **PASS**, Light **PASS**.
- Current-DOM browser capture: **2/2 PASS**; зафиксированы direct children и отсутствие `AI Coach`.
- Proposed prototype capture: **PASS**; synthetic PNG и JSON checks обновлены после настройки длительности на 320px.
- `git diff --check`: **PASS**.

Не заявляется проверка Physical iPhone/Safari, native Telegram Mini App, VoiceOver или настоящей OS-клавиатуры: все они **NOT_VERIFIED**. Chromium viewport и условная keyboard-state в prototype — не доказательство real-device поведения.

## План перед отдельной реализацией

Только после явного owner design approval именно этого current-aware варианта:

1. отдельная implementation-задача/PR с физической перестановкой JSX, сохранением существующих props, actions, feedback payload, personal-record gating и `AiCoachContextualEntry` feature-gate;
2. targeted unit/API checks для duration, strength/cardio/mixed/empty/long data и feedback persistence;
3. browser Dark/Light AFTER на `320/360/393/430/1280`, включая focus, `<details>`, dock clearance и long labels;
4. WebKit/TMA/VoiceOver/physical-device checks, где они доступны, с честными `NOT_VERIFIED` при отсутствии среды;
5. отдельная owner visual acceptance, затем отдельное разрешение на merge/release.

## Гейт

В live Issue ранее зафиксировано согласование старого design-only пакета #991. Текущий prompt явно удерживает эту ветку на стадии reproduction + final mockups и запрещает внедрение нового порядка до нового/явно подтверждённого owner design approval для данного пакета. Поэтому Draft PR, merge, auto-merge и deploy не создавались и не выполнялись.
