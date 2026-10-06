import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '../../shared/api/client';
import {
  addCalendarDays,
  calendarWeek,
  dateInputValue,
  formatCalendarDate,
} from '../../shared/dateTime';
import { invalidateNutritionSummaries, queryKeys } from '../../shared/queryKeys';
import type {
  Food,
  FoodList,
  NutritionMealTemplateList,
  NutritionPlanDay,
  NutritionPlanItemActionResponse,
  NutritionPlanItem,
  NutritionPlanWeek,
  RecipeList,
} from '../../shared/api/types';
import { WeekStrip, NUTRITION_WEEK_LEGEND } from '../../shared/ui/WeekStrip';
import {
  Badge,
  Button,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Select,
  SegmentedControl,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import type { MealType } from './FoodPickerDialog';
import { NutritionSuggestions } from './NutritionSuggestions';

type PlanView = 'day' | 'week';
type SourceKind = 'food' | 'recipe' | 'template';
type PlanAmountUnit = 'g' | 'ml' | 'serving';

const mealOrder: MealType[] = ['breakfast', 'lunch', 'dinner', 'snacks'];
const mealLabels: Record<MealType, string> = {
  breakfast: 'Завтрак',
  lunch: 'Обед',
  dinner: 'Ужин',
  snacks: 'Перекусы',
};

function requestKey(prefix: string): string {
  const id =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;
  return `${prefix}-${id}`;
}

function formatNumber(
  value: string | number | null | undefined,
  maximumFractionDigits = 0,
): string {
  if (value === null || value === undefined) return '—';
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? new Intl.NumberFormat('ru-RU', { maximumFractionDigits }).format(parsed)
    : '—';
}

function itemNutritionLabel(item: NutritionPlanItem): string {
  if (!item.nutrition) return 'Питательность недоступна';
  return `${formatNumber(item.nutrition.energy_kcal)} ккал · Б ${formatNumber(item.nutrition.protein_g, 1)} г · Ж ${formatNumber(item.nutrition.fat_g, 1)} г · У ${formatNumber(item.nutrition.carbs_g, 1)} г`;
}

function PlanSummary({ day, compact = false }: { day: NutritionPlanDay; compact?: boolean }) {
  const metrics = [
    ['Ккал', day.planned.energy_kcal, day.targets?.energy_kcal],
    ['Белки', day.planned.protein_g, day.targets?.protein_g],
    ['Жиры', day.planned.fat_g, day.targets?.fat_g],
    ['Углеводы', day.planned.carbs_g, day.targets?.carbs_g],
  ] as const;
  return (
    <div className={`meal-planner__facts${compact ? ' meal-planner__facts--compact' : ''}`}>
      <div className="meal-planner__facts-heading">
        <div>
          <span className="eyebrow">
            {compact
              ? formatCalendarDate(day.plan_date, {
                  weekday: 'short',
                  day: 'numeric',
                  month: 'short',
                })
              : 'План против цели'}
          </span>
          {!compact && <h3>Запланировано</h3>}
        </div>
        {day.targets ? <Badge tone="success">Цель есть</Badge> : <Badge>Без цели</Badge>}
      </div>
      <dl className="meal-planner__metrics">
        {metrics.map(([label, planned, target]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              {formatNumber(planned, label === 'Ккал' ? 0 : 1)}
              {target !== undefined && target !== null && (
                <small> / {formatNumber(target, label === 'Ккал' ? 0 : 1)}</small>
              )}
            </dd>
          </div>
        ))}
      </dl>
      {!compact && day.remaining && (
        <p className="meal-planner__remaining">
          Остаток: {formatNumber(day.remaining.energy_kcal)} ккал · Б{' '}
          {formatNumber(day.remaining.protein_g, 1)} г · Ж {formatNumber(day.remaining.fat_g, 1)} г
          · У {formatNumber(day.remaining.carbs_g, 1)} г
        </p>
      )}
    </div>
  );
}

function WeekSummary({ week }: { week: NutritionPlanWeek }) {
  const metrics = [
    ['Ккал', week.planned.energy_kcal, week.targets?.energy_kcal],
    ['Белки', week.planned.protein_g, week.targets?.protein_g],
    ['Жиры', week.planned.fat_g, week.targets?.fat_g],
    ['Углеводы', week.planned.carbs_g, week.targets?.carbs_g],
  ] as const;
  return (
    <div className="meal-planner__facts meal-planner__facts--week">
      <div className="meal-planner__facts-heading">
        <div>
          <span className="eyebrow">План недели</span>
          <h3>
            {formatCalendarDate(week.week_start, { day: 'numeric', month: 'short' })} —{' '}
            {formatCalendarDate(week.week_end, { day: 'numeric', month: 'short' })}
          </h3>
        </div>
        {week.targets ? (
          <Badge tone={week.nutrition_complete ? 'success' : undefined}>
            {week.nutrition_complete ? 'План заполнен' : 'План в работе'}
          </Badge>
        ) : (
          <Badge>Без цели</Badge>
        )}
      </div>
      <dl className="meal-planner__metrics">
        {metrics.map(([label, planned, target]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              {formatNumber(planned, label === 'Ккал' ? 0 : 1)}
              {target !== undefined && target !== null && (
                <small> / {formatNumber(target, label === 'Ккал' ? 0 : 1)}</small>
              )}
            </dd>
          </div>
        ))}
      </dl>
      {week.remaining && (
        <p className="meal-planner__remaining">
          Остаток недели: {formatNumber(week.remaining.energy_kcal)} ккал · Б{' '}
          {formatNumber(week.remaining.protein_g, 1)} г · Ж {formatNumber(week.remaining.fat_g, 1)}{' '}
          г · У {formatNumber(week.remaining.carbs_g, 1)} г
        </p>
      )}
    </div>
  );
}

function PlanItemRow({
  item,
  revision,
  readOnly,
  onChanged,
}: {
  item: NutritionPlanItem;
  revision: number;
  readOnly: boolean;
  onChanged: (day: NutritionPlanDay) => Promise<void>;
}) {
  const { toast } = useFeedback();
  const actionKey = useRef<string | null>(null);
  const [amount, setAmount] = useState(item.amount);
  const [amountUnit, setAmountUnit] = useState<PlanAmountUnit>(item.amount_unit);
  const [mealType, setMealType] = useState<MealType>(item.meal_type);
  const update = useMutation({
    mutationFn: () =>
      api<NutritionPlanDay>(`/api/v1/nutrition/plans/items/${item.id}`, {
        method: 'PATCH',
        body: {
          meal_type: mealType,
          amount,
          amount_unit: amountUnit,
          expected_revision: revision,
        },
      }),
    onSuccess: async (day) => {
      await onChanged(day);
      toast('План обновлён');
    },
    onError: (error) => {
      toast(
        error instanceof ApiError && error.status === 409
          ? 'План уже изменился. Обновите его.'
          : 'Не удалось изменить план',
      );
    },
  });
  const remove = useMutation({
    mutationFn: () =>
      api<NutritionPlanDay>(
        `/api/v1/nutrition/plans/items/${item.id}?expected_revision=${revision}`,
        {
          method: 'DELETE',
        },
      ),
    onSuccess: async (day) => {
      await onChanged(day);
      toast('Элемент убран из плана');
    },
    onError: (error) => {
      toast(
        error instanceof ApiError && error.status === 409
          ? 'План уже изменился. Обновите его.'
          : 'Не удалось удалить элемент',
      );
    },
  });
  const action = useMutation({
    mutationFn: (actionName: 'consume' | 'edit_and_consume' | 'skip') => {
      actionKey.current ??= requestKey('nutrition-plan-action');
      return api<NutritionPlanItemActionResponse>(
        `/api/v1/nutrition/plans/items/${item.id}/action`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': actionKey.current },
          body: {
            action: actionName,
            ...(actionName === 'edit_and_consume'
              ? { amount, amount_unit: amountUnit, meal_type: mealType }
              : {}),
            expected_revision: revision,
          },
        },
      );
    },
    onSuccess: async (response) => {
      actionKey.current = null;
      await onChanged(response.day);
      toast(response.item.status === 'skipped' ? 'Элемент пропущен' : 'Записано в дневник');
    },
    onError: (error) => {
      toast(
        error instanceof ApiError && error.status === 409
          ? 'План уже изменился. Обновите его.'
          : 'Не удалось обработать элемент плана',
      );
    },
  });
  const pending = update.isPending || remove.isPending || action.isPending;
  const resolved = item.status !== 'planned';

  return (
    <li className="meal-planner__item">
      <div className="meal-planner__item-copy">
        <strong>{item.name}</strong>
        <span>{itemNutritionLabel(item)}</span>
        <span className="meal-planner__item-status">
          {item.status === 'consumed'
            ? 'Съедено'
            : item.status === 'skipped'
              ? 'Пропущено'
              : 'Запланировано'}
        </span>
        {!item.available && (
          <span className="meal-planner__item-warning">
            {item.message ?? 'Источник недоступен'}
          </span>
        )}
      </div>
      <div className="meal-planner__item-controls">
        <Select
          aria-label={`Приём пищи для ${item.name}`}
          disabled={readOnly || resolved || pending}
          value={mealType}
          onChange={(event) => setMealType(event.target.value as MealType)}
        >
          {mealOrder.map((value) => (
            <option key={value} value={value}>
              {mealLabels[value]}
            </option>
          ))}
        </Select>
        <Input
          aria-label={`Количество для ${item.name}`}
          disabled={readOnly || resolved || pending}
          min="0.001"
          step="0.001"
          type="number"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
        />
        {item.item_kind === 'recipe' ? (
          <span className="meal-planner__unit">г</span>
        ) : (
          <Select
            aria-label={`Единица для ${item.name}`}
            disabled={readOnly || resolved || pending}
            value={amountUnit}
            onChange={(event) => setAmountUnit(event.target.value as PlanAmountUnit)}
          >
            <option value="g">г</option>
            <option value="ml">мл</option>
            <option value="serving">порц.</option>
          </Select>
        )}
        {!readOnly && !resolved && (
          <>
            <Button
              aria-label={`Сохранить ${item.name}`}
              disabled={pending}
              onClick={() => update.mutate()}
              type="button"
              variant="secondary"
            >
              Сохранить
            </Button>
            <Button
              aria-label={`Удалить ${item.name}`}
              disabled={pending}
              onClick={() => remove.mutate()}
              type="button"
              variant="danger"
            >
              Удалить
            </Button>
            <Button
              aria-label={`Съел ${item.name}`}
              disabled={pending}
              onClick={() => action.mutate('consume')}
              type="button"
              variant="secondary"
            >
              Съел
            </Button>
            <Button
              aria-label={`Изменить и записать ${item.name}`}
              disabled={pending}
              onClick={() => action.mutate('edit_and_consume')}
              type="button"
              variant="secondary"
            >
              Изменить и записать
            </Button>
            <Button
              aria-label={`Пропустить ${item.name}`}
              disabled={pending}
              onClick={() => action.mutate('skip')}
              type="button"
              variant="ghost"
            >
              Пропустить
            </Button>
          </>
        )}
      </div>
    </li>
  );
}

function SourceForm({
  day,
  foods,
  recipes,
  templates,
  readOnly,
  onChanged,
}: {
  day: NutritionPlanDay;
  foods: Food[];
  recipes: RecipeList['items'];
  templates: NutritionMealTemplateList['items'];
  readOnly: boolean;
  onChanged: (day: NutritionPlanDay) => Promise<void>;
}) {
  const { toast } = useFeedback();
  const [sourceKind, setSourceKind] = useState<SourceKind>('food');
  const [sourceId, setSourceId] = useState('');
  const [mealType, setMealType] = useState<MealType>('breakfast');
  const [amount, setAmount] = useState('100');
  const [amountUnit, setAmountUnit] = useState<PlanAmountUnit>('g');
  const sources = useMemo(() => {
    if (sourceKind === 'food')
      return foods.map((food) => ({
        id: food.id,
        label: `${food.name}${food.brand ? ` · ${food.brand}` : ''}`,
      }));
    if (sourceKind === 'recipe')
      return recipes.map((recipe) => ({ id: recipe.id, label: recipe.name }));
    return templates.map((template) => ({ id: template.id, label: template.name }));
  }, [foods, recipes, sourceKind, templates]);
  const add = useMutation({
    mutationFn: () => {
      const numericId = Number(sourceId);
      if (!numericId) throw new Error('Выберите источник');
      const body = {
        ...(sourceKind === 'food' ? { food_id: numericId } : {}),
        ...(sourceKind === 'recipe' ? { recipe_id: numericId } : {}),
        ...(sourceKind === 'template' ? { template_id: numericId } : {}),
        amount,
        amount_unit: amountUnit,
      };
      return api<NutritionPlanDay>(
        `/api/v1/nutrition/plans/items?plan_date=${day.plan_date}&meal_type=${mealType}&expected_revision=${day.revision}`,
        {
          method: 'POST',
          body,
          headers: { 'Idempotency-Key': requestKey('nutrition-plan-add') },
        },
      );
    },
    onSuccess: async (nextDay) => {
      await onChanged(nextDay);
      setAmount('100');
      toast('Добавлено в план');
    },
    onError: (error) => {
      toast(
        error instanceof ApiError && error.status === 409
          ? 'План уже изменился. Обновите его.'
          : error instanceof Error
            ? error.message
            : 'Не удалось добавить в план',
      );
    },
  });

  return (
    <form
      className="meal-planner__add"
      onSubmit={(event) => {
        event.preventDefault();
        add.mutate();
      }}
    >
      <div className="meal-planner__add-heading">
        <div>
          <span className="eyebrow">Добавить заранее</span>
          <h3>Собрать план</h3>
        </div>
        <span className="muted">Ревизия {day.revision}</span>
      </div>
      <div className="meal-planner__form-grid">
        <Field label="Источник" labelFor="meal-planner-source-kind">
          <Select
            id="meal-planner-source-kind"
            value={sourceKind}
            onChange={(event) => {
              const next = event.target.value as SourceKind;
              setSourceKind(next);
              setSourceId('');
              setAmountUnit(next === 'template' ? 'serving' : 'g');
            }}
          >
            <option value="food">Избранное или недавнее</option>
            <option value="recipe">Рецепт</option>
            <option value="template">Сохранённый шаблон</option>
          </Select>
        </Field>
        <Field label="Что добавить" labelFor="meal-planner-source">
          <Select
            id="meal-planner-source"
            value={sourceId}
            onChange={(event) => setSourceId(event.target.value)}
          >
            <option value="">Выберите источник</option>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Приём пищи" labelFor="meal-planner-meal">
          <Select
            id="meal-planner-meal"
            value={mealType}
            onChange={(event) => setMealType(event.target.value as MealType)}
          >
            {mealOrder.map((value) => (
              <option key={value} value={value}>
                {mealLabels[value]}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label={sourceKind === 'template' ? 'Повторы' : 'Количество'}
          labelFor="meal-planner-amount"
        >
          <Input
            id="meal-planner-amount"
            min="0.001"
            step="0.001"
            type="number"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </Field>
        <Field label="Единица" labelFor="meal-planner-unit">
          <Select
            id="meal-planner-unit"
            value={amountUnit}
            onChange={(event) => setAmountUnit(event.target.value as PlanAmountUnit)}
          >
            {sourceKind === 'template' ? (
              <option value="serving">повтор</option>
            ) : (
              <option value="g">г</option>
            )}
            {sourceKind === 'food' && (
              <>
                <option value="ml">мл</option>
                <option value="serving">порция</option>
              </>
            )}
          </Select>
        </Field>
      </div>
      <Button disabled={readOnly || add.isPending || !sourceId} type="submit">
        {add.isPending ? 'Добавляем…' : 'Добавить в план'}
      </Button>
      {!sources.length && (
        <p className="muted">
          Нет доступных источников. Добавьте продукт, рецепт или шаблон в разделе питания.
        </p>
      )}
    </form>
  );
}

function DayPlan({
  day,
  foods,
  recipes,
  templates,
  readOnly,
  onChanged,
}: {
  day: NutritionPlanDay;
  foods: Food[];
  recipes: RecipeList['items'];
  templates: NutritionMealTemplateList['items'];
  readOnly: boolean;
  onChanged: (day: NutritionPlanDay) => Promise<void>;
}) {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const copy = useMutation({
    mutationFn: () =>
      api<NutritionPlanDay>('/api/v1/nutrition/plans/copy', {
        method: 'POST',
        body: {
          source_date: addCalendarDays(day.plan_date, -1),
          target_date: day.plan_date,
          expected_revision: day.revision,
        },
        headers: { 'Idempotency-Key': requestKey('nutrition-plan-copy') },
      }),
    onSuccess: async (nextDay) => {
      queryClient.setQueryData(queryKeys.nutrition.plans.day(day.plan_date), nextDay);
      await onChanged(nextDay);
      toast('Предыдущий день скопирован в план');
    },
    onError: (error) =>
      toast(
        error instanceof ApiError && error.status === 409
          ? 'План уже изменился. Обновите его.'
          : 'Не удалось скопировать день',
      ),
  });
  return (
    <>
      <PlanSummary day={day} />
      {!readOnly && (
        <Button
          className="meal-planner__copy"
          disabled={copy.isPending}
          onClick={() => copy.mutate()}
          type="button"
          variant="secondary"
        >
          {copy.isPending ? 'Копируем…' : 'Скопировать предыдущий день'}
        </Button>
      )}
      {!readOnly && (
        <SourceForm
          day={day}
          foods={foods}
          recipes={recipes}
          templates={templates}
          readOnly={readOnly}
          onChanged={onChanged}
        />
      )}
      <NutritionSuggestions
        diaryDate={day.plan_date}
        initialMealType="breakfast"
        mode="plan"
        onPlanFilled={onChanged}
        planRevision={day.revision}
        readOnly={readOnly}
      />
      <div className="meal-planner__slots">
        {day.slots.map((slot) => (
          <section className="meal-planner__slot" key={slot.meal_type}>
            <header>
              <div>
                <span className="eyebrow">Приём пищи</span>
                <h3>{mealLabels[slot.meal_type]}</h3>
              </div>
              <span>{formatNumber(slot.planned.energy_kcal)} ккал</span>
            </header>
            {slot.items.length ? (
              <ul>
                {slot.items.map((item) => (
                  <PlanItemRow
                    item={item}
                    key={item.id}
                    onChanged={onChanged}
                    readOnly={readOnly}
                    revision={day.revision}
                  />
                ))}
              </ul>
            ) : (
              <p className="meal-planner__empty">Пока ничего не запланировано.</p>
            )}
          </section>
        ))}
      </div>
    </>
  );
}

export function MealPlanner({
  initialDate,
  readOnly = false,
  timeZone,
}: {
  initialDate?: string;
  readOnly?: boolean;
  timeZone?: string | null;
}) {
  const today = dateInputValue(new Date(), timeZone || undefined);
  const [open, setOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState(initialDate || today);
  const [view, setView] = useState<PlanView>('day');
  const queryClient = useQueryClient();
  const [weekStart = selectedDate] = calendarWeek(selectedDate);
  const dayQuery = useQuery({
    queryKey: queryKeys.nutrition.plans.day(selectedDate),
    queryFn: ({ signal }) =>
      api<NutritionPlanDay>(`/api/v1/nutrition/plans/day?plan_date=${selectedDate}`, { signal }),
    enabled: open && view === 'day',
  });
  const weekQuery = useQuery({
    queryKey: queryKeys.nutrition.plans.week(weekStart),
    queryFn: ({ signal }) =>
      api<NutritionPlanWeek>(`/api/v1/nutrition/plans/week?week_start=${weekStart}`, { signal }),
    enabled: open && view === 'week',
  });
  const favorites = useQuery({
    queryKey: ['nutrition', 'foods', 'favorites', 'planner'],
    queryFn: ({ signal }) =>
      api<FoodList>('/api/v1/nutrition/foods/favorites?limit=20', { signal }),
    enabled: open && !readOnly,
  });
  const recent = useQuery({
    queryKey: ['nutrition', 'foods', 'recent', 'planner'],
    queryFn: ({ signal }) => api<FoodList>('/api/v1/nutrition/foods/recent?limit=20', { signal }),
    enabled: open && !readOnly,
  });
  const recipes = useQuery({
    queryKey: queryKeys.nutrition.recipes,
    queryFn: ({ signal }) => api<RecipeList>('/api/v1/nutrition/recipes?limit=50', { signal }),
    enabled: open && !readOnly,
  });
  const templates = useQuery({
    queryKey: queryKeys.nutrition.mealTemplates,
    queryFn: ({ signal }) =>
      api<NutritionMealTemplateList>('/api/v1/nutrition/templates?limit=50', { signal }),
    enabled: open && !readOnly,
  });
  const foods = useMemo(() => {
    const unique = new Map<number, Food>();
    [...(favorites.data?.items ?? []), ...(recent.data?.items ?? [])].forEach((food) =>
      unique.set(food.id, food),
    );
    return [...unique.values()];
  }, [favorites.data?.items, recent.data?.items]);
  const day = dayQuery.data;
  const sourceLoading =
    favorites.isLoading || recent.isLoading || recipes.isLoading || templates.isLoading;
  const onChanged = async (nextDay: NutritionPlanDay) => {
    queryClient.setQueryData(queryKeys.nutrition.plans.day(nextDay.plan_date), nextDay);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.nutrition.plans.all }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.nutrition.planSuggestions(nextDay.plan_date),
      }),
      invalidateNutritionSummaries(queryClient),
    ]);
  };
  const weekNavigation = {
    onPrevious: () => setSelectedDate(addCalendarDays(selectedDate, -7)),
    onNext: () => setSelectedDate(addCalendarDays(selectedDate, 7)),
  };

  return (
    <details
      className="meal-planner"
      data-testid="meal-planner"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="meal-planner__summary">
        <span>
          <span className="eyebrow">Nutrition Planning</span>
          <strong>План питания</strong>
        </span>
        <span className="meal-planner__summary-note">День · неделя · шаблоны</span>
      </summary>
      <div className="meal-planner__body">
        <div className="meal-planner__toolbar">
          <SegmentedControl
            ariaLabel="Период плана"
            onChange={(next) => setView(next as PlanView)}
            options={[
              { label: 'День', value: 'day' },
              { label: 'Неделя', value: 'week' },
            ]}
            value={view}
          />
          {view === 'day' && (
            <span className="muted">
              {formatCalendarDate(selectedDate, { day: 'numeric', month: 'long' })}
            </span>
          )}
        </div>
        {view === 'day' ? (
          <WeekStrip
            anchorDate={selectedDate}
            ariaLabel="Выбор дня плана"
            mode="picker"
            onSelect={setSelectedDate}
            selectedDate={selectedDate}
            title="План дня"
            today={today}
          />
        ) : (
          <WeekStrip
            anchorDate={selectedDate}
            ariaLabel="Неделя плана"
            getDayMeta={(date) => {
              const weekDay = weekQuery.data?.days.find((item) => item.plan_date === date);
              if (!weekDay || _itemsCount(weekDay) === 0)
                return { status: { key: 'neutral', label: 'Нет плана', pictogram: 'missing' } };
              return {
                status: weekDay.nutrition_complete
                  ? { key: 'completed', label: 'План заполнен' }
                  : {
                      key: 'in-progress',
                      label: 'План частично заполнен',
                      pictogram: 'nutrition-incomplete',
                    },
              };
            }}
            legend={NUTRITION_WEEK_LEGEND}
            mode="overview"
            navigation={weekNavigation}
            rangeStart={weekStart}
            title="Неделя плана"
            today={today}
          />
        )}
        {view === 'day' && dayQuery.isLoading && <LoadingState label="Загружаем план дня…" />}
        {view === 'day' && dayQuery.error && (
          <ErrorState
            message={(dayQuery.error as Error).message}
            retry={() => void dayQuery.refetch()}
          />
        )}
        {view === 'day' && day && (
          <DayPlan
            day={day}
            foods={foods}
            recipes={recipes.data?.items ?? []}
            templates={templates.data?.items ?? []}
            readOnly={readOnly}
            onChanged={onChanged}
          />
        )}
        {view === 'day' && open && !readOnly && sourceLoading && (
          <p className="muted meal-planner__source-status">
            Загружаем избранные продукты, рецепты и шаблоны…
          </p>
        )}
        {view === 'week' && weekQuery.isLoading && <LoadingState label="Загружаем план недели…" />}
        {view === 'week' && weekQuery.error && (
          <ErrorState
            message={(weekQuery.error as Error).message}
            retry={() => void weekQuery.refetch()}
          />
        )}
        {view === 'week' && weekQuery.data && (
          <section className="meal-planner__week-list" aria-label="Планы по дням">
            <WeekSummary week={weekQuery.data} />
            {weekQuery.data.days.map((weekDay) => (
              <article className="meal-planner__week-day" key={weekDay.plan_date}>
                <PlanSummary day={weekDay} compact />
                <Button
                  onClick={() => {
                    setSelectedDate(weekDay.plan_date);
                    setView('day');
                  }}
                  type="button"
                  variant="ghost"
                >
                  Открыть день
                </Button>
              </article>
            ))}
          </section>
        )}
      </div>
    </details>
  );
}

function _itemsCount(day: NutritionPlanDay): number {
  return day.slots.reduce((count, slot) => count + slot.items.length, 0);
}
