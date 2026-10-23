export function positiveInteger(value: string | null | undefined): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

export function positiveIntegerParam(params: URLSearchParams, key: string): number | null {
  const values = params.getAll(key);
  return values.length === 1 ? positiveInteger(values[0]) : null;
}

export function hasNoDuplicateParams(
  params: URLSearchParams,
  keys: readonly string[] = Array.from(new Set(params.keys())),
): boolean {
  return keys.every((key) => params.getAll(key).length <= 1);
}
