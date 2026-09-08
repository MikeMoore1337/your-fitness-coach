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

function renderExperience() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <NavigationProvider>
        <AiCoachExperience entryPoint="profile" status={status} />
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
});
