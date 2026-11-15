import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NutritionMealNotes } from '../../../../src/features/nutrition/NutritionNotes';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', () => ({
  api: apiMock,
  AUTH_ACCOUNT_SWITCH_EVENT: 'fit:auth-account-switch',
  AUTH_LOGOUT_EVENT: 'fit:auth-logout',
  AUTH_VERIFIED_LOGIN_EVENT: 'fit:auth-verified-login',
}));

beforeEach(() => apiMock.mockReset());
afterEach(cleanup);

it('saves explicit no separately from omitted fields and clears it on a second click', async () => {
  apiMock.mockResolvedValueOnce([]).mockResolvedValueOnce({ meal_type: 'breakfast' });
  render(<NutritionMealNotes date="2026-01-01" meal="breakfast" />);
  const hunger = await screen.findByRole('group', { name: 'Голод до еды · необязательно' });
  const no = within(hunger).getByRole('button', { name: 'Нет' });
  expect(no).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(no);
  expect(no).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить отметки' }));
  await waitFor(() =>
    expect(apiMock).toHaveBeenLastCalledWith(
      '/api/v1/nutrition-notes/2026-01-01/breakfast',
      expect.objectContaining({
        method: 'PUT',
        body: { hunger_before: 'none', fullness_after: null, energy: null, note: null },
      }),
    ),
  );
  fireEvent.click(no);
  expect(no).toHaveAttribute('aria-pressed', 'false');
});

it('does not expose an empty editor after the initial read fails', async () => {
  apiMock.mockRejectedValueOnce(new Error('Нет соединения'));
  render(<NutritionMealNotes date="2026-01-01" meal="breakfast" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Нет соединения');
  expect(screen.queryByRole('button', { name: 'Сохранить отметки' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Повторить загрузку' })).toBeVisible();
});
