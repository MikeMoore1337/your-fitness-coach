import { expectNoHorizontalOverflow, test } from './fixtures/mobile-tma';
import { expect } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

const evidenceDir = '../.artifacts/tasks/731/evidence/screenshots';

const longExercise = {
  id: 11,
  title: 'Разгибание ног в тренажёре с контролируемой паузой в нижней точке',
  primary_muscle: 'Квадрицепс',
  equipment: 'Тренажёр',
  primary_muscle_ids: ['quadriceps'],
  secondary_muscle_ids: [],
  equipment_ids: ['machine'],
  alternatives: [],
  difficulty_level: 'intermediate',
  edit_target_id: null,
  slug: 'machine-leg-extension',
  is_custom: false,
  is_personalized: false,
  created_by_user_id: null,
  source_exercise_id: null,
  has_guide: false,
  guide: null,
};

const candidateExercise = {
  id: 12,
  title: 'Приседания с гантелями',
  slug: 'dumbbell-squat',
  metric_type: 'strength',
  primary_muscle: 'Ноги',
  equipment: 'Гантели',
  primary_muscle_ids: ['quadriceps'],
  secondary_muscle_ids: [],
  equipment_ids: ['dumbbell'],
  alternatives: [],
  difficulty_level: 'beginner',
  is_custom: false,
  is_personalized: false,
  has_guide: false,
};

function installProgramExercises(page: Parameters<typeof installPlatformApi>[0]) {
  return page.route('**/api/v1/programs/exercises', (route) =>
    route.fulfill({ json: [longExercise, candidateExercise] }),
  );
}

async function openProgramEditor(page: Parameters<typeof installPlatformApi>[0]) {
  await page.goto('/app?section=programs&view=manage&start=templates');
  await expect(page.getByRole('heading', { name: 'Программы и шаблоны' })).toBeVisible();
  await page.getByRole('button', { name: 'Редактировать шаблон', exact: true }).click();
  const modal = page.locator('.program-editor-modal');
  await expect(modal).toBeVisible();
  return modal;
}

async function assertEditorGeometry(
  page: Parameters<typeof installPlatformApi>[0],
  modal: ReturnType<Parameters<typeof installPlatformApi>[0]['locator']>,
) {
  await expectNoHorizontalOverflow(page);
  const geometry = await modal.evaluate((element) => {
    const panel = element.getBoundingClientRect();
    const controls = Array.from(
      element.querySelectorAll<HTMLElement>('input, select, textarea, button'),
    );
    const rows = Array.from(element.querySelectorAll<HTMLElement>('.program-exercise-row'));
    return {
      panelClientWidth: element.clientWidth,
      panelScrollWidth: element.scrollWidth,
      controlsOutside: controls
        .filter((control) => {
          const rect = control.getBoundingClientRect();
          return (
            rect.width > 0 &&
            rect.height > 0 &&
            (rect.left < panel.left - 1 || rect.right > panel.right + 1)
          );
        })
        .map((control) => ({
          ariaLabel: control.getAttribute('aria-label'),
          name: control.getAttribute('name'),
          left: Math.round(control.getBoundingClientRect().left),
          right: Math.round(control.getBoundingClientRect().right),
          width: Math.round(control.getBoundingClientRect().width),
        })),
      rowsWithOverflow: rows.filter((row) => row.scrollWidth > row.clientWidth + 1).length,
      rowsWithMisalignedFields: rows.filter((row) => {
        const heading = row.querySelector<HTMLElement>('.program-exercise-row__heading');
        const picker = row.querySelector<HTMLElement>('.exercise-picker > input');
        const metricLabels = Array.from(
          row.querySelectorAll<HTMLElement>('.program-exercise-row__metrics .field > span'),
        );
        const metricInputs = Array.from(
          row.querySelectorAll<HTMLElement>('.program-exercise-row__metrics .field > input'),
        );
        if (!heading || !picker || metricLabels.length === 0 || metricInputs.length === 0) {
          return true;
        }
        const center = (box: DOMRect) => box.top + box.height / 2;
        const headingCenter = center(heading.getBoundingClientRect());
        const pickerTop = picker.getBoundingClientRect().top;
        return (
          metricLabels.some(
            (label) => Math.abs(center(label.getBoundingClientRect()) - headingCenter) > 2,
          ) ||
          metricInputs.some((input) => Math.abs(input.getBoundingClientRect().top - pickerTop) > 2)
        );
      }).length,
    };
  });
  expect(geometry.panelClientWidth).toBeGreaterThan(700);
  expect(geometry.panelScrollWidth).toBeLessThanOrEqual(geometry.panelClientWidth + 1);
  expect(geometry.controlsOutside).toEqual([]);
  expect(geometry.rowsWithOverflow).toBe(0);
  expect(geometry.rowsWithMisalignedFields).toBe(0);
}

test('Task 731 desktop program editor has bounded geometry at supported widths', async ({
  page,
}) => {
  await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
  await installProgramExercises(page);
  await page.setViewportSize({ width: 1366, height: 768 });

  const modal = await openProgramEditor(page);
  await modal.getByRole('button', { name: 'Добавить упражнение' }).click();
  const picker = modal.getByRole('combobox', { name: 'Поиск упражнения' });
  await picker.fill('РАЗГИБАНИЕ');
  await expect(page.getByRole('option', { name: longExercise.title })).toBeVisible();
  await picker.press('ArrowDown');
  await picker.press('Enter');
  await expect(picker).toHaveValue(longExercise.title);

  for (const viewport of [
    { width: 1280, height: 720 },
    { width: 1366, height: 768 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(viewport);
    await assertEditorGeometry(page, modal);
    if (viewport.width === 1366 || viewport.width === 1920) {
      await page.screenshot({
        path: `${evidenceDir}/task-731-program-editor-${viewport.width}x${viewport.height}.png`,
      });
    }
  }
});

test('Task 731 import mapping searches locally and preserves resolve rows', async ({ page }) => {
  await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
  await page.route('**/api/v1/programs/exercises', (route) =>
    route.fulfill({ json: [longExercise] }),
  );

  let resolveBody: Record<string, unknown> | null = null;
  const preview = (resolved: boolean) => ({
    id: 'import-731',
    status: 'pending',
    source_format: 'csv',
    schema_version: 1,
    parser_version: 'test-parser',
    layout_version: 'generic-table-v1',
    duration_weeks: 1,
    expires_at: '2030-01-01T00:00:00Z',
    program_title: 'Импортированный план',
    goal: 'recomposition',
    level: 'intermediate',
    provenance: { provenance_type: 'CUSTOM' },
    rows: [
      {
        row_number: 3,
        source_sheet: 'Лист1',
        source_range: 'A3:F3',
        week_number: 1,
        day_number: 1,
        day_title: 'Силовая',
        exercise_name: 'Упражнение из файла',
        metric_type: 'strength',
        prescribed_sets: 3,
        prescribed_reps: '8–10',
        rest_seconds: 90,
        block_is_deload: false,
        resolved_exercise_id: resolved ? 11 : null,
        resolved_exercise_title: resolved ? longExercise.title : null,
        match_status: resolved ? 'matched' : 'needs_resolution',
        match_type: resolved ? 'manual' : null,
        candidates: [
          {
            exercise_id: candidateExercise.id,
            title: candidateExercise.title,
            slug: candidateExercise.slug,
            metric_type: 'strength',
            match_type: 'title',
          },
        ],
        issues: resolved
          ? []
          : [
              {
                code: 'exercise_needs_resolution',
                severity: 'blocking',
                message: 'Укажите упражнение вручную.',
                location: 'строка 3',
              },
            ],
      },
    ],
    issues: resolved
      ? []
      : [
          {
            code: 'exercise_needs_resolution',
            severity: 'blocking',
            message: 'Укажите упражнение вручную.',
            location: 'строка 3',
          },
        ],
    summary: {
      row_count: 1,
      cell_count: 6,
      matched_row_count: resolved ? 1 : 0,
      unresolved_row_count: resolved ? 0 : 1,
      blocking_issue_count: resolved ? 0 : 1,
      warning_count: 0,
    },
    ai: { status: 'unavailable', proposal_count: 0, conflict_count: 0 },
  });

  await page.route('**/api/v1/programs/imports', (route) =>
    route.fulfill({ json: preview(false) }),
  );
  await page.route('**/api/v1/programs/imports/targets', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/programs/imports/import-731/resolve', async (route) => {
    resolveBody = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ json: preview(true) });
  });

  await page.goto('/app?section=programs&view=manage&start=templates');
  const upload = page.getByLabel('Загрузить документ программы');
  await upload.setInputFiles({
    name: 'program.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('day,exercise,sets\n1,Упражнение из файла,3\n'),
  });
  await expect(
    page.getByRole('heading', { name: 'Проверьте план перед сохранением' }),
  ).toBeVisible();
  await expect(page.locator('.program-import-preview')).not.toContainText('generic-table-v1');
  await expect(page.locator('.program-import-preview')).not.toContainText('provider');

  const picker = page.getByRole('combobox', { name: 'Упражнение для строки 3' });
  await picker.click();
  await expect(page.getByRole('listbox')).toBeVisible();
  await expect(page.getByRole('listbox').getByRole('option')).toHaveCount(2);
  await picker.fill('РАЗГИБАНИЕ');
  await picker.evaluate((element) =>
    element.scrollIntoView({ block: 'center', inline: 'nearest' }),
  );
  const pickerResultsBox = await page.locator('.exercise-picker__results').boundingBox();
  const viewport = page.viewportSize();
  expect(pickerResultsBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(pickerResultsBox!.y).toBeGreaterThanOrEqual(-1);
  expect(pickerResultsBox!.y + pickerResultsBox!.height).toBeLessThanOrEqual(viewport!.height + 1);
  await page.screenshot({ path: `${evidenceDir}/task-731-import-picker-query.png` });
  await page.getByRole('option', { name: longExercise.title }).click();
  await expect(picker).toHaveValue(longExercise.title);

  await picker.fill('ПРИСЕД');
  await picker.press('ArrowDown');
  await picker.press('Enter');
  await expect(picker).toHaveValue(candidateExercise.title);
  await page.screenshot({ path: `${evidenceDir}/task-731-import-mapping-after-selection.png` });

  await page.getByRole('button', { name: 'Применить исправления' }).click();
  await expect.poll(() => resolveBody).not.toBeNull();
  expect(resolveBody).toMatchObject({
    rows: [{ row_number: 3, exercise_id: candidateExercise.id }],
  });
  await expect(page.getByText('Готово к подтверждению')).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test('Task 731 editor remains usable in Mobile Web and mocked TMA', async ({
  mobilePage,
  tmaPage,
}) => {
  for (const page of [mobilePage, tmaPage]) {
    await installPlatformApi(page, {
      browserSession: page === mobilePage,
      programHistory: 'many',
    });
    await page.setViewportSize({ width: 390, height: 844 });
    const modal = await openProgramEditor(page);
    await modal.getByRole('button', { name: 'Добавить упражнение' }).click();
    await expect(modal.getByRole('combobox', { name: 'Поиск упражнения' })).toBeVisible();
    await expectNoHorizontalOverflow(page);
    expect(await modal.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(
      true,
    );
  }
});
