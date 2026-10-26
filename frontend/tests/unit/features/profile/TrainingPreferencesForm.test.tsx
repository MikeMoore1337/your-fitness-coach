import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TrainingPreferencesForm } from '../../../../src/features/profile/TrainingPreferencesForm';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());
const reloadUser = vi.hoisted(() => vi.fn());
const authState = vi.hoisted(() => ({
  user: {
    id: 10,
    profile: {
      training_preferences: {
        preferred_duration_min: null,
        preferred_duration_max: null,
        preferred_weekdays: [],
        preferred_time: null,
        location_profiles: [],
        preferred_exercise_ids: [],
        avoided_exercises: [],
        note: null,
        updated_at: '2030-01-10T12:00:00',
        updated_by: { user_id: 20, display_name: 'Тренер Анна', role: 'trainer' },
        conflict: {
          status: 'review_required',
          active_program_id: 7,
          reasons: ['В активной программе есть упражнение из списка «избегать».'],
        },
      },
    },
  },
}));

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => ({ user: authState.user, reloadUser }),
}));

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <TrainingPreferencesForm />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('TrainingPreferencesForm', () => {
  beforeEach(() => {
    localStorage.clear();
    Object.assign(authState.user.profile.training_preferences, {
      preferred_duration_min: null,
      preferred_duration_max: null,
      preferred_weekdays: [],
      preferred_time: null,
      location_profiles: [],
      preferred_exercise_ids: [],
      avoided_exercises: [],
      note: null,
      updated_at: '2030-01-10T12:00:00',
      updated_by: { user_id: 20, display_name: 'Тренер Анна', role: 'trainer' },
    });
    apiMock.mockReset();
    reloadUser.mockReset();
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/programs/exercises') {
        return Promise.resolve([
          {
            id: 11,
            edit_target_id: 11,
            slug: 'bench-press',
            title: 'Жим штанги лёжа с очень длинным названием упражнения',
            equipment: 'Штанга',
            equipment_ids: ['barbell', 'bench'],
            primary_muscle_ids: ['chest'],
            secondary_muscle_ids: [],
            alternatives: [],
            difficulty_level: 'beginner',
            is_custom: false,
            is_personalized: false,
            created_by_user_id: null,
            source_exercise_id: null,
            has_guide: false,
          },
          {
            id: 12,
            edit_target_id: 12,
            slug: 'custom-row',
            title: 'Моя тяга',
            equipment: 'Собственный вес',
            equipment_ids: ['bodyweight'],
            primary_muscle_ids: ['back'],
            secondary_muscle_ids: [],
            alternatives: [],
            difficulty_level: 'beginner',
            is_custom: true,
            is_personalized: true,
            created_by_user_id: 10,
            source_exercise_id: null,
            has_guide: false,
          },
        ]);
      }
      if (path === '/api/v1/me/profile') return Promise.reject(new Error('Нет соединения'));
      return Promise.resolve(null);
    });
  });

  afterEach(cleanup);

  it('uses progressive groups, supports custom exercises and keeps a failed draft', async () => {
    renderForm();
    expect(screen.getByText('Тренер Анна', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('Текущую программу нужно проверить')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Проверить программу' })).toHaveAttribute(
      'href',
      '/app?section=programs',
    );
    expect(screen.getByText('Расписание').closest('details')).not.toHaveAttribute('open');

    const preferred = screen
      .getByText('Предпочитаемые упражнения')
      .closest('details') as HTMLDetailsElement;
    fireEvent.click(within(preferred).getByText('Предпочитаемые упражнения'));
    const custom = await within(preferred).findByText('Моя тяга');
    fireEvent.click(custom.closest('label')!);

    const avoid = screen
      .getByText('Упражнения и движения, которых хотите избегать')
      .closest('details') as HTMLDetailsElement;
    fireEvent.click(within(avoid).getByText('Упражнения и движения, которых хотите избегать'));
    const longExercise = await within(avoid).findByText(/Жим штанги лёжа/);
    fireEvent.click(longExercise.closest('label')!);
    expect(within(avoid).getByText('Штанга · Скамья')).toBeInTheDocument();
    expect(screen.getByText(/Это не медицинская оценка.*При боли или травме/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Дополнительная заметка'), {
      target: { value: 'Не ставить тяжёлые жимы подряд' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить предпочтения' }));
    expect(
      await screen.findByText(/Нет соединения.*Изменения сохранены в этом браузере/),
    ).toBeInTheDocument();
    const request = apiMock.mock.calls.find(([path]) => path === '/api/v1/me/profile');
    expect(request?.[1].body.training_preferences).toMatchObject({
      preferred_exercise_ids: [12],
      avoided_exercises: [{ exercise_id: 11 }],
      note: 'Не ставить тяжёлые жимы подряд',
    });
    await waitFor(() =>
      expect(localStorage.getItem('fit_training_preferences_draft_10')).toContain(
        'Не ставить тяжёлые жимы подряд',
      ),
    );
  });

  it('validates the duration range before sending', () => {
    renderForm();
    fireEvent.change(screen.getByLabelText('От, минут'), { target: { value: '90' } });
    fireEvent.change(screen.getByLabelText('До, минут'), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить предпочтения' }));
    expect(
      screen.getByText('Минимальная длительность не может быть больше максимальной.'),
    ).toBeInTheDocument();
    expect(apiMock.mock.calls.some(([path]) => path === '/api/v1/me/profile')).toBe(false);
  });

  it('does not persist a clean baseline and discards a draft from an older server revision', async () => {
    renderForm();
    expect(localStorage.getItem('fit_training_preferences_draft_10')).toBeNull();
    fireEvent.change(screen.getByLabelText('От, минут'), { target: { value: '45' } });
    await waitFor(() =>
      expect(localStorage.getItem('fit_training_preferences_draft_10')).toContain(
        '2030-01-10T12:00:00',
      ),
    );

    cleanup();
    Object.assign(authState.user.profile.training_preferences, {
      preferred_duration_min: 55,
      updated_at: '2030-01-11T12:00:00',
      updated_by: { user_id: 10, display_name: 'Анна', role: 'self' },
    });
    renderForm();

    expect(screen.getByLabelText('От, минут')).toHaveValue(55);
    expect(localStorage.getItem('fit_training_preferences_draft_10')).toBeNull();
  });
});
