import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { HydrationDay, HydrationEntry, HydrationPreset, User } from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { haptic } from '../../shared/telegram/useTelegram';
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
import { productEventSurface, trackCoreProductEvent } from '../../shared/analytics/productEvents';

const beverageLabels: Record<string, string> = {
  water: 'Вода',
  tea: 'Чай',
  coffee: 'Кофе',
  milk: 'Молоко',
  juice: 'Сок',
  other: 'Другой напиток',
};

function requestKey(prefix: string): string {
  const suffix = crypto.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  return `${prefix}-${suffix}`;
}

function localDateTimeValue(value: string, timeZone: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(value));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`;
}

function HydrationEntryRow({ entry, onChanged }: { entry: HydrationEntry; onChanged(): void }) {
  const { confirm, toast } = useFeedback();
  const [editing, setEditing] = useState(false);
  const [volume, setVolume] = useState(String(entry.volume_ml));
  const [beverageType, setBeverageType] = useState(entry.beverage_type);
  const [occurredAt, setOccurredAt] = useState(
    localDateTimeValue(entry.occurred_at, entry.timezone),
  );
  const update = useMutation({
    mutationFn: () =>
      api<HydrationEntry>(`/api/v1/nutrition/hydration/entries/${entry.id}`, {
        method: 'PATCH',
        body: {
          volume_ml: Number(volume),
          beverage_type: beverageType,
          occurred_at: occurredAt,
        },
      }),
    onSuccess: () => {
      setEditing(false);
      onChanged();
      toast('Запись обновлена');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const remove = useMutation({
    mutationFn: () =>
      api<void>(`/api/v1/nutrition/hydration/entries/${entry.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      onChanged();
      toast('Запись удалена');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  const requestDelete = async () => {
    const approved = await confirm({
      title: 'Удалить напиток?',
      message: `${entry.volume_ml} мл исчезнет из истории гидратации.`,
      confirmText: 'Удалить',
    });
    if (approved) remove.mutate();
  };

  return (
    <li className="hydration-entry">
      {editing ? (
        <div className="hydration-entry__editor">
          <Field label="Объём, мл" labelFor={`hydration-volume-${entry.id}`}>
            <Input
              id={`hydration-volume-${entry.id}`}
              inputMode="numeric"
              min="1"
              max="5000"
              type="number"
              value={volume}
              onChange={(event) => setVolume(event.target.value)}
            />
          </Field>
          <Field label="Напиток" labelFor={`hydration-kind-${entry.id}`}>
            <Select
              id={`hydration-kind-${entry.id}`}
              value={beverageType}
              onChange={(event) => setBeverageType(event.target.value as typeof beverageType)}
            >
              {Object.entries(beverageLabels).map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Дата и время" labelFor={`hydration-time-${entry.id}`}>
            <Input
              id={`hydration-time-${entry.id}`}
              type="datetime-local"
              value={occurredAt}
              onChange={(event) => setOccurredAt(event.target.value)}
            />
          </Field>
          <div className="hydration-entry__actions">
            <Button
              disabled={update.isPending || !volume || !occurredAt}
              type="button"
              onClick={() => update.mutate()}
            >
              {update.isPending ? 'Сохраняем…' : 'Сохранить'}
            </Button>
            <Button variant="secondary" type="button" onClick={() => setEditing(false)}>
              Отмена
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div>
            <strong>{entry.volume_ml} мл</strong>
            <span>{beverageLabels[entry.beverage_type]}</span>
          </div>
          <time dateTime={entry.occurred_at}>
            {new Intl.DateTimeFormat('ru-RU', {
              hour: '2-digit',
              minute: '2-digit',
              timeZone: entry.timezone,
            }).format(new Date(entry.occurred_at))}
          </time>
          <div className="hydration-entry__actions">
            <Button variant="secondary" type="button" onClick={() => setEditing(true)}>
              Изменить
            </Button>
            <Button variant="danger" type="button" onClick={() => void requestDelete()}>
              Удалить
            </Button>
          </div>
        </>
      )}
    </li>
  );
}

export function HydrationTracker({
  diaryDate,
  initialExpanded = false,
}: {
  diaryDate: string;
  initialExpanded?: boolean;
}) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const [expanded, setExpanded] = useState(initialExpanded);
  const [customVolume, setCustomVolume] = useState('');
  const [beverageType, setBeverageType] = useState('water');
  const [undoEntry, setUndoEntry] = useState<HydrationEntry | null>(null);
  const [goalModeDraft, setGoalMode] = useState<'reference' | 'manual' | null>(null);
  const [sexDraft, setSex] = useState<'male' | 'female' | null>();
  const [adultConfirmedDraft, setAdultConfirmed] = useState<boolean>();
  const [manualGoalDraft, setManualGoal] = useState<string>();
  const [saveSex, setSaveSex] = useState(false);
  const [presetName, setPresetName] = useState('');
  const [presetVolume, setPresetVolume] = useState('');
  const hydration = useQuery({
    queryKey: queryKeys.nutrition.hydrationDate(diaryDate),
    queryFn: () => api<HydrationDay>(`/api/v1/nutrition/hydration?diary_date=${diaryDate}`),
  });
  const profile = useQuery({
    queryKey: ['me'],
    queryFn: () => api<User>('/api/v1/me'),
  });
  const loadedGoal = hydration.data?.goal;
  const loadedGoalIsReference = loadedGoal?.source === 'national_academies_beverages';
  const goalMode = goalModeDraft ?? (loadedGoal && !loadedGoalIsReference ? 'manual' : 'reference');
  const sex =
    sexDraft !== undefined
      ? sexDraft
      : loadedGoalIsReference && (loadedGoal.sex === 'male' || loadedGoal.sex === 'female')
        ? loadedGoal.sex
        : null;
  const adultConfirmed =
    adultConfirmedDraft ?? (loadedGoalIsReference && Boolean(loadedGoal.adult_confirmed));
  const manualGoal = manualGoalDraft ?? String(loadedGoal?.target_ml ?? 2200);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.nutrition.hydration }),
      queryClient.invalidateQueries({ queryKey: queryKeys.progress.summaries }),
    ]);
  };
  const add = useMutation({
    mutationFn: ({
      volume,
      kind,
      source,
      key,
    }: {
      volume: number;
      kind: string;
      source: string;
      key: string;
    }) =>
      api<HydrationEntry>('/api/v1/nutrition/hydration/entries', {
        method: 'POST',
        headers: { 'Idempotency-Key': key },
        body: {
          volume_ml: volume,
          beverage_type: kind,
          diary_date: diaryDate,
          source,
        },
      }),
    onSuccess: async (entry) => {
      setUndoEntry(entry);
      setCustomVolume('');
      await refresh();
      trackCoreProductEvent(
        { name: 'hydration_logged', surface: productEventSurface() },
        'hydration_logged',
      );
      haptic('success');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const undo = useMutation({
    mutationFn: (entryId: number) =>
      api<void>(`/api/v1/nutrition/hydration/entries/${entryId}`, { method: 'DELETE' }),
    onSuccess: async () => {
      setUndoEntry(null);
      await refresh();
      toast('Добавление отменено');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const saveGoal = useMutation({
    mutationFn: (key: string) =>
      api('/api/v1/nutrition/hydration/goal', {
        method: 'POST',
        headers: { 'Idempotency-Key': key },
        body: {
          enabled: true,
          source: goalMode === 'reference' ? 'national_academies_beverages' : 'manual',
          target_ml: goalMode === 'manual' ? Number(manualGoal) : null,
          sex: goalMode === 'reference' ? sex : null,
          adult_confirmed: goalMode === 'reference' ? adultConfirmed : null,
          save_sex_to_profile: goalMode === 'reference' && saveSex,
        },
      }),
    onSuccess: async () => {
      await refresh();
      toast('Ориентир гидратации сохранён');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const disableGoal = useMutation({
    mutationFn: () =>
      api('/api/v1/nutrition/hydration/goal', {
        method: 'POST',
        headers: { 'Idempotency-Key': requestKey('hydration-goal-off') },
        body: { enabled: false, source: 'manual' },
      }),
    onSuccess: async () => {
      await refresh();
      toast('Ориентир выключен, история сохранена');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const savePreset = useMutation({
    mutationFn: () =>
      api<HydrationPreset>('/api/v1/nutrition/hydration/presets', {
        method: 'POST',
        body: {
          label: presetName,
          volume_ml: Number(presetVolume),
          beverage_type: beverageType,
        },
      }),
    onSuccess: async () => {
      setPresetName('');
      setPresetVolume('');
      await refresh();
      toast('Ёмкость добавлена');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const removePreset = useMutation({
    mutationFn: (presetId: number) =>
      api<void>(`/api/v1/nutrition/hydration/presets/${presetId}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await refresh();
      toast('Ёмкость удалена');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  const currentSex = profile.data?.profile?.sex;

  if (hydration.isLoading) {
    return (
      <section className="hydration-card">
        <LoadingState label="Загружаем гидратацию…" />
      </section>
    );
  }
  if (hydration.error || !hydration.data) {
    return (
      <section className="hydration-card">
        <ErrorState
          message={(hydration.error as Error).message}
          retry={() => void hydration.refetch()}
        />
      </section>
    );
  }

  const data = hydration.data;
  const target = data.goal?.enabled ? data.goal.target_ml : null;
  const progress = Math.min(data.progress_percent ?? 0, 100);
  return (
    <section className="hydration-card" aria-label="Гидратация">
      <header className="hydration-card__header">
        <div>
          <span className="eyebrow">Гидратация</span>
          <h2 id="hydration-title">Напитки</h2>
          <p>{target ? `${data.total_ml} из ${target} мл` : `${data.total_ml} мл записано`}</p>
        </div>
        <div className="hydration-orb" aria-hidden="true">
          <span style={{ height: `${progress}%` }} />
          <strong>{target ? `${Math.round(data.progress_percent ?? 0)}%` : 'H₂O'}</strong>
        </div>
      </header>
      <div
        className="hydration-progress"
        role={target ? 'progressbar' : undefined}
        aria-label={target ? 'Прогресс гидратации' : undefined}
        aria-hidden={target ? undefined : true}
        aria-valuemin={0}
        aria-valuemax={target ?? undefined}
        aria-valuenow={target ? Math.min(data.total_ml, target) : undefined}
        aria-valuetext={
          target ? `${data.total_ml} из ${target} миллилитров` : `${data.total_ml} миллилитров`
        }
      >
        <span style={{ width: `${progress}%` }} />
      </div>
      <div className="hydration-presets" aria-label="Быстро добавить напиток">
        {data.presets.map((preset) => (
          <Button
            variant="secondary"
            disabled={add.isPending}
            key={`${preset.id ?? 'default'}-${preset.label}`}
            type="button"
            onClick={() =>
              add.mutate({
                volume: preset.volume_ml,
                kind: preset.beverage_type,
                source: 'quick_preset',
                key: requestKey('hydration-entry'),
              })
            }
          >
            <span>{preset.label}</span>
            <strong>+{preset.volume_ml} мл</strong>
          </Button>
        ))}
      </div>
      {undoEntry && (
        <div className="hydration-undo" role="status">
          <span>Добавлено {undoEntry.volume_ml} мл</span>
          <Button variant="secondary" type="button" onClick={() => undo.mutate(undoEntry.id)}>
            Отменить
          </Button>
        </div>
      )}
      {add.isError && add.variables && (
        <div className="hydration-mutation-error" role="alert">
          <span>{add.error.message}</span>
          <Button variant="secondary" type="button" onClick={() => add.mutate(add.variables)}>
            Повторить без дубля
          </Button>
        </div>
      )}
      <Button
        aria-expanded={expanded}
        className="hydration-expand"
        variant="secondary"
        type="button"
        onClick={() => setExpanded((value) => !value)}
      >
        {expanded ? 'Скрыть детали' : 'Другой напиток, история и цель'}
      </Button>
      {expanded && (
        <div className="hydration-details">
          <section aria-labelledby="hydration-custom-title">
            <h3 id="hydration-custom-title">Другой объём</h3>
            <div className="hydration-form-row">
              <Field label="Объём, мл" labelFor="hydration-custom-volume">
                <Input
                  id="hydration-custom-volume"
                  inputMode="numeric"
                  min="1"
                  max="5000"
                  type="number"
                  value={customVolume}
                  onChange={(event) => setCustomVolume(event.target.value)}
                />
              </Field>
              <Field label="Напиток" labelFor="hydration-custom-kind">
                <Select
                  id="hydration-custom-kind"
                  value={beverageType}
                  onChange={(event) => setBeverageType(event.target.value)}
                >
                  {Object.entries(beverageLabels).map(([value, label]) => (
                    <option value={value} key={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button
                disabled={add.isPending || !customVolume}
                type="button"
                onClick={() =>
                  add.mutate({
                    volume: Number(customVolume),
                    kind: beverageType,
                    source: 'manual',
                    key: requestKey('hydration-entry'),
                  })
                }
              >
                {add.isPending ? 'Добавляем…' : 'Добавить'}
              </Button>
            </div>
            <p className="hydration-note">
              Запись напитка не изменяет калории и кофеин в дневнике питания.
            </p>
          </section>

          <section aria-labelledby="hydration-goal-title">
            <h3 id="hydration-goal-title">Личный ориентир</h3>
            <div
              className="hydration-choice"
              role="radiogroup"
              aria-label="Способ задания ориентира"
            >
              <label>
                <input
                  type="radio"
                  checked={goalMode === 'reference'}
                  onChange={() => setGoalMode('reference')}
                />{' '}
                По справочному ориентиру
              </label>
              <label>
                <input
                  type="radio"
                  checked={goalMode === 'manual'}
                  onChange={() => setGoalMode('manual')}
                />{' '}
                Вручную
              </label>
            </div>
            {goalMode === 'reference' ? (
              <div className="hydration-goal-fields">
                <Field label="Пол для справочного ориентира" labelFor="hydration-sex">
                  <Select
                    id="hydration-sex"
                    value={sex ?? ''}
                    onChange={(event) => setSex(event.target.value as 'male' | 'female')}
                  >
                    <option value="" disabled>
                      Выберите пол для расчёта
                    </option>
                    <option value="female">Женский — 2200 мл напитков</option>
                    <option value="male">Мужской — 3000 мл напитков</option>
                  </Select>
                </Field>
                <div className="hydration-profile-checks">
                  <label className="hydration-check hydration-check--adult">
                    <input
                      type="checkbox"
                      checked={adultConfirmed}
                      onChange={(event) => setAdultConfirmed(event.target.checked)}
                    />{' '}
                    <span>Мне 18 лет или больше</span>
                  </label>
                  {!currentSex && (
                    <label className="hydration-check">
                      <input
                        type="checkbox"
                        checked={saveSex}
                        onChange={(event) => setSaveSex(event.target.checked)}
                      />{' '}
                      <span>Сохранить выбранный пол в профиле</span>
                    </label>
                  )}
                </div>
                <p className="hydration-note">
                  Ориентир относится к напиткам для здоровых взрослых в обычных условиях. Еда даёт
                  дополнительную воду; жара, нагрузка, беременность и медицинские состояния требуют
                  индивидуального подхода.
                </p>
              </div>
            ) : (
              <Field label="Ориентир, мл в день" labelFor="hydration-manual-goal">
                <Input
                  id="hydration-manual-goal"
                  inputMode="numeric"
                  min="250"
                  max="10000"
                  type="number"
                  value={manualGoal}
                  onChange={(event) => setManualGoal(event.target.value)}
                />
              </Field>
            )}
            <div className="hydration-entry__actions">
              <Button
                disabled={
                  saveGoal.isPending || (goalMode === 'reference' && (!adultConfirmed || !sex))
                }
                type="button"
                onClick={() => saveGoal.mutate(requestKey('hydration-goal'))}
              >
                {saveGoal.isPending ? 'Сохраняем…' : 'Сохранить ориентир'}
              </Button>
              {data.goal?.enabled && (
                <Button variant="secondary" type="button" onClick={() => disableGoal.mutate()}>
                  Выключить
                </Button>
              )}
            </div>
            {saveGoal.isError && saveGoal.variables && (
              <div className="hydration-mutation-error" role="alert">
                <span>{saveGoal.error.message}</span>
                <Button
                  variant="secondary"
                  type="button"
                  onClick={() => saveGoal.mutate(saveGoal.variables)}
                >
                  Повторить сохранение
                </Button>
              </div>
            )}
          </section>

          <section aria-labelledby="hydration-presets-title">
            <h3 id="hydration-presets-title">Мои кружки и бутылки</h3>
            <div className="hydration-form-row">
              <Field label="Название" labelFor="hydration-preset-name">
                <Input
                  id="hydration-preset-name"
                  maxLength={40}
                  value={presetName}
                  onChange={(event) => setPresetName(event.target.value)}
                />
              </Field>
              <Field label="Объём, мл" labelFor="hydration-preset-volume">
                <Input
                  id="hydration-preset-volume"
                  inputMode="numeric"
                  min="1"
                  max="5000"
                  type="number"
                  value={presetVolume}
                  onChange={(event) => setPresetVolume(event.target.value)}
                />
              </Field>
              <Button
                variant="secondary"
                disabled={!presetName.trim() || !presetVolume || savePreset.isPending}
                type="button"
                onClick={() => savePreset.mutate()}
              >
                Добавить
              </Button>
            </div>
            {data.presets.some((preset) => !preset.is_default) && (
              <ul className="hydration-custom-presets" aria-label="Добавленные кружки и бутылки">
                {data.presets
                  .filter((preset) => !preset.is_default && preset.id != null)
                  .map((preset) => (
                    <li key={preset.id}>
                      <span>
                        {preset.label} · {preset.volume_ml} мл
                      </span>
                      <Button
                        variant="danger"
                        disabled={removePreset.isPending}
                        type="button"
                        onClick={() => removePreset.mutate(preset.id as number)}
                      >
                        Удалить
                      </Button>
                    </li>
                  ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="hydration-history-title">
            <h3 id="hydration-history-title">История за день</h3>
            {data.entries.length === 0 ? (
              <EmptyState
                title="Напитков пока нет"
                text="Быстро добавьте стакан или укажите другой объём."
              />
            ) : (
              <ul className="hydration-history">
                {data.entries.map((entry) => (
                  <HydrationEntryRow
                    entry={entry}
                    key={entry.id}
                    onChanged={() => void refresh()}
                  />
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
