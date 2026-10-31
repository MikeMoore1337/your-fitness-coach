import { expect, test, type Locator, type Page } from '@playwright/test';
import { resolve } from 'node:path';
import type { Workout } from '../../src/shared/api/types';
import {
  expectNoHorizontalOverflow,
  expectNoOverlap,
  expectTouchTargets,
  installTelegramHarness,
} from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

type WeekType = 'light' | 'medium' | 'heavy';
type Guidance = NonNullable<Workout['exercises'][number]['progression_guidance']>;

const evidenceDir = process.env.ISSUE_917_EVIDENCE_DIR;
const viewports = [
  { name: '320', width: 320, height: 844 },
  { name: '360', width: 360, height: 844 },
  { name: '393', width: 393, height: 844 },
  { name: '430', width: 430, height: 932 },
  { name: 'desktop', width: 1440, height: 900 },
] as const;

const facts = [
  { workout: 18, set: 42, date: '2026-10-23', type: 'medium', weight: 35, reps: 8 },
  { workout: 17, set: 41, date: '2026-10-20', type: 'heavy', weight: 40, reps: 10 },
  { workout: 13, set: 44, date: '2026-10-16', type: 'medium', weight: 35, reps: 8 },
  { workout: 12, set: 43, date: '2026-10-13', type: 'heavy', weight: 40, reps: 10 },
] as const;

function exerciseHistory(type: WeekType | 'all') {
  const selected = facts.filter((item) => type === 'all' || item.type === type);
  if (!selected.length) return [];
  return [
    {
      exercise_id: 11,
      exercise_title: 'Приседания',
      uses_bodyweight_equipment: false,
      performed_session_count: selected.length,
      completed_set_count: selected.length,
      first_performed_on: selected[selected.length - 1]!.date,
      last_performed_on: selected[0]!.date,
      reps_total: selected.reduce((sum, item) => sum + item.reps, 0),
      reps_recorded_sets: selected.length,
      max_external_load_kg: Math.max(...selected.map((item) => item.weight)),
      best_set_volume_kg: Math.max(...selected.map((item) => item.weight * item.reps)),
      external_load_volume_kg: selected.reduce((sum, item) => sum + item.weight * item.reps, 0),
      volume_recorded_sets: selected.length,
      history_truncated: false,
      sessions: selected.map((item) => ({
        workout_id: item.workout,
        workout_exercise_id: item.workout + 100,
        performed_on: item.date,
        completed_set_count: 1,
        reps_total: item.reps,
        reps_recorded_sets: 1,
        max_external_load_kg: item.weight,
        external_load_volume_kg: item.weight * item.reps,
        volume_recorded_sets: 1,
        sets: [{ set_number: 1, reps: item.reps, external_load_kg: item.weight, rir: '2' }],
      })),
    },
  ];
}

function typedGuidance(
  base: Guidance,
  weekType: WeekType,
  setVersion: number,
  targetWorkout = 42,
  targetSet = 201,
): Guidance {
  if (!base.proposal) throw new Error('Expected a proposal in the fixture');
  const chosen = facts.filter((item) => item.type === weekType);
  const reasons =
    weekType === 'heavy'
      ? ['top_range_repeated', 'full_rir_coverage']
      : weekType === 'medium'
        ? ['target_range_not_repeated']
        : ['too_few_comparable_sessions', 'insufficient_same_type_history'];
  const sessions = chosen.map((item) => ({
    workout_id: item.workout,
    scheduled_date: item.date,
    working_set_count: 1,
    load: item.weight,
    load_unit: 'kg' as const,
    reps_min: item.reps,
    reps_max: item.reps,
    rir_recorded_set_count: 1,
    rir_values: ['2' as const],
    reached_failure: false,
    completion_feedback: null,
  }));
  const eligible = weekType === 'heavy';
  return {
    ...base,
    ruleset_version: 'progression-guidance-v3',
    outcome: eligible ? 'consider_progressing' : weekType === 'medium' ? 'hold' : 'review',
    message: eligible
      ? base.message
      : weekType === 'medium'
        ? 'Пока оставьте текущую нагрузку'
        : 'Пока недостаточно данных',
    detail: eligible
      ? 'В двух сопоставимых тяжёлых тренировках достигнут верх диапазона; шаг 2,5 кг задан правилом.'
      : weekType === 'medium'
        ? 'Верх диапазона повторений ещё не повторился.'
        : 'Нужны полные сопоставимые рабочие подходы в текущем контексте программы.',
    suggested_weight: eligible ? 42.5 : null,
    suggested_increment: eligible ? 2.5 : null,
    evidence: {
      ...base.evidence,
      week_type: weekType,
      comparable_session_count: chosen.length,
      required_session_count: 2,
      working_set_count: chosen.length,
      rir_recorded_set_count: chosen.length,
      reason_keys: reasons,
      sessions,
    },
    proposal: {
      ...base.proposal,
      target_workout_id: targetWorkout,
      current_weight: chosen[0]?.weight ?? null,
      proposed_weight: eligible ? 42.5 : null,
      proposed_action: eligible ? 'set_load' : 'hold',
      target_set_updates: eligible
        ? [{ ...base.proposal.target_set_updates![0]!, set_id: targetSet, set_version: setVersion }]
        : [],
      source_evidence_ids: chosen.map((item) => `workout:${item.workout}/set:${item.set}`),
      comparable_session_count: chosen.length,
      reason_codes: reasons,
      eligibility_status: eligible ? 'eligible' : weekType === 'medium' ? 'no_change' : 'review',
    },
  };
}

async function prepare(page: Page, browserSession = true) {
  await installPlatformApi(page, {
    browserSession,
    fixedDate: '2026-10-30',
    workoutStatus: 'in_progress',
    progressionOutcome: 'consider_progressing',
    progressState: 'populated',
    programHistory: 'many',
  });
  await page.goto('/app?section=today');
  const fixture = await page.evaluate(async () => ({
    workout: (await (await fetch('/api/v1/workouts/today')).json()) as Workout,
    analytics: await (
      await fetch('/api/v1/workouts/progress/training-analytics?period_days=30')
    ).json(),
  }));
  const baseGuidance = fixture.workout.exercises[0]?.progression_guidance;
  if (!baseGuidance) throw new Error('Expected progression guidance in the fixture');
  let selected: WeekType = 'heavy';
  let setVersion = 1;
  let reviewConflict = false;
  let applied = false;
  const reviewBodies: Array<Record<string, unknown>> = [];
  const guidance = () => typedGuidance(baseGuidance, selected, setVersion);
  const assignedGuidance = () => {
    const result = typedGuidance(baseGuidance, selected, setVersion, 943, 301);
    const update = result.proposal?.target_set_updates?.[0];
    if (applied && update) update.current_weight = update.proposed_weight;
    return result;
  };

  await page.route('**/workouts/today', (route) =>
    route.fulfill({
      json: {
        ...fixture.workout,
        exercises: [{ ...fixture.workout.exercises[0], progression_guidance: guidance() }],
      },
    }),
  );
  await page.route('**/programs/exercises/11/history', (route) =>
    route.fulfill({
      json: { recent_sessions: [{ sets: [{ pr_eligible: true, load_kg: 35, reps: 8 }] }] },
    }),
  );
  await page.route('**/programs/assigned/77/progression-proposals', (route) =>
    route.fulfill({
      json: {
        target_program_id: 77,
        target_revision_number: 4,
        target_workout_id: 943,
        scheduled_date: '2026-10-30',
        exercises: [
          {
            exercise_id: 11,
            exercise_title: 'Приседания',
            guidance: assignedGuidance(),
          },
        ],
      },
    }),
  );
  await page.route('**/programs/assigned/77/progression-proposals/*/review', async (route) => {
    reviewBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    if (reviewConflict) {
      reviewConflict = false;
      setVersion = 2;
      return route.fulfill({ status: 409, json: { detail: 'Подход изменился' } });
    }
    applied = true;
    setVersion += 1;
    return route.fulfill({
      json: {
        decision: 'confirm',
        proposal_id: 'a'.repeat(64),
        applied_set_ids: [301],
        current_revision_number: 4,
      },
    });
  });
  await page.route('**/workouts/progress/training-analytics?**', (route) =>
    route.fulfill({
      json: {
        ...fixture.analytics,
        period_days: 30,
        period_start: '2026-10-01',
        period_end: '2026-10-30',
        previous_period_start: '2026-09-01',
        previous_period_end: '2026-09-30',
        completed_workout_count: 4,
        completed_set_count: 4,
        frequency_per_week: 0.93,
        previous_completed_workout_count: 2,
        previous_frequency_per_week: 0.47,
        reps_total: 36,
        reps_recorded_sets: 4,
        external_load_volume_kg: 1360,
        volume_recorded_sets: 4,
        exercises: exerciseHistory('all'),
        data_sufficiency: {
          ...fixture.analytics.data_sufficiency,
          working_sets: {
            status: 'limited',
            counters: {
              working_set_count: 4,
              workout_session_count: 4,
              required_working_set_count: 6,
              required_workout_session_count: 2,
            },
            reason_keys: [],
          },
        },
        muscle_group_workload: [
          {
            muscle_id: 'quadriceps',
            muscle_name: 'Передняя поверхность бедра',
            current: {
              completed_set_count: 4,
              primary_completed_set_count: 4,
              secondary_completed_set_count: 0,
              completed_session_count: 4,
              frequency_per_week: 0.93,
            },
            previous: null,
            completed_set_count_change: null,
            frequency_per_week_change: null,
            trend: 'no_comparable_data',
            contributing_exercises: [
              {
                exercise_id: 11,
                exercise_title: 'Приседания',
                contribution_roles: ['primary'],
                completed_set_count: 4,
                performed_session_count: 4,
                history_truncated: false,
                sessions: [],
              },
            ],
          },
        ],
      },
    }),
  );
  await page.route('**/workouts/progress/training-analytics/week-type?**', (route) => {
    const type = new URL(route.request().url()).searchParams.get('week_type') as WeekType;
    const exercises = exerciseHistory(type);
    return route.fulfill({
      json: {
        week_type: type,
        period_start: '2026-10-01',
        period_end: '2026-10-30',
        exercise_history_limit: 20,
        completed_workout_count: exercises[0]?.performed_session_count ?? 0,
        completed_set_count: exercises[0]?.completed_set_count ?? 0,
        external_load_volume_kg: exercises[0]?.external_load_volume_kg ?? null,
        volume_recorded_sets: exercises[0]?.volume_recorded_sets ?? 0,
        untyped_workout_count: 0,
        unknown_type_workout_count: 0,
        exercises,
      },
    });
  });
  return {
    select(type: WeekType) {
      selected = type;
    },
    conflictNextReview() {
      reviewConflict = true;
    },
    reviewBodies,
  };
}

async function screenshot(locator: Locator, name: string) {
  if (evidenceDir && test.info().project.name === 'chromium') {
    await locator.screenshot({ path: resolve(evidenceDir, name), animations: 'disabled' });
  }
}

for (const theme of ['dark', 'light'] as const) {
  for (const viewport of viewports) {
    test(`@critical Issue #917 typed guidance and history ${viewport.name} ${theme}`, async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await page.setViewportSize(viewport);
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      const scenario = await prepare(page);
      for (const type of ['heavy', 'medium', 'light'] as const) {
        scenario.select(type);
        await page.goto('/app?section=today');
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
        const summary = page.getByRole('region', { name: 'Что делать сейчас?' });
        await summary.getByRole('button', { name: 'Что делать сейчас?' }).click();
        const guidance = summary.locator('.progression-guidance');
        await expect(summary.getByText('Последний результат')).toBeVisible();
        await expect(summary.getByText('По всей истории упражнения')).toBeVisible();
        await expect(guidance).toContainText(
          type === 'heavy'
            ? 'Тяжёлая неделя'
            : type === 'medium'
              ? 'Средняя неделя'
              : 'Лёгкая неделя',
        );
        if (type === 'heavy') {
          await expect(guidance).toContainText('Прошлая сопоставимая: 40 кг × 10');
          await expect(guidance.getByRole('button', { name: 'Применить 42,5 кг' })).toBeVisible();
        } else {
          await expect(guidance.getByRole('button', { name: /Применить/ })).toHaveCount(0);
          if (type === 'light')
            await expect(guidance).toContainText('Сопоставимых тренировок пока нет');
        }
        await expectNoHorizontalOverflow(page);
        await screenshot(
          page.locator('.active-workout-exercise').first(),
          `workout-${type}-${theme}-${viewport.name}.png`,
        );
        if (evidenceDir && test.info().project.name === 'chromium') {
          await guidance.evaluate((node) => node.scrollIntoView({ block: 'center' }));
          await screenshot(guidance, `workout-${type}-guidance-${theme}-${viewport.name}.png`);
          if (
            type === 'heavy' ||
            (type === 'light' && ['393', 'desktop'].includes(viewport.name))
          ) {
            await page.screenshot({
              path: resolve(evidenceDir, `workout-${type}-viewport-${theme}-${viewport.name}.png`),
              animations: 'disabled',
            });
          }
        }
        if (type === 'heavy' && ['393', 'desktop'].includes(viewport.name)) {
          await guidance.getByText('Почему такой вес?').click();
          await expect(
            guidance
              .getByRole('list', { name: 'Последние тренировки' })
              .getByRole('listitem')
              .first(),
          ).toContainText(/10 повторов\s+1 раб\. подх\./);
          await expect(guidance).toContainText('workout:17/set:41');
          await expect(guidance).toContainText('progression-guidance-v3');
          await screenshot(guidance, `workout-heavy-details-${theme}-${viewport.name}.png`);
        }

        await page.goto('/app?section=programs&view=manage&panel=operations');
        const proposal = page.locator('.progression-proposals');
        await expect(proposal.locator('.progression-guidance')).toBeVisible();
        await expect(proposal).toContainText(
          type === 'heavy'
            ? 'Тяжёлая неделя'
            : type === 'medium'
              ? 'Средняя неделя'
              : 'Лёгкая неделя',
        );
        await screenshot(proposal, `program-${type}-${theme}-${viewport.name}.png`);
        if (type === 'heavy' && ['393', 'desktop'].includes(viewport.name)) {
          await proposal.getByText('Почему такой вес?').click();
          await expect(
            proposal
              .getByRole('list', { name: 'Последние тренировки' })
              .getByRole('listitem')
              .first(),
          ).toContainText(/10 повторов\s+1 раб\. подх\./);
          await expect(proposal).toContainText('workout:17/set:41');
          await screenshot(proposal, `program-heavy-details-${theme}-${viewport.name}.png`);
        }
      }

      await page.goto('/app?section=progress&progress_view=training');
      const training = page.locator('#progress-training');
      const tabs = training.getByRole('tablist', { name: 'Тип недели' });
      await expect(tabs).toBeVisible();
      await expectTouchTargets(tabs.getByRole('tab'));
      const totals = training.getByLabel('Итоги тренировок');
      await expect(totals).toContainText('1 360 кг');
      for (const [type, label] of [
        ['all', 'Все'],
        ['heavy', 'Тяжёлая'],
        ['medium', 'Средняя'],
        ['light', 'Лёгкая'],
      ] as const) {
        await tabs.getByRole('tab', { name: label }).click();
        if (type === 'light') {
          await expect(training).toContainText('тренировок лёгкого типа пока нет');
        } else {
          const exercise = training.locator('.progress-exercise').first();
          await expect(exercise).toBeVisible();
          await exercise.locator('summary').click();
          await expect(exercise).toContainText(type === 'medium' ? '35 кг' : '40 кг');
        }
        await expect(totals).toContainText('1 360 кг');
        await expectNoHorizontalOverflow(page);
        await screenshot(training, `analytics-${type}-${theme}-${viewport.name}.png`);
      }
    });
  }
}

test('@critical Issue #917 reconnects a type filter and retries a refreshed 409 proposal', async ({
  page,
}) => {
  const scenario = await prepare(page);
  await page.goto('/app?section=progress&progress_view=training');
  const training = page.locator('#progress-training');
  const tabs = training.getByRole('tablist', { name: 'Тип недели' });
  await expect(tabs).toBeVisible();
  await tabs.getByRole('tab', { name: 'Тяжёлая' }).focus();
  await page.keyboard.press('ArrowLeft');
  await expect(tabs.getByRole('tab', { name: 'Средняя' })).toHaveAttribute('aria-selected', 'true');
  await page.context().setOffline(true);
  await tabs.getByRole('tab', { name: 'Лёгкая' }).click();
  await expect(training).toContainText('История выбранного типа недоступна офлайн');
  await page.context().setOffline(false);
  await expect(training).toContainText('тренировок лёгкого типа пока нет');
  await expect(training.getByLabel('Итоги тренировок')).toContainText('1 360 кг');

  scenario.select('heavy');
  scenario.conflictNextReview();
  await page.goto('/app?section=programs&view=manage&panel=operations');
  const proposal = page.locator('.progression-proposals');
  await proposal.getByRole('button', { name: 'Применить 42,5 кг' }).click();
  await expect(page.getByText('Программа или подход изменились. Данные обновлены.')).toBeVisible();
  await proposal.getByRole('button', { name: 'Применить 42,5 кг' }).click();
  await expect.poll(() => scenario.reviewBodies.length).toBe(2);
  expect(scenario.reviewBodies.map((body) => body.expected_set_versions)).toEqual([
    { '301': 1 },
    { '301': 2 },
  ]);
  await expect(
    page.getByText('Предложенная нагрузка добавлена в незавершённые подходы'),
  ).toBeVisible();
  await expect(proposal.getByRole('button', { name: 'Вес подставлен' })).toBeDisabled();
});

test('@critical Issue #917 refreshes a cached type slice after reconnect', async ({ page }) => {
  await prepare(page);
  let requests = 0;
  await page.route('**/workouts/progress/training-analytics/week-type?**', (route) => {
    requests += 1;
    const type = new URL(route.request().url()).searchParams.get('week_type') as WeekType;
    const exercises = exerciseHistory(type).map((item) => ({
      ...item,
      exercise_title: requests === 1 ? 'Приседания до обновления' : 'Приседания после обновления',
    }));
    return route.fulfill({
      json: {
        week_type: type,
        period_start: '2026-10-01',
        period_end: '2026-10-30',
        exercise_history_limit: 20,
        completed_workout_count: 2,
        completed_set_count: 2,
        external_load_volume_kg: 800,
        volume_recorded_sets: 2,
        untyped_workout_count: 0,
        unknown_type_workout_count: 0,
        exercises,
      },
    });
  });
  await page.goto('/app?section=progress&progress_view=training');
  const training = page.locator('#progress-training');
  const tabs = training.getByRole('tablist', { name: 'Тип недели' });
  await tabs.getByRole('tab', { name: 'Тяжёлая' }).click();
  await expect(training.getByText('Приседания до обновления')).toBeVisible();
  await page.context().setOffline(true);
  await expect(training.getByText('Нет сети: показаны сохранённые данные.')).toBeVisible();
  await page.context().setOffline(false);
  await expect(training.getByText('Приседания после обновления')).toBeVisible();
  await expect(training.getByText('Приседания до обновления')).toHaveCount(0);
  expect(requests).toBe(2);
});

for (const theme of ['dark', 'light'] as const) {
  for (const viewport of [viewports[2], viewports[4]]) {
    test(`@critical Issue #917 missing progression facts ${viewport.name} ${theme}`, async ({
      page,
    }) => {
      await page.setViewportSize(viewport);
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await prepare(page);
      const workout = await page.evaluate(
        async () => (await (await fetch('/api/v1/workouts/today')).json()) as Workout,
      );
      const base = workout.exercises[0]?.progression_guidance;
      if (!base?.proposal) throw new Error('Expected a typed proposal in the fixture');
      let mode: 'missing-rir' | 'incomplete' = 'missing-rir';
      await page.route('**/workouts/today', (route) => {
        const reason = mode === 'missing-rir' ? 'missing_rir_evidence' : 'incomplete_session_facts';
        const sessions = base.evidence.sessions.map((session, index) => ({
          ...session,
          load: mode === 'incomplete' && index === 0 ? null : session.load,
          rir_recorded_set_count: mode === 'missing-rir' ? 0 : session.rir_recorded_set_count,
          rir_values: mode === 'missing-rir' ? [] : session.rir_values,
        }));
        const current: Guidance = {
          ...base,
          outcome: 'review',
          message: 'Пока недостаточно данных',
          detail:
            mode === 'missing-rir'
              ? 'Запас повторов (RIR) записан не для каждого подхода, который учитывается в прогрессии.'
              : 'Нужны полные результаты рабочих подходов последней сопоставимой тренировки.',
          suggested_weight: null,
          suggested_increment: null,
          evidence: {
            ...base.evidence,
            comparable_session_count: mode === 'incomplete' ? 1 : 2,
            rir_recorded_set_count: mode === 'missing-rir' ? 0 : 2,
            reason_keys: [reason],
            sessions,
          },
          proposal: {
            ...base.proposal!,
            rule_kind: mode === 'missing-rir' ? 'rir_rpe' : base.proposal!.rule_kind,
            rule_snapshot:
              mode === 'missing-rir'
                ? {
                    kind: 'rir_rpe',
                    scope: 'program',
                    effort_target: { kind: 'rir', value: 2 },
                    increment_value: 2.5,
                    increment_unit: 'kg',
                  }
                : base.proposal!.rule_snapshot,
            current_weight: mode === 'incomplete' ? null : base.proposal!.current_weight,
            proposed_weight: null,
            proposed_action: 'hold',
            target_set_updates: [],
            comparable_session_count: mode === 'incomplete' ? 1 : 2,
            reason_codes: [reason],
            eligibility_status: 'review',
          },
        };
        return route.fulfill({
          json: {
            ...workout,
            exercises: [{ ...workout.exercises[0], progression_guidance: current }],
          },
        });
      });
      for (const state of ['missing-rir', 'incomplete'] as const) {
        mode = state;
        await page.goto('/app?section=today');
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
        const summary = page.getByRole('region', { name: 'Что делать сейчас?' });
        await summary.getByRole('button', { name: 'Что делать сейчас?' }).click();
        const guidance = summary.locator('.progression-guidance');
        await expect(guidance.getByRole('button', { name: /Применить/ })).toHaveCount(0);
        await expect(guidance).toContainText(
          state === 'missing-rir' ? 'записан не для каждого подхода' : 'нагрузка неполная',
          { ignoreCase: true },
        );
        await guidance.evaluate((node) => node.scrollIntoView({ block: 'center' }));
        await screenshot(guidance, `workout-${state}-${theme}-${viewport.name}.png`);
        await guidance.getByText('Почему такой вес?').click();
        await expect(guidance).toContainText(
          state === 'missing-rir' ? 'missing_rir_evidence' : 'incomplete_session_facts',
        );
        await screenshot(guidance, `workout-${state}-details-${theme}-${viewport.name}.png`);
        await expectNoHorizontalOverflow(page);
      }
    });
  }
}

for (const theme of ['dark', 'light'] as const) {
  for (const viewport of [viewports[2], viewports[4]]) {
    test(`@critical Issue #917 incomplete and unavailable history ${viewport.name} ${theme}`, async ({
      page,
    }) => {
      await page.setViewportSize(viewport);
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await prepare(page);
      let mode: 'no-sets' | 'unknown' | 'error' = 'no-sets';
      const globalAnalytics = await page.evaluate(async () =>
        (await fetch('/api/v1/workouts/progress/training-analytics?period_days=30')).json(),
      );
      await page.route('**/workouts/progress/training-analytics?**', (route) =>
        route.fulfill({
          json: {
            ...globalAnalytics,
            completed_workout_count: mode === 'no-sets' ? 5 : 4,
            frequency_per_week: mode === 'no-sets' ? 1.17 : 0.93,
          },
        }),
      );
      await page.route('**/workouts/progress/training-analytics/week-type?**', (route) => {
        if (mode === 'error')
          return route.fulfill({ status: 503, json: { detail: 'История недоступна' } });
        const type = new URL(route.request().url()).searchParams.get('week_type');
        return route.fulfill({
          json: {
            week_type: type,
            period_start: '2026-10-01',
            period_end: '2026-10-30',
            exercise_history_limit: 20,
            completed_workout_count: mode === 'no-sets' ? 1 : 0,
            completed_set_count: 0,
            external_load_volume_kg: null,
            volume_recorded_sets: 0,
            untyped_workout_count: 0,
            unknown_type_workout_count: mode === 'unknown' ? 2 : 0,
            exercises: [],
          },
        });
      });
      await page.goto('/app?section=progress&progress_view=training');
      const training = page.locator('#progress-training');
      const history = training
        .locator('.progress-subsection')
        .filter({ has: page.getByRole('heading', { name: 'История упражнений' }) });
      const tabs = history.getByRole('tablist', { name: 'Тип недели' });
      const heavy = tabs.getByRole('tab', { name: 'Тяжёлая' });
      await heavy.click();
      await expect(history).toContainText('пока нет записанных рабочих подходов');
      await screenshot(history, `analytics-no-sets-${theme}-${viewport.name}.png`);

      mode = 'unknown';
      await page.reload();
      await heavy.click();
      await expect(history).toContainText('нет подтверждённых тренировок тяжёлого типа');
      await expect(history).toContainText('тип не удалось определить: 2');
      await screenshot(history, `analytics-unknown-${theme}-${viewport.name}.png`);

      mode = 'error';
      await page.reload();
      await heavy.click();
      await expect(history.getByRole('alert')).toContainText('Не удалось загрузить данные');
      await screenshot(history, `analytics-error-${theme}-${viewport.name}.png`);

      await page.context().setOffline(true);
      await tabs.getByRole('tab', { name: 'Средняя' }).click();
      await expect(history).toContainText('История выбранного типа недоступна офлайн');
      await screenshot(history, `analytics-offline-${theme}-${viewport.name}.png`);
      mode = 'no-sets';
      await page.context().setOffline(false);
      await expect(history).toContainText('пока нет записанных рабочих подходов');
      await expectNoHorizontalOverflow(page);
    });
  }
}

for (const theme of ['dark', 'light'] as const) {
  test(`@critical Issue #917 Telegram mock keeps typed controls usable ${theme}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    await installTelegramHarness(page, {
      colorScheme: theme,
      viewportHeight: 760,
      viewportStableHeight: 844,
      safeAreaInset: { top: 28, right: 2, bottom: 20, left: 2 },
      contentSafeAreaInset: { top: 44, right: 0, bottom: 16, left: 0 },
    });
    await prepare(page, false);
    await page.goto('/app?section=today');
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    const summary = page.getByRole('region', { name: 'Что делать сейчас?' });
    await summary.getByRole('button', { name: 'Что делать сейчас?' }).click();
    const guidance = summary.locator('.progression-guidance');
    const apply = guidance.getByRole('button', { name: 'Применить 42,5 кг' });
    await guidance.evaluate((node) => node.scrollIntoView({ block: 'center' }));
    await page.evaluate(() => window.scrollBy(0, 100));
    await expect(apply).toBeVisible();
    await expectTouchTargets(guidance.getByRole('button'));
    await expectNoOverlap(apply, page.locator('#appBottomNav'));
    await expectNoOverlap(
      summary.getByRole('button', { name: 'Боль или травма во время тренировки' }),
      page.locator('#appBottomNav'),
    );
    await expectNoHorizontalOverflow(page);
    if (evidenceDir && test.info().project.name === 'chromium') {
      await page.screenshot({
        path: resolve(evidenceDir, `tma-workout-${theme}-393.png`),
        animations: 'disabled',
      });
    }

    await page.goto('/app?section=progress&progress_view=training');
    const training = page.locator('#progress-training');
    const tabs = training.getByRole('tablist', { name: 'Тип недели' });
    await tabs.getByRole('tab', { name: 'Лёгкая' }).click();
    await expect(training).toContainText('тренировок лёгкого типа пока нет');
    await tabs.evaluate((node) => node.scrollIntoView({ block: 'center' }));
    await expectTouchTargets(tabs.getByRole('tab'));
    await expectNoOverlap(tabs, page.locator('#appBottomNav'));
    await expectNoHorizontalOverflow(page);
    if (evidenceDir && test.info().project.name === 'chromium') {
      await page.screenshot({
        path: resolve(evidenceDir, `tma-analytics-${theme}-393.png`),
        animations: 'disabled',
      });
    }
  });
}
