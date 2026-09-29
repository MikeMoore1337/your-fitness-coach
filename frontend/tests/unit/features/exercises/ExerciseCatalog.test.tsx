import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ExerciseCatalog } from '../../../../src/features/exercises/ExerciseCatalog';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const exercises = [
  {
    id: 1,
    title: 'Тяга верхнего блока с очень длинным названием для проверки переноса',
    metric_type: 'strength',
    slug: 'lat-pulldown',
    primary_muscle: 'Спина',
    equipment: 'Тросовый блок',
    primary_muscle_ids: ['back'],
    secondary_muscle_ids: ['biceps'],
    equipment_ids: ['cable'],
    aliases: ['верхняя тяга хаммер'],
    movement_pattern: 'vertical_pull',
    machine_variant_tags: [],
    execution_variant_tags: ['bilateral'],
    alternatives: [{ id: 2, slug: 'pull-up', title: 'Подтягивания' }],
    difficulty_level: 'beginner',
    is_custom: false,
    is_personalized: false,
    has_guide: true,
  },
  {
    id: 2,
    title: 'Подтягивания',
    metric_type: 'strength',
    slug: 'pull-up',
    primary_muscle: 'Спина',
    equipment: 'Собственный вес',
    primary_muscle_ids: ['back'],
    secondary_muscle_ids: ['biceps'],
    equipment_ids: ['bodyweight'],
    aliases: [],
    movement_pattern: 'vertical_pull',
    machine_variant_tags: [],
    execution_variant_tags: ['bilateral'],
    alternatives: [{ id: 1, slug: 'lat-pulldown', title: 'Тяга верхнего блока' }],
    difficulty_level: 'intermediate',
    is_custom: false,
    is_personalized: false,
    has_guide: true,
  },
];

function renderCatalog() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <ExerciseCatalog />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('ExerciseCatalog', () => {
  it('filters the visible list by structured equipment and supports an empty search state', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(exercises), { status: 200 }),
    );
    renderCatalog();

    expect(await screen.findByText('Подтягивания')).toBeInTheDocument();
    const compactRow = screen.getByRole('button', {
      name: /Техника и детали: Тяга верхнего блока с очень длинным названием/,
    });
    expect(compactRow).toBeVisible();
    fireEvent.click(compactRow);
    expect(screen.getByRole('dialog', { name: /Тяга верхнего блока/ })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть карточку упражнения' }));

    fireEvent.change(screen.getByLabelText('Оборудование'), { target: { value: 'cable' } });

    expect(screen.getByText(/Тяга верхнего блока с очень длинным названием/)).toBeInTheDocument();
    expect(screen.queryByText('Подтягивания')).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск' }), {
      target: { value: 'верхняя тяга хаммер' },
    });
    expect(screen.getByText(/Тяга верхнего блока с очень длинным названием/)).toBeInTheDocument();
    expect(screen.queryByText('Подтягивания')).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск' }), {
      target: { value: 'несуществующее движение' },
    });
    expect(screen.getByText('Ничего не найдено')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Сбросить фильтры' })).toBeInTheDocument();
  });

  it('shows a retryable error state when the catalog request fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Каталог временно недоступен' }), { status: 503 }),
    );
    renderCatalog();

    expect(await screen.findByText('Не удалось загрузить данные')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
  });

  it('sends a revision scope and reason when a coach changes one client program', async () => {
    let revisionBody: Record<string, unknown> | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/api/v1/programs/exercises')) {
        return new Response(JSON.stringify(exercises), { status: 200 });
      }
      if (url.endsWith('/api/v1/coach/assigned-programs')) {
        return new Response(
          JSON.stringify([
            {
              id: 44,
              client_id: 11,
              client_telegram_user_id: 123,
              client_full_name: 'Анна',
              template_id: 5,
              title: 'Силовая программа',
              assigned_at: '2026-09-01T10:00:00',
              is_active: true,
              status: 'active',
              start_date: '2026-09-30',
              duration_weeks: 4,
              schedule_weekdays: [1, 3],
              workouts_total: 8,
              workouts_completed: 0,
              workouts_planned: 8,
              current_revision_number: 7,
            },
          ]),
          { status: 200 },
        );
      }
      if (url.endsWith('/api/v1/coach/clients/11/programs/44/exercises')) {
        revisionBody = JSON.parse(String(init?.body));
        return new Response(JSON.stringify({ workouts_updated: 1, current_revision_number: 8 }), {
          status: 200,
        });
      }
      return new Response(JSON.stringify({ detail: `Unexpected request: ${url}` }), {
        status: 500,
      });
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <ExerciseCatalog canAssign targetTelegramId={123} />
        </FeedbackProvider>
      </QueryClientProvider>,
    );

    fireEvent.click((await screen.findAllByRole('button', { name: 'В программу' }))[1]!);
    expect(screen.getByText(/ID #11/)).toBeInTheDocument();
    expect(screen.getByText(/ID #44/)).toBeInTheDocument();
    expect(screen.getByText(/Telegram ID 123/)).toBeInTheDocument();
    expect(screen.getByText(/шаблон #5/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Причина изменения'), {
      target: { value: 'Сохранить индивидуальную нагрузку клиента' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить правку программы' }));

    await waitFor(() => expect(revisionBody).toBeDefined());
    expect(revisionBody).toMatchObject({
      expected_revision_number: 7,
      effective_scope: 'next_workout',
      effective_date: null,
      exercise_id: 1,
      day_number: null,
      reason: 'Сохранить индивидуальную нагрузку клиента',
    });
    expect(await screen.findByText(/Правка сохранена в версии v8/)).toBeInTheDocument();
  });
});
