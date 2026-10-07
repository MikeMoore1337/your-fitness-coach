import { useState, type FormEvent } from 'react';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import type {
  ApiSchemas,
  Client,
  CoachAssignedProgram,
  Exercise,
  ProgramTemplate,
} from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import {
  Badge,
  Button,
  EmptyState,
  Field,
  Input,
  LoadingState,
  Select,
} from '../../shared/ui/common';

type RevisionScope = ApiSchemas['CoachProgramExerciseCreate']['effective_scope'];
type ProposalList = ApiSchemas['ProgramProgressionProposalList'];
type ProposalExercise = ApiSchemas['ProgramProgressionProposalExercise'];
type Proposal = NonNullable<ProposalExercise['guidance']['proposal']>;
type RevisionResponse = ApiSchemas['CoachProgramExerciseAssignmentResponse'];
type ReviewResponse = ApiSchemas['ProgressionProposalReviewResponse'];
type RolloutPreview = ApiSchemas['CoachProgramRolloutPreviewResponse'];
type RolloutResult = ApiSchemas['CoachProgramRolloutResult'];

type ProgramTarget = {
  clientName: string;
  program: CoachAssignedProgram;
};

type ActionOutcome = {
  clientId: number;
  clientName: string;
  status: 'updated' | 'failed';
  message: string;
};

type ProposalCandidate = {
  target: ProgramTarget;
  exercise: ProposalExercise;
  proposal: Proposal;
  loadUnit: 'kg' | 'lb';
  scheduledDate: string;
};

type CommonRevisionCommand = {
  targets: ProgramTarget[];
  exercise: Exercise;
  scope: RevisionScope;
  dayNumber: number;
  effectiveDate: string;
  sets: number;
  reps: string;
  durationMinutes: number;
  restSeconds: number;
  reason: string;
};

function clientName(client: Client): string {
  const name = client.full_name?.trim();
  const username = client.username?.trim();
  if (name && username) return `${name} · @${username}`;
  return name || (username ? `@${username}` : `Клиент ${client.id}`);
}

function resultMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) {
    return 'Данные программы или тренировки изменились. Обновите и проверьте предложение.';
  }
  if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
    return 'Программа клиента больше недоступна.';
  }
  return 'Изменение не выполнено. Обновите данные и повторите.';
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) =>
      left < right ? -1 : left > right ? 1 : 0,
    );
    return `{${entries
      .map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`)
      .join(',')}}`;
  }
  return JSON.stringify(value) ?? 'null';
}

function proposalClass(candidate: ProposalCandidate): string {
  const { exercise, proposal } = candidate;
  return stableJson({
    exerciseId: exercise.exercise_id,
    loadUnit: candidate.loadUnit,
    ruleKind: proposal.rule_kind,
    ruleSnapshot: proposal.rule_snapshot,
    action: proposal.proposed_action,
    currentWeight: proposal.current_weight,
    proposedWeight: proposal.proposed_weight,
    deloadVolumePercent: proposal.deload_volume_percent,
    deloadIntensityPercent: proposal.deload_intensity_percent,
    reasonCodes: [...proposal.reason_codes].sort(),
    updates: (proposal.target_set_updates ?? []).map((item) => ({
      setNumber: item.set_number,
      plannedRole: item.planned_role,
      currentWeight: item.current_weight,
      proposedWeight: item.proposed_weight,
      relativeToTop: item.relative_to_top,
    })),
  });
}

function proposalActionLabel(proposal: Proposal, unit: 'kg' | 'lb'): string {
  if (proposal.proposed_action === 'set_load' && proposal.proposed_weight != null) {
    return `нагрузка ${proposal.proposed_weight} ${unit === 'kg' ? 'кг' : 'фунт'}`;
  }
  return proposal.proposed_action;
}

function formatDate(value: string): string {
  return `${value.slice(8, 10)}.${value.slice(5, 7)}.${value.slice(0, 4)}`;
}

function rolloutClassificationLabel(
  value: ApiSchemas['CoachProgramRolloutClientPreview']['classification'],
): string {
  return {
    compatible: 'Совместимо',
    personalization_required: 'Нужна персонализация',
    manual_review_required: 'Нужна ручная проверка',
  }[value];
}

function rolloutChangeLabel(value: ApiSchemas['CoachProgramRolloutDiff']['change']): string {
  return { added: 'добавить', updated: 'обновить', removed: 'убрать' }[value];
}

function rolloutReasonLabels(codes: string[]): string {
  const labels: Record<string, string> = {
    already_current: 'План уже совпадает с шаблоном.',
    duration_mismatch: 'Длительность шаблона не совпадает с программой.',
    schedule_mismatch: 'Расписание программы требует ручной проверки.',
    in_progress_workout: 'Есть тренировка в процессе.',
    no_future_workouts: 'Нет будущих запланированных тренировок.',
    exercise_unavailable: 'Упражнение нужно персонализировать для клиента.',
    exercise_replacement: 'Замена упражнения требует ручной проверки.',
    future_exercise_removal: 'Удаление будущего упражнения требует ручной проверки.',
    new_exercises: 'Есть новые упражнения.',
    prescription_changes: 'Есть изменения назначения.',
    no_active_program: 'У клиента нет активной программы тренера.',
  };
  return codes.map((code) => labels[code] ?? code).join(' ');
}

export function CoachProgramBulkOperations({
  programs,
  selectedClients,
  selectedTemplate,
}: {
  programs: CoachAssignedProgram[];
  selectedClients: Client[];
  selectedTemplate?: ProgramTemplate;
}) {
  const { confirm, toast } = useFeedback();
  const queryClient = useQueryClient();
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [proposalOpen, setProposalOpen] = useState(false);
  const [revisionScope, setRevisionScope] = useState<RevisionScope>('next_workout');
  const [exerciseId, setExerciseId] = useState('');
  const [dayNumber, setDayNumber] = useState(1);
  const [effectiveDate, setEffectiveDate] = useState('');
  const [sets, setSets] = useState(3);
  const [reps, setReps] = useState('8-12');
  const [durationMinutes, setDurationMinutes] = useState(20);
  const [restSeconds, setRestSeconds] = useState(90);
  const [reason, setReason] = useState('');
  const [rolloutReason, setRolloutReason] = useState(
    'Обновление будущего плана после проверки шаблона',
  );
  const [rolloutPreview, setRolloutPreview] = useState<RolloutPreview | null>(null);
  const [rolloutPreviewKey, setRolloutPreviewKey] = useState('');
  const [rolloutResults, setRolloutResults] = useState<RolloutResult[]>([]);
  const [rolloutResultsKey, setRolloutResultsKey] = useState('');
  const [revisionOutcomes, setRevisionOutcomes] = useState<ActionOutcome[]>([]);
  const [proposalOutcomes, setProposalOutcomes] = useState<ActionOutcome[]>([]);
  const selectedClientKey = selectedClients.map((client) => client.id ?? '').join(',');
  const rolloutSelectionKey = `${selectedTemplate?.id ?? ''}:${selectedClientKey}`;
  const currentRolloutPreview = rolloutPreviewKey === rolloutSelectionKey ? rolloutPreview : null;
  const currentRolloutResults = rolloutResultsKey === rolloutSelectionKey ? rolloutResults : [];

  const targets: ProgramTarget[] = selectedClients.flatMap((client) => {
    const program = programs.find((item) => item.client_id === client.id && item.is_active);
    return program ? [{ clientName: clientName(client), program }] : [];
  });
  const missingProgramNames = selectedClients
    .filter((client) => !targets.some((target) => target.program.client_id === client.id))
    .map(clientName);
  const commonDayCount = targets.length
    ? Math.min(...targets.map((target) => target.program.schedule_weekdays.length))
    : 0;
  const selectedDayNumber = Math.min(dayNumber, Math.max(1, commonDayCount));

  const exercises = useQuery({
    queryKey: ['exercises'],
    queryFn: () => api<Exercise[]>('/api/v1/programs/exercises'),
    enabled: revisionOpen,
  });
  const selectedExercise = exercises.data?.find((item) => String(item.id) === exerciseId);
  const lifecycles = useQueries({
    queries: targets.map(({ program }) => ({
      queryKey: ['assigned-program', program.id, 'lifecycle'],
      queryFn: () =>
        api<ApiSchemas['ProgramLifecycleResponse']>(
          `/api/v1/programs/assigned/${program.id}/lifecycle`,
        ),
      enabled: revisionOpen && revisionScope === 'current_block',
    })),
  });
  const allHaveActiveBlocks =
    lifecycles.length === targets.length &&
    lifecycles.length > 0 &&
    lifecycles.every(
      (query) => !query.isFetching && !query.isError && Boolean(query.data?.current_block),
    );

  const proposalQueries = useQueries({
    queries: targets.map(({ program }) => ({
      queryKey: ['assigned-program', program.id, 'progression-proposals'],
      queryFn: () =>
        api<ProposalList>(`/api/v1/programs/assigned/${program.id}/progression-proposals`),
      enabled: proposalOpen,
    })),
  });
  const proposalCandidates: ProposalCandidate[] = proposalQueries.flatMap((query, index) => {
    const target = targets[index];
    if (!target || !query.data) return [];
    return query.data.exercises.flatMap((exercise) => {
      const proposal = exercise.guidance.proposal;
      if (
        !proposal ||
        proposal.eligibility_status !== 'eligible' ||
        proposal.proposed_action !== 'set_load' ||
        !proposal.target_set_updates?.length
      ) {
        return [];
      }
      return [
        {
          target,
          exercise,
          proposal,
          loadUnit: exercise.guidance.load_unit,
          scheduledDate: query.data.scheduled_date,
        },
      ];
    });
  });
  const proposalGroups = Array.from(
    proposalCandidates.reduce((groups, candidate) => {
      const key = proposalClass(candidate);
      groups.set(key, [...(groups.get(key) ?? []), candidate]);
      return groups;
    }, new Map<string, ProposalCandidate[]>()),
  )
    .map(([, group]) => group)
    .filter(
      (group) =>
        group.length > 1 &&
        new Set(group.map((candidate) => candidate.target.program.client_id)).size === group.length,
    );

  const invalidateProgramData = async () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['coach', 'programs'] }),
      queryClient.invalidateQueries({ queryKey: ['assigned-program'] }),
      queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clientSummaries }),
    ]);

  const revisionMutation = useMutation({
    mutationFn: async (command: CommonRevisionCommand): Promise<ActionOutcome[]> =>
      Promise.all(
        command.targets.map(async ({ clientName: name, program }): Promise<ActionOutcome> => {
          try {
            await api<RevisionResponse>(
              `/api/v1/coach/clients/${program.client_id}/programs/${program.id}/exercises`,
              {
                method: 'POST',
                body: {
                  expected_revision_number: program.current_revision_number,
                  effective_scope: command.scope,
                  effective_date: command.scope === 'future_program' ? command.effectiveDate : null,
                  exercise_id: command.exercise.id,
                  day_number: command.scope === 'next_workout' ? null : command.dayNumber,
                  prescribed_sets: command.exercise.metric_type === 'cardio' ? null : command.sets,
                  prescribed_reps: command.exercise.metric_type === 'cardio' ? null : command.reps,
                  prescribed_duration_minutes:
                    command.exercise.metric_type === 'cardio' ? command.durationMinutes : null,
                  rest_seconds: command.exercise.metric_type === 'cardio' ? 0 : command.restSeconds,
                  reason: command.reason,
                },
              },
            );
            return {
              clientId: program.client_id,
              clientName: name,
              status: 'updated',
              message: 'Ревизия сохранена',
            };
          } catch (error) {
            return {
              clientId: program.client_id,
              clientName: name,
              status: 'failed',
              message: resultMessage(error),
            };
          }
        }),
      ),
    onSuccess: async (outcomes) => {
      setRevisionOutcomes(outcomes);
      await invalidateProgramData();
      const completed = outcomes.filter((item) => item.status === 'updated').length;
      const failed = outcomes.length - completed;
      toast(
        failed
          ? `Ревизий сохранено: ${completed}. Не выполнено: ${failed}; проверьте результат по клиентам.`
          : `Общая правка сохранена для ${completed} клиентов`,
        failed ? 'error' : 'success',
      );
      setReason('');
      setExerciseId('');
    },
    onError: () => toast('Не удалось выполнить общую правку программы.', 'error'),
  });

  const proposalMutation = useMutation({
    mutationFn: async (group: ProposalCandidate[]): Promise<ActionOutcome[]> =>
      Promise.all(
        group.map(async (candidate): Promise<ActionOutcome> => {
          const { proposal } = candidate;
          const expectedSetVersions = Object.fromEntries(
            (proposal.target_set_updates ?? []).map((update) => [
              update.set_id,
              update.set_version,
            ]),
          );
          try {
            await api<ReviewResponse>(
              `/api/v1/programs/assigned/${candidate.target.program.id}/progression-proposals/${proposal.proposal_id}/review`,
              {
                method: 'POST',
                body: {
                  decision: 'confirm',
                  workout_id: proposal.target_workout_id,
                  exercise_id: candidate.exercise.exercise_id,
                  expected_revision_number: proposal.target_revision_number,
                  expected_set_versions: expectedSetVersions,
                },
              },
            );
            return {
              clientId: candidate.target.program.client_id,
              clientName: candidate.target.clientName,
              status: 'updated',
              message: `Предложение подтверждено: ${candidate.exercise.exercise_title}`,
            };
          } catch (error) {
            return {
              clientId: candidate.target.program.client_id,
              clientName: candidate.target.clientName,
              status: 'failed',
              message: resultMessage(error),
            };
          }
        }),
      ),
    onSuccess: async (outcomes) => {
      setProposalOutcomes(outcomes);
      await invalidateProgramData();
      const completed = outcomes.filter((item) => item.status === 'updated').length;
      const failed = outcomes.length - completed;
      toast(
        failed
          ? `Предложений подтверждено: ${completed}. Не выполнено: ${failed}; проверьте результат по клиентам.`
          : `Одинаковые предложения подтверждены для ${completed} клиентов`,
        failed ? 'error' : 'success',
      );
    },
    onError: () => toast('Не удалось подтвердить предложения.', 'error'),
  });

  const rolloutPreviewMutation = useMutation({
    mutationFn: async (): Promise<RolloutPreview> => {
      if (!selectedTemplate || !selectedClients.length) {
        throw new Error('Выберите шаблон и клиентов');
      }
      return api<RolloutPreview>('/api/v1/coach/program-rollouts/preview', {
        method: 'POST',
        body: {
          template_id: selectedTemplate.id,
          client_ids: selectedClients.flatMap((client) => (client.id == null ? [] : [client.id])),
        },
      });
    },
    onSuccess: (preview) => {
      setRolloutPreview(preview);
      setRolloutPreviewKey(rolloutSelectionKey);
      setRolloutResults([]);
      setRolloutResultsKey('');
    },
    onError: () =>
      toast('Не удалось собрать предпросмотр rollout. Обновите данные и повторите.', 'error'),
  });

  const rolloutApplyMutation = useMutation({
    mutationFn: async ({
      preview,
      idempotencyKey,
    }: {
      preview: RolloutPreview;
      idempotencyKey: string;
    }) => {
      if (!selectedTemplate) throw new Error('Шаблон больше не выбран');
      const targets = preview.targets.flatMap((target) =>
        target.can_apply && target.program_id != null && target.current_revision_number != null
          ? [
              {
                client_id: target.client_id,
                program_id: target.program_id,
                expected_revision_number: target.current_revision_number,
              },
            ]
          : [],
      );
      return api<ApiSchemas['CoachProgramRolloutApplyResponse']>(
        '/api/v1/coach/program-rollouts/apply',
        {
          method: 'POST',
          headers: { 'Idempotency-Key': idempotencyKey },
          body: {
            template_id: selectedTemplate.id,
            template_fingerprint: preview.template_fingerprint,
            targets,
            confirmed: true,
            reason: rolloutReason.trim(),
            idempotency_key: idempotencyKey,
          },
        },
      );
    },
    onSuccess: async (result) => {
      setRolloutResults(result.results);
      setRolloutResultsKey(rolloutSelectionKey);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['coach', 'programs'] }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clientSummaries }),
      ]);
      toast(
        result.failed_count
          ? `Rollout применён: ${result.applied_count}. Не выполнено: ${result.failed_count}.`
          : `Rollout применён к ${result.applied_count} клиентам.`,
        result.failed_count ? 'error' : 'success',
      );
    },
    onError: () =>
      toast('Не удалось применить rollout. Обновите предпросмотр и повторите.', 'error'),
  });

  const scheduleCommonRevision = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (
      !selectedExercise ||
      !reason.trim() ||
      !targets.length ||
      missingProgramNames.length ||
      (revisionScope === 'future_program' && !effectiveDate) ||
      (revisionScope === 'current_block' && !allHaveActiveBlocks)
    ) {
      return;
    }
    const command: CommonRevisionCommand = {
      targets,
      exercise: selectedExercise,
      scope: revisionScope,
      dayNumber: selectedDayNumber,
      effectiveDate,
      sets,
      reps,
      durationMinutes,
      restSeconds,
      reason: reason.trim(),
    };
    const boundary =
      revisionScope === 'next_workout'
        ? 'в ближайшую запланированную тренировку'
        : revisionScope === 'current_block'
          ? 'в будущие тренировки активного блока'
          : `в программу с ${effectiveDate}`;
    const day = revisionScope === 'next_workout' ? '' : `, день ${selectedDayNumber}`;
    const prescription =
      selectedExercise.metric_type === 'cardio'
        ? `${durationMinutes} мин`
        : `${sets} подхода × ${reps}, отдых ${restSeconds} сек`;
    const approved = await confirm({
      title: 'Сохранить общую ревизию?',
      message: [
        `Общая правка «${selectedExercise.title}» (${prescription}) будет внесена ${boundary}${day}.`,
        `Она применяется отдельно для: ${targets.map((target) => target.clientName).join(', ')}.`,
        'Каждая программа получит собственную ревизию; история тренировок и базовые шаблоны не изменятся.',
      ].join(' '),
      confirmText: `Сохранить · ${targets.length}`,
    });
    if (approved) {
      setRevisionOutcomes([]);
      revisionMutation.mutate(command);
    }
  };

  const approveProposalGroup = async (group: ProposalCandidate[]) => {
    const first = group[0];
    if (!first) return;
    const approved = await confirm({
      title: 'Подтвердить одинаковые предложения?',
      message: [
        `${first.exercise.exercise_title}: ${proposalActionLabel(first.proposal, first.loadUnit)}.`,
        `Будут применены только совпадающие предложения для: ${group.map((candidate) => candidate.target.clientName).join(', ')}.`,
        'Для каждой тренировки сохраняется отдельный результат и аудит.',
      ].join(' '),
      confirmText: `Подтвердить · ${group.length}`,
    });
    if (approved) {
      setProposalOutcomes([]);
      proposalMutation.mutate(group);
    }
  };

  const applyableRolloutTargets =
    currentRolloutPreview?.targets.filter(
      (target) =>
        target.can_apply && target.program_id != null && target.current_revision_number != null,
    ) ?? [];

  const startRolloutPreview = () => {
    setRolloutPreview(null);
    setRolloutPreviewKey('');
    setRolloutResults([]);
    setRolloutResultsKey('');
    rolloutPreviewMutation.mutate();
  };

  const confirmRollout = async () => {
    if (!currentRolloutPreview || !applyableRolloutTargets.length || !rolloutReason.trim()) return;
    const approved = await confirm({
      title: 'Подтвердить rollout шаблона?',
      message: [
        `Шаблон «${currentRolloutPreview.template_title}» обновит только будущие запланированные тренировки у ${applyableRolloutTargets.length} клиентов.`,
        'Завершённые тренировки не изменятся. Клиенты с персонализацией или ручной проверкой будут пропущены.',
      ].join(' '),
      confirmText: `Подтвердить · ${applyableRolloutTargets.length}`,
    });
    if (!approved) return;
    const idempotencyKey =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `rollout-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    rolloutApplyMutation.mutate({ preview: currentRolloutPreview, idempotencyKey });
  };

  const canScheduleRevision =
    selectedClients.length > 0 &&
    targets.length === selectedClients.length &&
    targets.every(
      (target) =>
        target.program.workouts_planned > 0 && target.program.schedule_weekdays.length > 0,
    ) &&
    Boolean(selectedExercise) &&
    Boolean(reason.trim()) &&
    (revisionScope !== 'future_program' || Boolean(effectiveDate)) &&
    (revisionScope !== 'current_block' || allHaveActiveBlocks) &&
    !revisionMutation.isPending;

  const proposalLoading = proposalQueries.some((query) => query.isFetching);
  const proposalError = proposalQueries.some(
    (query) => query.isError && !(query.error instanceof ApiError && query.error.status === 409),
  );
  const proposalNoWorkout = proposalQueries.some(
    (query) => query.error instanceof ApiError && query.error.status === 409,
  );

  return (
    <section
      className="coach-program-bulk-operations stack"
      aria-label="Общие действия с программами"
    >
      {selectedTemplate && (
        <details className="coach-program-rollout">
          <summary>Проверить безопасный rollout выбранного шаблона</summary>
          {!selectedClients.length ? (
            <EmptyState title="Сначала выберите клиентов" text="Выбор клиентов находится выше." />
          ) : (
            <div className="stack">
              <p className="coach-program-operations__note">
                «{selectedTemplate.title}» сравнивается с будущими тренировками каждого клиента.
                Завершённые тренировки не меняются; несовместимые случаи останутся для ручной
                проверки.
              </p>
              <Button
                type="button"
                variant="secondary"
                disabled={rolloutPreviewMutation.isPending || rolloutApplyMutation.isPending}
                onClick={startRolloutPreview}
              >
                {rolloutPreviewMutation.isPending
                  ? 'Собираем предпросмотр…'
                  : 'Собрать предпросмотр'}
              </Button>
              {rolloutPreviewMutation.isError && (
                <p role="alert">Не удалось собрать предпросмотр. Обновите данные и повторите.</p>
              )}
              {currentRolloutPreview && (
                <div className="coach-program-rollout__preview" aria-live="polite">
                  {currentRolloutPreview.targets.map((target) => (
                    <fieldset className="coach-program-rollout__target" key={target.client_id}>
                      <legend>
                        {target.client_name}{' '}
                        <Badge
                          tone={
                            target.classification === 'compatible'
                              ? 'success'
                              : target.classification === 'personalization_required'
                                ? 'warning'
                                : 'danger'
                          }
                        >
                          {rolloutClassificationLabel(target.classification)}
                        </Badge>
                      </legend>
                      <p className="muted">{rolloutReasonLabels(target.reason_codes ?? [])}</p>
                      {(target.diff ?? []).length ? (
                        <ul>
                          {(target.diff ?? []).slice(0, 6).map((change, index) => (
                            <li key={`${change.week_number}-${change.day_number}-${index}`}>
                              {change.exercise_title}: {rolloutChangeLabel(change.change)} ·{' '}
                              {change.current ?? 'нет'} → {change.proposed ?? 'нет'}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted">Изменений не найдено.</p>
                      )}
                    </fieldset>
                  ))}
                  {applyableRolloutTargets.length ? (
                    <>
                      <p className="coach-program-operations__note">
                        К применению готово: {applyableRolloutTargets.length}. Остальные клиенты
                        будут пропущены до отдельной ручной проверки.
                      </p>
                      <Field label="Причина rollout" labelFor="coach-rollout-reason">
                        <Input
                          id="coach-rollout-reason"
                          required
                          maxLength={500}
                          value={rolloutReason}
                          onChange={(event) => setRolloutReason(event.target.value)}
                        />
                      </Field>
                      <Button
                        type="button"
                        disabled={rolloutApplyMutation.isPending || !rolloutReason.trim()}
                        onClick={() => void confirmRollout()}
                      >
                        {rolloutApplyMutation.isPending
                          ? 'Применяем…'
                          : `Проверено и применить · ${applyableRolloutTargets.length}`}
                      </Button>
                    </>
                  ) : (
                    <p role="status">Нет клиентов, готовых к безопасному применению rollout.</p>
                  )}
                </div>
              )}
              {currentRolloutResults.length > 0 && (
                <ul className="coach-program-operations__results" aria-live="polite">
                  {currentRolloutResults.map((result) => (
                    <li
                      key={`${result.client_id}-${result.status}`}
                      className={result.status === 'failed' ? 'is-failed' : undefined}
                    >
                      <strong>{result.client_name}:</strong> {result.detail}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </details>
      )}

      <details
        open={revisionOpen}
        onToggle={(event) => {
          const open = event.currentTarget.open;
          setRevisionOpen(open);
          if (open) setProposalOpen(false);
          if (!open) setRevisionOutcomes([]);
        }}
      >
        <summary>Запланировать общую правку программ</summary>
        {selectedClients.length === 0 ? (
          <EmptyState title="Сначала выберите клиентов" text="Выбор клиентов находится выше." />
        ) : missingProgramNames.length ? (
          <p role="status">
            У этих клиентов нет активной программы тренера: {missingProgramNames.join(', ')}.
          </p>
        ) : targets.some((target) => target.program.workouts_planned === 0) ? (
          <p role="status">У выбранных программ нет будущих запланированных тренировок.</p>
        ) : commonDayCount === 0 ? (
          <p role="status">Не удалось определить дни для общей правки выбранных программ.</p>
        ) : (
          <form className="stack" onSubmit={(event) => void scheduleCommonRevision(event)}>
            {exercises.isLoading ? (
              <LoadingState label="Загружаем упражнения…" />
            ) : exercises.error ? (
              <p role="alert">Не удалось загрузить список упражнений. Повторите попытку.</p>
            ) : (
              <Field label="Упражнение" labelFor="coach-common-exercise">
                <Select
                  id="coach-common-exercise"
                  required
                  value={exerciseId}
                  onChange={(event) => setExerciseId(event.target.value)}
                >
                  <option value="">Выберите упражнение</option>
                  {(exercises.data ?? []).map((exercise) => (
                    <option key={exercise.id} value={exercise.id}>
                      {exercise.title}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            <Field label="Когда применить" labelFor="coach-common-scope">
              <Select
                id="coach-common-scope"
                value={revisionScope}
                onChange={(event) => setRevisionScope(event.target.value as RevisionScope)}
              >
                <option value="next_workout">В ближайшую тренировку</option>
                <option value="current_block">В будущие тренировки активного блока</option>
                <option value="future_program">В программу с выбранной даты</option>
              </Select>
            </Field>
            {revisionScope !== 'next_workout' && (
              <Field label="День программы" labelFor="coach-common-day">
                <Select
                  id="coach-common-day"
                  value={selectedDayNumber}
                  onChange={(event) => setDayNumber(Number(event.target.value))}
                >
                  {Array.from({ length: commonDayCount }, (_, index) => index + 1).map((day) => (
                    <option key={day} value={day}>
                      День {day} у всех выбранных клиентов
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            {revisionScope === 'future_program' && (
              <Field label="Дата начала" labelFor="coach-common-date">
                <Input
                  id="coach-common-date"
                  type="date"
                  required
                  value={effectiveDate}
                  onChange={(event) => setEffectiveDate(event.target.value)}
                />
              </Field>
            )}
            {revisionScope === 'current_block' && (
              <>
                <p role="status">
                  {lifecycles.some((query) => query.isFetching)
                    ? 'Проверяем активные блоки у выбранных клиентов…'
                    : lifecycles.some((query) => query.isError)
                      ? 'Не удалось проверить активные блоки. Повторите проверку.'
                      : allHaveActiveBlocks
                        ? 'Общая правка попадёт только в будущие тренировки активного блока каждого клиента.'
                        : 'У каждого клиента должен быть активный тренировочный блок.'}
                </p>
                {lifecycles.some((query) => query.isError) && (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => void Promise.all(lifecycles.map((query) => query.refetch()))}
                  >
                    Повторить проверку
                  </Button>
                )}
              </>
            )}
            {selectedExercise?.metric_type === 'cardio' ? (
              <Field label="Длительность, мин" labelFor="coach-common-duration">
                <Input
                  id="coach-common-duration"
                  type="number"
                  min="1"
                  max="600"
                  required
                  value={durationMinutes}
                  onChange={(event) => setDurationMinutes(Number(event.target.value))}
                />
              </Field>
            ) : (
              <div className="assignment-context">
                <Field label="Подходы" labelFor="coach-common-sets">
                  <Input
                    id="coach-common-sets"
                    type="number"
                    min="1"
                    max="10"
                    required
                    value={sets}
                    onChange={(event) => setSets(Number(event.target.value))}
                  />
                </Field>
                <Field label="Повторения" labelFor="coach-common-reps">
                  <Input
                    id="coach-common-reps"
                    required
                    value={reps}
                    onChange={(event) => setReps(event.target.value)}
                  />
                </Field>
              </div>
            )}
            {selectedExercise?.metric_type !== 'cardio' && (
              <Field label="Отдых между подходами, сек" labelFor="coach-common-rest">
                <Input
                  id="coach-common-rest"
                  type="number"
                  min="15"
                  max="600"
                  required
                  value={restSeconds}
                  onChange={(event) => setRestSeconds(Number(event.target.value))}
                />
              </Field>
            )}
            <Field label="Причина общей правки" labelFor="coach-common-reason">
              <Input
                id="coach-common-reason"
                required
                maxLength={500}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </Field>
            <p>
              Будет создана отдельная ревизия для каждого клиента. Завершённые тренировки и базовый
              шаблон останутся без изменений.
            </p>
            <Button type="submit" disabled={!canScheduleRevision}>
              {revisionMutation.isPending
                ? 'Сохраняем…'
                : `Проверить и сохранить · ${targets.length}`}
            </Button>
          </form>
        )}
        {revisionOutcomes.length > 0 && (
          <ul className="coach-program-operations__results" aria-live="polite">
            {revisionOutcomes.map((outcome) => (
              <li
                key={outcome.clientId}
                className={outcome.status === 'failed' ? 'is-failed' : undefined}
              >
                <strong>{outcome.clientName}:</strong> {outcome.message}
              </li>
            ))}
          </ul>
        )}
      </details>

      <details
        open={proposalOpen}
        onToggle={(event) => {
          const open = event.currentTarget.open;
          setProposalOpen(open);
          if (open) setRevisionOpen(false);
          if (!open) setProposalOutcomes([]);
        }}
      >
        <summary>Проверить одинаковые предложения прогрессии</summary>
        {!selectedClients.length ? (
          <EmptyState title="Сначала выберите клиентов" text="Выбор клиентов находится выше." />
        ) : missingProgramNames.length ? (
          <p role="status">
            У этих клиентов нет активной программы тренера: {missingProgramNames.join(', ')}.
          </p>
        ) : proposalLoading ? (
          <LoadingState label="Проверяем предложения выбранных клиентов…" />
        ) : proposalError ? (
          <div role="alert">
            <p>Не удалось загрузить все предложения.</p>
            <Button
              type="button"
              variant="secondary"
              onClick={() => void Promise.all(proposalQueries.map((query) => query.refetch()))}
            >
              Повторить проверку
            </Button>
          </div>
        ) : proposalGroups.length ? (
          <div className="stack">
            {proposalGroups.map((group) => {
              const first = group[0];
              if (!first) return null;
              return (
                <fieldset
                  key={proposalClass(first)}
                  className="coach-program-operations__client-fieldset"
                >
                  <legend>
                    {first.exercise.exercise_title} ·{' '}
                    {proposalActionLabel(first.proposal, first.loadUnit)} · Совпадающие клиенты:{' '}
                    {group.length}
                  </legend>
                  <ul>
                    {group.map((candidate) => (
                      <li key={candidate.proposal.proposal_id}>
                        {candidate.target.clientName} · {candidate.proposal.current_weight ?? '—'} →{' '}
                        {candidate.proposal.proposed_weight ?? '—'}{' '}
                        {candidate.loadUnit === 'kg' ? 'кг' : 'фунт'} · тренировка на{' '}
                        {formatDate(candidate.scheduledDate)}
                      </li>
                    ))}
                  </ul>
                  <Button
                    type="button"
                    disabled={proposalMutation.isPending}
                    onClick={() => void approveProposalGroup(group)}
                  >
                    {proposalMutation.isPending
                      ? 'Подтверждаем…'
                      : `Подтвердить одинаковые предложения · ${group.length}`}
                  </Button>
                </fieldset>
              );
            })}
          </div>
        ) : (
          <EmptyState
            title="Одинаковых предложений нет"
            text="Для общей операции подходят только совпадающие проверяемые предложения с одинаковым результатом. Остальные можно проверить отдельно в карточке программы клиента."
          />
        )}
        {proposalNoWorkout && (
          <p role="status">У части клиентов пока нет ближайшей тренировки с предложением.</p>
        )}
        {proposalOutcomes.length > 0 && (
          <ul className="coach-program-operations__results" aria-live="polite">
            {proposalOutcomes.map((outcome) => (
              <li
                key={outcome.clientId}
                className={outcome.status === 'failed' ? 'is-failed' : undefined}
              >
                <strong>{outcome.clientName}:</strong> {outcome.message}
              </li>
            ))}
          </ul>
        )}
      </details>
    </section>
  );
}
