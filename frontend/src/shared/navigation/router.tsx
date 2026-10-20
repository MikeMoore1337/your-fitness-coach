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
import * as routeContracts from './routeContracts';

interface NavigationContextValue {
  path: string;
  search: string;
  hash: string;
  navigate(to: string, replace?: boolean, historyState?: unknown): void;
}

const NavigationContext = createContext<NavigationContextValue | null>(null);
export type { CoachTab } from './routeContracts';
export const PERSONAL_WORKSPACE_RETURN_STATE = 'yfcPersonalWorkspaceReturn';

export const coachTabFromSearch = routeContracts.coachTabFromSearch;
export const coachPathForTab = routeContracts.coachPathForTab;
export const demoReturnPathFromLogin = routeContracts.demoReturnPathFromLogin;

export function safeTrainerReturnPath(value: string | null | undefined): string | null {
  return routeContracts.safeTrainerReturnPath(value, window.location.origin);
}

function resolveNavigationPath(to: string): string {
  const runtime = getApiRuntime();
  return runtime.kind === 'demo' ? runtime.mapNavigationPath(to) : to;
}

export function progressReportReturn(search: string): string {
  return routeContracts.progressReportReturn(search, window.location.origin);
}

export function focusedContextReturn(search: string): string | null {
  return routeContracts.focusedContextReturn(search, window.location.origin);
}

export function NavigationProvider({ children }: { children: React.ReactNode }) {
  const [location, setLocation] = useState(() => ({
    path: window.location.pathname,
    search: window.location.search,
    hash: window.location.hash,
  }));

  useEffect(() => {
    const onLocationChange = () =>
      setLocation({
        path: window.location.pathname,
        search: window.location.search,
        hash: window.location.hash,
      });
    window.addEventListener('popstate', onLocationChange);
    window.addEventListener('hashchange', onLocationChange);
    return () => {
      window.removeEventListener('popstate', onLocationChange);
      window.removeEventListener('hashchange', onLocationChange);
    };
  }, []);

  const navigate = useCallback((to: string, replace = false, historyState?: unknown) => {
    const destination = resolveNavigationPath(to);
    const nextHistoryState = historyState === undefined ? {} : historyState;
    if (replace) window.history.replaceState(nextHistoryState, '', destination);
    else window.history.pushState(nextHistoryState, '', destination);
    setLocation({
      path: window.location.pathname,
      search: window.location.search,
      hash: window.location.hash,
    });
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
    () => ({ path: location.path, search: location.search, hash: location.hash, navigate }),
    [location.path, location.search, location.hash, navigate],
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
