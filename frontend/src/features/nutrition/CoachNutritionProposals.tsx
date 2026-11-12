import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { components } from '../../shared/api/schema';
import { addCalendarDays, dateInputValue, formatCalendarDate } from '../../shared/dateTime';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { DateInput } from '../../shared/ui/PickerInput';
import { Button, DisclosureIcon } from '../../shared/ui/common';
import { useTelegramOverlayBackButton } from '../../shared/telegram/useTelegramOverlayBackButton';
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
        Дата:{' '}
        {formatCalendarDate(proposal.request.target_date, {
          day: 'numeric',
          month: 'long',
          year: 'numeric',
        })}{' '}
        · Неизвестные значения показаны как «—».
      </p>
      {proposal.request.comment && <p>Комментарий: {proposal.request.comment}</p>}
    </>
  );
}

export function TrainerNutritionProposals({
  clientId,
  timeZone,
  onEditingChange,
  onAccessDenied,
}: {
  clientId: number;
  timeZone?: string | null;
  onEditingChange?: (editing: boolean) => void;
  onAccessDenied?: () => void;
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
  const [selectedProposal, setSelectedProposal] = useState<Proposal | null>(null);
  useTelegramOverlayBackButton(editing || selectedProposal !== null, () => {
    if (selectedProposal) setSelectedProposal(null);
    else if (preview) setPreview(null);
    else setEditing(false);
  });
  useEffect(() => {
    onEditingChange?.(editing || selectedProposal !== null);
  }, [editing, selectedProposal, onEditingChange]);
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
  const planData = plan.isError ? undefined : plan.data;
  useEffect(() => {
    if (
      [plan.error, assignments.error, list.error].some((error) =>
        [403, 404].includes((error as { status?: number } | null)?.status ?? 0),
      )
    )
      onAccessDenied?.();
  }, [plan.error, assignments.error, list.error, onAccessDenied]);
  useEffect(() => {
    if (!planData || planData.day.plan_date !== date || populatedDate.current === date) return;
    populatedDate.current = date;
    const target = planData.day.targets;
    setValues((current) => ({
      ...current,
      calories: target?.energy_kcal ?? '',
      protein_g: target?.protein_g ?? '',
      fat_g: target?.fat_g ?? '',
      carbs_g: target?.carbs_g ?? '',
      item: '',
      amount: '',
    }));
  }, [date, planData]);
  const send = useMutation({
    mutationFn: (body: Create) =>
      api<Proposal>(`/api/v1/coach-nutrition-proposals/clients/${clientId}`, {
        method: 'POST',
        headers: { 'Idempotency-Key': requestKey.current },
        body,
      }),
    onSuccess: async (proposal) => {
      setPreview(null);
      setEditing(false);
      setSelectedProposal(proposal);
      requestKey.current = key();
      await queryClient.invalidateQueries({ queryKey: listKey });
      toast('Предложение отправлено');
    },
    onError: (error) => toast((error as Error).message, 'error'),
  });
  const items =
    planData?.day.slots
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
    target: planData?.day.targets
      ? {
          calories: Number(planData.day.targets.energy_kcal),
          protein_g:
            planData.day.targets.protein_g === null ? null : Number(planData.day.targets.protein_g),
          fat_g: planData.day.targets.fat_g === null ? null : Number(planData.day.targets.fat_g),
          carbs_g:
            planData.day.targets.carbs_g === null ? null : Number(planData.day.targets.carbs_g),
        }
      : null,
    item: selected ?? null,
  };
  return (
    <section
      className="nutrition-section-card top-gap"
      aria-labelledby="coach-nutrition-proposal-title"
    >
      <h3 id="coach-nutrition-proposal-title">
        {selectedProposal
          ? selectedProposal.status === 'pending'
            ? 'Ожидает ответа'
            : selectedProposal.status === 'accepted'
              ? 'Предложение принято'
              : 'Предложение отклонено'
          : preview
            ? 'Что увидит клиент'
            : editing
              ? 'Изменить будущий план'
              : 'Назначено и запланировано'}
      </h3>
      {selectedProposal && (
        <section className="coach-nutrition-selected">
          <p>
            {labels[selectedProposal.status]} ·{' '}
            {formatCalendarDate(selectedProposal.target_date, {
              day: 'numeric',
              month: 'long',
              year: 'numeric',
            })}
          </p>
          <Comparison proposal={selectedProposal} />
          <div className="coach-nutrition-notice">
            <strong>
              {selectedProposal.status === 'accepted'
                ? 'Будущий план обновлён'
                : selectedProposal.status === 'rejected'
                  ? 'План не изменён'
                  : 'План ещё не изменён'}
            </strong>
            <p>
              {selectedProposal.status === 'pending'
                ? 'Изменения вступят в силу только после принятия клиентом.'
                : 'Прошедшие дни и дневник сохранены.'}
            </p>
          </div>
          <Button type="button" variant="secondary" onClick={() => setSelectedProposal(null)}>
            К отчёту клиента
          </Button>
        </section>
      )}
      {!editing && !selectedProposal && (
        <>
          {plan.isPending && <p role="status">Загружаем план…</p>}
          {plan.isError && <p role="alert">Не удалось загрузить план. Обновите страницу.</p>}
          {planData && (
            <div className="coach-nutrition-assigned">
              <p>
                <span>Цель на {formatCalendarDate(date, { day: 'numeric', month: 'long' })}</span>
                <strong>
                  {planData.day.targets?.energy_kcal ?? '—'} {planData.day.targets ? 'ккал' : ''}
                </strong>
              </p>
              <p>
                <span>Тренировочная программа</span>
                <strong>{planData.program?.title ?? 'Нет данных'}</strong>
              </p>
              <p>
                <span>План питания</span>
                <strong>
                  {planData.day.slots.flatMap((slot) => slot.items).length
                    ? 'Запланировано'
                    : 'Нет данных'}
                </strong>
              </p>
            </div>
          )}
          <button type="button" onClick={() => setEditing(true)}>
            Предложить изменение
          </button>
        </>
      )}
      {editing && !preview && !selectedProposal && (
        <p>Клиент увидит сравнение и сам примет решение. План до этого не изменится.</p>
      )}
      {editing && !preview && !selectedProposal && (
        <form
          className="stack coach-nutrition-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!planData) return;
            setPreview({
              before,
              request: {
                target_date: date,
                expected_target_id: planData.target_id,
                expected_plan_revision: planData.day.revision,
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
          {planData && (
            <p className="muted">
              Текущая цель: {planData.day.targets?.energy_kcal ?? '—'} ккал · версия плана{' '}
              {planData.day.revision}.
            </p>
          )}
          {planData && (
            <p className="muted">
              Программа: {planData.program?.title ?? 'нет данных'} ·{' '}
              {planData.program_day?.day_type === 'training'
                ? 'тренировочный день'
                : planData.program_day?.day_type === 'rest'
                  ? 'день отдыха'
                  : 'тип дня не определён'}
              .{planData.binding?.program_changed && ' Программа изменилась после назначения цели.'}
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
                disabled={!planData}
                value={values[name]}
                onChange={(event) => update(name, event.target.value)}
              />
            </label>
          ))}
          <label className="coach-nutrition-energy-confirm">
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
          <Button type="button" variant="secondary" onClick={() => setEditing(false)}>
            Отмена
          </Button>
          <button type="submit" disabled={!planData || send.isPending}>
            Проверить изменения
          </button>
        </form>
      )}
      {preview && !selectedProposal && (
        <section aria-label="Проверка предложения" className="top-gap">
          <Comparison proposal={preview} />
          <p>Прошедшие дни и дневник не изменятся.</p>
          {send.error && (
            <div className="coach-nutrition-notice" role="alert">
              <strong>Не удалось отправить предложение</strong>
              <p>{(send.error as Error).message}</p>
              <p>План не изменён. Обновите данные перед повторной проверкой.</p>
            </div>
          )}
          <div className="coach-nutrition-review-actions">
            <Button type="button" variant="secondary" onClick={() => setPreview(null)}>
              Вернуться к изменениям
            </Button>
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
      {!editing && !selectedProposal && (
        <>
          <details className="top-gap">
            <summary className="yfc-disclosure-summary">
              <span>История назначений по датам и правилам</span>
              <DisclosureIcon />
            </summary>
            {assignments.isPending && <p role="status">Загружаем назначения…</p>}
            {assignments.isError && <p role="alert">Не удалось загрузить назначения.</p>}
            {!assignments.isError &&
              assignments.data &&
              assignments.data.dates.length === 0 &&
              assignments.data.schedule.length === 0 && <p>Назначений пока нет.</p>}
            {!assignments.isError &&
              assignments.data?.dates.map((row) => (
                <p key={`date-${row.target.id}`}>
                  Дата {row.date}
                  {row.day_type ? ` · ${dayTypes[row.day_type]}` : ''}: {row.target.calories} ккал ·
                  Б {row.target.protein_g} · Ж {row.target.fat_g} · У {row.target.carbs_g} г
                </p>
              ))}
            {!assignments.isError &&
              assignments.data?.schedule.map((row) => (
                <p key={`rule-${row.id}`}>
                  {scopes[row.scope]} с {row.effective_from} · {dayTypes[row.day_type]}
                  {row.week_type ? ` · ${weekTypes[row.week_type]}` : ''}: {row.target.calories}{' '}
                  ккал · Б {row.target.protein_g} · Ж {row.target.fat_g} · У {row.target.carbs_g} г
                </p>
              ))}
          </details>
          <h4>Предложения</h4>
          {list.isPending && <p role="status">Загружаем…</p>}
          {list.isError && <p role="alert">Не удалось загрузить предложения.</p>}
          {!list.isError && list.data?.length === 0 && <p>Предложений пока нет.</p>}
          {!list.isError &&
            list.data?.map((proposal) => (
              <div key={proposal.id} className="top-gap">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setSelectedProposal(proposal)}
                >
                  {labels[proposal.status]} · {proposal.target_date}
                </Button>
              </div>
            ))}
        </>
      )}
    </section>
  );
}

export function ClientNutritionProposals({
  focused = true,
  onOpen,
  onClose,
}: {
  focused?: boolean;
  onOpen?: () => void;
  onClose?: () => void;
} = {}) {
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const keys = useRef<Record<string, string>>({});
  const title = useRef<HTMLHeadingElement>(null);
  const proposals = useQuery({
    queryKey: ['my-coach-nutrition-proposals'],
    queryFn: () => api<Proposal[]>('/api/v1/coach-nutrition-proposals'),
  });
  useEffect(() => {
    if (focused && proposals.data?.length) title.current?.focus();
  }, [focused, proposals.data?.length]);
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
  if (proposals.isPending || proposals.isError || !proposals.data?.length) {
    if (!focused && !proposals.isError && !proposals.isPending) return null;
    return (
      <section className="nutrition-section-card coach-nutrition-focused">
        {focused && onClose && (
          <Button type="button" variant="secondary" onClick={onClose}>
            К питанию
          </Button>
        )}
        {proposals.isPending ? (
          <p role="status">Загружаем предложения тренера…</p>
        ) : proposals.isError ? (
          <p role="alert">Не удалось загрузить предложения тренера.</p>
        ) : (
          <p>Предложений пока нет.</p>
        )}
      </section>
    );
  }
  if (!focused) {
    return (
      <section className="nutrition-section-card coach-nutrition-entry">
        <h2>Предложения тренера</h2>
        <p>Проверьте предложенные изменения и выберите решение.</p>
        <button type="button" onClick={onOpen}>
          Открыть предложения
        </button>
      </section>
    );
  }
  return (
    <section
      className="nutrition-section-card coach-nutrition-focused"
      aria-labelledby="client-nutrition-proposals"
    >
      {onClose && (
        <Button type="button" variant="secondary" onClick={onClose}>
          К питанию
        </Button>
      )}
      <h1 id="client-nutrition-proposals" ref={title} tabIndex={-1}>
        Предложения тренера
      </h1>
      {proposals.data.map((proposal) => (
        <article key={proposal.id} className="top-gap">
          <h3>{proposal.status === 'pending' ? 'Проверьте изменения' : labels[proposal.status]}</h3>
          <Comparison proposal={proposal} />
          {decide.error && decide.variables?.proposal.id === proposal.id && (
            <div className="coach-nutrition-notice" role="alert">
              <strong>
                {(decide.error as { status?: number }).status === 409
                  ? 'Данные изменились'
                  : 'Предложение недоступно'}
              </strong>
              <p>{(decide.error as Error).message}</p>
              <p>
                {[404, 409].includes((decide.error as { status?: number }).status ?? 0)
                  ? 'План не изменён этим запросом. Обновите данные или обратитесь к тренеру.'
                  : 'Проверьте статус предложения после обновления данных.'}
              </p>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  decide.reset();
                  void proposals.refetch();
                }}
              >
                Обновить данные
              </Button>
            </div>
          )}
          {proposal.status === 'pending' &&
            !(
              decide.variables?.proposal.id === proposal.id &&
              [404, 409].includes((decide.error as { status?: number } | null)?.status ?? 0)
            ) && (
              <>
                <div className="coach-nutrition-notice">
                  <strong>Решать вам</strong>
                  <p>До вашего решения план не изменится. Прошедшие дни сохранятся.</p>
                </div>
                <div className="coach-nutrition-review-actions">
                  <button
                    type="button"
                    disabled={decide.isPending}
                    onClick={() => decide.mutate({ proposal, decision: 'accept' })}
                  >
                    Принять изменения
                  </button>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={decide.isPending}
                    onClick={() => decide.mutate({ proposal, decision: 'reject' })}
                  >
                    Отклонить
                  </Button>
                </div>
              </>
            )}
          {proposal.status === 'accepted' && (
            <p className="coach-nutrition-notice">
              Будущий план обновлён. Прошедшие дни и дневник сохранены.
            </p>
          )}
          {proposal.status === 'rejected' && (
            <p className="coach-nutrition-notice">План не изменён.</p>
          )}
        </article>
      ))}
    </section>
  );
}
