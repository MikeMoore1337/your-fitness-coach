import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import { addCalendarDays, calendarWeek, dateInputValue } from '../../shared/dateTime';
import { invalidateNutritionSummaries, queryKeys } from '../../shared/queryKeys';
import { WeekStrip } from '../../shared/ui/WeekStrip';
import { QuantitativeProgress } from '../../shared/ui/DataViz';
import { Icon } from '../../shared/ui/Icon';
import { useSemanticMotion } from '../../shared/ui/useSemanticMotion';
import type {
  FoodDiaryDay,
  FoodDiaryEntry,
  FoodDiaryMeal,
  FoodDiaryNutrition,
  HydrationDay,
} from '../../shared/api/types';
import {
  Badge,
  Button,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Select,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { FoodPickerDialog, type MealType } from './FoodPickerDialog';
import { CopyDiaryDialog, type CopySubject } from './CopyDiaryDialog';
import { HydrationTracker } from './HydrationTracker';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';

const mealOrder: MealType[] = ['breakfast', 'lunch', 'dinner', 'snacks'];
const mealLabels: Record<MealType, string> = {
  breakfast: 'Завтрак',
  lunch: 'Обед',
  dinner: 'Ужин',
  snacks: 'Перекусы',
};

const emptyNutrition: FoodDiaryNutrition = {
  energy_kcal: '0',
  protein_g: '0',
  fat_g: '0',
  carbs_g: '0',
  fiber_g: null,
};

function formatNumber(
  value: string | number | null | undefined,
  maximumFractionDigits = 0,
): string {
  if (value === null || value === undefined) return '—';
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits }).format(number);
}

function plural(value: number, one: string, few: string, many: string): string {
  const absolute = Math.abs(value);
  const lastTwo = absolute % 100;
  if (lastTwo >= 11 && lastTwo <= 14) return many;
  const last = absolute % 10;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}

function formatDate(value: string, today: string): { title: string; subtitle: string } {
  const date = new Date(`${value}T12:00:00`);
  const formatted = new Intl.DateTimeFormat('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(date);
  const weekday = formatted.charAt(0).toUpperCase() + formatted.slice(1);
  if (value === today) return { title: 'Сегодня', subtitle: weekday };
  if (value === addCalendarDays(today, -1)) return { title: 'Вчера', subtitle: weekday };
  return { title: weekday, subtitle: String(date.getFullYear()) };
}

function amountLabel(entry: FoodDiaryEntry): string {
  if (entry.amount_unit === 'serving') {
    return `${formatNumber(entry.amount, 2)} ${Number(entry.amount) === 1 ? 'порция' : 'порции'} · ${formatNumber(entry.weight_g)} г`;
  }
  return `${formatNumber(entry.weight_g, 1)} г`;
}

function targetStatus(remaining: number, target: number, unit: string): string {
  if (remaining >= 0) return `Осталось ${formatNumber(remaining)} ${unit}`;
  const over = Math.abs(remaining);
  if (target > 0 && over / target <= 0.05)
    return `Немного выше ориентира: ${formatNumber(over)} ${unit}`;
  return `Выше ориентира на ${formatNumber(over)} ${unit}`;
}

function MacroProgress({
  label,
  total,
  target,
  remaining,
  unit,
}: {
  label: string;
  total: string | null;
  target: string | null;
  remaining: string | null;
  unit: 'г' | 'ккал';
}) {
  if (total === null || target === null || remaining === null) {
    return (
      <div className="nutrition-target nutrition-target--unknown">
        <div className="nutrition-target__heading">
          <span>{label}</span>
          <strong>Нет данных</strong>
        </div>
        <small>Quick Add содержит только калории; макронутриенты не считаются нулевыми.</small>
      </div>
    );
  }
  const totalNumber = Number(total);
  const targetNumber = Number(target);
  const remainingNumber = Number(remaining);
  const ratio = targetNumber > 0 ? totalNumber / targetNumber : 0;
  const meaningfullyOver = ratio > 1.1;
  return (
    <div className={`nutrition-target${meaningfullyOver ? ' is-over' : ''}`}>
      <QuantitativeProgress label={label} maximum={targetNumber} unit={unit} value={totalNumber} />
      <small>{targetStatus(remainingNumber, targetNumber, unit)}</small>
    </div>
  );
}

function DayBalance({
  day,
  hydration,
  hydrationUnavailable,
}: {
  day: FoodDiaryDay;
  hydration?: HydrationDay;
  hydrationUnavailable: boolean;
}) {
  const foodTarget = day.targets ? Number(day.targets.energy_kcal) : null;
  const hydrationTarget = hydration?.goal?.enabled ? hydration.goal.target_ml : null;
  return (
    <section
      className="nutrition-section-card nutrition-day-balance"
      aria-labelledby="nutrition-balance-title"
    >
      <header className="nutrition-section-card__header">
        <div>
          <span className="eyebrow">Сводка дня</span>
          <h2 id="nutrition-balance-title">Баланс дня</h2>
        </div>
        <p>Еда и жидкость — рядом, без смешивания показателей.</p>
      </header>
      <div className="nutrition-day-balance__metrics">
        <div>
          {foodTarget ? (
            <QuantitativeProgress
              label="Еда"
              maximum={foodTarget}
              unit="ккал"
              value={Number(day.totals.energy_kcal)}
            />
          ) : (
            <div className="nutrition-day-balance__value">
              <span>Еда</span>
              <strong>{formatNumber(day.totals.energy_kcal)} ккал</strong>
              <small>Ориентир не задан</small>
            </div>
          )}
        </div>
        <div>
          {hydration && hydrationTarget ? (
            <QuantitativeProgress
              label="Жидкость"
              maximum={hydrationTarget}
              unit="мл"
              value={hydration.total_ml}
            />
          ) : (
            <div className="nutrition-day-balance__value">
              <span>Жидкость</span>
              <strong>
                {hydration
                  ? `${formatNumber(hydration.total_ml)} мл`
                  : hydrationUnavailable
                    ? 'Недоступно'
                    : 'Загружается…'}
              </strong>
              <small>
                {hydration
                  ? 'Ориентир не задан'
                  : hydrationUnavailable
                    ? 'Проверьте карточку «Напитки»'
                    : 'Получаем записи напитков'}
              </small>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function DaySummary({ day }: { day: FoodDiaryDay }) {
  const { totals, targets, remaining } = day;
  const motion = useSemanticMotion<HTMLElement>(JSON.stringify([totals, targets, remaining]), {
    animateInitial: false,
  });
  return (
    <aside
      className="nutrition-day-summary semantic-card semantic-card--summary semantic-card--nutrition"
      data-card-variant="summary"
      data-semantic-family="nutrition"
      id={motion.elementId}
      aria-labelledby="nutrition-summary-title"
      data-motion-phase={motion.motionPhase}
      data-motion-revision={motion.motionRevision}
      onAnimationEnd={motion.onMotionAnimationEnd}
    >
      <div className="nutrition-day-summary__head">
        <div>
          <span className="eyebrow">Ориентиры дня</span>
          <h2 id="nutrition-summary-title">КБЖУ</h2>
        </div>
        {day.targets ? <Badge tone="success">Цель КБЖУ настроена</Badge> : <Badge>Без цели</Badge>}
      </div>
      {targets && remaining ? (
        <div className="nutrition-targets">
          <MacroProgress
            label="Калории"
            total={totals.energy_kcal}
            target={targets.energy_kcal}
            remaining={remaining.energy_kcal}
            unit="ккал"
          />
          <div className="nutrition-targets__macros">
            <MacroProgress
              label="Белки"
              total={totals.protein_g}
              target={targets.protein_g}
              remaining={remaining.protein_g}
              unit="г"
            />
            <MacroProgress
              label="Жиры"
              total={totals.fat_g}
              target={targets.fat_g}
              remaining={remaining.fat_g}
              unit="г"
            />
            <MacroProgress
              label="Углеводы"
              total={totals.carbs_g}
              target={targets.carbs_g}
              remaining={remaining.carbs_g}
              unit="г"
            />
          </div>
        </div>
      ) : (
        <div className="nutrition-targets nutrition-targets--unset">
          <strong>{formatNumber(totals.energy_kcal)} ккал записано</strong>
          <p>Настройте ориентиры КБЖУ, чтобы видеть остаток на день.</p>
          <a href="#nutrition-target-settings">Настроить цель</a>
        </div>
      )}
      <dl className="nutrition-day-summary__totals" aria-label="Сумма макронутриентов">
        <div>
          <dt>Белки</dt>
          <dd>{formatNumber(totals.protein_g, 1)} г</dd>
        </div>
        <div>
          <dt>Жиры</dt>
          <dd>{formatNumber(totals.fat_g, 1)} г</dd>
        </div>
        <div>
          <dt>Углеводы</dt>
          <dd>{formatNumber(totals.carbs_g, 1)} г</dd>
        </div>
      </dl>
    </aside>
  );
}

function EntryRow({
  entry,
  isNew,
  onCopy,
}: {
  entry: FoodDiaryEntry;
  isNew: boolean;
  onCopy: () => void;
}) {
  const queryClient = useQueryClient();
  const { confirm, toast } = useFeedback();
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState(entry.amount);
  const [amountUnit, setAmountUnit] = useState<'g' | 'serving'>(entry.amount_unit);
  const motion = useSemanticMotion<HTMLLIElement>(
    JSON.stringify([entry.amount, entry.amount_unit, entry.nutrition]),
    { animateInitial: isNew },
  );

  const update = useMutation({
    mutationFn: () =>
      api<FoodDiaryEntry>(`/api/v1/nutrition/diary/entries/${entry.id}`, {
        method: 'PATCH',
        body: { amount: Number(amount.replace(',', '.')), amount_unit: amountUnit },
      }),
    onSuccess: async () => {
      await invalidateNutritionSummaries(queryClient);
      setEditing(false);
      toast('Количество обновлено');
    },
  });
  const remove = useMutation({
    mutationFn: () =>
      api<void>(`/api/v1/nutrition/diary/entries/${entry.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await invalidateNutritionSummaries(queryClient);
      toast('Запись удалена');
    },
  });

  const requestDelete = async () => {
    const approved = await confirm({
      title: 'Удалить запись?',
      message: `${entry.food_name} исчезнет из этого приёма пищи.`,
      confirmText: 'Удалить',
    });
    if (approved) remove.mutate();
  };

  return (
    <li
      className="nutrition-entry"
      id={motion.elementId}
      data-motion-phase={motion.motionPhase}
      data-motion-revision={motion.motionRevision}
      onAnimationEnd={motion.onMotionAnimationEnd}
    >
      <div className="nutrition-entry__content">
        <div className="nutrition-entry__title">
          <div>
            <strong>{entry.food_name}</strong>
            <span>
              {entry.entry_kind === 'quick_add'
                ? `Быстрый ввод${entry.logged_at ? ` · ${entry.logged_at.slice(0, 5)}` : ''}`
                : entry.food_brand
                  ? `${entry.food_brand} · ${amountLabel(entry)}`
                  : amountLabel(entry)}
            </span>
          </div>
          <strong className="nutrition-entry__calories">
            {formatNumber(entry.nutrition.energy_kcal)} ккал
          </strong>
        </div>
        <div className="nutrition-entry__macros" aria-label="Пищевая ценность записи">
          <span>Б {formatNumber(entry.nutrition.protein_g, 1)}</span>
          <span>Ж {formatNumber(entry.nutrition.fat_g, 1)}</span>
          <span>У {formatNumber(entry.nutrition.carbs_g, 1)}</span>
        </div>
      </div>
      {!editing ? (
        <div className="nutrition-entry__actions">
          <button
            type="button"
            onClick={onCopy}
            disabled={remove.isPending}
            aria-label={`Повторить ${entry.food_name}`}
            title="Повторить"
          >
            <Icon name="sync" size={20} />
          </button>
          {entry.entry_kind !== 'quick_add' && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              disabled={remove.isPending}
              aria-label={`Изменить ${entry.food_name}`}
              title="Изменить"
            >
              <Icon name="edit" size={20} />
            </button>
          )}
          <button
            type="button"
            onClick={() => void requestDelete()}
            disabled={remove.isPending}
            aria-label={`${remove.isPending ? 'Удаляем' : 'Удалить'} ${entry.food_name}`}
            title="Удалить"
          >
            <Icon name={remove.isPending ? 'loading' : 'trash'} size={20} />
          </button>
        </div>
      ) : (
        <form
          className="nutrition-entry-editor"
          onSubmit={(event) => {
            event.preventDefault();
            update.mutate();
          }}
        >
          <Field label="Количество" labelFor={`nutrition-entry-amount-${entry.id}`}>
            <Input
              id={`nutrition-entry-amount-${entry.id}`}
              type="number"
              inputMode="decimal"
              min="0.001"
              step="any"
              required
              value={amount}
              onChange={(event) => {
                update.reset();
                setAmount(event.target.value);
              }}
            />
          </Field>
          <Field label="Единица" labelFor={`nutrition-entry-unit-${entry.id}`}>
            <Select
              id={`nutrition-entry-unit-${entry.id}`}
              value={amountUnit}
              onChange={(event) => {
                update.reset();
                setAmountUnit(event.target.value as 'g' | 'serving');
              }}
            >
              <option value="g">граммы</option>
              {entry.serving_weight_g && <option value="serving">порции</option>}
            </Select>
          </Field>
          <div className="nutrition-entry-editor__actions">
            <Button disabled={update.isPending} type="submit">
              {update.isPending ? 'Сохраняем…' : 'Сохранить'}
            </Button>
            <Button
              disabled={update.isPending}
              type="button"
              variant="ghost"
              onClick={() => {
                update.reset();
                setAmount(entry.amount);
                setAmountUnit(entry.amount_unit);
                setEditing(false);
              }}
            >
              Отмена
            </Button>
          </div>
          {update.error && (
            <div className="nutrition-inline-error" role="alert">
              <span>{(update.error as Error).message}</span>
              <button type="button" onClick={() => update.mutate()}>
                Повторить
              </button>
            </div>
          )}
        </form>
      )}
      {remove.error && (
        <div className="nutrition-inline-error nutrition-entry__delete-error" role="alert">
          <span>{(remove.error as Error).message}</span>
          <button type="button" onClick={() => void requestDelete()}>
            Повторить
          </button>
        </div>
      )}
    </li>
  );
}

function MealSection({
  meal,
  newEntryIds,
  expanded,
  onExpandedChange,
  onAdd,
  onCopy,
  onRepeatYesterday,
  onCopyEntry,
}: {
  meal: FoodDiaryMeal;
  newEntryIds: ReadonlySet<number>;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  onAdd: () => void;
  onCopy: () => void;
  onRepeatYesterday: () => void;
  onCopyEntry: (entry: FoodDiaryEntry) => void;
}) {
  const hasEntries = meal.entries.length > 0;
  const contentId = `nutrition-meal-content-${meal.meal_type}`;
  const headingId = `nutrition-meal-${meal.meal_type}`;

  return (
    <section className="nutrition-meal" aria-labelledby={headingId} data-expanded={expanded}>
      <header className="nutrition-meal__header">
        <div>
          <h2 id={headingId}>
            <button
              aria-controls={contentId}
              aria-expanded={expanded}
              className="nutrition-meal__toggle"
              onClick={() => onExpandedChange(!expanded)}
              type="button"
            >
              <span>{mealLabels[meal.meal_type as MealType]}</span>
              <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={16} />
            </button>
          </h2>
          <span>
            {hasEntries
              ? `${formatNumber(meal.totals.energy_kcal)} ккал · ${meal.entries.length} ${plural(meal.entries.length, 'запись', 'записи', 'записей')}`
              : 'Пока без записей'}
          </span>
        </div>
        <div className="nutrition-meal__actions">
          <Button variant="secondary" type="button" onClick={onAdd}>
            <Icon name="plus" size={16} /> Добавить
          </Button>
        </div>
      </header>
      <div className="nutrition-meal__content" hidden={!expanded} id={contentId}>
        <div className="nutrition-meal__secondary-actions">
          <button type="button" onClick={onRepeatYesterday} aria-label="Повторить вчера">
            Вчера
          </button>
          {hasEntries && (
            <button type="button" onClick={onCopy}>
              Копировать
            </button>
          )}
        </div>
        {hasEntries ? (
          <ul className="nutrition-entry-list">
            {meal.entries.map((entry) => (
              <EntryRow
                entry={entry}
                isNew={newEntryIds.has(entry.id)}
                key={entry.id}
                onCopy={() => onCopyEntry(entry)}
              />
            ))}
          </ul>
        ) : (
          <p className="nutrition-meal__empty">Добавьте продукт — недавние будут под рукой.</p>
        )}
      </div>
    </section>
  );
}

function normalizeMeals(meals: FoodDiaryMeal[]): FoodDiaryMeal[] {
  return mealOrder.map(
    (mealType) =>
      meals.find((meal) => meal.meal_type === mealType) ?? {
        meal_type: mealType,
        entries: [],
        totals: emptyNutrition,
      },
  );
}

const completenessCopy: Record<FoodDiaryDay['status'], { label: string; description: string }> = {
  complete: {
    label: 'День заполнен',
    description: 'Эти данные можно использовать в средних значениях и калибровке.',
  },
  incomplete: {
    label: 'Заполнен частично',
    description: 'Записи сохранены, но день не участвует в средних до подтверждения.',
  },
  unlogged: {
    label: 'Нет записей',
    description: 'Отсутствующий день не считается как 0 ккал.',
  },
  fasted: {
    label: 'День без приёмов пищи',
    description:
      'Используйте эту отметку, только если сознательно не ели весь день. Записи еды будут недоступны, пока вы не снимете отметку.',
  },
};

function DayCompleteness({ day }: { day: FoodDiaryDay }) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const update = useMutation({
    mutationFn: (status: FoodDiaryDay['status']) =>
      api<FoodDiaryDay>('/api/v1/nutrition/diary/status', {
        method: 'PUT',
        body: { diary_date: day.diary_date, status },
      }),
    onSuccess: async (updated, status) => {
      if (status === 'incomplete') {
        trackProductEvent({
          name: 'nutrition_incomplete_day_confirmed',
          surface: productEventSurface(),
        });
      }
      queryClient.setQueryData(queryKeys.nutrition.diaryDate(day.diary_date), updated);
      await invalidateNutritionSummaries(queryClient);
      toast('Полнота дня обновлена');
    },
  });
  const hasEntries = day.meals.some((meal) => meal.entries.length > 0);
  const copy = completenessCopy[day.status];
  const motion = useSemanticMotion<HTMLElement>(`${day.status}|${day.status_is_explicit}`, {
    animateInitial: false,
  });
  return (
    <section
      className="nutrition-completeness"
      id={motion.elementId}
      aria-labelledby="nutrition-completeness-title"
      data-motion-phase={motion.motionPhase}
      data-motion-revision={motion.motionRevision}
      onAnimationEnd={motion.onMotionAnimationEnd}
    >
      <div className="nutrition-completeness__copy">
        <div>
          <span className="eyebrow">Статус дневника</span>
          <h2 id="nutrition-completeness-title">Полнота данных</h2>
        </div>
        <Badge tone={day.status === 'complete' || day.status === 'fasted' ? 'success' : undefined}>
          {day.status_is_explicit ? 'Подтверждено' : 'Не подтверждено'}
        </Badge>
      </div>
      <strong className="nutrition-completeness__status">{copy.label}</strong>
      <p>{copy.description}</p>
      <div className="nutrition-completeness__actions">
        <Button
          type="button"
          variant="secondary"
          aria-pressed={day.status === 'complete'}
          disabled={!hasEntries || update.isPending}
          onClick={() => update.mutate('complete')}
        >
          День заполнен
        </Button>
        <Button
          type="button"
          variant="secondary"
          aria-pressed={day.status === 'incomplete'}
          disabled={update.isPending}
          onClick={() => update.mutate('incomplete')}
        >
          Заполнен частично
        </Button>
        <Button
          type="button"
          variant="secondary"
          aria-pressed={day.status === 'fasted'}
          disabled={hasEntries || update.isPending}
          onClick={() => update.mutate('fasted')}
        >
          Отметить день без приёмов пищи
        </Button>
        {day.status_is_explicit && (
          <button
            type="button"
            className="nutrition-completeness__reset"
            disabled={update.isPending}
            onClick={() => update.mutate('unlogged')}
          >
            Снять отметку
          </button>
        )}
      </div>
      {update.error && (
        <div className="nutrition-inline-error" role="alert">
          <span>{(update.error as Error).message}</span>
          <button type="button" onClick={() => update.mutate(update.variables ?? day.status)}>
            Повторить
          </button>
        </div>
      )}
    </section>
  );
}

function NutritionWeekSelector({
  selectedDate,
  today,
  onSelect,
}: {
  selectedDate: string;
  today: string;
  onSelect: (value: string) => void;
}) {
  return (
    <WeekStrip
      anchorDate={selectedDate}
      ariaLabel="Неделя дневника"
      isDateDisabled={(date) => date > today}
      mode="picker"
      navigation={{
        nextDisabled: addCalendarDays(selectedDate, 7) > today,
        onNext: () => onSelect(addCalendarDays(selectedDate, 7)),
        onPrevious: () => onSelect(addCalendarDays(selectedDate, -7)),
      }}
      onSelect={onSelect}
      selectedDate={selectedDate}
      title={calendarWeek(selectedDate).includes(today) ? 'Эта неделя' : 'Неделя'}
      today={today}
    />
  );
}

function defaultMealType(timeZone?: string | null): MealType {
  try {
    const hour = Number(
      new Intl.DateTimeFormat('en-GB', {
        timeZone: timeZone || undefined,
        hour: '2-digit',
        hourCycle: 'h23',
      }).format(new Date()),
    );
    if (hour < 11) return 'breakfast';
    if (hour < 16) return 'lunch';
    if (hour < 21) return 'dinner';
  } catch {
    // A missing or invalid timezone falls back to snacks without changing the diary date.
  }
  return 'snacks';
}

export function NutritionDiary({
  timeZone,
  initialDate,
  initialMealType,
  initialFoodQuickAdd = false,
  initialHydrationOpen = false,
}: {
  timeZone?: string | null;
  initialDate?: string;
  initialMealType?: MealType;
  initialFoodQuickAdd?: boolean;
  initialHydrationOpen?: boolean;
}) {
  const today = dateInputValue(new Date(), timeZone || undefined);
  const [selectedDate, setSelectedDate] = useState(initialDate || today);
  const [addingTo, setAddingTo] = useState<{
    mealType: MealType;
    initialView?: 'browse' | 'quick-add';
  } | null>(() => {
    if (initialMealType) return { mealType: initialMealType, initialView: 'quick-add' };
    return initialFoodQuickAdd
      ? { mealType: defaultMealType(timeZone), initialView: 'quick-add' }
      : null;
  });
  const [copySubject, setCopySubject] = useState<CopySubject | null>(null);
  const [lastAddedEntryId, setLastAddedEntryId] = useState<number | null>(null);
  const [mealExpansion, setMealExpansion] = useState<Partial<Record<MealType, boolean>>>({});
  const diary = useQuery({
    queryKey: queryKeys.nutrition.diaryDate(selectedDate),
    queryFn: () => api<FoodDiaryDay>(`/api/v1/nutrition/diary?diary_date=${selectedDate}`),
  });
  const hydration = useQuery({
    queryKey: queryKeys.nutrition.hydrationDate(selectedDate),
    queryFn: () => api<HydrationDay>(`/api/v1/nutrition/hydration?diary_date=${selectedDate}`),
    enabled: false,
  });
  const dateLabel = formatDate(selectedDate, today);
  const meals = useMemo(() => normalizeMeals(diary.data?.meals ?? []), [diary.data?.meals]);
  const newEntryIds = useMemo(
    () => (lastAddedEntryId == null ? new Set<number>() : new Set([lastAddedEntryId])),
    [lastAddedEntryId],
  );

  return (
    <div className="nutrition-diary nutrition-diary--design-v2">
      <header className="nutrition-diary__intro">
        <div>
          <span className="eyebrow">Ежедневный дневник</span>
          <h1>Питание</h1>
          <p>{dateLabel.subtitle}</p>
        </div>
        <div className="nutrition-diary__intro-actions">
          <Button
            className="nutrition-diary__primary-action"
            type="button"
            onClick={() =>
              setAddingTo({ mealType: defaultMealType(timeZone), initialView: 'quick-add' })
            }
          >
            <Icon name="plus" size={16} /> Быстрый ввод
          </Button>
          <Button
            variant="secondary"
            type="button"
            aria-label="Найти продукт для текущего приёма пищи"
            onClick={() => setAddingTo({ mealType: defaultMealType(timeZone) })}
          >
            Найти продукт
          </Button>
        </div>
      </header>

      <NutritionWeekSelector
        selectedDate={selectedDate}
        today={today}
        onSelect={(date) => {
          setLastAddedEntryId(null);
          setMealExpansion({});
          setSelectedDate(date);
        }}
      />

      {diary.isLoading && <LoadingState label="Загружаем дневник…" />}
      {diary.error && (
        <ErrorState message={(diary.error as Error).message} retry={() => void diary.refetch()} />
      )}
      {diary.data && (
        <>
          <DayCompleteness day={diary.data} />
          <DayBalance
            day={diary.data}
            hydration={hydration.data}
            hydrationUnavailable={hydration.isError}
          />
          <section
            className="nutrition-section-card nutrition-food-card"
            aria-labelledby="nutrition-food-title"
          >
            <header className="nutrition-section-card__header nutrition-food-card__header">
              <div>
                <span className="eyebrow">Дневник приёмов пищи</span>
                <h2 id="nutrition-food-title">Еда</h2>
              </div>
              {diary.data.meals.some((meal) => meal.entries.length > 0) && (
                <button
                  className="nutrition-food-card__copy"
                  type="button"
                  onClick={() =>
                    setCopySubject({
                      scope: 'day',
                      sourceDate: selectedDate,
                      label: `Все записи за ${dateLabel.title.toLowerCase()}`,
                    })
                  }
                >
                  Скопировать день
                </button>
              )}
            </header>
            <div className="nutrition-meals">
              {meals.map((meal) => (
                <MealSection
                  key={meal.meal_type}
                  meal={meal}
                  newEntryIds={newEntryIds}
                  expanded={mealExpansion[meal.meal_type as MealType] ?? meal.entries.length > 0}
                  onExpandedChange={(expanded) =>
                    setMealExpansion((current) => ({
                      ...current,
                      [meal.meal_type]: expanded,
                    }))
                  }
                  onAdd={() =>
                    setAddingTo({ mealType: meal.meal_type as MealType, initialView: 'browse' })
                  }
                  onCopy={() =>
                    setCopySubject({
                      scope: 'meal',
                      sourceDate: selectedDate,
                      sourceMeal: meal.meal_type as MealType,
                      label: `${mealLabels[meal.meal_type as MealType]} — ${meal.entries.length} записей`,
                    })
                  }
                  onRepeatYesterday={() =>
                    setCopySubject({
                      scope: 'meal',
                      sourceDate: addCalendarDays(selectedDate, -1),
                      sourceMeal: meal.meal_type as MealType,
                      initialTargetDate: selectedDate,
                      label: `${mealLabels[meal.meal_type as MealType]} за предыдущий день`,
                    })
                  }
                  onCopyEntry={(entry) =>
                    setCopySubject({
                      scope: 'product',
                      sourceDate: selectedDate,
                      sourceMeal: meal.meal_type as MealType,
                      entryId: entry.id,
                      label: entry.food_name,
                    })
                  }
                />
              ))}
            </div>
          </section>
          <DaySummary day={diary.data} />
        </>
      )}

      <HydrationTracker diaryDate={selectedDate} initialExpanded={initialHydrationOpen} />

      {addingTo && (
        <FoodPickerDialog
          diaryDate={selectedDate}
          mealType={addingTo.mealType}
          initialView={addingTo.initialView}
          disabled={diary.data?.status === 'fasted'}
          onAdded={(entry) => {
            setLastAddedEntryId(entry.id);
            setMealExpansion((current) => ({
              ...current,
              [addingTo.mealType]: true,
            }));
          }}
          onClose={() => setAddingTo(null)}
        />
      )}
      {copySubject && (
        <CopyDiaryDialog subject={copySubject} today={today} onClose={() => setCopySubject(null)} />
      )}
    </div>
  );
}
