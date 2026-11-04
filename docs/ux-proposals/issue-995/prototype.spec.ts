import {
  expect,
  test,
  type Page,
} from "../../../frontend/node_modules/@playwright/test/index.mjs";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import {
  expectNoHorizontalOverflow,
  installTelegramHarness,
  setNetworkOffline,
} from "../../../frontend/tests/e2e/fixtures/mobile-tma";
import { installPlatformApi } from "../../../frontend/tests/e2e/fixtures/platform-api";

test.use({ hasTouch: true, serviceWorkers: "block" });

const previous = {
  note: "Жим ногами можно прибавить.",
  completed_on: "2026-10-23",
  day_number: 3,
  workout_title: "Силовая база",
  is_latest_completion: true,
};

async function setupWorkout(
  page: Page,
  surface: "web" | "pwa" | "telegram" = "web",
  theme: "dark" | "light" = "dark",
) {
  if (surface === "telegram") {
    await installTelegramHarness(page, {
      platform: "ios",
      colorScheme: theme,
      viewportHeight: 844,
      viewportStableHeight: 844,
      safeAreaInset: { top: 20, right: 0, bottom: 18, left: 0 },
      contentSafeAreaInset: { top: 32, right: 0, bottom: 14, left: 0 },
    });
  } else if (surface === "pwa") {
    await page.addInitScript(() => {
      const original = window.matchMedia.bind(window);
      window.matchMedia = (query) => {
        const result = original(query);
        if (query === "(display-mode: standalone)") {
          Object.defineProperty(result, "matches", {
            configurable: true,
            value: true,
          });
        }
        return result;
      };
      Object.defineProperty(navigator, "standalone", {
        configurable: true,
        value: true,
      });
    });
  }
  const platform = await installPlatformApi(page, {
    browserSession: surface !== "telegram",
    fixedDate: "2026-10-30",
  });
  let status = "planned";
  let note: typeof previous | null = { ...previous };
  let noteStatus = 200;
  let sourceTemplateExerciseId: number | null = null;
  const noteMethods: string[] = [];
  const sets = [1, 2, 3].map((number) => ({
    id: 200 + number,
    set_number: number,
    actual_reps: null as number | null,
    actual_weight: null as number | null,
    rir: null as string | null,
    set_kind: "working",
    reached_failure: null as boolean | null,
    is_completed: false,
    version: 1,
  }));
  const workout = () => ({
    id: 42,
    scheduled_date: "2026-10-30",
    scheduled_time: null,
    title: "Силовая база",
    status,
    day_number: 3,
    week_number: 2,
    started_at: status === "in_progress" ? "2026-10-30T12:00:00" : null,
    completed_at: null,
    exercises: [
      {
        id: 101,
        exercise_id: 11,
        exercise_title: "Жим штанги лёжа",
        source_template_exercise_id: sourceTemplateExerciseId,
        metric_type: "strength",
        sort_order: 1,
        prescribed_sets: 3,
        prescribed_reps: "8–10",
        rest_seconds: 90,
        notes: null,
        has_guide: false,
        sets,
      },
    ],
  });
  await page.route("**/api/v1/workouts/today", (route) =>
    route.fulfill({ json: workout() }),
  );
  await page.route("**/api/v1/workouts/week", (route) =>
    route.fulfill({ json: [workout()] }),
  );
  await page.route("**/api/v1/workouts/42/start", (route) => {
    status = "in_progress";
    return route.fulfill({ json: workout() });
  });
  await page.route("**/api/v1/workouts/sets/*", (route) => {
    const id = Number(
      new URL(route.request().url()).pathname.split("/").at(-1),
    );
    const set = sets.find((item) => item.id === id)!;
    const body = route.request().postDataJSON();
    Object.assign(set, body, { version: set.version + 1 });
    return route.fulfill({ json: set });
  });
  await page.route("**/api/v1/workouts/42/rest-sessions", (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    const body = route.request().postDataJSON();
    return route.fulfill({
      json: {
        id: 900,
        workout_id: 42,
        source_set_id: body.source_set_id,
        started_at: body.started_at,
        ended_at: null,
        planned_seconds: 90,
        adjusted_seconds: 90,
        measured_seconds: null,
        status: "running",
        source: null,
        quality: "normal",
        version: 1,
        start_mutation_id: body.mutation_id,
      },
    });
  });
  await page.route(
    "**/api/v1/workouts/42/previous-completion-note",
    (route) => {
      noteMethods.push(route.request().method());
      return route.fulfill({
        status: noteStatus,
        json:
          noteStatus === 200
            ? { previous_note: note }
            : { detail: "Данные изменились" },
      });
    },
  );
  return {
    platform,
    sets,
    noteMethods,
    setNote(value: typeof previous | null) {
      note = value;
    },
    setNoteStatus(value: number) {
      noteStatus = value;
    },
    setSourceTemplateExerciseId(value: number) {
      sourceTemplateExerciseId = value;
    },
  };
}

async function insertPrototype(page: Page, completed = false) {
  await page.addStyleTag({
    content: [
      ".proposal-note { margin: 12px 0; border: 1px solid var(--border); border-radius: 14px; background: var(--card-bg); color: var(--text); overflow: hidden; }",
      ".proposal-note summary { list-style: none; cursor: pointer; min-height: 54px; display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 12px; }",
      ".proposal-note summary::-webkit-details-marker { display: none; }",
      ".proposal-note summary:focus-visible { outline: 3px solid var(--v2-focus); outline-offset: -3px; }",
      ".proposal-note__summary { display: grid; gap: 3px; min-width: 0; }",
      ".proposal-note__summary strong, .proposal-note label, .proposal-note legend { font-size: var(--font-size-body); font-weight: var(--font-weight-strong); }",
      ".proposal-note__summary small, .proposal-note__past small, .proposal-note__hint { color: var(--muted); font-size: var(--font-size-caption); line-height: 1.35; }",
      ".proposal-note__summary small { overflow-wrap: anywhere; }",
      ".proposal-note[open] .proposal-note__summary small { display: none; }",
      ".proposal-note__action { flex: 0 0 auto; font-size: var(--font-size-caption); font-weight: 700; }",
      '.proposal-note[open] .proposal-note__action::before { content: "Скрыть"; }',
      '.proposal-note:not([open]) .proposal-note__action::before { content: "Открыть"; }',
      ".proposal-note__content { border-top: 1px solid var(--border); padding: 12px; display: grid; gap: 12px; }",
      ".proposal-note__past { display: grid; gap: 4px; min-width: 0; }",
      ".proposal-note__past p { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; line-height: 1.4; }",
      ".proposal-note__editor { display: grid; gap: 7px; }",
      ".proposal-note textarea { box-sizing: border-box; width: 100%; min-height: 80px; resize: vertical; padding: 10px; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: 10px; font: inherit; }",
      ".proposal-note textarea:focus-visible { outline: 3px solid var(--v2-focus); outline-offset: 2px; }",
      ".proposal-note fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }",
      ".proposal-note legend { margin-bottom: 7px; }",
      ".proposal-note__tags { display: flex; flex-wrap: wrap; gap: 6px; }",
      ".proposal-note__tags button { min-height: 44px; padding: 0 10px; font-size: var(--font-size-caption); border: 1px solid var(--border); }",
      ".proposal-note__buttons { display: flex; gap: 8px; flex-wrap: wrap; }",
      ".proposal-note__buttons button { min-height: 44px; flex: 1 1 110px; }",
      ".proposal-note__state { margin: 0; padding: 10px; border: 1px solid var(--border); border-radius: 10px; color: var(--text); font-size: var(--font-size-caption); line-height: 1.4; display: grid; gap: 8px; }",
      ".proposal-note__state button { min-height: 44px; }",
    ].join("\n"),
  });
  await page.evaluate((isCompleted) => {
    const current = document.querySelector(
      '.active-workout-set[aria-current="step"]',
    );
    const controls = current?.querySelector(".active-workout-set__controls");
    const prefill = current?.querySelector(
      ".active-workout-set__prefill-actions--history",
    );
    const completedSets = document.querySelector(
      ".active-workout-exercise.is-completed .active-workout-exercise__sets",
    );
    if (
      isCompleted
        ? !completedSets
        : !controls || !prefill || controls.nextElementSibling !== prefill
    )
      throw new Error("Exercise insertion point is missing");
    const note = document.createElement("details");
    note.className = "proposal-note";
    note.innerHTML = [
      '<summary><span class="proposal-note__summary"><strong>Заметка к упражнению</strong>',
      "<small>Последняя · 23.10.2026 · средняя неделя<br>100 кг × 10: легко, в следующий раз попробовать 105 кг</small></span>",
      '<span class="proposal-note__action"></span></summary>',
      '<div class="proposal-note__content"><div class="proposal-note__past">',
      "<small>Последняя сохранённая заметка · 23 октября 2026 · средняя неделя<br>Нагрузка: подход 3 · 100 кг × 10</small>",
      "<p>Легко, в следующий раз попробовать 105 кг</p></div>",
      '<div class="proposal-note__editor"><label for="proposal-note-text">Заметка к этому выполнению</label>',
      '<textarea id="proposal-note-text" placeholder="Что стоит запомнить?"></textarea>',
      '<small class="proposal-note__hint">Необязательно</small></div>',
      '<fieldset><legend>Метки</legend><div class="proposal-note__tags">',
      '<button type="button" data-yfc-choice="compact" aria-pressed="true">Легко</button>',
      '<button type="button" data-yfc-choice="compact" aria-pressed="false">Тяжело</button>',
      '<button type="button" data-yfc-choice="compact" aria-pressed="true">Повысить вес</button>',
      '</div></fieldset><div class="proposal-note__buttons">',
      '<button type="button" class="ui-button ui-button--primary">Сохранить</button>',
      '<button type="button" class="ui-button ui-button--secondary">Отмена</button>',
      "</div></div>",
    ].join("");
    if (isCompleted) completedSets!.after(note);
    else prefill!.after(note);
    note
      .querySelectorAll<HTMLButtonElement>(".proposal-note__tags button")
      .forEach((button) => {
        button.addEventListener("click", () =>
          button.setAttribute(
            "aria-pressed",
            String(button.getAttribute("aria-pressed") !== "true"),
          ),
        );
      });
  }, completed);
}

const widths = [320, 360, 393, 430, 1440];
for (const theme of ["dark", "light"] as const) {
  for (const width of widths) {
    test(
      "prototype matrix " + theme + " " + width,
      async ({ page, browserName }) => {
        const height =
          width === 1440
            ? 900
            : width === 430
              ? 932
              : width === 393
                ? 844
                : 800;
        await page.setViewportSize({ width, height });
        await page.emulateMedia({
          colorScheme: theme,
          reducedMotion: "reduce",
        });
        await page.addInitScript(
          (value) => localStorage.setItem("app-theme", value),
          theme,
        );
        const state = await setupWorkout(page);
        state.setSourceTemplateExerciseId(71);
        await page.route("**/api/v1/workouts/42/set-history", (route) =>
          route.fulfill({
            json: {
              workout_id: 42,
              user_program_id: 1,
              program_revision_number: 1,
              sets: [1, 2, 3].map((number) => ({
                set_id: 200 + number,
                set_number: number,
                set_version: number === 1 ? 2 : 1,
                workout_exercise_id: 101,
                exercise_id: 11,
                source_template_exercise_id: 71,
                previous_today: null,
                history_status: "matched",
                previous_workout: {
                  set_id: 1200 + number,
                  set_number: number,
                  set_version: 1,
                  workout_id: 41,
                  workout_exercise_id: 100,
                  completed_at: "2026-10-23T12:00:00",
                  performed_on: "2026-10-23",
                  actual_weight: 100,
                  actual_reps: 10,
                },
              })),
            },
          }),
        );
        await page.goto("/app");
        await page
          .getByRole("button", { name: "Начать тренировку", exact: true })
          .first()
          .click();
        const first = page.locator('[data-workout-set-id="201"]');
        await first.getByLabel(/^Вес,/).fill("100");
        await first.getByLabel(/^Повторы,/).fill("10");
        await first.getByRole("button", { name: /^Завершить:/ }).click();
        const timer = page.getByRole("complementary", {
          name: "Отдых между подходами",
        });
        await expect(timer).toBeVisible();
        const second = page.locator('[data-workout-set-id="202"]');
        await expect(second).toHaveAttribute("aria-current", "step");
        await expect(
          second.locator(".active-workout-set__history"),
        ).toContainText("100 кг × 10");
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(250);
        const prefillOrder = await second
          .locator(".active-workout-set__prefill-actions--history")
          .evaluate((element) => getComputedStyle(element).order);
        const before = await second.evaluate((element) => {
          const top = element.getBoundingClientRect().top;
          return [
            ".active-workout-set__rir-row",
            ".active-workout-set__done",
          ].map((selector) => {
            const rect = element
              .querySelector(selector)!
              .getBoundingClientRect();
            return {
              top: rect.top - top,
              height: rect.height,
              width: rect.width,
            };
          });
        });
        const timerBefore = await timer.boundingBox();
        await insertPrototype(page);
        await expect(
          second.locator(".active-workout-set__prefill-actions--history"),
        ).toHaveCSS("order", prefillOrder);
        await expect(
          second.locator(
            ".active-workout-set__controls + .active-workout-set__prefill-actions--history",
          ),
        ).toHaveCount(1);
        const after = await second.evaluate((element) => {
          const top = element.getBoundingClientRect().top;
          return [
            ".active-workout-set__rir-row",
            ".active-workout-set__done",
          ].map((selector) => {
            const rect = element
              .querySelector(selector)!
              .getBoundingClientRect();
            return {
              top: rect.top - top,
              height: rect.height,
              width: rect.width,
            };
          });
        });
        expect(after).toEqual(before);
        const timerAfter = await timer.boundingBox();
        expect(timerAfter!.width).toBe(timerBefore!.width);
        expect(timerAfter!.height).toBe(timerBefore!.height);
        await expectNoHorizontalOverflow(page);
        const output =
          "../docs/ux-proposals/issue-995/design/" +
          browserName +
          "-" +
          theme +
          "-" +
          width;
        await page.waitForTimeout(200);
        await page.locator(".proposal-note").evaluate((element) =>
          window.scrollTo({
            top: Math.max(
              0,
              element.getBoundingClientRect().bottom +
                scrollY -
                innerHeight +
                110,
            ),
            behavior: "instant",
          }),
        );
        await page.screenshot({
          path: output + "-collapsed.png",
          animations: "disabled",
          scale: "css",
        });
        await page.locator(".proposal-note summary").click();
        await page
          .locator("#proposal-note-text")
          .fill("100 кг легко, в следующий раз попробовать 105 кг.");
        await page.locator("#proposal-note-text").blur();
        await page.locator(".proposal-note").evaluate((element) =>
          window.scrollTo({
            top: element.getBoundingClientRect().top + scrollY - 125,
            behavior: "instant",
          }),
        );
        await expectNoHorizontalOverflow(page);
        for (const button of await page
          .locator(".proposal-note button")
          .all()) {
          expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(
            44,
          );
        }
        await page.screenshot({
          path: output + "-editor.png",
          animations: "disabled",
          scale: "css",
        });

        if (width === 393) {
          await page.locator(".proposal-note__past").evaluate((el) => {
            el.innerHTML = "<small>Предыдущих заметок нет</small>";
          });
          await page.locator("#proposal-note-text").fill("");
          await page.locator("#proposal-note-text").blur();
          await page
            .locator(".proposal-note__tags button")
            .evaluateAll((buttons) =>
              buttons.forEach((button) =>
                button.setAttribute("aria-pressed", "false"),
              ),
            );
          await page.screenshot({
            path: output + "-empty.png",
            animations: "disabled",
            scale: "css",
          });

          const long =
            "Темп ровный, последние повторы потребовали больше внимания. Следить за положением лопаток и дыханием; вес добавлять только после спокойной оценки на следующей тренировке. Оченьдлинноесловобезпробеловдляпроверкипереносавузкомэкране.";
          await page.locator(".proposal-note__past").evaluate((el, value) => {
            el.innerHTML =
              "<small>Последняя сохранённая заметка · 23 октября 2026 · средняя неделя<br>Нагрузка: подход 3 · 100 кг × 10</small><p></p>";
            el.querySelector("p")!.textContent = value;
          }, long);
          await page.locator("#proposal-note-text").fill(long);
          await page.locator("#proposal-note-text").blur();
          await page.locator(".proposal-note").evaluate((element) =>
            window.scrollTo({
              top: element.getBoundingClientRect().top + scrollY - 125,
              behavior: "instant",
            }),
          );
          await expectNoHorizontalOverflow(page);
          await page.screenshot({
            path: output + "-long.png",
            animations: "disabled",
            scale: "css",
          });

          await page.locator(".proposal-note__past").evaluate((el) => {
            el.innerHTML =
              "<small>Последняя сохранённая заметка · 23 октября 2026 · средняя неделя<br>Нагрузка: подход 3 · 100 кг × 10</small><p>Легко, в следующий раз попробовать 105 кг</p>";
          });
          await page
            .locator("#proposal-note-text")
            .fill("Сегодня вес ощущался легко.");
          await page.locator("#proposal-note-text").blur();
          await page.locator(".proposal-note__buttons").evaluate((el) => {
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "ui-button ui-button--secondary";
            remove.textContent = "Удалить";
            el.append(remove);
          });
          await page.locator(".proposal-note").evaluate((element) =>
            window.scrollTo({
              top: element.getBoundingClientRect().top + scrollY - 125,
              behavior: "instant",
            }),
          );
          expect(
            await page.locator(".proposal-note summary").evaluate((element) => {
              const rect = element.getBoundingClientRect();
              const hit = document.elementFromPoint(
                rect.left + rect.width / 2,
                rect.top + rect.height / 2,
              );
              return Boolean(hit && (hit === element || element.contains(hit)));
            }),
          ).toBe(true);
          await page.screenshot({
            path: output + "-edit-delete.png",
            animations: "disabled",
            scale: "css",
          });

          await page.locator(".proposal-note__editor").evaluate((el) => {
            el.insertAdjacentHTML(
              "beforeend",
              '<p class="proposal-note__state">Нет сети. Заметка сохранена на устройстве и будет отправлена при подключении.</p>',
            );
          });
          await page.locator(".proposal-note").evaluate((element) =>
            window.scrollTo({
              top: element.getBoundingClientRect().top + scrollY - 125,
              behavior: "instant",
            }),
          );
          await page.screenshot({
            path: output + "-offline.png",
            animations: "disabled",
            scale: "css",
          });
          await page.locator(".proposal-note__state").evaluate((el) => {
            el.innerHTML =
              '<span>Заметка изменилась на другом устройстве. Ваш текст остался здесь.</span><button type="button" class="ui-button ui-button--secondary">Посмотреть сохранённую версию</button>';
          });
          await page
            .locator(".proposal-note__buttons .ui-button--primary")
            .evaluate((el: HTMLButtonElement) => {
              el.disabled = true;
            });
          await page.locator(".proposal-note").evaluate((element) =>
            window.scrollTo({
              top: element.getBoundingClientRect().top + scrollY - 125,
              behavior: "instant",
            }),
          );
          await page.screenshot({
            path: output + "-conflict.png",
            animations: "disabled",
            scale: "css",
          });
          await page.locator(".proposal-note").evaluate((element) =>
            window.scrollTo({
              top: Math.max(
                0,
                element.getBoundingClientRect().bottom +
                  scrollY -
                  innerHeight +
                  110,
              ),
              behavior: "instant",
            }),
          );
          await page.screenshot({
            path: output + "-conflict-bottom.png",
            animations: "disabled",
            scale: "css",
          });
          await page
            .locator(".proposal-note__state")
            .evaluate((el) => el.remove());
          await page
            .locator(".proposal-note__buttons .ui-button--primary")
            .evaluate((el: HTMLButtonElement) => {
              el.disabled = false;
            });
        }
        if (width !== 1440) {
          await page.setViewportSize({ width, height: 480 });
          await page.locator("#proposal-note-text").focus();
          await page.locator("#proposal-note-text").evaluate((element) =>
            window.scrollTo({
              top: element.getBoundingClientRect().top + scrollY - 135,
              behavior: "instant",
            }),
          );
          await expect(page.locator("#proposal-note-text")).toBeFocused();
          await expectNoHorizontalOverflow(page);
          expect(
            await page.locator("#proposal-note-text").evaluate((element) => {
              const rect = element.getBoundingClientRect();
              const hit = document.elementFromPoint(
                rect.left + rect.width / 2,
                rect.top + rect.height / 2,
              );
              return (
                rect.top >= 0 && rect.bottom <= innerHeight && hit === element
              );
            }),
          ).toBe(true);
          await page.screenshot({
            path: output + "-keyboard-model.png",
            animations: "disabled",
            scale: "css",
          });
          await page.setViewportSize({ width, height });
        }
        await page.locator(".proposal-note summary").focus();
        await page.keyboard.press("Enter");
        await expect(page.locator(".proposal-note")).not.toHaveAttribute(
          "open",
        );
        await page.keyboard.press("Enter");
        await expect(page.locator(".proposal-note")).toHaveAttribute(
          "open",
          "",
        );
        const tag = page.locator(".proposal-note__tags button").first();
        const oldPressed = await tag.getAttribute("aria-pressed");
        await tag.click();
        await expect(tag).toHaveAttribute(
          "aria-pressed",
          oldPressed === "true" ? "false" : "true",
        );
        await page.locator(".proposal-note summary").click();
        const done = second.getByRole("button", { name: /^Завершить:/ });
        await done.evaluate((element) =>
          window.scrollTo({
            top: element.getBoundingClientRect().top + scrollY - 145,
            behavior: "instant",
          }),
        );
        await expect(done).toBeVisible();
        expect(
          await done.evaluate((element) => {
            const rect = element.getBoundingClientRect();
            const hit = document.elementFromPoint(
              rect.left + rect.width / 2,
              rect.top + rect.height / 2,
            );
            return (
              rect.top >= 0 &&
              rect.bottom <= innerHeight &&
              Boolean(hit && (hit === element || element.contains(hit)))
            );
          }),
        ).toBe(true);
        expect(state.sets[0]).toMatchObject({
          is_completed: true,
          actual_weight: 100,
          actual_reps: 10,
        });
        expect(state.sets[1]).toMatchObject({
          is_completed: false,
          actual_weight: null,
          actual_reps: null,
        });
      },
    );
  }
}

for (const theme of ["dark", "light"] as const) {
  test(
    "prototype completed exercise " + theme,
    async ({ page, browserName }) => {
      await page.setViewportSize({ width: 393, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      await page.addInitScript(
        (value) => localStorage.setItem("app-theme", value),
        theme,
      );
      await setupWorkout(page);
      const rests: Array<Record<string, any>> = [];
      await page.route("**/api/v1/workouts/42/rest-sessions", async (route) => {
        if (route.request().method() === "GET")
          return route.fulfill({ json: rests });
        const body = route.request().postDataJSON();
        const rest = {
          id: 900 + rests.length,
          workout_id: 42,
          source_set_id: body.source_set_id,
          started_at: body.started_at,
          ended_at: null,
          planned_seconds: 90,
          adjusted_seconds: 90,
          measured_seconds: null,
          status: "running",
          source: null,
          quality: "normal",
          version: 1,
          start_mutation_id: body.mutation_id,
        };
        rests.push(rest);
        return route.fulfill({ json: rest });
      });
      await page.route(
        "**/api/v1/workouts/rest-sessions/*/actions",
        async (route) => {
          const id = Number(
            new URL(route.request().url()).pathname.split("/").at(-2),
          );
          const rest = rests.find((item) => item.id === id);
          if (!rest)
            return route.fulfill({
              status: 404,
              json: { detail: "Not found" },
            });
          const body = route.request().postDataJSON();
          rest.version += 1;
          rest.status =
            body.action === "complete"
              ? "completed"
              : body.action === "skip"
                ? "skipped"
                : "interrupted";
          rest.ended_at = body.ended_at ?? body.occurred_at;
          return route.fulfill({ json: rest });
        },
      );
      await page.goto("/app");
      await page
        .getByRole("button", { name: "Начать тренировку", exact: true })
        .first()
        .click();
      for (const id of [201, 202, 203]) {
        const row = page.locator('[data-workout-set-id="' + id + '"]');
        await expect(row).toHaveAttribute("aria-current", "step");
        await row.getByLabel(/^Вес,/).fill("100");
        await row.getByLabel(/^Повторы,/).fill("10");
        await row.getByRole("button", { name: /^Завершить:/ }).click();
        await expect
          .poll(() => rests.some((rest) => rest.source_set_id === id))
          .toBe(true);
      }
      const exercise = page
        .locator(".active-workout-exercise.is-completed")
        .first();
      await exercise.getByRole("button", { name: /3 из 3 сохранено/ }).click();
      await expect(
        exercise.locator(".active-workout-exercise__sets"),
      ).toBeVisible();
      await insertPrototype(page, true);
      await expect(
        page.getByRole("complementary", { name: "Отдых между подходами" }),
      ).not.toContainText("Ошибка сохранения");
      await page.locator(".proposal-note").evaluate((element) =>
        window.scrollTo({
          top: element.getBoundingClientRect().top + scrollY - 140,
          behavior: "instant",
        }),
      );
      await expectNoHorizontalOverflow(page);
      await page.screenshot({
        path:
          "../docs/ux-proposals/issue-995/design/" +
          browserName +
          "-" +
          theme +
          "-393-completed-exercise.png",
        animations: "disabled",
        scale: "css",
      });
      await page.locator(".proposal-note summary").click();
      await expect(page.locator("#proposal-note-text")).toBeVisible();
      const finish = page.getByRole("button", { name: "Завершить тренировку" });
      await finish.evaluate((element) =>
        window.scrollTo({
          top: element.getBoundingClientRect().top + scrollY - 145,
          behavior: "instant",
        }),
      );
      await expect(finish).toBeVisible();
      expect(
        await finish.evaluate((element) => {
          const rect = element.getBoundingClientRect();
          const hit = document.elementFromPoint(
            rect.left + rect.width / 2,
            rect.top + rect.height / 2,
          );
          return (
            rect.bottom <= innerHeight &&
            Boolean(hit && (hit === element || element.contains(hit)))
          );
        }),
      ).toBe(true);
    },
  );
}

for (const theme of ["dark", "light"] as const) {
  test("prototype telegram harness " + theme, async ({ page, browserName }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.addInitScript(
      (value) => localStorage.setItem("app-theme", value),
      theme,
    );
    const state = await setupWorkout(page, "telegram", theme);
    state.setSourceTemplateExerciseId(71);
    await page.route("**/api/v1/workouts/42/set-history", (route) =>
      route.fulfill({
        json: {
          workout_id: 42,
          user_program_id: 1,
          program_revision_number: 1,
          sets: [1, 2, 3].map((number) => ({
            set_id: 200 + number,
            set_number: number,
            set_version: number === 1 ? 2 : 1,
            workout_exercise_id: 101,
            exercise_id: 11,
            source_template_exercise_id: 71,
            previous_today: null,
            history_status: "matched",
            previous_workout: {
              set_id: 1200 + number,
              set_number: number,
              set_version: 1,
              workout_id: 41,
              workout_exercise_id: 100,
              completed_at: "2026-10-23T12:00:00",
              performed_on: "2026-10-23",
              actual_weight: 100,
              actual_reps: 10,
            },
          })),
        },
      }),
    );
    await page.goto("/app");
    await page
      .getByRole("button", { name: "Начать тренировку", exact: true })
      .first()
      .click();
    const first = page.locator('[data-workout-set-id="201"]');
    await first.getByLabel(/^Вес,/).fill("100");
    await first.getByLabel(/^Повторы,/).fill("10");
    await first.getByRole("button", { name: /^Завершить:/ }).click();
    const second = page.locator('[data-workout-set-id="202"]');
    await expect(second).toHaveAttribute("aria-current", "step");
    await expect(page.getByRole("timer", { name: "Отдых" })).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await insertPrototype(page);
    await page.locator(".proposal-note summary").click();
    await page
      .locator("#proposal-note-text")
      .fill("Сегодня вес ощущался легко.");
    await page.locator("#proposal-note-text").blur();
    await page.locator(".proposal-note").evaluate((element) =>
      window.scrollTo({
        top: element.getBoundingClientRect().top + scrollY - 140,
        behavior: "instant",
      }),
    );
    await expectNoHorizontalOverflow(page);
    await page.screenshot({
      path:
        "../docs/ux-proposals/issue-995/design/" +
        browserName +
        "-" +
        theme +
        "-393-tma-simulated.png",
      animations: "disabled",
      scale: "css",
    });
  });
}
