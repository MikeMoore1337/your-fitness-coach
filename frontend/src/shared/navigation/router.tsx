import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type AnchorHTMLAttributes,
} from 'react';
import { hideTelegramBackButtonWhenIdle, registerTelegramBackButton } from '../telegram/backButton';
import { getApiRuntime, useRuntime } from '../runtime/runtime';

interface NavigationContextValue {
  path: string;
  search: string;
  navigate(to: string, replace?: boolean, historyState?: unknown): void;
}

const NavigationContext = createContext<NavigationContextValue | null>(null);
export type CoachTab = 'today' | 'clients' | 'programs' | 'tools';

const COACH_TABS = new Set<CoachTab>(['today', 'clients', 'programs', 'tools']);
export const PERSONAL_WORKSPACE_RETURN_STATE = 'yfcPersonalWorkspaceReturn';
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

export function coachTabFromSearch(search: string): CoachTab {
  const params = new URLSearchParams(search);
  const requestedTab = params.get('tab');
  const clientId = params.get('client_id');
  if (params.getAll('tab').length > 1) return 'today';
  if (clientId !== null) {
    const parsedClientId = Number(clientId);
    const validClientId =
      /^\d+$/.test(clientId) && Number.isSafeInteger(parsedClientId) && parsedClientId > 0;
    if (!validClientId) return 'today';
    return !requestedTab || requestedTab === 'clients' ? 'clients' : 'today';
  }
  return requestedTab && COACH_TABS.has(requestedTab as CoachTab)
    ? (requestedTab as CoachTab)
    : 'today';
}

export function coachPathForTab(tab: CoachTab): string {
  return tab === 'today' ? '/coach' : `/coach?tab=${tab}`;
}

export function safeTrainerReturnPath(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value, window.location.origin);
    if (parsed.origin !== window.location.origin || parsed.pathname !== '/coach' || parsed.hash) {
      return null;
    }
    const keys = Array.from(parsed.searchParams.keys());
    if (keys.length > 1 || keys.some((key) => key !== 'tab')) return null;
    const requestedTab = parsed.searchParams.get('tab');
    if (!requestedTab) return '/coach';
    if (!COACH_TABS.has(requestedTab as CoachTab) || requestedTab === 'today') return null;
    return coachPathForTab(requestedTab as CoachTab);
  } catch {
    return null;
  }
}

function resolveNavigationPath(to: string): string {
  const runtime = getApiRuntime();
  return runtime.kind === 'demo' ? runtime.mapNavigationPath(to) : to;
}

export function demoReturnPathFromLogin(search: string): string | null {
  const params = new URLSearchParams(search);
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

function programHistoryReturn(value: string | null): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value, window.location.origin);
    const programId = parsed.searchParams.get('program_history');
    if (
      parsed.origin !== window.location.origin ||
      parsed.pathname !== '/app' ||
      parsed.searchParams.get('section') !== 'programs' ||
      !programId ||
      !/^\d+$/.test(programId) ||
      Number(programId) <= 0
    ) {
      return null;
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return null;
  }
}

function notificationCenterReturn(value: string | null): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value, window.location.origin);
    return parsed.origin === window.location.origin &&
      parsed.pathname === '/app' &&
      parsed.searchParams.get('section') === 'profile' &&
      parsed.hash === '#profile-notifications'
      ? `${parsed.pathname}${parsed.search}${parsed.hash}`
      : null;
  } catch {
    return null;
  }
}

function todayReturn(value: string | null): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value, window.location.origin);
    return parsed.origin === window.location.origin &&
      parsed.pathname === '/app' &&
      parsed.searchParams.get('section') === 'today'
      ? `${parsed.pathname}${parsed.search}${parsed.hash}`
      : null;
  } catch {
    return null;
  }
}

function progressReportReturn(search: string): string {
  const params = new URLSearchParams(search);
  const handoffId = params.get('handoff_id');
  if (handoffId && /^\d+$/.test(handoffId) && Number(handoffId) > 0) {
    return notificationCenterReturn(params.get('return_to')) ?? '/app?section=progress';
  }
  const clientId = params.get('client_id');
  if (clientId && /^\d+$/.test(clientId) && Number(clientId) > 0) {
    return `/coach?client_id=${clientId}`;
  }
  return '/app?section=progress';
}

function progressOverviewReturn(search: string): string {
  const current = new URLSearchParams(search);
  const params = new URLSearchParams({ section: 'progress' });
  for (const key of ['progress_period', 'progress_from', 'progress_to']) {
    const value = current.get(key);
    if (value) params.set(key, value);
  }
  return `/app?${params.toString()}`;
}

export function focusedContextReturn(search: string): string | null {
  const params = new URLSearchParams(search);
  const workoutId = params.get('workout_id');
  if (workoutId && /^\d+$/.test(workoutId) && Number(workoutId) > 0) {
    return (
      notificationCenterReturn(params.get('return_to')) ??
      programHistoryReturn(params.get('return_to')) ??
      todayReturn(params.get('return_to')) ??
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

export function NavigationProvider({ children }: { children: React.ReactNode }) {
  const [location, setLocation] = useState(() => ({
    path: window.location.pathname,
    search: window.location.search,
  }));

  useEffect(() => {
    const onPopState = () =>
      setLocation({ path: window.location.pathname, search: window.location.search });
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const navigate = useCallback((to: string, replace = false, historyState?: unknown) => {
    const destination = resolveNavigationPath(to);
    const nextHistoryState = historyState === undefined ? {} : historyState;
    if (replace) window.history.replaceState(nextHistoryState, '', destination);
    else window.history.pushState(nextHistoryState, '', destination);
    setLocation({ path: window.location.pathname, search: window.location.search });
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, []);

  useEffect(() => {
    const telegram = window.Telegram?.WebApp;
    const focusedReturn =
      location.path === '/app'
        ? focusedContextReturn(location.search)
        : location.path === '/app/report'
          ? progressReportReturn(location.search)
          : null;
    const publicReturn = location.path === '/demo' ? '/' : null;
    const demoHandoffReturn =
      location.path === '/login' ? demoReturnPathFromLogin(location.search) : null;
    if (
      (location.path === '/app' && !focusedReturn) ||
      location.path === '/onboarding' ||
      location.path === '/'
    ) {
      hideTelegramBackButtonWhenIdle(telegram);
      return;
    }
    const goBack = () => {
      const returnPath = focusedReturn ?? publicReturn ?? demoHandoffReturn;
      const historyState =
        location.path === '/coach' ? { [PERSONAL_WORKSPACE_RETURN_STATE]: true } : undefined;
      navigate(returnPath ?? '/app', Boolean(returnPath), historyState);
    };
    return registerTelegramBackButton(telegram, goBack, 'route');
  }, [navigate, location.path, location.search]);

  const value = useMemo(
    () => ({ path: location.path, search: location.search, navigate }),
    [location.path, location.search, navigate],
  );
  return <NavigationContext.Provider value={value}>{children}</NavigationContext.Provider>;
}

export function useNavigation(): NavigationContextValue {
  const value = useContext(NavigationContext);
  if (!value) throw new Error('useNavigation must be used inside NavigationProvider');
  return value;
}

export function AppLink({
  to,
  className,
  children,
  onClick,
  ...anchorAttributes
}: {
  to: string;
  children: React.ReactNode;
} & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>) {
  const { navigate } = useNavigation();
  const runtime = useRuntime();
  const href = runtime.kind === 'demo' ? runtime.mapNavigationPath(to) : to;
  return (
    <a
      href={href}
      className={className}
      {...anchorAttributes}
      onClick={(event) => {
        onClick?.(event);
        if (event.defaultPrevented) return;
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
          return;
        event.preventDefault();
        if (runtime.kind === 'demo') runtime.onNavigate?.(to);
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}

export function Redirect({ to }: { to: string }) {
  const { navigate } = useNavigation();
  useEffect(() => navigate(to, true), [navigate, to]);
  return null;
}
