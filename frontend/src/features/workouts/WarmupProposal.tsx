import { useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import type {
  WarmupProposalApply,
  WarmupProposalPreview,
  WarmupProposalRow,
} from '../../shared/api/types';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Button, CloseIcon, IconButton, Input } from '../../shared/ui/common';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { useOnlineStatus } from '../../shared/ui/OnlineStatus';
import { createWorkoutMutationId } from './activeWorkoutQueue';

type DraftRow = { weight: string; reps: string };

function readableError(reason: unknown): string {
  if (reason instanceof ApiError) {
    const detail =
      reason.body && typeof reason.body === 'object' && 'detail' in reason.body
        ? (reason.body as { detail?: unknown }).detail
        : null;
    if (detail && typeof detail === 'object' && 'message' in detail) {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === 'string' && message) return message;
    }
  }
  return reason instanceof Error ? reason.message : 'Не удалось выполнить действие.';
}

function toDraftRows(rows: WarmupProposalRow[]): DraftRow[] {
  return rows.map((row) => ({ weight: String(row.weight_kg), reps: String(row.reps) }));
}

function parseRows(rows: DraftRow[]): WarmupProposalRow[] | null {
  const parsed = rows.map((row) => ({
    weight_kg: Number(row.weight),
    reps: Number(row.reps),
  }));
  if (
    parsed.some(
      (row) =>
        !Number.isFinite(row.weight_kg) ||
        row.weight_kg <= 0 ||
        row.weight_kg > 1000 ||
        !Number.isInteger(row.reps) ||
        row.reps < 1 ||
        row.reps > 30,
    )
  ) {
    return null;
  }
  return parsed;
}

export function WarmupProposal({
  workoutId,
  workoutExerciseId,
  targetSetId,
  exerciseTitle,
  workingWeight,
  disabled,
  hasWarmupRows,
}: {
  workoutId: number;
  workoutExerciseId: number;
  targetSetId: number;
  exerciseTitle: string;
  workingWeight: string;
  disabled: boolean;
  hasWarmupRows: boolean;
}) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const online = useOnlineStatus();
  const titleId = useId();
  const descriptionId = useId();
  const mutationId = useRef<string | null>(null);
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<WarmupProposalPreview | null>(null);
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useModalA11y<HTMLDivElement>(
    open,
    () => setOpen(false),
    '.warmup-proposal-dialog__close',
  );
  const numericWorkingWeight = Number(workingWeight);
  const canPreview = Number.isFinite(numericWorkingWeight) && numericWorkingWeight > 0;

  const previewMutation = useMutation({
    mutationFn: () =>
      api<WarmupProposalPreview>(
        `/api/v1/workouts/${workoutId}/exercises/${workoutExerciseId}/warmup-proposals/preview`,
        {
          method: 'POST',
          body: { target_set_id: targetSetId, working_weight_kg: numericWorkingWeight },
        },
      ),
    onSuccess: (result) => {
      setPreview(result);
      setRows(toDraftRows(result.rows));
      setError(null);
      mutationId.current = null;
    },
    onError: (reason) => setError(readableError(reason)),
  });

  const applyMutation = useMutation({
    mutationFn: (request: {
      rows: WarmupProposalRow[];
      state_token: string;
      proposal_token: string;
    }) =>
      api<WarmupProposalApply>(
        `/api/v1/workouts/${workoutId}/exercises/${workoutExerciseId}/warmup-proposals/apply`,
        {
          method: 'POST',
          body: {
            target_set_id: targetSetId,
            working_weight_kg: numericWorkingWeight,
            rows: request.rows,
            state_token: request.state_token,
            proposal_token: request.proposal_token,
            mutation_id: mutationId.current ?? (mutationId.current = createWorkoutMutationId()),
          },
        },
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['workout'] });
      toast('Разминочные подходы добавлены в эту тренировку');
      mutationId.current = null;
      setOpen(false);
      setPreview(null);
      setRows([]);
    },
    onError: (reason) => {
      if (reason instanceof ApiError && reason.status === 409) {
        setPreview(null);
        mutationId.current = null;
        setError('Тренировка уже изменилась. Сформируйте предложение заново перед добавлением.');
        return;
      }
      setError(readableError(reason));
    },
  });

  const close = () => {
    if (previewMutation.isPending || applyMutation.isPending) return;
    setOpen(false);
  };

  const requestPreview = () => {
    if (!online) {
      setError('Для подготовки разминки нужно подключение к интернету. Ничего не сохранено.');
      return;
    }
    if (!canPreview) {
      setError('Сначала укажите рабочий вес.');
      return;
    }
    setError(null);
    previewMutation.mutate();
  };

  const apply = () => {
    if (!preview?.state_token || !preview.proposal_token) return;
    const parsedRows = parseRows(rows);
    if (!parsedRows || parsedRows.length === 0 || parsedRows.length > preview.max_rows) {
      setError(`Добавьте от одного до ${preview.max_rows} подходов и проверьте значения.`);
      return;
    }
    if (parsedRows.some((row) => row.weight_kg > numericWorkingWeight)) {
      setError('Вес разминки не может быть выше рабочего веса.');
      return;
    }
    setError(null);
    applyMutation.mutate({
      rows: parsedRows,
      state_token: preview.state_token,
      proposal_token: preview.proposal_token,
    });
  };

  const openDialog = () => {
    if (disabled || !online || !canPreview || hasWarmupRows) return;
    setPreview(null);
    setRows([]);
    setError(null);
    mutationId.current = null;
    setOpen(true);
  };

  if (hasWarmupRows) {
    return (
      <p className="active-workout-helper-muted warmup-proposal-status" role="status">
        Разминочные подходы уже добавлены.
      </p>
    );
  }

  return (
    <div className="warmup-proposal-entry" data-testid="warmup-proposal-entry">
      <Button
        type="button"
        variant="secondary"
        disabled={disabled || !online || !canPreview}
        onClick={openDialog}
      >
        Подготовить разминку
      </Button>
      {!online ? (
        <p className="active-workout-helper-muted" role="status">
          Разминка требует подключения. Ничего не сохранено.
        </p>
      ) : !canPreview ? (
        <p className="active-workout-helper-muted" role="status">
          Введите рабочий вес, чтобы получить предложение.
        </p>
      ) : null}

      {open &&
        createPortal(
          <div
            className="modal app-section--design-v2 workout-adaptation-dialog warmup-proposal-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={descriptionId}
          >
            <button
              className="modal__backdrop"
              type="button"
              aria-label="Закрыть предложение разминки"
              onClick={close}
            />
            <div
              className="modal__panel workout-adaptation-dialog__panel"
              ref={panelRef}
              tabIndex={-1}
            >
              <header className="workout-adaptation-dialog__header">
                <div>
                  <span className="eyebrow">Только эта тренировка</span>
                  <h2 id={titleId}>Подготовить разминку</h2>
                  <p id={descriptionId}>
                    Для «{exerciseTitle}» рассчитаем отдельные подходы от рабочего веса{' '}
                    {workingWeight} кг. Они появятся в тренировке только после вашего подтверждения.
                  </p>
                </div>
                <IconButton
                  className="workout-adaptation-dialog__close warmup-proposal-dialog__close"
                  type="button"
                  aria-label="Закрыть предложение разминки"
                  onClick={close}
                >
                  <CloseIcon />
                </IconButton>
              </header>

              <div className="workout-adaptation-dialog__body">
                {!preview && (
                  <section className="warmup-proposal-intro" aria-live="polite">
                    <strong>Редактируемое предложение</strong>
                    <p>
                      Ничего не сохраняется на этом шаге. После расчёта можно изменить вес и
                      повторы, добавить или удалить подход, а затем подтвердить результат.
                    </p>
                  </section>
                )}

                {preview?.status === 'unavailable' && (
                  <section className="warmup-proposal-intro" role="status">
                    <strong>Предложение недоступно</strong>
                    <p>{preview.message}</p>
                  </section>
                )}

                {preview?.status === 'proposal' && (
                  <section className="warmup-proposal-editor" aria-live="polite">
                    <div className="warmup-proposal-editor__heading">
                      <div>
                        <span className="eyebrow">Правило {preview.ruleset_version}</span>
                        <h3>Проверьте подходы</h3>
                      </div>
                      <span className="warmup-proposal-editor__limit">
                        максимум {preview.max_rows}
                      </span>
                    </div>
                    <p className="warmup-proposal-editor__message">{preview.message}</p>
                    <div className="warmup-proposal-rows" role="list" aria-label="Подходы разминки">
                      {rows.map((row, index) => (
                        <div className="warmup-proposal-row" role="listitem" key={index}>
                          <span className="warmup-proposal-row__number">{index + 1}</span>
                          <label>
                            <span>Вес, кг</span>
                            <Input
                              aria-label={`Вес разминки, подход ${index + 1}`}
                              inputMode="decimal"
                              min="0.5"
                              max={numericWorkingWeight}
                              step="0.5"
                              type="number"
                              value={row.weight}
                              onChange={(event) =>
                                setRows((current) =>
                                  current.map((item, itemIndex) =>
                                    itemIndex === index
                                      ? { ...item, weight: event.target.value }
                                      : item,
                                  ),
                                )
                              }
                            />
                          </label>
                          <label>
                            <span>Повторы</span>
                            <Input
                              aria-label={`Повторы разминки, подход ${index + 1}`}
                              inputMode="numeric"
                              min="1"
                              max="30"
                              step="1"
                              type="number"
                              value={row.reps}
                              onChange={(event) =>
                                setRows((current) =>
                                  current.map((item, itemIndex) =>
                                    itemIndex === index
                                      ? { ...item, reps: event.target.value }
                                      : item,
                                  ),
                                )
                              }
                            />
                          </label>
                          <button
                            className="warmup-proposal-row__remove"
                            type="button"
                            aria-label={`Удалить подход разминки ${index + 1}`}
                            onClick={() =>
                              setRows((current) =>
                                current.filter((_, itemIndex) => itemIndex !== index),
                              )
                            }
                          >
                            Удалить
                          </button>
                        </div>
                      ))}
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      disabled={rows.length >= preview.max_rows}
                      onClick={() => setRows((current) => [...current, { weight: '', reps: '' }])}
                    >
                      Добавить подход
                    </Button>
                    <p className="warmup-proposal-editor__note">
                      После подтверждения эти строки станут незавершёнными подходами разминки.
                      История и аналитика не изменятся, пока подходы не выполнены.
                    </p>
                  </section>
                )}

                {error && (
                  <div className="adaptation-error" role="alert">
                    <strong>Не удалось подготовить разминку</strong>
                    <p>{error}</p>
                  </div>
                )}
              </div>

              <footer className="workout-adaptation-dialog__footer">
                <Button
                  type="button"
                  variant="ghost"
                  disabled={applyMutation.isPending}
                  onClick={close}
                >
                  Отмена
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={!online || previewMutation.isPending || applyMutation.isPending}
                  aria-busy={previewMutation.isPending}
                  onClick={requestPreview}
                >
                  {previewMutation.isPending
                    ? 'Считаем…'
                    : preview?.status === 'proposal' || error
                      ? 'Обновить предложение'
                      : 'Рассчитать предложение'}
                </Button>
                {preview?.status === 'proposal' &&
                  preview.state_token &&
                  preview.proposal_token && (
                    <Button
                      type="button"
                      disabled={!online || applyMutation.isPending}
                      aria-busy={applyMutation.isPending}
                      onClick={apply}
                    >
                      {applyMutation.isPending ? 'Добавляем…' : 'Добавить в тренировку'}
                    </Button>
                  )}
              </footer>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
