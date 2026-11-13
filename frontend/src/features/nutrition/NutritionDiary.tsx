import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
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
  FoodDiaryCopyPreviewResponse,
  FoodDiaryCopyResponse,
  FoodDiaryEntry,
  FoodDiaryMeal,
  FoodDiaryNutrition,
} from '../../shared/api/types';
import type { components } from '../../shared/api/schema';
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
import { NutritionSuggestions } from './NutritionSuggestions';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';

const mealOrder: MealType[] = ['breakfast', 'lunch', 'dinner', 'snacks'];
const mealLabels: Record<MealType, string> = {
  breakfast: 'Завтрак',
  lunch: 'Обед',
  dinner: 'Ужин',
  snacks: 'Перекусы',
};
const mealGenitive: Record<MealType, string> = {
  breakfast: 'завтрака',
  lunch: 'обеда',
  dinner: 'ужина',
  snacks: 'перекусов',
};

type RepeatRequest = {
  candidate: NonNullable<FoodDiaryDay['repeat_candidate']>;
  date: string;
  key: string;
};
type RepeatUndo = {
  date: string;
  meal: MealType;
  entries: FoodDiaryEntry[];
};
type RepeatNotice = {
  date: string;
  meal: MealType;
  kind: 'added' | 'already-removed' | 'undone' | 'repeat-error' | 'conflict' | 'undo-error';
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
    const weight = entry.weight_g === null ? '' : ` · ${formatNumber(entry.weight_g)} г`;
    return `${formatNumber(entry.amount, 2)} ${Number(entry.amount) === 1 ? 'порция' : 'порции'}${weight}`;
  }
  if (entry.amount_unit === 'ml') return `${formatNumber(entry.amount, 1)} мл`;
  return `${formatNumber(entry.weight_g, 1)} г`;
}

function nutritionEntryMeta(entry: FoodDiaryEntry): string {
  if (entry.entry_kind === 'quick_add') {
    const source = entry.nutrition_source === 'restaurant' ? 'ресторанная оценка' : 'своя оценка';
    const confidence =
      entry.nutrition_confidence ??
      (entry.nutrition.protein_g === null ||
      entry.nutrition.fat_g === null ||
      entry.nutrition.carbs_g === null
        ? 'partial'
        : 'approximate');
    return `Приблизительно · ${source} · ${confidence === 'partial' ? 'частичные БЖУ' : 'все БЖУ'}`;
  }
  return entry.nutrition_source === 'recipe' ? 'Рецепт · точный расчёт' : 'Каталог · точный расчёт';
}

function targetStatus(remaining: number, target: number, unit: string): string {
  if (remaining >= 0) return `Осталось ${formatNumber(remaining)}\u00a0${unit}`;
  const over = Math.abs(remaining);
  if (target > 0 && over / target <= 0.05)
    return `Немного выше ориентира: ${formatNumber(over)}\u00a0${unit}`;
  return `Выше ориентира на ${formatNumber(over)}\u00a0${unit}`;
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
        {total !== null && (
          <small>
            Записано: {formatNumber(total, 1)} {unit}
          </small>
        )}
        {target !== null && (
          <small>
            Цель: {formatNumber(target, 1)} {unit}
          </small>
        )}
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

function DaySummary({
  day,
  selectedDate,
  today,
  onOpenSettings,
  onOverride,
  readOnlyTargets,
}: {
  day: FoodDiaryDay;
  selectedDate: string;
  today: string;
  onOpenSettings?: () => void;
  onOverride?: (
    date: string,
    target: components['schemas']['NutritionTargetResponse'] | null,
    dayType: components['schemas']['NutritionResolvedTargetResponse']['day_type'],
  ) => void;
  readOnlyTargets: boolean;
}) {
  const { totals, targets, remaining } = day;
  const resolved = useQuery({
    queryKey: ['nutrition', 'targets', 'resolved', selectedDate],
    queryFn: () =>
      api<components['schemas']['NutritionResolvedTargetResponse']>(
        `/api/v1/nutrition/targets/for-date?target_date=${selectedDate}`,
      ),
    enabled: Boolean(onOpenSettings),
  });
  const source =
    resolved.data?.origin === 'schedule'
      ? 'По программе'
      : resolved.data?.origin === 'date'
        ? 'Изменено вручную'
        : resolved.data?.origin === 'base'
          ? 'Базовая цель'
          : null;
  const dayNames = {
    training: 'Тренировочный день',
    recovery: 'Восстановительный день',
    rest: 'День отдыха',
  };
  const weekNames = { light: 'Лёгкая неделя', medium: 'Средняя неделя', heavy: 'Тяжёлая неделя' };
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
        {day.targets ? (
          <Badge tone="success">{source ?? 'Цель КБЖУ настроена'}</Badge>
        ) : (
          <Badge>Без цели</Badge>
        )}
      </div>
      {resolved.data &&
        (resolved.data.day_type || resolved.data.week_type || resolved.data.frozen) && (
          <p className="nutrition-goal-day-meta">
            {[
              resolved.data.day_type && dayNames[resolved.data.day_type],
              resolved.data.week_type && weekNames[resolved.data.week_type],
              resolved.data.frozen && 'Цель сохранена',
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        )}
      {resolved.error && (
        <ErrorState
          message="Не удалось узнать источник цели."
          retry={() => void resolved.refetch()}
        />
      )}
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
          {onOpenSettings ? (
            <Button type="button" variant="secondary" onClick={onOpenSettings}>
              Настроить цель
            </Button>
          ) : (
            <a href="#nutrition-target-settings">Настроить цель</a>
          )}
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
      {onOpenSettings && (
        <div className="nutrition-goal-actions">
          <Button
            type="button"
            variant="secondary"
            data-nutrition-focus="settings"
            onClick={onOpenSettings}
          >
            Настройки КБЖУ
          </Button>
          {onOverride &&
            !readOnlyTargets &&
            selectedDate >= today &&
            !resolved.data?.frozen &&
            day.status !== 'complete' &&
            day.status !== 'fasted' && (
              <Button
                type="button"
                variant="ghost"
                data-nutrition-focus="override"
                disabled={!resolved.isSuccess}
                onClick={() =>
                  onOverride(
                    selectedDate,
                    resolved.data?.target ?? null,
                    resolved.data?.day_type ?? null,
                  )
                }
              >
                Изменить на эту дату
              </Button>
            )}
        </div>
      )}
    </aside>
  );
}

function EntryRow({
  entry,
  isNew,
  onCopy,
  readOnly = false,
}: {
  entry: FoodDiaryEntry;
  isNew: boolean;
  onCopy: () => void;
  readOnly?: boolean;
}) {
  const queryClient = useQueryClient();
  const { confirm, toast } = useFeedback();
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState(entry.amount);
  const [amountUnit, setAmountUnit] = useState<FoodDiaryEntry['amount_unit']>(entry.amount_unit);
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
                ? `${nutritionEntryMeta(entry)}${entry.logged_at ? ` · ${entry.logged_at.slice(0, 5)}` : ''}`
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
            disabled={readOnly || remove.isPending}
            aria-label={`Повторить ${entry.food_name}`}
            title="Повторить"
          >
            <Icon name="sync" size={20} />
          </button>
          {entry.entry_kind !== 'quick_add' && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              disabled={readOnly || remove.isPending}
              aria-label={`Изменить ${entry.food_name}`}
              title="Изменить"
            >
              <Icon name="edit" size={20} />
            </button>
          )}
          <button
            type="button"
            onClick={() => void requestDelete()}
            disabled={readOnly || remove.isPending}
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
                setAmountUnit(event.target.value as FoodDiaryEntry['amount_unit']);
              }}
            >
              <option value="g">граммы</option>
              {(entry.amount_unit === 'ml' || entry.nutrition_basis_unit === 'ml') && (
                <option value="ml">миллилитры</option>
              )}
              {entry.serving_weight_g && <option value="serving">порции</option>}
            </Select>
          </Field>
          <div className="nutrition-entry-editor__actions">
            <Button disabled={readOnly || update.isPending} type="submit">
              {update.isPending ? 'Сохраняем…' : 'Сохранить'}
            </Button>
            <Button
              disabled={readOnly || update.isPending}
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
  repeatAction,
  repeatFeedback,
  readOnly = false,
}: {
  meal: FoodDiaryMeal;
  newEntryIds: ReadonlySet<number>;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  onAdd: () => void;
  onCopy: () => void;
  onRepeatYesterday: () => void;
  onCopyEntry: (entry: FoodDiaryEntry) => void;
  repeatAction?: ReactNode;
  repeatFeedback?: ReactNode;
  readOnly?: boolean;
}) {
  const hasEntries = meal.entries.length > 0;
  const contentId = `nutrition-meal-content-${meal.meal_type}`;
  const headingId = `nutrition-meal-${meal.meal_type}`;

  return (
    <section
      className="nutrition-meal"
      aria-labelledby={headingId}
      data-expanded={expanded}
      data-has-entries={hasEntries}
    >
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
              ? `${formatNumber(meal.totals.energy_kcal)}\u00a0ккал · Б\u00a0${formatNumber(meal.totals.protein_g, 1)} · Ж\u00a0${formatNumber(meal.totals.fat_g, 1)} · У\u00a0${formatNumber(meal.totals.carbs_g, 1)}\u00a0г · ${meal.entries.length}\u00a0${plural(meal.entries.length, 'запись', 'записи', 'записей')}`
              : 'Пока без записей'}
          </span>
        </div>
        <div className="nutrition-meal__actions">
          <Button variant="secondary" type="button" onClick={onAdd}>
            <Icon name="plus" size={16} /> Добавить
          </Button>
        </div>
      </header>
      {repeatAction}
      {repeatFeedback}
      <div className="nutrition-meal__content" hidden={!expanded} id={contentId}>
        <div className="nutrition-meal__secondary-actions">
          <button
            type="button"
            disabled={readOnly}
            onClick={onRepeatYesterday}
            aria-label="Повторить вчера"
          >
            Вчера
          </button>
          {hasEntries && (
            <button type="button" disabled={readOnly} onClick={onCopy}>
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
                readOnly={readOnly}
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

function DayCompleteness({ day, readOnly = false }: { day: FoodDiaryDay; readOnly?: boolean }) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const [expanded, setExpanded] = useState(false);
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
      trackProductEvent({
        name: 'nutrition_food_completeness_set',
        surface: productEventSurface(),
        status,
      });
      queryClient.setQueryData(queryKeys.nutrition.diaryDate(updated.diary_date), updated);
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
      <h2 id="nutrition-completeness-title" className="eyebrow">
        Проверка дневника
      </h2>
      <button
        type="button"
        className="nutrition-completeness__toggle"
        aria-expanded={expanded}
        aria-controls="nutrition-completeness-actions"
        onClick={() => setExpanded((value) => !value)}
      >
        <span className="nutrition-completeness__summary">
          <strong className="nutrition-completeness__status">
            {day.status_is_explicit || day.status !== 'unlogged' ? copy.label : 'Не подтверждено'}
          </strong>
          {(day.status_is_explicit || day.status !== 'unlogged') && (
            <span>{day.status_is_explicit ? 'Подтверждено' : 'Не подтверждено'}</span>
          )}
          <span>Изменить статус</span>
        </span>
        <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={16} />
      </button>
      <div id="nutrition-completeness-actions" hidden={!expanded}>
        <p>{copy.description}</p>
        {readOnly && (
          <p className="muted demo-capability-notice" role="status">
            Изменение статуса дневника доступно после входа.
          </p>
        )}
        <fieldset className="demo-capability-fieldset" disabled={readOnly}>
          <div className="nutrition-completeness__actions">
            <Button
              type="button"
              variant="secondary"
              aria-pressed={day.status_is_explicit && day.status === 'complete'}
              data-yfc-choice="compact"
              disabled={!hasEntries || update.isPending}
              onClick={() => update.mutate('complete')}
            >
              День заполнен
            </Button>
            <Button
              type="button"
              variant="secondary"
              aria-pressed={day.status_is_explicit && day.status === 'incomplete'}
              data-yfc-choice="compact"
              disabled={update.isPending}
              onClick={() => update.mutate('incomplete')}
            >
              Заполнен частично
            </Button>
            <Button
              type="button"
              variant="secondary"
              aria-pressed={day.status_is_explicit && day.status === 'fasted'}
              data-yfc-choice="compact"
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
        </fieldset>
        {update.isPending && <p role="status">Сохраняем статус…</p>}
        {update.error && (
          <div className="nutrition-inline-error" role="alert">
            <span>{(update.error as Error).message}</span>
            <button
              type="button"
              disabled={readOnly || update.isPending}
              onClick={() => update.mutate(update.variables ?? day.status)}
            >
              Повторить
            </button>
          </div>
        )}
      </div>
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
  readOnlyEntries = false,
  demoSafeMode = false,
  readOnlyTargets = false,
  onOpenSettings,
  onOverride,
  onDateChange,
  selectedDate: controlledDate,
}: {
  timeZone?: string | null;
  initialDate?: string;
  initialMealType?: MealType;
  initialFoodQuickAdd?: boolean;
  initialHydrationOpen?: boolean;
  readOnlyEntries?: boolean;
  demoSafeMode?: boolean;
  readOnlyTargets?: boolean;
  onOpenSettings?: () => void;
  onOverride?: (
    date: string,
    target: components['schemas']['NutritionTargetResponse'] | null,
    dayType: components['schemas']['NutritionResolvedTargetResponse']['day_type'],
  ) => void;
  onDateChange?: (date: string) => void;
  selectedDate?: string;
}) {
  const today = dateInputValue(new Date(), timeZone || undefined);
  const [uncontrolledDate, setUncontrolledDate] = useState(initialDate || today);
  const selectedDate = controlledDate ?? uncontrolledDate;
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
  const [hydrationQuickAddRequest, setHydrationQuickAddRequest] = useState(0);
  const [lastAddedEntryId, setLastAddedEntryId] = useState<number | null>(null);
  const [mealExpansion, setMealExpansion] = useState<Partial<Record<MealType, boolean>>>({});
  const [pendingRepeats, setPendingRepeats] = useState<Record<string, RepeatRequest>>({});
  const [repeatUndo, setRepeatUndo] = useState<RepeatUndo | null>(null);
  const [repeatNotice, setRepeatNotice] = useState<RepeatNotice | null>(null);
  const repeatInFlight = useRef(false);
  const undoInFlight = useRef(false);
  const repeatTokens = useRef<Record<string, string>>({});
  const repeatFeedback = useRef<HTMLDivElement>(null);
  const keepRepeatFocus = useRef(false);
  const queryClient = useQueryClient();
  const diary = useQuery({
    queryKey: queryKeys.nutrition.diaryDate(selectedDate),
    queryFn: () => api<FoodDiaryDay>(`/api/v1/nutrition/diary?diary_date=${selectedDate}`),
  });
  const dateLabel = formatDate(selectedDate, today);
  const meals = useMemo(() => normalizeMeals(diary.data?.meals ?? []), [diary.data?.meals]);
  const hasDiaryEntries = meals.some((meal) => meal.entries.length > 0);
  const newEntryIds = useMemo(
    () => (lastAddedEntryId == null ? new Set<number>() : new Set([lastAddedEntryId])),
    [lastAddedEntryId],
  );
  const refreshDiary = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['nutrition', 'foods', 'recent'] }),
      invalidateNutritionSummaries(queryClient),
    ]);
  };
  const repeat = useMutation({
    mutationFn: async (request: RepeatRequest) => {
      const body = {
        source_date: request.candidate.source_date,
        source_meal_type: request.candidate.source_meal_type,
        target_date: request.date,
        target_meal_type: request.candidate.source_meal_type,
      };
      if (!repeatTokens.current[request.key]) {
        const preview = await api<FoodDiaryCopyPreviewResponse>(
          '/api/v1/nutrition/diary/copy/meal/preview',
          { method: 'POST', body },
        );
        repeatTokens.current[request.key] = preview.preview_token;
      }
      return api<FoodDiaryCopyResponse>('/api/v1/nutrition/diary/copy/meal', {
        method: 'POST',
        headers: { 'Idempotency-Key': request.key, 'X-Require-Empty-Meal': 'true' },
        body: { ...body, preview_token: `${repeatTokens.current[request.key]}~quick` },
      });
    },
    onSuccess: async (result, request) => {
      const meal = request.candidate.source_meal_type;
      trackProductEvent({
        name: 'nutrition_food_repeat_used',
        surface: productEventSurface(),
        scope: 'meal',
        outcome: 'completed',
      });
      delete repeatTokens.current[request.key];
      setPendingRepeats((current) => {
        const next = { ...current };
        delete next[request.date];
        return next;
      });
      setRepeatUndo({ date: request.date, meal, entries: result.entries });
      setRepeatNotice({
        date: request.date,
        meal,
        kind: result.entries.length ? 'added' : 'already-removed',
      });
      await refreshDiary();
    },
    onError: async (error, request) => {
      const conflict =
        typeof error === 'object' && error !== null && 'status' in error && error.status === 409;
      if (conflict) {
        delete repeatTokens.current[request.key];
        setPendingRepeats((current) => {
          const next = { ...current };
          delete next[request.date];
          return next;
        });
        await refreshDiary();
      }
      setRepeatNotice({
        date: request.date,
        meal: request.candidate.source_meal_type,
        kind: conflict ? 'conflict' : 'repeat-error',
      });
    },
    onSettled: () => {
      repeatInFlight.current = false;
    },
  });
  const undoRepeat = useMutation({
    mutationFn: async (snapshot: RepeatUndo) => {
      for (const entry of snapshot.entries) {
        try {
          await api<void>(`/api/v1/nutrition/diary/entries/${entry.id}~undo`, {
            method: 'DELETE',
            headers: { 'X-Diary-Entry-Version': entry.created_at },
          });
        } catch (error) {
          if (!(
            typeof error === 'object' &&
            error !== null &&
            'status' in error &&
            error.status === 404
          )) {
            throw error;
          }
        }
      }
    },
    onSuccess: (_, snapshot) => {
      setRepeatUndo(null);
      setRepeatNotice({ date: snapshot.date, meal: snapshot.meal, kind: 'undone' });
    },
    onError: (_, snapshot) => {
      setRepeatNotice({ date: snapshot.date, meal: snapshot.meal, kind: 'undo-error' });
    },
    onSettled: async () => {
      await refreshDiary();
      undoInFlight.current = false;
    },
  });
  const candidate = pendingRepeats[selectedDate]?.candidate ?? diary.data?.repeat_candidate;
  useEffect(() => {
    if (
      repeatNotice?.date === selectedDate &&
      keepRepeatFocus.current &&
      !repeat.isPending &&
      !undoRepeat.isPending
    ) {
      if (document.activeElement === document.body)
        repeatFeedback.current?.focus({ preventScroll: true });
      keepRepeatFocus.current = false;
    }
  }, [candidate, repeatNotice, selectedDate, repeat.isPending, undoRepeat.isPending]);
  const submitRepeat = () => {
    if (!candidate || repeatInFlight.current || undoInFlight.current || undoRepeat.isPending)
      return;
    repeatInFlight.current = true;
    if (!pendingRepeats[selectedDate]) {
      trackProductEvent({
        name: 'nutrition_food_add_path_selected',
        surface: productEventSurface(),
        path: 'repeat',
      });
      trackProductEvent({
        name: 'nutrition_food_repeat_used',
        surface: productEventSurface(),
        scope: 'meal',
        outcome: 'started',
      });
    }
    const request = pendingRepeats[selectedDate] ?? {
      candidate,
      date: selectedDate,
      key:
        globalThis.crypto?.randomUUID?.() ??
        `repeat-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    };
    setPendingRepeats((current) => ({ ...current, [selectedDate]: request }));
    setRepeatNotice(null);
    repeat.mutate(request);
  };

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
            variant="primary"
            type="button"
            aria-label="Добавить продукт в текущий приём пищи"
            data-testid="nutrition-add-product"
            onClick={() => setAddingTo({ mealType: defaultMealType(timeZone) })}
          >
            <Icon name="plus" size={16} /> <span>Добавить продукт</span>
          </Button>
          <Button
            variant="secondary"
            type="button"
            onClick={() =>
              setAddingTo({ mealType: defaultMealType(timeZone), initialView: 'quick-add' })
            }
          >
            Быстрый ввод
          </Button>
        </div>
      </header>

      <NutritionWeekSelector
        selectedDate={selectedDate}
        today={today}
        onSelect={(date) => {
          setLastAddedEntryId(null);
          setMealExpansion({});
          if (controlledDate === undefined) setUncontrolledDate(date);
          onDateChange?.(date);
        }}
      />

      <Button
        className="nutrition-diary__water-action"
        variant="primary"
        type="button"
        onClick={() => setHydrationQuickAddRequest((value) => value + 1)}
      >
        <Icon name="plus" size={16} /> Добавить воду
      </Button>

      {diary.isLoading && <LoadingState label="Загружаем дневник…" />}
      {diary.error && (
        <ErrorState message={(diary.error as Error).message} retry={() => void diary.refetch()} />
      )}
      {diary.data && (
        <>
          <DaySummary
            day={diary.data}
            selectedDate={selectedDate}
            today={today}
            onOpenSettings={onOpenSettings}
            onOverride={onOverride}
            readOnlyTargets={readOnlyTargets}
          />
          <section
            className="nutrition-section-card nutrition-food-card"
            aria-labelledby="nutrition-food-title"
          >
            <header className="nutrition-section-card__header nutrition-food-card__header">
              <div>
                <span className="eyebrow">Дневник приёмов пищи</span>
                <h2 id="nutrition-food-title">Еда</h2>
                {!readOnlyEntries && !hasDiaryEntries && (
                  <span className="sr-only" id="nutrition-copy-empty">
                    В этом дне нет записей для копирования.
                  </span>
                )}
              </div>
              <Button
                className="nutrition-food-card__copy"
                variant="secondary"
                type="button"
                disabled={readOnlyEntries || !hasDiaryEntries}
                aria-describedby={
                  readOnlyEntries
                    ? 'nutrition-copy-readonly'
                    : !hasDiaryEntries
                      ? 'nutrition-copy-empty'
                      : undefined
                }
                onClick={() =>
                  setCopySubject({
                    scope: 'day',
                    sourceDate: selectedDate,
                    label: 'Все записи питания',
                  })
                }
              >
                <Icon name="sync" size={16} />
                <span>Копировать день</span>
              </Button>
              {readOnlyEntries && (
                <p
                  className="muted demo-capability-notice"
                  id="nutrition-copy-readonly"
                  role="status"
                >
                  Новые записи можно добавить в демо-сессию. Редактирование, удаление и копирование
                  существующих записей доступно после входа.
                </p>
              )}
            </header>
            <div className="nutrition-meals">
              {meals.map((meal) => (
                <MealSection
                  key={meal.meal_type}
                  meal={meal}
                  newEntryIds={newEntryIds}
                  repeatAction={
                    candidate &&
                    candidate.entry_count > 0 &&
                    candidate.source_meal_type === meal.meal_type &&
                    diary.data.status !== 'fasted' &&
                    !readOnlyEntries ? (
                      <div className="nutrition-meal__repeat">
                        <span>{`${mealLabels[candidate.source_meal_type]} за ${new Date(`${candidate.source_date}T12:00:00`).toLocaleDateString('ru-RU')} — в дневник за ${new Date(`${selectedDate}T12:00:00`).toLocaleDateString('ru-RU')}`}</span>
                        <Button
                          variant="secondary"
                          type="button"
                          disabled={repeat.isPending || undoRepeat.isPending}
                          data-testid="nutrition-repeat-default"
                          onClick={(event) => {
                            keepRepeatFocus.current =
                              document.activeElement === event.currentTarget;
                            submitRepeat();
                          }}
                        >
                          {repeat.isPending && repeat.variables?.date === selectedDate
                            ? 'Добавляем…'
                            : 'Повторить'}
                        </Button>
                      </div>
                    ) : null
                  }
                  repeatFeedback={
                    !readOnlyEntries &&
                    repeatNotice?.date === selectedDate &&
                    repeatNotice.meal === meal.meal_type ? (
                      <div
                        ref={repeatFeedback}
                        tabIndex={-1}
                        className={`${repeatNotice.kind.endsWith('error') || repeatNotice.kind === 'conflict' ? 'hydration-mutation-error' : 'hydration-undo'} nutrition-repeat-feedback`}
                        role={
                          repeatNotice.kind.endsWith('error') || repeatNotice.kind === 'conflict'
                            ? 'alert'
                            : 'status'
                        }
                      >
                        <span>
                          {repeatNotice.kind === 'added' &&
                            `${mealLabels[repeatNotice.meal]} добавлен${repeatNotice.meal === 'snacks' ? 'ы' : ''}`}
                          {repeatNotice.kind === 'already-removed' && 'Записи повтора уже удалены'}
                          {repeatNotice.kind === 'undone' &&
                            `Повтор ${mealGenitive[repeatNotice.meal]} отменён`}
                          {repeatNotice.kind === 'repeat-error' &&
                            `Не удалось проверить, добавлен ли ${mealLabels[repeatNotice.meal].toLowerCase()}. Попробуйте ещё раз.`}
                          {repeatNotice.kind === 'conflict' &&
                            'Не удалось повторить приём пищи. Проверьте записи и попробуйте ещё раз.'}
                          {repeatNotice.kind === 'undo-error' &&
                            `Не удалось отменить повтор. Проверьте записи ${mealGenitive[repeatNotice.meal]}.`}
                        </span>
                        {(repeatNotice.kind === 'added' || repeatNotice.kind === 'undo-error') &&
                          repeatUndo &&
                          repeatUndo.entries.length > 0 && (
                            <Button
                              variant="secondary"
                              type="button"
                              disabled={undoRepeat.isPending || repeat.isPending}
                              aria-label={`${repeatNotice.kind === 'undo-error' ? 'Повторить отмену' : 'Отменить повтор'} ${mealGenitive[repeatUndo.meal]}`}
                              onClick={(event) => {
                                if (undoInFlight.current || repeatInFlight.current) return;
                                keepRepeatFocus.current =
                                  document.activeElement === event.currentTarget;
                                undoInFlight.current = true;
                                undoRepeat.mutate(repeatUndo);
                              }}
                            >
                              {repeatNotice.kind === 'undo-error' ? 'Повторить отмену' : 'Отменить'}
                            </Button>
                          )}
                      </div>
                    ) : null
                  }
                  expanded={mealExpansion[meal.meal_type as MealType] ?? false}
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
                  readOnly={readOnlyEntries}
                />
              ))}
            </div>
          </section>
        </>
      )}

      <HydrationTracker
        diaryDate={selectedDate}
        initialExpanded={initialHydrationOpen}
        quickAddRequest={hydrationQuickAddRequest}
      />

      {diary.data && (
        <>
          <DayCompleteness
            key={diary.data.diary_date}
            day={diary.data}
            readOnly={readOnlyEntries || demoSafeMode}
          />
          <NutritionSuggestions
            diaryDate={selectedDate}
            initialMealType={initialMealType ?? defaultMealType(timeZone)}
            readOnly={readOnlyEntries}
            demoSafeMode={demoSafeMode}
          />
        </>
      )}

      {addingTo && (
        <FoodPickerDialog
          diaryDate={selectedDate}
          mealType={addingTo.mealType}
          mealEntries={
            diary.data?.meals.find((meal) => meal.meal_type === addingTo.mealType)?.entries ?? []
          }
          initialView={addingTo.initialView}
          disabled={diary.data?.status === 'fasted'}
          demoSafeMode={demoSafeMode}
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
      {copySubject && !readOnlyEntries && (
        <CopyDiaryDialog subject={copySubject} today={today} onClose={() => setCopySubject(null)} />
      )}
    </div>
  );
}
