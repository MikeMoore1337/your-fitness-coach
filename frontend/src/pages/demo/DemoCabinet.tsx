import { useCallback, useEffect, useMemo, useState } from 'react';
import { AppShell, type DemoAppShellConfig } from '../../app/AppShell';
import '../../styles/react.css';
import '../../styles/design-v2.css';
import {
  applyDemoAction,
  clearAllDemoSessions,
  clearDemoSession,
  DemoApiError,
  loadDemoSession,
  resetDemoSession,
  startDemoSession,
  type DemoScenario,
  type DemoSelfTrainingState,
  type DemoSessionSnapshot,
} from '../../features/demo/demoApi';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { calendarWeek, dateInputValue } from '../../shared/dateTime';
import { AppLink, useNavigation } from '../../shared/navigation/router';
import { DataConfidence } from '../../shared/ui/DataConfidence';
import { useSemanticMotion } from '../../shared/ui/useSemanticMotion';
import { QuantitativeProgress, TaskProgress } from '../../shared/ui/DataViz';
import {
  TRAINING_WEEK_LEGEND,
  WeekStrip,
  type WeekStripActivity,
  type WeekStripDayMeta,
} from '../../shared/ui/WeekStrip';
import {
  Badge,
  Button,
  ErrorState,
  Field,
  LoadingState,
  Metric,
  Surface,
} from '../../shared/ui/common';
import './demo-cabinet.css';

export type DemoCabinetSection = 'today' | 'nutrition' | 'progress' | 'trainer';

const SCENARIOS: ReadonlyArray<{
  value: DemoScenario;
  compactLabel: string;
  label: string;
}> = [
  { value: 'self_training', compactLabel: 'Для себя', label: 'Тренировка для себя' },
  { value: 'nutrition', compactLabel: 'Питание', label: 'Питание: дневник и итог' },
  { value: 'trainer', compactLabel: 'Тренер', label: 'Тренер: разбор результата клиента' },
];

function scenarioFromSearch(search: string): DemoScenario {
  const value = new URLSearchParams(search).get('scenario');
  return value === 'nutrition' || value === 'trainer' ? value : 'self_training';
}

function isCurrentScenario(scenario: DemoScenario): boolean {
  return scenarioFromSearch(window.location.search) === scenario;
}

function startSection(scenario: DemoScenario): DemoCabinetSection {
  return scenario === 'trainer' ? 'trainer' : 'today';
}

function sectionFromSearch(search: string, scenario: DemoScenario): DemoCabinetSection {
  const value = new URLSearchParams(search).get('section');
  if (value === 'today' || value === 'nutrition' || value === 'progress') return value;
  if (value === 'trainer' && scenario === 'trainer') return value;
  return startSection(scenario);
}

export function demoCabinetPath(
  scenario: DemoScenario,
  section: DemoCabinetSection = startSection(scenario),
): string {
  const safeSection =
    section === 'trainer' && scenario !== 'trainer' ? startSection(scenario) : section;
  return `/demo?cabinet=1&scenario=${scenario}&section=${safeSection}`;
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

function trainingAction(state: DemoSelfTrainingState): { action: string; label: string } | null {
  if (state.screen === 'today') return { action: 'start_workout', label: 'Продолжить тренировку' };
  if (state.screen !== 'active_workout') return null;
  if (state.completed_sets < state.total_sets) {
    return { action: 'complete_set', label: 'Завершить текущий подход' };
  }
  return { action: 'finish_workout', label: 'Завершить тренировку' };
}

function Conversion({
  scenario,
  section,
  title,
}: {
  scenario: DemoScenario;
  section: DemoCabinetSection;
  title: string;
}) {
  return (
    <section className="demo-cabinet-conversion" aria-labelledby="demoCabinetConversionTitle">
      <div>
        <span className="eyebrow">После демо</span>
        <h2 id="demoCabinetConversionTitle">{title}</h2>
        <p>
          Подготовленный пример останется в демо. После входа приложение откроется сразу, а свои
          данные можно добавить позже.
        </p>
      </div>
      <AppLink
        className="ui-button demo-cabinet-conversion__action"
        to={loginPath(scenario, section)}
        onClick={() => {
          clearAllDemoSessions();
          trackProductEvent(
            { name: 'demo_login_selected', surface: productEventSurface() },
            { dedupe: 'session', dedupeKey: scenario },
          );
        }}
      >
        Войти в приложение
      </AppLink>
    </section>
  );
}

function TodaySection({
  busy,
  onAction,
  scenario,
  snapshot,
}: {
  busy: boolean;
  onAction(action: string): void;
  scenario: DemoScenario;
  snapshot: DemoSessionSnapshot;
}) {
  const today = dateInputValue(new Date());
  const week = calendarWeek(today);
  const currentDay = week.indexOf(today);
  const getDayMeta = (date: string): WeekStripDayMeta => {
    const index = week.indexOf(date);
    const activity: WeekStripActivity = [0, 3, 5].includes(index)
      ? { key: 'strength', label: 'Силовая' }
      : [1, 4].includes(index)
        ? { key: 'cardio', label: 'Кардио' }
        : { key: 'rest', label: 'Отдых' };
    if (activity.key === 'rest') {
      return { activities: [activity], status: { key: 'neutral', label: 'День отдыха' } };
    }
    if (date === today) {
      return {
        activities: [activity],
        status: { key: 'in-progress', label: snapshot.cabinet.today.status_label },
      };
    }
    if (index >= 0 && index < snapshot.cabinet.today.completed_days) {
      return {
        activities: [activity],
        status: { key: 'completed', label: 'День завершён' },
      };
    }
    if (index > currentDay && index < snapshot.cabinet.today.planned_days) {
      return {
        activities: [activity],
        status: { key: 'planned', label: 'Есть план' },
      };
    }
    return {
      activities: [activity],
      status: { key: 'neutral', label: 'Без обязательного действия' },
    };
  };
  const state = snapshot.state;
  const nextTrainingAction = state.kind === 'self_training' ? trainingAction(state) : null;

  return (
    <>
      <header className="demo-cabinet-title">
        <span className="eyebrow">Сегодня</span>
        <h1>{snapshot.cabinet.today.title}</h1>
        <p>{snapshot.cabinet.today.summary}</p>
      </header>
      <WeekStrip
        anchorDate={today}
        ariaLabel="Контекст текущей недели"
        getDayMeta={getDayMeta}
        legend={TRAINING_WEEK_LEGEND}
        mode="overview"
        title="Неделя"
        today={today}
      />
      <div className="demo-cabinet-focus-grid">
        <Surface className="demo-cabinet-primary">
          <Badge tone={snapshot.cabinet.meaningful_action_completed ? 'success' : 'neutral'}>
            {snapshot.cabinet.today.status_label}
          </Badge>
          {state.kind === 'self_training' ? (
            <>
              <TaskProgress
                completed={state.completed_sets}
                label="Выполнено подходов"
                total={state.total_sets}
              />
              {nextTrainingAction && (
                <Button
                  disabled={busy}
                  fullWidth
                  onClick={() => onAction(nextTrainingAction.action)}
                >
                  {busy ? 'Обновляем…' : nextTrainingAction.label}
                </Button>
              )}
              <div className="demo-cabinet-rows" aria-label="Упражнения">
                {state.exercises.map((exercise) => (
                  <article className={`demo-cabinet-row is-${exercise.status}`} key={exercise.name}>
                    <div>
                      <strong>{exercise.name}</strong>
                      <span>{exercise.prescription}</span>
                    </div>
                    <small>
                      {exercise.status === 'completed'
                        ? 'Готово'
                        : exercise.status === 'current'
                          ? 'Сейчас'
                          : 'Далее'}
                    </small>
                  </article>
                ))}
              </div>
              {!nextTrainingAction && (
                <AppLink className="ui-button" to={demoCabinetPath(scenario, 'progress')}>
                  Посмотреть результат в прогрессе
                </AppLink>
              )}
            </>
          ) : state.kind === 'nutrition' ? (
            <>
              <p>Добавьте недавний продукт — итог изменится здесь и в разделе «Прогресс».</p>
              <div className="demo-cabinet-metrics">
                <Metric label="Калории" value={`${snapshot.cabinet.nutrition.calories} ккал`} />
                <Metric label="Приёмы пищи" value={snapshot.cabinet.nutrition.meals_logged} />
              </div>
              <Button
                disabled={busy || state.item_added}
                fullWidth
                onClick={() => onAction('add_recent')}
              >
                {busy
                  ? 'Добавляем…'
                  : state.item_added
                    ? 'Продукт уже добавлен'
                    : 'Добавить недавний продукт'}
              </Button>
            </>
          ) : (
            <>
              <p>
                Откройте подготовленный результат клиента и оставьте короткий комментарий к
                тренировке.
              </p>
              <AppLink className="ui-button" to={demoCabinetPath(scenario, 'trainer')}>
                Открыть контекст клиента
              </AppLink>
            </>
          )}
        </Surface>
        <aside className="demo-cabinet-linked" aria-label="Связанные факты дня">
          <div>
            <span>Питание</span>
            <strong>
              {snapshot.cabinet.nutrition.calories} из {snapshot.cabinet.nutrition.calorie_target}{' '}
              ккал
            </strong>
            <AppLink to={demoCabinetPath(scenario, 'nutrition')}>Открыть дневник</AppLink>
          </div>
          <div>
            <span>Прогресс</span>
            <strong>
              {snapshot.cabinet.progress.latest_volume_kg.toLocaleString('ru-RU')} кг за тренировку
            </strong>
            <AppLink to={demoCabinetPath(scenario, 'progress')}>Посмотреть динамику</AppLink>
          </div>
        </aside>
      </div>
    </>
  );
}

function NutritionSection({
  busy,
  onAction,
  scenario,
  snapshot,
}: {
  busy: boolean;
  onAction(action: string): void;
  scenario: DemoScenario;
  snapshot: DemoSessionSnapshot;
}) {
  const nutrition = snapshot.cabinet.nutrition;
  const isActionScenario = snapshot.state.kind === 'nutrition';
  return (
    <>
      <header className="demo-cabinet-title">
        <span className="eyebrow">Питание</span>
        <h1>Дневной итог без вымышленных нулей</h1>
        <p>Факты обновляются только после подтверждённого действия в текущей демо-сессии.</p>
      </header>
      <Surface className="demo-cabinet-nutrition">
        <div className="demo-cabinet-metrics" aria-label="Итоги питания">
          <Metric
            label="Калории"
            value={`${nutrition.calories} / ${nutrition.calorie_target}`}
            hint="ккал"
          />
          <Metric
            label="Белок"
            value={`${nutrition.protein_g} / ${nutrition.protein_target_g}`}
            hint="г"
          />
          <Metric label="Приёмы пищи" value={nutrition.meals_logged} />
        </div>
        <article className={`demo-cabinet-recent${nutrition.item_added ? ' is-added' : ''}`}>
          <div>
            <span>{nutrition.item_added ? 'Подтверждённая запись' : 'Недавний продукт'}</span>
            <strong>{nutrition.recent_item.name}</strong>
            <small>{nutrition.recent_item.serving}</small>
          </div>
          <strong>{nutrition.recent_item.calories} ккал</strong>
        </article>
        {isActionScenario ? (
          <Button
            disabled={busy || nutrition.item_added}
            fullWidth
            onClick={() => onAction('add_recent')}
          >
            {busy
              ? 'Добавляем…'
              : nutrition.item_added
                ? 'Запись уже учтена'
                : 'Добавить недавний продукт'}
          </Button>
        ) : (
          <AppLink
            className="ui-button ui-button--secondary"
            to={demoCabinetPath(scenario, 'today')}
          >
            Вернуться к главному действию
          </AppLink>
        )}
      </Surface>
    </>
  );
}

function ProgressSection({
  scenario,
  snapshot,
}: {
  scenario: DemoScenario;
  snapshot: DemoSessionSnapshot;
}) {
  const progress = snapshot.cabinet.progress;
  return (
    <>
      <header className="demo-cabinet-title">
        <span className="eyebrow">Прогресс</span>
        <h1>Подтверждённые действия становятся историей</h1>
        <p>{progress.summary}</p>
      </header>
      <Surface className="demo-cabinet-progress">
        <div className="demo-cabinet-metrics" aria-label="Факты прогресса">
          <Metric label="Тренировки" value={progress.workouts_completed} hint="завершено" />
          <Metric
            label="Последний объём"
            value={`${progress.latest_volume_kg.toLocaleString('ru-RU')} кг`}
          />
          <Metric
            label="Динамика объёма"
            value={`${progress.volume_change_percent > 0 ? '+' : ''}${progress.volume_change_percent}%`}
            hint="за 4 недели"
          />
        </div>
        <div className="demo-cabinet-progress__nutrition">
          <QuantitativeProgress
            label="Дневной итог питания"
            maximum={100}
            unit="%"
            value={progress.nutrition_completion_percent}
          />
          <small>Заполнено дней: {progress.nutrition_days_logged} из 7</small>
          <AppLink to={demoCabinetPath(scenario, 'nutrition')}>
            Открыть подтверждённые записи
          </AppLink>
        </div>
      </Surface>
      <DataConfidence
        kind="training"
        signal={{
          status: 'sufficient',
          counters: {
            working_set_count: progress.workouts_completed * 8,
            workout_session_count: progress.workouts_completed,
            required_working_set_count: 24,
            required_workout_session_count: 3,
          },
          reason_keys: [],
        }}
      />
    </>
  );
}

function TrainerSection({
  busy,
  onComment,
  snapshot,
}: {
  busy: boolean;
  onComment(comment: string): void;
  snapshot: DemoSessionSnapshot;
}) {
  const trainer = snapshot.cabinet.trainer;
  const [comment, setComment] = useState('Техника стабильна. Сохраняем темп и добавляем 2,5 кг.');
  if (!trainer) return null;
  return (
    <>
      <header className="demo-cabinet-title">
        <span className="eyebrow">Клиент тренера · демонстрационный пример</span>
        <h1>{trainer.client_name}</h1>
        <p>{trainer.context_label}</p>
      </header>
      <div className="demo-cabinet-focus-grid">
        <Surface className="demo-cabinet-trainer">
          <span>Тренировка</span>
          <h2>{trainer.workout_title}</h2>
          <dl>
            {trainer.facts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        </Surface>
        <Surface className="demo-cabinet-comment">
          {trainer.comment ? (
            <div className="demo-cabinet-comment__saved" role="status">
              <strong>Комментарий сохранён до конца демо-сессии</strong>
              <p>{trainer.comment}</p>
            </div>
          ) : (
            <>
              <Field
                label="Комментарий к этой тренировке"
                labelFor="demoCabinetTrainerComment"
                hint="Не вводите реальные имена, контакты или медицинские данные."
              >
                <textarea
                  className="ui-input"
                  id="demoCabinetTrainerComment"
                  maxLength={280}
                  onChange={(event) => setComment(event.currentTarget.value)}
                  rows={5}
                  value={comment}
                />
              </Field>
              <Button
                disabled={busy || !comment.trim()}
                fullWidth
                onClick={() => onComment(comment)}
              >
                {busy ? 'Сохраняем…' : 'Сохранить комментарий'}
              </Button>
            </>
          )}
          <div className="demo-cabinet-disabled-action">
            <Button aria-describedby="demoCabinetInviteReason" disabled variant="secondary">
              Пригласить нового клиента
            </Button>
            <span id="demoCabinetInviteReason">
              В демо нет реальных приглашений и отношений тренер–клиент.
            </span>
          </div>
        </Surface>
      </div>
    </>
  );
}

export default function DemoCabinet() {
  const { navigate, search } = useNavigation();
  const scenario = useMemo(() => scenarioFromSearch(search), [search]);
  const section = useMemo(() => sectionFromSearch(search, scenario), [scenario, search]);
  const [snapshot, setSnapshot] = useState<DemoSessionSnapshot | null>(null);
  const [loadedScenario, setLoadedScenario] = useState<DemoScenario | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<DemoApiError | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const next = await loadDemoSession(scenario, signal);
        if (!isCurrentScenario(scenario)) return;
        setSnapshot(next);
        setError(null);
        trackProductEvent(
          { name: 'demo_started', surface: productEventSurface() },
          { dedupe: 'session', dedupeKey: scenario },
        );
      } catch (nextError) {
        if (nextError instanceof DOMException && nextError.name === 'AbortError') return;
        if (!isCurrentScenario(scenario)) return;
        setSnapshot(null);
        setError(
          nextError instanceof DemoApiError
            ? nextError
            : new DemoApiError('Не удалось открыть демо.', 0),
        );
      } finally {
        if (!signal?.aborted && isCurrentScenario(scenario)) {
          setLoadedScenario(scenario);
          setLoading(false);
        }
      }
    },
    [scenario],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadDemoSession(scenario, controller.signal)
      .then((next) => {
        if (!isCurrentScenario(scenario)) return;
        setSnapshot(next);
        setError(null);
        trackProductEvent(
          { name: 'demo_started', surface: productEventSurface() },
          { dedupe: 'session', dedupeKey: scenario },
        );
      })
      .catch((nextError) => {
        if (nextError instanceof DOMException && nextError.name === 'AbortError') return;
        if (!isCurrentScenario(scenario)) return;
        setSnapshot(null);
        setError(
          nextError instanceof DemoApiError
            ? nextError
            : new DemoApiError('Не удалось открыть демо.', 0),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted && isCurrentScenario(scenario)) {
          setLoadedScenario(scenario);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [scenario]);

  useEffect(() => {
    const normalized = demoCabinetPath(scenario, section);
    if (`${window.location.pathname}${search}` !== normalized) navigate(normalized, true);
  }, [navigate, scenario, search, section]);

  const updateSnapshot = async (operation: () => Promise<DemoSessionSnapshot>, action?: string) => {
    const requestedScenario = scenario;
    setBusy(true);
    setError(null);
    try {
      const previousMeaningful = snapshot?.cabinet.meaningful_action_completed ?? false;
      const next = await operation();
      if (!isCurrentScenario(requestedScenario) || next.scenario !== requestedScenario) {
        return;
      }
      setSnapshot(next);
      if (!previousMeaningful && next.cabinet.meaningful_action_completed) {
        trackProductEvent(
          { name: 'demo_meaningful_action_completed', surface: productEventSurface() },
          { dedupe: 'session', dedupeKey: scenario },
        );
      }
      if (action === 'finish_workout') navigate(demoCabinetPath(scenario, 'progress'));
    } catch (nextError) {
      const normalized =
        nextError instanceof DemoApiError
          ? nextError
          : new DemoApiError('Не удалось обновить демо.', 0);
      if (normalized.status === 410) clearDemoSession(scenario);
      if (!isCurrentScenario(requestedScenario)) return;
      setError(normalized);
    } finally {
      setBusy(false);
    }
  };

  const runAction = (action: string, comment?: string) => {
    void updateSnapshot(() => applyDemoAction(scenario, action, comment), action);
  };
  const reset = () => void updateSnapshot(() => resetDemoSession(scenario));
  const newSession = () => {
    const requestedScenario = scenario;
    clearDemoSession(scenario);
    setLoading(true);
    setError(null);
    void startDemoSession(scenario)
      .then((next) => {
        if (isCurrentScenario(requestedScenario)) setSnapshot(next);
      })
      .catch((nextError) => {
        if (!isCurrentScenario(requestedScenario)) return;
        setError(
          nextError instanceof DemoApiError
            ? nextError
            : new DemoApiError('Не удалось начать новую демо-сессию.', 0),
        );
      })
      .finally(() => {
        if (isCurrentScenario(requestedScenario)) setLoading(false);
      });
  };
  const isLoading = loading || loadedScenario !== scenario;
  const cabinetMotion = useSemanticMotion<HTMLDivElement>(
    isLoading
      ? `loading:${scenario}`
      : error
        ? `error:${scenario}:${error.status}`
        : `${scenario}:${section}:${snapshot?.revision ?? 'empty'}`,
    { animateInitial: false },
  );
  const destinations: DemoAppShellConfig['destinations'] = [
    { key: 'today', label: 'Сегодня', icon: 'today', to: demoCabinetPath(scenario, 'today') },
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
            label: 'Клиент',
            icon: 'coach' as const,
            to: demoCabinetPath(scenario, 'trainer'),
          },
        ]
      : []),
  ];
  const shellDemo: DemoAppShellConfig = {
    activeSection: section,
    brandTo: demoCabinetPath(scenario),
    destinations,
    displayName: scenario === 'trainer' ? 'Демо тренера' : 'Демо-кабинет',
    exitTo: '/',
    menuTitle: 'Выберите демо-сценарий',
    moreLinks: SCENARIOS.map((item) => ({ label: item.label, to: demoCabinetPath(item.value) })),
    onReset: reset,
    resetDisabled: busy || isLoading || !snapshot,
  };

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
          <div>
            <Badge>Демо</Badge>
            <p>
              <strong>Подготовленные данные без сохранения</strong> · 30 минут.
            </p>
          </div>
          <label className="demo-cabinet-boundary__scenario">
            <span className="demo-cabinet-boundary__scenario-label">Демо-сценарий:</span>
            <span className="demo-cabinet-boundary__scenario-select">
              <select
                aria-label="Демо-сценарий"
                disabled={busy || isLoading}
                value={scenario}
                onChange={(event) =>
                  navigate(demoCabinetPath(event.currentTarget.value as DemoScenario))
                }
              >
                {SCENARIOS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.compactLabel}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <div className="demo-cabinet-boundary__actions">
            <Button disabled={shellDemo.resetDisabled} onClick={reset} variant="secondary">
              Сбросить
            </Button>
            <AppLink className="ui-button ui-button--secondary" to="/">
              Выйти
            </AppLink>
          </div>
        </section>

        {isLoading ? (
          <Surface className="demo-cabinet-state">
            <LoadingState label="Готовим демо-кабинет…" />
          </Surface>
        ) : error ? (
          <Surface className="demo-cabinet-state">
            <ErrorState
              message={error.message}
              retry={error.status === 410 || error.status === 403 ? newSession : () => void load()}
            />
            <p>
              {error.status === 410
                ? 'Начните новую изолированную сессию.'
                : 'Данные аккаунта и авторизация не затронуты.'}
            </p>
          </Surface>
        ) : snapshot ? (
          <>
            {section === 'today' && (
              <TodaySection
                busy={busy}
                onAction={runAction}
                scenario={scenario}
                snapshot={snapshot}
              />
            )}
            {section === 'nutrition' && (
              <NutritionSection
                busy={busy}
                onAction={runAction}
                scenario={scenario}
                snapshot={snapshot}
              />
            )}
            {section === 'progress' && <ProgressSection scenario={scenario} snapshot={snapshot} />}
            {section === 'trainer' && (
              <TrainerSection
                busy={busy}
                onComment={(comment) => runAction('save_comment', comment)}
                snapshot={snapshot}
              />
            )}
            {snapshot.cabinet.meaningful_action_completed && (
              <Conversion
                scenario={scenario}
                section={section}
                title={snapshot.cabinet.conversion_title}
              />
            )}
          </>
        ) : null}
      </div>
    </AppShell>
  );
}
