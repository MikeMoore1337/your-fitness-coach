import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';
import { createPortal } from 'react-dom';
import type { Exercise, ProgramTemplateCreate } from '../../shared/api/types';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { DisclosureIcon } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { SearchableExercisePicker } from './SearchableExercisePicker';
import { isPairedWithPrevious, moveItem, removeExercise, toggleSuperset } from './programDraft';
import { simpleTrainingTitle } from './programDefaults';
import './ProgramDayEditor.css';

type Day = ProgramTemplateCreate['days'][number];
type Row = Day['exercises'][number];

function complexPrescription(row: Row, sourceWeek: number): boolean {
  const plans = [
    row.prescription,
    row.weekly_prescriptions?.find((item) => item.week_number === sourceWeek)?.prescription,
  ];
  return (
    Boolean(row.prescription && row.weekly_prescriptions?.some((item) => !item.prescription)) ||
    plans.some((plan) =>
      Boolean(
        plan &&
        ((plan.groups?.length ?? 0) > 0 ||
          plan.segments.some(
            (segment) =>
              segment.role !== 'working' ||
              (segment.load_target?.kind ?? 'user_selected') !== 'user_selected' ||
              (segment.effort_target?.kind ?? 'none') !== 'none',
          )),
      ),
    )
  );
}

function changedRow(row: Row, next: Row, sourceWeek: number): Row {
  const changed =
    row.exercise_id !== next.exercise_id ||
    row.prescribed_sets !== next.prescribed_sets ||
    row.prescribed_reps !== next.prescribed_reps ||
    row.prescribed_duration_minutes !== next.prescribed_duration_minutes ||
    row.rest_seconds !== next.rest_seconds;
  if (!changed) return next;
  const prescription =
    row.prescription && !complexPrescription(row, sourceWeek) ? null : next.prescription;
  return {
    ...next,
    prescription,
    weekly_prescriptions: next.weekly_prescriptions?.map((item) =>
      item.week_number === sourceWeek
        ? {
            ...item,
            exercise_id: next.exercise_id,
            prescribed_sets: next.prescribed_sets ?? 1,
            prescribed_reps: next.prescribed_reps ?? '',
            prescribed_duration_minutes: next.prescribed_duration_minutes,
            rest_seconds: next.rest_seconds,
            prescription,
          }
        : item,
    ),
  };
}

function newExercise(restSeconds: number): Row {
  return {
    exercise_id: 0,
    prescribed_sets: 3,
    prescribed_reps: '8-12',
    prescribed_duration_minutes: null,
    rest_seconds: restSeconds,
    notes: '',
  };
}

type Props = {
  days: Day[];
  setDays: Dispatch<SetStateAction<Day[]>>;
  updateDay: (index: number, next: Day | ((current: Day) => Day)) => void;
  exercises: Exercise[];
  equipmentFilterEnabled: boolean;
  defaultRestSeconds: number;
  onOpenGuide: (exercise: Exercise) => void;
  sourceWeek?: number;
};

export function ProgramDayEditor({
  days,
  setDays,
  updateDay,
  exercises,
  equipmentFilterEnabled,
  defaultRestSeconds,
  onOpenGuide,
  sourceWeek = 1,
}: Props) {
  const { confirm } = useFeedback();
  const [selectedDay, setSelectedDay] = useState(0);
  const [selectedExercise, setSelectedExercise] = useState(0);
  const [allDaysOpen, setAllDaysOpen] = useState(false);
  const [allDaysReordering, setAllDaysReordering] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [reordering, setReordering] = useState(false);
  const [mobileView, setMobileView] = useState(
    () =>
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(max-width: 1099px)').matches,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia('(max-width: 1099px)');
    const update = () => {
      setMobileView(media.matches);
      if (!media.matches) setDetailOpen(false);
    };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  const [portalRoot, setPortalRoot] = useState<HTMLElement | null>(null);
  const captureRoot = useCallback((node: HTMLElement | null) => {
    if (node) setPortalRoot(node.closest<HTMLElement>('.modal') ?? document.body);
  }, []);
  const carouselRef = useRef<HTMLDivElement>(null);
  const dayTitleRef = useRef<HTMLInputElement>(null);
  const scrollTimerRef = useRef<number | null>(null);
  const allDaysReturnFocusRef = useRef<HTMLButtonElement | null>(null);
  const allDaysDialogRef = useRef<HTMLDivElement>(null);
  const detailDialogRef = useRef<HTMLDivElement>(null);
  const exerciseTriggerRef = useRef<HTMLButtonElement | null>(null);
  const dayIndex = Math.min(selectedDay, Math.max(0, days.length - 1));
  const day = days[dayIndex];
  const exerciseIndex = Math.min(selectedExercise, Math.max(0, (day?.exercises.length ?? 1) - 1));
  const activeRow = day?.exercises[exerciseIndex];
  const available = useCallback(
    (exerciseId: number) => exercises.find((exercise) => exercise.id === exerciseId),
    [exercises],
  );

  const selectDay = useCallback(
    (index: number) => {
      const next = Math.max(0, Math.min(index, days.length - 1));
      setSelectedDay(next);
      setSelectedExercise(0);
      setDetailOpen(false);
      setAllDaysOpen(false);
      const carousel = carouselRef.current;
      if (carousel) carousel.scrollLeft = carousel.clientWidth * next;
    },
    [days.length],
  );

  useEffect(() => {
    const carousel = carouselRef.current;
    if (!carousel) return;
    const align = () => {
      if (mobileView) carousel.scrollLeft = carousel.clientWidth * dayIndex;
    };
    const frame = window.requestAnimationFrame(align);
    const resize = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(align) : null;
    resize?.observe(carousel);
    return () => {
      window.cancelAnimationFrame(frame);
      resize?.disconnect();
    };
  }, [dayIndex, days.length, mobileView]);

  useEffect(() => {
    return () => {
      if (scrollTimerRef.current !== null) window.clearTimeout(scrollTimerRef.current);
    };
  }, []);

  const handleCarouselScroll = () => {
    const carousel = carouselRef.current;
    if (!carousel || carousel.clientWidth === 0) return;
    if (scrollTimerRef.current !== null) window.clearTimeout(scrollTimerRef.current);
    scrollTimerRef.current = window.setTimeout(() => {
      const next = Math.max(
        0,
        Math.min(days.length - 1, Math.round(carousel.scrollLeft / carousel.clientWidth)),
      );
      if (next !== dayIndex) {
        setSelectedDay(next);
        setSelectedExercise(0);
        setDetailOpen(false);
      }
    }, 120);
  };

  const openAllDays = (trigger: HTMLButtonElement, reordering = false) => {
    allDaysReturnFocusRef.current = trigger;
    if (scrollTimerRef.current !== null) window.clearTimeout(scrollTimerRef.current);
    setAllDaysReordering(reordering);
    setAllDaysOpen(true);
  };

  const closeAllDays = useCallback(() => {
    setAllDaysOpen(false);
    window.requestAnimationFrame(() => allDaysReturnFocusRef.current?.focus());
  }, []);
  const closeDetail = useCallback(() => {
    setDetailOpen(false);
    window.requestAnimationFrame(() => {
      const fallback = document.querySelector<HTMLButtonElement>(
        '.copy-editor__exercise[aria-pressed="true"]',
      );
      const previous = exerciseTriggerRef.current;
      if (previous?.isConnected) previous.focus();
      else fallback?.focus();
    });
  }, []);

  useEffect(() => {
    if (!allDaysOpen && !(detailOpen && mobileView)) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const dialog = allDaysOpen ? allDaysDialogRef.current : detailDialogRef.current;
    const focusables = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]',
        ) ?? [],
      );
    focusables()[0]?.focus({ preventScroll: true });
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (allDaysOpen) closeAllDays();
        else closeDetail();
      }
      if (event.key !== 'Tab') return;
      const items = focusables();
      if (!items.length) return;
      const first = items[0]!;
      const last = items[items.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [allDaysOpen, detailOpen, closeAllDays, closeDetail, mobileView]);

  if (!day) return <p className="muted">Добавьте первый тренировочный день.</p>;

  const changeRow = (index: number, change: (row: Row) => Row) => {
    updateDay(dayIndex, (current) => ({
      ...current,
      exercises: current.exercises.map((row, rowIndex) =>
        rowIndex === index ? changedRow(row, change(row), sourceWeek) : row,
      ),
    }));
  };

  const selectExerciseId = (index: number, exerciseId: number) => {
    const selected = available(exerciseId);
    changeRow(index, (row) => {
      if (selected?.metric_type === 'cardio') {
        return {
          ...row,
          exercise_id: exerciseId,
          prescribed_sets: null,
          prescribed_reps: null,
          prescribed_duration_minutes: row.prescribed_duration_minutes ?? 30,
          superset_group: null,
          superset_order: null,
        };
      }
      return {
        ...row,
        exercise_id: exerciseId,
        prescribed_sets: row.prescribed_sets ?? 3,
        prescribed_reps: row.prescribed_reps || '8-12',
        prescribed_duration_minutes: null,
      };
    });
  };

  const moveDay = (from: number, direction: number) => {
    const to = from + direction;
    if (from < 0 || from >= days.length || to < 0 || to >= days.length) return;
    if (scrollTimerRef.current !== null) window.clearTimeout(scrollTimerRef.current);
    setDays((current) => moveItem(current, from, to));
    setSelectedDay((selected) => {
      if (selected === from) return to;
      if (from < selected && to >= selected) return selected - 1;
      if (from > selected && to <= selected) return selected + 1;
      return selected;
    });
  };

  const deleteDay = async () => {
    if (
      days.length <= 1 ||
      !(await confirm({
        title: 'Удалить тренировочный день?',
        message: 'День и все его упражнения будут удалены из черновика программы.',
        confirmText: 'Удалить день',
      }))
    )
      return;
    setDays((current) => current.filter((_, index) => index !== dayIndex));
    selectDay(Math.max(0, dayIndex - 1));
  };

  const deleteRow = async (index: number) => {
    if (
      !(await confirm({
        title: 'Удалить упражнение?',
        message:
          'Упражнение будет удалено из этого дня. Изменение вступит в силу после сохранения программы.',
        confirmText: 'Удалить упражнение',
      }))
    )
      return;
    updateDay(dayIndex, (current) => {
      const next = removeExercise(current, index);
      return next.exercises.length
        ? next
        : { ...next, exercises: [newExercise(defaultRestSeconds)] };
    });
    setSelectedExercise(Math.max(0, index - 1));
    setDetailOpen(false);
  };

  const renderDetails = (mobile: boolean) => {
    if (!activeRow) {
      return <p className="copy-editor__muted">Выберите упражнение в списке.</p>;
    }
    const selected = available(activeRow.exercise_id);
    const cardio = selected?.metric_type === 'cardio';
    const alternatives = (selected?.alternatives ?? [])
      .map((alternative) => available(alternative.id))
      .filter((alternative): alternative is Exercise => Boolean(alternative));
    return (
      <div className="copy-editor__detail-fields">
        <div className="copy-editor__detail-title">
          <div>
            <span className="eyebrow">
              День {dayIndex + 1} · упражнение {exerciseIndex + 1}
            </span>
            <h3>{selected?.title ?? 'Выберите упражнение'}</h3>
          </div>
          {mobile && (
            <button
              type="button"
              className="secondary copy-editor__icon"
              onClick={closeDetail}
              aria-label="Закрыть параметры"
            >
              <Icon name="close" size={20} />
            </button>
          )}
        </div>
        {complexPrescription(activeRow, sourceWeek) && (
          <p className="muted">
            Сложное предписание сохранится в исходном виде. Его параметры нельзя изменить в этом
            редакторе.
          </p>
        )}
        <fieldset
          className="copy-editor__prescription-fields"
          disabled={complexPrescription(activeRow, sourceWeek)}
        >
          <div className="field">
            <span>Упражнение</span>
            <SearchableExercisePicker
              mobileSheet
              equipmentFilterEnabled={equipmentFilterEnabled}
              exercises={exercises}
              value={activeRow.exercise_id}
              clearValue={0}
              onOpenGuide={(exercise) => {
                const known = available(exercise.id);
                if (known) onOpenGuide(known);
              }}
              onChange={(id) => selectExerciseId(exerciseIndex, typeof id === 'number' ? id : 0)}
            />
          </div>
          {selected && (
            <button type="button" className="text-button" onClick={() => onOpenGuide(selected)}>
              {selected.has_guide ? 'Техника и детали' : 'Подробнее об упражнении'}
            </button>
          )}
          {cardio ? (
            <label className="field">
              <span>Плановая длительность, мин</span>
              <input
                type="number"
                inputMode="numeric"
                min="1"
                max="600"
                required
                value={activeRow.prescribed_duration_minutes ?? ''}
                onChange={(event) =>
                  changeRow(exerciseIndex, (row) => ({
                    ...row,
                    prescribed_duration_minutes: Number(event.target.value),
                  }))
                }
              />
            </label>
          ) : (
            <>
              <div className="copy-editor__metrics">
                <label className="field">
                  <span>Рабочие подходы</span>
                  <input
                    type="number"
                    inputMode="numeric"
                    min="1"
                    max="10"
                    required
                    value={activeRow.prescribed_sets ?? ''}
                    onChange={(event) =>
                      changeRow(exerciseIndex, (row) => ({
                        ...row,
                        prescribed_sets: Number(event.target.value),
                      }))
                    }
                  />
                </label>
                <label className="field">
                  <span>Отдых, сек</span>
                  <input
                    type="number"
                    inputMode="numeric"
                    min="15"
                    max="600"
                    required
                    value={activeRow.rest_seconds ?? ''}
                    onChange={(event) =>
                      changeRow(exerciseIndex, (row) => ({
                        ...row,
                        rest_seconds: Number(event.target.value),
                      }))
                    }
                  />
                </label>
              </div>
              <label className="field">
                <span>Повторы, включая последовательность по подходам</span>
                <input
                  type="text"
                  maxLength={32}
                  required
                  value={activeRow.prescribed_reps ?? ''}
                  placeholder="Например: 12/10/8/15"
                  onChange={(event) =>
                    changeRow(exerciseIndex, (row) => ({
                      ...row,
                      prescribed_reps: event.target.value,
                    }))
                  }
                />
              </label>
            </>
          )}
        </fieldset>
        <details className="compact-disclosure copy-editor__advanced">
          <summary className="yfc-disclosure-summary">
            <span>
              <strong>Заметка и дополнительные параметры</strong>
              <small>Суперсеты, замены, комментарий</small>
            </span>
            <DisclosureIcon />
          </summary>
          <div className="copy-editor__advanced-body">
            <label className="field">
              <span>Заметка к упражнению</span>
              <input
                maxLength={2000}
                disabled={sourceWeek !== 1}
                value={activeRow.notes ?? ''}
                placeholder="Например: выполнять медленно, без рывков"
                onChange={(event) =>
                  changeRow(exerciseIndex, (row) => ({
                    ...row,
                    notes: event.target.value,
                  }))
                }
              />
            </label>
            {exerciseIndex > 0 && !cardio && (
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={isPairedWithPrevious(day, exerciseIndex)}
                  disabled={sourceWeek !== 1 || complexPrescription(activeRow, sourceWeek)}
                  onChange={(event) =>
                    updateDay(dayIndex, (current) =>
                      toggleSuperset(current, exerciseIndex, event.target.checked),
                    )
                  }
                />
                <span>Суперсет с предыдущим упражнением</span>
              </label>
            )}
            <div className="stack">
              <strong>Проверенные замены</strong>
              {alternatives.length ? (
                alternatives.map((alternative) => (
                  <button
                    key={alternative.id}
                    type="button"
                    className="text-button"
                    disabled={complexPrescription(activeRow, sourceWeek)}
                    onClick={() => selectExerciseId(exerciseIndex, alternative.id)}
                  >
                    Заменить на «{alternative.title}»
                  </button>
                ))
              ) : (
                <small className="muted">Проверенных замен пока нет.</small>
              )}
            </div>
            {!cardio && (
              <small className="muted">
                Разминочные и дроп-сеты отмечаются во время тренировки.
              </small>
            )}
          </div>
        </details>
        {reordering && (
          <div className="copy-editor__order-actions" aria-label="Порядок упражнения">
            <button
              type="button"
              className="secondary"
              disabled={sourceWeek !== 1 || exerciseIndex === 0}
              onClick={() => {
                updateDay(dayIndex, (current) => ({
                  ...current,
                  exercises: moveItem(current.exercises, exerciseIndex, exerciseIndex - 1),
                }));
                setSelectedExercise(exerciseIndex - 1);
              }}
            >
              Выше
            </button>
            <button
              type="button"
              className="secondary"
              disabled={sourceWeek !== 1 || exerciseIndex === day.exercises.length - 1}
              onClick={() => {
                updateDay(dayIndex, (current) => ({
                  ...current,
                  exercises: moveItem(current.exercises, exerciseIndex, exerciseIndex + 1),
                }));
                setSelectedExercise(exerciseIndex + 1);
              }}
            >
              Ниже
            </button>
          </div>
        )}
        <button
          type="button"
          className="text-button copy-editor__danger"
          disabled={sourceWeek !== 1}
          onClick={() => void deleteRow(exerciseIndex)}
        >
          <Icon name="trash" size={16} /> Удалить упражнение
        </button>
      </div>
    );
  };

  const dayCount = days.length;
  const allDayButtons = days.map((item, index) =>
    allDaysReordering ? (
      <div key={index} className="copy-editor__day-sort-row">
        <div
          className="copy-editor__day-sort-name"
          aria-current={index === dayIndex ? 'true' : undefined}
        >
          <strong>
            День {index + 1} · {item.title || simpleTrainingTitle(index + 1)}
          </strong>
          <small>
            {item.exercises.filter((row) => row.exercise_id > 0).length} упр.
            {index === dayIndex ? ' · выбран' : ''}
          </small>
        </div>
        <div
          className="copy-editor__sort-actions"
          role="group"
          aria-label={`Порядок дня ${index + 1}`}
        >
          <button
            type="button"
            className="secondary"
            disabled={sourceWeek !== 1 || index === 0}
            onClick={() => moveDay(index, -1)}
            aria-label={`Переместить день ${index + 1} раньше`}
          >
            Раньше
          </button>
          <button
            type="button"
            className="secondary"
            disabled={sourceWeek !== 1 || index === dayCount - 1}
            onClick={() => moveDay(index, 1)}
            aria-label={`Переместить день ${index + 1} позже`}
          >
            Позже
          </button>
        </div>
      </div>
    ) : (
      <button
        key={index}
        type="button"
        className="copy-editor__day-choice"
        data-yfc-choice="compact"
        aria-pressed={index === dayIndex}
        onClick={() => {
          selectDay(index);
          window.requestAnimationFrame(() => allDaysReturnFocusRef.current?.focus());
        }}
      >
        <strong>День {index + 1}</strong>
        <span>{item.title || simpleTrainingTitle(index + 1)}</span>
        <small>{item.exercises.filter((row) => row.exercise_id > 0).length} упр.</small>
      </button>
    ),
  );

  return (
    <>
      <section ref={captureRoot} className="copy-editor" aria-label="Дни и упражнения программы">
        <aside className="copy-editor__rail" aria-label="Список тренировочных дней">
          <div className="copy-editor__section-head">
            <h3>Дни программы</h3>
            <span className="muted">{dayCount} из 8</span>
          </div>
          <div className="copy-editor__rail-days" role="tablist" aria-label="Тренировочные дни">
            {days.map((item, index) => (
              <button
                key={index}
                type="button"
                role="tab"
                data-yfc-choice="compact"
                aria-selected={index === dayIndex}
                className="copy-editor__rail-button"
                onClick={() => selectDay(index)}
              >
                <strong>День {index + 1}</strong>
                <span>{item.title || simpleTrainingTitle(index + 1)}</span>
                <small>{item.exercises.filter((row) => row.exercise_id > 0).length} упр.</small>
              </button>
            ))}
          </div>
          {dayCount > 1 && (
            <button
              type="button"
              className="secondary copy-editor__manage-days"
              onClick={(event) => openAllDays(event.currentTarget, true)}
            >
              Изменить порядок дней
            </button>
          )}
          <p className="muted copy-editor__limit">В одном цикле максимум 8 тренировочных дней.</p>
        </aside>

        <div className="copy-editor__content">
          <div className="copy-editor__mobile-days">
            <div className="copy-editor__section-head">
              <h3>Дни</h3>
              <button
                type="button"
                className="secondary"
                onClick={(event) => openAllDays(event.currentTarget)}
              >
                Все дни
              </button>
            </div>
            <div
              className="copy-editor__carousel"
              ref={carouselRef}
              onScroll={handleCarouselScroll}
              role="tablist"
              aria-label="Дни программы"
              onKeyDown={(event) => {
                if (event.key === 'ArrowRight') {
                  event.preventDefault();
                  selectDay(dayIndex + 1);
                }
                if (event.key === 'ArrowLeft') {
                  event.preventDefault();
                  selectDay(dayIndex - 1);
                }
                if (event.key === 'Home') {
                  event.preventDefault();
                  selectDay(0);
                }
                if (event.key === 'End') {
                  event.preventDefault();
                  selectDay(dayCount - 1);
                }
              }}
            >
              {days.map((item, index) => (
                <button
                  key={index}
                  type="button"
                  role="tab"
                  className="copy-editor__slide"
                  tabIndex={index === dayIndex ? 0 : -1}
                  aria-selected={index === dayIndex}
                  aria-label={'День ' + (index + 1) + ' из ' + dayCount + ': ' + item.title}
                  onClick={() => selectDay(index)}
                >
                  <span className="eyebrow">
                    День {index + 1} из {dayCount}
                  </span>
                  <strong>{item.title || simpleTrainingTitle(index + 1)}</strong>
                  <small>
                    {item.exercises.filter((row) => row.exercise_id > 0).length} упр. ·
                    тренировочный день
                  </small>
                </button>
              ))}
            </div>
            <div className="copy-editor__carousel-actions">
              <button
                type="button"
                className="secondary copy-editor__icon"
                disabled={dayIndex === 0}
                onClick={() => selectDay(dayIndex - 1)}
                aria-label="Предыдущий день"
              >
                <Icon name="chevron-left" size={20} />
              </button>
              <span aria-live="polite" className="copy-editor__counter">
                День {dayIndex + 1} из {dayCount}
              </span>
              <button
                type="button"
                className="secondary copy-editor__icon"
                disabled={dayIndex === dayCount - 1}
                onClick={() => selectDay(dayIndex + 1)}
                aria-label="Следующий день"
              >
                <Icon name="chevron-right" size={20} />
              </button>
            </div>
          </div>

          <div className="copy-editor__current-day">
            <label className="field">
              <span>Название дня</span>
              <input
                ref={dayTitleRef}
                maxLength={128}
                disabled={sourceWeek !== 1}
                required
                value={day.title}
                onChange={(event) =>
                  updateDay(dayIndex, (current) => ({
                    ...current,
                    title: event.target.value,
                  }))
                }
              />
            </label>
            <details className="copy-editor__day-actions">
              <summary className="yfc-disclosure-summary">
                <span>Действия с днём</span>
                <DisclosureIcon />
              </summary>
              <div className="copy-editor__day-menu">
                <button
                  type="button"
                  className="secondary"
                  disabled={sourceWeek !== 1}
                  onClick={() => {
                    dayTitleRef.current?.focus();
                    dayTitleRef.current?.select();
                  }}
                >
                  Изменить название дня
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={sourceWeek !== 1 || dayCount >= 8}
                  onClick={() => {
                    if (days.length >= 8) return;
                    const copy = structuredClone(day);
                    copy.title = `${day.title.slice(0, 120)} (копия)`;
                    setDays((current) => (current.length >= 8 ? current : [...current, copy]));
                    setSelectedDay(days.length);
                    setSelectedExercise(0);
                    setDetailOpen(false);
                  }}
                >
                  Дублировать день
                </button>
                {dayCount > 1 && (
                  <button
                    type="button"
                    className="text-button copy-editor__danger"
                    disabled={sourceWeek !== 1}
                    onClick={() => void deleteDay()}
                  >
                    Удалить день
                  </button>
                )}
              </div>
            </details>
          </div>

          <div className="copy-editor__section-head copy-editor__exercise-heading">
            <div>
              <h3>Упражнения</h3>
              <span className="muted">
                {day.exercises.filter((row) => row.exercise_id > 0).length} упр.
              </span>
            </div>
            <button
              type="button"
              className="secondary"
              aria-pressed={reordering}
              onClick={() => setReordering((value) => !value)}
            >
              {reordering ? 'Готово' : 'Изменить порядок'}
            </button>
          </div>
          <div className="copy-editor__exercise-list">
            {day.exercises.map((item, index) => {
              const details = available(item.exercise_id);
              const cardio = details?.metric_type === 'cardio';
              return (
                <button
                  key={index}
                  type="button"
                  className="copy-editor__exercise"
                  aria-pressed={index === exerciseIndex}
                  onClick={(event) => {
                    exerciseTriggerRef.current = event.currentTarget;
                    setSelectedExercise(index);
                    setDetailOpen(mobileView);
                  }}
                >
                  <span className="copy-editor__ordinal">{index + 1}</span>
                  <span className="copy-editor__exercise-info">
                    <strong>{details?.title ?? 'Выберите упражнение'}</strong>
                    <span>
                      {!item.exercise_id
                        ? 'Нажмите, чтобы выбрать'
                        : cardio
                          ? String(item.prescribed_duration_minutes ?? 0) + ' мин'
                          : String(item.prescribed_sets ?? 0) +
                            ' × ' +
                            String(item.prescribed_reps ?? '') +
                            ' · отдых ' +
                            String(item.rest_seconds ?? 0) +
                            ' сек'}
                    </span>
                    {(item.notes || isPairedWithPrevious(day, index)) && (
                      <small>
                        {item.notes ? 'Заметка ' : ''}
                        {isPairedWithPrevious(day, index) ? '· Суперсет' : ''}
                      </small>
                    )}
                  </span>
                  <Icon name="chevron-right" size={20} />
                </button>
              );
            })}
          </div>
          {day.exercises.length < 20 ? (
            <button
              type="button"
              className="secondary copy-editor__add"
              disabled={sourceWeek !== 1}
              onClick={() => {
                updateDay(dayIndex, (current) => ({
                  ...current,
                  exercises: [...current.exercises, newExercise(defaultRestSeconds)],
                }));
                setSelectedExercise(day.exercises.length);
                exerciseTriggerRef.current = null;
                setDetailOpen(mobileView);
              }}
            >
              <Icon name="plus" size={20} /> Добавить упражнение
            </button>
          ) : (
            <p className="muted">В одной тренировке максимум 20 упражнений.</p>
          )}

          <div className="copy-editor__add-day">
            {dayCount < 8 ? (
              <button
                type="button"
                className="secondary copy-editor__add"
                disabled={sourceWeek !== 1}
                onClick={() => {
                  setDays((current) => [
                    ...current,
                    {
                      title: simpleTrainingTitle(current.length + 1),
                      exercises: [newExercise(defaultRestSeconds)],
                    },
                  ]);
                  setSelectedDay(dayCount);
                  setSelectedExercise(0);
                }}
              >
                <Icon name="plus" size={20} /> Добавить день
              </button>
            ) : (
              <span className="muted">В одном цикле максимум 8 тренировочных дней.</span>
            )}
          </div>
        </div>

        <aside className="copy-editor__detail-rail" aria-label="Параметры упражнения">
          {!mobileView && renderDetails(false)}
        </aside>
      </section>

      {allDaysOpen &&
        portalRoot &&
        createPortal(
          <div
            className="copy-editor__overlay"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) closeAllDays();
            }}
          >
            <div
              className="copy-editor__sheet"
              role="dialog"
              aria-modal="true"
              aria-label="Все дни программы"
              ref={allDaysDialogRef}
            >
              <div className="copy-editor__sheet-header">
                <h3>Все дни программы</h3>
                <button
                  type="button"
                  className="secondary copy-editor__icon"
                  onClick={closeAllDays}
                  aria-label="Закрыть список дней"
                >
                  <Icon name="close" size={20} />
                </button>
              </div>
              {dayCount > 1 && (
                <div className="copy-editor__sheet-toolbar">
                  {allDaysReordering && (
                    <p className="muted">
                      Меняйте порядок кнопками «Раньше» и «Позже». Изменения сохранятся вместе с
                      программой.
                    </p>
                  )}
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setAllDaysReordering((current) => !current)}
                  >
                    {allDaysReordering ? 'Готово' : 'Изменить порядок'}
                  </button>
                </div>
              )}
              <div
                className={
                  allDaysReordering ? 'copy-editor__day-sort-list' : 'copy-editor__day-grid'
                }
              >
                {allDayButtons}
              </div>
            </div>
          </div>,
          portalRoot,
        )}
      {detailOpen &&
        mobileView &&
        portalRoot &&
        createPortal(
          <div
            className="copy-editor__overlay copy-editor__detail-overlay"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) closeDetail();
            }}
          >
            <div
              className="copy-editor__sheet copy-editor__detail-sheet"
              role="dialog"
              aria-modal="true"
              aria-label="Параметры упражнения"
              ref={detailDialogRef}
            >
              {renderDetails(true)}
            </div>
          </div>,
          portalRoot,
        )}
    </>
  );
}
