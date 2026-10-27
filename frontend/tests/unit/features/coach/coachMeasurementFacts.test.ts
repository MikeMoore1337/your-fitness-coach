import { describe, expect, it } from 'vitest';
import type { BodyMeasurement } from '../../../../src/shared/api/types';
import { formatMeasurementDetail } from '../../../../src/features/coach/coachMeasurementFacts';

function measurement(overrides: Partial<BodyMeasurement> = {}): BodyMeasurement {
  return {
    id: 1,
    measured_on: '2030-01-01',
    weight_kg: null,
    chest_cm: null,
    waist_cm: null,
    hips_cm: null,
    biceps_cm: null,
    thigh_cm: null,
    note: null,
    created_at: null,
    custom_values: [],
    ...overrides,
  };
}

describe('formatMeasurementDetail', () => {
  it('renders canonical-only measurements and omits missing values', () => {
    expect(
      formatMeasurementDetail(
        measurement({
          weight_kg: 68.5,
          waist_cm: 86,
        }),
      ),
    ).toBe('Вес 68.5 кг · Талия 86 см');
  });

  it('renders custom-only measurements with their user-facing label', () => {
    expect(
      formatMeasurementDetail(
        measurement({
          custom_values: [
            { definition_id: 91, label: 'Складка на боку', unit: 'cm', value: 14, archived: false },
          ],
        }),
      ),
    ).toBe('Складка на боку 14 cm');
  });

  it('preserves distinct canonical and custom facts in a mixed event', () => {
    expect(
      formatMeasurementDetail(
        measurement({
          weight_kg: 68.5,
          waist_cm: 86,
          custom_values: [
            { definition_id: 91, label: 'Плечо', unit: 'cm', value: 42, archived: false },
          ],
        }),
      ),
    ).toBe('Вес 68.5 кг · Талия 86 см · Плечо 42 cm');
  });

  it('removes an exact canonical/custom repeat without hiding different values', () => {
    expect(
      formatMeasurementDetail(
        measurement({
          waist_cm: 86,
          custom_values: [
            { definition_id: 91, label: 'Талия', unit: 'cm', value: 86, archived: false },
          ],
        }),
      ),
    ).toBe('Талия 86 см');
    expect(
      formatMeasurementDetail(
        measurement({
          waist_cm: 86,
          custom_values: [
            { definition_id: 91, label: 'Талия', unit: 'cm', value: 88, archived: false },
          ],
        }),
      ),
    ).toBe('Талия 86 см · Талия · пользовательский 88 cm');
  });

  it('keeps a renamed custom metric and does not expose its internal id', () => {
    const detail = formatMeasurementDetail(
      measurement({
        custom_values: [
          { definition_id: 12345, label: 'Обхват плеча', unit: 'cm', value: 42, archived: false },
        ],
      }),
    );

    expect(detail).toBe('Обхват плеча 42 cm');
    expect(detail).not.toContain('12345');
  });

  it('keeps archived historical custom values and treats zero as a value, not missing', () => {
    expect(
      formatMeasurementDetail(
        measurement({
          custom_values: [
            {
              definition_id: 91,
              label: 'Исторический показатель',
              unit: 'cm',
              value: 0,
              archived: true,
            },
          ],
        }),
      ),
    ).toBe('Исторический показатель 0 cm');
  });
});
