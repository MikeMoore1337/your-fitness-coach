# План проверки Variant 02 после owner final visual acceptance

Это design/evidence-план, а не заявка о выполненной production-проверке. До утверждения исправленной композиции production-кодирование нового выбора не начинается.

## Уже проверено в этом пакете

- 320/360/393/430 px и 1440 px, Chromium, Dark/Light, reduced motion.
- Footer: две кнопки в одном `footer-choice-row`, точный DOM-порядок `Показать изменения` → `Отмена`, одинаковая строка и touch target, без text wrapping/overflow.
- Safe-area: footer использует существующий `env(safe-area-inset-bottom)` с базовым 12 px padding; в headless Chromium значение env равно 0, поэтому реальное iOS inset остаётся отдельным `NOT_VERIFIED`.
- Search: value/caret/focus сохраняются после локального фильтра; фильтрация не добавляет кандидата вне полного синтетического ответа.
- States: loading, empty, error, offline, conflict/409, pain, started, preview и apply-disabled. Cancel доступна в каждом блокирующем состоянии; conflict разрешает заново показать изменения, но не apply старого preview.
- Reopen: отмена скрывает лист и возвращает control «Открыть замену снова»; повторное открытие ставит focus на close control.

## BEFORE/AFTER сравнение

BEFORE — [`audit/baseline-geometry.json`](audit/baseline-geometry.json), `origin/master` SHA `4c92832415d4eb994cf6b849a67074742f07ea50`, существующий synthetic `mockActiveWorkout`, Chromium/light/reduced-motion, height 844, widths 360/393/430. Зафиксировано: 5 кликов до видимого preview, 4 внутри диалога, 3 DOM scroll events; preview card частично выходила за body viewport.

AFTER сейчас — [`audit/variant-02-geometry.json`](audit/variant-02-geometry.json), static design prototype. Он проверяет геометрию новой footer-композиции, но не доказывает production click/scroll improvement. После implementation нужно повторить тот же fixture и сравнить:

| Измерение | Критерий | Источник |
| --- | --- | --- |
| Footer buttons | одна строка, `Показать изменения` слева, `Отмена` справа, обе кнопки без wrap и clipping | DOM rect + computed style |
| Width safety | `scrollWidth <= clientWidth` у row, кнопок, body и dialog | browser assertions |
| Safe-area | нижний padding сохраняет минимум 12 px и не закрывает footer | computed style + iOS run |
| Focus | preview → cancel; после reopen focus на close | keyboard/DOM |
| Search | value, caret и focus сохраняются после filter rerender | keyboard/DOM |
| Flow | preview не мутирует workout/program; apply отдельный и идемпотентный | request trace + API tests |
| Baseline | clicks, scroll events, body/preview rects повторяются тем же методом | same Playwright harness |

## E2E / браузер

- Chromium и WebKit, 320/360/393/430, Dark/Light, synthetic API: открыть нижний лист, выбрать 3–5 кандидатов, открыть «Все подходящие», выполнить поиск и допустимый equipment-фильтр.
- Request assertions: GET query содержит только выбранные `available_equipment_ids`; preview ровно один на submit; apply содержит тот же request и `preview_token`; до apply не меняются workout/program endpoints.
- Negative matrix: GET error/retry, empty, offline, preview 503/retry, apply 409/re-preview, duplicate submit, reopen, started/completed target, pain_or_injury, foreign workout/authorization.
- Проверить, что keyboard input не закрывает введённое значение и что Cancel остаётся доступной при каждом error/disabled state.
- WebKit/headless — evidence only. Physical iPhone/Safari, native Telegram Mini App, OS keyboard и VoiceOver — отдельные `NOT_VERIFIED` gates.

## Vitest

- Быстрый список: 3 visible + полный GET response; search/filter никогда не создаёт item вне response; no-result copy.
- Search focus/value/caret survives rerender; Escape/close возвращает focus на invoking control, если в production implementation будет второй layer.
- Preview/apply остаются разными действиями; pending/offline/conflict/started/pain/empty disabled states; нет program/future mutation в request mocks.
- Неизвестный `reason_key` не рендерится как обещание; UI использует только название, оборудование и нейтральную серверную допустимость.

## Pytest

- `list_compatible_alternatives`: equipment subset, metric, visible/avoided/used, unstarted target, curated/planned fallback distinction.
- Preview/apply: stale token/target facts/409, идемпотентный identical apply, program snapshot unchanged, pain safety stop и audit.
- На design-only этапе backend-тесты не расширяются и серверное поведение не меняется; после approval добавлять тесты только при конкретном контрактном изменении.

## Gates и ограничения

1. Owner final visual acceptance именно этого исправленного Variant 02 package.
2. Отдельная implementation ветка/PR только после gate; реальные AFTER Dark/Light.
3. Owner visual acceptance после implementation.
4. Отдельное прямое разрешение на merge и deploy.

`MERGE=false` · `DEPLOY=false` · `PHYSICAL_DEVICE=NOT_VERIFIED` · `TMA=NOT_VERIFIED` · `VOICEOVER=NOT_VERIFIED`
