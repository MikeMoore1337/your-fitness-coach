import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, authDiscardChanged, authDiscardSnapshot } from '../../shared/api/client';
import type { HydrationDay, HydrationEntry, HydrationPreset, User } from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { haptic } from '../../shared/telegram/useTelegram';
import {
  Button,
  DisclosureIcon,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Select,
} from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Icon } from '../../shared/ui/Icon';
import { productEventSurface, trackCoreProductEvent } from '../../shared/analytics/productEvents';
import { getApiRuntime, useRuntime } from '../../shared/runtime/runtime';
import { AUTHENTICATED_USER_ID_STORAGE_KEY } from '../../shared/userScopedStorage';
import {
  HYDRATION_PENDING_EVENT,
  demoHydrationScope,
  pendingStorageKey,
  readPendingHydration,
  withPendingHydration,
  writePendingHydration,
  type HydrationAddRequest as AddRequest,
  type PendingHydration,
} from './hydrationPending';

const beverageLabels: Record<string, string> = {
  water: 'Вода',
  tea: 'Чай',
  coffee: 'Кофе',
  milk: 'Молоко',
  juice: 'Сок',
  other: 'Другой напиток',
};

type AuthDiscard = ReturnType<typeof authDiscardSnapshot> & { userId?: number };

function accountHydrationScope(): string | null {
  try {
    const id = Number(sessionStorage.getItem(AUTHENTICATED_USER_ID_STORAGE_KEY));
    return Number.isSafeInteger(id) && id > 0 ? `user_${id}` : null;
  } catch {
    return null;
  }
}

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

function hydrationEntryCountLabel(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return 'запись';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'записи';
  return 'записей';
}

function deleteHydrationEntry(
  entry: HydrationEntry,
  mode: 'undo' | 'delete',
  demoGeneration?: number,
) {
  return api<void>(`/api/v1/nutrition/hydration/entries/${entry.id}-${mode}`, {
    method: 'DELETE',
    body: {
      created_at: entry.created_at,
      updated_at: entry.updated_at,
      diary_date: entry.diary_date,
      ...(demoGeneration === undefined ? {} : { _hydration_generation: demoGeneration }),
    },
  });
}

function HydrationEntryRow({
  entry,
  demoGeneration,
  onChanged,
}: {
  entry: HydrationEntry;
  demoGeneration?: number;
  onChanged(): void;
}) {
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
    mutationFn: () => deleteHydrationEntry(entry, 'delete', demoGeneration),
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
            <span>
              {beverageLabels[entry.beverage_type]} ·{' '}
              <time dateTime={entry.occurred_at}>
                {new Intl.DateTimeFormat('ru-RU', {
                  hour: '2-digit',
                  minute: '2-digit',
                  timeZone: entry.timezone,
                }).format(new Date(entry.occurred_at))}
              </time>
            </span>
          </div>
          <div className="hydration-entry__actions">
            <Button
              className="hydration-entry__icon"
              variant="ghost"
              aria-label={`Изменить запись: ${beverageLabels[entry.beverage_type]}, ${entry.volume_ml} мл`}
              type="button"
              onClick={() => setEditing(true)}
            >
              <Icon name="edit" size={20} />
            </Button>
            <Button
              className="hydration-entry__icon"
              variant="ghost"
              aria-label={`Удалить запись: ${beverageLabels[entry.beverage_type]}, ${entry.volume_ml} мл`}
              type="button"
              onClick={() => void requestDelete()}
            >
              <Icon name="trash" size={20} />
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
  quickAddRequest = 0,
}: {
  diaryDate: string;
  initialExpanded?: boolean;
  quickAddRequest?: number;
}) {
  const queryClient = useQueryClient();
  const { toast, confirm } = useFeedback();
  const runtime = useRuntime();
  const demoToken = runtime.kind === 'demo' ? runtime.sessionToken : null;
  const [demoScope, setDemoScope] = useState<{ token: string; scope: string } | null>(null);
  useEffect(() => {
    if (!demoToken) return;
    let active = true;
    void demoHydrationScope(demoToken)
      .then((scope) => {
        if (active) setDemoScope({ token: demoToken, scope });
      })
      .catch(() => {
        if (active) toast('Не удалось безопасно подготовить запись напитка.', 'error');
      });
    return () => {
      active = false;
    };
  }, [demoToken, toast]);
  const scope = demoToken
    ? demoScope?.token === demoToken
      ? demoScope.scope
      : null
    : accountHydrationScope();
  const scopeRef = useRef(scope);
  const dateRef = useRef(diaryDate);
  useLayoutEffect(() => {
    scopeRef.current = scope;
    dateRef.current = diaryDate;
  }, [scope, diaryDate]);
  const [pendingState, setPendingState] = useState<{
    scope: string | null;
    entries: PendingHydration;
  }>({ scope: null, entries: {} });
  const pendingRef = useRef(pendingState);
  const observedDemoGenerationRef = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!scope) return;
    let active = true;
    const sync = (otherTab = false) => {
      try {
        const store = readPendingHydration(scope);
        const previous = pendingRef.current.scope === scope ? pendingRef.current.entries : {};
        const confirmedElsewhere =
          otherTab &&
          Object.values(previous)
            .flat()
            .some((item) => store.confirmed.includes(item.key));
        if (active) {
          const next = { scope, entries: store.entries };
          pendingRef.current = next;
          setPendingState(next);
          if (confirmedElsewhere) {
            toast('Запись сохранена в другой вкладке.');
          }
          if (
            confirmedElsewhere ||
            (otherTab &&
              demoToken &&
              store.demoGeneration !== undefined &&
              store.demoGeneration !== observedDemoGenerationRef.current)
          ) {
            void queryClient.invalidateQueries({ queryKey: queryKeys.nutrition.hydration });
          }
        }
      } catch {
        // Submitting reports storage failures without sending an unsafe request.
      }
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === pendingStorageKey(scope)) sync(true);
    };
    const onLocal = (event: Event) => {
      if ((event as CustomEvent<string>).detail === pendingStorageKey(scope)) sync();
    };
    window.addEventListener('storage', onStorage);
    window.addEventListener(HYDRATION_PENDING_EVENT, onLocal);
    void withPendingHydration(scope, (store) => {
      if (active) {
        const next = { scope, entries: store.entries };
        pendingRef.current = next;
        setPendingState(next);
      }
    }).catch(() => undefined);
    return () => {
      active = false;
      window.removeEventListener('storage', onStorage);
      window.removeEventListener(HYDRATION_PENDING_EVENT, onLocal);
    };
  }, [scope, demoToken, toast, queryClient]);
  const isCurrentScope = (requestScope: string, boundary?: AuthDiscard) => {
    const current = getApiRuntime();
    if (requestScope !== scopeRef.current) return false;
    return demoToken
      ? current.kind === 'demo' && current.sessionToken === demoToken
      : current.kind === 'production' &&
          accountHydrationScope() === requestScope &&
          (boundary === undefined || !authDiscardChanged(boundary));
  };
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const quickAddRef = useRef<HTMLDivElement>(null);
  const consumedQuickAddRequest = useRef(0);
  const addInFlightRef = useRef(false);
  const [preparingAdd, setPreparingAdd] = useState(false);
  const [customVolume, setCustomVolume] = useState('');
  const [beverageType, setBeverageType] = useState('water');
  const [undoEntry, setUndoEntry] = useState<(HydrationEntry & { demoGeneration?: number }) | null>(
    null,
  );
  const [goalModeDraft, setGoalMode] = useState<'reference' | 'manual' | null>(null);
  const [sexDraft, setSex] = useState<'male' | 'female' | null>();
  const [adultConfirmedDraft, setAdultConfirmed] = useState<boolean>();
  const [manualGoalDraft, setManualGoal] = useState<string>();
  const [saveSex, setSaveSex] = useState(false);
  const [presetName, setPresetName] = useState('');
  const [presetVolume, setPresetVolume] = useState('');
  const hydration = useQuery({
    queryKey: queryKeys.nutrition.hydrationDate(diaryDate),
    queryFn: () =>
      api<HydrationDay & { demo_generation?: number }>(
        `/api/v1/nutrition/hydration?diary_date=${diaryDate}`,
      ),
  });
  const profile = useQuery({
    queryKey: ['me'],
    queryFn: () => api<User>('/api/v1/me'),
  });
  const demoGeneration = hydration.data?.demo_generation;
  const [readyDemoStore, setReadyDemoStore] = useState<{
    scope: string;
    generation: number;
  } | null>(null);
  const matchesDemoScope = readyDemoStore?.scope === scope;
  const matchesDemoGeneration = readyDemoStore?.generation === demoGeneration;
  const demoStoreReady = matchesDemoScope && matchesDemoGeneration;
  const demoStorageReady = !demoToken || demoStoreReady;
  useLayoutEffect(() => {
    observedDemoGenerationRef.current = demoGeneration;
  }, [demoToken, demoGeneration]);
  const lastDemoGenerationRef = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!demoToken || demoGeneration === undefined) return;
    if (
      lastDemoGenerationRef.current !== undefined &&
      lastDemoGenerationRef.current !== demoGeneration
    )
      setUndoEntry(null);
    lastDemoGenerationRef.current = demoGeneration;
  }, [demoToken, demoGeneration]);
  useEffect(() => {
    if (!scope || !demoToken || typeof demoGeneration !== 'number') return;
    if (!Number.isSafeInteger(demoGeneration)) return;
    const generation = demoGeneration;
    let active = true;
    // Readiness is keyed by scope and generation; an old key is never reusable.
    void withPendingHydration(scope, (store) => {
      if (store.demoGeneration !== undefined && (demoGeneration ?? -1) < store.demoGeneration)
        return;
      let changed = store.demoGeneration !== demoGeneration;
      if (store.demoGeneration !== undefined && store.demoGeneration !== demoGeneration)
        store.confirmed = [];
      store.demoGeneration = demoGeneration;
      for (const [date, items] of Object.entries(store.entries)) {
        const current = items.filter((item) => item.demoGeneration === demoGeneration);
        if (current.length !== items.length) {
          store.entries[date] = current;
          changed = true;
        }
      }
      if (changed) writePendingHydration(scope, store);
    })
      .then(() => {
        // Do not enable quick add until the generation fence commits in IDB.
        if (active) setReadyDemoStore({ scope, generation });
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [scope, demoToken, demoGeneration]);
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
      request,
      demo,
    }: {
      request: AddRequest;
      scope: string;
      demo: boolean;
      boundary?: AuthDiscard;
    }) =>
      api<HydrationEntry>('/api/v1/nutrition/hydration/entries/v2', {
        method: 'POST',
        headers: {
          'Idempotency-Key': request.key,
          'X-YFC-Hydration-Protocol': '2',
        },
        body: {
          volume_ml: request.volume,
          beverage_type: request.kind,
          diary_date: request.date,
          source: request.source,
          ...(demo
            ? { _hydration_retry_key: request.key, _hydration_generation: request.demoGeneration }
            : {}),
        },
      }),
    onSuccess: async (entry, { request, scope: requestScope, boundary }) => {
      if (!isCurrentScope(requestScope, boundary)) return;
      let removed = false;
      try {
        await withPendingHydration(requestScope, (store) => {
          if (!isCurrentScope(requestScope, boundary)) return;
          if (demoToken && store.demoGeneration !== request.demoGeneration) return;
          const items = store.entries[request.date] ?? [];
          store.entries[request.date] = items.filter((item) => item.key !== request.key);
          store.confirmed = [
            ...store.confirmed.filter((key) => key !== request.key),
            request.key,
          ].slice(-100);
          writePendingHydration(requestScope, store);
          removed = true;
        });
      } catch {
        toast('Запись сохранена, но не удалось обновить состояние повтора.', 'error');
      }
      if (!isCurrentScope(requestScope, boundary)) return;
      if (!removed) {
        await refresh();
        return;
      }
      setUndoEntry(
        entry.source === 'quick_preset' || entry.source === 'manual'
          ? { ...entry, demoGeneration: request.demoGeneration }
          : null,
      );
      setCustomVolume('');
      await refresh();
      trackCoreProductEvent(
        { name: 'hydration_logged', surface: productEventSurface() },
        'hydration_logged',
      );
      haptic('success');
    },
    onError: async (reason, { request, scope: requestScope, boundary }) => {
      if (!isCurrentScope(requestScope, boundary)) return;
      const status = (reason as { status?: number }).status;
      let confirmed = false;
      try {
        await withPendingHydration(requestScope, (store) => {
          if (!isCurrentScope(requestScope, boundary)) return;
          if (demoToken && store.demoGeneration !== request.demoGeneration) return;
          if (store.confirmed.includes(request.key)) {
            confirmed = true;
            return;
          }
          const items = store.entries[request.date] ?? [];
          const current = items.find((item) => item.key === request.key);
          if (
            !request.uncertain &&
            !current?.uncertain &&
            [400, 403, 404, 422].includes(status ?? 0)
          ) {
            store.entries[request.date] = items.filter((item) => item.key !== request.key);
            writePendingHydration(requestScope, store);
          } else if (!items.some((item) => item.key === request.key)) {
            store.entries[request.date] = [...items, { ...request, uncertain: true }];
            writePendingHydration(requestScope, store);
          }
        });
      } catch {
        /* Keep the saved request when its state cannot be updated. */
      }
      if (confirmed) {
        await refresh();
        toast('Запись уже сохранена.');
        return;
      }
      if (demoToken && status === 409) await refresh();
      toast((reason as Error).message, 'error');
    },
    onSettled: () => {
      addInFlightRef.current = false;
      setPreparingAdd(false);
    },
  });
  const addUnavailable = preparingAdd || add.isPending || !demoStorageReady;
  useEffect(() => {
    const url = new URL(window.location.href);
    const routeRequested = initialExpanded && url.searchParams.get('hydration') === 'quick';
    const pageRequested = quickAddRequest !== consumedQuickAddRequest.current;
    if (
      (!routeRequested && !pageRequested) ||
      !scope ||
      !hydration.data ||
      !demoStorageReady ||
      addUnavailable ||
      !quickAddRef.current
    ) {
      return;
    }
    const button = quickAddRef.current.querySelector<HTMLButtonElement>('button:not(:disabled)');
    if (!button) return;
    button.focus({ preventScroll: true });
    quickAddRef.current.scrollIntoView({ block: 'center', behavior: 'instant' });
    consumedQuickAddRequest.current = quickAddRequest;
    if (routeRequested) {
      url.searchParams.delete('hydration');
      window.history.replaceState(
        window.history.state,
        '',
        `${url.pathname}${url.search}${url.hash}`,
      );
      window.dispatchEvent(new PopStateEvent('popstate'));
    }
  }, [initialExpanded, hydration.data, scope, demoStorageReady, quickAddRequest, addUnavailable]);
  const submitAdd = async (payload: Pick<AddRequest, 'volume' | 'kind' | 'source'>) => {
    if (
      addInFlightRef.current ||
      add.isPending ||
      !scope ||
      !demoStorageReady ||
      !isCurrentScope(scope) ||
      dateRef.current !== diaryDate
    )
      return;
    if (!Number.isInteger(payload.volume) || payload.volume < 1 || payload.volume > 5000) {
      toast('Укажите объём от 1 до 5000 мл.', 'error');
      return;
    }
    if (demoToken && (!Number.isSafeInteger(demoGeneration) || (demoGeneration ?? -1) < 0)) {
      toast('Не удалось безопасно подготовить запись напитка. Обновите демо.', 'error');
      return;
    }
    addInFlightRef.current = true;
    setPreparingAdd(true);
    const boundary = demoToken
      ? undefined
      : { ...authDiscardSnapshot(), userId: Number(scope.slice(5)) };
    let approvedKeys = '';
    try {
      while (isCurrentScope(scope, boundary)) {
        const result = await withPendingHydration(scope, (store) => {
          if (!isCurrentScope(scope, boundary)) return null;
          if (
            demoToken &&
            store.demoGeneration !== undefined &&
            store.demoGeneration > (demoGeneration ?? -1)
          )
            return { stale: true };
          if (demoToken && store.demoGeneration !== demoGeneration) {
            store.entries = {};
            store.confirmed = [];
            store.demoGeneration = demoGeneration;
          }
          const entries = store.entries;
          const previous = entries[diaryDate] ?? [];
          const items = demoToken
            ? previous.filter((item) => item.demoGeneration === demoGeneration)
            : previous;
          if (items.length !== previous.length) {
            entries[diaryDate] = items;
            writePendingHydration(scope, store);
          }
          const same = items.find(
            (item) =>
              item.volume === payload.volume &&
              item.kind === payload.kind &&
              item.source === payload.source,
          );
          if (same) {
            same.uncertain = true;
            writePendingHydration(scope, store);
            return { request: same };
          }
          const keys = items
            .map((item) => item.key)
            .sort()
            .join('|');
          if (keys && keys !== approvedKeys) return { confirmKeys: keys };
          const request: AddRequest = {
            ...payload,
            date: diaryDate,
            key: requestKey('hydration-entry'),
            uncertain: false,
            ...(demoToken ? { demoGeneration } : {}),
          };
          entries[diaryDate] = [...items, request];
          writePendingHydration(scope, store);
          return { request };
        });
        if (!result) break;
        if ('stale' in result && result.stale) {
          await refresh();
          toast('Демо изменилось. Повторите добавление.', 'error');
          break;
        }
        if ('request' in result && result.request) {
          add.mutate({ request: result.request, scope, demo: Boolean(demoToken), boundary });
          return;
        }
        const approved = await confirm({
          title: 'Добавить другую запись?',
          message:
            'Предыдущая запись могла сохраниться. Проверьте историю перед добавлением нового напитка.',
          confirmText: 'Добавить новый',
          danger: false,
        });
        if (!approved || dateRef.current !== diaryDate) break;
        approvedKeys = result.confirmKeys ?? '';
      }
    } catch {
      toast(
        'Не удалось безопасно сохранить напиток. Проверьте доступ к хранилищу браузера.',
        'error',
      );
    }
    addInFlightRef.current = false;
    setPreparingAdd(false);
  };
  const undo = useMutation({
    mutationFn: (entry: HydrationEntry & { demoGeneration?: number }) =>
      deleteHydrationEntry(entry, 'undo', entry.demoGeneration),
    onSuccess: async () => {
      setUndoEntry(null);
      await refresh();
      toast('Добавление отменено');
    },
    onError: (reason) => {
      if ([404, 409].includes((reason as { status?: number }).status ?? 0)) {
        setUndoEntry(null);
        void refresh();
      }
      toast((reason as Error).message, 'error');
    },
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
  const pendingItems = pendingState.scope === scope ? (pendingState.entries[diaryDate] ?? []) : [];
  const pending = pendingItems[0];
  const target = data.goal?.enabled ? data.goal.target_ml : null;
  const progress =
    data.progress_percent == null ? null : Math.max(0, Math.min(data.progress_percent, 100));
  const hasFullHistory = data.entries.length > 3;
  const showFullHistory = hasFullHistory && historyExpanded;
  const historyEntries = showFullHistory ? data.entries : data.entries.slice(0, 3);
  const historyCount = hasFullHistory
    ? `${showFullHistory ? 'Вся история' : 'Последние 3'} · всего ${data.entries.length}`
    : `${data.entries.length} ${hydrationEntryCountLabel(data.entries.length)}`;
  return (
    <section className="hydration-card" aria-label="Гидратация">
      <header className="hydration-card__header">
        <div>
          <span className="eyebrow">Гидратация</span>
          <h2 id="hydration-title">Вода и напитки</h2>
          <p>{target ? `${data.total_ml} из ${target} мл` : `${data.total_ml} мл записано`}</p>
        </div>
        <div
          className={`hydration-orb${target && progress !== null && progress >= 70 ? ' hydration-orb--filled' : ''}`}
          role={target && progress !== null ? 'progressbar' : undefined}
          aria-label={target && progress !== null ? 'Прогресс гидратации' : undefined}
          aria-valuemin={target && progress !== null ? 0 : undefined}
          aria-valuemax={target && progress !== null ? target : undefined}
          aria-valuenow={target && progress !== null ? Math.min(data.total_ml, target) : undefined}
          aria-valuetext={
            target && progress !== null
              ? `${data.total_ml} из ${target} миллилитров, ${Math.round(data.progress_percent ?? 0)}%`
              : undefined
          }
          aria-hidden={target && progress !== null ? undefined : true}
        >
          {target && progress !== null && <span style={{ height: `${progress}%` }} />}
          <strong>
            {target && progress !== null ? `${Math.round(data.progress_percent ?? 0)}%` : 'Вода'}
          </strong>
        </div>
      </header>
      {(!target || progress === null) && (
        <p className="hydration-progress-note">
          {target ? 'Прогресс недоступен' : 'Ориентир не задан'}
        </p>
      )}
      {target && data.total_ml > target && (
        <p className="hydration-progress-note">Выше ориентира на {data.total_ml - target} мл</p>
      )}
      <div ref={quickAddRef} className="hydration-presets" aria-label="Быстро добавить напиток">
        {data.presets
          .filter((preset) => preset.is_default)
          .map((preset) => (
            <Button
              variant="secondary"
              aria-label={`${preset.label}, добавить ${preset.volume_ml} мл, ${beverageLabels[preset.beverage_type]}`}
              disabled={addUnavailable || !scope}
              key={`${preset.id ?? 'default'}-${preset.label}`}
              type="button"
              onClick={() =>
                void submitAdd({
                  volume: preset.volume_ml,
                  kind: preset.beverage_type,
                  source: 'quick_preset',
                })
              }
            >
              <strong>
                <Icon name="plus" size={16} /> {preset.volume_ml} мл
              </strong>
              <span>{beverageLabels[preset.beverage_type]}</span>
            </Button>
          ))}
      </div>
      {data.presets.some((preset) => !preset.is_default) && (
        <div className="hydration-saved-presets">
          {data.presets
            .filter((preset) => !preset.is_default)
            .map((preset) => (
              <Button
                variant="secondary"
                aria-label={`${preset.label}, добавить ${preset.volume_ml} мл, ${beverageLabels[preset.beverage_type]}`}
                disabled={addUnavailable || !scope}
                key={preset.id}
                type="button"
                onClick={() =>
                  void submitAdd({
                    volume: preset.volume_ml,
                    kind: preset.beverage_type,
                    source: 'quick_preset',
                  })
                }
              >
                <Icon name="plus" size={16} />
                <span>
                  {preset.volume_ml} мл · {preset.label} · {beverageLabels[preset.beverage_type]}
                </span>
              </Button>
            ))}
        </div>
      )}
      {undoEntry?.diary_date === diaryDate && (
        <div className="hydration-undo" role="status">
          <span>Добавлено {undoEntry.volume_ml} мл</span>
          <Button
            variant="secondary"
            type="button"
            disabled={undo.isPending}
            onClick={() => undo.mutate(undoEntry)}
          >
            Отменить
          </Button>
        </div>
      )}
      {add.isPaused && (
        <div className="hydration-mutation-error" role="status">
          Нет сети. Запись напитка ожидает соединения.
        </div>
      )}
      {pending && !add.isPending && !preparingAdd && (
        <div className="hydration-mutation-error" role="alert">
          <span>
            Не удалось проверить запись: {beverageLabels[pending.kind]}, {pending.volume} мл.
            Повторите её без дубля.
            {pendingItems.length > 1 && ` Ожидают проверки: ${pendingItems.length}.`}
          </span>
          <Button
            variant="secondary"
            type="button"
            disabled={addUnavailable}
            onClick={() => void submitAdd(pending)}
          >
            Повторить без дубля
          </Button>
        </div>
      )}
      <div className="hydration-details">
        <details>
          <summary className="hydration-details__summary yfc-disclosure-summary">
            <span id="hydration-custom-title">Другой напиток или объём</span>
            <DisclosureIcon />
          </summary>
          <section className="hydration-details__body" aria-labelledby="hydration-custom-title">
            <div className="hydration-form-row hydration-custom-form">
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
                disabled={addUnavailable || !scope || !customVolume}
                type="button"
                onClick={() =>
                  void submitAdd({
                    volume: Number(customVolume),
                    kind: beverageType,
                    source: 'manual',
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
        </details>
      </div>

      <section id="hydration-history-section" className="hydration-card__section" aria-labelledby="hydration-history-title">
        <div className="hydration-section-head">
          <div>
            <h3 id="hydration-history-title" tabIndex={-1}>История за день</h3>
          </div>
          <span className="hydration-history__count">{historyCount}</span>
        </div>
        {data.entries.length === 0 ? (
          <p className="hydration-empty">Напитков пока нет</p>
        ) : (
          <ul id="hydration-history-list" className="hydration-history" aria-live="polite">
            {historyEntries.map((entry) => (
              <HydrationEntryRow
                entry={entry}
                key={entry.id}
                demoGeneration={demoToken ? demoGeneration : undefined}
                onChanged={() => {
                  setUndoEntry((current) => (current?.id === entry.id ? null : current));
                  void refresh();
                }}
              />
            ))}
          </ul>
        )}
        {hasFullHistory && (
          <div className="hydration-history__actions">
            <Button
              aria-controls="hydration-history-list"
              aria-expanded={showFullHistory}
              type="button"
              onClick={() => setHistoryExpanded((value) => !value)}
            >
              {showFullHistory ? 'Свернуть историю' : 'Показать всю историю'}
              <Icon
                className={`hydration-history__toggle-icon${showFullHistory ? ' hydration-history__toggle-icon--expanded' : ''}`}
                name="disclosure-closed"
                size={16}
              />
            </Button>
          </div>
        )}
      </section>

      <div className="hydration-details">
        <details id="hydration-goal-details">
          <summary className="hydration-details__summary yfc-disclosure-summary">
            <span id="hydration-goal-title">Личный ориентир</span>
            <DisclosureIcon />
          </summary>
          <section className="hydration-details__body" aria-labelledby="hydration-goal-title">
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
        </details>

        <details id="hydration-presets-details">
          <summary className="hydration-details__summary yfc-disclosure-summary">
            <span id="hydration-presets-title">Мои кружки и бутылки</span>
            <DisclosureIcon />
          </summary>
          <section className="hydration-details__body" aria-labelledby="hydration-presets-title">
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
              <Field label="Напиток в ёмкости" labelFor="hydration-preset-kind">
                <Select
                  id="hydration-preset-kind"
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
                        {preset.label} · {preset.volume_ml} мл ·{' '}
                        {beverageLabels[preset.beverage_type]}
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
        </details>
      </div>
    </section>
  );
}
