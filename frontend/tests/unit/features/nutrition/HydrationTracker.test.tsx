import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HydrationTracker } from '../../../../src/features/nutrition/HydrationTracker';
import type { HydrationDay } from '../../../../src/shared/api/types';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import {
  PRODUCT_EVENT_NAME,
  type ProductEventEnvelope,
} from '../../../../src/shared/analytics/productEvents';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
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
    window.history.replaceState({}, '', '/app?section=nutrition');
    apiMock.mockReset();
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/me') return Promise.resolve({ profile: { sex: 'female' } });
      if (path.startsWith('/api/v1/nutrition/hydration?')) return Promise.resolve(day);
      return Promise.resolve({ ...day.entries[0], id: 11, volume_ml: 250 });
    });
  });

  afterEach(() => {
    cleanup();
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
        '/api/v1/nutrition/hydration/entries',
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

  it('reveals adult/reference boundaries and history without hiding edit actions', async () => {
    renderTracker();
    fireEvent.click(await screen.findByRole('button', { name: 'Другой напиток, история и цель' }));
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
    fireEvent.click(await screen.findByRole('button', { name: 'Другой напиток, история и цель' }));

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
    fireEvent.click(await screen.findByRole('button', { name: 'Другой напиток, история и цель' }));

    expect(screen.getByRole('radio', { name: 'По справочному ориентиру' })).toBeChecked();
    expect(screen.getByLabelText('Пол для справочного ориентира')).toHaveValue('male');
    expect(screen.getByLabelText('Мне 18 лет или больше')).toBeChecked();
    expect(screen.getByLabelText('Сохранить выбранный пол в профиле')).toBeVisible();
    const presets = screen
      .getByRole('heading', { name: 'Мои кружки и бутылки' })
      .closest('section') as HTMLElement;
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
    fireEvent.click(await screen.findByRole('button', { name: 'Другой напиток, история и цель' }));

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
