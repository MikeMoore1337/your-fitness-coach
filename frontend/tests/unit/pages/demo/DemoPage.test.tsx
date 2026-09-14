import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TrainingScenario } from '../../../../src/pages/demo/DemoPage';
import type { DemoSelfTrainingState } from '../../../../src/features/demo/demoApi';
import { NavigationProvider } from '../../../../src/shared/navigation/router';

const mocks = vi.hoisted(() => ({
  clearAll: vi.fn(),
  track: vi.fn(),
}));

vi.mock('../../../../src/features/demo/demoApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../../src/features/demo/demoApi')>();
  return { ...actual, clearAllDemoSessions: mocks.clearAll };
});

vi.mock('../../../../src/shared/analytics/productEvents', () => ({
  productEventSurface: () => 'mobile_web',
  trackProductEvent: mocks.track,
}));

const progressState: DemoSelfTrainingState = {
  kind: 'self_training',
  screen: 'progress',
  workout_title: 'Верх тела · уверенный старт',
  workout_subtitle: 'Подготовленная тренировка на сегодня',
  completed_sets: 3,
  total_sets: 3,
  exercises: [],
  duration_minutes: 46,
  total_volume_kg: 6840,
  progress_change_percent: 6.5,
};

describe('TrainingScenario landing preview', () => {
  beforeEach(() => vi.clearAllMocks());

  it('uses the same meaningful own-data handoff copy as the full demo cabinet', async () => {
    const user = userEvent.setup();
    render(
      <NavigationProvider>
        <TrainingScenario busy={false} onAction={vi.fn()} state={progressState} />
      </NavigationProvider>,
    );

    expect(
      screen.getByRole('heading', { name: 'Готово. Вы посмотрели основной сценарий' }),
    ).toBeVisible();
    expect(
      screen.getByText('Теперь можно начать со своими тренировками, питанием и прогрессом.'),
    ).toBeVisible();
    await user.click(screen.getByRole('link', { name: 'Начать со своими данными' }));

    expect(mocks.clearAll).toHaveBeenCalledOnce();
    expect(mocks.track).toHaveBeenCalledWith(
      { name: 'demo_own_data_selected', surface: 'mobile_web', scenario: 'self_training' },
      { dedupe: 'session', dedupeKey: 'self_training' },
    );
  });
});
