import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  AiCoachExperience,
  AiCoachSettingsCard,
  safeCoachUrl,
} from '../../../../src/features/ai/AiCoachExperience';
import { api } from '../../../../src/shared/api/client';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import type { AiCoachStatus } from '../../../../src/shared/api/types';

vi.mock('../../../../src/shared/api/client', () => ({
  api: vi.fn(),
}));

vi.mock('../../../../src/shared/analytics/productEvents', () => ({
  productEventSurface: () => 'mobile_web',
  trackProductEvent: vi.fn(),
}));

const apiMock = vi.mocked(api);
const status = {
  ui_enabled: true,
  generic_available: true,
  personal_available: false,
} as const;

function renderExperience(experienceStatus: AiCoachStatus = status) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <AiCoachExperience entryPoint="profile" status={experienceStatus} />
      </NavigationProvider>
    </QueryClientProvider>,
  );
}

function renderSettingsCard(settingsStatus: AiCoachStatus) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AiCoachSettingsCard status={settingsStatus} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  apiMock.mockReset();
});

describe('AiCoachExperience', () => {
  it('accepts only credential-free HTTPS URLs', () => {
    expect(safeCoachUrl('https://example.org/article')).toBe('https://example.org/article');
    expect(safeCoachUrl('javascript:alert(1)')).toBeNull();
    expect(safeCoachUrl('https://user:pass@example.org/article')).toBeNull();
    expect(safeCoachUrl('https://example.org/article#secret')).toBeNull();
  });

  it('keeps personal mode controlled when the server says the capability is unavailable', () => {
    apiMock.mockResolvedValue({
      status: 'revoked',
      scope: 'personal_readonly_tools_v1',
      consent_version: 'ai-coach-personal-v1',
      categories: [],
      purpose: 'test',
      provider_name: 'groq',
      provider_policy_revision: 'test',
      retention_notice: 'test',
      consent_source: 'test',
      granted_at: null,
      revoked_at: null,
    });
    renderExperience();

    fireEvent.click(screen.getByRole('button', { name: 'Моя сводка' }));
    expect(screen.getByTestId('ai-coach-personal-unavailable')).toHaveTextContent(
      'Публичная помощь AI Coach остаётся отдельным режимом',
    );
    expect(screen.getByRole('button', { name: 'Публичная помощь' })).toBeInTheDocument();
  });

  it('does not expose the profile card outside the server-authorized cohort', () => {
    renderSettingsCard({
      ui_enabled: false,
      generic_available: false,
      personal_available: false,
    });

    expect(screen.queryByTestId('ai-coach-experience')).not.toBeInTheDocument();
    expect(screen.queryByText('AI Coach · внутренняя beta')).not.toBeInTheDocument();
  });

  it('renders a checked answer and citations without executing provider HTML or unknown links', async () => {
    apiMock.mockImplementation(async (path) => {
      if (path === '/api/v1/ai-coach/consent') {
        return {
          status: 'revoked',
          scope: 'personal_readonly_tools_v1',
          consent_version: 'ai-coach-personal-v1',
          categories: [],
          purpose: 'test',
          provider_name: 'groq',
          provider_policy_revision: 'test',
          retention_notice: 'test',
          consent_source: 'test',
          granted_at: null,
          revoked_at: null,
        };
      }
      if (path === '/api/v1/ai-coach/generate') {
        return {
          outcome: 'answer',
          answer:
            'Проверенный текст. <img src="/secret"> [Материал](https://example.org/article) [Чужая ссылка](https://evil.example/secret)',
          citations: [
            {
              title: 'Публичный материал',
              publisher: 'YFC',
              url: 'https://example.org/article',
              source_type: 'canonical_yfc',
            },
          ],
          limitations: ['Это автоматическая проверка beta-ответа.'],
          safety_category: 'clear',
          prompt_version: 'ai-coach-beta-v1',
          request_id: 'request-test',
        };
      }
      throw new Error(`unexpected path ${path}`);
    });
    renderExperience();
    fireEvent.click(screen.getByRole('button', { name: 'Разобраться с тренировкой' }));
    fireEvent.click(screen.getByRole('button', { name: 'Получить ответ' }));

    await waitFor(() => expect(screen.getByTestId('ai-coach-response')).toBeInTheDocument());
    expect(screen.getByText(/Проверенный текст/)).toBeInTheDocument();
    expect(screen.getByText(/<img src="\/secret">/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Материал' })).toHaveAttribute(
      'href',
      'https://example.org/article',
    );
    expect(screen.getByText(/Чужая ссылка/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Чужая ссылка' })).not.toBeInTheDocument();
  });

  it('sends a bounded custom period and renders grounded insight groups', async () => {
    apiMock.mockImplementation(async (path, options) => {
      if (path === '/api/v1/ai-coach/consent') {
        return {
          status: 'granted',
          scope: 'personal_readonly_tools_v1',
          consent_version: 'ai-coach-personal-v1',
          categories: ['personal_progress', 'training_history', 'nutrition_summary'],
          purpose: 'test',
          provider_name: 'groq',
          provider_policy_revision: 'test',
          retention_notice: 'test',
          consent_source: 'test',
          granted_at: null,
          revoked_at: null,
        };
      }
      if (path === '/api/v1/ai-coach/personal/generate') {
        expect(options?.body).toEqual({
          tool: 'get_period_report_insights',
          period_days: 30,
          period: 'custom',
          date_from: '2026-09-01',
          date_to: '2026-09-07',
          message:
            'Сделай краткий итог моего канонического отчёта за выбранный период: факты, ограничения данных и 1–3 обратимых следующих шага.',
        });
        return {
          outcome: 'answer',
          answer:
            'Главное за период\n\n- Выполнено 3 тренировки.\n\nОграничения данных\n\n- Питание заполнено не полностью.\n\nЧто можно сделать дальше\n\n- Заполнить пропуски.\n\nПочему\n\n- Основание в отчёте.',
          citations: [
            {
              title: 'Канонический отчёт',
              publisher: 'YFC',
              url: 'https://your-fitness-coach.ru/progress',
              source_type: 'personal_tool_screen',
            },
          ],
          insights: [
            {
              kind: 'fact',
              text: 'За период выполнено 3 тренировки.',
              evidence_ids: ['training.completed_workouts'],
              reason_keys: [],
            },
            {
              kind: 'suggestion',
              text: 'Заполнить пропуски и повторить запрос.',
              evidence_ids: ['nutrition.logged_days'],
              reason_keys: ['nutrition_missing_days'],
            },
          ],
          limitations: ['Пропущенные дни не считаются нулевыми.'],
          safety_category: 'clear',
          prompt_version: 'ai-coach-period-report-v1',
          request_id: 'period-request',
          report_version: 'progress-report-v1',
          input_version: 'ai-coach-period-report-input-v1',
          output_version: 'ai-coach-period-report-output-v1',
          report_revision: 'revision-test',
          period_start: '2026-09-01',
          period_end: '2026-09-07',
          timezone: 'Europe/Moscow',
        };
      }
      throw new Error(`unexpected path ${path}`);
    });
    renderExperience({ ...status, personal_available: true });

    fireEvent.click(screen.getByRole('button', { name: 'Моя сводка' }));
    await waitFor(() => expect(screen.getByTestId('ai-coach-consent-granted')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Итог периода' }));
    fireEvent.change(screen.getByLabelText('Период сводки'), {
      target: { value: 'custom' },
    });
    fireEvent.change(screen.getByLabelText('Начало периода'), {
      target: { value: '2026-09-01' },
    });
    fireEvent.change(screen.getByLabelText('Окончание периода'), {
      target: { value: '2026-09-07' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Получить ответ' }));

    await waitFor(() => expect(screen.getByTestId('ai-coach-period-insights')).toBeInTheDocument());
    expect(screen.getByText('За период выполнено 3 тренировки.')).toBeInTheDocument();
    expect(
      screen.getByText('Основание: пропущенные дни питания отделены от нулевых значений.'),
    ).toBeInTheDocument();
    expect(screen.getByText(/Канонический отчёт progress-report-v1/)).toBeInTheDocument();
  });
});
