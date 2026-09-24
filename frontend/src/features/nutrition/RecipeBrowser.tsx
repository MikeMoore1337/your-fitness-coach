import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { Food, FoodSearch, Recipe, RecipeCreate, RecipeList } from '../../shared/api/types';
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

interface IngredientDraft {
  foodId: number;
  name: string;
  brand: string | null;
  amount: string;
  unit: 'g' | 'serving';
  servingWeight: string | null;
  nutritionPer100: NutritionPer100;
}

interface NutritionPer100 {
  energy: number | null;
  protein: number | null;
  fat: number | null;
  carbs: number | null;
  fiber: number | null;
}

interface RecipePreview {
  ingredientsWeight: number;
  total: NutritionPer100;
  per100: NutritionPer100;
}

function numberLabel(value: string | null, digits = 0): string {
  if (value === null) return '—';
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(Number(value));
}

function ingredientFromFood(food: Food): IngredientDraft {
  return {
    foodId: food.id,
    name: food.name,
    brand: food.brand,
    amount: food.standard_serving_weight_g ? '1' : '100',
    unit: food.standard_serving_weight_g ? 'serving' : 'g',
    servingWeight: food.standard_serving_weight_g,
    nutritionPer100: {
      energy: food.energy_kcal_per_100g === null ? null : Number(food.energy_kcal_per_100g),
      protein: food.protein_g_per_100g === null ? null : Number(food.protein_g_per_100g),
      fat: food.fat_g_per_100g === null ? null : Number(food.fat_g_per_100g),
      carbs: food.carbs_g_per_100g === null ? null : Number(food.carbs_g_per_100g),
      fiber: food.fiber_g_per_100g === null ? null : Number(food.fiber_g_per_100g),
    },
  };
}

function ingredientNutritionPer100(
  nutrition: Recipe['ingredients'][number]['nutrition'],
  weight: string,
): NutritionPer100 {
  const weightNumber = Number(weight);
  if (!Number.isFinite(weightNumber) || weightNumber <= 0) {
    return { energy: null, protein: null, fat: null, carbs: null, fiber: null };
  }
  const per100 = (value: string | null): number | null =>
    value === null ? null : (Number(value) * 100) / weightNumber;
  return {
    energy: per100(nutrition.energy_kcal),
    protein: per100(nutrition.protein_g),
    fat: per100(nutrition.fat_g),
    carbs: per100(nutrition.carbs_g),
    fiber: per100(nutrition.fiber_g),
  };
}

function ingredientsFromRecipe(recipe?: Recipe): IngredientDraft[] {
  if (!recipe) return [];
  return recipe.ingredients.flatMap((ingredient) =>
    ingredient.food_id
      ? [
          {
            foodId: ingredient.food_id,
            name: ingredient.food_name,
            brand: ingredient.food_brand,
            amount: ingredient.amount,
            unit: ingredient.amount_unit,
            servingWeight: ingredient.serving_weight_g,
            nutritionPer100: ingredientNutritionPer100(ingredient.nutrition, ingredient.weight_g),
          },
        ]
      : [],
  );
}

function sumNutritionValue(
  current: number | null,
  value: number | null,
  factor: number,
): number | null {
  if (current === null || value === null) return null;
  return current + value * factor;
}

function buildRecipePreview(ingredients: IngredientDraft[], finalWeight: string): RecipePreview {
  const total: NutritionPer100 = { energy: 0, protein: 0, fat: 0, carbs: 0, fiber: 0 };
  let ingredientsWeight = 0;
  for (const ingredient of ingredients) {
    const amount = Number(ingredient.amount.replace(',', '.'));
    if (!Number.isFinite(amount) || amount <= 0) continue;
    const weight =
      ingredient.unit === 'serving' ? amount * Number(ingredient.servingWeight || 0) : amount;
    if (!Number.isFinite(weight) || weight <= 0) continue;
    ingredientsWeight += weight;
    const factor = weight / 100;
    total.energy = sumNutritionValue(total.energy, ingredient.nutritionPer100.energy, factor);
    total.protein = sumNutritionValue(total.protein, ingredient.nutritionPer100.protein, factor);
    total.fat = sumNutritionValue(total.fat, ingredient.nutritionPer100.fat, factor);
    total.carbs = sumNutritionValue(total.carbs, ingredient.nutritionPer100.carbs, factor);
    total.fiber = sumNutritionValue(total.fiber, ingredient.nutritionPer100.fiber, factor);
  }
  const parsedFinalWeight = finalWeight.trim() ? Number(finalWeight.replace(',', '.')) : null;
  const effectiveWeight =
    parsedFinalWeight !== null && Number.isFinite(parsedFinalWeight) && parsedFinalWeight > 0
      ? parsedFinalWeight
      : ingredientsWeight;
  const toPer100 = (value: number | null): number | null =>
    value === null || effectiveWeight <= 0 ? null : (value * 100) / effectiveWeight;
  return {
    ingredientsWeight,
    total,
    per100: {
      energy: toPer100(total.energy),
      protein: toPer100(total.protein),
      fat: toPer100(total.fat),
      carbs: toPer100(total.carbs),
      fiber: toPer100(total.fiber),
    },
  };
}

function previewNumber(value: number | null): string {
  return value === null || !Number.isFinite(value)
    ? '—'
    : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value);
}

function RecipeEditor({
  recipe,
  onCancel,
  onSaved,
}: {
  recipe?: Recipe;
  onCancel: () => void;
  onSaved: (recipe: Recipe) => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(recipe?.name ?? '');
  const [finalWeight, setFinalWeight] = useState(recipe?.final_weight_g ?? '');
  const [ingredients, setIngredients] = useState<IngredientDraft[]>(() =>
    ingredientsFromRecipe(recipe),
  );
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [formError, setFormError] = useState('');
  useEffect(() => {
    const timer = window.setTimeout(
      () => setSearchQuery(searchInput.trim().replace(/\s+/g, ' ')),
      250,
    );
    return () => window.clearTimeout(timer);
  }, [searchInput]);
  const search = useQuery({
    queryKey: ['nutrition', 'foods', 'recipe-search', searchQuery],
    queryFn: ({ signal }) =>
      api<FoodSearch>(
        `/api/v1/nutrition/foods/search?q=${encodeURIComponent(searchQuery)}&limit=10`,
        { signal },
      ),
    enabled: searchQuery.length >= 2,
  });
  const mutation = useMutation({
    mutationFn: (payload: RecipeCreate) =>
      api<Recipe>(recipe ? `/api/v1/nutrition/recipes/${recipe.id}` : '/api/v1/nutrition/recipes', {
        method: recipe ? 'PATCH' : 'POST',
        body: payload,
      }),
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: ['nutrition', 'recipes'] });
      onSaved(saved);
    },
  });
  const addIngredient = (food: Food) => {
    if (ingredients.some((item) => item.foodId === food.id)) {
      setFormError('Этот продукт уже добавлен в рецепт. Измените его количество ниже.');
      return;
    }
    setIngredients((current) => [...current, ingredientFromFood(food)]);
    setSearchInput('');
    setSearchQuery('');
    setFormError('');
  };
  const updateIngredient = (foodId: number, patch: Partial<IngredientDraft>) => {
    mutation.reset();
    setIngredients((current) =>
      current.map((item) => (item.foodId === foodId ? { ...item, ...patch } : item)),
    );
  };
  const preview = useMemo(
    () => buildRecipePreview(ingredients, finalWeight),
    [finalWeight, ingredients],
  );

  return (
    <form
      className="nutrition-editor nutrition-recipe-editor"
      aria-label={recipe ? 'Изменить рецепт' : 'Новый рецепт'}
      onSubmit={(event) => {
        event.preventDefault();
        const normalizedName = name.trim().replace(/\s+/g, ' ');
        if (!normalizedName) return setFormError('Введите название рецепта.');
        if (!ingredients.length) return setFormError('Добавьте хотя бы один продукт.');
        if (
          ingredients.some(
            (item) =>
              !Number.isFinite(Number(item.amount.replace(',', '.'))) ||
              Number(item.amount.replace(',', '.')) <= 0,
          )
        )
          return setFormError('Количество каждого продукта должно быть больше нуля.');
        const normalizedWeight = finalWeight.trim() ? Number(finalWeight.replace(',', '.')) : null;
        if (
          normalizedWeight !== null &&
          (!Number.isFinite(normalizedWeight) || normalizedWeight <= 0)
        )
          return setFormError('Итоговый вес должен быть больше нуля.');
        setFormError('');
        mutation.mutate({
          name: normalizedName,
          final_weight_g: normalizedWeight,
          ingredients: ingredients.map((item) => ({
            food_id: item.foodId,
            amount: Number(item.amount.replace(',', '.')),
            amount_unit: item.unit,
          })),
        });
      }}
    >
      <div className="nutrition-editor__intro">
        <h3>{recipe ? 'Изменить рецепт' : 'Новый рецепт'}</h3>
        <p>Добавьте продукты и при необходимости укажите вес готового блюда после приготовления.</p>
      </div>
      <div className="nutrition-recipe-editor__heading">
        <Field label="Название *" labelFor="recipe-name">
          <Input
            id="recipe-name"
            autoFocus
            maxLength={256}
            value={name}
            onChange={(event) => {
              mutation.reset();
              setName(event.target.value);
            }}
          />
        </Field>
        <Field label="Итоговый вес" labelFor="recipe-final-weight" hint="необязательно, г">
          <Input
            id="recipe-final-weight"
            type="number"
            inputMode="decimal"
            min="0.001"
            step="any"
            value={finalWeight}
            onChange={(event) => {
              mutation.reset();
              setFinalWeight(event.target.value);
            }}
          />
        </Field>
      </div>
      <Field
        label="Добавить продукт"
        labelFor="recipe-food-search"
        hint="Поиск начинается после двух символов"
      >
        <Input
          id="recipe-food-search"
          type="search"
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          placeholder="Например, яйцо"
        />
      </Field>
      {search.isFetching && <LoadingState label="Ищем продукты…" />}
      {search.error && (
        <p className="nutrition-form-error" role="alert">
          Не удалось найти продукты. Попробуйте снова.
        </p>
      )}
      {searchQuery.length >= 2 && !search.isFetching && search.data && (
        <ul
          className="nutrition-food-results nutrition-food-results--compact"
          aria-label="Результаты для рецепта"
        >
          {search.data.items.map((food) => (
            <li key={food.id}>
              <button
                type="button"
                className="nutrition-food-result"
                onClick={() => addIngredient(food)}
              >
                <span className="nutrition-food-result__main">
                  <strong>{food.name}</strong>
                  <span>
                    {food.brand || `${numberLabel(food.energy_kcal_per_100g)} ккал / 100 г`}
                  </span>
                </span>
                <Icon name="plus" size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="nutrition-ingredients" aria-label="Состав рецепта">
        {ingredients.map((ingredient) => (
          <div className="nutrition-ingredient" key={ingredient.foodId}>
            <div>
              <strong>{ingredient.name}</strong>
              <span>{ingredient.brand || 'Продукт'}</span>
            </div>
            <Input
              aria-label={`Количество: ${ingredient.name}`}
              type="number"
              inputMode="decimal"
              min="0.001"
              step="any"
              value={ingredient.amount}
              onChange={(event) =>
                updateIngredient(ingredient.foodId, { amount: event.target.value })
              }
            />
            <Select
              aria-label={`Единица: ${ingredient.name}`}
              value={ingredient.unit}
              onChange={(event) =>
                updateIngredient(ingredient.foodId, { unit: event.target.value as 'g' | 'serving' })
              }
            >
              <option value="g">г</option>
              {ingredient.servingWeight && <option value="serving">порция</option>}
            </Select>
            <button
              type="button"
              aria-label={`Убрать ${ingredient.name}`}
              onClick={() =>
                setIngredients((current) =>
                  current.filter((item) => item.foodId !== ingredient.foodId),
                )
              }
            >
              <Icon name="close" size={16} />
            </button>
          </div>
        ))}
        {!ingredients.length && (
          <p className="nutrition-picker__empty">В составе пока нет продуктов.</p>
        )}
      </div>
      <div
        className="nutrition-recipe-editor__preview"
        aria-label="Предпросмотр питательности рецепта"
      >
        <div className="nutrition-recipe-editor__preview-heading">
          <strong>Предпросмотр</strong>
          <span>Расчёт обновляется при изменении состава и веса.</span>
        </div>
        <div className="nutrition-recipe-editor__preview-grid">
          <div>
            <span>Итого</span>
            <strong>{previewNumber(preview.total.energy)} ккал</strong>
            <small>
              Б {previewNumber(preview.total.protein)} · Ж {previewNumber(preview.total.fat)} · У{' '}
              {previewNumber(preview.total.carbs)}
            </small>
          </div>
          <div>
            <span>На 100 г готового блюда</span>
            <strong>{previewNumber(preview.per100.energy)} ккал</strong>
            <small>
              Б {previewNumber(preview.per100.protein)} · Ж {previewNumber(preview.per100.fat)} · У{' '}
              {previewNumber(preview.per100.carbs)}
            </small>
          </div>
        </div>
      </div>
      <p className="nutrition-recipe-editor__weight">
        Вес ингредиентов: <strong>{numberLabel(String(preview.ingredientsWeight), 1)} г</strong>
        {finalWeight && Number(finalWeight) > 0
          ? ` · готовое блюдо: ${numberLabel(finalWeight, 1)} г`
          : ''}
      </p>
      {(formError || mutation.error) && (
        <p className="nutrition-form-error" role="alert">
          {formError || 'Не удалось сохранить рецепт. Проверьте продукты и попробуйте снова.'}
        </p>
      )}
      <div className="nutrition-editor__actions app-action-group">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Сохраняем…' : recipe ? 'Сохранить рецепт' : 'Создать рецепт'}
        </Button>
        <Button type="button" variant="ghost" disabled={mutation.isPending} onClick={onCancel}>
          Отмена
        </Button>
      </div>
    </form>
  );
}

export function RecipeBrowser({ onSelect }: { onSelect: (recipe: Recipe) => void }) {
  const queryClient = useQueryClient();
  const { confirm } = useFeedback();
  const [editing, setEditing] = useState<Recipe | 'new' | null>(null);
  const recipes = useQuery({
    queryKey: ['nutrition', 'recipes'],
    queryFn: () => api<RecipeList>('/api/v1/nutrition/recipes?limit=50'),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api<void>(`/api/v1/nutrition/recipes/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['nutrition', 'recipes'] }),
  });
  const requestDelete = async (recipe: Recipe) => {
    const approved = await confirm({
      title: 'Удалить рецепт?',
      message: `${recipe.name} исчезнет из списка, но уже сохранённые записи дневника останутся без изменений.`,
      confirmText: 'Удалить',
    });
    if (approved) remove.mutate(recipe.id);
  };
  if (editing)
    return (
      <RecipeEditor
        recipe={editing === 'new' ? undefined : editing}
        onCancel={() => setEditing(null)}
        onSaved={() => setEditing(null)}
      />
    );
  return (
    <div className="nutrition-recipes">
      <div className="nutrition-tools-heading">
        <div>
          <h3>Мои рецепты</h3>
          <p>Выберите готовое блюдо или соберите новое.</p>
        </div>
        <Button type="button" variant="secondary" onClick={() => setEditing('new')}>
          <Icon name="plus" size={16} /> Новый рецепт
        </Button>
      </div>
      {recipes.isLoading && <LoadingState label="Загружаем рецепты…" />}
      {recipes.error && (
        <ErrorState message="Не удалось загрузить рецепты." retry={() => void recipes.refetch()} />
      )}
      {recipes.data && !recipes.data.items.length && (
        <p className="nutrition-picker__empty">
          Рецептов пока нет. Создайте первый из продуктов каталога.
        </p>
      )}
      {recipes.data && recipes.data.items.length > 0 && (
        <ul className="nutrition-recipe-list">
          {recipes.data.items.map((recipe) => {
            const editable = recipe.ingredients.every((item) => item.food_id !== null);
            return (
              <li className="nutrition-recipe" key={recipe.id}>
                <button
                  className="nutrition-recipe__select"
                  type="button"
                  onClick={() => onSelect(recipe)}
                  aria-label={`Добавить рецепт ${recipe.name}`}
                >
                  <span>
                    <strong>{recipe.name}</strong>
                    <small>
                      {recipe.ingredients.length} продуктов ·{' '}
                      {numberLabel(recipe.effective_weight_g, 1)} г
                    </small>
                  </span>
                  <span>
                    <strong>
                      {numberLabel(recipe.nutrients_per_100g.energy_kcal_per_100g)} ккал
                    </strong>
                    <small>на 100 г</small>
                  </span>
                </button>
                <div className="nutrition-recipe__details">
                  <Badge>{recipe.final_weight_g ? 'Итоговый вес задан' : 'Вес ингредиентов'}</Badge>
                  <span>
                    Б {numberLabel(recipe.nutrients_per_100g.protein_g_per_100g, 1)} · Ж{' '}
                    {numberLabel(recipe.nutrients_per_100g.fat_g_per_100g, 1)} · У{' '}
                    {numberLabel(recipe.nutrients_per_100g.carbs_g_per_100g, 1)}
                  </span>
                </div>
                <div className="nutrition-recipe__actions app-action-group">
                  <button
                    type="button"
                    disabled={!editable || remove.isPending}
                    title={editable ? undefined : 'Один из исходных продуктов удалён'}
                    onClick={() => setEditing(recipe)}
                  >
                    Изменить
                  </button>
                  <button
                    type="button"
                    disabled={remove.isPending}
                    onClick={() => void requestDelete(recipe)}
                  >
                    Удалить
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {remove.error && (
        <p className="nutrition-form-error" role="alert">
          Не удалось удалить рецепт.
        </p>
      )}
    </div>
  );
}
