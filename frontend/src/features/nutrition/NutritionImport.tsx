import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  api,
  ApiError,
  AUTH_ACCOUNT_SWITCH_EVENT,
  AUTH_LOGOUT_EVENT,
} from '../../shared/api/client';
import { AUTHENTICATED_USER_ID_STORAGE_KEY } from '../../shared/auth/legacySessionKeys';
import { NUTRITION_IMPORT_RECOVERY_SESSION_KEY as recoveryKey } from '../../shared/userScopedStorage';
import { Button, Field, Input, Select, Surface } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import type { components } from '../../shared/api/schema';
import { useTelegramOverlayBackButton } from '../../shared/telegram/useTelegramOverlayBackButton';
import { RecurringMealSuggestions } from './RecurringMealSuggestions';
import './NutritionImport.css';

type ImportPreview = components['schemas']['ImportPreview'];
type CatalogPreview = components['schemas']['CatalogImportPreview'];
type Receipt = components['schemas']['CatalogImportReceipt'];
type Correction = {
  index: number;
  name: string;
  brand: string | null;
  kind: 'standard_food' | 'branded_food' | 'personal_recipe';
  nutrition: {
    source_basis: 'per_100_g' | 'per_100_ml' | 'per_serving';
    serving_size?: { amount: string; unit: 'g' | 'ml' };
    energy_kcal: string;
    protein_g: string;
    fat_g: string;
    carbohydrate_g: string;
  } | null;
  confirmed: true;
};
type Choice = { index: number; action: 'reuse' | 'skip'; food_id: number | null };
type Pending = {
  revision: number;
  preview_signature: string;
  confirm_key: string;
  row_indexes: number[];
  corrections: Correction[];
  choices: Choice[];
  confirmed: true;
};
type Recovery = { userId: string; draftId: string; expiresAt: number; payload: Pending };
function readRecovery(): Recovery | null {
  try {
    const value = sessionStorage.getItem(recoveryKey);
    if (!value) return null;
    if (value.length > 2_000_000) {
      sessionStorage.removeItem(recoveryKey);
      return null;
    }
    const item = JSON.parse(value) as Recovery;
    const userId = sessionStorage.getItem(AUTHENTICATED_USER_ID_STORAGE_KEY);
    if (
      !userId ||
      item.userId !== userId ||
      !Number.isSafeInteger(Number(userId)) ||
      Number(userId) <= 0 ||
      typeof item.draftId !== 'string' ||
      !/^[0-9a-f-]{36}$/.test(item.draftId) ||
      !Number.isFinite(item.expiresAt) ||
      !item.payload ||
      item.payload.confirmed !== true ||
      typeof item.payload.confirm_key !== 'string' ||
      !/^[A-Za-z0-9._:-]{8,128}$/.test(item.payload.confirm_key) ||
      typeof item.payload.preview_signature !== 'string' ||
      !/^[a-f0-9]{64}$/.test(item.payload.preview_signature) ||
      !Array.isArray(item.payload.row_indexes) ||
      !Array.isArray(item.payload.corrections) ||
      !Array.isArray(item.payload.choices)
    ) {
      sessionStorage.removeItem(recoveryKey);
      return null;
    }
    return item;
  } catch {
    try {
      sessionStorage.removeItem(recoveryKey);
    } catch {
      /* Storage is unavailable. */
    }
    return null;
  }
}
const root = '/api/v1/nutrition/imports';
const key = () => crypto.randomUUID();
const statusLabels: Record<string, string> = {
  reuse: 'Совпадение',
  publish: 'Можно добавить',
  conflict: 'Конфликт',
  needs_review: 'Проверить сведения',
  private_only: 'Только для личного использования',
  skipped: 'Пропущено',
};
const units: Record<string, string> = { g: 'г', mg: 'мг', kcal: 'ккал', kJ: 'кДж' };
const reasonLabels: Record<string, string> = {
  unclassified_food: 'Не определён тип продукта',
  publication_rights_unconfirmed: 'Право публикации не подтверждено',
  classification_unconfirmed: 'Тип продукта требует проверки',
  nutrition_basis_unknown: 'Не указана основа КБЖУ',
  incomplete_nutrition: 'Не хватает данных о КБЖУ',
  catalog_facts_or_identity_conflict: 'Данные отличаются от каталога',
  identity_points_to_different_foods: 'Найдено несколько разных совпадений',
  user_skipped: 'Исключено вами',
  user_selected_existing: 'Выбран существующий продукт',
  personal_or_arbitrary_food: 'Личные сведения не публикуются',
  inconsistent_nutrition: 'Проверьте значения КБЖУ',
  brand_required: 'Укажите бренд',
  invalid_source_row: 'Строка содержит ошибки',
};
const diagnosticLabels: Record<string, string> = {
  nutrient_unreadable: 'Не удалось прочитать значение КБЖУ.',
  source_context_ambiguous: 'Не удалось однозначно связать строку с исходными данными.',
  quantity_unrecognized: 'Не удалось определить количество.',
  unknown_unit: 'Единица количества не распознана.',
  possible_duplicate: 'Похожая строка встречается в файле повторно.',
  saturated_fat_mapping_unconfirmed: 'Столбец насыщенных жиров требует проверки.',
  potassium_not_in_catalog: 'Калий не добавляется в карточку продукта.',
  totals_not_comparable: 'Итоги отчёта нельзя автоматически сопоставить со строками.',
  meal_source_values_differ: 'Итог приёма пищи отличается от строк отчёта.',
  day_source_values_differ: 'Итог дня отличается от строк отчёта.',
  day_meal_totals_differ: 'Итог дня отличается от итогов приёмов пищи.',
};

function ConflictCandidate({
  foodId,
  onSelect,
  disabled,
}: {
  foodId: number;
  onSelect: () => void;
  disabled: boolean;
}) {
  const [food, setFood] = useState<components['schemas']['FoodResponse'] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    api<components['schemas']['FoodResponse']>(`/api/v1/nutrition/foods/${foodId}`)
      .then((value) => {
        if (active) setFood(value);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [foodId]);
  if (error)
    return <p role="alert">Не удалось загрузить совпадение. Попробуйте проверить строку позже.</p>;
  if (!food) return <p role="status">Загружаем продукт из каталога…</p>;
  return (
    <div>
      <p>
        В каталоге: {food.name}
        {food.brand ? ` · ${food.brand}` : ''}
      </p>
      {food.nutrition_basis_kind === 'per_100_g' && (
        <p>
          На 100 г: {food.energy_kcal_per_100g ?? 'не указано'} ккал · Б{' '}
          {food.protein_g_per_100g ?? 'не указано'} г · Ж {food.fat_g_per_100g ?? 'не указано'} г ·
          У {food.carbs_g_per_100g ?? 'не указано'} г
        </p>
      )}
      <Button type="button" variant="secondary" disabled={disabled} onClick={onSelect}>
        Использовать существующий продукт
      </Button>
    </div>
  );
}

export function NutritionImport({
  onClose,
  diaryDate,
}: {
  onClose: () => void;
  diaryDate: string;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [draft, setDraft] = useState<ImportPreview | null>(null);
  const [preview, setPreview] = useState<CatalogPreview | null>(null);
  const [corrections, setCorrections] = useState<Correction[]>([]);
  const [choices, setChoices] = useState<Choice[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [basis, setBasis] = useState('');
  const [filter, setFilter] = useState('all');
  const [confirming, setConfirming] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [receiptDraftId, setReceiptDraftId] = useState<string | null>(null);
  const [showRecurring, setShowRecurring] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [recovery, setRecovery] = useState<Recovery | null>(readRecovery);
  const [pending, setPending] = useState<Pending | null>(() => recovery?.payload ?? null);
  const controller = useRef<AbortController | null>(null);
  const uploadKey = useRef(key());

  useEffect(() => {
    const clear = () => {
      try {
        sessionStorage.removeItem(recoveryKey);
      } catch {
        /* Storage is unavailable. */
      }
      controller.current?.abort();
      setRecovery(null);
      setPending(null);
      setDraft(null);
      setPreview(null);
      setCorrections([]);
      setChoices([]);
      setReceipt(null);
      setReceiptDraftId(null);
      setShowRecurring(false);
      setFile(null);
      setEditing(null);
      setConfirming(false);
    };
    window.addEventListener(AUTH_LOGOUT_EVENT, clear);
    window.addEventListener(AUTH_ACCOUNT_SWITCH_EVENT, clear);
    return () => {
      window.removeEventListener(AUTH_LOGOUT_EVENT, clear);
      window.removeEventListener(AUTH_ACCOUNT_SWITCH_EVENT, clear);
    };
  }, []);

  async function upload() {
    if (!file) return;
    const pdf = file.name.toLowerCase().endsWith('.pdf');
    if (
      (!pdf && !file.name.toLowerCase().endsWith('.csv')) ||
      file.size === 0 ||
      file.size > (pdf ? 2 * 1024 * 1024 : 512 * 1024)
    ) {
      setError('Выберите непустой CSV до 512 КБ или PDF до 2 МБ.');
      return;
    }
    setBusy(true);
    setError('');
    controller.current = new AbortController();
    const body = new FormData();
    body.append('file', file);
    body.append('adapter_id', pdf ? 'fatsecret-pdf-v1' : 'fatsecret-csv-v1');
    try {
      const result = await api<ImportPreview>(root, {
        method: 'POST',
        body,
        headers: { 'Idempotency-Key': uploadKey.current },
        signal: controller.current.signal,
        timeoutMs: 60_000,
      });
      const catalog = await api<CatalogPreview>(`${root}/${result.id}/catalog`);
      setDraft(result);
      setPreview(catalog);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось проверить файл. Попробуйте снова.');
    } finally {
      setBusy(false);
      controller.current = null;
    }
  }

  async function review(nextCorrections: Correction[], nextChoices: Choice[]) {
    if (!draft) return;
    setBusy(true);
    setError('');
    try {
      const result = await api<CatalogPreview>(`${root}/${draft.id}/catalog/review`, {
        method: 'POST',
        body: { revision: draft.revision, corrections: nextCorrections, choices: nextChoices },
      });
      setCorrections(nextCorrections);
      setChoices(nextChoices);
      setPreview(result);
      setEditing(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось обновить проверку.');
    } finally {
      setBusy(false);
    }
  }

  async function submit(payload: Pending) {
    const draftId = draft?.id ?? recovery?.draftId;
    if (!draftId) return;
    if (recovery && recovery.expiresAt <= Date.now()) {
      setError(
        'Срок хранения черновика истёк. Результат неизвестен; проверьте каталог перед новым импортом.',
      );
      return;
    }
    setPending(payload);
    let savedForRetry = Boolean(recovery);
    if (draft) {
      try {
        const userId = sessionStorage.getItem(AUTHENTICATED_USER_ID_STORAGE_KEY);
        if (userId && Number.isSafeInteger(Number(userId)) && Number(userId) > 0) {
          const saved = { userId, draftId, expiresAt: Date.parse(draft.expires_at), payload };
          sessionStorage.setItem(recoveryKey, JSON.stringify(saved));
          setRecovery(saved);
          savedForRetry = true;
        }
      } catch {
        /* Retry remains available while this screen is open. */
      }
    }
    setBusy(true);
    setError('');
    try {
      setReceipt(
        await api<Receipt>(`${root}/${draftId}/catalog/confirm`, {
          method: 'POST',
          body: payload,
          timeoutMs: 60_000,
        }),
      );
      setReceiptDraftId(draftId);
      setPending(null);
      setRecovery(null);
      try {
        sessionStorage.removeItem(recoveryKey);
      } catch {
        /* Storage is unavailable. */
      }
    } catch (e) {
      if (
        !pending &&
        e instanceof ApiError &&
        e.status >= 400 &&
        e.status < 500 &&
        e.status !== 408 &&
        e.status !== 429
      ) {
        setPending(null);
        setRecovery(null);
        try {
          sessionStorage.removeItem(recoveryKey);
        } catch {
          /* Storage is unavailable. */
        }
        setConfirming(false);
        setError(e.message);
      } else {
        setError(
          savedForRetry
            ? 'Ответ не получен. Проверьте результат прежнего подтверждения.'
            : 'Ответ не получен. Не закрывайте экран и проверьте результат прежнего подтверждения.',
        );
      }
    } finally {
      setBusy(false);
    }
  }

  function saveCorrection(event: FormEvent<HTMLFormElement>, index: number) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const value = (name: string) =>
      String(fields.get(name) ?? '')
        .trim()
        .replace(',', '.');
    const next: Correction = {
      index,
      name: String(fields.get('name') ?? '').trim(),
      brand: String(fields.get('brand') ?? '').trim() || null,
      kind: fields.get('kind') === 'branded_food' ? 'branded_food' : 'standard_food',
      nutrition: {
        source_basis:
          fields.get('basis') === 'per_100_ml'
            ? 'per_100_ml'
            : fields.get('basis') === 'per_serving'
              ? 'per_serving'
              : 'per_100_g',
        ...(fields.get('basis') === 'per_serving'
          ? {
              serving_size: {
                amount: value('serving'),
                unit: fields.get('serving-unit') === 'ml' ? 'ml' : 'g',
              },
            }
          : {}),
        energy_kcal: value('energy'),
        protein_g: value('protein'),
        fat_g: value('fat'),
        carbohydrate_g: value('carbs'),
      },
      confirmed: true,
    };
    void review(
      [...corrections.filter((item) => item.index !== index), next],
      choices.filter((item) => item.index !== index),
    );
  }

  async function cancel() {
    if (busy) {
      controller.current?.abort();
      return;
    }
    if (pending) {
      if (recovery && recovery.expiresAt <= Date.now()) {
        onClose();
        return;
      }
      setError('Сначала проверьте результат отправленного подтверждения.');
      return;
    }
    if (draft && !receipt) {
      try {
        await api(`${root}/${draft.id}/cancel`, {
          method: 'POST',
          body: { revision: draft.revision },
        });
      } catch {
        setError('Не удалось отменить черновик. Попробуйте ещё раз.');
        return;
      }
    }
    onClose();
  }

  useTelegramOverlayBackButton(!showRecurring, () => {
    void cancel();
  });

  const selectable =
    preview?.rows.filter((row) => row.outcome === 'publish' || row.outcome === 'reuse') ?? [];
  const rowsByIndex = new Map(preview?.rows.map((row) => [row.index, row]));
  if (showRecurring && receiptDraftId) {
    return (
      <RecurringMealSuggestions
        draftId={receiptDraftId}
        diaryDate={diaryDate}
        onBack={() => setShowRecurring(false)}
        onClose={onClose}
      />
    );
  }
  return (
    <div className="nutrition-import stack">
      <Button
        className="nutrition-import__back"
        type="button"
        variant="ghost"
        onClick={() => void cancel()}
      >
        <Icon name="chevron-left" size={16} /> Питание
      </Button>
      <header>
        <h1>Импорт питания</h1>
        <p>Загрузите экспорт FatSecret и проверьте продукты перед добавлением в общий каталог.</p>
      </header>
      <ol className="nutrition-import__steps" aria-label="Этапы импорта">
        {['Источник', 'Проверка', 'Подтверждение'].map((label, index) => (
          <li
            key={label}
            aria-current={
              (receipt || confirming ? 2 : draft ? 1 : 0) === index ? 'step' : undefined
            }
          >
            <span>{index + 1}</span>
            {label}
          </li>
        ))}
      </ol>
      <div className="nutrition-import__layout">
        <div className="stack">
          {error && <p role="alert">{error}</p>}
          {busy && <p role="status">Проверяем данные…</p>}
          {!draft && recovery && !receipt && (
            <Surface className="stack">
              <h2>Проверить результат импорта</h2>
              <p>Ответ на подтверждение не получен. Повторите проверку прежнего запроса.</p>
              <Button
                type="button"
                disabled={busy || !pending}
                onClick={() => {
                  if (pending) void submit(pending);
                }}
              >
                Проверить результат
              </Button>
            </Surface>
          )}
          {!draft && !recovery && !receipt && (
            <Surface className="stack">
              <h2>Источник данных</h2>
              <p>CSV до 512 КБ или текстовый PDF до 2 МБ.</p>
              <div className="nutrition-import__drop">
                <Icon name="arrow-up" size={24} />
                <strong>Выберите файл на устройстве</strong>
                <span>Поддерживаемые форматы: CSV и PDF</span>
                <Input
                  id="nutrition-import-file"
                  className="nutrition-import__file"
                  type="file"
                  accept=".csv,.pdf"
                  aria-label="Файл на устройстве"
                  onChange={(e) => {
                    setFile(e.target.files?.[0] ?? null);
                    uploadKey.current = key();
                  }}
                />
                <label className="ui-button ui-button--secondary" htmlFor="nutrition-import-file">
                  Выбрать файл
                </label>
                {file && <span>{file.name}</span>}
              </div>
              <Button type="button" disabled={!file || busy} onClick={() => void upload()}>
                Проверить файл
              </Button>
              {busy && (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => controller.current?.abort()}
                >
                  Отменить загрузку
                </Button>
              )}
              <p>До подтверждения продукты не добавляются. История питания не переносится.</p>
            </Surface>
          )}
          {draft && preview && !receipt && !confirming && (
            <Surface className="stack">
              <h2>
                {editing === null
                  ? `Предпросмотр: ${draft.rows.length} строк`
                  : 'Проверка продукта'}
              </h2>
              {editing === null && (
                <div className="nutrition-import__summary">
                  {(
                    [
                      'publish',
                      'reuse',
                      'conflict',
                      'needs_review',
                      'private_only',
                      'skipped',
                    ] as const
                  ).map((status) => (
                    <div key={status}>
                      <strong>{preview.rows.filter((row) => row.outcome === status).length}</strong>
                      <span>{statusLabels[status]}</span>
                    </div>
                  ))}
                </div>
              )}
              {editing === null && (
                <Field label="Показать" labelFor="nutrition-import-filter">
                  <Select
                    id="nutrition-import-filter"
                    value={filter}
                    onChange={(event) => setFilter(event.target.value)}
                  >
                    <option value="all">Все строки</option>
                    {Object.entries(statusLabels).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {draft.diagnostics.map((diagnostic, index) => (
                <p key={`${diagnostic.code}-${index}`}>
                  {diagnosticLabels[diagnostic.code] ??
                    'Не удалось однозначно обработать часть данных файла.'}
                </p>
              ))}
              {draft.rows.map((row) => {
                const item = rowsByIndex.get(row.index);
                if (!item) return null;
                if (editing !== null && editing !== row.index) return null;
                if (editing === null && filter !== 'all' && filter !== item.outcome) return null;
                const original = draft.original_totals.find(
                  (total) =>
                    total.coordinates.section === row.source.coordinates.section &&
                    total.coordinates.row === row.source.coordinates.row &&
                    total.coordinates.page === row.source.coordinates.page,
                );
                const correction = corrections.find((candidate) => candidate.index === row.index);
                return (
                  <section key={row.index} className="stack">
                    <h3>{row.source.food.name}</h3>
                    <p>
                      {statusLabels[item.outcome]}
                      {item.reason
                        ? ` · ${reasonLabels[item.reason] ?? 'Проверьте сведения о продукте'}`
                        : ''}
                    </p>
                    <p>Порция: {row.source.serving_label ?? 'не указана'}</p>
                    {item.outcome === 'private_only' && (
                      <p>Личные продукты в этом сценарии не сохраняются и не публикуются.</p>
                    )}
                    {original && (
                      <p>
                        Данные отчёта (основа не подтверждена):{' '}
                        {(
                          [
                            ['Калории', original.facts.energy_kcal],
                            ['Белки', original.facts.protein_g],
                            ['Жиры', original.facts.fat_g],
                            ['Углеводы', original.facts.carbohydrate_g],
                          ] as const
                        )
                          .map(
                            ([label, fact]) =>
                              `${label}: ${fact?.value ?? 'не указано'}${fact?.value != null && fact.unit ? ` ${units[fact.unit] ?? fact.unit}` : ''}`,
                          )
                          .join(' · ')}
                      </p>
                    )}
                    {correction?.nutrition && (
                      <p>
                        Проверенные значения{' '}
                        {correction.nutrition.source_basis === 'per_100_g'
                          ? 'на 100 г'
                          : correction.nutrition.source_basis === 'per_100_ml'
                            ? 'на 100 мл'
                            : correction.nutrition.serving_size
                              ? `на порцию ${correction.nutrition.serving_size.amount} ${correction.nutrition.serving_size.unit === 'ml' ? 'мл' : 'г'}`
                              : 'на порцию с неизвестной массой'}
                        : {correction.nutrition.energy_kcal} ккал · Б{' '}
                        {correction.nutrition.protein_g} г · Ж {correction.nutrition.fat_g} г · У{' '}
                        {correction.nutrition.carbohydrate_g} г
                      </p>
                    )}
                    {(row.source.diagnostics ?? []).map((diagnostic, index) => (
                      <p key={`${diagnostic.code}-${index}`}>
                        {diagnosticLabels[diagnostic.code] ??
                          'Сверьте сведения в строке с источником.'}
                      </p>
                    ))}
                    {editing === row.index ? (
                      <form
                        className="stack"
                        onSubmit={(event) => saveCorrection(event, row.index)}
                      >
                        <Field label="Название продукта" labelFor={`name-${row.index}`}>
                          <Input
                            id={`name-${row.index}`}
                            name="name"
                            required
                            defaultValue={correction?.name ?? row.source.food.name}
                          />
                        </Field>
                        <Field label="Категория" labelFor={`kind-${row.index}`}>
                          <Select
                            id={`kind-${row.index}`}
                            name="kind"
                            required
                            defaultValue={
                              correction?.kind === 'personal_recipe' ? '' : (correction?.kind ?? '')
                            }
                          >
                            <option value="" disabled>
                              Выберите категорию
                            </option>
                            <option value="standard_food">Обычный продукт</option>
                            <option value="branded_food">Продукт с брендом</option>
                          </Select>
                        </Field>
                        <Field label="Бренд, если указан" labelFor={`brand-${row.index}`}>
                          <Input
                            id={`brand-${row.index}`}
                            name="brand"
                            defaultValue={correction?.brand ?? ''}
                          />
                        </Field>
                        <Field label="Значения указаны" labelFor={`basis-${row.index}`}>
                          <Select
                            id={`basis-${row.index}`}
                            name="basis"
                            required
                            value={basis}
                            onChange={(event) => setBasis(event.target.value)}
                          >
                            <option value="" disabled>
                              Выберите основу значений
                            </option>
                            <option value="per_100_g">На 100 г</option>
                            <option value="per_100_ml">На 100 мл</option>
                            <option value="per_serving">На порцию</option>
                          </Select>
                        </Field>
                        {basis === 'per_serving' && (
                          <>
                            <Field
                              label="Масса или объём порции, если указаны значения на порцию"
                              labelFor={`serving-${row.index}`}
                            >
                              <Input
                                id={`serving-${row.index}`}
                                name="serving"
                                inputMode="decimal"
                                required
                                defaultValue={correction?.nutrition?.serving_size?.amount ?? ''}
                              />
                            </Field>
                            <Field label="Единица порции" labelFor={`serving-unit-${row.index}`}>
                              <Select
                                id={`serving-unit-${row.index}`}
                                name="serving-unit"
                                required
                                defaultValue={correction?.nutrition?.serving_size?.unit ?? ''}
                              >
                                <option value="" disabled>
                                  Выберите единицу
                                </option>
                                <option value="g">г</option>
                                <option value="ml">мл</option>
                              </Select>
                            </Field>
                          </>
                        )}
                        {(
                          [
                            ['energy', 'Калории, ккал'],
                            ['protein', 'Белки, г'],
                            ['fat', 'Жиры, г'],
                            ['carbs', 'Углеводы, г'],
                          ] as const
                        ).map(([name, label]) => (
                          <Field key={name} label={label} labelFor={`${name}-${row.index}`}>
                            <Input
                              id={`${name}-${row.index}`}
                              name={name}
                              inputMode="decimal"
                              required
                              defaultValue={
                                correction?.nutrition?.[
                                  name === 'energy'
                                    ? 'energy_kcal'
                                    : name === 'protein'
                                      ? 'protein_g'
                                      : name === 'fat'
                                        ? 'fat_g'
                                        : 'carbohydrate_g'
                                ] ?? ''
                              }
                            />
                          </Field>
                        ))}
                        <p>
                          Укажите только проверенные сведения о продукте. Значения в отчёте могут
                          относиться к съеденной порции.
                        </p>
                        <label className="nutrition-import__consent">
                          <input type="checkbox" required />
                          <span>
                            Я проверил тип продукта, основу и значения КБЖУ. Данные не содержат
                            личных сведений.
                          </span>
                        </label>
                        <Button type="submit" disabled={busy}>
                          Проверить продукт
                        </Button>
                        <Button type="button" variant="secondary" onClick={() => setEditing(null)}>
                          Назад
                        </Button>
                      </form>
                    ) : (
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={busy}
                        onClick={() => {
                          setBasis(correction?.nutrition?.source_basis ?? '');
                          setEditing(row.index);
                        }}
                      >
                        Разобрать
                      </Button>
                    )}
                    {editing === row.index && item.outcome === 'conflict' && item.food_id && (
                      <ConflictCandidate
                        foodId={item.food_id}
                        disabled={busy}
                        onSelect={() =>
                          void review(corrections, [
                            ...choices.filter((choice) => choice.index !== row.index),
                            { index: row.index, action: 'reuse', food_id: item.food_id },
                          ])
                        }
                      />
                    )}
                    {editing === row.index &&
                      item.suggestions.map((candidate) => (
                        <ConflictCandidate
                          key={candidate.food_id}
                          foodId={candidate.food_id}
                          disabled={busy}
                          onSelect={() =>
                            void review(corrections, [
                              ...choices.filter((choice) => choice.index !== row.index),
                              { index: row.index, action: 'reuse', food_id: candidate.food_id },
                            ])
                          }
                        />
                      ))}
                    {editing === row.index && item.outcome !== 'private_only' && (
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={busy}
                        onClick={() =>
                          void review(
                            [
                              ...corrections.filter((candidate) => candidate.index !== row.index),
                              {
                                index: row.index,
                                name: row.source.food.name,
                                brand: null,
                                kind: 'personal_recipe',
                                nutrition: null,
                                confirmed: true,
                              },
                            ],
                            choices.filter((candidate) => candidate.index !== row.index),
                          )
                        }
                      >
                        Не публиковать личный продукт
                      </Button>
                    )}
                    {editing === row.index && item.outcome !== 'skipped' && (
                      <Button
                        type="button"
                        variant="ghost"
                        disabled={busy}
                        onClick={() =>
                          void review(corrections, [
                            ...choices.filter((choice) => choice.index !== row.index),
                            { index: row.index, action: 'skip', food_id: null },
                          ])
                        }
                      >
                        Пропустить
                      </Button>
                    )}
                    {editing === row.index && item.outcome === 'skipped' && (
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={busy}
                        onClick={() =>
                          void review(
                            corrections,
                            choices.filter((choice) => choice.index !== row.index),
                          )
                        }
                      >
                        Вернуть на проверку
                      </Button>
                    )}
                  </section>
                );
              })}
              {editing === null && (
                <Button
                  type="button"
                  disabled={busy || draft.rows.length === 0}
                  onClick={() => setConfirming(true)}
                >
                  Продолжить
                </Button>
              )}
            </Surface>
          )}
          {draft && preview && confirming && !receipt && (
            <Surface className="stack">
              <h2>Что произойдёт</h2>
              <p>
                Подходящие продукты станут доступны всем пользователям. Совпадения будут
                использованы повторно.
              </p>
              <p>Выбрано строк: {selectable.length}. Личная история питания не переносится.</p>
              {pending ? (
                <Button type="button" disabled={busy} onClick={() => void submit(pending)}>
                  Проверить результат
                </Button>
              ) : (
                <>
                  <Button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void submit({
                        revision: draft.revision,
                        preview_signature: preview.preview_signature,
                        confirm_key: key(),
                        row_indexes: selectable.map((row) => row.index),
                        corrections,
                        choices,
                        confirmed: true,
                      })
                    }
                  >
                    Подтвердить импорт
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={busy}
                    onClick={() => setConfirming(false)}
                  >
                    Назад к проверке
                  </Button>
                </>
              )}
            </Surface>
          )}
          {receipt && (
            <Surface className="stack">
              <h2>Результат импорта</h2>
              <p>Добавлено: {receipt.rows.filter((row) => row.outcome === 'publish').length}</p>
              <p>
                Использовано повторно:{' '}
                {receipt.rows.filter((row) => row.outcome === 'reuse').length}
              </p>
              <p>
                Отложено на проверку:{' '}
                {
                  (receipt.excluded_rows ?? []).filter(
                    (row) => row.outcome === 'needs_review' || row.outcome === 'conflict',
                  ).length
                }
              </p>
              <p>
                Пропущено:{' '}
                {(receipt.excluded_rows ?? []).filter((row) => row.outcome === 'skipped').length}
              </p>
              {(receipt.excluded_rows ?? []).map((row) => (
                <p key={row.index}>
                  Строка {row.index + 1}: {statusLabels[row.outcome]}
                  {row.reason
                    ? ` · ${reasonLabels[row.reason] ?? 'Проверьте сведения о продукте'}`
                    : ''}
                </p>
              ))}
              {receiptDraftId && (
                <div className="stack">
                  <h3>Повторяющиеся приёмы пищи</h3>
                  <p>Проверьте привычные сочетания и сохраните подходящие как шаблоны.</p>
                  <Button type="button" variant="secondary" onClick={() => setShowRecurring(true)}>
                    Посмотреть предложения
                  </Button>
                </div>
              )}
              <Button type="button" onClick={onClose}>
                К питанию
              </Button>
            </Surface>
          )}
        </div>
        <Surface className="nutrition-import__aside stack" subtle>
          <h2>Сначала проверка</h2>
          <p>Посмотрите продукты и совпадения, затем подтвердите добавление пригодных продуктов.</p>
          <p>Личная история питания в этом сценарии не переносится.</p>
        </Surface>
      </div>
    </div>
  );
}
