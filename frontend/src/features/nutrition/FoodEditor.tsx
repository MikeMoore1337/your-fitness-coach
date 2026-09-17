import { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '../../shared/api/client';
import type { Food, UserFoodCreate } from '../../shared/api/types';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { Button, Field, Input } from '../../shared/ui/common';
import { NutritionLabelScanner } from './NutritionLabelScanner';
import type { NutritionLabelPrefill } from './NutritionLabelReview';
import { isValidGtin as isValidGtinValue } from './nutritionFoodUtils';

export { isValidGtin } from './nutritionFoodUtils';

interface FoodEditorProps {
  userId?: number | 'anonymous';
  barcode?: string;
  initialName?: string;
  food?: Food;
  onCancel: () => void;
  onSaved: (food: Food) => void;
}

interface FoodDraft {
  name: string;
  brand: string;
  barcode: string;
  classification: 'personal' | 'commercial';
  basis: 'per_100_g' | 'per_100_ml' | 'per_serving';
  energy: string;
  protein: string;
  fat: string;
  carbs: string;
  fiber: string;
  servingWeight: string;
}

type FoodErrors = Partial<Record<keyof FoodDraft, string>>;

type PhotoConflict = {
  label: string;
  current: string;
  recognized: string;
};

function initialDraft(food?: Food, barcode = '', initialName = ''): FoodDraft {
  return {
    name: food?.name ?? initialName,
    brand: food?.brand ?? '',
    barcode: food?.barcode ?? barcode,
    classification: 'personal',
    basis: (food?.nutrition_basis_kind as FoodDraft['basis'] | undefined) ?? 'per_100_g',
    energy: food?.energy_kcal_per_100g ?? '',
    protein: food?.protein_g_per_100g ?? '',
    fat: food?.fat_g_per_100g ?? '',
    carbs: food?.carbs_g_per_100g ?? '',
    fiber: food?.fiber_g_per_100g ?? '',
    servingWeight: food?.standard_serving_weight_g ?? '',
  };
}

function parseRequiredNumber(
  value: string,
  label: string,
  maximum: number,
): { value?: number; error?: string } {
  const parsed = Number(value.replace(',', '.'));
  if (!value.trim() || !Number.isFinite(parsed)) return { error: `Укажите ${label.toLowerCase()}` };
  if (parsed < 0 || parsed > maximum) return { error: `Допустимо от 0 до ${maximum}` };
  return { value: parsed };
}

function validateFood(draft: FoodDraft): { errors: FoodErrors; payload?: UserFoodCreate } {
  const errors: FoodErrors = {};
  const name = draft.name.trim().replace(/\s+/g, ' ');
  if (!name) errors.name = 'Введите название продукта';
  else if (name.length > 256) errors.name = 'Не больше 256 символов';
  if (draft.brand.trim().length > 128) errors.brand = 'Не больше 128 символов';
  const barcode = draft.barcode.replace(/\s+/g, '');
  if (barcode && !isValidGtinValue(barcode))
    errors.barcode = 'Проверьте цифры штрихкода GTIN-8, UPC-A, EAN-13 или GTIN-14';

  const energy = parseRequiredNumber(draft.energy, 'калорийность', 1000);
  const protein = parseRequiredNumber(draft.protein, 'белки', 100);
  const fat = parseRequiredNumber(draft.fat, 'жиры', 100);
  const carbs = parseRequiredNumber(draft.carbs, 'углеводы', 100);
  if (energy.error) errors.energy = energy.error;
  if (protein.error) errors.protein = protein.error;
  if (fat.error) errors.fat = fat.error;
  if (carbs.error) errors.carbs = carbs.error;

  let fiber: number | null = null;
  if (draft.fiber.trim()) {
    const parsedFiber = parseRequiredNumber(draft.fiber, 'клетчатку', 100);
    if (parsedFiber.error) errors.fiber = parsedFiber.error;
    else fiber = parsedFiber.value ?? null;
  }
  let servingWeight: number | null = null;
  if (draft.servingWeight.trim()) {
    servingWeight = Number(draft.servingWeight.replace(',', '.'));
    if (!Number.isFinite(servingWeight) || servingWeight <= 0)
      errors.servingWeight = 'Вес порции должен быть больше нуля';
  }
  if (Object.keys(errors).length) return { errors };
  return {
    errors,
    payload: {
      name,
      brand: draft.brand.trim().replace(/\s+/g, ' ') || null,
      barcode: barcode || null,
      classification: draft.classification,
      nutrition_basis_kind: draft.basis,
      nutrition_basis_amount: draft.basis === 'per_serving' ? 1 : 100,
      nutrition_basis_unit:
        draft.basis === 'per_100_ml' ? 'ml' : draft.basis === 'per_serving' ? 'serving' : 'g',
      energy_kcal_per_100g: energy.value!,
      protein_g_per_100g: protein.value!,
      fat_g_per_100g: fat.value!,
      carbs_g_per_100g: carbs.value!,
      fiber_g_per_100g: fiber,
      standard_serving_amount: servingWeight ? 1 : null,
      standard_serving_unit: servingWeight ? 'serving' : null,
      standard_serving_weight_g: servingWeight,
    },
  };
}

function saveError(error: unknown): string {
  if (error instanceof ApiError && error.status === 409)
    return 'Продукт с такими данными уже существует. Проверьте название, бренд и значения.';
  return 'Не удалось сохранить продукт. Проверьте данные и попробуйте снова.';
}

export function FoodEditor({
  userId = 'anonymous',
  barcode = '',
  initialName = '',
  food,
  onCancel,
  onSaved,
}: FoodEditorProps) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(() => initialDraft(food, barcode, initialName));
  const [errors, setErrors] = useState<FoodErrors>({});
  const [photoScanOpen, setPhotoScanOpen] = useState(false);
  const [photoConflicts, setPhotoConflicts] = useState<PhotoConflict[]>([]);
  const [pendingPhotoPrefill, setPendingPhotoPrefill] = useState<NutritionLabelPrefill | null>(
    null,
  );
  const [photoPrefillNotice, setPhotoPrefillNotice] = useState('');
  const title = food ? 'Изменить свой продукт' : 'Новый продукт';
  const mutation = useMutation({
    mutationFn: (payload: UserFoodCreate) =>
      api<Food>(food ? `/api/v1/nutrition/foods/${food.id}` : '/api/v1/nutrition/foods', {
        method: food ? 'PATCH' : 'POST',
        body: payload,
      }),
    onSuccess: async (saved) => {
      if (saved.catalog_contribution_outcome) {
        trackProductEvent({
          name: 'nutrition_food_catalog_contribution_outcome',
          surface: productEventSurface(),
          outcome: saved.catalog_contribution_outcome,
        });
      }
      await queryClient.invalidateQueries({ queryKey: ['nutrition', 'foods'] });
      onSaved(saved);
    },
  });
  const field = (key: keyof FoodDraft, value: string) => {
    mutation.reset();
    setErrors((current) => ({ ...current, [key]: undefined }));
    setDraft((current) => ({ ...current, [key]: value }));
  };
  const prefillUpdates = (prefill: NutritionLabelPrefill): Partial<FoodDraft> => ({
    name: prefill.name,
    brand: prefill.brand,
    barcode: prefill.barcode,
    basis: prefill.sourceBasis === 'ambiguous' ? 'per_100_g' : prefill.sourceBasis,
    ...(prefill.nutrientsCanPopulate100g
      ? {
          energy: prefill.nutrients.energy_kcal ?? '',
          protein: prefill.nutrients.protein_g ?? '',
          fat: prefill.nutrients.fat_g ?? '',
          carbs: prefill.nutrients.carbohydrate_g ?? '',
          fiber: prefill.nutrients.fiber_g ?? '',
        }
      : {}),
    ...(prefill.servingSize?.unit === 'g' ? { servingWeight: prefill.servingSize.amount } : {}),
  });

  const valuesMatch = (left: string, right: string): boolean => {
    if (!left.trim() || !right.trim()) return left.trim() === right.trim();
    const leftNumber = Number(left.replace(',', '.'));
    const rightNumber = Number(right.replace(',', '.'));
    if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
      return leftNumber === rightNumber;
    }
    return left.trim().replace(/\s+/g, ' ') === right.trim().replace(/\s+/g, ' ');
  };

  const applyPhotoPrefill = (prefill: NutritionLabelPrefill, replaceConflicts = false) => {
    const updates = prefillUpdates(prefill);
    setPhotoPrefillNotice(
      prefill.nutrientsCanPopulate100g
        ? ''
        : `Пищевая ценность указана ${prefill.sourceBasis === 'per_100_ml' ? 'на 100 мл' : 'на порцию без веса в граммах'}. Её нельзя безопасно перенести в форму «на 100 г» без плотности или массы порции.`,
    );
    const labels: Record<keyof FoodDraft, string> = {
      name: 'названии',
      brand: 'бренде',
      barcode: 'штрихкоде',
      classification: 'типе продукта',
      basis: 'основе пищевой ценности',
      energy: 'калорийности',
      protein: 'белках',
      fat: 'жирах',
      carbs: 'углеводах',
      fiber: 'клетчатке',
      servingWeight: 'весе порции',
    };
    const conflicts = (Object.keys(updates) as Array<keyof FoodDraft>)
      .filter(
        (key) =>
          draft[key].trim() && updates[key]?.trim() && !valuesMatch(draft[key], updates[key]!),
      )
      .map((key) => ({ label: labels[key], current: draft[key], recognized: updates[key]! }));
    setDraft((current) => {
      const next = { ...current };
      for (const key of Object.keys(updates) as Array<keyof FoodDraft>) {
        const recognized = updates[key];
        if (!recognized?.trim()) continue;
        if (replaceConflicts || !current[key].trim() || valuesMatch(current[key], recognized)) {
          Object.assign(next, { [key]: recognized });
        }
      }
      return next;
    });
    setPhotoScanOpen(false);
    setErrors({});
    if (replaceConflicts || conflicts.length === 0) {
      setPhotoConflicts([]);
      setPendingPhotoPrefill(null);
    } else {
      setPhotoConflicts(conflicts);
      setPendingPhotoPrefill(prefill);
    }
  };
  const macroFields = useMemo(
    () =>
      [
        ['energy', 'Калории', '0–1000 ккал'],
        ['protein', 'Белки', '0–100 г'],
        ['fat', 'Жиры', '0–100 г'],
        ['carbs', 'Углеводы', '0–100 г'],
      ] as const,
    [],
  );
  const basisLabel =
    draft.basis === 'per_100_ml' ? '100 мл' : draft.basis === 'per_serving' ? 'порцию' : '100 г';

  if (photoScanOpen) {
    return (
      <NutritionLabelScanner
        mode="prefill"
        userId={userId}
        initialBarcode={draft.barcode}
        initialBrand={draft.brand}
        initialName={draft.name}
        onCancel={() => setPhotoScanOpen(false)}
        onManualFallback={() => setPhotoScanOpen(false)}
        onPrefilled={applyPhotoPrefill}
      />
    );
  }

  return (
    <form
      className="nutrition-editor"
      aria-label={title}
      onSubmit={(event) => {
        event.preventDefault();
        const result = validateFood(draft);
        setErrors(result.errors);
        if (result.payload) {
          trackProductEvent({
            name: 'nutrition_food_classification_selected',
            surface: productEventSurface(),
            classification: draft.classification,
          });
          mutation.mutate(result.payload);
        }
      }}
    >
      <div className="nutrition-editor__intro">
        <h3>{title}</h3>
        <p>Проверьте основу и значения перед сохранением. Обязательные поля отмечены звёздочкой.</p>
        <Button
          type="button"
          variant="secondary"
          onClick={() => setPhotoScanOpen(true)}
          disabled={mutation.isPending}
        >
          Заполнить по фото
        </Button>
      </div>
      {pendingPhotoPrefill && photoConflicts.length > 0 && (
        <div className="nutrition-provider-fallback nutrition-editor__photo-conflict" role="alert">
          <strong>Фото отличается от уже введённых данных</strong>
          <span>
            Выберите, какие значения оставить. Пустые поля уже заполнены распознанными данными.
          </span>
          <ul>
            {photoConflicts.map((conflict) => (
              <li key={conflict.label}>
                {conflict.label}: {conflict.current} → {conflict.recognized}
              </li>
            ))}
          </ul>
          <div className="nutrition-editor__actions">
            <Button type="button" onClick={() => applyPhotoPrefill(pendingPhotoPrefill, true)}>
              Заменить распознанным
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setPhotoConflicts([]);
                setPendingPhotoPrefill(null);
              }}
            >
              Оставить введённое
            </Button>
          </div>
        </div>
      )}
      {photoPrefillNotice && (
        <p className="nutrition-provider-fallback" role="status">
          {photoPrefillNotice} Введите значения на 100 г вручную или вернитесь к сканированию и
          уточните основу.
        </p>
      )}
      <fieldset className="nutrition-editor__classification">
        <legend>Что это за продукт?</legend>
        <label className="nutrition-label-review__choice">
          <input
            type="radio"
            name="own-food-classification"
            value="personal"
            checked={draft.classification === 'personal'}
            onChange={() => {
              trackProductEvent({
                name: 'nutrition_food_classification_selected',
                surface: productEventSurface(),
                classification: 'personal',
              });
              field('classification', 'personal');
            }}
          />
          <span>
            <strong>Мой продукт или домашняя еда</strong>
            <small>Сохранится только в вашем списке продуктов.</small>
          </span>
        </label>
        <label className="nutrition-label-review__choice">
          <input
            type="radio"
            name="own-food-classification"
            value="commercial"
            checked={draft.classification === 'commercial'}
            onChange={() => {
              trackProductEvent({
                name: 'nutrition_food_classification_selected',
                surface: productEventSurface(),
                classification: 'commercial',
              });
              field('classification', 'commercial');
            }}
          />
          <span>
            <strong>Продукт из магазина</strong>
            <small>Проверенные вами данные помогут дополнить общий каталог.</small>
          </span>
        </label>
      </fieldset>
      <div className="nutrition-editor__grid">
        <Field label="Название *" labelFor="own-food-name" error={errors.name}>
          <Input
            id="own-food-name"
            autoFocus
            maxLength={256}
            value={draft.name}
            onChange={(event) => field('name', event.target.value)}
          />
        </Field>
        <Field label="Бренд" labelFor="own-food-brand" error={errors.brand}>
          <Input
            id="own-food-brand"
            maxLength={128}
            value={draft.brand}
            onChange={(event) => field('brand', event.target.value)}
          />
        </Field>
        <Field label="Основа пищевой ценности" labelFor="own-food-basis">
          <select
            id="own-food-basis"
            value={draft.basis}
            onChange={(event) => field('basis', event.target.value as FoodDraft['basis'])}
          >
            <option value="per_100_g">На 100 г</option>
            <option value="per_100_ml">На 100 мл</option>
            <option value="per_serving">На порцию</option>
          </select>
        </Field>
        {macroFields.map(([key, label]) => (
          <Field
            key={key}
            label={`${label} *`}
            labelFor={`own-food-${key}`}
            hint={`на ${basisLabel}`}
            error={errors[key]}
          >
            <Input
              id={`own-food-${key}`}
              type="number"
              inputMode="decimal"
              min="0"
              step="any"
              value={draft[key]}
              onChange={(event) => field(key, event.target.value)}
            />
          </Field>
        ))}
        <Field
          label="Клетчатка"
          labelFor="own-food-fiber"
          hint="необязательно, г"
          error={errors.fiber}
        >
          <Input
            id="own-food-fiber"
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            value={draft.fiber}
            onChange={(event) => field('fiber', event.target.value)}
          />
        </Field>
        <Field
          label="Вес одной порции"
          labelFor="own-food-serving"
          hint="необязательно, г"
          error={errors.servingWeight}
        >
          <Input
            id="own-food-serving"
            type="number"
            inputMode="decimal"
            min="0.001"
            step="any"
            value={draft.servingWeight}
            onChange={(event) => field('servingWeight', event.target.value)}
          />
        </Field>
        <Field
          label="Штрихкод"
          labelFor="own-food-barcode"
          hint="необязательно"
          error={errors.barcode}
        >
          <Input
            id="own-food-barcode"
            inputMode="numeric"
            maxLength={14}
            value={draft.barcode}
            onChange={(event) => field('barcode', event.target.value.replace(/\D/g, ''))}
          />
        </Field>
      </div>
      {mutation.error && (
        <p className="nutrition-form-error" role="alert">
          {saveError(mutation.error)}
        </p>
      )}
      <div className="nutrition-editor__actions">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Сохраняем…' : food ? 'Сохранить изменения' : 'Создать продукт'}
        </Button>
        <Button type="button" variant="ghost" disabled={mutation.isPending} onClick={onCancel}>
          Отмена
        </Button>
      </div>
    </form>
  );
}
