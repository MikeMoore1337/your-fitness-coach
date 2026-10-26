export const equipmentLabels: Readonly<Record<string, string>> = {
  bodyweight: 'Собственный вес',
  dumbbell: 'Гантели',
  barbell: 'Штанга',
  bench: 'Скамья',
  rack: 'Стойка/силовая рама',
  cable: 'Тросовый блок',
  machine: 'Тренажёр',
  kettlebell: 'Гиря',
  cardio: 'Кардиооборудование',
  other: 'Другое',
};

// shortcut: lowercase ASCII tokens are treated as technical IDs; distinguish custom labels at the source when available.
const technicalEquipmentIdentifier = /^[a-z][a-z0-9]*(?:[-_.:][a-z0-9]+)*$/;
const normalizedEquipmentLabels = new Map(
  Object.entries(equipmentLabels).flatMap(([identifier, label]) => [
    [identifier, label],
    [label.toLocaleLowerCase('ru-RU'), label],
  ]),
);

export function knownEquipmentLabel(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value.trim().toLocaleLowerCase('ru-RU');
  return normalizedEquipmentLabels.get(normalized) ?? null;
}

export function localizedEquipmentLabel(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value.trim();
  if (!normalized) return null;
  return (
    knownEquipmentLabel(normalized) ??
    (technicalEquipmentIdentifier.test(normalized) ? 'Неизвестное оборудование' : normalized)
  );
}

export function localizedEquipmentList(value: unknown): string {
  if (!Array.isArray(value) || !value.every((entry) => typeof entry === 'string')) {
    return 'Нет данных';
  }
  const entries = value.map((entry) => entry.trim());
  if (entries.some((entry) => !entry)) return 'Нет данных';
  if (!entries.length) return 'Не требуется (по данным шаблона)';

  const labels = new Map<string, string>();
  for (const entry of entries) {
    const label = localizedEquipmentLabel(entry);
    if (!label) return 'Нет данных';
    labels.set(label.toLocaleLowerCase('ru-RU'), label);
  }
  return [...labels.values()].join(' · ');
}

export function localizedEquipmentDisplayLabel(
  equipmentIds: readonly unknown[] | null | undefined,
  legacyValue: unknown,
): string | null {
  if (equipmentIds?.length) {
    const label = localizedEquipmentList(equipmentIds);
    if (label !== 'Нет данных') return label;
  }
  return localizedEquipmentLabel(legacyValue);
}
