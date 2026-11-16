import { useEffect, useId, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import { formatCalendarDate } from '../../shared/dateTime';
import { queryKeys, invalidateNutritionSummaries } from '../../shared/queryKeys';
import type {
  Food,
  FoodSearch,
  FoodDiaryBatchResponse,
  FoodDiaryNutrition,
  NutritionSuggestion,
  NutritionSuggestionCommitRequest,
  NutritionPlanDay,
  NutritionPlanFillRequest,
  NutritionSuggestions as NutritionSuggestionsResponse,
} from '../../shared/api/types';
import {
  Badge,
  Button,
  DisclosureIcon,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Select,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import type { MealType } from './FoodPickerDialog';
import { goalOptions } from './nutritionCalculatorOptions';
import styles from './NutritionSuggestions.module.css';

const mealLabels: Record<MealType, string> = {
  breakfast: 'Завтрак',
  lunch: 'Обед',
  dinner: 'Ужин',
  snacks: 'Перекусы',
};

const sourceLabels: Record<NutritionSuggestion['sources'][number], string> = {
  recent: 'Недавнее',
  frequent: 'Частое',
  favorite: 'Избранное',
  used: 'Уже использовали',
  saved_template: 'Сохранённый шаблон',
  personal_recipe: 'Личный рецепт',
};

const reasonLabels: Record<NutritionSuggestion['reasons'][number], string> = {
  protein_fit: 'Укладывается в известный остаток белка',
  lower_known_fat: 'Меньше известных жиров',
  recent: 'Недавнее',
  frequent: 'Частое',
  favorite: 'Избранное',
  used: 'Уже использовали',
  saved_template: 'Сохранённый шаблон',
  personal_recipe: 'Личный рецепт',
  partial_nutrition: 'Неполные БЖУ',
};

type ReviewItem = {
  key: string;
  item: NutritionSuggestion['items'][number];
  amount: string;
  amountUnit: NutritionSuggestion['items'][number]['amount_unit'];
};
type SuggestionMode = 'diary' | 'plan';
const limitFields = [
  { key: 'max_energy_kcal', label: 'Ккал', max: 10000, digits: 2 },
  { key: 'max_protein_g', label: 'Белки, г', max: 1000, digits: 3 },
  { key: 'max_fat_g', label: 'Жиры, г', max: 1000, digits: 3 },
  { key: 'max_carbs_g', label: 'Углеводы, г', max: 1000, digits: 3 },
] as const;
type LimitKey = (typeof limitFields)[number]['key'];
type SuggestionConstraints = Partial<Record<LimitKey, string>> & {
  preferred_food_ids: number[];
  excluded_food_ids: number[];
};
type FoodChoice = Pick<Food, 'id' | 'name' | 'brand'>;
type SuggestionPreview = {
  diary_date: string;
  meal_type: MealType;
  items: NutritionSuggestion['items'];
  before: FoodDiaryNutrition;
  addition: FoodDiaryNutrition;
  after: FoodDiaryNutrition;
  diary: FoodDiaryNutrition;
  planned: FoodDiaryNutrition | null;
  projected_after: FoodDiaryNutrition | null;
  targets: NutritionSuggestionsResponse['targets'];
  target_id: number | null;
  target_source: string | null;
  target_effective_from: string | null;
  target_weight_kg: string | null;
  target_goal: string | null;
  target_estimated_bmr_kcal?: number | null;
  target_estimated_tdee_kcal?: number | null;
  constraint_status: 'not_set' | 'satisfied' | 'violated' | 'unknown';
  constraint_messages: string[];
  preference_message: string | null;
  preview_token: string;
};

function isNutrition(value: unknown): value is FoodDiaryNutrition {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  const decimal = (entry: unknown) =>
    typeof entry === 'string' && entry.trim() !== '' && Number.isFinite(Number(entry));
  return (
    decimal(data.energy_kcal) &&
    ['protein_g', 'fat_g', 'carbs_g', 'fiber_g'].every(
      (field) => data[field] === null || decimal(data[field]),
    )
  );
}

const targetSourceLabels: Record<string, string> = {
  manual: 'ручное назначение',
  trainer: 'назначение тренера',
  calculated: 'расчёт',
  adaptive: 'адаптивная цель',
};

function formatNumber(value: string | number | null | undefined, fractionDigits = 1): string {
  if (value === null || value === undefined) return '—';
  const number = Number(value);
  return Number.isFinite(number)
    ? new Intl.NumberFormat('ru-RU', { maximumFractionDigits: fractionDigits }).format(number)
    : '—';
}

function macroLine(nutrition: FoodDiaryNutrition): string {
  return `Б ${formatNumber(nutrition.protein_g, 3)} · Ж ${formatNumber(nutrition.fat_g, 3)} · У ${formatNumber(nutrition.carbs_g, 3)}`;
}

function nutritionSummary(nutrition: FoodDiaryNutrition | null): string {
  return `${formatNumber(nutrition?.energy_kcal, 2)} ккал · Б ${formatNumber(nutrition?.protein_g, 3)} г · Ж ${formatNumber(nutrition?.fat_g, 3)} г · У ${formatNumber(nutrition?.carbs_g, 3)} г · клетчатка ${formatNumber(nutrition?.fiber_g, 3)} г`;
}

function confidenceLabel(confidence: NutritionSuggestion['nutrition_confidence']): string {
  if (confidence === 'partial') return 'Частичные БЖУ';
  if (confidence === 'approximate') return 'Приблизительные БЖУ';
  return 'БЖУ указаны';
}

function tagLabel(
  value: NutritionSuggestion['reasons'][number] | NutritionSuggestion['sources'][number],
): string {
  return value in reasonLabels
    ? reasonLabels[value as NutritionSuggestion['reasons'][number]]
    : sourceLabels[value as NutritionSuggestion['sources'][number]];
}

function requestKey(): string {
  const suffix =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;
  return `nutrition-suggestion-${suffix}`;
}

function reviewItemPayload(item: ReviewItem): NutritionSuggestionCommitRequest['items'][number] {
  if (item.item.food_id != null) {
    return { food_id: item.item.food_id, amount: item.amount, amount_unit: item.amountUnit };
  }
  if (item.item.recipe_id != null) {
    return { recipe_id: item.item.recipe_id, amount: item.amount, amount_unit: 'g' };
  }
  throw new Error('У варианта отсутствует подтверждённая identity.');
}

function planReviewItemPayload(item: ReviewItem): NutritionPlanFillRequest['items'][number] {
  if (item.item.food_id != null) {
    return {
      position: item.item.position,
      food_id: item.item.food_id,
      amount: item.amount,
      amount_unit: item.amountUnit,
    };
  }
  if (item.item.recipe_id != null) {
    return {
      position: item.item.position,
      recipe_id: item.item.recipe_id,
      amount: item.amount,
      amount_unit: 'g',
    };
  }
  throw new Error('У варианта отсутствует подтверждённая identity.');
}

function CandidateCard({
  candidate,
  remaining,
  compact = false,
  onSelect,
}: {
  candidate: NutritionSuggestion;
  remaining: NutritionSuggestionsResponse['remaining'];
  compact?: boolean;
  onSelect: (candidate: NutritionSuggestion) => void;
}) {
  const nameId = useId();
  const values = [...candidate.sources, ...candidate.reasons].filter(
    (value, index, all) => value !== 'lower_known_fat' && all.indexOf(value) === index,
  );
  const protein = candidate.nutrition.protein_g;
  const proteinRemaining = remaining?.protein_g;
  const proteinIndex = values.indexOf('protein_fit');
  if (proteinIndex >= 0) {
    values.splice(proteinIndex, 1);
    if (
      protein != null &&
      proteinRemaining != null &&
      Number(protein) > 0 &&
      Number(protein) <= Number(proteinRemaining)
    ) {
      values.splice(Math.min(1, values.length), 0, 'protein_fit');
    }
  }
  const tags = values.map((value) =>
    value === 'protein_fit'
      ? `${formatNumber(protein, 3)} г белка в пределах известного остатка ${formatNumber(proteinRemaining, 3)} г`
      : tagLabel(value),
  );
  let overageCount = 0;
  if (remaining) {
    const metrics = [
      ['energy_kcal', 'калории', 'ккал'],
      ['protein_g', 'белки', 'г'],
      ['fat_g', 'жиры', 'г'],
      ['carbs_g', 'углеводы', 'г'],
    ] as const;
    const overages: string[] = [];
    for (const [field, label, unit] of metrics) {
      const value = candidate.nutrition[field];
      const available = remaining[field];
      if (value != null && available != null && Number(value) > Math.max(Number(available), 0)) {
        const digits = field === 'energy_kcal' ? 2 : 3;
        overages.push(
          `${label}: ${formatNumber(value, digits)} ${unit} при остатке ${formatNumber(available, digits)} ${unit}`,
        );
      }
    }
    overageCount = overages.length;
    tags.unshift(...overages);
  }
  if (compact) {
    const facts = tags.filter(
      (tag) =>
        candidate.nutrition_confidence !== 'partial' || tag !== reasonLabels.partial_nutrition,
    );
    const visibleFactCount = Math.max(2, overageCount);
    return (
      <li className={`nutrition-suggestion-card ${styles.compactCard}`}>
        <strong id={nameId}>{candidate.name}</strong>
        <span className={styles.facts}>
          {formatNumber(candidate.nutrition.energy_kcal, 2)} ккал · {macroLine(candidate.nutrition)}{' '}
          · клетчатка {formatNumber(candidate.nutrition.fiber_g, 3)} г
        </span>
        <span className={styles.facts}>
          {candidate.nutrition_confidence !== 'exact' && (
            <>
              <span>{confidenceLabel(candidate.nutrition_confidence)}</span>
              {facts.length ? ' · ' : ''}
            </>
          )}
          {facts.slice(0, visibleFactCount).join(' · ')}
        </span>
        {facts.length > visibleFactCount && (
          <details className={styles.details}>
            <summary className="yfc-disclosure-summary">
              <span>Другие основания: {candidate.name}</span>
              <DisclosureIcon />
            </summary>
            <p>{facts.slice(visibleFactCount).join(' · ')}</p>
          </details>
        )}
        <Button
          type="button"
          variant="secondary"
          aria-describedby={nameId}
          onClick={() => onSelect(candidate)}
        >
          Проверить вариант
        </Button>
      </li>
    );
  }
  return (
    <li className="nutrition-suggestion-card">
      <div className="nutrition-suggestion-card__head">
        <div>
          <strong>{candidate.name}</strong>
          <span>
            {formatNumber(candidate.nutrition.energy_kcal, 2)} ккал ·{' '}
            {macroLine(candidate.nutrition)} · клетчатка{' '}
            {formatNumber(candidate.nutrition.fiber_g, 3)} г
          </span>
        </div>
        <Badge tone={candidate.nutrition_confidence === 'partial' ? 'warning' : 'neutral'}>
          {confidenceLabel(candidate.nutrition_confidence)}
        </Badge>
      </div>
      <div className="nutrition-suggestion-card__tags" aria-label="Почему вариант показан">
        {tags.map((tag) => (
          <span className="nutrition-suggestion-tag" key={tag}>
            {tag}
          </span>
        ))}
      </div>
      <p className="nutrition-suggestion-card__note">
        Вариант из сохранённых данных, не предписание.
      </p>
      <Button type="button" variant="secondary" onClick={() => onSelect(candidate)}>
        Проверить вариант
      </Button>
    </li>
  );
}

function DiaryCandidateList({
  candidates,
  remaining,
  onSelect,
}: {
  candidates: NutritionSuggestion[];
  remaining: NutritionSuggestionsResponse['remaining'];
  onSelect: (candidate: NutritionSuggestion) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const additionalId = useId();
  const plural = new Intl.PluralRules('ru').select(candidates.length);
  const word = plural === 'one' ? 'вариант' : plural === 'few' ? 'варианта' : 'вариантов';
  const renderCards = (items: NutritionSuggestion[]) =>
    items.map((candidate) => (
      <CandidateCard
        candidate={candidate}
        remaining={remaining}
        compact
        key={candidate.candidate_id}
        onSelect={onSelect}
      />
    ));

  return (
    <>
      <p className={styles.note}>Варианты из сохранённых данных, не предписание.</p>
      <ul className="nutrition-suggestions__list">{renderCards(candidates.slice(0, 2))}</ul>
      {candidates.length > 2 && (
        <>
          <Button
            className={styles.toggle}
            type="button"
            variant="secondary"
            aria-expanded={expanded}
            aria-controls={additionalId}
            onClick={() => setExpanded((current) => !current)}
          >
            {expanded ? 'Свернуть' : `Показать все ${candidates.length} ${word}`}
          </Button>
          <div id={additionalId} hidden={!expanded}>
            <ul className="nutrition-suggestions__list">{renderCards(candidates.slice(2))}</ul>
          </div>
        </>
      )}
    </>
  );
}

function FoodChoiceEditor({
  kind,
  selected,
  opposite,
  disabled,
  onChange,
  onPendingChange,
}: {
  kind: 'preferred' | 'excluded';
  selected: FoodChoice[];
  opposite: FoodChoice[];
  disabled: boolean;
  onChange: (items: FoodChoice[]) => void;
  onPendingChange: (pending: boolean) => void;
}) {
  const inputId = useId();
  const listId = useId();
  const [input, setInput] = useState('');
  const [settled, setSettled] = useState('');
  const [choice, setChoice] = useState<FoodChoice | null>(null);
  const query = input.trim().replace(/\s+/g, ' ');
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  const search = useQuery({
    queryKey: ['nutrition', 'suggestion-food-search', settled],
    queryFn: ({ signal }) =>
      api<FoodSearch>(`/api/v1/nutrition/foods/search?q=${encodeURIComponent(settled)}&limit=20`, {
        signal,
      }),
    enabled: !choice && query.length >= 2 && query === settled,
    retry: false,
  });
  const foods = query === settled ? (search.data?.items ?? []) : [];
  const labels = foods.map((food) => `${food.name}${food.brand ? ` — ${food.brand}` : ''}`);
  const options = foods.map((food, index) => ({
    food,
    label:
      labels.indexOf(labels[index]!) === labels.lastIndexOf(labels[index]!)
        ? labels[index]!
        : `${labels[index]} · №${food.id}`,
  }));
  const selectedChoice = choice ?? options.find((option) => option.label === input)?.food ?? null;
  const alreadySelected = selectedChoice && selected.some((food) => food.id === selectedChoice.id);
  const conflicts = selectedChoice && opposite.some((food) => food.id === selectedChoice.id);
  const preferred = kind === 'preferred';
  const heading = preferred ? 'Предпочитаю продукты' : 'Исключить продукты';
  const inputLabel = preferred ? 'Найти предпочитаемый продукт' : 'Найти исключаемый продукт';

  return (
    <div className={styles.foodChoices}>
      <h4>{heading}</h4>
      <p className={styles.choiceHint}>
        {preferred
          ? 'Выберите продукт из каталога, чтобы проверить его наличие в варианте.'
          : 'Проверяются продукты и известные ингредиенты рецептов.'}
      </p>
      <div className={styles.choiceRow}>
        <Field label="Продукт" labelFor={inputId}>
          <Input
            id={inputId}
            list={listId}
            aria-label={inputLabel}
            placeholder="Найти продукт"
            value={input}
            disabled={disabled}
            autoComplete="off"
            onChange={(event) => {
              const value = event.target.value;
              setInput(value);
              onPendingChange(value.trim().length > 0);
              setChoice(options.find((option) => option.label === value)?.food ?? null);
            }}
          />
        </Field>
        <datalist id={listId}>
          {options.map((option) => (
            <option key={option.food.id} value={option.label} />
          ))}
        </datalist>
        <Button
          type="button"
          variant="secondary"
          aria-label={
            preferred ? 'Добавить предпочитаемый продукт' : 'Добавить исключаемый продукт'
          }
          disabled={
            disabled ||
            !selectedChoice ||
            Boolean(alreadySelected || conflicts) ||
            selected.length >= 50
          }
          onClick={() => {
            if (!selectedChoice || alreadySelected || conflicts || selected.length >= 50) return;
            onChange([...selected, selectedChoice]);
            setChoice(null);
            setInput('');
            onPendingChange(false);
          }}
        >
          Добавить
        </Button>
      </div>
      {!choice && query.length > 0 && query.length < 2 && (
        <p className={styles.choiceHint}>Введите не менее двух символов.</p>
      )}
      {search.isFetching && !choice && <p className={styles.choiceHint}>Ищем продукты…</p>}
      {search.error && query === settled && !choice && (
        <ErrorState
          message="Не удалось найти продукты."
          retry={() => void search.refetch()}
          retryLabel="Повторить поиск"
        />
      )}
      {search.isSuccess && !search.isFetching && query === settled && !choice && !foods.length && (
        <p className={styles.choiceHint}>Продукты не найдены.</p>
      )}
      {alreadySelected && <p className={styles.choiceHint}>Этот продукт уже добавлен.</p>}
      {conflicts && <p className={styles.choiceHint}>Продукт указан в другом списке.</p>}
      {selected.length >= 50 && (
        <p className={styles.choiceHint}>Можно добавить не более 50 продуктов.</p>
      )}
      {selected.length > 0 && (
        <ul className={styles.selectedFoods}>
          {selected.map((food) => (
            <li key={food.id}>
              <span>
                {food.name}
                {food.brand ? ` — ${food.brand}` : ''}
              </span>
              <Button
                type="button"
                variant="ghost"
                disabled={disabled}
                aria-label={`Убрать ${food.name} ${preferred ? 'из предпочтений' : 'из исключений'}`}
                onClick={() => onChange(selected.filter((item) => item.id !== food.id))}
              >
                Убрать
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TargetFacts({ preview }: { preview: SuggestionPreview }) {
  const goal = preview.target_goal;
  const goalLabel =
    goal && Object.hasOwn(goalOptions, goal)
      ? goalOptions[goal as keyof typeof goalOptions].label
      : '—';
  if (!preview.targets) return null;
  return (
    <p className={styles.note}>
      Цель на{' '}
      {formatCalendarDate(preview.diary_date, { day: 'numeric', month: 'long', year: 'numeric' })}:{' '}
      {formatNumber(preview.targets.energy_kcal, 2)} ккал · Б{' '}
      {formatNumber(preview.targets.protein_g, 3)} г · Ж {formatNumber(preview.targets.fat_g, 3)} г
      · У {formatNumber(preview.targets.carbs_g, 3)} г. Запись цели №{' '}
      {formatNumber(preview.target_id, 0)} ·{' '}
      {targetSourceLabels[preview.target_source ?? ''] ?? 'источник не указан'} · действует с{' '}
      {preview.target_effective_from ?? '—'} · вес: {formatNumber(preview.target_weight_kg, 2)} кг ·
      цель расчёта: {goalLabel}. Расчётный основной обмен:{' '}
      {formatNumber(preview.target_estimated_bmr_kcal, 0)} ккал · расчётный общий расход:{' '}
      {formatNumber(preview.target_estimated_tdee_kcal, 0)} ккал.
    </p>
  );
}

function PreviewTable({ preview, mode }: { preview: SuggestionPreview; mode: SuggestionMode }) {
  const rows: { field: keyof FoodDiaryNutrition; label: string }[] = [
    { field: 'energy_kcal', label: 'Ккал' },
    { field: 'protein_g', label: 'Белки, г' },
    { field: 'fat_g', label: 'Жиры, г' },
    { field: 'carbs_g', label: 'Углеводы, г' },
    { field: 'fiber_g', label: 'Клетчатка, г' },
  ];
  return (
    <>
      <div>
        <strong>{mode === 'plan' ? 'Как изменится план' : 'Как изменится день'}</strong>
        <table className={styles.previewTable}>
          <thead>
            <tr>
              <th scope="col">Показатель</th>
              <th scope="col">Было</th>
              <th scope="col">Вариант</th>
              <th scope="col">Станет</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ field, label }) => (
              <tr key={field}>
                <th scope="row">{label}</th>
                <td>{formatNumber(preview.before[field], field === 'energy_kcal' ? 2 : 3)}</td>
                <td>
                  {preview.addition[field] != null && Number(preview.addition[field]) > 0
                    ? '+'
                    : ''}
                  {formatNumber(preview.addition[field], field === 'energy_kcal' ? 2 : 3)}
                </td>
                <td>{formatNumber(preview.after[field], field === 'energy_kcal' ? 2 : 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={styles.note}>
        {mode === 'plan' ? 'Записано в дневнике' : 'Ещё запланировано, но не съедено'}:{' '}
        {nutritionSummary(mode === 'plan' ? preview.diary : preview.planned)}.
      </p>
      <p className={styles.note}>
        Прогноз дня после добавления: {nutritionSummary(preview.projected_after)}.
      </p>
      <p className={styles.note}>
        Неизвестные значения отмечены знаком «—». Полнота данных не гарантирует их точность.
      </p>
    </>
  );
}

function SuggestionReview({
  candidate,
  diaryDate,
  initialMealType,
  mode,
  planRevision,
  disabled,
  onCancel,
  onSubmit,
  pending,
}: {
  candidate: NutritionSuggestion;
  diaryDate: string;
  initialMealType: MealType;
  mode: SuggestionMode;
  planRevision?: number;
  disabled: boolean;
  onCancel: () => void;
  onSubmit: (
    mealType: MealType,
    items: ReviewItem[],
    previewToken: string,
    constraints: SuggestionConstraints | undefined,
  ) => void;
  pending: boolean;
}) {
  const [mealType, setMealType] = useState<MealType>(initialMealType);
  const [items, setItems] = useState<ReviewItem[]>(() =>
    candidate.items.map((item) => ({
      key: `${item.item_kind}:${item.food_id ?? item.recipe_id}:${item.position}`,
      item,
      amount: item.amount,
      amountUnit: item.amount_unit,
    })),
  );
  const limitId = useId();
  const [limits, setLimits] = useState<Record<LimitKey, string>>({
    max_energy_kcal: '',
    max_protein_g: '',
    max_fat_g: '',
    max_carbs_g: '',
  });
  const [preferredFoods, setPreferredFoods] = useState<FoodChoice[]>([]);
  const [excludedFoods, setExcludedFoods] = useState<FoodChoice[]>([]);
  const [preferredPending, setPreferredPending] = useState(false);
  const [excludedPending, setExcludedPending] = useState(false);
  const invalidLimits = limitFields.filter(({ key, max, digits }) => {
    const value = limits[key].trim();
    return (
      value !== '' &&
      (!new RegExp(`^\\d+(?:\\.\\d{1,${digits}})?$`).test(value) || Number(value) > max)
    );
  });
  const hasConstraints =
    limitFields.some(({ key }) => limits[key].trim() !== '') ||
    preferredFoods.length > 0 ||
    excludedFoods.length > 0;
  const constraints: SuggestionConstraints | undefined = hasConstraints
    ? {
        ...Object.fromEntries(
          limitFields
            .filter(({ key }) => limits[key].trim() !== '')
            .map(({ key }) => [key, limits[key].trim()]),
        ),
        preferred_food_ids: preferredFoods.map((food) => food.id),
        excluded_food_ids: excludedFoods.map((food) => food.id),
      }
    : undefined;
  const body =
    mode === 'plan'
      ? {
          plan_date: diaryDate,
          meal_type: mealType,
          candidate_id: candidate.candidate_id,
          items: items.map(planReviewItemPayload),
          expected_revision: planRevision,
          ...(constraints ? { constraints } : {}),
        }
      : {
          diary_date: diaryDate,
          meal_type: mealType,
          items: items.map(reviewItemPayload),
          ...(constraints ? { constraints } : {}),
        };
  const request = JSON.stringify(body);
  const [settledRequest, setSettledRequest] = useState(request);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettledRequest(request), 250);
    return () => window.clearTimeout(timer);
  }, [request]);
  const canPreview =
    items.length > 0 &&
    items.every((item) => Number.isFinite(Number(item.amount)) && Number(item.amount) > 0) &&
    invalidLimits.length === 0 &&
    (mode !== 'plan' || planRevision != null);
  const preview = useQuery({
    queryKey: ['nutrition-suggestion-preview', mode, request],
    queryFn: async ({ signal }) => {
      const result = await api<SuggestionPreview>(
        mode === 'plan'
          ? '/api/v1/nutrition/plans/suggestions/preview'
          : '/api/v1/nutrition/diary/suggestions/preview',
        { method: 'POST', body, signal },
      );
      if (
        !result ||
        result.diary_date !== diaryDate ||
        result.meal_type !== mealType ||
        !Array.isArray(result.items) ||
        result.items.length !== items.length ||
        !result.items.every((item, index) => {
          const selected = items[index]!;
          return (
            item != null &&
            typeof item === 'object' &&
            item.food_id === selected.item.food_id &&
            item.recipe_id === selected.item.recipe_id &&
            Number(item.amount) === Number(selected.amount) &&
            item.amount_unit === selected.amountUnit &&
            isNutrition(item.nutrition)
          );
        }) ||
        !isNutrition(result.before) ||
        !isNutrition(result.addition) ||
        !isNutrition(result.after) ||
        !isNutrition(result.diary) ||
        (result.planned !== null && !isNutrition(result.planned)) ||
        (result.projected_after !== null && !isNutrition(result.projected_after)) ||
        !result.targets ||
        !isNutrition({ ...result.targets, fiber_g: null }) ||
        !Number.isSafeInteger(result.target_id) ||
        (result.target_id ?? 0) <= 0 ||
        typeof result.target_effective_from !== 'string' ||
        !Array.isArray(result.constraint_messages) ||
        !result.constraint_messages.every((message) => typeof message === 'string') ||
        (result.preference_message !== null && typeof result.preference_message !== 'string') ||
        (preferredFoods.length > 0 && !result.preference_message) ||
        ((limitFields.some(({ key }) => limits[key].trim() !== '') || excludedFoods.length > 0) &&
          result.constraint_status === 'not_set') ||
        typeof result.preview_token !== 'string' ||
        !/^[0-9a-f]{64}$/.test(result.preview_token) ||
        !['not_set', 'satisfied', 'violated', 'unknown'].includes(result.constraint_status)
      ) {
        throw new Error('Не удалось получить точный расчёт. Повторите попытку.');
      }
      return result;
    },
    enabled: canPreview && request === settledRequest,
    retry: false,
  });
  const previewReady =
    canPreview &&
    !preferredPending &&
    !excludedPending &&
    request === settledRequest &&
    !preview.isFetching &&
    !preview.error &&
    preview.data != null &&
    preview.data.constraint_status !== 'violated' &&
    preview.data.constraint_status !== 'unknown';

  return (
    <form
      className="nutrition-suggestion-review"
      onSubmit={(event) => {
        event.preventDefault();
        if (previewReady && preview.data)
          onSubmit(mealType, items, preview.data.preview_token, constraints);
      }}
    >
      <div className="nutrition-suggestion-review__head">
        <div>
          <span className="eyebrow">
            {mode === 'plan' ? 'Проверка перед планированием' : 'Проверка перед записью'}
          </span>
          <h3>{candidate.name}</h3>
        </div>
      </div>
      <p className="muted">
        {mode === 'plan'
          ? 'Ничего не попадёт в план до подтверждения.'
          : 'Ничего не попадёт в дневник до подтверждения.'}
      </p>
      {request === settledRequest && !preview.isFetching && preview.data && (
        <TargetFacts preview={preview.data} />
      )}
      <Field label="Приём пищи" labelFor="nutrition-suggestion-meal-type">
        <Select
          id="nutrition-suggestion-meal-type"
          value={mealType}
          onChange={(event) => setMealType(event.target.value as MealType)}
          disabled={disabled}
        >
          {(Object.keys(mealLabels) as MealType[]).map((value) => (
            <option key={value} value={value}>
              {mealLabels[value]}
            </option>
          ))}
        </Select>
      </Field>
      <div className="nutrition-suggestion-review__items">
        {items.map((reviewItem, index) => {
          const amountId = `nutrition-suggestion-amount-${reviewItem.key}`;
          const unitId = `nutrition-suggestion-unit-${reviewItem.key}`;
          return (
            <div className="nutrition-suggestion-review__item" key={reviewItem.key}>
              <div>
                <strong>{reviewItem.item.name}</strong>
                <span>
                  {preview.data?.items?.[index] && request === settledRequest && !preview.isFetching
                    ? macroLine(preview.data.items[index].nutrition)
                    : 'Рассчитываем выбранное количество…'}
                </span>
              </div>
              <Field label="Количество" labelFor={amountId}>
                <Input
                  id={amountId}
                  type="number"
                  inputMode="decimal"
                  min="0.001"
                  step="any"
                  required
                  value={reviewItem.amount}
                  disabled={disabled}
                  onChange={(event) =>
                    setItems((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, amount: event.target.value } : item,
                      ),
                    )
                  }
                />
              </Field>
              <Field label="Единица" labelFor={unitId}>
                <Select
                  id={unitId}
                  value={reviewItem.amountUnit}
                  disabled={disabled || reviewItem.item.recipe_id != null}
                  onChange={(event) =>
                    setItems((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index
                          ? {
                              ...item,
                              amountUnit: event.target.value as ReviewItem['amountUnit'],
                            }
                          : item,
                      ),
                    )
                  }
                >
                  <option value="g">граммы</option>
                  {reviewItem.item.amount_unit === 'ml' && <option value="ml">миллилитры</option>}
                  {reviewItem.item.amount_unit === 'serving' && (
                    <option value="serving">порции</option>
                  )}
                </Select>
              </Field>
              {items.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  disabled={disabled}
                  onClick={() =>
                    setItems((current) => current.filter((item) => item.key !== reviewItem.key))
                  }
                >
                  Убрать
                </Button>
              )}
            </div>
          );
        })}
      </div>
      {items.length === 0 && (
        <p className="nutrition-inline-error">Оставьте хотя бы один элемент.</p>
      )}
      {canPreview && (request !== settledRequest || preview.isFetching) && (
        <LoadingState label="Рассчитываем вариант…" />
      )}
      {request === settledRequest && preview.error && (
        <ErrorState
          message={(preview.error as Error).message}
          retry={() => void preview.refetch()}
          retryLabel="Обновить расчёт"
        />
      )}
      {request === settledRequest && !preview.isFetching && preview.data && (
        <PreviewTable preview={preview.data} mode={mode} />
      )}
      <details className={styles.constraints}>
        <summary className="yfc-disclosure-summary">
          <span>Предпочтения и ограничения</span>
          <DisclosureIcon />
        </summary>
        <p className={styles.choiceHint}>
          Необязательно. Действуют только при этой проверке и не сохраняются в профиле. Пустое поле
          означает, что предел неизвестен.
        </p>
        <h4>Верхние пределы на день с учётом плана</h4>
        <div className={styles.limitGrid}>
          {limitFields.map(({ key, label, max, digits }) => (
            <Field key={key} label={label} labelFor={`${limitId}-${key}`}>
              <Input
                id={`${limitId}-${key}`}
                type="number"
                inputMode="decimal"
                min="0"
                max={max}
                step={digits === 2 ? '0.01' : '0.001'}
                placeholder="Не задан"
                value={limits[key]}
                disabled={disabled}
                aria-invalid={invalidLimits.some((field) => field.key === key) || undefined}
                onChange={(event) =>
                  setLimits((current) => ({ ...current, [key]: event.target.value }))
                }
              />
            </Field>
          ))}
        </div>
        <FoodChoiceEditor
          kind="preferred"
          selected={preferredFoods}
          opposite={excludedFoods}
          disabled={disabled}
          onChange={setPreferredFoods}
          onPendingChange={setPreferredPending}
        />
        <FoodChoiceEditor
          kind="excluded"
          selected={excludedFoods}
          opposite={preferredFoods}
          disabled={disabled}
          onChange={setExcludedFoods}
          onPendingChange={setExcludedPending}
        />
        {!hasConstraints && (
          <p className={styles.choiceHint}>Предпочтения и ограничения не заданы.</p>
        )}
      </details>
      {invalidLimits.length > 0 && (
        <p className="nutrition-inline-error" role="alert">
          Проверьте пределы: укажите неотрицательное число в допустимом диапазоне и с допустимой
          точностью.
        </p>
      )}
      {(preferredPending || excludedPending) && (
        <p className={styles.choiceHint} role="status">
          Добавьте выбранный продукт или очистите поле поиска.
        </p>
      )}
      {request === settledRequest && !preview.isFetching && preview.data && (
        <div
          role="status"
          className={
            preview.data.constraint_status === 'violated' ||
            preview.data.constraint_status === 'unknown'
              ? 'nutrition-inline-error'
              : styles.choiceHint
          }
        >
          {preview.data.constraint_messages.map((message) => (
            <p key={message}>{message}</p>
          ))}
          {preview.data.preference_message && <p>{preview.data.preference_message}</p>}
        </div>
      )}
      <div className="nutrition-suggestion-review__actions">
        <Button type="submit" disabled={disabled || pending || !previewReady}>
          {pending ? 'Добавляем…' : mode === 'plan' ? 'Добавить в план' : 'Добавить выбранное'}
        </Button>
        <Button type="button" variant="ghost" disabled={pending} onClick={onCancel}>
          Вернуться к вариантам
        </Button>
      </div>
    </form>
  );
}

export function NutritionSuggestions({
  diaryDate,
  initialMealType,
  readOnly = false,
  demoSafeMode = false,
  mode = 'diary',
  planRevision,
  onPlanFilled,
}: {
  diaryDate: string;
  initialMealType: MealType;
  readOnly?: boolean;
  demoSafeMode?: boolean;
  mode?: SuggestionMode;
  planRevision?: number;
  onPlanFilled?: (day: NutritionPlanDay) => Promise<void>;
}) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const idempotencyKey = useRef<string | null>(null);
  const submittedPreview = useRef<string | null>(null);
  const titleId = `nutrition-suggestions-title-${mode}`;
  const contentId = useId();
  const [diaryExpanded, setDiaryExpanded] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState<NutritionSuggestion | null>(null);
  const suggestions = useQuery({
    queryKey:
      mode === 'plan'
        ? queryKeys.nutrition.planSuggestions(diaryDate)
        : queryKeys.nutrition.suggestions(diaryDate),
    queryFn: () =>
      api<
        NutritionSuggestionsResponse & {
          not_calculable?: boolean;
          remaining_includes_plan?: boolean;
        }
      >(
        mode === 'plan'
          ? `/api/v1/nutrition/plans/suggestions?plan_date=${diaryDate}`
          : `/api/v1/nutrition/diary/suggestions?diary_date=${diaryDate}`,
      ),
    enabled: !demoSafeMode,
  });
  const commit = useMutation<
    FoodDiaryBatchResponse | NutritionPlanDay,
    Error,
    {
      mealType: MealType;
      items: ReviewItem[];
      previewToken: string;
      constraints: SuggestionConstraints | undefined;
    }
  >({
    mutationFn: ({ mealType, items, previewToken, constraints }) => {
      if (submittedPreview.current !== previewToken) {
        idempotencyKey.current = null;
        submittedPreview.current = previewToken;
      }
      idempotencyKey.current ??= requestKey();
      if (mode === 'plan') {
        if (planRevision == null || selectedCandidate == null) {
          throw new Error('План изменился. Выберите вариант ещё раз.');
        }
        return api<NutritionPlanDay>('/api/v1/nutrition/plans/fill', {
          method: 'POST',
          headers: { 'Idempotency-Key': idempotencyKey.current },
          body: {
            plan_date: diaryDate,
            meal_type: mealType,
            candidate_id: selectedCandidate.candidate_id,
            items: items.map(planReviewItemPayload),
            expected_revision: planRevision,
            preview_token: previewToken,
            ...(constraints ? { constraints } : {}),
          } satisfies NutritionPlanFillRequest & {
            preview_token: string;
            constraints?: SuggestionConstraints;
          },
        });
      }
      return api<FoodDiaryBatchResponse>('/api/v1/nutrition/diary/suggestions/commit', {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey.current },
        body: {
          diary_date: diaryDate,
          meal_type: mealType,
          items: items.map(reviewItemPayload),
          preview_token: previewToken,
          ...(constraints ? { constraints } : {}),
        } satisfies NutritionSuggestionCommitRequest & {
          preview_token: string;
          constraints?: SuggestionConstraints;
        },
      });
    },
    onSuccess: async (result) => {
      if (mode === 'plan') {
        await onPlanFilled?.(result as NutritionPlanDay);
        await queryClient.invalidateQueries({
          queryKey: queryKeys.nutrition.planSuggestions(diaryDate),
        });
        toast('Вариант добавлен в план');
      } else {
        await Promise.all([
          invalidateNutritionSummaries(queryClient),
          queryClient.invalidateQueries({ queryKey: queryKeys.nutrition.suggestions(diaryDate) }),
          queryClient.invalidateQueries({
            queryKey: queryKeys.nutrition.planSuggestions(diaryDate),
          }),
          queryClient.resetQueries({ queryKey: ['workout', 'nutrition-report', 'me'] }),
        ]);
        toast('Вариант добавлен в дневник');
      }
      idempotencyKey.current = null;
      submittedPreview.current = null;
      setSelectedCandidate(null);
    },
  });

  const limitations = (suggestions.data?.limitations ?? []).filter(
    (message) =>
      message !==
        'Это варианты из уже сохранённых продуктов, рецептов и шаблонов, а не предписание.' &&
      message !== 'Проверьте состав и количество перед добавлением.',
  );
  const heading = (
    <h2 id={titleId}>
      {mode === 'diary' ? (
        <button
          type="button"
          className={styles.sectionToggle}
          aria-expanded={diaryExpanded}
          aria-controls={contentId}
          onClick={() => setDiaryExpanded((value) => !value)}
        >
          Варианты из вашей еды
          <DisclosureIcon />
        </button>
      ) : (
        'Варианты для плана'
      )}
    </h2>
  );

  if (demoSafeMode) {
    return (
      <section
        className={`nutrition-section-card nutrition-suggestions ${styles.diarySection}`}
        aria-labelledby={titleId}
      >
        <header className="nutrition-section-card__header">
          <div>
            <span className="eyebrow">Подбор из дневника</span>
            {heading}
          </div>
        </header>
        <p
          id={contentId}
          hidden={!diaryExpanded}
          className="muted demo-capability-notice"
          role="status"
        >
          Варианты доступны после входа в аккаунт.
        </p>
      </section>
    );
  }

  return (
    <section
      className={`nutrition-section-card nutrition-suggestions ${mode === 'diary' ? styles.diarySection : ''}`}
      aria-labelledby={titleId}
    >
      <header className="nutrition-section-card__header">
        <div>
          <span className="eyebrow">
            {mode === 'plan' ? 'Подбор для плана' : 'Подбор из дневника'}
          </span>
          {heading}
        </div>
      </header>
      <div id={contentId} hidden={mode === 'diary' && !diaryExpanded}>
        <p className="muted">
          {mode === 'plan'
            ? 'Выберите сохранённый вариант и проверьте его перед добавлением в план.'
            : 'Проверьте состав и количество перед добавлением.'}
        </p>
        {suggestions.data?.remaining && !selectedCandidate && (
          <p className={styles.context}>
            На {formatCalendarDate(diaryDate, { day: 'numeric', month: 'long' })} осталось:{' '}
            {formatNumber(suggestions.data.remaining.energy_kcal, 2)} ккал · белки{' '}
            {formatNumber(suggestions.data.remaining.protein_g, 3)} г · жиры{' '}
            {formatNumber(suggestions.data.remaining.fat_g, 3)} г · углеводы{' '}
            {formatNumber(suggestions.data.remaining.carbs_g, 3)} г.
            {suggestions.data.remaining_includes_plan && ' Учтён ещё не съеденный план.'}
          </p>
        )}
        {suggestions.data && !selectedCandidate && (
          <p className={styles.context}>Нет сведений о предпочтениях и ограничениях.</p>
        )}
        {suggestions.isLoading && (
          <LoadingState label="Подбираем варианты из сохранённых данных…" />
        )}
        {suggestions.error && (
          <ErrorState
            message={(suggestions.error as Error).message}
            retry={() => void suggestions.refetch()}
            retryLabel="Повторить варианты"
          />
        )}
        {suggestions.data && !selectedCandidate && (
          <>
            {limitations.length > 0 && (
              <div className="nutrition-suggestions__limitations" role="status">
                {limitations.map((limitation) => (
                  <p key={limitation}>{limitation}</p>
                ))}
              </div>
            )}
            {suggestions.data.candidates?.length && mode === 'diary' ? (
              <DiaryCandidateList
                key={JSON.stringify([diaryDate, suggestions.data.candidates])}
                candidates={suggestions.data.candidates}
                remaining={suggestions.data.remaining}
                onSelect={(nextCandidate) => {
                  idempotencyKey.current = null;
                  submittedPreview.current = null;
                  setSelectedCandidate(nextCandidate);
                }}
              />
            ) : suggestions.data.candidates?.length ? (
              <ul className="nutrition-suggestions__list">
                {suggestions.data.candidates.map((candidate) => (
                  <CandidateCard
                    candidate={candidate}
                    remaining={suggestions.data.remaining}
                    key={candidate.candidate_id}
                    onSelect={(nextCandidate) => {
                      idempotencyKey.current = null;
                      submittedPreview.current = null;
                      setSelectedCandidate(nextCandidate);
                    }}
                  />
                ))}
              </ul>
            ) : suggestions.data.not_calculable ? (
              <EmptyState
                title="Нельзя рассчитать варианты"
                text="Проверьте калории и БЖУ в цели питания."
              />
            ) : !suggestions.data.targets ? (
              <EmptyState
                title="Нет цели КБЖУ на эту дату"
                text="Без цели нельзя рассчитать остаток и подобрать вариант по нему."
              />
            ) : !suggestions.data.remaining ? (
              <EmptyState
                title="Не удалось рассчитать остаток"
                text="Проверьте доступность запланированных продуктов и блюд."
              />
            ) : (
              <EmptyState
                title="Пока нет готовых вариантов"
                text="Добавьте продукт или сохраните шаблон — здесь появятся только уже подтверждённые данные."
              />
            )}
          </>
        )}
        {selectedCandidate && (
          <SuggestionReview
            candidate={selectedCandidate}
            diaryDate={diaryDate}
            initialMealType={initialMealType}
            mode={mode}
            planRevision={planRevision}
            disabled={readOnly || commit.isPending}
            pending={commit.isPending}
            onCancel={() => {
              idempotencyKey.current = null;
              submittedPreview.current = null;
              setSelectedCandidate(null);
            }}
            onSubmit={(mealType, items, previewToken, constraints) =>
              commit.mutate({ mealType, items, previewToken, constraints })
            }
          />
        )}
        {commit.error && (
          <div className="nutrition-inline-error" role="alert">
            <span>{(commit.error as Error).message}</span>
            <button
              type="button"
              onClick={() => {
                commit.reset();
                void queryClient.invalidateQueries({ queryKey: ['nutrition-suggestion-preview'] });
              }}
            >
              Изменить вариант
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
