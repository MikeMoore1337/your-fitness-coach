import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '../../shared/api/client';
import type {
  Food,
  FoodDiaryBatchResponse,
  FoodDiaryEntry,
  FoodDiaryNutrition,
  FoodSearch,
  NutritionMealTemplate,
  NutritionMealTemplateCreate,
  NutritionMealTemplateItem,
  NutritionMealTemplateList,
  NutritionMealTemplateUpdate,
  Recipe,
  RecipeList,
} from '../../shared/api/types';
import { invalidateNutritionSummaries, queryKeys } from '../../shared/queryKeys';
import {
  trackProductEvent,
  productEventSurface,
  type NutritionPowerFlow,
  type NutritionPowerOutcome,
  type OnboardingLatencyBucket,
} from '../../shared/analytics/productEvents';
import {
  Badge,
  Button,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Select,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Icon } from '../../shared/ui/Icon';

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snacks';
type TemplateItemUnit = 'g' | 'ml' | 'serving';
type TemplateDraftItem = {
  itemKind: 'food' | 'recipe';
  id: number;
  name: string;
  brand: string | null;
  amount: string;
  amountUnit: TemplateItemUnit;
  available: boolean;
  message: string | null;
};

function timestamp(): number {
  return Date.now();
}

function numberLabel(value: string | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '—';
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(number);
}

function timingBucket(durationMs: number): OnboardingLatencyBucket {
  if (durationMs < 10_000) return 'under_10s';
  if (durationMs < 30_000) return '10_30s';
  if (durationMs < 60_000) return '30_60s';
  if (durationMs < 5 * 60_000) return '1_5m';
  if (durationMs < 15 * 60_000) return '5_15m';
  return 'over_15m';
}

function trackPowerResult(
  flow: NutritionPowerFlow,
  outcome: NutritionPowerOutcome,
  startedAt: number,
  operationKey: string,
): void {
  const dedupeKey = `nutrition-power:${flow}:${operationKey}:${outcome}`;
  trackProductEvent(
    { name: 'nutrition_power_flow_completed', surface: productEventSurface(), flow, outcome },
    { dedupe: 'session', dedupeKey },
  );
  trackProductEvent(
    {
      name: 'nutrition_power_flow_timing',
      surface: productEventSurface(),
      flow,
      duration_bucket: timingBucket(Date.now() - startedAt),
    },
    { dedupe: 'session', dedupeKey: `${dedupeKey}:timing` },
  );
}

function unitForFood(food: Food): TemplateItemUnit {
  if (food.nutrition_basis_kind === 'per_100_ml') return 'ml';
  if (food.nutrition_basis_kind === 'per_serving' || food.standard_serving_weight_g)
    return 'serving';
  return 'g';
}

function draftFromFood(food: Food): TemplateDraftItem {
  const amountUnit = unitForFood(food);
  return {
    itemKind: 'food',
    id: food.id,
    name: food.name,
    brand: food.brand,
    amount: amountUnit === 'serving' ? '1' : '100',
    amountUnit,
    available: true,
    message: null,
  };
}

function draftFromRecipe(recipe: Recipe): TemplateDraftItem {
  return {
    itemKind: 'recipe',
    id: recipe.id,
    name: recipe.name,
    brand: null,
    amount: '100',
    amountUnit: 'g',
    available: true,
    message: null,
  };
}

function draftFromTemplateItem(item: NutritionMealTemplateItem): TemplateDraftItem {
  return {
    itemKind: item.item_kind,
    id: (item.item_kind === 'food' ? item.food_id : item.recipe_id) ?? item.id,
    name: item.name,
    brand: item.brand,
    amount: item.amount,
    amountUnit: item.amount_unit,
    available: item.available,
    message: item.message ?? null,
  };
}

function draftFromDiaryEntry(entry: FoodDiaryEntry): TemplateDraftItem | null {
  if (entry.entry_kind === 'food' && entry.food_id !== null) {
    return {
      itemKind: 'food',
      id: entry.food_id,
      name: entry.food_name,
      brand: entry.food_brand,
      amount: entry.amount,
      amountUnit: entry.amount_unit,
      available: true,
      message: null,
    };
  }
  if (entry.entry_kind === 'recipe' && entry.recipe_id !== null) {
    return {
      itemKind: 'recipe',
      id: entry.recipe_id,
      name: entry.food_name,
      brand: entry.food_brand,
      amount: entry.amount,
      amountUnit: 'g',
      available: true,
      message: null,
    };
  }
  return null;
}

function newOperationKey(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function templateItemPayload(item: TemplateDraftItem) {
  return item.itemKind === 'food'
    ? {
        food_id: item.id,
        amount: item.amount,
        amount_unit: item.amountUnit as 'g' | 'ml' | 'serving',
      }
    : { recipe_id: item.id, amount: item.amount, amount_unit: 'g' as const };
}

function nutritionLine(nutrition: FoodDiaryNutrition): string {
  return `${numberLabel(nutrition.energy_kcal, 0)} ккал · Б ${numberLabel(nutrition.protein_g)} · Ж ${numberLabel(nutrition.fat_g)} · У ${numberLabel(nutrition.carbs_g)}`;
}

function TemplateEditor({
  templateId,
  initialName,
  initialItems,
  onCancel,
  onSaved,
}: {
  templateId: number | null;
  initialName: string;
  initialItems: TemplateDraftItem[];
  onCancel: () => void;
  onSaved: (template: NutritionMealTemplate) => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(initialName);
  const [items, setItems] = useState(initialItems);
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [formError, setFormError] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingKind, setEditingKind] = useState<'food' | 'recipe' | null>(null);

  const foodSearch = useQuery({
    queryKey: ['nutrition', 'meal-template', 'food-search', searchQuery],
    queryFn: ({ signal }) =>
      api<FoodSearch>(
        `/api/v1/nutrition/foods/search?q=${encodeURIComponent(searchQuery)}&limit=8`,
        { signal },
      ),
    enabled: searchQuery.length >= 2 && editingKind !== 'recipe',
  });
  const recipes = useQuery({
    queryKey: queryKeys.nutrition.recipes,
    queryFn: () => api<RecipeList>('/api/v1/nutrition/recipes?limit=50'),
  });
  const mutation = useMutation({
    mutationFn: (payload: NutritionMealTemplateCreate | NutritionMealTemplateUpdate) =>
      api<NutritionMealTemplate>(
        templateId === null
          ? '/api/v1/nutrition/templates'
          : `/api/v1/nutrition/templates/${templateId}`,
        { method: templateId === null ? 'POST' : 'PATCH', body: payload },
      ),
    onSuccess: async (template) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.nutrition.mealTemplates });
      onSaved(template);
    },
  });

  const addItem = (item: TemplateDraftItem) => {
    if (items.some((existing) => existing.itemKind === item.itemKind && existing.id === item.id)) {
      setFormError('Этот продукт или рецепт уже есть в шаблоне. Измените его количество ниже.');
      return;
    }
    setItems((current) => [...current, item]);
    setSearchInput('');
    setSearchQuery('');
    setEditingKind(null);
    setFormError('');
  };

  const editItem = (item: TemplateDraftItem) => {
    setEditingId(item.id);
    setEditingKind(item.itemKind);
  };

  const updateItem = (
    id: number,
    itemKind: 'food' | 'recipe',
    patch: Partial<TemplateDraftItem>,
  ) => {
    mutation.reset();
    setItems((current) =>
      current.map((item) =>
        item.id === id && item.itemKind === itemKind ? { ...item, ...patch } : item,
      ),
    );
  };

  return (
    <form
      className="nutrition-editor nutrition-template-editor"
      aria-label={templateId === null ? 'Новый шаблон приёма пищи' : 'Изменить шаблон приёма пищи'}
      onSubmit={(event) => {
        event.preventDefault();
        const normalizedName = name.trim().replace(/\s+/g, ' ');
        if (!normalizedName) return setFormError('Введите название шаблона.');
        if (!items.length) return setFormError('Добавьте хотя бы один продукт или рецепт.');
        if (items.some((item) => !item.available))
          return setFormError('Удалите недоступные элементы перед сохранением.');
        if (
          items.some((item) => {
            const amount = Number(item.amount.replace(',', '.'));
            return !Number.isFinite(amount) || amount <= 0;
          })
        )
          return setFormError('Количество каждого элемента должно быть больше нуля.');
        setFormError('');
        mutation.mutate({
          name: normalizedName,
          items: items.map(templateItemPayload),
        });
      }}
    >
      <div className="nutrition-editor__intro">
        <h3>{templateId === null ? 'Новый шаблон' : 'Изменить шаблон'}</h3>
        <p>Сохраните повторяющийся приём пищи и добавляйте его целиком в выбранную дату.</p>
      </div>
      <Field label="Название *" labelFor="nutrition-template-name">
        <Input
          id="nutrition-template-name"
          autoFocus
          maxLength={128}
          value={name}
          onChange={(event) => {
            mutation.reset();
            setName(event.target.value);
          }}
          placeholder="Например, мой обычный завтрак"
        />
      </Field>
      <div className="nutrition-template-editor__add">
        <Field
          label="Добавить продукт"
          labelFor="nutrition-template-food-search"
          hint="Поиск только в локальном каталоге"
        >
          <Input
            id="nutrition-template-food-search"
            type="search"
            value={searchInput}
            onFocus={() => setEditingKind('food')}
            onChange={(event) => {
              setEditingKind('food');
              setSearchInput(event.target.value);
              setSearchQuery(event.target.value.trim().replace(/\s+/g, ' '));
            }}
            placeholder="Например, творог"
          />
        </Field>
        {foodSearch.isFetching && <LoadingState label="Ищем продукты…" />}
        {foodSearch.error && (
          <p className="nutrition-form-error" role="alert">
            Не удалось найти продукты.
          </p>
        )}
        {searchQuery.length >= 2 && editingKind === 'food' && foodSearch.data && (
          <div className="nutrition-template-search-results" aria-label="Продукты для шаблона">
            {foodSearch.data.items.map((food) => (
              <button type="button" key={food.id} onClick={() => addItem(draftFromFood(food))}>
                <span>
                  <strong>{food.name}</strong>
                  <small>
                    {food.brand || 'Каталог'} · {numberLabel(food.energy_kcal_per_100g, 0)} ккал /
                    100 г
                  </small>
                </span>
                <Icon name="plus" size={16} />
              </button>
            ))}
            {!foodSearch.data.items.length && <span>Совпадений нет.</span>}
          </div>
        )}
        <div className="nutrition-template-editor__recipe-picker">
          <span className="ui-field__label">Добавить рецепт</span>
          {recipes.isLoading && <LoadingState label="Загружаем рецепты…" />}
          {recipes.error && (
            <p className="nutrition-form-error" role="alert">
              Не удалось загрузить рецепты.
            </p>
          )}
          {recipes.data && !recipes.data.items.length && (
            <span className="muted">Сначала создайте рецепт.</span>
          )}
          {recipes.data && recipes.data.items.length > 0 && (
            <div className="nutrition-template-search-results" aria-label="Рецепты для шаблона">
              {recipes.data.items.map((recipe) => (
                <button
                  type="button"
                  key={recipe.id}
                  onClick={() => addItem(draftFromRecipe(recipe))}
                >
                  <span>
                    <strong>{recipe.name}</strong>
                    <small>
                      {numberLabel(recipe.nutrients_per_100g.energy_kcal_per_100g, 0)} ккал / 100 г
                      · {numberLabel(recipe.effective_weight_g)} г
                    </small>
                  </span>
                  <Icon name="plus" size={16} />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="nutrition-template-items" aria-label="Состав шаблона">
        {items.map((item, index) => (
          <div
            className={`nutrition-template-item${item.available ? '' : ' nutrition-template-item--unavailable'}`}
            key={`${item.itemKind}-${item.id}-${index}`}
          >
            <div className="nutrition-template-item__copy">
              <strong>{item.name}</strong>
              <span>{item.itemKind === 'recipe' ? 'Рецепт' : item.brand || 'Продукт'}</span>
              {!item.available && <small>{item.message || 'Элемент недоступен'}</small>}
            </div>
            <Input
              aria-label={`Количество: ${item.name}`}
              type="number"
              inputMode="decimal"
              min="0.001"
              step="any"
              value={item.amount}
              disabled={!item.available}
              onChange={(event) =>
                updateItem(item.id, item.itemKind, { amount: event.target.value })
              }
            />
            <Select
              aria-label={`Единица: ${item.name}`}
              value={item.amountUnit}
              disabled={item.itemKind === 'recipe' || !item.available}
              onChange={(event) =>
                updateItem(item.id, item.itemKind, {
                  amountUnit: event.target.value as TemplateItemUnit,
                })
              }
            >
              <option value="g">г</option>
              {item.itemKind === 'food' && <option value="ml">мл</option>}
              {item.itemKind === 'food' && <option value="serving">порция</option>}
            </Select>
            <button
              type="button"
              onClick={() => editItem(item)}
              aria-label={`Изменить ${item.name}`}
            >
              <Icon name="edit" size={16} />
            </button>
            <button
              type="button"
              onClick={() =>
                setItems((current) => current.filter((_, itemIndex) => itemIndex !== index))
              }
              aria-label={`Убрать ${item.name}`}
            >
              <Icon name="close" size={16} />
            </button>
          </div>
        ))}
        {!items.length && <p className="nutrition-picker__empty">В шаблоне пока нет элементов.</p>}
      </div>
      {editingId !== null && editingKind !== null && (
        <p className="nutrition-template-editor__hint" role="status">
          Редактируется количество выбранного элемента. Для замены удалите его и добавьте другой.
        </p>
      )}
      {(formError || mutation.error) && (
        <p className="nutrition-form-error" role="alert">
          {formError || 'Не удалось сохранить шаблон. Проверьте элементы и попробуйте снова.'}
        </p>
      )}
      <div className="nutrition-editor__actions app-action-group">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Сохраняем…' : 'Сохранить шаблон'}
        </Button>
        <Button type="button" variant="ghost" disabled={mutation.isPending} onClick={onCancel}>
          Отмена
        </Button>
      </div>
    </form>
  );
}

export function MealTemplateBrowser({
  diaryDate,
  mealType,
  mealEntries,
  demoSafeMode = false,
  onCompleted,
  onCancel,
}: {
  diaryDate: string;
  mealType: MealType;
  mealEntries: FoodDiaryEntry[];
  demoSafeMode?: boolean;
  onCompleted: (response: FoodDiaryBatchResponse) => void;
  onCancel: () => void;
}) {
  const queryClient = useQueryClient();
  const { confirm, toast } = useFeedback();
  const [editing, setEditing] = useState<{ name: string; items: TemplateDraftItem[] } | null>(null);
  const [editingTemplateId, setEditingTemplateId] = useState<number | null>(null);
  const [targetMeal, setTargetMeal] = useState<MealType>(mealType);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [operationError, setOperationError] = useState('');
  const insertKeyRef = useRef<{ templateId: number; mealType: MealType; key: string } | null>(null);
  const insertInFlightRef = useRef(false);
  const insertStartedAtRef = useRef<number | null>(null);

  const templates = useQuery({
    queryKey: queryKeys.nutrition.mealTemplates,
    queryFn: () => api<NutritionMealTemplateList>('/api/v1/nutrition/templates?limit=50'),
    enabled: !demoSafeMode,
  });
  const remove = useMutation({
    mutationFn: (id: number) =>
      api<void>(`/api/v1/nutrition/templates/${id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.nutrition.mealTemplates });
      toast('Шаблон удалён');
    },
  });
  const insert = useMutation({
    mutationFn: ({
      templateId,
      key,
      mealType,
    }: {
      templateId: number;
      key: string;
      mealType: MealType;
    }) =>
      api<FoodDiaryBatchResponse>(`/api/v1/nutrition/templates/${templateId}/entries`, {
        method: 'POST',
        body: { diary_date: diaryDate, meal_type: mealType },
        headers: { 'Idempotency-Key': key },
      }),
    onSuccess: async (response) => {
      insertInFlightRef.current = false;
      const operationKey = insertKeyRef.current?.key ?? 'template';
      trackPowerResult('meal_template', 'success', insertStartedAtRef.current ?? 0, operationKey);
      await invalidateNutritionSummaries(queryClient);
      onCompleted(response);
      insertKeyRef.current = null;
      setOperationError('');
    },
    onError: (error) => {
      insertInFlightRef.current = false;
      const operationKey = insertKeyRef.current?.key ?? 'template';
      const outcome: NutritionPowerOutcome =
        error instanceof ApiError && error.status >= 400 && error.status < 500
          ? 'validation_error'
          : 'unavailable';
      trackPowerResult('meal_template', outcome, insertStartedAtRef.current ?? 0, operationKey);
      setOperationError(
        'Не удалось добавить шаблон. Проверьте доступность элементов и повторите попытку.',
      );
    },
  });

  const currentItems = useMemo(
    () => mealEntries.flatMap((entry) => draftFromDiaryEntry(entry) ?? []),
    [mealEntries],
  );
  const currentHasQuickAdd = mealEntries.some((entry) => entry.entry_kind === 'quick_add');
  const selectedTemplate =
    templates.data?.items.find((item) => item.id === selectedTemplateId) ?? null;
  const startNew = (items: TemplateDraftItem[] = []) => {
    setEditingTemplateId(null);
    setEditing({ name: '', items });
    setOperationError('');
  };
  const startEdit = (template: NutritionMealTemplate) => {
    setEditingTemplateId(template.id);
    setEditing({ name: template.name, items: template.items.map(draftFromTemplateItem) });
    setOperationError('');
  };
  const requestDelete = async (template: NutritionMealTemplate) => {
    const approved = await confirm({
      title: 'Удалить шаблон?',
      message: `${template.name} исчезнет из списка. Записи дневника, добавленные раньше, останутся без изменений.`,
      confirmText: 'Удалить',
    });
    if (approved) remove.mutate(template.id);
  };
  const requestInsert = (template: NutritionMealTemplate) => {
    if (demoSafeMode || insertInFlightRef.current || insert.isPending) return;
    if (template.items.some((item) => !item.available || item.nutrition === null)) {
      setOperationError(
        'В шаблоне есть недоступный или неполный элемент. Измените шаблон перед добавлением.',
      );
      setSelectedTemplateId(template.id);
      return;
    }
    const existing = insertKeyRef.current;
    const key =
      existing?.templateId === template.id && existing.mealType === targetMeal
        ? existing.key
        : newOperationKey('meal-template');
    insertKeyRef.current = { templateId: template.id, mealType: targetMeal, key };
    insertStartedAtRef.current = timestamp();
    insertInFlightRef.current = true;
    setSelectedTemplateId(template.id);
    setOperationError('');
    insert.mutate({ templateId: template.id, key, mealType: targetMeal });
  };

  if (editing) {
    return (
      <TemplateEditor
        templateId={editingTemplateId}
        initialName={editing.name}
        initialItems={editing.items}
        onCancel={() => setEditing(null)}
        onSaved={(template) => {
          setEditing(null);
          setEditingTemplateId(null);
          setSelectedTemplateId(template.id);
          toast('Шаблон сохранён');
        }}
      />
    );
  }

  return (
    <div className="nutrition-template-browser">
      <div className="nutrition-editor__intro">
        <h3>Шаблоны приёмов пищи</h3>
        <p>Сохраните привычное сочетание продуктов и добавляйте его целиком в другой приём пищи.</p>
      </div>
      {demoSafeMode && (
        <p className="muted demo-capability-notice" role="status">
          В демо шаблоны показываются только как capability-safe заглушка. Сохранение и добавление
          доступны после входа.
        </p>
      )}
      {!demoSafeMode && (
        <div className="nutrition-template-browser__actions app-action-group">
          <Button type="button" variant="secondary" onClick={() => startNew()}>
            <Icon name="plus" size={16} /> Новый шаблон
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={!currentItems.length}
            title={currentItems.length ? undefined : 'В текущем приёме нет продуктов или рецептов'}
            onClick={() => startNew(currentItems)}
          >
            Сохранить этот приём
          </Button>
        </div>
      )}
      {!demoSafeMode && currentHasQuickAdd && currentItems.length > 0 && (
        <p className="nutrition-template-browser__note" role="status">
          Быстрые записи с калориями не войдут в шаблон — сохраняются только продукты и рецепты.
        </p>
      )}
      {!demoSafeMode && templates.isLoading && <LoadingState label="Загружаем шаблоны…" />}
      {!demoSafeMode && templates.error && (
        <ErrorState
          message="Не удалось загрузить шаблоны."
          retry={() => void templates.refetch()}
        />
      )}
      {!demoSafeMode && templates.data && !templates.data.items.length && (
        <p className="nutrition-picker__empty">Шаблонов пока нет. Сохраните текущий приём пищи.</p>
      )}
      {!demoSafeMode && templates.data && templates.data.items.length > 0 && (
        <div className="nutrition-template-list" aria-label="Мои шаблоны приёмов пищи">
          {templates.data.items.map((template) => {
            const unavailable = template.items.some(
              (item) => !item.available || item.nutrition === null,
            );
            const open = selectedTemplateId === template.id;
            return (
              <article className="nutrition-template-card" key={template.id}>
                <button
                  type="button"
                  className="nutrition-template-card__toggle"
                  aria-expanded={open}
                  onClick={() => setSelectedTemplateId(open ? null : template.id)}
                >
                  <span>
                    <strong>{template.name}</strong>
                    <small>
                      {template.items.length} элементов · {nutritionLine(template.totals)}
                    </small>
                  </span>
                  <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} />
                </button>
                {open && (
                  <div className="nutrition-template-card__details">
                    <ul>
                      {template.items.map((item) => (
                        <li key={item.id}>
                          <span>{item.name}</span>
                          <small>
                            {numberLabel(item.amount)}{' '}
                            {item.amount_unit === 'serving' ? 'порц.' : item.amount_unit}
                          </small>
                          {!item.available && <Badge>Недоступно</Badge>}
                        </li>
                      ))}
                    </ul>
                    {unavailable && (
                      <p className="nutrition-form-error" role="alert">
                        Один из элементов недоступен. Измените шаблон, чтобы добавить его.
                      </p>
                    )}
                    <Field label="Добавить в" labelFor={`nutrition-template-target-${template.id}`}>
                      <Select
                        id={`nutrition-template-target-${template.id}`}
                        value={targetMeal}
                        disabled={insert.isPending}
                        onChange={(event) => {
                          setTargetMeal(event.target.value as MealType);
                          setOperationError('');
                        }}
                      >
                        <option value="breakfast">Завтрак</option>
                        <option value="lunch">Обед</option>
                        <option value="dinner">Ужин</option>
                        <option value="snacks">Перекусы</option>
                      </Select>
                    </Field>
                    <div className="nutrition-template-card__actions">
                      <Button
                        type="button"
                        disabled={unavailable || insert.isPending}
                        onClick={() => requestInsert(template)}
                      >
                        {insert.isPending && selectedTemplateId === template.id
                          ? 'Добавляем…'
                          : 'Добавить в дневник'}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={insert.isPending}
                        onClick={() => startEdit(template)}
                      >
                        Изменить
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        disabled={remove.isPending || insert.isPending}
                        onClick={() => void requestDelete(template)}
                      >
                        Удалить
                      </Button>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
      {(operationError || insert.error || remove.error) && (
        <div className="nutrition-inline-error" role="alert">
          <span>{operationError || 'Не удалось выполнить операцию с шаблоном.'}</span>
          {insert.error && selectedTemplate && (
            <button
              type="button"
              disabled={insert.isPending}
              onClick={() => requestInsert(selectedTemplate)}
            >
              Повторить
            </button>
          )}
        </div>
      )}
      <div className="nutrition-editor__actions app-action-group">
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={insert.isPending || remove.isPending}
        >
          Отмена
        </Button>
      </div>
    </div>
  );
}
