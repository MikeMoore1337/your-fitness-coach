import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PhotoMealScanner } from '../../../../src/features/nutrition/PhotoMealScanner';
import { ApiError } from '../../../../src/shared/api/client';
import type { PhotoMealConfirmResponse, PhotoMealDraft } from '../../../../src/shared/api/types';

const apiMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../../src/shared/api/client')>()),
  api: apiMock,
}));

const draft: PhotoMealDraft = {
  draft_id: 'photo-meal-draft-516',
  revision: 1,
  status: 'draft',
  expires_at: '2026-10-01T12:15:00Z',
  candidates: [
    {
      candidate_id: 'food-1',
      name: 'Курица с рисом',
      portion_amount: '250',
      portion_unit: 'g',
      portion_confidence: 'medium',
      identity_confidence: 'high',
      nutrition_confidence: 'medium',
      uncertainty_codes: [],
      energy_kcal: '420',
      protein_g: '34',
      fat_g: '12',
      carbs_g: '38',
    },
  ],
  warnings: ['manual_review_required'],
  requires_user_review: true,
  source_photo_retained: false,
};

const confirmed = {
  draft_id: draft.draft_id,
  replayed: false,
  entry: { id: 516 },
} as unknown as PhotoMealConfirmResponse;

describe('PhotoMealScanner', () => {
  beforeEach(() => {
    cleanup();
    apiMock.mockReset();
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:meal-preview');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('keeps recognition as an editable draft until explicit confirmation', async () => {
    const onCompleted = vi.fn();
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/nutrition/photo-meals') return Promise.resolve(draft);
      if (path.endsWith('/confirm')) return Promise.resolve(confirmed);
      return Promise.resolve(undefined);
    });

    render(
      <PhotoMealScanner
        userId={10}
        diaryDate="2026-10-01"
        mealType="lunch"
        onCancel={vi.fn()}
        onCompleted={onCompleted}
      />,
    );
    const file = new File(['meal-photo'], 'meal.png', { type: 'image/png' });
    fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file] } });
    fireEvent.click(await screen.findByRole('button', { name: 'Распознать приблизительно' }));

    expect(await screen.findByRole('heading', { name: 'Проверьте оценку блюда' })).toBeVisible();
    expect(screen.getByText('Результат требует проверки перед добавлением.')).toBeVisible();
    expect(apiMock.mock.calls.filter(([path]) => path.endsWith('/confirm'))).toHaveLength(0);

    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Курица и рис' } });
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить и добавить в дневник' }));

    await waitFor(() => expect(onCompleted).toHaveBeenCalledWith(confirmed));
    const confirmCall = apiMock.mock.calls.find(([path]) => path.endsWith('/confirm'));
    expect(confirmCall?.[1].body).toMatchObject({
      revision: 1,
      diary_date: '2026-10-01',
      meal_type: 'lunch',
      items: [expect.objectContaining({ candidate_id: 'food-1', name: 'Курица и рис' })],
    });
  });

  it('offers approximate/manual fallback when the provider is unavailable', async () => {
    const onManualFallback = vi.fn();
    apiMock.mockRejectedValue(
      new ApiError('Unavailable', 503, {
        detail: { code: 'vision_unavailable', message: 'fallback' },
      }),
    );
    render(
      <PhotoMealScanner
        userId={10}
        diaryDate="2026-10-01"
        mealType="lunch"
        onCancel={vi.fn()}
        onManualFallback={onManualFallback}
        onCompleted={vi.fn()}
      />,
    );
    const file = new File(['meal-photo'], 'meal.png', { type: 'image/png' });
    fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file] } });
    fireEvent.click(await screen.findByRole('button', { name: 'Распознать приблизительно' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Распознавание фото сейчас недоступно. Добавьте запись приблизительно.',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Добавить вручную' }));
    expect(onManualFallback).toHaveBeenCalledOnce();
  });

  it('retries the same confirmation after losing the response', async () => {
    const onCompleted = vi.fn();
    const replayed = { ...confirmed, replayed: true };
    let confirmAttempts = 0;
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/nutrition/photo-meals') return Promise.resolve(draft);
      if (path.endsWith('/confirm')) {
        confirmAttempts += 1;
        return confirmAttempts === 1
          ? Promise.reject(new ApiError('Нет связи', 0))
          : Promise.resolve(replayed);
      }
      return Promise.resolve(undefined);
    });
    render(
      <PhotoMealScanner
        userId={10}
        diaryDate="2026-10-01"
        mealType="lunch"
        onCancel={vi.fn()}
        onCompleted={onCompleted}
      />,
    );
    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [new File(['meal-photo'], 'meal.png', { type: 'image/png' })] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Распознать приблизительно' }));
    const button = await screen.findByRole('button', { name: 'Подтвердить и добавить в дневник' });
    fireEvent.click(button);
    expect(await screen.findByRole('alert')).toHaveTextContent('Нет связи');
    fireEvent.click(button);
    await waitFor(() => expect(onCompleted).toHaveBeenCalledOnce());
    expect(onCompleted).toHaveBeenCalledWith(replayed);
    const confirmations = apiMock.mock.calls.filter(([path]) => path.endsWith('/confirm'));
    expect(confirmations).toHaveLength(2);
    expect(confirmations[0]?.[1].body).toEqual(confirmations[1]?.[1].body);
  });

  it('reuses the request key for retries, but not for a different photo', async () => {
    apiMock
      .mockRejectedValueOnce(new ApiError('Network error', 0))
      .mockRejectedValueOnce(new ApiError('Network error', 0))
      .mockResolvedValueOnce(draft);
    render(
      <PhotoMealScanner
        userId={10}
        diaryDate="2026-10-01"
        mealType="lunch"
        onCancel={vi.fn()}
        onCompleted={vi.fn()}
      />,
    );
    const input = document.querySelector('input[type="file"]')!;
    fireEvent.change(input, {
      target: { files: [new File(['first'], 'first.png', { type: 'image/png' })] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Распознать приблизительно' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Повторить' }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    await screen.findByRole('button', { name: 'Повторить' });
    fireEvent.change(input, {
      target: { files: [new File(['second'], 'second.png', { type: 'image/png' })] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Распознать приблизительно' }));
    await screen.findByRole('heading', { name: 'Проверьте оценку блюда' });
    const keys = apiMock.mock.calls.map(([, options]) => options.headers['Idempotency-Key']);
    expect(keys[0]).toBe(keys[1]);
    expect(keys[2]).not.toBe(keys[0]);
  });

  it('ignores an earlier recognition when a different photo is selected', async () => {
    let resolveFirst!: (value: PhotoMealDraft) => void;
    apiMock
      .mockImplementationOnce(() => new Promise((resolve) => (resolveFirst = resolve)))
      .mockResolvedValueOnce({
        ...draft,
        candidates: [{ ...draft.candidates[0], name: 'Овощи' }],
      });
    render(
      <PhotoMealScanner
        userId={10}
        diaryDate="2026-10-01"
        mealType="lunch"
        onCancel={vi.fn()}
        onCompleted={vi.fn()}
      />,
    );
    const input = document.querySelector('input[type="file"]')!;
    fireEvent.change(input, {
      target: { files: [new File(['first'], 'first.png', { type: 'image/png' })] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Распознать приблизительно' }));
    fireEvent.change(input, {
      target: { files: [new File(['second'], 'second.png', { type: 'image/png' })] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Распознать приблизительно' }));
    expect(await screen.findByDisplayValue('Овощи')).toBeVisible();
    await act(async () => resolveFirst(draft));
    expect(screen.getByDisplayValue('Овощи')).toBeVisible();
  });
});
