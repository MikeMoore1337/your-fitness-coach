import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import type { components } from '../../shared/api/schema';
import { invalidateNutritionSummaries } from '../../shared/queryKeys';
import {
  AUTHENTICATED_USER_ID_STORAGE_KEY,
  NUTRITION_HISTORY_RECOVERY_SESSION_KEY,
} from '../../shared/userScopedStorage';
import { Button, Field, Select, Surface } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useTelegramOverlayBackButton } from '../../shared/telegram/useTelegramOverlayBackButton';

type Preview = components['schemas']['HistoryPreview'];
type Review = components['schemas']['HistoryReview'];
type ReviewRequest = components['schemas']['HistoryReviewRequest'];
type ConfirmRequest = components['schemas']['HistoryConfirmRequest'];
type Receipt = components['schemas']['HistoryReceipt'];
type Nutrients = components['schemas']['HistoryNutritionAmount'];
type Recovery = { userId: string; draftId: string; expiresAt: number; payload: ConfirmRequest };
type Stage = 'selection' | 'issues' | 'review' | 'result';

const storageKey = NUTRITION_HISTORY_RECOVERY_SESSION_KEY;
const mealLabels: Record<string, string> = {
  breakfast: 'Завтрак',
  lunch: 'Обед',
  dinner: 'Ужин',
  snacks: 'Перекус',
};
const units: Record<string, string> = { g: 'г', ml: 'мл', piece: 'шт.', serving: 'порц.' };

export function readHistoryRecovery(): Recovery | null {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw || raw.length > 500_000) return null;
    const saved = JSON.parse(raw) as Recovery;
    const userId = sessionStorage.getItem(AUTHENTICATED_USER_ID_STORAGE_KEY);
    if (
      !userId ||
      saved.userId !== userId ||
      !Number.isSafeInteger(Number(userId)) ||
      Number(userId) <= 0 ||
      !/^[0-9a-f-]{36}$/.test(saved.draftId) ||
      !Number.isFinite(saved.expiresAt) ||
      !saved.payload ||
      saved.payload.confirmed !== true ||
      !/^[A-Za-z0-9._:-]{8,128}$/.test(saved.payload.confirm_key) ||
      !/^[a-f0-9]{64}$/.test(saved.payload.preview_signature) ||
      !/^[a-f0-9]{64}$/.test(saved.payload.review_signature)
    ) {
      sessionStorage.removeItem(storageKey);
      return null;
    }
    return saved;
  } catch {
    return null;
  }
}

function clearRecovery() {
  try {
    sessionStorage.removeItem(storageKey);
  } catch {
    // Storage is optional.
  }
}

function displayDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${value}T12:00:00Z`));
}

function displayValue(value: string | null): string {
  return value === null ? 'не указано' : value.replace('.', ',');
}

function difference(left: string | null, right: string | null): string {
  if (left === null || right === null) return 'неизвестно';
  const a = /^(\d+)(?:\.(\d+))?$/.exec(left);
  const b = /^(\d+)(?:\.(\d+))?$/.exec(right);
  if (!a || !b) return 'неизвестно';
  const scale = Math.max(a[2]?.length ?? 0, b[2]?.length ?? 0);
  const number = (parts: RegExpExecArray) =>
    BigInt(`${parts[1]}${(parts[2] ?? '').padEnd(scale, '0')}`);
  const result = number(a) - number(b);
  const digits = (result < 0n ? -result : result).toString().padStart(scale + 1, '0');
  const whole = scale ? digits.slice(0, -scale) : digits;
  const fraction = scale ? digits.slice(-scale).replace(/0+$/, '') : '';
  return `${result > 0n ? '+' : result < 0n ? '−' : ''}${whole}${fraction ? `,${fraction}` : ''}`;
}

function nutritionLine(value: Nutrients): string {
  return `${displayValue(value.energy_kcal)} ккал · Б ${displayValue(value.protein_g)} г · Ж ${displayValue(value.fat_g)} г · У ${displayValue(value.carbs_g)} г`;
}

function differenceLine(source: Nutrients, existing: Nutrients): string {
  return `ккал ${difference(source.energy_kcal, existing.energy_kcal)} · Б ${difference(source.protein_g, existing.protein_g)} г · Ж ${difference(source.fat_g, existing.fat_g)} г · У ${difference(source.carbs_g, existing.carbs_g)} г`;
}

export function NutritionHistoryImport({
  draftId,
  expiresAt,
  onBack,
  onDone,
  onClose,
}: {
  draftId: string;
  expiresAt: number;
  onBack: () => void;
  onDone: () => void;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const saved = readHistoryRecovery();
  const [pending, setPending] = useState<ConfirmRequest | null>(
    saved?.draftId === draftId ? saved.payload : null,
  );
  const [enabled, setEnabled] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [mode, setMode] = useState<ReviewRequest['mode']>('keep');
  const [selected, setSelected] = useState<number[]>([]);
  const [decisions, setDecisions] = useState<Record<number, 'add' | 'skip'>>({});
  const [review, setReview] = useState<Review | null>(null);
  const [stage, setStage] = useState<Stage>('selection');
  const [confirmed, setConfirmed] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [expired, setExpired] = useState(false);
  const [stale, setStale] = useState(false);
  const inFlight = useRef(false);
  const root = `/api/v1/nutrition/imports/${encodeURIComponent(draftId)}/history`;
  useTelegramOverlayBackButton(true, () => {
    if (!pending && !busy) onBack();
  });

  useEffect(() => {
    if (!enabled || pending) return;
    const controller = new AbortController();
    api<Preview>(root, { signal: controller.signal })
      .then((data) => {
        setPreview(data);
        setFrom(data.dates[0] ?? '');
        setTo(data.dates[data.dates.length - 1] ?? '');
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : 'Не удалось проверить историю.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [enabled, pending, root]);

  function resetPlan() {
    setReview(null);
    setDecisions({});
    setConfirmed(false);
    setError('');
  }

  async function makeReview(nextDecisions = decisions) {
    if (!preview || busy) return;
    setBusy(true);
    setError('');
    const request: ReviewRequest = {
      revision: preview.revision,
      preview_signature: preview.preview_signature,
      date_from: from,
      date_to: to,
      mode,
      selected_rows: mode === 'manual' ? selected : [],
      decisions: Object.entries(nextDecisions).map(([index, action]) => ({
        index: Number(index),
        action,
      })),
    };
    try {
      const result = await api<Review>(`${root}/review`, { method: 'POST', body: request });
      setReview(result);
      setStage(
        result.rows.some((row) => row.action === 'conflict' || row.action === 'invalid')
          ? 'issues'
          : 'review',
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось проверить изменения.');
      if (e instanceof ApiError && e.status === 409) {
        setPreview(null);
        setEnabled(false);
        setStage('selection');
        setStale(true);
      }
    } finally {
      setBusy(false);
    }
  }

  async function submit(payload: ConfirmRequest) {
    if (inFlight.current) return;
    if (expiresAt <= Date.now()) {
      setExpired(true);
      setError('Срок хранения черновика истёк. Проверьте дневник перед новым импортом.');
      return;
    }
    inFlight.current = true;
    setPending(payload);
    try {
      const userId = sessionStorage.getItem(AUTHENTICATED_USER_ID_STORAGE_KEY);
      if (userId)
        sessionStorage.setItem(storageKey, JSON.stringify({ userId, draftId, expiresAt, payload }));
    } catch {
      // Retry remains available while the screen is open.
    }
    setBusy(true);
    setError('');
    try {
      const result = await api<Receipt>(`${root}/confirm`, {
        method: 'POST',
        body: payload,
        timeoutMs: 60_000,
      });
      setReceipt(result);
      setPending(null);
      clearRecovery();
      await invalidateNutritionSummaries(queryClient);
      setStage('result');
      onDone();
    } catch (e) {
      if (
        e instanceof ApiError &&
        e.status >= 400 &&
        e.status < 500 &&
        e.status !== 408 &&
        e.status !== 429
      ) {
        setPending(null);
        clearRecovery();
        setError(e.message);
        if (e.status === 409) {
          setPreview(null);
          setEnabled(false);
          setStage('selection');
          setStale(true);
        }
      } else {
        setError('Ответ не получен. Повторите проверку прежнего подтверждения.');
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const visible =
    preview?.rows.filter(
      (row) =>
        row.source.diary_date && row.source.diary_date >= from && row.source.diary_date <= to,
    ) ?? [];
  const issues =
    review?.rows.filter((row) => row.action === 'conflict' || row.action === 'invalid') ?? [];
  const unknownContext =
    preview?.rows.filter((row) => !row.source.diary_date || !row.source.meal_type).length ?? 0;
  const unresolved = issues.some((item) => !decisions[item.index]);
  const selectedVisible = selected.filter((index) => visible.some((row) => row.index === index));
  const currentRequest: ReviewRequest | null =
    preview && review
      ? {
          revision: preview.revision,
          preview_signature: preview.preview_signature,
          date_from: from,
          date_to: to,
          mode,
          selected_rows: mode === 'manual' ? selectedVisible : [],
          decisions: Object.entries(decisions).map(([index, action]) => ({
            index: Number(index),
            action,
          })),
        }
      : null;

  if (pending) {
    return (
      <Surface className="stack">
        <h2>Проверить результат переноса</h2>
        <p>Ответ на подтверждение не получен. Повторите проверку прежнего запроса.</p>
        {error && <p role="alert">{error}</p>}
        <Button type="button" disabled={busy} onClick={() => void submit(pending)}>
          Проверить результат
        </Button>
        {expired && (
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              clearRecovery();
              setPending(null);
              onBack();
            }}
          >
            Закрыть
          </Button>
        )}
      </Surface>
    );
  }

  return (
    <div className="stack">
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">Проверяем данные…</p>}
      {stale && (
        <Surface className="stack">
          <div className="nutrition-import__history-eyebrow">Проверка изменений</div>
          <h2>Проверьте данные ещё раз</h2>
          <p>
            Не удалось подтвердить перенос. Если вы уже переносили историю, проверьте записи в
            дневнике.
          </p>
          <p className="nutrition-import__history-notice">
            <Icon name="info" size={16} /> Обновите предпросмотр и снова проверьте совпадения.
          </p>
          <Button
            type="button"
            onClick={() => {
              setStale(false);
              setError('');
              setBusy(true);
              setEnabled(true);
            }}
          >
            Обновить предпросмотр
          </Button>
          <Button type="button" variant="secondary" onClick={onBack}>
            Вернуться к импорту
          </Button>
        </Surface>
      )}
      {stage === 'selection' && !stale && (
        <Surface className="stack">
          <div className="nutrition-import__history-eyebrow">Личная история</div>
          <h2>Перенести записи в дневник</h2>
          <p>
            Отдельно от импорта продуктов в общий каталог. Дневник изменится только после
            подтверждения.
          </p>
          <label className="nutrition-import__consent nutrition-import__history-option">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => {
                setEnabled(event.target.checked);
                setBusy(event.target.checked);
                resetPlan();
              }}
            />
            <span>
              <strong>Перенести историю питания</strong>
              <br />
              <small>По умолчанию история не переносится.</small>
            </span>
          </label>
          {enabled && preview && preview.dates.length === 0 && (
            <>
              <p>Записи с датами не найдены. Проверьте файл или продолжите импорт продуктов.</p>
              <Button type="button" variant="secondary" onClick={onBack}>
                Вернуться к импорту
              </Button>
            </>
          )}
          {enabled && preview && preview.dates.length > 0 && (
            <>
              <div className="nutrition-import__history-soft">
                <strong>В файле найдены дни с записями</strong>
                <br />
                <small>
                  {preview.dates.map(displayDate).join(', ')} · дни без записей не добавятся
                </small>
              </div>
              {unknownContext > 0 && (
                <p>
                  <Icon name="warning" size={16} /> Строк без даты или приёма пищи: {unknownContext}
                  . Они не будут перенесены.
                </p>
              )}
              <div className="nutrition-import__history-dates">
                <Field label="С даты" labelFor="history-from">
                  <Select
                    id="history-from"
                    value={from}
                    onChange={(event) => {
                      const next = event.target.value;
                      setFrom(next);
                      if (next > to) setTo(next);
                      setSelected([]);
                      resetPlan();
                    }}
                  >
                    {preview.dates.map((date) => (
                      <option key={date} value={date}>
                        {date.split('-').reverse().join('.')}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="По дату" labelFor="history-to">
                  <Select
                    id="history-to"
                    value={to}
                    onChange={(event) => {
                      const next = event.target.value;
                      setTo(next);
                      if (next < from) setFrom(next);
                      setSelected([]);
                      resetPlan();
                    }}
                  >
                    {preview.dates.map((date) => (
                      <option key={date} value={date}>
                        {date.split('-').reverse().join('.')}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              <fieldset className="nutrition-import__history-options">
                <legend>Если в дневнике уже есть записи</legend>
                {(
                  [
                    [
                      'keep',
                      'Сохранить существующие записи',
                      'Пропустить приёмы пищи, в которых уже есть записи.',
                    ],
                    [
                      'add_missing',
                      'Добавить отсутствующие',
                      'Возможные совпадения потребуется проверить.',
                    ],
                    [
                      'manual',
                      'Выбрать строки вручную',
                      'Отметьте записи, которые хотите перенести.',
                    ],
                  ] as const
                ).map(([value, label, hint]) => (
                  <label
                    className="nutrition-import__consent nutrition-import__history-option"
                    key={value}
                  >
                    <input
                      type="radio"
                      name="history-mode"
                      checked={mode === value}
                      onChange={() => {
                        setMode(value);
                        resetPlan();
                      }}
                    />
                    <span>
                      <strong>{label}</strong>
                      <br />
                      <small>{hint}</small>
                    </span>
                  </label>
                ))}
              </fieldset>
              {mode === 'manual' && (
                <div className="stack">
                  {visible.map((row) => (
                    <label
                      className="nutrition-import__consent nutrition-import__history-option"
                      key={row.index}
                    >
                      <input
                        type="checkbox"
                        checked={selected.includes(row.index)}
                        onChange={(event) => {
                          setSelected(
                            event.target.checked
                              ? [...selected, row.index]
                              : selected.filter((item) => item !== row.index),
                          );
                          resetPlan();
                        }}
                      />
                      <span>
                        {row.source.diary_date && displayDate(row.source.diary_date)} ·{' '}
                        {mealLabels[row.source.meal_type ?? ''] ?? 'Приём пищи не указан'} ·{' '}
                        {row.source.food.name} · {row.source.quantity ?? 'не указано'}{' '}
                        {units[row.source.amount_unit ?? ''] ?? row.source.source_unit ?? ''}
                        <br />
                        <small>{nutritionLine(row.nutrition_amount)}</small>
                      </span>
                    </label>
                  ))}
                </div>
              )}
              <div className="nutrition-import__history-actions">
                <Button type="button" variant="secondary" onClick={onBack}>
                  Отмена
                </Button>
                <Button
                  type="button"
                  disabled={busy || (mode === 'manual' && selectedVisible.length === 0)}
                  onClick={() => void makeReview()}
                >
                  Проверить изменения
                </Button>
              </div>
            </>
          )}
          {!enabled && (
            <Button type="button" variant="secondary" onClick={onBack}>
              Назад к импорту
            </Button>
          )}
        </Surface>
      )}
      {stage === 'issues' && preview && (
        <Surface className="stack">
          <div className="nutrition-import__history-eyebrow">Нужно проверить · {issues.length}</div>
          <h2>Похожие записи и недостающие данные</h2>
          {issues.map((issue) => {
            const row = preview.rows.find((item) => item.index === issue.index);
            if (!row) return null;
            const existing = preview.existing_meals.find(
              (meal) =>
                meal.date === row.source.diary_date && meal.meal_type === row.source.meal_type,
            );
            const normalize = (value: string) =>
              value.trim().replace(/\s+/g, ' ').toLocaleLowerCase('ru-RU');
            const namedMatches =
              existing?.entries.filter(
                (entry) => normalize(entry.food_name) === normalize(row.source.food.name),
              ) ?? [];
            const matches = namedMatches.length ? namedMatches : (existing?.entries ?? []);
            const fileMatches = preview.rows.filter(
              (other) =>
                other.index !== row.index &&
                other.source.diary_date === row.source.diary_date &&
                other.source.meal_type === row.source.meal_type &&
                normalize(other.source.food.name) === normalize(row.source.food.name) &&
                other.source.quantity === row.source.quantity &&
                other.source.amount_unit === row.source.amount_unit,
            );
            return (
              <div className="nutrition-import__history-issue stack" key={row.index}>
                <strong>
                  {row.source.diary_date && displayDate(row.source.diary_date)} ·{' '}
                  {mealLabels[row.source.meal_type ?? ''] ?? 'Приём пищи не указан'}
                </strong>
                <div className="nutrition-import__history-soft">
                  <small>В файле</small>
                  <p>
                    {row.source.food.name} · {row.source.quantity ?? 'не указано'}{' '}
                    {units[row.source.amount_unit ?? ''] ?? row.source.source_unit ?? ''}
                    <br />
                    {nutritionLine(row.nutrition_amount)}
                  </p>
                </div>
                {matches.map((entry) => (
                  <div className="nutrition-import__history-soft" key={entry.id}>
                    <small>Уже в дневнике</small>
                    <p>
                      {entry.food_name} · {entry.amount}{' '}
                      {entry.serving_unit === 'piece'
                        ? 'шт.'
                        : (units[entry.amount_unit] ?? entry.amount_unit)}
                      <br />
                      {nutritionLine(entry.nutrition)}
                      <br />
                      Разница: {differenceLine(row.nutrition_amount, entry.nutrition)}
                    </p>
                  </div>
                ))}
                {fileMatches.map((other) => (
                  <div className="nutrition-import__history-soft" key={other.index}>
                    <small>Другая строка файла</small>
                    <p>
                      {other.source.food.name} · {other.source.quantity ?? 'не указано'}{' '}
                      {units[other.source.amount_unit ?? ''] ?? other.source.source_unit ?? ''}
                      <br />
                      {nutritionLine(other.nutrition_amount)}
                    </p>
                  </div>
                ))}
                {issue.action === 'invalid' ? (
                  <p className="nutrition-import__history-notice">
                    <Icon name="warning" size={16} />{' '}
                    {issue.reason === 'day_status_conflict'
                      ? 'День отмечен как заполненный или голодание. Сначала измените его статус в дневнике.'
                      : 'Не хватает данных для переноса. Неизвестные значения не заменяются нулями.'}
                  </p>
                ) : (
                  <p className="nutrition-import__history-notice">
                    <Icon name="info" size={16} /> Похожие записи могут быть отдельными
                    употреблениями. Существующие записи не изменятся.
                  </p>
                )}
                <label className="nutrition-import__consent nutrition-import__history-option">
                  <input
                    type="radio"
                    name={`history-choice-${row.index}`}
                    checked={decisions[row.index] === 'skip'}
                    onChange={() => setDecisions({ ...decisions, [row.index]: 'skip' })}
                  />
                  <span>Пропустить строку из файла</span>
                </label>
                {issue.action === 'conflict' && (
                  <label className="nutrition-import__consent nutrition-import__history-option">
                    <input
                      type="radio"
                      name={`history-choice-${row.index}`}
                      checked={decisions[row.index] === 'add'}
                      onChange={() => setDecisions({ ...decisions, [row.index]: 'add' })}
                    />
                    <span>Добавить как отдельное употребление</span>
                  </label>
                )}
              </div>
            );
          })}
          <div className="nutrition-import__history-actions">
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setStage('selection');
                resetPlan();
              }}
            >
              Назад
            </Button>
            <Button type="button" disabled={busy || unresolved} onClick={() => void makeReview()}>
              Продолжить
            </Button>
          </div>
        </Surface>
      )}
      {stage === 'review' && review && currentRequest && (
        <Surface className="stack">
          <div className="nutrition-import__history-eyebrow">Перед подтверждением</div>
          <h2>Проверьте перенос</h2>
          <p>
            Выбраны записи за {displayDate(from)} — {displayDate(to)}. Дни без записей не добавятся.
          </p>
          <p className="nutrition-import__history-soft">
            Будет добавлено: {review.rows.filter((row) => row.action === 'add').length}. Пропущено:{' '}
            {
              review.rows.filter(
                (row) => row.action === 'skip' && row.reason !== 'outside_selection',
              ).length
            }
            . Решено конфликтов: {review.rows.filter((row) => row.conflict).length}.
          </p>
          <p className="nutrition-import__history-notice">
            <Icon name="info" size={16} /> Дни не будут автоматически отмечены как заполненные.
            Существующие записи сохранятся.
          </p>
          <label className="nutrition-import__consent nutrition-import__history-option">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            <span>Подтверждаю перенос выбранных записей в личный дневник.</span>
          </label>
          <div className="nutrition-import__history-actions">
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setStage('selection');
                resetPlan();
              }}
            >
              Назад
            </Button>
            <Button
              type="button"
              disabled={!confirmed || busy}
              onClick={() =>
                void submit({
                  ...currentRequest,
                  review_signature: review.review_signature,
                  confirm_key: crypto.randomUUID(),
                  confirmed: true,
                })
              }
            >
              Перенести историю
            </Button>
          </div>
        </Surface>
      )}
      {stage === 'result' && receipt && (
        <Surface className="stack">
          <div className="nutrition-import__history-eyebrow">Готово</div>
          <h2>История перенесена</h2>
          <p className="nutrition-import__history-soft">
            Добавлено: {receipt.added} · Пропущено: {receipt.skipped} · Конфликтов проверено:{' '}
            {receipt.conflicts}
          </p>
          <p>Дни не отмечены как заполненные автоматически. Проверьте записи в дневнике.</p>
          <Button type="button" onClick={onClose}>
            Открыть дневник
          </Button>
          <Button type="button" variant="secondary" onClick={onBack}>
            Вернуться к импорту
          </Button>
        </Surface>
      )}
    </div>
  );
}
