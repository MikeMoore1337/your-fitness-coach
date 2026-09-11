import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NutritionDiary } from '../../../../src/features/nutrition/NutritionDiary';
import type { Food, FoodDiaryDay, FoodDiaryEntry } from '../../../../src/shared/api/types';
import {
  PRODUCT_EVENT_NAME,
  type ProductEventEnvelope,
} from '../../../../src/shared/analytics/productEvents';
import { dateInputValue } from '../../../../src/shared/dateTime';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());
const useAuthMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/app/AuthProvider', () => ({ useAuth: useAuthMock }));
vi.mock('../../../../src/features/nutrition/HydrationTracker', () => ({
  HydrationTracker: ({ diaryDate }: { diaryDate: string }) => (
    <section aria-label="Гидратация">
      <h2>Напитки</h2>
      Гидратация за {diaryDate}
    </section>
  ),
}));

const nutrition = {
  energy_kcal: '420.00',
  protein_g: '18.500',
  fat_g: '12.000',
  carbs_g: '54.000',
  fiber_g: '7.000',
};

const entry: FoodDiaryEntry = {
  id: 41,
  diary_date: '2026-08-19',
  meal_type: 'breakfast',
  food_id: 7,
  recipe_id: null,
  entry_kind: 'food',
  logged_at: null,
  food_name: 'Овсяная каша',
  food_brand: null,
  amount: '100.000',
  amount_unit: 'g',
  weight_g: '100.000',
  serving_amount: '1.000',
  serving_unit: 'serving',
  serving_weight_g: '50.000',
  nutrition,
  created_at: '2026-08-19T07:00:00Z',
  updated_at: '2026-08-19T07:00:00Z',
};

const food: Food = {
  id: 7,
  name: 'Овсяная каша',
  brand: null,
  barcode: null,
  energy_kcal_per_100g: '420.00',
  protein_g_per_100g: '18.500',
  fat_g_per_100g: '12.000',
  carbs_g_per_100g: '54.000',
  fiber_g_per_100g: '7.000',
  standard_serving_amount: '1.000',
  standard_serving_unit: 'serving',
  standard_serving_weight_g: '50.000',
  food_type: 'system',
  is_favorite: true,
  last_used_at: '2026-08-18T07:00:00Z',
  created_at: '2026-08-01T07:00:00Z',
  updated_at: '2026-08-01T07:00:00Z',
};

function makeDay(entries: FoodDiaryEntry[] = [entry]): FoodDiaryDay {
  return {
    diary_date: '2026-08-19',
    timezone: 'Europe/Moscow',
    meals: [
      { meal_type: 'breakfast', entries, totals: entries.length ? nutrition : zeroNutrition },
      { meal_type: 'lunch', entries: [], totals: zeroNutrition },
      { meal_type: 'dinner', entries: [], totals: zeroNutrition },
      { meal_type: 'snacks', entries: [], totals: zeroNutrition },
    ],
    totals: entries.length ? nutrition : zeroNutrition,
    targets: {
      energy_kcal: '2000.00',
      protein_g: '140.000',
      fat_g: '70.000',
      carbs_g: '220.000',
    },
    remaining: {
      energy_kcal: entries.length ? '1580.00' : '2000.00',
      protein_g: entries.length ? '121.500' : '140.000',
      fat_g: entries.length ? '58.000' : '70.000',
      carbs_g: entries.length ? '166.000' : '220.000',
    },
    status: entries.length ? 'incomplete' : 'unlogged',
    status_is_explicit: false,
  };
}

const zeroNutrition = {
  energy_kcal: '0.00',
  protein_g: '0.000',
  fat_g: '0.000',
  carbs_g: '0.000',
  fiber_g: null,
};

function renderDiary({ initialFoodQuickAdd = false }: { initialFoodQuickAdd?: boolean } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <NutritionDiary
          initialDate="2026-08-19"
          initialFoodQuickAdd={initialFoodQuickAdd}
          timeZone="Europe/Moscow"
        />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

function breakfastSection(): HTMLElement {
  return screen.getByRole('heading', { name: 'Завтрак' }).closest('section') as HTMLElement;
}

describe('NutritionDiary', () => {
  beforeEach(() => {
    localStorage.clear();
    apiMock.mockReset();
    useAuthMock.mockReturnValue({ user: { id: 10 } });
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it('opens the quick food entry requested by the global action', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay([]));
      if (path.startsWith('/api/v1/nutrition/foods/recent')) {
        return Promise.resolve({ items: [food], total: 1, limit: 12, offset: 0 });
      }
      if (path.startsWith('/api/v1/nutrition/foods/favorites')) {
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary({ initialFoodQuickAdd: true });

    expect(await screen.findByRole('heading', { name: 'Быстрый ввод' })).toBeVisible();
    expect(screen.getByRole('dialog', { name: 'Быстрый ввод' })).toBeVisible();
  });

  it('shows all meals, entry macros, targets and navigates by date', async () => {
    apiMock.mockResolvedValue(makeDay());
    renderDiary();

    expect(await screen.findByText('Овсяная каша')).toBeInTheDocument();
    expect(
      screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent),
    ).toEqual(
      expect.arrayContaining([
        'Полнота данных',
        'Баланс дня',
        'Еда',
        'Завтрак',
        'Обед',
        'Ужин',
        'Перекусы',
        'КБЖУ',
        'Напитки',
      ]),
    );
    const sectionOrder = screen
      .getAllByRole('heading', { level: 2 })
      .map((heading) => heading.textContent)
      .filter((heading) =>
        ['Полнота данных', 'Баланс дня', 'Еда', 'КБЖУ', 'Напитки'].includes(heading ?? ''),
      );
    expect(sectionOrder).toEqual(['Полнота данных', 'Баланс дня', 'Еда', 'КБЖУ', 'Напитки']);
    expect(screen.getByRole('progressbar', { name: /Калории: 420 из 2.+000 ккал/ })).toBeVisible();
    expect(screen.getByText('Б 18,5')).toBeVisible();

    expect(screen.queryByRole('navigation', { name: 'Дата дневника' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /18 августа/i }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/api/v1/nutrition/diary?diary_date=2026-08-18'),
    );
  });

  it('keeps empty meals compact and lets every meal be expanded or collapsed', async () => {
    apiMock.mockResolvedValue(makeDay());
    renderDiary();

    await screen.findByText('Овсяная каша');
    const breakfast = breakfastSection();
    const lunch = screen.getByRole('heading', { name: 'Обед' }).closest('section') as HTMLElement;
    const breakfastToggle = within(breakfast).getByRole('button', { name: 'Завтрак' });
    const lunchToggle = within(lunch).getByRole('button', { name: 'Обед' });

    expect(breakfastToggle).toHaveAttribute('aria-expanded', 'true');
    expect(lunchToggle).toHaveAttribute('aria-expanded', 'false');
    expect(
      within(lunch).queryByText('Добавьте продукт — недавние будут под рукой.'),
    ).not.toBeVisible();

    fireEvent.click(lunchToggle);
    expect(lunchToggle).toHaveAttribute('aria-expanded', 'true');
    expect(within(lunch).getByText('Добавьте продукт — недавние будут под рукой.')).toBeVisible();

    fireEvent.click(breakfastToggle);
    expect(breakfastToggle).toHaveAttribute('aria-expanded', 'false');
    expect(within(breakfast).queryByText('Овсяная каша')).not.toBeVisible();
  });

  it('uses Russian plural forms in compact meal summaries', async () => {
    const entries = (count: number, mealType: FoodDiaryEntry['meal_type'], idOffset: number) =>
      Array.from({ length: count }, (_, index) => ({
        ...entry,
        id: idOffset + index,
        meal_type: mealType,
        food_name: `${mealType}-${index}`,
      }));
    const day = makeDay([]);
    day.meals = [
      { meal_type: 'breakfast', entries: entries(5, 'breakfast', 100), totals: nutrition },
      { meal_type: 'lunch', entries: entries(11, 'lunch', 200), totals: nutrition },
      { meal_type: 'dinner', entries: entries(21, 'dinner', 300), totals: nutrition },
      { meal_type: 'snacks', entries: [], totals: zeroNutrition },
    ];
    apiMock.mockResolvedValue(day);
    renderDiary();

    expect(await screen.findByText(/5 записей/)).toBeVisible();
    expect(screen.getByText(/11 записей/)).toBeVisible();
    expect(screen.getByText(/21 запись/)).toBeVisible();
  });

  it('names an intentionally empty day without ambiguous fasting terminology', async () => {
    apiMock.mockResolvedValue({
      ...makeDay([]),
      status: 'fasted',
      status_is_explicit: true,
    });
    renderDiary();

    expect(await screen.findByText('День без приёмов пищи', { selector: 'strong' })).toBeVisible();
    expect(screen.getByText(/только если сознательно не ели весь день/i)).toBeVisible();
    expect(screen.queryByText(/пост/i)).not.toBeInTheDocument();
  });

  it('adds a recent product and reloads the persisted diary', async () => {
    let logged = false;
    apiMock.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) {
        return Promise.resolve(makeDay(logged ? [entry] : []));
      }
      if (path.startsWith('/api/v1/nutrition/foods/recent')) {
        return Promise.resolve({ items: [food], total: 1, limit: 12, offset: 0 });
      }
      if (path.startsWith('/api/v1/nutrition/foods/favorites')) {
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      }
      if (path === '/api/v1/nutrition/diary/entries' && options?.method === 'POST') {
        logged = true;
        return Promise.resolve(entry);
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();
    await screen.findAllByText('Пока без записей');

    fireEvent.click(within(breakfastSection()).getByRole('button', { name: /Добавить/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Добавить Овсяная каша' }));
    const amount = screen.getByRole('spinbutton', { name: 'Количество' });
    fireEvent.change(amount, { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Добавить в дневник' }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/diary/entries',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({
            food_id: 7,
            amount: 2,
            amount_unit: 'serving',
            meal_type: 'breakfast',
          }),
        }),
      ),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(await screen.findByText('Овсяная каша')).toBeVisible();
    expect(localStorage.getItem('fit_food_draft_10_2026-08-19_breakfast')).toBeNull();
  });

  it('keeps an unsaved entry edit when another product is added to the meal', async () => {
    let currentEntries = [entry];
    const addedEntry = { ...entry, id: 42, food_name: 'Второй продукт' };
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) {
        return Promise.resolve(makeDay(currentEntries));
      }
      if (path.startsWith('/api/v1/nutrition/foods/recent')) {
        return Promise.resolve({ items: [food], total: 1, limit: 12, offset: 0 });
      }
      if (path.startsWith('/api/v1/nutrition/foods/favorites')) {
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      }
      if (path === '/api/v1/nutrition/diary/entries' && options?.method === 'POST') {
        currentEntries = [...currentEntries, addedEntry];
        return Promise.resolve(addedEntry);
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();
    await screen.findByText('Овсяная каша');

    fireEvent.click(screen.getByRole('button', { name: 'Изменить Овсяная каша' }));
    const breakfast = breakfastSection();
    const draftAmount = within(breakfast).getByRole('spinbutton', { name: 'Количество' });
    fireEvent.change(draftAmount, { target: { value: '175' } });
    fireEvent.click(within(breakfast).getByRole('button', { name: /Добавить/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Добавить Овсяная каша' }));
    fireEvent.click(screen.getByRole('button', { name: 'Добавить в дневник' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(await screen.findByText('Второй продукт')).toBeVisible();
    expect(within(breakfastSection()).getByRole('spinbutton', { name: 'Количество' })).toHaveValue(
      175,
    );
    expect(within(breakfastSection()).getByRole('button', { name: 'Сохранить' })).toBeVisible();
  });

  it('keeps a calories-only Quick Add draft and reuses its idempotency key on retry', async () => {
    let attempts = 0;
    apiMock.mockImplementation(
      (
        path: string,
        options?: { method?: string; body?: unknown; headers?: Record<string, string> },
      ) => {
        if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay([]));
        if (path.startsWith('/api/v1/nutrition/foods/recent'))
          return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
        if (path.startsWith('/api/v1/nutrition/foods/favorites'))
          return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
        if (path === '/api/v1/nutrition/diary/entries' && options?.method === 'POST') {
          attempts += 1;
          if (attempts === 1) return Promise.reject(new Error('Временная ошибка сети'));
          return Promise.resolve({ ...entry, entry_kind: 'quick_add', food_id: null });
        }
        throw new Error(`Unexpected API call: ${path}`);
      },
    );
    renderDiary();
    await screen.findAllByText('Пока без записей');

    fireEvent.click(screen.getByRole('button', { name: /Быстрый ввод/ }));
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Калории' }), {
      target: { value: '530' },
    });
    fireEvent.change(screen.getByLabelText('Время (необязательно)'), {
      target: { value: '13:25' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить Quick Add' }));

    expect(await screen.findByText('Временная ошибка сети')).toBeVisible();
    expect(screen.getByRole('spinbutton', { name: 'Калории' })).toHaveValue(530);
    const firstSubmission = apiMock.mock.calls.find(
      ([path, options]) => path === '/api/v1/nutrition/diary/entries' && options?.method === 'POST',
    );
    expect(firstSubmission?.[1]).toEqual(
      expect.objectContaining({
        body: expect.objectContaining({
          quick_add: {
            name: null,
            energy_kcal: 530,
            protein_g: null,
            fat_g: null,
            carbs_g: null,
          },
          logged_at: '13:25',
        }),
        headers: { 'Idempotency-Key': expect.any(String) },
      }),
    );
    const requestId = firstSubmission?.[1]?.headers?.['Idempotency-Key'];

    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    await waitFor(() => expect(attempts).toBe(2));
    const submissions = apiMock.mock.calls.filter(
      ([path, options]) => path === '/api/v1/nutrition/diary/entries' && options?.method === 'POST',
    );
    expect(submissions[1]?.[1]?.headers?.['Idempotency-Key']).toBe(requestId);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('marks a populated day complete only after explicit confirmation', async () => {
    let complete = false;
    apiMock.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) {
        return Promise.resolve({
          ...makeDay(),
          status: complete ? 'complete' : 'incomplete',
          status_is_explicit: complete,
        });
      }
      if (path === '/api/v1/nutrition/diary/status' && options?.method === 'PUT') {
        complete = true;
        return Promise.resolve({ ...makeDay(), status: 'complete', status_is_explicit: true });
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();
    expect(await screen.findByText('Заполнен частично', { selector: 'strong' })).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'День заполнен' }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/api/v1/nutrition/diary/status', {
        method: 'PUT',
        body: { diary_date: '2026-08-19', status: 'complete' },
      }),
    );
    expect(await screen.findByText('Подтверждено')).toBeVisible();
  });

  it('tracks an explicit incomplete-day confirmation without diary details', async () => {
    const analyticsEvents: ProductEventEnvelope[] = [];
    const listener = (event: Event) => {
      analyticsEvents.push((event as CustomEvent<ProductEventEnvelope>).detail);
    };
    window.addEventListener(PRODUCT_EVENT_NAME, listener);
    apiMock.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay());
      if (path === '/api/v1/nutrition/diary/status' && options?.method === 'PUT') {
        return Promise.resolve({ ...makeDay(), status_is_explicit: true });
      }
      throw new Error(`Unexpected API call: ${path}`);
    });

    renderDiary();
    expect(await screen.findByText('Заполнен частично', { selector: 'strong' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Заполнен частично' }));

    await waitFor(() =>
      expect(
        analyticsEvents.filter((event) => event.name === 'nutrition_incomplete_day_confirmed'),
      ).toHaveLength(1),
    );
    expect(analyticsEvents.at(-1)).not.toHaveProperty('diary_date');
    expect(analyticsEvents.at(-1)).not.toHaveProperty('energy_kcal');
    window.removeEventListener(PRODUCT_EVENT_NAME, listener);
  });

  it('keeps the quantity draft through a recoverable failure and remount', async () => {
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay([]));
      if (path.startsWith('/api/v1/nutrition/foods/recent')) {
        return Promise.resolve({ items: [food], total: 1, limit: 12, offset: 0 });
      }
      if (path.startsWith('/api/v1/nutrition/foods/favorites')) {
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      }
      if (path === '/api/v1/nutrition/diary/entries' && options?.method === 'POST') {
        return Promise.reject(new Error('Соединение прервано'));
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    const first = renderDiary();
    await screen.findAllByText('Пока без записей');
    fireEvent.click(within(breakfastSection()).getByRole('button', { name: /Добавить/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Добавить Овсяная каша' }));
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Количество' }), {
      target: { value: '2.5' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Добавить в дневник' }));

    expect(await screen.findByText('Соединение прервано')).toBeVisible();
    expect(screen.getByRole('spinbutton', { name: 'Количество' })).toHaveValue(2.5);
    const storedDraft = JSON.parse(
      localStorage.getItem('fit_food_draft_10_2026-08-19_breakfast') ?? '{}',
    );
    expect(storedDraft.food).toEqual({
      id: 7,
      name: 'Овсяная каша',
      brand: null,
      food_type: 'system',
      energy_kcal_per_100g: '420.00',
      protein_g_per_100g: '18.500',
      fat_g_per_100g: '12.000',
      carbs_g_per_100g: '54.000',
      standard_serving_weight_g: '50.000',
    });
    expect(storedDraft.food).not.toHaveProperty('barcode');
    expect(storedDraft.food).not.toHaveProperty('last_used_at');
    first.unmount();

    renderDiary();
    await screen.findAllByText('Пока без записей');
    fireEvent.click(within(breakfastSection()).getByRole('button', { name: /Добавить/ }));
    expect(await screen.findByRole('spinbutton', { name: 'Количество' })).toHaveValue(2.5);
    expect(screen.getByRole('heading', { name: 'Овсяная каша' })).toBeVisible();
  });

  it('edits and deletes an entry with explicit confirmation', async () => {
    let currentEntries = [entry];
    apiMock.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) {
        return Promise.resolve(makeDay(currentEntries));
      }
      if (path.endsWith('/entries/41') && options?.method === 'PATCH') {
        currentEntries = [{ ...entry, amount: '150.000', weight_g: '150.000' }];
        return Promise.resolve(currentEntries[0]);
      }
      if (path.endsWith('/entries/41') && options?.method === 'DELETE') {
        currentEntries = [];
        return Promise.resolve(undefined);
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();
    await screen.findByText('Овсяная каша');

    fireEvent.click(screen.getByRole('button', { name: 'Изменить Овсяная каша' }));
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Количество' }), {
      target: { value: '150' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/diary/entries/41',
        expect.objectContaining({ method: 'PATCH', body: { amount: 150, amount_unit: 'g' } }),
      ),
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Удалить Овсяная каша' }));
    const confirmDialog = await screen.findByRole('dialog', { name: 'Удалить запись?' });
    fireEvent.click(within(confirmDialog).getByRole('button', { name: 'Удалить' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/api/v1/nutrition/diary/entries/41', {
        method: 'DELETE',
      }),
    );
    await waitFor(() => expect(screen.queryByText('Овсяная каша')).not.toBeInTheDocument());
  });

  it('retries the day and keeps favorites usable when recent products fail', async () => {
    let diaryAttempts = 0;
    apiMock.mockImplementation((path: string) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) {
        diaryAttempts += 1;
        return diaryAttempts === 1
          ? Promise.reject(new Error('Дневник недоступен'))
          : Promise.resolve(makeDay([]));
      }
      if (path.startsWith('/api/v1/nutrition/foods/recent')) {
        return Promise.reject(new Error('Недавние недоступны'));
      }
      if (path.startsWith('/api/v1/nutrition/foods/favorites')) {
        return Promise.resolve({ items: [food], total: 1, limit: 12, offset: 0 });
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();

    expect(await screen.findByText('Дневник недоступен')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    await screen.findAllByText('Пока без записей');
    fireEvent.click(within(breakfastSection()).getByRole('button', { name: /Добавить/ }));
    expect(
      await screen.findByText('Локальный каталог сейчас не ответил. Попробуйте снова.'),
    ).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Избранное' }));
    expect(await screen.findByRole('button', { name: 'Добавить Овсяная каша' })).toBeVisible();
  });

  it('ignores a stale local search and keeps an unavailable external provider optional', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let staleSignal: AbortSignal | undefined;
    apiMock.mockImplementation((path: string, options?: { signal?: AbortSignal }) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay([]));
      if (path.startsWith('/api/v1/nutrition/foods/recent'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      if (path.startsWith('/api/v1/nutrition/foods/favorites'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      const decoded = decodeURIComponent(path);
      if (decoded.includes('q=ов&')) {
        staleSignal = options?.signal;
        return new Promise(() => undefined);
      }
      if (decoded.includes('q=тофу') && decoded.includes('include_external=true')) {
        return Promise.resolve({
          items: [],
          external_items: [],
          total: 0,
          limit: 20,
          offset: 0,
          provider_status: 'unavailable',
        });
      }
      if (decoded.includes('q=тофу')) {
        return Promise.resolve({
          items: [],
          external_items: [],
          total: 0,
          limit: 20,
          offset: 0,
          provider_status: 'not_requested',
        });
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();
    await screen.findAllByText('Пока без записей');
    fireEvent.click(within(breakfastSection()).getByRole('button', { name: /Добавить/ }));
    const search = screen.getByRole('searchbox', { name: 'Поиск по названию или бренду' });
    fireEvent.change(search, { target: { value: 'ов' } });
    await act(() => vi.advanceTimersByTimeAsync(250));
    await waitFor(() => expect(staleSignal).toBeDefined());
    fireEvent.change(search, { target: { value: 'тофу' } });
    await act(() => vi.advanceTimersByTimeAsync(250));

    await waitFor(() => expect(staleSignal?.aborted).toBe(true));
    expect(
      await screen.findByText(
        'Внешний каталог временно недоступен. Локальные продукты продолжают работать.',
      ),
    ).toBeVisible();
    expect(screen.queryByText(/429|timeout/i)).not.toBeInTheDocument();
  });

  it('automatically shows real external matches when the local search is empty', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const importedFood: Food = {
      ...food,
      id: 82,
      name: 'Nutella hazelnut spread',
      brand: 'Ferrero',
      barcode: '3017620422003',
      food_type: 'user',
      is_favorite: false,
      standard_serving_weight_g: null,
    };
    apiMock.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay([]));
      if (path.startsWith('/api/v1/nutrition/foods/recent'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      if (path.startsWith('/api/v1/nutrition/foods/favorites'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      const decoded = decodeURIComponent(path);
      if (decoded.includes('q=нутелла') && decoded.includes('include_external=true')) {
        return Promise.resolve({
          items: [],
          external_items: [
            {
              name: 'Nutella hazelnut spread',
              brand: 'Ferrero',
              barcode: '3017620422003',
              energy_kcal_per_100g: '539.00',
              protein_g_per_100g: '6.300',
              fat_g_per_100g: '30.900',
              carbs_g_per_100g: '57.500',
              fiber_g_per_100g: null,
              standard_serving_amount: null,
              standard_serving_unit: null,
              standard_serving_weight_g: null,
              external_id: '3017620422003',
              source: {
                provider: 'open_food_facts',
                attribution: 'Open Food Facts contributors',
                source_url: 'https://world.openfoodfacts.org/product/3017620422003',
                license: 'ODbL-1.0',
                license_url: 'https://opendatacommons.org/licenses/odbl/1-0/',
              },
            },
          ],
          total: 0,
          limit: 20,
          offset: 0,
          provider_status: 'available',
        });
      }
      if (decoded.includes('q=нутелла')) {
        return Promise.resolve({
          items: [],
          external_items: [],
          total: 0,
          limit: 20,
          offset: 0,
          provider_status: 'not_requested',
        });
      }
      if (path === '/api/v1/nutrition/foods' && options?.method === 'POST') {
        return Promise.resolve(importedFood);
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();
    await screen.findAllByText('Пока без записей');
    fireEvent.click(within(breakfastSection()).getByRole('button', { name: /Добавить/ }));
    const barcodeEntry = screen.getByRole('button', { name: 'Поиск по штрихкоду' });
    const nameSearch = screen.getByRole('searchbox', { name: 'Поиск по названию или бренду' });
    expect(
      barcodeEntry.compareDocumentPosition(nameSearch) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    fireEvent.change(nameSearch, {
      target: { value: 'нутелла' },
    });
    await act(() => vi.advanceTimersByTimeAsync(250));

    expect(await screen.findByText('Nutella hazelnut spread')).toBeVisible();
    expect(screen.getByText(/Ferrero/)).toBeVisible();
    expect(screen.getByRole('link', { name: 'Источник' })).toHaveAttribute(
      'href',
      'https://world.openfoodfacts.org/product/3017620422003',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Выбрать продукт' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/foods',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({
            name: 'Nutella hazelnut spread',
            brand: 'Ferrero',
            barcode: '3017620422003',
            energy_kcal_per_100g: '539.00',
          }),
        }),
      ),
    );
    expect(await screen.findByRole('heading', { name: 'Nutella hazelnut spread' })).toBeVisible();
    expect(screen.getByRole('spinbutton', { name: 'Количество' })).toHaveValue(100);
  });

  it('supplements local search with a generic no-barcode result during partial provider failure', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const localFood: Food = { ...food, id: 91, name: 'Рис домашний' };
    const importedFood: Food = {
      ...food,
      id: 92,
      name: 'Рис белый приготовленный, без добавления масла',
      brand: null,
      barcode: null,
      food_type: 'user',
      is_favorite: false,
      standard_serving_weight_g: null,
    };
    apiMock.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay([]));
      if (path.startsWith('/api/v1/nutrition/foods/recent'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      if (path.startsWith('/api/v1/nutrition/foods/favorites'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      const decoded = decodeURIComponent(path);
      if (decoded.includes('q=рис') && decoded.includes('include_external=true')) {
        return Promise.resolve({
          items: [localFood],
          external_items: [
            {
              name: 'Рис белый приготовленный, без добавления масла',
              brand: null,
              barcode: null,
              energy_kcal_per_100g: '130.00',
              protein_g_per_100g: '2.700',
              fat_g_per_100g: '0.300',
              carbs_g_per_100g: '28.000',
              fiber_g_per_100g: '0.400',
              standard_serving_amount: null,
              standard_serving_unit: null,
              standard_serving_weight_g: null,
              external_id: '2708360',
              source: {
                provider: 'usda_fdc',
                attribution: 'U.S. Department of Agriculture, FoodData Central',
                source_url: 'https://fdc.nal.usda.gov/fdc-app.html#/food-details/2708360/nutrients',
                license: 'CC0-1.0',
                license_url: 'https://creativecommons.org/publicdomain/zero/1.0/',
              },
            },
          ],
          total: 1,
          limit: 20,
          offset: 0,
          provider_status: 'available',
          provider_statuses: [
            { provider: 'open_food_facts', status: 'unavailable', result_count: 0 },
            { provider: 'usda_fdc', status: 'available', result_count: 1 },
          ],
        });
      }
      if (decoded.includes('q=рис')) {
        return Promise.resolve({
          items: [localFood],
          external_items: [],
          total: 1,
          limit: 20,
          offset: 0,
          provider_status: 'not_requested',
          provider_statuses: [],
        });
      }
      if (path === '/api/v1/nutrition/foods' && options?.method === 'POST') {
        return Promise.resolve(importedFood);
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();
    await screen.findAllByText('Пока без записей');
    fireEvent.click(within(breakfastSection()).getByRole('button', { name: /Добавить/ }));
    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск по названию или бренду' }), {
      target: { value: 'рис' },
    });
    await act(() => vi.advanceTimersByTimeAsync(250));

    expect(await screen.findByRole('button', { name: 'Добавить Рис домашний' })).toBeVisible();
    expect(await screen.findByText('Рис белый приготовленный, без добавления масла')).toBeVisible();
    expect(
      screen.getByText(
        'Часть внешних источников временно недоступна; показаны результаты остальных.',
      ),
    ).toBeVisible();
    expect(screen.queryByText(/штрихкод отсутствует/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Выбрать продукт' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/foods',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({
            barcode: null,
            external_source: expect.objectContaining({
              provider: 'usda_fdc',
              external_id: '2708360',
              license: 'CC0-1.0',
            }),
          }),
        }),
      ),
    );
    expect(
      await screen.findByRole('heading', {
        name: 'Рис белый приготовленный, без добавления масла',
      }),
    ).toBeVisible();
  });

  it('validates and creates an own food before selecting its serving', async () => {
    const ownFood = {
      ...food,
      id: 81,
      name: 'Домашний хлеб',
      food_type: 'user' as const,
      is_favorite: false,
      standard_serving_weight_g: '35.000',
    };
    apiMock.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay([]));
      if (path.startsWith('/api/v1/nutrition/foods/recent'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      if (path.startsWith('/api/v1/nutrition/foods/favorites'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      if (path === '/api/v1/nutrition/foods' && options?.method === 'POST')
        return Promise.resolve(ownFood);
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();
    await screen.findAllByText('Пока без записей');
    fireEvent.click(within(breakfastSection()).getByRole('button', { name: /Добавить/ }));
    fireEvent.click(screen.getByRole('button', { name: /Свой продукт/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Создать продукт' }));
    expect(await screen.findByText('Введите название продукта')).toBeVisible();
    expect(apiMock).not.toHaveBeenCalledWith('/api/v1/nutrition/foods', expect.anything());

    fireEvent.change(screen.getByRole('textbox', { name: 'Название *' }), {
      target: { value: 'Домашний хлеб' },
    });
    for (const [name, value] of [
      ['Калории *', '240'],
      ['Белки *', '8'],
      ['Жиры *', '3'],
      ['Углеводы *', '45'],
      ['Вес одной порции', '35'],
    ]) {
      fireEvent.change(screen.getByRole('spinbutton', { name }), { target: { value } });
    }
    fireEvent.click(screen.getByRole('button', { name: 'Создать продукт' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/foods',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({
            name: 'Домашний хлеб',
            standard_serving_amount: 1,
            standard_serving_unit: 'serving',
            standard_serving_weight_g: 35,
          }),
        }),
      ),
    );
    expect(await screen.findByRole('heading', { name: 'Домашний хлеб' })).toBeVisible();
    expect(screen.getByRole('spinbutton', { name: 'Количество' })).toHaveValue(1);
  });

  it('uses recipe totals and adds an explicit gram serving to the diary', async () => {
    const recipe = {
      id: 9,
      name: 'Омлет с сыром',
      ingredients: [
        {
          id: 1,
          position: 0,
          food_id: 7,
          food_name: 'Яйцо',
          food_brand: null,
          amount: '180.000',
          amount_unit: 'g' as const,
          weight_g: '180.000',
          serving_amount: null,
          serving_unit: null,
          serving_weight_g: null,
          nutrition,
        },
      ],
      ingredients_weight_g: '180.000',
      final_weight_g: '160.000',
      effective_weight_g: '160.000',
      totals: nutrition,
      nutrients_per_100g: {
        energy_kcal_per_100g: '262.50',
        protein_g_per_100g: '11.563',
        fat_g_per_100g: '7.500',
        carbs_g_per_100g: '33.750',
        fiber_g_per_100g: '4.375',
      },
      created_at: '2026-08-19T08:00:00Z',
      updated_at: '2026-08-19T08:00:00Z',
    };
    apiMock.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay([]));
      if (path.startsWith('/api/v1/nutrition/foods/recent'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      if (path.startsWith('/api/v1/nutrition/foods/favorites'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      if (path.startsWith('/api/v1/nutrition/recipes'))
        return Promise.resolve({ items: [recipe], total: 1, limit: 50, offset: 0 });
      if (path === '/api/v1/nutrition/diary/entries' && options?.method === 'POST')
        return Promise.resolve(entry);
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();
    await screen.findAllByText('Пока без записей');
    fireEvent.click(within(breakfastSection()).getByRole('button', { name: /Добавить/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Рецепты' }));
    expect(await screen.findByText(/1 продуктов · 160 г/)).toBeVisible();
    expect(screen.getByText(/263 ккал/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Добавить рецепт Омлет с сыром' }));
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Порция готового блюда, г' }), {
      target: { value: '140' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Добавить в дневник' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/diary/entries',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({ recipe_id: 9, amount: 140, amount_unit: 'g' }),
        }),
      ),
    );
  });

  it('copies a product with an explicit target and blocks double submit', async () => {
    const targetDate = dateInputValue(new Date(), 'Europe/Moscow');
    let resolveCopy: ((value: unknown) => void) | undefined;
    const copyPromise = new Promise((resolve) => {
      resolveCopy = resolve;
    });
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay());
      if (path.endsWith('/copy/product') && options?.method === 'POST') return copyPromise;
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();
    await screen.findByText('Овсяная каша');
    fireEvent.click(screen.getByRole('button', { name: 'Повторить Овсяная каша' }));
    expect(await screen.findByText('Овсяная каша', { selector: 'dd' })).toBeVisible();
    const submit = screen.getByRole('button', { name: 'Повторить продукт' });
    fireEvent.click(submit);
    fireEvent.click(submit);
    await waitFor(() =>
      expect(
        apiMock.mock.calls.filter(([path]) => String(path).endsWith('/copy/product')),
      ).toHaveLength(1),
    );
    const [, request] = apiMock.mock.calls.find(([path]) =>
      String(path).endsWith('/copy/product'),
    )!;
    expect(request).toEqual(
      expect.objectContaining({
        headers: { 'Idempotency-Key': expect.any(String) },
        body: {
          source_date: '2026-08-19',
          target_date: targetDate,
          source_entry_id: 41,
          source_meal_type: 'breakfast',
          target_meal_type: 'breakfast',
        },
      }),
    );
    resolveCopy?.({
      copy_scope: 'product',
      source_date: '2026-08-19',
      source_meal_type: 'breakfast',
      target_date: targetDate,
      target_meal_type: 'breakfast',
      entries: [entry],
      replayed: false,
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('handles barcode not found and continues with a prefilled manual product', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay([]));
      if (path.startsWith('/api/v1/nutrition/foods/recent'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      if (path.startsWith('/api/v1/nutrition/foods/favorites'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      if (path.endsWith('/foods/barcode/3017620422003'))
        return Promise.resolve({
          barcode: '3017620422003',
          status: 'not_found',
          source: null,
          local_item: null,
          external_item: null,
          provider_status: 'unavailable',
        });
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();
    await screen.findAllByText('Пока без записей');
    fireEvent.click(within(breakfastSection()).getByRole('button', { name: /Добавить/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Поиск по штрихкоду' }));
    expect(screen.queryByRole('button', { name: 'Сканировать камерой' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Найти' })).toHaveClass('ui-button--primary');
    fireEvent.change(screen.getByRole('textbox', { name: 'Штрихкод' }), {
      target: { value: '3017620422003' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Найти' }));
    expect(await screen.findByText('Продукт не найден')).toBeVisible();
    expect(screen.queryByText(/timeout|429/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Создать свой продукт' }));
    expect(screen.getByRole('textbox', { name: 'Штрихкод' })).toHaveValue('3017620422003');
  });

  it('uses local barcode results and keeps external results read-only with attribution', async () => {
    const externalFood = {
      name: 'Шоколадная паста',
      brand: 'Example',
      barcode: '3017620422003',
      energy_kcal_per_100g: '539.00',
      protein_g_per_100g: '6.300',
      fat_g_per_100g: '30.900',
      carbs_g_per_100g: '57.500',
      fiber_g_per_100g: null,
      standard_serving_amount: null,
      standard_serving_unit: null,
      standard_serving_weight_g: null,
      external_id: '3017620422003',
      source: {
        provider: 'open_food_facts',
        attribution: 'Open Food Facts contributors',
        source_url: 'https://world.openfoodfacts.org/product/3017620422003',
        license: 'ODbL-1.0',
        license_url: 'https://opendatacommons.org/licenses/odbl/1-0/',
      },
    };
    apiMock.mockImplementation((path: string) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay([]));
      if (path.startsWith('/api/v1/nutrition/foods/recent'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      if (path.startsWith('/api/v1/nutrition/foods/favorites'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      if (path.endsWith('/foods/barcode/4006381333931'))
        return Promise.resolve({
          barcode: '4006381333931',
          status: 'found',
          source: 'local',
          local_item: food,
          external_item: null,
          provider_status: 'not_needed',
        });
      if (path.endsWith('/foods/barcode/3017620422003'))
        return Promise.resolve({
          barcode: '3017620422003',
          status: 'found',
          source: 'external',
          local_item: null,
          external_item: externalFood,
          provider_status: 'available',
        });
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderDiary();
    await screen.findAllByText('Пока без записей');
    fireEvent.click(within(breakfastSection()).getByRole('button', { name: /Добавить/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Поиск по штрихкоду' }));
    expect(screen.queryByRole('button', { name: 'Сканировать камерой' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Найти' })).toHaveClass('ui-button--primary');
    const barcode = screen.getByRole('textbox', { name: 'Штрихкод' });
    fireEvent.change(barcode, { target: { value: '4006381333931' } });
    fireEvent.click(screen.getByRole('button', { name: 'Найти' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Выбрать продукт' }));
    expect(await screen.findByRole('heading', { name: 'Овсяная каша' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: /Выбрать другое/ }));

    fireEvent.change(screen.getByRole('textbox', { name: 'Штрихкод' }), {
      target: { value: '3017620422003' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Найти' }));
    expect(await screen.findByText('Шоколадная паста')).toBeVisible();
    expect(screen.getByRole('link', { name: /Open Food Facts contributors/ })).toHaveAttribute(
      'href',
      'https://opendatacommons.org/licenses/odbl/1-0/',
    );
    expect(screen.queryByRole('button', { name: /Выбрать продукт/ })).not.toBeInTheDocument();
  });

  it('explains denied camera permission and preserves manual barcode input', async () => {
    const originalMediaDevices = navigator.mediaDevices;
    const originalDetector = (globalThis as typeof globalThis & { BarcodeDetector?: unknown })
      .BarcodeDetector;
    Object.defineProperty(globalThis, 'BarcodeDetector', {
      configurable: true,
      value: class {
        detect() {
          return Promise.resolve([]);
        }
      },
    });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockRejectedValue(new DOMException('Denied', 'NotAllowedError')),
      },
    });
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation((query: string) => ({
        matches: query === '(hover: none) and (pointer: coarse)',
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
    apiMock.mockImplementation((path: string) => {
      if (path.startsWith('/api/v1/nutrition/diary?')) return Promise.resolve(makeDay([]));
      if (path.startsWith('/api/v1/nutrition/foods/recent'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      if (path.startsWith('/api/v1/nutrition/foods/favorites'))
        return Promise.resolve({ items: [], total: 0, limit: 12, offset: 0 });
      throw new Error(`Unexpected API call: ${path}`);
    });
    try {
      renderDiary();
      await screen.findAllByText('Пока без записей');
      fireEvent.click(within(breakfastSection()).getByRole('button', { name: /Добавить/ }));
      fireEvent.click(screen.getByRole('button', { name: 'Поиск по штрихкоду' }));
      const scan = screen.getByRole('button', { name: 'Сканировать камерой' });
      expect(scan).toHaveClass('ui-button--primary');
      expect(screen.getByRole('button', { name: 'Найти' })).toHaveClass('ui-button--secondary');
      fireEvent.click(scan);
      expect(
        await screen.findByText(
          'Доступ к камере запрещён. Разрешите его в настройках браузера или введите код вручную.',
        ),
      ).toBeVisible();
      expect(screen.getByRole('textbox', { name: 'Штрихкод' })).toBeEnabled();
    } finally {
      Object.defineProperty(navigator, 'mediaDevices', {
        configurable: true,
        value: originalMediaDevices,
      });
      Object.defineProperty(globalThis, 'BarcodeDetector', {
        configurable: true,
        value: originalDetector,
      });
      vi.unstubAllGlobals();
    }
  });
});
