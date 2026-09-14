import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TemplatesList } from '../../../../src/features/programs/TemplatesList';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import { NavigationProvider } from '../../../../src/shared/navigation/router';

vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      profile: {
        timezone: 'Europe/Moscow',
        goal: 'recomposition',
        level: 'beginner',
        workouts_per_week: 3,
      },
    },
    reloadUser: vi.fn(),
  }),
}));

vi.mock('../../../../src/features/programs/ProgramBuilder', () => ({
  ProgramBuilder: ({
    editingTemplate,
    saveAsCopy,
  }: {
    editingTemplate: { title: string };
    saveAsCopy: boolean;
  }) => <div>{`${saveAsCopy ? 'copy' : 'update'}:${editingTemplate.title}`}</div>,
}));

const templateBase = {
  slug: 'template',
  goal: 'recomposition',
  level: 'intermediate',
  owner_user_id: null,
  owner_telegram_user_id: null,
  owner_full_name: null,
  created_by_user_id: null,
  is_public: true,
  is_assigned_to_current_user: false,
  is_active_for_current_user: false,
  assigned_by_user_id: null,
  assigned_by_full_name: null,
  days: [
    {
      id: 1,
      day_number: 1,
      title: 'День 1',
      exercises: [
        {
          id: 1,
          exercise_id: 1,
          exercise_title: 'Приседания',
          prescribed_sets: 3,
          prescribed_reps: '8',
          rest_seconds: 90,
          notes: null,
          has_guide: true,
        },
      ],
    },
  ],
};

function renderList(mode: 'full' | 'summary' = 'full') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <NavigationProvider>
          <TemplatesList mode={mode} />
        </NavigationProvider>
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('TemplatesList editing', () => {
  let activeProgram = true;
  let deleteResponse: (() => Promise<Response>) | null = null;

  beforeEach(() => {
    activeProgram = true;
    deleteResponse = null;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method?.toUpperCase() ?? 'GET';
      if (path === '/api/v1/programs/templates/mine') {
        return new Response(
          JSON.stringify([
            {
              ...templateBase,
              id: 10,
              title: 'Готовый шаблон',
              is_example: true,
              can_edit: false,
            },
            {
              ...templateBase,
              id: 11,
              title: 'Моя программа',
              slug: 'custom-template',
              is_example: false,
              can_edit: true,
              is_public: false,
              owner_user_id: 1,
            },
            {
              ...templateBase,
              id: 12,
              title: 'Активная программа',
              slug: 'active-template',
              is_example: false,
              can_edit: true,
              is_public: false,
              owner_user_id: 1,
              is_active_for_current_user: activeProgram,
              assigned_program_id: 42,
            },
          ]),
          { status: 200 },
        );
      }
      if (path === '/api/v1/programs/assigned/42' && method === 'DELETE') {
        if (deleteResponse) return deleteResponse();
        activeProgram = false;
        return new Response(null, { status: 204 });
      }
      if (path.startsWith('/api/v1/programs/templates/') && method === 'DELETE') {
        return new Response(null, { status: 204 });
      }
      if (path === '/api/v1/programs/templates/hidden') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (path === '/api/v1/programs/templates/recommendation') {
        return new Response(
          JSON.stringify({
            status: 'recommended',
            criteria: {
              goal: 'recomposition',
              experience: 'beginner',
              workouts_per_week: 3,
              training_location: null,
              available_equipment_ids: null,
              profile_fields_used: [],
            },
            missing_fields: [],
            message: 'Сначала посмотрите состав программы.',
            recommendation: {
              template: {
                ...templateBase,
                id: 20,
                title: 'Фуллбади по правилам',
                split_type: 'full_body',
                is_example: true,
                can_edit: false,
              },
              reason: 'Подходит по цели, уровню и частоте.',
              fit_facts: ['Три тренировки за цикл.'],
              limitations: ['Оборудование не проверялось.'],
            },
            alternatives: [],
            requires_explicit_start: true,
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('opens a personal copy editor for a ready-made template', async () => {
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: 'Настроить копию' }));

    expect(screen.getByText('copy:Готовый шаблон')).toBeInTheDocument();
  });

  it('updates an owned template directly', async () => {
    renderList();

    const programCard = (
      await screen.findByRole('button', { name: 'Посмотреть программу «Моя программа»' })
    ).closest('article');
    expect(programCard).not.toBeNull();
    fireEvent.click(within(programCard!).getByRole('button', { name: 'Редактировать' }));

    expect(screen.getByText('update:Моя программа')).toBeInTheDocument();
  });

  it('shows that the active program is already assigned', async () => {
    renderList();

    expect(await screen.findByRole('heading', { name: 'Активная программа' })).toBeInTheDocument();
    expect(screen.getByText('Активна')).toBeInTheDocument();
  });

  it('shows assigned-program deletion only in full management mode', async () => {
    renderList();

    const activeSection = (
      await screen.findByRole('heading', { name: 'Активная программа' })
    ).closest('section');
    expect(activeSection).not.toBeNull();
    expect(within(activeSection!).getByText('Другие действия')).toBeInTheDocument();

    fireEvent.click(within(activeSection!).getByText('Другие действия'));
    expect(
      within(activeSection!).getByRole('button', { name: 'Удалить программу' }),
    ).toBeInTheDocument();

    cleanup();
    renderList('summary');
    const summarySection = (
      await screen.findByRole('heading', { name: 'Активная программа' })
    ).closest('section');
    expect(summarySection).not.toBeNull();
    expect(within(summarySection!).queryByText('Другие действия')).not.toBeInTheDocument();
    expect(
      within(summarySection!).queryByRole('button', { name: 'Удалить программу' }),
    ).not.toBeInTheDocument();
  });

  it('confirms assigned-program deletion and sends the assigned program id', async () => {
    renderList();
    const activeSection = (
      await screen.findByRole('heading', { name: 'Активная программа' })
    ).closest('section');
    fireEvent.click(within(activeSection!).getByText('Другие действия'));
    fireEvent.click(within(activeSection!).getByRole('button', { name: 'Удалить программу' }));

    const dialog = await screen.findByRole('dialog', { name: 'Удалить текущую программу?' });
    expect(
      within(dialog).getByText(
        'Программа перестанет быть активной, а будущие запланированные тренировки будут отменены. История выполненных тренировок и сам шаблон программы сохранятся.',
      ),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Удалить программу' }));

    expect(await screen.findByRole('heading', { name: 'План ещё не выбран' })).toBeInTheDocument();
    expect(await screen.findByText('Программа удалена')).toBeInTheDocument();
    const deleteCalls = vi
      .mocked(globalThis.fetch)
      .mock.calls.filter(
        ([input, init]) =>
          String(input) === '/api/v1/programs/assigned/42' && init?.method === 'DELETE',
      );
    expect(deleteCalls).toHaveLength(1);
    expect(
      vi
        .mocked(globalThis.fetch)
        .mock.calls.map(([input]) => String(input))
        .filter((path) => path.includes('/templates/12')),
    ).toHaveLength(0);
  });

  it('does not delete when confirmation is cancelled', async () => {
    renderList();
    const activeSection = (
      await screen.findByRole('heading', { name: 'Активная программа' })
    ).closest('section');
    fireEvent.click(within(activeSection!).getByText('Другие действия'));
    fireEvent.click(within(activeSection!).getByRole('button', { name: 'Удалить программу' }));
    const dialog = await screen.findByRole('dialog', { name: 'Удалить текущую программу?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Отмена' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(
      vi
        .mocked(globalThis.fetch)
        .mock.calls.some(([input]) => String(input) === '/api/v1/programs/assigned/42'),
    ).toBe(false);
  });

  it('maps an in-progress deletion conflict to the user-facing message', async () => {
    deleteResponse = async () =>
      new Response(
        JSON.stringify({ detail: 'Cannot delete a program while a workout is in progress' }),
        { status: 409, headers: { 'Content-Type': 'application/json' } },
      );
    renderList();
    const activeSection = (
      await screen.findByRole('heading', { name: 'Активная программа' })
    ).closest('section');
    fireEvent.click(within(activeSection!).getByText('Другие действия'));
    fireEvent.click(within(activeSection!).getByRole('button', { name: 'Удалить программу' }));
    const dialog = await screen.findByRole('dialog', { name: 'Удалить текущую программу?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Удалить программу' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'Сначала завершите текущую тренировку - во время неё программу удалить нельзя.',
    );
    expect(screen.getByRole('heading', { name: 'Активная программа' })).toBeInTheDocument();
  });

  it('disables repeated deletion while the request is pending', async () => {
    let resolveDelete!: (response: Response) => void;
    deleteResponse = () => new Promise<Response>((resolve) => (resolveDelete = resolve));
    renderList();
    const activeSection = (
      await screen.findByRole('heading', { name: 'Активная программа' })
    ).closest('section');
    fireEvent.click(within(activeSection!).getByText('Другие действия'));
    fireEvent.click(within(activeSection!).getByRole('button', { name: 'Удалить программу' }));
    const dialog = await screen.findByRole('dialog', { name: 'Удалить текущую программу?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Удалить программу' }));

    await waitFor(() =>
      expect(
        within(activeSection!).getByRole('button', { name: 'Удалить программу' }),
      ).toBeDisabled(),
    );
    expect(
      vi
        .mocked(globalThis.fetch)
        .mock.calls.filter(([input]) => String(input) === '/api/v1/programs/assigned/42'),
    ).toHaveLength(1);
    resolveDelete(new Response(null, { status: 204 }));
  });

  it('keeps template deletion on the template endpoint', async () => {
    renderList();
    const card = (
      await screen.findByRole('button', { name: 'Посмотреть программу «Моя программа»' })
    ).closest('article');
    fireEvent.click(within(card!).getByText('Другие действия'));
    fireEvent.click(within(card!).getByRole('button', { name: 'Удалить программу' }));
    const dialog = await screen.findByRole('dialog', { name: 'Удалить программу?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Удалить' }));

    await waitFor(() =>
      expect(
        vi
          .mocked(globalThis.fetch)
          .mock.calls.some(
            ([input, init]) =>
              String(input) === '/api/v1/programs/templates/11' && init?.method === 'DELETE',
          ),
      ).toBe(true),
    );
  });

  it('makes own-program creation primary when no program is active', async () => {
    vi.mocked(globalThis.fetch).mockImplementation(async (input) => {
      const path = String(input);
      if (path === '/api/v1/programs/templates/mine') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (path === '/api/v1/programs/templates/hidden') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });

    renderList();

    expect(await screen.findByRole('heading', { name: 'План ещё не выбран' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Создать свою программу' })).toHaveAttribute(
      'href',
      '#program-builder',
    );
    expect(screen.getByRole('link', { name: 'Программы и шаблоны' })).toHaveAttribute(
      'href',
      '#program-library',
    );
    expect(screen.queryByRole('button', { name: 'Подобрать программу' })).not.toBeInTheDocument();
  });

  it('previews a deterministic recommendation before explicit start', async () => {
    renderList();

    fireEvent.click(await screen.findByRole('button', { name: 'Подобрать другую' }));
    expect(screen.queryByRole('button', { name: 'Начать подбор' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
    fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
    fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
    fireEvent.click(screen.getByRole('radio', { name: /Место не важно/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Далее' }));
    fireEvent.click(screen.getByRole('radio', { name: /Не проверять оборудование/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Показать рекомендацию' }));

    expect(await screen.findByText('Фуллбади по правилам')).toBeInTheDocument();
    expect(screen.getByText('Подходит по цели, уровню и частоте.')).toBeInTheDocument();
    expect(screen.getByText('Оборудование не проверялось.')).toBeInTheDocument();

    fireEvent.click(
      within(screen.getByRole('dialog', { name: 'Ваш результат' })).getByRole('button', {
        name: 'Посмотреть план',
      }),
    );
    expect(screen.getByRole('dialog', { name: /Фуллбади по правилам/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Настроить расписание и запустить' }));
    expect(screen.getByRole('dialog', { name: /Фуллбади по правилам/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Назначить по расписанию' }));
    expect(
      await screen.findByRole('dialog', { name: 'Заменить активную программу?' }),
    ).toBeInTheDocument();

    const requestedPaths = vi.mocked(globalThis.fetch).mock.calls.map(([input]) => String(input));
    expect(requestedPaths).toContain('/api/v1/programs/templates/recommendation');
    expect(requestedPaths.some((path) => path.includes('/assign-to-me'))).toBe(false);
  });
});
