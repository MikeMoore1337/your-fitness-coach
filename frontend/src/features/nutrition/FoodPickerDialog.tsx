import { TimeInput } from '../../shared/ui/PickerInput';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { ApiError, api } from '../../shared/api/client';
import type {
  ExternalFood,
  Food,
  FoodBarcodeLookup,
  FoodDiaryEntry,
  FoodDiaryBatchResponse,
  FoodDiaryNutrition,
  FoodList,
  FoodSearch,
  NutritionLabelConfirmResponse,
  NaturalInputCommitRequest,
  PhotoMealConfirmResponse,
  Recipe,
  UserFoodCreate,
} from '../../shared/api/types';
import { usePersistentState, writeStorage } from '../../shared/storage';
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
  DisclosureIcon,
  Badge,
  Button,
  CloseIcon,
  ErrorState,
  Field,
  IconButton,
  Input,
  LoadingState,
  Select,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { BarcodeLookup } from './BarcodeLookup';
import { FoodEditor } from './FoodEditor';
import { NutritionLabelScanner } from './NutritionLabelScanner';
import { PhotoMealScanner } from './PhotoMealScanner';
import { MealTemplateBrowser } from './MealTemplateBrowser';
import { NaturalFoodInput } from './NaturalFoodInput';
import { RecipeBrowser } from './RecipeBrowser';

export type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snacks';

const mealLabels: Record<MealType, string> = {
  breakfast: 'завтрак',
  lunch: 'обед',
  dinner: 'ужин',
  snacks: 'перекусы',
};
type PickerSource = 'mine' | 'recent' | 'frequent' | 'favorites';
type PickerView =
  | 'browse'
  | 'quick-add'
  | 'food-editor'
  | 'recipes'
  | 'templates'
  | 'natural'
  | 'barcode'
  | 'label-scan'
  | 'photo-meal';

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
  nutritionSource: 'manual' | 'restaurant';
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

type BatchItem = {
  food: Food;
  amount: string;
  amountUnit: FoodAmountUnit;
  sourceLabel: string;
  externalKey?: string;
};

type BatchDraft = { items: BatchItem[]; requestId: string; pending: boolean };

const emptyQuickAdd: QuickAddDraft = {
  name: '',
  calories: '',
  protein: '',
  fat: '',
  carbs: '',
  loggedAt: '',
  nutritionSource: 'manual',
};

function newEntryRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `entry-${crypto.randomUUID()}`;
  }
  return `entry-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function foodSourceLabel(
  food: Pick<Food, 'food_type' | 'catalog_quality'> &
    Partial<Pick<Food, 'source_name' | 'external_id'>>,
): string {
  if (food.external_id && food.source_name === 'open_food_facts') return 'Open Food Facts';
  if (food.external_id && food.source_name === 'usda_fdc') return 'USDA';
  if (food.external_id && food.source_name) return food.source_name;
  if (food.catalog_quality === 'community_unverified') return 'Добавлено пользователем';
  if (food.catalog_quality === 'verified') return 'Проверено YFC';
  if (food.food_type === 'user') return 'Мой продукт';
  if (food.food_type === 'branded') return 'Брендовый';
  return 'Каталог';
}

function foodIdentityLabel(food: Food, duplicate = false): string {
  return [
    food.name,
    food.brand,
    food.external_id ? `${foodSourceLabel(food)} ${food.external_id}` : null,
    food.barcode ? `штрихкод ${food.barcode}` : null,
    duplicate ? `продукт ${food.id}` : null,
  ]
    .filter(Boolean)
    .join(', ');
}

function isUserFood(food: Pick<Food, 'food_type'>): boolean {
  return food.food_type === 'user';
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

function foodAmountUnits(food: Food): FoodAmountUnit[] {
  const units: FoodAmountUnit[] = [];
  const basis = food.nutrition_basis_kind ?? 'per_100_g';
  const servingSize = food.canonical_facts?.serving_size;
  const servingUnit =
    servingSize && typeof servingSize === 'object' && 'unit' in servingSize
      ? servingSize.unit
      : undefined;
  if (basis === 'per_100_g' || (basis === 'per_serving' && servingUnit === 'g')) units.push('g');
  if (basis === 'per_100_ml' || (basis === 'per_serving' && servingUnit === 'ml')) units.push('ml');
  if (
    basis === 'per_serving' ||
    (basis === 'per_100_g' && (food.standard_serving_weight_g || servingUnit === 'g')) ||
    (basis === 'per_100_ml' && servingUnit === 'ml')
  )
    units.push('serving');
  return units;
}

type FoodFact = { value?: string | number | null; basis_ref?: string; evidence?: string };
type FoodFactName = 'energy_kcal' | 'protein_g' | 'fat_g' | 'carbohydrate_g' | 'fiber_g';

function foodBasisData(
  food: Pick<Food, 'nutrition_basis_kind' | 'energy_kcal_per_100g' | 'canonical_facts'>,
): { basis: string; energy: string | null } {
  const normalized = food.canonical_facts?.normalized_facts as
    Partial<Record<FoodFactName, FoodFact | null>> | undefined;
  const source = food.canonical_facts?.source_facts as
    Partial<Record<FoodFactName, FoodFact[] | null>> | undefined;
  const fact =
    normalized?.energy_kcal ??
    (food.nutrition_basis_kind === 'per_serving'
      ? source?.energy_kcal?.find(
          (value) => value.evidence === 'read' && value.basis_ref === 'per_serving',
        )
      : undefined);
  const basis = fact?.basis_ref ?? food.nutrition_basis_kind ?? 'per_100_g';
  const value =
    fact?.value ??
    (!food.canonical_facts && basis === 'per_100_g' ? food.energy_kcal_per_100g : null);
  return { basis, energy: value === null ? null : String(value) };
}

function foodBasisLabel(
  food: Pick<Food, 'nutrition_basis_kind' | 'energy_kcal_per_100g' | 'canonical_facts'>,
): string {
  const { basis, energy } = foodBasisData(food);
  const label = basis === 'per_100_ml' ? '100 мл' : basis === 'per_serving' ? 'порцию' : '100 г';
  return `${formatNumber(energy)} ккал / ${label}`;
}

function foodMacroLabel(food: Food): string {
  const { basis } = foodBasisData(food);
  const normalized = food.canonical_facts?.normalized_facts as
    Partial<Record<FoodFactName, FoodFact | null>> | undefined;
  const source = food.canonical_facts?.source_facts as
    Partial<Record<FoodFactName, FoodFact[] | null>> | undefined;
  const value = (name: FoodFactName, fallback: string | null) => {
    const normalizedFact = normalized?.[name];
    const fact =
      normalizedFact?.basis_ref === basis
        ? normalizedFact
        : basis === 'per_serving'
          ? source?.[name]?.find(
              (item) => item.evidence === 'read' && item.basis_ref === 'per_serving',
            )
          : undefined;
    const result =
      fact?.value ?? (!food.canonical_facts && basis === 'per_100_g' ? fallback : null);
    return formatNumber(result === null ? null : String(result));
  };
  return `Б ${value('protein_g', food.protein_g_per_100g)} · Ж ${value('fat_g', food.fat_g_per_100g)} · У ${value('carbohydrate_g', food.carbs_g_per_100g)} · клетчатка ${value('fiber_g', food.fiber_g_per_100g)}`;
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
  allowBatch = true,
  selectedIds,
  onToggle,
  selectionLocked,
}: {
  foods: Food[];
  onEdit: (food: Food) => void;
  onFavorite: (food: Food) => void;
  onSelect: (food: Food) => void;
  pendingFavorite: number | null;
  allowManage?: boolean;
  allowBatch?: boolean;
  selectedIds: Set<number>;
  onToggle: (food: Food) => void;
  selectionLocked: boolean;
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
    <>
      <p id="nutrition-food-results-hint" className="nutrition-food-results__hint">
        Нажмите на карточку, чтобы выбрать продукт
      </p>
      <ul className="nutrition-food-results" aria-label="Продукты">
        {foods.map((food) => {
          const duplicate = foods.some(
            (other) =>
              other.id !== food.id && other.name === food.name && other.brand === food.brand,
          );
          const identity = foodIdentityLabel(food, duplicate);
          return (
            <li
              className={`nutrition-food-result nutrition-food-result--picker${selectedIds.has(food.id) ? ' nutrition-food-result--selected' : ''}`}
              key={food.id}
            >
              <button
                className="nutrition-food-result__select"
                type="button"
                onClick={() => onSelect(food)}
                disabled={selectionLocked}
                aria-describedby="nutrition-food-results-hint"
                aria-label={`Выбрать ${identity}`}
              >
                <span className="nutrition-food-result__main">
                  <strong>{food.name}</strong>
                  <span>
                    {food.brand ? `${food.brand} · ` : ''}
                    {foodBasisLabel(food)}
                  </span>
                  {(food.barcode || food.external_id) && (
                    <span>
                      {food.external_id ? `${foodSourceLabel(food)} · ${food.external_id}` : ''}
                      {food.external_id && food.barcode ? ' · ' : ''}
                      {food.barcode ? `штрихкод ${food.barcode}` : ''}
                    </span>
                  )}
                </span>
              </button>
              <div className="nutrition-food-result__meta">
                <Badge>{foodSourceLabel(food)}</Badge>
                {allowManage && (
                  <button
                    type="button"
                    className="nutrition-food-result__favorite"
                    aria-label={
                      food.is_favorite
                        ? `Убрать ${identity} из избранного`
                        : `Добавить ${identity} в избранное`
                    }
                    aria-pressed={food.is_favorite}
                    disabled={pendingFavorite === food.id}
                    onClick={() => onFavorite(food)}
                  >
                    <Icon name={food.is_favorite ? 'star-filled' : 'star'} size={20} />
                  </button>
                )}
                {isUserFood(food) && allowManage && (
                  <button
                    type="button"
                    className="nutrition-food-result__edit"
                    onClick={() => onEdit(food)}
                    aria-label={`Изменить ${identity}`}
                    disabled={selectionLocked}
                  >
                    Изменить
                  </button>
                )}
                {allowBatch && (
                  <button
                    type="button"
                    className="nutrition-food-result__batch"
                    data-yfc-choice="compact"
                    aria-pressed={selectedIds.has(food.id)}
                    aria-label={`${selectedIds.has(food.id) ? 'Убрать' : 'Выбрать'} ${identity} ${selectedIds.has(food.id) ? 'из подборки' : 'в подборку'}`}
                    disabled={selectionLocked}
                    onPointerDown={(event) => event.preventDefault()}
                    onClick={() => onToggle(food)}
                  >
                    {selectedIds.has(food.id) ? 'Выбрано' : 'Выбрать'}
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </>
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

function externalFoodKey(food: ExternalFood): string {
  return JSON.stringify([
    food.source.provider,
    food.external_id,
    food.barcode,
    food.brand,
    food.name,
  ]);
}

function ExternalResults({
  response,
  onSelect,
  pendingExternalKey,
  onToggle,
  selectedExternalKeys,
  selectionLocked,
}: {
  response: FoodSearch;
  onSelect: (food: ExternalFood) => void;
  pendingExternalKey: string | null;
  onToggle: (food: ExternalFood) => void;
  selectedExternalKeys: Set<string>;
  selectionLocked: boolean;
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
        <article className="nutrition-external-result" key={externalFoodKey(food)}>
          <div>
            <strong>{food.name}</strong>
            <span>
              {food.brand || 'Без бренда'} · {formatNumber(food.energy_kcal_per_100g)} ккал / 100 г
            </span>
            <span>
              {food.source.attribution} · {food.external_id}
              {food.barcode ? ` · штрихкод ${food.barcode}` : ''}
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
            aria-label={
              (response.external_items?.length ?? 0) > 1
                ? `Выбрать продукт ${food.name}${food.brand ? `, ${food.brand}` : ''}, ${food.source.attribution} ${food.external_id}`
                : undefined
            }
            disabled={pendingExternalKey !== null || selectionLocked}
            onPointerDown={(event) => event.preventDefault()}
            onClick={() => onSelect(food)}
          >
            {pendingExternalKey === externalFoodKey(food) ? 'Сохраняем…' : 'Выбрать продукт'}
          </Button>
          <Button
            fullWidth
            type="button"
            variant="secondary"
            data-yfc-choice="compact"
            aria-pressed={selectedExternalKeys.has(externalFoodKey(food))}
            aria-label={`${selectedExternalKeys.has(externalFoodKey(food)) ? 'Убрать' : 'Выбрать'} ${food.name}${food.brand ? `, ${food.brand}` : ''}, ${food.source.attribution} ${food.external_id} ${selectedExternalKeys.has(externalFoodKey(food)) ? 'из подборки' : 'в подборку'}`}
            disabled={pendingExternalKey !== null || selectionLocked}
            onPointerDown={(event) => event.preventDefault()}
            onClick={() => onToggle(food)}
          >
            {selectedExternalKeys.has(externalFoodKey(food)) ? 'Выбрано' : 'Выбрать в подборку'}
          </Button>
        </article>
      ))}
    </div>
  );
}

export function FoodPickerDialog({
  diaryDate,
  mealType,
  mealEntries = [],
  initialView = 'browse',
  disabled = false,
  demoSafeMode = false,
  onAdded,
  onClose,
}: {
  diaryDate: string;
  mealType: MealType;
  mealEntries?: FoodDiaryEntry[];
  initialView?: 'browse' | 'quick-add';
  disabled?: boolean;
  demoSafeMode?: boolean;
  onAdded?: (entry: FoodDiaryEntry) => void;
  onClose: () => void;
}) {
  const { user } = useAuth();
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
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
  const batchStorageKey = `${foodDraftStorageKey(user?.id ?? 'anonymous', diaryDate, mealType)}_batch`;
  const [batch, setBatch, clearBatch] = usePersistentState<BatchDraft>(batchStorageKey, {
    items: [],
    requestId: newEntryRequestId(),
    pending: false,
  });
  const batchInFlight = useRef(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [importedExternal, setImportedExternal] = useState<Record<string, Food>>({});
  const handleClose = () => {
    if (batchInFlight.current) return;
    if (!batch.pending) clearBatch();
    onClose();
  };
  const panelRef = useModalA11y<HTMLDivElement>(
    true,
    handleClose,
    initialView === 'quick-add' ? '#nutrition-quick-calories' : '#nutrition-food-search',
  );
  const quick = useMemo(() => ({ ...emptyQuickAdd, ...(draft.quick ?? {}) }), [draft.quick]);

  useEffect(() => {
    if (draft.requestId && draft.quick?.nutritionSource) return;
    setDraft({
      ...draft,
      quick,
      requestId: draft.requestId ?? newEntryRequestId(),
    });
  }, [draft, quick, setDraft]);

  const normalizedSearchInput = searchInput.trim().replace(/\s+/g, ' ');
  const clearSearch = () => {
    setSearchInput('');
    setSearchQuery('');
    document.getElementById('nutrition-food-search')?.focus();
  };
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
          if (
            existing.local_item?.source_name === food.source.provider &&
            existing.local_item.external_id === food.external_id &&
            existing.local_item.barcode === food.barcode &&
            existing.local_item.name === food.name &&
            existing.local_item.brand === food.brand
          )
            return existing.local_item;
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
  const selectedIds = useMemo(
    () => new Set(batch.items.map((item) => item.food.id)),
    [batch.items],
  );
  const selectedExternalKeys = useMemo(
    () => new Set(batch.items.flatMap((item) => (item.externalKey ? [item.externalKey] : []))),
    [batch.items],
  );
  const batchPayload = useMemo<NaturalInputCommitRequest>(
    () => ({
      diary_date: diaryDate,
      meal_type: mealType,
      items: batch.items.map((item) => ({
        row_id: `food-${item.food.id}`,
        food_id: item.food.id,
        amount: item.amount.replace(',', '.'),
        amount_unit: item.amountUnit,
      })),
    }),
    [batch.items, diaryDate, mealType],
  );
  const batchValid =
    batch.items.length > 0 &&
    batch.items.every((item) => {
      const amount = Number(item.amount.replace(',', '.'));
      return item.amount.trim() !== '' && Number.isFinite(amount) && amount > 0;
    });
  const batchPreview = useQuery({
    queryKey: ['nutrition', 'diary', 'batch-preview', batchPayload],
    queryFn: ({ signal }) =>
      api<FoodDiaryNutrition>('/api/v1/nutrition/diary/batch/preview', {
        method: 'POST',
        body: batchPayload,
        signal,
      }),
    enabled: batchValid && view === 'browse' && !quantityMode,
    retry: false,
  });

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
        if (!(active instanceof HTMLElement) || !panel?.contains(active)) return;
        if (
          !(active instanceof HTMLInputElement) &&
          !(active instanceof HTMLSelectElement) &&
          !(active instanceof HTMLTextAreaElement)
        )
          return;
        const visibleTop = viewport?.offsetTop ?? 0;
        const visibleBottom = visibleTop + (viewport?.height ?? window.innerHeight);
        const bounds = active.getBoundingClientRect();
        if (bounds.top < visibleTop || bounds.bottom > visibleBottom) {
          active.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
        }
      });
    };
    viewport?.addEventListener('resize', keepActiveFieldVisible);
    panel?.addEventListener('focusin', keepActiveFieldVisible);
    return () => {
      if (frame !== null) window.cancelAnimationFrame(frame);
      viewport?.removeEventListener('resize', keepActiveFieldVisible);
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
              const parsedMacros = macroValues.map((value) => {
                if (value.trim() === '') return null;
                const parsed = Number(value.replace(',', '.'));
                if (!Number.isFinite(parsed) || parsed < 0) {
                  throw new Error('Макронутриенты должны быть неотрицательными числами');
                }
                return parsed;
              });
              return {
                quick_add: {
                  name: quick.name.trim() || null,
                  nutrition_source: quick.nutritionSource,
                  energy_kcal: energy,
                  protein_g: parsedMacros[0],
                  fat_g: parsedMacros[1],
                  carbs_g: parsedMacros[2],
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
  const handleBatchCompleted = async (response: FoodDiaryBatchResponse) => {
    response.entries.forEach((entry) => onAdded?.(entry));
    await invalidateNutritionSummaries(queryClient);
    toast(
      response.replayed
        ? 'Эта запись уже была добавлена'
        : `Добавлено в ${mealLabels[response.meal_type]}`,
    );
    onClose();
  };
  const commitBatch = useMutation({
    mutationFn: ({
      payload,
      requestId,
    }: {
      payload: NaturalInputCommitRequest;
      requestId: string;
    }) =>
      api<FoodDiaryBatchResponse>('/api/v1/nutrition/diary/natural-input/commit', {
        method: 'POST',
        body: payload,
        headers: { 'Idempotency-Key': requestId },
      }),
    onSuccess: async (response) => {
      batchInFlight.current = false;
      clearBatch({ items: [], requestId: newEntryRequestId(), pending: false });
      await handleBatchCompleted(response);
    },
    onError: (error) => {
      batchInFlight.current = false;
      if (error instanceof ApiError && [400, 401, 403, 404, 422, 429].includes(error.status)) {
        setBatch((current) => ({ ...current, pending: false, requestId: newEntryRequestId() }));
        setBatchError('Не удалось добавить подборку. Проверьте продукты и повторите.');
      } else {
        setBatchError(
          'Не удалось узнать результат. Повторите подтверждение: записи не продублируются.',
        );
      }
    },
  });
  const submitBatch = () => {
    if (batchInFlight.current || importExternal.isPending) return;
    if (
      !batch.pending &&
      (!batchValid || !batchPreview.data || batchPreview.isFetching || batchPreview.error)
    )
      return;
    const pending = { ...batch, pending: true };
    if (!writeStorage(batchStorageKey, pending)) {
      setBatchError('Не удалось подготовить добавление. Проверьте настройки браузера и повторите.');
      return;
    }
    batchInFlight.current = true;
    setBatch(pending);
    setBatchError(null);
    commitBatch.mutate({ payload: batchPayload, requestId: pending.requestId });
  };
  const toggleBatchFood = (
    food: Food,
    sourceLabel = foodSourceLabel(food),
    externalKey?: string,
    onlyAdd = false,
  ) => {
    if (batch.pending || batchInFlight.current) return;
    setBatch((current) => {
      if (current.items.some((item) => item.food.id === food.id)) {
        if (onlyAdd) return current;
        return { ...current, items: current.items.filter((item) => item.food.id !== food.id) };
      }
      if (current.items.length >= 100) return current;
      const amountUnit = foodAmountUnit(food);
      return {
        ...current,
        items: [
          ...current.items,
          {
            food,
            amount: amountUnit === 'serving' ? '1' : '100',
            amountUnit,
            sourceLabel,
            externalKey,
          },
        ],
      };
    });
    setBatchError(null);
  };
  const updateBatchItem = (
    foodId: number,
    changes: Partial<Pick<BatchItem, 'amount' | 'amountUnit'>>,
  ) => {
    if (batch.pending || batchInFlight.current) return;
    setBatch((current) => ({
      ...current,
      items: current.items.map((item) =>
        item.food.id === foodId ? { ...item, ...changes } : item,
      ),
    }));
    setBatchError(null);
  };
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
    if (demoSafeMode || importExternal.isPending) return;
    importExternal.mutate(food, {
      onSuccess: async (savedFood) => {
        await queryClient.invalidateQueries({ queryKey: ['nutrition', 'foods'] });
        selectFood(savedFood, { sourceOverride: 'external' });
      },
    });
  };
  const toggleExternalFood = (food: ExternalFood) => {
    if (demoSafeMode || importExternal.isPending || batch.pending || batchInFlight.current) return;
    const key = externalFoodKey(food);
    const selected = batch.items.find((item) => item.externalKey === key);
    if (selected) {
      toggleBatchFood(selected.food);
      return;
    }
    const cached = importedExternal[key];
    if (cached) {
      if (selectedIds.has(cached.id)) {
        setBatchError('Этот продукт уже выбран. Проверьте источник и штрихкод.');
        return;
      }
      toggleBatchFood(cached, food.source.attribution, key, true);
      return;
    }
    importExternal.mutate(food, {
      onSuccess: (savedFood) => {
        setImportedExternal((current) => ({ ...current, [key]: savedFood }));
        toggleBatchFood(savedFood, food.source.attribution, key, true);
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
        browse: 'Выберите продукты',
        'quick-add': 'Быстрый ввод',
        'food-editor': editingFood ? 'Изменить продукт' : 'Новый продукт',
        recipes: 'Рецепты',
        templates: 'Шаблоны приёмов',
        natural: 'Список продуктов',
        barcode: 'Штрихкод',
        'label-scan': 'Сканирование этикетки',
        'photo-meal': 'Фото блюда',
      } as const
    )[view];
  return (
    <div
      className="modal nutrition-picker"
      role="dialog"
      aria-modal="true"
      aria-labelledby="nutrition-picker-title"
    >
      <div className="modal__backdrop" aria-hidden="true" onClick={handleClose} />
      <div
        className={`modal__panel nutrition-picker__panel${view === 'browse' && !quantityMode && !disabled && !demoSafeMode && batch.items.length ? ' nutrition-picker__panel--batch' : ''}`}
        ref={panelRef}
        tabIndex={-1}
      >
        <header data-glass="" data-glass-variant="regular" className="nutrition-picker__header">
          <div>
            <span className="eyebrow">Добавить в {mealLabels[mealType]}</span>
            <h2 id="nutrition-picker-title">{title}</h2>
          </div>
          <Button
            variant="ghost"
            type="button"
            aria-label="Закрыть добавление"
            onClick={handleClose}
            disabled={commitBatch.isPending}
          >
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
            <div className="nutrition-picker__submit">
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
              {mealLabels[mealType]} · {diaryDate}. Это приблизительная запись: неизвестные БЖУ
              останутся без значения, а не станут нулём.
            </p>
            <Field label="Название или контекст (необязательно)" labelFor="nutrition-quick-name">
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
                <TimeInput
                  className="ui-input"
                  id="nutrition-quick-time"

                  value={quick.loggedAt}
                  onChange={(event) => updateQuick({ loggedAt: event.target.value })}
                />
              </Field>
            </div>
            <Field label="Источник оценки" labelFor="nutrition-quick-source">
              <Select
                id="nutrition-quick-source"
                value={quick.nutritionSource}
                onChange={(event) =>
                  updateQuick({
                    nutritionSource: event.target.value as QuickAddDraft['nutritionSource'],
                  })
                }
              >
                <option value="manual">Своя оценка</option>
                <option value="restaurant">Ресторан или кафе</option>
              </Select>
            </Field>
            <fieldset className="nutrition-quick-add__macros">
              <legend>Макронутриенты (необязательно)</legend>
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
            <div className="nutrition-picker__submit">
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
        ) : view === 'natural' ? (
          <div className="nutrition-picker__browse">
            <button
              className="nutrition-picker__back"
              type="button"
              onClick={() => setView('browse')}
            >
              <Icon name="arrow-left" size={16} /> К продуктам
            </button>
            <NaturalFoodInput
              diaryDate={diaryDate}
              mealType={mealType}
              userId={user?.id ?? 'anonymous'}
              demoSafeMode={demoSafeMode}
              onCompleted={handleBatchCompleted}
              onCancel={() => setView('browse')}
            />
          </div>
        ) : view === 'templates' ? (
          <div className="nutrition-picker__browse">
            <button
              className="nutrition-picker__back"
              type="button"
              onClick={() => setView('browse')}
            >
              <Icon name="arrow-left" size={16} /> К продуктам
            </button>
            <MealTemplateBrowser
              diaryDate={diaryDate}
              mealType={mealType}
              mealEntries={mealEntries}
              demoSafeMode={demoSafeMode}
              onCompleted={handleBatchCompleted}
              onCancel={() => setView('browse')}
            />
          </div>
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
        ) : view === 'photo-meal' ? (
          <div className="nutrition-picker__browse">
            <button
              className="nutrition-picker__back"
              type="button"
              onClick={() => setView('browse')}
            >
              <Icon name="arrow-left" size={16} /> К способам добавления
            </button>
            <PhotoMealScanner
              userId={user?.id ?? 'anonymous'}
              diaryDate={diaryDate}
              mealType={mealType}
              onCancel={() => setView('browse')}
              onManualFallback={() => {
                setEntryMethod('quick_add');
                setView('quick-add');
              }}
              onCompleted={async (response: PhotoMealConfirmResponse) => {
                onAdded?.(response.entry);
                await invalidateNutritionSummaries(queryClient);
                toast('Приблизительная запись добавлена в дневник');
                onClose();
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
          <div
            className="nutrition-picker__browse"
            data-search-active={searchQuery.length >= 2 ? 'true' : undefined}
          >
            <div className="nutrition-picker__search-field">
              <Field
                label="Найти продукт"
                labelFor="nutrition-food-search"
                hint="Локальный поиск начинается после двух символов"
              >
                <div
                  className={`nutrition-picker__search-control${
                    searchInput ? ' nutrition-picker__search-control--has-clear' : ''
                  }`}
                >
                  <Input
                    id="nutrition-food-search"
                    className={searchInput ? 'nutrition-picker__search-input--has-clear' : ''}
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
                    onKeyDown={(event) => {
                      if (event.key === 'Escape' && searchInput) {
                        event.preventDefault();
                        event.stopPropagation();
                        clearSearch();
                      }
                    }}
                    placeholder="Например, овсянка"
                  />
                  {searchInput && (
                    <IconButton
                      className="nutrition-picker__search-clear"
                      type="button"
                      aria-label="Очистить поиск"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={clearSearch}
                    >
                      <Icon name="close" size={16} />
                    </IconButton>
                  )}
                </div>
              </Field>
            </div>
            <div className="nutrition-picker__search-flow">
              <div className="nutrition-picker__result-content">
                {!demoSafeMode && (
                  <details
                    className="nutrition-batch__tray"
                    data-empty={batch.items.length === 0 ? 'true' : undefined}
                  >
                    <summary>
                      <strong>Подборка · {batch.items.length}</strong>
                      <span className="nutrition-batch__open">Изменить</span>
                      <span className="nutrition-batch__close">Свернуть</span>
                    </summary>
                    <div className="nutrition-batch__items">
                      {batch.items.length === 0 && (
                        <p className="muted">Вы пока не выбрали продукты.</p>
                      )}
                      {batch.items.map((item) => {
                        const itemLabel = `${item.food.name}${item.food.brand ? `, ${item.food.brand}` : ''}, ${item.sourceLabel}`;
                        const amount = Number(item.amount.replace(',', '.'));
                        const invalid =
                          item.amount.trim() === '' || !Number.isFinite(amount) || amount <= 0;
                        return (
                          <div className="nutrition-batch__item" key={item.food.id}>
                            <div className="nutrition-batch__item-header">
                              <div>
                                <strong>{item.food.name}</strong>
                                <small>
                                  {item.food.brand ? `${item.food.brand} · ` : ''}
                                  {item.sourceLabel} · {foodBasisLabel(item.food)}
                                </small>
                                <small>{foodMacroLabel(item.food)}</small>
                              </div>
                              <button
                                type="button"
                                className="nutrition-batch__remove"
                                aria-label={`Убрать ${itemLabel} из подборки`}
                                disabled={batch.pending || commitBatch.isPending}
                                onClick={() => toggleBatchFood(item.food)}
                              >
                                Убрать
                              </button>
                            </div>
                            <div className="nutrition-batch__amount">
                              <label htmlFor={`nutrition-batch-${item.food.id}`}>Количество</label>
                              <Input
                                id={`nutrition-batch-${item.food.id}`}
                                aria-label={`Количество: ${itemLabel}`}
                                aria-invalid={invalid}
                                type="number"
                                inputMode="decimal"
                                min="0.001"
                                step="any"
                                value={item.amount}
                                disabled={batch.pending || commitBatch.isPending}
                                onChange={(event) =>
                                  updateBatchItem(item.food.id, { amount: event.target.value })
                                }
                              />
                              <Select
                                aria-label={`Единица: ${itemLabel}`}
                                value={item.amountUnit}
                                disabled={batch.pending || commitBatch.isPending}
                                onChange={(event) =>
                                  updateBatchItem(item.food.id, {
                                    amountUnit: event.target.value as FoodAmountUnit,
                                  })
                                }
                              >
                                {foodAmountUnits(item.food).map((unit) => (
                                  <option key={unit} value={unit}>
                                    {unit === 'g' ? 'г' : unit === 'ml' ? 'мл' : 'порц.'}
                                  </option>
                                ))}
                              </Select>
                            </div>
                            {item.amountUnit === 'serving' &&
                              item.food.standard_serving_weight_g && (
                                <small>
                                  1 порция ≈ {formatNumber(item.food.standard_serving_weight_g)} г
                                </small>
                              )}
                            {invalid && (
                              <p className="nutrition-form-error" role="alert">
                                Введите количество больше нуля.
                              </p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </details>
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
                    selectedIds={selectedIds}
                    onToggle={(food) => toggleBatchFood(food)}
                    selectionLocked={batch.pending || commitBatch.isPending}
                    allowManage={!demoSafeMode}
                    allowBatch={!demoSafeMode}
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
                    onToggle={toggleExternalFood}
                    selectedExternalKeys={selectedExternalKeys}
                    selectionLocked={batch.pending || commitBatch.isPending}
                    pendingExternalKey={
                      importExternal.isPending && importExternal.variables
                        ? externalFoodKey(importExternal.variables)
                        : null
                    }
                  />
                )}
                {importExternal.error && (
                  <p className="nutrition-form-error" role="alert">
                    {importExternal.error instanceof ApiError && importExternal.error.status === 409
                      ? 'Продукт с таким штрихкодом уже есть с другими данными. Проверьте источник.'
                      : 'Не удалось сохранить продукт. Попробуйте снова.'}
                  </p>
                )}
              </div>
              {!demoSafeMode && (
                <div className="nutrition-picker__primary-path-actions">
                  <Button
                    id="nutrition-label-scan-entry"
                    fullWidth
                    type="button"
                    variant="secondary"
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
                  <Button
                    fullWidth
                    type="button"
                    variant="secondary"
                    onClick={() => {
                      trackProductEvent({
                        name: 'nutrition_food_add_path_selected',
                        surface: productEventSurface(),
                        path: 'photo',
                      });
                      setEntryMethod('label_scan');
                      setView('photo-meal');
                    }}
                  >
                    По фото блюда
                  </Button>
                  <Button
                    fullWidth
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
                </div>
              )}
              {demoSafeMode && (
                <p className="muted demo-capability-notice" role="status">
                  В демо доступны поиск, подготовленный каталог и быстрый ввод. Фото этикетки,
                  ручное сохранение и внешние каталоги доступны после входа.
                </p>
              )}
              <details className="nutrition-picker__secondary-tools">
                <summary className="yfc-disclosure-summary">
                  Другие способы добавления
                  <DisclosureIcon />
                </summary>
                <div className="nutrition-picker__tools" aria-label="Другие способы добавления">
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={demoSafeMode}
                    title={demoSafeMode ? 'Доступно после входа' : undefined}
                    onClick={() => setView('natural')}
                  >
                    Вставить список
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={demoSafeMode}
                    title={demoSafeMode ? 'Доступно после входа' : undefined}
                    onClick={() => setView('templates')}
                  >
                    Шаблоны приёмов
                  </Button>
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
                <details className="nutrition-picker__catalog-filters">
                  <summary className="yfc-disclosure-summary">
                    Каталог и фильтры
                    <DisclosureIcon />
                  </summary>
                  <div className="nutrition-picker__tabs" aria-label="Быстрое добавление">
                    <button
                      type="button"
                      className={source === 'mine' ? 'is-active' : ''}
                      aria-pressed={source === 'mine'}
                      data-yfc-choice="compact"
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
                      data-yfc-choice="compact"
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
                      data-yfc-choice="compact"
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
                      data-yfc-choice="compact"
                      onClick={() => {
                        setEntryMethod('favorite');
                        setSource('favorites');
                      }}
                    >
                      Избранное
                    </button>
                  </div>
                </details>
              )}
            </div>
          </div>
        )}
        {view === 'browse' &&
          !quantityMode &&
          !disabled &&
          !demoSafeMode &&
          batch.items.length > 0 && (
            <footer className="nutrition-batch__footer">
              {(batchError || batch.pending || batchPreview.error) && (
                <p className="nutrition-form-error" role="alert">
                  {batchError ||
                    (batch.pending
                      ? 'Результат предыдущего добавления неизвестен. Повторите подтверждение.'
                      : 'Не удалось рассчитать подборку. Проверьте продукты и количество.')}
                </p>
              )}
              {batchPreview.error && !batch.pending && (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void batchPreview.refetch()}
                >
                  Повторить расчёт
                </Button>
              )}
              <div className="nutrition-batch__totals">
                <div>
                  <strong>Итого</strong>
                  <small>Выбрано: {batch.items.length}</small>
                </div>
                <div aria-live="polite">
                  <strong>
                    {batchPreview.isFetching
                      ? 'Рассчитываем…'
                      : `${formatNumber(batchPreview.data?.energy_kcal ?? null)} ккал`}
                  </strong>
                  <small>
                    Б {formatNumber(batchPreview.data?.protein_g ?? null)} · Ж{' '}
                    {formatNumber(batchPreview.data?.fat_g ?? null)} · У{' '}
                    {formatNumber(batchPreview.data?.carbs_g ?? null)} г
                  </small>
                  <small>Клетчатка {formatNumber(batchPreview.data?.fiber_g ?? null)} г</small>
                </div>
              </div>
              <Button
                fullWidth
                type="button"
                disabled={
                  commitBatch.isPending ||
                  importExternal.isPending ||
                  (!batch.pending &&
                    (!batchValid ||
                      !batchPreview.data ||
                      batchPreview.isFetching ||
                      Boolean(batchPreview.error)))
                }
                onClick={submitBatch}
              >
                {commitBatch.isPending
                  ? 'Добавляем…'
                  : batch.pending
                    ? 'Повторить подтверждение'
                    : 'Добавить в дневник'}
              </Button>
            </footer>
          )}
      </div>
    </div>
  );
}
