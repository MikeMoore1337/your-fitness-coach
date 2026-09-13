import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  NUTRITION_LABEL_FIELDS,
  NutritionLabelReview,
  nutritionLabelPrefillFromValues,
  type NutritionLabelReviewValues,
} from '../../../../src/features/nutrition/NutritionLabelReview';
import type { NutritionLabelDraft } from '../../../../src/shared/api/types';

const REQUIRED_VALUES: Record<string, string> = {
  energy_kcal: '240',
  energy_kj: '1004',
  protein_g: '8',
  fat_g: '4',
  carbohydrate_g: '32',
};

function buildDraft({ ambiguous = false, sourceBasis = 'per_100_g' } = {}): NutritionLabelDraft {
  const sourceFacts = Object.fromEntries(
    NUTRITION_LABEL_FIELDS.map((field) => [
      field,
      [
        {
          value: REQUIRED_VALUES[field] ?? null,
          unit: field.includes('energy_kcal') ? 'kcal' : field.includes('energy_kj') ? 'kJ' : 'g',
          basis_ref: 'per_100_g',
          column_ref: `${field}-first`,
          evidence: 'read',
        },
        ...(ambiguous && field === 'energy_kcal'
          ? [
              {
                value: '250',
                unit: 'kcal',
                basis_ref: 'per_100_g',
                column_ref: `${field}-second`,
                evidence: 'ambiguous',
              },
            ]
          : []),
      ],
    ]),
  );
  const normalizedFacts = Object.fromEntries(
    NUTRITION_LABEL_FIELDS.map((field) => [
      field,
      REQUIRED_VALUES[field]
        ? {
            value: REQUIRED_VALUES[field],
            unit: field.includes('energy_kcal') ? 'kcal' : field.includes('energy_kj') ? 'kJ' : 'g',
            basis_ref: 'per_100_g',
          }
        : null,
    ]),
  );
  const fieldEvidence = Object.fromEntries(
    NUTRITION_LABEL_FIELDS.map((field) => [
      field,
      ambiguous && field === 'energy_kcal' ? 'ambiguous' : 'read',
    ]),
  );

  return {
    draft_id: 'draft-review-128c',
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
      source_basis: sourceBasis,
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
      warnings: ambiguous ? ['ambiguous_column'] : [],
      requires_user_review: true,
      metadata: {
        provider: 'local_ocr',
        model: 'tesseract-text-v1',
        prompt_version: 'none',
        schema_version: 'nutrition-label-draft-v1',
        policy_revision: 'nutrition-label-v1',
      },
    },
    warnings: ambiguous ? ['ambiguous_column'] : [],
    requires_user_review: true,
  } as unknown as NutritionLabelDraft;
}

function renderReview(
  draft = buildDraft(),
  onSubmit = vi.fn(),
): { onSubmit: ReturnType<typeof vi.fn> } {
  render(
    <NutritionLabelReview draft={draft} mode="catalog" onCancel={vi.fn()} onSubmit={onSubmit} />,
  );
  return { onSubmit };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('NutritionLabelReview', () => {
  it('requires an explicit basis and an explicit choice for ambiguous columns', () => {
    const { onSubmit } = renderReview(buildDraft({ ambiguous: true, sourceBasis: 'ambiguous' }));

    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить и сохранить продукт' }));
    expect(
      screen.getByText('Выберите основу расчёта: 100 г, 100 мл или порция.'),
    ).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByRole('combobox', { name: 'Значения указаны' }), {
      target: { value: 'per_100_g' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить и сохранить продукт' }));
    expect(
      screen.getByText('Выберите колонку на фото для каждой неоднозначной строки.'),
    ).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByRole('combobox', { name: 'Колонка на фото для поля «Калории»' }), {
      target: { value: 'energy_kcal-second' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить и сохранить продукт' }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        visibility: 'private',
        nutrition: expect.objectContaining({ source_basis: 'per_100_g', energy_kcal: 250 }),
      }),
    );
  });

  it('keeps an unreadable optional value blank instead of turning it into zero', () => {
    renderReview();

    fireEvent.click(screen.getByText('Дополнительные значения и сведения'));
    const fiber = screen.getByRole('textbox', { name: 'Клетчатка' });
    expect(fiber).toHaveValue('');
    expect(fiber).toHaveAttribute('placeholder', 'Не распознано');
  });

  it('shows a derived nutrient separately from the editable source value', () => {
    const draft = buildDraft();
    draft.nutrition.derived_fields.sodium_mg = {
      value: '600',
      unit: 'mg',
      reason: 'derived from salt',
      source_fields: ['salt_g'],
    };

    renderReview(draft);

    fireEvent.click(screen.getByText('Дополнительные значения и сведения'));
    expect(screen.getByText(/Вычислено отдельно: 600 mg/)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Натрий' })).toHaveValue('');
  });

  it('offers shared catalog visibility only for a valid GTIN', () => {
    const onSubmit = vi.fn();
    render(
      <NutritionLabelReview
        draft={buildDraft()}
        mode="catalog"
        initialBarcode="4006381333931"
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(screen.getByRole('radio', { name: /Добавить в каталог YFC/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить и сохранить продукт' }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ visibility: 'share_to_yfc_catalog' }),
    );
  });

  it('normalizes a gram-based serving into the legacy 100 gram editor projection', () => {
    const values: NutritionLabelReviewValues = {
      name: 'Батончик',
      brand: '',
      barcode: '',
      visibility: 'private',
      nutrition: {
        source_basis: 'per_serving',
        serving_size: { amount: 25, unit: 'g' },
        servings_per_container: null,
        package_amount: null,
        energy_kcal: 100,
        energy_kj: null,
        protein_g: 5,
        fat_g: 2,
        carbohydrate_g: 10,
        sugars_g: null,
        added_sugars_g: null,
        fiber_g: null,
        saturated_fat_g: null,
        trans_fat_g: null,
        salt_g: null,
        sodium_mg: null,
        cholesterol_mg: null,
      },
    };

    const prefill = nutritionLabelPrefillFromValues(values);
    expect(prefill.nutrients.energy_kcal).toBe('400');
    expect(prefill.nutrients.protein_g).toBe('20');
    expect(prefill.nutrientsCanPopulate100g).toBe(true);
  });
});
