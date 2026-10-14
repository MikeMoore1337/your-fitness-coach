import { DateInput } from '../../shared/ui/PickerInput';
import { useMemo } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { NutritionTarget } from '../../shared/api/types';
import { dateInputValue, detectedTimeZone } from '../../shared/dateTime';
import { invalidateNutritionSummaries, queryKeys } from '../../shared/queryKeys';
import { usePersistentState } from '../../shared/storage';
import { nutritionDraftStorageKey } from '../../shared/userScopedStorage';
import { useFeedback } from '../../shared/ui/FeedbackProvider';

type ManualTargetDraft = {
  calories: string;
  protein_g: string;
  fat_g: string;
  carbs_g: string;
  effective_from: string;
  note: string;
  confirm_energy_mismatch: boolean;
};

function initialDraft(
  initial: NutritionTarget | null | undefined,
  today: string,
): ManualTargetDraft {
  return {
    calories: String(initial?.calories ?? 2200),
    protein_g: String(initial?.protein_g ?? 150),
    fat_g: String(initial?.fat_g ?? 70),
    carbs_g: String(initial?.carbs_g ?? 240),
    effective_from: today,
    note: '',
    confirm_energy_mismatch: false,
  };
}

export function ManualNutritionTargetForm({
  clientId,
  targetTelegramId,
  initial,
  timeZone,
  onSaved,
}: {
  clientId?: number;
  targetTelegramId?: number | null;
  initial?: NutritionTarget | null;
  timeZone?: string | null;
  onSaved?: () => void | Promise<void>;
}) {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const today = dateInputValue(new Date(), timeZone || detectedTimeZone());
  const [draft, setDraft, clearDraft] = usePersistentState<ManualTargetDraft>(
    nutritionDraftStorageKey(
      `${targetTelegramId ? `client_${targetTelegramId}` : 'me'}_manual_target`,
    ),
    () => initialDraft(initial, today),
  );
  const values = useMemo(
    () => ({
      calories: Number(draft.calories),
      protein_g: Number(draft.protein_g),
      fat_g: Number(draft.fat_g),
      carbs_g: Number(draft.carbs_g),
    }),
    [draft.calories, draft.carbs_g, draft.fat_g, draft.protein_g],
  );
  const impliedEnergy = values.protein_g * 4 + values.fat_g * 9 + values.carbs_g * 4;
  const energyDifference = Math.abs(impliedEnergy - values.calories);
  const allowedDifference = Math.max(100, Math.round(values.calories * 0.1));
  const hasEnergyMismatch =
    Number.isFinite(impliedEnergy) &&
    Number.isFinite(values.calories) &&
    energyDifference > allowedDifference;

  const mutation = useMutation({
    mutationFn: () =>
      api<NutritionTarget>('/api/v1/nutrition/targets/manual', {
        method: 'POST',
        body: {
          ...values,
          effective_from: draft.effective_from,
          note: draft.note.trim() || null,
          confirm_energy_mismatch: draft.confirm_energy_mismatch,
          target_telegram_user_id: targetTelegramId || null,
        },
      }),
    onSuccess: async () => {
      clearDraft();
      await Promise.all([
        invalidateNutritionSummaries(queryClient, clientId),
        queryClient.invalidateQueries({
          queryKey: queryKeys.nutrition.targetHistory(targetTelegramId),
        }),
        queryClient.invalidateQueries({ queryKey: queryKeys.nutrition.currentTarget }),
      ]);
      await onSaved?.();
      toast('Ручные ориентиры КБЖУ сохранены');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  const setValue = (field: keyof ManualTargetDraft, value: string | boolean) =>
    setDraft({
      ...draft,
      [field]: value,
      ...(field !== 'confirm_energy_mismatch' ? { confirm_energy_mismatch: false } : {}),
    });

  return (
    <form
      className="stack nutrition-manual-form"
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
    >
      <p className="muted">
        Значения сохраняются без пересчёта. Это ориентиры для самоконтроля, а не медицинское
        назначение.
      </p>
      <div className="form-grid nutrition-manual-grid">
        <label className="field">
          <span>Калории, ккал</span>
          <input
            type="number"
            inputMode="numeric"
            enterKeyHint="next"
            min="800"
            max="6000"
            step="1"
            required
            value={draft.calories}
            onChange={(event) => setValue('calories', event.target.value)}
          />
        </label>
        <label className="field">
          <span>Белки, г</span>
          <input
            type="number"
            inputMode="numeric"
            enterKeyHint="next"
            min="0"
            max="400"
            step="1"
            required
            value={draft.protein_g}
            onChange={(event) => setValue('protein_g', event.target.value)}
          />
        </label>
        <label className="field">
          <span>Жиры, г</span>
          <input
            type="number"
            inputMode="numeric"
            enterKeyHint="next"
            min="0"
            max="250"
            step="1"
            required
            value={draft.fat_g}
            onChange={(event) => setValue('fat_g', event.target.value)}
          />
        </label>
        <label className="field">
          <span>Углеводы, г</span>
          <input
            type="number"
            inputMode="numeric"
            enterKeyHint="next"
            min="0"
            max="800"
            step="1"
            required
            value={draft.carbs_g}
            onChange={(event) => setValue('carbs_g', event.target.value)}
          />
        </label>
        <label className="field nutrition-manual-grid__wide">
          <span>Действует с</span>
          <DateInput
            min={initial?.effective_from}
            max={today}
            required
            value={draft.effective_from}
            onChange={(event) => setValue('effective_from', event.target.value)}
          />
          <small className="field-hint">Дата учитывается в часовом поясе владельца цели.</small>
        </label>
        <label className="field nutrition-manual-grid__wide">
          <span>Комментарий (необязательно)</span>
          <textarea
            maxLength={500}
            rows={3}
            value={draft.note}
            onChange={(event) => setValue('note', event.target.value)}
            placeholder="Например, ориентир на ближайший этап"
          />
        </label>
      </div>

      <div className="nutrition-energy-check" aria-live="polite">
        <span>Энергия по БЖУ</span>
        <strong>{Number.isFinite(impliedEnergy) ? impliedEnergy : 0} ккал</strong>
        <small>
          Справочная проверка: белки и углеводы × 4, жиры × 9. Маркировка и округление могут давать
          небольшую разницу.
        </small>
      </div>

      {hasEnergyMismatch && (
        <div className="nutrition-warning nutrition-energy-warning" role="alert">
          <strong>Проверьте разницу: {energyDifference} ккал</strong>
          <p>
            Указанная калорийность заметно отличается от энергии по БЖУ. Исправьте значения или
            подтвердите, что хотите сохранить их без изменения.
          </p>
          <label className="nutrition-confirmation">
            <input
              type="checkbox"
              checked={draft.confirm_energy_mismatch}
              onChange={(event) => setValue('confirm_energy_mismatch', event.target.checked)}
            />
            <span>Сохранить значения с этой разницей</span>
          </label>
        </div>
      )}

      <button
        className="nutrition-target-save"
        disabled={mutation.isPending || (hasEnergyMismatch && !draft.confirm_energy_mismatch)}
        aria-busy={mutation.isPending}
      >
        {mutation.isPending ? 'Сохраняем…' : 'Сохранить ручные ориентиры'}
      </button>
    </form>
  );
}
