import { useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import type {
  WorkoutRecoveryApply,
  WorkoutRecoveryPreview,
  WorkoutRecoveryRequest,
  WorkoutScheduleItem,
} from '../../shared/api/types';
import { dateInputValue, formatCalendarDate } from '../../shared/dateTime';
import { workoutStatusLabel } from '../../shared/statusLabels';
import { Badge, Button, CloseIcon, Field, IconButton, Select } from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { DateInput, TimeInput } from '../../shared/ui/PickerInput';
import { useModalA11y } from '../../shared/ui/useModalA11y';

type RecoveryAction = WorkoutRecoveryRequest['action'];

function formatDate(value: string): string {
  return formatCalendarDate(value, {
    day: 'numeric',
    month: 'short',
    weekday: 'short',
  });
}

function scheduleText(item: WorkoutScheduleItem): string {
  return `${formatDate(item.scheduled_date)}${item.scheduled_time ? ` в ${item.scheduled_time.slice(0, 5)}` : ''}`;
}

export function WorkoutRecovery({
  workout,
  timeZone,
  open: controlledOpen,
  onOpenChange,
  hideTrigger = false,
  fullWidth = false,
  triggerLabel,
  onApplied,
}: {
  workout: WorkoutScheduleItem;
  timeZone?: string | null;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  hideTrigger?: boolean;
  fullWidth?: boolean;
  triggerLabel?: string;
  onApplied?: () => void;
}) {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const titleId = useId();
  const descriptionId = useId();
  const minDate = dateInputValue(new Date(), timeZone || 'UTC');
  const [internalOpen, setInternalOpen] = useState(false);
  const [action, setAction] = useState<RecoveryAction>('move');
  const [scheduledDate, setScheduledDate] = useState(() =>
    workout.scheduled_date < minDate ? minDate : workout.scheduled_date,
  );
  const [scheduledTime, setScheduledTime] = useState(workout.scheduled_time?.slice(0, 5) ?? '');
  const [preview, setPreview] = useState<WorkoutRecoveryPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isOpen = controlledOpen ?? internalOpen;
  const setOpen = (next: boolean) => {
    if (next) {
      setAction('move');
      setScheduledDate(workout.scheduled_date < minDate ? minDate : workout.scheduled_date);
      setScheduledTime(workout.scheduled_time?.slice(0, 5) ?? '');
      setPreview(null);
      setError(null);
    }
    if (controlledOpen === undefined) setInternalOpen(next);
    onOpenChange?.(next);
  };
  const panelRef = useModalA11y<HTMLDivElement>(
    isOpen,
    () => setOpen(false),
    '.workout-adaptation-dialog__close',
  );

  const buildRequest = (): WorkoutRecoveryRequest => ({
    action,
    expected_scheduled_date: workout.scheduled_date,
    expected_scheduled_time: workout.scheduled_time ?? null,
    scheduled_date: action === 'move' ? scheduledDate : null,
    scheduled_time: action === 'move' ? scheduledTime || null : null,
  });

  const previewMutation = useMutation({
    mutationFn: (request: WorkoutRecoveryRequest) =>
      api<WorkoutRecoveryPreview>(`/api/v1/workouts/${workout.id}/recovery/preview`, {
        method: 'POST',
        body: request,
      }),
    onSuccess: (result) => {
      setPreview(result);
      setError(null);
    },
    onError: (reason) => setError((reason as Error).message),
  });
  const applyMutation = useMutation({
    mutationFn: ({ request, token }: { request: WorkoutRecoveryRequest; token: string }) =>
      api<WorkoutRecoveryApply>(`/api/v1/workouts/${workout.id}/recovery/apply`, {
        method: 'POST',
        body: { ...request, preview_token: token },
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workout'] }),
        queryClient.invalidateQueries({ queryKey: ['progress'] }),
        queryClient.invalidateQueries({ queryKey: ['weekly-check-ins'] }),
      ]);
      toast(action === 'move' ? 'Тренировка перенесена' : 'Тренировка отмечена пропущенной');
      setOpen(false);
      setPreview(null);
      setError(null);
      onApplied?.();
    },
    onError: (reason) => {
      if (reason instanceof ApiError && reason.status === 409) {
        setPreview(null);
        setError('Расписание уже изменилось. Обновите варианты перед применением.');
        return;
      }
      setError((reason as Error).message);
    },
  });

  const requestPreview = () => {
    setError(null);
    previewMutation.mutate(buildRequest());
  };

  return (
    <>
      {!hideTrigger && (
        <Button
          fullWidth={fullWidth}
          type="button"
          variant="secondary"
          onClick={() => setOpen(true)}
        >
          {triggerLabel ||
            (workout.status === 'missed' ? 'Вернуться к тренировке' : 'Изменить план')}
        </Button>
      )}

      {hideTrigger && (
        <section
          className="today-recovery-card semantic-card semantic-card--action"
          aria-labelledby={`${titleId}-summary`}
        >
          <Badge tone="warning">Нужно решить</Badge>
          <h2 id={`${titleId}-summary`}>Тренировка осталась невыполненной</h2>
          <p>
            {workout.title} · {scheduleText(workout)}. Посмотрите изменения и выберите новый день
            или явно отметьте тренировку пропущенной. Остальные тренировки и программа не
            изменятся.
          </p>
        </section>
      )}

      {isOpen &&
        createPortal(
          <div
            className="modal app-section--design-v2 workout-recovery-dialog workout-adaptation-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={descriptionId}
          >
            <button
              className="modal__backdrop"
              type="button"
              aria-label="Закрыть восстановление расписания"
              onClick={() => setOpen(false)}
            />
            <div
              className="modal__panel workout-recovery-dialog__panel workout-adaptation-dialog__panel"
              ref={panelRef}
              tabIndex={-1}
            >
              <header className="workout-recovery-dialog__header workout-adaptation-dialog__header">
                <div>
                  <span className="eyebrow">Сначала — предпросмотр изменений</span>
                  <h2 id={titleId}>Восстановить план</h2>
                  <p id={descriptionId}>
                    До подтверждения расписание и история не меняются. После подтверждения
                    применится только выбранное действие.
                  </p>
                </div>
                <IconButton
                  className="workout-recovery-dialog__close workout-adaptation-dialog__close"
                  type="button"
                  aria-label="Закрыть восстановление расписания"
                  onClick={() => setOpen(false)}
                >
                  <CloseIcon />
                </IconButton>
              </header>

              <div className="workout-recovery-dialog__body workout-adaptation-dialog__body">
                <p>
                  <strong>{workout.title}</strong> · {scheduleText(workout)} ·{' '}
                  {workoutStatusLabel(workout.status)}
                </p>
                <Field label="Что сделать с этой тренировкой" labelFor={`${titleId}-action`}>
                  <Select
                    id={`${titleId}-action`}
                    value={action}
                    onChange={(event) => {
                      setAction(event.target.value as RecoveryAction);
                      setPreview(null);
                      setError(null);
                    }}
                  >
                    <option value="move">Перенести на другой день</option>
                    <option value="skip">Отметить как пропущенную</option>
                  </Select>
                </Field>
                {action === 'move' && (
                  <div className="workout-recovery-dialog__date-fields adaptation-choice-grid">
                    <Field label="Новая дата" labelFor={`${titleId}-date`}>
                      <DateInput
                        id={`${titleId}-date`}
                        min={minDate}
                        value={scheduledDate}
                        onChange={(event) => {
                          setScheduledDate(event.target.value);
                          setPreview(null);
                        }}
                        required
                      />
                    </Field>
                    <Field label="Время" labelFor={`${titleId}-time`}>
                      <TimeInput
                        id={`${titleId}-time`}
                        value={scheduledTime}
                        onChange={(event) => {
                          setScheduledTime(event.target.value);
                          setPreview(null);
                        }}
                      />
                    </Field>
                  </div>
                )}

                {error && (
                  <p className="today-inline-state adaptation-inline-error" role="alert">
                    {error}
                  </p>
                )}

                {preview && (
                  <section
                    className="workout-recovery-preview adaptation-preview"
                    aria-live="polite"
                    aria-labelledby={`${titleId}-preview`}
                  >
                    <span className="eyebrow">Предпросмотр</span>
                    <h3 id={`${titleId}-preview`}>
                      {preview.status === 'preview' ? 'Что изменится' : 'План остаётся прежним'}
                    </h3>
                    <p>{preview.message}</p>
                    {preview.changes.map((change) => (
                      <p key={change.kind}>
                        {change.kind === 'moved'
                          ? `${formatDate(change.from_scheduled_date)} → ${change.to_scheduled_date ? formatDate(change.to_scheduled_date) : '—'}`
                          : `Будет отмечена как пропущенная: ${formatDate(change.from_scheduled_date)}`}
                      </p>
                    ))}
                    {preview.remaining_workouts.length > 0 && (
                      <div>
                        <strong>Что останется в плане</strong>
                        <ul>
                          {preview.remaining_workouts.slice(0, 3).map((item) => (
                            <li key={item.id}>
                              {item.title} · {scheduleText(item)}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </section>
                )}
              </div>

              <footer className="workout-recovery-dialog__footer workout-adaptation-dialog__footer">
                <Button
                  type="button"
                  variant="ghost"
                  disabled={applyMutation.isPending}
                  onClick={() => setOpen(false)}
                >
                  Отмена
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={previewMutation.isPending || applyMutation.isPending}
                  onClick={requestPreview}
                >
                  {previewMutation.isPending
                    ? 'Проверяем…'
                    : preview
                      ? 'Обновить варианты'
                      : 'Показать изменения'}
                </Button>
                {preview?.status === 'preview' && preview.preview_token && (
                  <Button
                    type="button"
                    disabled={applyMutation.isPending}
                    onClick={() =>
                      applyMutation.mutate({
                        request: buildRequest(),
                        token: preview.preview_token!,
                      })
                    }
                  >
                    {applyMutation.isPending ? 'Применяем…' : 'Подтвердить'}
                  </Button>
                )}
              </footer>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
