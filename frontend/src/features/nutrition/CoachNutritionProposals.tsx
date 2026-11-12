import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { components } from '../../shared/api/schema';
import { addCalendarDays, dateInputValue } from '../../shared/dateTime';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { DateInput } from '../../shared/ui/PickerInput';
import { DisclosureIcon } from '../../shared/ui/common';
import './coach-nutrition-proposals.css';

type Proposal = components['schemas']['CoachNutritionProposalResponse'];
type Create = components['schemas']['CoachNutritionProposalCreate-Input'];
type Plan = components['schemas']['CoachNutritionPlanPreview'];
type Assignments = components['schemas']['CoachNutritionTargetAssignments'];
const labels: Record<string, string> = {
  pending: 'Ожидает ответа',
  accepted: 'Принято',
  rejected: 'Отклонено',
};
const units = { g: 'г', ml: 'мл', serving: 'порц.' } as const;
const dayTypes = { training: 'тренировка', rest: 'отдых', recovery: 'восстановление' } as const;
const weekTypes = {
  light: 'лёгкая неделя',
  medium: 'средняя неделя',
  heavy: 'тяжёлая неделя',
} as const;
const scopes = { template: 'шаблон', future: 'повторение', recovery: 'восстановление' } as const;
const key = () =>
  `nutrition-proposal-${typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;

function Comparison({
  proposal,
}: {
  proposal: { before: Proposal['before']; request: Create | Proposal['request'] };
}) {
  const target = proposal.before.target as Record<string, number> | null;
  const item = proposal.before.item as {
    name: string;
    amount: string;
    amount_unit: keyof typeof units;
  } | null;
  const rows = [
    ['Энергия, ккал', 'calories'],
    ['Белки, г', 'protein_g'],
    ['Жиры, г', 'fat_g'],
    ['Углеводы, г', 'carbs_g'],
  ] as const;
  return (
    <>
      <div className="coach-nutrition-comparison">
        <table>
          <thead>
            <tr>
              <th>На день</th>
              <th>Сейчас</th>
              <th>Предлагается</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, field]) => (
              <tr key={field}>
                <th scope="row">{label}</th>
                <td>{target?.[field] ?? '—'}</td>
                <td>{proposal.request[field]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {item && (
        <p>
          Приём пищи: {item.name} · {item.amount} {units[item.amount_unit]} →{' '}
          {proposal.request.item_amount} {units[item.amount_unit]}
        </p>
      )}
      <p className="muted">
        Дата: {proposal.request.target_date}. Неизвестные значения показаны как «—».
      </p>
      {proposal.request.comment && <p>Комментарий: {proposal.request.comment}</p>}
    </>
  );
}

export function TrainerNutritionProposals({
  clientId,
  timeZone,
}: {
  clientId: number;
  timeZone?: string | null;
}) {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const [date, setDate] = useState(() =>
    addCalendarDays(dateInputValue(new Date(), timeZone || undefined), 1),
  );
  const [values, setValues] = useState({
    calories: '',
    protein_g: '',
    fat_g: '',
    carbs_g: '',
    item: '',
    amount: '',
    comment: '',
  });
  const [preview, setPreview] = useState<{ before: Proposal['before']; request: Create } | null>(
    null,
  );
  const populatedDate = useRef<string | null>(null);
  const [confirmEnergy, setConfirmEnergy] = useState(false);
  const [editing, setEditing] = useState(false);
  const requestKey = useRef(key());
  const listKey = ['coach-nutrition-proposals', clientId] as const;
  const list = useQuery({
    queryKey: listKey,
    queryFn: () => api<Proposal[]>(`/api/v1/coach-nutrition-proposals?client_id=${clientId}`),
  });
  const assignments = useQuery({
    queryKey: ['coach-nutrition-assignments', clientId],
    queryFn: () =>
      api<Assignments>(`/api/v1/coach-nutrition-proposals/clients/${clientId}/target-assignments`),
  });
  const plan = useQuery({
    queryKey: ['coach-nutrition-plan', clientId, date],
    enabled: Boolean(date),
    queryFn: () =>
      api<Plan>(
        `/api/v1/coach-nutrition-proposals/clients/${clientId}/day?target_date=${encodeURIComponent(date)}`,
      ),
  });
  useEffect(() => {
    if (!plan.data || plan.data.day.plan_date !== date || populatedDate.current === date) return;
    populatedDate.current = date;
    const target = plan.data.day.targets;
    setValues((current) => ({
      ...current,
      calories: target?.energy_kcal ?? '',
      protein_g: target?.protein_g ?? '',
      fat_g: target?.fat_g ?? '',
      carbs_g: target?.carbs_g ?? '',
      item: '',
      amount: '',
    }));
  }, [date, plan.data]);
  const send = useMutation({
    mutationFn: (body: Create) =>
      api<Proposal>(`/api/v1/coach-nutrition-proposals/clients/${clientId}`, {
        method: 'POST',
        headers: { 'Idempotency-Key': requestKey.current },
        body,
      }),
    onSuccess: async () => {
      setPreview(null);
      setEditing(false);
      requestKey.current = key();
      await queryClient.invalidateQueries({ queryKey: listKey });
      toast('Предложение отправлено');
    },
    onError: (error) => toast((error as Error).message, 'error'),
  });
  const items =
    plan.data?.day.slots
      .flatMap((slot) => slot.items)
      .filter((item) => item.status === 'planned' && item.available) ?? [];
  const selected = items.find((item) => String(item.id) === values.item);
  const update = (name: keyof typeof values, value: string) => {
    setValues((current) => ({ ...current, [name]: value }));
    setPreview(null);
    setConfirmEnergy(false);
    requestKey.current = key();
  };
  const before = {
    target: plan.data?.day.targets
      ? {
          calories: Number(plan.data.day.targets.energy_kcal),
          protein_g:
            plan.data.day.targets.protein_g === null
              ? null
              : Number(plan.data.day.targets.protein_g),
          fat_g: plan.data.day.targets.fat_g === null ? null : Number(plan.data.day.targets.fat_g),
          carbs_g:
            plan.data.day.targets.carbs_g === null ? null : Number(plan.data.day.targets.carbs_g),
        }
      : null,
    item: selected ?? null,
  };
  return (
    <section
      className="nutrition-section-card top-gap"
      aria-labelledby="coach-nutrition-proposal-title"
    >
      <h3 id="coach-nutrition-proposal-title">Предложения по питанию</h3>
      {!editing && (
        <button type="button" onClick={() => setEditing(true)}>
          Предложить изменение
        </button>
      )}
      {editing && !preview && (
        <p>Клиент увидит сравнение и сам примет решение. План до этого не изменится.</p>
      )}
      {editing && !preview && (
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            if (!plan.data) return;
            setPreview({
              before,
              request: {
                target_date: date,
                expected_target_id: plan.data.target_id,
                expected_plan_revision: plan.data.day.revision,
                calories: Number(values.calories),
                protein_g: Number(values.protein_g),
                fat_g: Number(values.fat_g),
                carbs_g: Number(values.carbs_g),
                confirm_energy_mismatch: confirmEnergy,
                item_id: selected?.id ?? null,
                item_amount: selected ? values.amount : null,
                comment: values.comment || null,
              },
            });
          }}
        >
          <label className="field">
            <span>Будущая дата</span>
            <DateInput
              required
              min={addCalendarDays(dateInputValue(new Date(), timeZone || undefined), 1)}
              value={date}
              onChange={(event) => {
                setDate(event.target.value);
                populatedDate.current = null;
                setPreview(null);
                requestKey.current = key();
              }}
            />
          </label>
          {plan.isPending && <p role="status">Загружаем план…</p>}
          {plan.isError && <p role="alert">Не удалось загрузить план. Обновите страницу.</p>}
          {plan.data && (
            <p className="muted">
              Текущая цель: {plan.data.day.targets?.energy_kcal ?? '—'} ккал · версия плана{' '}
              {plan.data.day.revision}.
            </p>
          )}
          {plan.data && (
            <p className="muted">
              Программа: {plan.data.program?.title ?? 'нет данных'} ·{' '}
              {plan.data.program_day?.day_type === 'training'
                ? 'тренировочный день'
                : plan.data.program_day?.day_type === 'rest'
                  ? 'день отдыха'
                  : 'тип дня не определён'}
              .
              {plan.data.binding?.program_changed && ' Программа изменилась после назначения цели.'}
            </p>
          )}
          {(
            [
              ['calories', 'Энергия, ккал', 800, 6000],
              ['protein_g', 'Белки, г', 0, 400],
              ['fat_g', 'Жиры, г', 0, 250],
              ['carbs_g', 'Углеводы, г', 0, 800],
            ] as const
          ).map(([name, label, min, max]) => (
            <label className="field" key={name}>
              <span>{label}</span>
              <input
                type="number"
                min={min}
                max={max}
                required
                disabled={!plan.data}
                value={values[name]}
                onChange={(event) => update(name, event.target.value)}
              />
            </label>
          ))}
          <label>
            <input
              type="checkbox"
              checked={confirmEnergy}
              onChange={(event) => {
                setConfirmEnergy(event.target.checked);
                setPreview(null);
                requestKey.current = key();
              }}
            />{' '}
            Подтверждаю возможное расхождение калорийности и БЖУ
          </label>
          <label className="field">
            <span>Приём пищи</span>
            <select value={values.item} onChange={(event) => update('item', event.target.value)}>
              <option value="">Без изменения</option>
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {item.amount} {units[item.amount_unit]}
                </option>
              ))}
            </select>
          </label>
          {selected && (
            <label className="field">
              <span>Предлагаемое количество, {units[selected.amount_unit]}</span>
              <input
                type="number"
                min="0.001"
                step="0.001"
                required
                value={values.amount}
                onChange={(event) => update('amount', event.target.value)}
              />
            </label>
          )}
          <label className="field">
            <span>Комментарий клиенту</span>
            <input
              maxLength={500}
              value={values.comment}
              onChange={(event) => update('comment', event.target.value)}
            />
          </label>
          <button type="submit" disabled={!plan.data || send.isPending}>
            Проверить изменения
          </button>
          <button type="button" className="secondary" onClick={() => setEditing(false)}>
            Отмена
          </button>
        </form>
      )}
      {preview && (
        <section aria-label="Проверка предложения" className="top-gap">
          <h4>Что увидит клиент</h4>
          <Comparison proposal={preview} />
          <p>Прошедшие дни и дневник не изменятся.</p>
          <div className="coach-nutrition-review-actions">
            <button type="button" className="secondary" onClick={() => setPreview(null)}>
              Вернуться к изменениям
            </button>
            <button
              type="button"
              disabled={send.isPending}
              onClick={() => send.mutate(preview.request)}
            >
              {send.isPending ? 'Отправляем…' : 'Отправить предложение'}
            </button>
          </div>
        </section>
      )}
      <details className="top-gap">
        <summary className="yfc-disclosure-summary">
          <span>История назначений по датам и правилам</span>
          <DisclosureIcon />
        </summary>
        {assignments.isPending && <p role="status">Загружаем назначения…</p>}
        {assignments.isError && <p role="alert">Не удалось загрузить назначения.</p>}
        {assignments.data &&
          assignments.data.dates.length === 0 &&
          assignments.data.schedule.length === 0 && <p>Назначений пока нет.</p>}
        {assignments.data?.dates.map((row) => (
          <p key={`date-${row.target.id}`}>
            Дата {row.date}
            {row.day_type ? ` · ${dayTypes[row.day_type]}` : ''}: {row.target.calories} ккал · Б{' '}
            {row.target.protein_g} · Ж {row.target.fat_g} · У {row.target.carbs_g} г
          </p>
        ))}
        {assignments.data?.schedule.map((row) => (
          <p key={`rule-${row.id}`}>
            {scopes[row.scope]} с {row.effective_from} · {dayTypes[row.day_type]}
            {row.week_type ? ` · ${weekTypes[row.week_type]}` : ''}: {row.target.calories} ккал · Б{' '}
            {row.target.protein_g} · Ж {row.target.fat_g} · У {row.target.carbs_g} г
          </p>
        ))}
      </details>
      <h4>Предложения</h4>
      {list.isPending && <p role="status">Загружаем…</p>}
      {list.isError && <p role="alert">Не удалось загрузить предложения.</p>}
      {list.data?.length === 0 && <p>Предложений пока нет.</p>}
      {list.data?.map((proposal) => (
        <div key={proposal.id} className="top-gap">
          <strong>
            {labels[proposal.status]} · {proposal.target_date}
          </strong>
          <Comparison proposal={proposal} />
        </div>
      ))}
    </section>
  );
}

export function ClientNutritionProposals() {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const keys = useRef<Record<string, string>>({});
  const proposals = useQuery({
    queryKey: ['my-coach-nutrition-proposals'],
    queryFn: () => api<Proposal[]>('/api/v1/coach-nutrition-proposals'),
  });
  const decide = useMutation({
    mutationFn: ({ proposal, decision }: { proposal: Proposal; decision: 'accept' | 'reject' }) => {
      const identity = `${proposal.id}-${decision}`;
      keys.current[identity] ??= key();
      return api<Proposal>(`/api/v1/coach-nutrition-proposals/${proposal.id}/decision`, {
        method: 'POST',
        headers: { 'Idempotency-Key': keys.current[identity] },
        body: { decision, version: proposal.version },
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      toast('Решение сохранено');
    },
    onError: (error) => toast((error as Error).message, 'error'),
  });
  if (proposals.isPending) return <p role="status">Загружаем предложения тренера…</p>;
  if (proposals.isError) return <p role="alert">Не удалось загрузить предложения тренера.</p>;
  if (!proposals.data?.length) return null;
  return (
    <section className="nutrition-section-card" aria-labelledby="client-nutrition-proposals">
      <h2 id="client-nutrition-proposals">Предложения тренера</h2>
      {proposals.data.map((proposal) => (
        <article key={proposal.id} className="top-gap">
          <h3>{proposal.status === 'pending' ? 'Проверьте изменения' : labels[proposal.status]}</h3>
          <Comparison proposal={proposal} />
          {proposal.status === 'pending' && (
            <>
              <p>До вашего решения план не изменится. Прошедшие дни сохранятся.</p>
              <div className="toolbar wrap">
                <button
                  type="button"
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ proposal, decision: 'accept' })}
                >
                  Принять изменения
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ proposal, decision: 'reject' })}
                >
                  Отклонить
                </button>
              </div>
            </>
          )}
        </article>
      ))}
    </section>
  );
}
