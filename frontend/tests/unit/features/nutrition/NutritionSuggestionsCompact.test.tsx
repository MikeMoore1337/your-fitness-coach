import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NutritionSuggestions } from '../../../../src/features/nutrition/NutritionSuggestions';
import type {
  NutritionSuggestion,
  NutritionSuggestions as Response,
} from '../../../../src/shared/api/types';
import { queryKeys } from '../../../../src/shared/queryKeys';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));

const nutrition = { energy_kcal: '165', protein_g: '31', fat_g: null, carbs_g: '0', fiber_g: null };
const candidate = (index: number): NutritionSuggestion => ({
  candidate_id: `food:${index}`,
  candidate_kind: 'food',
  identity_id: index,
  name: `Продукт ${index}`,
  items: [
    {
      position: 0,
      item_kind: 'food',
      food_id: index,
      recipe_id: null,
      name: `Продукт ${index}`,
      brand: null,
      amount: '100',
      amount_unit: 'g',
      nutrition,
      nutrition_confidence: 'partial',
    },
  ],
  nutrition,
  nutrition_confidence: 'partial',
  sources: ['recent', 'favorite'],
  reasons: ['recent', 'protein_fit', 'partial_nutrition'],
});

function response(count: number): Response {
  return {
    mode: 'deterministic',
    diary_date: '2026-11-06',
    targets: { energy_kcal: '2000', protein_g: '150', fat_g: '70', carbs_g: '190' },
    remaining: { energy_kcal: '500', protein_g: '50', fat_g: null, carbs_g: '60' },
    remaining_confidence: 'partial',
    limitations: ['Часть БЖУ неизвестна.'],
    max_candidates: 6,
    candidates: Array.from({ length: count }, (_, index) => candidate(index + 1)),
  };
}

function setup(mode: 'diary' | 'plan' = 'diary') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const tree = (date: string) => (
    <QueryClientProvider client={client}>
      <FeedbackProvider>
        <NutritionSuggestions
          diaryDate={date}
          initialMealType="lunch"
          mode={mode}
          planRevision={1}
        />
      </FeedbackProvider>
    </QueryClientProvider>
  );
  const view = render(tree('2026-11-06'));
  return { client, changeDate: (date: string) => view.rerender(tree(date)) };
}

const region = () => screen.getByRole('region', { name: 'Варианты из вашей еды' });
const visibleNames = () =>
  within(region())
    .queryAllByRole('listitem')
    .map((item) => item.querySelector('strong')?.textContent);

describe('компактные рекомендации дневника', () => {
  beforeEach(() => {
    apiMock.mockReset();
  });
  afterEach(() => cleanup());

  it.each([0, 1, 2, 3, 6])('показывает нужное число из %i вариантов', async (count) => {
    apiMock.mockResolvedValue(response(count));
    setup();
    if (count === 0) await screen.findByText('Пока нет готовых вариантов');
    else await screen.findByText('Продукт 1');
    expect(visibleNames()).toEqual(
      Array.from({ length: Math.min(count, 2) }, (_, i) => `Продукт ${i + 1}`),
    );
    if (count <= 2) {
      expect(
        within(region()).queryByRole('button', { name: /Показать все/ }),
      ).not.toBeInTheDocument();
    } else {
      const toggle = within(region()).getByRole('button', {
        name: new RegExp(`Показать все ${count}`),
      });
      expect(toggle).toHaveAttribute('aria-expanded', 'false');
      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute('aria-expanded', 'true');
      expect(visibleNames()).toEqual(Array.from({ length: count }, (_, i) => `Продукт ${i + 1}`));
      fireEvent.click(toggle);
      expect(visibleNames()).toEqual(['Продукт 1', 'Продукт 2']);
    }
  });

  it('сохраняет неизвестные БЖУ, достоверность, причины и источники без повторов', async () => {
    apiMock.mockResolvedValue(response(3));
    setup();
    const card = (await screen.findByText('Продукт 1')).closest('li')!;
    expect(within(card).getByText(/165 ккал · Б 31 · Ж — · У 0/)).toBeVisible();
    expect(within(card).getByText('Частичные БЖУ')).toBeVisible();
    expect(card).toHaveTextContent('Недавнее · Укладывается в известный остаток белка');
    expect(within(card).queryByText('Неполные БЖУ')).not.toBeInTheDocument();
    fireEvent.click(within(card).getByText('Другие основания: Продукт 1'));
    expect(within(card).getByText('Избранное')).toBeVisible();
    expect(within(region()).getByText(/Остаток: 500 ккал · Б 50/)).toBeVisible();
    expect(within(region()).getByText('Часть БЖУ неизвестна.')).toBeVisible();
    expect(
      within(card).getByRole('button', { name: 'Проверить вариант' }),
    ).toHaveAccessibleDescription('Продукт 1');
  });

  it('не выдумывает остаток и сохраняет приблизительную достоверность', async () => {
    const data = response(1);
    data.remaining = null;
    data.remaining_confidence = null;
    data.candidates![0] = {
      ...data.candidates![0]!,
      nutrition: { ...nutrition, fat_g: '3', fiber_g: '1' },
      nutrition_confidence: 'approximate',
      reasons: ['recent'],
    };
    apiMock.mockResolvedValue(data);
    setup();
    await screen.findByText('Продукт 1');
    expect(within(region()).queryByText(/Остаток:/)).not.toBeInTheDocument();
    expect(within(region()).getByText('Приблизительные БЖУ')).toBeVisible();
  });

  it('объясняет отсутствие цели, если вариантов нет', async () => {
    apiMock.mockResolvedValue({ ...response(0), targets: null, remaining: null });
    setup();
    expect(await screen.findByText('Нет цели КБЖУ на эту дату')).toBeVisible();
    expect(screen.queryByText('Пока нет готовых вариантов')).not.toBeInTheDocument();
  });

  it('сворачивает список при смене даты и набора, в том числе при возврате на дату', async () => {
    apiMock.mockImplementation((path: string) =>
      Promise.resolve({
        ...response(6),
        diary_date: new URL(path, 'http://localhost').searchParams.get('diary_date'),
      }),
    );
    const { client, changeDate } = setup();
    await screen.findByText('Продукт 1');
    fireEvent.click(screen.getByRole('button', { name: 'Показать все 6 вариантов' }));
    changeDate('2026-11-07');
    await screen.findByRole('button', { name: 'Показать все 6 вариантов' });
    expect(visibleNames()).toEqual(['Продукт 1', 'Продукт 2']);
    changeDate('2026-11-06');
    await screen.findByRole('button', { name: 'Показать все 6 вариантов' });
    fireEvent.click(screen.getByRole('button', { name: 'Показать все 6 вариантов' }));
    client.setQueryData(queryKeys.nutrition.suggestions('2026-11-06'), response(3));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Показать все 3 варианта' })).toHaveAttribute(
        'aria-expanded',
        'false',
      ),
    );
  });

  it('открывает прежнюю проверку скрытого варианта и обновляет список после подтверждения', async () => {
    let current = response(3);
    apiMock.mockImplementation(
      (
        path: string,
        options?: { body: { diary_date: string; meal_type: string; items: { amount: string }[] } },
      ) => {
        if (path.endsWith('/commit')) {
          current = response(2);
          return Promise.resolve({ entries: [], replayed: false });
        }
        if (path.endsWith('/preview')) {
          const scale = Number(options!.body.items[0]!.amount) / 100;
          const addition = {
            energy_kcal: String(165 * scale),
            protein_g: String(31 * scale),
            fat_g: null,
            carbs_g: '0',
            fiber_g: null,
          };
          const before = {
            energy_kcal: '0',
            protein_g: '0',
            fat_g: '0',
            carbs_g: '0',
            fiber_g: '0',
          };
          return Promise.resolve({
            diary_date: options!.body.diary_date,
            meal_type: options!.body.meal_type,
            items: [
              {
                ...candidate(3).items[0],
                amount: options!.body.items[0]!.amount,
                nutrition: addition,
              },
            ],
            before,
            addition,
            after: addition,
            diary: before,
            planned: null,
            projected_after: addition,
            targets: response(3).targets,
            target_id: 1,
            target_source: null,
            target_effective_from: '2026-11-06',
            target_weight_kg: null,
            target_goal: null,
            constraint_status: 'not_set',
            constraint_messages: [],
            preference_message: null,
            preview_token: 'c'.repeat(64),
          });
        }
        return Promise.resolve(current);
      },
    );
    setup();
    await screen.findByText('Продукт 1');
    fireEvent.click(screen.getByRole('button', { name: 'Показать все 3 варианта' }));
    const third = screen.getByText('Продукт 3').closest('li')!;
    fireEvent.click(within(third).getByRole('button', { name: 'Проверить вариант' }));
    fireEvent.change(screen.getByLabelText('Количество'), { target: { value: '150' } });
    fireEvent.change(screen.getByLabelText('Приём пищи'), { target: { value: 'dinner' } });
    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/commit'))).toBe(false);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Добавить выбранное' })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Добавить выбранное' }));
    await waitFor(() =>
      expect(apiMock.mock.calls.some(([path]) => path.endsWith('/commit'))).toBe(true),
    );
    const call = apiMock.mock.calls.find(([path]) => path.endsWith('/commit'));
    expect(call?.[1].body).toEqual({
      diary_date: '2026-11-06',
      meal_type: 'dinner',
      items: [{ food_id: 3, amount: '150', amount_unit: 'g' }],
      preview_token: 'c'.repeat(64),
    });
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Показать все/ })).not.toBeInTheDocument(),
    );
    expect(visibleNames()).toEqual(['Продукт 1', 'Продукт 2']);
  });

  it('сохраняет повторную загрузку после ошибки сети', async () => {
    apiMock.mockRejectedValueOnce(new Error('Сеть недоступна')).mockResolvedValue(response(3));
    setup();
    expect(await screen.findByText('Сеть недоступна')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Повторить варианты' }));
    expect(await screen.findByRole('button', { name: 'Показать все 3 варианта' })).toBeVisible();
  });

  it('не меняет режим плана', async () => {
    apiMock.mockResolvedValue(response(6));
    setup('plan');
    const plan = await screen.findByRole('region', { name: 'Варианты для плана' });
    await within(plan).findByText('Продукт 1');
    expect(within(plan).getAllByRole('listitem')).toHaveLength(6);
    expect(within(plan).queryByRole('button', { name: /Показать все/ })).not.toBeInTheDocument();
    expect(
      within(plan).getAllByText('Вариант из сохранённых данных, не предписание.'),
    ).toHaveLength(6);
  });
});
