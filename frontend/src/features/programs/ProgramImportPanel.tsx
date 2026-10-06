import { useMemo, useState, type ChangeEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiFile, ApiError } from '../../shared/api/client';
import type {
  Exercise,
  ProgramImport,
  ProgramImportConfirmResponse,
  ProgramImportTarget,
} from '../../shared/api/types';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Badge, Button, Card, Field, Input, Select } from '../../shared/ui/common';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { SearchableExercisePicker, type ExercisePickerExercise } from './SearchableExercisePicker';
import './program-import.css';

const PAGE_SIZE = 50;
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

export function ProgramImportPanel({ onImported }: { onImported?: () => void } = {}) {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<ProgramImport | null>(null);
  const [title, setTitle] = useState('');
  const [goal, setGoal] = useState('');
  const [level, setLevel] = useState('');
  const [provenance, setProvenance] = useState<ImportProvenance>({
    provenance_type: 'CUSTOM',
  });
  const [targetProgramId, setTargetProgramId] = useState<number | ''>('');
  const [selectedExercises, setSelectedExercises] = useState<Record<number, number | ''>>({});
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    target.duration_weeks === (preview?.duration_weeks ?? 1) &&
    target.day_numbers.join(',') === previewDayNumbers.join(',');

  const applyPreview = (next: ProgramImport) => {
    setPreview(next);
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
      const next = await api<ProgramImport>('/api/v1/programs/imports', {
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
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api<ProgramImport>(`/api/v1/programs/imports/${preview.id}/resolve`, {
        method: 'POST',
        body: {
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
          rows: Object.entries(selectedExercises)
            .filter(([, exerciseId]) => exerciseId !== '')
            .map(([rowNumber, exerciseId]) => ({
              row_number: Number(rowNumber),
              exercise_id: exerciseId,
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
    if (!preview || preview.summary.blocking_issue_count > 0) return;
    if (targetProgramId !== '' && !selectedTarget) return;
    setBusy(true);
    setError(null);
    try {
      await api<ProgramImportConfirmResponse>(`/api/v1/programs/imports/${preview.id}/confirm`, {
        method: 'POST',
        body: {
          target_program_id: selectedTarget?.program_id ?? null,
          expected_revision_number: selectedTarget?.current_revision_number ?? null,
        },
      });
      setPreview(null);
      await queryClient.invalidateQueries({ queryKey: ['templates'] });
      await queryClient.invalidateQueries({ queryKey: ['assigned-program'] });
      await queryClient.invalidateQueries({ queryKey: ['program-import', 'targets'] });
      onImported?.();
      toast(
        selectedTarget
          ? 'Новая ревизия программы сохранена'
          : 'Программа импортирована в личные шаблоны',
      );
      trackProductEvent({ name: 'program_import_confirmed', surface: productEventSurface() });
    } catch (reason) {
      setError(formatError(reason));
      trackProductEvent({ name: 'program_import_failed', surface: productEventSurface() });
    } finally {
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

  return (
    <Card
      className="program-import-card"
      collapsible={false}
      family="training"
      title="Импорт программы"
      description="Загрузите XLSX, CSV, TXT или DOCX с программой. YFC сначала детерминированно извлечёт данные, а программа появится только после проверки и подтверждения."
    >
      {!preview ? (
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

          {!!preview.issues.length && (
            <div className="program-import-issues" role="status">
              <strong>Сначала проверьте найденные проблемы</strong>
              <ul>
                {preview.issues.map((issue, index) => (
                  <li key={`${issue.code}-${issue.location}-${index}`}>
                    <span>{issue.message}</span>
                    {issue.location && <small>{issue.location}</small>}
                  </li>
                ))}
              </ul>
            </div>
          )}

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

          <details className="program-import-provenance">
            <summary>Источник и заметки об адаптации</summary>
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
                <Input
                  id="program-import-source-date"
                  type="date"
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
            {preview.duration_weeks ? ` · Недель: ${preview.duration_weeks}` : ''}
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
                    <td>{row.week_number ?? '—'}</td>
                    <td>
                      <strong>{row.day_number ?? '—'}</strong>
                      <small>{row.day_title || 'Название дня не указано'}</small>
                    </td>
                    <td>
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
                    <td>
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
                        <small>Из файла: {row.source_auxiliary} (не импортируется как вес)</small>
                      )}
                    </td>
                    <td>
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
              disabled={busy}
              type="button"
              variant="secondary"
              onClick={() => void resolve()}
            >
              Применить исправления
            </Button>
            <Button
              disabled={
                busy ||
                preview.summary.blocking_issue_count > 0 ||
                (targetProgramId !== '' &&
                  (!selectedTarget || !targetMatchesImport(selectedTarget)))
              }
              type="button"
              onClick={() => void confirm()}
            >
              {busy
                ? 'Сохраняем…'
                : selectedTarget
                  ? 'Подтвердить и создать ревизию'
                  : 'Подтвердить и сохранить шаблон'}
            </Button>
          </div>
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
    </Card>
  );
}
