import { useMemo, useState, type ChangeEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiFile, ApiError } from '../../shared/api/client';
import type { Exercise, ProgramImport, ProgramImportConfirmResponse } from '../../shared/api/types';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Badge, Button, Card, Field, Input, Select } from '../../shared/ui/common';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import './program-import.css';

const PAGE_SIZE = 50;

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
  return row.resolved_exercise_title || row.exercise_name || row.exercise_slug || 'Не сопоставлено';
}

export function ProgramImportPanel({ onImported }: { onImported?: () => void } = {}) {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<ProgramImport | null>(null);
  const [title, setTitle] = useState('');
  const [goal, setGoal] = useState('');
  const [level, setLevel] = useState('');
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

  const pageRows = useMemo(() => {
    if (!preview) return [];
    return preview.rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  }, [page, preview]);
  const pageCount = preview ? Math.max(1, Math.ceil(preview.rows.length / PAGE_SIZE)) : 1;

  const applyPreview = (next: ProgramImport) => {
    setPreview(next);
    setTitle(next.program_title ?? '');
    setGoal(next.goal ?? '');
    setLevel(next.level ?? '');
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
    setBusy(true);
    setError(null);
    try {
      await api<ProgramImportConfirmResponse>(`/api/v1/programs/imports/${preview.id}/confirm`, {
        method: 'POST',
      });
      setPreview(null);
      await queryClient.invalidateQueries({ queryKey: ['templates'] });
      onImported?.();
      toast('Программа импортирована в личные шаблоны');
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
      downloadBlob(result.blob, result.filename ?? `yfc-program-template-v1.${format}`);
    } catch (reason) {
      setError(formatError(reason));
    }
  };

  const exerciseOptions = (row: ProgramImport['rows'][number]) => {
    type ExerciseOption = Pick<Exercise, 'id' | 'title' | 'slug' | 'metric_type'>;
    const byId = new Map<number, ExerciseOption>();
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
      description="Загрузите канонический шаблон v1 в XLSX или CSV. Программа появится только после проверки и подтверждения."
    >
      {!preview ? (
        <div className="program-import-intro">
          <div className="program-import-intro__actions">
            <label className="program-import-upload">
              <span>{busy ? 'Проверяем файл…' : 'Загрузить XLSX или CSV'}</span>
              <input
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
            Поддерживается только версия v1: один лист, фиксированные поля, UTF-8 и запятая в CSV.
            Макросы, формулы, внешние ссылки и произвольные выгрузки не принимаются.
          </p>
        </div>
      ) : (
        <section className="program-import-preview" aria-labelledby="program-import-preview-title">
          <div className="program-import-preview__head">
            <div>
              <span className="eyebrow">Предпросмотр · {preview.source_format.toUpperCase()}</span>
              <h3 id="program-import-preview-title">Проверьте план перед сохранением</h3>
            </div>
            <Badge tone={preview.summary.blocking_issue_count ? 'danger' : 'success'}>
              {preview.summary.blocking_issue_count
                ? `${preview.summary.blocking_issue_count} проблем`
                : 'Готово к подтверждению'}
            </Badge>
          </div>

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

          {!!preview.issues.length && (
            <div className="program-import-issues" role="status">
              <strong>Что нужно проверить</strong>
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

          <div className="program-import-table-wrap">
            <table className="program-import-table">
              <caption>
                Строки упражнений: {preview.summary.row_count}; сопоставлено:{' '}
                {preview.summary.matched_row_count}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Строка</th>
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
                    <td>
                      <strong>{row.day_number ?? '—'}</strong>
                      <small>{row.day_title || 'Название дня не указано'}</small>
                    </td>
                    <td>
                      {row.match_status === 'matched' ? (
                        <strong>{rowExerciseLabel(row)}</strong>
                      ) : (
                        <Select
                          aria-label={`Упражнение для строки ${row.row_number}`}
                          value={String(selectedExercises[row.row_number] ?? '')}
                          onChange={(event) =>
                            setSelectedExercises((current) => ({
                              ...current,
                              [row.row_number]: event.target.value
                                ? Number(event.target.value)
                                : '',
                            }))
                          }
                        >
                          <option value="">Выберите упражнение</option>
                          {exerciseOptions(row).map((exercise) => (
                            <option value={exercise.id} key={exercise.id}>
                              {exercise.title}
                            </option>
                          ))}
                        </Select>
                      )}
                      {row.exercise_name && row.match_status === 'matched' && (
                        <small>Из файла: {row.exercise_name}</small>
                      )}
                    </td>
                    <td>
                      {row.metric_type === 'cardio'
                        ? `${row.prescribed_duration_minutes ?? '—'} мин`
                        : `${row.prescribed_sets ?? '—'} × ${row.prescribed_reps ?? '—'}`}
                      <small>отдых {row.rest_seconds ?? 90} сек.</small>
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
              disabled={busy || preview.summary.blocking_issue_count > 0}
              type="button"
              onClick={() => void confirm()}
            >
              {busy ? 'Сохраняем…' : 'Подтвердить и сохранить'}
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
