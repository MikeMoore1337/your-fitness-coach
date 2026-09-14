import { useMemo, useRef, useState, type FormEvent } from 'react';
import type {
  NutritionLabelCanonicalDraft,
  NutritionLabelConfirmRequest,
  NutritionLabelDraft,
  NutritionLabelFactsEdit,
} from '../../shared/api/types';
import { Button, Field, Input, Select } from '../../shared/ui/common';
import { isValidGtin } from './nutritionFoodUtils';

export const NUTRITION_LABEL_FIELDS = [
  'energy_kcal',
  'energy_kj',
  'protein_g',
  'fat_g',
  'carbohydrate_g',
  'sugars_g',
  'added_sugars_g',
  'fiber_g',
  'saturated_fat_g',
  'trans_fat_g',
  'salt_g',
  'sodium_mg',
  'cholesterol_mg',
] as const;

export type NutritionLabelField = (typeof NUTRITION_LABEL_FIELDS)[number];
export type NutritionLabelEditableNutrients = Record<NutritionLabelField, string | null>;

export type NutritionLabelPrefill = {
  name: string;
  brand: string;
  barcode: string;
  nutrients: NutritionLabelEditableNutrients;
  servingSize: { amount: string; unit: 'g' | 'ml' } | null;
  sourceBasis: NutritionLabelFactsEdit['source_basis'];
  nutrientsCanPopulate100g: boolean;
};

type ReviewMode = 'catalog' | 'prefill';

type NutritionLabelReviewProps = {
  draft: NutritionLabelDraft;
  mode: ReviewMode;
  initialName?: string;
  initialBrand?: string;
  initialBarcode?: string;
  isSubmitting?: boolean;
  submitError?: string;
  onCancel: () => void;
  onManualFallback?: () => void;
  onCorrection?: () => void;
  onSubmit: (values: NutritionLabelReviewValues) => void;
};

export type NutritionLabelReviewValues = {
  name: string;
  brand: string;
  barcode: string;
  visibility: NutritionLabelConfirmRequest['visibility'];
  nutrition: NutritionLabelFactsEdit;
};

const REQUIRED_FIELDS: readonly NutritionLabelField[] = [
  'energy_kcal',
  'protein_g',
  'fat_g',
  'carbohydrate_g',
];

const FIELD_LABELS: Record<NutritionLabelField, string> = {
  energy_kcal: 'Калории',
  energy_kj: 'Энергия, кДж',
  protein_g: 'Белки',
  fat_g: 'Жиры',
  carbohydrate_g: 'Углеводы',
  sugars_g: 'Сахара',
  added_sugars_g: 'Добавленные сахара',
  fiber_g: 'Клетчатка',
  saturated_fat_g: 'Насыщенные жиры',
  trans_fat_g: 'Трансжиры',
  salt_g: 'Соль',
  sodium_mg: 'Натрий',
  cholesterol_mg: 'Холестерин',
};

const FIELD_UNITS: Record<NutritionLabelField, string> = {
  energy_kcal: 'ккал',
  energy_kj: 'кДж',
  protein_g: 'г',
  fat_g: 'г',
  carbohydrate_g: 'г',
  sugars_g: 'г',
  added_sugars_g: 'г',
  fiber_g: 'г',
  saturated_fat_g: 'г',
  trans_fat_g: 'г',
  salt_g: 'г',
  sodium_mg: 'мг',
  cholesterol_mg: 'мг',
};

const BASIS_LABELS: Record<NutritionLabelFactsEdit['source_basis'], string> = {
  per_100_g: 'на 100 г',
  per_100_ml: 'на 100 мл',
  per_serving: 'на порцию',
  ambiguous: 'основа не выбрана',
};

const WARNING_LABELS: Record<string, string> = {
  ambiguous_basis: 'Основа расчёта не определена однозначно.',
  ambiguous_column: 'Для одного из значений найдено несколько возможных колонок.',
  serving_size_required_for_normalization: 'Для пересчёта порции нужен размер порции.',
  dv_as_mass: 'Процент дневной нормы не используется как масса нутриента.',
  missing_required_fact: 'Не все обязательные значения удалось найти.',
  energy_unit_ambiguous: 'Единица энергии не распознана однозначно — проверьте кДж и ккал.',
  energy_unit_conflict: 'Пара кДж/ккал не согласуется — сверяйте оба значения с упаковкой.',
  energy_outlier: 'Калорийность выглядит нереалистично для указанной основы — проверьте упаковку.',
  nutrient_outlier: 'Одно из значений выглядит нереалистично — проверьте упаковку.',
  untrusted_numeric_token: 'Число без надёжно распознанной единицы не подставлено автоматически.',
  energy_sanity_warning: 'Проверьте калорийность по упаковке.',
  unreadable_field: 'Часть значений на фото читается недостаточно хорошо.',
  ocr_budget_exhausted:
    'Показан лучший результат в пределах лимита распознавания — проверьте значения по упаковке.',
  user_corrected_fields: 'Некоторые значения изменены пользователем.',
};

function numericText(value: string | null | undefined): string {
  return value ?? '';
}

function sourceCells(
  nutrition: NutritionLabelCanonicalDraft,
  field: NutritionLabelField,
): NonNullable<NutritionLabelCanonicalDraft['source_facts'][NutritionLabelField]> {
  return nutrition.source_facts[field] ?? [];
}

function initialFieldValues(
  nutrition: NutritionLabelCanonicalDraft,
): NutritionLabelEditableNutrients {
  return Object.fromEntries(
    NUTRITION_LABEL_FIELDS.map((field) => {
      const cell = sourceCells(nutrition, field).find(
        (candidate) => candidate.evidence === 'read' && candidate.value !== null,
      );
      return [field, numericText(cell?.value) || null];
    }),
  ) as NutritionLabelEditableNutrients;
}

function initialColumnChoices(
  nutrition: NutritionLabelCanonicalDraft,
): Record<NutritionLabelField, string> {
  return Object.fromEntries(
    NUTRITION_LABEL_FIELDS.map((field) => {
      const cells = sourceCells(nutrition, field);
      return [field, cells.length === 1 ? (cells[0]?.column_ref ?? '') : ''];
    }),
  ) as Record<NutritionLabelField, string>;
}

function basisSummary(nutrition: NutritionLabelCanonicalDraft): string {
  const basis = BASIS_LABELS[nutrition.source_basis];
  if (nutrition.source_basis === 'per_serving' && nutrition.serving_size) {
    return `${basis}, ${nutrition.serving_size.amount} ${nutrition.serving_size.unit}`;
  }
  return basis;
}

function formatNormalizedFact(
  fact: NutritionLabelCanonicalDraft['normalized_facts'][NutritionLabelField],
  field: NutritionLabelField,
): string {
  if (!fact) return 'Не распознано';
  return `${fact.value} ${FIELD_UNITS[field]} / ${
    fact.basis_ref === 'per_100_g' ? '100 г' : fact.basis_ref === 'per_100_ml' ? '100 мл' : 'порция'
  }`;
}

function formatDerivedFact(
  fact: NutritionLabelCanonicalDraft['derived_fields'][NutritionLabelField],
): string | null {
  if (!fact) return null;
  return `Вычислено отдельно: ${fact.value} ${fact.unit}. Сверьте с упаковкой.`;
}

function evidenceLabel(
  nutrition: NutritionLabelCanonicalDraft,
  field: NutritionLabelField,
): string {
  const evidence = nutrition.field_evidence[field];
  if (evidence === 'read') return 'Найдено на фото — проверьте';
  if (evidence === 'ambiguous') return 'Нужно уточнить';
  if (evidence === 'derived') return 'Вычислено отдельно';
  if (evidence === 'unreadable') return 'Не удалось прочитать';
  return 'Не распознано';
}

function warningLabel(code: string): string {
  return WARNING_LABELS[code] ?? 'Часть данных требует проверки по упаковке.';
}

function isRequired(field: NutritionLabelField): boolean {
  return REQUIRED_FIELDS.includes(field);
}

function parseNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value.replace(',', '.'));
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function fieldError(value: string, required: boolean): string | undefined {
  if (!value.trim()) return required ? 'Укажите значение' : undefined;
  return parseNumber(value) === null ? 'Введите неотрицательное число' : undefined;
}

export function nutritionLabelPrefillFromValues(
  values: NutritionLabelReviewValues,
): NutritionLabelPrefill {
  const canUseSourceValues = values.nutrition.source_basis === 'per_100_g';
  const canNormalizeServing =
    values.nutrition.source_basis === 'per_serving' &&
    values.nutrition.serving_size?.unit === 'g' &&
    Number(values.nutrition.serving_size.amount) > 0;
  const nutrients = Object.fromEntries(
    NUTRITION_LABEL_FIELDS.map((field) => [
      field,
      canUseSourceValues
        ? values.nutrition[field] === null || values.nutrition[field] === undefined
          ? null
          : String(values.nutrition[field])
        : canNormalizeServing
          ? (() => {
              const value = values.nutrition[field];
              if (value === null || value === undefined) return null;
              return String((Number(value) * 100) / Number(values.nutrition.serving_size?.amount));
            })()
          : null,
    ]),
  ) as NutritionLabelEditableNutrients;
  const servingSize = values.nutrition.serving_size
    ? {
        amount: String(values.nutrition.serving_size.amount),
        unit: values.nutrition.serving_size.unit,
      }
    : null;
  return {
    name: values.name,
    brand: values.brand,
    barcode: values.barcode,
    nutrients,
    servingSize,
    sourceBasis: values.nutrition.source_basis,
    nutrientsCanPopulate100g: canUseSourceValues || canNormalizeServing,
  };
}

export function NutritionLabelReview({
  draft,
  mode,
  initialName = '',
  initialBrand = '',
  initialBarcode = '',
  isSubmitting = false,
  submitError,
  onCancel,
  onManualFallback,
  onCorrection,
  onSubmit,
}: NutritionLabelReviewProps) {
  const nutrition = draft.nutrition;
  const [name, setName] = useState(draft.product_name ?? initialName);
  const [brand, setBrand] = useState(draft.product_brand ?? initialBrand);
  const [barcode, setBarcode] = useState(draft.product_barcode ?? initialBarcode);
  const [basis, setBasis] = useState<NutritionLabelFactsEdit['source_basis']>(
    nutrition.source_basis,
  );
  const [values, setValues] = useState<NutritionLabelEditableNutrients>(() =>
    initialFieldValues(nutrition),
  );
  const [columnChoices, setColumnChoices] = useState<Record<NutritionLabelField, string>>(() =>
    initialColumnChoices(nutrition),
  );
  const [servingAmount, setServingAmount] = useState(
    nutrition.serving_size ? String(nutrition.serving_size.amount) : '',
  );
  const [servingUnit, setServingUnit] = useState<'g' | 'ml'>(nutrition.serving_size?.unit ?? 'g');
  const [servingsPerContainer, setServingsPerContainer] = useState(
    nutrition.servings_per_container ?? '',
  );
  const [packageAmount, setPackageAmount] = useState(
    nutrition.package_amount ? String(nutrition.package_amount.amount) : '',
  );
  const [packageUnit, setPackageUnit] = useState<'g' | 'ml'>(nutrition.package_amount?.unit ?? 'g');
  const [visibility, setVisibility] =
    useState<NutritionLabelConfirmRequest['visibility']>('private');
  const [formError, setFormError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<NutritionLabelField, string>>>({});
  const correctionReportedRef = useRef(false);

  const reportCorrection = () => {
    if (correctionReportedRef.current) return;
    correctionReportedRef.current = true;
    onCorrection?.();
  };

  const validBarcode = isValidGtin(barcode.replace(/\s+/g, ''));

  const warningLabels = useMemo(
    () => Array.from(new Set(draft.warnings.map(warningLabel))),
    [draft.warnings],
  );
  const sourceFactsWithChoices = useMemo(
    () => NUTRITION_LABEL_FIELDS.filter((field) => sourceCells(nutrition, field).length > 1),
    [nutrition],
  );
  const hasMissingColumnChoice = sourceFactsWithChoices.some((field) => !columnChoices[field]);
  const normalizedBasis = basisSummary(nutrition);

  const updateValue = (field: NutritionLabelField, value: string) => {
    reportCorrection();
    setFormError('');
    setFieldErrors((current) => ({ ...current, [field]: undefined }));
    setValues((current) => ({ ...current, [field]: value || null }));
  };

  const selectColumn = (field: NutritionLabelField, columnRef: string) => {
    setColumnChoices((current) => ({ ...current, [field]: columnRef }));
    const candidate = sourceCells(nutrition, field).find((cell) => cell.column_ref === columnRef);
    updateValue(field, candidate?.value ?? '');
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isSubmitting) return;
    const errors: Partial<Record<NutritionLabelField, string>> = {};
    for (const field of NUTRITION_LABEL_FIELDS) {
      const error = fieldError(values[field] ?? '', isRequired(field));
      if (error) errors[field] = error;
    }
    const normalizedName = name.trim().replace(/\s+/g, ' ');
    const normalizedBarcode = barcode.replace(/\s+/g, '');
    if (!normalizedName) {
      setFormError('Введите название продукта.');
    } else if (!basis || basis === 'ambiguous') {
      setFormError('Выберите основу расчёта: 100 г, 100 мл или порция.');
    } else if (basis === 'per_serving' && servingAmount && parseNumber(servingAmount) === null) {
      setFormError('Проверьте размер порции.');
    } else if (servingsPerContainer && parseNumber(servingsPerContainer) === null) {
      setFormError('Проверьте количество порций в упаковке.');
    } else if (packageAmount && parseNumber(packageAmount) === null) {
      setFormError('Проверьте массу или объём упаковки.');
    } else if (hasMissingColumnChoice) {
      setFormError('Выберите колонку на фото для каждой неоднозначной строки.');
    } else if (Object.keys(errors).length > 0) {
      setFormError('Проверьте обязательные значения и исправьте ошибки.');
    } else if (normalizedBarcode && !isValidGtin(normalizedBarcode)) {
      setFormError('Проверьте цифры штрихкода или оставьте поле пустым.');
    } else {
      const nutritionEdit = {
        source_basis: basis,
        serving_size: servingAmount
          ? { amount: parseNumber(servingAmount)!, unit: servingUnit }
          : null,
        servings_per_container: servingsPerContainer ? parseNumber(servingsPerContainer) : null,
        package_amount: packageAmount
          ? { amount: parseNumber(packageAmount)!, unit: packageUnit }
          : null,
        ...Object.fromEntries(
          NUTRITION_LABEL_FIELDS.map((field) => [field, parseNumber(values[field] ?? '')]),
        ),
      } as NutritionLabelFactsEdit;
      onSubmit({
        name: normalizedName,
        brand: brand.trim().replace(/\s+/g, ' '),
        barcode: normalizedBarcode,
        visibility: validBarcode ? visibility : 'private',
        nutrition: nutritionEdit,
      });
      return;
    }
    setFieldErrors(errors);
  };

  return (
    <form
      className="nutrition-label-review"
      aria-label="Проверка данных с этикетки"
      onSubmit={submit}
    >
      <div className="nutrition-label-review__intro">
        <span className="eyebrow">Проверьте перед сохранением</span>
        <h3>Данные с пищевой этикетки</h3>
        <p>
          Распознавание только заполняет черновик. Сверьте каждое значение с упаковкой — особенно
          основу расчёта и неоднозначные строки.
        </p>
      </div>

      <div className="nutrition-label-review__summary" role="status">
        <div>
          <span>Основа на фото</span>
          <strong>{normalizedBasis}</strong>
        </div>
        <div>
          <span>Нормализованный вид</span>
          <strong>
            {basis === 'per_100_ml' ? '100 мл' : basis === 'per_serving' ? 'порция' : '100 г'}
          </strong>
        </div>
      </div>

      {warningLabels.length > 0 && (
        <div className="nutrition-label-review__warnings" role="alert">
          <strong>Что требует внимания</strong>
          <ul>
            {warningLabels.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <fieldset className="nutrition-label-review__fieldset">
        <legend>Основа расчёта *</legend>
        <Field
          label="Значения указаны"
          labelFor="nutrition-label-basis"
          hint="Выберите строку с упаковки, а не процент дневной нормы"
        >
          <Select
            id="nutrition-label-basis"
            value={basis}
            onChange={(event) => {
              reportCorrection();
              setBasis(event.target.value as NutritionLabelFactsEdit['source_basis']);
              setFormError('');
            }}
          >
            <option value="">Выберите основу…</option>
            <option value="per_100_g">На 100 г</option>
            <option value="per_100_ml">На 100 мл</option>
            <option value="per_serving">На порцию</option>
          </Select>
        </Field>
        {basis === 'per_serving' && (
          <div className="nutrition-label-review__basis-grid">
            <Field
              label="Размер порции"
              labelFor="nutrition-label-serving-amount"
              hint="если указан"
            >
              <Input
                id="nutrition-label-serving-amount"
                type="text"
                inputMode="decimal"
                value={servingAmount}
                onChange={(event) => {
                  reportCorrection();
                  setServingAmount(event.target.value);
                }}
                placeholder="например, 30"
              />
            </Field>
            <Field label="Единица" labelFor="nutrition-label-serving-unit">
              <Select
                id="nutrition-label-serving-unit"
                value={servingUnit}
                onChange={(event) => {
                  reportCorrection();
                  setServingUnit(event.target.value as 'g' | 'ml');
                }}
              >
                <option value="g">г</option>
                <option value="ml">мл</option>
              </Select>
            </Field>
          </div>
        )}
      </fieldset>

      <fieldset className="nutrition-label-review__fieldset">
        <legend>Название продукта</legend>
        <div className="nutrition-label-review__identity-grid">
          <Field label="Название *" labelFor="nutrition-label-name">
            <Input
              id="nutrition-label-name"
              value={name}
              maxLength={256}
              onChange={(event) => {
                reportCorrection();
                setName(event.target.value);
                setFormError('');
              }}
              autoFocus={!name}
            />
          </Field>
          <Field label="Бренд" labelFor="nutrition-label-brand">
            <Input
              id="nutrition-label-brand"
              value={brand}
              maxLength={128}
              onChange={(event) => {
                reportCorrection();
                setBrand(event.target.value);
              }}
            />
          </Field>
          <Field
            label="Штрихкод"
            labelFor="nutrition-label-barcode"
            hint="корректный GTIN открывает общий каталог"
          >
            <Input
              id="nutrition-label-barcode"
              inputMode="numeric"
              maxLength={14}
              value={barcode}
              onChange={(event) => {
                reportCorrection();
                const nextBarcode = event.target.value.replace(/\D/g, '');
                setBarcode(nextBarcode);
                if (!isValidGtin(nextBarcode)) setVisibility('private');
                setFormError('');
              }}
              placeholder="необязательно"
            />
          </Field>
        </div>
      </fieldset>

      <fieldset className="nutrition-label-review__fieldset">
        <legend>Пищевая ценность *</legend>
        <p className="nutrition-label-review__fieldset-hint">
          Пустое значение остаётся «Не распознано», а не превращается в ноль. Единицы рядом с полем
          взяты из контракта этикетки.
        </p>
        <div className="nutrition-label-review__nutrients">
          {REQUIRED_FIELDS.map((field) => (
            <NutrientField
              field={field}
              key={field}
              value={values[field] ?? ''}
              error={fieldErrors[field]}
              evidence={evidenceLabel(nutrition, field)}
              normalized={formatNormalizedFact(nutrition.normalized_facts[field], field)}
              derived={formatDerivedFact(nutrition.derived_fields[field])}
              onChange={updateValue}
              cells={sourceCells(nutrition, field)}
              selectedColumn={columnChoices[field]}
              onSelectColumn={selectColumn}
            />
          ))}
        </div>
      </fieldset>

      <details className="nutrition-label-review__details" open={sourceFactsWithChoices.length > 0}>
        <summary>Дополнительные значения и сведения</summary>
        <div className="nutrition-label-review__details-body">
          <div className="nutrition-label-review__nutrients">
            {NUTRITION_LABEL_FIELDS.filter((field) => !REQUIRED_FIELDS.includes(field)).map(
              (field) => (
                <NutrientField
                  field={field}
                  key={field}
                  value={values[field] ?? ''}
                  error={fieldErrors[field]}
                  evidence={evidenceLabel(nutrition, field)}
                  normalized={formatNormalizedFact(nutrition.normalized_facts[field], field)}
                  derived={formatDerivedFact(nutrition.derived_fields[field])}
                  onChange={updateValue}
                  cells={sourceCells(nutrition, field)}
                  selectedColumn={columnChoices[field]}
                  onSelectColumn={selectColumn}
                />
              ),
            )}
          </div>
          <div className="nutrition-label-review__package-grid">
            <Field label="Порций в упаковке" labelFor="nutrition-label-servings">
              <Input
                id="nutrition-label-servings"
                type="text"
                inputMode="decimal"
                value={servingsPerContainer}
                onChange={(event) => {
                  reportCorrection();
                  setServingsPerContainer(event.target.value);
                }}
              />
            </Field>
            <Field label="Масса или объём упаковки" labelFor="nutrition-label-package-amount">
              <Input
                id="nutrition-label-package-amount"
                type="text"
                inputMode="decimal"
                value={packageAmount}
                onChange={(event) => {
                  reportCorrection();
                  setPackageAmount(event.target.value);
                }}
              />
            </Field>
            <Field label="Единица упаковки" labelFor="nutrition-label-package-unit">
              <Select
                id="nutrition-label-package-unit"
                value={packageUnit}
                onChange={(event) => {
                  reportCorrection();
                  setPackageUnit(event.target.value as 'g' | 'ml');
                }}
              >
                <option value="g">г</option>
                <option value="ml">мл</option>
              </Select>
            </Field>
          </div>
          {sourceFactsWithChoices.length > 0 && (
            <p className="nutrition-label-review__source-note">
              Для строк с несколькими колонками выберите нужную колонку перед сохранением.
            </p>
          )}
          <dl className="nutrition-label-review__provenance">
            <div>
              <dt>Язык этикетки</dt>
              <dd>
                {nutrition.source_language === 'ru'
                  ? 'русский'
                  : nutrition.source_language === 'en'
                    ? 'английский'
                    : nutrition.source_language === 'mixed'
                      ? 'смешанный'
                      : 'не определён'}
              </dd>
            </div>
            <div>
              <dt>Формат</dt>
              <dd>
                {nutrition.label_format === 'us_nutrition_facts'
                  ? 'Nutrition Facts'
                  : nutrition.label_format === 'eu_uk'
                    ? 'EU / UK'
                    : nutrition.label_format === 'ru_standard'
                      ? 'российская этикетка'
                      : 'не определён'}
              </dd>
            </div>
          </dl>
          <div className="nutrition-label-review__normalized">
            <strong>Нормализованный просмотр</strong>
            <ul>
              {REQUIRED_FIELDS.map((field) => (
                <li key={field}>
                  {FIELD_LABELS[field]}:{' '}
                  {formatNormalizedFact(nutrition.normalized_facts[field], field)}
                </li>
              ))}
            </ul>
          </div>
          <p className="nutrition-label-review__confidence">
            {nutrition.confidence_kind === 'none'
              ? 'Автоматическая точность не измерялась. Окончательное значение подтверждаете вы.'
              : 'Автоматическая оценка точности не заменяет сверку с упаковкой.'}
          </p>
        </div>
      </details>

      <fieldset className="nutrition-label-review__fieldset nutrition-label-review__visibility">
        <legend>Кому доступен продукт</legend>
        <label className="nutrition-label-review__choice">
          <input
            type="radio"
            name="nutrition-label-visibility"
            value="private"
            checked={visibility === 'private' || !validBarcode}
            onChange={() => {
              reportCorrection();
              setVisibility('private');
            }}
          />
          <span>
            <strong>Сохранить только для себя</strong>
            <small>Продукт останется в вашем личном каталоге.</small>
          </span>
        </label>
        {validBarcode ? (
          <label className="nutrition-label-review__choice">
            <input
              type="radio"
              name="nutrition-label-visibility"
              value="share_to_yfc_catalog"
              checked={visibility === 'share_to_yfc_catalog'}
              onChange={() => {
                reportCorrection();
                setVisibility('share_to_yfc_catalog');
              }}
            />
            <span>
              <strong>Добавить в каталог YFC</strong>
              <small>Другие пользователи увидят карточку без вашего фото и имени.</small>
            </span>
          </label>
        ) : (
          <p className="nutrition-label-review__visibility-hint">
            Для общего каталога нужен корректный GTIN-8, UPC-A, EAN-13 или GTIN-14. Сейчас выбран
            личный каталог.
          </p>
        )}
      </fieldset>

      {(formError || submitError) && (
        <p className="nutrition-form-error" role="alert">
          {submitError || formError}
        </p>
      )}

      <div className="nutrition-editor__actions nutrition-label-review__actions">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting
            ? 'Сохраняем…'
            : mode === 'prefill'
              ? 'Использовать в форме'
              : 'Подтвердить и сохранить продукт'}
        </Button>
        {onManualFallback && (
          <Button
            type="button"
            variant="secondary"
            disabled={isSubmitting}
            onClick={onManualFallback}
          >
            Продолжить вручную
          </Button>
        )}
        <Button type="button" variant="ghost" disabled={isSubmitting} onClick={onCancel}>
          Отмена
        </Button>
      </div>
    </form>
  );
}

function NutrientField({
  field,
  value,
  error,
  evidence,
  normalized,
  derived,
  onChange,
  cells,
  selectedColumn,
  onSelectColumn,
}: {
  field: NutritionLabelField;
  value: string;
  error?: string;
  evidence: string;
  normalized: string;
  derived: string | null;
  onChange: (field: NutritionLabelField, value: string) => void;
  cells: NonNullable<NutritionLabelCanonicalDraft['source_facts'][NutritionLabelField]>;
  selectedColumn: string;
  onSelectColumn: (field: NutritionLabelField, columnRef: string) => void;
}) {
  const id = `nutrition-label-${field}`;
  return (
    <div className="nutrition-label-review__nutrient">
      <Field
        label={`${FIELD_LABELS[field]}${isRequired(field) ? ' *' : ''}`}
        labelFor={id}
        hint={`${FIELD_UNITS[field]} · ${evidence}`}
        error={error}
      >
        <div className="nutrition-label-review__input-with-unit">
          <Input
            id={id}
            type="text"
            inputMode="decimal"
            value={value}
            placeholder="Не распознано"
            onChange={(event) => onChange(field, event.target.value)}
          />
          <span aria-hidden="true">{FIELD_UNITS[field]}</span>
        </div>
      </Field>
      {cells.length > 1 && (
        <label className="nutrition-label-review__column">
          <span>Колонка на фото</span>
          <select
            aria-label={`Колонка на фото для поля «${FIELD_LABELS[field]}»`}
            aria-required="true"
            value={selectedColumn}
            onChange={(event) => onSelectColumn(field, event.target.value)}
          >
            <option value="">Выберите колонку…</option>
            {cells.map((cell, index) => (
              <option key={cell.column_ref} value={cell.column_ref}>
                {`Колонка ${index + 1}`}
              </option>
            ))}
          </select>
        </label>
      )}
      <span className="nutrition-label-review__normalized-fact">
        {normalized}
        {derived && (
          <>
            {normalized ? ' · ' : ''}
            {derived}
          </>
        )}
      </span>
    </div>
  );
}
