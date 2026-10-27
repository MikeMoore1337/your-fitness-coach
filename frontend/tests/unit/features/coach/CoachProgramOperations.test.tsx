import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type {
  Client,
  CoachAssignedProgram,
  ProgramTemplate,
} from '../../../../src/shared/api/types';
import { CoachProgramOperations } from '../../../../src/features/coach/CoachProgramOperations';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const template = {
  id: 15,
  title: 'Базовая программа',
  default_duration_weeks: 6,
  goal: 'recomposition',
  level: 'intermediate',
  days: [],
} as unknown as ProgramTemplate;

const clients = [
  { id: 71, status: 'active', full_name: 'Анна' },
  { id: 72, status: 'active', full_name: 'Иван' },
] as Client[];

function renderOperations(programs: CoachAssignedProgram[] = []) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <CoachProgramOperations clients={clients} programs={programs} />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('CoachProgramOperations', () => {
  it('reviews shared template assignment and reports each client result', async () => {
    const assignmentRequests: Array<{ url: string; body: Record<string, unknown> }> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/api/v1/programs/templates/mine')) {
        return new Response(JSON.stringify([template]), { status: 200 });
      }
      if (url.includes('/api/v1/coach/clients/72/templates/15/assign')) {
        assignmentRequests.push({ url, body: JSON.parse(String(init?.body)) });
        return new Response(JSON.stringify({ detail: 'У клиента уже есть активная программа' }), {
          status: 409,
        });
      }
      if (url.includes('/api/v1/coach/clients/71/templates/15/assign')) {
        assignmentRequests.push({ url, body: JSON.parse(String(init?.body)) });
        return new Response(
          JSON.stringify({
            user_program_id: 501,
            workouts_created: 18,
            status: 'scheduled',
            start_date: '2026-09-30',
            duration_weeks: 6,
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: `Unexpected request: ${url}` }), {
        status: 500,
      });
    });
    renderOperations();

    fireEvent.change(await screen.findByLabelText('Базовый шаблон'), {
      target: { value: '15' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: /Анна/ }));
    fireEvent.click(screen.getByRole('checkbox', { name: /Иван/ }));
    expect(screen.getByText(/активная программа автоматически не заменяется/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Назначить выбранным · 2' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Назначить 2' }));

    expect(await screen.findByText('программа назначена')).toBeInTheDocument();
    expect(await screen.findByText(/У клиента уже есть активная программа/)).toBeInTheDocument();
    await waitFor(() => expect(assignmentRequests).toHaveLength(2));
    expect(assignmentRequests.map(({ body }) => body)).toEqual([
      { duration_weeks: 6, replace_active: false },
      { duration_weeks: 6, replace_active: false },
    ]);
    expect(screen.getByRole('checkbox', { name: /Иван/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Анна/ })).not.toBeChecked();
  });

  it('clones the selected template through the provenance-preserving endpoint', async () => {
    const cloneRequest = vi.fn();
    const clonedTemplate = { ...template, id: 16, title: 'Базовая программа (копия)' };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/api/v1/programs/templates/mine')) {
        return new Response(JSON.stringify([template, clonedTemplate]), { status: 200 });
      }
      if (url.endsWith('/api/v1/programs/templates/15/clone')) {
        cloneRequest(init);
        return new Response(JSON.stringify(clonedTemplate), { status: 201 });
      }
      return new Response(JSON.stringify({ detail: `Unexpected request: ${url}` }), {
        status: 500,
      });
    });
    renderOperations();

    fireEvent.change(await screen.findByLabelText('Базовый шаблон'), {
      target: { value: '15' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Создать копию выбранного шаблона' }));
    expect(
      screen.getByText(/Исходная программа и назначения клиентов не изменятся/),
    ).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: 'Создать копию' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Создана копия «Базовая программа (копия)»',
    );
    expect(cloneRequest).toHaveBeenCalledWith(expect.objectContaining({ method: 'POST' }));
    expect(await screen.findByLabelText('Базовый шаблон')).toHaveValue('16');
  });
});
