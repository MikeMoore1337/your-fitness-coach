import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProfileForm, validateProfileForm } from '../../../../src/features/profile/ProfileForm';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());
const reloadUser = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => ({ user: { id: 10, profile: null }, reloadUser }),
}));
vi.mock('../../../../src/features/profile/TrainingPreferencesForm', () => ({
  TrainingPreferencesForm: () => null,
}));

const previewByGoal = {
  fat_loss: { min_bpm: 130, max_bpm: 140 },
  recomposition: { min_bpm: 124, max_bpm: 140 },
  maintenance: { min_bpm: 119, max_bpm: 140 },
  muscle_gain: { min_bpm: 119, max_bpm: 130 },
} as const;

const zones = [
  { zone: 1, title: 'Восстановление', min_bpm: 130, max_bpm: 140 },
  { zone: 2, title: 'Лёгкая', min_bpm: 140, max_bpm: 151 },
  { zone: 3, title: 'Аэробная', min_bpm: 151, max_bpm: 162 },
  { zone: 4, title: 'Пороговая', min_bpm: 162, max_bpm: 173 },
  { zone: 5, title: 'Максимальная', min_bpm: 173, max_bpm: 184 },
];

function renderForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <ProfileForm />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

function birthDateInput(): HTMLInputElement {
  const label = screen.getByText('Дата рождения').closest('label');
  const input = label?.querySelector('input');
  if (!input) throw new Error('Birth date input not found');
  return input;
}

function restingHeartRateInput(): HTMLInputElement {
  const label = screen.getByText('Средний пульс в покое, уд/мин').closest('label');
  const input = label?.querySelector('input');
  if (!input) throw new Error('Resting heart rate input not found');
  return input;
}

describe('ProfileForm personal data', () => {
  beforeEach(() => {
    localStorage.clear();
    apiMock.mockReset();
    apiMock.mockResolvedValue({ items: [] });
  });

  afterEach(cleanup);

  it('keeps the full selected goal readable and connected to its native select', () => {
    renderForm();
    fireEvent.click(screen.getByText('Личные данные и фитнес-профиль'));
    const goal = screen.getByRole('combobox', { name: 'Цель' });
    expect(goal).toHaveAccessibleDescription('Выберите цель из списка.');

    fireEvent.change(goal, { target: { value: 'recomposition' } });
    expect(goal).toHaveValue('recomposition');
    expect(goal).toHaveAccessibleDescription('Улучшить форму без фокуса на вес');
    expect(document.getElementById('profile-goal-value')).toBeVisible();

    fireEvent.change(goal, { target: { value: 'muscle_gain' } });
    expect(goal).toHaveAccessibleDescription('Набрать мышечную массу');
  });

  it('opens the avatar editor from Personal data and restores focus to its trigger', async () => {
    renderForm();

    const avatarSetting = screen.getByText('Фото профиля').closest('.profile-avatar-setting');
    expect(avatarSetting).not.toBeNull();
    expect(avatarSetting).toHaveTextContent('Используется нейтральный emoji');
    const editAvatar = screen.getByRole('button', { name: 'Изменить аватар' });
    editAvatar.focus();
    expect(editAvatar).toHaveFocus();
    fireEvent.click(editAvatar);

    expect(await screen.findByRole('dialog', { name: 'Аватар' })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Выбрать изображение' })).toHaveFocus(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть редактор аватара' }));

    await waitFor(() => expect(editAvatar).toHaveFocus());
  });
});

describe('ProfileForm heart rate preview', () => {
  beforeEach(() => {
    localStorage.clear();
    apiMock.mockReset();
    apiMock.mockImplementation(
      (path: string, options?: { body: { goal: keyof typeof previewByGoal } }) => {
        if (path.endsWith('/body-priority-options'))
          return Promise.resolve({ items: [{ id: 'chest', name: 'Грудь' }] });
        return Promise.resolve({
          estimated_max_heart_rate: 184,
          heart_rate_reserve: 109,
          heart_rate_calculation_method: 'heart_rate_reserve',
          heart_rate_zones: zones,
          recommended_cardio_range: previewByGoal[options!.body.goal],
        });
      },
    );
  });

  afterEach(cleanup);

  it('updates only the recommendation when the goal changes', async () => {
    renderForm();
    fireEvent.change(birthDateInput(), { target: { value: '1992-08-12' } });
    fireEvent.change(restingHeartRateInput(), {
      target: { value: '75' },
    });
    fireEvent.change(screen.getByLabelText('Цель'), { target: { value: 'fat_loss' } });

    expect((await screen.findAllByText('130–140 уд/мин')).length).toBeGreaterThan(1);
    const zoneList = screen.getByText('Пульсовые зоны').parentElement?.nextElementSibling;
    expect(zoneList).not.toBeNull();
    const initialZones = zoneList?.textContent;

    fireEvent.change(screen.getByLabelText('Цель'), { target: { value: 'recomposition' } });
    await screen.findByText('124–140 уд/мин');

    fireEvent.change(screen.getByLabelText('Цель'), { target: { value: 'maintenance' } });
    await screen.findByText('119–140 уд/мин');

    fireEvent.change(screen.getByLabelText('Цель'), { target: { value: 'muscle_gain' } });
    await screen.findByText('119–130 уд/мин');

    expect(screen.getByText('184 уд/мин')).toBeInTheDocument();
    expect(zoneList?.textContent).toBe(initialZones);
    expect(document.body).not.toHaveTextContent(/HRR|MET/);
  });

  it('treats nonnumeric input as empty and does not preview an out-of-range value', async () => {
    renderForm();
    fireEvent.change(birthDateInput(), { target: { value: '1992-08-12' } });
    const restingHeartRate = restingHeartRateInput();
    fireEvent.change(restingHeartRate, {
      target: { value: 'abc' },
    });
    await waitFor(() =>
      expect(
        apiMock.mock.calls.filter(([path]) => path.endsWith('/heart-rates/preview')),
      ).toHaveLength(1),
    );
    expect(restingHeartRate).toHaveValue(null);
    const previewCall = apiMock.mock.calls.find(([path]) => path.endsWith('/heart-rates/preview'));
    expect(previewCall?.[1].body.resting_heart_rate).toBeNull();

    apiMock.mockClear();
    fireEvent.change(restingHeartRate, {
      target: { value: '121' },
    });
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(
      apiMock.mock.calls.filter(([path]) => path.endsWith('/heart-rates/preview')),
    ).toHaveLength(0);
  });

  it('shows validation beside the field and keeps entered values after a recoverable error', async () => {
    renderForm();
    fireEvent.change(screen.getByLabelText('Цель'), { target: { value: 'maintenance' } });
    fireEvent.change(screen.getByLabelText('Уровень подготовки'), {
      target: { value: 'beginner' },
    });
    fireEvent.change(screen.getByLabelText('Рост, см'), { target: { value: '99' } });

    fireEvent.click(screen.getByRole('button', { name: 'Сохранить изменения' }));

    expect(await screen.findByText('Укажите рост от 100 до 250 см.')).toBeInTheDocument();
    expect(screen.getByLabelText('Рост, см')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Рост, см')).toHaveValue(99);
    expect(apiMock.mock.calls.filter(([path]) => path === '/api/v1/me/profile')).toHaveLength(0);

    fireEvent.change(screen.getByLabelText('Рост, см'), { target: { value: '170' } });
    fireEvent.change(screen.getByLabelText('Имя'), { target: { value: 'Анна' } });
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/body-priority-options')) return Promise.resolve({ items: [] });
      if (path === '/api/v1/me/profile') return Promise.reject(new Error('Нет соединения'));
      return Promise.resolve(null);
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить изменения' }));

    expect(
      await screen.findByText(/Нет соединения.*Введённые данные сохранены в этом браузере/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Имя')).toHaveValue('Анна');
    expect(screen.getByLabelText('Вес, кг')).toHaveAttribute('inputmode', 'decimal');
    expect(screen.getByLabelText('Силовых тренировок в неделю')).toHaveAttribute(
      'inputmode',
      'numeric',
    );
  });
});

describe('validateProfileForm', () => {
  it('uses the backend profile ranges without making optional measurements required', () => {
    expect(
      validateProfileForm({
        goal: 'maintenance',
        level: 'beginner',
        workouts_per_week: 3,
        cardio_trainings_per_week: 0,
        height_cm: null,
        weight_kg: null,
        resting_heart_rate: null,
      }),
    ).toEqual({
      birth_date: undefined,
      goal: undefined,
      level: undefined,
      height_cm: undefined,
      weight_kg: undefined,
      workouts_per_week: undefined,
      cardio_trainings_per_week: undefined,
      resting_heart_rate: undefined,
    });
  });
});
