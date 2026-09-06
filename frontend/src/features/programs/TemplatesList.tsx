import { useEffect, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import type { ProgramTemplate } from '../../shared/api/types';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import {
  Badge,
  Card,
  CloseIcon,
  DisclosureIcon,
  EmptyState,
  ErrorState,
  LoadingState,
} from '../../shared/ui/common';
import { useAuth } from '../../app/AuthProvider';
import { dateInputValue, detectedTimeZone } from '../../shared/dateTime';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { ExerciseGuideDialog } from '../exercises/ExerciseGuideDialog';
import { ProgramBuilder } from './ProgramBuilder';
import { shouldSaveTemplateAsCopy } from './templateEditing';
import { DateInput } from '../../shared/ui/PickerInput';
import { ProgramRecommendation } from './ProgramRecommendation';
import { productEventSurface, trackCoreProductEvent } from '../../shared/analytics/productEvents';
import { AssignedProgramDetails } from './AssignedProgramDetails';
import { ProgramImportPanel } from './ProgramImportPanel';

const goalLabels: Record<string, string> = {
  muscle_gain: 'Набор мышечной массы',
  fat_loss: 'Снижение веса',
  maintenance: 'Поддержание формы',
  recomposition: 'Рекомпозиция',
};

const levelLabels: Record<string, string> = {
  beginner: 'Начальный уровень',
  intermediate: 'Средний уровень',
  advanced: 'Продвинутый уровень',
};
const weekdayLabels = [
  'Понедельник',
  'Вторник',
  'Среда',
  'Четверг',
  'Пятница',
  'Суббота',
  'Воскресенье',
];

function weekdayFromDate(value: string): number {
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.valueOf()) ? 0 : (date.getUTCDay() + 6) % 7;
}

function defaultWeekdays(template: ProgramTemplate, startDate: string): number[] {
  if (template.days.length > 7) return [];
  const firstWeekday = weekdayFromDate(startDate);
  return template.days.map((_, index) => (firstWeekday + index) % 7);
}

function programMeta(item: ProgramTemplate) {
  const remainder = item.days.length % 10;
  const suffix =
    remainder === 1 && item.days.length % 100 !== 11
      ? 'тренировка'
      : remainder >= 2 &&
          remainder <= 4 &&
          (item.days.length % 100 < 10 || item.days.length % 100 >= 20)
        ? 'тренировки'
        : 'тренировок';
  return `${goalLabels[item.goal] ?? 'Цель не указана'} · ${levelLabels[item.level] ?? 'Уровень не указан'} · ${item.days.length} ${suffix} в цикле`;
}

function programKind(item: ProgramTemplate, currentUserId?: number): string {
  if (item.assigned_by_user_id && item.assigned_by_user_id !== currentUserId) return 'От тренера';
  if (item.is_example) return 'Готовый шаблон';
  if (item.owner_user_id === currentUserId || item.can_edit) return 'Моя программа';
  return 'Шаблон';
}

export function TemplatesList({
  children,
  defaultLibraryOpen = false,
}: {
  children?: ReactNode;
  defaultLibraryOpen?: boolean;
}) {
  const { toast, confirm } = useFeedback();
  const { user, reloadUser } = useAuth();
  const queryClient = useQueryClient();
  const [selectedExample, setSelectedExample] = useState<ProgramTemplate | null>(null);
  const [guide, setGuide] = useState<{ id: number; title: string } | null>(null);
  const [editingTemplate, setEditingTemplate] = useState<ProgramTemplate | null>(null);
  const [saveAsCopy, setSaveAsCopy] = useState(false);
  const [assignmentTemplate, setAssignmentTemplate] = useState<ProgramTemplate | null>(null);
  const [recommendationOpen, setRecommendationOpen] = useState(false);
  const defaultStartDate = dateInputValue(
    new Date(),
    user?.profile?.timezone || detectedTimeZone(),
  );
  const [assignmentStartDate, setAssignmentStartDate] = useState(defaultStartDate);
  const [assignmentDuration, setAssignmentDuration] = useState(4);
  const [assignmentWeekdays, setAssignmentWeekdays] = useState<number[]>([]);
  const examplePanelRef = useModalA11y<HTMLDivElement>(Boolean(selectedExample), () =>
    setSelectedExample(null),
  );
  const assignmentPanelRef = useModalA11y<HTMLDivElement>(Boolean(assignmentTemplate), () =>
    setAssignmentTemplate(null),
  );
  const templates = useQuery({
    queryKey: ['templates', 'mine'],
    queryFn: () => api<ProgramTemplate[]>('/api/v1/programs/templates/mine'),
  });
  const hidden = useQuery({
    queryKey: ['templates', 'hidden'],
    queryFn: () => api<ProgramTemplate[]>('/api/v1/programs/templates/hidden'),
  });
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: unknown }) =>
      api(path, { method, body }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['templates'] }),
        queryClient.invalidateQueries({ queryKey: ['workout'] }),
        reloadUser(),
      ]);
      toast('Программы обновлены');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  const assignmentMutation = useMutation({
    mutationFn: ({ templateId, replaceActive }: { templateId: number; replaceActive: boolean }) =>
      api(`/api/v1/programs/templates/${templateId}/assign-to-me`, {
        method: 'POST',
        body: {
          start_date: assignmentStartDate,
          duration_weeks: assignmentDuration,
          schedule_weekdays:
            assignmentTemplate && assignmentTemplate.days.length > 7 ? null : assignmentWeekdays,
          replace_active: replaceActive,
        },
      }),
    onSuccess: async () => {
      trackCoreProductEvent(
        { name: 'program_activated', surface: productEventSurface() },
        'program_activated',
      );
      setAssignmentTemplate(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['templates'] }),
        queryClient.invalidateQueries({ queryKey: ['workout'] }),
        reloadUser(),
      ]);
      toast('Программа назначена');
    },
    onError: async (reason, variables) => {
      if (
        reason instanceof ApiError &&
        reason.status === 409 &&
        !variables.replaceActive &&
        reason.message.toLowerCase().includes('confirmation')
      ) {
        if (
          await confirm({
            title: 'Заменить активную программу?',
            message:
              'Текущая программа будет отправлена в архив. Тренировку, которая уже идёт, заменить нельзя.',
            confirmText: 'Заменить программу',
          })
        )
          assignmentMutation.mutate({ ...variables, replaceActive: true });
        return;
      }
      toast(
        reason instanceof ApiError && reason.message.toLowerCase().includes('in progress')
          ? 'Сначала завершите текущую тренировку — во время неё программу заменить нельзя.'
          : (reason as Error).message,
        'error',
      );
    },
  });

  const assignmentOffsets = assignmentWeekdays.map(
    (weekday) => (weekday - (assignmentWeekdays[0] ?? weekday) + 7) % 7,
  );
  const assignmentScheduleIsValid =
    Boolean(assignmentTemplate) &&
    ((assignmentTemplate?.days.length ?? 0) > 7
      ? assignmentWeekdays.length === 0
      : assignmentWeekdays.length === assignmentTemplate?.days.length &&
        new Set(assignmentWeekdays).size === assignmentWeekdays.length &&
        assignmentOffsets.every(
          (offset, index) => index === 0 || offset > assignmentOffsets[index - 1]!,
        ));

  const openAssignment = (template: ProgramTemplate) => {
    setAssignmentStartDate(defaultStartDate);
    setAssignmentDuration(4);
    setAssignmentWeekdays(defaultWeekdays(template, defaultStartDate));
    setAssignmentTemplate(template);
  };

  const editCopy = (template: ProgramTemplate) => {
    setSaveAsCopy(true);
    setEditingTemplate(template);
  };

  const activeTemplate = templates.data?.find((item) => item.is_active_for_current_user) ?? null;
  const ownTemplates =
    templates.data?.filter(
      (item) =>
        !item.is_active_for_current_user &&
        !item.is_example &&
        (item.owner_user_id === user?.id || item.can_edit),
    ) ?? [];
  const readyTemplates =
    templates.data?.filter(
      (item) =>
        !item.is_active_for_current_user &&
        (item.is_example || (item.owner_user_id !== user?.id && !item.can_edit)),
    ) ?? [];

  useEffect(() => {
    if (!defaultLibraryOpen || templates.isLoading) return;
    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById('program-library');
      if (!(target instanceof HTMLDetailsElement)) return;
      target.open = true;
      target.scrollIntoView({ block: 'start' });
      target.querySelector<HTMLElement>(':scope > summary')?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [defaultLibraryOpen, templates.isLoading]);

  const renderTemplate = (item: ProgramTemplate) => (
    <article className="program-template-card" key={item.id}>
      <button
        type="button"
        className="text-button program-template-card__main"
        aria-label={`Посмотреть ${item.is_example ? 'шаблон' : 'программу'} «${item.title}»`}
        onClick={() => setSelectedExample(item)}
      >
        <span className="program-template-badges">
          <Badge>{programKind(item, user?.id)}</Badge>
        </span>
        <strong>{item.title}</strong>
        <span className="muted">{programMeta(item)}</span>
        <span className="program-example-trigger__hint">Открыть состав</span>
      </button>
      <div className="program-template-card__actions">
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setSaveAsCopy(shouldSaveTemplateAsCopy(item));
            setEditingTemplate(item);
          }}
        >
          {shouldSaveTemplateAsCopy(item) ? 'Настроить копию' : 'Редактировать'}
        </button>
        <button onClick={() => openAssignment(item)}>Запустить</button>
      </div>
      <details className="program-danger-menu">
        <summary>Другие действия</summary>
        <button
          type="button"
          className="btn-danger"
          onClick={async () => {
            if (
              await confirm({
                title: item.is_example ? 'Скрыть шаблон?' : 'Удалить программу?',
                message: item.title,
                confirmText: item.is_example ? 'Скрыть' : 'Удалить',
              })
            )
              mutation.mutate({
                path: `/api/v1/programs/templates/${item.id}`,
                method: 'DELETE',
              });
          }}
        >
          {item.is_example ? 'Скрыть шаблон' : 'Удалить программу'}
        </button>
      </details>
    </article>
  );

  return (
    <>
      <section
        className="program-active semantic-card semantic-card--action semantic-card--training"
        data-card-variant="action"
        data-semantic-family="training"
        aria-labelledby="active-program-title"
      >
        {templates.isLoading ? (
          <LoadingState label="Загружаем текущую программу…" />
        ) : templates.error ? (
          <ErrorState
            message={(templates.error as Error).message}
            retry={() => void templates.refetch()}
          />
        ) : activeTemplate ? (
          <>
            <div className="program-active__head">
              <div>
                <span className="eyebrow">Текущая программа</span>
                <h2 id="active-program-title">{activeTemplate.title}</h2>
                <p>{programMeta(activeTemplate)}</p>
              </div>
              <Badge tone="success">Активна</Badge>
            </div>
            <div className="program-active__source">
              <strong>{programKind(activeTemplate, user?.id)}</strong>
              {activeTemplate.assigned_by_user_id &&
              activeTemplate.assigned_by_user_id !== user?.id ? (
                <span>
                  Назначил тренер
                  {activeTemplate.assigned_by_full_name
                    ? ` ${activeTemplate.assigned_by_full_name}`
                    : ''}
                </span>
              ) : (
                <span>Вы можете посмотреть состав или изменить будущий шаблон.</span>
              )}
            </div>
            {activeTemplate.assigned_program_id &&
              activeTemplate.assigned_program_start_date &&
              activeTemplate.assigned_program_duration_weeks != null &&
              activeTemplate.current_revision_number != null && (
                <AssignedProgramDetails
                  key={activeTemplate.assigned_program_id}
                  programId={activeTemplate.assigned_program_id}
                  currentRevisionNumber={activeTemplate.current_revision_number}
                  startDate={activeTemplate.assigned_program_start_date}
                  durationWeeks={activeTemplate.assigned_program_duration_weeks}
                  workoutHistoryReturnPath="/app?section=programs"
                />
              )}
            <div className="program-active__actions">
              <button
                type="button"
                className="secondary"
                onClick={() => setSelectedExample(activeTemplate)}
              >
                Посмотреть план
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => setRecommendationOpen(true)}
              >
                Подобрать другую
              </button>
              <button
                type="button"
                className="program-active__edit-action"
                onClick={() => {
                  setSaveAsCopy(shouldSaveTemplateAsCopy(activeTemplate));
                  setEditingTemplate(activeTemplate);
                }}
              >
                {shouldSaveTemplateAsCopy(activeTemplate)
                  ? 'Настроить свою копию'
                  : 'Редактировать шаблон'}
              </button>
            </div>
          </>
        ) : (
          <div className="program-active__empty">
            <span className="eyebrow">Текущая программа</span>
            <h2 id="active-program-title">План ещё не выбран</h2>
            <p>Создайте свою программу сразу или выберите готовый шаблон.</p>
            <div className="program-active__actions">
              <a className="button-link program-wizard__anchor" href="#program-builder">
                Создать свою программу
              </a>
              <a className="secondary program-wizard__anchor" href="#program-library">
                Программы и шаблоны
              </a>
            </div>
          </div>
        )}
      </section>
      {children}
      <ProgramImportPanel />
      <ProgramRecommendation
        open={recommendationOpen}
        onOpenChange={setRecommendationOpen}
        onPreview={setSelectedExample}
        onEditCopy={editCopy}
      />
      <Card
        defaultOpen={defaultLibraryOpen}
        family="training"
        id="program-library"
        title="Программы и шаблоны"
        description="Ваши заготовки и готовые варианты для быстрого запуска."
      >
        {templates.isLoading ? (
          <LoadingState />
        ) : templates.error ? (
          <ErrorState message={(templates.error as Error).message} />
        ) : !ownTemplates.length && !readyTemplates.length ? (
          <EmptyState title="Программ пока нет" text="Создайте первую программу в конструкторе." />
        ) : (
          <div className="program-library top-gap">
            {!!ownTemplates.length && (
              <section className="program-library__group" aria-labelledby="own-programs-title">
                <div>
                  <h3 id="own-programs-title">Мои программы</h3>
                  <span>{ownTemplates.length}</span>
                </div>
                <div className="program-template-grid">{ownTemplates.map(renderTemplate)}</div>
              </section>
            )}
            {!!readyTemplates.length && (
              <section className="program-library__group" aria-labelledby="ready-programs-title">
                <div>
                  <h3 id="ready-programs-title">Готовые шаблоны</h3>
                  <span>{readyTemplates.length}</span>
                </div>
                <div className="program-template-grid">{readyTemplates.map(renderTemplate)}</div>
              </section>
            )}
          </div>
        )}
        {!!hidden.data?.length && (
          <details className="compact-disclosure top-gap">
            <summary>
              <span>Скрытые примеры программ ({hidden.data.length})</span>
              <DisclosureIcon />
            </summary>
            <div className="list-grid top-gap">
              {hidden.data.map((item) => (
                <article className="list-row" key={item.id}>
                  <strong>{item.title}</strong>
                  <button
                    className="secondary"
                    onClick={() =>
                      mutation.mutate({
                        path: `/api/v1/programs/templates/${item.id}/restore`,
                        method: 'POST',
                      })
                    }
                  >
                    Восстановить
                  </button>
                </article>
              ))}
            </div>
          </details>
        )}
      </Card>
      {selectedExample && (
        <div
          className="modal program-example-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="program-example-title"
        >
          <button
            type="button"
            className="modal__backdrop"
            aria-label="Закрыть состав программы"
            onClick={() => setSelectedExample(null)}
          />
          <div
            className="modal__panel card program-example-modal__panel"
            ref={examplePanelRef}
            tabIndex={-1}
          >
            <div className="program-example-modal__head">
              <div>
                <span className="eyebrow">
                  {selectedExample.is_example ? 'Пример программы' : 'Моя программа'}
                </span>
                <h2 id="program-example-title">{selectedExample.title}</h2>
                <p className="muted">{programMeta(selectedExample)}</p>
              </div>
              <button
                type="button"
                className="secondary program-example-modal__close"
                aria-label="Закрыть состав программы"
                onClick={() => setSelectedExample(null)}
              >
                <CloseIcon />
              </button>
            </div>
            <div className="program-example-days">
              {selectedExample.days.map((day) => (
                <section className="program-example-day" key={day.id}>
                  <h3>
                    День {day.day_number}. {day.title}
                  </h3>
                  <ol>
                    {day.exercises.map((exercise) => (
                      <li key={exercise.id}>
                        <strong>{exercise.exercise_title}</strong>
                        <span>
                          {exercise.metric_type === 'cardio'
                            ? `${exercise.prescribed_duration_minutes ?? '—'} мин`
                            : `${exercise.prescribed_sets} подх. × ${exercise.prescribed_reps} · отдых ${exercise.rest_seconds} сек.`}
                        </span>
                        {exercise.superset_group && (
                          <small>
                            Суперсет {exercise.superset_group} · упражнение{' '}
                            {exercise.superset_order} из 2
                          </small>
                        )}
                        {exercise.notes && <small>{exercise.notes}</small>}
                        <button
                          type="button"
                          className="text-button"
                          onClick={() =>
                            setGuide({
                              id: exercise.exercise_id,
                              title: exercise.exercise_title,
                            })
                          }
                        >
                          {exercise.has_guide ? 'Техника и детали' : 'Подробнее об упражнении'}
                        </button>
                      </li>
                    ))}
                  </ol>
                </section>
              ))}
            </div>
            <div className="program-example-modal__actions">
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  const template = selectedExample;
                  setSelectedExample(null);
                  setSaveAsCopy(shouldSaveTemplateAsCopy(template));
                  setEditingTemplate(template);
                }}
              >
                {shouldSaveTemplateAsCopy(selectedExample)
                  ? 'Настроить личную копию'
                  : 'Редактировать программу'}
              </button>
              {selectedExample.is_active_for_current_user ? (
                <button type="button" disabled>
                  Уже запущена
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    const template = selectedExample;
                    setSelectedExample(null);
                    openAssignment(template);
                  }}
                >
                  Настроить расписание и запустить
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      {assignmentTemplate && (
        <div
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="assign-program-title"
        >
          <button
            type="button"
            className="modal__backdrop"
            aria-label="Закрыть настройку расписания"
            onClick={() => setAssignmentTemplate(null)}
          />
          <div
            className="modal__panel card assignment-modal"
            ref={assignmentPanelRef}
            tabIndex={-1}
          >
            <div className="section-head">
              <div>
                <span className="eyebrow">Расписание программы</span>
                <h2 id="assign-program-title">{assignmentTemplate.title}</h2>
              </div>
              <button
                type="button"
                className="secondary"
                aria-label="Закрыть настройку расписания"
                onClick={() => setAssignmentTemplate(null)}
              >
                <CloseIcon />
              </button>
            </div>
            <form
              className="stack"
              onSubmit={async (event) => {
                event.preventDefault();
                const active = templates.data?.find(
                  (template) => template.is_active_for_current_user,
                );
                let replaceActive = false;
                if (
                  active &&
                  !(await confirm({
                    title: 'Заменить активную программу?',
                    message: `«${active.title}» будет отправлена в архив, а «${assignmentTemplate.title}» станет активной.`,
                    confirmText: 'Заменить программу',
                  }))
                )
                  return;
                replaceActive = Boolean(active);
                assignmentMutation.mutate({ templateId: assignmentTemplate.id, replaceActive });
              }}
            >
              <div className="form-grid">
                <label className="field">
                  <span>Начать не раньше</span>
                  <DateInput
                    min={defaultStartDate}
                    value={assignmentStartDate}
                    onChange={(event) => {
                      const nextStartDate = event.target.value;
                      setAssignmentStartDate(nextStartDate);
                      setAssignmentWeekdays(defaultWeekdays(assignmentTemplate, nextStartDate));
                    }}
                    required
                  />
                </label>
                <label className="field">
                  <span>Длительность, недель</span>
                  <input
                    type="number"
                    min="1"
                    max="24"
                    value={assignmentDuration}
                    onChange={(event) => setAssignmentDuration(Number(event.target.value))}
                    required
                  />
                </label>
              </div>
              {assignmentTemplate.days.length > 7 ? (
                <p className="auth-notice">
                  Восьмидневный цикл планируется последовательно: одна тренировка за другой, начиная
                  с выбранной даты.
                </p>
              ) : (
                <div className="form-grid">
                  {assignmentTemplate.days.map((day, dayIndex) => (
                    <label className="field" key={day.id}>
                      <span>{day.title || `День ${dayIndex + 1}`}</span>
                      <select
                        value={assignmentWeekdays[dayIndex] ?? ''}
                        onChange={(event) =>
                          setAssignmentWeekdays(
                            assignmentWeekdays.map((value, index) =>
                              index === dayIndex ? Number(event.target.value) : value,
                            ),
                          )
                        }
                      >
                        {weekdayLabels.map((label, weekday) => (
                          <option value={weekday} key={label}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
              )}
              {!assignmentScheduleIsValid && (
                <p className="field-error" role="alert">
                  Выберите разные дни недели в порядке тренировок. В одной неделе доступно до семи
                  дней.
                </p>
              )}
              <button
                disabled={
                  assignmentMutation.isPending ||
                  !assignmentScheduleIsValid ||
                  assignmentDuration < 1 ||
                  assignmentDuration > 24
                }
              >
                {assignmentMutation.isPending ? 'Назначаем…' : 'Назначить по расписанию'}
              </button>
            </form>
          </div>
        </div>
      )}
      {guide && (
        <ExerciseGuideDialog
          exerciseId={guide.id}
          exerciseTitle={guide.title}
          onClose={() => setGuide(null)}
        />
      )}
      {editingTemplate && (
        <div
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-label={`${saveAsCopy ? 'Создание копии' : 'Редактирование'} программы «${editingTemplate.title}»`}
        >
          <button
            type="button"
            className="modal__backdrop"
            aria-label="Закрыть редактирование"
            onClick={() => setEditingTemplate(null)}
          />
          <div className="modal__panel assignment-modal">
            <div className="section-head">
              <strong>
                {saveAsCopy ? 'Редактирование личной копии' : 'Редактирование программы'}
              </strong>
              <button
                type="button"
                className="secondary"
                aria-label="Закрыть редактирование"
                onClick={() => setEditingTemplate(null)}
              >
                <CloseIcon />
              </button>
            </div>
            <ProgramBuilder
              editingTemplate={editingTemplate}
              saveAsCopy={saveAsCopy}
              onSaved={() => setEditingTemplate(null)}
            />
          </div>
        </div>
      )}
    </>
  );
}
