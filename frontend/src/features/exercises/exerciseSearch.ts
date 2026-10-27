const punctuation = /[^\p{L}\p{N}]+/gu;

export type ExerciseSearchItem = {
  id: number;
  title: string;
  slug?: string | null;
  canonical_slug?: string | null;
  primary_muscle?: string | null;
  equipment?: string | null;
  aliases?: string[] | null;
  machine_variant_tags?: string[] | null;
  execution_variant_tags?: string[] | null;
  alternatives?: Array<{ title: string }> | null;
};

export function normalizeExerciseSearchText(value: string): string {
  return value
    .normalize('NFKC')
    .toLocaleLowerCase('ru-RU')
    .replaceAll('ё', 'е')
    .replace(punctuation, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

type SearchGroup<T extends ExerciseSearchItem> = {
  exercise: T;
  titles: string[];
  aliases: string[];
  haystack: string;
};

function canonicalKey(exercise: ExerciseSearchItem): string {
  return exercise.canonical_slug ?? exercise.slug ?? `exercise-${exercise.id}`;
}

function buildSearchGroups<T extends ExerciseSearchItem>(exercises: T[]): SearchGroup<T>[] {
  const grouped = new Map<string, T[]>();
  for (const exercise of exercises) {
    const key = canonicalKey(exercise);
    grouped.set(key, [...(grouped.get(key) ?? []), exercise]);
  }

  return [...grouped.entries()].map(([key, records]) => {
    const canonical = records.find((record) => record.slug === key) ?? records[0]!;
    const titles = records.map((record) => normalizeExerciseSearchText(record.title));
    const aliases = records.flatMap((record) =>
      (record.aliases ?? []).map(normalizeExerciseSearchText),
    );
    const searchableValues = records.flatMap((record) => [
      record.title,
      record.primary_muscle ?? '',
      record.equipment ?? '',
      ...(record.aliases ?? []),
      ...(record.machine_variant_tags ?? []),
      ...(record.execution_variant_tags ?? []),
      ...(record.alternatives ?? []).map((alternative) => alternative.title),
    ]);
    return {
      exercise: canonical,
      titles,
      aliases,
      haystack: normalizeExerciseSearchText(searchableValues.join(' ')),
    };
  });
}

function searchRank<T extends ExerciseSearchItem>(
  group: SearchGroup<T>,
  query: string,
): number | null {
  if (!query) return 0;
  if (group.titles.includes(query)) return 0;
  if (group.aliases.includes(query)) return 1;
  if (group.titles.some((title) => title.startsWith(query))) return 2;
  if (group.aliases.some((alias) => alias.startsWith(query))) return 3;

  const tokens = query.split(' ').filter(Boolean);
  return tokens.every((token) => group.haystack.includes(token)) ? 4 : null;
}

export function rankExercisesForSearch<T extends ExerciseSearchItem>(
  exercises: T[],
  rawQuery: string,
): T[] {
  const query = normalizeExerciseSearchText(rawQuery);
  return buildSearchGroups(exercises)
    .map((group) => ({ group, rank: searchRank(group, query) }))
    .filter((item): item is { group: SearchGroup<T>; rank: number } => item.rank !== null)
    .sort(
      (left, right) =>
        left.rank - right.rank ||
        left.group.exercise.title.localeCompare(right.group.exercise.title, 'ru'),
    )
    .map((item) => item.group.exercise);
}

export function matchesExerciseSearch<T extends ExerciseSearchItem>(
  exercise: T,
  rawQuery: string,
): boolean {
  return rankExercisesForSearch([exercise], rawQuery).length > 0;
}
