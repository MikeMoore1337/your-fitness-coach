import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NutritionSuggestions } from '../../../../src/features/nutrition/NutritionSuggestions';
import type { NutritionSuggestions as NutritionSuggestionsResponse } from '../../../../src/shared/api/types';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));

const suggestions: NutritionSuggestionsResponse = {
  mode: 'deterministic',
  diary_date: '2026-08-19',
  targets: {
    energy_kcal: '2000',
    protein_g: '140',
    fat_g: '70',
    carbs_g: '220',
  },
  remaining: {
    energy_kcal: '500',
    protein_g: '30',
    fat_g: '20',
    carbs_g: '60',
  },
  remaining_confidence: 'partial',
  limitations: ['Часть БЖУ неизвестна: неполные записи не превращаются в нули.'],
  max_candidates: 6,
  candidates: [
    {
      candidate_id: 'template:7',
      candidate_kind: 'template',
      identity_id: 7,
      name: 'Мой ужин',
      items: [
        {
          position: 0,
          item_kind: 'food',
          food_id: 11,
          recipe_id: null,
          name: 'Курица',
          brand: 'YFC',
          amount: '100',
          amount_unit: 'g',
          nutrition: {
            energy_kcal: '165',
            protein_g: '31',
            fat_g: null,
            carbs_g: '0',
            fiber_g: null,
          },
          nutrition_confidence: 'partial',
        },
        {
          position: 1,
          item_kind: 'recipe',
          food_id: null,
          recipe_id: 12,
          name: 'Рис',
          brand: null,
          amount: '80',
          amount_unit: 'g',
          nutrition: {
            energy_kcal: '104',
            protein_g: '2',
            fat_g: '0.2',
            carbs_g: '23',
            fiber_g: '1',
          },
          nutrition_confidence: 'exact',
        },
      ],
      nutrition: {
        energy_kcal: '269',
        protein_g: '33',
        fat_g: null,
        carbs_g: '23',
        fiber_g: null,
      },
      nutrition_confidence: 'partial',
      sources: ['saved_template'],
      reasons: ['saved_template', 'protein_fit', 'partial_nutrition'],
    },
  ],
};

function renderSuggestions() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <NutritionSuggestions diaryDate="2026-08-19" initialMealType="lunch" />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('NutritionSuggestions', () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path: string) => {
      if (path.startsWith('/api/v1/nutrition/diary/suggestions?')) {
        return Promise.resolve(suggestions);
      }
      if (path === '/api/v1/nutrition/diary/suggestions/commit') {
        return Promise.resolve({
          operation_kind: 'suggestion',
          diary_date: '2026-08-19',
          meal_type: 'lunch',
          entries: [],
          replayed: false,
        });
      }
      return Promise.reject(new Error(`Unexpected API call: ${path}`));
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows partial data and waits for explicit editable confirmation before persisting', async () => {
    renderSuggestions();

    expect(await screen.findByText('Мой ужин')).toBeVisible();
    expect(screen.getByText('Частичные БЖУ')).toBeVisible();
    expect(
      screen.getByText('Часть БЖУ неизвестна: неполные записи не превращаются в нули.'),
    ).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Изменить вариант' })).not.toBeInTheDocument();
    expect(
      apiMock.mock.calls.some(([path]) => path === '/api/v1/nutrition/diary/suggestions/commit'),
    ).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Проверить вариант' }));
    const amountInputs = screen.getAllByLabelText('Количество');
    fireEvent.change(amountInputs[0]!, { target: { value: '150' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Убрать' })[1]!);
    fireEvent.change(screen.getByLabelText('Приём пищи'), { target: { value: 'dinner' } });

    expect(screen.getAllByLabelText('Количество')).toHaveLength(1);
    expect(
      apiMock.mock.calls.some(([path]) => path === '/api/v1/nutrition/diary/suggestions/commit'),
    ).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Добавить выбранное' }));
    await waitFor(() =>
      expect(
        apiMock.mock.calls.some(([path]) => path === '/api/v1/nutrition/diary/suggestions/commit'),
      ).toBe(true),
    );
    const commitCall = apiMock.mock.calls.find(
      ([path]) => path === '/api/v1/nutrition/diary/suggestions/commit',
    );
    expect(commitCall?.[1]).toEqual(
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Idempotency-Key': expect.stringContaining('nutrition-suggestion-'),
        }),
        body: {
          diary_date: '2026-08-19',
          meal_type: 'dinner',
          items: [{ food_id: 11, amount: '150', amount_unit: 'g' }],
        },
      }),
    );
  });
});
