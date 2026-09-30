import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ExerciseGuideDialog } from '../../../../src/features/exercises/ExerciseGuideDialog';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import type { Exercise, ExerciseHistory } from '../../../../src/shared/api/types';

const fullExercise: Exercise = {
  id: 1,
  title: 'Тяга верхнего блока',
  metric_type: 'strength',
  primary_muscle: 'Спина',
  equipment: 'Тросовый блок',
  primary_muscle_ids: ['back'],
  secondary_muscle_ids: ['biceps'],
  equipment_ids: ['cable'],
  alternatives: [{ id: 2, slug: 'band-pulldown', title: 'Тяга резиновой ленты' }],
  difficulty_level: 'beginner',
  is_custom: false,
  is_personalized: false,
  has_guide: true,
  guide: {
    technique_steps: ['Зафиксируйте корпус.', 'Опустите локти под контролем.'],
    breathing: 'Выдохните во время тяги.',
    common_mistakes: ['Раскачивание корпусом'],
    muscles: [
      {
        identifier: 'back',
        name: 'Спина',
        role_id: 'primary',
        role: 'Основная',
        function: 'Тянет плечевой пояс назад и вниз.',
      },
      {
        identifier: 'biceps',
        name: 'Бицепс',
        role_id: 'secondary',
        role: 'Дополнительная',
        function: 'Сгибает локоть.',
      },
    ],
    equipment: [{ identifier: 'cable', name: 'Тросовый блок' }],
    safety_notes: ['Не тяните рукоять рывком.'],
    alternatives: [{ id: 2, slug: 'band-pulldown', title: 'Тяга резиновой ленты' }],
    media: [
      {
        type: 'image',
        url: '/static/exercise-guides/lat-pulldown-active.jpg',
        poster: '/static/exercise-guides/lat-pulldown-active.jpg',
        phase_id: 'concentric_end',
        phase: 'Фаза усилия',
        alt: 'Тяга верхнего блока: фаза усилия',
        source_name: 'Проверенный источник',
        source_url: 'https://example.com/source',
        source_license: 'Разрешённая лицензия',
        source_license_url: 'https://example.com/license',
        width: 850,
        height: 567,
        byte_size: 75_000,
        sort_order: 0,
        sources: [
          {
            url: '/static/exercise-guides/lat-pulldown-active.jpg',
            mime_type: 'image/jpeg',
            width: 850,
            height: 567,
            byte_size: 75_000,
          },
        ],
      },
      {
        type: 'image',
        url: '/static/exercise-guides/lat-pulldown-start.jpg',
        poster: '/static/exercise-guides/lat-pulldown-start.jpg',
        phase_id: 'eccentric_end',
        phase: 'Фаза возврата',
        alt: 'Тяга верхнего блока: фаза возврата',
        source_name: 'Проверенный источник',
        source_url: 'https://example.com/source',
        source_license: 'Разрешённая лицензия',
        source_license_url: 'https://example.com/license',
        width: 850,
        height: 567,
        byte_size: 75_000,
        sort_order: 1,
        sources: [
          {
            url: '/static/exercise-guides/lat-pulldown-start.jpg',
            mime_type: 'image/jpeg',
            width: 850,
            height: 567,
            byte_size: 75_000,
          },
        ],
      },
    ],
    images: [
      {
        phase: 'Фаза усилия',
        url: '/static/exercise-guides/lat-pulldown-active.jpg',
        alt: 'Тяга верхнего блока: фаза усилия',
      },
      {
        phase: 'Фаза возврата',
        url: '/static/exercise-guides/lat-pulldown-start.jpg',
        alt: 'Тяга верхнего блока: фаза возврата',
      },
    ],
    media_reference: 'exercise-guides:lat-pulldown',
    source_name: 'Проверенный источник',
    source_url: 'https://example.com/source',
    source_license: 'Разрешённая лицензия',
    source_license_url: 'https://example.com/license',
  },
};

const customExercise: Exercise = {
  id: 2,
  title: 'Тяга резиновой ленты',
  metric_type: 'strength',
  primary_muscle: 'Спина',
  equipment: 'Резиновая лента',
  primary_muscle_ids: [],
  secondary_muscle_ids: [],
  equipment_ids: [],
  alternatives: [{ id: 1, slug: 'lat-pulldown', title: 'Тяга верхнего блока' }],
  difficulty_level: 'beginner',
  is_custom: true,
  is_personalized: true,
  has_guide: false,
  guide: null,
};

const history: ExerciseHistory = {
  exercise_id: 1,
  exercise_title: fullExercise.title,
  metric_type: 'strength',
  load_unit: 'kg',
  last_performed: {
    workout_id: 44,
    workout_title: 'Тренировка спины',
    performed_on: '2026-09-30',
    completed_at: '2026-09-30T08:00:00Z',
  },
  best_authoritative_load: {
    value_kg: 80,
    workout: {
      workout_id: 44,
      workout_title: 'Тренировка спины',
      performed_on: '2026-09-30',
      completed_at: '2026-09-30T08:00:00Z',
    },
    reps: 8,
  },
  estimated_1rm: {
    kind: 'estimated',
    formula: 'brzycki',
    value_kg: 99.5,
    workout: {
      workout_id: 44,
      workout_title: 'Тренировка спины',
      performed_on: '2026-09-30',
      completed_at: '2026-09-30T08:00:00Z',
    },
    reps: 8,
    load_kg: 80,
  },
  rep_prs: [
    {
      range_key: '6-10',
      range_label: '6–10 повторений',
      min_reps: 6,
      max_reps: 10,
      best_reps: 8,
      best_reps_workout: {
        workout_id: 44,
        workout_title: 'Тренировка спины',
        performed_on: '2026-09-30',
        completed_at: '2026-09-30T08:00:00Z',
      },
      best_load_kg: 80,
      best_load_workout: {
        workout_id: 44,
        workout_title: 'Тренировка спины',
        performed_on: '2026-09-30',
        completed_at: '2026-09-30T08:00:00Z',
      },
    },
  ],
  windows: [
    {
      days: 7,
      period_start: '2026-09-24',
      period_end: '2026-09-30',
      performed_session_count: 1,
      completed_set_count: 2,
      authoritative_set_count: 2,
      reps_total: 16,
      best_authoritative_load_kg: 80,
      estimated_1rm_kg: 99.5,
    },
    {
      days: 30,
      period_start: '2026-09-01',
      period_end: '2026-09-30',
      performed_session_count: 2,
      completed_set_count: 4,
      authoritative_set_count: 4,
      reps_total: 32,
      best_authoritative_load_kg: 80,
      estimated_1rm_kg: 99.5,
    },
    {
      days: 90,
      period_start: '2026-07-03',
      period_end: '2026-09-30',
      performed_session_count: 3,
      completed_set_count: 6,
      authoritative_set_count: 6,
      reps_total: 48,
      best_authoritative_load_kg: 80,
      estimated_1rm_kg: 99.5,
    },
  ],
  recent_sessions: [
    {
      workout: {
        workout_id: 44,
        workout_title: 'Тренировка спины',
        performed_on: '2026-09-30',
        completed_at: '2026-09-30T08:00:00Z',
      },
      workout_exercise_id: 144,
      prescribed_reps: '6–10',
      completed_set_count: 2,
      authoritative_set_count: 2,
      reps_total: 16,
      max_authoritative_load_kg: 80,
      best_set_volume_kg: 640,
      estimated_1rm_kg: 99.5,
      sets: [
        {
          set_number: 1,
          reps: 8,
          load_kg: 80,
          volume_kg: 640,
          rir: '2',
          set_kind: 'working',
          planned_role: 'top',
          analytics_bucket: 'working',
          pr_eligible: true,
        },
      ],
    },
  ],
  progression: [
    {
      performed_on: '2026-09-30',
      workout_id: 44,
      max_reps: 8,
      max_authoritative_load_kg: 80,
      estimated_1rm_kg: 99.5,
      authoritative_set_count: 2,
    },
  ],
  progression_events: [
    {
      event_id: 7,
      event_kind: 'confirm',
      proposal_id: 'proposal-44',
      target_workout_id: 44,
      exercise_id: 1,
      rule_id: 'double_progression',
      rule_kind: 'rep_range',
      rule_snapshot: { min_reps: 6, max_reps: 10 },
      source_evidence_ids: ['workout:44'],
      reason_codes: ['top_range_repeated'],
      proposed_weight_kg: 82.5,
      adjusted_weight_kg: null,
      result: { action: 'confirmed' },
      created_at: '2026-09-30T08:30:00Z',
    },
  ],
  history_truncated: false,
};

const customHistory: ExerciseHistory = {
  ...history,
  exercise_id: customExercise.id,
  exercise_title: customExercise.title,
  last_performed: null,
  best_authoritative_load: null,
  estimated_1rm: null,
  rep_prs: [],
  windows: history.windows.map((window) => ({
    ...window,
    performed_session_count: 0,
    completed_set_count: 0,
    authoritative_set_count: 0,
    reps_total: null,
    best_authoritative_load_kg: null,
    estimated_1rm_kg: null,
  })),
  recent_sessions: [],
  progression: [],
  progression_events: [],
};

function renderGuide() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <ExerciseGuideDialog
          exerciseId={fullExercise.id}
          exerciseTitle={fullExercise.title}
          onClose={vi.fn()}
        />
      </NavigationProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('ExerciseGuideDialog', () => {
  it('shows reviewed guide metadata and opens an alternative in the same dialog', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/history')) {
        return new Response(JSON.stringify(path.includes('/2/history') ? customHistory : history), {
          status: 200,
        });
      }
      const exercise = path.endsWith('/2') ? customExercise : fullExercise;
      return new Response(JSON.stringify(exercise), { status: 200 });
    });
    renderGuide();

    expect(await screen.findByRole('heading', { name: 'Техника выполнения' })).toBeVisible();
    expect(screen.getByAltText('Тяга верхнего блока: фаза усилия')).toBeVisible();
    expect(screen.getByAltText('Тяга верхнего блока: фаза возврата')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Основные мышцы' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Дополнительные мышцы' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Оборудование' })).toBeVisible();
    expect(screen.getByText('Не тяните рукоять рывком.')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Разрешённая лицензия' })).toHaveAttribute(
      'href',
      'https://example.com/license',
    );
    expect(screen.getByText('Лучший авторитетный вес')).toBeVisible();
    expect(screen.getByText('80 кг')).toBeVisible();
    expect(screen.getByText('Оценка по формуле Бжицки')).toBeVisible();
    expect(screen.getByText('6–10 повторений')).toBeVisible();
    expect(screen.getByText(/Предложено: 82\.5 кг/)).toBeVisible();
    expect(screen.getByRole('link', { name: 'Открыть тренировку' })).toHaveAttribute(
      'href',
      '/app?section=progress&workout_id=44',
    );

    fireEvent.click(screen.getByRole('button', { name: 'Тяга резиновой ленты' }));

    expect(await screen.findByRole('heading', { name: 'Техника пока не добавлена' })).toBeVisible();
    expect(screen.getByText('Пользовательское упражнение')).toBeVisible();
    expect(screen.getByText('Резиновая лента')).toBeVisible();
    expect(screen.queryByText('Всё тело')).not.toBeInTheDocument();
    expect(screen.queryByText('Без оборудования')).not.toBeInTheDocument();
  });
});
