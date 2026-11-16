import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { CoachInvites } from '../../../../src/features/profile/CoachInvites';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => ({ user: { trainer: { id: 1, full_name: 'Тренер' } }, reloadUser: vi.fn() }),
}));
vi.mock('../../../../src/shared/ui/FeedbackProvider', () => ({
  useFeedback: () => ({ toast: vi.fn(), confirm: vi.fn() }),
}));

afterEach(() => {
  cleanup();
  apiMock.mockReset();
});

it('отзывает доступ только после успешного ответа сервера', async () => {
  apiMock.mockImplementation((_path: string, options?: { method?: string }) =>
    Promise.resolve({ relationship_id: 1, nutrition_access: options?.method !== 'PUT' }),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <CoachInvites />
    </QueryClientProvider>,
  );
  const control = await screen.findByRole('checkbox', {
    name: 'Разрешить тренеру доступ к питанию',
  });
  await waitFor(() => expect(control).toBeChecked());
  fireEvent.click(control);
  await waitFor(() => expect(control).not.toBeChecked());
  expect(apiMock).toHaveBeenCalledWith('/api/v1/me/trainer/nutrition-access', {
    method: 'PUT',
    body: { nutrition_access: false, relationship_id: 1 },
  });
});
