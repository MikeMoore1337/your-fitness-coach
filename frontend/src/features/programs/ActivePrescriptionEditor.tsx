import { useEffect, useMemo, useRef, useState } from 'react';
import type { ApiSchemas } from '../../shared/api/types';
import { hasDecimalScale, parseDecimalDraft } from '../../shared/numeric/decimalDraft';

type Plan = ApiSchemas['ExercisePrescriptionPlan'];
type Segment = ApiSchemas['PrescriptionSegment'];
type RepTarget = ApiSchemas['PrescriptionRepTarget'];
type Row = {
  key: number;
  segment: Segment;
  reps: string;
  weight: string;
  effort: string;
  rest: string;
};

function repText(target: Segment['rep_target']): string {
  if (target?.kind === 'exact') return String(target.value ?? '');
  if (target?.kind === 'range') return `${target.min_reps ?? ''}-${target.max_reps ?? ''}`;
  return target?.cap_reps ? `AMRAP ${target.cap_reps}` : 'AMRAP';
}

function parseReps(value: string): RepTarget | null {
  const text = value.trim();
  const exact = /^(\d+)$/.exec(text);
  if (exact && Number(exact[1]) >= 1 && Number(exact[1]) <= 1000)
    return { kind: 'exact', value: Number(exact[1]) };
  const range = /^(\d+)\s*[-–]\s*(\d+)$/.exec(text);
  if (
    range &&
    Number(range[1]) >= 1 &&
    Number(range[2]) <= 1000 &&
    Number(range[1]) <= Number(range[2])
  )
    return { kind: 'range', min_reps: Number(range[1]), max_reps: Number(range[2]) };
  const amrap = /^AMRAP(?:\s+(\d+))?$/i.exec(text);
  if (amrap && (!amrap[1] || (Number(amrap[1]) >= 1 && Number(amrap[1]) <= 1000)))
    return { kind: 'amrap', cap_reps: amrap[1] ? Number(amrap[1]) : null };
  return null;
}

function rowFromSegment(segment: Segment): Row {
  return {
    key: segment.position,
    segment,
    reps: repText(segment.rep_target),
    weight: segment.load_target?.kind === 'absolute' ? String(segment.load_target.value ?? '') : '',
    effort: segment.effort_target?.kind === 'rir' ? String(segment.effort_target.value ?? '') : '',
    rest: String(segment.rest_after_seconds),
  };
}

export function ActivePrescriptionEditor({
  initial,
  sets,
  reps,
  rest,
  onChange,
}: {
  initial: Plan | null;
  sets: number;
  reps: string;
  rest: number;
  onChange: (plan: Plan | null) => void;
}) {
  const [rows, setRows] = useState<Row[]>(
    () =>
      initial?.segments.map(rowFromSegment) ??
      Array.from({ length: sets }, (_, index) => ({
        key: index + 1,
        segment: { position: index + 1, role: 'working', rest_after_seconds: rest },
        reps,
        weight: '',
        effort: '',
        rest: String(rest),
      })),
  );
  const nextKey = useRef(rows.length + 1);
  const groups = useMemo(() => initial?.groups ?? [], [initial]);
  const canChangeCount =
    groups.length === 0 &&
    rows.every(
      (row) =>
        ['working', 'warmup'].includes(row.segment.role) &&
        !['relative_to_top', 'relative_to_previous'].includes(row.segment.load_target?.kind ?? ''),
    );
  const plan = useMemo<Plan | null>(() => {
    const segments: Segment[] = [];
    for (const [index, row] of rows.entries()) {
      const repTarget = parseReps(row.reps);
      const weight = row.weight.trim() ? parseDecimalDraft(row.weight) : null;
      const restSeconds = Number(row.rest);
      const editableLoad =
        !row.segment.load_target ||
        ['user_selected', 'absolute'].includes(row.segment.load_target.kind);
      const editableEffort =
        !row.segment.effort_target || ['none', 'rir'].includes(row.segment.effort_target.kind);
      const effortValue = row.effort === '4+' ? '4+' : parseDecimalDraft(row.effort);
      if (
        !repTarget ||
        !/^\d+$/.test(row.rest) ||
        restSeconds < (index === 0 ? 15 : 0) ||
        restSeconds > 600 ||
        (editableLoad &&
          row.weight.trim() !== '' &&
          (weight === null || weight < 0 || weight > 100000 || !hasDecimalScale(row.weight, 2))) ||
        (editableEffort &&
          row.effort !== '' &&
          (effortValue === null ||
            (typeof effortValue === 'number' && (effortValue < 0 || effortValue > 10))))
      )
        return null;
      segments.push({
        ...row.segment,
        position: index + 1,
        rep_target: repTarget,
        load_target: editableLoad
          ? weight === null
            ? { kind: 'user_selected' }
            : { kind: 'absolute', value: weight }
          : row.segment.load_target,
        effort_target: editableEffort
          ? row.effort === ''
            ? { kind: 'none' }
            : { kind: 'rir', value: effortValue }
          : row.segment.effort_target,
        rest_after_seconds: restSeconds,
      });
    }
    return { version: 1, metric_type: 'strength', groups, segments };
  }, [groups, rows]);
  useEffect(() => onChange(plan), [onChange, plan]);

  const update = (index: number, patch: Partial<Row>) =>
    setRows((current) =>
      current.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)),
    );

  return (
    <div className="program-periodization__prescription">
      <p className="muted">Настройте план каждого подхода. Записанные результаты не изменятся.</p>
      {rows.map((row, index) => {
        const editableLoad =
          !row.segment.load_target ||
          ['user_selected', 'absolute'].includes(row.segment.load_target.kind);
        const editableEffort =
          !row.segment.effort_target || ['none', 'rir'].includes(row.segment.effort_target.kind);
        return (
          <div className="program-periodization__segment" key={row.key}>
            <strong>
              {row.segment.role === 'warmup' ? 'Разминочный' : 'Подход'} {index + 1}
            </strong>
            <div className="program-periodization__fields">
              <label className="field">
                <span>Повторы · подход {index + 1}</span>
                <input
                  value={row.reps}
                  onChange={(event) => update(index, { reps: event.target.value })}
                />
              </label>
              {editableLoad ? (
                <label className="field">
                  <span>Вес, кг · подход {index + 1}</span>
                  <input
                    inputMode="decimal"
                    value={row.weight}
                    onChange={(event) => update(index, { weight: event.target.value })}
                  />
                </label>
              ) : (
                <p className="muted">Исходный способ расчёта нагрузки сохранится.</p>
              )}
              {editableEffort ? (
                <label className="field">
                  <span>RIR · подход {index + 1}</span>
                  <input
                    value={row.effort}
                    placeholder="Не задан"
                    onChange={(event) => update(index, { effort: event.target.value })}
                  />
                </label>
              ) : (
                <p className="muted">Исходное правило усилия сохранится.</p>
              )}
              <label className="field">
                <span>Отдых, сек · подход {index + 1}</span>
                <input
                  type="number"
                  min="0"
                  max="600"
                  value={row.rest}
                  onChange={(event) => update(index, { rest: event.target.value })}
                />
              </label>
            </div>
            {canChangeCount && rows.length > 1 && (
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  setRows((current) => current.filter((_, rowIndex) => rowIndex !== index))
                }
              >
                Убрать подход {index + 1}
              </button>
            )}
          </div>
        );
      })}
      {canChangeCount && rows.length < 100 && (
        <button
          type="button"
          className="secondary"
          onClick={() => {
            const key = nextKey.current++;
            setRows((current) => [
              ...current,
              {
                key,
                segment: {
                  position: current.length + 1,
                  role: 'working',
                  rest_after_seconds: rest,
                },
                reps,
                weight: '',
                effort: '',
                rest: String(rest),
              },
            ]);
          }}
        >
          Добавить подход
        </button>
      )}
      {!plan && (
        <p className="field-error" role="alert">
          Проверьте повторы, вес, RIR и отдых каждого подхода.
        </p>
      )}
    </div>
  );
}
