export type DemoScenario = 'self_training' | 'nutrition' | 'trainer';

export interface DemoExercise {
  name: string;
  prescription: string;
  status: 'completed' | 'current' | 'next';
}

export interface DemoSelfTrainingState {
  kind: 'self_training';
  screen: 'today' | 'active_workout' | 'summary' | 'progress';
  workout_title: string;
  workout_subtitle: string;
  completed_sets: number;
  total_sets: number;
  exercises: DemoExercise[];
  duration_minutes: number;
  total_volume_kg: number;
  progress_change_percent: number;
}

export interface DemoNutritionState {
  kind: 'nutrition';
  screen: 'diary' | 'report';
  date_label: string;
  item_added: boolean;
  recent_item: {
    name: string;
    serving: string;
    calories: number;
    protein_g: number;
  };
  calories: number;
  calorie_target: number;
  protein_g: number;
  protein_target_g: number;
  meals_logged: number;
}

export interface DemoTrainerState {
  kind: 'trainer';
  screen: 'client';
  selected_client_id: 'alexey' | 'maria' | 'ivan';
  clients: Array<{
    id: 'alexey' | 'maria' | 'ivan';
    name: 'Алексей' | 'Мария' | 'Иван';
    status_label: string;
    context_label: string;
    workout_title: string;
    facts: Array<{ label: string; value: string }>;
    comment: string | null;
  }>;
}

export interface DemoCabinetState {
  program: {
    name: string;
    current_week: number;
    total_weeks: number;
    sessions_per_week: number;
    schedule: Array<{
      day_label: string;
      workout_title: string;
      status: 'completed' | 'planned' | 'rest';
    }>;
  };
  today: {
    title: string;
    summary: string;
    status_label: string;
    completed_days: number;
    planned_days: number;
  };
  nutrition: {
    calories: number;
    calorie_target: number;
    protein_g: number;
    protein_target_g: number;
    meals_logged: number;
    item_added: boolean;
    recent_item: DemoNutritionState['recent_item'];
  };
  progress: {
    workouts_completed: number;
    latest_volume_kg: number;
    volume_change_percent: number;
    nutrition_days_logged: number;
    nutrition_completion_percent: number;
    summary: string;
    adherence_percent: number;
    training_history: Array<{
      period_label: string;
      workout_title: string;
      completed_sets: number;
      volume_kg: number;
    }>;
    volume_history: Array<{ period_label: string; volume_kg: number }>;
    nutrition_history: Array<{
      date_label: string;
      status: 'complete' | 'incomplete' | 'not_logged';
      calories: number | null;
      protein_g: number | null;
    }>;
    measurements: Array<{ label: string; value: string; date_label: string }>;
  };
  trainer: DemoTrainerState | null;
  meaningful_action_completed: boolean;
  conversion_title: string;
}

export type DemoScenarioState = DemoSelfTrainingState | DemoNutritionState | DemoTrainerState;

export interface DemoSessionSnapshot {
  capability: 'demo';
  scenario: DemoScenario;
  fixture_version: 'demo-curated-v2';
  revision: number;
  expires_at: string;
  state: DemoScenarioState;
  cabinet: DemoCabinetState;
}

type DemoSessionCreated = DemoSessionSnapshot & { session_token: string };
type DemoSessionTokens = Partial<Record<DemoScenario, string>>;

const SESSION_STORAGE_KEY = 'fit_demo_sessions_v1';
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{32,128}$/;
let memoryTokens: DemoSessionTokens = {};

export class DemoApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'DemoApiError';
  }
}

function readTokens(): DemoSessionTokens {
  try {
    const value = JSON.parse(window.sessionStorage.getItem(SESSION_STORAGE_KEY) || '{}') as unknown;
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    const storedTokens = Object.fromEntries(
      Object.entries(value).filter(
        ([scenario, token]) =>
          ['self_training', 'nutrition', 'trainer'].includes(scenario) &&
          typeof token === 'string' &&
          TOKEN_PATTERN.test(token),
      ),
    ) as DemoSessionTokens;
    return { ...memoryTokens, ...storedTokens };
  } catch {
    return { ...memoryTokens };
  }
}

function writeToken(scenario: DemoScenario, token: string | null): void {
  const tokens = readTokens();
  if (token) tokens[scenario] = token;
  else delete tokens[scenario];
  memoryTokens = tokens;
  try {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(tokens));
  } catch {
    // Restrictive WebViews still get an isolated in-memory server session for the current page.
  }
}

async function demoRequest<T>(
  path: string,
  { body, signal, token }: { body?: unknown; signal?: AbortSignal; token?: string } = {},
): Promise<T> {
  try {
    const response = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
      signal,
      headers: {
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { 'X-Demo-Session': token } : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    if (!response.ok) {
      throw new DemoApiError(
        payload?.detail || 'Не удалось обновить демо. Попробуйте снова.',
        response.status,
      );
    }
    return payload as T;
  } catch (error) {
    if (error instanceof DemoApiError || error instanceof DOMException) throw error;
    throw new DemoApiError('Нет соединения с сервером. Проверьте интернет и повторите.', 0);
  }
}

export async function startDemoSession(
  scenario: DemoScenario,
  signal?: AbortSignal,
): Promise<DemoSessionSnapshot> {
  const created = await demoRequest<DemoSessionCreated>('/api/v1/demo/sessions', {
    body: { scenario },
    signal,
  });
  writeToken(scenario, created.session_token);
  return {
    capability: created.capability,
    scenario: created.scenario,
    fixture_version: created.fixture_version,
    revision: created.revision,
    expires_at: created.expires_at,
    state: created.state,
    cabinet: created.cabinet,
  };
}

export async function loadDemoSession(
  scenario: DemoScenario,
  signal?: AbortSignal,
): Promise<DemoSessionSnapshot> {
  const token = readTokens()[scenario];
  if (!token) return startDemoSession(scenario, signal);
  try {
    return await demoRequest<DemoSessionSnapshot>('/api/v1/demo/sessions/current', {
      signal,
      token,
    });
  } catch (error) {
    if (error instanceof DemoApiError && error.status === 410) writeToken(scenario, null);
    throw error;
  }
}

function requireToken(scenario: DemoScenario): string {
  const token = readTokens()[scenario];
  if (!token) throw new DemoApiError('Демо-сессия истекла. Начните новый сценарий.', 410);
  return token;
}

export function getDemoSessionToken(scenario: DemoScenario): string | null {
  return readTokens()[scenario] ?? null;
}

export function applyDemoAction(
  scenario: DemoScenario,
  action: string,
  comment?: string,
  clientId?: DemoTrainerState['selected_client_id'],
): Promise<DemoSessionSnapshot> {
  return demoRequest('/api/v1/demo/sessions/current/actions', {
    body: {
      action,
      ...(comment === undefined ? {} : { comment }),
      ...(clientId === undefined ? {} : { client_id: clientId }),
    },
    token: requireToken(scenario),
  });
}

export function resetDemoSession(scenario: DemoScenario): Promise<DemoSessionSnapshot> {
  return demoRequest('/api/v1/demo/sessions/current/reset', {
    body: {},
    token: requireToken(scenario),
  });
}

export function clearDemoSession(scenario: DemoScenario): void {
  writeToken(scenario, null);
}

export function clearAllDemoSessions(): void {
  memoryTokens = {};
  try {
    window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // The in-memory credentials are still discarded in restrictive WebViews.
  }
}
