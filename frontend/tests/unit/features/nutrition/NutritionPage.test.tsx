import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NutritionPage } from '../../../../src/features/nutrition/NutritionPage';

vi.mock('../../../../src/shared/telegram/useTelegramOverlayBackButton', () => ({
  useTelegramOverlayBackButton: () => undefined,
}));
vi.mock('../../../../src/features/nutrition/CoachNutritionProposals', () => ({
  ClientNutritionProposals: () => null,
}));
vi.mock('../../../../src/features/ai/AiCoachContextualEntry', () => ({
  AiCoachContextualEntry: () => null,
}));
vi.mock('../../../../src/features/nutrition/NutritionDiary', () => ({
  NutritionDiary: () => (
    <div data-testid="nutrition-diary-stub">
      <section id="hydration-history-section">
        <h3 tabIndex={-1}>История за день</h3>
      </section>
      <details id="hydration-goal-details">
        <summary>Личный ориентир воды</summary>
        <p>Текущий ориентир</p>
      </details>
      <details id="hydration-presets-details">
        <summary>Мои ёмкости</summary>
        <p>Сохранённые ёмкости</p>
      </details>
    </div>
  ),
}));
vi.mock('../../../../src/features/nutrition/MealPlanner', () => ({
  MealPlanner: () => (
    <details>
      <summary>План питания</summary>
    </details>
  ),
}));
vi.mock('../../../../src/features/nutrition/GroceryList', () => ({
  GroceryList: () => (
    <details>
      <summary>Список покупок</summary>
    </details>
  ),
}));
vi.mock('../../../../src/features/nutrition/NutritionTargets', () => ({
  NutritionTargets: ({ onClose }: { onClose: () => void }) => (
    <button type="button" onClick={onClose}>
      Закрыть настройки
    </button>
  ),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('NutritionPage - secondary actions (#1442)', () => {
  it('shows the secondary actions as separate controls in one group', () => {
    render(<NutritionPage />);
    const extras = screen.getByTestId('nutrition-extras');
    expect(screen.getByTestId('nutrition-diary-stub')).toBeVisible();
    expect(within(extras).getByRole('button', { name: /Настройки КБЖУ/ })).toBeVisible();
    expect(within(extras).getByText('План питания')).toBeVisible();
    expect(within(extras).getByText('Список покупок')).toBeVisible();
  });

  it('keeps hydration settings available in their original disclosures', () => {
    render(<NutritionPage />);
    const goal = document.getElementById('hydration-goal-details') as HTMLDetailsElement;
    fireEvent.click(within(goal).getByText('Личный ориентир воды'));
    expect(goal.open).toBe(true);
    fireEvent.click(screen.getByText('Мои ёмкости'));
    expect((document.getElementById('hydration-presets-details') as HTMLDetailsElement).open).toBe(
      true,
    );
  });

  it('returns focus to the same settings entry when closing target settings', async () => {
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      setTimeout(() => cb(0), 0);
      return 1;
    });
    render(<NutritionPage />);
    const extras = screen.getByTestId('nutrition-extras');
    const settingsButton = within(extras).getByRole('button', { name: /Настройки КБЖУ/ });
    fireEvent.click(settingsButton);
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть настройки' }));
    await waitFor(() => expect(settingsButton).toHaveFocus());
  });
});
