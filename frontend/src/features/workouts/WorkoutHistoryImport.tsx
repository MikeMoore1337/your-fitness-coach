import { useEffect, useMemo, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiFile, ApiError, getUserFacingErrorMessage } from '../../shared/api/client';
import type {
  ApiSchemas,
  WorkoutHistoryImportDraft,
  WorkoutHistoryImportPreview,
  WorkoutHistoryImportRow,
} from '../../shared/api/types';
import { Button, Input, Select } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import './WorkoutHistoryImport.css';

const IMPORT_URL = '/api/v1/workout-history-imports';
type Stage =
  | 'drafts'
  | 'upload'
  | 'loading'
  | 'preview'
  | 'match'
  | 'unsupported'
  | 'conflicts'
  | 'confirm'
  | 'success'
  | 'unknown'
  | 'stale'
  | 'expired';
type Choice = 'keep' | 'skip';
type Duplicate = ApiSchemas['HistoryImportDuplicate'];
type Fact = Duplicate['source_sets'][number];

function importError(reason: unknown): string {
  return getUserFacingErrorMessage(reason, 'Не удалось обработать импорт. Попробуйте ещё раз.');
}

function Note({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="history-import__note">
      <Icon name="warning" size={20} />
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </div>
  );
}

function setText(row: WorkoutHistoryImportRow): string {
  const labels: Record<string, string> = {
    warmup: 'Разминка',
    working: 'Рабочий',
    drop: 'Дроп-сет',
  };
  const kind = labels[row.source.set_kind] ?? 'Подход';
  const weight = row.weight_kg === null ? 'вес не указан' : `${row.weight_kg} кг`;
  const sourceWeight = row.source.weight_unit === 'lb' ? ` (${row.source.weight} lb)` : '';
  const reps = row.reps === null ? 'повторы не указаны' : `${row.reps}`;
  return `${kind} · ${weight}${sourceWeight} × ${reps}${row.source.rir ? ` · резерв ${row.source.rir}` : ''}`;
}

function factText(fact: Fact, names: Map<number, string>): string {
  const [exerciseId, , reps, weight, kind, rir] = fact;
  const label = names.get(exerciseId) ?? `Упражнение ${exerciseId}`;
  const type = kind === 'warmup' ? 'разминка' : kind === 'drop' ? 'дроп-сет' : 'рабочий';
  return `${label} · ${weight === null ? 'вес не указан' : `${weight} кг`} × ${reps === null ? 'повторы не указаны' : reps} · ${type}${rir ? ` · резерв ${rir}` : ''}`;
}

function displayDate(value: string | undefined): string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return 'Дата не распознана';
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
    .format(new Date(`${value}T12:00:00Z`))
    .replace(/ г\.$/, '');
}

function displayZone(timestamp: string, zone: string): string {
  try {
    return (
      new Intl.DateTimeFormat('ru-RU', { timeZone: zone, timeZoneName: 'long' })
        .formatToParts(new Date(timestamp))
        .find((part) => part.type === 'timeZoneName')?.value ?? zone
    );
  } catch {
    return zone;
  }
}

function groupExercises(rows: WorkoutHistoryImportRow[]) {
  const groups = new Map<string, [WorkoutHistoryImportRow, ...WorkoutHistoryImportRow[]]>();
  for (const row of rows) {
    const key = row.source.exercise_ref || `row-${row.line}`;
    const group = groups.get(key);
    if (group) group.push(row);
    else groups.set(key, [row]);
  }
  return [...groups.entries()];
}

export function WorkoutHistoryImport({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [stage, setStage] = useState<Stage>('drafts');
  const [preview, setPreview] = useState<WorkoutHistoryImportPreview | null>(null);
  const [fileName, setFileName] = useState('Черновик импорта');
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [selectedExercise, setSelectedExercise] = useState<number | ''>('');
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const drafts = useQuery({
    queryKey: ['workout-history-import', 'drafts'],
    queryFn: () => api<WorkoutHistoryImportDraft[]>(IMPORT_URL),
    staleTime: 0,
  });
  const catalog = useQuery({
    queryKey: ['workout-history-import', 'catalog', search.trim()],
    queryFn: () =>
      api<ApiSchemas['HistoryImportExerciseCandidate'][]>(`${IMPORT_URL}/catalog`, {
        method: 'POST',
        body: { q: search.trim() },
      }),
    enabled: stage === 'match' && search.trim().length >= 2,
  });
  const currentStage: Stage = stage === 'drafts' && drafts.data?.length === 0 ? 'upload' : stage;
  useEffect(() => {
    titleRef.current?.focus();
  }, [currentStage]);

  const rows = useMemo(() => preview?.rows ?? [], [preview]);
  const duplicates = preview?.duplicates ?? [];
  const choices = preview?.duplicate_choices ?? {};
  const selected = rows.find((row) => row.line === selectedLine) ?? null;
  const names = useMemo(
    () =>
      new Map(
        rows
          .filter((row) => row.exercise_id !== null && row.resolved_title)
          .map((row) => [row.exercise_id as number, row.resolved_title as string]),
      ),
    [rows],
  );
  const grouped = useMemo(() => {
    const groups = new Map<string, [WorkoutHistoryImportRow, ...WorkoutHistoryImportRow[]]>();
    for (const row of rows) {
      const ref = row.source.workout_ref || `row-${row.line}`;
      const group = groups.get(ref);
      if (group) group.push(row);
      else groups.set(ref, [row]);
    }
    return [...groups.entries()];
  }, [rows]);
  const pageCount = Math.max(1, Math.ceil(grouped.length / 5));
  const currentPage = Math.min(page, pageCount - 1);
  const visibleGroups = grouped.slice(currentPage * 5, currentPage * 5 + 5);
  const included = rows.filter(
    (row) => !row.excluded && choices[row.source.workout_ref] !== 'skip',
  );
  const confirmGroups = grouped.flatMap(([ref, group]) => {
    if (choices[ref] === 'skip') return [];
    const [first, ...rest] = group.filter((row) => !row.excluded);
    if (!first) return [];
    const includedGroup: [WorkoutHistoryImportRow, ...WorkoutHistoryImportRow[]] = [first, ...rest];
    return [[ref, includedGroup] as const];
  });
  const confirmPageCount = Math.max(1, Math.ceil(confirmGroups.length / 5));
  const confirmPage = Math.min(page, confirmPageCount - 1);
  const unresolved = included.some((row) => row.blocking_issues.length > 0);
  const unresolvedDuplicates = duplicates.some(
    (item) =>
      item.candidates.length > 0 &&
      (item.choice !== 'keep' ||
        item.candidates.some((candidate) => candidate.kind !== 'possible')),
  );
  const canConfirm = included.length > 0 && !unresolved && !unresolvedDuplicates;
  const workoutsCount = new Set(included.map((row) => row.source.workout_ref)).size;
  const excludedCount = rows.length - included.length;
  const skippedTitles = grouped
    .filter(([ref]) => choices[ref] === 'skip')
    .map(([, group]) => `тренировка «${group[0].source.workout_title}»`);
  const excludedLines = rows
    .filter((row) => row.excluded && choices[row.source.workout_ref] !== 'skip')
    .map((row) => `строка ${row.line}`);
  const excludedDescriptions = [...skippedTitles, ...excludedLines];

  const apply = (next: WorkoutHistoryImportPreview) => {
    if (next.id !== preview?.id) setPage(0);
    setPreview(next);
    setError(null);
    setStage(next.status === 'confirmed' ? 'success' : 'preview');
  };
  const openDraft = async (draftId: string) => {
    setBusy(true);
    setError(null);
    try {
      apply(await api<WorkoutHistoryImportPreview>(`${IMPORT_URL}/${draftId}`));
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 410) setStage('expired');
      else setError(importError(reason));
    } finally {
      setBusy(false);
    }
  };
  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setFileName(file.name);
    setBusy(true);
    setError(null);
    setStage('loading');
    try {
      const body = new FormData();
      body.append('file', file);
      apply(
        await api<WorkoutHistoryImportPreview>(IMPORT_URL, {
          method: 'POST',
          body,
          timeoutMs: 30_000,
        }),
      );
    } catch (reason) {
      setError(importError(reason));
      setStage('upload');
    } finally {
      setBusy(false);
    }
  };
  const saveResolution = async (options: {
    exercise?: [number, number];
    excluded?: number[];
    duplicateChoices?: Record<string, Choice>;
  }) => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api<WorkoutHistoryImportPreview>(`${IMPORT_URL}/${preview.id}/resolve`, {
        method: 'POST',
        body: {
          version: preview.version,
          exercise_choices: options.exercise ? { [options.exercise[0]]: options.exercise[1] } : {},
          excluded_lines:
            options.excluded ?? rows.filter((row) => row.excluded).map((row) => row.line),
          duplicate_choices: options.duplicateChoices ?? choices,
        },
      });
      apply(next);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) setStage('stale');
      else if (reason instanceof ApiError && reason.status === 410) setStage('expired');
      else setError(importError(reason));
    } finally {
      setBusy(false);
    }
  };
  const exclude = (line: number, next: boolean) => {
    const current = rows.filter((row) => row.excluded && row.line !== line).map((row) => row.line);
    if (next) current.push(line);
    void saveResolution({ excluded: current });
  };
  const excludeGroup = (row: WorkoutHistoryImportRow) => {
    const current = new Set(rows.filter((item) => item.excluded).map((item) => item.line));
    for (const item of rows)
      if (
        item.source.workout_ref === row.source.workout_ref &&
        item.source.exercise_ref === row.source.exercise_ref
      )
        current.add(item.line);
    void saveResolution({ excluded: [...current] });
  };
  const restoreWorkout = (ref: string) => {
    const next = { ...choices };
    delete next[ref];
    void saveResolution({ duplicateChoices: next });
  };
  const review = () => {
    const issue = included.find((row) => row.blocking_issues.length > 0);
    if (issue) {
      setSelectedLine(issue.line);
      if (
        issue.blocking_issues.some((item) =>
          ['unsupported_side', 'unsupported_rpe', 'unsupported_metric'].includes(item.code),
        )
      )
        setStage('unsupported');
      else if (issue.match_status !== 'matched') {
        setSearch(issue.source.exercise_name);
        setSelectedExercise('');
        setStage('match');
      } else setStage('conflicts');
    } else if (unresolvedDuplicates) setStage('conflicts');
    else setStage('confirm');
  };
  const confirm = async () => {
    if (!preview?.preview_signature || !canConfirm) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api<WorkoutHistoryImportPreview>(`${IMPORT_URL}/${preview.id}/confirm`, {
        method: 'POST',
        body: { version: preview.version, preview_signature: preview.preview_signature },
        timeoutMs: 30_000,
      });
      setPreview(result);
      setStage('success');
      await Promise.all(
        ['workout', 'progress', 'exercises', 'me', 'workout-history-import'].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      );
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) setStage('stale');
      else if (reason instanceof ApiError && reason.status === 410) setStage('expired');
      else if (!(reason instanceof ApiError) || reason.status === 0 || reason.status >= 500)
        setStage('unknown');
      else setError(importError(reason));
    } finally {
      setBusy(false);
    }
  };
  const cancel = async (draftId: string, version: number) => {
    setBusy(true);
    setError(null);
    try {
      await api(`${IMPORT_URL}/${draftId}?version=${version}`, { method: 'DELETE' });
      setPreview(null);
      setStage('upload');
      void drafts.refetch();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 410) setStage('expired');
      else if (reason instanceof ApiError && reason.status === 409) setStage('stale');
      else setError(importError(reason));
    } finally {
      setBusy(false);
    }
  };
  const download = async () => {
    setError(null);
    try {
      const result = await apiFile(`${IMPORT_URL}/template.csv`);
      const url = URL.createObjectURL(result.blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = result.filename ?? 'yfc-workout-history-v1.csv';
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (reason) {
      setError(importError(reason));
    }
  };
  const openMatch = (row: WorkoutHistoryImportRow) => {
    setSelectedLine(row.line);
    setSelectedExercise('');
    setSearch(row.source.exercise_name);
    setStage('match');
  };
  const description: Record<Stage, string> = {
    drafts: 'Есть незавершённый импорт.',
    upload: 'Загрузите CSV-файл с выполненными тренировками.',
    loading: 'Читаем файл и проверяем записи.',
    preview: 'Проверьте распознанные данные перед сохранением.',
    match: 'Сопоставьте упражнение с каталогом YFC.',
    unsupported: 'Не все данные можно перенести.',
    conflicts: 'Проверьте совпадения и строки с ошибками.',
    confirm: 'Проверьте итог и подтвердите сохранение.',
    success: 'Сохранение завершено.',
    unknown: 'Не удалось получить результат сохранения.',
    stale: 'Черновик изменился.',
    expired: 'Срок хранения черновика истёк.',
  };
  const candidates = [
    ...new Map(
      [...(selected?.candidates ?? []), ...(catalog.data ?? [])].map((item) => [
        item.exercise_id,
        item,
      ]),
    ).values(),
  ];

  return (
    <div className="history-import">
      <header className="history-import__head">
        <h2 tabIndex={-1} ref={titleRef}>
          Импорт истории тренировок
        </h2>
        <p>{description[currentStage]}</p>
      </header>
      {error && (
        <p className="history-import__error" role="alert">
          {error}
        </p>
      )}
      {currentStage === 'drafts' && (
        <>
          {drafts.isLoading && <p role="status">Ищем черновики…</p>}
          {drafts.isError && (
            <p role="alert">Не удалось загрузить черновики. Попробуйте ещё раз.</p>
          )}
          {(drafts.data ?? []).map((draft) => (
            <div className="history-import__row" key={draft.id}>
              <strong>
                {draft.status === 'confirmed' ? 'Завершённый импорт' : 'Черновик импорта'}
              </strong>
              <p>Доступен до {new Date(draft.expires_at).toLocaleString('ru-RU')}</p>
              <div className="history-import__actions">
                <Button disabled={busy} onClick={() => void openDraft(draft.id)}>
                  {draft.status === 'confirmed' ? 'Посмотреть результат' : 'Продолжить проверку'}
                </Button>
                {draft.status === 'pending' && (
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => void cancel(draft.id, draft.version)}
                  >
                    Удалить черновик
                  </Button>
                )}
              </div>
            </div>
          ))}
          <div className="history-import__actions">
            <Button variant="secondary" onClick={() => setStage('upload')}>
              Загрузить другой файл
            </Button>
            <Button variant="secondary" onClick={onClose}>
              Закрыть
            </Button>
          </div>
        </>
      )}
      {currentStage === 'upload' && (
        <>
          <div className="history-import__upload">
            <strong>Выберите файл</strong>
            <p>Используйте шаблон YFC. Перед сохранением вы сможете проверить каждую тренировку.</p>
            <input
              ref={fileInput}
              className="history-import__file"
              type="file"
              accept=".csv,text/csv"
              aria-label="Выбрать CSV-файл"
              tabIndex={-1}
              onChange={upload}
            />
            <Button onClick={() => fileInput.current?.click()}>Выбрать файл</Button>
          </div>
          <p className="history-import__muted">
            До подтверждения история и статистика не изменятся.
          </p>
          <div className="history-import__actions">
            <Button variant="secondary" onClick={() => void download()}>
              Скачать шаблон
            </Button>
            <Button variant="secondary" onClick={onClose}>
              Закрыть
            </Button>
          </div>
        </>
      )}
      {currentStage === 'loading' && (
        <>
          <p role="status">
            <strong>Проверяем файл…</strong>
          </p>
          <p className="history-import__muted">История пока не изменена.</p>
          <div className="history-import__actions">
            <Button variant="secondary" onClick={onClose}>
              Закрыть
            </Button>
          </div>
        </>
      )}
      {currentStage === 'preview' && preview && (
        <>
          <div className="history-import__file-summary">
            <strong>{fileName}</strong>
            <span>
              {grouped.length} тренировок · {rows.length} строк
            </span>
          </div>
          {(unresolved || unresolvedDuplicates) && (
            <Note title="Нужно проверить записи">
              Выберите упражнение, сравните возможные дубли и проверьте строки с ошибкой.
            </Note>
          )}
          {visibleGroups.map(([ref, group]) => (
            <div className="history-import__row" key={ref}>
              <div className="history-import__row-head">
                <strong>{group[0].source.workout_title || 'Тренировка без названия'}</strong>
                <span>{displayDate(group[0].completed_on ?? undefined)}</span>
              </div>
              <p>
                {group[0].completed_at_utc
                  ? `${group[0].source.completed_at.slice(11, 16)} · ${displayZone(group[0].source.completed_at, group[0].source.timezone)}`
                  : 'Время не распознано'}
                {choices[ref] === 'skip' ? ' · исключена' : ''}
                {duplicates.some((item) => item.workout_ref === ref && item.candidates.length > 0)
                  ? ' · возможный дубль'
                  : ''}
              </p>
              {choices[ref] === 'skip' && (
                <Button variant="secondary" disabled={busy} onClick={() => restoreWorkout(ref)}>
                  Вернуть тренировку
                </Button>
              )}
              {groupExercises(group).map(([exerciseRef, exerciseRows]) => (
                <div key={exerciseRef}>
                  <button
                    type="button"
                    className="history-import__exercise"
                    onClick={() => openMatch(exerciseRows[0])}
                    aria-label={`Изменить упражнение: ${exerciseRows[0].source.exercise_name}`}
                  >
                    {exerciseRows[0].resolved_title ||
                      exerciseRows[0].source.exercise_name ||
                      'Упражнение не распознано'}
                  </button>
                  {exerciseRows.some((row) => row.blocking_issues.length > 0 && !row.excluded) && (
                    <span className="history-import__issue"> · требуется проверка</span>
                  )}
                  <ul>
                    {exerciseRows.map((row) => (
                      <li key={row.line}>
                        {setText(row)}
                        {row.excluded && (
                          <>
                            {' · исключено '}
                            <Button
                              variant="secondary"
                              disabled={busy}
                              onClick={() => exclude(row.line, false)}
                            >
                              Вернуть строку
                            </Button>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ))}
          {pageCount > 1 && (
            <div className="history-import__actions">
              <Button
                variant="secondary"
                disabled={currentPage === 0}
                onClick={() => setPage(currentPage - 1)}
              >
                Назад
              </Button>
              <span>
                Страница {currentPage + 1} из {pageCount}
              </span>
              <Button
                variant="secondary"
                disabled={currentPage + 1 >= pageCount}
                onClick={() => setPage(currentPage + 1)}
              >
                Далее
              </Button>
            </div>
          )}
          <div className="history-import__actions">
            <Button disabled={busy || included.length === 0} onClick={review}>
              {canConfirm ? 'Продолжить' : 'Проверить записи'}
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => void cancel(preview.id, preview.version)}
            >
              Отменить импорт
            </Button>
          </div>
        </>
      )}
      {currentStage === 'match' && selected && preview && (
        <>
          <Note
            title={
              selected.match_status === 'unknown' ? 'Упражнение не найдено' : 'Выберите упражнение'
            }
          >
            Выберите подходящий вариант вручную или исключите строки из импорта.
          </Note>
          <div className="history-import__row">
            <p>В файле · строка {selected.line}</p>
            <h3>{selected.source.exercise_name}</h3>
            <p>Тренировка «{selected.source.workout_title}»</p>
            <label htmlFor="history-import-search">Поиск по каталогу</label>
            <Input
              id="history-import-search"
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            {selected.match_status !== 'unknown' ? (
              <>
                <label htmlFor="history-import-exercise">Упражнение в YFC</label>
                <Select
                  id="history-import-exercise"
                  value={selectedExercise}
                  onChange={(event) =>
                    setSelectedExercise(event.target.value ? Number(event.target.value) : '')
                  }
                >
                  <option value="">Выберите упражнение</option>
                  {candidates.map((candidate) => (
                    <option
                      key={candidate.exercise_id}
                      value={candidate.exercise_id}
                      disabled={candidate.metric_type !== 'strength' || candidate.unsupported_side}
                    >
                      {candidate.title}
                    </option>
                  ))}
                </Select>
              </>
            ) : (
              <fieldset className="history-import__candidates">
                <legend>Выберите подходящее упражнение</legend>
                {candidates.map((candidate) => (
                  <label key={candidate.exercise_id}>
                    <input
                      type="radio"
                      name="history-import-exercise"
                      value={candidate.exercise_id}
                      checked={selectedExercise === candidate.exercise_id}
                      disabled={candidate.metric_type !== 'strength' || candidate.unsupported_side}
                      onChange={() => setSelectedExercise(candidate.exercise_id)}
                    />
                    {candidate.title}
                  </label>
                ))}
              </fieldset>
            )}
            <p>Если подходящего упражнения нет, исключите эти строки из импорта.</p>
          </div>
          <div className="history-import__actions">
            <Button
              disabled={busy || selectedExercise === ''}
              onClick={() =>
                selectedExercise !== '' &&
                void saveResolution({ exercise: [selected.line, selectedExercise] })
              }
            >
              Сохранить выбор
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => excludeGroup(selected)}>
              Исключить строки
            </Button>
            <Button variant="secondary" onClick={() => setStage('preview')}>
              Назад к просмотру
            </Button>
          </div>
        </>
      )}
      {currentStage === 'unsupported' && selected && (
        <>
          <Note title="Эти данные пока не поддерживаются">
            Исправьте файл или подтвердите исключение этой записи.
          </Note>
          <div className="history-import__row">
            <strong>
              Строка {selected.line} · {selected.source.exercise_name}
            </strong>
            {selected.source.side && (
              <p>
                Сторона:{' '}
                {selected.source.side === 'left'
                  ? 'левая'
                  : selected.source.side === 'right'
                    ? 'правая'
                    : selected.source.side}
              </p>
            )}
            <p>
              В файле: {selected.source.weight || 'вес не указан'} {selected.source.weight_unit} ×{' '}
              {selected.source.reps || 'повторы не указаны'}
            </p>
            {selected.source.rpe && <p>RPE: {selected.source.rpe}</p>}
            <p>{selected.blocking_issues.map((issue) => issue.message).join('. ')}</p>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => exclude(selected.line, true)}
            >
              Исключить строку
            </Button>
          </div>
          <div className="history-import__actions">
            <Button variant="secondary" onClick={() => setStage('preview')}>
              Назад к просмотру
            </Button>
          </div>
        </>
      )}
      {currentStage === 'conflicts' && preview && (
        <>
          {duplicates
            .filter((item) => item.candidates.length > 0)
            .map((item) => (
              <div className="history-import__row" key={item.workout_ref}>
                <p className="history-import__issue">
                  <Icon name="warning" size={20} /> Возможный дубль
                </p>
                <strong>
                  {
                    rows.find((row) => row.source.workout_ref === item.workout_ref)?.source
                      .workout_title
                  }
                </strong>
                <p>Сравните записи перед решением.</p>
                <div className="history-import__compare">
                  <div>
                    <strong>В файле</strong>
                    <ul>
                      {item.source_sets.map((fact, index) => (
                        <li key={index}>{factText(fact, names)}</li>
                      ))}
                    </ul>
                  </div>
                  {item.candidates.map((candidate, index) => (
                    <div key={candidate.workout_id ?? candidate.source_ref ?? index}>
                      <strong>
                        {candidate.source_ref ? 'В файле' : 'В истории'} · {candidate.title}
                      </strong>
                      <ul>
                        {candidate.sets.map((fact, factIndex) => (
                          <li key={factIndex}>{factText(fact, names)}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() =>
                    void saveResolution({
                      duplicateChoices: { ...choices, [item.workout_ref]: 'skip' },
                    })
                  }
                >
                  Исключить тренировку
                </Button>
                {item.candidates.every((candidate) => candidate.kind === 'possible') && (
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() =>
                      void saveResolution({
                        duplicateChoices: { ...choices, [item.workout_ref]: 'keep' },
                      })
                    }
                  >
                    Это другая тренировка
                  </Button>
                )}
              </div>
            ))}
          {included
            .filter((row) => row.blocking_issues.length > 0)
            .map((row) => (
              <div className="history-import__row" key={row.line}>
                <p className="history-import__issue">
                  <Icon name="warning" size={20} /> Строка {row.line} · требует проверки
                </p>
                <strong>{row.blocking_issues[0]?.message}</strong>
                <p>Исправьте файл или подтвердите исключение этой строки.</p>
                <Button variant="secondary" disabled={busy} onClick={() => exclude(row.line, true)}>
                  Подтвердить исключение
                </Button>
              </div>
            ))}
          <div className="history-import__actions">
            <Button variant="secondary" onClick={() => setStage('preview')}>
              Вернуться к просмотру
            </Button>
          </div>
        </>
      )}
      {currentStage === 'confirm' && preview && (
        <>
          <div className="history-import__stats">
            <div>
              <span>Тренировок</span>
              <strong>{workoutsCount}</strong>
            </div>
            <div>
              <span>Подходов</span>
              <strong>{included.length}</strong>
            </div>
            <div>
              <span>Исключено</span>
              <strong>{excludedCount} строк</strong>
            </div>
          </div>
          {confirmGroups.slice(confirmPage * 5, confirmPage * 5 + 5).map(([ref, group]) => (
            <div className="history-import__row" key={ref}>
              <div className="history-import__row-head">
                <strong>{group[0].source.workout_title}</strong>
                <span>{displayDate(group[0].completed_on ?? undefined)}</span>
              </div>
              {group.map((row) => (
                <p key={row.line}>
                  {row.resolved_title} · {setText(row)}
                </p>
              ))}
            </div>
          ))}
          {confirmPageCount > 1 && (
            <div className="history-import__actions">
              <Button
                variant="secondary"
                disabled={confirmPage === 0}
                onClick={() => setPage(confirmPage - 1)}
              >
                Назад
              </Button>
              <span>
                Страница {confirmPage + 1} из {confirmPageCount}
              </span>
              <Button
                variant="secondary"
                disabled={confirmPage + 1 >= confirmPageCount}
                onClick={() => setPage(confirmPage + 1)}
              >
                Далее
              </Button>
            </div>
          )}
          {excludedDescriptions.length > 0 && (
            <p className="history-import__muted">
              Не войдут: {excludedDescriptions.slice(0, 20).join(', ')}
              {excludedDescriptions.length > 20
                ? ` и ещё ${excludedDescriptions.length - 20}. Полный список доступен в просмотре.`
                : '.'}
            </p>
          )}
          <p className="history-import__muted">
            После подтверждения эти данные появятся в истории и статистике.
          </p>
          <div className="history-import__actions">
            <Button disabled={busy || !canConfirm} onClick={() => void confirm()}>
              Сохранить историю
            </Button>
            <Button variant="secondary" onClick={() => setStage('preview')}>
              Вернуться к просмотру
            </Button>
          </div>
        </>
      )}
      {currentStage === 'success' && (
        <>
          <div className="history-import__result">
            <Icon name="success" size={20} />
            <div>
              <h3>История дополнена</h3>
              <p>
                Сохранено тренировок: {preview?.result?.workout_count ?? 0}, подходов:{' '}
                {preview?.result?.set_count ?? 0}. Исключённые строки не добавлены.
              </p>
            </div>
          </div>
          <div className="history-import__actions">
            <Button onClick={onClose}>Открыть историю</Button>
            <Button variant="secondary" onClick={onClose}>
              Готово
            </Button>
          </div>
        </>
      )}
      {currentStage === 'unknown' && preview && (
        <>
          <Note title="Проверьте состояние импорта">
            Соединение прервалось. Обновите статус, прежде чем повторять сохранение.
          </Note>
          <div className="history-import__actions">
            <Button disabled={busy} onClick={() => void openDraft(preview.id)}>
              Обновить статус
            </Button>
            <Button variant="secondary" onClick={onClose}>
              Закрыть
            </Button>
          </div>
        </>
      )}
      {currentStage === 'stale' && preview && (
        <>
          <Note title="Нужен актуальный просмотр">
            В другой вкладке данные уже изменились. Обновите предпросмотр перед подтверждением.
          </Note>
          <div className="history-import__actions">
            <Button disabled={busy} onClick={() => void openDraft(preview.id)}>
              Обновить предпросмотр
            </Button>
            <Button variant="secondary" onClick={onClose}>
              Закрыть
            </Button>
          </div>
        </>
      )}
      {currentStage === 'expired' && (
        <>
          <Note title="Черновик удалён">Чтобы продолжить, загрузите файл ещё раз.</Note>
          <div className="history-import__actions">
            <Button
              onClick={() => {
                setPreview(null);
                setStage('upload');
              }}
            >
              Загрузить файл
            </Button>
            <Button variant="secondary" onClick={onClose}>
              Закрыть
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
