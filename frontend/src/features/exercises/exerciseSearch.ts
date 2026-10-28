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

function oneEditApart(left: string, right: string): boolean {
  if (left.length < 5 || left.slice(0, 2) !== right.slice(0, 2)) return false;
  if (Math.abs(left.length - right.length) > 1) return false;
  let i = 0;
  while (i < left.length && left[i] === right[i]) i += 1;
  if (left.length === right.length) {
    return (
      left.slice(i + 1) === right.slice(i + 1) ||
      (left[i] === right[i + 1] &&
        left[i + 1] === right[i] &&
        left.slice(i + 2) === right.slice(i + 2))
    );
  }
  return left.length > right.length
    ? left.slice(i + 1) === right.slice(i)
    : left.slice(i) === right.slice(i + 1);
}

function fuzzyMatches(value: string, tokens: string[]): boolean {
  const words = value.split(' ');
  let edits = 0;
  for (const token of tokens) {
    if (words.some((word) => word.includes(token))) continue;
    if (
      !words.some(
        (word) =>
          oneEditApart(token, word.slice(0, token.length + 1)) ||
          (word.length >= token.length && oneEditApart(token, word.slice(0, token.length - 1))),
      )
    )
      return false;
    edits += 1;
  }
  return edits === 1;
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
  if (tokens.every((token) => group.haystack.includes(token))) return 4;
  return [...group.titles, ...group.aliases].some((value) => fuzzyMatches(value, tokens))
    ? 5
    : null;
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
