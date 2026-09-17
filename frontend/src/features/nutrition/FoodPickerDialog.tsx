import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { ApiError, api } from '../../shared/api/client';
import type {
  ExternalFood,
  Food,
  FoodBarcodeLookup,
  FoodDiaryEntry,
  FoodList,
  FoodSearch,
  NutritionLabelConfirmResponse,
  Recipe,
  UserFoodCreate,
} from '../../shared/api/types';
import { usePersistentState } from '../../shared/storage';
import { Icon } from '../../shared/ui/Icon';
import { foodDraftStorageKey } from '../../shared/userScopedStorage';
import { invalidateNutritionSummaries } from '../../shared/queryKeys';
import {
  trackCoreProductEvent,
  trackGrowthEvent,
  trackProductEvent,
  productEventSurface,
  type FoodEntryMethod,
  type NutritionFoodAddPath,
  type NutritionFoodSource,
  type OnboardingLatencyBucket,
} from '../../shared/analytics/productEvents';
import {
  Badge,
  Button,
  CloseIcon,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Select,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { BarcodeLookup } from './BarcodeLookup';
import { FoodEditor } from './FoodEditor';
import { NutritionLabelScanner } from './NutritionLabelScanner';
import { RecipeBrowser } from './RecipeBrowser';

export type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snacks';

const mealLabels: Record<MealType, string> = {
  breakfast: 'завтрак',
  lunch: 'обед',
  dinner: 'ужин',
  snacks: 'перекусы',
};
type PickerSource = 'mine' | 'recent' | 'frequent' | 'favorites';
type PickerView = 'browse' | 'quick-add' | 'food-editor' | 'recipes' | 'barcode' | 'label-scan';

function nutritionFoodPath(entryMethod: FoodEntryMethod): NutritionFoodAddPath {
  if (entryMethod === 'label_scan') return 'photo';
  if (entryMethod === 'custom') return 'manual';
  if (entryMethod === 'quick_add') return 'quick_add';
  return 'search';
}

function nutritionFoodTimingBucket(durationMs: number): OnboardingLatencyBucket {
  if (durationMs < 10_000) return 'under_10s';
  if (durationMs < 30_000) return '10_30s';
  if (durationMs < 60_000) return '30_60s';
  if (durationMs < 5 * 60_000) return '1_5m';
  if (durationMs < 15 * 60_000) return '5_15m';
  return 'over_15m';
}

function pickerSourceAnalytics(source: PickerSource): NutritionFoodSource {
  if (source === 'mine') return 'personal';
  if (source === 'frequent') return 'frequent';
  if (source === 'recent') return 'recent';
  return 'favorite';
}

interface QuickAddDraft {
  name: string;
  calories: string;
  protein: string;
  fat: string;
  carbs: string;
  loggedAt: string;
}

type FoodDraftSelection = Pick<
  Food,
  | 'id'
  | 'name'
  | 'brand'
  | 'food_type'
  | 'energy_kcal_per_100g'
  | 'protein_g_per_100g'
  | 'fat_g_per_100g'
  | 'carbs_g_per_100g'
  | 'nutrition_basis_kind'
  | 'nutrition_basis_unit'
  | 'canonical_facts'
  | 'standard_serving_weight_g'
  | 'catalog_quality'
>;

type FoodAmountUnit = FoodDiaryEntry['amount_unit'];

interface AddDraft {
  food: FoodDraftSelection | null;
  amount: string;
  amountUnit: FoodAmountUnit;
  quick?: QuickAddDraft;
  requestId?: string;
}

const emptyQuickAdd: QuickAddDraft = {
  name: '',
  calories: '',
  protein: '',
  fat: '',
  carbs: '',
  loggedAt: '',
};

function newEntryRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `entry-${crypto.randomUUID()}`;
  }
  return `entry-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function foodSourceLabel(food: Pick<Food, 'food_type' | 'catalog_quality'>): string {
  if (food.catalog_quality === 'community_unverified') return 'Добавлено пользователем';
  if (food.catalog_quality === 'verified') return 'Проверено YFC';
  if (food.food_type === 'user') return 'Мой продукт';
  if (food.food_type === 'branded') return 'Брендовый';
  return 'Каталог';
}

function foodDraftSelection(food: Food): FoodDraftSelection {
  return {
    id: food.id,
    name: food.name,
    brand: food.brand,
    food_type: food.food_type,
    energy_kcal_per_100g: food.energy_kcal_per_100g,
    protein_g_per_100g: food.protein_g_per_100g,
    fat_g_per_100g: food.fat_g_per_100g,
    carbs_g_per_100g: food.carbs_g_per_100g,
    nutrition_basis_kind: food.nutrition_basis_kind,
    nutrition_basis_unit: food.nutrition_basis_unit,
    canonical_facts: food.canonical_facts,
    standard_serving_weight_g: food.standard_serving_weight_g,
    catalog_quality: food.catalog_quality,
  };
}

function formatNumber(value: string | null): string {
  if (value === null) return '—';
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(Number(value));
}

function normalizeFoodSearchValue(value: string): string {
  return value.trim().toLocaleLowerCase('ru-RU').replace(/\s+/g, ' ');
}

function hasExactLocalFoodHit(items: Food[], query: string): boolean {
  const normalizedQuery = normalizeFoodSearchValue(query);
  return items.some((item) => {
    const searchableValues = [item.name, item.brand ?? ''];
    if (item.brand) searchableValues.push(`${item.brand} ${item.name}`);
    return searchableValues.some((value) => normalizeFoodSearchValue(value) === normalizedQuery);
  });
}

function foodAmountUnit(
  food: Pick<Food, 'nutrition_basis_kind' | 'standard_serving_weight_g'>,
): FoodAmountUnit {
  if (food.nutrition_basis_kind === 'per_100_ml') return 'ml';
  if (food.nutrition_basis_kind === 'per_serving') return 'serving';
  return food.standard_serving_weight_g ? 'serving' : 'g';
}

function foodEnergyValue(
  food: Pick<Food, 'energy_kcal_per_100g' | 'canonical_facts'>,
): string | null {
  if (food.energy_kcal_per_100g !== null) return food.energy_kcal_per_100g;
  const normalized = food.canonical_facts?.normalized_facts;
  if (!normalized || typeof normalized !== 'object') return null;
  const value = (normalized as { energy_kcal?: { value?: unknown } }).energy_kcal?.value;
  return value === null || value === undefined ? null : String(value);
}

function foodBasisLabel(
  food: Pick<Food, 'nutrition_basis_kind' | 'energy_kcal_per_100g' | 'canonical_facts'>,
): string {
  const basis =
    food.nutrition_basis_kind === 'per_100_ml'
      ? '100 мл'
      : food.nutrition_basis_kind === 'per_serving'
        ? 'порцию'
        : '100 г';
  return `${formatNumber(foodEnergyValue(food))} ккал / ${basis}`;
}

function providerMessage(status: FoodSearch['provider_status']): string | null {
  if (status === 'not_needed')
    return 'В локальном каталоге появился подходящий продукт. Обновите поиск, чтобы выбрать его.';
  if (status === 'disabled')
    return 'Внешний каталог не подключён. Можно выбрать локальный продукт или добавить свой.';
  if (status === 'rate_limited')
    return 'Внешний каталог временно занят. Локальные продукты продолжают работать.';
  if (status === 'unavailable')
    return 'Внешний каталог временно недоступен. Локальные продукты продолжают работать.';
  return null;
}

function FoodResults({
  foods,
  onEdit,
  onFavorite,
  onSelect,
  pendingFavorite,
  allowManage = true,
}: {
  foods: Food[];
  onEdit: (food: Food) => void;
  onFavorite: (food: Food) => void;
  onSelect: (food: Food) => void;
  pendingFavorite: number | null;
  allowManage?: boolean;
}) {
  if (!foods.length)
    return (
      <p className="nutrition-picker__empty">
        {allowManage
          ? 'Здесь пока пусто. Найдите продукт по названию или создайте свой.'
          : 'Подготовленных продуктов пока нет. Попробуйте поиск по названию.'}
      </p>
    );
  return (
    <ul className="nutrition-food-results" aria-label="Продукты">
      {foods.map((food) => (
        <li className="nutrition-food-result" key={food.id}>
          <button
            className="nutrition-food-result__select"
            type="button"
            onClick={() => onSelect(food)}
            aria-label={`Добавить ${food.name}`}
          >
            <span className="nutrition-food-result__main">
              <strong>{food.name}</strong>
              <span>
                {food.brand ? `${food.brand} · ` : ''}
                {foodBasisLabel(food)}
              </span>
            </span>
            <Badge>{foodSourceLabel(food)}</Badge>
          </button>
          {allowManage && (
            <div className="nutrition-food-result__actions">
              <button
                type="button"
                aria-label={
                  food.is_favorite
                    ? `Убрать ${food.name} из избранного`
                    : `Добавить ${food.name} в избранное`
                }
                aria-pressed={food.is_favorite}
                disabled={pendingFavorite === food.id}
                onClick={() => onFavorite(food)}
              >
                <Icon name={food.is_favorite ? 'star-filled' : 'star'} size={20} />
              </button>
              {food.food_type === 'user' && (
                <button
                  type="button"
                  onClick={() => onEdit(food)}
                  aria-label={`Изменить ${food.name}`}
                >
                  Изменить
                </button>
              )}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function externalFoodPayload(food: ExternalFood): UserFoodCreate {
  return {
    name: food.name,
    brand: food.brand,
    barcode: food.barcode,
    energy_kcal_per_100g: food.energy_kcal_per_100g,
    protein_g_per_100g: food.protein_g_per_100g,
    fat_g_per_100g: food.fat_g_per_100g,
    carbs_g_per_100g: food.carbs_g_per_100g,
    fiber_g_per_100g: food.fiber_g_per_100g,
    standard_serving_amount: food.standard_serving_amount,
    standard_serving_unit: food.standard_serving_unit,
    standard_serving_weight_g: food.standard_serving_weight_g,
    classification: 'personal',
    nutrition_basis_kind: 'per_100_g',
    nutrition_basis_amount: 100,
    nutrition_basis_unit: 'g',
    external_source: {
      external_id: food.external_id,
      ...food.source,
    },
  };
}

function ExternalResults({
  response,
  onSelect,
  pendingExternalKey,
}: {
  response: FoodSearch;
  onSelect: (food: ExternalFood) => void;
  pendingExternalKey: string | null;
}) {
  const fallback = providerMessage(response.provider_status);
  if (fallback)
    return (
      <div className="nutrition-provider-fallback" role="status">
        <strong>Продолжайте с локальным каталогом</strong>
        <span>{fallback}</span>
      </div>
    );
  if (!response.external_items?.length)
    return (
      <div className="nutrition-provider-fallback">
        <strong>Во внешнем каталоге ничего не найдено</strong>
        <span>Попробуйте другое название или создайте свой продукт по данным с упаковки.</span>
      </div>
    );
  return (
    <div className="nutrition-external-results">
      {response.provider_statuses?.some(
        ({ status }) => status === 'unavailable' || status === 'rate_limited',
      ) && (
        <p className="nutrition-provider-fallback" role="status">
          Часть внешних источников временно недоступна; показаны результаты остальных.
        </p>
      )}
      <p>Выберите карточку — продукт сохранится в «Мои продукты», затем укажите порцию.</p>
      {response.external_items.map((food: ExternalFood) => (
        <article
          className="nutrition-external-result"
          key={`${food.source.provider}-${food.external_id}`}
        >
          <div>
            <strong>{food.name}</strong>
            <span>
              {food.brand || 'Без бренда'} · {formatNumber(food.energy_kcal_per_100g)} ккал / 100 г
            </span>
          </div>
          <div className="nutrition-external-result__links">
            <a href={food.source.source_url} target="_blank" rel="noreferrer">
              Источник
            </a>
            <a href={food.source.license_url} target="_blank" rel="noreferrer">
              {food.source.attribution} · {food.source.license}
            </a>
          </div>
          <Button
            fullWidth
            type="button"
            disabled={pendingExternalKey !== null}
            onClick={() => onSelect(food)}
          >
            {pendingExternalKey === `${food.source.provider}-${food.external_id}`
              ? 'Сохраняем…'
              : 'Выбрать продукт'}
          </Button>
        </article>
      ))}
    </div>
  );
}

export function FoodPickerDialog({
  diaryDate,
  mealType,
  initialView = 'browse',
  disabled = false,
  demoSafeMode = false,
  onAdded,
  onClose,
}: {
  diaryDate: string;
  mealType: MealType;
  initialView?: 'browse' | 'quick-add';
  disabled?: boolean;
  demoSafeMode?: boolean;
  onAdded?: (entry: FoodDiaryEntry) => void;
  onClose: () => void;
}) {
  const { user } = useAuth();
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const panelRef = useModalA11y<HTMLDivElement>(
    true,
    onClose,
    initialView === 'quick-add'
      ? '#nutrition-quick-calories'
      : demoSafeMode
        ? '#nutrition-food-search'
        : '#nutrition-food-search',
  );
  const [view, setView] = useState<PickerView>(initialView);
  const [source, setSource] = useState<PickerSource>('recent');
  const [entryMethod, setEntryMethod] = useState<FoodEntryMethod>(
    initialView === 'quick-add' ? 'quick_add' : 'recent',
  );
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [editingFood, setEditingFood] = useState<Food | undefined>();
  const [editorBarcode, setEditorBarcode] = useState('');
  const [scanBarcode, setScanBarcode] = useState('');
  const [flowStartedAt, setFlowStartedAt] = useState(() => Date.now());
  const [selectedRecipe, setSelectedRecipe] = useState<Recipe | null>(null);
  const [recipeAmount, setRecipeAmount] = useState('100');
  const [draft, setDraft, clearDraft] = usePersistentState<AddDraft>(
    foodDraftStorageKey(user?.id ?? 'anonymous', diaryDate, mealType),
    {
      food: null,
      amount: '100',
      amountUnit: 'g',
      quick: emptyQuickAdd,
      requestId: newEntryRequestId(),
    },
  );
  const quick = draft.quick ?? emptyQuickAdd;

  useEffect(() => {
    if (draft.requestId && draft.quick) return;
    setDraft({
      ...draft,
      quick,
      requestId: draft.requestId ?? newEntryRequestId(),
    });
  }, [draft, quick, setDraft]);

  const normalizedSearchInput = searchInput.trim().replace(/\s+/g, ' ');
  useEffect(() => {
    const timer = window.setTimeout(() => setSearchQuery(normalizedSearchInput), 250);
    return () => window.clearTimeout(timer);
  }, [normalizedSearchInput]);
  const recent = useQuery({
    queryKey: ['nutrition', 'foods', 'recent'],
    queryFn: () => api<FoodList>('/api/v1/nutrition/foods/recent?limit=12'),
    enabled: source === 'recent',
  });
  const frequent = useQuery({
    queryKey: ['nutrition', 'foods', 'frequent'],
    queryFn: () => api<FoodList>('/api/v1/nutrition/foods/frequent?limit=12'),
    enabled: source === 'frequent',
  });
  const mine = useQuery({
    queryKey: ['nutrition', 'foods', 'mine'],
    queryFn: () => api<FoodList>('/api/v1/nutrition/foods/mine?limit=12'),
    enabled: source === 'mine',
  });
  const favorites = useQuery({
    queryKey: ['nutrition', 'foods', 'favorites'],
    queryFn: () => api<FoodList>('/api/v1/nutrition/foods/favorites?limit=12'),
    enabled: source === 'favorites',
  });
  const search = useQuery({
    queryKey: ['nutrition', 'foods', 'search', searchQuery],
    queryFn: ({ signal }) =>
      api<FoodSearch>(
        `/api/v1/nutrition/foods/search?q=${encodeURIComponent(searchQuery)}&limit=20`,
        { signal },
      ),
    enabled: searchQuery.length >= 2,
  });
  const externalQuery =
    !demoSafeMode &&
    searchQuery.length >= 2 &&
    searchQuery === normalizedSearchInput &&
    !search.isFetching &&
    !search.error &&
    search.data !== undefined &&
    (search.data.items.length === 0 ||
      !hasExactLocalFoodHit(search.data.items, searchQuery) ||
      search.data.items.some((item) => item.canonical_complete === false))
      ? searchQuery
      : '';
  const external = useQuery({
    queryKey: ['nutrition', 'foods', 'external-search', externalQuery],
    queryFn: ({ signal }) =>
      api<FoodSearch>(
        `/api/v1/nutrition/foods/search?q=${encodeURIComponent(externalQuery)}&limit=20&include_external=true`,
        { signal },
      ),
    enabled: !demoSafeMode && externalQuery.length >= 2 && externalQuery === searchQuery,
  });
  const favorite = useMutation({
    mutationFn: (food: Food) =>
      api<Food | void>(`/api/v1/nutrition/foods/${food.id}/favorite`, {
        method: food.is_favorite ? 'DELETE' : 'PUT',
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['nutrition', 'foods'] }),
  });
  const importExternal = useMutation({
    mutationFn: async (food: ExternalFood) => {
      try {
        return await api<Food>('/api/v1/nutrition/foods', {
          method: 'POST',
          body: externalFoodPayload(food),
        });
      } catch (error) {
        if (error instanceof ApiError && error.status === 409 && food.barcode) {
          const existing = await api<FoodBarcodeLookup>(
            `/api/v1/nutrition/foods/barcode/${encodeURIComponent(food.barcode)}`,
          );
          if (existing.local_item) return existing.local_item;
        }
        throw error;
      }
    },
  });
  const activeCollection =
    source === 'mine'
      ? mine
      : source === 'frequent'
        ? frequent
        : source === 'recent'
          ? recent
          : favorites;
  const shownFoods = useMemo(
    () => (searchQuery.length >= 2 ? search.data?.items : activeCollection.data?.items) ?? [],
    [activeCollection.data?.items, search.data?.items, searchQuery.length],
  );
  const activeError = searchQuery.length >= 2 ? search.error : activeCollection.error;
  const activeLoading = searchQuery.length >= 2 ? search.isFetching : activeCollection.isLoading;
  const quantityMode = Boolean(draft.food || selectedRecipe);

  useEffect(() => {
    if (!searchQuery || !search.data) return;
    trackProductEvent(
      {
        name: 'nutrition_food_search_result',
        surface: productEventSurface(),
        outcome: search.data.total > 0 ? 'success' : 'no_result',
      },
      {
        dedupe: 'session',
        dedupeKey: `food-search-result:${searchQuery}:${search.data.total > 0}`,
      },
    );
    if (search.data.total < 1) return;
    trackProductEvent(
      { name: 'yfc_food_catalog_local_hit', surface: productEventSurface() },
      { dedupe: 'session', dedupeKey: `food-search-local:${searchQuery}` },
    );
  }, [search.data, searchQuery]);

  useEffect(() => {
    if (!externalQuery || !external.data) return;
    trackProductEvent(
      { name: 'yfc_food_catalog_external_fallback', surface: productEventSurface() },
      { dedupe: 'session', dedupeKey: `food-search-external:${externalQuery}` },
    );
  }, [external.data, externalQuery]);

  useEffect(() => {
    const viewport = window.visualViewport;
    const panel = panelRef.current;
    let frame: number | null = null;
    const keepActiveFieldVisible = () => {
      if (frame !== null) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        frame = null;
        const active = document.activeElement;
        if (active instanceof HTMLElement && panel?.contains(active)) {
          active.scrollIntoView?.({ block: 'center', inline: 'nearest' });
        }
      });
    };
    viewport?.addEventListener('resize', keepActiveFieldVisible);
    viewport?.addEventListener('scroll', keepActiveFieldVisible);
    panel?.addEventListener('focusin', keepActiveFieldVisible);
    return () => {
      if (frame !== null) window.cancelAnimationFrame(frame);
      viewport?.removeEventListener('resize', keepActiveFieldVisible);
      viewport?.removeEventListener('scroll', keepActiveFieldVisible);
      panel?.removeEventListener('focusin', keepActiveFieldVisible);
    };
  }, [panelRef]);

  useEffect(() => {
    if (!quantityMode) return;
    const frame = window.requestAnimationFrame(() => {
      const amountField = panelRef.current?.querySelector<HTMLInputElement>(
        draft.food ? '#nutrition-food-amount' : '#nutrition-recipe-amount',
      );
      amountField?.focus({ preventScroll: true });
      amountField?.scrollIntoView?.({ block: 'center', inline: 'nearest' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [draft.food, panelRef, quantityMode, selectedRecipe]);

  const addEntry = useMutation({
    mutationFn: (submission: { closeAfter: boolean }) => {
      void submission.closeAfter;
      if (disabled) throw new Error('Сначала снимите отметку «Без приёмов пищи» для этого дня');
      const selected =
        view === 'quick-add'
          ? (() => {
              const energy = Number(quick.calories.replace(',', '.'));
              if (!Number.isFinite(energy) || energy <= 0)
                throw new Error('Введите калории больше нуля');
              const macroValues = [quick.protein, quick.fat, quick.carbs];
              const filledMacros = macroValues.filter((value) => value.trim() !== '');
              if (filledMacros.length > 0 && filledMacros.length < 3)
                throw new Error('Укажите все три макронутриента или оставьте их пустыми');
              const parsedMacros = macroValues.map((value) => Number(value.replace(',', '.')));
              if (
                filledMacros.length === 3 &&
                parsedMacros.some((value) => !Number.isFinite(value) || value < 0)
              ) {
                throw new Error('Макронутриенты должны быть неотрицательными числами');
              }
              return {
                quick_add: {
                  name: quick.name.trim() || null,
                  energy_kcal: energy,
                  protein_g: filledMacros.length === 3 ? parsedMacros[0] : null,
                  fat_g: filledMacros.length === 3 ? parsedMacros[1] : null,
                  carbs_g: filledMacros.length === 3 ? parsedMacros[2] : null,
                },
                amount: 1,
                amount_unit: 'serving' as const,
                logged_at: quick.loggedAt || null,
              };
            })()
          : draft.food
            ? {
                food_id: draft.food.id,
                amount: Number(draft.amount.replace(',', '.')),
                amount_unit: draft.amountUnit,
                logged_at: null,
              }
            : selectedRecipe
              ? {
                  recipe_id: selectedRecipe.id,
                  amount: Number(recipeAmount.replace(',', '.')),
                  amount_unit: 'g' as const,
                  logged_at: null,
                }
              : null;
      if (!selected) throw new Error('Сначала выберите продукт или рецепт');
      if (!Number.isFinite(selected.amount) || selected.amount <= 0)
        throw new Error('Введите количество больше нуля');
      return api<FoodDiaryEntry>('/api/v1/nutrition/diary/entries', {
        method: 'POST',
        body: { ...selected, diary_date: diaryDate, meal_type: mealType },
        headers: { 'Idempotency-Key': draft.requestId ?? newEntryRequestId() },
      });
    },
    onSuccess: async (entry, variables) => {
      onAdded?.(entry);
      clearDraft({
        food: null,
        amount: '100',
        amountUnit: 'g',
        quick: emptyQuickAdd,
        requestId: newEntryRequestId(),
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['nutrition', 'foods'] }),
        invalidateNutritionSummaries(queryClient),
      ]);
      trackCoreProductEvent(
        { name: 'food_logged', surface: productEventSurface(), entry_method: entryMethod },
        'food_logged',
      );
      trackProductEvent({
        name: 'nutrition_food_flow_timing',
        surface: productEventSurface(),
        path: nutritionFoodPath(entryMethod),
        duration_bucket: nutritionFoodTimingBucket(Date.now() - flowStartedAt),
      });
      if (user?.has_food_history === false) {
        trackGrowthEvent('first_food_entry_added', { dedupe: 'session' });
      }
      toast(`Добавлено в ${mealLabels[mealType]}`);
      if (variables.closeAfter) onClose();
      else {
        setSelectedRecipe(null);
        setEntryMethod(initialView === 'quick-add' ? 'quick_add' : 'recent');
        setFlowStartedAt(Date.now());
        setView(initialView);
      }
    },
  });
  const updateDraft = (changes: Partial<AddDraft>) => {
    addEntry.reset();
    setDraft({ ...draft, ...changes, requestId: newEntryRequestId() });
  };
  const updateQuick = (changes: Partial<QuickAddDraft>) => {
    updateDraft({ quick: { ...quick, ...changes } });
  };
  const selectFood = (
    food: Food,
    {
      trackCommunityReuse = true,
      sourceOverride,
    }: { trackCommunityReuse?: boolean; sourceOverride?: NutritionFoodSource } = {},
  ) => {
    const source =
      sourceOverride ??
      (food.food_type === 'user'
        ? 'personal'
        : food.catalog_quality === 'community_unverified'
          ? 'shared'
          : 'local');
    trackProductEvent({
      name: 'nutrition_food_source_selected',
      surface: productEventSurface(),
      source,
    });
    if (trackCommunityReuse && food.catalog_quality === 'community_unverified') {
      trackProductEvent({
        name: 'nutrition_label_community_product_reused',
        surface: productEventSurface(),
      });
    }
    trackProductEvent({
      name: 'food_log_started',
      surface: productEventSurface(),
      entry_method: entryMethod,
    });
    setSelectedRecipe(null);
    const amountUnit = foodAmountUnit(food);
    updateDraft({
      food: foodDraftSelection(food),
      amount: amountUnit === 'serving' ? '1' : '100',
      amountUnit,
    });
  };
  const selectExternalFood = (food: ExternalFood) => {
    if (demoSafeMode) return;
    importExternal.mutate(food, {
      onSuccess: async (savedFood) => {
        await queryClient.invalidateQueries({ queryKey: ['nutrition', 'foods'] });
        selectFood(savedFood, { sourceOverride: 'external' });
      },
    });
  };
  const selectRecipe = (recipe: Recipe) => {
    trackProductEvent({
      name: 'food_log_started',
      surface: productEventSurface(),
      entry_method: 'recipe',
    });
    updateDraft({ food: null });
    setSelectedRecipe(recipe);
    setRecipeAmount('100');
  };
  const title =
    draft.food?.name ||
    selectedRecipe?.name ||
    (
      {
        browse: 'Выберите продукт',
        'quick-add': 'Быстрый ввод',
        'food-editor': editingFood ? 'Изменить продукт' : 'Новый продукт',
        recipes: 'Рецепты',
        barcode: 'Штрихкод',
        'label-scan': 'Сканирование этикетки',
      } as const
    )[view];
  return (
    <div
      className="modal nutrition-picker"
      role="dialog"
      aria-modal="true"
      aria-labelledby="nutrition-picker-title"
    >
      <div className="modal__backdrop" aria-hidden="true" onClick={onClose} />
      <div className="modal__panel nutrition-picker__panel" ref={panelRef} tabIndex={-1}>
        <header data-glass="" data-glass-variant="regular" className="nutrition-picker__header">
          <div>
            <span className="eyebrow">Добавить в {mealLabels[mealType]}</span>
            <h2 id="nutrition-picker-title">{title}</h2>
          </div>
          <Button variant="ghost" type="button" aria-label="Закрыть добавление" onClick={onClose}>
            <CloseIcon />
          </Button>
        </header>
        {disabled ? (
          <div className="nutrition-picker__browse">
            <div className="nutrition-provider-fallback" role="status">
              <strong>День отмечен без приёмов пищи</strong>
              <span>Снимите отметку «Без приёмов пищи», чтобы добавить запись.</span>
            </div>
          </div>
        ) : quantityMode ? (
          <form
            className="nutrition-picker__quantity"
            onSubmit={(event) => {
              event.preventDefault();
              if (!addEntry.isPending) addEntry.mutate({ closeAfter: true });
            }}
          >
            <button
              className="nutrition-picker__back"
              type="button"
              onClick={() => {
                addEntry.reset();
                setSelectedRecipe(null);
                updateDraft({ food: null });
              }}
            >
              <Icon name="arrow-left" size={16} /> Выбрать другое
            </button>
            {draft.food ? (
              <>
                <div className="nutrition-picker__selected">
                  <span>{draft.food.brand || foodSourceLabel(draft.food)}</span>
                  <strong>{foodBasisLabel(draft.food)}</strong>
                  <small>
                    Б {formatNumber(draft.food.protein_g_per_100g)} · Ж{' '}
                    {formatNumber(draft.food.fat_g_per_100g)} · У{' '}
                    {formatNumber(draft.food.carbs_g_per_100g)}
                  </small>
                </div>
                <div className="nutrition-picker__amount-grid">
                  <Field label="Количество" labelFor="nutrition-food-amount">
                    <Input
                      id="nutrition-food-amount"
                      type="number"
                      inputMode="decimal"
                      min="0.001"
                      step="any"
                      required
                      value={draft.amount}
                      enterKeyHint="next"
                      onChange={(event) => updateDraft({ amount: event.target.value })}
                    />
                  </Field>
                  <Field label="Единица" labelFor="nutrition-food-unit">
                    <Select
                      id="nutrition-food-unit"
                      value={draft.amountUnit}
                      onChange={(event) =>
                        updateDraft({ amountUnit: event.target.value as FoodAmountUnit })
                      }
                    >
                      {draft.food.nutrition_basis_kind === 'per_100_g' && (
                        <option value="g">граммы</option>
                      )}
                      {draft.food.nutrition_basis_kind === 'per_100_ml' && (
                        <option value="ml">миллилитры</option>
                      )}
                      {(draft.food.nutrition_basis_kind === 'per_serving' ||
                        draft.food.standard_serving_weight_g) && (
                        <option value="serving">порции</option>
                      )}
                    </Select>
                  </Field>
                </div>
                {draft.amountUnit === 'serving' && draft.food.standard_serving_weight_g && (
                  <p className="nutrition-picker__serving-hint">
                    1 порция ≈ {formatNumber(draft.food.standard_serving_weight_g)} г
                  </p>
                )}
              </>
            ) : (
              selectedRecipe && (
                <>
                  <div className="nutrition-picker__selected">
                    <span>Рецепт · {selectedRecipe.ingredients.length} продуктов</span>
                    <strong>
                      {formatNumber(selectedRecipe.nutrients_per_100g.energy_kcal_per_100g)} ккал /
                      100 г
                    </strong>
                    <small>Итоговый вес: {formatNumber(selectedRecipe.effective_weight_g)} г</small>
                  </div>
                  <Field
                    label="Порция готового блюда, г"
                    labelFor="nutrition-recipe-amount"
                    hint="Можно указать любую фактическую массу"
                  >
                    <Input
                      id="nutrition-recipe-amount"
                      type="number"
                      inputMode="decimal"
                      min="0.001"
                      step="any"
                      required
                      value={recipeAmount}
                      onChange={(event) => setRecipeAmount(event.target.value)}
                    />
                  </Field>
                </>
              )
            )}
            {addEntry.error && (
              <div className="nutrition-inline-error" role="alert">
                <span>{(addEntry.error as Error).message}</span>
                <button
                  type="button"
                  disabled={addEntry.isPending}
                  onClick={() => addEntry.mutate({ closeAfter: true })}
                >
                  Повторить
                </button>
              </div>
            )}
            <div className="nutrition-picker__submit">
              <Button fullWidth disabled={addEntry.isPending} type="submit">
                {addEntry.isPending ? 'Добавляем…' : 'Добавить в дневник'}
              </Button>
              <Button
                fullWidth
                disabled={addEntry.isPending}
                type="button"
                variant="secondary"
                onClick={() => addEntry.mutate({ closeAfter: false })}
              >
                Добавить и выбрать ещё
              </Button>
            </div>
          </form>
        ) : view === 'quick-add' ? (
          <form
            className="nutrition-picker__quantity nutrition-quick-add"
            onSubmit={(event) => {
              event.preventDefault();
              if (!addEntry.isPending) addEntry.mutate({ closeAfter: true });
            }}
          >
            <button
              className="nutrition-picker__back"
              type="button"
              onClick={() => setView('browse')}
            >
              <Icon name="arrow-left" size={16} /> К продуктам
            </button>
            <p className="nutrition-quick-add__context">
              {mealLabels[mealType]} · {diaryDate}. Название и время можно не указывать.
            </p>
            <Field label="Название (необязательно)" labelFor="nutrition-quick-name">
              <Input
                id="nutrition-quick-name"
                value={quick.name}
                enterKeyHint="next"
                onChange={(event) => updateQuick({ name: event.target.value })}
                placeholder="Например, обед вне дома"
              />
            </Field>
            <div className="nutrition-quick-add__primary-fields">
              <Field label="Калории" labelFor="nutrition-quick-calories">
                <Input
                  id="nutrition-quick-calories"
                  type="number"
                  inputMode="decimal"
                  enterKeyHint="next"
                  min="0.01"
                  max="10000"
                  step="any"
                  required
                  value={quick.calories}
                  onChange={(event) => updateQuick({ calories: event.target.value })}
                />
              </Field>
              <Field label="Время (необязательно)" labelFor="nutrition-quick-time">
                <Input
                  id="nutrition-quick-time"
                  type="time"
                  value={quick.loggedAt}
                  onChange={(event) => updateQuick({ loggedAt: event.target.value })}
                />
              </Field>
            </div>
            <fieldset className="nutrition-quick-add__macros">
              <legend>Макронутриенты (все три или ни одного)</legend>
              {(
                [
                  ['Белки', 'protein'],
                  ['Жиры', 'fat'],
                  ['Углеводы', 'carbs'],
                ] as const
              ).map(([label, field], index) => (
                <Field key={field} label={label} labelFor={`nutrition-quick-${field}`}>
                  <Input
                    id={`nutrition-quick-${field}`}
                    type="number"
                    inputMode="decimal"
                    enterKeyHint={index === 2 ? 'done' : 'next'}
                    min="0"
                    max="1000"
                    step="any"
                    value={quick[field]}
                    onChange={(event) => updateQuick({ [field]: event.target.value })}
                  />
                </Field>
              ))}
            </fieldset>
            {addEntry.error && (
              <div className="nutrition-inline-error" role="alert">
                <span>{(addEntry.error as Error).message}</span>
                <button
                  type="button"
                  disabled={addEntry.isPending}
                  onClick={() => addEntry.mutate({ closeAfter: true })}
                >
                  Повторить
                </button>
              </div>
            )}
            <div className="nutrition-picker__submit">
              <Button fullWidth disabled={addEntry.isPending} type="submit">
                {addEntry.isPending ? 'Сохраняем…' : 'Сохранить Quick Add'}
              </Button>
              <Button
                fullWidth
                disabled={addEntry.isPending}
                type="button"
                variant="secondary"
                onClick={() => addEntry.mutate({ closeAfter: false })}
              >
                Сохранить и добавить ещё
              </Button>
            </div>
          </form>
        ) : view === 'food-editor' ? (
          <div className="nutrition-picker__browse">
            <FoodEditor
              userId={user?.id ?? 'anonymous'}
              barcode={editorBarcode}
              food={editingFood}
              onCancel={() => setView('browse')}
              onSaved={(food) => {
                toast(editingFood ? 'Продукт обновлён' : 'Продукт создан');
                setEditingFood(undefined);
                setEditorBarcode('');
                selectFood(food);
              }}
            />
          </div>
        ) : view === 'label-scan' ? (
          <div className="nutrition-picker__browse">
            <button
              className="nutrition-picker__back"
              type="button"
              onClick={() => setView('browse')}
            >
              <Icon name="arrow-left" size={16} /> К способам добавления
            </button>
            <NutritionLabelScanner
              userId={user?.id ?? 'anonymous'}
              initialBarcode={scanBarcode}
              onCancel={() => {
                setScanBarcode('');
                setView('browse');
              }}
              onManualFallback={() => {
                setEditorBarcode(scanBarcode);
                setEditingFood(undefined);
                setScanBarcode('');
                setEntryMethod('custom');
                setView('food-editor');
              }}
              onSaved={async (food, response: NutritionLabelConfirmResponse) => {
                await queryClient.invalidateQueries({ queryKey: ['nutrition', 'foods'] });
                if (response.contribution_outcome) {
                  trackProductEvent({
                    name: 'nutrition_food_catalog_contribution_outcome',
                    surface: productEventSurface(),
                    outcome: response.contribution_outcome,
                  });
                }
                toast(
                  response.visibility === 'share_to_yfc_catalog'
                    ? 'Продукт добавлен в каталог YFC'
                    : 'Продукт сохранён только для вас',
                );
                setEntryMethod('label_scan');
                setScanBarcode('');
                selectFood(food, { trackCommunityReuse: false });
              }}
            />
          </div>
        ) : view === 'recipes' ? (
          <div className="nutrition-picker__browse">
            <button
              className="nutrition-picker__back"
              type="button"
              onClick={() => setView('browse')}
            >
              <Icon name="arrow-left" size={16} /> К продуктам
            </button>
            <RecipeBrowser onSelect={selectRecipe} />
          </div>
        ) : view === 'barcode' ? (
          <div className="nutrition-picker__browse">
            <button
              className="nutrition-picker__back"
              type="button"
              onClick={() => setView('browse')}
            >
              <Icon name="arrow-left" size={16} /> К продуктам
            </button>
            <BarcodeLookup
              onSelect={selectFood}
              onCreate={(barcode) => {
                setEditorBarcode(barcode);
                setEditingFood(undefined);
                setView('food-editor');
              }}
              onScanLabel={(barcode) => {
                setEntryMethod('label_scan');
                setScanBarcode(barcode);
                setView('label-scan');
              }}
            />
          </div>
        ) : (
          <div className="nutrition-picker__browse">
            {!demoSafeMode && (
              <>
                <Button
                  id="nutrition-label-scan-entry"
                  fullWidth
                  type="button"
                  onClick={() => {
                    trackProductEvent({
                      name: 'nutrition_food_add_path_selected',
                      surface: productEventSurface(),
                      path: 'photo',
                    });
                    setEntryMethod('label_scan');
                    setScanBarcode('');
                    setView('label-scan');
                  }}
                >
                  По фото этикетки
                </Button>
              </>
            )}
            {demoSafeMode && (
              <p className="muted demo-capability-notice" role="status">
                В демо доступны поиск, подготовленный каталог и быстрый ввод. Фото этикетки, ручное
                сохранение и внешние каталоги доступны после входа.
              </p>
            )}
            <Field
              label="Найти продукт"
              labelFor="nutrition-food-search"
              hint="Локальный поиск начинается после двух символов"
            >
              <Input
                id="nutrition-food-search"
                type="search"
                value={searchInput}
                onFocus={() =>
                  trackProductEvent(
                    {
                      name: 'nutrition_food_add_path_selected',
                      surface: productEventSurface(),
                      path: 'search',
                    },
                    { dedupe: 'session', dedupeKey: 'nutrition-food-add-path-search' },
                  )
                }
                onChange={(event) => {
                  if (event.target.value.trim()) setEntryMethod('search');
                  setSearchInput(event.target.value);
                }}
                placeholder="Например, овсянка"
              />
            </Field>
            {!demoSafeMode && (
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  trackProductEvent({
                    name: 'nutrition_food_add_path_selected',
                    surface: productEventSurface(),
                    path: 'manual',
                  });
                  setEntryMethod('custom');
                  setEditingFood(undefined);
                  setEditorBarcode('');
                  setView('food-editor');
                }}
              >
                <Icon name="plus" size={16} /> Ввести вручную
              </Button>
            )}
            <details className="nutrition-picker__secondary-tools">
              <summary>Другие способы добавления</summary>
              <div className="nutrition-picker__tools" aria-label="Другие способы добавления">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    trackProductEvent({
                      name: 'nutrition_food_add_path_selected',
                      surface: productEventSurface(),
                      path: 'quick_add',
                    });
                    setEntryMethod('quick_add');
                    trackProductEvent({
                      name: 'food_log_started',
                      surface: productEventSurface(),
                      entry_method: 'quick_add',
                    });
                    setView('quick-add');
                  }}
                >
                  <Icon name="plus" size={16} /> Быстрый ввод
                </Button>
                {!demoSafeMode && (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => {
                      setEntryMethod('recipe');
                      setView('recipes');
                    }}
                  >
                    Рецепты
                  </Button>
                )}
              </div>
            </details>
            {searchQuery.length < 2 && (
              <div className="nutrition-picker__tabs" aria-label="Быстрое добавление">
                <button
                  type="button"
                  className={source === 'mine' ? 'is-active' : ''}
                  aria-pressed={source === 'mine'}
                  onClick={() => {
                    setEntryMethod('personal');
                    setSource('mine');
                  }}
                >
                  Мои продукты
                </button>
                <button
                  type="button"
                  className={source === 'frequent' ? 'is-active' : ''}
                  aria-pressed={source === 'frequent'}
                  onClick={() => {
                    setEntryMethod('frequent');
                    setSource('frequent');
                  }}
                >
                  Частые
                </button>
                <button
                  type="button"
                  className={source === 'recent' ? 'is-active' : ''}
                  aria-pressed={source === 'recent'}
                  onClick={() => {
                    setEntryMethod('recent');
                    setSource('recent');
                  }}
                >
                  Недавние
                </button>
                <button
                  type="button"
                  className={source === 'favorites' ? 'is-active' : ''}
                  aria-pressed={source === 'favorites'}
                  onClick={() => {
                    setEntryMethod('favorite');
                    setSource('favorites');
                  }}
                >
                  Избранное
                </button>
              </div>
            )}
            {activeLoading && <LoadingState label="Ищем продукты…" />}
            {activeError && (
              <ErrorState
                message="Локальный каталог сейчас не ответил. Попробуйте снова."
                retry={() =>
                  void (searchQuery.length >= 2 ? search.refetch() : activeCollection.refetch())
                }
              />
            )}
            {!activeLoading && !activeError && (
              <FoodResults
                foods={shownFoods}
                onSelect={(food) =>
                  selectFood(food, {
                    sourceOverride:
                      searchQuery.length >= 2 ? undefined : pickerSourceAnalytics(source),
                  })
                }
                onFavorite={(food) => favorite.mutate(food)}
                pendingFavorite={favorite.isPending ? (favorite.variables?.id ?? null) : null}
                allowManage={!demoSafeMode}
                onEdit={(food) => {
                  setEditingFood(food);
                  setEditorBarcode('');
                  setView('food-editor');
                }}
              />
            )}
            {favorite.error && (
              <p className="nutrition-form-error" role="alert">
                Не удалось обновить избранное.
              </p>
            )}
            {external.isFetching && <LoadingState label="Проверяем внешний каталог…" />}
            {external.error && (
              <div className="nutrition-provider-fallback" role="status">
                <strong>Внешний каталог временно недоступен</strong>
                <span>Можно использовать локальный поиск или создать свой продукт.</span>
              </div>
            )}
            {!demoSafeMode && external.data && externalQuery === searchQuery && (
              <ExternalResults
                response={external.data}
                onSelect={selectExternalFood}
                pendingExternalKey={
                  importExternal.isPending && importExternal.variables
                    ? `${importExternal.variables.source.provider}-${importExternal.variables.external_id}`
                    : null
                }
              />
            )}
            {importExternal.error && (
              <p className="nutrition-form-error" role="alert">
                Не удалось сохранить продукт. Попробуйте снова.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
