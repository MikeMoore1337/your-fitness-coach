import { DateInput } from '../../shared/ui/PickerInput';
import { useMemo, useRef, useState, type ChangeEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiFile, ApiError } from '../../shared/api/client';
import type {
  Exercise,
  ProgramImport,
  ProgramImportConfirmResponse,
  ProgramImportTarget,
  ProgramTemplate,
} from '../../shared/api/types';
import { dateInputValue, formatCalendarDate } from '../../shared/dateTime';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { DisclosureIcon, Badge, Button, Card, Field, Input, Select } from '../../shared/ui/common';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { SearchableExercisePicker, type ExercisePickerExercise } from './SearchableExercisePicker';
import {
  assignmentPlanFromTemplate,
  assignmentFirstDate,
  ProgramAssignmentDialog,
  type AssignmentSchedule,
} from './ProgramAssignmentDialog';
import './program-import.css';

const PAGE_SIZE = 50;
const WEEK_PAGE_SIZE = 8;
const RECOVERY_KEY = 'program-import-confirmation-v1';
type AssignmentRequest = AssignmentSchedule & {
  replace_active: boolean;
  expected_active_program_id: number | null;
  expected_active_revision_number: number | null;
};
type Recovery = { id: string; intent: 'save' | 'assign'; assignment?: AssignmentRequest };
type ImportResult = {
  kind: 'saved' | 'assigned' | 'partial' | 'uncertain';
  id: string;
  title?: string;
  template?: ProgramTemplate;
  assignedId?: number;
  scheduled?: boolean;
  startDate?: string;
  notCurrent?: boolean;
  reason?: string;
  message?: string;
};

function outcomeUnknown(error: unknown): boolean {
  return (
    !(error instanceof ApiError) ||
    error.status === 0 ||
    error.status >= 500 ||
    error.status === 408 ||
    error.status === 429
  );
}

function assignmentFailureCode(error: unknown): string | undefined {
  if (!(error instanceof ApiError) || !error.body || typeof error.body !== 'object')
    return undefined;
  const detail = (error.body as { detail?: unknown }).detail;
  if (!detail || typeof detail !== 'object') return undefined;
  const code = (detail as { code?: unknown }).code;
  return typeof code === 'string' ? code : undefined;
}

function readRecovery(): Recovery | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(RECOVERY_KEY) ?? 'null') as Recovery | null;
    return value &&
      typeof value.id === 'string' &&
      (value.intent === 'save' || value.intent === 'assign')
      ? value
      : null;
  } catch {
    return null;
  }
}

function rememberRecovery(value: Recovery | null): void {
  try {
    if (value) sessionStorage.setItem(RECOVERY_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(RECOVERY_KEY);
  } catch {
    // The current screen still supports recovery if storage is unavailable.
  }
}
type WeekType = 'light' | 'medium' | 'heavy' | null;
type MatrixImport = ProgramImport & {
  draft_version?: number | null;
  assignment_duration_weeks?: number | null;
  repeat?: boolean | null;
  week_types?: WeekType[] | null;
  week_type_candidates?: {
    week_number: number;
    week_type: Exclude<WeekType, null>;
    source_text: string;
    source_sheet?: string | null;
    source_cell: string;
  }[];
  rows: (ProgramImport['rows'][number] & { manual_planned_loads?: string | null })[];
};
const weekTypeLabels: Record<Exclude<WeekType, null>, string> = {
  light: 'Лёгкая',
  medium: 'Средняя',
  heavy: 'Тяжёлая',
};

type ImportProvenance = NonNullable<ProgramImport['provenance']>;
type ImportCoachingRule = NonNullable<ProgramImport['coaching_rules']>[number];

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

const coachingRuleLabels: Record<string, string> = {
  fixed_prescription: 'Фиксированное предписание',
  double_progression: 'Двойная прогрессия',
  linear_load: 'Линейное увеличение нагрузки',
  percentage_training_max: 'Процент от тренировочного максимума',
  rir_rpe: 'Целевое усилие RIR или RPE',
  amrap_success_failure: 'Условие успеха и неудачи AMRAP',
  deload: 'Правило разгрузки',
};

const prescriptionRoleLabels: Record<string, string> = {
  warmup: 'Разминка',
  working: 'Рабочий подход',
  top: 'Тяжёлый подход',
  backoff: 'Снижение нагрузки',
  drop: 'Подход со снижением веса',
  activation: 'Активационный подход',
  mini_set: 'Мини-подход',
  cluster_member: 'Кластерный подход',
};

const prescriptionGroupLabels: Record<string, string> = {
  sequence: 'Последовательность',
  superset: 'Суперсет',
  rest_pause: 'Отдых-пауза',
  myo_reps: 'Мио-повторы',
  cluster: 'Кластер',
  drop_chain: 'Подход со снижением веса',
  circuit: 'Круговая тренировка',
};

const importFormatLabels: Record<ProgramImport['source_format'], string> = {
  csv: 'CSV',
  xlsx: 'Excel',
  txt: 'Текст',
  docx: 'Word',
};

const importLayoutLabels: Record<string, string> = {
  'canonical-table-v1': 'каноническая таблица',
  'weekly-matrix-v1': 'таблица недель',
  'generic-table-v1': 'обычная таблица',
  'text-list-v1': 'текстовый список',
  'docx-document-v1': 'документ Word',
};

const aiProposalFieldLabels: Record<string, string> = {
  program_title: 'название программы',
  goal: 'цель',
  level: 'уровень',
  day_number: 'номер дня',
  day_title: 'название дня',
  prescribed_sets: 'рабочие подходы',
  prescribed_reps: 'повторы',
  prescribed_duration_minutes: 'длительность',
  rest_seconds: 'отдых между подходами',
  notes: 'заметка',
  exercise_mapping: 'сопоставление упражнения',
};

function prescriptionPreview(row: ProgramImport['rows'][number]): string[] {
  const prescription = row.prescription;
  const segments = (prescription?.segments ?? []).map((segment) => {
    const reps = segment.rep_target;
    const repLabel =
      reps?.kind === 'exact'
        ? `${reps.value} повт.`
        : reps?.kind === 'range'
          ? `${reps.min_reps}–${reps.max_reps} повт.`
          : reps?.kind === 'amrap'
            ? `максимум повторов${reps.cap_reps ? `, не более ${reps.cap_reps}` : ''}`
            : '';
    const load = segment.load_target;
    const loadLabel = !load
      ? ''
      : load.kind === 'user_selected'
        ? 'нагрузка на выбор'
        : load.value == null
          ? ''
          : load.kind === 'absolute'
            ? `${load.value.toLocaleString('ru-RU')} кг`
            : load.kind === 'percent_1rm'
              ? `${load.value.toLocaleString('ru-RU')}% от 1ПМ`
              : load.kind === 'percent_training_max'
                ? `${load.value.toLocaleString('ru-RU')}% от тренировочного максимума`
                : load.kind === 'relative_to_top'
                  ? `${(load.value * 100).toLocaleString('ru-RU')}% от топ-сета`
                  : `${(load.value * 100).toLocaleString('ru-RU')}% от предыдущего подхода`;
    const effort = segment.effort_target;
    const effortLabel =
      effort?.kind === 'rir' && effort.value != null
        ? `${effort.value} повтора в запасе (RIR)`
        : effort?.kind === 'rpe' && effort.value != null
          ? `усилие RPE ${effort.value}`
          : effort?.kind === 'failure'
            ? 'до отказа'
            : '';
    return [
      prescriptionRoleLabels[segment.role] ?? 'Подход',
      segment.group_id == null
        ? ''
        : [
            `группа ${segment.group_id}`,
            segment.group_position == null ? '' : `позиция ${segment.group_position}`,
            segment.round_number == null ? '' : `раунд ${segment.round_number}`,
          ]
            .filter(Boolean)
            .join(', '),
      repLabel,
      loadLabel,
      effortLabel,
      `отдых ${segment.rest_after_seconds} сек.`,
    ]
      .filter(Boolean)
      .join(' · ');
  });

  const groups = (prescription?.groups ?? []).map((group) =>
    [
      `Группа ${group.group_id}: ${prescriptionGroupLabels[group.kind] ?? 'группа'}`,
      group.exercise_slot == null ? '' : `упражнение в группе ${group.exercise_slot}`,
      group.rounds == null ? '' : `раундов ${group.rounds}`,
      `пауза между элементами ${group.intra_group_rest_seconds} сек.`,
      `отдых после группы ${group.rest_after_group_seconds} сек.`,
    ]
      .filter(Boolean)
      .join(' · '),
  );
  return [...segments, ...groups];
}

function coachingRulePreview(rule: ImportCoachingRule, preview: ProgramImport): string {
  const parts = [coachingRuleLabels[rule.kind] ?? 'Правило прогрессии'];
  if (rule.scope === 'block') {
    const title = preview.blocks?.find((block) => block.block_number === rule.block_number)?.title;
    parts.push(title ? `блок ${rule.block_number} · ${title}` : `блок ${rule.block_number}`);
  } else if (rule.scope === 'exercise') {
    const exercise = preview.rows.find((row) => row.resolved_exercise_id === rule.exercise_id);
    parts.push(exercise ? rowExerciseLabel(exercise) : `упражнение №${rule.exercise_id}`);
  } else {
    parts.push('вся программа');
  }

  const rep = rule.rep_target;
  if (rep?.kind === 'exact' && rep.value != null) parts.push(`${rep.value} повторов`);
  if (rep?.kind === 'range' && rep.min_reps != null && rep.max_reps != null) {
    parts.push(`${rep.min_reps}–${rep.max_reps} повторов`);
  }
  if (rep?.kind === 'amrap') {
    parts.push(`AMRAP${rep.cap_reps ? ` до ${rep.cap_reps} повторов` : ''}`);
  }

  const load = rule.load_target;
  if (load) {
    const loadLabels: Record<string, string> = {
      user_selected: 'нагрузка на выбор',
      absolute: 'кг',
      percent_1rm: '% от 1ПМ',
      percent_training_max: '% от тренировочного максимума',
      relative_to_top: '% от топ-сета',
      relative_to_previous: '% от предыдущего подхода',
    };
    const loadLabel = loadLabels[load.kind] ?? 'нагрузка';
    parts.push(
      load.value == null ? loadLabel : `${load.value.toLocaleString('ru-RU')} ${loadLabel}`,
    );
  }

  const effort = rule.effort_target;
  if ((effort?.kind === 'rir' || effort?.kind === 'rpe') && effort.value != null) {
    parts.push(`${effort.kind.toUpperCase()} ${effort.value}`);
  }
  if (rule.increment_value != null && rule.increment_unit) {
    const incrementUnits: Record<string, string> = {
      kg: 'кг',
      lb: 'фунта',
      percent: '%',
    };
    parts.push(
      `шаг ${rule.increment_value.toLocaleString('ru-RU')} ${incrementUnits[rule.increment_unit] ?? '%'}`,
    );
  }
  if (rule.reset_on_failure != null) {
    parts.push(rule.reset_on_failure ? 'сброс после неудачи' : 'без сброса после неудачи');
  }
  if (rule.amrap_min_reps != null) parts.push(`успех от ${rule.amrap_min_reps} повторов`);
  if (rule.amrap_failure_action) {
    const failureActionLabels: Record<string, string> = {
      repeat: 'повторить нагрузку при неудаче',
      reduce_load: 'снизить нагрузку при неудаче',
      deload: 'разгрузка при неудаче',
      manual_review: 'ручная проверка при неудаче',
    };
    parts.push(failureActionLabels[rule.amrap_failure_action] ?? 'действие после неудачи');
  }
  if (rule.deload_volume_percent != null) {
    parts.push(`объём разгрузки ${rule.deload_volume_percent}%`);
  }
  if (rule.deload_intensity_percent != null) {
    parts.push(`интенсивность разгрузки ${rule.deload_intensity_percent}%`);
  }
  if (rule.week_start != null && rule.week_end != null) {
    parts.push(`недели ${rule.week_start}–${rule.week_end}`);
  } else if (rule.week_start != null) {
    parts.push(`с недели ${rule.week_start}`);
  } else if (rule.week_end != null) {
    parts.push(`до недели ${rule.week_end}`);
  }
  return parts.join(' · ');
}

function formatError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'Не удалось обработать файл. Попробуйте ещё раз.';
}

function formatStartDate(value: string): string {
  return formatCalendarDate(value, { day: 'numeric', month: 'long', year: 'numeric' }).replace(
    /\s*г\.$/,
    '',
  );
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function rowExerciseLabel(row: ProgramImport['rows'][number]): string {
  return row.resolved_exercise_title || row.exercise_name || 'Упражнение не сопоставлено';
}

function importLayoutLabel(layoutVersion: string | null | undefined): string {
  return layoutVersion ? (importLayoutLabels[layoutVersion] ?? 'табличный формат') : 'определяется';
}

export function ProgramImportPanel({
  onImported,
  allowSelfAssignment = false,
  defaultStartDate = dateInputValue(new Date()),
  onOpenTemplates,
  onOpenProgram,
  onOpenWorkout,
}: {
  onImported?: () => void;
  allowSelfAssignment?: boolean;
  defaultStartDate?: string;
  onOpenTemplates?: () => void;
  onOpenProgram?: (id: number) => void;
  onOpenWorkout?: () => void;
} = {}) {
  const { toast, confirm: confirmAction } = useFeedback();
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<MatrixImport | null>(null);
  const [title, setTitle] = useState('');
  const [goal, setGoal] = useState('');
  const [level, setLevel] = useState('');
  const [provenance, setProvenance] = useState<ImportProvenance>({
    provenance_type: 'CUSTOM',
  });
  const [targetProgramId, setTargetProgramId] = useState<number | ''>('');
  const [selectedExercises, setSelectedExercises] = useState<Record<number, number | ''>>({});
  const [rowSets, setRowSets] = useState<Record<number, string>>({});
  const [rowReps, setRowReps] = useState<Record<number, string>>({});
  const [plannedLoads, setPlannedLoads] = useState<Record<number, string>>({});
  const [weekTypes, setWeekTypes] = useState<WeekType[]>([]);
  const [assignmentWeeks, setAssignmentWeeks] = useState('1');
  const [repeatCycle, setRepeatCycle] = useState(false);
  const [weekPage, setWeekPage] = useState(0);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recovery, setRecovery] = useState<Recovery | null>(() =>
    allowSelfAssignment ? readRecovery() : null,
  );
  const [result, setResult] = useState<ImportResult | null>(() => {
    const pending = allowSelfAssignment ? readRecovery() : null;
    return pending ? { kind: 'uncertain', id: pending.id } : null;
  });
  const [assignmentOpen, setAssignmentOpen] = useState(false);
  const [confirmingReplacement, setConfirmingReplacement] = useState(false);
  const requestLock = useRef(false);

  const updateRecovery = (value: Recovery | null) => {
    setRecovery(value);
    rememberRecovery(value);
  };

  const exercises = useQuery({
    queryKey: ['program-import', 'exercises'],
    queryFn: () => api<Exercise[]>('/api/v1/programs/exercises'),
    enabled: Boolean(preview),
    staleTime: 5 * 60_000,
  });

  const importTargets = useQuery({
    queryKey: ['program-import', 'targets'],
    queryFn: () => api<ProgramImportTarget[]>('/api/v1/programs/imports/targets'),
    enabled: Boolean(preview),
    staleTime: 30_000,
  });

  const pageRows = useMemo(() => {
    if (!preview) return [];
    return preview.rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  }, [page, preview]);
  const pageCount = preview ? Math.max(1, Math.ceil(preview.rows.length / PAGE_SIZE)) : 1;
  const previewBlocks = preview?.blocks ?? [];
  const previewCoachingRules = preview?.coaching_rules ?? [];
  const sourceWeeks = preview?.duration_weeks ?? 1;
  const isMatrix = preview?.layout_version === 'weekly-matrix-v1' && preview.draft_version != null;
  const totalWeeks = Number(assignmentWeeks);
  const invalidDuration =
    isMatrix &&
    (!Number.isSafeInteger(totalWeeks) ||
      totalWeeks < 1 ||
      totalWeeks > 20000 ||
      (!repeatCycle && totalWeeks > sourceWeeks));
  const previewWeeks = [...new Set([1, Math.ceil(totalWeeks / 2), totalWeeks])].filter(
    (week) => Number.isSafeInteger(week) && week > 0 && week <= 20000,
  );
  const hasPendingChanges = Boolean(
    preview &&
    (title !== (preview.program_title ?? '') ||
      goal !== (preview.goal ?? '') ||
      level !== (preview.level ?? '') ||
      JSON.stringify(provenance) !==
        JSON.stringify(preview.provenance ?? { provenance_type: 'CUSTOM' }) ||
      (isMatrix &&
        (assignmentWeeks !== String(preview.assignment_duration_weeks ?? sourceWeeks) ||
          repeatCycle !== Boolean(preview.repeat) ||
          JSON.stringify(weekTypes) !==
            JSON.stringify(preview.week_types ?? Array(sourceWeeks).fill(null)))) ||
      preview.rows.some(
        (row) =>
          (selectedExercises[row.row_number] !== undefined &&
            selectedExercises[row.row_number] !== (row.resolved_exercise_id ?? '')) ||
          rowSets[row.row_number] !== undefined ||
          rowReps[row.row_number] !== undefined ||
          (plannedLoads[row.row_number] !== undefined &&
            plannedLoads[row.row_number] !== (row.manual_planned_loads ?? '')),
      )),
  );
  const selectedTarget = importTargets.data?.find(
    (target) => target.program_id === targetProgramId,
  );
  const previewDayNumbers = preview
    ? [
        ...new Set(
          preview.rows.map((row) => row.day_number).filter((day): day is number => day != null),
        ),
      ].sort((left, right) => left - right)
    : [];

  const targetMatchesImport = (target: ProgramImportTarget) =>
    target.duration_weeks ===
      (preview?.assignment_duration_weeks ?? preview?.duration_weeks ?? 1) &&
    target.day_numbers.join(',') === previewDayNumbers.join(',');

  const applyPreview = (next: MatrixImport) => {
    setPreview(next);
    setWeekTypes(next.week_types ?? Array(next.duration_weeks ?? 1).fill(null));
    setAssignmentWeeks(String(next.assignment_duration_weeks ?? next.duration_weeks ?? 1));
    setRepeatCycle(Boolean(next.repeat));
    setWeekPage(0);
    setRowSets({});
    setRowReps({});
    setPlannedLoads({});
    setTitle(next.program_title ?? '');
    setGoal(next.goal ?? '');
    setLevel(next.level ?? '');
    setProvenance(next.provenance ?? { provenance_type: 'CUSTOM' });
    if (preview?.id !== next.id) setTargetProgramId('');
    const initialSelections: Record<number, number | ''> = {};
    for (const row of next.rows) {
      if (row.match_type === 'manual' && row.resolved_exercise_id != null) {
        initialSelections[row.row_number] = row.resolved_exercise_id;
      }
    }
    setSelectedExercises(initialSelections);
    setPage(0);
  };

  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setBusy(true);
    setError(null);
    trackProductEvent({ name: 'program_import_started', surface: productEventSurface() });
    try {
      const body = new FormData();
      body.append('file', file);
      const next = await api<MatrixImport>('/api/v1/programs/imports', {
        method: 'POST',
        body,
        timeoutMs: 30_000,
      });
      applyPreview(next);
      trackProductEvent({ name: 'program_import_previewed', surface: productEventSurface() });
    } catch (reason) {
      setError(formatError(reason));
      trackProductEvent({ name: 'program_import_failed', surface: productEventSurface() });
    } finally {
      setBusy(false);
    }
  };

  const resolve = async () => {
    if (!preview || invalidDuration) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api<MatrixImport>(`/api/v1/programs/imports/${preview.id}/resolve`, {
        method: 'POST',
        body: {
          expected_draft_version: preview.draft_version ?? undefined,
          assignment_duration_weeks: isMatrix ? totalWeeks : undefined,
          repeat: isMatrix ? repeatCycle : undefined,
          week_types: isMatrix ? weekTypes : undefined,
          title: title.trim() || undefined,
          goal: goal || undefined,
          level: level || undefined,
          provenance: {
            provenance_type: provenance.provenance_type,
            source_name: provenance.source_name?.trim() || null,
            creator: provenance.creator?.trim() || null,
            organization: provenance.organization?.trim() || null,
            source_reference: provenance.source_reference?.trim() || null,
            source_version: provenance.source_version?.trim() || null,
            source_date: provenance.source_date || null,
            adaptation_notes: provenance.adaptation_notes?.trim() || null,
          },
          rows: preview.rows
            .filter(
              (row) =>
                selectedExercises[row.row_number] !== undefined ||
                rowSets[row.row_number] !== undefined ||
                rowReps[row.row_number] !== undefined ||
                plannedLoads[row.row_number] !== undefined,
            )
            .map((row) => ({
              row_number: row.row_number,
              exercise_id: selectedExercises[row.row_number] || undefined,
              prescribed_sets:
                rowSets[row.row_number] !== undefined ? Number(rowSets[row.row_number]) : undefined,
              prescribed_reps: rowReps[row.row_number],
              planned_loads: plannedLoads[row.row_number],
            })),
        },
      });
      applyPreview(next);
    } catch (reason) {
      setError(formatError(reason));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (
      !preview ||
      preview.summary.blocking_issue_count > 0 ||
      hasPendingChanges ||
      invalidDuration
    )
      return;
    if (targetProgramId !== '' && !selectedTarget) return;
    if (requestLock.current) return;
    requestLock.current = true;
    setBusy(true);
    setError(null);
    if (allowSelfAssignment && !selectedTarget) updateRecovery({ id: preview.id, intent: 'save' });
    try {
      const saved = await api<ProgramImportConfirmResponse>(
        `/api/v1/programs/imports/${preview.id}/confirm`,
        {
          method: 'POST',
          body: {
            target_program_id: selectedTarget?.program_id ?? null,
            expected_revision_number: selectedTarget?.current_revision_number ?? null,
            expected_draft_version: preview.draft_version ?? undefined,
          },
        },
      );
      setPreview(null);
      if (allowSelfAssignment && !selectedTarget) {
        setResult({ kind: 'saved', id: preview.id, title: saved.template.title });
      }
      await Promise.allSettled([
        queryClient.invalidateQueries({ queryKey: ['templates'] }),
        queryClient.invalidateQueries({ queryKey: ['assigned-program'] }),
        queryClient.invalidateQueries({ queryKey: ['program-import', 'targets'] }),
      ]);
      onImported?.();
      if (!allowSelfAssignment || selectedTarget)
        toast(
          selectedTarget
            ? 'Новая ревизия программы сохранена'
            : 'Программа импортирована в личные шаблоны',
        );
      trackProductEvent({ name: 'program_import_confirmed', surface: productEventSurface() });
    } catch (reason) {
      if (allowSelfAssignment && !selectedTarget && outcomeUnknown(reason)) {
        setResult({ kind: 'uncertain', id: preview.id });
        setPreview(null);
      } else if (allowSelfAssignment && !selectedTarget) {
        updateRecovery(null);
      }
      setError(
        reason instanceof ApiError && reason.status === 409
          ? 'Черновик или программа изменились. Проверьте актуальные данные и повторите подтверждение.'
          : formatError(reason),
      );
      trackProductEvent({ name: 'program_import_failed', surface: productEventSurface() });
    } finally {
      requestLock.current = false;
      setBusy(false);
    }
  };

  const finishAssignment = (
    id: string,
    template: ProgramTemplate,
    assigned: { user_program_id: number; status: string; start_date: string },
  ) => {
    setPreview(null);
    setAssignmentOpen(false);
    setResult({
      kind: 'assigned',
      id,
      title: template.title,
      assignedId: assigned.user_program_id,
      scheduled: assigned.status === 'scheduled',
      startDate: assigned.start_date,
      notCurrent: assigned.status !== 'scheduled' && assigned.status !== 'active',
    });
    updateRecovery({ id, intent: 'assign' });
    void Promise.allSettled([
      queryClient.invalidateQueries({ queryKey: ['templates'] }),
      queryClient.invalidateQueries({ queryKey: ['assigned-program'] }),
      queryClient.invalidateQueries({ queryKey: ['workout'] }),
      queryClient.invalidateQueries({ queryKey: ['notifications'] }),
    ]);
    onImported?.();
    trackProductEvent({ name: 'program_import_confirmed', surface: productEventSurface() });
  };

  const assign = async (schedule: AssignmentSchedule) => {
    if (requestLock.current || (!preview && !result?.template)) return;
    requestLock.current = true;
    setBusy(true);
    setError(null);
    const importId = preview?.id ?? result!.id;
    let savedTemplate = result?.template;
    let assignmentRequest: AssignmentRequest | undefined;
    try {
      const templates = await api<ProgramTemplate[]>('/api/v1/programs/templates/mine');
      const active = templates.find((item) => item.is_active_for_current_user);
      if (
        active &&
        (active.assigned_program_id == null || active.current_revision_number == null)
      ) {
        throw new Error(
          'Не удалось проверить текущую программу. Обновите данные и попробуйте снова.',
        );
      }
      const newTitle = savedTemplate?.title ?? title;
      const firstDate = assignmentFirstDate(schedule);
      const assignmentDescription =
        firstDate > defaultStartDate
          ? `будет запланирована с ${formatStartDate(firstDate)}`
          : 'будет назначена';
      if (active) {
        setConfirmingReplacement(true);
        const approved = await confirmAction({
          title: 'Заменить активную программу?',
          message: `«${active.title}» будет сразу отправлена в архив. «${newTitle}» ${assignmentDescription}. Выполненные тренировки и история сохранятся.`,
          confirmText: 'Заменить программу',
          danger: true,
        });
        setConfirmingReplacement(false);
        if (!approved) return;
      }
      assignmentRequest = {
        ...schedule,
        replace_active: Boolean(active),
        expected_active_program_id: active?.assigned_program_id ?? null,
        expected_active_revision_number: active?.current_revision_number ?? null,
      };
      updateRecovery({ id: importId, intent: 'assign', assignment: assignmentRequest });
      if (!savedTemplate && preview) {
        const saved = await api<ProgramImportConfirmResponse>(
          `/api/v1/programs/imports/${importId}/confirm`,
          {
            method: 'POST',
            body: {
              target_program_id: null,
              expected_revision_number: null,
              expected_draft_version: preview.draft_version ?? undefined,
            },
          },
        );
        savedTemplate = saved.template;
      }
      if (!savedTemplate) throw new Error('Сохранённый шаблон недоступен.');
      const assigned = await api<{ user_program_id: number; status: string; start_date: string }>(
        `/api/v1/programs/imports/${importId}/assign-to-me`,
        {
          method: 'POST',
          body: assignmentRequest,
        },
      );
      finishAssignment(importId, savedTemplate, assigned);
    } catch (reason) {
      const uncertain = outcomeUnknown(reason);
      if (assignmentRequest && uncertain) {
        setPreview(null);
        setAssignmentOpen(false);
        setResult({ kind: 'uncertain', id: importId, title: savedTemplate?.title });
      } else if (savedTemplate && assignmentRequest) {
        updateRecovery({ id: importId, intent: 'assign' });
        setPreview(null);
        setAssignmentOpen(false);
        setResult({
          kind: 'partial',
          id: importId,
          title: savedTemplate.title,
          template: savedTemplate,
          reason: assignmentFailureCode(reason),
          message: reason instanceof Error ? reason.message : 'Не удалось назначить программу.',
        });
        void queryClient.invalidateQueries({ queryKey: ['templates'] });
      } else {
        if (assignmentRequest) updateRecovery(null);
        setError(reason instanceof Error ? reason.message : 'Не удалось проверить программу.');
      }
    } finally {
      requestLock.current = false;
      setBusy(false);
    }
  };

  const checkResult = async () => {
    if (!recovery || requestLock.current) return;
    requestLock.current = true;
    setBusy(true);
    setError(null);
    try {
      const current = await api<MatrixImport>(`/api/v1/programs/imports/${recovery.id}`);
      if (current.status === 'pending') {
        applyPreview(current);
        setResult(null);
        updateRecovery(null);
        return;
      }
      if (current.status !== 'confirmed' || current.confirmed_template_id == null) {
        throw new Error('Результат импорта недоступен. Проверьте личные шаблоны.');
      }
      const template = await api<ProgramTemplate>(
        `/api/v1/programs/templates/${current.confirmed_template_id}`,
      );
      if (current.self_assigned_program_id != null) {
        const lifecycle = await api<{ status: string; start_date: string }>(
          `/api/v1/programs/assigned/${current.self_assigned_program_id}/lifecycle`,
        );
        finishAssignment(current.id, template, {
          user_program_id: current.self_assigned_program_id,
          status: lifecycle.status,
          start_date: lifecycle.start_date,
        });
      } else if (recovery.intent === 'assign' && recovery.assignment) {
        try {
          const assigned = await api<{
            user_program_id: number;
            status: string;
            start_date: string;
          }>(`/api/v1/programs/imports/${current.id}/assign-to-me`, {
            method: 'POST',
            body: recovery.assignment,
          });
          finishAssignment(current.id, template, assigned);
        } catch (reason) {
          if (outcomeUnknown(reason)) throw reason;
          updateRecovery({ id: current.id, intent: 'assign' });
          setResult({
            kind: 'partial',
            id: current.id,
            title: template.title,
            template,
            reason: assignmentFailureCode(reason),
            message: reason instanceof Error ? reason.message : undefined,
          });
        }
      } else if (recovery.intent === 'assign') {
        setResult({ kind: 'partial', id: current.id, title: template.title, template });
      } else {
        setResult({ kind: 'saved', id: current.id, title: template.title });
      }
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Не удалось проверить результат. Попробуйте ещё раз.',
      );
    } finally {
      requestLock.current = false;
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/api/v1/programs/imports/${preview.id}/cancel`, { method: 'POST' });
      setPreview(null);
      trackProductEvent({ name: 'program_import_cancelled', surface: productEventSurface() });
    } catch (reason) {
      setError(formatError(reason));
    } finally {
      setBusy(false);
    }
  };

  const downloadTemplate = async (format: 'csv' | 'xlsx') => {
    setError(null);
    try {
      const result = await apiFile(`/api/v1/programs/imports/template.${format}`);
      downloadBlob(result.blob, result.filename ?? `шаблон-программы.${format}`);
    } catch (reason) {
      setError(formatError(reason));
    }
  };

  const exerciseOptions = (row: ProgramImport['rows'][number]) => {
    const byId = new Map<number, ExercisePickerExercise>();
    for (const candidate of row.candidates ?? []) {
      byId.set(candidate.exercise_id, {
        id: candidate.exercise_id,
        title: candidate.title,
        slug: candidate.slug,
        metric_type: candidate.metric_type,
      });
    }
    for (const exercise of exercises.data ?? []) byId.set(exercise.id, exercise);
    return [...byId.values()].sort((left, right) => left.title.localeCompare(right.title, 'ru'));
  };

  const previewDays =
    preview?.rows.filter((row) => row.week_number == null || row.week_number === 1) ?? [];
  const days = [
    ...new Set(
      previewDays.map((row) => row.day_number).filter((day): day is number => day != null),
    ),
  ]
    .sort((left, right) => left - right)
    .map((day) => ({
      title: previewDays.find((row) => row.day_number === day)?.day_title || `День ${day}`,
    }));
  const assignmentPlan = result?.template
    ? assignmentPlanFromTemplate(result.template)
    : preview
      ? {
          title: title || 'Программа',
          days,
          frequency: days.length,
          defaultDurationWeeks: preview.assignment_duration_weeks ?? preview.duration_weeks ?? 1,
          cycle: isMatrix ? { length_weeks: sourceWeeks, repeat: Boolean(preview.repeat) } : null,
        }
      : null;
  const confirmationDisabled =
    busy ||
    !preview ||
    preview.summary.blocking_issue_count > 0 ||
    hasPendingChanges ||
    Boolean(invalidDuration) ||
    (targetProgramId !== '' && (!selectedTarget || !targetMatchesImport(selectedTarget)));

  return (
    <Card
      className="program-import-card"
      collapsible={false}
      family="training"
      title={result ? undefined : 'Импорт программы'}
      description={
        result
          ? undefined
          : 'Загрузите XLSX, CSV, TXT или DOCX с программой. YFC сначала детерминированно извлечёт данные, а программа появится только после проверки и подтверждения.'
      }
    >
      {result ? (
        <section className="program-import-outcome" role="status" aria-live="polite">
          <span className="eyebrow">Результат импорта</span>
          <h3>
            {result.kind === 'saved'
              ? 'Шаблон сохранён'
              : result.kind === 'assigned'
                ? result.notCurrent
                  ? 'Назначение было создано'
                  : result.scheduled
                    ? 'Программа запланирована'
                    : 'Программа назначена'
                : result.kind === 'partial'
                  ? result.reason === 'workout_in_progress'
                    ? 'Сначала завершите тренировку'
                    : result.reason === 'trainer_owned_program'
                      ? 'Программа назначена тренером'
                      : result.reason === 'active_program_conflict'
                        ? 'Данные программы изменились'
                        : 'Шаблон сохранён, назначение не выполнено'
                  : recovery?.intent === 'save'
                    ? 'Результат сохранения пока неизвестен'
                    : 'Результат назначения пока неизвестен'}
          </h3>
          <div className="program-import-result">
            {result.title && (
              <p>
                <strong>{result.title}</strong>
              </p>
            )}
            <p>
              {result.kind === 'saved'
                ? 'Программа доступна в личной библиотеке. Текущий план не изменился.'
                : result.kind === 'assigned'
                  ? result.notCurrent
                    ? 'Назначение уже не является текущим. Проверьте программу в плане.'
                    : `${result.startDate ? `Начало: ${formatStartDate(result.startDate)}. ` : ''}${result.scheduled ? 'До этой даты программа будет запланирована.' : 'Тренировки доступны в разделе «План».'}`
                  : result.kind === 'partial'
                    ? `Шаблон сохранён. ${result.message || 'Повторите только назначение, загружать файл заново не нужно.'}`
                    : recovery?.intent === 'save'
                      ? 'Связь прервалась. Проверьте, сохранился ли шаблон.'
                      : 'Связь прервалась. Проверьте результат; при необходимости мы безопасно повторим подтверждённое назначение.'}
            </p>
          </div>
          <div className="program-import-actions">
            {result.kind === 'uncertain' && (
              <Button disabled={busy} type="button" onClick={() => void checkResult()}>
                {busy ? 'Проверяем…' : 'Проверить результат'}
              </Button>
            )}
            {result.kind === 'partial' &&
              result.reason === 'workout_in_progress' &&
              onOpenWorkout && (
                <Button type="button" onClick={onOpenWorkout}>
                  Открыть тренировку
                </Button>
              )}
            {result.kind === 'partial' &&
              result.template &&
              result.reason !== 'trainer_owned_program' &&
              result.reason !== 'workout_in_progress' && (
                <Button disabled={busy} type="button" onClick={() => setAssignmentOpen(true)}>
                  {result.reason === 'active_program_conflict'
                    ? 'Обновить данные'
                    : 'Повторить назначение'}
                </Button>
              )}
            {result.kind === 'assigned' && result.assignedId != null && onOpenProgram && (
              <Button
                type="button"
                onClick={() => {
                  updateRecovery(null);
                  onOpenProgram(result.assignedId!);
                }}
              >
                Открыть программу
              </Button>
            )}
            {(result.kind === 'saved' ||
              result.kind === 'partial' ||
              result.kind === 'uncertain') &&
              onOpenTemplates && (
                <Button
                  type="button"
                  variant={
                    result.kind === 'saved' || result.reason === 'trainer_owned_program'
                      ? undefined
                      : 'secondary'
                  }
                  onClick={() => {
                    if (result.kind !== 'uncertain') updateRecovery(null);
                    onOpenTemplates();
                  }}
                >
                  Открыть в моих шаблонах
                </Button>
              )}
            <button
              type="button"
              className="text-button"
              onClick={() => {
                updateRecovery(null);
                setResult(null);
                setError(null);
              }}
            >
              Импортировать другую программу
            </button>
          </div>
        </section>
      ) : !preview ? (
        <div className="program-import-intro">
          <div className="program-import-intro__actions">
            <label className="program-import-upload">
              <span>{busy ? 'Проверяем файл…' : 'Загрузить документ программы'}</span>
              <input
                accept=".csv,.xlsx,.txt,.docx,text/csv,text/plain,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                disabled={busy}
                onChange={upload}
                type="file"
              />
            </label>
            <div className="program-import-template-links" aria-label="Канонические шаблоны">
              <button
                type="button"
                className="text-button"
                onClick={() => void downloadTemplate('xlsx')}
              >
                Скачать XLSX-шаблон
              </button>
              <button
                type="button"
                className="text-button"
                onClick={() => void downloadTemplate('csv')}
              >
                Скачать CSV-шаблон
              </button>
            </div>
          </div>
          <p className="muted">
            Поддерживаются каноническая таблица, обычные таблицы, списки и таблицы недель. Макросы,
            формулы и внешние связи запрещены; неоднозначные упражнения всегда выбираются вручную.
          </p>
        </div>
      ) : (
        <section className="program-import-preview" aria-labelledby="program-import-preview-title">
          <div className="program-import-preview__head">
            <div>
              <span className="eyebrow">
                Предпросмотр · {importFormatLabels[preview.source_format]}
              </span>
              <h3 id="program-import-preview-title">Проверьте план перед сохранением</h3>
            </div>
            <Badge tone={preview.summary.blocking_issue_count ? 'danger' : 'success'}>
              {preview.summary.blocking_issue_count
                ? `${preview.summary.blocking_issue_count} проблем`
                : 'Готово к подтверждению'}
            </Badge>
          </div>

          {(['blocking', 'warning'] as const).map((severity) => {
            const issues = preview.issues.filter((issue) =>
              severity === 'blocking'
                ? preview.summary.blocking_issue_count > 0 && issue.severity === 'blocking'
                : issue.severity === 'warning' ||
                  (preview.summary.blocking_issue_count === 0 && issue.severity === 'blocking'),
            );
            return (
              !!issues.length && (
                <div
                  key={severity}
                  className={`program-import-issues${severity === 'warning' ? ' program-import-issues--warning' : ''}`}
                  role="status"
                >
                  <strong>
                    {severity === 'blocking'
                      ? 'Сначала проверьте найденные проблемы'
                      : 'Особенности импорта'}
                  </strong>
                  <ul>
                    {issues.map((issue, index) => (
                      <li key={`${issue.code}-${issue.location}-${index}`}>
                        <span>{issue.message}</span>
                        {issue.location && <small>{issue.location}</small>}
                      </li>
                    ))}
                  </ul>
                </div>
              )
            );
          })}

          <div className="program-import-fields">
            <Field label="Название программы" labelFor="program-import-title">
              <Input
                id="program-import-title"
                maxLength={128}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </Field>
            <Field label="Цель" labelFor="program-import-goal">
              <Select
                id="program-import-goal"
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
              >
                <option value="">Выберите цель</option>
                {Object.entries(goalLabels).map(([value, label]) => (
                  <option value={value} key={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Уровень" labelFor="program-import-level">
              <Select
                id="program-import-level"
                value={level}
                onChange={(event) => setLevel(event.target.value)}
              >
                <option value="">Выберите уровень</option>
                {Object.entries(levelLabels).map(([value, label]) => (
                  <option value={value} key={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          {isMatrix && (
            <section className="program-import-cycle" aria-labelledby="import-cycle-heading">
              <div className="program-import-cycle__heading">
                <div>
                  <span className="eyebrow">Периодизация · по желанию</span>
                  <h4 id="import-cycle-heading">Исходные недели и срок программы</h4>
                  <p className="muted">
                    В файле распознано {sourceWeeks} исходных недель. Типы недель не зависят от
                    цвета.
                  </p>
                </div>
                <strong>Исходных недель: {sourceWeeks}</strong>
              </div>
              <div className="program-import-cycle__fields">
                <label htmlFor="program-import-duration">
                  Всего недель программы
                  <Input
                    id="program-import-duration"
                    type="number"
                    min={1}
                    max={20000}
                    value={assignmentWeeks}
                    onChange={(event) => setAssignmentWeeks(event.target.value)}
                    aria-invalid={invalidDuration}
                  />
                </label>
                <label className="program-import-cycle__repeat">
                  <input
                    type="checkbox"
                    checked={repeatCycle}
                    onChange={(event) => setRepeatCycle(event.target.checked)}
                  />
                  Повторять исходные недели до конца срока
                </label>
              </div>
              {invalidDuration && (
                <p className="field-error" role="alert">
                  Укажите положительное число недель. Если срок больше исходного цикла, включите
                  повтор.
                </p>
              )}
              <div
                className="program-import-week-map"
                aria-label="Пример повторения исходных недель"
              >
                {previewWeeks.map((week) => {
                  const sourceWeek = repeatCycle ? ((week - 1) % sourceWeeks) + 1 : week;
                  return (
                    <span key={week}>
                      Неделя {week} → исходная {sourceWeek}
                    </span>
                  );
                })}
              </div>
              <div className="program-import-cycle__heading">
                <strong>Типы исходных недель</strong>
                {!!preview.week_type_candidates?.length && (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() =>
                      setWeekTypes((current) =>
                        current.map(
                          (currentType, index) =>
                            currentType ??
                            preview.week_type_candidates?.find(
                              (item) => item.week_number === index + 1,
                            )?.week_type ??
                            null,
                        ),
                      )
                    }
                  >
                    Принять текстовые подсказки
                  </Button>
                )}
              </div>
              <div className="program-import-week-types">
                {weekTypes
                  .slice(weekPage * WEEK_PAGE_SIZE, (weekPage + 1) * WEEK_PAGE_SIZE)
                  .map((weekType, index) => {
                    const number = weekPage * WEEK_PAGE_SIZE + index + 1;
                    const candidate = preview.week_type_candidates?.find(
                      (item) => item.week_number === number,
                    );
                    return (
                      <label key={number}>
                        Неделя {number}
                        <Select
                          aria-label={`Тип исходной недели ${number}`}
                          value={weekType ?? ''}
                          onChange={(event) => {
                            const value = (event.target.value || null) as WeekType;
                            setWeekTypes((current) =>
                              current.map((item, position) =>
                                position === number - 1 ? value : item,
                              ),
                            );
                          }}
                        >
                          <option value="">Без типа</option>
                          {Object.entries(weekTypeLabels).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </Select>
                        {candidate && (
                          <small>
                            В файле: {candidate.source_text} · {candidate.source_cell}. Подсказка не
                            применяется автоматически.
                          </small>
                        )}
                      </label>
                    );
                  })}
              </div>
              {sourceWeeks > WEEK_PAGE_SIZE && (
                <nav className="program-import-pagination" aria-label="Страницы типов недель">
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={weekPage === 0}
                    onClick={() => setWeekPage((current) => current - 1)}
                  >
                    Ранее
                  </Button>
                  <span>
                    {weekPage + 1} из {Math.ceil(sourceWeeks / WEEK_PAGE_SIZE)}
                  </span>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={(weekPage + 1) * WEEK_PAGE_SIZE >= sourceWeeks}
                    onClick={() => setWeekPage((current) => current + 1)}
                  >
                    Далее
                  </Button>
                </nav>
              )}
              <p className="muted">
                Тип недели можно оставить пустым. Повтор не копирует выполненные тренировки. Если
                недели распознаны неправильно, исправьте заголовки в исходном файле и загрузите его
                повторно.
              </p>
            </section>
          )}

          <details className="program-import-provenance">
            <summary className="yfc-disclosure-summary">
              Источник и заметки об адаптации
              <DisclosureIcon />
            </summary>
            <div className="program-import-fields">
              <Field label="Тип программы" labelFor="program-import-provenance-type">
                <Select
                  id="program-import-provenance-type"
                  value={provenance.provenance_type}
                  onChange={(event) =>
                    setProvenance((current) => ({
                      ...current,
                      provenance_type: event.target.value as 'CUSTOM' | 'SOURCE_ADAPTATION',
                    }))
                  }
                >
                  <option value="CUSTOM">Собственная программа</option>
                  <option value="SOURCE_ADAPTATION">Адаптация внешнего источника</option>
                </Select>
              </Field>
              <Field label="Название источника" labelFor="program-import-source-name">
                <Input
                  id="program-import-source-name"
                  maxLength={128}
                  value={provenance.source_name ?? ''}
                  onChange={(event) =>
                    setProvenance((current) => ({ ...current, source_name: event.target.value }))
                  }
                />
              </Field>
              <Field label="Автор" labelFor="program-import-source-creator">
                <Input
                  id="program-import-source-creator"
                  maxLength={128}
                  value={provenance.creator ?? ''}
                  onChange={(event) =>
                    setProvenance((current) => ({ ...current, creator: event.target.value }))
                  }
                />
              </Field>
              <Field label="Организация или сообщество" labelFor="program-import-source-org">
                <Input
                  id="program-import-source-org"
                  maxLength={128}
                  value={provenance.organization ?? ''}
                  onChange={(event) =>
                    setProvenance((current) => ({
                      ...current,
                      organization: event.target.value,
                    }))
                  }
                />
              </Field>
              <Field
                label="Ссылка или идентификатор источника"
                labelFor="program-import-source-ref"
              >
                <Input
                  id="program-import-source-ref"
                  maxLength={500}
                  value={provenance.source_reference ?? ''}
                  onChange={(event) =>
                    setProvenance((current) => ({
                      ...current,
                      source_reference: event.target.value,
                    }))
                  }
                />
              </Field>
              <Field label="Версия источника" labelFor="program-import-source-version">
                <Input
                  id="program-import-source-version"
                  maxLength={64}
                  value={provenance.source_version ?? ''}
                  onChange={(event) =>
                    setProvenance((current) => ({
                      ...current,
                      source_version: event.target.value,
                    }))
                  }
                />
              </Field>
              <Field label="Дата источника" labelFor="program-import-source-date">
                <DateInput
                  className="ui-input"
                  id="program-import-source-date"

                  value={provenance.source_date ?? ''}
                  onChange={(event) =>
                    setProvenance((current) => ({
                      ...current,
                      source_date: event.target.value,
                    }))
                  }
                />
              </Field>
              <Field label="Что изменено при адаптации" labelFor="program-import-adaptation-notes">
                <Input
                  id="program-import-adaptation-notes"
                  maxLength={1000}
                  value={provenance.adaptation_notes ?? ''}
                  onChange={(event) =>
                    setProvenance((current) => ({
                      ...current,
                      adaptation_notes: event.target.value,
                    }))
                  }
                />
              </Field>
            </div>
            <p className="muted">
              Сохраняются ссылки и короткие заметки. Длинные фрагменты исходных материалов не
              копируются.
            </p>
          </details>

          {(previewBlocks.length > 0 || previewCoachingRules.length > 0) && (
            <div className="program-import-structured-summary">
              {previewBlocks.length > 0 && (
                <div>
                  <strong>Блоки программы</strong>
                  <ul>
                    {previewBlocks.map((block) => (
                      <li key={block.block_number}>
                        {block.title}: недели {block.week_start}–{block.week_end}
                        {block.is_deload ? ' · разгрузочный блок' : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {previewCoachingRules.length > 0 && (
                <div>
                  <strong>Правила программы</strong>
                  <ul>
                    {previewCoachingRules.map((rule, index) => (
                      <li key={`${rule.kind}-${rule.scope}-${index}`}>
                        {coachingRulePreview(rule, preview)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <Field label="Сохранить как" labelFor="program-import-target">
            <Select
              id="program-import-target"
              value={targetProgramId === '' ? '' : String(targetProgramId)}
              onChange={(event) =>
                setTargetProgramId(event.target.value ? Number(event.target.value) : '')
              }
              disabled={importTargets.isLoading || importTargets.isError}
            >
              <option value="">Отдельный личный шаблон</option>
              {(importTargets.data ?? []).map((target) => (
                <option
                  key={target.program_id}
                  value={target.program_id}
                  disabled={!targetMatchesImport(target)}
                >
                  {target.title}
                  {target.owner_name ? ` · ${target.owner_name}` : ''}
                  {targetMatchesImport(target) ? '' : ' · не совпадают недели или дни'}
                </option>
              ))}
            </Select>
          </Field>
          {selectedTarget && (
            <p className="muted">
              Будет создана ревизия {selectedTarget.current_revision_number + 1}. Обновятся только
              предстоящие запланированные тренировки; завершённая история и блоки останутся
              неизменными.
            </p>
          )}
          {importTargets.isError && (
            <p className="muted" role="status">
              Не удалось загрузить список назначенных программ. Можно сохранить отдельный шаблон.
            </p>
          )}

          <p className="muted program-import-layout-summary">
            Формат: {importLayoutLabel(preview.layout_version)} · Дней:{' '}
            {new Set(preview.rows.map((row) => row.day_number).filter((day) => day != null)).size}
            {preview.duration_weeks ? ` · Исходных недель: ${preview.duration_weeks}` : ''}
            {isMatrix ? ` · Срок: ${preview.assignment_duration_weeks ?? sourceWeeks}` : ''}
          </p>

          {preview.ai && preview.ai.status !== 'not_needed' && (
            <div className="program-import-ai" role="status">
              <strong>
                AI-помощь:{' '}
                {preview.ai.status === 'proposed' ? 'есть предложения для проверки' : 'недоступна'}
              </strong>
              <p>
                {preview.ai.status === 'proposed'
                  ? `Предложений: ${preview.ai.proposal_count}. Они привязаны к источнику и не подтверждают импорт автоматически.`
                  : 'Документ не передавался внешнему сервису. Используйте детерминированные значения и ручное разрешение.'}
              </p>
              {preview.ai.conflict_count > 0 && (
                <small>Отклонено конфликтующих предложений: {preview.ai.conflict_count}</small>
              )}
            </div>
          )}

          <div className="program-import-table-wrap">
            <table className="program-import-table">
              <caption>
                Упражнений: {preview.summary.row_count}; сопоставлено:{' '}
                {preview.summary.matched_row_count}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Строка</th>
                  <th scope="col">Неделя</th>
                  <th scope="col">День</th>
                  <th scope="col">Упражнение</th>
                  <th scope="col">Нагрузка</th>
                  <th scope="col">Статус</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((row) => (
                  <tr key={row.row_number}>
                    <th scope="row">
                      {row.row_number}
                      <small>
                        {row.source_sheet ? `Лист «${row.source_sheet}» · ` : ''}
                        {row.source_range ?? `строка ${row.row_number}`}
                      </small>
                    </th>
                    <td data-label="Неделя">{row.week_number ?? '—'}</td>
                    <td data-label="День">
                      <strong>{row.day_number ?? '—'}</strong>
                      <small>{row.day_title || 'Название дня не указано'}</small>
                    </td>
                    <td data-label="Упражнение">
                      {row.match_status === 'matched' ? (
                        <strong>{rowExerciseLabel(row)}</strong>
                      ) : (
                        <SearchableExercisePicker
                          ariaLabel={`Упражнение для строки ${row.row_number}`}
                          exercises={exerciseOptions(row)}
                          portalResults
                          value={selectedExercises[row.row_number] ?? ''}
                          onChange={(exerciseId) =>
                            setSelectedExercises((current) => ({
                              ...current,
                              [row.row_number]: exerciseId,
                            }))
                          }
                        />
                      )}
                      {row.ai_rerank_reason && (
                        <small className="program-import-ai-evidence">
                          AI предложил порядок вариантов: {row.ai_rerank_reason} Только ручной выбор
                          подтверждает упражнение.
                        </small>
                      )}
                      {row.exercise_name && row.match_status === 'matched' && (
                        <small>Из файла: {row.exercise_name}</small>
                      )}
                      {row.ai_proposals?.map((proposal, index) => (
                        <small
                          className="program-import-ai-evidence"
                          key={`${proposal.evidence_id}-${index}`}
                        >
                          AI-подсказка:{' '}
                          {aiProposalFieldLabels[proposal.field] ?? 'параметр программы'} ={' '}
                          {proposal.value} · {proposal.applied ? 'применена' : 'только подсказка'}
                          <br />
                          Источник: {proposal.source_location} — {proposal.source_text}
                        </small>
                      ))}
                    </td>
                    <td data-label="Назначение">
                      {row.metric_type === 'cardio'
                        ? `${row.prescribed_duration_minutes ?? '—'} мин`
                        : `${row.prescribed_sets ?? '—'} × ${row.prescribed_reps ?? '—'}`}
                      <small>отдых {row.rest_seconds ?? 90} сек.</small>
                      {prescriptionPreview(row).map((segment, index) => (
                        <small className="program-import-prescription-preview" key={index}>
                          {segment}
                        </small>
                      ))}
                      {row.source_auxiliary && (
                        <small>
                          Дополнительная ячейка: {row.source_auxiliary} (не считается плановым весом
                          без подтверждения)
                        </small>
                      )}
                      {isMatrix && row.metric_type !== 'cardio' && (
                        <details className="program-import-edit">
                          <summary className="yfc-disclosure-summary">
                            Исправить назначение
                            <DisclosureIcon />
                          </summary>
                          <label>
                            Подходы
                            <Input
                              type="number"
                              min={1}
                              max={10}
                              value={rowSets[row.row_number] ?? String(row.prescribed_sets ?? '')}
                              onChange={(event) =>
                                setRowSets((current) => ({
                                  ...current,
                                  [row.row_number]: event.target.value,
                                }))
                              }
                            />
                          </label>
                          <label>
                            Повторы
                            <Input
                              value={rowReps[row.row_number] ?? row.prescribed_reps ?? ''}
                              maxLength={32}
                              onChange={(event) =>
                                setRowReps((current) => ({
                                  ...current,
                                  [row.row_number]: event.target.value,
                                }))
                              }
                            />
                          </label>
                          <label>
                            Плановые веса, кг
                            <Input
                              value={plannedLoads[row.row_number] ?? row.manual_planned_loads ?? ''}
                              maxLength={256}
                              placeholder={row.source_auxiliary ?? 'например, 70/72.5/75/77.5'}
                              onChange={(event) =>
                                setPlannedLoads((current) => ({
                                  ...current,
                                  [row.row_number]: event.target.value,
                                }))
                              }
                            />
                          </label>
                          {row.source_cells?.source_auxiliary && (
                            <small>
                              Ячейка: {row.source_cells.source_auxiliary}. Значение из файла
                              применяется только после вашего ввода и подтверждения.
                            </small>
                          )}
                        </details>
                      )}
                    </td>
                    <td data-label="Статус">
                      <span
                        className={
                          row.match_status === 'matched'
                            ? 'program-import-ok'
                            : 'program-import-warning'
                        }
                      >
                        {row.match_status === 'matched' ? 'Сопоставлено' : 'Нужно выбрать'}
                      </span>
                      {!!row.issues?.length && (
                        <ul className="program-import-row-issues">
                          {row.issues?.map((issue, index) => (
                            <li key={`${issue.code}-${index}`}>{issue.message}</li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {pageCount > 1 && (
            <nav className="program-import-pagination" aria-label="Страницы предпросмотра">
              <Button
                disabled={page === 0}
                type="button"
                variant="secondary"
                onClick={() => setPage((current) => Math.max(0, current - 1))}
              >
                Назад
              </Button>
              <span>
                Страница {page + 1} из {pageCount}
              </span>
              <Button
                disabled={page + 1 >= pageCount}
                type="button"
                variant="secondary"
                onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))}
              >
                Далее
              </Button>
            </nav>
          )}

          <div className="program-import-actions">
            <Button disabled={busy} type="button" variant="secondary" onClick={() => void cancel()}>
              Отменить
            </Button>
            <Button
              disabled={busy || Boolean(invalidDuration)}
              type="button"
              variant="secondary"
              onClick={() => void resolve()}
            >
              Применить исправления
            </Button>
            <Button
              disabled={confirmationDisabled}
              type="button"
              variant={allowSelfAssignment && !selectedTarget ? 'secondary' : undefined}
              onClick={() => void confirm()}
            >
              {busy
                ? 'Сохраняем…'
                : selectedTarget
                  ? 'Подтвердить и создать ревизию'
                  : allowSelfAssignment
                    ? 'Сохранить шаблон'
                    : 'Подтвердить и сохранить шаблон'}
            </Button>
            {allowSelfAssignment && targetProgramId === '' && (
              <Button
                disabled={confirmationDisabled || days.length === 0}
                type="button"
                onClick={() => setAssignmentOpen(true)}
              >
                Сохранить и назначить
              </Button>
            )}
          </div>
          {hasPendingChanges && (
            <p className="muted" role="status">
              Сначала нажмите «Применить исправления», проверьте обновлённый план, затем подтвердите
              импорт.
            </p>
          )}
          <p className="muted program-import-retention">
            Черновик доступен {new Date(preview.expires_at).toLocaleString('ru-RU')}. После
            подтверждения исходные данные предпросмотра удаляются.
          </p>
        </section>
      )}
      {error && (
        <p className="field-error program-import-error" role="alert">
          {error}
        </p>
      )}
      {assignmentOpen && assignmentPlan && (
        <ProgramAssignmentDialog
          plan={assignmentPlan}
          defaultStartDate={defaultStartDate}
          busy={busy}
          concealed={confirmingReplacement}
          submitLabel={result?.template ? 'Назначить программу' : 'Сохранить и назначить'}
          backLabel={result?.template ? 'Вернуться к результату' : 'Вернуться к импорту'}
          onClose={() => setAssignmentOpen(false)}
          onSubmit={(schedule) => void assign(schedule)}
        />
      )}
    </Card>
  );
}
