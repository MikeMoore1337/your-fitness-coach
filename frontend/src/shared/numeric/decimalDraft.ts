export function normalizeDecimalDraft(value: string): string {
  return value.trim().replace(',', '.');
}

export function isCompleteDecimalDraft(value: string): boolean {
  return /^-?(?:\d+(?:\.\d+)?|\.\d+)$/.test(normalizeDecimalDraft(value));
}

export function parseDecimalDraft(value: string): number | null {
  if (!isCompleteDecimalDraft(value)) return null;
  const parsed = Number(normalizeDecimalDraft(value));
  return Number.isFinite(parsed) ? parsed : null;
}

export function hasDecimalScale(value: string, maximumFractionDigits: number): boolean {
  const normalized = normalizeDecimalDraft(value);
  if (!isCompleteDecimalDraft(normalized)) return false;
  return (normalized.split('.')[1] ?? '').length <= maximumFractionDigits;
}

export function decimalDraftFromValue(value: number | string | null | undefined): string {
  return value == null ? '' : String(value);
}
