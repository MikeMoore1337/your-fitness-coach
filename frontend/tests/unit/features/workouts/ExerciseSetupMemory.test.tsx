import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ExerciseSetupMemory } from '../../../../src/features/workouts/ExerciseSetupMemory';
import type { ExerciseSetupMemory as ExerciseSetupMemoryValue } from '../../../../src/shared/api/types';
import { readStorage, removeStorage } from '../../../../src/shared/storage';
import { exerciseSetupMemoryDraftStorageKey } from '../../../../src/shared/userScopedStorage';

const memory: ExerciseSetupMemoryValue = {
  id: 7,
  exercise_id: 11,
  body: 'Сиденье 4',
  version: 2,
  created_at: '2026-10-04T10:00:00',
  updated_at: '2026-10-04T10:05:00',
};

function renderMemory(value: ExerciseSetupMemoryValue | null = null, canEdit = true) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <ExerciseSetupMemory canEdit={canEdit} exerciseId={11} memory={value} userId={7} />
    </QueryClientProvider>,
  );
}

describe('ExerciseSetupMemory', () => {
  afterEach(() => {
    cleanup();
    removeStorage(exerciseSetupMemoryDraftStorageKey(7, 11));
    vi.restoreAllMocks();
  });

  it('creates and updates a private setup memory through the API', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          ...memory,
          body: 'Спинка 2',
          version: 3,
        }),
        { status: 200 },
      ),
    );
    const user = userEvent.setup();
    renderMemory(memory);

    await user.click(screen.getByRole('button', { name: 'Изменить настройку' }));
    const input = screen.getByRole('textbox', { name: 'Что важно настроить' });
    await user.clear(input);
    await user.type(input, 'Спинка 2');
    await user.click(screen.getByRole('button', { name: 'Сохранить настройку' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0]!;
    expect(String(path)).toContain('/api/v1/me/exercise-setup-memories/11');
    expect(JSON.parse(String((options as RequestInit).body))).toEqual({
      body: 'Спинка 2',
      expected_version: 2,
    });
    expect(await screen.findByText('Настройка сохранена.')).toBeInTheDocument();
    expect(screen.getByText('Спинка 2')).toBeInTheDocument();
  });

  it('keeps an offline draft local and does not claim server persistence', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    const user = userEvent.setup();
    renderMemory();

    await user.click(screen.getByRole('button', { name: 'Добавить настройку' }));
    await user.type(screen.getByRole('textbox', { name: 'Что важно настроить' }), 'Блок 7');
    await user.click(screen.getByRole('button', { name: 'Сохранить настройку' }));

    expect(
      await screen.findByText(
        'Черновик сохранён на устройстве. Сервер ещё не подтвердил сохранение.',
      ),
    ).toBeInTheDocument();
    expect(
      readStorage<{ body: string } | null>(exerciseSetupMemoryDraftStorageKey(7, 11), null),
    ).toMatchObject({ body: 'Блок 7' });
    expect(screen.getByRole('textbox', { name: 'Что важно настроить' })).toHaveValue('Блок 7');
  });

  it('shows private data but no mutation action in read-only runtime', () => {
    renderMemory(memory, false);

    expect(screen.getByText('Сиденье 4')).toBeInTheDocument();
    expect(screen.getByText('Изменение доступно после входа.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Изменить настройку' })).not.toBeInTheDocument();
  });
});
