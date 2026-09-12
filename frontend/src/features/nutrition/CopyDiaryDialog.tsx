import { useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { FoodDiaryCopyResponse } from '../../shared/api/types';
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
  const submittingRef = useRef(false);
  const mutation = useMutation({
    mutationFn: ({ key }: { key: string }) => {
      const common = { source_date: subject.sourceDate, target_date: targetDate };
      const body =
        subject.scope === 'day'
          ? common
          : subject.scope === 'meal'
            ? { ...common, source_meal_type: subject.sourceMeal, target_meal_type: targetMeal }
            : {
                ...common,
                source_entry_id: subject.entryId,
                source_meal_type: subject.sourceMeal,
                target_meal_type: targetMeal,
              };
      return api<FoodDiaryCopyResponse>(`/api/v1/nutrition/diary/copy/${subject.scope}`, {
        method: 'POST',
        headers: { 'Idempotency-Key': key },
        body,
      });
    },
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['nutrition', 'foods', 'recent'] }),
        invalidateNutritionSummaries(queryClient),
      ]);
      toast(
        result.replayed
          ? 'Копия уже была добавлена — повторов не создано'
          : `Скопировано записей: ${result.entries.length}`,
      );
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
        ? 'Скопировать приём пищи'
        : 'Скопировать весь день';
  const submit = (key = idempotencyKey()) => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    mutation.mutate({ key });
  };

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
            <span className="eyebrow">Проверьте источник и цель</span>
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
              <dd>{subject.label}</dd>
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
                  mutation.reset();
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
                    mutation.reset();
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
          <p className="nutrition-copy__notice">
            Новые записи добавятся к уже существующим. Ничего в выбранном дне не будет заменено.
          </p>
          {mutation.error && (
            <div className="nutrition-inline-error" role="alert">
              <span>Не удалось скопировать записи. Проверьте дату и попробуйте снова.</span>
              <button
                type="button"
                disabled={mutation.isPending}
                onClick={() => mutation.variables && submit(mutation.variables.key)}
              >
                Повторить
              </button>
            </div>
          )}
          <div className="nutrition-editor__actions">
            <Button type="submit" disabled={mutation.isPending || !targetDate}>
              {mutation.isPending ? 'Копируем…' : scopeLabel}
            </Button>
            <Button type="button" variant="ghost" disabled={mutation.isPending} onClick={onClose}>
              Отмена
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
