import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { CoachAssignedProgram, Exercise } from '../../shared/api/types';
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
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { ExerciseGuideDialog } from './ExerciseGuideDialog';
import { rankExercisesForSearch } from './exerciseSearch';

const difficultyLabels: Record<Exercise['difficulty_level'], string> = {
  beginner: 'Начальный',
  intermediate: 'Средний',
  advanced: 'Продвинутый',
};

const equipmentLabels: Record<string, string> = {
  bodyweight: 'Собственный вес',
  dumbbell: 'Гантели',
  barbell: 'Штанга',
  bench: 'Скамья',
  cable: 'Тросовый блок',
  machine: 'Тренажёр',
  kettlebell: 'Гиря',
  cardio: 'Кардиооборудование',
  other: 'Другое',
};

const weekdayLabels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const PAGE_SIZE = 32;

export function ExerciseCatalog({
  canCreate = false,
  canAssign = false,
  targetTelegramId,
}: {
  canCreate?: boolean;
  canAssign?: boolean;
  targetTelegramId?: number | null;
}) {
  const { toast, confirm } = useFeedback();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [muscle, setMuscle] = useState('');
  const [equipment, setEquipment] = useState('');
  const [difficulty, setDifficulty] = useState<Exercise['difficulty_level'] | ''>('');
  const [visibleLimit, setVisibleLimit] = useState(PAGE_SIZE);
  const [guide, setGuide] = useState<Exercise | null>(null);
  const [assignment, setAssignment] = useState<Exercise | null>(null);
  const [assignmentClientId, setAssignmentClientId] = useState(0);
  const [assignmentProgramId, setAssignmentProgramId] = useState(0);
  const [assignmentSets, setAssignmentSets] = useState(3);
  const [assignmentReps, setAssignmentReps] = useState('8-12');
  const [assignmentDuration, setAssignmentDuration] = useState(30);
  const [assignmentRest, setAssignmentRest] = useState(90);
  const [assignmentDay, setAssignmentDay] = useState(1);
  const [assignmentNotes, setAssignmentNotes] = useState('');
  const [assignmentSupersetGroup, setAssignmentSupersetGroup] = useState<number | ''>('');
  const [assignmentSupersetOrder, setAssignmentSupersetOrder] = useState<1 | 2>(1);
  const [assignmentReason, setAssignmentReason] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [newMuscle, setNewMuscle] = useState('');
  const [newEquipment, setNewEquipment] = useState('');
  const [newDifficulty, setNewDifficulty] = useState<Exercise['difficulty_level']>('intermediate');
  const [newMetricType, setNewMetricType] = useState<'strength' | 'cardio'>('strength');
  const assignmentPanelRef = useModalA11y<HTMLDivElement>(Boolean(assignment), () =>
    setAssignment(null),
  );
  const rows = useQuery({
    queryKey: ['exercises'],
    queryFn: () => api<Exercise[]>('/api/v1/programs/exercises'),
  });
  const coachPrograms = useQuery({
    queryKey: ['coach', 'programs'],
    queryFn: () => api<CoachAssignedProgram[]>('/api/v1/coach/assigned-programs'),
    enabled: canAssign,
  });
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: unknown }) =>
      api(path, { method, body }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['exercises'] });
      setNewTitle('');
      setNewMuscle('');
      setNewEquipment('');
      setNewDifficulty('intermediate');
      setNewMetricType('strength');
      toast('Каталог обновлён');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  const muscleOptions = useMemo(() => {
    const values = new Map<string, string>();
    for (const exercise of rows.data ?? []) {
      const ids = exercise.primary_muscle_ids ?? [];
      if (ids.length) {
        for (const id of ids) values.set(id, exercise.primary_muscle || id);
      } else if (exercise.primary_muscle) {
        values.set(`legacy:${exercise.primary_muscle}`, exercise.primary_muscle);
      }
    }
    return [...values].sort((left, right) => left[1].localeCompare(right[1], 'ru'));
  }, [rows.data]);

  const equipmentOptions = useMemo(() => {
    const values = new Map<string, string>();
    for (const exercise of rows.data ?? []) {
      const ids = exercise.equipment_ids ?? [];
      if (ids.length) {
        for (const id of ids) values.set(id, equipmentLabels[id] ?? exercise.equipment ?? id);
      } else if (exercise.equipment) {
        values.set(`legacy:${exercise.equipment}`, exercise.equipment);
      }
    }
    return [...values].sort((left, right) => left[1].localeCompare(right[1], 'ru'));
  }, [rows.data]);

  const filtered = useMemo(() => {
    const canonicalRows = rankExercisesForSearch(rows.data ?? [], search);
    return canonicalRows.filter((item) => {
      const matchesMuscle =
        !muscle ||
        (muscle.startsWith('legacy:')
          ? item.primary_muscle === muscle.slice(7)
          : (item.primary_muscle_ids ?? []).includes(muscle));
      const matchesEquipment =
        !equipment ||
        (equipment.startsWith('legacy:')
          ? item.equipment === equipment.slice(7)
          : (item.equipment_ids ?? []).includes(equipment));
      return (
        matchesMuscle && matchesEquipment && (!difficulty || item.difficulty_level === difficulty)
      );
    });
  }, [difficulty, equipment, muscle, rows.data, search]);

  const assignablePrograms = useMemo(
    () => (coachPrograms.data ?? []).filter((item) => item.is_active && item.workouts_planned > 0),
    [coachPrograms.data],
  );
  const assignmentClients = useMemo(
    () => [
      ...new Map(
        assignablePrograms.map((item) => [
          item.client_id,
          {
            id: item.client_id,
            name:
              item.client_full_name ||
              (item.client_username
                ? `@${item.client_username}`
                : String(item.client_telegram_user_id)),
          },
        ]),
      ).values(),
    ],
    [assignablePrograms],
  );
  const activeAssignmentClientId = assignmentClients.some((item) => item.id === assignmentClientId)
    ? assignmentClientId
    : (assignablePrograms.find((item) => item.client_telegram_user_id === targetTelegramId)
        ?.client_id ??
      assignmentClients[0]?.id ??
      0);
  const clientPrograms = assignablePrograms.filter(
    (item) => item.client_id === activeAssignmentClientId,
  );
  const activeAssignmentProgramId = clientPrograms.some((item) => item.id === assignmentProgramId)
    ? assignmentProgramId
    : (clientPrograms[0]?.id ?? 0);
  const activeAssignmentProgram = clientPrograms.find(
    (item) => item.id === activeAssignmentProgramId,
  );

  const assignmentMutation = useMutation({
    mutationFn: () => {
      if (!assignment || !activeAssignmentClientId || !activeAssignmentProgramId)
        throw new Error('Выберите клиента и программу');
      return api<{ workouts_updated: number; current_revision_number: number }>(
        `/api/v1/coach/clients/${activeAssignmentClientId}/programs/${activeAssignmentProgramId}/exercises`,
        {
          method: 'POST',
          body: {
            expected_revision_number: activeAssignmentProgram?.current_revision_number ?? 0,
            exercise_id: assignment.id,
            day_number: assignmentDay,
            prescribed_sets: assignment.metric_type === 'cardio' ? null : assignmentSets,
            prescribed_reps: assignment.metric_type === 'cardio' ? null : assignmentReps,
            prescribed_duration_minutes:
              assignment.metric_type === 'cardio' ? assignmentDuration : null,
            rest_seconds: assignmentRest,
            notes: assignmentNotes || null,
            superset_group:
              assignment.metric_type === 'cardio' ? null : assignmentSupersetGroup || null,
            superset_order:
              assignment.metric_type === 'cardio' || !assignmentSupersetGroup
                ? null
                : assignmentSupersetOrder,
            reason: assignmentReason || null,
          },
        },
      );
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['coach', 'programs'] });
      toast(`Упражнение добавлено в ${result.workouts_updated} предстоящих тренировок`);
      setAssignment(null);
      setAssignmentNotes('');
      setAssignmentSupersetGroup('');
      setAssignmentReason('');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  const resetFilters = () => {
    setSearch('');
    setMuscle('');
    setEquipment('');
    setDifficulty('');
    setVisibleLimit(PAGE_SIZE);
  };

  return (
    <>
      <Card
        className="exercise-catalog"
        collapsible={false}
        title="Упражнения"
        description="Найдите движение по названию, мышцам или доступному оборудованию."
      >
        <div className="exercise-catalog__search top-gap">
          <label className="field">
            <span>Поиск</span>
            <input
              type="search"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setVisibleLimit(PAGE_SIZE);
              }}
              placeholder="Например, приседание или гантели"
            />
          </label>
        </div>
        <div className="exercise-catalog__filters" aria-label="Фильтры упражнений">
          <label className="field">
            <span>Мышцы</span>
            <select
              data-glass=""
              data-glass-variant="tinted"
              data-glass-interactive=""
              value={muscle}
              onChange={(event) => {
                setMuscle(event.target.value);
                setVisibleLimit(PAGE_SIZE);
              }}
            >
              <option value="">Все группы</option>
              {muscleOptions.map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Оборудование</span>
            <select
              data-glass=""
              data-glass-variant="tinted"
              data-glass-interactive=""
              value={equipment}
              onChange={(event) => {
                setEquipment(event.target.value);
                setVisibleLimit(PAGE_SIZE);
              }}
            >
              <option value="">Любое</option>
              {equipmentOptions.map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Опыт</span>
            <select
              data-glass=""
              data-glass-variant="tinted"
              data-glass-interactive=""
              value={difficulty}
              onChange={(event) => {
                setDifficulty(event.target.value as Exercise['difficulty_level'] | '');
                setVisibleLimit(PAGE_SIZE);
              }}
            >
              <option value="">Любой</option>
              {Object.entries(difficultyLabels).map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {(search || muscle || equipment || difficulty) && (
            <button type="button" className="text-button" onClick={resetFilters}>
              Сбросить фильтры
            </button>
          )}
        </div>
        {canCreate && (
          <details className="exercise-create compact-disclosure">
            <summary>
              <span>
                <strong>Создать своё упражнение</strong>
                <small>
                  {targetTelegramId
                    ? 'Персонально для выбранного клиента'
                    : 'Если подходящего движения нет в каталоге'}
                </small>
              </span>
              <DisclosureIcon />
            </summary>
            <form
              className="exercise-create__form"
              onSubmit={(event) => {
                event.preventDefault();
                mutation.mutate({
                  path: '/api/v1/programs/exercises',
                  method: 'POST',
                  body: {
                    title: newTitle,
                    primary_muscle: newMuscle || null,
                    equipment: newEquipment || null,
                    difficulty_level: newDifficulty,
                    metric_type: newMetricType,
                    target_telegram_user_id: targetTelegramId || null,
                  },
                });
              }}
            >
              <label className="field exercise-create__title">
                <span>Название</span>
                <input
                  value={newTitle}
                  maxLength={128}
                  onChange={(event) => setNewTitle(event.target.value)}
                  required
                />
              </label>
              <label className="field">
                <span>Основная мышечная группа</span>
                <input
                  value={newMuscle}
                  maxLength={64}
                  onChange={(event) => setNewMuscle(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Оборудование</span>
                <input
                  value={newEquipment}
                  maxLength={64}
                  onChange={(event) => setNewEquipment(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Уровень</span>
                <select
                  value={newDifficulty}
                  onChange={(event) =>
                    setNewDifficulty(event.target.value as Exercise['difficulty_level'])
                  }
                >
                  {Object.entries(difficultyLabels).map(([value, label]) => (
                    <option value={value} key={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Как записывать результат</span>
                <select
                  value={newMetricType}
                  onChange={(event) =>
                    setNewMetricType(event.target.value as 'strength' | 'cardio')
                  }
                >
                  <option value="strength">Вес и повторения</option>
                  <option value="cardio">Время и дистанция</option>
                </select>
              </label>
              <button disabled={mutation.isPending}>
                {mutation.isPending ? 'Создаём…' : 'Создать упражнение'}
              </button>
            </form>
          </details>
        )}
        {!rows.isLoading && !rows.error && (
          <p className="exercise-catalog__count" aria-live="polite">
            Найдено: <strong>{filtered.length}</strong>
          </p>
        )}
        {rows.isLoading ? (
          <LoadingState />
        ) : rows.error ? (
          <ErrorState message={(rows.error as Error).message} retry={() => void rows.refetch()} />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="Ничего не найдено"
            text="Попробуйте убрать один из фильтров или изменить запрос."
          />
        ) : (
          <>
            <div className="exercise-catalog-list" aria-live="polite">
              {filtered.slice(0, visibleLimit).map((exercise) => (
                <article className="exercise-catalog-item" key={exercise.id}>
                  <button
                    aria-label={`${exercise.has_guide ? 'Техника и детали' : 'Подробнее'}: ${exercise.title}`}
                    className="exercise-catalog-item__main"
                    type="button"
                    onClick={() => setGuide(exercise)}
                  >
                    <span className="exercise-catalog-item__copy">
                      <strong>{exercise.title}</strong>
                      <span>
                        {exercise.primary_muscle || 'Всё тело'} ·{' '}
                        {exercise.equipment || 'Без оборудования'}
                      </span>
                      <span className="exercise-catalog-item__badges">
                        <Badge>{difficultyLabels[exercise.difficulty_level]}</Badge>
                        {exercise.metric_type === 'cardio' && <Badge>Время и дистанция</Badge>}
                        {exercise.is_custom && <Badge>Своё</Badge>}
                        {!!exercise.alternatives?.length && (
                          <Badge>{exercise.alternatives.length} проверенных замен</Badge>
                        )}
                      </span>
                    </span>
                    <DisclosureIcon />
                  </button>
                  {canAssign && (
                    <div className="exercise-catalog-item__actions">
                      <button type="button" onClick={() => setAssignment(exercise)}>
                        В программу
                      </button>
                    </div>
                  )}
                  {exercise.is_custom && (
                    <details className="exercise-catalog-item__danger">
                      <summary>Другие действия</summary>
                      <button
                        className="btn-danger"
                        type="button"
                        onClick={async () => {
                          if (
                            await confirm({
                              title: 'Удалить упражнение?',
                              message: exercise.title,
                              confirmText: 'Удалить',
                            })
                          )
                            mutation.mutate({
                              path: `/api/v1/programs/exercises/${exercise.id}`,
                              method: 'DELETE',
                            });
                        }}
                      >
                        Удалить упражнение
                      </button>
                    </details>
                  )}
                </article>
              ))}
            </div>
            {visibleLimit < filtered.length && (
              <button
                type="button"
                className="secondary exercise-catalog__more"
                onClick={() => setVisibleLimit((value) => value + PAGE_SIZE)}
              >
                Показать ещё {Math.min(PAGE_SIZE, filtered.length - visibleLimit)}
              </button>
            )}
          </>
        )}
      </Card>
      {guide && (
        <ExerciseGuideDialog
          exerciseId={guide.id}
          exerciseTitle={guide.title}
          onClose={() => setGuide(null)}
        />
      )}
      {assignment && (
        <div className="modal" role="dialog" aria-modal="true" aria-labelledby="assign-title">
          <button
            className="modal__backdrop"
            aria-label="Закрыть"
            onClick={() => setAssignment(null)}
          />
          <div
            className="modal__panel card assignment-modal"
            ref={assignmentPanelRef}
            tabIndex={-1}
          >
            <div className="section-head">
              <div>
                <span className="eyebrow">Изменение будущего плана</span>
                <h2 id="assign-title">{assignment.title}</h2>
              </div>
              <button
                className="secondary"
                aria-label="Закрыть назначение упражнения"
                onClick={() => setAssignment(null)}
              >
                <CloseIcon />
              </button>
            </div>
            {coachPrograms.isLoading ? (
              <LoadingState />
            ) : coachPrograms.error ? (
              <ErrorState
                message={(coachPrograms.error as Error).message}
                retry={() => void coachPrograms.refetch()}
              />
            ) : assignmentClients.length === 0 ? (
              <EmptyState
                title="Нет подходящих программ"
                text="Сначала создайте и назначьте клиенту программу с предстоящими тренировками."
              />
            ) : (
              <form
                className="stack"
                onSubmit={(event) => {
                  event.preventDefault();
                  assignmentMutation.mutate();
                }}
              >
                <div className="assignment-context">
                  <label className="field">
                    <span>Клиент</span>
                    <select
                      value={activeAssignmentClientId}
                      onChange={(event) => {
                        const nextClientId = Number(event.target.value);
                        setAssignmentClientId(nextClientId);
                        setAssignmentProgramId(
                          assignablePrograms.find((item) => item.client_id === nextClientId)?.id ??
                            0,
                        );
                        setAssignmentDay(1);
                      }}
                    >
                      {assignmentClients.map((client) => (
                        <option value={client.id} key={client.id}>
                          {client.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>Активная программа</span>
                    <select
                      value={activeAssignmentProgramId}
                      onChange={(event) => {
                        setAssignmentProgramId(Number(event.target.value));
                        setAssignmentDay(1);
                      }}
                    >
                      {clientPrograms.map((program) => (
                        <option value={program.id} key={program.id}>
                          {program.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>День программы</span>
                    <select
                      value={assignmentDay}
                      onChange={(event) => setAssignmentDay(Number(event.target.value))}
                    >
                      {(activeAssignmentProgram?.schedule_weekdays ?? []).map((weekday, index) => (
                        <option value={index + 1} key={`${weekday}-${index}`}>
                          День {index + 1} ·{' '}
                          {weekdayLabels[weekday] ?? `день недели ${weekday + 1}`}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <p className="muted assignment-modal__hint">
                  Изменение попадёт только в будущие тренировки выбранного дня. Завершённые и уже
                  начатые тренировки не изменятся.
                </p>
                {assignment.metric_type === 'cardio' ? (
                  <div className="form-grid assignment-prescription">
                    <label className="field">
                      <span>Плановая длительность, мин</span>
                      <input
                        type="number"
                        inputMode="numeric"
                        min="1"
                        max="600"
                        required
                        value={assignmentDuration}
                        onChange={(event) => setAssignmentDuration(Number(event.target.value))}
                      />
                    </label>
                  </div>
                ) : (
                  <div className="form-grid assignment-prescription">
                    <label className="field">
                      <span>Рабочие подходы</span>
                      <input
                        type="number"
                        min="1"
                        max="10"
                        value={assignmentSets}
                        onChange={(event) => setAssignmentSets(Number(event.target.value))}
                      />
                    </label>
                    <label className="field">
                      <span>Повторения</span>
                      <input
                        value={assignmentReps}
                        maxLength={32}
                        onChange={(event) => setAssignmentReps(event.target.value)}
                      />
                    </label>
                    <label className="field">
                      <span>Отдых, сек</span>
                      <input
                        type="number"
                        min="15"
                        max="600"
                        value={assignmentRest}
                        onChange={(event) => setAssignmentRest(Number(event.target.value))}
                      />
                    </label>
                  </div>
                )}
                <label className="field">
                  <span>Заметка клиенту (необязательно)</span>
                  <textarea
                    maxLength={2000}
                    value={assignmentNotes}
                    placeholder="Например: выполнять медленно, без рывков"
                    onChange={(event) => setAssignmentNotes(event.target.value)}
                  />
                </label>
                <details className="compact-disclosure assignment-advanced">
                  <summary>
                    <span>
                      <strong>Дополнительные настройки</strong>
                      <small>
                        {assignment.metric_type === 'cardio'
                          ? 'Причина изменения'
                          : 'Суперсет и причина изменения'}
                      </small>
                    </span>
                    <DisclosureIcon />
                  </summary>
                  <div className="assignment-advanced__body">
                    {assignment.metric_type !== 'cardio' && (
                      <div className="form-grid">
                        <label className="field">
                          <span>Номер суперсета</span>
                          <input
                            type="number"
                            min="1"
                            value={assignmentSupersetGroup}
                            placeholder="Не задан"
                            onChange={(event) =>
                              setAssignmentSupersetGroup(
                                event.target.value ? Number(event.target.value) : '',
                              )
                            }
                          />
                        </label>
                        <label className="field">
                          <span>Порядок в паре</span>
                          <select
                            value={assignmentSupersetOrder}
                            disabled={!assignmentSupersetGroup}
                            onChange={(event) =>
                              setAssignmentSupersetOrder(Number(event.target.value) as 1 | 2)
                            }
                          >
                            <option value="1">Первое</option>
                            <option value="2">Второе</option>
                          </select>
                        </label>
                      </div>
                    )}
                    {assignment.metric_type !== 'cardio' && (
                      <small className="muted">
                        Суперсет — два упражнения подряд. Используйте номер уже существующей пары.
                      </small>
                    )}
                    <label className="field">
                      <span>Причина изменения (необязательно)</span>
                      <input
                        value={assignmentReason}
                        maxLength={500}
                        onChange={(event) => setAssignmentReason(event.target.value)}
                      />
                    </label>
                  </div>
                </details>
                <button disabled={assignmentMutation.isPending || !activeAssignmentProgramId}>
                  {assignmentMutation.isPending ? 'Сохраняем…' : 'Добавить в будущий план'}
                </button>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
