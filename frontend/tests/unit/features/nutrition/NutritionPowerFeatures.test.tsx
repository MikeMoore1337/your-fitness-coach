import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MealTemplateBrowser } from '../../../../src/features/nutrition/MealTemplateBrowser';
import { NaturalFoodInput } from '../../../../src/features/nutrition/NaturalFoodInput';
import type {
  Food,
  FoodDiaryBatchResponse,
  FoodDiaryEntry,
  FoodSearchAliasList,
  NaturalInputPreview,
  NutritionMealTemplate,
  NutritionMealTemplateList,
} from '../../../../src/shared/api/types';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));

const nutrition = {
  energy_kcal: '180.00',
  protein_g: '22.000',
  fat_g: '4.000',
  carbs_g: '12.000',
  fiber_g: null,
};

const food: Food = {
  id: 17,
  name: 'Творог 5%',
  brand: null,
  barcode: null,
  energy_kcal_per_100g: '120.00',
  protein_g_per_100g: '17.000',
  fat_g_per_100g: '5.000',
  carbs_g_per_100g: '3.000',
  fiber_g_per_100g: null,
  nutrition_basis_kind: 'per_100_g',
  nutrition_basis_amount: '100.000',
  nutrition_basis_unit: 'g',
  canonical_facts: null,
  nutrition_provenance: null,
  catalog_quality: 'verified',
  provenance: 'internal',
  trust_level: 'verified',
  canonical_complete: true,
  standard_serving_amount: null,
  standard_serving_unit: null,
  standard_serving_weight_g: null,
  food_type: 'system',
  is_favorite: false,
  last_used_at: null,
  created_at: '2026-08-01T07:00:00Z',
  updated_at: '2026-08-01T07:00:00Z',
};

const entry: FoodDiaryEntry = {
  id: 71,
  diary_date: '2026-08-19',
  meal_type: 'breakfast',
  food_id: food.id,
  recipe_id: null,
  entry_kind: 'food',
  logged_at: null,
  food_name: food.name,
  food_brand: null,
  amount: '180.000',
  amount_unit: 'g',
  weight_g: '180.000',
  nutrition_basis_kind: 'per_100_g',
  nutrition_basis_amount: '100.000',
  nutrition_basis_unit: 'g',
  serving_amount: null,
  serving_unit: null,
  serving_weight_g: null,
  nutrition,
  created_at: '2026-08-19T07:00:00Z',
  updated_at: '2026-08-19T07:00:00Z',
};

const batchResponse: FoodDiaryBatchResponse = {
  operation_kind: 'natural_input',
  diary_date: '2026-08-19',
  meal_type: 'breakfast',
  entries: [entry],
  replayed: false,
};

const naturalPreview: NaturalInputPreview = {
  rows: [
    {
      row_id: 'row-0',
      raw_text: 'творог 180 г',
      name: 'творог',
      amount: '180',
      amount_unit: 'g',
      unit_inferred: false,
      status: 'matched',
      selected_food_id: food.id,
      selected_food: food,
      nutrition,
      candidates: [{ food, source: 'personal' }],
      message: 'Проверьте найденный продукт перед записью.',
    },
  ],
};

const emptyAliases: FoodSearchAliasList = { items: [] };

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>{ui}</FeedbackProvider>
    </QueryClientProvider>,
  );
}

function templateResponse(): NutritionMealTemplate {
  return {
    id: 4,
    name: 'Обычный завтрак',
    items: [
      {
        id: 12,
        position: 0,
        item_kind: 'food',
        food_id: food.id,
        recipe_id: null,
        name: food.name,
        brand: null,
        amount: '180.000',
        amount_unit: 'g',
        weight_g: '180.000',
        nutrition,
        available: true,
        message: null,
      },
    ],
    total_weight_g: '180.000',
    totals: nutrition,
    created_at: '2026-08-01T07:00:00Z',
    updated_at: '2026-08-01T07:00:00Z',
  };
}

describe('nutrition power features', () => {
  beforeEach(() => {
    apiMock.mockReset();
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
  });

  it('reviews natural rows and sends one idempotent batch on a double click', async () => {
    const commitControl: {
      resolve?: (value: FoodDiaryBatchResponse) => void;
    } = {};
    const commitPromise = new Promise<FoodDiaryBatchResponse>((resolve) => {
      commitControl.resolve = resolve;
    });
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/nutrition/food-aliases') return Promise.resolve(emptyAliases);
      if (path === '/api/v1/nutrition/diary/natural-input/preview')
        return Promise.resolve(naturalPreview);
      if (path === '/api/v1/nutrition/diary/natural-input/commit' && options?.method === 'POST')
        return commitPromise;
      throw new Error(`Unexpected API call: ${path}`);
    });
    const onCompleted = vi.fn();
    renderWithProviders(
      <NaturalFoodInput
        diaryDate="2026-08-19"
        mealType="breakfast"
        userId={10}
        onCompleted={onCompleted}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('Список продуктов'), {
      target: { value: 'творог 180 г' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Проверить список' }));
    expect(await screen.findByText('Проверено')).toBeVisible();
    expect(screen.getByRole('region', { name: 'Итого по списку' })).toHaveTextContent('180 ккал');

    const commitButton = screen.getByRole('button', { name: 'Записать проверенные продукты' });
    fireEvent.click(commitButton);
    fireEvent.click(commitButton);
    await waitFor(() =>
      expect(
        apiMock.mock.calls.filter(
          ([path, options]) =>
            path === '/api/v1/nutrition/diary/natural-input/commit' && options?.method === 'POST',
        ),
      ).toHaveLength(1),
    );
    const firstCommit = apiMock.mock.calls.find(
      ([path, options]) =>
        path === '/api/v1/nutrition/diary/natural-input/commit' && options?.method === 'POST',
    );
    expect(firstCommit?.[1]).toEqual(
      expect.objectContaining({
        body: {
          diary_date: '2026-08-19',
          meal_type: 'breakfast',
          items: [{ row_id: 'row-0', food_id: 17, amount: '180', amount_unit: 'g' }],
        },
        headers: { 'Idempotency-Key': expect.stringContaining('natural-') },
      }),
    );
    commitControl.resolve?.(batchResponse);
    await waitFor(() => expect(onCompleted).toHaveBeenCalledWith(batchResponse));
  });

  it('keeps private aliases editable without exposing their target in telemetry', async () => {
    const alias = {
      id: 8,
      alias: 'теос',
      food_id: food.id,
      food_name: food.name,
      food_brand: null,
      available: true,
      created_at: '2026-08-01T07:00:00Z',
      updated_at: '2026-08-01T07:00:00Z',
    };
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/nutrition/food-aliases' && !options?.method)
        return Promise.resolve({ items: [alias] });
      if (path === '/api/v1/nutrition/food-aliases/8' && options?.method === 'PATCH')
        return Promise.resolve({ ...alias, alias: 'мой творог' });
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderWithProviders(
      <NaturalFoodInput
        diaryDate="2026-08-19"
        mealType="breakfast"
        userId={10}
        onCompleted={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.click(await screen.findByText('Мои названия продуктов'));
    fireEvent.click(await screen.findByRole('button', { name: 'Изменить' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Новое название вместо теос' }), {
      target: { value: 'мой творог' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/food-aliases/8',
        expect.objectContaining({ method: 'PATCH', body: { alias: 'мой творог' } }),
      ),
    );
  });

  it('offers manual creation for an unresolved row without leaving the review flow', async () => {
    const unresolvedPreview: NaturalInputPreview = {
      rows: [
        {
          ...naturalPreview.rows[0]!,
          raw_text: 'неизвестный продукт 180 г',
          name: 'неизвестный продукт',
          status: 'unresolved',
          selected_food_id: null,
          selected_food: null,
          candidates: [],
          message: 'Продукт не найден. Найдите его в каталоге или удалите строку.',
        },
      ],
    };
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/nutrition/food-aliases') return Promise.resolve(emptyAliases);
      if (path === '/api/v1/nutrition/diary/natural-input/preview')
        return Promise.resolve(unresolvedPreview);
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderWithProviders(
      <NaturalFoodInput
        diaryDate="2026-08-19"
        mealType="breakfast"
        userId={10}
        onCompleted={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('Список продуктов'), {
      target: { value: 'неизвестный продукт 180 г' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Проверить список' }));
    expect(await screen.findByText('Не найдено')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Создать вручную' }));

    expect(await screen.findByRole('form', { name: 'Новый продукт' })).toBeVisible();
    expect(screen.getByLabelText('Название *')).toHaveValue('неизвестный продукт');
  });

  it('inserts a selected meal template with a stable batch boundary', async () => {
    const template = templateResponse();
    const list: NutritionMealTemplateList = { items: [template], total: 1, limit: 50, offset: 0 };
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/nutrition/templates?limit=50') return Promise.resolve(list);
      if (path === '/api/v1/nutrition/templates/4/entries' && options?.method === 'POST')
        return Promise.resolve({ ...batchResponse, operation_kind: 'meal_template' });
      throw new Error(`Unexpected API call: ${path}`);
    });
    const onCompleted = vi.fn();
    renderWithProviders(
      <MealTemplateBrowser
        diaryDate="2026-08-19"
        mealType="breakfast"
        mealEntries={[entry]}
        onCompleted={onCompleted}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.click(await screen.findByRole('button', { name: /Обычный завтрак/ }));
    const insertButton = screen.getByRole('button', { name: 'Добавить в дневник' });
    fireEvent.click(insertButton);
    fireEvent.click(insertButton);
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/templates/4/entries',
        expect.objectContaining({
          method: 'POST',
          body: { diary_date: '2026-08-19', meal_type: 'breakfast' },
          headers: { 'Idempotency-Key': expect.stringContaining('meal-template-') },
        }),
      ),
    );
    expect(
      apiMock.mock.calls.filter(
        ([path, options]) =>
          path === '/api/v1/nutrition/templates/4/entries' && options?.method === 'POST',
      ),
    ).toHaveLength(1);
    await waitFor(() => expect(onCompleted).toHaveBeenCalled());
  });

  it('does not query or mutate personal templates in demo mode', async () => {
    renderWithProviders(
      <MealTemplateBrowser
        diaryDate="2026-08-19"
        mealType="breakfast"
        mealEntries={[]}
        demoSafeMode
        onCompleted={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(await screen.findByText(/capability-safe заглушка/i)).toBeVisible();
    expect(apiMock).not.toHaveBeenCalled();
  });
});
