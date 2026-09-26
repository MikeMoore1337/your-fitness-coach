import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NutritionLabelScanner } from '../../../../src/features/nutrition/NutritionLabelScanner';
import { NUTRITION_LABEL_FIELDS } from '../../../../src/features/nutrition/NutritionLabelReview';
import { ApiError } from '../../../../src/shared/api/client';
import type { NutritionLabelDraft } from '../../../../src/shared/api/types';
import { nutritionLabelDraftStorageKey } from '../../../../src/shared/userScopedStorage';

const apiMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../../src/shared/api/client')>()),
  api: apiMock,
}));

function buildDraft(): NutritionLabelDraft {
  const values: Record<string, string> = {
    energy_kcal: '240',
    energy_kj: '1004',
    protein_g: '8',
    fat_g: '4',
    carbohydrate_g: '32',
  };
  const sourceFacts = Object.fromEntries(
    NUTRITION_LABEL_FIELDS.map((field) => [
      field,
      [
        {
          value: values[field] ?? null,
          unit: field === 'energy_kcal' ? 'kcal' : field === 'energy_kj' ? 'kJ' : 'g',
          basis_ref: 'per_100_g',
          column_ref: `${field}-column`,
          evidence: values[field] ? 'read' : 'unreadable',
        },
      ],
    ]),
  );
  const normalizedFacts = Object.fromEntries(
    NUTRITION_LABEL_FIELDS.map((field) => [
      field,
      values[field]
        ? {
            value: values[field],
            unit: field === 'energy_kcal' ? 'kcal' : field === 'energy_kj' ? 'kJ' : 'g',
            basis_ref: 'per_100_g',
          }
        : null,
    ]),
  );
  const fieldEvidence = Object.fromEntries(
    NUTRITION_LABEL_FIELDS.map((field) => [field, values[field] ? 'read' : 'unreadable']),
  );
  return {
    draft_id: 'draft-scanner-128c',
    revision: 3,
    status: 'draft',
    expires_at: '2026-09-13T14:15:00Z',
    product_name: 'Овсяная каша',
    product_brand: 'YFC',
    product_barcode: null,
    nutrition: {
      schema_version: 'nutrition-label-draft-v1',
      source_language: 'ru',
      label_format: 'ru_standard',
      source_basis: 'per_100_g',
      serving_size: null,
      servings_per_container: null,
      package_amount: null,
      source_facts: sourceFacts,
      normalized_facts: normalizedFacts,
      derived_fields: {},
      displayed_daily_value_percent: {},
      field_evidence: fieldEvidence,
      confidence_kind: 'none',
      confidence: {},
      warnings: [],
      requires_user_review: true,
      metadata: {
        provider: 'local_ocr',
        model: 'tesseract-text-v1',
        prompt_version: 'none',
        schema_version: 'nutrition-label-draft-v1',
        policy_revision: 'nutrition-label-v1',
      },
    },
    warnings: [],
    requires_user_review: true,
  } as unknown as NutritionLabelDraft;
}

const confirmedFood = {
  id: 128,
  name: 'Овсяная каша',
  brand: 'YFC',
  barcode: null,
  energy_kcal_per_100g: '240.00',
  protein_g_per_100g: '8.000',
  fat_g_per_100g: '4.000',
  carbs_g_per_100g: '32.000',
  fiber_g_per_100g: null,
  nutrition_basis_kind: 'per_100_g',
  nutrition_basis_amount: '100',
  nutrition_basis_unit: 'g',
  canonical_facts: null,
  nutrition_provenance: null,
  catalog_quality: 'private',
  provenance: 'user',
  trust_level: 'verified',
  canonical_complete: true,
  standard_serving_amount: null,
  standard_serving_unit: null,
  standard_serving_weight_g: null,
  food_type: 'user',
  is_favorite: false,
  last_used_at: null,
  created_at: '2026-09-13T14:00:00Z',
  updated_at: '2026-09-13T14:00:00Z',
};

describe('NutritionLabelScanner', () => {
  const originalOnline = navigator.onLine;
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;

  beforeEach(() => {
    cleanup();
    localStorage.clear();
    apiMock.mockReset();
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:label-preview'),
    });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    vi.stubGlobal(
      'createImageBitmap',
      vi.fn().mockResolvedValue({
        width: 240,
        height: 320,
        close: vi.fn(),
      }),
    );
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      drawImage: vi.fn(),
      imageSmoothingEnabled: false,
      imageSmoothingQuality: 'low',
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((callback) => {
      callback(new Blob(['normalized-label'], { type: 'image/jpeg' }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: originalOnline });
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: originalCreateObjectURL,
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: originalRevokeObjectURL,
    });
  });

  it('prepares one selected image, requires review, confirms once, and clears the browser pointer', async () => {
    const draft = buildDraft();
    let resolveSaved!: () => void;
    const savedCompletion = new Promise<void>((resolve) => {
      resolveSaved = resolve;
    });
    const onSaved = vi.fn(() => savedCompletion);
    const confirmResponse = {
      food: confirmedFood,
      visibility: 'private',
      contribution_state: 'private',
      catalog_quality: 'private',
      provenance: 'user',
      diary_entry_created: false,
    };
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/nutrition/label-scans') return Promise.resolve(draft);
      if (path.endsWith('/confirm')) return Promise.resolve(confirmResponse);
      return Promise.resolve(undefined);
    });

    render(<NutritionLabelScanner userId={10} onCancel={vi.fn()} onSaved={onSaved} />);
    const file = new File(['camera-or-gallery-image'], 'label.png', { type: 'image/png' });
    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });

    expect(await screen.findByRole('button', { name: 'Распознать' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Распознать' }));
    expect(
      await screen.findByRole('heading', { name: 'Данные с пищевой этикетки' }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(JSON.parse(localStorage.getItem(nutritionLabelDraftStorageKey(10))!)).toEqual({
        draftId: draft.draft_id,
        revision: draft.revision,
        mode: 'catalog',
      }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить и сохранить продукт' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(confirmedFood, confirmResponse));
    const confirmButton = screen.getByRole('button', { name: 'Сохраняем…' });
    expect(confirmButton).toBeDisabled();
    fireEvent.click(confirmButton);

    const scanCall = apiMock.mock.calls.find(([path]) => path === '/api/v1/nutrition/label-scans');
    const confirmCalls = apiMock.mock.calls.filter(([path]) => path.endsWith('/confirm'));
    const confirmCall = confirmCalls[0];
    expect(scanCall?.[1].body).toBeInstanceOf(FormData);
    expect((scanCall?.[1].body as FormData).get('image')).toBeInstanceOf(File);
    expect(scanCall?.[1].headers['Idempotency-Key']).toMatch(/^nutrition-label-scan-/);
    expect(confirmCalls).toHaveLength(1);
    expect(confirmCall?.[1].body).toMatchObject({
      revision: draft.revision,
      classification: 'personal',
      barcode: null,
      nutrition: expect.objectContaining({ source_basis: 'per_100_g', energy_kcal: 240 }),
    });
    resolveSaved();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Подтвердить и сохранить продукт' })).toBeEnabled(),
    );
    expect(localStorage.getItem(nutritionLabelDraftStorageKey(10))).toBeNull();
  });

  it('recovers an active owner-scoped draft after reload without storing the source image', async () => {
    const draft = buildDraft();
    localStorage.setItem(
      nutritionLabelDraftStorageKey(10),
      JSON.stringify({ draftId: draft.draft_id, revision: draft.revision }),
    );
    apiMock.mockResolvedValue(draft);

    render(<NutritionLabelScanner userId={10} onCancel={vi.fn()} />);

    expect(
      await screen.findByRole('heading', { name: 'Данные с пищевой этикетки' }),
    ).toBeInTheDocument();
    expect(apiMock).toHaveBeenCalledWith(`/api/v1/nutrition/label-scans/${draft.draft_id}`, {
      timeoutMs: 8_000,
    });
    expect(localStorage.getItem(nutritionLabelDraftStorageKey(10))).not.toContain(
      'camera-or-gallery',
    );
  });

  it('shows a specific Russian fallback for an unsupported selected file', async () => {
    render(<NutritionLabelScanner userId={10} onCancel={vi.fn()} />);
    const file = new File(['not-an-image'], 'label.pdf', { type: 'application/pdf' });

    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Выберите фото в формате JPEG, PNG или WebP.',
    );
    expect(apiMock).not.toHaveBeenCalled();
  });

  it('shows retake guidance for a backend retake response instead of a timeout message', async () => {
    apiMock.mockRejectedValue(
      new ApiError('Bad Request', 400, {
        detail: {
          code: 'retake_required',
          message: 'Нужен более чёткий снимок этикетки',
        },
      }),
    );

    render(<NutritionLabelScanner userId={10} onCancel={vi.fn()} />);
    const file = new File(['camera-or-gallery-image'], 'label.png', { type: 'image/png' });
    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });

    fireEvent.click(await screen.findByRole('button', { name: 'Распознать' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Нужен более чёткий снимок этикетки крупным планом.',
    );
    expect(screen.getByRole('alert')).not.toHaveTextContent('Сервер не ответил вовремя');
  });

  it('keeps the gallery picker separate from the explicit camera flow', () => {
    render(<NutritionLabelScanner userId={10} onCancel={vi.fn()} />);

    const galleryInput = document.querySelector('input[type="file"]');
    expect(galleryInput).toBeInTheDocument();
    expect(galleryInput).not.toHaveAttribute('capture');
    expect(screen.getByRole('button', { name: 'Открыть камеру' })).toBeInTheDocument();
  });

  it('does not attach an in-flight account A recognition result to account B', async () => {
    const draft = buildDraft();
    let resolveRecognition!: (value: NutritionLabelDraft) => void;
    const recognition = new Promise<NutritionLabelDraft>((resolve) => {
      resolveRecognition = resolve;
    });
    apiMock.mockImplementation((path: string) =>
      path === '/api/v1/nutrition/label-scans' ? recognition : Promise.resolve(undefined),
    );
    const view = render(<NutritionLabelScanner userId={10} onCancel={vi.fn()} />);
    const file = new File(['camera-or-gallery-image'], 'label.png', { type: 'image/png' });
    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Распознать' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/api/v1/nutrition/label-scans', expect.anything()),
    );

    view.rerender(<NutritionLabelScanner userId={11} onCancel={vi.fn()} />);
    await act(async () => resolveRecognition(draft));

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Сканировать пищевую ценность' }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByRole('heading', { name: 'Данные с пищевой этикетки' }),
    ).not.toBeInTheDocument();
    expect(localStorage.getItem(nutritionLabelDraftStorageKey(11))).toBeNull();
  });
});
