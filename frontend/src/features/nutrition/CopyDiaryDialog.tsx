import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  FoodDiaryCopyPreviewResponse,
  FoodDiaryCopyResponse,
  FoodDiaryEntry,
} from '../../shared/api/types';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { invalidateNutritionSummaries } from '../../shared/queryKeys';
import { Button, CloseIcon, Field, Input, Select } from '../../shared/ui/common';
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
  const panelRef = useModalA11y<HTMLDivElement>(true, onClose, '#nutrition-copy-target-date');
  const [targetDate, setTargetDate] = useState(subject.initialTargetDate ?? today);
  const [targetMeal, setTargetMeal] = useState<MealType>(
    subject.scope === 'day' ? 'breakfast' : subject.sourceMeal,
  );
  const confirmationKeyRef = useRef<string | null>(null);
  const submittingRef = useRef(false);

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

  const preview = useQuery({
    queryKey: ['nutrition', 'copy-preview', subject.scope, previewBody],
    queryFn: () =>
      api<FoodDiaryCopyPreviewResponse>(`/api/v1/nutrition/diary/copy/${subject.scope}/preview`, {
        method: 'POST',
        body: previewBody,
      }),
    enabled: Boolean(targetDate),
    retry: false,
    refetchOnWindowFocus: false,
  });

  const confirmation = useMutation({
    mutationFn: ({ key, token }: { key: string; token: string }) =>
      api<FoodDiaryCopyResponse>(`/api/v1/nutrition/diary/copy/${subject.scope}`, {
        method: 'POST',
        headers: { 'Idempotency-Key': key },
        body: { ...previewBody, preview_token: token },
      }),
    onSuccess: async (result) => {
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
          : `Добавлено записей: ${result.entries.length}`,
      );
      submittingRef.current = false;
      onClose();
    },
    onError: () => {
      submittingRef.current = false;
    },
  });

  const scopeLabel =
    subject.scope === 'product'
      ? 'Повторить продукт'
      : subject.scope === 'meal'
        ? 'Повторить приём пищи'
        : 'Повторить день';
  const submit = () => {
    const token = preview.data?.preview_token;
    if (!token || confirmation.isPending || submittingRef.current) return;
    submittingRef.current = true;
    const key = confirmationKeyRef.current ?? idempotencyKey();
    confirmationKeyRef.current = key;
    confirmation.mutate({ key, token });
  };
  const sourceLabel = subject.label;

  return (
    <div
      className="modal nutrition-copy"
      role="dialog"
      aria-modal="true"
      aria-labelledby="nutrition-copy-title"
    >
      <div className="modal__backdrop" aria-hidden="true" onClick={onClose} />
      <div className="modal__panel nutrition-copy__panel" ref={panelRef} tabIndex={-1}>
        <header data-glass="" data-glass-variant="regular" className="nutrition-picker__header">
          <div>
            <span className="eyebrow">Сначала проверьте записи</span>
            <h2 id="nutrition-copy-title">{scopeLabel}</h2>
          </div>
          <Button variant="ghost" type="button" aria-label="Закрыть копирование" onClick={onClose}>
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
              <Input
                id="nutrition-copy-target-date"
                type="date"
                max={today}
                required
                value={targetDate}
                onChange={(event) => {
                  confirmation.reset();
                  submittingRef.current = false;
                  confirmationKeyRef.current = null;
                  setTargetDate(event.target.value);
                }}
              />
            </Field>
            {subject.scope !== 'day' && (
              <Field label="Приём пищи" labelFor="nutrition-copy-target-meal">
                <Select
                  id="nutrition-copy-target-meal"
                  value={targetMeal}
                  onChange={(event) => {
                    confirmation.reset();
                    submittingRef.current = false;
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
              {preview.data && <span>{preview.data.entries.length} записей</span>}
            </div>
            {preview.isLoading ? (
              <p className="nutrition-copy__preview-state">Проверяем записи…</p>
            ) : preview.error ? (
              <div className="nutrition-inline-error" role="alert">
                <span>Не удалось подготовить предварительный просмотр.</span>
                <button type="button" onClick={() => void preview.refetch()}>
                  Повторить
                </button>
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
          <p className="nutrition-copy__notice">
            Новые записи добавятся к уже существующим. Ничего в выбранном дне не будет заменено.
          </p>
          {confirmation.error && (
            <div className="nutrition-inline-error" role="alert">
              <span>Не удалось добавить записи. Предварительный просмотр мог устареть.</span>
              <button type="button" disabled={confirmation.isPending} onClick={submit}>
                Повторить
              </button>
            </div>
          )}
          <div className="nutrition-editor__actions app-action-group">
            <Button
              type="submit"
              disabled={
                confirmation.isPending || preview.isLoading || !preview.data?.entries.length
              }
            >
              {confirmation.isPending ? 'Добавляем…' : 'Подтвердить'}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={confirmation.isPending}
              onClick={onClose}
            >
              Отмена
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
