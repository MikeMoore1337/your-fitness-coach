import { StrictMode, lazy, Suspense, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './app/AuthProvider';
import { AuthGate } from './app/AuthGate';
import { OnboardingGate } from './app/OnboardingGate';
import { ErrorBoundary } from './app/ErrorBoundary';
import { FeedbackProvider } from './shared/ui/FeedbackProvider';
import { OnlineStatus } from './shared/ui/OnlineStatus';
import { LoadingState } from './shared/ui/common';
import { isTelegramLaunch } from './shared/telegram/launch';
import { applyPlatformTheme, useTelegram } from './shared/telegram/useTelegram';
import { NavigationProvider, Redirect, useNavigation } from './shared/navigation/router';
import {
  isPublicKnowledgePath,
  publicKnowledgePathFromLegacyRoute,
} from './shared/navigation/knowledgeRoutes';
import { applyRouteMetadata } from './shared/seo/metadata';
import { clearAllDemoSessions } from './features/demo/demoApi';
import { PwaProvider } from './shared/pwa/PwaProvider';
import './styles/legacy.css';
import './styles/fonts.css';
import './styles/design-system.css';

const publicContentRoots = new Set([
  '/training',
  '/nutrition',
  '/progress',
  '/for-trainers',
  '/knowledge',
  '/exercises',
]);

function isArticleRoute(path: string): boolean {
  return path === '/articles' || path.startsWith('/articles/');
}

function isPublicContentRoute(path: string): boolean {
  return (
    publicContentRoots.has(path) || path.startsWith('/knowledge/') || path.startsWith('/exercises/')
  );
}

const MiniAppPage = lazy(() => import('./pages/miniapp/MiniAppPage'));
const ProgressReportPage = lazy(() => import('./pages/reports/ProgressReportPage'));
const CoachPage = lazy(() => import('./pages/coach/CoachPage'));
const AdminPage = lazy(() => import('./pages/admin/AdminPage'));
const LandingPage = lazy(() => import('./pages/landing/LandingPage'));
const DemoPage = lazy(() => import('./pages/demo/DemoPage'));
const PublicContentPage = lazy(() => import('./pages/public/PublicContentPage'));
const ArticlesPage = lazy(() => import('./pages/public/ArticlesPage'));
const PublicKnowledgeRoute = lazy(() => import('./pages/public/PublicKnowledgeRoute'));
const VerifyEmailPage = lazy(() => import('./pages/auth/VerifyEmailPage'));
const ResetPasswordPage = lazy(() => import('./pages/auth/ResetPasswordPage'));
const LoginPage = lazy(() => import('./pages/auth/LoginPage'));
const JoinCoachPage = lazy(() => import('./pages/join/JoinCoachPage'));
const OnboardingPage = lazy(() => import('./pages/onboarding/OnboardingPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
function loadTelegramSdk(): Promise<void> {
  if (!isTelegramLaunch(window.location) || window.Telegram?.WebApp) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-web-app.js';
    script.async = true;
    script.addEventListener('load', () => resolve(), { once: true });
    script.addEventListener('error', () => resolve(), { once: true });
    document.head.append(script);
  });
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
    mutations: { retry: 0 },
  },
});

function AuthenticatedRoute({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AuthGate>{children}</AuthGate>
    </AuthProvider>
  );
}

function AppRoutes() {
  const { path } = useNavigation();
  const legacyKnowledgePath = publicKnowledgePathFromLegacyRoute(path);
  useEffect(() => {
    if (path !== '/' && !isPublicContentRoute(path) && !isArticleRoute(path)) {
      applyRouteMetadata(path);
    }
  }, [path]);
  if (path === '/') return <LandingPage />;
  if (isArticleRoute(path)) return <ArticlesPage />;
  if (path === '/demo') {
    if (isTelegramLaunch(window.location)) return <Redirect to="/app" />;
    return <DemoPage />;
  }
  if (legacyKnowledgePath) {
    return <PublicKnowledgeRoute articlePath={legacyKnowledgePath} legacyRoute />;
  }
  if (isPublicKnowledgePath(path)) {
    return <PublicKnowledgeRoute articlePath={path} />;
  }
  if (isPublicContentRoute(path)) {
    return <PublicContentPage />;
  }
  if (path === '/login')
    return (
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    );
  if (path === '/verify-email')
    return (
      <AuthProvider>
        <VerifyEmailPage />
      </AuthProvider>
    );
  if (path === '/reset-password')
    return (
      <AuthProvider>
        <ResetPasswordPage />
      </AuthProvider>
    );
  if (path.startsWith('/join/')) {
    const token = path.slice('/join/'.length);
    if (/^[A-Za-z0-9_-]{20,128}$/.test(token)) {
      return (
        <AuthenticatedRoute>
          <JoinCoachPage token={token} />
        </AuthenticatedRoute>
      );
    }
  }
  if (path === '/app')
    return (
      <AuthenticatedRoute>
        <OnboardingGate>
          <MiniAppPage />
        </OnboardingGate>
      </AuthenticatedRoute>
    );
  if (path === '/app/report')
    return (
      <AuthenticatedRoute>
        <OnboardingGate>
          <ProgressReportPage />
        </OnboardingGate>
      </AuthenticatedRoute>
    );
  if (path === '/onboarding')
    return (
      <AuthenticatedRoute>
        <OnboardingPage />
      </AuthenticatedRoute>
    );
  if (path === '/coach')
    return (
      <AuthenticatedRoute>
        <CoachPage />
      </AuthenticatedRoute>
    );
  if (path === '/admin') {
    if (isTelegramLaunch(window.location)) return <Redirect to="/app" />;
    return (
      <AuthenticatedRoute>
        <AdminPage />
      </AuthenticatedRoute>
    );
  }
  return <NotFoundPage />;
}

function Root() {
  useTelegram();
  return (
    <QueryClientProvider client={queryClient}>
      <PwaProvider>
        <ErrorBoundary>
          <FeedbackProvider>
            <NavigationProvider>
              <OnlineStatus />
              <Suspense
                fallback={
                  <main className="container">
                    <LoadingState />
                  </main>
                }
              >
                <AppRoutes />
              </Suspense>
            </NavigationProvider>
          </FeedbackProvider>
        </ErrorBoundary>
      </PwaProvider>
    </QueryClientProvider>
  );
}

function renderApp(): void {
  applyPlatformTheme(window.Telegram?.WebApp ?? null);
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <Root />
    </StrictMode>,
  );
}

async function bootstrap(): Promise<void> {
  if (isTelegramLaunch(window.location)) {
    await loadTelegramSdk();
  }
  if (window.location.pathname === '/demo' && isTelegramLaunch(window.location)) {
    clearAllDemoSessions();
  }
  renderApp();
}

void bootstrap();
