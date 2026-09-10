import { useCallback, useEffect, useMemo, useState } from 'react';
import { AppThemeToggle } from '../../shared/ui/AppThemeToggle';
import { BrandLockup } from '../../shared/ui/BrandLogo';
import {
  Badge,
  Button,
  ErrorState,
  Field,
  LoadingState,
  Metric,
  Surface,
} from '../../shared/ui/common';
import { AppLink, useNavigation } from '../../shared/navigation/router';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { TaskProgress } from '../../shared/ui/DataViz';
import {
  applyDemoAction,
  clearAllDemoSessions,
  clearDemoSession,
  DemoApiError,
  loadDemoSession,
  resetDemoSession,
  startDemoSession,
  type DemoNutritionState,
  type DemoScenario,
  type DemoSelfTrainingState,
  type DemoSessionSnapshot,
  type DemoTrainerState,
} from '../../features/demo/demoApi';
import DemoCabinet from './DemoCabinet';
import './demo.css';

const SCENARIOS: ReadonlyArray<{ value: DemoScenario; label: string; context: string }> = [
  { value: 'self_training', label: 'Тренировка', context: 'Для себя' },
  { value: 'nutrition', label: 'Питание', context: 'Дневник' },
  { value: 'trainer', label: 'Тренеру', context: 'Клиент' },
];

function scenarioFromSearch(search: string): DemoScenario {
  const value = new URLSearchParams(search).get('scenario');
  return value === 'nutrition' || value === 'trainer' ? value : 'self_training';
}

function DemoLoginAction({ scenario }: { scenario: DemoScenario }) {
  const loginPath = `/login?next=%2Fapp&from=demo&scenario=${scenario}`;

  return (
    <section className="demo-conversion" aria-labelledby={`demoConversion-${scenario}`}>
      <div>
        <p>Продолжить после демо</p>
        <h3 id={`demoConversion-${scenario}`}>Начните с чистого профиля</h3>
        <span>
          Демо-изменения не переносятся. После входа приложение откроется сразу, а профиль можно
          заполнить позже.
        </span>
      </div>
      <AppLink
        className="ui-button demo-login-action"
        to={loginPath}
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

export function TrainingScenario({
  busy,
  onAction,
  state,
}: {
  busy: boolean;
  onAction: (action: string) => void;
  state: DemoSelfTrainingState;
}) {
  if (state.screen === 'summary') {
    return (
      <>
        <div className="demo-stage__heading">
          <Badge tone="success">Тренировка завершена</Badge>
          <h2>Результат уже собран</h2>
          <p>Факты занятия готовы к просмотру без ручного подсчёта.</p>
        </div>
        <div className="demo-metrics" aria-label="Итоги тренировки">
          <Metric label="Время" value={`${state.duration_minutes} мин`} />
          <Metric label="Объём" value={`${state.total_volume_kg.toLocaleString('ru-RU')} кг`} />
          <Metric label="Подходы" value={`${state.total_sets} из ${state.total_sets}`} />
        </div>
        <Button disabled={busy} fullWidth onClick={() => onAction('open_progress')}>
          {busy ? 'Открываем…' : 'Перейти к прогрессу'}
        </Button>
      </>
    );
  }

  if (state.screen === 'progress') {
    return (
      <>
        <div className="demo-stage__heading">
          <Badge>Прогресс</Badge>
          <h2>Результат становится контекстом</h2>
          <p>Тренировка связана с историей, а динамика показана как факт, не как обещание.</p>
        </div>
        <div className="demo-progress-fact">
          <span>Рабочий объём за 4 недели</span>
          <strong>+{state.progress_change_percent}%</strong>
          <small>по подтверждённым тренировкам этого сценария</small>
        </div>
        <DemoLoginAction scenario="self_training" />
      </>
    );
  }

  const active = state.screen === 'active_workout';
  const allSetsComplete = state.completed_sets >= state.total_sets;
  const action = !active ? 'start_workout' : allSetsComplete ? 'finish_workout' : 'complete_set';
  const label = !active
    ? 'Начать тренировку'
    : allSetsComplete
      ? 'Завершить тренировку'
      : 'Завершить текущий подход';

  return (
    <>
      <div className="demo-stage__heading">
        <Badge>{active ? 'В процессе' : 'Сегодня'}</Badge>
        <h2>{state.workout_title}</h2>
        <p>{state.workout_subtitle}</p>
      </div>
      <TaskProgress
        completed={state.completed_sets}
        label="Выполнено подходов"
        total={state.total_sets}
      />
      <div className="demo-fact-list" aria-label="Упражнения тренировки">
        {state.exercises.map((exercise) => (
          <article className={`demo-fact-row is-${exercise.status}`} key={exercise.name}>
            <div>
              <strong>{exercise.name}</strong>
              <span>{exercise.prescription}</span>
            </div>
            <span className="demo-fact-row__status">
              {exercise.status === 'completed'
                ? 'Готово'
                : exercise.status === 'current'
                  ? 'Сейчас'
                  : 'Далее'}
            </span>
          </article>
        ))}
      </div>
      <Button
        className="demo-training-action"
        disabled={busy}
        fullWidth
        onClick={() => onAction(action)}
      >
        {busy ? 'Обновляем…' : label}
      </Button>
    </>
  );
}

function NutritionScenario({
  busy,
  onAction,
  state,
}: {
  busy: boolean;
  onAction: (action: string) => void;
  state: DemoNutritionState;
}) {
  if (state.screen === 'report') {
    const caloriePercent = Math.round((state.calories / state.calorie_target) * 100);
    const proteinPercent = Math.round((state.protein_g / state.protein_target_g) * 100);
    return (
      <>
        <div className="demo-stage__heading">
          <Badge>Отчёт по питанию</Badge>
          <h2>День виден целиком</h2>
          <p>Ориентиры и фактические записи показаны вместе, без подмены пропусков нулями.</p>
        </div>
        <div className="demo-metrics" aria-label="Итоги питания">
          <Metric label="Калории" value={`${caloriePercent}%`} hint="от ориентира" />
          <Metric label="Белок" value={`${proteinPercent}%`} hint="от ориентира" />
          <Metric label="Приёмы пищи" value={state.meals_logged} />
        </div>
        <div className="demo-confidence">
          <strong>Данных достаточно для дневного итога</strong>
          <span>Отчёт основан только на подготовленных записях текущей демо-сессии.</span>
        </div>
        <DemoLoginAction scenario="nutrition" />
      </>
    );
  }

  return (
    <>
      <div className="demo-stage__heading">
        <Badge>Питание</Badge>
        <h2>Быстрая запись без длинного поиска</h2>
        <p>{state.date_label}</p>
      </div>
      <div className="demo-metrics" aria-label="Сводка питания">
        <Metric label="Калории" value={`${state.calories} / ${state.calorie_target}`} hint="ккал" />
        <Metric label="Белок" value={`${state.protein_g} / ${state.protein_target_g}`} hint="г" />
        <Metric label="Приёмы пищи" value={state.meals_logged} />
      </div>
      <article className={`demo-recent-item${state.item_added ? ' is-added' : ''}`}>
        <div>
          <span>{state.item_added ? 'Добавлено в дневник' : 'Недавний продукт'}</span>
          <strong>{state.recent_item.name}</strong>
          <small>{state.recent_item.serving}</small>
        </div>
        <strong>{state.recent_item.calories} ккал</strong>
      </article>
      <Button
        disabled={busy}
        fullWidth
        onClick={() => onAction(state.item_added ? 'open_nutrition_report' : 'add_recent')}
      >
        {busy
          ? 'Обновляем…'
          : state.item_added
            ? 'Открыть отчёт по питанию'
            : 'Добавить недавний продукт'}
      </Button>
    </>
  );
}

function TrainerScenario({
  busy,
  onComment,
  state,
}: {
  busy: boolean;
  onComment: (comment: string) => void;
  state: DemoTrainerState;
}) {
  const [comment, setComment] = useState(
    'Техника стабильна. На следующей тренировке сохраняем темп и добавляем 2,5 кг.',
  );

  return (
    <>
      <div className="demo-stage__heading">
        <Badge>Клиент тренера</Badge>
        <h2>{state.client_name}</h2>
        <p>{state.context_label}</p>
      </div>
      <div className="demo-trainer-workout">
        <span>Тренировка</span>
        <strong>{state.workout_title}</strong>
      </div>
      <dl className="demo-trainer-facts">
        {state.facts.map((fact) => (
          <div key={fact.label}>
            <dt>{fact.label}</dt>
            <dd>{fact.value}</dd>
          </div>
        ))}
      </dl>
      {state.comment ? (
        <div className="demo-comment-saved" role="status">
          <strong>Контекстный комментарий сохранён до конца демо-сессии</strong>
          <span>{state.comment}</span>
        </div>
      ) : (
        <>
          <Field
            label="Комментарий к этой тренировке"
            labelFor="demoTrainerComment"
            hint="Не вводите реальные имена, контакты или медицинские данные."
          >
            <textarea
              id="demoTrainerComment"
              className="ui-input demo-comment-input"
              maxLength={280}
              rows={4}
              value={comment}
              onChange={(event) => setComment(event.currentTarget.value)}
            />
          </Field>
          <Button disabled={busy || !comment.trim()} fullWidth onClick={() => onComment(comment)}>
            {busy ? 'Сохраняем…' : 'Сохранить комментарий'}
          </Button>
        </>
      )}
      <div className="demo-disabled-action">
        <Button aria-describedby="demoInviteReason" disabled variant="secondary">
          Пригласить нового клиента
        </Button>
        <span id="demoInviteReason">
          В демо нет реальных приглашений и отношений тренер–клиент.
        </span>
      </div>
      {state.comment && <DemoLoginAction scenario="trainer" />}
    </>
  );
}

function LegacyDemoPage() {
  const { navigate, search } = useNavigation();
  const scenario = useMemo(() => scenarioFromSearch(search), [search]);
  const [snapshot, setSnapshot] = useState<DemoSessionSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadedScenario, setLoadedScenario] = useState<DemoScenario | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<DemoApiError | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const next = await loadDemoSession(scenario, signal);
        setSnapshot(next);
        trackProductEvent(
          { name: 'demo_started', surface: productEventSurface() },
          { dedupe: 'session', dedupeKey: scenario },
        );
      } catch (nextError) {
        if (nextError instanceof DOMException && nextError.name === 'AbortError') return;
        setSnapshot(null);
        setError(
          nextError instanceof DemoApiError
            ? nextError
            : new DemoApiError('Не удалось открыть демо.', 0),
        );
      } finally {
        if (!signal?.aborted) {
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
        setSnapshot(next);
        trackProductEvent(
          { name: 'demo_started', surface: productEventSurface() },
          { dedupe: 'session', dedupeKey: scenario },
        );
      })
      .catch((nextError) => {
        if (nextError instanceof DOMException && nextError.name === 'AbortError') return;
        setSnapshot(null);
        setError(
          nextError instanceof DemoApiError
            ? nextError
            : new DemoApiError('Не удалось открыть демо.', 0),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoadedScenario(scenario);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [scenario]);

  const retryLoad = () => {
    setLoading(true);
    setError(null);
    void load();
  };

  const selectScenario = (nextScenario: DemoScenario) => {
    if (nextScenario === scenario) return;
    setSnapshot(null);
    setError(null);
    setLoading(true);
    navigate(`/demo?scenario=${nextScenario}`);
  };

  const updateSnapshot = async (operation: () => Promise<DemoSessionSnapshot>) => {
    setBusy(true);
    setError(null);
    try {
      setSnapshot(await operation());
    } catch (nextError) {
      const normalized =
        nextError instanceof DemoApiError
          ? nextError
          : new DemoApiError('Не удалось обновить демо.', 0);
      if (normalized.status === 410) clearDemoSession(scenario);
      setError(normalized);
    } finally {
      setBusy(false);
    }
  };

  const runAction = (action: string, comment?: string) => {
    void updateSnapshot(async () => {
      const next = await applyDemoAction(scenario, action, comment);
      if (['finish_workout', 'add_recent', 'save_comment'].includes(action)) {
        trackProductEvent(
          { name: 'demo_meaningful_action_completed', surface: productEventSurface() },
          { dedupe: 'session', dedupeKey: scenario },
        );
      }
      return next;
    }).then(() => {
      if (!['open_progress', 'open_nutrition_report', 'save_comment'].includes(action)) return;
      window.requestAnimationFrame(() => {
        document.querySelector('.demo-conversion')?.scrollIntoView({ block: 'nearest' });
      });
    });
  };

  const newSession = () => {
    clearDemoSession(scenario);
    setLoading(true);
    setError(null);
    void startDemoSession(scenario)
      .then(setSnapshot)
      .catch((nextError) =>
        setError(
          nextError instanceof DemoApiError
            ? nextError
            : new DemoApiError('Не удалось начать новую демо-сессию.', 0),
        ),
      )
      .finally(() => setLoading(false));
  };

  const reset = () => void updateSnapshot(() => resetDemoSession(scenario));
  const isLoading = loading || loadedScenario !== scenario;
  const prioritizesTrainingAction =
    snapshot?.state.kind === 'self_training' &&
    (snapshot.state.screen === 'today' || snapshot.state.screen === 'active_workout');

  return (
    <div className="demo-page app-shell--design-v2">
      <a className="demo-skip-link" href="#demoContent">
        К демо-сценарию
      </a>
      <header className="demo-header">
        <AppLink className="demo-header__brand" to="/" aria-label="Your Fitness Coach — на главную">
          <BrandLockup />
        </AppLink>
        <div className="demo-header__status">
          <Badge>Демо</Badge>
          <span className="demo-header__message">Данные исчезнут после завершения сессии</span>
        </div>
        <div className="demo-header__actions">
          <AppThemeToggle />
          <Button disabled={busy || isLoading || !snapshot} onClick={reset} variant="secondary">
            Сбросить
          </Button>
        </div>
      </header>

      <main id="demoContent" className="demo-main" tabIndex={-1}>
        <section className="demo-intro" aria-labelledby="demoTitle">
          <p>Три подготовленных сценария</p>
          <h1 id="demoTitle">Посмотрите продукт в действии</h1>
          <span>Без регистрации, сохранения в аккаунт, уведомлений и внешних вызовов.</span>
        </section>

        <nav className="demo-scenario-nav" aria-label="Демо-сценарии">
          {SCENARIOS.map((item) => (
            <button
              type="button"
              key={item.value}
              className={item.value === scenario ? 'is-active' : ''}
              aria-current={item.value === scenario ? 'page' : undefined}
              disabled={isLoading || busy}
              onClick={() => selectScenario(item.value)}
            >
              <span>{item.context}</span>
              <strong>{item.label}</strong>
            </button>
          ))}
        </nav>

        <div className="demo-layout">
          <aside className="demo-boundary" aria-labelledby="demoBoundaryTitle">
            <h2 id="demoBoundaryTitle">Что безопасно попробовать</h2>
            <ul>
              <li>Изменения живут только в этой демо-сессии.</li>
              <li>Подготовленные данные не относятся к реальным людям.</li>
              <li>Сброс возвращает исходный сценарий.</li>
            </ul>
            <p>
              Экспорт, удаление аккаунта, приглашения, Telegram-связка и уведомления недоступны.
            </p>
          </aside>

          <Surface
            className={`demo-stage${prioritizesTrainingAction ? ' demo-stage--training-action' : ''}`}
            aria-live="polite"
          >
            {isLoading ? (
              <LoadingState label="Готовим демо-сценарий…" />
            ) : error ? (
              <div className="demo-error-state">
                <ErrorState
                  message={error.message}
                  retry={error.status === 410 || error.status === 403 ? newSession : retryLoad}
                />
                {(error.status === 410 || error.status === 403) && (
                  <p>
                    {error.status === 410
                      ? 'Начните новую изолированную сессию.'
                      : 'Сценарий можно безопасно перезапустить.'}
                  </p>
                )}
              </div>
            ) : snapshot?.state.kind === 'self_training' ? (
              <TrainingScenario
                busy={busy}
                state={snapshot.state}
                onAction={(action) => runAction(action)}
              />
            ) : snapshot?.state.kind === 'nutrition' ? (
              <NutritionScenario
                busy={busy}
                state={snapshot.state}
                onAction={(action) => runAction(action)}
              />
            ) : snapshot?.state.kind === 'trainer' ? (
              <TrainerScenario
                busy={busy}
                state={snapshot.state}
                onComment={(comment) => runAction('save_comment', comment)}
              />
            ) : null}
          </Surface>
        </div>
      </main>
    </div>
  );
}

export default function DemoPage() {
  const { search } = useNavigation();
  return new URLSearchParams(search).get('cabinet') === '1' ? <DemoCabinet /> : <LegacyDemoPage />;
}
