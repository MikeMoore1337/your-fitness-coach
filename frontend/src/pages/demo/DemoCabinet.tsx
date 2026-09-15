import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AppShell, type AppSection, type DemoAppShellConfig } from '../../app/AppShell';
import type { QuickAddAction } from '../../app/QuickAddSheet';
import '../../styles/react.css';
import '../../styles/design-v2.css';
import '../../styles/ux-ia-redesign.css';
import {
  clearAllDemoSessions,
  clearDemoSession,
  getDemoSessionToken,
  loadDemoSession,
  resetDemoSession,
  startDemoSession,
  type DemoScenario,
  type DemoSessionSnapshot,
} from '../../features/demo/demoApi';
import { DEMO_SCENARIOS } from '../../features/demo/demoContent';
import {
  getDemoRouteState,
  isDemoRouteVisible,
  setDemoRouteVisible,
  type DemoRouteState,
  type DemoRouteTarget,
} from '../../features/demo/demoRoute';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { AppLink, useNavigation } from '../../shared/navigation/router';
import { DemoRuntimeProvider } from '../../shared/runtime/runtime';
import { Button, ErrorState, LoadingState, Surface } from '../../shared/ui/common';
import { useSemanticMotion } from '../../shared/ui/useSemanticMotion';
import DemoAuthProvider from './DemoAuthProvider';
import MiniAppPage from '../miniapp/MiniAppPage';
import CoachPage from '../coach/CoachPage';
import './demo-cabinet.css';

export type DemoCabinetSection =
  'today' | 'plan' | 'nutrition' | 'progress' | 'profile' | 'trainer';

function scenarioFromSearch(search: string): DemoScenario {
  const value = new URLSearchParams(search).get('scenario');
  return value === 'nutrition' || value === 'trainer' ? value : 'self_training';
}

function startSection(scenario: DemoScenario): DemoCabinetSection {
  return scenario === 'trainer' ? 'trainer' : 'today';
}

function sectionFromSearch(search: string, scenario: DemoScenario): DemoCabinetSection {
  const value = new URLSearchParams(search).get('section');
  if (
    value === 'today' ||
    value === 'plan' ||
    value === 'nutrition' ||
    value === 'progress' ||
    value === 'profile'
  ) {
    return value;
  }
  if (value === 'trainer' && scenario === 'trainer') return value;
  return startSection(scenario);
}

export function demoCabinetPath(
  scenario: DemoScenario,
  section: DemoCabinetSection = startSection(scenario),
): string {
  const safeSection =
    section === 'trainer' && scenario !== 'trainer' ? startSection(scenario) : section;
  const params = new URLSearchParams({ cabinet: '1', scenario, section: safeSection });
  return `/demo?${params.toString()}`;
}

function loginPath(scenario: DemoScenario, section: DemoCabinetSection): string {
  const params = new URLSearchParams({
    next: '/app',
    from: 'demo',
    scenario,
    cabinet: '1',
    section,
  });
  return `/login?${params.toString()}`;
}

function productionPathInDemo(to: string, scenario: DemoScenario): string {
  let parsed: URL;
  try {
    parsed = new URL(to, window.location.origin);
  } catch {
    return to;
  }
  if (parsed.origin !== window.location.origin) return to;

  if (parsed.pathname === '/coach') {
    return demoCabinetPath(scenario, scenario === 'trainer' ? 'trainer' : 'today');
  }
  if (parsed.pathname === '/app/report') return demoCabinetPath(scenario, 'progress');
  if (parsed.pathname !== '/app') return to;

  const requested = parsed.searchParams.get('section');
  const mapped: DemoCabinetSection =
    requested === 'programs' || requested === 'catalog'
      ? 'plan'
      : requested === 'nutrition'
        ? 'nutrition'
        : requested === 'progress'
          ? 'progress'
          : requested === 'profile'
            ? 'profile'
            : startSection(scenario);
  return demoCabinetPath(scenario, mapped);
}

function isCurrentDemoLocation(scenario: DemoScenario): boolean {
  return scenarioFromSearch(window.location.search) === scenario;
}

function demoQuickAddLinks(scenario: DemoScenario): ReadonlyArray<QuickAddAction> {
  return [
    {
      key: 'food',
      label: 'Добавить еду',
      detail: 'Открыть дневник питания',
      icon: 'calories',
      to: `${demoCabinetPath(scenario, 'nutrition')}&quick_add=food`,
    },
    {
      key: 'water',
      label: 'Добавить воду',
      detail: 'Открыть трекер жидкости',
      icon: 'water',
      to: `${demoCabinetPath(scenario, 'nutrition')}&hydration=quick`,
    },
    {
      key: 'cardio',
      label: 'Добавить кардио',
      detail: 'Демо показывает подготовленную активность',
      icon: 'week-cardio',
      to: demoCabinetPath(scenario, 'today'),
    },
    {
      key: 'measurement',
      label: 'Добавить замер',
      detail: 'Открыть прогресс',
      icon: 'body-measurement',
      to: `${demoCabinetPath(scenario, 'progress')}&focus=measurements`,
    },
    {
      key: 'wellbeing',
      label: 'Отметить самочувствие',
      detail: 'Открыть сегодняшний экран',
      icon: 'checklist',
      to: demoCabinetPath(scenario, 'today'),
    },
    {
      key: 'ai-coach',
      label: 'Открыть AI Coach',
      detail: 'В демо доступность показана без запуска провайдера',
      icon: 'ai-coach',
      to: `${demoCabinetPath(scenario, 'profile')}#profile-ai-coach`,
    },
  ];
}

function DemoRoute({
  onContinue,
  onHide,
  onShow,
  route,
  visible,
}: {
  onContinue(target: DemoRouteTarget): void;
  onHide(): void;
  onShow(): void;
  route: DemoRouteState;
  visible: boolean;
}) {
  if (!visible) {
    return (
      <section className="demo-route demo-route--hidden" aria-label="Маршрут демо">
        <Button aria-expanded={false} onClick={onShow} variant="secondary">
          Показать маршрут
        </Button>
      </section>
    );
  }

  return (
    <section className="demo-route" aria-label="Маршрут демо">
      <div className="demo-route__header">
        <strong id="demoRouteTitle">Маршрут демо · {route.currentStep} из 4</strong>
        <Button aria-controls="demoRouteSteps" onClick={onHide} variant="secondary">
          Скрыть маршрут
        </Button>
      </div>
      <ol id="demoRouteSteps" className="demo-route__steps">
        {route.steps.map((step, index) => (
          <li
            className={
              step.complete ? 'is-complete' : index + 1 === route.currentStep ? 'is-current' : ''
            }
            key={step.key}
            aria-current={index + 1 === route.currentStep ? 'step' : undefined}
          >
            <span aria-hidden="true">{step.complete ? '✓' : index + 1}</span>
            <strong>{step.label}</strong>
          </li>
        ))}
      </ol>
      <div className="demo-route__next">
        <p role="status">{route.nextHint}</p>
        {route.target && !route.complete && (
          <Button onClick={() => onContinue(route.target)}>Продолжить</Button>
        )}
      </div>
    </section>
  );
}

function Conversion({
  scenario,
  section,
}: {
  scenario: DemoScenario;
  section: DemoCabinetSection;
}) {
  const otherScenario =
    DEMO_SCENARIOS.find((item) => item.value !== scenario) ?? DEMO_SCENARIOS[0]!;
  return (
    <section className="demo-cabinet-conversion" aria-labelledby="demoCabinetConversionTitle">
      <div>
        <span className="eyebrow">Основной сценарий завершён</span>
        <h2 id="demoCabinetConversionTitle">Готово. Вы посмотрели основной сценарий</h2>
        <p>Теперь можно начать со своими тренировками, питанием и прогрессом.</p>
      </div>
      <div className="demo-cabinet-conversion__actions">
        <AppLink
          className="ui-button demo-cabinet-conversion__action"
          to={loginPath(scenario, section)}
          onClick={() => {
            clearAllDemoSessions();
            trackProductEvent(
              { name: 'demo_own_data_selected', surface: productEventSurface(), scenario },
              { dedupe: 'session', dedupeKey: scenario },
            );
          }}
        >
          Начать со своими данными
        </AppLink>
        <AppLink
          className="ui-button ui-button--secondary demo-cabinet-conversion__action"
          to={demoCabinetPath(otherScenario.value)}
        >
          Попробовать другой сценарий
        </AppLink>
      </div>
    </section>
  );
}

export default function DemoCabinet() {
  const { navigate, search } = useNavigation();
  const queryClient = useQueryClient();
  const scenario = useMemo(() => scenarioFromSearch(search), [search]);
  const section = useMemo(() => sectionFromSearch(search, scenario), [scenario, search]);
  const [snapshot, setSnapshot] = useState<DemoSessionSnapshot | null>(null);
  const [loadedScenario, setLoadedScenario] = useState<DemoScenario | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [routeVisibility, setRouteVisibility] = useState<Record<DemoScenario, boolean>>(() => ({
    self_training: isDemoRouteVisible('self_training'),
    nutrition: isDemoRouteVisible('nutrition'),
    trainer: isDemoRouteVisible('trainer'),
  }));
  const [visitedSectionsByScenario, setVisitedSectionsByScenario] = useState<
    Record<DemoScenario, ReadonlySet<string>>
  >(() => ({
    self_training: scenario === 'self_training' ? new Set([section]) : new Set(),
    nutrition: scenario === 'nutrition' ? new Set([section]) : new Set(),
    trainer: scenario === 'trainer' ? new Set([section]) : new Set(),
  }));
  const routeCompletedRef = useRef(false);

  const markVisited = useCallback((nextScenario: DemoScenario, nextSection: string) => {
    setVisitedSectionsByScenario((current) => {
      const visited = current[nextScenario];
      if (visited.has(nextSection)) return current;
      return {
        ...current,
        [nextScenario]: new Set([...visited, nextSection]),
      };
    });
  }, []);

  const markNavigation = useCallback(
    (to: string) => {
      const mapped = productionPathInDemo(to, scenario);
      if (!mapped.startsWith('/demo')) return;
      const destination = new URL(mapped, window.location.origin);
      markVisited(scenario, sectionFromSearch(destination.search, scenario));
    },
    [markVisited, scenario],
  );

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const next = await loadDemoSession(scenario, signal);
        if (!isCurrentDemoLocation(scenario)) return;
        setSnapshot(next);
        setError(null);
        trackProductEvent(
          { name: 'demo_started', surface: productEventSurface(), scenario },
          { dedupe: 'session', dedupeKey: scenario },
        );
        trackProductEvent(
          { name: 'demo_route_started', surface: productEventSurface(), scenario },
          { dedupe: 'session', dedupeKey: `route:${scenario}` },
        );
      } catch (reason) {
        if (reason instanceof DOMException && reason.name === 'AbortError') return;
        if (!isCurrentDemoLocation(scenario)) return;
        setSnapshot(null);
        setError(reason instanceof Error ? reason : new Error('Не удалось открыть демо.'));
      } finally {
        if (!signal?.aborted && isCurrentDemoLocation(scenario)) {
          setLoadedScenario(scenario);
          setLoading(false);
        }
      }
    },
    [scenario],
  );

  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => load(controller.signal));
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    const normalized = demoCabinetPath(scenario, section);
    if (`${window.location.pathname}${search}` !== normalized) navigate(normalized, true);
  }, [navigate, scenario, search, section]);

  const refreshSnapshot = useCallback(async () => {
    const next = await loadDemoSession(scenario);
    if (isCurrentDemoLocation(scenario) && next.scenario === scenario) setSnapshot(next);
  }, [scenario]);

  const reset = useCallback(async () => {
    const token = getDemoSessionToken(scenario);
    if (!token) return;
    routeCompletedRef.current = false;
    setVisitedSectionsByScenario((current) => ({
      ...current,
      [scenario]: new Set([section]),
    }));
    setError(null);
    queryClient.clear();
    try {
      const next = await resetDemoSession(scenario);
      setSnapshot(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason : new Error('Не удалось начать демо заново.'));
    }
  }, [queryClient, scenario, section]);

  const newSession = useCallback(async () => {
    clearDemoSession(scenario);
    routeCompletedRef.current = false;
    setVisitedSectionsByScenario((current) => ({
      ...current,
      [scenario]: new Set([section]),
    }));
    setLoading(true);
    setError(null);
    queryClient.clear();
    try {
      const next = await startDemoSession(scenario);
      setSnapshot(next);
      setLoadedScenario(scenario);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason : new Error('Не удалось начать новую демо-сессию.'),
      );
    } finally {
      setLoading(false);
    }
  }, [queryClient, scenario, section]);

  const selectScenario = (nextScenario: DemoScenario) => {
    if (nextScenario === scenario || loading) return;
    trackProductEvent({
      name: 'demo_scenario_selected',
      surface: productEventSurface(),
      scenario: nextScenario,
    });
    queryClient.clear();
    setSnapshot(null);
    setError(null);
    markVisited(nextScenario, startSection(nextScenario));
    navigate(demoCabinetPath(nextScenario));
  };

  const visitedSections = visitedSectionsByScenario[scenario] ?? new Set<string>();
  const route =
    snapshot?.scenario === scenario
      ? getDemoRouteState(scenario, snapshot, section, visitedSections)
      : null;

  useEffect(() => {
    if (!route || !snapshot || !route.complete || routeCompletedRef.current) return;
    routeCompletedRef.current = true;
    trackProductEvent(
      { name: 'demo_route_completed', surface: productEventSurface(), scenario },
      { dedupe: 'session', dedupeKey: `completed:${scenario}` },
    );
  }, [route, scenario, snapshot]);

  const onRouteContinue = (target: DemoRouteTarget) => {
    if (!target) return;
    if (target.kind === 'navigate') {
      markVisited(scenario, target.section);
      navigate(demoCabinetPath(scenario, target.section));
      return;
    }
    window.requestAnimationFrame(() => document.getElementById(target.targetId)?.focus());
  };

  const hideRoute = () => {
    setRouteVisibility((current) => ({ ...current, [scenario]: false }));
    setDemoRouteVisible(scenario, false);
    trackProductEvent({ name: 'demo_route_hidden', surface: productEventSurface(), scenario });
  };

  const showRoute = () => {
    setRouteVisibility((current) => ({ ...current, [scenario]: true }));
    setDemoRouteVisible(scenario, true);
    trackProductEvent({ name: 'demo_route_reopened', surface: productEventSurface(), scenario });
  };

  const isLoading = loading || loadedScenario !== scenario;
  const cabinetMotion = useSemanticMotion<HTMLDivElement>(
    isLoading
      ? `loading:${scenario}`
      : error
        ? `error:${scenario}`
        : `${scenario}:${section}:${snapshot?.revision ?? 'empty'}`,
    { animateInitial: false },
  );
  const destinations: DemoAppShellConfig['destinations'] = [
    { key: 'today', label: 'Сегодня', icon: 'today', to: demoCabinetPath(scenario, 'today') },
    { key: 'plan', label: 'План', icon: 'plan', to: demoCabinetPath(scenario, 'plan') },
    {
      key: 'nutrition',
      label: 'Питание',
      icon: 'nutrition',
      to: demoCabinetPath(scenario, 'nutrition'),
    },
    {
      key: 'progress',
      label: 'Прогресс',
      icon: 'progress',
      to: demoCabinetPath(scenario, 'progress'),
    },
    ...(scenario === 'trainer'
      ? [
          {
            key: 'trainer',
            label: 'Работа тренера',
            icon: 'coach' as const,
            to: demoCabinetPath(scenario, 'trainer'),
            mobileHidden: true,
          },
        ]
      : []),
  ];
  const shellDemo: DemoAppShellConfig = {
    activeSection: section === 'trainer' ? 'today' : section,
    brandTo: demoCabinetPath(scenario),
    destinations,
    displayName: 'Демо',
    exitTo: '/',
    menuTitle: 'Сценарии демо',
    minimalUtility: true,
    moreLinks: DEMO_SCENARIOS.map((item) => ({
      label: item.label,
      to: demoCabinetPath(item.value),
      onClick: () =>
        trackProductEvent({
          name: 'demo_scenario_selected',
          surface: productEventSurface(),
          scenario: item.value,
        }),
    })),
    onReset: () => void reset(),
    onNavigate: markNavigation,
    quickAddLinks: demoQuickAddLinks(scenario),
    resetDisabled: isLoading || !snapshot,
  };
  const token = getDemoSessionToken(scenario);
  const sectionOverride: AppSection =
    section === 'trainer' ? 'today' : section === 'plan' ? 'programs' : section;
  const mapNavigationPath = useCallback(
    (to: string) => productionPathInDemo(to, scenario),
    [scenario],
  );

  return (
    <AppShell demo={shellDemo}>
      <div
        className={`page-stack app-section app-section--design-v2 demo-cabinet demo-cabinet--${section}`}
        id={cabinetMotion.elementId}
        data-demo-state={isLoading ? 'loading' : error ? 'error' : 'ready'}
        data-motion-phase={cabinetMotion.motionPhase}
        data-motion-revision={cabinetMotion.motionRevision}
        onAnimationEnd={cabinetMotion.onMotionAnimationEnd}
      >
        <section className="demo-cabinet-boundary" aria-label="Граница демо-режима">
          <strong>Демо-режим · данные не сохраняются</strong>
          <label className="demo-cabinet-boundary__scenario">
            <span className="demo-cabinet-boundary__scenario-label">Сценарий</span>
            <select
              aria-label="Сценарий демо"
              disabled={isLoading}
              value={scenario}
              onChange={(event) => selectScenario(event.currentTarget.value as DemoScenario)}
            >
              {DEMO_SCENARIOS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <div className="demo-cabinet-boundary__actions">
            <Button
              disabled={shellDemo.resetDisabled}
              onClick={() => void reset()}
              variant="secondary"
            >
              Начать заново
            </Button>
            <AppLink className="ui-button ui-button--secondary" to="/">
              Выйти из демо
            </AppLink>
          </div>
        </section>

        {isLoading ? (
          <Surface className="demo-cabinet-state">
            <LoadingState label="Готовим демо-кабинет…" />
          </Surface>
        ) : error || !snapshot || !route || !token ? (
          <Surface className="demo-cabinet-state">
            <ErrorState message={error?.message ?? 'Демо-сессия недоступна.'} retry={newSession} />
            <p>Рабочие аккаунты и их данные не затрагиваются.</p>
          </Surface>
        ) : (
          <>
            <DemoRoute
              onContinue={onRouteContinue}
              onHide={hideRoute}
              onShow={showRoute}
              route={route}
              visible={routeVisibility[scenario]}
            />
            <DemoRuntimeProvider
              mapNavigationPath={mapNavigationPath}
              onNavigate={markNavigation}
              onMutation={refreshSnapshot}
              sessionToken={token}
            >
              <DemoAuthProvider>
                {section === 'trainer' ? (
                  <CoachPage demo={shellDemo} renderShell={false} />
                ) : (
                  <MiniAppPage
                    demo={shellDemo}
                    renderShell={false}
                    sectionOverride={sectionOverride}
                  />
                )}
              </DemoAuthProvider>
            </DemoRuntimeProvider>
            {route.complete && snapshot.cabinet.meaningful_action_completed && (
              <Conversion scenario={scenario} section={section} />
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}
