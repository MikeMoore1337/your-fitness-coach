import type { DemoScenario, DemoSessionSnapshot, DemoTrainerState } from './demoApi';

export type DemoRouteStepKey =
  | 'plan'
  | 'workout'
  | 'result'
  | 'progress'
  | 'diary'
  | 'product'
  | 'total'
  | 'client'
  | 'comment'
  | 'ready';

export type DemoRouteStep = {
  key: DemoRouteStepKey;
  label: string;
  complete: boolean;
};

export type DemoRouteTarget =
  | { kind: 'navigate'; section: 'today' | 'plan' | 'nutrition' | 'progress' | 'trainer' }
  | { kind: 'action'; action: string }
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

function trainerComment(snapshot: DemoSessionSnapshot): string | null {
  const state = snapshot.state;
  if (state.kind !== 'trainer') return null;
  const client = state.clients.find((item) => item.id === state.selected_client_id);
  return client?.comment ?? null;
}

function currentSectionVisited(visitedSections: ReadonlySet<string>, section: string): boolean {
  return visitedSections.has(section);
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
  const progressComplete =
    state.screen === 'progress' && currentSectionVisited(visitedSections, 'progress');
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
    target =
      section === 'today'
        ? { kind: 'action', action: 'start_workout' }
        : { kind: 'navigate', section: 'today' };
    nextHint = 'Следующий шаг: откройте сегодняшнюю тренировку.';
  } else if (!resultComplete) {
    if (state.completed_sets < state.total_sets) {
      target = { kind: 'action', action: 'complete_set' };
      nextHint = 'Следующий шаг: завершите текущий подход.';
    } else {
      target = { kind: 'action', action: 'finish_workout' };
      nextHint = 'Следующий шаг: завершите тренировку.';
    }
  } else if (!progressComplete) {
    target =
      section === 'progress'
        ? { kind: 'action', action: 'open_progress' }
        : { kind: 'navigate', section: 'progress' };
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
  const resultComplete = state.screen === 'report';
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
    target =
      section === 'nutrition'
        ? { kind: 'action', action: 'add_recent' }
        : { kind: 'navigate', section: 'nutrition' };
    nextHint = 'Следующий шаг: добавьте недавний продукт.';
  } else if (!resultComplete) {
    target =
      section === 'nutrition'
        ? { kind: 'action', action: 'open_nutrition_report' }
        : { kind: 'navigate', section: 'nutrition' };
    nextHint = 'Следующий шаг: откройте обновлённый дневной итог.';
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
  section: string,
  visitedSections: ReadonlySet<string>,
): DemoRouteState {
  const state = snapshot.state;
  if (state.kind !== 'trainer') throw new Error('Trainer route requires a trainer snapshot');
  const clientComplete = currentSectionVisited(visitedSections, 'trainer');
  const resultComplete = Boolean(state.selected_client_id) && clientComplete;
  const commentComplete = Boolean(trainerComment(snapshot));
  const steps: readonly DemoRouteStep[] = [
    { key: 'client', label: 'Клиент', complete: clientComplete },
    { key: 'result', label: 'Результат', complete: resultComplete },
    { key: 'comment', label: 'Комментарий', complete: commentComplete },
    { key: 'ready', label: 'Готово', complete: commentComplete },
  ];
  let target: DemoRouteTarget = null;
  let nextHint = 'Маршрут завершён. Можно начать со своими данными.';
  if (!clientComplete || !resultComplete) {
    target = { kind: 'navigate', section: 'trainer' };
    nextHint = 'Следующий шаг: откройте подготовленного клиента.';
  } else if (!commentComplete) {
    target = { kind: 'focus', targetId: 'demoCabinetTrainerComment' };
    nextHint = 'Следующий шаг: оставьте короткий комментарий к результату.';
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
