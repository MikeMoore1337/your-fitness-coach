import { describe, expect, it } from 'vitest';
import {
  decimalDraftFromValue,
  hasDecimalScale,
  isCompleteDecimalDraft,
  parseDecimalDraft,
} from '../../../../src/shared/numeric/decimalDraft';

describe('decimalDraft', () => {
  it.each([
    ['72', 72],
    ['72.3', 72.3],
    ['72.34', 72.34],
    ['72,34', 72.34],
    ['.34', 0.34],
    [',34', 0.34],
  ] as const)('parses complete value %s', (value, expected) => {
    expect(isCompleteDecimalDraft(value)).toBe(true);
    expect(parseDecimalDraft(value)).toBeCloseTo(expected, 2);
  });

  it.each(['', '72.', '72,', '.', ',', '-'])('keeps incomplete value %s unparsed', (value) => {
    expect(isCompleteDecimalDraft(value)).toBe(false);
    expect(parseDecimalDraft(value)).toBeNull();
  });

  it('rejects values beyond the declared scale instead of rounding them', () => {
    expect(hasDecimalScale('72.34', 2)).toBe(true);
    expect(hasDecimalScale('72.345', 2)).toBe(false);
    expect(hasDecimalScale('72,345', 2)).toBe(false);
  });

  it('formats existing values for a draft without adding trailing zeroes', () => {
    expect(decimalDraftFromValue(72.34)).toBe('72.34');
    expect(decimalDraftFromValue(null)).toBe('');
  });
});
