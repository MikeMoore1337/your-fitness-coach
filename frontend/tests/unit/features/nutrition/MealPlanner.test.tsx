import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MealPlanner } from '../../../../src/features/nutrition/MealPlanner';
import type { NutritionPlanDay, NutritionPlanWeek } from '../../../../src/shared/api/types';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', () => ({
  api: apiMock,
  ApiError: class ApiError extends Error {},
}));

const nutrition = {
  energy_kcal: '120.00',
  protein_g: '12.000',
  fat_g: '4.000',
  carbs_g: '8.000',
  fiber_g: '2.000',
};
const targets = {
  energy_kcal: '2000.00',
  protein_g: '140.000',
  fat_g: '70.000',
  carbs_g: '220.000',
};

function makeDay(date = '2026-08-19'): NutritionPlanDay {
  return {
    plan_date: date,
    timezone: 'Europe/Moscow',
    revision: 1,
    slots: [
      {
        meal_type: 'breakfast',
        planned: nutrition,
        items: [
          {
            id: 7,
            meal_type: 'breakfast',
            position: 0,
            item_kind: 'food',
            food_id: 11,
            recipe_id: null,
            source_template_id: null,
            name: 'Овсянка',
            brand: null,
            amount: '100.000',
            amount_unit: 'g',
            weight_g: '100.000',
            nutrition,
            available: true,
          },
        ],
      },
      ...(['lunch', 'dinner', 'snacks'] as const).map((meal_type) => ({
        meal_type,
        planned: {
          ...nutrition,
          energy_kcal: '0.00',
          protein_g: '0.000',
          fat_g: '0.000',
          carbs_g: '0.000',
        },
        items: [],
      })),
    ],
    planned: nutrition,
    targets,
    remaining: {
      energy_kcal: '1880.00',
      protein_g: '128.000',
      fat_g: '66.000',
      carbs_g: '212.000',
    },
    nutrition_complete: true,
    updated_at: '2026-08-19T08:00:00Z',
    replayed: false,
  };
}

function makeWeek(): NutritionPlanWeek {
  const days = Array.from({ length: 7 }, (_, index) =>
    makeDay(`2026-08-${String(17 + index).padStart(2, '0')}`),
  );
  return {
    week_start: '2026-08-17',
    week_end: '2026-08-23',
    timezone: 'Europe/Moscow',
    days,
    planned: {
      ...nutrition,
      energy_kcal: '840.00',
      protein_g: '84.000',
      fat_g: '28.000',
      carbs_g: '56.000',
      fiber_g: '14.000',
    },
    targets: {
      ...targets,
      energy_kcal: '14000.00',
      protein_g: '980.000',
      fat_g: '490.000',
      carbs_g: '1540.000',
    },
    remaining: {
      energy_kcal: '13160.00',
      protein_g: '896.000',
      fat_g: '462.000',
      carbs_g: '1484.000',
    },
    nutrition_complete: true,
  };
}

function renderPlanner() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <MealPlanner initialDate="2026-08-19" timeZone="Europe/Moscow" />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('MealPlanner', () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (options?.method === 'POST') return Promise.resolve(makeDay());
      if (path.includes('/plans/day')) return Promise.resolve(makeDay());
      if (path.includes('/plans/week')) return Promise.resolve(makeWeek());
      if (path.includes('/foods/favorites'))
        return Promise.resolve({ items: [], total: 0, limit: 20, offset: 0 });
      if (path.includes('/foods/recent')) {
        return Promise.resolve({
          items: [{ id: 11, name: 'Овсянка', brand: null }],
          total: 1,
          limit: 20,
          offset: 0,
        });
      }
      if (path.includes('/recipes'))
        return Promise.resolve({ items: [], total: 0, limit: 50, offset: 0 });
      if (path.includes('/templates'))
        return Promise.resolve({ items: [], total: 0, limit: 50, offset: 0 });
      throw new Error(`Unexpected API call: ${path}`);
    });
  });

  afterEach(() => cleanup());

  it('loads a day plan only after opening, shows target versus planned facts and adds a food', async () => {
    renderPlanner();
    const planner = screen.getByTestId('meal-planner');
    expect(apiMock).not.toHaveBeenCalled();
    fireEvent.click(within(planner).getByText('План питания'));

    expect(await screen.findByText('Овсянка', { selector: 'strong' })).toBeVisible();
    expect(screen.getByText('120 ккал')).toBeVisible();
    expect(screen.getByText(/1[\s\u00a0]880 ккал/)).toBeVisible();
    fireEvent.change(screen.getByLabelText('Что добавить'), { target: { value: '11' } });
    fireEvent.click(screen.getByRole('button', { name: 'Добавить в план' }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/nutrition/plans/items?plan_date=2026-08-19'),
        expect.objectContaining({
          method: 'POST',
          body: { food_id: 11, amount: '100', amount_unit: 'g' },
          headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }),
        }),
      ),
    );
  });

  it('switches to the seven-day plan view with the shared week strip', async () => {
    renderPlanner();
    fireEvent.click(screen.getByText('План питания'));
    await screen.findByText('Овсянка', { selector: 'strong' });
    fireEvent.click(screen.getByRole('tab', { name: 'Неделя' }));

    expect(await screen.findByRole('heading', { name: 'Неделя плана' })).toBeVisible();
    expect(await screen.findByRole('region', { name: 'Планы по дням' })).toBeVisible();
    expect(screen.getAllByRole('button', { name: 'Открыть день' })).toHaveLength(7);
  });
});
