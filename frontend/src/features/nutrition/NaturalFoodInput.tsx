import { useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiError, api } from '../../shared/api/client';
import type {
  Food,
  FoodSearch,
  FoodSearchAlias,
  FoodSearchAliasList,
  FoodDiaryBatchResponse,
  FoodDiaryNutrition,
  NaturalInputPreview,
} from '../../shared/api/types';
import { naturalInputDraftStorageKey } from '../../shared/userScopedStorage';
import { usePersistentState } from '../../shared/storage';
import {
  productEventSurface,
  trackProductEvent,
  type NutritionPowerOutcome,
  type OnboardingLatencyBucket,
} from '../../shared/analytics/productEvents';
import { Button, Field, Input, LoadingState, Select } from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { FoodEditor } from './FoodEditor';

type NaturalRow = NaturalInputPreview['rows'][number];
type NaturalUnit = NonNullable<NaturalRow['amount_unit']>;

const emptyDraft = { text: '' };

function newRequestId(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function timingBucket(durationMs: number): OnboardingLatencyBucket {
  if (durationMs < 10_000) return 'under_10s';
  if (durationMs < 30_000) return '10_30s';
  if (durationMs < 60_000) return '30_60s';
  if (durationMs < 5 * 60_000) return '1_5m';
  if (durationMs < 15 * 60_000) return '5_15m';
  return 'over_15m';
}

function trackNaturalResult(
  outcome: NutritionPowerOutcome,
  startedAt: number,
  operationKey: string,
): void {
  const dedupeKey = `nutrition-power:natural_input:${operationKey}:${outcome}`;
  trackProductEvent(
    {
      name: 'nutrition_power_flow_completed',
      surface: productEventSurface(),
      flow: 'natural_input',
      outcome,
    },
    { dedupe: 'session', dedupeKey },
  );
  trackProductEvent(
    {
      name: 'nutrition_power_flow_timing',
      surface: productEventSurface(),
      flow: 'natural_input',
      duration_bucket: timingBucket(Date.now() - startedAt),
    },
    { dedupe: 'session', dedupeKey: `${dedupeKey}:timing` },
  );
}

function foodSourceLabel(source: string): string {
  return (
    {
      alias: 'Ваше название',
      personal: 'Мой продукт',
      favorite: 'Избранное',
      frequent: 'Частый продукт',
      recent: 'Недавний продукт',
      shared: 'Каталог YFC',
      local: 'Локальный каталог',
    }[source] ?? 'Локальный каталог'
  );
}

function foodDescription(food: Food): string {
  const energy = food.energy_kcal_per_100g === null ? '—' : `${food.energy_kcal_per_100g} ккал`;
  return `${food.brand ? `${food.brand} · ` : ''}${energy}`;
}

function scaledNutritionValue(value: string | null, factor: number, digits: number): string | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? (parsed * factor).toFixed(digits) : null;
}

function estimateFoodNutrition(
  food: Food,
  amount: string | null,
  amountUnit: NaturalUnit | null,
): FoodDiaryNutrition | null {
  if (!amount || !amountUnit) return null;
  const parsedAmount = Number(amount.replace(',', '.'));
  if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) return null;
  const weight =
    amountUnit === 'serving'
      ? parsedAmount * Number(food.standard_serving_weight_g ?? 0)
      : parsedAmount;
  if (!Number.isFinite(weight) || weight <= 0) return null;
  const factor = weight / 100;
  const energy = scaledNutritionValue(food.energy_kcal_per_100g, factor, 2);
  if (energy === null) return null;
  return {
    energy_kcal: energy,
    protein_g: scaledNutritionValue(food.protein_g_per_100g, factor, 3),
    fat_g: scaledNutritionValue(food.fat_g_per_100g, factor, 3),
    carbs_g: scaledNutritionValue(food.carbs_g_per_100g, factor, 3),
    fiber_g: scaledNutritionValue(food.fiber_g_per_100g, factor, 3),
  };
}

function sumNutrition(rows: NaturalRow[]): FoodDiaryNutrition | null {
  const matchedRows = rows.filter((row) => row.status === 'matched');
  if (!matchedRows.length || matchedRows.some((row) => !row.nutrition)) return null;
  const values = matchedRows.map((row) => row.nutrition as FoodDiaryNutrition);
  const sum = (key: keyof FoodDiaryNutrition): string | null => {
    const current = values.map((value) => value[key]);
    if (current.some((value) => value === null)) return null;
    const total = current.reduce((result, value) => result + Number(value), 0);
    return total.toFixed(key === 'energy_kcal' ? 2 : 3);
  };
  return {
    energy_kcal: sum('energy_kcal') ?? '0.00',
    protein_g: sum('protein_g'),
    fat_g: sum('fat_g'),
    carbs_g: sum('carbs_g'),
    fiber_g: sum('fiber_g'),
  };
}

function rowStatusLabel(row: NaturalRow): string {
  if (row.status === 'matched') return 'Проверено';
  if (row.status === 'ambiguous') return 'Нужно выбрать';
  if (row.status === 'excluded') return 'Не добавляется';
  return 'Не найдено';
}

function NaturalRowEditor({
  row,
  onChange,
  onSelect,
  onCreate,
  canCreateFood,
  onRemove,
  onRemember,
}: {
  row: NaturalRow;
  onChange: (patch: Partial<NaturalRow>) => void;
  onSelect: (food: Food) => void;
  onCreate: () => void;
  canCreateFood: boolean;
  onRemove: () => void;
  onRemember: () => void;
}) {
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const search = useQuery({
    queryKey: ['nutrition', 'natural-input', 'food-search', row.row_id, searchQuery],
    queryFn: ({ signal }) =>
      api<FoodSearch>(
        `/api/v1/nutrition/foods/search?q=${encodeURIComponent(searchQuery)}&limit=8`,
        { signal },
      ),
    enabled: searchQuery.length >= 2,
  });
  const selected = row.selected_food;
  const candidates = row.candidates ?? [];
  return (
    <li className={`nutrition-natural-row nutrition-natural-row--${row.status}`}>
      <div className="nutrition-natural-row__head">
        <div>
          <strong>{row.name || 'Продукт без названия'}</strong>
          <small>{row.raw_text || 'Строка без текста'}</small>
        </div>
        <span className="nutrition-natural-row__status" role="status">
          {rowStatusLabel(row)}
        </span>
      </div>
      {row.message && <p className="nutrition-natural-row__message">{row.message}</p>}
      {row.status !== 'excluded' && (
        <>
          <div className="nutrition-natural-row__fields">
            <Field label="Количество" labelFor={`natural-amount-${row.row_id}`}>
              <Input
                id={`natural-amount-${row.row_id}`}
                type="number"
                inputMode="decimal"
                min="0.001"
                step="any"
                value={row.amount ?? ''}
                onChange={(event) => onChange({ amount: event.target.value })}
              />
            </Field>
            <Field label="Единица" labelFor={`natural-unit-${row.row_id}`}>
              <Select
                id={`natural-unit-${row.row_id}`}
                value={row.amount_unit ?? ''}
                onChange={(event) =>
                  onChange({
                    amount_unit: event.target.value as NaturalUnit,
                    unit_inferred: false,
                  })
                }
              >
                {!row.amount_unit && (
                  <option value="" disabled>
                    Выберите единицу
                  </option>
                )}
                <option value="g">граммы</option>
                <option value="ml">миллилитры</option>
                <option value="serving">порции</option>
              </Select>
            </Field>
          </div>
          {row.unit_inferred && (
            <p className="nutrition-natural-row__hint">
              Единица не указана — для проверки использованы граммы. При необходимости измените её.
            </p>
          )}
          {selected && (
            <div className="nutrition-natural-row__selected">
              <div>
                <strong>{selected.name}</strong>
                <span>{foodDescription(selected)}</span>
              </div>
              <span>
                {foodSourceLabel(
                  candidates.find((item) => item.food.id === selected.id)?.source ?? 'local',
                )}
              </span>
            </div>
          )}
          {candidates.length > 0 && row.status !== 'matched' && (
            <div className="nutrition-natural-row__candidates" aria-label="Варианты продукта">
              <span>Выберите продукт</span>
              {candidates.map((candidate) => (
                <button
                  key={candidate.food.id}
                  type="button"
                  onClick={() => onSelect(candidate.food)}
                >
                  <strong>{candidate.food.name}</strong>
                  <small>
                    {foodSourceLabel(candidate.source)} · {foodDescription(candidate.food)}
                  </small>
                </button>
              ))}
            </div>
          )}
          {row.status !== 'matched' && (
            <div className="nutrition-natural-row__search">
              <Field
                label="Найти продукт"
                labelFor={`natural-search-${row.row_id}`}
                hint="Ищем только в локальном каталоге"
              >
                <Input
                  id={`natural-search-${row.row_id}`}
                  type="search"
                  value={searchInput}
                  onChange={(event) => {
                    const value = event.target.value;
                    setSearchInput(value);
                    setSearchQuery(value.trim().replace(/\s+/g, ' '));
                  }}
                  placeholder="Например, банан"
                />
              </Field>
              {search.isFetching && <LoadingState label="Ищем продукты…" />}
              {search.data && searchQuery.length >= 2 && (
                <div
                  className="nutrition-natural-row__search-results"
                  aria-label="Результаты поиска"
                >
                  {search.data.items.map((food) => (
                    <button key={food.id} type="button" onClick={() => onSelect(food)}>
                      <strong>{food.name}</strong>
                      <small>{foodDescription(food)}</small>
                    </button>
                  ))}
                  {!search.data.items.length && <span>Совпадений нет. Уточните запрос.</span>}
                </div>
              )}
              {canCreateFood && (
                <Button type="button" variant="secondary" onClick={onCreate}>
                  Создать вручную
                </Button>
              )}
            </div>
          )}
          {selected && (
            <div className="nutrition-natural-row__actions">
              <Button type="button" variant="ghost" onClick={onRemember}>
                Запомнить название
              </Button>
              <button
                type="button"
                onClick={() =>
                  onChange({ selected_food_id: null, selected_food: null, status: 'unresolved' })
                }
              >
                Выбрать другой
              </button>
            </div>
          )}
        </>
      )}
      <button type="button" className="nutrition-natural-row__remove" onClick={onRemove}>
        {row.status === 'excluded' ? 'Вернуть строку' : 'Удалить из списка'}
      </button>
    </li>
  );
}

export function NaturalFoodInput({
  diaryDate,
  mealType,
  userId,
  demoSafeMode = false,
  onCompleted,
  onCancel,
}: {
  diaryDate: string;
  mealType: 'breakfast' | 'lunch' | 'dinner' | 'snacks';
  userId: number | 'anonymous';
  demoSafeMode?: boolean;
  onCompleted: (response: FoodDiaryBatchResponse) => void;
  onCancel: () => void;
}) {
  const { confirm, toast } = useFeedback();
  const [draft, setDraft, clearDraft] = usePersistentState(
    naturalInputDraftStorageKey(userId, diaryDate, mealType),
    emptyDraft,
  );
  const [rows, setRows] = useState<NaturalRow[]>([]);
  const [manualFood, setManualFood] = useState<{ rowId: string; name: string } | null>(null);
  const commitKeyRef = useRef<string | null>(null);
  const commitInFlightRef = useRef(false);
  const commitStartedAtRef = useRef<number | null>(null);
  const aliases = useQuery({
    queryKey: ['nutrition', 'food-aliases'],
    queryFn: () => api<FoodSearchAliasList>('/api/v1/nutrition/food-aliases'),
    enabled: !demoSafeMode,
  });
  const [editingAliasId, setEditingAliasId] = useState<number | null>(null);
  const [editingAliasText, setEditingAliasText] = useState('');
  const updateAlias = useMutation({
    mutationFn: ({ aliasId, alias }: { aliasId: number; alias: string }) =>
      api<FoodSearchAlias>(`/api/v1/nutrition/food-aliases/${aliasId}`, {
        method: 'PATCH',
        body: { alias },
      }),
    onSuccess: async () => {
      await aliases.refetch();
      setEditingAliasId(null);
      toast('Ваше название обновлено');
    },
  });
  const removeAlias = useMutation({
    mutationFn: (aliasId: number) =>
      api<void>(`/api/v1/nutrition/food-aliases/${aliasId}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await aliases.refetch();
      toast('Ваше название удалено');
    },
  });
  const preview = useMutation({
    mutationFn: () =>
      api<NaturalInputPreview>('/api/v1/nutrition/diary/natural-input/preview', {
        method: 'POST',
        body: { text: draft.text },
      }),
    onSuccess: (response) => setRows(response.rows),
  });
  const rememberAlias = useMutation({
    mutationFn: ({ alias, foodId }: { alias: string; foodId: number }) =>
      api<FoodSearchAlias>('/api/v1/nutrition/food-aliases', {
        method: 'POST',
        body: { alias, food_id: foodId },
      }),
    onSuccess: async () => {
      await aliases.refetch();
      toast('Название сохранено только для вашего поиска');
    },
  });
  const commit = useMutation({
    onMutate: () => {
      if (!commitKeyRef.current) commitKeyRef.current = newRequestId('natural');
      commitStartedAtRef.current = Date.now();
    },
    mutationFn: () => {
      const items = rows
        .filter(
          (row) =>
            row.status === 'matched' && row.selected_food_id && row.amount && row.amount_unit,
        )
        .map((row) => ({
          row_id: row.row_id,
          food_id: row.selected_food_id as number,
          amount: row.amount as string,
          amount_unit: row.amount_unit ?? 'g',
        }));
      if (!items.length) throw new Error('Выберите хотя бы один продукт для записи');
      if (rows.some((row) => row.status !== 'matched' && row.status !== 'excluded')) {
        throw new Error('Проверьте все строки или исключите те, которые не нужно добавлять');
      }
      if (
        rows.some(
          (row) =>
            row.status === 'matched' && (!row.selected_food_id || !row.amount || !row.amount_unit),
        )
      ) {
        throw new Error('Укажите количество и единицу для каждой выбранной строки');
      }
      return api<FoodDiaryBatchResponse>('/api/v1/nutrition/diary/natural-input/commit', {
        method: 'POST',
        body: { diary_date: diaryDate, meal_type: mealType, items },
        headers: {
          'Idempotency-Key': commitKeyRef.current as string,
        },
      });
    },
    onSuccess: (response) => {
      commitInFlightRef.current = false;
      trackNaturalResult(
        'success',
        commitStartedAtRef.current ?? Date.now(),
        commitKeyRef.current ?? 'natural',
      );
      clearDraft(emptyDraft);
      commitKeyRef.current = null;
      onCompleted(response);
    },
    onError: (error) => {
      commitInFlightRef.current = false;
      const outcome: NutritionPowerOutcome =
        error instanceof ApiError
          ? error.status >= 400 && error.status < 500
            ? 'validation_error'
            : 'unavailable'
          : 'validation_error';
      trackNaturalResult(
        outcome,
        commitStartedAtRef.current ?? Date.now(),
        commitKeyRef.current ?? 'natural',
      );
    },
  });
  const submitCommit = () => {
    if (commitInFlightRef.current || commit.isPending) return;
    commitInFlightRef.current = true;
    commit.mutate();
  };
  const updateRow = (rowId: string, patch: Partial<NaturalRow>) => {
    commit.reset();
    setRows((current) =>
      current.map((row) => {
        if (row.row_id !== rowId) return row;
        const next = { ...row, ...patch };
        return next.selected_food && ('amount' in patch || 'amount_unit' in patch)
          ? {
              ...next,
              nutrition: estimateFoodNutrition(next.selected_food, next.amount, next.amount_unit),
            }
          : next;
      }),
    );
  };
  const selectFood = (rowId: string, food: Food) => {
    const row = rows.find((item) => item.row_id === rowId);
    if (!row) return;
    updateRow(rowId, {
      status: 'matched',
      selected_food_id: food.id,
      selected_food: food,
      nutrition: estimateFoodNutrition(food, row.amount, row.amount_unit),
      candidates: [{ food, source: 'local' }],
      message: 'Проверьте найденный продукт перед записью.',
    });
  };
  if (manualFood) {
    return (
      <div className="nutrition-natural-input__manual-editor">
        <button
          type="button"
          className="nutrition-picker__back"
          onClick={() => setManualFood(null)}
        >
          К проверке списка
        </button>
        <FoodEditor
          userId={userId}
          initialName={manualFood.name}
          onCancel={() => setManualFood(null)}
          onSaved={(food) => {
            selectFood(manualFood.rowId, food);
            setManualFood(null);
          }}
        />
      </div>
    );
  }
  const actionableRows = rows.filter((row) => row.status !== 'excluded');
  const reviewTotals = sumNutrition(rows);
  const canCommit =
    actionableRows.length > 0 &&
    actionableRows.every(
      (row) => row.status === 'matched' && row.selected_food_id && row.amount && row.amount_unit,
    );
  const requestRemoveAlias = async (alias: FoodSearchAlias) => {
    const approved = await confirm({
      title: 'Удалить ваше название?',
      message: `Название «${alias.alias}» больше не будет подставлять ${alias.food_name ?? 'продукт'}.`,
      confirmText: 'Удалить',
    });
    if (approved) removeAlias.mutate(alias.id);
  };
  return (
    <div className="nutrition-natural-input">
      <div className="nutrition-editor__intro">
        <h3>Вставить список продуктов</h3>
        <p>
          Например: «творог 180 г, банан 120 г». Сначала проверьте каждую строку, затем подтвердите
          запись.
        </p>
      </div>
      <Field
        label="Список продуктов"
        labelFor="nutrition-natural-text"
        hint="Можно разделять строки запятыми, переносами или пробелами; вода не добавляется."
      >
        <textarea
          id="nutrition-natural-text"
          className="ui-textarea nutrition-natural-input__textarea"
          maxLength={2000}
          rows={5}
          value={draft.text}
          disabled={demoSafeMode || preview.isPending || commit.isPending}
          onChange={(event) => {
            preview.reset();
            setRows([]);
            setDraft({ text: event.target.value });
          }}
          placeholder="творог 180 г\nбанан 120 г"
        />
      </Field>
      {demoSafeMode && (
        <p className="muted demo-capability-notice" role="status">
          Проверка и запись списка доступны после входа.
        </p>
      )}
      {preview.error && (
        <p className="nutrition-form-error" role="alert">
          {(preview.error as Error).message}
        </p>
      )}
      <div className="nutrition-editor__actions">
        <Button
          type="button"
          disabled={demoSafeMode || preview.isPending || commit.isPending || !draft.text.trim()}
          onClick={() => preview.mutate()}
        >
          {preview.isPending ? 'Проверяем…' : 'Проверить список'}
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={preview.isPending || commit.isPending}
        >
          Отмена
        </Button>
      </div>
      {rows.length > 0 && (
        <section
          className="nutrition-natural-review"
          aria-labelledby="nutrition-natural-review-title"
        >
          <div className="nutrition-natural-review__heading">
            <div>
              <span className="eyebrow">Шаг проверки</span>
              <h4 id="nutrition-natural-review-title">Проверьте список перед записью</h4>
            </div>
            <span>{rows.filter((row) => row.status === 'matched').length} готово</span>
          </div>
          <ul className="nutrition-natural-review__list">
            {rows.map((row) => (
              <NaturalRowEditor
                key={row.row_id}
                row={row}
                onChange={(patch) => updateRow(row.row_id, patch)}
                onSelect={(food) => selectFood(row.row_id, food)}
                onCreate={() => setManualFood({ rowId: row.row_id, name: row.name })}
                canCreateFood={!demoSafeMode}
                onRemove={() =>
                  updateRow(
                    row.row_id,
                    row.status === 'excluded'
                      ? { status: 'unresolved', message: 'Выберите продукт или исключите строку.' }
                      : { status: 'excluded', selected_food_id: null, selected_food: null },
                  )
                }
                onRemember={() => {
                  if (row.selected_food_id) {
                    rememberAlias.mutate({ alias: row.name, foodId: row.selected_food_id });
                  }
                }}
              />
            ))}
          </ul>
          {reviewTotals && (
            <div
              className="nutrition-natural-review__totals"
              role="region"
              aria-label="Итого по списку"
            >
              <strong>Итого</strong>
              <span>
                {Number(reviewTotals.energy_kcal).toLocaleString('ru-RU', {
                  maximumFractionDigits: 0,
                })}{' '}
                ккал
              </span>
              <small>
                Б{' '}
                {reviewTotals.protein_g === null
                  ? '—'
                  : Number(reviewTotals.protein_g).toLocaleString('ru-RU', {
                      maximumFractionDigits: 1,
                    })}{' '}
                · Ж{' '}
                {reviewTotals.fat_g === null
                  ? '—'
                  : Number(reviewTotals.fat_g).toLocaleString('ru-RU', {
                      maximumFractionDigits: 1,
                    })}{' '}
                · У{' '}
                {reviewTotals.carbs_g === null
                  ? '—'
                  : Number(reviewTotals.carbs_g).toLocaleString('ru-RU', {
                      maximumFractionDigits: 1,
                    })}
              </small>
            </div>
          )}
          {commit.error && (
            <p className="nutrition-form-error" role="alert">
              {(commit.error as Error).message}
            </p>
          )}
          <Button
            fullWidth
            type="button"
            disabled={!canCommit || commit.isPending}
            onClick={submitCommit}
          >
            {commit.isPending ? 'Записываем…' : 'Записать проверенные продукты'}
          </Button>
        </section>
      )}
      {!demoSafeMode && (
        <details className="nutrition-natural-aliases">
          <summary>Мои названия продуктов</summary>
          {aliases.isLoading && <LoadingState label="Загружаем ваши названия…" />}
          {aliases.error && (
            <p className="nutrition-form-error" role="alert">
              Не удалось загрузить ваши названия.
            </p>
          )}
          {aliases.data && !aliases.data.items.length && (
            <p className="muted">Сохранённые названия появятся после проверки списка.</p>
          )}
          {aliases.data && aliases.data.items.length > 0 && (
            <ul className="nutrition-natural-aliases__list">
              {aliases.data.items.map((alias) => (
                <li key={alias.id}>
                  {editingAliasId === alias.id ? (
                    <>
                      <Input
                        aria-label={`Новое название вместо ${alias.alias}`}
                        value={editingAliasText}
                        maxLength={128}
                        onChange={(event) => setEditingAliasText(event.target.value)}
                      />
                      <div className="nutrition-natural-aliases__actions">
                        <Button
                          type="button"
                          disabled={updateAlias.isPending || !editingAliasText.trim()}
                          onClick={() =>
                            updateAlias.mutate({
                              aliasId: alias.id,
                              alias: editingAliasText.trim(),
                            })
                          }
                        >
                          Сохранить
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          disabled={updateAlias.isPending}
                          onClick={() => setEditingAliasId(null)}
                        >
                          Отмена
                        </Button>
                      </div>
                    </>
                  ) : (
                    <>
                      <span>
                        <strong>{alias.alias}</strong>
                        <small>
                          {alias.food_name ?? 'Продукт недоступен'}
                          {alias.food_brand ? ` · ${alias.food_brand}` : ''}
                        </small>
                      </span>
                      <div className="nutrition-natural-aliases__actions">
                        <button
                          type="button"
                          onClick={() => {
                            setEditingAliasId(alias.id);
                            setEditingAliasText(alias.alias);
                          }}
                        >
                          Изменить
                        </button>
                        <button
                          type="button"
                          disabled={removeAlias.isPending}
                          onClick={() => void requestRemoveAlias(alias)}
                        >
                          Удалить
                        </button>
                      </div>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
          {updateAlias.error && (
            <p className="nutrition-form-error" role="alert">
              Не удалось обновить название.
            </p>
          )}
          {removeAlias.error && (
            <p className="nutrition-form-error" role="alert">
              Не удалось удалить название.
            </p>
          )}
        </details>
      )}
    </div>
  );
}
