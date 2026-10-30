import { expect, test, type Locator, type Page } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { inflateSync } from 'node:zlib';
import { emptyHydrationDay, installPlatformApi } from './fixtures/platform-api';
import { progressOverview } from './fixtures/locators';
import {
  expectNoHorizontalOverflow,
  expectNoOverlap,
  expectTouchTargets,
} from './fixtures/mobile-tma';
import type { TrainingAnalytics } from '../../src/shared/api/types';

const captureFeedbackAudit = Boolean(
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.CAPTURE_FEEDBACK_AUDIT,
);

const signal = (
  status: 'sufficient' | 'limited' | 'insufficient',
  counters: Record<string, number> = {},
  reasonKeys: string[] = status === 'sufficient' ? ['thresholds_met'] : ['too_few_points'],
) => ({
  status,
  counters,
  reason_keys: reasonKeys,
});

const TASK_111_SCREENSHOTS = resolve(
  process.cwd(),
  '..',
  '..',
  '..',
  'tasks',
  '111',
  'deliverables',
  'screenshots',
);

type NutritionReportState = 'partial' | 'no-data' | 'long';

const REDUCED_MOTION_MAX_DURATION_MS = 0.01;
const CSS_TIME_TOKEN = /^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(ms|s)$/i;

function hasOnlyReducedMotionDurations(value: string): boolean {
  const durations = value.split(',');
  return (
    durations.length > 0 &&
    durations.every((duration) => {
      const match = CSS_TIME_TOKEN.exec(duration.trim());
      if (!match) return false;
      const unit = match[2];
      if (!unit) return false;
      const amount = Number(match[1]);
      if (!Number.isFinite(amount) || amount < 0) return false;
      const durationMs = amount * (unit.toLowerCase() === 's' ? 1_000 : 1);
      return durationMs <= REDUCED_MOTION_MAX_DURATION_MS + Number.EPSILON;
    })
  );
}

const CAPTURE_PROGRESS_865 = process.env.CAPTURE_PROGRESS_865;
const CAPTURE_970_AFTER = process.env.CAPTURE_970_AFTER === '1';
const WORKTREE_ROOT = resolve(process.cwd(), '..');
const CAPTURE_1050_PHASE = process.env.CAPTURE_1050_PHASE;
const ISSUE_1050_EVIDENCE_DIR = resolve(
  WORKTREE_ROOT,
  'docs',
  'ux',
  'issue-1050-muscle-workload-cards',
  'evidence',
);
const ISSUE_970_AFTER_DIR = resolve(
  WORKTREE_ROOT,
  'docs',
  'ux',
  'final-issues-acceptance',
  'evidence',
  '970-report-mobile-20261013',
  'after',
);
const CAPTURE_1049_EVIDENCE = process.env.CAPTURE_1049_EVIDENCE === '1';
const CAPTURE_1049_BEFORE_EVIDENCE = process.env.CAPTURE_1049_BEFORE_EVIDENCE === '1';
const ISSUE_1049_EVIDENCE_DIR = resolve(WORKTREE_ROOT, '.artifacts', 'tasks', '1049', 'evidence');

type DateVisualMetrics = {
  contentWidth: number;
  expectedTextWidth: number;
  inputWidth: number;
  inkLeft: number | null;
  inkRight: number | null;
  inkWidth: number;
  textRegionRight: number;
};

type DecodedPng = { data: Uint8Array; height: number; width: number };

async function paintedScheduleBottom(card: Locator): Promise<number> {
  const png = decodePng(await card.screenshot({ animations: 'disabled', scale: 'css' }));
  const pixel = (x: number, y: number) =>
    png.data.slice((y * png.width + x) * 4, (y * png.width + x) * 4 + 3);
  let visible = 0;
  for (let i = 2; i <= 8; i += 1) {
    const x = Math.floor((png.width * i) / 10);
    const inside = pixel(x, png.height - 8);
    if (
      [1, 2, 3].some(
        (offset) =>
          pixel(x, png.height - offset).reduce(
            (sum, value, channel) => sum + Math.abs(value - inside[channel]!),
            0,
          ) > 45,
      )
    )
      visible += 1;
  }
  return visible;
}

function decodePng(buffer: Buffer): DecodedPng {
  if (buffer.readUInt32BE(0) !== 0x89504e47 || buffer.readUInt32BE(4) !== 0x0d0a1a0a) {
    throw new Error('Date visual regression expected a PNG screenshot');
  }
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  let interlaceMethod = 0;
  const imageData: Buffer[] = [];
  for (let offset = 8; offset < buffer.length;) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString('ascii', offset + 4, offset + 8);
    const dataStart = offset + 8;
    const dataEnd = dataStart + length;
    if (type === 'IHDR') {
      width = buffer.readUInt32BE(dataStart);
      height = buffer.readUInt32BE(dataStart + 4);
      bitDepth = buffer[dataStart + 8]!;
      colorType = buffer[dataStart + 9]!;
      interlaceMethod = buffer[dataStart + 12]!;
    } else if (type === 'IDAT') {
      imageData.push(buffer.subarray(dataStart, dataEnd));
    }
    offset = dataEnd + 4;
  }
  if (bitDepth !== 8 || interlaceMethod !== 0 || ![2, 6].includes(colorType)) {
    throw new Error(
      `Unsupported date screenshot PNG format: ${bitDepth}/${colorType}/${interlaceMethod}`,
    );
  }
  const channels = colorType === 6 ? 4 : 3;
  const bytesPerRow = width * channels;
  const raw = inflateSync(Buffer.concat(imageData));
  const pixels = new Uint8Array(width * height * 4);
  const previous = new Uint8Array(bytesPerRow);
  const current = new Uint8Array(bytesPerRow);
  let rawOffset = 0;
  for (let y = 0; y < height; y += 1) {
    const filter = raw[rawOffset++]!;
    for (let index = 0; index < bytesPerRow; index += 1) {
      const left = index >= channels ? current[index - channels]! : 0;
      const above = previous[index]!;
      const upperLeft = index >= channels ? previous[index - channels]! : 0;
      const source = raw[rawOffset++]!;
      const predictor =
        filter === 1
          ? left
          : filter === 2
            ? above
            : filter === 3
              ? Math.floor((left + above) / 2)
              : filter === 4
                ? paethPredictor(left, above, upperLeft)
                : 0;
      if (![0, 1, 2, 3, 4].includes(filter)) {
        throw new Error(`Unsupported PNG row filter: ${filter}`);
      }
      current[index] = (source + predictor) & 0xff;
    }
    for (let x = 0; x < width; x += 1) {
      const source = x * channels;
      const destination = (y * width + x) * 4;
      pixels[destination] = current[source]!;
      pixels[destination + 1] = current[source + 1]!;
      pixels[destination + 2] = current[source + 2]!;
      pixels[destination + 3] = channels === 4 ? current[source + 3]! : 255;
    }
    previous.set(current);
    current.fill(0);
  }
  return { data: pixels, height, width };
}

function paethPredictor(left: number, above: number, upperLeft: number): number {
  const estimate = left + above - upperLeft;
  const leftDistance = Math.abs(estimate - left);
  const aboveDistance = Math.abs(estimate - above);
  const upperLeftDistance = Math.abs(estimate - upperLeft);
  if (leftDistance <= aboveDistance && leftDistance <= upperLeftDistance) return left;
  if (aboveDistance <= upperLeftDistance) return above;
  return upperLeft;
}

type DateLayoutMetrics = {
  contentWidth: number;
  expectedTextWidth: number;
  inputWidth: number;
  paddingLeft: number;
  paddingRight: number;
};

function analyzeDateScreenshots(
  filledBuffer: Buffer,
  blankBuffer: Buffer,
  layout: DateLayoutMetrics,
): DateVisualMetrics {
  const filled = decodePng(filledBuffer);
  const blank = decodePng(blankBuffer);
  const scale = filled.width / Math.max(layout.inputWidth, 1);
  const textRegionRight = Math.floor(filled.width - Math.max(42, layout.paddingRight) * scale);
  const textRegionLeft = Math.max(4, Math.floor(layout.paddingLeft * scale - 2));
  const changedColumns = new Uint8Array(filled.width);
  const width = Math.min(filled.width, blank.width);
  const height = Math.min(filled.height, blank.height);
  for (let y = 6; y < height - 6; y += 1) {
    for (let x = textRegionLeft; x < Math.min(textRegionRight, width); x += 1) {
      const index = (y * width + x) * 4;
      const difference =
        Math.abs(filled.data[index]! - blank.data[index]!) +
        Math.abs(filled.data[index + 1]! - blank.data[index + 1]!) +
        Math.abs(filled.data[index + 2]! - blank.data[index + 2]!);
      if (difference >= 32) changedColumns[x] = 1;
    }
  }
  const changed = Array.from(changedColumns.entries())
    .filter(([, value]) => value === 1)
    .map(([column]) => column);
  return {
    contentWidth: layout.contentWidth,
    expectedTextWidth: layout.expectedTextWidth,
    inputWidth: layout.inputWidth,
    inkLeft: changed.length ? changed[0]! / scale : null,
    inkRight: changed.length ? changed[changed.length - 1]! / scale : null,
    inkWidth: changed.length ? (changed[changed.length - 1]! - changed[0]! + 1) / scale : 0,
    textRegionRight: textRegionRight / scale,
  };
}

async function inspectDateVisual(
  page: Page,
  input: Locator,
  value: string,
  focused: boolean,
): Promise<DateVisualMetrics> {
  const setFocusState = async () => {
    if (focused) {
      await input.focus();
      return;
    }
    await page.evaluate(() => {
      const active = document.activeElement;
      if (active instanceof HTMLElement) active.blur();
    });
  };

  const capture = async (nextValue: string) => {
    await input.fill(nextValue);
    await expect(input).toHaveValue(nextValue);
    await setFocusState();
    return input.screenshot({ animations: 'disabled' });
  };

  const filled = await capture(value);
  const blank = await capture('');
  await input.fill(value);
  await expect(input).toHaveValue(value);
  await setFocusState();
  const id = await input.getAttribute('id');
  if (!id) throw new Error('Date input must have an id for visual regression');
  const layout = await page.locator(`#${id}`).evaluate((element) => {
    const input = element as HTMLInputElement;
    const style = getComputedStyle(input);
    const rect = input.getBoundingClientRect();
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Canvas is unavailable for font measurement');
    context.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    return {
      contentWidth:
        input.clientWidth -
        (Number.parseFloat(style.paddingLeft) || 0) -
        (Number.parseFloat(style.paddingRight) || 0),
      expectedTextWidth: Math.max(
        context.measureText('01.01.2025').width,
        context.measureText('2025-01-01').width,
      ),
      inputWidth: rect.width,
      paddingLeft: Number.parseFloat(style.paddingLeft) || 0,
      paddingRight: Number.parseFloat(style.paddingRight) || 0,
    };
  });
  return analyzeDateScreenshots(filled, blank, layout);
}

function shiftDate(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function nutritionReportFixture(url: URL, state: NutritionReportState) {
  const period = url.searchParams.get('period') ?? 'days_30';
  let periodEnd = '2030-01-30';
  let periodStart = shiftDate(
    periodEnd,
    period === 'days_7' ? -6 : period === 'days_90' ? -89 : -29,
  );
  if (period === 'current_week') periodStart = '2030-01-28';
  if (period === 'current_month') periodStart = '2030-01-01';
  if (period === 'previous_month') {
    periodStart = '2029-12-01';
    periodEnd = '2029-12-31';
  }
  if (period === 'custom') {
    periodStart = url.searchParams.get('date_from') ?? periodStart;
    periodEnd = url.searchParams.get('date_to') ?? periodEnd;
  }
  const dayCount =
    Math.round(
      (Date.parse(`${periodEnd}T12:00:00Z`) - Date.parse(`${periodStart}T12:00:00Z`)) / 86_400_000,
    ) + 1;
  const targetChangeDate = shiftDate(
    periodStart,
    Math.min(Math.max(1, Math.floor(dayCount * 0.45)), dayCount - 1),
  );
  const daily = Array.from({ length: dayCount }, (_, index) => {
    const diaryDate = shiftDate(periodStart, index);
    const trainerTarget = state === 'long' && diaryDate > targetChangeDate;
    const targetCalories = diaryDate < targetChangeDate ? 2100 : trainerTarget ? 2000 : 1950;
    const targetProtein = diaryDate < targetChangeDate ? 140 : trainerTarget ? 140 : 135;
    const targetFat = diaryDate < targetChangeDate ? 70 : trainerTarget ? 70 : 65;
    const targetCarbs = diaryDate < targetChangeDate ? 230 : trainerTarget ? 220 : 210;
    const status =
      state === 'no-data'
        ? 'missing'
        : index === dayCount - 1
          ? 'incomplete'
          : index === dayCount - 3
            ? 'fasted'
            : index % (state === 'long' ? 6 : 4) === 0
              ? 'complete'
              : 'missing';
    const logged = status === 'complete' || status === 'fasted';
    const calories =
      status === 'fasted'
        ? 0
        : status === 'complete'
          ? 2020 + (index % 5) * 35
          : status === 'incomplete'
            ? 760
            : null;
    const protein =
      status === 'fasted'
        ? 0
        : status === 'complete'
          ? 138 + (index % 4) * 3
          : status === 'incomplete'
            ? 52
            : null;
    const fat =
      status === 'fasted'
        ? 0
        : status === 'complete'
          ? 64 + (index % 4) * 2
          : status === 'incomplete'
            ? 24
            : null;
    const carbs =
      status === 'fasted'
        ? 0
        : status === 'complete'
          ? 205 + (index % 4) * 4
          : status === 'incomplete'
            ? 85
            : null;
    return {
      diary_date: diaryDate,
      status,
      is_current_day: diaryDate === '2030-01-30',
      calories,
      protein_g: protein,
      fat_g: fat,
      carbs_g: carbs,
      target_calories: targetCalories,
      target_protein_g: targetProtein,
      target_fat_g: targetFat,
      target_carbs_g: targetCarbs,
      calorie_deviation: logged && calories != null ? calories - targetCalories : null,
      protein_deviation_g: logged && protein != null ? protein - targetProtein : null,
      fat_deviation_g: logged && fat != null ? fat - targetFat : null,
      carbs_deviation_g: logged && carbs != null ? carbs - targetCarbs : null,
      within_calorie_tolerance:
        logged && calories != null
          ? Math.abs(calories - targetCalories) <= targetCalories * 0.1
          : null,
      meets_protein_target: logged && protein != null ? protein >= targetProtein : null,
      target_changed: state !== 'no-data' && diaryDate === targetChangeDate,
    };
  });
  const logged = daily.filter((point) => point.status === 'complete' || point.status === 'fasted');
  const values = (key: 'calories' | 'protein_g' | 'fat_g' | 'carbs_g') =>
    logged.map((point) => point[key] as number);
  const metric = (key: 'calories' | 'protein_g' | 'fat_g' | 'carbs_g') => {
    const items = values(key);
    return items.length
      ? {
          average: items.reduce((sum, value) => sum + value, 0) / items.length,
          minimum: Math.min(...items),
          maximum: Math.max(...items),
          sample_days: items.length,
        }
      : { average: null, minimum: null, maximum: null, sample_days: 0 };
  };
  const comparison = (
    actualKey: 'calories' | 'protein_g' | 'fat_g' | 'carbs_g',
    targetKey: 'target_calories' | 'target_protein_g' | 'target_fat_g' | 'target_carbs_g',
  ) => {
    if (!logged.length)
      return {
        average_actual: null,
        average_target: null,
        average_deviation: null,
        evaluated_days: 0,
      };
    const actual =
      logged.reduce((sum, point) => sum + (point[actualKey] as number), 0) / logged.length;
    const target =
      logged.reduce((sum, point) => sum + (point[targetKey] as number), 0) / logged.length;
    return {
      average_actual: actual,
      average_target: target,
      average_deviation: actual - target,
      evaluated_days: logged.length,
    };
  };
  return {
    period,
    period_start: periodStart,
    period_end: periodEnd,
    timezone: 'Europe/Moscow',
    summary: {
      logged_days: logged.length,
      eligible_days: daily.length,
      coverage_percent: Math.round((logged.length * 1000) / daily.length) / 10,
      complete_days: daily.filter((point) => point.status === 'complete').length,
      incomplete_days: daily.filter((point) => point.status === 'incomplete').length,
      fasted_days: daily.filter((point) => point.status === 'fasted').length,
      missing_days: daily.filter((point) => point.status === 'missing').length,
      current_day_status: daily.find((point) => point.is_current_day)?.status ?? null,
      calories: metric('calories'),
      protein_g: metric('protein_g'),
      fat_g: metric('fat_g'),
      carbs_g: metric('carbs_g'),
      calorie_comparison: comparison('calories', 'target_calories'),
      protein_comparison: comparison('protein_g', 'target_protein_g'),
      fat_comparison: comparison('fat_g', 'target_fat_g'),
      carbs_comparison: comparison('carbs_g', 'target_carbs_g'),
      days_within_calorie_tolerance: logged.filter((point) => point.within_calorie_tolerance)
        .length,
      calorie_tolerance_evaluated_days: logged.length,
      days_meeting_protein_target: logged.filter((point) => point.meets_protein_target).length,
      protein_target_evaluated_days: logged.length,
    },
    daily,
    target_changes:
      state === 'no-data'
        ? []
        : [
            {
              effective_from: targetChangeDate,
              source: 'adaptive',
              calories: 1950,
              protein_g: 135,
              fat_g: 65,
              carbs_g: 210,
            },
            ...(state === 'long'
              ? [
                  {
                    effective_from: shiftDate(targetChangeDate, 1),
                    source: 'trainer',
                    calories: 2000,
                    protein_g: 140,
                    fat_g: 70,
                    carbs_g: 220,
                  },
                ]
              : []),
          ],
  };
}

type ProgressMockOptions = {
  muscleGroupWorkload?: TrainingAnalytics['muscle_group_workload'];
};

function issue1050Period(
  completedSetCount: number,
  completedSessionCount: number,
  frequencyPerWeek: number,
) {
  return {
    completed_set_count: completedSetCount,
    primary_completed_set_count: completedSetCount,
    secondary_completed_set_count: 0,
    completed_session_count: completedSessionCount,
    frequency_per_week: frequencyPerWeek,
  };
}

const ISSUE_1050_MUSCLE_WORKLOAD: TrainingAnalytics['muscle_group_workload'] = [
  {
    muscle_id: 'chest',
    muscle_name: 'Грудь',
    current: issue1050Period(18, 6, 1.4),
    previous: issue1050Period(12, 4, 0.93),
    completed_set_count_change: 6,
    frequency_per_week_change: 0.47,
    trend: 'increased',
    contributing_exercises: [],
  },
  {
    muscle_id: 'front-deltoid',
    muscle_name: 'Передняя дельта и стабилизаторы плечевого пояса',
    current: issue1050Period(9, 3, 0.7),
    previous: null,
    completed_set_count_change: null,
    frequency_per_week_change: null,
    trend: 'no_comparable_data',
    contributing_exercises: [],
  },
  {
    muscle_id: 'core',
    muscle_name: 'Кор',
    current: issue1050Period(6, 2, 0.47),
    previous: issue1050Period(6, 2, 0.47),
    completed_set_count_change: 0,
    frequency_per_week_change: 0,
    trend: 'unchanged',
    contributing_exercises: [],
  },
];

async function mockProgress(
  page: Page,
  reportState: NutritionReportState = 'partial',
  options: ProgressMockOptions = {},
) {
  const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Moscow' });
  const previousDate = shiftDate(today, -7);
  let measurements: Array<{
    id: number;
    measured_on: string;
    weight_kg: number | null;
    chest_cm: number | null;
    waist_cm: number | null;
    hips_cm: number | null;
    biceps_cm: number | null;
    thigh_cm: number | null;
    note: string | null;
  }> = [
    {
      id: 1,
      measured_on: previousDate,
      weight_kg: 69.1,
      chest_cm: null,
      waist_cm: 72.5,
      hips_cm: null,
      biceps_cm: null,
      thigh_cm: null,
      note: 'Утром до завтрака',
    },
  ];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const period = Number(url.searchParams.get('period_days')) || 30;
    if (path.endsWith('/public/config')) {
      return route.fulfill({
        json: { app_env: 'dev', enable_dev_auth: true, telegram_bot_username: '' },
      });
    }
    if (path.endsWith('/auth/refresh')) {
      return route.fulfill({ status: 401, json: { detail: 'No refresh cookie' } });
    }
    if (path.endsWith('/auth/dev-login')) {
      return route.fulfill({ json: { access_token: 'test-token', token_type: 'bearer' } });
    }
    if (path.endsWith('/me')) {
      return route.fulfill({
        json: {
          id: 7,
          first_name: 'Анна',
          is_coach: false,
          is_admin: false,
          has_active_program: true,
          has_workout_history: true,
          onboarding: { status: 'complete', required_fields: [], missing_fields: [] },
          profile: { full_name: 'Анна Петрова', timezone: 'Europe/Moscow', kbju: null },
          trainer: { id: 70 },
        },
      });
    }
    if (path.endsWith('/workouts/today')) {
      return route.fulfill({ status: 404, json: { detail: 'На сегодня тренировка не назначена' } });
    }
    if (path.endsWith('/nutrition/hydration')) {
      return route.fulfill({
        json: emptyHydrationDay(url.searchParams.get('diary_date') || '2030-01-30'),
      });
    }
    if (path.endsWith('/nutrition/diary')) {
      return route.fulfill({
        json: {
          diary_date: url.searchParams.get('diary_date') || '2030-01-30',
          timezone: 'Europe/Moscow',
          meals: [],
          status: 'unlogged',
          status_is_explicit: false,
          totals: {
            energy_kcal: '0',
            protein_g: '0',
            fat_g: '0',
            carbs_g: '0',
            fiber_g: null,
          },
          targets: null,
          remaining: null,
        },
      });
    }
    if (path.endsWith('/workouts/progress/summary')) {
      return route.fulfill({
        json: {
          user_id: 7,
          period_days: period,
          period_start: '2030-01-01',
          period_end: '2030-01-30',
          training: {
            planned_workouts: 8,
            completed_workouts: 7,
            frequency_per_week: 1.63,
            volume_kg: 12400,
            new_personal_records: 2,
            last_completed_workout_on: '2030-01-28',
            next_workout: null,
          },
          nutrition: {
            visible: true,
            logged_days: 9,
            adherence_evaluated_days: 9,
            complete_days: 18,
            incomplete_days: 2,
            fasted_days: 0,
            unlogged_days: 10,
            average_calories: 1980,
            target_calories: 2100,
            average_protein_g: 132,
            target_protein_g: 140,
            target_effective_on: '2029-12-01',
          },
          body: {
            latest_measurement: { measured_on: '2030-01-29', weight_kg: 68.4, waist_cm: 72 },
            trends: [
              {
                metric: 'weight_kg',
                unit: 'kg',
                first_value: 69.4,
                latest_value: 68.4,
                change: -1,
                first_measured_on: '2030-01-02',
                latest_measured_on: '2030-01-29',
                point_count: 4,
                span_days: 27,
                interpretation_status: 'available',
                points: [
                  { measured_on: '2030-01-02', value: 69.4 },
                  { measured_on: '2030-01-05', value: 69.1 },
                  { measured_on: '2030-01-22', value: 68.8 },
                  { measured_on: '2030-01-29', value: 68.4 },
                ],
              },
              {
                metric: 'waist_cm',
                unit: 'cm',
                first_value: 73,
                latest_value: 72,
                change: -1,
                first_measured_on: '2030-01-02',
                latest_measured_on: '2030-01-29',
                point_count: 2,
                span_days: 27,
                interpretation_status: 'insufficient_points',
                points: [
                  { measured_on: '2030-01-02', value: 73 },
                  { measured_on: '2030-01-29', value: 72 },
                ],
              },
            ],
            priority: {
              mode: 'muscle_groups',
              muscle_group_ids: ['back', 'posterior_chain'],
            },
            guidance: {
              comparison_basis: 'self',
              minimum_points_for_interpretation: 3,
              minimum_span_days_for_interpretation: 14,
              consistency_tips: ['Снимайте замеры в похожее время суток и в одинаковых условиях.'],
              circumference_limitations: [
                'Окружность плеча не измеряет отдельно бицепс или трицепс.',
              ],
            },
          },
          cardio: {
            completed_sessions: 3,
            planned_sessions: 0,
            frequency_per_week: 0.7,
            duration_minutes: 120,
            distance_km: 12,
            zone_duration: [],
          },
          adherence: {
            formula_version: 'adherence-v1',
            overall_percent: 84,
            included_components: ['workouts', 'calories', 'protein'],
            workouts: {
              status: 'available',
              percent: 87.5,
              achieved: 7,
              evaluated: 8,
              weight: 0.4,
            },
            cardio: {
              status: 'unsupported',
              percent: null,
              achieved: 0,
              evaluated: 0,
              weight: 0.2,
            },
            calories: {
              status: 'available',
              percent: 77.8,
              achieved: 7,
              evaluated: 9,
              weight: 0.2,
            },
            protein: {
              status: 'available',
              percent: 66.7,
              achieved: 6,
              evaluated: 9,
              weight: 0.2,
            },
          },
          data_sufficiency: {
            ruleset_version: 'data-sufficiency-v1',
            workout_logging: signal('sufficient', {
              completed_workout_count: 7,
              prescribed_set_count: 28,
              logged_set_count: 28,
              coverage_percent: 100,
            }),
            working_sets: signal('sufficient', {
              workout_session_count: 7,
              working_set_count: 28,
              required_workout_session_count: 2,
              required_working_set_count: 6,
            }),
            rir_coverage: signal('limited', {
              working_set_count: 28,
              recorded_set_count: 16,
              required_recorded_set_count: 3,
              coverage_percent: 57.1,
              required_coverage_percent: 50,
            }),
            nutrition_coverage: signal('sufficient', {
              logged_day_count: 9,
              eligible_day_count: 30,
              required_logged_day_count: 7,
              coverage_percent: 30,
            }),
            weight_trend: signal('sufficient', {
              point_count: 4,
              span_days: 27,
              required_point_count: 3,
              required_span_days: 14,
            }),
            anthropometry: signal(
              'limited',
              {
                measured_metric_count: 1,
                sufficient_metric_count: 0,
                maximum_point_count: 2,
                maximum_span_days: 27,
                required_point_count_per_metric: 3,
                required_span_days_per_metric: 14,
              },
              ['too_few_points'],
            ),
            schedule_adherence: signal('sufficient', {
              evaluable_workout_count: 8,
              required_evaluable_workout_count: 3,
            }),
          },
        },
      });
    }
    if (path.endsWith('/workouts/progress/nutrition-report')) {
      return route.fulfill({ json: nutritionReportFixture(url, reportState) });
    }
    if (path.endsWith('/workouts/progress/nutrition-report.csv')) {
      return route.fulfill({
        body: '\ufeffrow_type,period_start,period_end\nsummary,2030-01-01,2030-01-30\n',
        contentType: 'text/csv; charset=utf-8',
        headers: { 'Content-Disposition': 'attachment; filename="nutrition-report.csv"' },
      });
    }
    if (path.endsWith('/workouts/progress/activity-heatmap')) {
      const year = Number(
        new URL(route.request().url()).searchParams.get('year') ?? new Date().getFullYear(),
      );
      const count = (Date.UTC(year + 1, 0, 1) - Date.UTC(year, 0, 1)) / 86400000;
      return route.fulfill({
        json: {
          timezone: 'Europe/Moscow',
          history_complete: year === 2023 || year === 2022,
          undated_workouts: year === 2023 || year === 2022 ? 0 : 1,
          days: Array.from({ length: count }, (_, index) => ({
            date: new Date(Date.UTC(year, 0, 1 + index)).toISOString().slice(0, 10),
            is_future: year === new Date().getFullYear() && index > 29,
            completed_workouts:
              year === 2023
                ? 0
                : year === 2022
                  ? index % 5 === 0
                    ? 1
                    : 0
                  : index === 26 || (year === 2024 && index >= 35 && index % 5 === 0)
                    ? 1
                    : null,
            working_sets:
              year === 2023
                ? 0
                : year === 2022
                  ? index % 5 === 0
                    ? 4
                    : 0
                  : index === 26 || (year === 2024 && index >= 35 && index % 5 === 0)
                    ? 4
                    : null,
          })),
        },
      });
    }
    if (path.endsWith('/workouts/progress/training-analytics')) {
      return route.fulfill({
        json: {
          period_days: period,
          period_start: '2030-01-01',
          period_end: '2030-01-30',
          previous_period_start: '2029-12-02',
          previous_period_end: '2029-12-31',
          exercise_history_limit: 20,
          completed_set_count: 28,
          completed_workout_count: 7,
          frequency_per_week: 1.63,
          previous_completed_workout_count: 6,
          previous_frequency_per_week: 1.4,
          reps_total: 226,
          reps_recorded_sets: 28,
          external_load_volume_kg: 12400,
          volume_recorded_sets: 24,
          exercises: [
            {
              exercise_id: 11,
              exercise_title: 'Жим штанги лёжа',
              uses_bodyweight_equipment: false,
              performed_session_count: 6,
              completed_set_count: 18,
              first_performed_on: '2030-01-03',
              last_performed_on: '2030-01-28',
              reps_total: 144,
              reps_recorded_sets: 18,
              max_external_load_kg: 62.5,
              best_set_volume_kg: 500,
              external_load_volume_kg: 7200,
              volume_recorded_sets: 18,
              history_truncated: false,
              sessions: [
                {
                  workout_id: 42,
                  workout_exercise_id: 101,
                  performed_on: '2030-01-28',
                  completed_set_count: 2,
                  reps_total: 16,
                  reps_recorded_sets: 2,
                  max_external_load_kg: 62.5,
                  external_load_volume_kg: 980,
                  volume_recorded_sets: 2,
                  sets: [
                    {
                      set_number: 1,
                      reps: 8,
                      external_load_kg: 60,
                      external_load_volume_kg: 480,
                      rir: '2',
                      set_kind: 'working',
                      reached_failure: false,
                    },
                    {
                      set_number: 2,
                      reps: 8,
                      external_load_kg: 62.5,
                      external_load_volume_kg: 500,
                      rir: null,
                      set_kind: 'working',
                      reached_failure: false,
                    },
                  ],
                },
              ],
            },
          ],
          rir: {
            completed_set_count: 28,
            recorded_set_count: 16,
            missing_set_count: 12,
            distribution: [],
          },
          primary_muscle_exposure: [
            { muscle_id: 'chest', muscle_name: 'Грудные', completed_set_count: 18 },
          ],
          secondary_muscle_exposure: [
            { muscle_id: 'triceps', muscle_name: 'Трицепс', completed_set_count: 18 },
          ],
          muscle_group_workload: options.muscleGroupWorkload ?? [
            {
              muscle_id: 'chest',
              muscle_name: 'Грудные',
              current: {
                completed_set_count: 18,
                primary_completed_set_count: 18,
                secondary_completed_set_count: 0,
                completed_session_count: 6,
                frequency_per_week: 1.4,
              },
              previous: {
                completed_set_count: 12,
                primary_completed_set_count: 12,
                secondary_completed_set_count: 0,
                completed_session_count: 4,
                frequency_per_week: 0.93,
              },
              completed_set_count_change: 6,
              frequency_per_week_change: 0.47,
              trend: 'increased',
              contributing_exercises: [],
            },
          ],
          completed_sets_without_muscle_metadata: 0,
          data_sufficiency: {
            ruleset_version: 'data-sufficiency-v1',
            workout_logging: signal('sufficient', {
              completed_workout_count: 7,
              prescribed_set_count: 28,
              logged_set_count: 28,
              coverage_percent: 100,
            }),
            working_sets: signal('sufficient', {
              workout_session_count: 7,
              working_set_count: 28,
              required_workout_session_count: 2,
              required_working_set_count: 6,
            }),
            rir_coverage: signal('limited', {
              working_set_count: 28,
              recorded_set_count: 16,
              required_recorded_set_count: 3,
              coverage_percent: 57.1,
              required_coverage_percent: 50,
            }),
          },
        },
      });
    }
    if (path.endsWith('/me/profile/body-priority-options')) {
      return route.fulfill({
        json: {
          items: [
            { id: 'back', name: 'Мышцы спины' },
            { id: 'posterior_chain', name: 'Задняя поверхность тела и ягодичные мышцы' },
          ],
        },
      });
    }
    if (path.endsWith('/workouts/diary') && request.method() === 'GET') {
      return route.fulfill({ json: measurements });
    }
    if (path.endsWith('/workouts/diary') && request.method() === 'POST') {
      const body = request.postDataJSON() as Record<string, unknown> & { measured_on: string };
      const existing = measurements.find((item) => item.measured_on === body.measured_on);
      const saved = {
        id: existing?.id ?? measurements.length + 1,
        weight_kg: null,
        chest_cm: null,
        waist_cm: null,
        hips_cm: null,
        biceps_cm: null,
        thigh_cm: null,
        note: null,
        ...existing,
        ...body,
      };
      measurements = [saved, ...measurements.filter((item) => item.id !== saved.id)];
      return route.fulfill({ json: saved });
    }
    if (/\/workouts\/diary\/\d+$/.test(path) && request.method() === 'DELETE') {
      const id = Number(path.split('/').at(-1));
      measurements = measurements.filter((item) => item.id !== id);
      return route.fulfill({ status: 204, body: '' });
    }
    if (path.endsWith('/check-ins/weekly/current')) {
      return route.fulfill({
        json: {
          week_start: '2030-01-28',
          week_end: '2030-02-03',
          submitted_on: '2030-01-30',
          timezone: 'Europe/Moscow',
          existing: {
            id: 1,
            status: 'completed',
            note: null,
            summary: { adaptive_energy: null },
          },
          summary: {
            ruleset_version: 'weekly-review-summary-v2',
            period_start: '2030-01-28',
            period_end: '2030-02-03',
            goal: 'maintenance',
            training: { planned_workouts: 2, completed_workouts: 2, adherence: {} },
            nutrition: {
              logged_days: 3,
              complete_days: 2,
              incomplete_days: 1,
              fasted_days: 0,
              unlogged_days: 4,
              average_calories: 1980,
              target_calories: 2100,
              average_protein_g: 132,
              target_protein_g: 140,
              calories_adherence: {},
              protein_adherence: {},
              current_target: {
                effective_from: '2030-01-01',
                source: 'manual',
                calories: 2100,
                protein_g: 140,
                fat_g: 70,
                carbs_g: 230,
              },
              suspicious_low_days: [],
            },
            progression: { new_personal_records: 1 },
            weight_trend: null,
            anthropometry_trends: [],
            body_priority: null,
            data_sufficiency: {
              weight_trend: {
                status: 'insufficient',
                counters: { point_count: 0 },
                reason_keys: ['no_measurements'],
              },
            },
            adaptive_energy: null,
          },
        },
      });
    }
    if (path.endsWith('/check-ins/weekly')) {
      return route.fulfill({ json: { items: [], total: 0, limit: 4, offset: 0 } });
    }
    if (path.endsWith('/workouts/week')) {
      return route.fulfill({
        json: [
          {
            id: 43,
            scheduled_date: '2030-01-28',
            scheduled_time: '18:30:00',
            title: 'Ноги и корпус',
            status: 'completed',
            day_number: 2,
            week_number: 4,
          },
        ],
      });
    }
    if (path.endsWith('/workouts/schedule')) {
      return route.fulfill({
        json: [
          {
            id: 43,
            scheduled_date: '2030-01-28',
            scheduled_time: '18:30:00',
            title: 'Ноги и корпус',
            status: 'completed',
            day_number: 2,
            week_number: 4,
          },
        ],
      });
    }
    if (path.endsWith('/workouts/cardio')) {
      const dateTo = url.searchParams.get('date_to') ?? '2030-01-30';
      const cardioSessions = [
        {
          activity_type: 'walking',
          duration_minutes: 30,
          distance_km: 3,
          average_heart_rate_bpm: 118,
          heart_rate_zone: 2,
          note: 'Утреннее кардио',
          scheduled_at: `${shiftDate(dateTo, -12)}T08:00:00+03:00`,
          status: 'completed',
          id: 101,
          source: 'manual',
          completed_at: `${shiftDate(dateTo, -12)}T08:30:00+03:00`,
          created_at: `${shiftDate(dateTo, -12)}T08:00:00+03:00`,
          updated_at: `${shiftDate(dateTo, -12)}T08:30:00+03:00`,
        },
        {
          activity_type: 'running',
          duration_minutes: 45,
          distance_km: 4,
          average_heart_rate_bpm: 136,
          heart_rate_zone: 3,
          note: null,
          scheduled_at: `${shiftDate(dateTo, -6)}T18:30:00+03:00`,
          status: 'completed',
          id: 102,
          source: 'manual',
          completed_at: `${shiftDate(dateTo, -6)}T19:15:00+03:00`,
          created_at: `${shiftDate(dateTo, -6)}T18:30:00+03:00`,
          updated_at: `${shiftDate(dateTo, -6)}T19:15:00+03:00`,
        },
        {
          activity_type: 'cycling',
          duration_minutes: 45,
          distance_km: 5,
          average_heart_rate_bpm: null,
          heart_rate_zone: null,
          note: 'Спокойный темп',
          scheduled_at: `${dateTo}T07:30:00+03:00`,
          status: 'completed',
          id: 103,
          source: 'manual',
          completed_at: `${dateTo}T08:15:00+03:00`,
          created_at: `${dateTo}T07:30:00+03:00`,
          updated_at: `${dateTo}T08:15:00+03:00`,
        },
      ];
      return route.fulfill({ json: cardioSessions });
    }
    if (path.endsWith('/workouts/history')) {
      return route.fulfill({
        json: [
          {
            id: 43,
            scheduled_date: '2030-01-28',
            scheduled_time: '18:30:00',
            title: 'Ноги и корпус',
            status: 'completed',
            started_at: '2030-01-28T18:30:00',
            completed_at: '2030-01-28T19:20:00',
            completed_sets: 4,
            volume_kg: 1480,
            exercises: [
              {
                workout_exercise_id: 55,
                exercise_id: 11,
                title: 'Присед со штангой',
                prescribed_sets: 4,
                prescribed_reps: '8',
                sort_order: 1,
              },
            ],
            adaptations: [],
          },
          {
            id: 44,
            scheduled_date: '2030-01-22',
            scheduled_time: '07:30:00',
            title: 'Грудь и спина',
            status: 'completed',
            started_at: '2030-01-22T07:30:00',
            completed_at: '2030-01-22T08:25:00',
            completed_sets: 5,
            volume_kg: 1730,
            exercises: [
              {
                workout_exercise_id: 66,
                exercise_id: 17,
                title: 'Жим гантелей лёжа',
                prescribed_sets: 3,
                prescribed_reps: '10',
                sort_order: 1,
              },
            ],
            adaptations: [],
          },
        ],
      });
    }
    if (path.endsWith('/workouts/43/comments')) {
      return route.fulfill({
        json: [
          {
            id: 7,
            trainer_author_id: 70,
            client_user_id: 7,
            workout_id: 43,
            workout_exercise_id: 55,
            body: 'Держите колени по направлению носков. <script>не HTML</script>',
            body_format: 'plain_text',
            created_at: '2030-01-28T20:00:00',
            updated_at: '2030-01-28T20:05:00',
            revisions: [],
          },
        ],
      });
    }
    if (path.endsWith('/workouts/history/summary')) {
      return route.fulfill({
        json: { workouts_completed: 2, completed_sets: 9, volume_kg: 3210 },
      });
    }
    return route.fulfill({ json: [] });
  });
}

async function expectTrainingHeading(page: Page) {
  const desktop = await page.evaluate(() => matchMedia('(min-width: 768px)').matches);
  await expect(
    page.locator('#progress-training').getByRole('heading', {
      name: desktop ? 'Показатели за период' : 'Тренировки',
      level: 2,
      exact: true,
    }),
  ).toBeVisible();
}

test('progress remains clear and free of horizontal overflow at supported widths', async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  const runtimeErrors: string[] = [];
  page.on('console', (message) => {
    const expectedHttpState =
      message.text().includes('401 (Unauthorized)') || message.text().includes('404 (Not Found)');
    if (message.type() === 'error' && !expectedHttpState) {
      consoleErrors.push(message.text());
    }
  });
  page.on('pageerror', (error) => runtimeErrors.push(error.stack || error.message));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();
  await expect(
    page
      .getByRole('heading', { name: 'Прогресс', exact: true })
      .or(page.getByRole('heading', { name: 'Приложение не смогло продолжить работу' })),
  ).toBeVisible();
  expect(consoleErrors).toEqual([]);
  expect(runtimeErrors).toEqual([]);
  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();
  await expect(page.getByText('84%').first()).toBeVisible();

  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Тренировки/ })
    .click();
  await expectTrainingHeading(page);
  await expect(page.getByRole('heading', { name: 'Активность', exact: true })).toBeVisible();
  await expect(page.getByText('История неполная', { exact: true })).toBeVisible();
  const distribution = page.getByRole('region', { name: 'Мышечные группы', exact: true });
  const chest = distribution.getByRole('button', { name: /^Грудные Всего 18 / });
  await expect(chest).toBeVisible();
  await expect(chest).toHaveAttribute('aria-pressed', 'true');
  await expect(distribution.getByRole('region', { name: 'Грудные', exact: true })).toContainText(
    'Изменение: +6 подходов',
  );
  await page
    .locator('#progress-training .progress-exercises')
    .getByText('Жим штанги лёжа', { exact: true })
    .click();
  await expect(page.getByText('Детали тренировки')).toBeVisible();
  await page.locator('.progress-hero').getByRole('tab', { name: '7 дней' }).click();
  await expect(page.locator('.progress-hero').getByRole('tab', { name: '7 дней' })).toHaveAttribute(
    'aria-selected',
    'true',
  );

  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 768, height: 900 },
    { width: 430, height: 932 },
    { width: 390, height: 844 },
    { width: 360, height: 800 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
    await expect(
      page.locator('.progress-hero').getByRole('tab', { name: '30 дней' }),
    ).toBeVisible();
    await expectTrainingHeading(page);
  }

  expect(consoleErrors).toEqual([]);
  expect(runtimeErrors).toEqual([]);
});

test('schedule card keeps one contour and only internal dividers across mobile states', async ({
  page,
}, testInfo) => {
  const scheduleFixture = [
    {
      id: 1,
      scheduled_date: '2030-01-01',
      scheduled_time: '18:30:00',
      title: 'ДЕНЬ 1',
      status: 'planned',
      day_number: 1,
      week_number: 1,
    },
    {
      id: 2,
      scheduled_date: '2030-01-08',
      scheduled_time: '18:30:00',
      title: 'ДЕНЬ 2',
      status: 'in_progress',
      day_number: 2,
      week_number: 2,
    },
    {
      id: 3,
      scheduled_date: '2030-01-15',
      scheduled_time: '18:30:00',
      title: 'ДЕНЬ 3',
      status: 'missed',
      day_number: 3,
      week_number: 3,
    },
    {
      id: 4,
      scheduled_date: '2030-01-22',
      scheduled_time: '18:30:00',
      title: 'ДЕНЬ 4',
      status: 'completed',
      day_number: 4,
      week_number: 4,
    },
    {
      id: 5,
      scheduled_date: '2030-01-29',
      scheduled_time: '18:30:00',
      title: 'ДЕНЬ 5',
      status: 'planned',
      day_number: 5,
      week_number: 5,
    },
    {
      id: 6,
      scheduled_date: '2030-02-05',
      scheduled_time: '18:30:00',
      title: 'ДЕНЬ 6',
      status: 'completed',
      day_number: 6,
      week_number: 6,
    },
    {
      id: 7,
      scheduled_date: '2030-02-12',
      scheduled_time: '18:30:00',
      title: 'ДЕНЬ 7',
      status: 'completed',
      day_number: 7,
      week_number: 7,
    },
    {
      id: 8,
      scheduled_date: '2030-02-19',
      scheduled_time: '18:30:00',
      title: 'ДЕНЬ 8',
      status: 'completed',
      day_number: 8,
      week_number: 8,
    },
  ];
  const captureEvidence = process.env.CAPTURE_1228_EVIDENCE === '1';
  const evidenceDir = resolve(
    process.cwd(),
    '..',
    '.artifacts',
    'tasks',
    '1228',
    'evidence',
    'after',
  );
  if (captureEvidence) {
    await mkdir(evidenceDir, { recursive: true });
  }
  await mockProgress(page);
  await page.route('**/api/v1/programs/templates/mine', (route) =>
    route.fulfill({
      json: [
        {
          id: 700,
          title: 'Силовая программа на восемь недель',
          goal: 'recomposition',
          level: 'intermediate',
          is_active_for_current_user: true,
          days: [],
        },
      ],
    }),
  );
  await page.route('**/api/v1/workouts/schedule', async (route) =>
    route.fulfill({ json: scheduleFixture }),
  );

  for (const colorScheme of ['light', 'dark'] as const) {
    for (const width of [320, 360, 393, 430] as const) {
      await page.setViewportSize({ width, height: 932 });
      await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
      await page.goto('/app?section=programs');
      const clientButton = page.getByRole('button', { name: 'Клиент' });
      const planHeading = page.getByRole('heading', { name: 'План', exact: true });
      await expect(clientButton.or(planHeading)).toBeVisible();
      if (await clientButton.isVisible()) await clientButton.click();
      await expect(planHeading).toBeVisible();
      await expect(
        page.getByRole('heading', { name: 'Силовая программа на восемь недель' }),
      ).toBeVisible();

      const card = page.locator('details.workout-schedule-card');
      const fieldset = page.locator('fieldset.demo-capability-fieldset');
      const cardSummary = card.locator(':scope > summary');
      await expect(card).toHaveCount(1);
      await expect(card).not.toHaveAttribute('open', '');
      await expect(cardSummary).toBeVisible();
      await expect(card).toHaveCSS('backdrop-filter', 'none');
      await expectTouchTargets(cardSummary);
      if (width === 320 && colorScheme === 'light') {
        await page.addStyleTag({ content: 'html { font-size: 125%; }' });
      }
      // Regression #1228: checking border width only missed an unreadable collapsed top edge.
      const collapsedContour = await card.evaluate((element) => {
        const style = getComputedStyle(element);
        const sides = ['top', 'right', 'bottom', 'left'];
        const borderColors = sides.map((side) => style.getPropertyValue(`border-${side}-color`));
        const borderWidths = sides.map((side) => style.getPropertyValue(`border-${side}-width`));
        const channels = (color: string): number[] =>
          (color.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
        const foreground = channels(style.borderTopColor);
        const background = channels(style.backgroundColor);
        return {
          borderColors,
          borderWidths,
          radius: style.borderTopLeftRadius,
          contrastDistance: foreground.reduce(
            (sum, channel, index) => sum + Math.abs(channel - (background[index] ?? 0)),
            0,
          ),
        };
      });
      expect(collapsedContour.borderWidths).toEqual(['1px', '1px', '1px', '1px']);
      expect(new Set(collapsedContour.borderColors).size).toBe(1);
      expect(collapsedContour.radius).not.toBe('0px');
      // CSS RGB channel distance catches a painted but barely visible border on both themes.
      expect(collapsedContour.contrastDistance).toBeGreaterThanOrEqual(180);
      const bounds = await card.evaluate((element) => {
        const cardRect = element.getBoundingClientRect();
        const parentRect = element.closest('fieldset')!.getBoundingClientRect();
        return { cardBottom: cardRect.bottom, parentBottom: parentRect.bottom };
      });
      expect(bounds.cardBottom).toBeLessThanOrEqual(bounds.parentBottom + 0.5);
      expect(await paintedScheduleBottom(card)).toBe(7);
      await page.evaluate(() =>
        window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' }),
      );
      await expectNoOverlap(card, page.locator('#appBottomNav'));
      if (width === 320 && colorScheme === 'light') {
        await fieldset.evaluate((element) => {
          element.style.clipPath = 'inset(0 0 3px 0)';
        });
        expect(await paintedScheduleBottom(card)).toBe(0);
        await fieldset.evaluate((element) => {
          element.style.removeProperty('clip-path');
        });
      }
      if (captureEvidence && [320, 393, 430].includes(width)) {
        await card.screenshot({
          path: resolve(
            evidenceDir,
            `schedule-${testInfo.project.name}-${colorScheme}-${width}-collapsed.png`,
          ),
        });
      }

      await cardSummary.focus();
      await expect(cardSummary).toBeFocused();
      await cardSummary.press('Enter');
      await expect(card).toHaveAttribute('open', '');
      await expect(card.locator('.workout-context-row')).toHaveCount(8);

      const body = card.locator(':scope > .card-disclosure__body');
      const lists = card.locator('.workout-schedule-list');
      const outerList = lists.nth(0);
      const innerList = lists.nth(1);
      const outerRows = outerList.locator(':scope > .workout-context-row');
      const allWeeks = card.locator('details.workout-schedule-all');
      const allWeeksSummary = allWeeks.locator(':scope > summary');

      await expect(body).toHaveCSS('border-top-width', '1px');
      await expect(lists).toHaveCount(2);
      await expect(outerList).toHaveCSS('border-top-width', '0px');
      await expect(outerList).toHaveCSS('margin-top', '0px');
      await expect(outerRows).toHaveCount(4);
      await expect(outerRows.first()).toHaveCSS('border-bottom-width', '1px');
      await expect(outerRows.last()).toHaveCSS('border-bottom-width', '0px');
      await expect(allWeeks).not.toHaveAttribute('open', '');
      await expect(outerRows.first().locator('.workout-feedback-disclosure')).toHaveCSS(
        'border-top-width',
        '1px',
      );

      await allWeeksSummary.click();
      await expect(allWeeks).toHaveAttribute('open', '');
      await expect(innerList).toBeVisible();
      const innerRows = innerList.locator(':scope > .workout-context-row');
      await expect(innerRows).toHaveCount(4);
      await expect(innerList).toHaveCSS('border-top-width', '0px');
      await expect(innerRows.first()).toHaveCSS('border-bottom-width', '1px');
      await expect(innerRows.last()).toHaveCSS('border-bottom-width', '0px');
      await expect(
        card.getByRole('article', { name: 'Тренировка ДЕНЬ 1 в расписании' }),
      ).toContainText('Запланирована');
      await expect(
        card.getByRole('article', { name: 'Тренировка ДЕНЬ 2 в расписании' }),
      ).toContainText('В процессе');
      await expect(
        card.getByRole('article', { name: 'Тренировка ДЕНЬ 3 в расписании' }),
      ).toContainText('Нужно решить');
      await expect(
        card.getByRole('article', { name: 'Тренировка ДЕНЬ 4 в расписании' }),
      ).toContainText('Завершена');
      await expect(card.getByRole('button', { name: 'Изменить план' }).first()).toBeVisible();
      await expect(card.getByRole('button', { name: 'Вернуться к тренировке' })).toBeVisible();
      await expectTouchTargets(card.getByRole('button', { name: 'Изменить план' }));
      await expectTouchTargets(card.getByRole('button', { name: 'Вернуться к тренировке' }));

      const cardStyles = await card.evaluate((element) => {
        const style = getComputedStyle(element);
        return {
          borderWidths: [
            style.borderTopWidth,
            style.borderRightWidth,
            style.borderBottomWidth,
            style.borderLeftWidth,
          ],
          borderStyles: [
            style.borderTopStyle,
            style.borderRightStyle,
            style.borderBottomStyle,
            style.borderLeftStyle,
          ],
          borderRadius: style.borderRadius,
          overflow: style.overflow,
        };
      });
      expect(cardStyles.borderWidths).toEqual(['1px', '1px', '1px', '1px']);
      expect(cardStyles.borderStyles).toEqual(['solid', 'solid', 'solid', 'solid']);
      expect(cardStyles.borderRadius).not.toBe('0px');
      expect(cardStyles.overflow).toBe('visible');
      expect(await paintedScheduleBottom(card)).toBe(7);

      await expectNoHorizontalOverflow(page);
      await innerRows.last().scrollIntoViewIfNeeded();
      await expectNoOverlap(innerRows.last(), page.locator('#appBottomNav'));
      if (captureEvidence && [320, 393, 430].includes(width)) {
        await card.screenshot({
          path: resolve(
            evidenceDir,
            `schedule-${testInfo.project.name}-${colorScheme}-${width}-expanded.png`,
          ),
        });
      }

      await allWeeksSummary.click();
      await expect(allWeeks).not.toHaveAttribute('open', '');
      await cardSummary.focus();
      await cardSummary.press('Enter');
      await expect(card).not.toHaveAttribute('open', '');
    }
  }
});

test('muscle workload distribution preserves analytics, keyboard drill-down and responsive readability', async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await mockProgress(page, 'partial', { muscleGroupWorkload: ISSUE_1050_MUSCLE_WORKLOAD });
  await page.goto('/app?section=progress&progress_view=training');
  await page.getByRole('button', { name: 'Клиент', exact: true }).click();

  const workload = page.getByRole('region', { name: 'Мышечные группы', exact: true });
  const choices = workload.getByRole('button');
  await expect(choices).toHaveCount(3);
  const longName = workload.getByText('Передняя дельта и стабилизаторы плечевого пояса', {
    exact: true,
  });
  await expect(longName).toBeVisible();
  const first = choices.first();
  await expect(first).toContainText('Всего 18');
  await expect(first).toContainText('1,4 / нед.');
  const longChoice = choices.nth(1);
  await longChoice.focus();
  await longChoice.press('Enter');
  await expect(longChoice).toBeFocused();
  await expect(longChoice).toHaveAttribute('aria-pressed', 'true');
  const longDetail = workload.getByRole('region', {
    name: 'Передняя дельта и стабилизаторы плечевого пояса',
    exact: true,
  });
  await expect(longDetail).toContainText('Нет данных для сравнения');
  await expect(longDetail).toContainText('Текущие 30 дней');
  await first.focus();
  await first.press('Space');
  await expect(first).toBeFocused();
  await expect(first).toHaveAttribute('aria-pressed', 'true');
  await expect(longChoice).toHaveAttribute('aria-pressed', 'false');
  await expect(workload.getByRole('region', { name: 'Грудь', exact: true })).toContainText(
    'Изменение: +6 подходов',
  );

  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
    for (const viewport of [
      { width: 320, height: 800 },
      { width: 360, height: 800 },
      { width: 393, height: 844 },
      { width: 430, height: 932 },
      { width: 1280, height: 900 },
    ]) {
      await page.setViewportSize(viewport);
      await expectNoHorizontalOverflow(page);
      await expectTouchTargets(choices);
      await expect(longName).toBeVisible();
      const nameFits = await longName.evaluate(
        (element) => element.scrollWidth <= element.clientWidth + 1,
      );
      expect(nameFits).toBe(true);
      const visualContract = await first.evaluate((element) => {
        const style = getComputedStyle(element);
        return {
          borders: [
            style.borderTopWidth,
            style.borderRightWidth,
            style.borderBottomWidth,
            style.borderLeftWidth,
          ],
          radius: style.borderRadius,
          choice: element.getAttribute('data-yfc-choice'),
        };
      });
      expect(visualContract.borders).toEqual(['1px', '1px', '1px', '1px']);
      expect(visualContract.radius).not.toBe('0px');
      expect(visualContract.choice).toBe('compact');
    }
  }
  await page.setViewportSize({ width: 393, height: 844 });
  await choices.last().scrollIntoViewIfNeeded();
  await expectNoOverlap(choices.last(), page.locator('#appBottomNav'));
});

test('captures synthetic #1050 muscle workload before/after evidence', async ({ page }) => {
  test.skip(!CAPTURE_1050_PHASE, 'evidence capture is opt-in');
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await mockProgress(page, 'partial', { muscleGroupWorkload: ISSUE_1050_MUSCLE_WORKLOAD });
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();
  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Тренировки/ })
    .click();

  const section = page.getByRole('region', { name: 'Мышечные группы', exact: true });
  await expect(section).toBeVisible();
  await mkdir(ISSUE_1050_EVIDENCE_DIR, { recursive: true });
  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
    for (const viewport of [
      { name: 'mobile-393', width: 393, height: 844 },
      { name: 'desktop-1280', width: 1280, height: 900 },
    ]) {
      await page.setViewportSize(viewport);
      await section.screenshot({
        path: resolve(
          ISSUE_1050_EVIDENCE_DIR,
          `${CAPTURE_1050_PHASE}-${viewport.name}-${colorScheme}.png`,
        ),
      });
    }
  }

  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 393, height: 844 });
  await section.getByRole('button').nth(1).press('Enter');
  await expect(section.getByRole('button').nth(1)).toHaveAttribute('aria-pressed', 'true');
  await section.screenshot({
    path: resolve(ISSUE_1050_EVIDENCE_DIR, `${CAPTURE_1050_PHASE}-mobile-393-light-open.png`),
  });
});

test('Progress has no decorative one-sided lime rails across themes and widths', async ({
  page,
}) => {
  await mockProgress(page);
  const viewports = [
    { width: 320, height: 780 },
    { width: 360, height: 800 },
    { width: 393, height: 852 },
    { width: 430, height: 932 },
    { width: 1440, height: 900 },
  ];

  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await page.goto('/app?section=progress');
  await expect(page.getByRole('button', { name: 'Клиент' })).toBeVisible();
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();
  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();

  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
    const detailBack = page.locator('.progress-detail-header__back');
    if (await detailBack.isVisible()) {
      await detailBack.click();
    }
    await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();

    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await expect(page.locator('.progress-insights__column--good')).toBeVisible();
      const contract = await page.evaluate(() => {
        const root = document.querySelector<HTMLElement>('.progress-experience');
        const probe = document.createElement('span');
        probe.style.color = 'var(--v2-lime)';
        document.body.append(probe);
        const lime = getComputedStyle(probe).color;
        probe.remove();
        const allowed = (element: HTMLElement) =>
          Boolean(
            element.closest(
              '.data-viz-chart__selection, [aria-selected="true"], [aria-current], .is-active, .is-focused, .cta',
            ),
          );
        const violations: string[] = [];
        for (const element of Array.from(root?.querySelectorAll<HTMLElement>('*') ?? [])) {
          const style = getComputedStyle(element);
          const sides = [
            ['left', style.borderLeftWidth, style.borderLeftColor],
            ['right', style.borderRightWidth, style.borderRightColor],
            ['top', style.borderTopWidth, style.borderTopColor],
            ['bottom', style.borderBottomWidth, style.borderBottomColor],
          ].filter(([, width, color]) => Number.parseFloat(width ?? '0') >= 3 && color === lime);
          if (sides.length === 1 && !allowed(element)) {
            violations.push(`${element.className}:border-${sides[0]?.[0]}`);
          }
          const shadow = style.boxShadow;
          if (shadow.includes('inset') && shadow.includes(lime)) {
            const edgeShadow = shadow.match(/inset\s+(-?\d+(?:\.\d+)?)px\s+(-?\d+(?:\.\d+)?)px/);
            if (
              edgeShadow &&
              ((Math.abs(Number(edgeShadow[1] ?? 0)) >= 3 &&
                Math.abs(Number(edgeShadow[2] ?? 0)) < 3) ||
                (Math.abs(Number(edgeShadow[2] ?? 0)) >= 3 &&
                  Math.abs(Number(edgeShadow[1] ?? 0)) < 3)) &&
              !allowed(element)
            ) {
              violations.push(`${element.className}:inset-shadow`);
            }
          }
        }
        const good = root?.querySelector<HTMLElement>('.progress-insights__column--good');
        const confidence = root?.querySelector<HTMLElement>('.data-confidence--sufficient');
        return {
          violations,
          goodBorderLeftWidth: good ? getComputedStyle(good).borderLeftWidth : null,
          confidenceBorderLeftWidth: confidence
            ? getComputedStyle(confidence).borderLeftWidth
            : null,
          confidenceBorderLeftColor: confidence
            ? getComputedStyle(confidence).borderLeftColor
            : null,
          confidenceBorderTopColor: confidence ? getComputedStyle(confidence).borderTopColor : null,
          lime,
        };
      });
      expect(contract.violations).toEqual([]);
      expect(contract.goodBorderLeftWidth).not.toBe('3px');
      expect(contract.confidenceBorderLeftWidth).toBe('1px');
      expect(contract.confidenceBorderLeftColor).toBe(contract.confidenceBorderTopColor);
      expect(contract.confidenceBorderLeftColor).not.toBe(contract.lime);

      if (CAPTURE_1049_BEFORE_EVIDENCE && viewport.width >= 1440) {
        const baselineStyle = await page.addStyleTag({
          content:
            '.app-section--progress .progress-insights__column--good { border-left: 3px solid var(--v2-lime) !important; }',
        });
        await mkdir(ISSUE_1049_EVIDENCE_DIR, { recursive: true });
        await page.locator('.progress-experience').screenshot({
          path: resolve(
            ISSUE_1049_EVIDENCE_DIR,
            colorScheme + '-desktop-1440x900-before-origin-master.png',
          ),
        });
        await baselineStyle.evaluate((element) => element.parentNode?.removeChild(element));
      }

      if (CAPTURE_1049_EVIDENCE && viewport.width === 393) {
        await mkdir(ISSUE_1049_EVIDENCE_DIR, { recursive: true });
        const goodCard = page.locator('.progress-insights__column--good');
        const baselineStyle = await page.addStyleTag({
          content:
            '.app-section--progress .progress-insights__column--good { border-left: 3px solid var(--v2-lime) !important; }',
        });
        await goodCard.screenshot({
          path: resolve(ISSUE_1049_EVIDENCE_DIR, colorScheme + '-mobile-393-before-good.png'),
        });
        await baselineStyle.evaluate((element) => element.parentNode?.removeChild(element));
        await goodCard.screenshot({
          path: resolve(ISSUE_1049_EVIDENCE_DIR, colorScheme + '-mobile-393-after-good.png'),
        });

        const confidenceCard = page.locator('.data-confidence--sufficient').first();
        const historicalConfidenceRail = await page.addStyleTag({
          content:
            '.app-section--progress .data-confidence { border-inline-start-width: 3px !important; border-inline-start-color: var(--v2-lime) !important; }',
        });
        await confidenceCard.screenshot({
          path: resolve(ISSUE_1049_EVIDENCE_DIR, colorScheme + '-mobile-393-before-confidence.png'),
        });
        await historicalConfidenceRail.evaluate((element) =>
          element.parentNode?.removeChild(element),
        );
        await confidenceCard.screenshot({
          path: resolve(ISSUE_1049_EVIDENCE_DIR, colorScheme + '-mobile-393-after-confidence.png'),
        });
      }

      if (CAPTURE_1049_EVIDENCE && viewport.width >= 1440) {
        await mkdir(ISSUE_1049_EVIDENCE_DIR, { recursive: true });
        await page.locator('.progress-experience').screenshot({
          path: resolve(ISSUE_1049_EVIDENCE_DIR, colorScheme + '-desktop-1440x900-after.png'),
        });
      }
    }

    await page
      .getByRole('navigation', { name: 'Разделы прогресса' })
      .getByRole('tab', { name: /^Тренировки/ })
      .click();
    await expectTrainingHeading(page);
    const trainingContract = await page.locator('.progress-experience').evaluate((root) => {
      const cards = Array.from(root.querySelectorAll<HTMLElement>('.program-history-workout'));
      return cards.map((card) => getComputedStyle(card).boxShadow);
    });
    expect(trainingContract.every((shadow) => shadow === 'none')).toBe(true);
  }
});

test('all Progress views keep decorative lime edges out of informational surfaces', async ({
  page,
}) => {
  const views = ['overview', 'body', 'training', 'nutrition', 'cardio', 'wellbeing', 'history'];
  const viewLabels: Record<string, string> = {
    overview: 'Обзор',
    body: 'Тело',
    training: 'Тренировки',
    nutrition: 'Питание',
    cardio: 'Кардио',
    wellbeing: 'Самочувствие',
    history: 'История',
  };
  const viewports = [
    { width: 320, height: 844 },
    { width: 393, height: 844 },
    { width: 1440, height: 1000 },
  ];

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();
  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();

  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await page.goto('/app?section=progress&progress_view=overview');
      await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();
      await expect(page.locator('.progress-experience')).toBeVisible();

      for (const view of views) {
        const tab = page
          .getByRole('navigation', { name: 'Разделы прогресса' })
          .getByRole('tab', { name: new RegExp(`^${viewLabels[view]}`) });
        if (view !== 'overview') {
          await tab.click();
        }
        await expect(tab).toHaveAttribute('aria-selected', 'true');
        await expect(page.locator('[role="status"][aria-busy="true"]')).toHaveCount(0);

        const audit = await page.locator('.progress-experience').evaluate((root) => {
          const probe = document.createElement('span');
          probe.style.color = 'var(--v2-lime)';
          document.body.append(probe);
          const lime = getComputedStyle(probe).color;
          probe.remove();
          const limeChannels = lime.match(/\d+(?:,\s*\d+){2}/)?.[0] ?? '';
          const hasLimeColor = (value: string) =>
            value === lime || (limeChannels !== '' && value.includes(limeChannels));
          const allowed = (element: HTMLElement) =>
            Boolean(
              element.closest(
                '.data-viz-chart__selection, [aria-selected="true"], [aria-current], .is-active, .is-focused, .cta',
              ),
            );
          const violations: string[] = [];
          const describe = (element: HTMLElement) =>
            `${element.tagName.toLowerCase()}.${String(element.className).replace(/\s+/g, '.')}`;
          const physicalEdgeSides = [
            ['left', 'borderLeftWidth', 'borderLeftColor'],
            ['right', 'borderRightWidth', 'borderRightColor'],
            ['top', 'borderTopWidth', 'borderTopColor'],
            ['bottom', 'borderBottomWidth', 'borderBottomColor'],
          ] as const;
          const logicalEdgeSides = [
            ['inline-start', 'borderInlineStartWidth', 'borderInlineStartColor'],
            ['inline-end', 'borderInlineEndWidth', 'borderInlineEndColor'],
          ] as const;
          const frameCandidates = Array.from(
            root.querySelectorAll<HTMLElement>(
              '.progress-insights__column, .progress-overview__adherence',
            ),
          );
          const unevenInfoFrames = frameCandidates.flatMap((element) => {
            if (
              element.classList.contains('progress-overview__adherence') &&
              window.innerWidth < 641
            ) {
              return [];
            }
            const style = getComputedStyle(element);
            const widths = [
              style.borderLeftWidth,
              style.borderRightWidth,
              style.borderTopWidth,
              style.borderBottomWidth,
            ];
            const colors = [
              style.borderLeftColor,
              style.borderRightColor,
              style.borderTopColor,
              style.borderBottomColor,
            ];
            return widths.every((width) => width === '1px') &&
              colors.every((color) => color === colors[0])
              ? []
              : [describe(element)];
          });

          for (const element of Array.from(root.querySelectorAll<HTMLElement>('*'))) {
            const style = getComputedStyle(element);
            const physicalLimeBorders = physicalEdgeSides.filter(
              ([, widthProperty, colorProperty]) => {
                const width = Number.parseFloat(style[widthProperty]);
                return width >= 3 && hasLimeColor(style[colorProperty]);
              },
            );
            const logicalLimeBorders = logicalEdgeSides.filter(
              ([, widthProperty, colorProperty]) => {
                const width = Number.parseFloat(style[widthProperty]);
                return width >= 3 && hasLimeColor(style[colorProperty]);
              },
            );
            if (
              (physicalLimeBorders.length === 1 ||
                (physicalLimeBorders.length === 0 && logicalLimeBorders.length === 1)) &&
              !allowed(element)
            ) {
              const side = physicalLimeBorders[0]?.[0] ?? logicalLimeBorders[0]?.[0];
              violations.push(`${describe(element)}: border-${side}`);
            }

            if (
              style.boxShadow.includes('inset') &&
              hasLimeColor(style.boxShadow) &&
              !allowed(element)
            ) {
              violations.push(`${describe(element)}: inset lime shadow`);
            }

            for (const pseudo of ['::before', '::after'] as const) {
              const pseudoStyle = getComputedStyle(element, pseudo);
              const hasContent = pseudoStyle.content !== 'none' && pseudoStyle.content !== '""';
              const physicalLimePseudoBorders = physicalEdgeSides.filter(
                ([, widthProperty, colorProperty]) => {
                  const width = Number.parseFloat(pseudoStyle[widthProperty]);
                  return width >= 3 && hasLimeColor(pseudoStyle[colorProperty]);
                },
              );
              const logicalLimePseudoBorders = logicalEdgeSides.filter(
                ([, widthProperty, colorProperty]) => {
                  const width = Number.parseFloat(pseudoStyle[widthProperty]);
                  return width >= 3 && hasLimeColor(pseudoStyle[colorProperty]);
                },
              );
              const hasLimeEdge =
                physicalLimePseudoBorders.length === 1 ||
                (physicalLimePseudoBorders.length === 0 && logicalLimePseudoBorders.length === 1);
              const hasLimeBackground =
                hasLimeColor(pseudoStyle.backgroundColor) ||
                hasLimeColor(pseudoStyle.backgroundImage);
              if (hasContent && (hasLimeEdge || hasLimeBackground) && !allowed(element)) {
                violations.push(`${describe(element)}${pseudo}: lime pseudo-element edge`);
              }
            }

            if (
              style.backgroundImage !== 'none' &&
              hasLimeColor(style.backgroundImage) &&
              !allowed(element)
            ) {
              violations.push(`${describe(element)}: lime background image`);
            }
          }

          return { lime, unevenInfoFrames, violations };
        });

        expect(audit.violations, `${colorScheme}/${viewport.width}/${view}`).toEqual([]);
        expect(audit.unevenInfoFrames, `${colorScheme}/${viewport.width}/${view}`).toEqual([]);
      }
    }
  }
});

test('mobile Body keeps expanded surfaces separated and reachable above the dock', async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await mockProgress(page);
  await page.goto('/app?section=progress&progress_view=body');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await expect(page.getByRole('heading', { name: 'Тело', level: 2 })).toBeVisible();

  const diary = page.locator('#progress-body details.progress-body-diary');
  await diary.locator(':scope > summary').click();
  await expect(diary).toHaveAttribute('open', '');

  for (const viewport of [
    { width: 320, height: 844 },
    { width: 393, height: 844 },
    { width: 430, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await expectNoHorizontalOverflow(page);

    const contract = await page.locator('#progress-body').evaluate((root) => {
      const visible = (element: Element) => {
        const box = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return (
          box.width > 0 &&
          box.height > 0 &&
          style.display !== 'none' &&
          style.visibility !== 'hidden'
        );
      };
      const rect = (element: Element) => {
        const box = element.getBoundingClientRect();
        return { top: box.top, bottom: box.bottom };
      };
      const gaps = (elements: Element[]) =>
        elements.slice(1).map((element, index) => {
          const previous = rect(elements[index]!);
          return element.getBoundingClientRect().top - previous.bottom;
        });
      const token = (name: string) =>
        getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      const approved = root.querySelector<HTMLElement>('.progress-body-approved');
      const trends = root.querySelector<HTMLElement>('.progress-body-trends');
      const fieldset = root.querySelector<HTMLElement>(
        '.progress-body-diary .measurement-diary--embedded > .demo-capability-fieldset',
      );
      const children = (parent: Element | null) =>
        parent ? Array.from(parent.children).filter(visible) : [];
      const cards = [
        '.progress-body-hero-card',
        '.progress-trend-panel',
        '.progress-body-diary',
        '.data-confidence',
      ]
        .flatMap((selector) => Array.from(root.querySelectorAll<HTMLElement>(selector)))
        .filter(visible);

      return {
        bodyGap: approved ? getComputedStyle(approved).rowGap : null,
        bodyGaps: gaps(children(approved)),
        trendGap: trends ? getComputedStyle(trends).rowGap : null,
        trendGaps: gaps(children(trends)),
        diaryGap: fieldset ? getComputedStyle(fieldset).rowGap : null,
        diaryGaps: gaps(children(fieldset)),
        bodyToken: token('--v2-space-4'),
        relatedToken: token('--v2-space-3'),
        cards: cards.map((element) => {
          const style = getComputedStyle(element);
          return {
            borderWidths: [
              style.borderTopWidth,
              style.borderRightWidth,
              style.borderBottomWidth,
              style.borderLeftWidth,
            ],
            borderColors: [
              style.borderTopColor,
              style.borderRightColor,
              style.borderBottomColor,
              style.borderLeftColor,
            ],
            borderRadius: style.borderRadius,
          };
        }),
      };
    });

    const bodyGap = Number.parseFloat(contract.bodyToken);
    const relatedGap = Number.parseFloat(contract.relatedToken);
    expect(contract.bodyGap).toBe(contract.bodyToken);
    expect(contract.bodyGaps.every((gap) => gap >= bodyGap - 0.5)).toBe(true);
    expect(contract.trendGap).toBe(contract.relatedToken);
    expect(contract.trendGaps.every((gap) => gap >= relatedGap - 0.5)).toBe(true);
    expect(contract.diaryGap).toBe(contract.relatedToken);
    expect(contract.diaryGaps.every((gap) => gap >= relatedGap - 0.5)).toBe(true);
    expect(contract.cards.length).toBeGreaterThanOrEqual(4);
    for (const card of contract.cards) {
      expect(card.borderWidths).toEqual(['1px', '1px', '1px', '1px']);
      expect(new Set(card.borderColors).size).toBe(1);
      expect(card.borderRadius).not.toBe('0px');
    }

    const dock = page.locator('#appBottomNav');
    await expect(dock).toBeVisible();
    const lastHistoryRow = diary.locator('.measurement-history__row').last();
    await lastHistoryRow.scrollIntoViewIfNeeded();
    await expectNoOverlap(lastHistoryRow, dock);
    const saveButton = diary.locator('.measurement-diary__save');
    await saveButton.scrollIntoViewIfNeeded();
    await expectNoOverlap(saveButton, dock);
  }
});

test('shared data confidence keeps analytics factual, responsive and explicit while refreshing', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await mockProgress(page);

  let releaseRefresh!: () => void;
  let markRefreshStarted!: () => void;
  const refreshGate = new Promise<void>((resolve) => {
    releaseRefresh = resolve;
  });
  const refreshStarted = new Promise<void>((resolve) => {
    markRefreshStarted = resolve;
  });
  await page.route('**/workouts/progress/summary?period_days=7', async (route) => {
    markRefreshStarted();
    await refreshGate;
    await route.fallback();
  });

  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Тренировки/ })
    .click();
  await expectTrainingHeading(page);
  const trainingConfidence = page
    .locator('#progress-training')
    .getByLabel('Достаточно ли данных: Данных достаточно для оценки')
    .first();
  await expect(trainingConfidence).toContainText('28 рабочих подходов в 7 тренировках');
  const trainingRegion = page.locator('#progress-training');
  const confidenceBox = await trainingRegion.locator('.data-confidence').boundingBox();
  const nextBox = await trainingRegion.locator('.progress-subsection').first().boundingBox();
  expect(confidenceBox).not.toBeNull();
  expect(nextBox).not.toBeNull();
  expect(confidenceBox!.y + confidenceBox!.height).toBeLessThanOrEqual(nextBox!.y);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator('#progress-training').screenshot({
    path: '../.artifacts/screenshots/task-61/desktop-1440x900-light-analytics.png',
  });

  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Тело/ })
    .click();
  await expect(page.getByRole('heading', { name: 'Тело' })).toBeVisible();
  const limitedConfidence = page.getByLabel(
    'Достаточно ли данных: Окружности — Вывод пока предварительный',
  );
  await expect(limitedConfidence).toContainText(
    'В самой заполненной окружности — 2 замера; для оценки одной окружности нужно минимум 3 замера',
  );
  await expect(limitedConfidence.locator('.badge')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Добавить замер' })).toBeVisible();

  const visualContract = await page.evaluate(() => {
    const tokenColor = (token: string) => {
      const sample = document.createElement('span');
      sample.style.color = `var(${token})`;
      document.body.append(sample);
      const value = getComputedStyle(sample).color;
      sample.remove();
      return value;
    };
    const sufficient = document.querySelector<HTMLElement>('.data-confidence--sufficient');
    const limited = document.querySelector<HTMLElement>('.data-confidence--limited');
    const disclosure = limited?.querySelector<HTMLElement>('.disclosure-icon');
    const disclosureBox = disclosure?.getBoundingClientRect();
    return {
      lime: tokenColor('--v2-lime'),
      sufficientBoundary: sufficient ? getComputedStyle(sufficient).borderLeftColor : null,
      limitedBoundary: limited ? getComputedStyle(limited).borderLeftColor : null,
      disclosure: disclosureBox
        ? {
            width: disclosureBox.width,
            height: disclosureBox.height,
            radius: getComputedStyle(disclosure!).borderRadius,
          }
        : null,
    };
  });
  expect(visualContract.sufficientBoundary).not.toBe(visualContract.lime);
  expect(visualContract.limitedBoundary).not.toBe(visualContract.lime);
  expect(visualContract.disclosure).toEqual({ width: 28, height: 28, radius: '50%' });

  for (const viewport of [
    { width: 768, height: 900 },
    { width: 430, height: 932 },
    { width: 390, height: 844 },
    { width: 360, height: 800 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
    const disclosure = page.locator('.data-confidence__details > summary').first();
    expect((await disclosure.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  }

  await limitedConfidence.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/screenshots/task-61/mobile-web-360x800-light-analytics.png',
  });

  await page.locator('.progress-detail-header__back').click();
  await expect(progressOverview(page)).toHaveCount(1);
  await expect(progressOverview(page)).toBeVisible();
  await page.locator('.progress-hero').getByRole('tab', { name: '7 дней' }).click();
  await refreshStarted;
  const loadingState = page.getByRole('status').filter({ hasText: 'Обновляем динамику за период' });
  await expect(loadingState).toBeVisible();
  await expect(progressOverview(page)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await loadingState.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/screenshots/task-61/mobile-web-390x844-light-period-loading.png',
  });
  releaseRefresh();
  await expect(progressOverview(page)).toBeVisible();
});

test('measurements keep priority context, units, mobile order and add/edit history', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Тело/ })
    .click();

  const body = page.locator('#progress-body');
  await expect(body.getByRole('heading', { name: 'Тело' })).toBeVisible();
  await body.getByText('Выбранные мышечные группы').click();
  await expect(body.getByText('Мышцы спины')).toBeVisible();
  await expect(body.getByText('Задняя поверхность тела и ягодичные мышцы')).toBeVisible();
  await expect(body.getByText(/не оценивает тело/)).toBeVisible();
  await expect(body.locator('.progress-measurement-editor')).not.toHaveAttribute('open');
  await body.locator('.progress-measurement-editor > summary').click();
  await expect(
    body.locator('.measurement-diary').getByText(/Вес: 69,1 кг · Талия: 72,5 см/),
  ).toBeVisible();
  await expect(body.getByText(/разовое изменение не считаем трендом/)).toBeVisible();
  await expect(body.locator('.progress-body-guidance')).toHaveCSS('display', 'none');
  await expect(body.locator('.measurement-diary').getByText('Как сравнивать замеры')).toBeVisible();

  await page.setViewportSize({ width: 1440, height: 1000 });
  const desktopTrend = await body.locator('.progress-body-trends').boundingBox();
  const desktopDiary = await body.locator('.progress-body-diary').boundingBox();
  expect(desktopTrend).not.toBeNull();
  expect(desktopDiary).not.toBeNull();
  expect(desktopTrend!.y).toBeLessThanOrEqual(desktopDiary!.y);
  await body.evaluate((element) => element.scrollIntoView({ block: 'start' }));
  await page.screenshot({
    path: '../.artifacts/screenshots/task-60/desktop-1440x1000-light.png',
  });

  await page.setViewportSize({ width: 360, height: 800 });
  await expect
    .poll(async () => {
      const mobileTrend = await body.locator('.progress-body-trends').boundingBox();
      const mobileDiary = await body.locator('.progress-body-diary').boundingBox();
      return Boolean(mobileTrend && mobileDiary && mobileDiary.y > mobileTrend.y);
    })
    .toBe(true);
  await expect(body.getByLabel('Вес, кг')).toHaveAttribute('inputmode', 'decimal');
  await body.evaluate((element) => element.scrollIntoView({ block: 'start' }));
  await expect(body.locator('.measurement-diary__save-dock')).toHaveCSS('position', 'static');
  await page.screenshot({
    path: '../.artifacts/screenshots/task-60/mobile-web-360x800-light.png',
  });
  const mobileSave = body.getByRole('button', { name: 'Сохранить замер' });
  await mobileSave.scrollIntoViewIfNeeded();
  const noteField = await body.getByLabel('Заметка').boundingBox();
  const saveButton = await mobileSave.boundingBox();
  expect(noteField).not.toBeNull();
  expect(saveButton).not.toBeNull();
  expect(saveButton!.y - (noteField!.y + noteField!.height)).toBeGreaterThanOrEqual(18 - 0.01);
  await page.screenshot({
    path: '../.artifacts/screenshots/task-60/mobile-web-360x800-light-save.png',
  });

  await body.getByLabel('Вес, кг').fill('68.7');
  await body.getByLabel('Талия, см').fill('71.9');
  expect(
    await body
      .locator('.measurement-diary__form :invalid')
      .evaluateAll((elements) => elements.map((element) => element.getAttribute('aria-label'))),
  ).toEqual([]);
  const createRequest = page.waitForRequest(
    (request) => request.url().endsWith('/workouts/diary') && request.method() === 'POST',
  );
  await body.getByRole('button', { name: 'Сохранить замер' }).click();
  await createRequest;
  await expect(body.getByText(/Вес: 68,7 кг · Талия: 71,9 см/)).toBeVisible();

  const todayRow = body.locator('.measurement-history__row').filter({ hasText: '68,7 кг' });
  await todayRow.getByRole('button', { name: 'Изменить' }).click();
  await expect(body.getByRole('heading', { name: 'Изменить замер' })).toBeVisible();
  await body.getByLabel('Вес, кг').fill('68.5');
  const editRequest = page.waitForRequest(
    (request) => request.url().endsWith('/workouts/diary') && request.method() === 'POST',
  );
  await body.getByRole('button', { name: 'Сохранить изменения' }).click();
  await editRequest;
  await expect(body.getByText(/Вес: 68,5 кг · Талия: 71,9 см/)).toBeVisible();
  await expect(body.getByText(/Вес: 68,7 кг/)).not.toBeAttached();

  const save = body.getByRole('button', { name: 'Сохранить замер' });
  expect((await save.boundingBox())?.height).toBeGreaterThanOrEqual(48);
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    )
    .toBe(true);
});

test('#1190 saves body measurements with hundredths without HTML step mismatch', async ({
  page,
}) => {
  await mockProgress(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app?section=progress&focus=measurements');
  await page.getByRole('button', { name: 'Клиент' }).click();

  const diary = page.locator('#measurement-diary');
  await expect(diary.getByRole('heading', { name: 'Новый замер' })).toBeVisible();
  const weight = diary.getByLabel('Вес, кг');
  const waist = diary.getByLabel('Талия, см');
  await expect(weight).toHaveAttribute('step', '0.01');
  await expect(waist).toHaveAttribute('step', '0.01');
  await weight.fill('72.34');
  await waist.fill('71.23');
  expect(
    await weight.evaluate((element) => (element as HTMLInputElement).validity.stepMismatch),
  ).toBe(false);
  expect(
    await waist.evaluate((element) => (element as HTMLInputElement).validity.stepMismatch),
  ).toBe(false);

  const sent = page.waitForResponse(
    (response) =>
      response.url().endsWith('/workouts/diary') && response.request().method() === 'POST',
  );
  await diary.getByRole('button', { name: 'Сохранить замер' }).click();
  const response = await sent;
  expect(response.status()).toBe(200);
  const request = response.request();
  expect(request.postDataJSON()).toMatchObject({ weight_kg: 72.34, waist_cm: 71.23 });
  expect(await response.json()).toMatchObject({ weight_kg: 72.34, waist_cm: 71.23 });
  await expect(diary.getByText(/Вес: 72,34 кг · Талия: 71,23 см/)).toBeVisible();

  await page.goto('/app?section=progress&focus=measurements');
  await expect(
    page.locator('#measurement-diary').getByText(/Вес: 72,34 кг · Талия: 71,23 см/),
  ).toBeVisible();
});

test('#1189 keeps measurement inputs visible in a keyboard-sized viewport', async ({ page }) => {
  await mockProgress(page);
  await page.goto('/app?section=progress&focus=measurements');
  await page.getByRole('button', { name: 'Клиент' }).click();

  const diary = page.locator('#measurement-diary');
  const weight = diary.getByLabel('Вес, кг');
  const waist = diary.getByLabel('Талия, см');
  const saveDock = diary.locator('.measurement-diary__save-dock');

  // Reduced viewport is a browser regression fixture, not a real iOS keyboard.
  for (const width of [320, 393]) {
    await page.setViewportSize({ width, height: 440 });
    await page.evaluate(() => {
      document.documentElement.setAttribute('data-yfc-keyboard', 'visible');
    });

    await weight.fill('72.34');
    await expect(weight).toBeFocused();
    await expect(saveDock).toHaveCSS('position', 'static');
    // Scrolling once to keep the focused field visible is correct native behavior.
    // A fixed window.scrollY assertion wrongly rejects a legitimate 320px focus correction.
    const inVisualViewport = async (input: typeof weight) =>
      input.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const top = window.visualViewport?.offsetTop ?? 0;
        const bottom = top + (window.visualViewport?.height ?? window.innerHeight);
        return rect.top >= top - 1 && rect.bottom <= bottom + 1;
      });

    await weight.press('Backspace');
    await weight.press('4');
    await expect(weight).toHaveValue('72.34');
    await expect.poll(() => inVisualViewport(weight), { timeout: 2000 }).toBe(true);

    await waist.fill('71.23');
    await expect(waist).toBeFocused();
    await expect.poll(() => inVisualViewport(waist), { timeout: 2000 }).toBe(true);
    await expect(diary.getByRole('button', { name: 'Сохранить замер' })).toBeAttached();
  }
});

test('#1189 iOS PWA delegates measurement keyboard focus and typing to the native viewport', async ({
  page,
}) => {
  // Mirror the already accepted active-workout #1099 standalone PWA harness.
  await page.addInitScript(() => {
    const original = window.matchMedia.bind(window);
    window.matchMedia = (query: string) => {
      const result = original(query);
      if (query === '(display-mode: standalone)') {
        Object.defineProperty(result, 'matches', { configurable: true, value: true });
      }
      return result;
    };
    Object.defineProperty(navigator, 'standalone', { configurable: true, value: true });
  });
  await mockProgress(page);
  await page.goto('/app?section=progress&focus=measurements');
  await page.getByRole('button', { name: 'Клиент' }).click();

  const diary = page.locator('#measurement-diary');
  const weight = diary.getByLabel('Вес, кг');
  const chest = diary.getByLabel('Грудь, см');
  const waist = diary.getByLabel('Талия, см');
  await expect(diary.getByRole('heading', { name: 'Новый замер' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-measurement-pwa', 'true');

  await page.evaluate(() => {
    const root = window as Window & { __yfc1189ScrollCalls?: number };
    const original = window.scrollBy.bind(window);
    root.__yfc1189ScrollCalls = 0;
    window.scrollBy = (x: number | ScrollToOptions = {}, y?: number) => {
      root.__yfc1189ScrollCalls = (root.__yfc1189ScrollCalls ?? 0) + 1;
      if (typeof x === 'number') return original(x, y ?? 0);
      return original(x);
    };
    document.documentElement.setAttribute('data-yfc-keyboard', 'visible');
  });

  // Native focus may pan the page; application-owned scrollBy must not pan it again.
  // The viewport simulates an opened numeric keyboard, not a physical iOS keyboard.
  for (const width of [393, 320]) {
    await page.setViewportSize({ width, height: 440 });
    await weight.fill('75.25');
    await chest.fill('102');
    await waist.fill('84');
    // `fill` does not guarantee the caret position across browser engines.
    // Put it at the end before exercising a delete-and-retype sequence.
    await weight.press('End');
    await weight.press('Backspace');
    await weight.press('5');
    await expect(weight).toHaveValue('75.25');
    await expect(chest).toHaveValue('102');
    await expect(waist).toHaveValue('84');
    await expect(weight).toBeFocused();
    await expect(weight).toHaveCSS('scroll-margin-block-start', '0px');
    await expect(diary.locator('.measurement-diary__save-dock')).toHaveCSS('position', 'static');
    await page.evaluate(
      () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())),
    );
    expect(
      await page.evaluate(
        () => (window as Window & { __yfc1189ScrollCalls?: number }).__yfc1189ScrollCalls,
      ),
    ).toBe(0);
  }
});

test('quick measurement can return without losing an unsaved draft', async ({ page }) => {
  await mockProgress(page);
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await page.setViewportSize({ width: 390, height: 844 });
  const evidenceRoot = resolve(
    process.cwd(),
    '..',
    '.artifacts',
    'runtime',
    'tests',
    'screenshots',
    'issue-969',
  );
  await mkdir(evidenceRoot, { recursive: true });
  await page.goto('/app?section=progress&focus=measurements');
  await page.getByRole('button', { name: 'Клиент' }).click();

  const diary = page.locator('#measurement-diary');
  await expect(diary.getByRole('heading', { name: 'Новый замер' })).toBeVisible();
  await page.screenshot({
    fullPage: true,
    path: resolve(evidenceRoot, `${test.info().project.name}-measurement-light-390x844.png`),
  });
  await page.setViewportSize({ width: 360, height: 800 });
  await page.screenshot({
    fullPage: true,
    path: resolve(evidenceRoot, `${test.info().project.name}-measurement-light-360x800.png`),
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.localStorage.setItem('app-theme', 'dark'));
  await page.reload();
  await expect(
    page.locator('#measurement-diary').getByRole('heading', { name: 'Новый замер' }),
  ).toBeVisible();
  await page.screenshot({
    fullPage: true,
    path: resolve(evidenceRoot, `${test.info().project.name}-measurement-dark-390x844.png`),
  });
  await page.setViewportSize({ width: 360, height: 800 });
  await page.screenshot({
    fullPage: true,
    path: resolve(evidenceRoot, `${test.info().project.name}-measurement-dark-360x800.png`),
  });
  await page.setViewportSize({ width: 390, height: 844 });
  const weight = diary.getByLabel('Вес, кг');
  await weight.fill('70.2');
  await diary.getByRole('button', { name: 'Вернуться' }).click();

  const discardDialog = page.getByRole('dialog', { name: 'Вернуться без сохранения?' });
  await expect(discardDialog).toBeVisible();
  await discardDialog.getByRole('button', { name: 'Отмена' }).click();
  await expect(weight).toHaveValue('70.2');

  await diary.getByRole('button', { name: 'Вернуться' }).click();
  await page
    .getByRole('dialog', { name: 'Вернуться без сохранения?' })
    .getByRole('button', { name: 'Вернуться' })
    .click();
  await expect(page).toHaveURL(/\/app\?section=progress$/);
  await expect(page.locator('[data-testid="quick-add-trigger"]')).toBeFocused();

  await page.goto('/app?section=progress&focus=measurements');
  await expect(page.locator('#measurement-diary').getByLabel('Вес, кг')).toHaveValue('70.2');
});

test('nutrition report preserves truthful period context, daily drill-down and responsive hierarchy', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await mockProgress(page, 'long');
  await page.goto('/app?section=progress&progress_period=days_7');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Питание/ })
    .click();

  const report = page.locator('#nutrition-period-report');
  const selector = page
    .locator('.progress-period-controls')
    .getByRole('tablist', { name: 'Период прогресса' });
  await expect(report.getByRole('heading', { name: 'Отчёт по питанию' })).toBeVisible();
  await selector.getByRole('tab', { name: '7 дней' }).click();
  await expect(report.getByText('Заполнено 2 из 7 дней')).toBeVisible();
  await expect(
    report.getByText('Средние значения рассчитаны только по заполненным дням.'),
  ).toBeVisible();
  await expect(report.getByRole('img', { name: /Калории по дням/ })).toBeVisible();
  const targetHistory = report.locator('.nutrition-report-target-history');
  const targetHistorySummary = targetHistory.locator(':scope > summary');
  await expect(targetHistory).not.toHaveAttribute('open', '');
  await expect(targetHistorySummary).toHaveAttribute('aria-expanded', 'false');
  const days = report.locator('.nutrition-report-days');
  const daysSummary = days.locator(':scope > summary');
  const daysStyle = await days.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      borderWidths: [
        style.borderTopWidth,
        style.borderRightWidth,
        style.borderBottomWidth,
        style.borderLeftWidth,
      ],
      borderRadius: style.borderRadius,
    };
  });
  expect(daysStyle.borderWidths).toEqual(['1px', '1px', '1px', '1px']);
  expect(Number.parseFloat(daysStyle.borderRadius)).toBeGreaterThan(0);
  await expect(days.locator('.nutrition-report-days__table-wrap')).toHaveCSS(
    'border-left-width',
    '0px',
  );
  await expect(daysSummary).toHaveText('Дни периода: 7');
  await expect(days).not.toHaveAttribute('open', '');
  await expect(daysSummary).toHaveAttribute('aria-expanded', 'false');
  if (process.env.CAPTURE_1051_EVIDENCE === '1') {
    const dir = resolve('..', 'docs/ux/issue-1051-progress-nutrition-cards-20261017/after');
    await mkdir(dir, { recursive: true });
    const originalViewport = page.viewportSize();
    await page.setViewportSize({ width: 393, height: 932 });
    for (const colorScheme of ['dark', 'light'] as const) {
      await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
      await targetHistory.screenshot({
        path: resolve(dir, `mobile-393-${colorScheme}-target-history-collapsed.png`),
      });
      await days.screenshot({
        path: resolve(dir, `mobile-393-${colorScheme}-days-collapsed.png`),
      });
    }
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
    if (originalViewport) await page.setViewportSize(originalViewport);
  }
  await daysSummary.focus();
  await page.keyboard.press('Enter');
  await expect(days).toHaveAttribute('open', '');
  await expect(daysSummary).toHaveAttribute('aria-expanded', 'true');
  await expect(report.getByText('Изменения цели в периоде')).toBeHidden();
  await targetHistorySummary.focus();
  await page.keyboard.press('Enter');
  await expect(targetHistory).toHaveAttribute('open', '');
  await expect(targetHistorySummary).toHaveAttribute('aria-expanded', 'true');
  await expect(report.getByText('Изменения цели в периоде')).toBeVisible();
  await expect(days).toHaveAttribute('open', '');
  await expect(daysSummary).toHaveAttribute('aria-expanded', 'true');
  await expect(
    report.getByRole('table', {
      name: 'Дневные КБЖУ, статус заполнения и действовавшая цель',
    }),
  ).toBeVisible();
  const dailyTable = report.getByRole('table', {
    name: 'Дневные КБЖУ, статус заполнения и действовавшая цель',
  });
  await expect(
    dailyTable.getByRole('cell', { name: 'Нет данных', exact: true }).first(),
  ).toBeVisible();
  await expect(dailyTable.getByRole('cell', { name: '0 ккал', exact: true }).first()).toBeVisible();

  for (const period of ['30 дней', '90 дней']) {
    await selector.getByRole('tab', { name: period }).click();
    await expect(selector.getByRole('tab', { name: period })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    const pointNavigation = report.getByRole('group', {
      name: 'Навигация по точкам графика',
    });
    await expect(pointNavigation).toBeVisible();
    const previousPointButton = pointNavigation.getByRole('button', {
      name: 'Предыдущая точка графика',
    });
    await expect(previousPointButton).toBeVisible();
    await expect
      .poll(async () => (await previousPointButton.boundingBox())?.height ?? 0)
      .toBeGreaterThanOrEqual(44);
    await expect(report.locator('.nutrition-report-days > summary')).toContainText(
      `Дни периода: ${period === '30 дней' ? '30' : '90'}`,
    );
    await expect(report.locator('.nutrition-report-days')).not.toHaveAttribute('open', '');
    if (process.env.CAPTURE_1051_EVIDENCE === '1' && period === '30 дней') {
      const dir = resolve('..', 'docs/ux/issue-1051-progress-nutrition-cards-20261017/after');
      const originalViewport = page.viewportSize();
      await page.setViewportSize({ width: 393, height: 932 });
      for (const colorScheme of ['dark', 'light'] as const) {
        await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
        await report.locator('.nutrition-report-days').screenshot({
          path: resolve(dir, `mobile-393-${colorScheme}-days30-collapsed.png`),
        });
      }
      await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
      if (originalViewport) await page.setViewportSize(originalViewport);
    }
  }
  await expect(page).toHaveURL(/progress_period=days_90/);
  await expect(report.getByText(/Заполнено \d+ из 90 дней/)).toBeVisible();

  await selector.getByRole('tab', { name: 'Свой период' }).click();
  await page.getByLabel('Начало периода').fill('2025-01-01');
  await page.getByLabel('Конец периода').fill('2025-12-31');
  await page.getByRole('button', { name: 'Показать период' }).click();
  await expect(page).toHaveURL(/progress_period=custom/);
  await expect(report.getByText(/Заполнено \d+ из 365 дней/)).toBeVisible();
  await expect(report.locator('.nutrition-report-days > summary')).toHaveText('Дни периода: 365');
  await expect(report.locator('.nutrition-report-days')).not.toHaveAttribute('open', '');
  const longRangeNavigation = report.getByRole('group', {
    name: 'Навигация по точкам графика',
  });
  await longRangeNavigation.focus();
  await page.keyboard.press('Home');
  const selectedDayLink = report.getByRole('link', { name: 'Открыть день' });
  await expect(selectedDayLink).toHaveAttribute('href', /date=2025-01-01/);
  await page.keyboard.press('ArrowRight');
  await expect(selectedDayLink).toHaveAttribute('href', /date=2025-01-07/);
  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
    expect((await longRangeNavigation.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    expect((await selectedDayLink.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  }
  await report.locator('.data-viz-chart').screenshot({
    path: '../.artifacts/screenshots/task-69b/data-dense-chart-mobile-web-light.png',
  });
  await page.setViewportSize({ width: 768, height: 900 });
  await report.screenshot({
    path: '../.artifacts/screenshots/task-57/tablet-768x900-light-long-range.png',
  });

  await selector.getByRole('tab', { name: '7 дней' }).click();
  const dayLink = report.getByRole('link', { name: 'Открыть день' });
  const reportUrl = page.url();
  await dayLink.click();
  await expect(page).toHaveURL(/section=nutrition&date=/);
  const returnTo = await page.evaluate(() => new URLSearchParams(location.search).get('return_to'));
  expect(returnTo).toBe(
    new URL(reportUrl).pathname + new URL(reportUrl).search + '#nutrition-period-report',
  );
  await expect(page.getByRole('heading', { name: 'Питание', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'К отчёту по питанию' }).click();
  await expect(page).toHaveURL(`${reportUrl}#nutrition-period-report`);
  await expect(selector.getByRole('tab', { name: '7 дней' })).toHaveAttribute(
    'aria-selected',
    'true',
  );

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1280, height: 900 },
    { width: 1024, height: 900 },
    { width: 430, height: 932 },
    { width: 390, height: 844 },
    { width: 360, height: 800 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
    const selectorTargets = await selector
      .getByRole('tab')
      .evaluateAll((tabs) => tabs.map((tab) => tab.getBoundingClientRect().height));
    expect(selectorTargets.every((height) => height >= 44)).toBe(true);
    if (viewport.width <= 430) {
      const selectorScroller = page.locator('.progress-period-controls__tabs');
      const selectorScrollState = await selectorScroller.evaluate((element) => {
        const style = getComputedStyle(element);
        return {
          clientWidth: element.clientWidth,
          overflowX: style.overflowX,
          scrollWidth: element.scrollWidth,
        };
      });
      expect(selectorScrollState.scrollWidth).toBeGreaterThanOrEqual(
        selectorScrollState.clientWidth,
      );
      expect(selectorScrollState.overflowX).toBe('auto');
    }
    const reportBox = await report.boundingBox();
    const categoryNavBox = await page.locator('.progress-category-nav').boundingBox();
    expect(reportBox).not.toBeNull();
    expect(categoryNavBox).not.toBeNull();
    expect(reportBox!.y).toBeGreaterThanOrEqual(categoryNavBox!.y);
    if (viewport.width === 1440) {
      expect(reportBox!.x).toBeGreaterThanOrEqual(24);
      expect(reportBox!.x + reportBox!.width).toBeLessThanOrEqual(viewport.width - 24);
      await report.evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await page.screenshot({
        path: '../.artifacts/screenshots/task-57/desktop-1440x900-light-report.png',
      });
      await page.screenshot({
        path: '../.artifacts/screenshots/task-69b/desktop-1440x900-light-overview.png',
      });
      await report.screenshot({
        path: '../.artifacts/screenshots/task-57/desktop-1440x900-light-partial.png',
      });
      await report.locator('.data-viz-chart').screenshot({
        path: '../.artifacts/screenshots/task-69b/data-dense-chart-desktop-light.png',
      });
    }
    if (viewport.width === 360) {
      const pointStyle = await report
        .locator('.data-viz-chart__point-ring')
        .first()
        .evaluate((point) => {
          const style = getComputedStyle(point);
          return { fill: style.fill, stroke: style.stroke };
        });
      expect(pointStyle.fill).not.toBe(pointStyle.stroke);
      expect(
        (await report.getByRole('img', { name: /Калории по дням/ }).boundingBox())?.height,
      ).toBeGreaterThanOrEqual(180);
      const pointTargets = await report
        .locator('.data-viz-chart__point-navigation button')
        .evaluateAll((buttons) =>
          buttons.map((button) => {
            const box = button.getBoundingClientRect();
            return { width: box.width, height: box.height };
          }),
        );
      expect(pointTargets.length).toBeGreaterThan(0);
      expect(
        Math.min(...pointTargets.map((box) => Math.min(box.width, box.height))),
      ).toBeGreaterThanOrEqual(44);
      await report.evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await page.screenshot({
        path: '../.artifacts/screenshots/task-69b/mobile-web-360x800-light-compact.png',
      });
      await report.screenshot({
        path: '../.artifacts/screenshots/task-69b/mobile-web-360x800-light-report.png',
      });
    }
  }
});

for (const width of [320, 360, 390, 393, 430]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`#970 target changes stay readable at ${width}px ${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 932 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await mockProgress(page, 'long');
      await page.goto('/app?section=progress&progress_period=days_30');
      await page.getByRole('button', { name: 'Клиент' }).click();
      await page
        .getByRole('navigation', { name: 'Основная навигация' })
        .getByRole('link', { name: 'Прогресс' })
        .click();
      await page
        .getByRole('navigation', { name: 'Разделы прогресса' })
        .getByRole('tab', { name: /^Питание/ })
        .click();

      const report = page.locator('#nutrition-period-report');
      const history = report.locator('.nutrition-report-target-history');
      const historyStyle = await history.evaluate((element) => {
        const style = getComputedStyle(element);
        return {
          borderWidths: [
            style.borderTopWidth,
            style.borderRightWidth,
            style.borderBottomWidth,
            style.borderLeftWidth,
          ],
          borderRadius: style.borderRadius,
        };
      });
      expect(historyStyle.borderWidths).toEqual(['1px', '1px', '1px', '1px']);
      expect(Number.parseFloat(historyStyle.borderRadius)).toBeGreaterThan(0);
      await history.locator(':scope > summary').press('Enter');
      const targetChanges = report
        .locator('.nutrition-report-targets')
        .filter({ hasText: 'Изменения цели в периоде' });
      await expect(targetChanges).toBeVisible();
      const cards = targetChanges.locator('ol > li');
      await expect(cards).toHaveCount(2);
      await expect(cards.first().getByText('Принятая адаптация', { exact: true })).toBeVisible();
      await expect(cards.last().getByText('Цель тренера', { exact: true })).toBeVisible();
      for (const card of await cards.all()) {
        for (const label of ['Дата', 'Источник', 'Калории', 'Б / Ж / У']) {
          await expect(card.getByText(label, { exact: true })).toBeVisible();
        }
      }

      // Layout stress only: keep valid API enums and model a longer localized label in the DOM.
      const source = cards.first().locator('.nutrition-report-targets__content--source');
      await source.evaluate((element) => {
        element.textContent = 'Принятая адаптация по согласованному индивидуальному плану питания';
      });
      await expect(source).toContainText('индивидуальному плану питания');

      const geometry = await targetChanges.evaluate((element) => {
        const viewport = document.documentElement.clientWidth;
        const heading = element.querySelector<HTMLElement>('h3');
        const list = element.querySelector<HTMLElement>('ol');
        const firstCard = element.querySelector<HTMLElement>('ol > li');
        const secondCard = element.querySelector<HTMLElement>('ol > li:nth-child(2)');
        if (!heading || !list || !firstCard || !secondCard)
          throw new Error('Target changes geometry is incomplete');
        const headingBox = heading.getBoundingClientRect();
        const firstCardBox = firstCard.getBoundingClientRect();
        const secondCardBox = secondCard.getBoundingClientRect();
        const rowGap = Number.parseFloat(getComputedStyle(element).rowGap);
        const listStyle = getComputedStyle(list);
        return {
          viewport,
          documentWidth: document.documentElement.scrollWidth,
          rowGap,
          headingToFirstCard: firstCardBox.top - headingBox.bottom,
          cardRowGap: Number.parseFloat(listStyle.rowGap),
          firstToSecondCard: secondCardBox.top - firstCardBox.bottom,
          listBorderWidths: [
            listStyle.borderTopWidth,
            listStyle.borderRightWidth,
            listStyle.borderBottomWidth,
            listStyle.borderLeftWidth,
          ],
          cards: [...element.querySelectorAll<HTMLElement>('ol > li')].map((cardElement) => {
            const box = cardElement.getBoundingClientRect();
            const descendants = [...cardElement.querySelectorAll<HTMLElement>('*')].map((child) => {
              const childBox = child.getBoundingClientRect();
              return { left: childBox.left, right: childBox.right };
            });
            return {
              left: box.left,
              right: box.right,
              width: box.width,
              borderWidths: [
                getComputedStyle(cardElement).borderTopWidth,
                getComputedStyle(cardElement).borderRightWidth,
                getComputedStyle(cardElement).borderBottomWidth,
                getComputedStyle(cardElement).borderLeftWidth,
              ],
              borderRadius: getComputedStyle(cardElement).borderRadius,
              descendants,
            };
          }),
        };
      });
      expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewport);
      expect(geometry.rowGap).toBeGreaterThanOrEqual(12);
      expect(geometry.headingToFirstCard).toBeGreaterThanOrEqual(geometry.rowGap - 0.5);
      expect(geometry.firstToSecondCard).toBeGreaterThanOrEqual(0);
      expect(geometry.cardRowGap).toBe(0);
      expect(geometry.firstToSecondCard).toBeCloseTo(geometry.cardRowGap, 1);
      expect(geometry.listBorderWidths).toEqual(['0px', '0px', '0px', '0px']);
      for (const [index, card] of geometry.cards.entries()) {
        expect(card.width).toBeGreaterThan(0);
        expect(card.left).toBeGreaterThanOrEqual(-1);
        expect(card.right).toBeLessThanOrEqual(geometry.viewport + 1);
        expect(card.borderWidths).toEqual(
          index === 0 ? ['0px', '0px', '0px', '0px'] : ['1px', '0px', '0px', '0px'],
        );
        expect(card.borderRadius).toBe('0px');
        for (const child of card.descendants) {
          expect(child.left).toBeGreaterThanOrEqual(card.left - 1);
          expect(child.right).toBeLessThanOrEqual(card.right + 1);
        }
      }

      if (CAPTURE_970_AFTER) {
        await mkdir(ISSUE_970_AFTER_DIR, { recursive: true });
        await targetChanges.screenshot({
          path: resolve(ISSUE_970_AFTER_DIR, `${testInfo.project.name}-${theme}-${width}.png`),
        });
        await writeFile(
          resolve(ISSUE_970_AFTER_DIR, `${testInfo.project.name}-${theme}-${width}-geometry.json`),
          JSON.stringify(
            { browser: testInfo.project.name, theme, width, height: 932, geometry },
            null,
            2,
          ) + '\n',
        );
      }

      if (width === 390) {
        const list = targetChanges.locator('ol');
        await page.emulateMedia({ media: 'print' });
        await expect(list).toHaveCSS('row-gap', 'normal');
        await expect(list).toHaveCSS('border-top-width', '1px');
        await page.emulateMedia({ media: 'screen' });
        await page.setViewportSize({ width: 1280, height: 932 });
        await expect(list).toHaveCSS('row-gap', 'normal');
        await expect(list).toHaveCSS('border-top-width', '1px');
        await expect(report.locator('.nutrition-report-days table')).toHaveCSS('display', 'table');
      }
    });
  }
}

test('nutrition report no-data state keeps missing days distinct from zero', async ({ page }) => {
  await page.setViewportSize({ width: 430, height: 932 });
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await mockProgress(page, 'no-data');
  await page.goto('/app?section=progress&progress_period=days_30');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Питание/ })
    .click();

  const report = page.locator('#nutrition-period-report');
  await expect(report.getByText('Заполнено 0 из 30 дней')).toBeVisible();
  await expect(report.getByText('Нет заполненных дней за период')).toBeVisible();
  await expect(report.getByRole('link', { name: 'Открыть дневник питания' })).toHaveAttribute(
    'href',
    '/app?section=nutrition',
  );
  await expect(report.getByRole('img')).not.toBeAttached();
  await expect(report.getByText('0 ккал', { exact: true })).not.toBeAttached();
  const targetHistory = report.locator('.nutrition-report-target-history');
  const targetHistorySummary = targetHistory.locator(':scope > summary');
  await expect(targetHistory).not.toHaveAttribute('open', '');
  await expect(targetHistorySummary).toHaveAttribute('aria-expanded', 'false');
  await targetHistorySummary.press('Enter');
  await expect(
    report.getByText('За выбранный период изменений целей питания не было.'),
  ).toBeVisible();
  await expect(targetHistorySummary).toHaveAttribute('aria-expanded', 'true');
  const days = report.locator('.nutrition-report-days');
  await expect(days).not.toHaveAttribute('open', '');
  await expect(days.locator(':scope > summary')).toHaveAttribute('aria-expanded', 'false');
  await report.screenshot({
    path: '../.artifacts/screenshots/task-69b/sparse-insufficient-mobile-light.png',
  });
});

test('nutrition separates confirmed day statuses from filled report days', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await mockProgress(page);
  await page.goto('/app?section=progress&progress_view=nutrition');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();
  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Питание/ })
    .click();

  const nutrition = page.locator('#progress-nutrition');
  await expect(
    nutrition.getByText('18 из 30 дней отмечены завершёнными или без приёмов пищи'),
  ).toBeVisible();
  await expect(nutrition.getByText('Дни с данными для средних')).toBeVisible();
  await expect(nutrition.getByText('9 дней', { exact: true })).toBeVisible();
  await expect(
    page.locator('#nutrition-period-report').getByText('Заполнено 9 из 30 дней'),
  ).toBeVisible();
});

test('cardio rows match the requested period source and summary count', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await mockProgress(page);
  await page.goto('/app?section=progress&progress_view=overview');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  const cardioRequest = page.waitForRequest(
    (request) => request.url().includes('/workouts/cardio?') && request.method() === 'GET',
  );
  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^Кардио/ })
    .click();
  const request = await cardioRequest;
  const cardioUrl = new URL(request.url());
  expect(cardioUrl.searchParams.get('date_from')).toBeTruthy();
  expect(cardioUrl.searchParams.get('date_to')).toBeTruthy();

  const cardio = page.locator('#progress-cardio');
  await expect(cardio.getByText('3 завершено', { exact: true })).toBeVisible();
  await expect(cardio.locator('.cardio-session-row')).toHaveCount(3);
  await expect(cardio.getByText('Кардио пока не записано')).toHaveCount(0);
  await expect(cardio.getByText('Ходьба')).toBeVisible();
  await expect(cardio.getByText('Бег')).toBeVisible();
  await expect(cardio.getByText('Велосипед')).toBeVisible();
});

test('history keeps two workout records, totals and navigation separate', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await mockProgress(page);
  await page.goto('/app?section=progress&progress_view=history');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();
  await page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^История/ })
    .click();

  const history = page.locator('.workout-history-card');
  await expect(history.getByText('2', { exact: true }).first()).toBeVisible();
  await expect(history.getByText('9', { exact: true }).first()).toBeVisible();
  await expect(history.getByText('3210 кг', { exact: true })).toBeVisible();
  const first = page.locator('#workout-history-43');
  const second = page.locator('#workout-history-44');
  await expect(first).toContainText('Ноги и корпус');
  await expect(first).toContainText('Присед со штангой');
  await expect(first).not.toContainText('Грудь и спина');
  await expect(second).toContainText('Грудь и спина');
  await expect(second).toContainText('Жим гантелей лёжа');
  await expect(second).not.toContainText('Присед со штангой');

  const week = page.locator('.progress-history-week');
  await week.locator(':scope > summary').press('Enter');
  await week.getByRole('link', { name: /Открыть тренировочный день: Ноги и корпус/ }).click();
  await expect(page).toHaveURL(/#workout-history-43$/);
  await page.goBack();
  await expect(first).toBeVisible();
  await expect(second).toBeVisible();

  const clearHistory = history.getByRole('button', { name: 'Очистить историю' });
  await expect(clearHistory).toHaveClass(/secondary/);
  await clearHistory.click();
  await expect(page.getByRole('dialog', { name: 'Очистить историю?' })).toBeVisible();
  await page.getByRole('button', { name: 'Отмена' }).click();
  await expect(first).toBeVisible();
});

test('notification deep-link opens exact workout feedback and preserves back navigation', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockProgress(page);

  await page.goto('/app?section=today');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await expect(page.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  await page.goto('/app?workout_id=43&comment_id=7&workout_exercise_id=55');

  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();
  const historyCard = page.locator('.workout-history-card');
  await expect(historyCard).toHaveAttribute('open', '');
  const feedbackDisclosure = page.locator('#workout-history-43 .workout-feedback-disclosure');
  await expect(feedbackDisclosure).toHaveAttribute('open', '');
  await expect(feedbackDisclosure.locator('.workout-feedback__body')).toContainText(
    'Держите колени по направлению носков.',
  );
  await expect(page.locator('#workout-comment-7')).toHaveClass(/is-focused/);
  await expect(page.locator('#workout-comment-7')).toHaveCount(1);
  await expect(feedbackDisclosure.getByText('Упражнение · Присед со штангой')).toBeVisible();
  await expect(feedbackDisclosure.getByText('Изменено')).toBeVisible();
  await expect(page.locator('.workout-feedback script')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  const clearHistory = historyCard.getByRole('button', { name: 'Очистить историю' });
  const clearHistoryBox = await clearHistory.boundingBox();
  const historyFeedbackBox = await historyCard.locator('.workout-feedback').boundingBox();
  expect(clearHistoryBox?.y ?? 0).toBeGreaterThan(
    (historyFeedbackBox?.y ?? 0) + (historyFeedbackBox?.height ?? 0),
  );
  expect(clearHistoryBox?.height).toBeGreaterThanOrEqual(44);
  await clearHistory.click();
  await expect(page.getByRole('dialog', { name: 'Очистить историю?' })).toBeVisible();
  await page.getByRole('button', { name: 'Отмена' }).click();
  await expect(historyCard).toHaveAttribute('open', '');
  const historyMetricBoxes = await historyCard
    .locator('.workout-history__metrics .metric')
    .evaluateAll((metrics) => metrics.map((metric) => metric.getBoundingClientRect()));
  expect(historyMetricBoxes).toHaveLength(3);
  expect(
    Math.max(...historyMetricBoxes.map((box) => box.top)) -
      Math.min(...historyMetricBoxes.map((box) => box.top)),
  ).toBeLessThan(2);
  expect(historyMetricBoxes.every((box) => box.width >= 90)).toBe(true);

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 430, height: 932 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
    const metricBoxes = await historyCard
      .locator('.workout-history__metrics .metric')
      .evaluateAll((metrics) => metrics.map((metric) => metric.getBoundingClientRect()));
    expect(
      Math.max(...metricBoxes.map((box) => box.top)) -
        Math.min(...metricBoxes.map((box) => box.top)),
    ).toBeLessThan(2);
  }
  const historyRowBox = await page.locator('#workout-history-43').boundingBox();
  const feedbackBox = await page
    .locator('#workout-history-43 .workout-feedback-disclosure')
    .boundingBox();
  expect(historyRowBox).not.toBeNull();
  expect(feedbackBox).not.toBeNull();
  expect(feedbackBox!.x).toBeGreaterThanOrEqual(historyRowBox!.x);
  expect(feedbackBox!.x + feedbackBox!.width).toBeLessThanOrEqual(
    historyRowBox!.x + historyRowBox!.width + 1,
  );

  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('.workout-feedback').first()).toHaveCSS('color', 'rgb(245, 245, 245)');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

  if (captureFeedbackAudit) {
    await page.screenshot({
      path: '../.artifacts/ui-audit/task-49/client-feedback-mobile-dark.png',
      fullPage: true,
    });
  }

  await page.goBack();
  await expect(page).toHaveURL(/\/app(?:\?section=today)?$/);
  await expect(page.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
});

test('dark progress keeps the compact overview readable', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  await expect(progressOverview(page)).toBeVisible();
  await expect(page.getByText('84%', { exact: true })).toBeVisible();
  await expect(page.locator('.progress-overview__metric')).toHaveCount(4);
  await expect(page.locator('.progress-overview__adherence')).toHaveCount(1);
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(page.locator('.progress-bento__adherence')).toHaveCount(0);
});

test('light progress keeps the compact overview readable', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  await expect(progressOverview(page)).toBeVisible();
  await expect(page.getByText('84%', { exact: true })).toBeVisible();
  await expect(page.locator('.progress-overview__metric')).toHaveCount(4);
  await expect(page.locator('.progress-overview__adherence')).toHaveCount(1);
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
  await expect(page.locator('.progress-bento__adherence')).toHaveCount(0);
});

for (const theme of ['light', 'dark'] as const) {
  for (const width of [320, 360, 393, 430, 1440]) {
    test(`#1052 compact cardio cards stay usable at ${width}px ${theme}`, async ({ page }) => {
      await page.setViewportSize({
        width,
        height: width >= 1000 ? 900 : width === 430 ? 932 : 844,
      });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((selectedTheme) => {
        localStorage.setItem('app-theme', selectedTheme);
      }, theme);
      await installPlatformApi(page, {
        browserSession: true,
        cardioState: 'many',
        fixedDate: '2030-01-30',
      });
      await page.goto('/app?section=progress&progress_period=days_30');

      const cardioTab = page
        .getByRole('navigation', { name: 'Разделы прогресса' })
        .getByRole('tab', { name: /^Кардио/ });
      await cardioTab.click();

      const history = page.locator('#progress-cardio');
      await expect(history).toBeVisible();
      const rows = history.locator('.cardio-session-row');
      await expect(rows).toHaveCount(3);
      if (process.env.CAPTURE_1052_SCREENSHOTS === '1' && [393, 1440].includes(width)) {
        const captureTarget = rows.first();
        await captureTarget.scrollIntoViewIfNeeded();
        await captureTarget.screenshot({
          path: resolve(
            WORKTREE_ROOT,
            'docs',
            'ux',
            'issue-1052-compact-cardio-session-cards',
            'evidence',
            `${process.env.CAPTURE_1052_PHASE ?? 'capture'}-${theme}-${width}.png`,
          ),
        });
      }

      const cards = history.locator('.cardio-session-row--compact');
      await expect(cards).toHaveCount(3);
      await expect(cards.first()).toHaveCSS('border-top-width', '1px');
      expect(
        await cards.first().evaluate((element) => getComputedStyle(element).borderRadius),
      ).not.toBe('0px');

      const noMetrics = cards.filter({ hasText: 'Эллиптический тренажёр' });
      await expect(noMetrics).toContainText('40 мин');
      await expect(noMetrics.getByText(/Средний пульс/)).toHaveCount(0);
      await expect(noMetrics.getByText(/уд\/мин/)).toHaveCount(0);

      const withMetrics = cards.filter({ hasText: 'Велотренажёр / велоэргометр' });
      await expect(withMetrics).toContainText('136 уд/мин');
      await withMetrics.getByText('Дополнительные показатели').click();
      await expect(withMetrics).toContainText('8,1 км');
      await withMetrics.getByText('Действия с записью').click();
      await expect(withMetrics.getByRole('button', { name: 'Изменить' })).toBeVisible();
      await expectTouchTargets(withMetrics.locator('.cardio-session-row__menu > summary'));

      await expectNoHorizontalOverflow(page);
      if (width <= 430) {
        await withMetrics.scrollIntoViewIfNeeded();
        const dock = page.locator('#appBottomNav');
        await expect(dock).toBeVisible();
        await expectNoOverlap(withMetrics, dock);
      }
    });
  }
}

test('reduced-motion duration matcher follows the CSS time contract', () => {
  for (const value of ['0s', '1e-05s', '0.01ms', '0s, 0.01ms']) {
    expect(hasOnlyReducedMotionDurations(value)).toBe(true);
  }
  for (const value of ['150ms', '0s, 150ms', '0.01px', 'invalid']) {
    expect(hasOnlyReducedMotionDurations(value)).toBe(false);
  }
});

test('canonical charts and icons remain operable in forced colors and reduced motion', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  expect(
    await page.evaluate(() => ({
      forcedColors: matchMedia('(forced-colors: active)').matches,
      reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
    })),
  ).toEqual({ forcedColors: true, reducedMotion: true });
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();

  const chart = page.locator('.data-viz-chart').first();
  await expect(chart.getByRole('img')).toBeVisible();
  await expect(chart.getByRole('group', { name: 'Навигация по точкам графика' })).toBeVisible();
  await chart.getByRole('group', { name: 'Навигация по точкам графика' }).focus();
  await page.keyboard.press('Home');
  await expect(chart.locator('.data-viz-chart__selection')).toBeVisible();
  await expect(
    page
      .getByRole('navigation', { name: 'Основная навигация' })
      .getByRole('link', { name: 'Прогресс' })
      .locator('[data-icon="nav-progress"]'),
  ).toBeVisible();
  expect(
    await chart
      .locator('.data-viz-chart__actual')
      .first()
      .evaluate((line) => getComputedStyle(line).stroke),
  ).not.toBe('none');
  const transitionDuration = await chart
    .locator('.data-viz-chart__point-ring')
    .first()
    .evaluate((point) => getComputedStyle(point).transitionDuration);
  expect(hasOnlyReducedMotionDurations(transitionDuration)).toBe(true);
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    )
    .toBe(true);
});

test('exercise catalogue uses the selected folder and dumbbell glyph on desktop and mobile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await mockProgress(page);
  await page.goto('/app?section=progress');
  await page.getByRole('button', { name: 'Клиент' }).click();

  const desktopCatalogue = page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Упражнения' });
  const desktopIcon = desktopCatalogue.locator('[data-icon="nav-exercise-catalog"]');
  await expect(desktopIcon).toBeVisible();
  expect((await desktopIcon.boundingBox())?.width).toBeGreaterThanOrEqual(16);
  await desktopCatalogue.screenshot({
    path: '../.artifacts/screenshots/task-69b/exercise-catalog-desktop-light.png',
  });

  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  const morePanel = page.getByRole('dialog');
  const mobileCatalogue = morePanel.getByRole('link', { name: 'Упражнения' });
  await expect(mobileCatalogue.locator('[data-icon="nav-exercise-catalog"]')).toBeVisible();
  await morePanel.screenshot({
    path: '../.artifacts/screenshots/task-69b/exercise-catalog-mobile-dark.png',
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test('progress overview keeps matching light and dark visual forms for the same data', async ({
  browser,
  baseURL,
}) => {
  test.setTimeout(120_000);
  const surfaces = [
    { name: 'desktop-1440x900', width: 1440, height: 900 },
    { name: 'tablet-768x900', width: 768, height: 900 },
    { name: 'mobile-390x844', width: 390, height: 844 },
  ];

  for (const surface of surfaces) {
    for (const theme of ['light', 'dark'] as const) {
      const context = await browser.newContext({
        baseURL,
        colorScheme: theme,
        viewport: { width: 1440, height: 900 },
      });
      await context.addInitScript((selectedTheme) => {
        localStorage.setItem('app-theme', selectedTheme);
      }, theme);
      await context.addInitScript(() => {
        const RealDate = globalThis.Date;
        const fixedNow = RealDate.parse('2030-01-30T12:00:00Z');
        globalThis.Date = class extends RealDate {
          constructor(value?: string | number | Date) {
            super(value ?? fixedNow);
          }

          static now() {
            return fixedNow;
          }
        } as DateConstructor;
      });
      const page = await context.newPage();
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await mockProgress(page);
      await page.goto('/app?section=progress&progress_period=days_30');
      await page.getByRole('button', { name: 'Клиент' }).click();
      await page
        .getByRole('navigation', { name: 'Основная навигация' })
        .getByRole('link', { name: 'Прогресс' })
        .click();
      await page.locator('.progress-period-controls').getByRole('tab', { name: '30 дней' }).click();
      await page.setViewportSize({ width: surface.width, height: surface.height });

      await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();
      await expect(progressOverview(page)).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
      await expect(
        page.locator('.progress-period-controls').getByRole('tab', { name: '30 дней' }),
      ).toHaveAttribute('aria-selected', 'true');
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(surface.width);
      await page.screenshot({
        path: resolve(TASK_111_SCREENSHOTS, `progress-overview-${surface.name}-${theme}.png`),
      });
      await context.close();
    }
  }
});

test('progress period controls drive one exact URL and API range through history', async ({
  page,
}) => {
  await page.setViewportSize({ width: 430, height: 932 });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await mockProgress(page);
  const requests: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (/\/workouts\/progress\/(summary|training-analytics|nutrition-report)$/.test(url.pathname)) {
      requests.push(`${url.pathname}${url.search}`);
    }
  });

  await page.goto('/app?section=progress&progress_period=days_30');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page
    .getByRole('navigation', { name: 'Основная навигация' })
    .getByRole('link', { name: 'Прогресс' })
    .click();
  const controls = page.locator('.progress-period-controls');
  await expect(controls.getByRole('tab')).toHaveCount(4);
  await controls.getByRole('tab', { name: '30 дней' }).click();
  await expect(progressOverview(page)).toBeVisible();

  for (const period of [7, 30, 90] as const) {
    const label = `${period} дней`;
    await controls.getByRole('tab', { name: label }).click();
    await expect(page).toHaveURL(new RegExp(`progress_period=days_${period}(?:&|$)`));
    await expect(controls.getByRole('tab', { name: label })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await expect(progressOverview(page)).toBeVisible();
  }

  await controls.getByRole('tab', { name: 'Свой период' }).click();
  await page.getByLabel('Начало периода').fill('2025-01-01');
  await page.getByLabel('Конец периода').fill('2025-01-30');
  await page.getByRole('button', { name: 'Показать период' }).click();
  await expect(page).toHaveURL(/progress_period=custom/);
  await expect(page).toHaveURL(/progress_from=2025-01-01/);
  await expect(page).toHaveURL(/progress_to=2025-01-30/);
  expect(requests.some((request) => request.includes('date_from=2025-01-01'))).toBe(true);
  expect(requests.some((request) => request.includes('date_to=2025-01-30'))).toBe(true);

  await page.goBack();
  await expect(page).toHaveURL(/progress_period=days_90/);
  await page.goForward();
  await expect(page).toHaveURL(/progress_period=custom/);
  await expect(progressOverview(page)).toBeVisible();
});

test('progress header keeps the title row separate from period and report controls', async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await mockProgress(page);
  await page.goto('/app?section=progress&progress_period=days_30');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();

  for (const theme of ['light', 'dark'] as const) {
    if (theme === 'dark') {
      await page.evaluate(() => {
        localStorage.setItem('app-theme', 'dark');
        window.dispatchEvent(new CustomEvent('yfc-theme-preference-change'));
      });
    }
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);

    for (const width of [320, 360, 393, 430, 1280, 1440, 1920, 2560]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
      const help = page.locator('.progress-hero__help summary');
      const report = page.getByRole('link', { name: 'Скачать отчёт' });
      const period = page.locator('.progress-hero__period');
      const tabs = period.getByRole('tablist', { name: 'Период прогресса' });

      await expect(help).toBeVisible();
      await expect(report).toBeVisible();
      await expect(tabs.getByRole('tab')).toHaveCount(4);
      await expect(page.locator('.progress-hero')).toHaveCSS('border-bottom-width', '0px');
      const selectorGeometry = await tabs.evaluate((element) => {
        const tabStyle = getComputedStyle(element);
        const wrapperStyle = getComputedStyle(element.parentElement!);
        return {
          radius: tabStyle.borderTopLeftRadius,
          overflowX: wrapperStyle.overflowX,
          overflowY: wrapperStyle.overflowY,
        };
      });
      expect(selectorGeometry.radius).not.toBe('0px');
      expect(selectorGeometry.overflowX).toBe('auto');
      expect(selectorGeometry.overflowY).toBe('hidden');
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);

      const helpGeometry = await help.evaluate((summary) => {
        const textNode = Array.from(summary.childNodes).find(
          (node) => node.nodeType === Node.TEXT_NODE,
        );
        const range = document.createRange();
        if (textNode) range.selectNodeContents(textNode);
        const textRects = textNode ? Array.from(range.getClientRects()) : [];
        const summaryBox = summary.getBoundingClientRect();
        const summaryStyle = getComputedStyle(summary);
        return {
          textRectCount: textRects.length,
          textWidths: textRects.map((rect) => Math.round(rect.width * 100) / 100),
          height: summaryBox.height,
          width: summaryBox.width,
          x: summaryBox.x,
          right: summaryBox.right,
          top: summaryBox.top,
          bottom: summaryBox.bottom,
          viewportWidth: window.innerWidth,
          minHeight: parseFloat(summaryStyle.minHeight),
        };
      });
      const boxes = await page.evaluate(() => {
        const rect = (selector: string) => {
          const element = document.querySelector<HTMLElement>(selector);
          if (!element) return null;
          const value = element.getBoundingClientRect();
          return {
            bottom: value.bottom,
            left: value.left,
            right: value.right,
            top: value.top,
          };
        };
        return {
          heading: rect('.progress-hero__heading'),
          title: rect('.progress-hero__copy h1'),
          help: rect('.progress-hero__help summary'),
          report: rect('.progress-hero__download'),
          period: rect('.progress-hero__period'),
        };
      });
      expect(boxes.heading).not.toBeNull();
      expect(boxes.title).not.toBeNull();
      expect(boxes.help).not.toBeNull();
      expect(boxes.report).not.toBeNull();
      expect(boxes.period).not.toBeNull();
      expect(helpGeometry.top).toBeLessThan(boxes.title!.bottom);
      expect(helpGeometry.bottom).toBeGreaterThan(boxes.title!.top);
      expect(boxes.help!.right).toBeLessThanOrEqual(boxes.heading!.right + 0.5);
      if (width <= 430) {
        expect(boxes.period!.left).toBeGreaterThanOrEqual(boxes.heading!.left - 0.5);
        expect(boxes.period!.right).toBeLessThanOrEqual(boxes.heading!.right + 0.5);
        expect(boxes.period!.top).toBeGreaterThanOrEqual(boxes.heading!.bottom - 1);
        expect(boxes.report!.left).toBeGreaterThanOrEqual(boxes.period!.left);
        expect(boxes.report!.top).toBeGreaterThanOrEqual(boxes.period!.bottom - 1);
        expect(
          helpGeometry.textRectCount,
          `wrapped at ${width}px: ${JSON.stringify(helpGeometry)}`,
        ).toBe(1);
        expect(helpGeometry.height, `touch target at ${width}px`).toBeGreaterThanOrEqual(44);
        expect(helpGeometry.right, `overflow at ${width}px`).toBeLessThanOrEqual(
          helpGeometry.viewportWidth,
        );
      }
      if (width >= 1280) {
        expect(boxes.period!.left).toBeGreaterThanOrEqual(boxes.heading!.right + 1);
        expect(boxes.help!.right).toBeLessThan(boxes.period!.left);
        expect(boxes.report!.left).toBeGreaterThanOrEqual(boxes.period!.left);
        expect(boxes.report!.top).toBeGreaterThanOrEqual(boxes.period!.bottom - 1);
      }
    }
  }
});

test('progress header keeps expanded help and custom period in normal flow', async ({ page }) => {
  test.setTimeout(120_000);
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await mockProgress(page);
  await page.goto('/app?section=progress&progress_period=days_30');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();

  const captureDirectory = CAPTURE_PROGRESS_865
    ? resolve(
        process.cwd(),
        '..',
        'docs',
        'ux',
        'final-issues-acceptance',
        'evidence',
        '865',
        CAPTURE_PROGRESS_865,
      )
    : null;

  for (const theme of ['light', 'dark'] as const) {
    if (theme === 'dark') {
      await page.evaluate(() => {
        localStorage.setItem('app-theme', 'dark');
        window.dispatchEvent(new CustomEvent('yfc-theme-preference-change'));
      });
    }
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);

    for (const width of [320, 360, 390, 393, 430, 1280, 1440, 1920, 2560]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
      const summary = page.locator('.progress-hero__help summary');
      const helpBody = page.locator('.progress-hero__help .contextual-help__body');
      const period = page.locator('.progress-hero__period');
      const customTab = period.getByRole('tab', { name: 'Свой период' });
      const customForm = period.locator('.progress-period-controls__custom');

      await expect(summary).toHaveAttribute('aria-expanded', 'false');
      await expect(customForm).toBeHidden();

      const measureGeometry = async () =>
        page.evaluate(() => {
          type Box = { bottom: number; left: number; right: number; top: number; width: number };
          const box = (selector: string): Box | null => {
            const element = document.querySelector<HTMLElement>(selector);
            if (!element) return null;
            const rect = element.getBoundingClientRect();
            return {
              top: rect.top,
              right: rect.right,
              bottom: rect.bottom,
              left: rect.left,
              width: rect.width,
            };
          };
          const boxes = {
            heading: box('.progress-hero__copy h1'),
            headingRegion: box('.progress-hero__heading'),
            summary: box('.progress-hero__help summary'),
            helpBody: box('.progress-hero__help .contextual-help__body'),
            period: box('.progress-hero__period'),
            custom: box('.progress-period-controls__custom'),
            from: box('#progress-period-from'),
            to: box('#progress-period-to'),
            actions: box('.progress-period-controls__custom-actions'),
            download: box('.progress-hero__download'),
          };
          const overlaps = (left: Box | null, right: Box | null) =>
            Boolean(
              left &&
              right &&
              left.left < right.right &&
              left.right > right.left &&
              left.top < right.bottom &&
              left.bottom > right.top,
            );
          const topLevel = ['heading', 'summary', 'period', 'download'] as const;
          const internal = ['from', 'to', 'actions'] as const;
          const overlapPairs = [
            ...topLevel.flatMap((left, index) =>
              topLevel.slice(index + 1).map((right) => `${left}:${right}`),
            ),
            ...internal.flatMap((left, index) =>
              internal.slice(index + 1).map((right) => `${left}:${right}`),
            ),
            'helpBody:period',
            'helpBody:custom',
            'helpBody:download',
          ] as const;
          const outOfViewport = Object.entries(boxes)
            .filter(([, value]) => value)
            .filter(([, value]) => value!.left < -0.5 || value!.right > window.innerWidth + 0.5)
            .map(([name]) => name);
          return {
            boxes,
            overlapPairs: overlapPairs.filter((pair) => {
              const [left, right] = pair.split(':') as [keyof typeof boxes, keyof typeof boxes];
              return overlaps(boxes[left], boxes[right]);
            }),
            outOfViewport,
            scrollWidth: document.documentElement.scrollWidth,
            viewportWidth: window.innerWidth,
          };
        });

      const assertGeometry = async (state: string) => {
        const geometry = await measureGeometry();
        expect(
          geometry.overlapPairs,
          `${theme} ${width}px ${state}: ${JSON.stringify(geometry)}`,
        ).toEqual([]);
        expect(geometry.outOfViewport, `${theme} ${width}px ${state}`).toEqual([]);
        expect(geometry.scrollWidth, `${theme} ${width}px ${state}`).toBeLessThanOrEqual(
          geometry.viewportWidth,
        );
        const headingRegionBox = geometry.boxes.headingRegion;
        const headingBox = geometry.boxes.heading;
        const summaryBox = geometry.boxes.summary;
        expect(headingRegionBox).not.toBeNull();
        expect(headingBox).not.toBeNull();
        expect(summaryBox).not.toBeNull();
        expect(
          summaryBox!.top,
          `${theme} ${width}px ${state}: ${JSON.stringify(geometry)}`,
        ).toBeLessThan(headingBox!.bottom);
        expect(
          summaryBox!.bottom,
          `${theme} ${width}px ${state}: ${JSON.stringify(geometry)}`,
        ).toBeGreaterThan(headingBox!.top);
        if (width >= 1280) {
          const customTabText = await customTab.evaluate((tab) => {
            const range = document.createRange();
            range.selectNodeContents(tab);
            const box = tab.getBoundingClientRect();
            return {
              clientWidth: tab.clientWidth,
              height: box.height,
              scrollWidth: tab.scrollWidth,
              textRectCount: range.getClientRects().length,
            };
          });
          expect(
            customTabText.textRectCount,
            `${theme} ${width}px ${state}: custom period label wrapped unexpectedly`,
          ).toBe(1);
          expect(customTabText.scrollWidth).toBeLessThanOrEqual(customTabText.clientWidth);
        }
        if (state.includes('help')) {
          const helpBodyBox = geometry.boxes.helpBody;
          expect(helpBodyBox, `${theme} ${width}px ${state} help body`).not.toBeNull();
          expect(helpBodyBox!.left).toBeGreaterThanOrEqual(headingRegionBox!.left - 0.5);
          expect(helpBodyBox!.right).toBeLessThanOrEqual(headingRegionBox!.right + 0.5);
          expect(
            helpBodyBox!.top,
            `${theme} ${width}px ${state}: ${JSON.stringify(geometry)}`,
          ).toBeGreaterThanOrEqual(Math.max(headingBox!.bottom, summaryBox!.bottom) - 0.5);
        }
        if (state.includes('custom')) {
          expect(geometry.boxes.custom).not.toBeNull();
          expect(geometry.boxes.from).not.toBeNull();
          expect(geometry.boxes.to).not.toBeNull();
          expect(geometry.boxes.actions).not.toBeNull();
          for (const [id, value] of [
            ['#progress-period-from', '2025-01-01'],
            ['#progress-period-to', '2025-01-30'],
          ] as const) {
            const input = page.locator(id);
            const dateContract = await input.evaluate((element) => {
              const input = element as HTMLInputElement;
              const style = getComputedStyle(input);
              const webkitValue = getComputedStyle(input, '::-webkit-date-and-time-value');
              const control = input.closest('.date-control');
              return {
                value: input.value,
                width: input.getBoundingClientRect().width,
                textAlign: style.textAlign,
                textAlignLast: style.textAlignLast,
                overflow: style.overflow,
                controlOverflow: control ? getComputedStyle(control).overflow : null,
                webkitTextAlign: webkitValue.textAlign,
              };
            });
            expect(dateContract.value).toBe(value);
            expect(dateContract.width).toBeGreaterThanOrEqual(140);
            expect(dateContract.textAlign).toBe('start');
            expect(dateContract.textAlignLast).toBe('start');
            expect(['clip', 'visible']).toContain(dateContract.overflow);
            expect(dateContract.controlOverflow).toBe('visible');
            // WebKit does not expose this pseudo-element through computed styles.
            expect(['', 'start']).toContain(dateContract.webkitTextAlign);

            if (state === 'custom-open') {
              for (const focused of [true, false]) {
                const visual = await inspectDateVisual(page, input, value, focused);
                const stateLabel = focused ? 'focused' : 'blurred';
                const context = `${theme} ${width}px ${id} ${stateLabel}`;
                expect(visual.inkLeft, `${context}: no value pixels`).not.toBeNull();
                expect(visual.inkRight, `${context}: no value pixels`).not.toBeNull();
                expect(visual.contentWidth, `${context}: content box`).toBeGreaterThanOrEqual(
                  visual.expectedTextWidth,
                );
                expect(visual.inkWidth, `${context}: rendered date pixels`).toBeGreaterThanOrEqual(
                  visual.expectedTextWidth - 8,
                );
                expect(
                  visual.inkRight,
                  `${context}: value reaches calendar reserve`,
                ).toBeLessThanOrEqual(visual.textRegionRight + 1);
              }
            }
          }
        }
        if (captureDirectory) {
          await mkdir(captureDirectory, { recursive: true });
          await page.locator('.progress-hero').screenshot({
            path: resolve(
              captureDirectory,
              `${test.info().project.name}-${width}-${theme}-${state}.png`,
            ),
          });
        }
      };

      await assertGeometry('closed-closed');

      await summary.focus();
      await page.keyboard.press('Enter');
      await expect(summary).toHaveAttribute('aria-expanded', 'true');
      await expect(summary).toBeFocused();
      await expect(helpBody).toBeVisible();
      await assertGeometry('help-open');

      await summary.focus();
      await page.keyboard.press('Enter');
      await expect(summary).toHaveAttribute('aria-expanded', 'false');
      await expect(summary).toBeFocused();
      await expect(helpBody).toBeHidden();

      await customTab.click();
      await expect(customForm).toBeVisible();
      await page.getByLabel('Начало периода').fill('2025-01-01');
      await page.getByLabel('Конец периода').fill('2025-01-30');
      await assertGeometry('custom-open');

      await summary.click();
      await expect(summary).toHaveAttribute('aria-expanded', 'true');
      await expect(helpBody).toBeVisible();
      await assertGeometry('help-and-custom-open');

      await summary.focus();
      await page.keyboard.press('Enter');
      await expect(summary).toHaveAttribute('aria-expanded', 'false');
      await period.getByRole('button', { name: 'Отмена' }).click();
      await expect(customForm).toBeHidden();
    }
  }
});

const ISSUE_873_CAPTURE_SECTIONS = [
  'overview',
  'body',
  'training',
  'nutrition',
  'cardio',
  'wellbeing',
  'history',
] as const;
const ISSUE_873_CAPTURE_VIEWPORTS = [320, 360, 393, 430, 1024, 1280, 1440, 1920] as const;

test('Issue #873 paired browser evidence capture', async ({ page }) => {
  test.skip(process.env.CAPTURE_ISSUE_873 !== '1', 'Evidence-only capture');
  test.setTimeout(600_000);

  const outputDir = process.env.ISSUE_873_CAPTURE_DIR;
  if (!outputDir) throw new Error('ISSUE_873_CAPTURE_DIR is required for Issue #873 evidence');
  await mkdir(outputDir, { recursive: true });
  await mockProgress(page);

  const captures: Array<Record<string, unknown>> = [];
  const settleCapture = async () => {
    await expect(page.locator('[role="status"][aria-busy="true"]')).toHaveCount(0);
    await page.evaluate(async () => {
      await document.fonts.ready;
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      );
      window.scrollTo(0, 0);
    });
  };
  const capture = async (
    theme: 'light' | 'dark',
    section: (typeof ISSUE_873_CAPTURE_SECTIONS)[number],
    width: number,
    state: 'default' | 'expanded' | 'action-add-measurement',
  ) => {
    const region =
      section === 'overview'
        ? page.locator('.progress-summary').first()
        : page.locator('.progress-details').first();
    await expect(region).toBeVisible();
    await settleCapture();
    const metrics = await region.evaluate((element) => {
      const visible = (candidate: Element) => {
        const box = candidate.getBoundingClientRect();
        const style = getComputedStyle(candidate);
        return (
          box.width > 0 &&
          box.height > 0 &&
          style.display !== 'none' &&
          style.visibility !== 'hidden'
        );
      };
      const actions = [...element.querySelectorAll('a,button,[role="tab"],summary')]
        .filter(visible)
        .map((candidate) =>
          (candidate.getAttribute('aria-label') ?? candidate.textContent ?? '')
            .trim()
            .replace(/\s+/g, ' ')
            .slice(0, 100),
        );
      const box = element.getBoundingClientRect();
      return {
        regionHeight: Math.round(box.height),
        regionTop: Math.round(box.top),
        pageScrollHeight: document.documentElement.scrollHeight,
        viewportHeight: window.innerHeight,
        scrollY: Math.round(window.scrollY),
        actionCount: actions.length,
        actionLabels: actions,
        openDetails: [...element.querySelectorAll('details')].filter((candidate) => candidate.open)
          .length,
        detailsCount: element.querySelectorAll('details').length,
      };
    });
    const file = `${theme}-${section}-${width}-${state}.jpg`;
    const path = resolve(outputDir, file);
    await region.screenshot({
      path,
      type: 'jpeg',
      quality: 88,
      animations: 'disabled',
      caret: 'hide',
    });
    captures.push({ theme, section, width, state, file, ...metrics });
  };

  await page.addInitScript(() => {
    const theme = new URLSearchParams(window.location.search).get('capture_theme');
    if (theme === 'light' || theme === 'dark') window.localStorage.setItem('app-theme', theme);
    window.sessionStorage.setItem('fit_access_token', 'test-token');
  });
  const ensureClient = async () => {
    const clientButton = page.getByRole('button', { name: 'Клиент', exact: true });
    if (await clientButton.count()) {
      await expect(clientButton).toBeVisible();
      await clientButton.click();
    }
    await expect(page.locator('.app-shell')).toBeVisible();
  };
  const openSection = async (
    theme: 'light' | 'dark',
    section: (typeof ISSUE_873_CAPTURE_SECTIONS)[number],
  ) => {
    await page.goto(`/app?section=progress&progress_view=${section}&capture_theme=${theme}`);
    await ensureClient();
    await expect(
      section === 'overview'
        ? page.locator('.progress-summary').first()
        : page.locator('.progress-details').first(),
    ).toBeVisible();
  };

  for (const theme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });

    for (const width of ISSUE_873_CAPTURE_VIEWPORTS) {
      await page.setViewportSize({ width, height: width < 900 ? 844 : 1000 });
      for (const section of ISSUE_873_CAPTURE_SECTIONS) {
        await openSection(theme, section);
        await capture(theme, section, width, 'default');
      }
    }

    for (const width of [393, 1440]) {
      await page.setViewportSize({ width, height: width < 900 ? 844 : 1000 });
      for (const section of ISSUE_873_CAPTURE_SECTIONS) {
        await openSection(theme, section);
        const region =
          section === 'overview'
            ? page.locator('.progress-summary').first()
            : page.locator('.progress-details').first();
        await expect(region).toBeVisible();
        await region.locator('details').evaluateAll((elements) => {
          for (const element of elements) (element as HTMLDetailsElement).open = true;
        });
        await capture(theme, section, width, 'expanded');
      }
    }

    for (const width of [393, 1440]) {
      await page.setViewportSize({ width, height: width < 900 ? 844 : 1000 });
      await openSection(theme, 'body');
      await page
        .getByRole('link', { name: /Добавить замер/ })
        .first()
        .click();
      await expect(page.locator('details#measurement-diary')).toHaveAttribute('open', '');
      await capture(theme, 'body', width, 'action-add-measurement');
    }
  }

  await writeFile(
    resolve(outputDir, 'manifest.json'),
    JSON.stringify(
      {
        issue: 873,
        fixture: 'progress-experience.spec.ts::mockProgress',
        revision: process.env.ISSUE_873_CAPTURE_REVISION ?? 'NOT_SPECIFIED',
        browser: 'Chromium',
        themes: ['light', 'dark'],
        viewports: ISSUE_873_CAPTURE_VIEWPORTS.map((width) => ({
          width,
          height: width < 900 ? 844 : 1000,
        })),
        region: '.progress-summary for overview; .progress-details for detail views',
        scrollState:
          'window.scrollY=0; region screenshot after two animation frames and document.fonts.ready',
        captures,
      },
      null,
      2,
    ),
  );
});

for (const menuOpen of [false, true]) {
  test(`#835 quick add keeps focus when the training section loads${menuOpen ? ' with its menu open' : ''}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockProgress(page);
    let releaseSummary!: () => void;
    let markSummaryStarted!: () => void;
    const summaryGate = new Promise<void>((resolve) => {
      releaseSummary = resolve;
    });
    const summaryStarted = new Promise<void>((resolve) => {
      markSummaryStarted = resolve;
    });
    await page.route('**/workouts/progress/summary**', async (route) => {
      markSummaryStarted();
      await summaryGate;
      await route.fallback();
    });
    await page.goto('/app?section=progress&progress_view=training');
    await page.getByRole('button', { name: 'Клиент', exact: true }).click();
    await summaryStarted;
    const add = page.getByRole('button', { name: 'Быстро добавить' });
    await expect(add).toBeVisible();
    const original = await add.elementHandle();
    if (!original) throw new Error('quick-add trigger missing');
    if (menuOpen) {
      await add.click();
      await expect(page.getByRole('dialog', { name: 'Что добавить?' })).toBeVisible();
    } else {
      await add.focus();
      await expect(add).toBeFocused();
    }
    releaseSummary();
    const slot = page.locator('.progress-training-actions__quick-add');
    await expect(slot.locator('[data-testid="quick-add-trigger"]')).toHaveCount(1);
    expect(await original.evaluate((node) => node.isConnected)).toBe(true);
    if (menuOpen) {
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog', { name: 'Что добавить?' })).toBeHidden();
    }
    await expect(add).toBeFocused();
  });
}

test.use({ video: process.env.CAPTURE_835_VIDEO === '1' ? 'on' : 'off' });
test.describe('#835 carousel', () => {
  for (const width of [320, 360, 390, 430, 768, 1024, 1280, 1440, 1920]) {
    for (const theme of ['dark', 'light'] as const) {
      test(`#835 month calendar selects days and resets years at ${width}px ${theme}`, async ({
        page,
        browserName,
      }) => {
        await page.setViewportSize({ width, height: width === 1440 ? 1000 : 844 });
        await page.emulateMedia({
          colorScheme: theme,
          reducedMotion: process.env.CAPTURE_835_VIDEO === '1' ? 'no-preference' : 'reduce',
        });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        await mockProgress(page);
        await page.goto('/app?section=progress');
        await page.getByRole('button', { name: 'Клиент', exact: true }).click();
        await page
          .getByRole('navigation', { name: 'Основная навигация' })
          .getByRole('link', { name: 'Прогресс' })
          .click();
        await page
          .getByRole('navigation', { name: 'Разделы прогресса' })
          .getByRole('tab', { name: /^Тренировки/ })
          .click();
        const calendar = page.locator('.activity-heatmap');

        const capture = async (state: string) => {
          if (!process.env.CAPTURE_835_FINAL) return;
          const dir = resolve(process.env.CAPTURE_835_FINAL);
          await mkdir(dir, { recursive: true });
          await page.evaluate(() => document.fonts.ready);
          if (width < 768 && state !== 'table' && state !== 'overview')
            await calendar.locator('.activity-heatmap__mobile').scrollIntoViewIfNeeded();
          if (width < 768)
            await expect
              .poll(() =>
                calendar.locator('.activity-heatmap__carousel').evaluate((node) => {
                  const slide = node.querySelector('.activity-heatmap__slide:not([inert])')!;
                  return Math.abs(
                    slide.getBoundingClientRect().left - node.getBoundingClientRect().left,
                  );
                }),
              )
              .toBeLessThan(1);
          const path = resolve(dir, `${browserName}-${theme}-${width}-${state}.png`);
          if (state === 'table') {
            await calendar.getByRole('table').scrollIntoViewIfNeeded();
            await page.screenshot({ path, animations: 'disabled' });
          } else {
            await page.screenshot({
              path,
              fullPage:
                state === 'overview' || state === 'active-year' || state === 'complete-year',
              animations: 'disabled',
            });
          }
        };
        if (width < 768) {
          const mobile = calendar.locator('.activity-heatmap__mobile');
          const slider = mobile.locator('.activity-heatmap__carousel');
          const active = mobile.locator('.activity-heatmap__slide:not([inert])');
          const next = mobile.getByRole('button', { name: 'Следующий месяц' });
          const previous = mobile.getByRole('button', { name: 'Предыдущий месяц' });
          const currentMonth = new Intl.DateTimeFormat('ru-RU', {
            month: 'long',
            timeZone: 'Europe/Moscow',
          }).format(new Date());
          await expect(mobile.getByRole('heading')).toContainText(currentMonth);
          await expect(active).toHaveCount(1);
          await expect
            .poll(() =>
              slider.evaluate((node) => {
                const slide = node.querySelector('.activity-heatmap__slide:not([inert])')!;
                return Math.abs(
                  slide.getBoundingClientRect().left - node.getBoundingClientRect().left,
                );
              }),
            )
            .toBeLessThan(1);

          await expect(slider.locator('.activity-heatmap__slide')).toHaveCount(12);
          await capture('overview');
          await calendar.getByLabel('Год', { exact: true }).selectOption('2024');
          await expect(previous).toBeDisabled();
          await expect(mobile.getByRole('heading')).toContainText('январь');
          await next.click();
          await expect(mobile.getByRole('heading')).toContainText('февраль');
          await expect(active.locator('button[data-date]')).toHaveCount(29);
          await active.locator('button[data-date="2024-02-29"]').click();
          await expect(calendar.locator('[aria-live]').last()).toContainText('29 февраля 2024');
          await next.click();
          await expect(mobile.getByRole('heading')).toContainText('март');
          await expect(active.locator('[aria-pressed="true"]')).toHaveCount(0);
          await previous.click();
          await expect(active.locator('[aria-pressed="true"]')).toHaveAttribute(
            'data-date',
            '2024-02-29',
          );
          const box = await slider.boundingBox();
          if (!box) throw new Error('calendar viewport missing');
          await page.mouse.move(box.x + box.width / 2, box.y + 60);
          await page.mouse.wheel(box.width, 0);
          await expect(mobile.getByRole('heading')).toContainText('март');
          await page.mouse.wheel(-box.width, 0);
          await expect(mobile.getByRole('heading')).toContainText('февраль');
          await page.mouse.wheel(0, 100);
          await expect(mobile.getByRole('heading')).toContainText('февраль');
          if (browserName === 'chromium') {
            await slider.scrollIntoViewIfNeeded();
            const touchBox = await slider.boundingBox();
            if (!touchBox) throw new Error('touch viewport missing');
            const session = await page.context().newCDPSession(page);
            await session.send('Emulation.setTouchEmulationEnabled', { enabled: true });
            const swipe = async (horizontal: boolean, reverse = false) => {
              const x = horizontal
                ? touchBox.x + (reverse ? 30 : touchBox.width - 30)
                : touchBox.x + touchBox.width / 2;
              const y = touchBox.y + 120;
              await session.send('Input.dispatchTouchEvent', {
                type: 'touchStart',
                touchPoints: [{ x, y }],
              });
              for (let step = 1; step <= 12; step++) {
                await session.send('Input.dispatchTouchEvent', {
                  type: 'touchMove',
                  touchPoints: [
                    {
                      x: horizontal
                        ? x + ((reverse ? 1 : -1) * (touchBox.width - 60) * step) / 12
                        : x,
                      y: horizontal ? y : y - step * 6,
                    },
                  ],
                });
                await new Promise((resolve) => setTimeout(resolve, 25));
              }
              await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
            };
            await swipe(true);
            await expect(mobile.getByRole('heading')).toContainText('март');
            await swipe(true, true);
            await expect(mobile.getByRole('heading')).toContainText('февраль');
            await swipe(false);
            await expect(mobile.getByRole('heading')).toContainText('февраль');
            await session.detach();
          }

          await capture('month');
          await active.locator('button[data-date]').first().focus();
          await page.keyboard.press('ArrowRight');
          await expect(active.locator('button[data-date]').nth(1)).toBeFocused();
          await page.keyboard.press('Enter');
          await expect(active.locator('button[data-date]').nth(1)).toHaveAttribute(
            'aria-pressed',
            'true',
          );
          await calendar
            .getByLabel('Год', { exact: true })
            .selectOption(String(new Date().getFullYear()));
          await expect(mobile.getByRole('heading')).toContainText(currentMonth);
          await calendar.getByLabel('Год', { exact: true }).selectOption('2024');
          const jan = active.locator('button[data-date="2024-01-01"]');
          await jan.click();
          await expect(calendar.locator('[aria-live]').last()).toContainText('Нет данных');
          await capture('unknown');
          await active.locator('button[data-date="2024-01-27"]').click();
          await expect(calendar.locator('[aria-live]').last()).toContainText('рабочие подходы — 4');
          await capture('selected');
          await expect(active.locator('button[data-date="2024-01-28"]')).toHaveAttribute(
            'data-level',
            'unknown',
          );
          const bounds = await jan.boundingBox();
          expect(bounds?.height).toBeGreaterThanOrEqual(44);
          expect(bounds?.width).toBeGreaterThanOrEqual(32);
          expect(bounds?.width).toBeLessThanOrEqual(
            (await slider.evaluate((node) => node.clientWidth)) / 7,
          );
          await calendar
            .getByLabel('Год', { exact: true })
            .selectOption(String(new Date().getFullYear()));
          while (!(await next.isDisabled())) {
            const before = await mobile.getByRole('heading').textContent();
            await next.click();
            await expect(mobile.getByRole('heading')).not.toHaveText(before ?? '');
          }
          await expect(mobile.getByRole('heading')).toContainText('декабрь');
          await expect(next).toBeDisabled();
          await expect(active.locator('button[data-date]:enabled')).toHaveCount(0);
          await capture('future');
        } else {
          const grid = calendar.getByRole('grid', { name: 'Годовая карта активности' });
          await expect(grid.getByRole('row')).toHaveCount(7);
          await expect(grid.locator('button[tabindex="0"]')).toHaveCount(1);
          const panel = calendar.getByLabel('Данные выбранного дня');
          await expect(panel).toBeVisible();
          expect((await calendar.boundingBox())?.height).toBeLessThan(width <= 1280 ? 480 : 420);
          const gridBounds = await grid.boundingBox();
          const panelBounds = await panel.boundingBox();
          expect(gridBounds).not.toBeNull();
          expect(panelBounds).not.toBeNull();
          if (width >= 1440) {
            expect(panelBounds!.x).toBeGreaterThanOrEqual(gridBounds!.x + gridBounds!.width);
          } else {
            expect(panelBounds!.y).toBeGreaterThanOrEqual(gridBounds!.y + gridBounds!.height);
          }
          expect(
            await grid.evaluate((element) => Number.parseFloat(getComputedStyle(element).fontSize)),
          ).toBeGreaterThanOrEqual(13);
          await capture('overview');
          const warning = calendar.getByText('История неполная', { exact: true });
          await warning.click();
          await expect(calendar.locator('.activity-heatmap__history')).toHaveAttribute('open', '');
          await expect(calendar.locator('.activity-heatmap__history')).toContainText(
            'Без подтверждённой даты: 1',
          );
          await capture('history-details');
          await warning.click();
          await calendar.getByLabel('Год', { exact: true }).selectOption('2022');
          await expect(grid.locator('button[data-date="2022-01-01"]')).toHaveCount(1);
          await expect(calendar.locator('.activity-heatmap__history')).toHaveCount(0);
          await capture('complete-year');
          await calendar.getByLabel('Год', { exact: true }).selectOption('2024');
          await expect(grid.locator('button[data-date]')).toHaveCount(366);
          await capture('active-year');
          const chosen = grid.locator('button[data-date="2024-01-27"]');
          await chosen.hover();
          await expect(calendar.getByRole('tooltip')).toContainText('рабочие подходы — 4');
          await capture('hover');
          await calendar.getByRole('tooltip').hover();
          await expect(calendar.getByRole('tooltip')).toBeVisible();
          expect((await chosen.boundingBox())?.width).toBeGreaterThanOrEqual(11);
          expect((await chosen.boundingBox())?.width).toBeLessThanOrEqual(16);
          await chosen.click();
          await expect(calendar.getByRole('tooltip')).toHaveCount(0);
          await expect(chosen).toHaveAttribute('aria-pressed', 'true');
          await expect(panel).toContainText('Тренировок');
          await expect(panel).toContainText('Рабочих подходов');
          await expect(panel).toContainText('4');
          if (width === 1440) {
            await page.locator('.progress-hero').getByRole('tab', { name: '7 дней' }).click();
            await expect(calendar.getByLabel('Год', { exact: true })).toHaveValue('2024');
            await expect(page.locator('#progress-training')).toContainText('Тренировки · 7 дней');
            await page.locator('.progress-hero').getByRole('tab', { name: '30 дней' }).click();
            await expect(calendar.getByLabel('Год', { exact: true })).toHaveValue('2024');
          }
          await capture('selected');
          await chosen.focus();
          await chosen.press('Escape');
          await expect(calendar.getByRole('tooltip')).toHaveCount(0);
          await chosen.press('ArrowRight');
          await expect(grid.locator('button[data-date="2024-02-03"]')).toBeFocused();
          await page.keyboard.press('ArrowDown');
          await expect(grid.locator('button[data-date="2024-02-04"]')).toBeFocused();
          await page.keyboard.press('Enter');
          await expect(panel).toContainText('Нет достоверных данных за этот день.');
          await capture('unknown');
          await grid.locator('button[data-date="2024-02-29"]').click();
          await expect(calendar.locator('[aria-live]').last()).toContainText('29 февраля 2024');
          await capture('leap');
          await expect(grid.locator('button[tabindex="0"]')).toHaveCount(1);
          await calendar
            .getByLabel('Год', { exact: true })
            .selectOption(String(new Date().getFullYear()));
          await expect(grid.locator('button[data-date$="-01-31"]')).toBeDisabled();
          await expect(calendar.locator('[aria-live]').last()).toContainText('30 января');
          await capture('future');
          const add = page.getByTestId('quick-add-trigger');
          await calendar.scrollIntoViewIfNeeded();
          await expectNoOverlap(calendar, add);
          if (width >= 900) {
            await expect(
              page.locator('#progress-training').getByTestId('quick-add-trigger'),
            ).toHaveCount(1);
            await add.click();
            await expect(page.getByRole('dialog', { name: 'Что добавить?' })).toBeVisible();
            await page.keyboard.press('Escape');
            await expect(page.getByRole('dialog', { name: 'Что добавить?' })).toHaveCount(0);
            await expect(add).toBeFocused();
          }
        }
        await calendar.getByText('Данные по дням', { exact: true }).click();
        await expect(calendar.getByRole('table')).toBeVisible();
        if (width >= 768) {
          const tableRegion = calendar.getByRole('region', { name: 'Таблица активности по дням' });
          await expect(tableRegion).toHaveAttribute('tabindex', '0');
          await tableRegion.focus();
          await page.keyboard.press('End');
          await expect
            .poll(() => tableRegion.evaluate((element) => element.scrollTop))
            .toBeGreaterThan(0);
        }
        await capture('table');
        await calendar.getByLabel('Год', { exact: true }).selectOption('2023');
        await expect(
          calendar.getByText('За этот период нет завершённых тренировок.'),
        ).toBeVisible();
        if (width < 768)
          await expect(
            calendar.locator(
              '.activity-heatmap__slide:not([inert]) button[data-date="2023-01-28"]',
            ),
          ).toHaveAttribute('data-level', '0');
        await capture('empty');
        await expectNoHorizontalOverflow(page);
      });
    }
  }
});

for (const theme of ['dark', 'light'] as const) {
  test(`#835 desktop activity levels are distinguishable in ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    await mockProgress(page);
    await page.route('**/workouts/progress/activity-heatmap**', async (route) => {
      const year = Number(new URL(route.request().url()).searchParams.get('year'));
      const count = (Date.UTC(year + 1, 0, 1) - Date.UTC(year, 0, 1)) / 86_400_000;
      await route.fulfill({
        json: {
          timezone: 'Europe/Moscow',
          history_complete: true,
          undated_workouts: 0,
          days: Array.from({ length: count }, (_, index) => ({
            date: new Date(Date.UTC(year, 0, 1 + index)).toISOString().slice(0, 10),
            is_future: year === new Date().getFullYear() && index > 29,
            completed_workouts: index < 4 ? index : 0,
            working_sets: index < 4 ? index * 4 : 0,
          })),
        },
      });
    });
    await page.goto('/app?section=progress');
    await page.getByRole('button', { name: 'Клиент', exact: true }).click();
    await page
      .getByRole('navigation', { name: 'Основная навигация' })
      .getByRole('link', { name: 'Прогресс' })
      .click();
    await page
      .getByRole('navigation', { name: 'Разделы прогресса' })
      .getByRole('tab', { name: /^Тренировки/ })
      .click();
    const calendar = page.locator('.activity-heatmap');
    await calendar.getByLabel('Год', { exact: true }).selectOption('2022');
    const grid = calendar.getByRole('grid', { name: 'Годовая карта активности' });
    for (let level = 0; level <= 3; level += 1) {
      const day = grid.locator(`button[data-date="2022-01-0${level + 1}"]`);
      await expect(day).toHaveAttribute('data-level', String(level));
      await expect(day).toHaveAccessibleName(new RegExp(`тренировки — ${level}`));
    }
    await expect(grid.locator('button[data-date="2022-01-03"]')).toHaveCSS('opacity', '0.65');
    await expect(grid.locator('button[data-date="2022-01-04"]')).toHaveCSS('opacity', '1');
  });
}
