import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import {
  addCalendarDays,
  calendarWeek,
  dateInputValue,
  formatCalendarDate,
} from '../../shared/dateTime';
import type {
  GroceryList as GroceryListResponse,
  GroceryListItem,
  GroceryListItemUpdate,
  GroceryListManualItemCreate,
} from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { WeekStrip } from '../../shared/ui/WeekStrip';
import {
  Button,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Select,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';

type GroceryAmountUnit = Exclude<GroceryListItem['amount_unit'], null>;

const unitLabels: Record<GroceryAmountUnit, string> = {
  g: 'г',
  ml: 'мл',
  piece: 'шт.',
  serving: 'порц.',
};

const mealLabels = {
  breakfast: 'Завтрак',
  lunch: 'Обед',
  dinner: 'Ужин',
  snacks: 'Перекус',
} as const;

function formatAmount(item: GroceryListItem): string | null {
  if (item.amount === null || item.amount_unit === null) return null;
  const amount = Number(item.amount);
  if (!Number.isFinite(amount)) return `${item.amount} ${unitLabels[item.amount_unit]}`;
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 }).format(amount)} ${unitLabels[item.amount_unit]}`;
}

function sourceLabel(source: GroceryListItem['sources'][number]): string {
  return `${source.recipe_name} · ${mealLabels[source.meal_type]} · ${formatCalendarDate(
    source.plan_date,
    {
      day: 'numeric',
      month: 'short',
    },
  )}`;
}

function GroceryItemRow({
  item,
  pending,
  readOnly,
  onDelete,
  onUpdate,
}: {
  item: GroceryListItem;
  pending: boolean;
  readOnly: boolean;
  onDelete(): void;
  onUpdate(payload: GroceryListItemUpdate): void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState('');
  const [amount, setAmount] = useState('');
  const [unit, setUnit] = useState<GroceryAmountUnit | ''>('');

  const save = () => {
    const normalizedName = name.trim();
    if (!normalizedName || Boolean(amount) !== Boolean(unit)) return;
    const amountUnit: GroceryAmountUnit | null = unit || null;
    onUpdate({
      name: normalizedName,
      amount: amount || null,
      amount_unit: amount ? amountUnit : null,
    });
    setEditing(false);
  };

  return (
    <li className={`grocery-list__item${item.checked ? ' grocery-list__item--checked' : ''}`}>
      <div className="grocery-list__item-copy">
        <label className="grocery-list__check">
          <input
            aria-label={`Куплено: ${item.name}`}
            checked={item.checked}
            disabled={readOnly || pending}
            onChange={() => onUpdate({ checked: !item.checked })}
            type="checkbox"
          />
          <span>
            <strong>{item.name}</strong>
            {item.brand && <small>{item.brand}</small>}
          </span>
        </label>
        <div className="grocery-list__item-meta">
          {formatAmount(item) && <span>{formatAmount(item)}</span>}
          <span>{item.source_kind === 'manual' ? 'Вручную' : 'Из плана'}</span>
        </div>
        {item.sources.length > 0 && (
          <ul className="grocery-list__sources" aria-label={`Источники: ${item.name}`}>
            {item.sources.map((source) => (
              <li key={`${source.plan_item_id}-${source.plan_date}`}>{sourceLabel(source)}</li>
            ))}
          </ul>
        )}
      </div>
      <div className="grocery-list__item-controls">
        <label className="grocery-list__owned">
          <input
            aria-label={`Уже есть: ${item.name}`}
            checked={item.owned}
            disabled={readOnly || pending}
            onChange={() => onUpdate({ owned: !item.owned })}
            type="checkbox"
          />
          <span>Уже есть</span>
        </label>
        {!readOnly && item.source_kind === 'manual' && !editing && (
          <>
            <Button
              disabled={pending}
              onClick={() => {
                setName(item.name);
                setAmount(item.amount === null ? '' : String(item.amount));
                setUnit(item.amount_unit ?? '');
                setEditing(true);
              }}
              type="button"
              variant="ghost"
            >
              Изменить
            </Button>
            <Button disabled={pending} onClick={onDelete} type="button" variant="danger">
              Удалить
            </Button>
          </>
        )}
      </div>
      {editing && (
        <form
          className="grocery-list__edit"
          onSubmit={(event) => {
            event.preventDefault();
            save();
          }}
        >
          <Field label="Название" labelFor={`grocery-edit-name-${item.id}`}>
            <Input
              id={`grocery-edit-name-${item.id}`}
              onChange={(event) => setName(event.target.value)}
              value={name}
            />
          </Field>
          <Field label="Количество" labelFor={`grocery-edit-amount-${item.id}`}>
            <Input
              id={`grocery-edit-amount-${item.id}`}
              min="0.001"
              onChange={(event) => setAmount(event.target.value)}
              step="0.001"
              type="number"
              value={amount}
            />
          </Field>
          <Field label="Единица" labelFor={`grocery-edit-unit-${item.id}`}>
            <Select
              id={`grocery-edit-unit-${item.id}`}
              onChange={(event) => setUnit(event.target.value as GroceryAmountUnit | '')}
              value={unit}
            >
              <option value="">Без количества</option>
              <option value="g">г</option>
              <option value="ml">мл</option>
              <option value="piece">шт.</option>
              <option value="serving">порц.</option>
            </Select>
          </Field>
          <div className="grocery-list__edit-actions">
            <Button disabled={pending || !name.trim()} type="submit">
              Сохранить
            </Button>
            <Button onClick={() => setEditing(false)} type="button" variant="ghost">
              Отмена
            </Button>
          </div>
        </form>
      )}
    </li>
  );
}

export function GroceryList({
  initialDate,
  readOnly = false,
  timeZone,
}: {
  initialDate?: string;
  readOnly?: boolean;
  timeZone?: string | null;
}) {
  const today = dateInputValue(new Date(), timeZone || undefined);
  const [open, setOpen] = useState(false);
  const [weekStart, setWeekStart] = useState(
    () => calendarWeek(initialDate || today)[0] || initialDate || today,
  );
  const [manualName, setManualName] = useState('');
  const [manualAmount, setManualAmount] = useState('');
  const [manualUnit, setManualUnit] = useState<GroceryAmountUnit | ''>('');
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const queryKey = queryKeys.nutrition.groceryList(weekStart);
  const listQuery = useQuery({
    queryKey,
    queryFn: ({ signal }) =>
      api<GroceryListResponse>(
        `/api/v1/nutrition/grocery-list?week_start=${encodeURIComponent(weekStart)}`,
        { signal },
      ),
    enabled: open,
  });
  const setList = (next: GroceryListResponse) => {
    queryClient.setQueryData(queryKey, next);
  };
  const reportError = (reason: unknown) => toast((reason as Error).message, 'error');
  const generate = useMutation({
    mutationFn: () =>
      api<GroceryListResponse>('/api/v1/nutrition/grocery-list', {
        method: 'PUT',
        body: { week_start: weekStart },
      }),
    onSuccess: (next) => {
      setList(next);
      toast('Список покупок обновлён');
    },
    onError: reportError,
  });
  const add = useMutation({
    mutationFn: (payload: GroceryListManualItemCreate) =>
      api<GroceryListResponse>('/api/v1/nutrition/grocery-list/items', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: (next) => {
      setList(next);
      setManualName('');
      setManualAmount('');
      setManualUnit('');
      toast('Пункт добавлен');
    },
    onError: reportError,
  });
  const update = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: GroceryListItemUpdate }) =>
      api<GroceryListResponse>(`/api/v1/nutrition/grocery-list/items/${id}`, {
        method: 'PATCH',
        body: payload,
      }),
    onSuccess: setList,
    onError: reportError,
  });
  const remove = useMutation({
    mutationFn: (id: number) =>
      api<GroceryListResponse>(`/api/v1/nutrition/grocery-list/items/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: (next) => {
      setList(next);
      toast('Пункт удалён');
    },
    onError: reportError,
  });
  const pending = add.isPending || update.isPending || remove.isPending;
  const submitManual = () => {
    const name = manualName.trim();
    if (!name || Boolean(manualAmount) !== Boolean(manualUnit)) return;
    const amountUnit: GroceryAmountUnit | null = manualUnit || null;
    add.mutate({
      week_start: weekStart,
      name,
      amount: manualAmount || null,
      amount_unit: manualAmount ? amountUnit : null,
    });
  };

  return (
    <details
      className="grocery-list"
      data-testid="grocery-list"
      onToggle={(event) => setOpen(event.currentTarget.open)}
      open={open}
    >
      <summary className="grocery-list__summary">
        <span>
          <span className="eyebrow">Планирование питания</span>
          <strong>Список покупок</strong>
        </span>
        <span className="grocery-list__summary-note">По рецептам недели</span>
      </summary>
      <div className="grocery-list__body">
        <WeekStrip
          anchorDate={weekStart}
          ariaLabel="Неделя списка покупок"
          mode="overview"
          navigation={{
            onPrevious: () => setWeekStart(addCalendarDays(weekStart, -7)),
            onNext: () => setWeekStart(addCalendarDays(weekStart, 7)),
          }}
          rangeStart={weekStart}
          title="Неделя списка покупок"
          today={today}
        />
        {listQuery.isLoading && <LoadingState label="Загружаем список покупок…" />}
        {listQuery.error && (
          <ErrorState
            message={(listQuery.error as Error).message}
            retry={() => void listQuery.refetch()}
          />
        )}
        {listQuery.data && (
          <>
            {listQuery.data.refresh_required && (
              <div className="grocery-list__notice" role="status">
                <strong>План изменился</strong>
                <span>Обновите список, чтобы увидеть актуальные количества.</span>
                {!readOnly && (
                  <Button
                    disabled={generate.isPending}
                    onClick={() => generate.mutate()}
                    type="button"
                  >
                    {generate.isPending ? 'Обновляем…' : 'Обновить список'}
                  </Button>
                )}
              </div>
            )}
            <div className="grocery-list__heading">
              <div>
                <span className="eyebrow">
                  {formatCalendarDate(weekStart, { day: 'numeric', month: 'long' })}
                </span>
                <h3>{listQuery.data.generated ? 'Что купить' : 'Список ещё не сформирован'}</h3>
              </div>
              {!readOnly && (
                <Button
                  disabled={generate.isPending}
                  onClick={() => generate.mutate()}
                  type="button"
                >
                  {generate.isPending
                    ? 'Формируем…'
                    : listQuery.data.generated
                      ? 'Обновить список'
                      : 'Сформировать список'}
                </Button>
              )}
            </div>
            {listQuery.data.stale_sources.length > 0 && (
              <div className="grocery-list__stale" role="alert">
                <strong>Часть источников недоступна</strong>
                <ul>
                  {listQuery.data.stale_sources.map((source) => (
                    <li key={source.plan_item_id}>
                      {source.source_name}: {source.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {listQuery.data.items.length > 0 ? (
              <ul className="grocery-list__items" aria-label="Продукты в списке">
                {listQuery.data.items.map((item) => (
                  <GroceryItemRow
                    item={item}
                    key={item.id}
                    pending={pending}
                    readOnly={readOnly}
                    onDelete={() => remove.mutate(item.id)}
                    onUpdate={(payload) => update.mutate({ id: item.id, payload })}
                  />
                ))}
              </ul>
            ) : (
              <EmptyState
                text={
                  listQuery.data.generated
                    ? 'В выбранной неделе нет рецептов с ингредиентами.'
                    : 'Список строится из рецептов, запланированных на выбранную неделю.'
                }
                title="Пока нет продуктов"
              />
            )}
            {!readOnly && (
              <form
                className="grocery-list__add"
                onSubmit={(event) => {
                  event.preventDefault();
                  submitManual();
                }}
              >
                <div className="grocery-list__heading">
                  <div>
                    <span className="eyebrow">Вручную</span>
                    <h3>Добавить пункт</h3>
                  </div>
                </div>
                <div className="grocery-list__form-grid">
                  <Field label="Название продукта" labelFor="grocery-manual-name">
                    <Input
                      id="grocery-manual-name"
                      onChange={(event) => setManualName(event.target.value)}
                      required
                      value={manualName}
                    />
                  </Field>
                  <Field label="Количество" labelFor="grocery-manual-amount">
                    <Input
                      id="grocery-manual-amount"
                      min="0.001"
                      onChange={(event) => setManualAmount(event.target.value)}
                      step="0.001"
                      type="number"
                      value={manualAmount}
                    />
                  </Field>
                  <Field label="Единица" labelFor="grocery-manual-unit">
                    <Select
                      id="grocery-manual-unit"
                      onChange={(event) =>
                        setManualUnit(event.target.value as GroceryAmountUnit | '')
                      }
                      value={manualUnit}
                    >
                      <option value="">Без количества</option>
                      <option value="g">г</option>
                      <option value="ml">мл</option>
                      <option value="piece">шт.</option>
                      <option value="serving">порц.</option>
                    </Select>
                  </Field>
                </div>
                <Button disabled={add.isPending || !manualName.trim()} type="submit">
                  {add.isPending ? 'Добавляем…' : 'Добавить в список'}
                </Button>
              </form>
            )}
          </>
        )}
      </div>
    </details>
  );
}
