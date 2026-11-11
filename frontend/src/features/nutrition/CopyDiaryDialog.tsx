import { DateInput } from '../../shared/ui/PickerInput';
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  FoodDiaryCopyPreviewResponse,
  FoodDiaryCopyResponse,
  FoodDiaryEntry,
} from '../../shared/api/types';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { invalidateNutritionSummaries } from '../../shared/queryKeys';
import { Button, CloseIcon, Field, Select } from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import type { MealType } from './FoodPickerDialog';

const mealLabels: Record<MealType, string> = {
  breakfast: 'Завтрак',
  lunch: 'Обед',
  dinner: 'Ужин',
  snacks: 'Перекусы',
};

const confidenceLabels: Record<NonNullable<FoodDiaryEntry['nutrition_confidence']>, string> = {
  exact: 'точные данные',
  approximate: 'приблизительная оценка',
  partial: 'частичные данные',
};

export type CopySubject = (
  | { scope: 'product'; sourceDate: string; sourceMeal: MealType; entryId: number; label: string }
  | { scope: 'meal'; sourceDate: string; sourceMeal: MealType; label: string }
  | { scope: 'day'; sourceDate: string; label: string }
) & { initialTargetDate?: string };

function idempotencyKey(): string {
  return (
    globalThis.crypto?.randomUUID?.() ?? `copy-${Date.now()}-${Math.random().toString(36).slice(2)}`
  );
}

function errorStatus(error: unknown): unknown {
  return error && typeof error === 'object' && 'status' in error ? error.status : undefined;
}

function copyErrorMessage(error: unknown): string {
  const status = errorStatus(error);
  const body = error && typeof error === 'object' && 'body' in error ? error.body : null;
  const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
  if (status === 422 && (detail === 'source day is empty' || detail === 'source meal is empty'))
    return 'В источнике нет записей для копирования.';
  if (
    status === 409 &&
    detail === 'day is marked as fasted; change completeness before adding food'
  )
    return 'В дне назначения отмечено отсутствие питания. Выберите другую дату или измените статус дня.';
  if (status === 401) return 'Сессия истекла. Войдите снова.';
  if (status === 403) return 'Недостаточно прав для копирования.';
  if (status === 422) return 'Проверьте выбранные данные и попробуйте снова.';
  if (status === 0) return 'Нет соединения с сервером. Проверьте интернет.';
  return 'Не удалось выполнить запрос. Попробуйте позже.';
}

function canRetry(error: unknown): boolean {
  const status = errorStatus(error);
  return (
    status === undefined ||
    status === 0 ||
    status === 429 ||
    (typeof status === 'number' && status >= 500)
  );
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(new Date(`${value}T12:00:00`));
}

function entryAmount(entry: FoodDiaryEntry): string {
  if (entry.amount_unit === 'ml') return `${entry.amount} мл`;
  if (entry.amount_unit === 'serving') return `${entry.amount} порц.`;
  return `${entry.weight_g ?? entry.amount} г`;
}

function entryDetails(entry: FoodDiaryEntry): string {
  const confidence = entry.nutrition_confidence
    ? confidenceLabels[entry.nutrition_confidence]
    : 'данные сохранены как в источнике';
  const origin =
    entry.entry_kind === 'recipe'
      ? 'рецепт'
      : entry.entry_kind === 'quick_add'
        ? 'ручная оценка'
        : 'продукт';
  return `${entryAmount(entry)} · ${origin} · ${confidence}`;
}

export function CopyDiaryDialog({
  subject,
  today,
  onClose,
}: {
  subject: CopySubject;
  today: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const initialTargetDate = subject.initialTargetDate ?? today;
  const [targetDate, setTargetDate] = useState(
    subject.scope === 'day' && initialTargetDate === subject.sourceDate ? '' : initialTargetDate,
  );
  const [targetMeal, setTargetMeal] = useState<MealType>(
    subject.scope === 'day' ? 'breakfast' : subject.sourceMeal,
  );
  const confirmationKeyRef = useRef<{ token: string; key: string; revision: number } | null>(null);
  const submittingRef = useRef(false);
  const closeDialog = () => {
    if (!submittingRef.current) onClose();
  };
  const panelRef = useModalA11y<HTMLDivElement>(true, closeDialog, '#nutrition-copy-target-date');
  const targetDateValid = Boolean(
    targetDate &&
    targetDate <= today &&
    (subject.scope !== 'day' || targetDate !== subject.sourceDate),
  );
  const targetDateHint = targetDateValid
    ? undefined
    : targetDate && targetDate > today
      ? 'Выберите дату не позже сегодняшней.'
      : subject.scope === 'day'
        ? 'Выберите дату, которая отличается от исходной.'
        : 'Выберите дату назначения.';

  useEffect(() => {
    trackProductEvent({
      name: 'nutrition_food_add_path_selected',
      surface: productEventSurface(),
      path: 'repeat',
    });
    trackProductEvent({
      name: 'nutrition_food_repeat_used',
      surface: productEventSurface(),
      scope: subject.scope,
      outcome: 'started',
    });
  }, [subject.scope]);

  const previewBody = useMemo(() => {
    const common = { source_date: subject.sourceDate, target_date: targetDate };
    return subject.scope === 'day'
      ? common
      : subject.scope === 'meal'
        ? { ...common, source_meal_type: subject.sourceMeal, target_meal_type: targetMeal }
        : {
            ...common,
            source_entry_id: subject.entryId,
            source_meal_type: subject.sourceMeal,
            target_meal_type: targetMeal,
          };
  }, [subject, targetDate, targetMeal]);
  const requestIdentity = JSON.stringify([subject.scope, previewBody]);
  const currentIdentityRef = useRef(requestIdentity);
  const revisionRef = useRef(0);
  const settledRevisionRef = useRef(0);
  useLayoutEffect(() => {
    if (currentIdentityRef.current !== requestIdentity) {
      currentIdentityRef.current = requestIdentity;
      revisionRef.current += 1;
      confirmationKeyRef.current = null;
    }
  }, [requestIdentity]);

  const preview = useQuery({
    queryKey: ['nutrition', 'copy-preview', subject.scope, previewBody],
    queryFn: ({ signal }) =>
      api<FoodDiaryCopyPreviewResponse>(`/api/v1/nutrition/diary/copy/${subject.scope}/preview`, {
        method: 'POST',
        body: previewBody,
        signal,
      }),
    enabled: targetDateValid,
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const confirmation = useMutation({
    mutationFn: ({ key, token }: { key: string; token: string; revision: number }) =>
      api<FoodDiaryCopyResponse>(`/api/v1/nutrition/diary/copy/${subject.scope}`, {
        method: 'POST',
        headers: { 'Idempotency-Key': key },
        body: { ...previewBody, preview_token: token },
      }),
    onSuccess: async (result, variables) => {
      trackProductEvent({
        name: 'nutrition_food_repeat_used',
        surface: productEventSurface(),
        scope: subject.scope,
        outcome: 'completed',
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['nutrition', 'foods', 'recent'] }),
        invalidateNutritionSummaries(queryClient),
        queryClient.invalidateQueries({ queryKey: ['nutrition', 'diary'] }),
      ]);
      toast(
        result.replayed
          ? 'Копия уже была добавлена — повторов не создано'
          : subject.scope === 'day'
            ? `Добавлено записей: ${result.entries.length} · ${formatDate(result.target_date)}`
            : `Добавлено записей: ${result.entries.length}`,
      );
      submittingRef.current = false;
      if (variables.revision === revisionRef.current) onClose();
    },
    onError: (error, variables) => {
      submittingRef.current = false;
      if (variables.revision !== revisionRef.current && canRetry(error)) {
        toast(
          'Не удалось узнать результат копирования. Проверьте дату назначения в дневнике.',
          'error',
        );
      }
    },
  });

  const resetConfirmation = confirmation.reset;
  useEffect(() => {
    if (settledRevisionRef.current !== revisionRef.current && !submittingRef.current) {
      settledRevisionRef.current = revisionRef.current;
      confirmationKeyRef.current = null;
      resetConfirmation();
    }
  }, [requestIdentity, confirmation.isPending, resetConfirmation]);

  const scopeLabel =
    subject.scope === 'product'
      ? 'Повторить продукт'
      : subject.scope === 'meal'
        ? 'Повторить приём пищи'
        : 'Копировать записи дня';
  const submit = () => {
    const previousAttempt =
      confirmationKeyRef.current?.revision === revisionRef.current
        ? confirmationKeyRef.current
        : null;
    const token =
      confirmation.error && canRetry(confirmation.error) && previousAttempt
        ? previousAttempt.token
        : preview.data?.preview_token;
    if (
      !targetDateValid ||
      !preview.isSuccess ||
      preview.isFetching ||
      !preview.data?.entries.length ||
      !token ||
      (confirmation.error && !canRetry(confirmation.error)) ||
      confirmation.isPending ||
      submittingRef.current
    )
      return;
    submittingRef.current = true;
    const key = previousAttempt?.token === token ? previousAttempt.key : idempotencyKey();
    confirmationKeyRef.current = { key, token, revision: revisionRef.current };
    confirmation.mutate({ key, token, revision: revisionRef.current });
  };
  const sourceLabel = subject.label;

  return (
    <div
      className="modal nutrition-copy"
      role="dialog"
      aria-modal="true"
      aria-labelledby="nutrition-copy-title"
    >
      <div className="modal__backdrop" aria-hidden="true" onClick={closeDialog} />
      <div className="modal__panel nutrition-copy__panel" ref={panelRef} tabIndex={-1}>
        <header data-glass="" data-glass-variant="regular" className="nutrition-picker__header">
          <div>
            <span className="eyebrow">Сначала проверьте записи</span>
            <h2 id="nutrition-copy-title">{scopeLabel}</h2>
          </div>
          <Button
            variant="ghost"
            type="button"
            aria-label="Закрыть копирование"
            disabled={confirmation.isPending}
            onClick={closeDialog}
          >
            <CloseIcon />
          </Button>
        </header>
        <form
          className="nutrition-copy__form"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          {subject.scope === 'day' && (
            <p className="nutrition-copy__notice">
              Все записи питания будут добавлены в другую дату. Исходные записи и существующие
              записи дня назначения сохранятся.
            </p>
          )}
          <dl className="nutrition-copy__source">
            <div>
              <dt>Что копируем</dt>
              <dd>{sourceLabel}</dd>
            </div>
            <div>
              <dt>Откуда</dt>
              <dd>
                {formatDate(subject.sourceDate)}
                {subject.scope !== 'day' ? ` · ${mealLabels[subject.sourceMeal]}` : ''}
              </dd>
            </div>
          </dl>
          <div className="nutrition-copy__target">
            <Field label="Дата назначения" labelFor="nutrition-copy-target-date">
              <DateInput
                className="ui-input"
                id="nutrition-copy-target-date"
                max={today}
                required
                disabled={confirmation.isPending}
                aria-invalid={targetDate ? !targetDateValid : undefined}
                aria-describedby={targetDateHint ? 'nutrition-copy-date-hint' : undefined}
                value={targetDate}
                onChange={(event) => {
                  confirmation.reset();
                  confirmationKeyRef.current = null;
                  setTargetDate(event.target.value);
                }}
              />
              {targetDateHint && (
                <span className="ui-field__hint" id="nutrition-copy-date-hint">
                  {targetDateHint}
                </span>
              )}
            </Field>
            {subject.scope !== 'day' && (
              <Field label="Приём пищи" labelFor="nutrition-copy-target-meal">
                <Select
                  id="nutrition-copy-target-meal"
                  value={targetMeal}
                  disabled={confirmation.isPending}
                  onChange={(event) => {
                    confirmation.reset();
                    confirmationKeyRef.current = null;
                    setTargetMeal(event.target.value as MealType);
                  }}
                >
                  {Object.entries(mealLabels).map(([value, label]) => (
                    <option value={value} key={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
          </div>
          <section
            className="nutrition-copy__preview"
            aria-labelledby="nutrition-copy-preview-title"
          >
            <div className="nutrition-copy__preview-heading">
              <div>
                <span className="eyebrow">Проверка</span>
                <h3 id="nutrition-copy-preview-title">Что будет добавлено</h3>
              </div>
              {targetDateValid && preview.isSuccess && !preview.isFetching && (
                <span>
                  {subject.scope === 'day'
                    ? `Записей: ${preview.data.entries.length}`
                    : `${preview.data.entries.length} записей`}
                </span>
              )}
            </div>
            {!targetDateValid ? (
              <p className="nutrition-copy__preview-state">
                Выберите дату назначения, чтобы увидеть записи.
              </p>
            ) : preview.isFetching ? (
              <p className="nutrition-copy__preview-state">Проверяем записи…</p>
            ) : preview.error ? (
              <div className="nutrition-inline-error" role="alert">
                <span>{copyErrorMessage(preview.error)}</span>
                {canRetry(preview.error) && (
                  <button type="button" onClick={() => void preview.refetch()}>
                    Повторить
                  </button>
                )}
              </div>
            ) : preview.data?.entries.length ? (
              <ul className="nutrition-copy__preview-list">
                {preview.data.entries.map((entry) => (
                  <li key={entry.id}>
                    <strong>{entry.food_name}</strong>
                    <span>{entryDetails(entry)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="nutrition-copy__preview-state">Подходящих записей не найдено.</p>
            )}
          </section>
          {subject.scope !== 'day' && (
            <p className="nutrition-copy__notice">
              Новые записи добавятся к уже существующим. Ничего в выбранном дне не будет заменено.
            </p>
          )}
          {confirmation.error && (
            <div className="nutrition-inline-error" role="alert">
              <span>
                {errorStatus(confirmation.error) === 409
                  ? 'Предварительный просмотр устарел. Обновите его перед копированием.'
                  : errorStatus(confirmation.error) === 0
                    ? 'Нет соединения. Записи могли добавиться — повторите запрос или проверьте дневник.'
                    : copyErrorMessage(confirmation.error)}
              </span>
              {errorStatus(confirmation.error) === 409 ? (
                <button
                  type="button"
                  onClick={() => {
                    confirmationKeyRef.current = null;
                    confirmation.reset();
                    void preview.refetch();
                  }}
                >
                  Обновить просмотр
                </button>
              ) : (
                canRetry(confirmation.error) && (
                  <button type="button" disabled={confirmation.isPending} onClick={submit}>
                    Повторить
                  </button>
                )
              )}
            </div>
          )}
          <div className="nutrition-editor__actions app-action-group">
            <Button
              type="submit"
              disabled={
                !targetDateValid ||
                confirmation.isPending ||
                (Boolean(confirmation.error) && !canRetry(confirmation.error)) ||
                preview.isFetching ||
                !preview.isSuccess ||
                !preview.data?.entries.length
              }
            >
              {confirmation.isPending ? 'Добавляем…' : 'Подтвердить'}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={confirmation.isPending}
              onClick={closeDialog}
            >
              Отмена
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
