# Landing #895 — final targeted polish / owner review

Дата: 09.10.2026. Это **незакоммиченный локальный WIP** существующей ветки
`codex/landing-v10-p0-895-working` и worktree Task #895. Region-recovery WIP сохранён.
Предварительное положительное мнение владельца не представлено как окончательное
согласование recovery или разрешение доставки.

[Компактная итоговая галерея](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-polish/index.html) ·
[Классификация всех 13 сцен / 50 регионов, ratios и SHA-256](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-polish/classification.json) ·
[Capture manifest](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-polish/candidate-captures.json).

```text
OWNER_VISUAL_APPROVAL=PENDING_FINAL_REVIEW_CURRENT_WIP
PREVIOUS_FINAL_CORRECTION_VISUAL_APPROVAL=APPROVED
PREVIOUS_FINAL_CORRECTION_BASELINE=FROZEN
REGION_RECOVERY_OWNER_FEEDBACK=PRELIMINARILY_SATISFACTORY
ARCHIVE_ORIGINALS_HASHES=PASS (28/28; 25 product + 3 gallery-only)
FROZEN_ORIGINALS_HASHES=PASS (20/20; unchanged)
ARCHIVE_VISUAL_PARITY=FAIL
ACTIVE_ARCHIVE_SCENES=13 (0 complete PASS)
ACTIVE_ARCHIVE_REGIONS=50 (2 partial PASS / 48 FAIL)
DEDICATED_VISUAL_SUITE=7 PASS / 39 FAIL (exit 1)
READY_FOR_MERGE_APPROVAL=NO
COMMIT_PUSH_PR_UPDATE_MERGE_DEPLOY_CUTOVER=NOT_PERFORMED
ISSUES_895_TO_900=NOT_CLOSED
CONTROLLER=ABSENT
CONTROLLER_V2=ABSENT
env change required: no
```

## Исправления и первопричины

1. **Два мобильных заголовка.** В `LandingV10Cycle` JSX не содержал пробела
   перед `<br>`. Media query до 1000px скрывает этот BR, поэтому DOM отображал
   `Продолжениеимеет` / `Сопровождение.С`. Добавлен обычный пробел в JSX перед BR
   для обеих аудиторий. Desktop-перенос сохранён; шрифты, размеры, цвета,
   отступы и CSS не менялись. Проверки видимого текста добавлены в существующую
   матрицу 11 ширин × две темы × две аудитории.
2. **Готовность прогресса.** Контролируемая задержка настоящего lazy JS chunk
   воспроизвела краткий fallback. Старый `aria-busy` уже был `false`, хотя
   график ещё отсутствовал. После реального ответа компонент успешно загружается;
   постоянного зависания не обнаружено. `Suspense` теперь окружает конечный
   контейнер: fallback имеет `aria-busy=true`, загруженный график — `false`.
   Итоговый DOM по-прежнему имеет одну рамку; существующий optional wrapper и
   остальные callers сохранены. API/данные/вычисления прогресса не менялись.
3. **Съёмка стабильного состояния (C).** Прежний helper ждал изображения/шрифты,
   но не lazy chart. Новый helper прокручивает сам наблюдаемый panel, ждёт
   заголовок «Объём тренировок», настоящий график, отсутствие fallback и
   `aria-busy=false`; затем пересчитывает прокрутку. Произвольных sleep нет.
   PWA может отдавать chunk из cache, поэтому только тест холодной загрузки
   блокирует service worker и управляет реальным сетевым ответом. Обычные
   проверки Web/TMA не обходят PWA этим способом.

Диагностика «до» сохранена в `before-diagnostic.json` и изображениях `before/`.
Восемь холодных загрузок на 320/390/430/1440 × light/dark проходят в Chromium и
WebKit. Unit-проверка подтверждает конечный busy-state и отсутствие запуска demo
session. Hero/header/CTA, фотографии, business logic Coach OS, backend, auth,
настоящие demo routes, SEO и analytics не изменялись этой итерацией.

## Архивная классификация — без искусственного PASS

Штатный `playwright.landing-visual.config.ts` запущен на свежем production build
с собственным strict-port preview 4201. Все 28 оригиналов проверены по SHA-256;
последние три PNG — только дизайн-галерея. Исходный ZIP SHA-256:
`2be733d3539d98ecb575e9da0449978dfaf8ee993dda8bebbadb7d7e03d3acef`.
Frozen PNG, normalization/disposition/region fixtures и допуски этой итерацией
не изменены. Threshold остаётся **0.01**, RGB channel tolerance — **16**.

Для каждой из 13 active scenes и каждого из 50 регионов в `classification.json`
и галерее указаны результат, changedPixelRatio, threshold, оригинал, candidate,
diff, классификация и подтверждение. Полная
[таблица 50 регионов](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-polish/regional-table.md).

- **A:** доказанные текущие дефекты вне desktop archive matrix — два мобильных
  слипания и преждевременный busy-state — исправлены. Нового доказанного
  runtime-дефекта, объясняющего все остаточные archive pixels, не установлено.
- **B:** поздние изменения header/teaser имеют узкую подтверждённую область,
  уже отражённую в прежних exclusions. Matte header: owner directive
  `88e2a024-1c27-494d-982f-0a516ebd186e`, P0-2, и последующее
  `FINAL_CORRECTION_VISUAL_DESIGN` approval. Athlete teaser: directive
  `6aa84c98-df4b-4cf1-bdcb-a2ac545bfd6d`, §2. Trainer FAQ «Понятные правила.»:
  тот же directive, §3.2, и подтверждение ранее согласованных секций в
  `TASK #895 — OWNER VISUAL APPROVAL RECEIVED`. Это не blanket waiver остальных
  пикселей и не доказательство согласования athlete FAQ.
- **C:** ранний mobile progress screenshot исправлен детерминированной
  подготовкой. В отдельных archive regions измеряется компонент сдвига 1–3px,
  в двух page-end сценах — около 23px. Диагностическая регистрация выполнена
  отдельно, без записи aligned golden, изменения fixture или acceptance ratio.
  Сам сдвиг не доказывает причину и не списывает оставшиеся pixels. Два небольших
  partial regions находятся в пределах прежнего допуска; полного PASS это не даёт.
- **D:** у **48 FAIL-регионов** остаётся неразрешённый остаток. Оригиналы не
  записывают точные viewport/DPR/zoom/font-rasterizer условия. Нельзя доказательно
  назвать все расхождения antialiasing или всеми считать дефектами UI. Для этих
  регионов явно сохранён D, даже если часть имеет измеренный C-компонент или
  отдельно согласованный B-текст. Athlete FAQ требует отдельного copy decision.

Уточнены две неточности предыдущего отчёта: активный `14-10_1` и candidate оба
содержат «COACH OS / ВНИМАНИЕ → КОНТЕКСТ»; `REVIEW WORKSPACE` не является
различием этой пары. В `14-07_1` подпись прогресса в обоих изображениях uppercase.
Это исправления диагностики, не изменения продукта.

Остаются **13 active scene FAIL / 48 region FAIL**. Общие **39 failed tests**:
13 active + 16 mobile frozen + 10 нижних `VISUAL_NOT_PROVEN`. Четыре desktop
frozen pixel comparisons проходят. Шестнадцать mobile frozen сравнений используют
снимки, предшествующие существующему 44px изменению нижней hero-ссылки; точный
capture commit не записан. Их нельзя автоматически заменить. Десять нижних
сцен не получают PASS от несоответствующего first-screen baseline. Два DOM
first-screen checks — структурные, не pixel acceptance. Итоговый dedicated suite
выходит с кодом **1**, без skip/retry/ослабления проверок.

## Финальная визуальная и функциональная проверка

Снято **176 актуальных PNG**: 16 initial full pages, 8 trainer interacted full
pages, cycle/progress areas и 16 initial/intermediate/final chapter states в каждой
из восьми trainer комбинаций. Галерея использует selectors и раскрываемые таблицы,
чтобы не повторять одну и ту же композицию. Полные PNG доступны отдельно.

Матрица: athlete/coach × light/dark × 1440/320/390/430, все шесть глав и их
изменённые состояния. Дополнительно E2E покрывает 360/768/1280/1366/1498/1600/1920.
Проверены переносы, геометрия, header/menu/CTA, lower sections/footer, реальные
demo destinations, theme/audience/hash/history, keyboard/focus, 44px targets,
reduced motion и mocked TMA safe-area/resize. В capture matrix: 0 horizontal
overflow, 0 page errors, 0 API writes, 0 progress loading fallbacks в финальных
снимках. Шесть восстановленных глав сохранены без переписывания функциональности.

| Проверка                        | Итог текущего WIP          |
| ------------------------------- | -------------------------- |
| Chromium Landing / six chapters | 66/66 PASS                 |
| WebKit Landing / six chapters   | 66/66 PASS                 |
| Vitest targeted                 | 88/88 PASS                 |
| Auth / DemoCabinet / privacy    | 9/9 PASS                   |
| SEO, configured origin 4173     | 1/1 PASS                   |
| TypeScript                      | PASS                       |
| ESLint changed frontend files   | PASS                       |
| Russian UI guard                | PASS                       |
| Prettier changed files          | PASS; no global formatting |
| Production build                | PASS                       |
| git diff --check                | PASS                       |
| Dedicated archive/frozen suite  | 7 PASS / 39 FAIL, exit 1   |

Все логи и JSON лежат рядом с галереей. Начальная TypeScript ошибка нового теста
(`innerText` на union HTMLElement/SVGElement) исправлена; исходный лог сохранён.
Два сбоя нового capture helper (ожидание ещё невидимой lazy panel; замена placeholder
во время scroll action) сохранены отдельно и исправлены наблюдаемой готовностью
panel и native scroll, без увеличения timeout. Это не runtime/visual PASS.

Известный исторический demo nutrition quick-add failure текущим изолированным
nutrition/coach тестом **не воспроизведён**. Это не объявление исправления; code
nutrition не менялся. Windows EPERM — известное ограничение sandbox запуска
subprocess; проверки выполнены разрешёнными local commands вне sandbox. Оно не
скрывает красный visual suite. Firefox и native Telegram **NOT_RUN**, ни PASS, ни
FAIL. TMA proof синтетический; production/real-user proof не заявляется.

[PR #902](https://github.com/MikeMoore1337/your-fitness-coach/pull/902) прочитан без
изменений: OPEN / MERGEABLE / CLEAN,
HEAD `a4df49e80e1e15f1ab125ff7047d75f03f3890f2`. Required aggregate `checks` SUCCESS,
mobile Chromium + WebKit SUCCESS. Необязательные расширенные Firefox jobs SKIPPED.
Этот удалённый CI не валидирует незакоммиченный WIP. PR не обновлён, Issues не закрыты.

## Короткий owner review

1. **D-1:** окончательно принять текущий recovery и шесть тренерских глав по
   полной галерее. Предварительное положительное мнение сохранено как предварительное.
2. **D-2:** athlete FAQ — оставить «Понятные правила.» или восстановить архивное
   «Понятные границы.». Trainer wording подтверждено отдельно; текущий текст не менялся.
3. **D-3:** определить reference contract для показанных остаточных пикселей,
   16 старых mobile frozen captures и 10 нижних сцен: отдельно принять перечисленные
   отклонения / разрешить согласованное обновление baseline либо восстановить
   условия оригинальной съёмки. До этого нет 1:1 PASS и готовности к merge approval.
   Архив, hashes и thresholds остаются неизменными в любом случае.

Остановлено **перед commit/push/PR update/merge/deploy**. Полный ранее утверждённый
header/hero/CTA baseline сохранён, финальное решение по текущему WIP ожидается.
