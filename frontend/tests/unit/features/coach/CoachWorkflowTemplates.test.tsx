import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CoachWorkflowTemplates } from '../../../../src/features/coach/CoachWorkflowTemplates';
import type { Client } from '../../../../src/shared/api/types';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const clients = [{ id: 71, status: 'active', full_name: 'Анна' }] as Client[];

const onboardingTemplate = {
  id: 11,
  name: 'Первые шаги',
  description: 'Порядок подключения',
  is_active: true,
  current_version: {
    id: 21,
    version: 2,
    steps: ['invite', 'goals'],
    program_template_id: null,
    check_in_template_id: null,
    created_at: '2026-10-08T08:00:00Z',
  },
  assignments: [],
  created_at: '2026-10-08T08:00:00Z',
  updated_at: '2026-10-08T08:00:00Z',
};

const communicationTemplate = {
  id: 12,
  name: 'После встречи',
  description: 'Короткое сообщение',
  is_active: true,
  current_version: {
    id: 22,
    version: 1,
    subject: 'Первые шаги',
    body: 'Проверьте план и напишите тренеру.',
    created_at: '2026-10-08T08:00:00Z',
  },
  drafts: [
    {
      id: 31,
      client_id: 71,
      client_name: 'Анна',
      version: 1,
      status: 'draft',
      updated_at: '2026-10-08T08:00:00Z',
      confirmed_at: null,
    },
  ],
  created_at: '2026-10-08T08:00:00Z',
  updated_at: '2026-10-08T08:00:00Z',
};

function renderTemplates() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <CoachWorkflowTemplates clients={clients} />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

function mockReadRoutes() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith('/workflow-templates/onboarding')) {
      return new Response(JSON.stringify({ items: [onboardingTemplate] }), { status: 200 });
    }
    if (url.endsWith('/workflow-templates/communication')) {
      return new Response(JSON.stringify({ items: [communicationTemplate] }), { status: 200 });
    }
    if (url.endsWith('/programs/templates/mine')) {
      return new Response(JSON.stringify([]), { status: 200 });
    }
    if (url.endsWith('/check-in-templates')) {
      return new Response(JSON.stringify({ items: [], field_catalog: [] }), { status: 200 });
    }
    return new Response(JSON.stringify({ detail: `Неожиданный запрос: ${url}` }), { status: 500 });
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('CoachWorkflowTemplates', () => {
  it('renders Russian onboarding and communication surfaces without mixed English copy', async () => {
    mockReadRoutes();
    renderTemplates();

    expect(
      await screen.findByRole('heading', { name: 'Подключение клиентов и сообщения' }),
    ).toBeVisible();
    expect(screen.getByText('Первые шаги')).toBeVisible();
    expect(screen.getByText('История назначений')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Открыть черновик' })).toBeVisible();
    expect(document.body.textContent).not.toMatch(/follow-up|review|rollout|nutrition planning/i);
  });

  it('keeps onboarding stages label-associated and toggles once from the card or checkbox', async () => {
    mockReadRoutes();
    renderTemplates();

    const questionnaire = await screen.findByRole('checkbox', { name: 'Анкета' });
    expect(questionnaire).not.toBeChecked();
    expect(screen.getByLabelText('Анкета')).toBe(questionnaire);

    fireEvent.click(screen.getByText('Анкета', { exact: true }));
    expect(questionnaire).toBeChecked();

    fireEvent.click(questionnaire);
    expect(questionnaire).not.toBeChecked();
  });

  it('edits a draft and sends it only after explicit confirmation', async () => {
    const requests: Array<{ url: string; method: string; body?: Record<string, unknown> }> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      const method = String(init?.method ?? 'GET');
      const body = init?.body
        ? (JSON.parse(String(init.body)) as Record<string, unknown>)
        : undefined;
      requests.push({ url, method, body });
      if (url.endsWith('/workflow-templates/onboarding')) {
        return new Response(JSON.stringify({ items: [onboardingTemplate] }), { status: 200 });
      }
      if (url.endsWith('/workflow-templates/communication')) {
        return new Response(JSON.stringify({ items: [communicationTemplate] }), { status: 200 });
      }
      if (url.endsWith('/programs/templates/mine')) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (url.endsWith('/check-in-templates')) {
        return new Response(JSON.stringify({ items: [], field_catalog: [] }), { status: 200 });
      }
      if (url.endsWith('/communication-drafts/31') && method === 'PATCH') {
        return new Response(
          JSON.stringify({
            id: 31,
            template_id: 12,
            client_id: 71,
            client_name: 'Анна',
            version: 1,
            subject: body?.subject,
            body: body?.body,
            status: 'draft',
            notification_id: null,
            created_at: '2026-10-08T08:00:00Z',
            updated_at: '2026-10-08T08:04:00Z',
            confirmed_at: null,
          }),
          { status: 200 },
        );
      }
      if (url.endsWith('/communication-drafts/31') && method === 'GET') {
        return new Response(
          JSON.stringify({
            id: 31,
            template_id: 12,
            client_id: 71,
            client_name: 'Анна',
            version: 1,
            subject: 'Первые шаги',
            body: 'Проверьте план и напишите тренеру.',
            status: 'draft',
            notification_id: null,
            created_at: '2026-10-08T08:00:00Z',
            updated_at: '2026-10-08T08:00:00Z',
            confirmed_at: null,
          }),
          { status: 200 },
        );
      }
      if (url.endsWith('/communication-drafts/31/confirm')) {
        return new Response(
          JSON.stringify({
            id: 31,
            template_id: 12,
            client_id: 71,
            client_name: 'Анна',
            version: 1,
            subject: 'Проверка плана',
            body: 'Напишите тренеру после проверки.',
            status: 'confirmed',
            notification_id: 55,
            created_at: '2026-10-08T08:00:00Z',
            updated_at: '2026-10-08T08:05:00Z',
            confirmed_at: '2026-10-08T08:05:00Z',
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: `Неожиданный запрос: ${url}` }), {
        status: 500,
      });
    });
    renderTemplates();

    fireEvent.click(await screen.findByRole('button', { name: 'Открыть черновик' }));
    const subject = await screen.findByDisplayValue('Первые шаги');
    fireEvent.change(subject, { target: { value: 'Проверка плана' } });
    fireEvent.change(screen.getByDisplayValue('Проверьте план и напишите тренеру.'), {
      target: { value: 'Напишите тренеру после проверки.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить изменения' }));
    await waitFor(() =>
      expect(
        requests.some(
          (request) =>
            request.method === 'PATCH' &&
            request.body?.subject === 'Проверка плана' &&
            request.body?.body === 'Напишите тренеру после проверки.',
        ),
      ).toBe(true),
    );

    expect(requests.some((request) => request.url.endsWith('/confirm'))).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить сообщение' }));
    await waitFor(() =>
      expect(requests.some((request) => request.url.endsWith('/confirm'))).toBe(true),
    );
    expect(await screen.findByText('Сообщение подтверждено')).toBeVisible();
  });
});
