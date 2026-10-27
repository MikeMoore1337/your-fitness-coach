import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
});
