import { hasNoDuplicateParams, positiveIntegerParam } from './routeParams';

export type CoachTab = 'today' | 'clients' | 'programs' | 'tools';

const COACH_TABS = new Set<CoachTab>(['today', 'clients', 'programs', 'tools']);
const DEMO_SCENARIOS = new Set(['self_training', 'nutrition', 'trainer']);
const DEMO_CABINET_SECTIONS = new Set([
  'today',
  'plan',
  'nutrition',
  'progress',
  'profile',
  'trainer',
]);
const PROGRESS_DETAIL_VIEWS = new Set([
  'body',
  'training',
  'nutrition',
  'cardio',
  'wellbeing',
  'history',
]);

function sameOriginUrl(value: string | null | undefined, origin: string): URL | null {
  if (!value) return null;
  try {
    const parsed = new URL(value, origin);
    return parsed.origin === origin ? parsed : null;
  } catch {
    return null;
  }
}

function internalPath(parsed: URL): string {
  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}

export function coachTabFromSearch(search: string): CoachTab {
  const params = new URLSearchParams(search);
  if (!hasNoDuplicateParams(params, ['tab', 'client_id'])) return 'today';
  const requestedTab = params.get('tab');
  const clientId = positiveIntegerParam(params, 'client_id');
  if (params.has('client_id')) {
    if (clientId === null) return 'today';
    return !requestedTab || requestedTab === 'clients' ? 'clients' : 'today';
  }
  return requestedTab && COACH_TABS.has(requestedTab as CoachTab)
    ? (requestedTab as CoachTab)
    : 'today';
}

export function coachPathForTab(tab: CoachTab): string {
  return tab === 'today' ? '/coach' : `/coach?tab=${tab}`;
}

export function safeTrainerReturnPath(
  value: string | null | undefined,
  origin: string,
): string | null {
  const parsed = sameOriginUrl(value, origin);
  if (
    !parsed ||
    parsed.pathname !== '/coach' ||
    parsed.hash ||
    !hasNoDuplicateParams(parsed.searchParams)
  ) {
    return null;
  }
  const keys = Array.from(parsed.searchParams.keys());
  if (keys.length > 1 || keys.some((key) => key !== 'tab')) return null;
  const requestedTab = parsed.searchParams.get('tab');
  if (!requestedTab) return '/coach';
  if (!COACH_TABS.has(requestedTab as CoachTab) || requestedTab === 'today') return null;
  return coachPathForTab(requestedTab as CoachTab);
}

export function demoReturnPathFromLogin(search: string): string | null {
  const params = new URLSearchParams(search);
  if (!hasNoDuplicateParams(params, ['from', 'scenario', 'cabinet', 'section'])) return null;
  const scenario = params.get('scenario');
  if (params.get('from') !== 'demo' || !scenario || !DEMO_SCENARIOS.has(scenario)) return null;
  const cabinet = params.get('cabinet') === '1';
  const section = params.get('section');
  if (cabinet) {
    const safeSection =
      section &&
      DEMO_CABINET_SECTIONS.has(section) &&
      (section !== 'trainer' || scenario === 'trainer')
        ? section
        : scenario === 'trainer'
          ? 'trainer'
          : 'today';
    return `/demo?cabinet=1&scenario=${scenario}&section=${safeSection}`;
  }
  return `/demo?scenario=${scenario}`;
}

function programHistoryReturn(value: string | null, origin: string): string | null {
  const parsed = sameOriginUrl(value, origin);
  const programId = parsed && positiveIntegerParam(parsed.searchParams, 'program_history');
  if (
    !parsed ||
    !hasNoDuplicateParams(parsed.searchParams) ||
    parsed.pathname !== '/app' ||
    parsed.searchParams.get('section') !== 'programs' ||
    programId === null
  ) {
    return null;
  }
  return internalPath(parsed);
}

function notificationCenterReturn(value: string | null, origin: string): string | null {
  const parsed = sameOriginUrl(value, origin);
  return parsed &&
    hasNoDuplicateParams(parsed.searchParams) &&
    parsed.pathname === '/app' &&
    parsed.searchParams.get('section') === 'profile' &&
    parsed.hash === '#profile-notifications'
    ? internalPath(parsed)
    : null;
}

function todayReturn(value: string | null, origin: string): string | null {
  const parsed = sameOriginUrl(value, origin);
  return parsed &&
    hasNoDuplicateParams(parsed.searchParams) &&
    parsed.pathname === '/app' &&
    parsed.searchParams.get('section') === 'today'
    ? internalPath(parsed)
    : null;
}

export function progressReportReturn(search: string, origin: string): string {
  const params = new URLSearchParams(search);
  if (
    !hasNoDuplicateParams(params, [
      'handoff_id',
      'return_to',
      'client_id',
      'progress_view',
      'period',
      'date_from',
      'date_to',
    ])
  ) {
    return '/app?section=progress';
  }
  const handoffId = positiveIntegerParam(params, 'handoff_id');
  if (handoffId !== null) {
    return notificationCenterReturn(params.get('return_to'), origin) ?? '/app?section=progress';
  }
  const clientId = positiveIntegerParam(params, 'client_id');
  if (clientId !== null) return `/coach?client_id=${clientId}`;
  const view = params.get('progress_view');
  const target = new URLSearchParams({ section: 'progress' });
  if (view && PROGRESS_DETAIL_VIEWS.has(view)) target.set('progress_view', view);
  const period = params.get('period');
  if (period && ['days_7', 'days_30', 'days_90'].includes(period))
    target.set('progress_period', period.slice(5));
  if (period === 'custom') {
    const from = params.get('date_from');
    const to = params.get('date_to');
    if (from && to && /^\d{4}-\d{2}-\d{2}$/.test(from) && /^\d{4}-\d{2}-\d{2}$/.test(to)) {
      target.set('progress_period', 'custom');
      target.set('progress_from', from);
      target.set('progress_to', to);
    }
  }
  return `/app?${target}`;
}

function progressOverviewReturn(search: string): string {
  const current = new URLSearchParams(search);
  if (!hasNoDuplicateParams(current, ['progress_period', 'progress_from', 'progress_to'])) {
    return '/app?section=progress';
  }
  const params = new URLSearchParams({ section: 'progress' });
  for (const key of ['progress_period', 'progress_from', 'progress_to']) {
    const value = current.get(key);
    if (value) params.set(key, value);
  }
  return `/app?${params}`;
}

export function focusedContextReturn(search: string, origin: string): string | null {
  const params = new URLSearchParams(search);
  if (
    !hasNoDuplicateParams(params, [
      'workout_id',
      'comment_id',
      'workout_exercise_id',
      'section',
      'return_to',
      'progress_view',
      'progress_period',
      'progress_from',
      'progress_to',
      'weekly_review',
    ])
  ) {
    return null;
  }
  const workoutId = positiveIntegerParam(params, 'workout_id');
  if (workoutId !== null) {
    return (
      notificationCenterReturn(params.get('return_to'), origin) ??
      programHistoryReturn(params.get('return_to'), origin) ??
      todayReturn(params.get('return_to'), origin) ??
      (params.get('section') === 'programs' ? '/app?section=programs' : '/app?section=progress')
    );
  }
  if (
    params.get('section') === 'progress' &&
    PROGRESS_DETAIL_VIEWS.has(params.get('progress_view') ?? '')
  ) {
    return progressOverviewReturn(search);
  }
  if (params.get('weekly_review') === '1') return '/app';
  return null;
}
