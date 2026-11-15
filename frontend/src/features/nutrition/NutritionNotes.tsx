import { useEffect, useState } from 'react';
import {
  api,
  AUTH_ACCOUNT_SWITCH_EVENT,
  AUTH_LOGOUT_EVENT,
  AUTH_VERIFIED_LOGIN_EVENT,
} from '../../shared/api/client';
import { Button } from '../../shared/ui/common';
import type { MealType } from './FoodPickerDialog';

type ConsentStatus = 'enabled' | 'disabled' | 'revoked' | 'recovery_hold';
type Feeling = 'none' | 'low' | 'medium' | 'high';
type Energy = 'low' | 'normal' | 'high';
type Note = {
  meal_type: MealType;
  hunger_before: Feeling | null;
  fullness_after: Feeling | null;
  energy: Energy | null;
  note: string | null;
};

export function useNutritionNotesConsent(available: boolean) {
  const [status, setStatus] = useState<ConsentStatus | null>(null);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  useEffect(() => {
    const reset = () => {
      setStatus(null);
      setRevision((value) => value + 1);
    };
    window.addEventListener(AUTH_ACCOUNT_SWITCH_EVENT, reset);
    window.addEventListener(AUTH_LOGOUT_EVENT, reset);
    window.addEventListener(AUTH_VERIFIED_LOGIN_EVENT, reset);
    return () => {
      window.removeEventListener(AUTH_ACCOUNT_SWITCH_EVENT, reset);
      window.removeEventListener(AUTH_LOGOUT_EVENT, reset);
      window.removeEventListener(AUTH_VERIFIED_LOGIN_EVENT, reset);
    };
  }, []);
  useEffect(() => {
    if (!available) return;
    const controller = new AbortController();
    api<{ status: ConsentStatus }>('/api/v1/nutrition-notes/consent', {
      signal: controller.signal,
    })
      .then((result) => setStatus(result.status))
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError((reason as Error).message);
      });
    return () => controller.abort();
  }, [available, revision]);
  const change = async (action: 'enable' | 'disable' | 'revoke') => {
    if (action === 'revoke' && !window.confirm('Отозвать согласие и удалить все личные отметки?'))
      return;
    setPending(true);
    setError('');
    try {
      const result = await api<{ status: ConsentStatus }>(
        `/api/v1/nutrition-notes/consent/${action}`,
        { method: 'POST' },
      );
      setStatus(result.status);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setPending(false);
    }
  };
  const refresh = () => {
    setStatus(null);
    setError('');
    setRevision((value) => value + 1);
  };
  return { status, change, error, pending, refresh };
}

export function NutritionNotesControls({
  consent,
}: {
  consent: ReturnType<typeof useNutritionNotesConsent>;
}) {
  const { status, change, error, pending, refresh } = consent;
  if (status === null && !error) return null;
  if (status === null)
    return (
      <div role="alert">
        {error}{' '}
        <Button type="button" variant="secondary" onClick={refresh}>
          Повторить загрузку
        </Button>
      </div>
    );
  return (
    <div className="nutrition-notes-controls">
      <strong>Личные отметки</strong>
      <p>По желанию · только для вас. Тренер и ИИ не получают отметки.</p>
      {status === 'recovery_hold' ? (
        <p role="status">
          После восстановления отметки временно недоступны до проверки. Вы можете отозвать согласие
          и удалить их.
        </p>
      ) : status !== 'enabled' ? (
        <>
          <p>
            Включая отметки, вы соглашаетесь на сохранение личных ощущений и заметки. Согласие можно
            отозвать.
          </p>
          <Button
            type="button"
            variant="secondary"
            disabled={pending}
            onClick={() => void change('enable')}
          >
            Включить личные отметки
          </Button>
        </>
      ) : (
        <Button
          type="button"
          variant="secondary"
          disabled={pending}
          onClick={() => void change('disable')}
        >
          Отключить отметки
        </Button>
      )}
      {status !== null && status !== 'revoked' && (
        <Button
          type="button"
          variant="secondary"
          disabled={pending}
          onClick={() => void change('revoke')}
        >
          Отозвать согласие и удалить отметки
        </Button>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}

const feelings: [Feeling, string][] = [
  ['none', 'Нет'],
  ['low', 'Слабо'],
  ['medium', 'Средне'],
  ['high', 'Сильно'],
];
const energies: [Energy, string][] = [
  ['low', 'Мало'],
  ['normal', 'Обычно'],
  ['high', 'Много'],
];

export function NutritionMealNotes({ date, meal }: { date: string; meal: MealType }) {
  const [hunger, setHunger] = useState<Feeling | null>(null);
  const [fullness, setFullness] = useState<Feeling | null>(null);
  const [energy, setEnergy] = useState<Energy | null>(null);
  const [note, setNote] = useState('');
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [loadRevision, setLoadRevision] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const path = `/api/v1/nutrition-notes/${date}/${meal}`;
  useEffect(() => {
    const controller = new AbortController();
    api<Note[]>(`/api/v1/nutrition-notes/${date}`, { signal: controller.signal })
      .then((notes) => {
        const record = notes.find((item) => item.meal_type === meal);
        setHunger(record?.hunger_before ?? null);
        setFullness(record?.fullness_after ?? null);
        setEnergy(record?.energy ?? null);
        setNote(record?.note ?? '');
        setSaved(Boolean(record));
        setLoaded(true);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError((reason as Error).message);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [date, meal, loadRevision]);
  const save = async (remove = false) => {
    if (remove && !window.confirm('Удалить эту личную отметку? Продукты останутся в дневнике.'))
      return;
    setPending(true);
    setError('');
    try {
      if (remove) {
        await api(path, { method: 'DELETE' });
        setHunger(null);
        setFullness(null);
        setEnergy(null);
        setNote('');
        setSaved(false);
      } else {
        const result = await api<Note | null>(path, {
          method: 'PUT',
          body: { hunger_before: hunger, fullness_after: fullness, energy, note: note || null },
        });
        setSaved(Boolean(result));
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setPending(false);
    }
  };
  if (loading) return <p role="status">Загружаем личные отметки…</p>;
  if (!loaded)
    return (
      <div role="alert">
        {error}{' '}
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            setLoading(true);
            setError('');
            setLoadRevision((value) => value + 1);
          }}
        >
          Повторить загрузку
        </Button>
      </div>
    );
  return (
    <div className="nutrition-personal-notes">
      <strong>Ощущения во время еды</strong>
      <p>Лично для вас · можно пропустить любое поле. Повторное нажатие снимает выбор.</p>
      <fieldset disabled={pending}>
        <legend>Голод до еды · необязательно</legend>
        <div className="nutrition-personal-notes__choices">
          {feelings.map(([value, label]) => (
            <Button
              type="button"
              variant="secondary"
              data-yfc-choice="compact"
              aria-pressed={hunger === value}
              key={value}
              onClick={() => setHunger(hunger === value ? null : value)}
            >
              {label}
            </Button>
          ))}
        </div>
      </fieldset>
      <fieldset disabled={pending}>
        <legend>Сытость после · необязательно</legend>
        <div className="nutrition-personal-notes__choices">
          {feelings.map(([value, label]) => (
            <Button
              type="button"
              variant="secondary"
              data-yfc-choice="compact"
              aria-pressed={fullness === value}
              key={value}
              onClick={() => setFullness(fullness === value ? null : value)}
            >
              {label}
            </Button>
          ))}
        </div>
      </fieldset>
      <fieldset disabled={pending}>
        <legend>Энергия · необязательно</legend>
        <div className="nutrition-personal-notes__choices">
          {energies.map(([value, label]) => (
            <Button
              type="button"
              variant="secondary"
              data-yfc-choice="compact"
              aria-pressed={energy === value}
              key={value}
              onClick={() => setEnergy(energy === value ? null : value)}
            >
              {label}
            </Button>
          ))}
        </div>
      </fieldset>
      <label>
        Короткая заметка · необязательно
        <textarea
          value={note}
          maxLength={500}
          disabled={pending}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <div className="nutrition-personal-notes__actions">
        <Button type="button" disabled={pending} onClick={() => void save()}>
          Сохранить отметки
        </Button>
        {saved && (
          <Button
            type="button"
            variant="secondary"
            disabled={pending}
            onClick={() => void save(true)}
          >
            Удалить отметку
          </Button>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
