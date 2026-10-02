import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import { queryKeys, invalidateNutritionSummaries } from '../../shared/queryKeys';
import type {
  FoodDiaryBatchResponse,
  FoodDiaryNutrition,
  NutritionSuggestion,
  NutritionSuggestionCommitRequest,
  NutritionSuggestions as NutritionSuggestionsResponse,
} from '../../shared/api/types';
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Select,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import type { MealType } from './FoodPickerDialog';

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

function formatNumber(value: string | number | null | undefined, fractionDigits = 1): string {
  if (value === null || value === undefined) return '—';
  const number = Number(value);
  return Number.isFinite(number)
    ? new Intl.NumberFormat('ru-RU', { maximumFractionDigits: fractionDigits }).format(number)
    : '—';
}

function macroLine(nutrition: FoodDiaryNutrition): string {
  return `Б ${formatNumber(nutrition.protein_g)} · Ж ${formatNumber(nutrition.fat_g)} · У ${formatNumber(nutrition.carbs_g)}`;
}

function confidenceLabel(confidence: NutritionSuggestion['nutrition_confidence']): string {
  if (confidence === 'partial') return 'Частичные БЖУ';
  if (confidence === 'approximate') return 'Приблизительные БЖУ';
  return 'Точные БЖУ';
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

function CandidateCard({
  candidate,
  onSelect,
}: {
  candidate: NutritionSuggestion;
  onSelect: (candidate: NutritionSuggestion) => void;
}) {
  const tags = [...candidate.reasons, ...candidate.sources]
    .filter((value, index, values) => values.indexOf(value) === index)
    .map(tagLabel);
  return (
    <li className="nutrition-suggestion-card">
      <div className="nutrition-suggestion-card__head">
        <div>
          <strong>{candidate.name}</strong>
          <span>
            {formatNumber(candidate.nutrition.energy_kcal, 0)} ккал ·{' '}
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

function SuggestionReview({
  candidate,
  initialMealType,
  disabled,
  onCancel,
  onSubmit,
  pending,
}: {
  candidate: NutritionSuggestion;
  initialMealType: MealType;
  disabled: boolean;
  onCancel: () => void;
  onSubmit: (mealType: MealType, items: ReviewItem[]) => void;
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

  return (
    <form
      className="nutrition-suggestion-review"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(mealType, items);
      }}
    >
      <div className="nutrition-suggestion-review__head">
        <div>
          <span className="eyebrow">Проверка перед записью</span>
          <h3>{candidate.name}</h3>
        </div>
        <Badge>Можно изменить</Badge>
      </div>
      <p className="muted">
        Измените количество или уберите ингредиент. В дневник ничего не попадёт до явного
        подтверждения.
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
                <span>{macroLine(reviewItem.item.nutrition)}</span>
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
      <div className="nutrition-suggestion-review__actions">
        <Button type="submit" disabled={disabled || pending || items.length === 0}>
          {pending ? 'Добавляем…' : 'Добавить выбранное'}
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
}: {
  diaryDate: string;
  initialMealType: MealType;
  readOnly?: boolean;
  demoSafeMode?: boolean;
}) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const [selectedCandidate, setSelectedCandidate] = useState<NutritionSuggestion | null>(null);
  const suggestions = useQuery({
    queryKey: queryKeys.nutrition.suggestions(diaryDate),
    queryFn: () =>
      api<NutritionSuggestionsResponse>(
        `/api/v1/nutrition/diary/suggestions?diary_date=${diaryDate}`,
      ),
    enabled: !demoSafeMode,
  });
  const commit = useMutation({
    mutationFn: ({ mealType, items }: { mealType: MealType; items: ReviewItem[] }) =>
      api<FoodDiaryBatchResponse>('/api/v1/nutrition/diary/suggestions/commit', {
        method: 'POST',
        headers: { 'Idempotency-Key': requestKey() },
        body: {
          diary_date: diaryDate,
          meal_type: mealType,
          items: items.map(reviewItemPayload),
        } satisfies NutritionSuggestionCommitRequest,
      }),
    onSuccess: async () => {
      await Promise.all([
        invalidateNutritionSummaries(queryClient),
        queryClient.invalidateQueries({ queryKey: queryKeys.nutrition.suggestions(diaryDate) }),
      ]);
      setSelectedCandidate(null);
      toast('Вариант добавлен в дневник');
    },
  });

  if (demoSafeMode) {
    return (
      <section
        className="nutrition-section-card nutrition-suggestions"
        aria-labelledby="nutrition-suggestions-title"
      >
        <header className="nutrition-section-card__header">
          <div>
            <span className="eyebrow">Подбор из дневника</span>
            <h2 id="nutrition-suggestions-title">Варианты из вашей еды</h2>
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
      className="nutrition-section-card nutrition-suggestions"
      aria-labelledby="nutrition-suggestions-title"
    >
      <header className="nutrition-section-card__header">
        <div>
          <span className="eyebrow">Подбор из дневника</span>
          <h2 id="nutrition-suggestions-title">Варианты из вашей еды</h2>
          <p className="muted">Что можно добавить дальше — проверьте состав и количество сами.</p>
        </div>
        {suggestions.data?.remaining && (
          <Badge tone={suggestions.data.remaining_confidence === 'partial' ? 'warning' : 'neutral'}>
            Остаток: {formatNumber(suggestions.data.remaining.energy_kcal, 0)} ккал · Б{' '}
            {formatNumber(suggestions.data.remaining.protein_g)}
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
          {suggestions.data.candidates?.length ? (
            <ul className="nutrition-suggestions__list">
              {suggestions.data.candidates.map((candidate) => (
                <CandidateCard
                  candidate={candidate}
                  key={candidate.candidate_id}
                  onSelect={setSelectedCandidate}
                />
              ))}
            </ul>
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
          initialMealType={initialMealType}
          disabled={readOnly}
          pending={commit.isPending}
          onCancel={() => setSelectedCandidate(null)}
          onSubmit={(mealType, items) => commit.mutate({ mealType, items })}
        />
      )}
      {commit.error && (
        <div className="nutrition-inline-error" role="alert">
          <span>{(commit.error as Error).message}</span>
          <button type="button" onClick={() => commit.reset()}>
            Изменить вариант
          </button>
        </div>
      )}
    </section>
  );
}
