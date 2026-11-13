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
  it('hides secondary settings, planning and shopping under one explicit disclosure', () => {
    render(<NutritionPage />);
    const extras = screen.getByTestId('nutrition-extras') as HTMLDetailsElement;
    expect(extras.open).toBe(false);
    expect(screen.getByTestId('nutrition-diary-stub')).toBeVisible();
    expect(within(extras).getByText('План питания')).not.toBeVisible();
    fireEvent.click(within(extras).getByText('Дополнительно'));
    expect(extras.open).toBe(true);
    expect(within(extras).getByText('План питания')).toBeVisible();
    expect(within(extras).getByText('Список покупок')).toBeVisible();
  });

  it('opens an existing hydration setting instead of duplicating its form', () => {
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });
    Element.prototype.scrollIntoView = vi.fn();
    render(<NutritionPage />);
    const extras = screen.getByTestId('nutrition-extras');
    fireEvent.click(within(extras).getByText('Дополнительно'));
    fireEvent.click(within(extras).getByRole('button', { name: 'Личный ориентир' }));
    const goal = document.getElementById('hydration-goal-details') as HTMLDetailsElement;
    expect(goal.open).toBe(true);
    expect(within(goal).getByText('Личный ориентир воды')).toHaveFocus();
    fireEvent.click(within(extras).getByRole('button', { name: 'Мои кружки и бутылки' }));
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
    fireEvent.click(within(extras).getByText('Дополнительно'));
    const settingsButton = within(extras).getByRole('button', { name: 'Настройки КБЖУ' });
    fireEvent.click(settingsButton);
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть настройки' }));
    await waitFor(() => expect(settingsButton).toHaveFocus());
  });
});

it('temporary #1442 formatting diagnostic - remove before merge', async () => {
  const prettier = await import('prettier');
  const fs = await import('node:fs/promises');
  for (const filePath of [
    'src/features/nutrition/NutritionPage.tsx',
    'src/features/nutrition/HydrationTracker.tsx',
  ]) {
    const current = await fs.readFile(filePath, 'utf8');
    const formatted = await prettier.format(current, {
      ...(await prettier.resolveConfig(filePath)),
      filepath: filePath,
      endOfLine: 'auto',
    });
    if (current === formatted) continue;
    const a = current.split('\n');
    const b = formatted.split('\n');
    let startIndex = 0;
    while (startIndex < a.length && a[startIndex] === b[startIndex]) startIndex++;
    let aEnd = a.length - 1;
    let bEnd = b.length - 1;
    while (aEnd >= startIndex && bEnd >= startIndex && a[aEnd] === b[bEnd]) {
      aEnd--;
      bEnd--;
    }
    console.log('PRETTIER_DIAGNOSTIC', filePath);
    console.log('BEFORE:', a.slice(Math.max(0, startIndex - 3), aEnd + 4).join('\n').slice(0, 7000));
    console.log('AFTER:', b.slice(Math.max(0, startIndex - 3), bEnd + 4).join('\n').slice(0, 7000));
  }
});
