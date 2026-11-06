import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { components } from '../../shared/api/schema';
import type { NutritionTarget } from '../../shared/api/types';
import { addCalendarDays, dateInputValue } from '../../shared/dateTime';
import { invalidateNutritionSummaries } from '../../shared/queryKeys';
import { Button, ErrorState, LoadingState } from '../../shared/ui/common';
import { DateInput } from '../../shared/ui/PickerInput';
import { Icon } from '../../shared/ui/Icon';
import { useTelegramOverlayBackButton } from '../../shared/telegram/useTelegramOverlayBackButton';
import { NutritionForm } from './NutritionForm';

type Schemas = components['schemas'];
type DayType = Schemas['NutritionScheduleRuleSave']['day_type'];
type WeekType = NonNullable<Schemas['NutritionScheduleRuleSave']['week_type']>;
type Values = Pick<
  Schemas['NutritionScheduleRuleSave'],
  'calories' | 'protein_g' | 'fat_g' | 'carbs_g'
>;
type Rule = Schemas['NutritionScheduleRuleSave'];
type Change = Schemas['NutritionSchedulePreviewChange'];
type Preview = {
  kind: 'date' | 'rule' | 'binding';
  body: Record<string, unknown>;
  changes: Change[];
  key: string;
  from: string;
  to: string;
  end: string;
};

const dayLabels: Record<DayType, string> = {
  training: 'Тренировочный',
  recovery: 'Восстановительный',
  rest: 'Отдых',
};
const weekLabels: Record<WeekType, string> = {
  light: 'Лёгкая неделя',
  medium: 'Средняя неделя',
  heavy: 'Тяжёлая неделя',
};
const fields = [
  ['calories', 'Калории, ккал', 800, 6000],
  ['protein_g', 'Белки, г', 0, 400],
  ['fat_g', 'Жиры, г', 0, 250],
  ['carbs_g', 'Углеводы, г', 0, 800],
] as const;

function formatValues(target: Values | null | undefined) {
  return target
    ? `${target.calories.toLocaleString('ru-RU')} ккал · Б ${target.protein_g} · Ж ${target.fat_g} · У ${target.carbs_g}`
    : 'Цель не задана';
}

function targetValues(target: Values | null | undefined): Values {
  return target
    ? {
        calories: target.calories,
        protein_g: target.protein_g,
        fat_g: target.fat_g,
        carbs_g: target.carbs_g,
      }
    : { calories: 2200, protein_g: 150, fat_g: 70, carbs_g: 240 };
}

function keyForChange() {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `nutrition-${Date.now()}-${Math.random().toString(36).slice(2)}`
  );
}

export function NutritionTargets({
  mode,
  date,
  initial,
  dateTarget,
  initialDayType,
  timeZone,
  readOnly,
  onClose,
  onSaved,
}: {
  mode: 'settings' | 'override';
  date: string;
  initial?: NutritionTarget | null;
  dateTarget?: NutritionTarget | null;
  initialDayType?: DayType | null;
  timeZone?: string | null;
  readOnly: boolean;
  onClose: (savedDate?: string) => void;
  onSaved?: () => void | Promise<void>;
}) {
  const queryClient = useQueryClient();
  const today = dateInputValue(new Date(), timeZone || undefined);
  const tomorrow = addCalendarDays(today, 1);
  const [selectedDate, setSelectedDate] = useState(date);
  const [dayType, setDayType] = useState<DayType | ''>(initialDayType ?? '');
  const [weekDay, setWeekDay] = useState<DayType>('training');
  const [scope, setScope] = useState<'date' | 'future'>('date');
  const [editing, setEditing] = useState<{ day: DayType; week: WeekType | null } | null>(null);
  const [editBase, setEditBase] = useState(false);
  const [values, setValues] = useState<Values>(() => targetValues(dateTarget ?? initial));
  const [confirmMismatch, setConfirmMismatch] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [checking, setChecking] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const previewOpen = preview !== null;
  useEffect(() => {
    heading.current?.focus();
  }, [previewOpen]);
  useTelegramOverlayBackButton(true, () => {
    if (previewOpen) setPreview(null);
    else onClose();
  });
  const program = useQuery({
    queryKey: ['nutrition', 'targets', 'program'],
    staleTime: 0,
    queryFn: () =>
      api<Schemas['NutritionScheduleProgramContext'] | null>(
        '/api/v1/nutrition/targets/schedule/program',
      ),
  });
  const rules = useQuery({
    queryKey: ['nutrition', 'targets', 'schedule'],
    staleTime: 0,
    queryFn: () =>
      api<Schemas['NutritionScheduleRuleResponse'][]>('/api/v1/nutrition/targets/schedule'),
  });
  const binding = useQuery({
    queryKey: ['nutrition', 'targets', 'binding', tomorrow],
    staleTime: 0,
    queryFn: () =>
      api<Schemas['NutritionScheduleBindingStatus'] | null>(
        `/api/v1/nutrition/targets/schedule/binding?target_date=${tomorrow}`,
      ),
  });
  const programDay = useQuery({
    queryKey: [
      'nutrition',
      'targets',
      'program-day',
      program.data?.program_id,
      program.data?.revision_number,
      selectedDate,
    ],
    queryFn: () =>
      api<Schemas['NutritionProgramDayResponse']>(
        `/api/v1/nutrition/targets/program-day?program_id=${program.data!.program_id}&revision_number=${program.data!.revision_number}&target_date=${selectedDate}`,
      ),
    enabled: mode === 'override' && Boolean(program.data?.revision_number),
  });
  const current = useQuery({
    queryKey: ['nutrition', 'targets', 'resolved', selectedDate],
    queryFn: () =>
      api<Schemas['NutritionResolvedTargetResponse']>(
        `/api/v1/nutrition/targets/for-date?target_date=${selectedDate}`,
      ),
    enabled: mode === 'override',
  });
  const mutation = useMutation({
    mutationFn: (item: Preview) =>
      api(
        item.kind === 'date'
          ? '/api/v1/nutrition/targets/dates'
          : item.kind === 'rule'
            ? '/api/v1/nutrition/targets/schedule'
            : '/api/v1/nutrition/targets/schedule/binding/confirm',
        {
          method: 'POST',
          headers: { 'Idempotency-Key': item.key },
          body: item.body,
        },
      ),
    onSuccess: async () => {
      await Promise.all([
        invalidateNutritionSummaries(queryClient),
        queryClient.invalidateQueries({ queryKey: ['nutrition', 'targets'] }),
      ]);
      await onSaved?.();
      onClose(mode === 'override' ? selectedDate : undefined);
    },
  });
  const mismatch =
    Math.abs(values.protein_g * 4 + values.fat_g * 9 + values.carbs_g * 4 - values.calories) >
    Math.max(100, Math.round(values.calories * 0.1));
  const effective =
    program.data && program.data.start_date > tomorrow ? program.data.start_date : tomorrow;
  const programEnd = program.data
    ? addCalendarDays(program.data.start_date, program.data.duration_weeks * 7 - 1)
    : effective;
  const end = programEnd > effective ? programEnd : effective;
  const latest = (day: DayType, week: WeekType | null) =>
    rules.data
      ?.filter(
        (rule) => rule.scope === 'template' && rule.day_type === day && rule.week_type === week,
      )
      .sort((a, b) => b.effective_from.localeCompare(a.effective_from) || b.id - a.id)[0];
  const startEdit = (day: DayType, week: WeekType | null) => {
    const target = latest(day, week)?.target ?? latest(day, null)?.target ?? initial;
    setValues(targetValues(target));
    setEditing({ day, week });
    setConfirmMismatch(false);
    setProblem(null);
  };
  const loadPreview = async (
    kind: 'rule' | 'binding',
    body: Record<string, unknown>,
    from: string,
    until: string,
    existingKey?: string,
  ) => {
    const to = addCalendarDays(from, 92) < until ? addCalendarDays(from, 92) : until;
    const result = await api<Schemas['NutritionSchedulePreviewResponse']>(
      kind === 'rule'
        ? '/api/v1/nutrition/targets/schedule/preview'
        : '/api/v1/nutrition/targets/schedule/binding/preview',
      { method: 'POST', body: { ...body, date_from: from, date_to: to } },
    );
    setPreview({
      kind,
      body:
        kind === 'binding'
          ? { ...body, expected_binding_id: result.expected_binding_id, confirm: true }
          : body,
      changes: result.changes,
      key: existingKey ?? keyForChange(),
      from,
      to,
      end: until,
    });
  };
  const prepare = async () => {
    if (checking) return;
    setChecking(true);
    setProblem(null);
    try {
      if (mismatch && !confirmMismatch)
        throw new Error('Подтвердите разницу между калориями и энергией по БЖУ.');
      if (mode === 'override' && !dayType) throw new Error('Выберите тип дня.');
      if (mode === 'override' && scope === 'date') {
        const resolved = await current.refetch();
        if (resolved.isError || !resolved.data || resolved.data.frozen || selectedDate < today)
          throw new Error('Для этой даты нельзя изменить сохранённую цель.');
        const body = {
          ...values,
          effective_from: selectedDate,
          day_type: dayType,
          confirm_energy_mismatch: confirmMismatch,
        };
        setPreview({
          kind: 'date',
          body,
          changes: [
            { date: selectedDate, before: resolved.data.target, after: { id: -1, ...values } },
          ],
          key: keyForChange(),
          from: selectedDate,
          to: selectedDate,
          end: selectedDate,
        });
        return;
      }
      if (!program.data?.revision_number || program.data.schedule_mode !== 'calendar')
        throw new Error('Для назначения по расписанию нужна активная календарная программа.');
      const isTemplate = mode === 'settings';
      if (isTemplate && !editing) return;
      const start = isTemplate ? effective : selectedDate;
      if (start <= today || start > programEnd)
        throw new Error('Выберите будущую дату в пределах программы.');
      const body: Rule = {
        ...values,
        effective_from: start,
        program_id: program.data.program_id,
        revision_number: program.data.revision_number,
        scope: isTemplate ? 'template' : 'future',
        day_type: isTemplate ? editing!.day : (dayType as DayType),
        week_type: isTemplate ? editing!.week : (programDay.data?.week_type ?? null),
        confirm_energy_mismatch: confirmMismatch,
      };
      if (!isTemplate && !programDay.data?.day_type)
        throw new Error('Тип дня по программе для этой даты недоступен.');
      await loadPreview('rule', body, start, programEnd);
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setChecking(false);
    }
  };
  const previewBinding = async () => {
    if (checking) return;
    setChecking(true);
    setProblem(null);
    try {
      if (!program.data?.revision_number) throw new Error('Активная программа недоступна.');
      const body = {
        program_id: program.data.program_id,
        revision_number: program.data.revision_number,
        effective_from: effective,
        expected_binding_id: binding.data?.id ?? null,
      };
      await loadPreview('binding', body, effective, end);
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setChecking(false);
    }
  };
  const inputs = (
    <>
      <div className="nutrition-goal-grid">
        {fields.map(([field, label, min, max]) => (
          <label className="field" key={field}>
            <span>{label}</span>
            <input
              type="number"
              inputMode="numeric"
              min={min}
              max={max}
              step="1"
              required
              value={values[field]}
              onChange={(event) => {
                setValues({ ...values, [field]: Number(event.target.value) });
                setConfirmMismatch(false);
              }}
            />
          </label>
        ))}
      </div>
      {mismatch && (
        <label className="nutrition-goal-option">
          <input
            type="checkbox"
            checked={confirmMismatch}
            onChange={(event) => setConfirmMismatch(event.target.checked)}
          />
          <span>Калории отличаются от энергии по БЖУ. Сохранить введённые значения.</span>
        </label>
      )}
    </>
  );
  const busy = mutation.isPending;

  if (preview)
    return (
      <section className="nutrition-goal-page" aria-labelledby="nutrition-preview-title">
        <header className="nutrition-goal-header">
          <div>
            <span className="eyebrow">Питание · проверка изменений</span>
            <h1 id="nutrition-preview-title" ref={heading} tabIndex={-1}>
              {preview.kind === 'date' ? 'Цель на выбранную дату' : 'Будущие цели'}
            </h1>
            <p className="muted">Проверьте значения до применения.</p>
          </div>
          <Button type="button" variant="secondary" onClick={() => setPreview(null)}>
            Назад
          </Button>
        </header>
        <div className="nutrition-goal-panel">
          <h2>Изменения по датам</h2>
          <p className="muted">
            Период: {preview.from} — {preview.to}. Ручные и сохранённые цели учитываются.
          </p>
          {preview.changes.length ? (
            <div className="nutrition-goal-comparison">
              {preview.changes.map((change) => (
                <div className="nutrition-goal-comparison__row" key={change.date}>
                  <strong>{change.date}</strong>
                  <span>Было: {formatValues(change.before)}</span>
                  <span>Станет: {formatValues(change.after)}</span>
                </div>
              ))}
            </div>
          ) : (
            <p>В этом периоде изменения не найдены.</p>
          )}
          {preview.to < preview.end && (
            <Button
              type="button"
              variant="secondary"
              onClick={() =>
                void loadPreview(
                  preview.kind as 'rule' | 'binding',
                  preview.body,
                  addCalendarDays(preview.to, 1),
                  preview.end,
                  preview.key,
                ).catch((error: Error) => setProblem(error.message))
              }
            >
              Показать следующие даты
            </Button>
          )}
        </div>
        <p className="nutrition-goal-notice">
          <strong>
            <Icon name="warning" size={20} /> Нужно подтверждение
          </strong>
          {preview.kind === 'date'
            ? 'Изменится только выбранная дата.'
            : 'Изменятся только будущие назначения.'}{' '}
          Прошлые и завершённые дни сохранят свои цели.
        </p>
        {problem && <p role="alert">{problem}</p>}
        {mutation.error && <p role="alert">{(mutation.error as Error).message}</p>}
        <div className="nutrition-goal-actions">
          <Button type="button" disabled={busy} onClick={() => mutation.mutate(preview)}>
            {busy
              ? 'Сохраняем…'
              : preview.kind === 'date'
                ? 'Применить к этой дате'
                : 'Применить к будущим датам'}
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={() => setPreview(null)}
          >
            Не применять
          </Button>
        </div>
      </section>
    );

  return (
    <section
      className="nutrition-goal-page"
      id="nutrition-target-settings"
      aria-labelledby="nutrition-goal-title"
    >
      <header className="nutrition-goal-header">
        <div>
          <span className="eyebrow">Питание · цели по дням</span>
          <h1 id="nutrition-goal-title" ref={heading} tabIndex={-1}>
            {mode === 'settings' ? 'Цели по дням' : 'Изменить цель'}
          </h1>
          <p className="muted">
            {mode === 'settings'
              ? 'Назначайте ориентиры для программы и отдельных дат.'
              : 'Выберите, на какие даты повлияет изменение.'}
          </p>
        </div>
        <Button type="button" variant="secondary" onClick={() => onClose()}>
          К дневнику
        </Button>
      </header>
      {program.isLoading || rules.isLoading || binding.isLoading ? (
        <LoadingState label="Загружаем цели…" />
      ) : null}
      {program.error && (
        <ErrorState
          message={(program.error as Error).message}
          retry={() => void program.refetch()}
        />
      )}
      {rules.error && (
        <ErrorState message={(rules.error as Error).message} retry={() => void rules.refetch()} />
      )}
      {binding.error && (
        <ErrorState
          message={(binding.error as Error).message}
          retry={() => void binding.refetch()}
        />
      )}
      {binding.data?.program_changed && (
        <div className="nutrition-goal-notice">
          <strong>
            <Icon name="warning" size={20} /> Программа изменилась
          </strong>
          <p>
            Проверьте будущие цели перед применением новой версии. Текущие назначения сохраняются.
          </p>
          <div className="nutrition-goal-actions">
            <Button
              type="button"
              variant="secondary"
              disabled={readOnly || !program.data || checking}
              onClick={() => void previewBinding()}
            >
              Проверить изменения
            </Button>
            <Button type="button" variant="secondary" onClick={() => onClose()}>
              Оставить как есть
            </Button>
          </div>
        </div>
      )}
      {mode === 'settings' ? (
        <>
          <div className="nutrition-goal-panel">
            <div className="nutrition-goal-row">
              <div>
                <h2>Базовая цель</h2>
                <p className="muted">Используется, когда цель для дня не назначена.</p>
              </div>
              <Button
                type="button"
                variant="secondary"
                disabled={readOnly}
                onClick={() => setEditBase(!editBase)}
              >
                {editBase ? 'Закрыть' : 'Изменить'}
              </Button>
            </div>
            {initial ? (
              <dl className="nutrition-goal-metrics">
                <div>
                  <dt>ккал</dt>
                  <dd>{initial.calories.toLocaleString('ru-RU')}</dd>
                </div>
                <div>
                  <dt>Белки</dt>
                  <dd>{initial.protein_g} г</dd>
                </div>
                <div>
                  <dt>Жиры</dt>
                  <dd>{initial.fat_g} г</dd>
                </div>
                <div>
                  <dt>Углеводы</dt>
                  <dd>{initial.carbs_g} г</dd>
                </div>
              </dl>
            ) : (
              <p>Цель не задана</p>
            )}
            {editBase && (
              <NutritionForm
                embedded
                initial={initial}
                readOnly={readOnly}
                timeZone={timeZone}
                onSaved={onSaved}
              />
            )}
          </div>
          <div className="nutrition-goal-panel">
            <h2>Цели по типу дня</h2>
            <p className="muted">Восстановительный день используется, только если он задан явно.</p>
            {(Object.keys(dayLabels) as DayType[]).map((day) => (
              <div className="nutrition-goal-row nutrition-goal-row--day" key={day}>
                <div>
                  <strong>{dayLabels[day]}</strong>
                  <small className="muted">
                    {day === 'recovery' ? 'По явному назначению' : 'По расписанию'}
                  </small>
                </div>
                <span className="nutrition-goal-values">
                  {formatValues(latest(day, null)?.target)}
                </span>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={
                    readOnly ||
                    !program.data ||
                    program.data.schedule_mode !== 'calendar' ||
                    !rules.isSuccess ||
                    !binding.isSuccess ||
                    Boolean(binding.data?.program_changed)
                  }
                  onClick={() => startEdit(day, null)}
                >
                  Изменить
                </Button>
              </div>
            ))}
          </div>
          <div className="nutrition-goal-panel">
            <h2>Типы недель</h2>
            <p className="muted">Уточнение доступно для типа недели, указанного в программе.</p>
            <label className="field">
              <span>Тип дня</span>
              <select
                value={weekDay}
                onChange={(event) => setWeekDay(event.target.value as DayType)}
              >
                {(Object.keys(dayLabels) as DayType[]).map((day) => (
                  <option key={day} value={day}>
                    {dayLabels[day]}
                  </option>
                ))}
              </select>
            </label>
            <div className="nutrition-goal-detail">
              <strong>Тяжёлая неделя · {dayLabels[weekDay].toLowerCase()}</strong>
              <span className="nutrition-goal-values">
                {formatValues(
                  latest(weekDay, 'heavy')?.target ?? latest(weekDay, null)?.target ?? initial,
                )}
              </span>
              <p className="muted">
                Для других недель без уточнения используется цель соответствующего дня.
              </p>
              <Button
                type="button"
                variant="secondary"
                disabled={
                  readOnly ||
                  !rules.isSuccess ||
                  !binding.isSuccess ||
                  program.data?.schedule_mode !== 'calendar' ||
                  !program.data?.week_types.includes('heavy') ||
                  Boolean(binding.data?.program_changed)
                }
                onClick={() => startEdit(weekDay, 'heavy')}
              >
                Изменить уточнение
              </Button>
            </div>
            {(['light', 'medium'] as WeekType[]).map((week) => (
              <div className="nutrition-goal-row" key={week}>
                <div>
                  <strong>{weekLabels[week]}</strong>
                  <span className="nutrition-goal-values">
                    {latest(weekDay, week)
                      ? formatValues(latest(weekDay, week)?.target)
                      : 'Пока действует цель типа дня'}
                  </span>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={
                    readOnly ||
                    !rules.isSuccess ||
                    !binding.isSuccess ||
                    program.data?.schedule_mode !== 'calendar' ||
                    !program.data?.week_types.includes(week) ||
                    Boolean(binding.data?.program_changed)
                  }
                  onClick={() => startEdit(weekDay, week)}
                >
                  Изменить
                </Button>
              </div>
            ))}
          </div>
          {!program.data && !program.isLoading && (
            <p className="nutrition-goal-notice">
              Для целей по расписанию сначала назначьте календарную программу.
            </p>
          )}
          {program.data?.schedule_mode === 'rotation' && (
            <p className="nutrition-goal-notice">
              Для целей по дням требуется календарное расписание программы.
            </p>
          )}
          {editing && (
            <form
              className="nutrition-goal-panel"
              onSubmit={(event) => {
                event.preventDefault();
                void prepare();
              }}
            >
              <h2>Изменить цель</h2>
              <p className="muted">
                {dayLabels[editing.day]}
                {editing.week ? ` · ${weekLabels[editing.week].toLowerCase()}` : ''}
              </p>
              {inputs}
              <p className="muted">Изменения применяются к будущим датам после подтверждения.</p>
              <div className="nutrition-goal-actions">
                <Button type="submit" disabled={checking}>
                  {checking ? 'Проверяем…' : 'Проверить изменения'}
                </Button>
                <Button type="button" variant="secondary" onClick={() => setEditing(null)}>
                  Отмена
                </Button>
              </div>
            </form>
          )}
        </>
      ) : (
        <form
          className="nutrition-goal-stack"
          onSubmit={(event) => {
            event.preventDefault();
            void prepare();
          }}
        >
          <div className="nutrition-goal-panel">
            <h2>Дата и область</h2>
            <div className="nutrition-goal-grid">
              <label className="field">
                <span>Выбранная дата</span>
                <DateInput
                  min={today}
                  required
                  value={selectedDate}
                  onChange={(event) => {
                    setSelectedDate(event.target.value);
                    setDayType('');
                  }}
                />
              </label>
              <label className="field">
                <span>Тип дня</span>
                <select
                  value={dayType}
                  required
                  onChange={(event) => setDayType(event.target.value as DayType | '')}
                >
                  <option value="">Выберите тип дня</option>
                  {(Object.keys(dayLabels) as DayType[]).map((day) => (
                    <option key={day} value={day}>
                      {dayLabels[day]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <fieldset>
              <legend>Область изменения</legend>
              <label className="nutrition-goal-option" data-yfc-choice="compact">
                <input
                  type="radio"
                  name="nutrition-scope"
                  checked={scope === 'date'}
                  onChange={() => setScope('date')}
                />
                <span>
                  <strong>Только выбранная дата</strong>
                  <small>Другие дни и повторения не изменятся.</small>
                </span>
              </label>
              <label className="nutrition-goal-option" data-yfc-choice="compact">
                <input
                  type="radio"
                  name="nutrition-scope"
                  checked={scope === 'future'}
                  onChange={() => setScope('future')}
                />
                <span>
                  <strong>Будущие такие дни</strong>
                  <small>Повторения выбранного типа в этой программе.</small>
                </span>
              </label>
            </fieldset>
            <p className="muted">
              Тип недели по программе:{' '}
              {programDay.data?.week_type
                ? weekLabels[programDay.data.week_type].toLowerCase()
                : 'не указан'}
              . Прошлые завершённые дни сохранят свои цели.
            </p>
          </div>
          <div className="nutrition-goal-panel">
            <h2>Ориентиры КБЖУ</h2>
            <p className="muted">Сейчас: {formatValues(current.data?.target)}</p>
            {inputs}
            <p className="muted">Ручная цель имеет приоритет над целью по программе.</p>
            {current.error && (
              <ErrorState
                message={(current.error as Error).message}
                retry={() => void current.refetch()}
              />
            )}
            {current.data?.frozen && (
              <p role="status">Завершённый день сохраняет ранее назначенную цель.</p>
            )}
            {scope === 'future' && programDay.error && (
              <ErrorState
                message={(programDay.error as Error).message}
                retry={() => void programDay.refetch()}
              />
            )}
          </div>
          <div className="nutrition-goal-actions">
            <Button
              type="submit"
              disabled={readOnly || checking || !current.isSuccess || Boolean(current.data?.frozen)}
            >
              {checking ? 'Проверяем…' : 'Проверить изменения'}
            </Button>
            <Button type="button" variant="secondary" onClick={() => onClose()}>
              Отмена
            </Button>
          </div>
        </form>
      )}
      {problem && <p role="alert">{problem}</p>}
    </section>
  );
}
