import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import {
  expect,
  test,
  type Page,
} from "../../../frontend/node_modules/@playwright/test/index.mjs";
import { installPlatformApi } from "../../../frontend/tests/e2e/fixtures/platform-api";

const warning = `<svg class="yfc-icon yfc-icon--20" data-icon="warning" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>`;
const success = `<svg class="yfc-icon yfc-icon--20" data-icon="success" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="m16 9-5.5 5.5L8 12"/></svg>`;
const button = (
  label: string,
  variant: "primary" | "secondary" = "secondary",
) =>
  `<button type="button" class="ui-button ui-button--${variant}">${label}</button>`;
const heading = (description: string) =>
  `<header class="import-head"><h2>Импорт истории тренировок</h2><p>${description}</p></header>`;
const note = (title: string, text: string) =>
  `<div class="import-note">${warning}<div><strong>${title}</strong><p>${text}</p></div></div>`;
const actions = (...buttons: string[]) =>
  `<div class="import-actions">${buttons.join("")}</div>`;

const states: Record<string, string> = {
  entry: `
    <div class="import-entry"><h2>История</h2>${button("Импортировать историю")}</div>
    <p class="import-muted">Добавьте выполненные тренировки из подготовленного файла.</p>
    <div class="import-stats"><div><span>Тренировок</span><strong>1</strong></div><div><span>Подходов</span><strong>2</strong></div><div><span>Объём</span><strong>320 кг</strong></div></div>
    <div class="import-row"><strong>Ноги и корпус</strong><p>9 октября 2026 · 2 подхода</p><p>Приседания</p></div>`,
  upload: `
    ${heading("Загрузите CSV-файл с выполненными тренировками.")}
    <div class="import-upload"><strong>Выберите файл</strong><p>Используйте шаблон YFC. Перед сохранением вы сможете проверить каждую тренировку.</p>${button("Выбрать файл", "primary")}</div>
    <p class="import-muted">До подтверждения история и статистика не изменятся.</p>
    ${actions(button("Скачать шаблон"), button("Закрыть"))}`,
  preview: `
    ${heading("Проверьте распознанные данные перед сохранением.")}
    <div class="import-file"><strong>history.csv</strong><span>2 тренировки · 6 строк</span></div>
    ${note("Нужно проверить 3 записи", "Выберите упражнение, сравните возможный дубль и проверьте строку с ошибкой.")}
    <div class="import-row"><div class="import-row-head"><strong>Верх тела</strong><span>12 октября 2025</span></div><p>18:30 · Москва</p><strong>Жим на скамье <span class="import-issue">· выбрать упражнение</span></strong><ul><li>Разминка · 40 кг × 10</li><li>Рабочий · 60 кг × 8 · резерв 2</li><li>Рабочий · 60 кг × 7</li></ul></div>
    <div class="import-row"><div class="import-row-head"><strong>Ноги и корпус</strong><span>9 октября 2025</span></div><p>2 подхода · возможный дубль</p></div>
    ${actions(button("Проверить записи", "primary"), button("Отменить импорт"))}`,
  match: `
    ${heading("Сопоставьте упражнения с каталогом YFC.")}
    ${note("Выберите упражнение", "Похожее название — только подсказка. Пока вы не выберете вариант, запись не будет готова к сохранению.")}
    <div class="import-row"><p class="import-muted">В файле · строки 2–4</p><h3>Жим на скамье</h3><p>3 подхода · тренировка «Верх тела»</p>
      <label for="issue833-exercise">Упражнение в YFC</label>
      <select id="issue833-exercise" class="ui-select"><option>Выберите упражнение</option><option>Жим штанги лёжа</option><option>Жим гантелей лёжа</option></select>
      <p>Возможные варианты: жим штанги лёжа, жим гантелей лёжа.</p>
      <p class="import-muted">Если подходящего упражнения нет, исключите эти строки из импорта.</p>
    </div>
    ${note("Раздельные стороны пока не поддерживаются", "Исправьте файл или явно исключите такие записи.")}
    ${actions('<button type="button" class="ui-button ui-button--primary" disabled>Сохранить выбор</button>', button("Исключить строки"), button("Назад к просмотру"))}`,
  unknown: `
    ${heading("Найдите упражнение в каталоге YFC.")}
    ${note("Упражнение не найдено", "Выберите подходящий вариант вручную или исключите строки из импорта.")}
    <div class="import-row"><p class="import-muted">В файле · строки 7–8</p><h3>Тяга на тренажёре</h3><p>2 подхода · тренировка «Спина»</p>
      <label for="issue833-search">Поиск по каталогу</label><input id="issue833-search" class="ui-input" type="search" value="тяга">
      <p class="import-muted">Выберите подходящее упражнение:</p>
      <label class="import-candidate"><input type="radio" name="candidate"> Тяга горизонтального блока</label>
      <label class="import-candidate"><input type="radio" name="candidate"> Тяга верхнего блока</label>
    </div>
    ${actions('<button type="button" class="ui-button ui-button--primary" disabled>Сохранить выбор</button>', button("Исключить строки"), button("Назад к просмотру"))}`,
  duplicates: `
    ${heading("Проверьте совпадения и строки с ошибками.")}
    <div class="import-row"><p class="import-issue">${warning} Возможный дубль</p><h3>Ноги и корпус · 9 октября 2025</h3><p>В истории уже есть тренировка в этот день. Сравните состав перед решением.</p>
      <div class="import-compare"><div><strong>В файле</strong><p>Приседания · 2 подхода</p></div><div><strong>В истории</strong><p>Приседания · 2 подхода</p></div></div>
      ${actions(button("Исключить тренировку"), button("Это другая тренировка"))}
    </div>
    <div class="import-row"><p class="import-issue">${warning} Строка 6 · не включена</p><strong>Не распознана дата завершения</strong><p>Исправьте файл или подтвердите исключение этой строки.</p>${button("Подтвердить исключение")}</div>
    ${actions(button("Вернуться к просмотру"))}`,
  confirm: `
    ${heading("Проверьте итог и подтвердите сохранение.")}
    <div class="import-stats"><div><span>Тренировок</span><strong>1</strong></div><div><span>Подходов</span><strong>3</strong></div><div><span>Исключено</span><strong>3 строки</strong></div></div>
    <div class="import-row"><div class="import-row-head"><strong>Верх тела</strong><span>12 октября 2025</span></div><p>18:30 · Москва</p><p>Жим штанги лёжа · 3 подхода</p><ul><li>40 кг × 10 · разминка</li><li>60 кг × 8 · резерв 2</li><li>60 кг × 7</li></ul></div>
    <p class="import-muted">Не войдут: тренировка «Ноги и корпус» (возможный дубль) и строка 6 с нераспознанной датой.</p>
    <p>После подтверждения эти данные появятся в истории и статистике.</p>
    ${actions(button("Сохранить историю", "primary"), button("Вернуться к просмотру"))}`,
  success: `
    ${heading("Сохранение завершено.")}
    <div class="import-result">${success}<div><h3>История дополнена</h3><p>Сохранена 1 тренировка и 3 подхода. Исключённые строки не добавлены.</p></div></div>
    ${actions(button("Открыть историю", "primary"), button("Готово"))}`,
  error: `
    ${heading("Не удалось получить результат сохранения.")}
    ${note("Проверьте состояние импорта", "Соединение прервалось. Обновите статус, прежде чем повторять сохранение.")}
    ${actions(button("Обновить статус", "primary"), button("Закрыть"))}`,
  reopen: `
    ${heading("Есть незавершённый импорт.")}
    <div class="import-file"><strong>history.csv</strong><span>2 тренировки · требуется проверка</span></div>
    <p>Черновик доступен до 1 ноября 2026, 18:30. Вы можете продолжить проверку или удалить его.</p>
    ${actions(button("Продолжить проверку", "primary"), button("Удалить черновик"))}`,
};

const styles = `
  .issue833-prototype { min-width: 0; color: var(--v2-text-primary); }
  .issue833-prototype h2, .issue833-prototype h3, .issue833-prototype p { margin: 0; }
  .issue833-prototype h2 { font-family: Oswald, sans-serif; font-size: 22px; line-height: 1.2; }
  .issue833-prototype h3 { font-size: 17px; line-height: 1.35; }
  .issue833-prototype p { line-height: 1.45; }
  .issue833-prototype .import-head { display: grid; gap: 7px; margin-bottom: 20px; }
  .issue833-prototype .import-head p, .issue833-prototype .import-muted { color: var(--v2-text-secondary); }
  .issue833-prototype .import-entry, .issue833-prototype .import-row-head { display: flex; gap: 12px; align-items: center; justify-content: space-between; flex-wrap: wrap; }
  .issue833-prototype .import-entry + p { margin-top: 12px; }
  .issue833-prototype .import-upload { display: grid; gap: 10px; justify-items: start; padding: 18px; border: 1px dashed var(--v2-border-strong); border-radius: 14px; margin-bottom: 14px; }
  .issue833-prototype .import-upload p { max-width: 62ch; color: var(--v2-text-secondary); }
  .issue833-prototype .import-file { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; padding: 12px 0; border-bottom: 1px solid var(--v2-border); margin-bottom: 16px; }
  .issue833-prototype .import-file span, .issue833-prototype .import-row-head span { color: var(--v2-text-secondary); }
  .issue833-prototype .import-note { display: flex; align-items: flex-start; gap: 10px; padding: 14px; margin: 16px 0; border: 1px solid var(--v2-border); border-radius: 14px; background: var(--v2-surface); }
  .issue833-prototype .import-note svg, .issue833-prototype .import-result svg { flex: 0 0 20px; }
  .issue833-prototype .import-note p { margin-top: 5px; color: var(--v2-text-secondary); }
  .issue833-prototype .import-row { display: grid; gap: 8px; padding: 16px 0; border-bottom: 1px solid var(--v2-border); }
  .issue833-prototype .import-row p { color: var(--v2-text-secondary); }
  .issue833-prototype .import-row ul { padding-left: 20px; margin: 0; line-height: 1.65; font-variant-numeric: tabular-nums; }
  .issue833-prototype .import-row label { margin-top: 5px; font-weight: 700; }
  .issue833-prototype .import-row select { width: 100%; max-width: 460px; }
  .issue833-prototype .import-row input[type="search"] { width: 100%; max-width: 460px; }
  .issue833-prototype .import-candidate { display: flex; align-items: center; gap: 10px; min-height: 44px; font-weight: 400 !important; }
  .issue833-prototype .import-candidate input { width: 18px; height: 18px; min-width: 18px; padding: 0; margin: 0; flex: 0 0 18px; }
  .issue833-prototype .import-row + p, .issue833-prototype > p + p { margin-top: 12px; }
  .issue833-prototype .import-issue { color: var(--v2-warning) !important; font-weight: 700; }
  .issue833-prototype p.import-issue { display: flex; gap: 8px; align-items: center; }
  .issue833-prototype .import-issue svg { flex: 0 0 20px; }
  .issue833-prototype .import-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
  .issue833-prototype .import-actions button { min-height: 44px; }
  .issue833-prototype .import-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-block: 1px solid var(--v2-border); margin: 16px 0; }
  .issue833-prototype .import-stats div { display: grid; gap: 4px; padding: 12px 8px; }
  .issue833-prototype .import-stats strong { font-size: 19px; font-variant-numeric: tabular-nums; }
  .issue833-prototype .import-compare { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 6px; }
  .issue833-prototype .import-compare > div { border: 1px solid var(--v2-border); border-radius: 12px; padding: 12px; min-width: 0; }
  .issue833-prototype .import-result { display: flex; gap: 12px; padding: 16px 0; }
  .issue833-prototype .import-result p { margin-top: 6px; }
  @media (max-width: 600px) {
    .issue833-prototype .import-actions button { width: 100%; }
    .issue833-prototype .import-entry { align-items: flex-start; }
    .issue833-prototype .import-compare { grid-template-columns: 1fr; }
  }
  @media (max-width: 360px) {
    .issue833-prototype .import-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
`;

async function setup(page: Page, theme: string) {
  await page.addInitScript(
    (value) => localStorage.setItem("app-theme", value),
    theme,
  );
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: "2026-10-09",
    progressState: "populated",
  });
  await page.route(/\/api\/v1\/workouts\/history(?:\?.*)?$/, (route) =>
    route.fulfill({
      json: [
        {
          id: 43,
          title: "Ноги и корпус",
          scheduled_date: "2026-10-09",
          status: "completed",
          completed_sets: 2,
          volume_kg: 320,
          completion_note: null,
          completion_feedback: null,
          adaptations: [],
          rest_sessions: [],
          exercises: [
            {
              workout_exercise_id: 55,
              exercise_id: 11,
              title: "Приседания",
              prescribed_sets: 2,
              prescribed_reps: "8",
              sort_order: 1,
            },
          ],
        },
      ],
    }),
  );
  await page.route("**/api/v1/workouts/history/summary", (route) =>
    route.fulfill({
      json: { workouts_completed: 1, completed_sets: 2, volume_kg: 320 },
    }),
  );
  await page.goto("/app?section=progress&progress_view=history");
  await expect(page.locator("#workout-history-43")).toBeVisible();
  await page.addStyleTag({ content: styles });
}

const viewports = [
  { width: 320, height: 800 },
  { width: 360, height: 800 },
  { width: 393, height: 844 },
  { width: 430, height: 932 },
  { width: 1440, height: 900 },
];
const output = resolve("../.artifacts/tasks/833/temporary/prototype");

for (const theme of ["dark", "light"]) {
  for (const viewport of viewports) {
    test(`history import prototype ${theme} ${viewport.width}`, async ({
      page,
    }, info) => {
      await page.setViewportSize(viewport);
      await page.emulateMedia({
        colorScheme: theme as "dark" | "light",
        reducedMotion: "reduce",
      });
      await setup(page, theme);
      await page.evaluate(() => document.fonts.ready);
      await mkdir(output, { recursive: true });
      const card = page.locator(".workout-history-card");
      for (const [name, markup] of Object.entries(states)) {
        await card.evaluate((element, content) => {
          element.innerHTML = `<div class="issue833-prototype">${content}</div>`;
        }, markup);
        const panel = card.locator(".issue833-prototype");
        await expect(panel.locator("h2")).toBeVisible();
        if (name === "match") {
          await expect(panel.getByLabel("Упражнение в YFC")).toHaveValue(
            "Выберите упражнение",
          );
          await expect(
            panel.getByRole("button", { name: "Сохранить выбор" }),
          ).toBeDisabled();
        }
        const overflow = await panel.evaluate((element) => {
          const right = element.getBoundingClientRect().right;
          const offenders = [...element.querySelectorAll("*")]
            .filter((item) => item.getBoundingClientRect().right > right + 1)
            .map(
              (item) =>
                `${item.tagName} ${item.textContent?.trim().slice(0, 50)}`,
            );
          if (element.scrollWidth > element.clientWidth + 1)
            offenders.push("panel scrolls horizontally");
          return offenders;
        });
        expect(overflow, `${name} overflows at ${viewport.width}`).toEqual([]);
        await page.locator("#appBottomNav").evaluateAll((nodes) =>
          nodes.forEach((node) => {
            (node as HTMLElement).style.visibility = "hidden";
          }),
        );
        await card.screenshot({
          path: resolve(
            output,
            `${info.project.name}-${theme}-${viewport.width}-${name}.png`,
          ),
          animations: "disabled",
        });
        await page.locator("#appBottomNav").evaluateAll((nodes) =>
          nodes.forEach((node) => {
            (node as HTMLElement).style.visibility = "";
          }),
        );
        if (name === "upload") {
          await page.screenshot({
            path: resolve(
              output,
              `${info.project.name}-${theme}-${viewport.width}-context.png`,
            ),
            fullPage: true,
            animations: "disabled",
          });
        }
      }
    });
  }
}
