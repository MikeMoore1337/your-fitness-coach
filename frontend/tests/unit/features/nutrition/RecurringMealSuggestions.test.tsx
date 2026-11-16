import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RecurringMealSuggestions } from '../../../../src/features/nutrition/RecurringMealSuggestions';
import { ApiError } from '../../../../src/shared/api/client';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', () => ({
  api: apiMock,
  ApiError: class extends Error {
    constructor(
      message: string,
      public status: number,
    ) {
      super(message);
    }
  },
}));
vi.mock('../../../../src/shared/telegram/useTelegramOverlayBackButton', () => ({
  useTelegramOverlayBackButton: () => {},
}));
vi.mock('../../../../src/features/nutrition/MealTemplateBrowser', () => ({
  MealTemplateBrowser: ({ initialTemplateId }: { initialTemplateId: number }) => (
    <p>Шаблон {initialTemplateId}</p>
  ),
}));

const source = {
  source_index: 1,
  food_id: 4,
  source: { food: { name: 'Йогурт' }, quantity: '150', amount_unit: 'piece' },
  original_total: { facts: { energy_kcal: { value: '112', unit: 'kcal' } } },
};
const proposal = {
  observed_days: 8,
  items: [
    {
      meal_type: 'breakfast',
      repeat_days: 3,
      occurrences: [
        { date: '2026-11-01', items: [source] },
        {
          date: '2026-11-02',
          items: [
            {
              ...source,
              source_index: 2,
              source: { ...source.source, quantity: '100', amount_unit: 'g' },
            },
          ],
        },
      ],
    },
  ],
};
const review = {
  preview_signature: 'signed',
  items: [
    {
      source,
      item: { amount: '150', amount_unit: 'g' },
      catalog_nutrition: { energy_kcal: '105', protein_g: null, fat_g: null, carbohydrate_g: null },
      comparison: {
        energy_kcal: 'different',
        protein_g: 'unknown',
        fat_g: 'unknown',
        carbohydrate_g: 'unknown',
      },
    },
  ],
};

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RecurringMealSuggestions
        draftId="draft"
        diaryDate="2026-11-13"
        onBack={vi.fn()}
        onClose={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

async function choose() {
  fireEvent.click(await screen.findByRole('button', { name: 'Проверить состав' }));
}

describe('recurring meal review', () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation(async (path: string) =>
      path.endsWith('/review') ? review : proposal,
    );
  });
  afterEach(cleanup);

  it('requires an explicit unit and updates the portion for a different source day', async () => {
    mount();
    await choose();
    fireEvent.click(screen.getByRole('button', { name: 'Сравнить КБЖУ' }));
    expect(screen.getByRole('alert')).toHaveTextContent('единицу');
    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/review'))).toBe(false);
    fireEvent.click(screen.getByLabelText('2 ноября'));
    expect(screen.getByLabelText('Количество')).toHaveValue('100');
    expect(screen.getByLabelText('Единица')).toHaveValue('g');
    fireEvent.click(screen.getByRole('button', { name: 'Сравнить КБЖУ' }));
    await screen.findAllByText('Расходится');
    expect(screen.getAllByText(/Нельзя сопоставить/).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Сохранить шаблон' })).toBeDisabled();
    expect(apiMock).toHaveBeenCalledWith(
      expect.stringContaining('/review'),
      expect.objectContaining({
        body: expect.objectContaining({
          date: '2026-11-02',
          items: [expect.objectContaining({ source_index: 2, amount: '100', amount_unit: 'g' })],
        }),
      }),
    );
  });

  it('keeps different recurring combinations for the same meal selectable', async () => {
    const second = {
      ...proposal.items[0],
      occurrences: [
        {
          date: '2026-11-03',
          items: [
            { ...source, source: { ...source.source, food: { name: 'Каша' }, amount_unit: 'g' } },
          ],
        },
      ],
    };
    apiMock.mockResolvedValue({ ...proposal, items: [...proposal.items, second] });
    mount();
    const buttons = await screen.findAllByRole('button', { name: 'Проверить состав' });
    expect(buttons).toHaveLength(2);
    fireEvent.click(buttons[1]!);
    expect(screen.getByText('Каша')).toBeVisible();
  });

  it('retries an uncertain confirmation with exactly the same reviewed payload and opens an existing template', async () => {
    let attempts = 0;
    apiMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/review')) return review;
      if (path.endsWith('/confirm')) {
        attempts += 1;
        if (attempts === 1) throw new Error('connection lost');
        return { existing: true, template: { id: 77, name: 'Завтрак' } };
      }
      return proposal;
    });
    mount();
    await choose();
    fireEvent.change(screen.getByLabelText('Количество'), { target: { value: '150' } });
    fireEvent.change(screen.getByLabelText('Единица'), { target: { value: 'g' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сравнить КБЖУ' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: /Я проверил данные/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить шаблон' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Проверить результат' }));
    await screen.findByText('Такой шаблон уже сохранён');
    const calls = apiMock.mock.calls.filter(([path]) => path.endsWith('/confirm'));
    expect(calls).toHaveLength(2);
    expect(calls[0]![1].body).toEqual(calls[1]![1].body);
    expect(calls[0]![1].body).toMatchObject({
      preview_signature: 'signed',
      confirmed: true,
      acknowledge_nutrition: true,
    });
    fireEvent.click(screen.getByRole('button', { name: 'Открыть шаблон' }));
    await waitFor(() => expect(screen.getByText('Шаблон 77')).toBeVisible());
  });

  it('requires a new comparison after the server rejects a stale preview', async () => {
    apiMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/review')) return review;
      if (path.endsWith('/confirm')) throw new ApiError('stale', 409);
      return proposal;
    });
    mount();
    await choose();
    fireEvent.click(screen.getByLabelText('2 ноября'));
    fireEvent.click(screen.getByRole('button', { name: 'Сравнить КБЖУ' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: /Я проверил данные/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить шаблон' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Данные изменились');
    fireEvent.click(screen.getByRole('button', { name: 'Изменить состав' }));
    expect(screen.getByLabelText('Количество')).toHaveValue('100');
    fireEvent.click(screen.getByRole('button', { name: 'Сравнить КБЖУ' }));
    expect(await screen.findByRole('checkbox', { name: /Я проверил данные/ })).not.toBeChecked();
  });
});
