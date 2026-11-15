import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NutritionHistoryImport } from '../../../../src/features/nutrition/NutritionHistoryImport';
import { ApiError } from '../../../../src/shared/api/client';
import {
  AUTHENTICATED_USER_ID_STORAGE_KEY,
  NUTRITION_HISTORY_RECOVERY_SESSION_KEY,
} from '../../../../src/shared/userScopedStorage';

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

const nutrients = {
  energy_kcal: '12.30',
  protein_g: '2',
  fat_g: null,
  carbs_g: '3',
  fiber_g: null,
};
const source = {
  diary_date: '2024-02-29',
  meal_type: 'breakfast',
  food: { name: 'Яйцо' },
  quantity: '2',
  amount_unit: 'piece',
};
const preview = {
  revision: 1,
  preview_signature: 'a'.repeat(64),
  dates: ['2024-02-29'],
  rows: [{ index: 0, source, nutrition_amount: nutrients }],
  existing_meals: [
    {
      date: '2024-02-29',
      meal_type: 'breakfast',
      entries: [
        {
          id: 1,
          food_name: 'Яйцо',
          amount: '1',
          amount_unit: 'serving',
          serving_unit: 'piece',
          nutrition: { ...nutrients, energy_kcal: '10.10' },
        },
      ],
    },
  ],
};
const draftId = '123e4567-e89b-42d3-a456-426614174000';

function mount() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <NutritionHistoryImport
        draftId={draftId}
        expiresAt={Date.now() + 60_000}
        onBack={vi.fn()}
        onDone={vi.fn()}
        onClose={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

describe('history import review', () => {
  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem(AUTHENTICATED_USER_ID_STORAGE_KEY, '7');
    apiMock.mockReset();
    apiMock.mockImplementation(
      async (path: string, options?: { body: { decisions: unknown[] } }) => {
        if (path.endsWith('/review'))
          return {
            review_signature: 'b'.repeat(64),
            rows: [
              {
                index: 0,
                action: options?.body.decisions.length ? 'add' : 'conflict',
                conflict: true,
              },
            ],
          };
        return preview;
      },
    );
  });
  afterEach(cleanup);

  it('keeps history optional and requires a conflict decision and confirmation', async () => {
    mount();
    expect(apiMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText(/Перенести историю питания/));
    await screen.findByLabelText(/Добавить отсутствующие/);
    fireEvent.click(screen.getByLabelText(/Добавить отсутствующие/));
    fireEvent.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    await screen.findByText(/Нужно проверить/);
    expect(screen.getByText(/Разница: ккал \+2,2/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Продолжить' })).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Добавить как отдельное употребление'));
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
    await screen.findByText('Проверьте перенос');
    expect(screen.getByRole('button', { name: 'Перенести историю' })).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Подтверждаю перенос/));
    expect(screen.getByRole('button', { name: 'Перенести историю' })).toBeEnabled();
  });

  it('retries the same confirmation after a lost response', async () => {
    const payload = {
      revision: 1,
      preview_signature: 'a'.repeat(64),
      review_signature: 'b'.repeat(64),
      confirm_key: 'retry-key',
      confirmed: true,
      date_from: '2024-02-29',
      date_to: '2024-02-29',
      mode: 'manual',
      selected_rows: [0],
      decisions: [],
    };
    sessionStorage.setItem(
      NUTRITION_HISTORY_RECOVERY_SESSION_KEY,
      JSON.stringify({ userId: '7', draftId, expiresAt: Date.now() + 60_000, payload }),
    );
    apiMock
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ added: 1, skipped: 0, conflicts: 0 });
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Проверить результат' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Проверить результат' }));
    await screen.findByText('История перенесена');
    expect(apiMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining('/confirm'),
      expect.objectContaining({ body: payload }),
    );
    expect(apiMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining('/confirm'),
      expect.objectContaining({ body: payload }),
    );
    await waitFor(() =>
      expect(sessionStorage.getItem(NUTRITION_HISTORY_RECOVERY_SESSION_KEY)).toBeNull(),
    );
  });

  it('lets the user leave an empty history', async () => {
    apiMock.mockResolvedValue({ ...preview, dates: [], rows: [] });
    mount();
    fireEvent.click(screen.getByLabelText(/Перенести историю питания/));
    await screen.findByText(/Записи с датами не найдены/);
    expect(screen.getByRole('button', { name: 'Вернуться к импорту' })).toBeVisible();
  });

  it('allows refreshing after the diary changed', async () => {
    apiMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/review')) throw new ApiError('Изменилось', 409);
      return preview;
    });
    mount();
    fireEvent.click(screen.getByLabelText(/Перенести историю питания/));
    await screen.findByLabelText(/Добавить отсутствующие/);
    fireEvent.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Обновить предпросмотр' }));
    await screen.findByLabelText(/Добавить отсутствующие/);
    expect(apiMock).toHaveBeenCalledTimes(3);
  });
});
