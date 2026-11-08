import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { webcrypto } from 'node:crypto';
import { IDBFactory } from 'fake-indexeddb';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HydrationTracker } from '../../../../src/features/nutrition/HydrationTracker';
import { resetHydrationFences } from '../../../../src/shared/browser/hydrationFence';
import type { HydrationDay, HydrationEntry } from '../../../../src/shared/api/types';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import { AUTHENTICATED_USER_ID_STORAGE_KEY } from '../../../../src/shared/userScopedStorage';
import { DemoRuntimeProvider } from '../../../../src/shared/runtime/runtime';
import {
  PRODUCT_EVENT_NAME,
  type ProductEventEnvelope,
} from '../../../../src/shared/analytics/productEvents';

const apiMock = vi.hoisted(() => vi.fn());
const discardChanged = vi.hoisted(() => vi.fn(() => false));
vi.mock('../../../../src/shared/api/client', () => ({
  api: apiMock,
  authDiscardSnapshot: () => ({ generation: null, revision: 0, verifiedLogin: null }),
  authDiscardChanged: discardChanged,
}));
vi.mock('../../../../src/shared/telegram/useTelegram', () => ({ haptic: vi.fn() }));

const day: HydrationDay = {
  diary_date: '2026-09-01',
  timezone: 'Europe/Moscow',
  total_ml: 850,
  goal: {
    id: 1,
    enabled: true,
    target_ml: 2200,
    source: 'national_academies_beverages',
    method_version: 'nasem-ai-2005-observed-beverages-v1',
    reference_scope: 'beverages',
    sex: 'female',
    adult_confirmed: true,
    effective_from: '2026-09-01',
    effective_to: null,
    created_at: '2026-09-01T08:00:00',
  },
  progress_percent: 38.6,
  entries: [
    {
      id: 10,
      volume_ml: 350,
      beverage_type: 'water',
      occurred_at: '2026-09-01T06:00:00Z',
      diary_date: '2026-09-01',
      timezone: 'Europe/Moscow',
      source: 'quick_preset',
      created_at: '2026-09-01T09:00:00',
      updated_at: '2026-09-01T09:00:00',
    },
  ],
  presets: [
    { id: null, label: 'Стакан', volume_ml: 250, beverage_type: 'water', is_default: true },
    { id: null, label: 'Бутылка', volume_ml: 500, beverage_type: 'water', is_default: true },
  ],
  last_logged_at: '2026-09-01T06:00:00Z',
  reminder_suppression_key: 'hydration-logged:1:2026-09-01',
  action_url: '/app?section=nutrition&date=2026-09-01&hydration=quick',
};

function renderTracker(initialExpanded = false) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <HydrationTracker diaryDate="2026-09-01" initialExpanded={initialExpanded} />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
  return { ...result, queryClient };
}

describe('HydrationTracker', () => {
  beforeEach(() => {
    vi.stubGlobal('indexedDB', new IDBFactory());
    window.history.replaceState({}, '', '/app?section=nutrition');
    sessionStorage.clear();
    localStorage.clear();
    discardChanged.mockReturnValue(false);
    sessionStorage.setItem(AUTHENTICATED_USER_ID_STORAGE_KEY, '7');
    apiMock.mockReset();
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
      if (path.startsWith('/api/v1/nutrition/hydration?')) return Promise.resolve(day);
      return Promise.resolve({ ...day.entries[0], id: 11, volume_ml: 250 });
    });
  });

  afterEach(async () => {
    cleanup();
    await resetHydrationFences(null);
    vi.unstubAllGlobals();
    Reflect.deleteProperty(Element.prototype, 'scrollIntoView');
  });

  it('consumes a loaded water intent once and preserves the route and drafts on refresh', async () => {
    const scroll = vi.fn();
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: scroll,
    });
    window.history.replaceState(
      { returnTo: 'today' },
      '',
      '/app?section=nutrition&date=2026-09-01&hydration=quick#diary',
    );
    const { queryClient } = renderTracker(true);
    const preset = await screen.findByRole('button', { name: /Стакан.*250 мл/ });
    await waitFor(() => expect(preset).toHaveFocus());
    expect(scroll).toHaveBeenCalledTimes(1);
    expect(window.location.search).toBe('?section=nutrition&date=2026-09-01');
    expect(window.location.hash).toBe('#diary');
    expect(window.history.state).toEqual({ returnTo: 'today' });
    const volume = within(screen.getByRole('region', { name: 'Другой объём' })).getByLabelText(
      'Объём, мл',
    );
    fireEvent.change(volume, { target: { value: '425' } });
    await queryClient.invalidateQueries();
    expect(volume).toHaveValue(425);
    expect(scroll).toHaveBeenCalledTimes(1);
  });

  it('keeps the water intent through a load error until retry mounts the controls', async () => {
    const scroll = vi.fn();
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: scroll,
    });
    let failed = false;
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
      if (!failed) {
        failed = true;
        return Promise.reject(new Error('Гидратация временно недоступна'));
      }
      return Promise.resolve(day);
    });
    window.history.replaceState({}, '', '/app?section=nutrition&hydration=quick');
    renderTracker(true);
    expect(await screen.findByText('Гидратация временно недоступна')).toBeVisible();
    expect(window.location.search).toContain('hydration=quick');
    expect(scroll).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /Повторить/ }));
    await waitFor(() => expect(scroll).toHaveBeenCalledTimes(1));
    expect(window.location.search).not.toContain('hydration=quick');
  });

  it('shows a compact factual summary and quick presets', async () => {
    renderTracker();
    expect(await screen.findByRole('heading', { name: 'Напитки' })).toBeVisible();
    expect(screen.getByText('850 из 2200 мл')).toBeVisible();
    expect(screen.getByRole('progressbar', { name: 'Прогресс гидратации' })).toHaveAttribute(
      'aria-valuetext',
      '850 из 2200 миллилитров',
    );
    expect(screen.getByRole('button', { name: /Стакан.*250 мл/ })).toBeVisible();
    expect(
      within(screen.getByRole('region', { name: 'Другой объём' })).getByLabelText('Объём, мл'),
    ).toBeVisible();
    expect(screen.getByText('История за день')).toBeVisible();
    expect(screen.getByText('Личный ориентир', { exact: true })).toBeVisible();
  });

  it.each([
    { entries: [], label: '0 записей', toggle: false },
    { entries: [day.entries[0], { ...day.entries[0], id: 11 }], label: '2 записи', toggle: false },
    {
      entries: [
        day.entries[0],
        { ...day.entries[0], id: 11 },
        { ...day.entries[0], id: 12 },
        { ...day.entries[0], id: 13 },
      ],
      label: 'Последние 3 · всего 4',
      toggle: true,
    },
  ])('reports history count truthfully for $label', async ({ entries, label, toggle }) => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
      if (path.startsWith('/api/v1/nutrition/hydration?')) {
        return Promise.resolve({ ...day, entries: entries as HydrationEntry[] });
      }
      return Promise.resolve({});
    });

    renderTracker();

    expect(await screen.findByText(label, { exact: true })).toBeVisible();
    if (entries.length > 0) {
      const history = screen.getByRole('list');
      expect(within(history).getAllByRole('button', { name: 'Изменить' })).toHaveLength(
        Math.min(entries.length, 3),
      );
    } else {
      expect(screen.queryByRole('list')).not.toBeInTheDocument();
    }
    if (!toggle) {
      expect(
        screen.queryByRole('button', { name: 'Показать всю историю' }),
      ).not.toBeInTheDocument();
      return;
    }

    const history = screen.getByRole('list');
    const toggleButton = screen.getByRole('button', { name: 'Показать всю историю' });
    expect(toggleButton).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggleButton);
    expect(screen.getByText('Вся история · всего 4', { exact: true })).toBeVisible();
    expect(within(history).getAllByRole('button', { name: 'Изменить' })).toHaveLength(4);
    fireEvent.click(screen.getByRole('button', { name: 'Свернуть историю' }));
    expect(within(history).getAllByRole('button', { name: 'Изменить' })).toHaveLength(3);
  });

  it('quick-adds once and offers explicit undo', async () => {
    renderTracker();
    const events: ProductEventEnvelope[] = [];
    const listener = (event: Event) =>
      events.push((event as CustomEvent<ProductEventEnvelope>).detail);
    window.addEventListener(PRODUCT_EVENT_NAME, listener);
    fireEvent.click(await screen.findByRole('button', { name: /Стакан.*250 мл/ }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/hydration/entries/v2',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({ volume_ml: 250, source: 'quick_preset' }),
        }),
      ),
    );
    expect(await screen.findByText('Добавлено 250 мл')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Отменить' })).toBeVisible();
    expect(events.map((event) => event.name)).toContain('hydration_logged');
    window.removeEventListener(PRODUCT_EVENT_NAME, listener);
  });

  it('reuses the saved request after a lost response, then accepts a new entry', async () => {
    const saved = new Map<string, HydrationEntry>();
    const requests: Array<{ key: string; body: unknown }> = [];
    let loseResponse = true;
    apiMock.mockImplementation(
      (
        path: string,
        options?: { method?: string; headers?: Record<string, string>; body?: unknown },
      ) => {
        if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
        if (path.startsWith('/api/v1/nutrition/hydration?')) return Promise.resolve(day);
        if (path === '/api/v1/nutrition/hydration/entries/v2' && options?.method === 'POST') {
          const key = options.headers?.['Idempotency-Key'];
          if (!key) throw new Error('Missing idempotency key');
          requests.push({ key, body: options.body });
          if (!saved.has(key)) {
            const firstEntry = day.entries[0];
            if (!firstEntry) throw new Error('Missing hydration fixture');
            saved.set(key, { ...firstEntry, id: 10 + saved.size + 1, volume_ml: 250 });
          }
          if (loseResponse) {
            loseResponse = false;
            return Promise.reject(new Error('Нет соединения'));
          }
          return Promise.resolve(saved.get(key));
        }
        return Promise.resolve();
      },
    );

    renderTracker();
    const preset = await screen.findByRole('button', { name: /Стакан.*250 мл/ });
    fireEvent.click(preset);
    await screen.findByRole('button', { name: 'Повторить без дубля' });
    await waitFor(() => expect(preset).toBeEnabled());
    fireEvent.click(preset);
    await screen.findByText('Добавлено 250 мл');
    expect(requests).toHaveLength(2);
    expect(requests[1]).toEqual(requests[0]);
    expect(saved.size).toBe(1);

    fireEvent.click(preset);
    await waitFor(() => expect(requests).toHaveLength(3));
    expect(requests[2]?.key).not.toBe(requests[0]?.key);
    expect(saved.size).toBe(2);
  });

  it('keeps an uncertain request through remount and retries it for the original date', async () => {
    const requests: Array<{ key: string; body: { diary_date: string } }> = [];
    let loseResponse = true;
    apiMock.mockImplementation(
      (
        path: string,
        options?: {
          method?: string;
          headers?: Record<string, string>;
          body?: { diary_date: string };
        },
      ) => {
        if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
        if (path.startsWith('/api/v1/nutrition/hydration?')) return Promise.resolve(day);
        if (path === '/api/v1/nutrition/hydration/entries/v2' && options?.method === 'POST') {
          const key = options.headers?.['Idempotency-Key'];
          if (!key || !options.body) throw new Error('Missing hydration request');
          requests.push({ key, body: options.body });
          if (loseResponse) {
            loseResponse = false;
            return Promise.reject(new Error('Нет соединения'));
          }
          return Promise.resolve({ ...day.entries[0], id: 11, volume_ml: 250 });
        }
        return Promise.resolve();
      },
    );

    const first = renderTracker();
    fireEvent.click(await screen.findByRole('button', { name: /Стакан.*250 мл/ }));
    await screen.findByRole('button', { name: 'Повторить без дубля' });
    first.unmount();

    const { rerender, queryClient } = renderTracker();
    await screen.findByRole('button', { name: 'Повторить без дубля' });
    rerender(
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <HydrationTracker diaryDate="2026-08-31" />
        </FeedbackProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('button', { name: /Стакан.*250 мл/ })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Повторить без дубля' })).not.toBeInTheDocument();
    rerender(
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <HydrationTracker diaryDate="2026-09-01" />
        </FeedbackProvider>
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Повторить без дубля' }));
    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1]).toEqual(requests[0]);
    expect(requests[1]?.body.diary_date).toBe('2026-09-01');
  });

  it('asks before replacing an unresolved request with a different drink', async () => {
    let posts = 0;
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
      if (path.startsWith('/api/v1/nutrition/hydration?')) return Promise.resolve(day);
      if (options?.method === 'POST') {
        posts += 1;
        return posts === 1
          ? Promise.reject(new Error('Нет соединения'))
          : Promise.resolve({ ...day.entries[0], id: 12, volume_ml: 500 });
      }
      return Promise.resolve();
    });
    renderTracker();
    const glass = await screen.findByRole('button', { name: /Стакан.*250 мл/ });
    await waitFor(() => expect(glass).toBeEnabled());
    fireEvent.click(glass);
    // The request and the pending-state update are async IndexedDB operations.
    // Assert the failed POST first so a missing retry button cannot hide a dropped click.
    await waitFor(() => expect(posts).toBe(1), { timeout: 5_000 });
    await screen.findByRole('button', { name: 'Повторить без дубля' }, { timeout: 5_000 });
    const bottle = screen.getByRole('button', { name: /Бутылка.*500 мл/ });
    await waitFor(() => expect(bottle).toBeEnabled());
    fireEvent.click(bottle);
    const dialog = await screen.findByRole('dialog', { name: 'Добавить другую запись?' });
    expect(within(dialog).getByText(/Предыдущая запись могла сохраниться/)).toBeVisible();
    expect(posts).toBe(1);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Отмена' }));
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Повторить без дубля' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: /Бутылка.*500 мл/ }));
    fireEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Добавить новый' }),
    );
    await screen.findByText('Добавлено 500 мл');
    expect(posts).toBe(2);
  });

  it('keeps separate unresolved requests for different dates', async () => {
    const requests: Array<{ date: string; key: string }> = [];
    apiMock.mockImplementation(
      (
        path: string,
        options?: {
          method?: string;
          headers?: Record<string, string>;
          body?: { diary_date: string };
        },
      ) => {
        if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
        if (path.startsWith('/api/v1/nutrition/hydration?')) return Promise.resolve(day);
        if (options?.method === 'POST' && options.body && options.headers) {
          const date = options.body.diary_date;
          const key = options.headers['Idempotency-Key'];
          if (!key) throw new Error('Missing idempotency key');
          requests.push({ date, key });
          if (requests.filter((request) => request.date === date).length === 1)
            return Promise.reject(new Error('Нет соединения'));
          return Promise.resolve({ ...day.entries[0], id: 11, diary_date: date, volume_ml: 250 });
        }
        return Promise.resolve();
      },
    );
    const { rerender, queryClient } = renderTracker();
    const showDate = (date: string) =>
      rerender(
        <QueryClientProvider client={queryClient}>
          <FeedbackProvider>
            <HydrationTracker diaryDate={date} />
          </FeedbackProvider>
        </QueryClientProvider>,
      );
    const clickEnabled = async (name: string | RegExp) => {
      const button = await screen.findByRole('button', { name });
      await waitFor(() => expect(button).toBeEnabled());
      fireEvent.click(button);
    };
    await clickEnabled(/Стакан.*250 мл/);
    await screen.findByRole('button', { name: 'Повторить без дубля' });
    showDate('2026-08-31');
    await clickEnabled(/Стакан.*250 мл/);
    await screen.findByRole('button', { name: 'Повторить без дубля' });
    showDate('2026-09-01');
    await clickEnabled('Повторить без дубля');
    await screen.findByText('Добавлено 250 мл');
    showDate('2026-08-31');
    await clickEnabled('Повторить без дубля');
    await waitFor(() => expect(requests).toHaveLength(4));
    expect(requests[2]).toEqual(requests[0]);
    expect(requests[3]).toEqual(requests[1]);
    expect(requests[0]?.key).not.toBe(requests[1]?.key);
  });

  it('does not lose a newer pending date when an unmounted request fails late', async () => {
    let rejectFirst: (reason: Error) => void = () => {};
    let posts = 0;
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
      if (path.startsWith('/api/v1/nutrition/hydration?')) return Promise.resolve(day);
      if (options?.method === 'POST') {
        posts += 1;
        if (posts === 1)
          return new Promise((_resolve, reject) => {
            rejectFirst = reject;
          });
        return Promise.reject(new Error('Нет соединения'));
      }
      return Promise.resolve();
    });
    const first = renderTracker();
    fireEvent.click(await screen.findByRole('button', { name: /Стакан.*250 мл/ }));
    await waitFor(() => expect(posts).toBe(1));
    first.unmount();
    const second = renderTracker();
    second.rerender(
      <QueryClientProvider client={second.queryClient}>
        <FeedbackProvider>
          <HydrationTracker diaryDate="2026-08-31" />
        </FeedbackProvider>
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole('button', { name: /Стакан.*250 мл/ }));
    await screen.findByRole('button', { name: 'Повторить без дубля' });
    await act(async () => rejectFirst(new Error('Нет соединения')));
    second.unmount();
    const third = renderTracker();
    await screen.findByRole('button', { name: 'Повторить без дубля' });
    third.rerender(
      <QueryClientProvider client={third.queryClient}>
        <FeedbackProvider>
          <HydrationTracker diaryDate="2026-08-31" />
        </FeedbackProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('button', { name: 'Повторить без дубля' })).toBeVisible();
  });

  it('preserves the same demo retry key through reload and transport body', async () => {
    Object.defineProperty(globalThis.crypto, 'subtle', {
      configurable: true,
      value: webcrypto.subtle,
    });
    const requests: Array<{ headers: Record<string, string>; body: Record<string, unknown> }> = [];
    apiMock.mockImplementation(
      (
        path: string,
        options?: {
          method?: string;
          headers: Record<string, string>;
          body: Record<string, unknown>;
        },
      ) => {
        if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
        if (path.startsWith('/api/v1/nutrition/hydration?'))
          return Promise.resolve({ ...day, demo_generation: 0 });
        if (options?.method === 'POST') {
          requests.push({ headers: options.headers, body: options.body });
          return requests.length === 1
            ? Promise.reject(new Error('Нет соединения'))
            : Promise.resolve({ ...day.entries[0], id: 11, volume_ml: 250 });
        }
        return Promise.resolve();
      },
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const demo = (
      <DemoRuntimeProvider sessionToken="synthetic-session" mapNavigationPath={(path) => path}>
        <QueryClientProvider client={queryClient}>
          <FeedbackProvider>
            <HydrationTracker diaryDate="2026-09-01" />
          </FeedbackProvider>
        </QueryClientProvider>
      </DemoRuntimeProvider>
    );
    const first = render(demo);
    const glass = await screen.findByRole('button', { name: /Стакан.*250 мл/ });
    await waitFor(() => expect(glass).toBeEnabled());
    fireEvent.click(glass);
    await screen.findByRole('button', { name: 'Повторить без дубля' });
    expect(JSON.stringify(localStorage)).not.toContain('synthetic-session');
    first.unmount();
    render(demo);
    const retry = await screen.findByRole('button', { name: 'Повторить без дубля' });
    // The new demo context must persist its IndexedDB generation fence first.
    await waitFor(() => expect(retry).toBeEnabled());
    fireEvent.click(retry);
    await screen.findByText('Добавлено 250 мл');
    expect(requests).toHaveLength(2);
    expect(requests[1]).toEqual(requests[0]);
    expect(requests[0]?.body._hydration_retry_key).toBe(requests[0]?.headers['Idempotency-Key']);
  });

  it('waits for demo scope before consuming and focusing the water shortcut', async () => {
    Object.defineProperty(globalThis.crypto, 'subtle', {
      configurable: true,
      value: webcrypto.subtle,
    });
    const scroll = vi.fn();
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: scroll,
    });
    window.history.replaceState({}, '', '/demo?scenario=nutrition&hydration=quick');
    apiMock.mockImplementation((path: string) =>
      path === '/api/v1/me'
        ? Promise.resolve({ profile: { sex: 'female' } })
        : Promise.resolve({ ...day, demo_generation: 0 }),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <DemoRuntimeProvider sessionToken="synthetic-session" mapNavigationPath={(path) => path}>
        <QueryClientProvider client={queryClient}>
          <FeedbackProvider>
            <HydrationTracker diaryDate="2026-09-01" initialExpanded />
          </FeedbackProvider>
        </QueryClientProvider>
      </DemoRuntimeProvider>,
    );
    const glass = await screen.findByRole('button', { name: /Стакан.*250 мл/ });
    await waitFor(() => expect(glass).toHaveFocus());
    expect(scroll).toHaveBeenCalledTimes(1);
    expect(window.location.search).not.toContain('hydration=quick');
  });

  it('discards old demo pending state and delayed success after reset', async () => {
    Object.defineProperty(globalThis.crypto, 'subtle', {
      configurable: true,
      value: webcrypto.subtle,
    });
    let generation = 0;
    let resolveFirst: (entry: HydrationEntry) => void = () => {};
    const requests: Array<{ body: Record<string, unknown>; headers: Record<string, string> }> = [];
    apiMock.mockImplementation(
      (
        path: string,
        options?: {
          method?: string;
          body: Record<string, unknown>;
          headers: Record<string, string>;
        },
      ) => {
        if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
        if (path.startsWith('/api/v1/nutrition/hydration?'))
          return Promise.resolve({ ...day, demo_generation: generation });
        if (options?.method === 'POST') {
          requests.push({ body: options.body, headers: options.headers });
          if (requests.length === 1)
            return new Promise((resolve) => {
              resolveFirst = resolve;
            });
          return Promise.resolve({ ...day.entries[0], id: 12, volume_ml: 250 });
        }
        return Promise.resolve();
      },
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <DemoRuntimeProvider sessionToken="synthetic-session" mapNavigationPath={(path) => path}>
        <QueryClientProvider client={queryClient}>
          <FeedbackProvider>
            <HydrationTracker diaryDate="2026-09-01" />
          </FeedbackProvider>
        </QueryClientProvider>
      </DemoRuntimeProvider>,
    );
    const glass = await screen.findByRole('button', { name: /Стакан.*250 мл/ });
    await waitFor(() => expect(glass).toBeEnabled());
    // Await the persisted generation before sending the first request.
    // Otherwise the reset scenario can race the initial IndexedDB fence.
    await waitFor(() =>
      expect(
        Object.values(localStorage).some((value) => value.includes('"demoGeneration":0')),
      ).toBe(true),
    );
    fireEvent.click(glass);
    await waitFor(() => expect(requests).toHaveLength(1));
    generation = 1;
    await act(async () => {
      await queryClient.invalidateQueries();
    });
    await waitFor(() =>
      expect(
        Object.values(localStorage).some((value) => value.includes('"demoGeneration":1')),
      ).toBe(true),
    );
    const firstEntry = day.entries[0];
    if (!firstEntry) throw new Error('Missing hydration fixture');
    await act(async () => resolveFirst({ ...firstEntry, id: 11, volume_ml: 250 }));
    await waitFor(() => expect(glass).toBeEnabled());
    expect(screen.queryByText('Добавлено 250 мл')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Повторить без дубля' })).not.toBeInTheDocument();
    fireEvent.click(glass);
    await screen.findByText('Добавлено 250 мл');
    expect(requests).toHaveLength(2);
    expect(requests[0]?.body._hydration_generation).toBe(0);
    expect(requests[1]?.body._hydration_generation).toBe(1);
    expect(requests[1]?.headers['Idempotency-Key']).not.toBe(
      requests[0]?.headers['Idempotency-Key'],
    );
  });

  it('allows correcting a rejected volume and isolates unresolved requests by account', async () => {
    let posts = 0;
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
      if (path.startsWith('/api/v1/nutrition/hydration?')) return Promise.resolve(day);
      if (options?.method === 'POST') {
        posts += 1;
        if (posts === 1)
          return Promise.reject(Object.assign(new Error('Проверьте объём'), { status: 422 }));
        if (posts === 2) return Promise.reject(new Error('Нет соединения'));
        return Promise.resolve({ ...day.entries[0], id: 12, volume_ml: 250 });
      }
      return Promise.resolve();
    });
    const { rerender, queryClient } = renderTracker();
    const preset = await screen.findByRole('button', { name: /Стакан.*250 мл/ });
    fireEvent.click(preset);
    await screen.findByText('Проверьте объём');
    expect(screen.queryByRole('button', { name: 'Повторить без дубля' })).not.toBeInTheDocument();
    fireEvent.click(preset);
    await screen.findByRole('button', { name: 'Повторить без дубля' });

    await waitFor(() => expect(preset).toBeEnabled());
    sessionStorage.setItem(AUTHENTICATED_USER_ID_STORAGE_KEY, '8');
    fireEvent.click(preset);
    expect(posts).toBe(2);
    rerender(
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <HydrationTracker diaryDate="2026-09-01" />
        </FeedbackProvider>
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Повторить без дубля' })).not.toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /Стакан.*250 мл/ }));
    await screen.findByText('Добавлено 250 мл');
    expect(posts).toBe(3);
  });

  it('does not send a water request when shared storage cannot be written', async () => {
    const original = Storage.prototype.setItem;
    const broken = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (
      this: Storage,
      key,
      value,
    ) {
      if (key.startsWith('fit_cross_context_lock_') || key.startsWith('fit_hydration_pending_v2_'))
        throw new DOMException('full', 'QuotaExceededError');
      original.call(this, key, value);
    });
    try {
      renderTracker();
      fireEvent.click(await screen.findByRole('button', { name: /Стакан.*250 мл/ }));
      expect(await screen.findByText(/Не удалось безопасно сохранить напиток/)).toBeVisible();
      expect(
        apiMock.mock.calls.filter(
          ([path, options]) =>
            path === '/api/v1/nutrition/hydration/entries/v2' && options?.method === 'POST',
        ),
      ).toHaveLength(0);
    } finally {
      broken.mockRestore();
    }
  });

  it('keeps a shared retry when one tab is rejected while another is still saving', async () => {
    let rejectFirst: (reason: Error) => void = () => {};
    let resolveSecond: (entry: HydrationEntry) => void = () => {};
    const keys: string[] = [];
    apiMock.mockImplementation(
      (path: string, options?: { method?: string; headers?: Record<string, string> }) => {
        if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
        if (path.startsWith('/api/v1/nutrition/hydration?')) return Promise.resolve(day);
        if (options?.method === 'POST') {
          const key = options.headers?.['Idempotency-Key'];
          if (!key) throw new Error('Missing key');
          keys.push(key);
          if (keys.length === 1)
            return new Promise((_resolve, reject) => {
              rejectFirst = reject;
            });
          if (keys.length === 2)
            return new Promise((resolve) => {
              resolveSecond = resolve;
            });
          return Promise.resolve({ ...day.entries[0], id: 12, volume_ml: 250 });
        }
        return Promise.resolve();
      },
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <HydrationTracker diaryDate="2026-09-01" />
          <HydrationTracker diaryDate="2026-09-01" />
        </FeedbackProvider>
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.getAllByRole('region', { name: 'Гидратация' })).toHaveLength(2),
    );
    const regions = screen.getAllByRole('region', { name: 'Гидратация' });
    const first = within(regions[0]!);
    const second = within(regions[1]!);
    fireEvent.click(first.getByRole('button', { name: /Стакан.*250 мл/ }));
    await waitFor(() => expect(keys).toHaveLength(1));
    fireEvent.click(second.getByRole('button', { name: /Стакан.*250 мл/ }));
    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[1]).toBe(keys[0]);
    await act(async () => rejectFirst(Object.assign(new Error('Нет доступа'), { status: 403 })));
    expect(await first.findByRole('button', { name: 'Повторить без дубля' })).toBeVisible();
    const entry = day.entries[0];
    if (!entry) throw new Error('Missing hydration fixture');
    await act(async () => resolveSecond({ ...entry, id: 11, volume_ml: 250 }));
    await second.findByText('Добавлено 250 мл');
    await waitFor(() =>
      expect(first.queryByRole('button', { name: 'Повторить без дубля' })).not.toBeInTheDocument(),
    );
    fireEvent.click(first.getByRole('button', { name: /Стакан.*250 мл/ }));
    await waitFor(() => expect(keys).toHaveLength(3));
    expect(keys[2]).not.toBe(keys[0]);
  });

  it('does not restore a late failed request after logout and same-account login', async () => {
    let rejectRequest: (reason: Error) => void = () => {};
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
      if (path.startsWith('/api/v1/nutrition/hydration?')) return Promise.resolve(day);
      if (options?.method === 'POST')
        return new Promise((_resolve, reject) => {
          rejectRequest = reject;
        });
      return Promise.resolve();
    });
    renderTracker();
    fireEvent.click(await screen.findByRole('button', { name: /Стакан.*250 мл/ }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/hydration/entries/v2',
        expect.objectContaining({ method: 'POST' }),
      ),
    );
    localStorage.clear();
    discardChanged.mockReturnValue(true);
    await act(async () => rejectRequest(new Error('Нет соединения')));
    expect(
      Object.keys(localStorage).filter((key) => key.startsWith('fit_hydration_pending_v2_')),
    ).toHaveLength(0);
  });

  it.each([false, true])(
    'keeps water undo on the entry date when the response is delayed: %s',
    async (delayed) => {
      const firstEntry = day.entries[0];
      if (!firstEntry) throw new Error('Missing hydration entry fixture');
      const added = { ...firstEntry, id: 11, volume_ml: 250 };
      let resolveAdd: (entry: HydrationEntry) => void = () => {};
      const response = new Promise<HydrationEntry>((resolve) => {
        resolveAdd = resolve;
      });
      apiMock.mockImplementation((path: string, options?: { method?: string }) => {
        if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
        if (path.startsWith('/api/v1/nutrition/hydration?')) {
          return Promise.resolve(
            path.includes('2026-08-31')
              ? { ...day, diary_date: '2026-08-31', total_ml: 0, entries: [] }
              : day,
          );
        }
        if (options?.method === 'DELETE') return Promise.resolve();
        return delayed ? response : Promise.resolve(added);
      });

      const { rerender, queryClient } = renderTracker();
      const showDate = (diaryDate: string) =>
        rerender(
          <QueryClientProvider client={queryClient}>
            <FeedbackProvider>
              <HydrationTracker diaryDate={diaryDate} />
            </FeedbackProvider>
          </QueryClientProvider>,
        );

      fireEvent.click(await screen.findByRole('button', { name: /Стакан.*250 мл/ }));
      if (!delayed) expect(await screen.findByText('Добавлено 250 мл')).toBeVisible();
      if (delayed)
        await waitFor(() =>
          expect(apiMock).toHaveBeenCalledWith(
            '/api/v1/nutrition/hydration/entries/v2',
            expect.objectContaining({ method: 'POST' }),
          ),
        );

      showDate('2026-08-31');
      expect(await screen.findByText('0 из 2200 мл')).toBeVisible();
      if (delayed) {
        await act(async () => resolveAdd(added));
        await waitFor(() =>
          expect(screen.getByRole('button', { name: /Стакан.*250 мл/ })).toBeEnabled(),
        );
      }
      expect(screen.queryByText('Добавлено 250 мл')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Отменить' })).not.toBeInTheDocument();
      expect(apiMock).not.toHaveBeenCalledWith(
        '/api/v1/nutrition/hydration/entries/11',
        expect.objectContaining({ method: 'DELETE' }),
      );

      showDate('2026-09-01');
      expect(await screen.findByText('Добавлено 250 мл')).toBeVisible();
      fireEvent.click(screen.getByRole('button', { name: 'Отменить' }));
      await waitFor(() =>
        expect(apiMock).toHaveBeenCalledWith('/api/v1/nutrition/hydration/entries/11', {
          method: 'DELETE',
        }),
      );
    },
  );

  it('reveals adult/reference boundaries and history without hiding edit actions', async () => {
    renderTracker();
    fireEvent.click(await screen.findByText('Личный ориентир', { exact: true }));
    expect(screen.getByText(/для здоровых взрослых/i)).toBeVisible();
    expect(screen.getByLabelText('Мне 18 лет или больше')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'История за день' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Изменить' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Удалить' })).toBeVisible();
  });

  it('initializes the editor from an existing manual goal', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: null } });
      if (path.startsWith('/api/v1/nutrition/hydration?')) {
        return Promise.resolve({
          ...day,
          goal: {
            ...day.goal,
            id: 2,
            source: 'manual',
            method_version: 'manual-v1',
            target_ml: 3000,
            sex: null,
            adult_confirmed: null,
          },
        });
      }
      return Promise.resolve({});
    });

    renderTracker();
    fireEvent.click(await screen.findByText('Личный ориентир', { exact: true }));

    expect(screen.getByRole('radio', { name: 'Вручную' })).toBeChecked();
    expect(screen.getByLabelText('Ориентир, мл в день')).toHaveValue(3000);
  });

  it('reuses the persisted reference sex even when the profile has none', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: null } });
      if (path.startsWith('/api/v1/nutrition/hydration?')) {
        return Promise.resolve({ ...day, goal: { ...day.goal, target_ml: 3000, sex: 'male' } });
      }
      return Promise.resolve({});
    });

    renderTracker();
    fireEvent.click(await screen.findByText('Личный ориентир', { exact: true }));

    expect(screen.getByRole('radio', { name: 'По справочному ориентиру' })).toBeChecked();
    expect(screen.getByLabelText('Пол для справочного ориентира')).toHaveValue('male');
    expect(screen.getByLabelText('Мне 18 лет или больше')).toBeChecked();
    expect(screen.getByLabelText('Сохранить выбранный пол в профиле')).toBeVisible();
    fireEvent.click(await screen.findByText('Мои кружки и бутылки', { exact: true }));
    const presets = screen
      .getByText('Мои кружки и бутылки', { exact: true })
      .closest('details') as HTMLElement;
    expect(within(presets).getByRole('button', { name: 'Добавить' })).toBeVisible();
  });

  it('requires an explicit reference sex when the profile has none', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: null } });
      if (path.startsWith('/api/v1/nutrition/hydration?')) {
        return Promise.resolve({ ...day, goal: null });
      }
      return Promise.resolve({});
    });

    renderTracker();
    fireEvent.click(await screen.findByText('Личный ориентир', { exact: true }));

    const sex = screen.getByLabelText('Пол для справочного ориентира');
    expect(sex).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Сохранить ориентир' })).toBeDisabled();

    fireEvent.change(sex, { target: { value: 'male' } });
    fireEvent.click(screen.getByLabelText('Мне 18 лет или больше'));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить ориентир' }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/nutrition/hydration/goal',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({
            sex: 'male',
            adult_confirmed: true,
            save_sex_to_profile: false,
          }),
        }),
      ),
    );
  });
});
