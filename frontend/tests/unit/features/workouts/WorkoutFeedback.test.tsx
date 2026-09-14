import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  WORKOUT_COMMENT_MAX_LENGTH,
  WorkoutFeedback,
  WorkoutFeedbackDisclosure,
} from '../../../../src/features/workouts/WorkoutFeedback';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import { queryKeys } from '../../../../src/shared/queryKeys';

const authState = vi.hoisted(() => ({ value: { user: { trainer: { id: 7 } } } as unknown }));
vi.mock('../../../../src/app/AuthProvider', () => ({
  useOptionalAuth: () => authState.value,
}));

const comments = [
  {
    id: 2,
    trainer_author_id: 7,
    client_user_id: 11,
    workout_id: 501,
    workout_exercise_id: null,
    body: 'Темп стал ровнее.',
    body_format: 'plain_text' as const,
    created_at: '2026-08-20T12:00:00',
    updated_at: null,
    revisions: [],
  },
  {
    id: 1,
    trainer_author_id: 7,
    client_user_id: 11,
    workout_id: 501,
    workout_exercise_id: 91,
    body: '<script>alert("xss")</script>',
    body_format: 'plain_text' as const,
    created_at: '2026-08-20T10:00:00',
    updated_at: '2026-08-20T10:05:00',
    revisions: [
      {
        id: 10,
        revision_number: 1,
        body: 'Старый текст',
        edited_by_user_id: 7,
        created_at: '2026-08-20T10:05:00',
      },
    ],
  },
];

function renderFeedback(node: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>{node}</FeedbackProvider>
    </QueryClientProvider>,
  );
  return { ...result, queryClient };
}

const trainerProps = {
  workoutId: 501,
  workoutTitle: 'Ноги и корпус',
  workoutDate: '2026-08-20',
  exercises: [{ workoutExerciseId: 91, title: 'Присед со штангой' }],
  viewer: 'trainer' as const,
  clientId: 11,
  clientName: 'Анна Петрова',
  canCompose: true,
};

describe('WorkoutFeedback', () => {
  beforeEach(() => {
    authState.value = { user: { trainer: { id: 7 } } };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).endsWith('/comments')) {
        return new Response(JSON.stringify(comments), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('показывает plain text, хронологию, автора, exercise context и edited state', async () => {
    renderFeedback(<WorkoutFeedback {...trainerProps} />);

    expect(await screen.findByText('<script>alert("xss")</script>')).toBeVisible();
    expect(document.querySelector('.workout-feedback script')).toBeNull();
    const rows = screen.getAllByRole('listitem');
    expect(within(rows[0]!).getByText('Присед со штангой', { exact: false })).toBeVisible();
    expect(within(rows[0]!).getByText('Вы')).toBeVisible();
    expect(within(rows[0]!).getByText('Изменено')).toBeVisible();
    expect(within(rows[1]!).getByText('Темп стал ровнее.')).toBeVisible();
    expect(screen.getByLabelText('Контекст комментария')).toHaveValue('');
    expect(screen.getByLabelText('Комментарий')).toHaveAttribute(
      'maxlength',
      String(WORKOUT_COMMENT_MAX_LENGTH),
    );
  });

  it('сохраняет draft после ошибки и явно повторяет отправку', async () => {
    const user = userEvent.setup();
    let postCount = 0;
    const idempotencyKeys: string[] = [];
    const replayedComment = {
      ...comments[1],
      id: 3,
      body: 'Следите за коленями.',
      workout_exercise_id: 91,
      updated_at: null,
      revisions: [],
    };
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
      if (String(input).endsWith('/comments') && (!init?.method || init.method === 'GET')) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (String(input).endsWith('/comments') && init?.method === 'POST') {
        postCount += 1;
        idempotencyKeys.push(new Headers(init.headers).get('Idempotency-Key') ?? '');
        if (postCount === 1) {
          return new Response(JSON.stringify({ detail: 'Временная ошибка сети' }), { status: 500 });
        }
        return new Response(JSON.stringify(replayedComment), { status: 201 });
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
    const { queryClient } = renderFeedback(<WorkoutFeedback {...trainerProps} />);

    await screen.findByText('Комментариев пока нет');
    await user.selectOptions(screen.getByLabelText('Контекст комментария'), '91');
    await user.type(screen.getByLabelText('Комментарий'), 'Следите за коленями.');
    await user.click(screen.getByRole('button', { name: 'Отправить комментарий' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Временная ошибка сети');
    expect(screen.getByLabelText('Комментарий')).toHaveValue('Следите за коленями.');
    queryClient.setQueryData(queryKeys.workoutComments.trainer(11, 501), [replayedComment]);
    await user.click(screen.getByRole('button', { name: 'Повторить отправку' }));

    expect(await screen.findAllByText('Следите за коленями.')).toHaveLength(1);
    expect(screen.getByLabelText('Комментарий')).toHaveValue('');
    expect(postCount).toBe(2);
    expect(idempotencyKeys[0]).toMatch(/^\S{8,128}$/);
    expect(idempotencyKeys[1]).toBe(idempotencyKeys[0]);
  });

  it('редактирует существующий комментарий через поддерживаемый PATCH', async () => {
    const user = userEvent.setup();
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
      if (String(input).endsWith('/comments') && (!init?.method || init.method === 'GET')) {
        return new Response(JSON.stringify(comments), { status: 200 });
      }
      if (String(input).endsWith('/comments/1') && init?.method === 'PATCH') {
        return new Response(
          JSON.stringify({
            ...comments[1],
            body: 'Колени двигаются увереннее.',
            updated_at: '2026-08-20T12:30:00',
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
    renderFeedback(<WorkoutFeedback {...trainerProps} />);

    const originalComment = await screen.findByText('<script>alert("xss")</script>');
    await user.click(
      within(originalComment.closest('li')!).getByRole('button', { name: 'Изменить' }),
    );
    const editor = screen.getByLabelText('Изменить комментарий');
    await user.clear(editor);
    await user.type(editor, 'Колени двигаются увереннее.');
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    expect(await screen.findByText('Колени двигаются увереннее.')).toBeVisible();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/coach/clients/11/workouts/501/comments/1',
      expect.objectContaining({ method: 'PATCH' }),
    );
  });

  it('не показывает composer клиенту и открывает deep-link comment в том же контексте', async () => {
    renderFeedback(
      <WorkoutFeedbackDisclosure
        {...trainerProps}
        viewer="client"
        clientId={undefined}
        clientName={undefined}
        canCompose={false}
        focusedCommentId={1}
        focusedExerciseId={91}
      />,
    );

    expect(await screen.findByText('<script>alert("xss")</script>')).toBeVisible();
    expect(screen.queryByLabelText('Комментарий')).not.toBeInTheDocument();
    expect(within(document.getElementById('workout-comment-1')!).getByText('Тренер')).toBeVisible();
    expect(document.activeElement).toHaveAttribute('id', 'workout-comment-1');
  });

  it('скрывает trainer feedback без активной связи с тренером', () => {
    authState.value = { user: { trainer: null } };
    renderFeedback(
      <WorkoutFeedbackDisclosure
        {...trainerProps}
        viewer="client"
        clientId={undefined}
        clientName={undefined}
        canCompose={false}
      />,
    );

    expect(screen.queryByText('Обратная связь тренера')).not.toBeInTheDocument();
  });

  it('оставляет историю read-only при отозванной связи', async () => {
    renderFeedback(<WorkoutFeedback {...trainerProps} canCompose={false} />);

    expect(await screen.findByText('Новые комментарии недоступны')).toBeVisible();
    expect(await screen.findByText('Темп стал ровнее.')).toBeVisible();
    expect(screen.queryByLabelText('Комментарий')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Изменить' })).not.toBeInTheDocument();
  });
});
