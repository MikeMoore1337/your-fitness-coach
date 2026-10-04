export type PlateCalculation = {
  perSide: number;
  plates: number[];
  remainder: number;
};

export type PlateInventoryEntry = {
  weight: number;
  count: number;
};

export type PlateLoadCalculation = {
  targetTotal: number;
  barWeight: number;
  requestedPerSide: number;
  achievedPerSide: number;
  achievedTotal: number;
  difference: number;
  exact: boolean;
  plates: number[];
};

export type PlateLoadCalculationErrorCode =
  | 'invalid_target'
  | 'invalid_bar'
  | 'target_below_bar'
  | 'invalid_inventory'
  | 'invalid_denomination'
  | 'invalid_count'
  | 'duplicate_denomination'
  | 'inventory_too_large'
  | 'unsupported_precision';

export type PlateLoadCalculationError = {
  code: PlateLoadCalculationErrorCode;
  message: string;
};

export type PlateLoadCalculationResult =
  { ok: true; calculation: PlateLoadCalculation } | { ok: false; error: PlateLoadCalculationError };

const PLATE_SIZES = [25, 20, 15, 10, 5, 2.5, 1.25, 1, 0.5] as const;
export const DEFAULT_PLATE_INVENTORY: readonly PlateInventoryEntry[] = PLATE_SIZES.map(
  (weight) => ({
    weight,
    count: 2,
  }),
);
const CALCULATOR_SCALE = 100;
const MAX_CALCULATOR_WEIGHT_KG = 1000;
const MAX_INVENTORY_DENOMINATIONS = 12;
const MAX_PLATES_PER_DENOMINATION = 8;
const MAX_INVENTORY_PLATES = 48;
const MAX_INVENTORY_WEIGHT_KG = 250;
const roundToHalf = (value: number) => Math.round(value * 2) / 2;

const normalizeWeight = (value: number): number => {
  const normalized = Number(value.toFixed(3));
  return Object.is(normalized, -0) ? 0 : normalized;
};

function invalid(code: PlateLoadCalculationErrorCode, message: string): PlateLoadCalculationError {
  return { code, message };
}

function parseScaledWeight(
  value: number,
  code: 'invalid_target' | 'invalid_bar' | 'invalid_denomination',
  label: string,
): number | PlateLoadCalculationError {
  if (!Number.isFinite(value)) {
    return invalid(code, `Укажите корректный ${label}.`);
  }
  const scaledValue = value * CALCULATOR_SCALE;
  const scaled = Math.round(scaledValue);
  if (!Number.isSafeInteger(scaled) || Math.abs(scaledValue - scaled) > 1e-7) {
    return invalid('unsupported_precision', `${label} можно указать с точностью до 0,01 кг.`);
  }
  if (scaled < 0 || value > MAX_CALCULATOR_WEIGHT_KG) {
    return invalid(code, `${label} должен быть от 0 до ${MAX_CALCULATOR_WEIGHT_KG} кг.`);
  }
  return scaled;
}

type Combination = {
  counts: number[];
  plateCount: number;
};

function preferCombination(candidate: Combination, current: Combination): boolean {
  if (candidate.plateCount !== current.plateCount) {
    return candidate.plateCount < current.plateCount;
  }
  for (let index = 0; index < candidate.counts.length; index += 1) {
    const candidateCount = candidate.counts[index] ?? 0;
    const currentCount = current.counts[index] ?? 0;
    if (candidateCount !== currentCount) return candidateCount > currentCount;
  }
  return false;
}

export function calculatePlateLoadWithInventory(
  totalWeight: number,
  barWeight: number,
  inventory: readonly PlateInventoryEntry[],
): PlateLoadCalculationResult {
  const targetUnits = parseScaledWeight(totalWeight, 'invalid_target', 'целевой вес');
  if (typeof targetUnits !== 'number') return { ok: false, error: targetUnits };

  const barUnits = parseScaledWeight(barWeight, 'invalid_bar', 'вес грифа');
  if (typeof barUnits !== 'number') return { ok: false, error: barUnits };
  if (barUnits <= 0) {
    return { ok: false, error: invalid('invalid_bar', 'Вес грифа должен быть больше 0 кг.') };
  }
  if (targetUnits < barUnits) {
    return {
      ok: false,
      error: invalid('target_below_bar', 'Целевой вес не может быть меньше веса грифа.'),
    };
  }
  if (!Array.isArray(inventory) || inventory.length > MAX_INVENTORY_DENOMINATIONS) {
    return {
      ok: false,
      error: invalid(
        'invalid_inventory',
        `Добавьте не больше ${MAX_INVENTORY_DENOMINATIONS} размеров блинов.`,
      ),
    };
  }

  const seenWeights = new Set<number>();
  const normalizedInventory: Array<{ weight: number; units: number; count: number }> = [];
  let totalPlateCount = 0;
  let totalInventoryUnits = 0;
  for (const entry of inventory) {
    if (entry == null || typeof entry !== 'object') {
      return {
        ok: false,
        error: invalid('invalid_inventory', 'Инвентарь блинов имеет некорректный формат.'),
      };
    }
    const weightUnits = parseScaledWeight(entry.weight, 'invalid_denomination', 'вес блина');
    if (typeof weightUnits !== 'number') return { ok: false, error: weightUnits };
    if (weightUnits <= 0) {
      return {
        ok: false,
        error: invalid('invalid_denomination', 'Вес блина должен быть больше 0 кг.'),
      };
    }
    if (seenWeights.has(weightUnits)) {
      return {
        ok: false,
        error: invalid('duplicate_denomination', 'Размер блина не должен повторяться в инвентаре.'),
      };
    }
    seenWeights.add(weightUnits);
    if (!Number.isInteger(entry.count) || entry.count < 0) {
      return {
        ok: false,
        error: invalid('invalid_count', 'Количество блинов должно быть целым числом от 0.'),
      };
    }
    if (entry.count > MAX_PLATES_PER_DENOMINATION) {
      return {
        ok: false,
        error: invalid(
          'inventory_too_large',
          `Для одного размера доступно не больше ${MAX_PLATES_PER_DENOMINATION} блинов на сторону.`,
        ),
      };
    }
    totalPlateCount += entry.count;
    totalInventoryUnits += weightUnits * entry.count;
    normalizedInventory.push({
      weight: normalizeWeight(entry.weight),
      units: weightUnits,
      count: entry.count,
    });
  }
  if (
    totalPlateCount > MAX_INVENTORY_PLATES ||
    totalInventoryUnits > MAX_INVENTORY_WEIGHT_KG * CALCULATOR_SCALE
  ) {
    return {
      ok: false,
      error: invalid(
        'inventory_too_large',
        `Инвентарь ограничен ${MAX_INVENTORY_PLATES} блинами и ${MAX_INVENTORY_WEIGHT_KG} кг на сторону.`,
      ),
    };
  }

  normalizedInventory.sort((left, right) => right.units - left.units);
  const combinations = new Map<number, Combination>([[0, { counts: [], plateCount: 0 }]]);
  for (const entry of normalizedInventory) {
    const nextCombinations = new Map<number, Combination>();
    for (const [currentUnits, currentCombination] of combinations) {
      for (let count = 0; count <= entry.count; count += 1) {
        const units = currentUnits + count * entry.units;
        const candidate: Combination = {
          counts: [...currentCombination.counts, count],
          plateCount: currentCombination.plateCount + count,
        };
        const existing = nextCombinations.get(units);
        if (!existing || preferCombination(candidate, existing)) {
          nextCombinations.set(units, candidate);
        }
      }
    }
    combinations.clear();
    for (const [units, combination] of nextCombinations) combinations.set(units, combination);
  }

  const requestedPerSideUnits = targetUnits - barUnits;
  let bestUnits = 0;
  let bestCombination = combinations.get(0) ?? { counts: [], plateCount: 0 };
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const [sideUnits, combination] of combinations) {
    const distance = Math.abs(sideUnits * 2 - requestedPerSideUnits);
    if (distance < bestDistance) {
      bestUnits = sideUnits;
      bestCombination = combination;
      bestDistance = distance;
      continue;
    }
    if (distance !== bestDistance) continue;

    // Equal-distance ties intentionally choose the lower total load first.
    const candidateTotal = barUnits + sideUnits * 2;
    const currentTotal = barUnits + bestUnits * 2;
    if (candidateTotal < currentTotal) {
      bestUnits = sideUnits;
      bestCombination = combination;
      continue;
    }
    if (candidateTotal === currentTotal && preferCombination(combination, bestCombination)) {
      bestUnits = sideUnits;
      bestCombination = combination;
    }
  }

  const plates: number[] = [];
  normalizedInventory.forEach((entry, index) => {
    const count = bestCombination.counts[index] ?? 0;
    for (let plateIndex = 0; plateIndex < count; plateIndex += 1) {
      plates.push(entry.weight);
    }
  });
  const achievedTotalUnits = barUnits + bestUnits * 2;
  const differenceUnits = achievedTotalUnits - targetUnits;
  return {
    ok: true,
    calculation: {
      targetTotal: normalizeWeight(totalWeight),
      barWeight: normalizeWeight(barWeight),
      requestedPerSide: normalizeWeight(requestedPerSideUnits / (2 * CALCULATOR_SCALE)),
      achievedPerSide: normalizeWeight(bestUnits / CALCULATOR_SCALE),
      achievedTotal: normalizeWeight(achievedTotalUnits / CALCULATOR_SCALE),
      difference: normalizeWeight(differenceUnits / CALCULATOR_SCALE),
      exact: differenceUnits === 0,
      plates,
    },
  };
}

export function warmupSuggestions(workingWeight: number): number[] {
  if (!Number.isFinite(workingWeight) || workingWeight <= 20) return [];
  return [0.4, 0.6, 0.75]
    .map((ratio) => roundToHalf(workingWeight * ratio))
    .filter((weight, index, values) => weight >= 20 && values.indexOf(weight) === index);
}

function calculateLegacyPlateLoad(totalWeight: number, barWeight: number): PlateCalculation | null {
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

export function calculatePlateLoad(
  totalWeight: number,
  barWeight?: number,
): PlateCalculation | null;
export function calculatePlateLoad(
  totalWeight: number,
  barWeight: number,
  inventory: readonly PlateInventoryEntry[],
): PlateLoadCalculationResult;
export function calculatePlateLoad(
  totalWeight: number,
  barWeight = 20,
  inventory?: readonly PlateInventoryEntry[],
): PlateCalculation | PlateLoadCalculationResult | null {
  if (inventory !== undefined)
    return calculatePlateLoadWithInventory(totalWeight, barWeight, inventory);
  return calculateLegacyPlateLoad(totalWeight, barWeight);
}
