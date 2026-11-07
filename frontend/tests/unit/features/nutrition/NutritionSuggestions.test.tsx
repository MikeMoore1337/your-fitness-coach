import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NutritionSuggestions } from '../../../../src/features/nutrition/NutritionSuggestions';
import type {
  FoodDiaryNutrition,
  NutritionSuggestions as NutritionSuggestionsResponse,
} from '../../../../src/shared/api/types';
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

type PreviewRequest = {
  diary_date: string;
  meal_type: string;
  items: { food_id?: number; recipe_id?: number; amount: string; amount_unit: string }[];
};

const tokenFor = (body: PreviewRequest) => (body.items[0]?.amount === '150' ? 'b' : 'a').repeat(64);

function makePreview(body: PreviewRequest) {
  const fields = ['energy_kcal', 'protein_g', 'fat_g', 'carbs_g', 'fiber_g'] as const;
  const items = body.items.map((selected, position) => {
    const source = suggestions.candidates![0]!.items.find(
      (item) =>
        (selected.food_id != null && item.food_id === selected.food_id) ||
        (selected.recipe_id != null && item.recipe_id === selected.recipe_id),
    )!;
    const scale = Number(selected.amount) / Number(source.amount);
    const nutrition = Object.fromEntries(
      fields.map((field) => [
        field,
        source.nutrition[field] == null ? null : String(Number(source.nutrition[field]) * scale),
      ]),
    ) as FoodDiaryNutrition;
    return { ...source, ...selected, position, nutrition };
  });
  const before: FoodDiaryNutrition = {
    energy_kcal: '1000',
    protein_g: '50',
    fat_g: '20',
    carbs_g: '100',
    fiber_g: '5',
  };
  const addition = Object.fromEntries(
    fields.map((field) => [
      field,
      items.some((item) => item.nutrition[field] == null)
        ? null
        : String(items.reduce((sum, item) => sum + Number(item.nutrition[field]), 0)),
    ]),
  ) as FoodDiaryNutrition;
  const after = Object.fromEntries(
    fields.map((field) => [
      field,
      before[field] == null || addition[field] == null
        ? null
        : String(Number(before[field]) + Number(addition[field])),
    ]),
  ) as FoodDiaryNutrition;
  return {
    diary_date: body.diary_date,
    meal_type: body.meal_type,
    items,
    before,
    addition,
    after,
    diary: before,
    planned: null,
    projected_after: null,
    targets: suggestions.targets,
    target_id: 1,
    target_source: 'manual',
    target_effective_from: '2026-08-19',
    target_weight_kg: null,
    target_goal: null,
    constraint_status: 'not_set',
    constraint_messages: [],
    preference_message: null,
    preview_token: tokenFor(body),
  };
}

function renderSuggestions() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <NutritionSuggestions diaryDate="2026-08-19" initialMealType="lunch" />
        </FeedbackProvider>
      </QueryClientProvider>,
    ),
  };
}

describe('NutritionSuggestions', () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path: string, options?: { body: PreviewRequest }) => {
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
      if (path === '/api/v1/nutrition/diary/suggestions/preview') {
        return Promise.resolve(makePreview(options!.body));
      }
      return Promise.reject(new Error(`Unexpected API call: ${path}`));
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('shows partial data and waits for explicit editable confirmation before persisting', async () => {
    const { queryClient } = renderSuggestions();
    const reportKey = ['workout', 'nutrition-report', 'me', 'days_7', null, null] as const;
    queryClient.setQueryData(reportKey, { cached: true });

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
    await screen.findByText('Как изменится день');
    const amountInputs = screen.getAllByLabelText('Количество');
    fireEvent.change(amountInputs[0]!, { target: { value: '150' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Убрать' })[1]!);
    fireEvent.change(screen.getByLabelText('Приём пищи'), { target: { value: 'dinner' } });

    expect(screen.getAllByLabelText('Количество')).toHaveLength(1);
    expect(
      apiMock.mock.calls.some(([path]) => path === '/api/v1/nutrition/diary/suggestions/commit'),
    ).toBe(false);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Добавить выбранное' })).toBeEnabled(),
    );
    expect(screen.getByText('247,5')).toBeVisible();
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
          preview_token: tokenFor({
            diary_date: '2026-08-19',
            meal_type: 'dinner',
            items: [{ food_id: 11, amount: '150', amount_unit: 'g' }],
          }),
        },
      }),
    );
    await waitFor(() => expect(queryClient.getQueryData(reportKey)).toBeUndefined());
  });

  it('never confirms an older preview when responses arrive out of order', async () => {
    const pending: {
      body: PreviewRequest;
      resolve: (value: ReturnType<typeof makePreview>) => void;
    }[] = [];
    apiMock.mockImplementation((path: string, options?: { body: PreviewRequest }) => {
      if (path.startsWith('/api/v1/nutrition/diary/suggestions?'))
        return Promise.resolve(suggestions);
      if (path === '/api/v1/nutrition/diary/suggestions/preview') {
        return new Promise((resolve) => pending.push({ body: options!.body, resolve }));
      }
      if (path === '/api/v1/nutrition/diary/suggestions/commit') {
        return Promise.resolve({ entries: [], replayed: false });
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderSuggestions();
    fireEvent.click(await screen.findByRole('button', { name: 'Проверить вариант' }));
    await waitFor(() => expect(pending).toHaveLength(1));
    expect(screen.getByRole('button', { name: 'Добавить выбранное' })).toBeDisabled();
    fireEvent.change(screen.getAllByLabelText('Количество')[0]!, { target: { value: '150' } });
    await waitFor(() => expect(pending).toHaveLength(2));
    await act(async () => pending[1]!.resolve(makePreview(pending[1]!.body)));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Добавить выбранное' })).toBeEnabled(),
    );
    expect(screen.getByText('351,5')).toBeVisible();
    await act(async () => pending[0]!.resolve(makePreview(pending[0]!.body)));
    expect(screen.getByText('351,5')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить выбранное' }));
    await waitFor(() => {
      const call = apiMock.mock.calls.find(([path]) => path.endsWith('/commit'));
      expect(call?.[1].body.preview_token).toBe(tokenFor(pending[1]!.body));
    });
  });

  it('shows the full stored precision in the preview', async () => {
    apiMock.mockImplementation((path: string, options?: { body: PreviewRequest }) => {
      if (path.startsWith('/api/v1/nutrition/diary/suggestions?'))
        return Promise.resolve(suggestions);
      if (path.endsWith('/preview')) {
        const preview = makePreview(options!.body);
        preview.addition.energy_kcal = '247.58';
        preview.addition.protein_g = '46.503';
        preview.after.energy_kcal = '1247.58';
        preview.after.protein_g = '96.503';
        return Promise.resolve(preview);
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderSuggestions();
    fireEvent.click(await screen.findByRole('button', { name: 'Проверить вариант' }));
    expect(await screen.findByText('247,58')).toBeVisible();
    expect(screen.getByText('46,503')).toBeVisible();
  });

  it('does not allow confirmation when the preview response is incomplete', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path.startsWith('/api/v1/nutrition/diary/suggestions?'))
        return Promise.resolve(suggestions);
      if (path.endsWith('/preview')) return Promise.resolve({ items: [] });
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderSuggestions();
    fireEvent.click(await screen.findByRole('button', { name: 'Проверить вариант' }));
    expect(
      await screen.findByText('Не удалось получить точный расчёт. Повторите попытку.'),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Добавить выбранное' })).toBeDisabled();
    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/commit'))).toBe(false);
  });

  it('locks the reviewed inputs while saving and retries with the same idempotency key', async () => {
    let rejectFirst: ((reason: Error) => void) | undefined;
    let writes = 0;
    apiMock.mockImplementation((path: string, options?: { body: PreviewRequest }) => {
      if (path.startsWith('/api/v1/nutrition/diary/suggestions?'))
        return Promise.resolve(suggestions);
      if (path.endsWith('/preview')) return Promise.resolve(makePreview(options!.body));
      if (path.endsWith('/commit')) {
        writes += 1;
        if (writes === 1)
          return new Promise((_resolve, reject) => {
            rejectFirst = reject;
          });
        return Promise.resolve({ entries: [], replayed: true });
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderSuggestions();
    fireEvent.click(await screen.findByRole('button', { name: 'Проверить вариант' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Добавить выбранное' })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Добавить выбранное' }));
    await waitFor(() => expect(rejectFirst).toBeDefined());
    expect(screen.getAllByLabelText('Количество')[0]).toBeDisabled();
    await act(async () => rejectFirst!(new Error('Сеть недоступна')));
    expect(await screen.findByText('Сеть недоступна')).toBeVisible();
    expect(screen.getAllByLabelText('Количество')[0]).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить выбранное' }));
    await waitFor(() => expect(writes).toBe(2));
    const calls = apiMock.mock.calls.filter(([path]) => path.endsWith('/commit'));
    expect(calls[0]?.[1].headers['Idempotency-Key']).toBe(calls[1]?.[1].headers['Idempotency-Key']);
    expect(calls[0]?.[1].body).toEqual(calls[1]?.[1].body);
  });
});
