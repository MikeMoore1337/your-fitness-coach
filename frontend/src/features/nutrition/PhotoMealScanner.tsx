import { useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, api } from '../../shared/api/client';
import type { PhotoMealConfirmResponse, PhotoMealDraft } from '../../shared/api/types';
import { Button, Field, Input, Select } from '../../shared/ui/common';

const MAX_IMAGE_BYTES = 8_388_608;
const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snacks';
type CaptureStatus = 'capture' | 'preview' | 'recognizing' | 'review';
type PortionUnit = 'g' | 'ml' | 'serving';

type EditableCandidate = {
  candidateId: string;
  name: string;
  portionAmount: string;
  portionUnit: PortionUnit | '';
  portionConfidence: string;
  identityConfidence: string;
  nutritionConfidence: string;
  uncertaintyCodes: string[];
  energyKcal: string;
  proteinG: string;
  fatG: string;
  carbsG: string;
};

type PhotoMealScannerProps = {
  userId?: number | 'anonymous';
  diaryDate: string;
  mealType: MealType;
  onCancel: () => void;
  onManualFallback?: () => void;
  onCompleted: (response: PhotoMealConfirmResponse) => void | Promise<void>;
};

function errorCode(error: unknown): string | null {
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : null;
  const body = error.body;
  const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
  const code = detail && typeof detail === 'object' && 'code' in detail ? detail.code : null;
  return typeof code === 'string' ? code : null;
}

function errorMessage(error: unknown): string {
  const code = errorCode(error);
  const messages: Record<string, string> = {
    feature_disabled: 'Фото блюда сейчас недоступно. Добавьте запись приблизительно.',
    vision_unavailable: 'Распознавание фото сейчас недоступно. Добавьте запись приблизительно.',
    vision_timeout: 'Распознавание не завершилось вовремя. Добавьте запись приблизительно.',
    vision_invalid_response: 'Результат распознавания не удалось безопасно проверить.',
    vision_failed: 'Распознавание временно недоступно. Добавьте запись приблизительно.',
    manual_fallback_required:
      'На фото не удалось надёжно определить блюдо. Добавьте его вручную или приблизительно.',
    unsupported_mime: 'Выберите фото в формате JPEG, PNG или WebP.',
    invalid_image: 'Файл не похож на допустимое изображение. Выберите другое фото.',
    decode_failed: 'Фото не удалось прочитать. Переснимите блюдо.',
    oversized_image: 'Фото слишком большое. Выберите снимок меньшего размера.',
    retake_required: 'Нужен более чёткий снимок блюда крупным планом.',
    draft_expired: 'Черновик истёк. Начните распознавание заново.',
    draft_not_active: 'Черновик уже закрыт. Начните заново.',
    stale_draft_revision: 'Черновик устарел. Начните распознавание заново.',
    unknown_candidate: 'Состав блюда изменился. Начните распознавание заново.',
    future_diary_date: 'Нельзя добавить запись на будущую дату.',
  };
  if (code && messages[code]) return messages[code];
  if (error instanceof ApiError && error.status === 0) return error.message;
  if (error instanceof ApiError && error.status >= 500) {
    return 'Сервис временно недоступен. Можно добавить запись приблизительно.';
  }
  return 'Не удалось обработать фото. Попробуйте ещё раз или добавьте запись вручную.';
}

function randomRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `photo-meal-${crypto.randomUUID()}`;
  }
  return `photo-meal-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function editableCandidates(draft: PhotoMealDraft): EditableCandidate[] {
  return draft.candidates.map((candidate) => ({
    candidateId: candidate.candidate_id,
    name: candidate.name,
    portionAmount: candidate.portion_amount === null ? '' : String(candidate.portion_amount),
    portionUnit: candidate.portion_unit ?? '',
    portionConfidence: candidate.portion_confidence,
    identityConfidence: candidate.identity_confidence,
    nutritionConfidence: candidate.nutrition_confidence,
    uncertaintyCodes: candidate.uncertainty_codes ?? [],
    energyKcal: candidate.energy_kcal === null ? '' : String(candidate.energy_kcal),
    proteinG: candidate.protein_g === null ? '' : String(candidate.protein_g),
    fatG: candidate.fat_g === null ? '' : String(candidate.fat_g),
    carbsG: candidate.carbs_g === null ? '' : String(candidate.carbs_g),
  }));
}

function confidenceLabel(value: string): string {
  return (
    {
      high: 'выше',
      medium: 'средняя',
      low: 'низкая',
      unknown: 'неизвестна',
    }[value] ?? 'неизвестна'
  );
}

function uncertaintyLabel(code: string): string {
  return (
    {
      identity_uncertain: 'Название требует проверки',
      portion_uncertain: 'Порция приблизительная',
      nutrition_uncertain: 'Пищевая ценность приблизительная',
    }[code] ?? 'Проверьте оценку'
  );
}

function warningLabel(code: string): string {
  return (
    {
      identity_uncertain: 'Название одного или нескольких продуктов требует проверки.',
      portion_uncertain: 'Размер одной или нескольких порций приблизительный.',
      nutrition_uncertain: 'Пищевая ценность одной или нескольких позиций приблизительная.',
      unsupported_image: 'Фото распознано не полностью.',
      manual_review_required: 'Результат требует проверки перед добавлением.',
    }[code] ?? 'Результат требует проверки перед добавлением.'
  );
}

function parseRequired(value: string, label: string): number {
  const parsed = Number(value.replace(',', '.'));
  if (!Number.isFinite(parsed) || parsed <= 0) throw new Error(`Укажите ${label} больше нуля`);
  return parsed;
}

function parseOptional(value: string, label: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value.replace(',', '.'));
  if (!Number.isFinite(parsed) || parsed < 0)
    throw new Error(`${label} должно быть неотрицательным`);
  return parsed;
}

export function PhotoMealScanner({
  userId = 'anonymous',
  diaryDate,
  mealType,
  onCancel,
  onManualFallback,
  onCompleted,
}: PhotoMealScannerProps) {
  const [status, setStatus] = useState<CaptureStatus>('capture');
  const [file, setFile] = useState<File | null>(null);
  const [draft, setDraft] = useState<PhotoMealDraft | null>(null);
  const [items, setItems] = useState<EditableCandidate[]>([]);
  const [error, setError] = useState('');
  const [submitError, setSubmitError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const generationRef = useRef(0);
  const requestRef = useRef<string | null>(null);
  const previousUserIdRef = useRef(userId);

  useEffect(() => {
    if (previousUserIdRef.current === userId) return;
    previousUserIdRef.current = userId;
    generationRef.current += 1;
    requestRef.current = null;
    setStatus('capture');
    setFile(null);
    setDraft(null);
    setItems([]);
    setError('');
    setSubmitError('');
    setIsSubmitting(false);
  }, [userId]);

  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const chooseFile = (candidate: File) => {
    setError('');
    setSubmitError('');
    setDraft(null);
    setItems([]);
    if (!ALLOWED_IMAGE_TYPES.has(candidate.type)) {
      setFile(null);
      setStatus('capture');
      setError('Выберите фото в формате JPEG, PNG или WebP.');
      return;
    }
    if (candidate.size > MAX_IMAGE_BYTES) {
      setFile(null);
      setStatus('capture');
      setError('Фото слишком большое. Выберите снимок меньшего размера.');
      return;
    }
    setFile(candidate);
    setStatus('preview');
  };

  const recognize = async () => {
    if (!file || status === 'recognizing') return;
    const generation = generationRef.current;
    setStatus('recognizing');
    setError('');
    setSubmitError('');
    const requestId = requestRef.current ?? randomRequestId();
    requestRef.current = requestId;
    const form = new FormData();
    form.append('image', file, file.name || 'meal-photo');
    try {
      const response = await api<PhotoMealDraft>('/api/v1/nutrition/photo-meals', {
        method: 'POST',
        body: form,
        headers: { 'Idempotency-Key': requestId },
        timeoutMs: 20_000,
      });
      if (generation !== generationRef.current) return;
      setDraft(response);
      setItems(editableCandidates(response));
      setStatus('review');
    } catch (recognitionError) {
      if (generation !== generationRef.current) return;
      setStatus('preview');
      setError(errorMessage(recognitionError));
    }
  };

  const cancelDraft = () => {
    if (!draft || draft.status !== 'draft') return;
    void api<void>(
      `/api/v1/nutrition/photo-meals/${encodeURIComponent(draft.draft_id)}/cancel?revision=${draft.revision}`,
      { method: 'POST', timeoutMs: 8_000 },
    ).catch(() => undefined);
  };

  const handleCancel = () => {
    cancelDraft();
    onCancel();
  };

  const handleManualFallback = () => {
    cancelDraft();
    (onManualFallback ?? onCancel)();
  };

  const updateItem = (index: number, changes: Partial<EditableCandidate>) => {
    setItems((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...changes } : item)),
    );
    setSubmitError('');
  };

  const confirm = async () => {
    if (!draft || isSubmitting) return;
    try {
      const payload = items.map((item) => ({
        candidate_id: item.candidateId,
        name: item.name.trim(),
        portion_amount: item.portionAmount.trim()
          ? parseRequired(item.portionAmount, 'размер порции')
          : null,
        portion_unit: item.portionUnit || null,
        energy_kcal: parseRequired(item.energyKcal, 'калории'),
        protein_g: parseOptional(item.proteinG, 'Белки'),
        fat_g: parseOptional(item.fatG, 'Жиры'),
        carbs_g: parseOptional(item.carbsG, 'Углеводы'),
      }));
      if (payload.some((item) => !item.name)) throw new Error('Укажите название каждого продукта');
      if (payload.some((item) => (item.portion_amount === null) !== (item.portion_unit === null))) {
        throw new Error('Укажите и размер порции, и единицу измерения');
      }
      setIsSubmitting(true);
      setSubmitError('');
      const generation = generationRef.current;
      const response = await api<PhotoMealConfirmResponse>(
        `/api/v1/nutrition/photo-meals/${encodeURIComponent(draft.draft_id)}/confirm`,
        {
          method: 'POST',
          body: {
            revision: draft.revision,
            diary_date: diaryDate,
            meal_type: mealType,
            items: payload,
          },
          timeoutMs: 15_000,
        },
      );
      if (generation !== generationRef.current) return;
      await onCompleted(response);
    } catch (confirmationError) {
      setSubmitError(errorMessage(confirmationError));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (status === 'review' && draft) {
    return (
      <div
        className="nutrition-label-scanner photo-meal-scanner"
        aria-label="Проверка блюда по фото"
      >
        <div className="nutrition-label-scanner__intro">
          <span className="eyebrow">Черновик приёма пищи</span>
          <h3>Проверьте оценку блюда</h3>
          <p>
            Это приблизительное распознавание. Измените название, порцию и БЖУ. В дневник ничего не
            попадёт, пока вы явно не нажмёте подтверждение.
          </p>
        </div>
        <div className="nutrition-provider-fallback" role="status">
          <strong>Порции и калории не точны</strong>
          <span>Проверьте результат по упаковке или своему описанию блюда. Фото не хранится.</span>
        </div>
        {(draft.warnings ?? []).length > 0 && (
          <ul className="photo-meal-scanner__warnings" aria-label="Предупреждения распознавания">
            {(draft.warnings ?? []).map((warning) => (
              <li key={warning}>{warningLabel(warning)}</li>
            ))}
          </ul>
        )}
        <div className="photo-meal-scanner__candidates">
          {items.map((item, index) => (
            <article className="photo-meal-scanner__candidate" key={item.candidateId}>
              <div className="photo-meal-scanner__candidate-header">
                <strong>Продукт {index + 1}</strong>
                {item.uncertaintyCodes.length > 0 && (
                  <span className="photo-meal-scanner__uncertainty">
                    {item.uncertaintyCodes.map(uncertaintyLabel).join(' · ')}
                  </span>
                )}
              </div>
              <Field label="Название" labelFor={`photo-meal-${item.candidateId}-name`}>
                <Input
                  id={`photo-meal-${item.candidateId}-name`}
                  value={item.name}
                  onChange={(event) => updateItem(index, { name: event.target.value })}
                />
              </Field>
              <div className="nutrition-picker__amount-grid">
                <Field label="Порция" labelFor={`photo-meal-${item.candidateId}-amount`}>
                  <Input
                    id={`photo-meal-${item.candidateId}-amount`}
                    type="number"
                    inputMode="decimal"
                    min="0.001"
                    step="any"
                    value={item.portionAmount}
                    onChange={(event) => updateItem(index, { portionAmount: event.target.value })}
                  />
                </Field>
                <Field label="Единица" labelFor={`photo-meal-${item.candidateId}-unit`}>
                  <Select
                    id={`photo-meal-${item.candidateId}-unit`}
                    value={item.portionUnit}
                    onChange={(event) =>
                      updateItem(index, { portionUnit: event.target.value as PortionUnit | '' })
                    }
                  >
                    <option value="">Не указана</option>
                    <option value="g">граммы</option>
                    <option value="ml">миллилитры</option>
                    <option value="serving">порция</option>
                  </Select>
                </Field>
              </div>
              <p className="photo-meal-scanner__confidence">
                Название: {confidenceLabel(item.identityConfidence)} · порция:{' '}
                {confidenceLabel(item.portionConfidence)} · БЖУ:{' '}
                {confidenceLabel(item.nutritionConfidence)}
              </p>
              <div className="photo-meal-scanner__nutrients">
                <Field label="Ккал" labelFor={`photo-meal-${item.candidateId}-energy`}>
                  <Input
                    id={`photo-meal-${item.candidateId}-energy`}
                    type="number"
                    inputMode="decimal"
                    min="0.01"
                    step="any"
                    required
                    value={item.energyKcal}
                    onChange={(event) => updateItem(index, { energyKcal: event.target.value })}
                  />
                </Field>
                <Field label="Белки" labelFor={`photo-meal-${item.candidateId}-protein`}>
                  <Input
                    id={`photo-meal-${item.candidateId}-protein`}
                    type="number"
                    inputMode="decimal"
                    min="0"
                    step="any"
                    value={item.proteinG}
                    onChange={(event) => updateItem(index, { proteinG: event.target.value })}
                  />
                </Field>
                <Field label="Жиры" labelFor={`photo-meal-${item.candidateId}-fat`}>
                  <Input
                    id={`photo-meal-${item.candidateId}-fat`}
                    type="number"
                    inputMode="decimal"
                    min="0"
                    step="any"
                    value={item.fatG}
                    onChange={(event) => updateItem(index, { fatG: event.target.value })}
                  />
                </Field>
                <Field label="Углеводы" labelFor={`photo-meal-${item.candidateId}-carbs`}>
                  <Input
                    id={`photo-meal-${item.candidateId}-carbs`}
                    type="number"
                    inputMode="decimal"
                    min="0"
                    step="any"
                    value={item.carbsG}
                    onChange={(event) => updateItem(index, { carbsG: event.target.value })}
                  />
                </Field>
              </div>
            </article>
          ))}
        </div>
        {submitError && (
          <div className="nutrition-inline-error" role="alert">
            {submitError}
          </div>
        )}
        <div className="nutrition-editor__actions app-action-group nutrition-label-scanner__actions">
          <Button type="button" fullWidth disabled={isSubmitting} onClick={() => void confirm()}>
            {isSubmitting ? 'Добавляем…' : 'Подтвердить и добавить в дневник'}
          </Button>
          <Button
            type="button"
            variant="secondary"
            fullWidth
            disabled={isSubmitting}
            onClick={handleManualFallback}
          >
            Продолжить вручную
          </Button>
          <Button type="button" variant="ghost" disabled={isSubmitting} onClick={handleCancel}>
            Отмена
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="nutrition-label-scanner photo-meal-scanner"
      aria-label="Добавление блюда по фото"
    >
      <div className="nutrition-label-scanner__intro">
        <span className="eyebrow">Черновик приёма пищи</span>
        <h3>Сфотографировать блюдо</h3>
        <p>
          Выберите фото готового блюда. Мы покажем только приблизительные продукты, порции и БЖУ —
          вы проверите и измените их перед добавлением.
        </p>
      </div>
      <div className="nutrition-provider-fallback" role="note">
        <strong>Фото не сохраняется</strong>
        <span>
          Исходное изображение используется только для текущего анализа и не попадает в дневник.
        </span>
      </div>
      <div className="nutrition-label-scanner__picker">
        <span className="nutrition-label-scanner__picker-title">
          Сделайте снимок или выберите фото
        </span>
        <label className="nutrition-label-scanner__file-control">
          <span>Открыть камеру или галерею</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            onChange={(event) => {
              const selected = event.currentTarget.files?.[0];
              event.currentTarget.value = '';
              if (selected) chooseFile(selected);
            }}
          />
        </label>
      </div>
      {previewUrl && status === 'preview' && (
        <div className="nutrition-label-scanner__preview">
          <img src={previewUrl} alt="Предпросмотр фото блюда" />
          <div className="nutrition-label-scanner__preview-actions">
            <Button type="button" fullWidth onClick={() => void recognize()}>
              Распознать приблизительно
            </Button>
            <Button
              type="button"
              variant="secondary"
              fullWidth
              onClick={() => {
                setFile(null);
                setStatus('capture');
                setError('');
                requestRef.current = null;
              }}
            >
              Переснять
            </Button>
          </div>
        </div>
      )}
      {status === 'recognizing' && (
        <div className="nutrition-label-scanner__progress" role="status">
          <strong>Готовим черновик…</strong>
          <span>Проверяем фото и отделяем приблизительную оценку от подтверждённой записи.</span>
        </div>
      )}
      {error && (
        <div className="nutrition-provider-fallback" role="alert">
          <strong>Фото не распознано</strong>
          <span>{error}</span>
          {file && status !== 'recognizing' && (
            <Button type="button" variant="secondary" onClick={() => void recognize()}>
              Повторить
            </Button>
          )}
        </div>
      )}
      <div className="nutrition-editor__actions app-action-group nutrition-label-scanner__actions">
        <Button
          type="button"
          variant="secondary"
          disabled={status === 'recognizing'}
          onClick={handleManualFallback}
        >
          Добавить вручную
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={status === 'recognizing'}
          onClick={handleCancel}
        >
          Отмена
        </Button>
      </div>
    </div>
  );
}
