import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FoodPickerDialog } from '../../../../src/features/nutrition/FoodPickerDialog';
import { ApiError } from '../../../../src/shared/api/client';
import type { Food } from '../../../../src/shared/api/types';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', () => ({
  api: apiMock,
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public status = 0,
    ) {
      super(message);
    }
  },
}));
vi.mock('../../../../src/app/AuthProvider', () => ({ useAuth: () => ({ user: { id: 10 } }) }));

const baseFood: Food = {
  id: 1,
  name: 'Йогурт натуральный',
  brand: 'Марка А',
  barcode: null,
  energy_kcal_per_100g: '60.00',
  protein_g_per_100g: '3.000',
  fat_g_per_100g: '2.000',
  carbs_g_per_100g: '4.000',
  fiber_g_per_100g: null,
  nutrition_basis_kind: 'per_100_g',
  nutrition_basis_amount: '100',
  nutrition_basis_unit: 'g',
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
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};
const foods = [baseFood, { ...baseFood, id: 2, brand: 'Марка Б' }];
const preview = {
  energy_kcal: '120.00',
  protein_g: null,
  fat_g: '4.000',
  carbs_g: '8.000',
  fiber_g: null,
};

function renderPicker(onClose = vi.fn(), demoSafeMode = false) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <FoodPickerDialog
          diaryDate="2026-08-19"
          mealType="breakfast"
          onClose={onClose}
          demoSafeMode={demoSafeMode}
        />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('FoodPicker batch selection', () => {
  beforeEach(() => {
    localStorage.clear();
    apiMock.mockReset();
  });
  afterEach(() => cleanup());

  it('keeps distinct brands and retries the same confirmed payload after a lost response', async () => {
    let rejectFirst: ((error: Error) => void) | undefined;
    let attempts = 0;
    apiMock.mockImplementation((path: string) => {
      if (
        path.startsWith('/api/v1/nutrition/foods/recent') ||
        path.startsWith('/api/v1/nutrition/foods/search')
      )
        return Promise.resolve({ items: foods, total: foods.length, limit: 20, offset: 0 });
      if (path === '/api/v1/nutrition/diary/batch/preview') return Promise.resolve(preview);
      if (path === '/api/v1/nutrition/diary/natural-input/commit') {
        attempts += 1;
        if (attempts === 1)
          return new Promise((_resolve, reject) => {
            rejectFirst = reject;
          });
        return Promise.resolve({
          operation_kind: 'natural_input',
          diary_date: '2026-08-19',
          meal_type: 'breakfast',
          entries: [],
          replayed: true,
        });
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    const first = renderPicker();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Выбрать Йогурт натуральный, Марка А в подборку' }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Выбрать Йогурт натуральный, Марка Б в подборку' }),
    );
    expect(
      screen.getByRole('button', { name: 'Выбрать Йогурт натуральный, Марка А' }),
    ).toBeVisible();
    expect(
      screen.getByRole('button', { name: 'Выбрать Йогурт натуральный, Марка Б' }),
    ).toBeVisible();
    expect(await screen.findByText(/Клетчатка — г/)).toBeVisible();
    expect(apiMock.mock.calls.filter(([path]) => path.endsWith('/commit'))).toHaveLength(0);
    const confirm = screen.getByRole('button', { name: 'Добавить в дневник' });
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await waitFor(() => expect(attempts).toBe(1));
    const firstRequest = apiMock.mock.calls.find(([path]) => path.endsWith('/commit'))?.[1];
    expect(firstRequest.body.items.map((item: { food_id: number }) => item.food_id)).toEqual([
      1, 2,
    ]);
    rejectFirst?.(new Error('Соединение прервано'));
    expect(await screen.findByText(/Не удалось узнать результат/)).toBeVisible();
    expect(
      screen.getByRole('button', { name: 'Убрать Йогурт натуральный, Марка А из подборки' }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть добавление' }));
    first.unmount();
    const onClose = vi.fn();
    renderPicker(onClose);
    const retry = await screen.findByRole('button', { name: 'Повторить подтверждение' });
    fireEvent.click(retry);
    await waitFor(() => expect(attempts).toBe(2));
    const requests = apiMock.mock.calls.filter(([path]) => path.endsWith('/commit'));
    expect(requests[1]?.[1].headers).toEqual(firstRequest.headers);
    expect(requests[1]?.[1].body).toEqual(firstRequest.body);
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(localStorage.getItem('fit_food_draft_10_2026-08-19_breakfast_batch')).toBeNull();
  });

  it('edits and removes one product without clearing the search and blocks invalid amounts', async () => {
    apiMock.mockImplementation((path: string) => {
      if (
        path.startsWith('/api/v1/nutrition/foods/recent') ||
        path.startsWith('/api/v1/nutrition/foods/search')
      )
        return Promise.resolve({ items: foods, total: foods.length, limit: 20, offset: 0 });
      if (path === '/api/v1/nutrition/diary/batch/preview') return Promise.resolve(preview);
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderPicker();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Выбрать Йогурт натуральный, Марка А в подборку' }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Выбрать Йогурт натуральный, Марка Б в подборку' }),
    );
    const search = screen.getByRole('searchbox', { name: 'Найти продукт' });
    fireEvent.change(search, { target: { value: 'йогурт' } });
    fireEvent.click(screen.getByText('Подборка · 2'));
    const amount = screen.getByRole('spinbutton', {
      name: 'Количество: Йогурт натуральный, Марка А, Проверено YFC',
    });
    fireEvent.change(amount, { target: { value: '0' } });
    expect(screen.getByText('Введите количество больше нуля.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Добавить в дневник' })).toBeDisabled();
    fireEvent.change(amount, { target: { value: '150' } });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'Убрать Йогурт натуральный, Марка Б, Проверено YFC из подборки',
      }),
    );
    expect(search).toHaveValue('йогурт');
    expect(screen.getByText('Подборка · 1')).toBeVisible();
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/diary/batch/preview',
        expect.objectContaining({
          body: expect.objectContaining({
            items: [expect.objectContaining({ food_id: 1, amount: '150' })],
          }),
        }),
      ),
    );
  });

  it('labels calories with their actual basis for products specified per serving', async () => {
    const items: Food[] = [
      {
        ...baseFood,
        name: 'Порция с известной массой',
        energy_kcal_per_100g: '500',
        nutrition_basis_kind: 'per_serving',
        canonical_facts: {
          normalized_facts: {
            energy_kcal: { value: '500', basis_ref: 'per_100_g' },
            protein_g: { value: '20', basis_ref: 'per_100_g' },
            fat_g: { value: '10', basis_ref: 'per_100_g' },
            carbohydrate_g: { value: '60', basis_ref: 'per_100_g' },
          },
          source_facts: {
            energy_kcal: [{ value: '250', basis_ref: 'per_serving', evidence: 'read' }],
            protein_g: [{ value: '10', basis_ref: 'per_serving', evidence: 'read' }],
          },
        },
      },
      {
        ...baseFood,
        id: 2,
        name: 'Порция без известной массы',
        energy_kcal_per_100g: null,
        nutrition_basis_kind: 'per_serving',
        canonical_facts: {
          normalized_facts: { energy_kcal: null },
          source_facts: {
            energy_kcal: [{ value: '250', basis_ref: 'per_serving', evidence: 'read' }],
            protein_g: [{ value: '10', basis_ref: 'per_serving', evidence: 'read' }],
          },
        },
      },
    ];
    apiMock.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('/batch/preview')
          ? preview
          : { items, total: items.length, limit: 20, offset: 0 },
      ),
    );
    renderPicker();
    expect(await screen.findByText('Марка А · 500 ккал / 100 г')).toBeVisible();
    expect(screen.getByText('Марка А · 250 ккал / порцию')).toBeVisible();
    fireEvent.click(
      screen.getByRole('button', { name: 'Выбрать Порция с известной массой, Марка А в подборку' }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'Выбрать Порция без известной массы, Марка А в подборку',
      }),
    );
    fireEvent.click(screen.getByText('Подборка · 2'));
    expect(screen.getByText(/Б 20 · Ж 10 · У 60 · клетчатка —/)).toBeVisible();
    expect(screen.getByText(/Б 10 · Ж — · У — · клетчатка —/)).toBeVisible();
  });

  it('keeps the supported single-product flow in demo without offering batch actions', async () => {
    apiMock.mockResolvedValue({ items: foods, total: foods.length, limit: 20, offset: 0 });
    renderPicker(vi.fn(), true);
    const single = await screen.findByRole('button', {
      name: 'Выбрать Йогурт натуральный, Марка А',
    });
    expect(screen.queryByText('Подборка · 0')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /в подборку/ })).not.toBeInTheDocument();
    fireEvent.click(single);
    expect(screen.getByRole('spinbutton', { name: /Количество/ })).toBeVisible();
    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/batch/preview'))).toBe(false);
  });

  it('blocks confirmation when a selected item cannot be previewed and allows a retry', async () => {
    let previews = 0;
    apiMock.mockImplementation((path: string) => {
      if (path.startsWith('/api/v1/nutrition/foods/'))
        return Promise.resolve({ items: foods, total: foods.length, limit: 20, offset: 0 });
      if (path.endsWith('/batch/preview')) {
        previews += 1;
        return previews === 1 ? Promise.reject(new Error('Недоступно')) : Promise.resolve(preview);
      }
      throw new Error(`Unexpected API call: ${path}`);
    });
    renderPicker();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Выбрать Йогурт натуральный, Марка А в подборку' }),
    );
    const retry = await screen.findByRole('button', { name: 'Повторить расчёт' });
    expect(screen.getByRole('button', { name: 'Добавить в дневник' })).toBeDisabled();
    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/commit'))).toBe(false);
    fireEvent.click(retry);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Добавить в дневник' })).toBeEnabled(),
    );
  });

  it('does not offer a serving based only on grams for a product measured in millilitres', async () => {
    const liquid: Food = {
      ...baseFood,
      nutrition_basis_kind: 'per_100_ml',
      nutrition_basis_unit: 'ml',
      standard_serving_weight_g: '50',
    };
    apiMock.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('/batch/preview')
          ? preview
          : { items: [liquid], total: 1, limit: 20, offset: 0 },
      ),
    );
    renderPicker();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Выбрать Йогурт натуральный, Марка А в подборку' }),
    );
    fireEvent.click(screen.getByText('Подборка · 1'));
    const units = screen.getByRole('combobox', {
      name: 'Единица: Йогурт натуральный, Марка А, Проверено YFC',
    });
    expect(units).toHaveValue('ml');
    expect(units.querySelectorAll('option')).toHaveLength(1);
  });

  it('does not reuse a barcode match from a different external source', async () => {
    const external = {
      ...baseFood,
      barcode: '1234567890123',
      external_id: 'fdc-2',
      source: {
        provider: 'usda_fdc',
        attribution: 'USDA',
        source_url: 'https://example.com/food',
        license: 'CC0',
        license_url: 'https://example.com/license',
      },
    };
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/nutrition/foods') return Promise.reject(new ApiError('conflict', 409));
      if (path.includes('/foods/barcode/'))
        return Promise.resolve({
          local_item: {
            ...baseFood,
            barcode: external.barcode,
            source_name: 'open_food_facts',
            external_id: 'other',
          },
        });
      if (path.endsWith('include_external=true'))
        return Promise.resolve({
          items: [],
          external_items: [external],
          total: 0,
          provider_status: 'available',
        });
      return Promise.resolve({
        items: [],
        external_items: [],
        total: 0,
        provider_status: 'not_requested',
      });
    });
    renderPicker();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Найти продукт' }), {
      target: { value: 'йогурт' },
    });
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Выбрать Йогурт натуральный, Марка А, USDA fdc-2 в подборку',
      }),
    );
    expect(await screen.findByText(/с таким штрихкодом уже есть с другими данными/)).toBeVisible();
    expect(screen.queryByText('Подборка · 1')).not.toBeInTheDocument();
    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/commit'))).toBe(false);
  });

  it('previews edited grams, millilitres and servings with their own units', async () => {
    const items: Food[] = [
      { ...baseFood, standard_serving_weight_g: '50' },
      {
        ...baseFood,
        id: 2,
        name: 'Напиток',
        nutrition_basis_kind: 'per_100_ml',
        nutrition_basis_unit: 'ml',
        canonical_facts: { serving_size: { amount: '200', unit: 'ml' } },
      },
      {
        ...baseFood,
        id: 3,
        name: 'Блюдо',
        nutrition_basis_kind: 'per_serving',
        nutrition_basis_unit: 'serving',
      },
    ];
    apiMock.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('/batch/preview')
          ? preview
          : { items, total: items.length, limit: 20, offset: 0 },
      ),
    );
    renderPicker();
    for (const item of items)
      fireEvent.click(
        await screen.findByRole('button', { name: `Выбрать ${item.name}, Марка А в подборку` }),
      );
    fireEvent.click(screen.getByText('Подборка · 3'));
    fireEvent.change(
      screen.getByRole('combobox', { name: 'Единица: Йогурт натуральный, Марка А, Проверено YFC' }),
      { target: { value: 'g' } },
    );
    fireEvent.change(
      screen.getByRole('spinbutton', {
        name: 'Количество: Йогурт натуральный, Марка А, Проверено YFC',
      }),
      { target: { value: '150' } },
    );
    const liquidUnit = screen.getByRole('combobox', {
      name: 'Единица: Напиток, Марка А, Проверено YFC',
    });
    fireEvent.change(liquidUnit, { target: { value: 'serving' } });
    fireEvent.change(liquidUnit, { target: { value: 'ml' } });
    fireEvent.change(
      screen.getByRole('spinbutton', { name: 'Количество: Напиток, Марка А, Проверено YFC' }),
      { target: { value: '250' } },
    );
    fireEvent.change(
      screen.getByRole('spinbutton', { name: 'Количество: Блюдо, Марка А, Проверено YFC' }),
      { target: { value: '2' } },
    );
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/diary/batch/preview',
        expect.objectContaining({
          body: expect.objectContaining({
            items: [
              expect.objectContaining({ food_id: 1, amount: '150', amount_unit: 'g' }),
              expect.objectContaining({ food_id: 2, amount: '250', amount_unit: 'ml' }),
              expect.objectContaining({ food_id: 3, amount: '2', amount_unit: 'serving' }),
            ],
          }),
        }),
      ),
    );
  });

  it('discards an unconfirmed selection on close and reopens without diary writes', async () => {
    apiMock.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith('/batch/preview')
          ? preview
          : { items: foods, total: foods.length, limit: 20, offset: 0 },
      ),
    );
    const first = renderPicker();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Выбрать Йогурт натуральный, Марка А в подборку' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть добавление' }));
    first.unmount();
    renderPicker();
    expect(await screen.findByText('Подборка · 0')).toBeVisible();
    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/commit'))).toBe(false);
  });
});
