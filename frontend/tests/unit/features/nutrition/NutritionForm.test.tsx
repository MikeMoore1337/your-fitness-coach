import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NutritionForm } from '../../../../src/features/nutrition/NutritionForm';
import { queryKeys } from '../../../../src/shared/queryKeys';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());
const useAuthMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: useAuthMock,
}));

function SummaryProbe({ queryFn }: { queryFn: () => Promise<unknown> }) {
  useQuery({ queryKey: queryKeys.progress.summary(30), queryFn });
  return null;
}

function renderForm(dependentQuery?: () => Promise<unknown>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        {dependentQuery && <SummaryProbe queryFn={dependentQuery} />}
        <NutritionForm />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('NutritionForm', () => {
  beforeEach(() => {
    localStorage.clear();
    apiMock.mockReset();
    apiMock.mockResolvedValue({});
    useAuthMock.mockReturnValue({ user: { id: 10, profile: null } });
  });

  afterEach(cleanup);

  it('shows plain-language daily activity, goals and calculation details', () => {
    renderForm();

    expect(
      screen.getByRole('combobox', { name: /Как проходит большая часть/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('combobox', { name: /Сколько шагов вы обычно проходите/ }),
    ).toBeInTheDocument();
    expect(screen.getByText('Сохранять текущий вес и форму.')).toBeInTheDocument();
    expect(screen.getByText(/Не учитывайте здесь отдельную ходьбу/)).toBeInTheDocument();
    expect(screen.getByText('Целевая калорийность')).toBeInTheDocument();
    expect(
      screen.getByText('Стартовый ориентир. Проверьте результат по динамике за 14–21 день.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Точность стартовой оценки: высокая.')).toBeInTheDocument();
    expect(screen.getByText(/Смарт-часы и фитнес-браслеты оценивают/)).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/MET/i);
    expect(document.body).not.toHaveTextContent(/×\s*1[.,]5/);
  });

  it('prefills progressively collected profile values for the personal calculation', () => {
    useAuthMock.mockReturnValue({
      user: {
        id: 10,
        profile: {
          birth_date: '1990-08-12',
          goal: 'fat_loss',
          height_cm: 182,
          weight_kg: 83,
        },
      },
    });
    renderForm();

    expect(screen.getByRole('combobox', { name: /^Цель/ })).toHaveValue('fat_loss');
    expect(screen.getByLabelText('Рост, см')).toHaveValue('182');
    expect(screen.getByLabelText('Вес, кг')).toHaveValue('83');
  });

  it('adds and removes separately configured cardio trainings', () => {
    renderForm();

    fireEvent.click(screen.getByRole('button', { name: 'Добавить кардио' }));
    expect(screen.getByText('Кардио 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Вид')).toHaveValue('walking');
    expect(screen.getByRole('combobox', { name: /Интенсивность/ })).toHaveValue('moderate');

    fireEvent.change(screen.getByRole('combobox', { name: /Интенсивность/ }), {
      target: { value: 'hard' },
    });
    expect(screen.getByText('Могу произнести только несколько слов подряд.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Удалить кардио 1' }));
    expect(screen.queryByLabelText('Вид')).not.toBeInTheDocument();
    expect(screen.getByText('Если кардио нет, ничего добавлять не нужно.')).toBeInTheDocument();
  });

  it('lowers confidence when steps are unknown', () => {
    renderForm();

    fireEvent.change(screen.getByRole('combobox', { name: /Сколько шагов/ }), {
      target: { value: 'unknown' },
    });

    expect(screen.getByText('Точность стартовой оценки: низкая.')).toBeInTheDocument();
  });

  it('submits only the new detailed activity fields', async () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить кардио' }));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить КБЖУ' }));

    await waitFor(() =>
      expect(apiMock.mock.calls.some(([path]) => path === '/api/v1/nutrition/targets')).toBe(true),
    );
    const options = apiMock.mock.calls.find(([path]) => path === '/api/v1/nutrition/targets')![1];
    expect(options.body).toMatchObject({
      daily_routine: 'mixed',
      steps_range: 'from_7000_to_10000',
      strength_training_type: 'regular',
      cardio_trainings: [
        {
          kind: 'walking',
          trainings_per_week: 2,
          duration_minutes: 30,
          intensity: 'moderate',
        },
      ],
    });
    expect(options.body).not.toHaveProperty('daily_activity_level');
    expect(options.body).not.toHaveProperty('cardio_trainings_per_week');
    expect(options.body).not.toHaveProperty('cardio_intensity');
  });

  it('refetches adherence summaries after saving nutrition targets', async () => {
    const dependentQuery = vi.fn().mockResolvedValue({});
    renderForm(dependentQuery);
    await waitFor(() => expect(dependentQuery).toHaveBeenCalledOnce());

    fireEvent.click(screen.getByRole('button', { name: 'Сохранить КБЖУ' }));

    await waitFor(() => expect(dependentQuery).toHaveBeenCalledTimes(2));
  });

  it('switches to accessible manual numeric inputs and explains implied energy', () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Указать вручную' }));

    const calories = screen.getByRole('spinbutton', { name: 'Калории, ккал' });
    expect(calories).toHaveAttribute('inputmode', 'numeric');
    expect(calories).toHaveAttribute('enterkeyhint', 'next');
    expect(screen.getByText('2190 ккал')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Сохранить ручные ориентиры' })).toBeEnabled();
  });

  it('requires explicit confirmation for a large manual energy mismatch and keeps the draft', async () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Указать вручную' }));
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Калории, ккал' }), {
      target: { value: '1200' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Белки, г' }), {
      target: { value: '200' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Жиры, г' }), {
      target: { value: '100' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Углеводы, г' }), {
      target: { value: '200' },
    });

    const save = screen.getByRole('button', { name: 'Сохранить ручные ориентиры' });
    expect(screen.getByRole('alert')).toHaveTextContent('Проверьте разницу: 1300 ккал');
    expect(save).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /Сохранить значения/ }));
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() =>
      expect(apiMock.mock.calls.some(([path]) => path === '/api/v1/nutrition/targets/manual')).toBe(
        true,
      ),
    );
    const body = apiMock.mock.calls.find(
      ([path]) => path === '/api/v1/nutrition/targets/manual',
    )![1].body;
    expect(body).toMatchObject({
      calories: 1200,
      protein_g: 200,
      fat_g: 100,
      carbs_g: 200,
      confirm_energy_mismatch: true,
    });
  });
});
