import { useEffect, useId, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import { queryKeys, invalidateNutritionSummaries } from '../../shared/queryKeys';
import type {
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
  const tags = [...candidate.reasons, ...candidate.sources]
    .filter((value, index, values) => values.indexOf(value) === index)
    .map(tagLabel);
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
    tags.unshift(...overages);
  }
  if (compact) {
    const facts = tags.filter(
      (tag) =>
        candidate.nutrition_confidence !== 'partial' || tag !== reasonLabels.partial_nutrition,
    );
    return (
      <li className={`nutrition-suggestion-card ${styles.compactCard}`}>
        <strong id={nameId}>{candidate.name}</strong>
        <span className={styles.facts}>
          {formatNumber(candidate.nutrition.energy_kcal, 2)} ккал · {macroLine(candidate.nutrition)}
        </span>
        <span className={styles.facts}>
          <span>{confidenceLabel(candidate.nutrition_confidence)}</span>
          {facts.slice(0, 2).map((fact) => ` · ${fact}`)}
        </span>
        {facts.length > 2 && (
          <details className={styles.details}>
            <summary className="yfc-disclosure-summary">
              <span>Другие основания: {candidate.name}</span>
              <DisclosureIcon />
            </summary>
            <p>{facts.slice(2).join(' · ')}</p>
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
            {macroLine(candidate.nutrition)}
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

function PreviewTable({ preview, mode }: { preview: SuggestionPreview; mode: SuggestionMode }) {
  const rows: { field: keyof FoodDiaryNutrition; label: string }[] = [
    { field: 'energy_kcal', label: 'Ккал' },
    { field: 'protein_g', label: 'Белки, г' },
    { field: 'fat_g', label: 'Жиры, г' },
    { field: 'carbs_g', label: 'Углеводы, г' },
    { field: 'fiber_g', label: 'Клетчатка, г' },
  ];
  const goal = preview.target_goal;
  const goalLabel =
    goal && Object.hasOwn(goalOptions, goal)
      ? goalOptions[goal as keyof typeof goalOptions].label
      : '—';
  return (
    <>
      {preview.targets && (
        <p className={styles.note}>
          Цель: {formatNumber(preview.targets.energy_kcal, 0)} ккал · Б{' '}
          {formatNumber(preview.targets.protein_g)} г · Ж {formatNumber(preview.targets.fat_g)} г ·
          У {formatNumber(preview.targets.carbs_g)} г. Запись цели №{' '}
          {formatNumber(preview.target_id, 0)} ·{' '}
          {targetSourceLabels[preview.target_source ?? ''] ?? 'источник не указан'} · действует с{' '}
          {preview.target_effective_from ?? '—'} · вес: {formatNumber(preview.target_weight_kg, 2)}{' '}
          кг · цель расчёта: {goalLabel}.
        </p>
      )}
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
                <td>{formatNumber(preview.addition[field], field === 'energy_kcal' ? 2 : 3)}</td>
                <td>{formatNumber(preview.after[field], field === 'energy_kcal' ? 2 : 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
  onSubmit: (mealType: MealType, items: ReviewItem[], previewToken: string) => void;
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
  const body =
    mode === 'plan'
      ? {
          plan_date: diaryDate,
          meal_type: mealType,
          candidate_id: candidate.candidate_id,
          items: items.map(planReviewItemPayload),
          expected_revision: planRevision,
        }
      : { diary_date: diaryDate, meal_type: mealType, items: items.map(reviewItemPayload) };
  const request = JSON.stringify(body);
  const [settledRequest, setSettledRequest] = useState(request);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettledRequest(request), 250);
    return () => window.clearTimeout(timer);
  }, [request]);
  const canPreview =
    items.length > 0 &&
    items.every((item) => Number.isFinite(Number(item.amount)) && Number(item.amount) > 0) &&
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
        if (previewReady && preview.data) onSubmit(mealType, items, preview.data.preview_token);
      }}
    >
      <div className="nutrition-suggestion-review__head">
        <div>
          <span className="eyebrow">
            {mode === 'plan' ? 'Проверка перед планированием' : 'Проверка перед записью'}
          </span>
          <h3>{candidate.name}</h3>
        </div>
        <Badge>Можно изменить</Badge>
      </div>
      <p className="muted">
        Измените количество или уберите ингредиент.{' '}
        {mode === 'plan'
          ? 'В план ничего не попадёт до явного подтверждения.'
          : 'В дневник ничего не попадёт до явного подтверждения.'}
      </p>
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
  const [selectedCandidate, setSelectedCandidate] = useState<NutritionSuggestion | null>(null);
  const suggestions = useQuery({
    queryKey:
      mode === 'plan'
        ? queryKeys.nutrition.planSuggestions(diaryDate)
        : queryKeys.nutrition.suggestions(diaryDate),
    queryFn: () =>
      api<NutritionSuggestionsResponse & { not_calculable?: boolean }>(
        mode === 'plan'
          ? `/api/v1/nutrition/plans/suggestions?plan_date=${diaryDate}`
          : `/api/v1/nutrition/diary/suggestions?diary_date=${diaryDate}`,
      ),
    enabled: !demoSafeMode,
  });
  const commit = useMutation<
    FoodDiaryBatchResponse | NutritionPlanDay,
    Error,
    { mealType: MealType; items: ReviewItem[]; previewToken: string }
  >({
    mutationFn: ({ mealType, items, previewToken }) => {
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
          } satisfies NutritionPlanFillRequest & { preview_token: string },
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
        } satisfies NutritionSuggestionCommitRequest & { preview_token: string },
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

  if (demoSafeMode) {
    return (
      <section className="nutrition-section-card nutrition-suggestions" aria-labelledby={titleId}>
        <header className="nutrition-section-card__header">
          <div>
            <span className="eyebrow">Подбор из дневника</span>
            <h2 id={titleId}>Варианты из вашей еды</h2>
          </div>
        </header>
        <p className="muted demo-capability-notice" role="status">
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
          <h2 id={titleId}>{mode === 'plan' ? 'Варианты для плана' : 'Варианты из вашей еды'}</h2>
          <p className="muted">
            {mode === 'plan'
              ? 'Выберите сохранённый вариант и проверьте его перед добавлением в план.'
              : 'Что можно добавить дальше — проверьте состав и количество сами.'}
          </p>
        </div>
        {suggestions.data?.remaining && (
          <Badge tone={suggestions.data.remaining_confidence === 'partial' ? 'warning' : 'neutral'}>
            Остаток: {formatNumber(suggestions.data.remaining.energy_kcal, 2)} ккал · Б{' '}
            {formatNumber(suggestions.data.remaining.protein_g, 3)} · Ж{' '}
            {formatNumber(suggestions.data.remaining.fat_g, 3)} · У{' '}
            {formatNumber(suggestions.data.remaining.carbs_g, 3)}
          </Badge>
        )}
      </header>
      {suggestions.isLoading && <LoadingState label="Подбираем варианты из сохранённых данных…" />}
      {suggestions.error && (
        <ErrorState
          message={(suggestions.error as Error).message}
          retry={() => void suggestions.refetch()}
          retryLabel="Повторить варианты"
        />
      )}
      {suggestions.data && !selectedCandidate && (
        <>
          <div className="nutrition-suggestions__limitations" role="status">
            {suggestions.data.limitations?.map((limitation) => (
              <p key={limitation}>{limitation}</p>
            ))}
          </div>
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
          onSubmit={(mealType, items, previewToken) =>
            commit.mutate({ mealType, items, previewToken })
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
    </section>
  );
}
