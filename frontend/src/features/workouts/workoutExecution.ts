export type PlateCalculation = {
  perSide: number;
  plates: number[];
  remainder: number;
};

const PLATE_SIZES = [25, 20, 15, 10, 5, 2.5, 1.25, 1, 0.5] as const;
const roundToHalf = (value: number) => Math.round(value * 2) / 2;

export function warmupSuggestions(workingWeight: number): number[] {
  if (!Number.isFinite(workingWeight) || workingWeight <= 20) return [];
  return [0.4, 0.6, 0.75]
    .map((ratio) => roundToHalf(workingWeight * ratio))
    .filter((weight, index, values) => weight >= 20 && values.indexOf(weight) === index);
}

export function calculatePlateLoad(totalWeight: number, barWeight = 20): PlateCalculation | null {
  if (
    !Number.isFinite(totalWeight) ||
    !Number.isFinite(barWeight) ||
    totalWeight < barWeight ||
    barWeight <= 0
  ) {
    return null;
  }

  const perSide = roundToHalf((totalWeight - barWeight) / 2);
  let remainder = perSide;
  const plates: number[] = [];
  for (const size of PLATE_SIZES) {
    const count = Math.floor((remainder + 0.001) / size);
    for (let index = 0; index < count; index += 1) plates.push(size);
    remainder = Math.max(0, Math.round((remainder - count * size) * 100) / 100);
  }
  return { perSide, plates, remainder };
}
