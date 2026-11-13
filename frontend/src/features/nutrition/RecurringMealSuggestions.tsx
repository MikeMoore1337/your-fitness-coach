import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import type { components } from '../../shared/api/schema';
import { queryKeys } from '../../shared/queryKeys';
import { useTelegramOverlayBackButton } from '../../shared/telegram/useTelegramOverlayBackButton';
import { Button, Field, Input, Select, Surface } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { MealTemplateBrowser } from './MealTemplateBrowser';
import './RecurringMealSuggestions.css';

type Schemas = components['schemas'];
type Proposal = Schemas['RecurringImportMeal'];
type Choice = Schemas['RecurringMealChoice-Input'];
type Request = Schemas['RecurringMealReviewRequest'];
type Review = Schemas['RecurringMealReview'];
type Receipt = Schemas['RecurringMealReceipt'];
type Row = {
  sourceIndex: number | null;
  foodId: number;
  name: string;
  amount: string;
  unit: '' | Choice['amount_unit'];
};

const meals: Record<Proposal['meal_type'], string> = {
  breakfast: 'Завтрак',
  lunch: 'Обед',
  dinner: 'Ужин',
  snacks: 'Перекус',
};
const nutrients = [
  ['energy_kcal', 'Калории', 'ккал'],
  ['protein_g', 'Белки', 'г'],
  ['fat_g', 'Жиры', 'г'],
  ['carbohydrate_g', 'Углеводы', 'г'],
] as const;
const statuses = { equal: 'Совпадает', different: 'Расходится', unknown: 'Нельзя сопоставить' };
const sourceUnits: Record<string, string> = { g: 'г', ml: 'мл', serving: 'порц.', piece: 'шт.' };

function rowsFor(occurrence: Proposal['occurrences'][number]): Row[] {
  return occurrence.items.map(({ source, source_index, food_id }) => ({
    sourceIndex: source_index,
    foodId: food_id,
    name: [source.food.name, source.food.brand].filter(Boolean).join(' · '),
    amount: source.amount_unit === 'piece' ? '' : (source.quantity ?? ''),
    unit:
      source.amount_unit === 'g' || source.amount_unit === 'ml' || source.amount_unit === 'serving'
        ? source.amount_unit
        : '',
  }));
}

export function RecurringMealSuggestions({
  draftId,
  diaryDate,
  onBack,
  onClose,
}: {
  draftId: string;
  diaryDate: string;
  onBack: () => void;
  onClose: () => void;
}) {
  const root = `/api/v1/nutrition/imports/${draftId}/recurring-meals`;
  const queryClient = useQueryClient();
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [date, setDate] = useState('');
  const [name, setName] = useState('');
  const [rows, setRows] = useState<Row[]>([]);
  const [search, setSearch] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [review, setReview] = useState<Review | null>(null);
  const [reviewed, setReviewed] = useState<Request | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [openTemplate, setOpenTemplate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState('');
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  const suggestions = useQuery({
    queryKey: ['nutrition', 'recurring-meals', draftId],
    queryFn: ({ signal }) => api<Schemas['RecurringImportMeals']>(root, { signal }),
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: 'always',
  });
  const foods = useQuery({
    queryKey: ['nutrition', 'recurring-meal-search', searchQuery],
    queryFn: ({ signal }) =>
      api<Schemas['FoodSearchResponse']>(
        `/api/v1/nutrition/foods/search?q=${encodeURIComponent(searchQuery)}&limit=8`,
        { signal },
      ),
    enabled: searchQuery.length >= 2,
  });

  function back() {
    if (busy || uncertain) return;
    setError('');
    if (openTemplate) setOpenTemplate(false);
    else if (receipt) {
      setReceipt(null);
      setProposal(null);
      setReview(null);
    } else if (review) {
      setReview(null);
      setAcknowledged(false);
    } else if (proposal) setProposal(null);
    else onBack();
  }
  useTelegramOverlayBackButton(true, back);

  function selectOccurrence(item: Proposal, selectedDate: string) {
    const occurrence = item.occurrences.find((entry) => entry.date === selectedDate);
    if (!occurrence) return;
    setDate(selectedDate);
    setRows(rowsFor(occurrence));
    setReview(null);
    setAcknowledged(false);
    setError('');
  }
  function selectProposal(item: Proposal) {
    if (!item.occurrences[0]) return;
    setProposal(item);
    setName(meals[item.meal_type]);
    selectOccurrence(item, item.occurrences[0].date);
  }
  async function check() {
    if (!proposal || busy) return;
    const valid =
      rows.length > 0 &&
      rows.some((row) => row.sourceIndex !== null) &&
      rows.every(
        (row) =>
          row.unit &&
          /^(?:\d+)(?:[.,]\d{1,3})?$/.test(row.amount.trim()) &&
          Number(row.amount.replace(',', '.')) > 0,
      );
    if (!name.trim() || !valid) {
      setError(
        'Укажите название, положительное количество и единицу для каждого продукта. Оставьте хотя бы один продукт из предложения.',
      );
      return;
    }
    const payload: Request = {
      meal_type: proposal.meal_type,
      date,
      name: name.trim(),
      items: rows.map((row) => ({
        source_index: row.sourceIndex,
        food_id: row.foodId,
        amount: row.amount.trim().replace(',', '.'),
        amount_unit: row.unit as Choice['amount_unit'],
      })),
    };
    setBusy(true);
    setError('');
    try {
      const result = await api<Review>(`${root}/review`, { method: 'POST', body: payload });
      if (!active.current) return;
      setReviewed(payload);
      setReview(result);
      setAcknowledged(false);
    } catch (err) {
      if (active.current)
        setError(
          err instanceof ApiError && err.status === 410
            ? 'Срок хранения импорта истёк. Загрузите файл снова.'
            : 'Не удалось проверить состав. Проверьте данные и повторите попытку.',
        );
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function confirm() {
    if (!review || !reviewed || busy || (!acknowledged && !uncertain)) return;
    setBusy(true);
    setError('');
    try {
      const result = await api<Receipt>(`${root}/confirm`, {
        method: 'POST',
        body: {
          ...reviewed,
          preview_signature: review.preview_signature,
          confirmed: true,
          acknowledge_nutrition: true,
        },
      });
      if (!active.current) return;
      setReceipt(result);
      setUncertain(false);
      await queryClient.invalidateQueries({ queryKey: queryKeys.nutrition.mealTemplates });
    } catch (err) {
      if (!active.current) return;
      if (
        err instanceof ApiError &&
        err.status >= 400 &&
        err.status < 500 &&
        err.status !== 408 &&
        err.status !== 429
      ) {
        setUncertain(false);
        setError(
          err.status === 409
            ? 'Данные изменились. Вернитесь к составу и проверьте сравнение ещё раз.'
            : err.status === 410
              ? 'Срок хранения импорта истёк. Загрузите файл снова.'
              : 'Не удалось сохранить шаблон. Проверьте состав и попробуйте снова.',
        );
      } else {
        setUncertain(true);
        setError(
          'Ответ не получен. Проверьте результат повторной отправкой этого же подтверждения.',
        );
      }
    } finally {
      if (active.current) setBusy(false);
    }
  }

  return (
    <div className="recurring-meals stack">
      <Button type="button" variant="ghost" disabled={busy || uncertain} onClick={back}>
        <Icon name="chevron-left" size={16} /> {proposal ? 'Назад' : 'Импорт питания'}
      </Button>
      <header>
        <h1>Повторяющиеся приёмы пищи</h1>
        <p>
          Выберите сочетание из файла и сохраните его как шаблон. Дневник питания при этом не
          изменится.
        </p>
      </header>
      <div className="recurring-meals__layout">
        <Surface className="recurring-meals__main stack">
          {error && (
            <p className="nutrition-form-error" role="alert">
              {error}
            </p>
          )}
          {openTemplate && receipt && proposal ? (
            <Surface>
              <MealTemplateBrowser
                diaryDate={diaryDate}
                mealType={proposal.meal_type}
                mealEntries={[]}
                initialTemplateId={receipt.template.id}
                onCompleted={onClose}
                onCancel={onClose}
              />
            </Surface>
          ) : receipt ? (
            <Surface className="stack">
              <h2>{receipt.existing ? 'Такой шаблон уже сохранён' : 'Шаблон сохранён'}</h2>
              <p>
                «{receipt.template.name}» доступен в ваших шаблонах. В дневник ничего не добавлено.
              </p>
              <Button type="button" onClick={() => setOpenTemplate(true)}>
                Открыть шаблон
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setReceipt(null);
                  setReview(null);
                  setProposal(null);
                }}
              >
                К предложениям
              </Button>
            </Surface>
          ) : review && reviewed ? (
            <div className="stack">
              <header>
                <p>Шаг 2 из 2</p>
                <h2>Проверьте КБЖУ</h2>
                <p>Сравните данные файла с расчётом каталога для выбранных порций.</p>
              </header>
              {review.items.some((item) =>
                Object.values(item.comparison).some((status) => status !== 'equal'),
              ) && (
                <Surface subtle>
                  Есть расхождения или данные, которые нельзя сопоставить. Проверьте каждую строку
                  перед сохранением.
                </Surface>
              )}
              {review.items.map((item, index) => (
                <Surface className="stack recurring-meals__comparison" key={index}>
                  <div className="recurring-meals__item-heading">
                    <h3>
                      {rows[index]?.name ?? 'Продукт'} · {item.item.amount}{' '}
                      {item.item.amount_unit === 'g'
                        ? 'г'
                        : item.item.amount_unit === 'ml'
                          ? 'мл'
                          : 'порц.'}
                    </h3>
                    <span>
                      {
                        statuses[
                          Object.values(item.comparison).includes('different')
                            ? 'different'
                            : Object.values(item.comparison).includes('unknown')
                              ? 'unknown'
                              : 'equal'
                        ]
                      }
                    </span>
                  </div>
                  <div className="recurring-meals__table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th scope="col">Показатель</th>
                          <th scope="col">В файле</th>
                          <th scope="col">В каталоге</th>
                        </tr>
                      </thead>
                      <tbody>
                        {nutrients.map(([key, label, unit]) => {
                          const fact = item.source?.original_total?.facts[key];
                          const comparison = item.comparison[key] ?? 'unknown';
                          return (
                            <tr key={key}>
                              <th scope="row">{label}</th>
                              <td>
                                {fact?.value != null
                                  ? `${fact.value} ${fact.unit === 'kcal' ? 'ккал' : fact.unit === 'kJ' ? 'кДж' : fact.unit === 'mg' ? 'мг' : fact.unit === 'g' ? 'г' : unit}`
                                  : '—'}
                              </td>
                              <td>
                                {item.catalog_nutrition[key] != null
                                  ? `${item.catalog_nutrition[key]} ${unit}`
                                  : '—'}
                                <span className="recurring-meals__comparison-status">
                                  {statuses[comparison]}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  {Object.values(item.comparison).includes('unknown') && (
                    <p>
                      Не установлено, относятся ли значения из файла к этой строке и порции. Прочерк
                      означает отсутствие данных.
                    </p>
                  )}
                </Surface>
              ))}
              <Surface className="stack">
                <h2>Перед сохранением</h2>
                <p>
                  Шаблон использует КБЖУ из каталога. Исходные значения файла в шаблоне не
                  сохраняются. Запись в дневнике не создаётся.
                </p>
                <label className="recurring-meals__ack">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    disabled={uncertain || busy}
                    onChange={(event) => setAcknowledged(event.target.checked)}
                  />{' '}
                  Я проверил данные и согласен сохранить шаблон с КБЖУ из каталога
                </label>
                <Button
                  type="button"
                  disabled={busy || (!acknowledged && !uncertain)}
                  onClick={() => void confirm()}
                >
                  {busy ? 'Сохраняем…' : uncertain ? 'Проверить результат' : 'Сохранить шаблон'}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={busy || uncertain}
                  onClick={() => {
                    setReview(null);
                    setAcknowledged(false);
                  }}
                >
                  Изменить состав
                </Button>
              </Surface>
            </div>
          ) : proposal ? (
            <div className="stack">
              <header>
                <p>Шаг 1 из 2</p>
                <h2>Проверьте состав</h2>
                <p>Выберите день, уточните порции и название шаблона.</p>
              </header>
              <Surface className="stack">
                <fieldset className="recurring-meals__days">
                  <legend>На основе какого дня?</legend>
                  {proposal.occurrences.map((occurrence) => (
                    <label key={occurrence.date} data-yfc-choice="compact">
                      <input
                        type="radio"
                        name="occurrence"
                        checked={date === occurrence.date}
                        onChange={() => selectOccurrence(proposal, occurrence.date)}
                      />
                      {new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' }).format(
                        new Date(`${occurrence.date}T12:00:00`),
                      )}
                    </label>
                  ))}
                </fieldset>
                <Field label="Название шаблона" labelFor="recurring-name">
                  <Input
                    id="recurring-name"
                    value={name}
                    maxLength={120}
                    onChange={(event) => setName(event.target.value)}
                  />
                </Field>
                <h2>Состав и порции</h2>
                {rows.map((row, index) => (
                  <div
                    className="recurring-meals__row"
                    key={`${row.sourceIndex ?? 'added'}-${index}`}
                  >
                    <div className="recurring-meals__row-heading">
                      <strong>{row.name}</strong>
                      <Button
                        type="button"
                        variant="secondary"
                        aria-label={`Удалить ${row.name}`}
                        onClick={() => setRows(rows.filter((_, i) => i !== index))}
                      >
                        <Icon name="trash" size={20} />
                      </Button>
                    </div>
                    <div className="recurring-meals__portion">
                      <Field label="Количество" labelFor={`recurring-amount-${index}`}>
                        <Input
                          id={`recurring-amount-${index}`}
                          inputMode="decimal"
                          value={row.amount}
                          onChange={(event) =>
                            setRows(
                              rows.map((item, i) =>
                                i === index ? { ...item, amount: event.target.value } : item,
                              ),
                            )
                          }
                        />
                      </Field>
                      <Field label="Единица" labelFor={`recurring-unit-${index}`}>
                        <Select
                          id={`recurring-unit-${index}`}
                          value={row.unit}
                          onChange={(event) =>
                            setRows(
                              rows.map((item, i) =>
                                i === index
                                  ? { ...item, unit: event.target.value as Row['unit'] }
                                  : item,
                              ),
                            )
                          }
                        >
                          <option value="">Выберите</option>
                          <option value="g">г</option>
                          <option value="ml">мл</option>
                          <option value="serving">порция</option>
                        </Select>
                      </Field>
                    </div>
                    {!row.unit && <p>Укажите единицу порции: её не удалось определить по файлу.</p>}
                    {row.sourceIndex !== null && (
                      <p>
                        В файле:{' '}
                        {proposal.occurrences
                          .flatMap((occurrence) =>
                            occurrence.items.filter((item) => item.food_id === row.foodId),
                          )
                          .map(
                            (item) =>
                              [
                                item.source.quantity,
                                item.source.source_unit ||
                                  (item.source.amount_unit
                                    ? sourceUnits[item.source.amount_unit]
                                    : ''),
                              ]
                                .filter(Boolean)
                                .join(' ') || 'не указано',
                          )
                          .join(' · ')}
                        . Единицы не пересчитываются автоматически.
                      </p>
                    )}
                  </div>
                ))}
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    setSearchQuery(search.trim());
                  }}
                  className="recurring-meals__search"
                >
                  <Field label="Добавить продукт из каталога" labelFor="recurring-search">
                    <Input
                      id="recurring-search"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                    />
                  </Field>
                  <Button type="submit" variant="secondary" disabled={search.trim().length < 2}>
                    Найти
                  </Button>
                </form>
                {foods.isLoading && searchQuery && <p role="status">Ищем продукты…</p>}
                {foods.error && <p role="alert">Не удалось найти продукты. Повторите поиск.</p>}
                {foods.data?.items.map((food) => (
                  <Button
                    type="button"
                    variant="secondary"
                    key={food.id}
                    disabled={rows.some((row) => row.foodId === food.id)}
                    onClick={() => {
                      setRows([
                        ...rows,
                        {
                          sourceIndex: null,
                          foodId: food.id,
                          name: [food.name, food.brand].filter(Boolean).join(' · '),
                          amount: '',
                          unit: '',
                        },
                      ]);
                      setSearch('');
                      setSearchQuery('');
                    }}
                  >
                    Добавить: {food.name}
                    {food.brand ? ` · ${food.brand}` : ''}
                  </Button>
                ))}
                <Button type="button" disabled={busy} onClick={() => void check()}>
                  {busy ? 'Проверяем…' : 'Сравнить КБЖУ'}
                </Button>
              </Surface>
            </div>
          ) : (
            <div className="stack">
              <header>
                <h2>Предложения</h2>
                <p>
                  Выберите сочетание для проверки. Ничего не сохранится без вашего подтверждения.
                </p>
              </header>
              {suggestions.isLoading && <p role="status">Ищем предложения…</p>}
              {suggestions.error && (
                <Surface className="stack">
                  <p role="alert">
                    Не удалось загрузить предложения. Срок хранения импорта мог истечь.
                  </p>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => void suggestions.refetch()}
                  >
                    Повторить
                  </Button>
                </Surface>
              )}
              {suggestions.data && !suggestions.data.items.length && (
                <Surface>Повторяющихся сочетаний не найдено.</Surface>
              )}
              {suggestions.data?.items.map((item) => (
                <Surface className="stack" key={`${item.meal_type}-${item.occurrences[0]?.date}`}>
                  <h2>{meals[item.meal_type]}</h2>
                  <p>
                    {item.repeat_days} из {suggestions.data.observed_days} дней
                  </p>
                  <p>
                    {item.occurrences[0]?.items.map((entry) => entry.source.food.name).join(' · ')}
                  </p>
                  <Button type="button" onClick={() => selectProposal(item)}>
                    Проверить состав
                  </Button>
                </Surface>
              ))}
              <Button type="button" variant="secondary" onClick={onBack}>
                Не сохранять сейчас
              </Button>
            </div>
          )}
        </Surface>
        <Surface className="recurring-meals__aside stack" subtle>
          <h2>Что будет дальше</h2>
          <p>
            Шаблон хранит выбранные продукты и порции. Его можно открыть и изменить в разделе
            «Питание».
          </p>
          <p>Запись в дневнике появится только после отдельного добавления шаблона.</p>
          <p>Предложения доступны, пока действует черновик импорта: до 24 часов.</p>
        </Surface>
      </div>
    </div>
  );
}
