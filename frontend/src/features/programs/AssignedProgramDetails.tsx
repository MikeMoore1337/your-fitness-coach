import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import type { ApiSchemas } from '../../shared/api/types';
import { AppLink } from '../../shared/navigation/router';
import {
  Badge,
  Button,
  DisclosureIcon,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { DateInput } from '../../shared/ui/PickerInput';
import { Icon } from '../../shared/ui/Icon';
import { AiAdaptationProposal } from '../ai/AiAdaptationProposal';
import { ProgressionGuidance } from '../workouts/ProgressionGuidance';
import {
  blockStatusLabel,
  buildRevisionPresentation,
  formatProgramDate,
  formatRevisionMoment,
  primaryBlockHeading,
  primaryTrainingBlock,
  type ProgramRevision,
  type TrainingBlock,
  workoutStatusLabel,
} from './programHistory';

type TrainingBlockMutation = ApiSchemas['TrainingBlockMutationResponse'];
type ProgressionProposalList = ApiSchemas['ProgramProgressionProposalList'];
type ProgressionReviewResponse = ApiSchemas['ProgressionProposalReviewResponse'];
type ProgramLifecycleSummary = ApiSchemas['ProgramLifecycleResponse'];
type ProgramLifecycleAction = ApiSchemas['ProgramLifecycleActionRequest']['action'];
type ProgramLifecycleMutation = ApiSchemas['ProgramLifecycleMutationResponse'];

const changeLabels: Record<ProgramRevision['change_kind'], string> = {
  assigned: 'Программа назначена',
  program_archived: 'Программа отправлена в архив',
  plan_updated: 'План тренировок изменён',
  block_created: 'Добавлен тренировочный блок',
  block_updated: 'Тренировочный блок изменён',
  block_status_changed: 'Изменён статус тренировочного блока',
  program_lifecycle: 'Изменён жизненный цикл программы',
  program_restarted: 'Начат новый цикл программы',
};

const programStatusLabels: Record<ProgramLifecycleSummary['status'], string> = {
  scheduled: 'Запланирована',
  active: 'Выполняется',
  paused: 'На паузе',
  completed: 'Завершена',
  terminated: 'Прекращена',
  archived: 'В архиве',
};

function revisionChangeLabel(revision: ProgramRevision): string {
  if (revision.change_kind === 'plan_updated') {
    if (revision.changed_fields.operation === 'exercise_replaced') return 'Упражнение заменено';
    if (revision.changed_fields.operation === 'prescription_updated') {
      return 'Предписание упражнения изменено';
    }
  }
  return changeLabels[revision.change_kind];
}

const actorLabels: Record<ProgramRevision['actor_role'], string> = {
  self: 'Вы',
  trainer: 'Тренер',
  admin: 'Администратор',
  system: 'Система',
};

function addDays(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function earlierDate(left: string, right: string): string {
  return left <= right ? left : right;
}

function returnContext(programId: number): { revision: number | null; shouldOpen: boolean } {
  const params = new URLSearchParams(window.location.search);
  if (params.get('program_history') !== String(programId)) {
    return { revision: null, shouldOpen: false };
  }
  const value = params.get('program_revision');
  const revision = value && /^\d+$/.test(value) ? Number(value) : null;
  return { revision, shouldOpen: true };
}

function historyReturnPath(basePath: string, programId: number, revisionNumber: number): string {
  const parsed = new URL(basePath, window.location.origin);
  parsed.searchParams.set('program_history', String(programId));
  parsed.searchParams.set('program_revision', String(revisionNumber));
  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}

function workoutPath(
  workoutId: number,
  programId: number,
  revisionNumber: number,
  returnTo: string,
): string {
  const params = new URLSearchParams({
    section: 'progress',
    workout_id: String(workoutId),
    program_history: String(programId),
    program_revision: String(revisionNumber),
    return_to: returnTo,
  });
  return `/app?${params.toString()}`;
}

function queryErrorMessage(error: unknown): string {
  if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
    return 'История недоступна. Возможно, доступ тренера к программе был отозван.';
  }
  return error instanceof Error ? error.message : 'Повторите попытку позже.';
}

interface BlockFormValue {
  title: string;
  startDate: string;
  endDate: string;
  purpose: string;
  notes: string;
  isDeload: boolean;
  reason: string;
}

function BlockForm({
  block,
  endLimit,
  isPending,
  onCancel,
  onSubmit,
  startLimit,
}: {
  block?: TrainingBlock;
  endLimit: string;
  isPending: boolean;
  onCancel: () => void;
  onSubmit: (value: BlockFormValue) => void;
  startLimit: string;
}) {
  const initialValue = useMemo<BlockFormValue>(
    () => ({
      title: block?.title ?? 'Основной блок',
      startDate: block?.start_date ?? startLimit,
      endDate: block?.end_date ?? earlierDate(addDays(startLimit, 27), endLimit),
      purpose: block?.purpose ?? 'Последовательно выполнять программу',
      notes: block?.notes ?? '',
      isDeload: block?.is_deload ?? false,
      reason: '',
    }),
    [block, endLimit, startLimit],
  );
  const [value, setValue] = useState(initialValue);
  const changed =
    !block ||
    value.title.trim() !== block.title ||
    value.startDate !== block.start_date ||
    value.endDate !== block.end_date ||
    value.purpose.trim() !== block.purpose ||
    value.notes.trim() !== (block.notes ?? '') ||
    value.isDeload !== block.is_deload;
  const invalid =
    !value.title.trim() ||
    !value.purpose.trim() ||
    !value.reason.trim() ||
    value.endDate < value.startDate ||
    !changed;
  const prefix = block ? `program-block-${block.id}` : 'program-block-new';

  return (
    <form
      className="program-block-editor"
      onSubmit={(event) => {
        event.preventDefault();
        if (!invalid) onSubmit(value);
      }}
    >
      <Field label="Название этапа" labelFor={`${prefix}-title`}>
        <Input
          id={`${prefix}-title`}
          maxLength={128}
          value={value.title}
          onChange={(event) => setValue((current) => ({ ...current, title: event.target.value }))}
          required
        />
      </Field>
      <Field label="Начало" labelFor={`${prefix}-start`}>
        <DateInput
          id={`${prefix}-start`}
          min={startLimit}
          max={endLimit}
          value={value.startDate}
          onChange={(event) =>
            setValue((current) => ({ ...current, startDate: event.target.value }))
          }
          required
        />
      </Field>
      <Field label="Окончание" labelFor={`${prefix}-end`}>
        <DateInput
          id={`${prefix}-end`}
          min={value.startDate}
          max={endLimit}
          value={value.endDate}
          onChange={(event) => setValue((current) => ({ ...current, endDate: event.target.value }))}
          required
        />
      </Field>
      <Field label="Цель этапа" labelFor={`${prefix}-purpose`}>
        <Input
          id={`${prefix}-purpose`}
          maxLength={500}
          value={value.purpose}
          onChange={(event) => setValue((current) => ({ ...current, purpose: event.target.value }))}
          required
        />
      </Field>
      <Field label="Заметка (необязательно)" labelFor={`${prefix}-notes`}>
        <textarea
          className="ui-input"
          id={`${prefix}-notes`}
          maxLength={2000}
          value={value.notes}
          onChange={(event) => setValue((current) => ({ ...current, notes: event.target.value }))}
        />
      </Field>
      <label className="program-block-editor__check">
        <input
          type="checkbox"
          checked={value.isDeload}
          onChange={(event) =>
            setValue((current) => ({ ...current, isDeload: event.target.checked }))
          }
        />
        <span>Это облегчённый период со сниженной нагрузкой</span>
      </label>
      <Field
        label="Почему меняется программа"
        labelFor={`${prefix}-reason`}
        hint="Эта причина останется в истории программы."
      >
        <Input
          id={`${prefix}-reason`}
          maxLength={500}
          value={value.reason}
          onChange={(event) => setValue((current) => ({ ...current, reason: event.target.value }))}
          required
        />
      </Field>
      <div className="program-block-editor__actions">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Отменить
        </Button>
        <Button disabled={isPending || invalid} type="submit">
          {isPending ? 'Сохраняем…' : block ? 'Сохранить изменения' : 'Добавить этап'}
        </Button>
      </div>
    </form>
  );
}

export function AssignedProgramDetails({
  programId,
  currentRevisionNumber,
  startDate,
  durationWeeks,
  showAiAdaptation = false,
  workoutHistoryReturnPath,
}: {
  programId: number;
  currentRevisionNumber: number;
  startDate: string;
  durationWeeks: number;
  showAiAdaptation?: boolean;
  workoutHistoryReturnPath?: string;
}) {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const initialReturn = useMemo(() => returnContext(programId), [programId]);
  const [historyOpen, setHistoryOpen] = useState(initialReturn.shouldOpen);
  const [mutationRevisionNumber, setMutationRevisionNumber] = useState(currentRevisionNumber);
  const [editingBlock, setEditingBlock] = useState<TrainingBlock | 'new' | null>(null);
  const [historyReason, setHistoryReason] = useState('');
  const [lifecycleActionsOpen, setLifecycleActionsOpen] = useState(false);
  const [dismissedProposals, setDismissedProposals] = useState<Set<string>>(() => new Set());
  const [adjustedWeights, setAdjustedWeights] = useState<Record<string, string>>({});
  const returnedRevisionRef = useRef<HTMLDetailsElement>(null);
  const programEndDate = useMemo(
    () => addDays(startDate, Math.max(1, durationWeeks) * 7 - 1),
    [durationWeeks, startDate],
  );

  const revisions = useQuery({
    queryKey: ['assigned-program', programId, 'revisions'],
    queryFn: () => api<ProgramRevision[]>(`/api/v1/programs/assigned/${programId}/revisions`),
    enabled: historyOpen,
  });
  const lifecycle = useQuery({
    queryKey: ['assigned-program', programId, 'lifecycle'],
    queryFn: () => api<ProgramLifecycleSummary>(`/api/v1/programs/assigned/${programId}/lifecycle`),
  });
  const blocks = useQuery({
    queryKey: ['assigned-program', programId, 'blocks'],
    queryFn: () => api<TrainingBlock[]>(`/api/v1/programs/assigned/${programId}/blocks`),
  });
  const progressionProposals = useQuery({
    queryKey: ['assigned-program', programId, 'progression-proposals'],
    queryFn: () =>
      api<ProgressionProposalList>(`/api/v1/programs/assigned/${programId}/progression-proposals`),
    enabled: blocks.isSuccess,
  });
  const latestRevisionNumber = revisions.data?.[0]?.revision_number ?? 0;
  const revisionNumber = Math.max(
    currentRevisionNumber,
    mutationRevisionNumber,
    latestRevisionNumber,
    lifecycle.data?.current_revision_number ?? 0,
  );
  const primaryBlock = primaryTrainingBlock(blocks.data ?? []);
  const canManageProgram =
    lifecycle.data?.status === 'scheduled' || lifecycle.data?.status === 'active';
  const canRestartProgram = Boolean(lifecycle.data);

  const invalidateProgramContext = async () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['assigned-program', programId] }),
      queryClient.invalidateQueries({ queryKey: ['templates'] }),
      queryClient.invalidateQueries({ queryKey: ['coach', 'programs'] }),
      queryClient.invalidateQueries({ queryKey: ['workout'] }),
    ]);

  useEffect(() => {
    if (!initialReturn.revision || revisions.isLoading || !returnedRevisionRef.current) return;
    const frame = requestAnimationFrame(() => {
      returnedRevisionRef.current?.scrollIntoView({ block: 'center' });
      returnedRevisionRef.current?.querySelector<HTMLElement>('summary')?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [initialReturn.revision, revisions.data, revisions.isLoading]);

  const mutation = useMutation({
    mutationFn: ({ blockId, body }: { blockId?: number; body: Record<string, unknown> }) =>
      api<TrainingBlockMutation>(
        blockId
          ? `/api/v1/programs/assigned/${programId}/blocks/${blockId}`
          : `/api/v1/programs/assigned/${programId}/blocks`,
        { method: blockId ? 'PATCH' : 'POST', body },
      ),
    onSuccess: async (result, variables) => {
      setMutationRevisionNumber(result.current_revision_number);
      setEditingBlock(null);
      await invalidateProgramContext();
      toast(variables.blockId ? 'Тренировочный блок обновлён' : 'Тренировочный блок добавлен');
    },
    onError: async (reason) => {
      if (reason instanceof ApiError && reason.status === 409) {
        setEditingBlock(null);
        await invalidateProgramContext();
        toast(
          'Программа уже изменилась. Редактор закрыт, данные обновлены — откройте этап заново.',
          'error',
        );
        return;
      }
      toast(queryErrorMessage(reason), 'error');
    },
  });

  const lifecycleMutation = useMutation({
    mutationFn: ({ action, reason }: { action: ProgramLifecycleAction; reason: string }) =>
      api<ProgramLifecycleMutation>(`/api/v1/programs/assigned/${programId}/lifecycle`, {
        method: 'POST',
        body: {
          expected_revision_number: revisionNumber,
          action,
          reason,
        },
      }),
    onSuccess: async (result) => {
      setMutationRevisionNumber(result.current_revision_number);
      setHistoryReason('');
      setLifecycleActionsOpen(false);
      await invalidateProgramContext();
      toast(
        result.new_program_id
          ? 'Новый цикл создан, история исходной программы сохранена'
          : `Статус программы: ${programStatusLabels[result.status]}`,
      );
    },
    onError: async (reason) => {
      if (reason instanceof ApiError && reason.status === 409) {
        await invalidateProgramContext();
        toast('Программа уже изменилась. Данные обновлены.', 'error');
        return;
      }
      toast(queryErrorMessage(reason), 'error');
    },
  });

  const blockActionMutation = useMutation({
    mutationFn: ({
      blockId,
      action,
      reason,
    }: {
      blockId: number;
      action: 'advance' | 'repeat';
      reason: string;
    }) =>
      api<{ block: TrainingBlock; current_revision_number: number }>(
        `/api/v1/programs/assigned/${programId}/blocks/${blockId}/${action}`,
        {
          method: 'POST',
          body: { expected_revision_number: revisionNumber, reason },
        },
      ),
    onSuccess: async (result, variables) => {
      setMutationRevisionNumber(result.current_revision_number);
      setHistoryReason('');
      await invalidateProgramContext();
      toast(
        variables.action === 'advance'
          ? 'Следующий тренировочный блок начат'
          : 'Тренировочный блок добавлен в новый цикл недель',
      );
    },
    onError: async (reason) => {
      if (reason instanceof ApiError && reason.status === 409) {
        await invalidateProgramContext();
        toast('Программа или блок уже изменились. Данные обновлены.', 'error');
        return;
      }
      toast(queryErrorMessage(reason), 'error');
    },
  });

  const progressionReview = useMutation({
    mutationFn: ({
      exerciseId,
      proposalId,
      workoutId,
      decision,
      adjustedWeight,
      expectedSetVersions,
      expectedRevisionNumber,
    }: {
      exerciseId: number;
      proposalId: string;
      workoutId: number;
      decision: 'confirm' | 'reject' | 'adjust';
      adjustedWeight?: number;
      expectedSetVersions?: Record<number, number>;
      expectedRevisionNumber: number;
    }) =>
      api<ProgressionReviewResponse>(
        `/api/v1/programs/assigned/${programId}/progression-proposals/${proposalId}/review`,
        {
          method: 'POST',
          body: {
            decision,
            workout_id: workoutId,
            exercise_id: exerciseId,
            expected_revision_number: expectedRevisionNumber,
            adjusted_weight: adjustedWeight,
            expected_set_versions: expectedSetVersions ?? {},
          },
        },
      ),
    onSuccess: async (_result, variables) => {
      if (variables.decision === 'reject') {
        setDismissedProposals((current) => new Set(current).add(variables.proposalId));
      }
      await queryClient.invalidateQueries({
        queryKey: ['assigned-program', programId, 'progression-proposals'],
      });
      toast(
        variables.decision === 'reject'
          ? 'Предложение отклонено, текущая нагрузка сохранена'
          : 'Предложенная нагрузка добавлена в незавершённые подходы',
      );
    },
    onError: async (reason) => {
      if (reason instanceof ApiError && reason.status === 409) {
        await queryClient.invalidateQueries({
          queryKey: ['assigned-program', programId, 'progression-proposals'],
        });
        toast('Программа или подход изменились. Данные обновлены.', 'error');
        return;
      }
      toast(queryErrorMessage(reason), 'error');
    },
  });

  const updateBlockStatus = (block: TrainingBlock, status: TrainingBlock['status']) =>
    mutation.mutate({
      blockId: block.id,
      body: {
        expected_revision_number: revisionNumber,
        status,
        reason:
          status === 'active'
            ? `Этап «${block.title}» начат по плану`
            : status === 'completed'
              ? `Этап «${block.title}» завершён`
              : `Этап «${block.title}» перенесён в архив`,
      },
    });

  const applyLifecycleAction = (action: ProgramLifecycleAction) => {
    const reason = historyReason.trim();
    if (!reason) return;
    const confirmation =
      action === 'complete'
        ? 'Завершить программу? Будущие запланированные тренировки будут отменены.'
        : action === 'terminate'
          ? 'Прекратить программу? Будущие запланированные тренировки будут отменены.'
          : action === 'restart'
            ? 'Начать новый цикл? Исходная история останется отдельной программой.'
            : null;
    if (confirmation && !window.confirm(confirmation)) return;
    lifecycleMutation.mutate({ action, reason });
  };

  const blockActions = (block: TrainingBlock) => {
    if (!canManageProgram || block.status === 'archived') return null;
    const busy = mutation.isPending || blockActionMutation.isPending;
    if (block.status === 'completed') {
      return (
        <div className="program-block-actions">
          <Button
            type="button"
            variant="secondary"
            disabled={busy || !historyReason.trim()}
            onClick={() => {
              if (!window.confirm(`Повторить блок «${block.title}» в новых неделях?`)) return;
              blockActionMutation.mutate({
                blockId: block.id,
                action: 'repeat',
                reason: historyReason.trim(),
              });
            }}
          >
            Повторить блок
          </Button>
        </div>
      );
    }
    return (
      <div className="program-block-actions">
        {block.status === 'active' && lifecycle.data?.next_block && (
          <Button
            type="button"
            variant="secondary"
            disabled={busy || !historyReason.trim()}
            onClick={() =>
              blockActionMutation.mutate({
                blockId: block.id,
                action: 'advance',
                reason: historyReason.trim(),
              })
            }
          >
            Перейти к следующему блоку
          </Button>
        )}
        {block.status === 'planned' && (
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={() => updateBlockStatus(block, 'active')}
          >
            Начать этап
          </Button>
        )}
        {block.status === 'active' && (
          <Button
            type="button"
            variant="secondary"
            disabled={mutation.isPending}
            onClick={() => updateBlockStatus(block, 'completed')}
          >
            Завершить этап
          </Button>
        )}
        <Button type="button" variant="ghost" onClick={() => setEditingBlock(block)}>
          Изменить
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={busy}
          onClick={() => updateBlockStatus(block, 'archived')}
        >
          В архив
        </Button>
      </div>
    );
  };

  return (
    <section className="program-history" aria-labelledby={`program-history-${programId}`}>
      <div className="program-history__intro">
        <div>
          <span className="eyebrow">Эволюция программы</span>
          <h3 id={`program-history-${programId}`}>Текущий этап и история</h3>
        </div>
        <span className="program-history__version">Версия {revisionNumber}</span>
      </div>

      {lifecycle.isLoading ? (
        <LoadingState label="Загружаем состояние программы…" />
      ) : lifecycle.error instanceof ApiError &&
        (lifecycle.error.status === 403 ||
          lifecycle.error.status === 404) ? null : lifecycle.error ? (
        <ErrorState
          message={queryErrorMessage(lifecycle.error)}
          retry={() => void lifecycle.refetch()}
        />
      ) : lifecycle.data ? (
        <>
          <article className="program-lifecycle" aria-label="Жизненный цикл программы">
            <div className="program-lifecycle__summary">
              <div className="program-lifecycle__status">
                <Badge
                  tone={
                    lifecycle.data.status === 'active'
                      ? 'success'
                      : lifecycle.data.status === 'paused'
                        ? 'warning'
                        : 'neutral'
                  }
                >
                  {programStatusLabels[lifecycle.data.status]}
                </Badge>
                <strong>
                  {lifecycle.data.current_week_number
                    ? `Неделя ${lifecycle.data.current_week_number} из ${lifecycle.data.duration_weeks}`
                    : `${lifecycle.data.duration_weeks} нед.`}
                </strong>
              </div>
              <div className="program-lifecycle__next">
                <span>Следующая тренировка</span>
                {lifecycle.data.next_workout ? (
                  <strong>
                    {lifecycle.data.next_workout.title} ·{' '}
                    {formatProgramDate(lifecycle.data.next_workout.scheduled_date)}
                  </strong>
                ) : (
                  <strong>Не запланирована</strong>
                )}
              </div>
            </div>
            {(lifecycle.data.next_block || lifecycle.data.next_deload) && (
              <div className="program-lifecycle__upcoming">
                {lifecycle.data.next_block && (
                  <span>
                    Дальше: {lifecycle.data.next_block.title} · неделя{' '}
                    {lifecycle.data.next_block.week_start ?? '—'}
                  </span>
                )}
                {lifecycle.data.next_deload && (
                  <span>
                    <Badge tone="warning">
                      {lifecycle.data.next_deload.status === 'active'
                        ? 'Идёт облегчённый блок'
                        : 'Запланирован облегчённый блок'}
                    </Badge>{' '}
                    {formatProgramDate(lifecycle.data.next_deload.start_date)}
                  </span>
                )}
              </div>
            )}
            <details
              className="program-lifecycle__controls"
              open={lifecycleActionsOpen}
              onToggle={(event) => setLifecycleActionsOpen(event.currentTarget.open)}
            >
              <summary>
                <span>Действия с программой</span>
                <DisclosureIcon />
              </summary>
              <div className="program-lifecycle__actions">
                <div className="program-lifecycle__buttons">
                  {canManageProgram && (
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={lifecycleMutation.isPending || !historyReason.trim()}
                      onClick={() => applyLifecycleAction('pause')}
                    >
                      Приостановить
                    </Button>
                  )}
                  {lifecycle.data.status === 'paused' && (
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={lifecycleMutation.isPending || !historyReason.trim()}
                      onClick={() => applyLifecycleAction('resume')}
                    >
                      Продолжить
                    </Button>
                  )}
                  {(canManageProgram || lifecycle.data.status === 'paused') && (
                    <>
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={lifecycleMutation.isPending || !historyReason.trim()}
                        onClick={() => applyLifecycleAction('complete')}
                      >
                        Завершить программу
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={lifecycleMutation.isPending || !historyReason.trim()}
                        onClick={() => applyLifecycleAction('terminate')}
                      >
                        Прекратить программу
                      </Button>
                    </>
                  )}
                  {canRestartProgram && (
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={lifecycleMutation.isPending || !historyReason.trim()}
                      onClick={() => applyLifecycleAction('restart')}
                    >
                      Начать новый цикл
                    </Button>
                  )}
                </div>
              </div>
            </details>
          </article>
        </>
      ) : null}

      {blocks.isLoading ? (
        <LoadingState label="Загружаем текущий этап…" />
      ) : blocks.error ? (
        <ErrorState message={queryErrorMessage(blocks.error)} retry={() => void blocks.refetch()} />
      ) : primaryBlock ? (
        <article className={`program-current-block is-${primaryBlock.status}`}>
          <div className="program-current-block__topline">
            <span>{primaryBlockHeading(primaryBlock)}</span>
            <Badge tone={primaryBlock.status === 'active' ? 'success' : 'neutral'}>
              {blockStatusLabel(primaryBlock.status)}
            </Badge>
          </div>
          <div className="program-current-block__content">
            <div>
              <h4>{primaryBlock.title}</h4>
              <p>{primaryBlock.purpose}</p>
            </div>
            <dl className="program-current-block__facts">
              <div>
                <dt>Период</dt>
                <dd>
                  {formatProgramDate(primaryBlock.start_date)} —{' '}
                  {formatProgramDate(primaryBlock.end_date)}
                </dd>
              </div>
              <div>
                <dt>Длительность</dt>
                <dd>{primaryBlock.duration_days} дн.</dd>
              </div>
            </dl>
          </div>
          {primaryBlock.notes && (
            <p className="program-current-block__note">{primaryBlock.notes}</p>
          )}
          {primaryBlock.is_deload && <Badge tone="warning">Облегчённый период</Badge>}
          <details className="program-current-block__actions">
            <summary>Действия с этапом</summary>
            {blockActions(primaryBlock)}
          </details>
        </article>
      ) : (
        <EmptyState
          title="Тренировочные блоки ещё не настроены"
          text="Программа продолжает работать. Добавьте первый этап, чтобы зафиксировать его цель и период."
        />
      )}

      {lifecycle.data && (
        <div className="program-lifecycle__reason">
          <Field
            label="Причина для истории"
            labelFor={`program-lifecycle-reason-${programId}`}
            hint="Причина сохранится вместе с изменением программы или этапа."
          >
            <Input
              id={`program-lifecycle-reason-${programId}`}
              maxLength={500}
              value={historyReason}
              onChange={(event) => setHistoryReason(event.target.value)}
              required
            />
          </Field>
        </div>
      )}

      {showAiAdaptation && canManageProgram && (
        <AiAdaptationProposal
          programId={programId}
          revisionNumber={revisionNumber}
          targetWorkoutId={lifecycle.data?.next_workout?.id}
          onApplied={(nextRevisionNumber) => {
            setMutationRevisionNumber(nextRevisionNumber);
            void invalidateProgramContext();
          }}
        />
      )}

      <section
        className="program-history__region progression-proposals"
        aria-labelledby={`progression-proposals-${programId}`}
        hidden={!blocks.isSuccess}
      >
        <div className="program-history__heading">
          <div>
            <h4 id={`progression-proposals-${programId}`}>Предложение на ближайшую тренировку</h4>
            <p>Изменение попадёт в незавершённые подходы только после подтверждения.</p>
          </div>
        </div>
        {progressionProposals.isLoading ? (
          <LoadingState label="Проверяем результаты тренировок…" />
        ) : progressionProposals.error ? (
          progressionProposals.error instanceof ApiError &&
          progressionProposals.error.status === 409 ? (
            <p className="program-history__quiet">
              Нет ближайшей тренировки для предложения прогрессии.
            </p>
          ) : (
            <ErrorState
              message={queryErrorMessage(progressionProposals.error)}
              retry={() => void progressionProposals.refetch()}
            />
          )
        ) : progressionProposals.data?.exercises.length ? (
          <div className="progression-proposals__items">
            {progressionProposals.data.exercises.map((item) => {
              const proposal = item.guidance.proposal;
              if (!proposal || dismissedProposals.has(proposal.proposal_id)) return null;
              const updates = proposal.target_set_updates ?? [];
              const expectedSetVersions = Object.fromEntries(
                updates.map((update) => [update.set_id, update.set_version]),
              );
              const adjustedWeight =
                adjustedWeights[proposal.proposal_id] ?? String(proposal.proposed_weight ?? '');
              const alreadyApplied =
                updates.length > 0 &&
                updates.every((update) => update.current_weight === update.proposed_weight);
              return (
                <article className="progression-proposals__item" key={item.exercise_id}>
                  <h5>{item.exercise_title}</h5>
                  <ProgressionGuidance
                    applied={alreadyApplied}
                    exerciseKey={item.exercise_id}
                    guidance={item.guidance}
                    onApply={
                      proposal.eligibility_status === 'eligible'
                        ? () =>
                            progressionReview.mutate({
                              exerciseId: item.exercise_id,
                              proposalId: proposal.proposal_id,
                              workoutId: proposal.target_workout_id,
                              decision: 'confirm',
                              expectedRevisionNumber: proposal.target_revision_number,
                              expectedSetVersions,
                            })
                        : undefined
                    }
                    onDismiss={() =>
                      progressionReview.mutate({
                        exerciseId: item.exercise_id,
                        proposalId: proposal.proposal_id,
                        workoutId: proposal.target_workout_id,
                        decision: 'reject',
                        expectedRevisionNumber: proposal.target_revision_number,
                      })
                    }
                  />
                  {proposal.eligibility_status === 'eligible' && canManageProgram && (
                    <div className="progression-proposals__adjust">
                      <Field
                        label="Изменить предложенный вес, кг"
                        labelFor={`progression-adjust-${proposal.proposal_id}`}
                        hint="Тренерское или пользовательское изменение применится к незавершённым подходам."
                      >
                        <Input
                          id={`progression-adjust-${proposal.proposal_id}`}
                          type="number"
                          min="0.01"
                          max="100000"
                          step="any"
                          value={adjustedWeight}
                          onChange={(event) =>
                            setAdjustedWeights((current) => ({
                              ...current,
                              [proposal.proposal_id]: event.target.value,
                            }))
                          }
                        />
                      </Field>
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={
                          progressionReview.isPending ||
                          !Number.isFinite(Number(adjustedWeight)) ||
                          Number(adjustedWeight) <= 0
                        }
                        onClick={() =>
                          progressionReview.mutate({
                            exerciseId: item.exercise_id,
                            proposalId: proposal.proposal_id,
                            workoutId: proposal.target_workout_id,
                            decision: 'adjust',
                            adjustedWeight: Number(adjustedWeight),
                            expectedRevisionNumber: proposal.target_revision_number,
                            expectedSetVersions,
                          })
                        }
                      >
                        Применить изменённый вес
                      </Button>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        ) : (
          <p className="program-history__quiet">Для ближайшей тренировки нет предложений.</p>
        )}
      </section>

      <details className="program-history__disclosure" open={historyOpen}>
        <summary
          onClick={(event) => {
            event.preventDefault();
            setHistoryOpen((open) => !open);
          }}
        >
          <span className="program-history__summary-copy">
            <strong>Все этапы и изменения</strong>
            <small>Кто, когда и почему менял программу</small>
          </span>
          <DisclosureIcon />
        </summary>
        <div className="program-history__body">
          <section className="program-history__region" aria-labelledby={`blocks-${programId}`}>
            <div className="program-history__heading">
              <div>
                <h4 id={`blocks-${programId}`}>Тренировочные блоки</h4>
                <p>Текущий, будущие и архивные этапы в хронологическом порядке.</p>
              </div>
              {canManageProgram && (
                <Button type="button" variant="secondary" onClick={() => setEditingBlock('new')}>
                  Добавить этап
                </Button>
              )}
            </div>

            {editingBlock && (
              <BlockForm
                key={editingBlock === 'new' ? 'new' : editingBlock.id}
                block={editingBlock === 'new' ? undefined : editingBlock}
                endLimit={programEndDate}
                isPending={mutation.isPending}
                startLimit={startDate}
                onCancel={() => setEditingBlock(null)}
                onSubmit={(value) => {
                  const body = {
                    expected_revision_number: revisionNumber,
                    title: value.title.trim(),
                    start_date: value.startDate,
                    end_date: value.endDate,
                    purpose: value.purpose.trim(),
                    notes: value.notes.trim() || null,
                    is_deload: value.isDeload,
                    reason: value.reason.trim(),
                    ...(editingBlock === 'new' ? { priority_muscle_ids: [] } : {}),
                  };
                  mutation.mutate({
                    blockId: editingBlock === 'new' ? undefined : editingBlock.id,
                    body,
                  });
                }}
              />
            )}

            {!blocks.data?.length ? (
              <p className="program-history__quiet">После добавления этап появится здесь.</p>
            ) : (
              <ol className="program-block-timeline">
                {blocks.data.map((block) => (
                  <li className={block.id === primaryBlock?.id ? 'is-current' : ''} key={block.id}>
                    <span className="program-block-timeline__rail" aria-hidden="true" />
                    <details>
                      <summary>
                        <span className="program-block-timeline__copy">
                          <strong>{block.title}</strong>
                          <small>
                            {formatProgramDate(block.start_date)} —{' '}
                            {formatProgramDate(block.end_date)}
                          </small>
                        </span>
                        <Badge tone={block.status === 'active' ? 'success' : 'neutral'}>
                          {blockStatusLabel(block.status)}
                        </Badge>
                        <DisclosureIcon />
                      </summary>
                      <div className="program-block-timeline__details">
                        <p>{block.purpose}</p>
                        {block.notes && <p className="muted">{block.notes}</p>}
                        {block.is_deload && <Badge tone="warning">Облегчённый период</Badge>}
                        {block.id !== primaryBlock?.id && blockActions(block)}
                      </div>
                    </details>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="program-history__region" aria-labelledby={`history-${programId}`}>
            <div className="program-history__heading">
              <div>
                <h4 id={`history-${programId}`}>История изменений</h4>
                <p>Каждая версия хранит причину, автора и фактический снимок плана.</p>
              </div>
            </div>
            {revisions.isLoading ? (
              <LoadingState label="Загружаем историю…" />
            ) : revisions.error ? (
              <ErrorState
                message={queryErrorMessage(revisions.error)}
                retry={() => void revisions.refetch()}
              />
            ) : !revisions.data?.length ? (
              <EmptyState
                title="История появится после первого сохранённого изменения"
                text="Для старых программ без ревизий приложение не придумывает прошлые события."
              />
            ) : (
              <ol className="program-revision-timeline">
                {revisions.data.map((revision, index) => {
                  const presentation = buildRevisionPresentation(
                    revision,
                    revisions.data[index + 1],
                  );
                  const returnTo = workoutHistoryReturnPath
                    ? historyReturnPath(
                        workoutHistoryReturnPath,
                        programId,
                        revision.revision_number,
                      )
                    : null;
                  const returned = initialReturn.revision === revision.revision_number;
                  return (
                    <li key={revision.id}>
                      <span className="program-revision-timeline__rail" aria-hidden="true" />
                      <details
                        id={`program-revision-${programId}-${revision.revision_number}`}
                        ref={
                          returned
                            ? (element) => {
                                returnedRevisionRef.current = element;
                                if (element) element.open = true;
                              }
                            : undefined
                        }
                      >
                        <summary>
                          <span className="program-revision-timeline__copy">
                            <strong>{revisionChangeLabel(revision)}</strong>
                            <small>
                              {actorLabels[revision.actor_role]} ·{' '}
                              {formatRevisionMoment(revision.created_at)}
                            </small>
                          </span>
                          <Badge>v{revision.revision_number}</Badge>
                          <DisclosureIcon />
                        </summary>
                        <div className="program-revision-timeline__details">
                          <div className="program-revision-reason">
                            <strong>Причина</strong>
                            <p>{revision.reason || 'Причина не указана.'}</p>
                          </div>
                          {presentation.differences.length ? (
                            <dl className="program-revision-diff" aria-label="Что изменилось">
                              {presentation.differences.map((difference) => (
                                <div
                                  key={`${difference.label}-${difference.before}-${difference.after}`}
                                >
                                  <dt>{difference.label}</dt>
                                  <dd>
                                    <span>{difference.before}</span>
                                    <Icon name="arrow-right" size={16} />
                                    <strong>{difference.after}</strong>
                                  </dd>
                                </div>
                              ))}
                            </dl>
                          ) : (
                            <p className="program-history__quiet">
                              Снимок версии сохранён; дополнительных различий для показа нет.
                            </p>
                          )}
                          {presentation.workoutContextLabel && (
                            <div className="program-revision-workouts">
                              <strong>{presentation.workoutContextLabel}</strong>
                              {presentation.workouts.length ? (
                                <ul>
                                  {presentation.workouts.map((workout) => (
                                    <li key={workout.id}>
                                      {returnTo ? (
                                        <AppLink
                                          to={workoutPath(
                                            workout.id,
                                            programId,
                                            revision.revision_number,
                                            returnTo,
                                          )}
                                        >
                                          <span>
                                            <strong>{workout.title}</strong>
                                            <small>
                                              {formatProgramDate(workout.scheduledDate)} ·{' '}
                                              {workoutStatusLabel(workout.status)}
                                            </small>
                                          </span>
                                          <span>Открыть</span>
                                        </AppLink>
                                      ) : (
                                        <span>
                                          <strong>{workout.title}</strong>
                                          <small>
                                            {formatProgramDate(workout.scheduledDate)} ·{' '}
                                            {workoutStatusLabel(workout.status)}
                                          </small>
                                        </span>
                                      )}
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="program-history__quiet">
                                  В этом периоде не было материализованных тренировок.
                                </p>
                              )}
                            </div>
                          )}
                        </div>
                      </details>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>
        </div>
      </details>
    </section>
  );
}
