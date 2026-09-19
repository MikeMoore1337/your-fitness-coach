import type { BodyMeasurement } from '../../shared/api/types';

type CanonicalMetric = {
  key: 'weight_kg' | 'chest_cm' | 'waist_cm' | 'hips_cm' | 'biceps_cm' | 'thigh_cm';
  label: string;
  unit: 'кг' | 'см';
};

type MeasurementFact = {
  label: string;
  value: number;
  unit: string;
  source: 'canonical' | 'custom';
};

const CANONICAL_METRICS: readonly CanonicalMetric[] = [
  { key: 'weight_kg', label: 'Вес', unit: 'кг' },
  { key: 'chest_cm', label: 'Грудь', unit: 'см' },
  { key: 'waist_cm', label: 'Талия', unit: 'см' },
  { key: 'hips_cm', label: 'Бёдра', unit: 'см' },
  { key: 'biceps_cm', label: 'Бицепс', unit: 'см' },
  { key: 'thigh_cm', label: 'Бедро', unit: 'см' },
];

function normalizeLabel(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toLocaleLowerCase('ru-RU');
}

function normalizeUnit(value: string): string {
  return value.trim().toLocaleLowerCase('ru-RU') === 'см' ? 'cm' : value.trim().toLowerCase();
}

function valueKey(value: number): string {
  return String(value);
}

function factKey(fact: MeasurementFact): string {
  return `${normalizeLabel(fact.label)}|${valueKey(fact.value)}|${normalizeUnit(fact.unit)}`;
}

function sameSemanticFact(left: MeasurementFact, right: MeasurementFact): boolean {
  return factKey(left) === factKey(right);
}

function formatFact(fact: MeasurementFact, ambiguousCustomLabel: boolean): string {
  const label = ambiguousCustomLabel ? `${fact.label} · пользовательский` : fact.label;
  return `${label} ${fact.value}${fact.unit ? ` ${fact.unit}` : ''}`;
}

export function formatMeasurementDetail(measurement: BodyMeasurement): string {
  const canonicalFacts = CANONICAL_METRICS.flatMap((metric): MeasurementFact[] => {
    const value = measurement[metric.key];
    return typeof value === 'number' && Number.isFinite(value)
      ? [{ label: metric.label, value, unit: metric.unit, source: 'canonical' }]
      : [];
  });

  const customFacts = (measurement.custom_values ?? []).flatMap((custom): MeasurementFact[] => {
    const label = typeof custom.label === 'string' ? custom.label.trim() : '';
    return label && typeof custom.value === 'number' && Number.isFinite(custom.value)
      ? [{ label, value: custom.value, unit: custom.unit ?? '', source: 'custom' }]
      : [];
  });

  const facts: MeasurementFact[] = [...canonicalFacts];
  const customDuplicates = new Set<string>();

  for (const custom of customFacts) {
    const duplicateCanonical = canonicalFacts.find((canonical) =>
      sameSemanticFact(canonical, custom),
    );
    if (duplicateCanonical) continue;
    const customKey = factKey(custom);
    if (customDuplicates.has(customKey)) continue;
    customDuplicates.add(customKey);
    facts.push(custom);
  }

  if (!facts.length) return 'Числовые значения не указаны';

  const labelCounts = new Map<string, number>();
  for (const fact of facts) {
    const key = normalizeLabel(fact.label);
    labelCounts.set(key, (labelCounts.get(key) ?? 0) + 1);
  }

  return facts
    .map((fact) => {
      const ambiguousCustom =
        fact.source === 'custom' &&
        (canonicalFacts.some(
          (canonical) => normalizeLabel(canonical.label) === normalizeLabel(fact.label),
        ) ||
          (labelCounts.get(normalizeLabel(fact.label)) ?? 0) > 1);
      return formatFact(fact, ambiguousCustom);
    })
    .join(' · ');
}
