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
  defaultRestSeconds: number;
  onOpenGuide: (exercise: Exercise) => void;
};

export function ProgramDayEditor({
  days,
  setDays,
  updateDay,
  exercises,
  defaultRestSeconds,
  onOpenGuide,
}: Props) {
  const { confirm } = useFeedback();
  const [selectedDay, setSelectedDay] = useState(0);
  const [selectedExercise, setSelectedExercise] = useState(0);
  const [allDaysOpen, setAllDaysOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [reordering, setReordering] = useState(false);
  const [mobileView, setMobileView] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function' &&
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
  const carouselRef = useRef<HTMLDivElement>(null);
  const scrollTimerRef = useRef<number | null>(null);
  const allDaysTriggerRef = useRef<HTMLButtonElement>(null);
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
    const frame = window.requestAnimationFrame(() => {
      carousel.scrollLeft = carousel.clientWidth * dayIndex;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [dayIndex, days.length]);

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

  const closeAllDays = useCallback(() => {
    setAllDaysOpen(false);
    window.requestAnimationFrame(() => allDaysTriggerRef.current?.focus());
  }, []);
  const closeDetail = useCallback(() => {
    setDetailOpen(false);
    window.requestAnimationFrame(() => {
      const fallback = document.querySelector<HTMLButtonElement>('.copy-editor__exercise[aria-pressed="true"]');
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
        rowIndex === index ? change(row) : row,
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

  const moveDay = (direction: number) => {
    const next = dayIndex + direction;
    if (next < 0 || next >= days.length) return;
    setDays((current) => moveItem(current, dayIndex, next));
    selectDay(next);
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
        message: 'Упражнение будет удалено из этого дня. Изменение вступит в силу после сохранения программы.',
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
            <span className="eyebrow">День {dayIndex + 1} · упражнение {exerciseIndex + 1}</span>
            <h3>{selected?.title ?? 'Выберите упражнение'}</h3>
          </div>
          {mobile && (
            <button type="button" className="secondary copy-editor__icon" onClick={closeDetail} aria-label="Закрыть параметры">
              <Icon name="close" size={20} />
            </button>
          )}
        </div>
        <div className="field">
          <span>Упражнение</span>
          <SearchableExercisePicker
            mobileSheet
            exercises={exercises}
            value={activeRow.exercise_id}
            clearValue={0}
            onOpenGuide={onOpenGuide}
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
            <input type="number" inputMode="numeric" min="1" max="600" required
              value={activeRow.prescribed_duration_minutes ?? ''}
              onChange={(event) => changeRow(exerciseIndex, (row) => ({
                ...row, prescribed_duration_minutes: Number(event.target.value),
              }))}
            />
          </label>
        ) : (
          <>
            <div className="copy-editor__metrics">
              <label className="field">
                <span>Рабочие подходы</span>
                <input type="number" inputMode="numeric" min="1" max="10" required
                  value={activeRow.prescribed_sets ?? ''}
                  onChange={(event) => changeRow(exerciseIndex, (row) => ({
                    ...row, prescribed_sets: Number(event.target.value),
                  }))}
                />
              </label>
              <label className="field">
                <span>Отдых, сек</span>
                <input type="number" inputMode="numeric" min="15" max="600" required
                  value={activeRow.rest_seconds ?? ''}
                  onChange={(event) => changeRow(exerciseIndex, (row) => ({
                    ...row, rest_seconds: Number(event.target.value),
                  }))}
                />
              </label>
            </div>
            <label className="field">
              <span>Повторы, включая последовательность по подходам</span>
              <input type="text" maxLength={32} required value={activeRow.prescribed_reps ?? ''}
                placeholder="Например: 12/10/8/15"
                onChange={(event) => changeRow(exerciseIndex, (row) => ({
                  ...row, prescribed_reps: event.target.value,
                }))}
              />
            </label>
          </>
        )}
        <details className="compact-disclosure copy-editor__advanced">
          <summary className="yfc-disclosure-summary">
            <span><strong>Заметка и дополнительные параметры</strong><small>Суперсеты, замены, комментарий</small></span>
            <DisclosureIcon />
          </summary>
          <div className="copy-editor__advanced-body">
            <label className="field">
              <span>Заметка к упражнению</span>
              <input maxLength={2000} value={activeRow.notes ?? ''}
                placeholder="Например: выполнять медленно, без рывков"
                onChange={(event) => changeRow(exerciseIndex, (row) => ({
                  ...row, notes: event.target.value,
                }))}
              />
            </label>
            {exerciseIndex > 0 && !cardio && (
              <label className="checkbox-row">
                <input type="checkbox" checked={isPairedWithPrevious(day, exerciseIndex)}
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
              {alternatives.length ? alternatives.map((alternative) => (
                <button key={alternative.id} type="button" className="text-button"
                  onClick={() => selectExerciseId(exerciseIndex, alternative.id)}>
                  Заменить на «{alternative.title}»
                </button>
              )) : <small className="muted">Проверенных замен пока нет.</small>}
            </div>
            {!cardio && <small className="muted">Разминочные и дроп-сеты отмечаются во время тренировки.</small>}
          </div>
        </details>
        {reordering && (
          <div className="copy-editor__order-actions" aria-label="Порядок упражнения">
            <button type="button" className="secondary" disabled={exerciseIndex === 0}
              onClick={() => {
                updateDay(dayIndex, (current) => ({
                  ...current, exercises: moveItem(current.exercises, exerciseIndex, exerciseIndex - 1),
                }));
                setSelectedExercise(exerciseIndex - 1);
              }}>
              <Icon name="move-up" size={18} /> Выше
            </button>
            <button type="button" className="secondary" disabled={exerciseIndex === day.exercises.length - 1}
              onClick={() => {
                updateDay(dayIndex, (current) => ({
                  ...current, exercises: moveItem(current.exercises, exerciseIndex, exerciseIndex + 1),
                }));
                setSelectedExercise(exerciseIndex + 1);
              }}>
              <Icon name="move-down" size={18} /> Ниже
            </button>
          </div>
        )}
        <button type="button" className="text-button copy-editor__danger" onClick={() => void deleteRow(exerciseIndex)}>
          <Icon name="trash" size={16} /> Удалить упражнение
        </button>
      </div>
    );
  };

  const dayCount = days.length;
  const allDayButtons = days.map((item, index) => (
    <button key={index} type="button"
      className="copy-editor__day-choice" data-yfc-choice="compact"
      aria-pressed={index === dayIndex}
      onClick={() => {
        selectDay(index);
        window.requestAnimationFrame(() => allDaysTriggerRef.current?.focus());
      }}>
      <strong>День {index + 1}</strong>
      <span>{item.title || simpleTrainingTitle(index + 1)}</span>
      <small>{item.exercises.length} упр.</small>
    </button>
  ));

  return (
    <>
      <section className="copy-editor" aria-label="Дни и упражнения программы">
        <aside className="copy-editor__rail" aria-label="Список тренировочных дней">
          <div className="copy-editor__section-head">
            <h3>Дни программы</h3><span className="muted">{dayCount} из 8</span>
          </div>
          <div className="copy-editor__rail-days" role="tablist" aria-label="Тренировочные дни">
            {days.map((item, index) => (
              <button key={index} type="button" role="tab"
                data-yfc-choice="compact" aria-selected={index === dayIndex}
                className="copy-editor__rail-button"
                onClick={() => selectDay(index)}>
                <strong>День {index + 1}</strong>
                <span>{item.title || simpleTrainingTitle(index + 1)}</span>
                <small>{item.exercises.length} упр.</small>
              </button>
            ))}
          </div>
          <p className="muted copy-editor__limit">В одном цикле максимум 8 тренировочных дней.</p>
        </aside>

        <div className="copy-editor__content">
          <div className="copy-editor__mobile-days">
            <div className="copy-editor__section-head">
              <h3>Выбор дня</h3>
              <button type="button" className="secondary" ref={allDaysTriggerRef}
                onClick={() => setAllDaysOpen(true)}>
                Все дни
              </button>
            </div>
            <div className="copy-editor__carousel" ref={carouselRef} onScroll={handleCarouselScroll}
              role="tablist" aria-label="Дни программы" onKeyDown={(event) => {
                if (event.key === 'ArrowRight') { event.preventDefault(); selectDay(dayIndex + 1); }
                if (event.key === 'ArrowLeft') { event.preventDefault(); selectDay(dayIndex - 1); }
                if (event.key === 'Home') { event.preventDefault(); selectDay(0); }
                if (event.key === 'End') { event.preventDefault(); selectDay(dayCount - 1); }
              }}>
              {days.map((item, index) => (
                <button key={index} type="button" role="tab"
                  className="copy-editor__slide" tabIndex={index === dayIndex ? 0 : -1}
                  aria-selected={index === dayIndex}
                  aria-label={'День ' + (index + 1) + ' из ' + dayCount + ': ' + item.title}
                  onClick={() => selectDay(index)}>
                  <span className="eyebrow">День {index + 1} из {dayCount}</span>
                  <strong>{item.title || simpleTrainingTitle(index + 1)}</strong>
                  <small>{item.exercises.length} упр. · тренировочный день</small>
                </button>
              ))}
            </div>
            <div className="copy-editor__carousel-actions">
              <button type="button" className="secondary copy-editor__icon" disabled={dayIndex === 0}
                onClick={() => selectDay(dayIndex - 1)} aria-label="Предыдущий день">
                <Icon name="chevron-left" size={20} />
              </button>
              <span aria-live="polite" className="copy-editor__counter">День {dayIndex + 1} из {dayCount}</span>
              <button type="button" className="secondary copy-editor__icon"
                disabled={dayIndex === dayCount - 1} onClick={() => selectDay(dayIndex + 1)}
                aria-label="Следующий день">
                <Icon name="chevron-right" size={20} />
              </button>
            </div>
          </div>

          <div className="copy-editor__current-day">
            <div className="copy-editor__eyebrow">День {dayIndex + 1} из {dayCount}</div>
            <label className="field">
              <span>Название дня</span>
              <input maxLength={128} required value={day.title}
                onChange={(event) => updateDay(dayIndex, (current) => ({
                  ...current, title: event.target.value,
                }))}
              />
            </label>
            <div className="copy-editor__order-actions">
              <button type="button" className="secondary" disabled={dayIndex === 0}
                onClick={() => moveDay(-1)} aria-label="Переместить день выше">
                <Icon name="move-up" size={18} />
              </button>
              <button type="button" className="secondary" disabled={dayIndex === dayCount - 1}
                onClick={() => moveDay(1)} aria-label="Переместить день ниже">
                <Icon name="move-down" size={18} />
              </button>
              {dayCount > 1 && (
                <button type="button" className="text-button copy-editor__danger"
                  onClick={() => void deleteDay()}>Удалить день</button>
              )}
            </div>
          </div>

          <div className="copy-editor__section-head copy-editor__exercise-heading">
            <div><h3>Упражнения</h3><span className="muted">{day.exercises.length} упр. · только выбранный день</span></div>
            <button type="button" className="secondary" aria-pressed={reordering}
              onClick={() => setReordering((value) => !value)}>
              {reordering ? 'Готово' : 'Изменить порядок'}
            </button>
          </div>
          <div className="copy-editor__exercise-list">
            {day.exercises.map((item, index) => {
              const details = available(item.exercise_id);
              const cardio = details?.metric_type === 'cardio';
              return (
                <button key={index} type="button" className="copy-editor__exercise"
                  aria-pressed={index === exerciseIndex}
                  onClick={(event) => {
                    exerciseTriggerRef.current = event.currentTarget;
                    setSelectedExercise(index);
                    setDetailOpen(mobileView);
                  }}>
                  <span className="copy-editor__ordinal">{index + 1}</span>
                  <span className="copy-editor__exercise-info">
                    <strong>{details?.title ?? 'Выберите упражнение'}</strong>
                    <span>
                      {cardio
                        ? String(item.prescribed_duration_minutes ?? 0) + ' мин'
                        : String(item.prescribed_sets ?? 0) + ' × ' +
                          String(item.prescribed_reps ?? '') + ' · отдых ' +
                          String(item.rest_seconds ?? 0) + ' сек'}
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
            <button type="button" className="secondary copy-editor__add"
              onClick={() => {
                updateDay(dayIndex, (current) => ({
                  ...current,
                  exercises: [...current.exercises, newExercise(defaultRestSeconds)],
                }));
                setSelectedExercise(day.exercises.length);
                exerciseTriggerRef.current = null;
                setDetailOpen(mobileView);
              }}>
              <Icon name="plus" size={18} /> Добавить упражнение
            </button>
          ) : <p className="muted">В одной тренировке максимум 20 упражнений.</p>}

          <div className="copy-editor__add-day">
            {dayCount < 8 ? (
              <button type="button" className="secondary"
                onClick={() => {
                  setDays((current) => [
                    ...current,
                    { title: simpleTrainingTitle(current.length + 1), exercises: [newExercise(defaultRestSeconds)] },
                  ]);
                  setSelectedDay(dayCount);
                  setSelectedExercise(0);
                }}>
                <Icon name="plus" size={18} /> Добавить день
              </button>
            ) : <span className="muted">В одном цикле максимум 8 тренировочных дней.</span>}
          </div>
        </div>

        <aside className="copy-editor__detail-rail" aria-label="Параметры упражнения">
          {!mobileView && renderDetails(false)}
        </aside>
      </section>

      {allDaysOpen && createPortal(
        <div className="copy-editor__overlay" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeAllDays();
        }}>
          <div className="copy-editor__sheet" role="dialog" aria-modal="true"
            aria-label="Все дни программы" ref={allDaysDialogRef}>
            <div className="copy-editor__sheet-header">
              <h3>Все дни программы</h3>
              <button type="button" className="secondary copy-editor__icon"
                onClick={closeAllDays} aria-label="Закрыть список дней">
                <Icon name="close" size={20} />
              </button>
            </div>
            <div className="copy-editor__day-grid">{allDayButtons}</div>
          </div>
        </div>,
        document.body,
      )}
      {detailOpen && mobileView && createPortal(
        <div className="copy-editor__overlay copy-editor__detail-overlay" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeDetail();
        }}>
          <div className="copy-editor__sheet copy-editor__detail-sheet" role="dialog"
            aria-modal="true" aria-label="Параметры упражнения" ref={detailDialogRef}>
            {renderDetails(true)}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
