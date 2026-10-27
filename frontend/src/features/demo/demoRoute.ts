import type { DemoScenario, DemoSessionSnapshot, DemoTrainerState } from './demoApi';

export type DemoRouteStepKey =
  | 'today'
  | 'attention'
  | 'plan'
  | 'workout'
  | 'result'
  | 'progress'
  | 'diary'
  | 'product'
  | 'total'
  | 'client'
  | 'operations'
  | 'task'
  | 'return'
  | 'comment'
  | 'ready';

export type DemoRouteStep = {
  key: DemoRouteStepKey;
  label: string;
  complete: boolean;
};

export type TrainerDemoStepKey =
  'today' | 'attention' | 'client' | 'workout' | 'progress' | 'operations' | 'task' | 'return';

export type DemoRouteTarget =
  | {
      kind: 'navigate';
      section: 'today' | 'plan' | 'nutrition' | 'progress' | 'trainer';
      demoStep?: TrainerDemoStepKey;
    }
  | { kind: 'focus'; targetId: string }
  | null;

export type DemoRouteState = {
  steps: readonly DemoRouteStep[];
  currentStep: number;
  complete: boolean;
  nextHint: string;
  target: DemoRouteTarget;
};

const ROUTE_VISIBILITY_STORAGE_KEY = 'fit_demo_route_ui_v1';

function readRouteVisibility(): Partial<Record<DemoScenario, boolean>> {
  try {
    const value = JSON.parse(
      window.sessionStorage.getItem(ROUTE_VISIBILITY_STORAGE_KEY) ?? '{}',
    ) as unknown;
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return Object.fromEntries(
      Object.entries(value).filter(
        ([scenario, visible]) =>
          ['self_training', 'nutrition', 'trainer'].includes(scenario) &&
          typeof visible === 'boolean',
      ),
    ) as Partial<Record<DemoScenario, boolean>>;
  } catch {
    return {};
  }
}

export function isDemoRouteVisible(scenario: DemoScenario): boolean {
  return readRouteVisibility()[scenario] !== false;
}

export function setDemoRouteVisible(scenario: DemoScenario, visible: boolean): void {
  const next = { ...readRouteVisibility(), [scenario]: visible };
  try {
    window.sessionStorage.setItem(ROUTE_VISIBILITY_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // A restrictive WebView may not expose storage; the route remains available in the page.
  }
}

function currentSectionVisited(visitedSections: ReadonlySet<string>, section: string): boolean {
  return visitedSections.has(section);
}

function trainerStepVisited(
  visitedSections: ReadonlySet<string>,
  step: TrainerDemoStepKey,
): boolean {
  return visitedSections.has(`trainer:${step}`);
}

function firstIncompleteIndex(steps: readonly DemoRouteStep[]): number {
  const index = steps.findIndex((step) => !step.complete);
  return index === -1 ? steps.length - 1 : index;
}

function trainingRoute(
  snapshot: DemoSessionSnapshot,
  section: string,
  visitedSections: ReadonlySet<string>,
): DemoRouteState {
  const state = snapshot.state;
  if (state.kind !== 'self_training')
    throw new Error('Training route requires a training snapshot');
  const planComplete = currentSectionVisited(visitedSections, 'plan');
  const workoutComplete = state.screen !== 'today';
  const resultComplete = state.screen === 'summary' || state.screen === 'progress';
  const progressComplete = resultComplete && currentSectionVisited(visitedSections, 'progress');
  const steps: readonly DemoRouteStep[] = [
    { key: 'plan', label: 'План', complete: planComplete },
    { key: 'workout', label: 'Тренировка', complete: workoutComplete },
    { key: 'result', label: 'Результат', complete: resultComplete },
    { key: 'progress', label: 'Прогресс', complete: progressComplete },
  ];
  let target: DemoRouteTarget = null;
  let nextHint = 'Маршрут завершён. Можно начать со своими данными.';
  if (!planComplete) {
    target = { kind: 'navigate', section: 'plan' };
    nextHint = 'Следующий шаг: откройте активный план.';
  } else if (!workoutComplete) {
    target = { kind: 'navigate', section: 'today' };
    nextHint = 'Следующий шаг: откройте сегодняшнюю тренировку.';
  } else if (!resultComplete) {
    target = { kind: 'navigate', section: 'today' };
    nextHint =
      state.completed_sets < state.total_sets
        ? 'Следующий шаг: завершите текущий подход на экране тренировки.'
        : 'Следующий шаг: завершите тренировку на экране тренировки.';
  } else if (!progressComplete) {
    target = { kind: 'navigate', section: 'progress' };
    nextHint = 'Следующий шаг: откройте обновлённый прогресс.';
  }
  return {
    steps,
    currentStep: firstIncompleteIndex(steps) + 1,
    complete: steps.every((step) => step.complete),
    nextHint,
    target,
  };
}

function nutritionRoute(
  snapshot: DemoSessionSnapshot,
  section: string,
  visitedSections: ReadonlySet<string>,
): DemoRouteState {
  const state = snapshot.state;
  if (state.kind !== 'nutrition') throw new Error('Nutrition route requires a nutrition snapshot');
  const diaryComplete = currentSectionVisited(visitedSections, 'nutrition');
  const productComplete = state.item_added;
  // The shared production nutrition surface has no client-side report transition.
  // Adding the curated item updates the diary totals; the next route step is
  // therefore the real Progress navigation, not a legacy demo-only action.
  const resultComplete = productComplete;
  const progressComplete = resultComplete && currentSectionVisited(visitedSections, 'progress');
  const steps: readonly DemoRouteStep[] = [
    { key: 'diary', label: 'Дневник', complete: diaryComplete },
    { key: 'product', label: 'Продукт', complete: productComplete },
    { key: 'total', label: 'Итог', complete: resultComplete },
    { key: 'progress', label: 'Прогресс', complete: progressComplete },
  ];
  let target: DemoRouteTarget = null;
  let nextHint = 'Маршрут завершён. Можно начать со своими данными.';
  if (!diaryComplete) {
    target = { kind: 'navigate', section: 'nutrition' };
    nextHint = 'Следующий шаг: откройте подготовленный дневник.';
  } else if (!productComplete) {
    target = { kind: 'navigate', section: 'nutrition' };
    nextHint = 'Следующий шаг: добавьте недавний продукт на экране дневника.';
  } else if (!resultComplete) {
    target = { kind: 'navigate', section: 'nutrition' };
    nextHint = 'Следующий шаг: откройте обновлённый дневной итог в дневнике.';
  } else if (!progressComplete) {
    target = { kind: 'navigate', section: 'progress' };
    nextHint = 'Следующий шаг: посмотрите, как запись влияет на показатели.';
  }
  return {
    steps,
    currentStep: firstIncompleteIndex(steps) + 1,
    complete: steps.every((step) => step.complete),
    nextHint,
    target,
  };
}

function trainerRoute(
  snapshot: DemoSessionSnapshot,
  _section: string,
  visitedSections: ReadonlySet<string>,
): DemoRouteState {
  const state = snapshot.state;
  if (state.kind !== 'trainer') throw new Error('Trainer route requires a trainer snapshot');
  const todayComplete = currentSectionVisited(visitedSections, 'trainer');
  const attentionComplete = trainerStepVisited(visitedSections, 'attention');
  const clientComplete =
    Boolean(state.selected_client_id) && trainerStepVisited(visitedSections, 'client');
  const workoutComplete = trainerStepVisited(visitedSections, 'workout');
  const progressComplete = trainerStepVisited(visitedSections, 'progress');
  const operationsComplete = trainerStepVisited(visitedSections, 'operations');
  const taskComplete = trainerStepVisited(visitedSections, 'task');
  const returnComplete = trainerStepVisited(visitedSections, 'return');
  const steps: readonly DemoRouteStep[] = [
    { key: 'today', label: 'Сегодня', complete: todayComplete },
    { key: 'attention', label: 'Внимание', complete: attentionComplete },
    { key: 'client', label: 'Клиент', complete: clientComplete },
    { key: 'workout', label: 'Тренировка', complete: workoutComplete },
    { key: 'progress', label: 'Прогресс', complete: progressComplete },
    { key: 'operations', label: 'Операции', complete: operationsComplete },
    { key: 'task', label: 'Задача', complete: taskComplete },
    { key: 'return', label: 'Назад в Сегодня', complete: returnComplete },
  ];
  let target: DemoRouteTarget = null;
  let nextHint = 'Маршрут завершён. Можно начать со своими данными.';
  if (!todayComplete) {
    target = { kind: 'navigate', section: 'trainer', demoStep: 'today' };
    nextHint = 'Следующий шаг: откройте Coach Today.';
  } else if (!attentionComplete) {
    target = { kind: 'focus', targetId: 'coach-attention-title' };
    nextHint = 'Следующий шаг: выберите действие из списка внимания.';
  } else if (!clientComplete) {
    target = { kind: 'focus', targetId: 'coach-client-detail-title' };
    nextHint = 'Следующий шаг: откройте карточку клиента.';
  } else if (!workoutComplete) {
    target = { kind: 'focus', targetId: 'coach-client-timeline' };
    nextHint = 'Следующий шаг: откройте последние события и тренировку клиента.';
  } else if (!progressComplete) {
    target = { kind: 'focus', targetId: 'coach-client-progress' };
    nextHint = 'Следующий шаг: откройте прогресс и замеры клиента.';
  } else if (!operationsComplete) {
    target = { kind: 'navigate', section: 'trainer', demoStep: 'operations' };
    nextHint = 'Следующий шаг: вернитесь в Сегодня и соберите рабочий день.';
  } else if (!taskComplete) {
    target = { kind: 'focus', targetId: 'coach-tasks-title' };
    nextHint = 'Следующий шаг: посмотрите задачу клиента.';
  } else if (!returnComplete) {
    target = { kind: 'navigate', section: 'trainer', demoStep: 'return' };
    nextHint = 'Следующий шаг: вернитесь в Coach Today.';
  }
  return {
    steps,
    currentStep: firstIncompleteIndex(steps) + 1,
    complete: steps.every((step) => step.complete),
    nextHint,
    target,
  };
}

export function getDemoRouteState(
  scenario: DemoScenario,
  snapshot: DemoSessionSnapshot,
  section: string,
  visitedSections: ReadonlySet<string>,
): DemoRouteState {
  if (scenario === 'self_training') return trainingRoute(snapshot, section, visitedSections);
  if (scenario === 'nutrition') return nutritionRoute(snapshot, section, visitedSections);
  return trainerRoute(snapshot, section, visitedSections);
}

export function selectedTrainerClient(
  state: DemoTrainerState,
): DemoTrainerState['clients'][number] {
  return (
    state.clients.find((client) => client.id === state.selected_client_id) ?? state.clients[0]!
  );
}
