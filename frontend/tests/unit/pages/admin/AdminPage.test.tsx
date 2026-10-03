import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AdminPage from '../../../../src/pages/admin/AdminPage';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import { NavigationProvider } from '../../../../src/shared/navigation/router';

const mocks = vi.hoisted(() => ({
  user: {
    id: 1,
    is_admin: true,
    is_root: true,
    is_coach: false,
  },
}));

vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => ({ user: mocks.user }),
}));

vi.mock('../../../../src/app/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const searchRow = {
  id: 2,
  telegram_user_id: 71020,
  username: 'long_support_identifier',
  display_name: 'Очень длинное имя пользователя для проверки переноса',
  is_active: true,
  is_trainer: true,
  is_root: false,
  created_at: '2030-01-01T10:00:00',
  linked_providers: ['google', 'telegram'],
};

const detail = {
  ...searchRow,
  identities: [
    {
      provider: 'google',
      identifier: 'l***@example.com',
      verified: true,
      last_login_at: '2030-01-02T10:00:00',
    },
  ],
  relationships: [
    {
      id: 9,
      account_role: 'trainer',
      counterparty_user_id: 3,
      counterparty_name: 'Клиент с длинным именем',
      status: 'active',
      created_at: '2030-01-01T10:00:00',
      accepted_at: '2030-01-01T10:00:00',
      ended_at: null,
      ended_reason: null,
      can_end: true,
    },
  ],
  jobs: [
    {
      job_id: 'notification:10',
      kind: 'notification',
      user_id: 2,
      status: 'failed',
      created_at: '2030-01-03T10:00:00',
      scheduled_for: '2030-01-03T10:00:00',
      completed_at: null,
      attempt_count: 3,
      error_code: null,
      retry_allowed: false,
    },
    {
      job_id: 'export:71020000-0000-0000-0000-000000000000',
      kind: 'account_export',
      user_id: 2,
      status: 'error',
      created_at: '2030-01-03T09:00:00',
      scheduled_for: null,
      completed_at: '2030-01-03T09:01:00',
      attempt_count: null,
      error_code: 'generation_failed',
      retry_allowed: true,
    },
  ],
  audit_history: [
    {
      id: 20,
      action: 'root.account_blocked',
      actor_user_id: 1,
      target_user_id: 2,
      resource_type: 'user',
      resource_id: '2',
      reason: 'security_incident',
      created_at: '2030-01-04T10:00:00',
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <FeedbackProvider>
          <AdminPage />
        </FeedbackProvider>
      </NavigationProvider>
    </QueryClientProvider>,
  );
}

describe('AdminPage', () => {
  beforeEach(() => {
    mocks.user.is_root = true;
    Object.defineProperty(window, 'Telegram', { configurable: true, value: undefined });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.startsWith('/api/v1/admin/users?q=')) {
        return new Response(JSON.stringify([searchRow]), { status: 200 });
      }
      if (path === '/api/v1/admin/users/2' && (!init?.method || init.method === 'GET')) {
        return new Response(JSON.stringify(detail), { status: 200 });
      }
      if (path === '/api/v1/admin/users/2/status' && init?.method === 'PATCH') {
        return new Response(JSON.stringify({ ...detail, is_active: false }), { status: 200 });
      }
      if (path === '/api/v1/admin/jobs') {
        return new Response(JSON.stringify(detail.jobs), { status: 200 });
      }
      if (path === '/api/v1/admin/funnel?period_days=30') {
        return new Response(
          JSON.stringify({
            period_days: 30,
            cohort_since: '2030-01-01T00:00:00',
            cohort_until: '2030-01-31T00:00:00',
            as_of: '2030-01-31T00:00:00',
            cohort_size: 10,
            complete_weekly_cohorts: 1,
            eligible_real_account_count: 10,
            analytics_provider_status: 'not_connected',
            coverage_note: 'Только агрегаты подтверждённых данных аккаунта.',
            effect_status: 'NOT_YET_PROVEN',
            effect_note: 'Эффект пока не подтверждён.',
            exclusions: [],
            data_quality: {
              status: 'clean',
              duplicate_milestones: 0,
              impossible_order: 0,
              client_success_without_server: 0,
              invalid_milestones: 0,
              excluded_role_accounts: 0,
              timezone_fallback_accounts: 0,
            },
            kpis: [
              {
                key: 'activation_rate',
                numerator: 6,
                denominator: 10,
                cohort_size: 10,
                rate_percent: 60,
                median_seconds: null,
                window: 'первые 24 часа',
              },
              {
                key: 'time_to_first_useful_action',
                numerator: 5,
                denominator: 10,
                cohort_size: 10,
                rate_percent: 50,
                median_seconds: 3600,
                window: 'до первой тренировки',
              },
              {
                key: 'first_workout_completion_rate',
                numerator: 4,
                denominator: 5,
                cohort_size: 10,
                rate_percent: 80,
                median_seconds: null,
                window: 'до 72 часов',
              },
              {
                key: 'first_week_value_rate',
                numerator: 3,
                denominator: 8,
                cohort_size: 10,
                rate_percent: 37.5,
                median_seconds: null,
                window: 'первые 7 дней',
              },
              {
                key: 'd1_meaningful_return',
                numerator: 4,
                denominator: 8,
                cohort_size: 10,
                rate_percent: 50,
                median_seconds: null,
                window: 'следующий день',
              },
              {
                key: 'd7_meaningful_return',
                numerator: 3,
                denominator: 6,
                cohort_size: 10,
                rate_percent: 50,
                median_seconds: null,
                window: 'седьмой день',
              },
              {
                key: 'd30_meaningful_return',
                numerator: 1,
                denominator: 2,
                cohort_size: 10,
                rate_percent: 50,
                median_seconds: null,
                window: 'тридцатый день',
              },
              {
                key: 'missed_workout_recovery_conversion',
                numerator: 2,
                denominator: 4,
                cohort_size: 10,
                rate_percent: 50,
                median_seconds: null,
                window: 'после пропуска',
              },
              {
                key: 'nutrition_repeat_rate',
                numerator: 2,
                denominator: 5,
                cohort_size: 10,
                rate_percent: 40,
                median_seconds: null,
                window: 'первые 7 дней',
              },
              {
                key: 'weekly_loop_completion',
                numerator: 1,
                denominator: 8,
                cohort_size: 10,
                rate_percent: 12.5,
                median_seconds: null,
                window: 'первые 7 дней',
              },
            ],
          }),
          { status: 200 },
        );
      }
      if (path === '/api/v1/admin/audit') {
        return new Response(JSON.stringify(detail.audit_history), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('ведёт Root по одному scan path от поиска к деталям и безопасным status rows', async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText('Безопасный идентификатор'), {
      target: { value: '@long_support_identifier' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Найти' }));
    fireEvent.click(
      await screen.findByRole('button', {
        name: /Очень длинное имя пользователя для проверки переноса/,
      }),
    );

    expect(
      await screen.findByRole('heading', { name: searchRow.display_name }),
    ).toBeInTheDocument();
    expect(screen.getByText('l***@example.com')).toBeInTheDocument();
    expect(screen.getByText('Связанные способы входа')).toBeInTheDocument();
    expect(screen.getByText('История аудита')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Повторить экспорт' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /повтор.*уведом/i })).not.toBeInTheDocument();
    expect(screen.queryByText('Заявки тренеров')).not.toBeInTheDocument();
    expect(screen.queryByText('Шаблоны программ')).not.toBeInTheDocument();
    expect(screen.queryByText(/Назначить админом/)).not.toBeInTheDocument();
  });

  it('показывает subject и allowlisted reason до подтверждения блокировки', async () => {
    renderPage();
    fireEvent.change(screen.getByLabelText('Безопасный идентификатор'), {
      target: { value: '71020' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Найти' }));
    fireEvent.click(
      await screen.findByRole('button', { name: new RegExp(searchRow.display_name) }),
    );
    const block = await screen.findByRole('button', {
      name: `Заблокировать ${searchRow.display_name}`,
    });
    fireEvent.click(block);

    const dialog = screen.getByRole('dialog', {
      name: `Заблокировать ${searchRow.display_name}`,
    });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText(/Причина: Запрос поддержки/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Подтвердить блокировку' }));

    await waitFor(() => {
      const call = vi
        .mocked(fetch)
        .mock.calls.find(([input]) => String(input).includes('/api/v1/admin/users/2/status'));
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        is_active: false,
        reason: 'support_request',
      });
    });
  });

  it('показывает controlled permission state для не-Root web account', () => {
    mocks.user.is_root = false;
    renderPage();

    expect(screen.getByRole('heading', { name: 'Root-доступ не подтверждён' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Вернуться в личный режим' })).toHaveAttribute(
      'href',
      '/app',
    );
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it('показывает controlled search error и восстанавливается через retry', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Сервис поиска временно недоступен' }), {
        status: 503,
      }),
    );
    renderPage();

    fireEvent.change(screen.getByLabelText('Безопасный идентификатор'), {
      target: { value: '@long_support_identifier' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Найти' }));

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Сервис поиска временно недоступен')).toBeInTheDocument();
    fireEvent.click(within(alert).getByRole('button', { name: 'Повторить' }));

    expect(
      await screen.findByRole('button', {
        name: /Очень длинное имя пользователя для проверки переноса/,
      }),
    ).toBeInTheDocument();
  });

  it('показывает агрегаты без raw events и отдельный audit history', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Агрегаты' }));

    expect(await screen.findByText('60%')).toBeInTheDocument();
    expect(screen.getByText('Данные проверены')).toBeInTheDocument();
    expect(screen.getByText('Только агрегаты подтверждённых данных аккаунта.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Аудит' }));
    expect(await screen.findByText('Аккаунт заблокирован')).toBeInTheDocument();
    expect(screen.getByText('Инцидент безопасности')).toBeInTheDocument();
  });
});
