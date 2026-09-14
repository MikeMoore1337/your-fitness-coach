import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AppShell, type DemoAppShellConfig } from '../../app/AppShell';
import type { QuickAddAction } from '../../app/QuickAddSheet';
import '../../styles/react.css';
import '../../styles/design-v2.css';
import '../../styles/ux-ia-redesign.css';
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
  type DemoTrainerState,
} from '../../features/demo/demoApi';
import { DEMO_SCENARIOS } from '../../features/demo/demoContent';
import {
  getDemoRouteState,
  isDemoRouteVisible,
  selectedTrainerClient,
  setDemoRouteVisible,
  type DemoRouteState,
  type DemoRouteTarget,
} from '../../features/demo/demoRoute';
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

export type DemoCabinetSection =
  'today' | 'plan' | 'nutrition' | 'progress' | 'profile' | 'trainer';

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

function demoQuickAddLinks(scenario: DemoScenario): ReadonlyArray<QuickAddAction> {
  return [
    {
      key: 'food',
      label: 'Добавить еду',
      detail: 'Открыть подготовленный дневник',
      icon: 'calories',
      to: demoCabinetPath(scenario, 'nutrition'),
    },
    {
      key: 'water',
      label: 'Добавить воду',
      detail: 'Точка входа в трекер жидкости',
      icon: 'water',
      to: demoCabinetPath(scenario, 'nutrition'),
    },
    {
      key: 'cardio',
      label: 'Добавить кардио',
      detail: 'Точка входа в запись активности',
      icon: 'week-cardio',
      to: demoCabinetPath(scenario, 'today'),
    },
    {
      key: 'measurement',
      label: 'Добавить замер',
      detail: 'Точка входа в историю тела',
      icon: 'body-measurement',
      to: demoCabinetPath(scenario, 'progress'),
    },
    {
      key: 'wellbeing',
      label: 'Отметить самочувствие',
      detail: 'Точка входа в check-in',
      icon: 'checklist',
      to: demoCabinetPath(scenario, 'today'),
    },
    {
      key: 'ai-coach',
      label: 'Открыть AI Coach',
      detail: 'Настройки открываются после входа',
      icon: 'ai-coach',
      to: demoCabinetPath(scenario, 'profile'),
    },
  ];
}

function trainingAction(state: DemoSelfTrainingState): { action: string; label: string } | null {
  if (state.screen === 'today') return { action: 'start_workout', label: 'Начать тренировку' };
  if (state.screen !== 'active_workout') return null;
  if (state.completed_sets < state.total_sets) {
    return { action: 'complete_set', label: 'Завершить текущий подход' };
  }
  return { action: 'finish_workout', label: 'Завершить тренировку' };
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

function scheduleActivity(title: string): WeekStripActivity {
  return title.toLocaleLowerCase('ru-RU').includes('кардио')
    ? { key: 'cardio', label: 'Кардио' }
    : { key: 'strength', label: 'Силовая' };
}

function scheduleDayMeta(
  snapshot: DemoSessionSnapshot,
  today: string,
  date: string,
): WeekStripDayMeta {
  const week = calendarWeek(today);
  const index = week.indexOf(date);
  const schedule = snapshot.cabinet.program.schedule[index];
  if (!schedule || schedule.status === 'rest') {
    return {
      activities: [{ key: 'rest', label: 'Отдых' }],
      status: { key: 'neutral', label: 'День отдыха' },
    };
  }
  const activity = scheduleActivity(schedule.workout_title);
  if (date === today) {
    return {
      activities: [activity],
      status: { key: 'in-progress', label: snapshot.cabinet.today.status_label },
    };
  }
  if (schedule.status === 'completed') {
    return { activities: [activity], status: { key: 'completed', label: 'День завершён' } };
  }
  return { activities: [activity], status: { key: 'planned', label: 'Есть план' } };
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
          onClick={() => {
            clearDemoSession(scenario);
            trackProductEvent({
              name: 'demo_other_scenario_selected',
              surface: productEventSurface(),
              from_scenario: scenario,
              to_scenario: otherScenario.value,
            });
          }}
        >
          Попробовать другой сценарий
        </AppLink>
      </div>
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
        getDayMeta={(date) => scheduleDayMeta(snapshot, today, date)}
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
              {state.screen !== 'today' && state.screen !== 'active_workout' && (
                <div className="demo-cabinet-result" role="status">
                  <strong>Тренировка уже записана</strong>
                  <span>
                    {state.total_volume_kg.toLocaleString('ru-RU')} кг · {state.duration_minutes}{' '}
                    мин
                  </span>
                </div>
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
              {state.screen === 'summary' ? (
                <Button disabled={busy} fullWidth onClick={() => onAction('open_progress')}>
                  {busy ? 'Открываем…' : 'Перейти к прогрессу'}
                </Button>
              ) : !nextTrainingAction ? (
                <AppLink
                  className="ui-button ui-button--secondary"
                  to={demoCabinetPath(scenario, 'progress')}
                >
                  Посмотреть прогресс
                </AppLink>
              ) : null}
            </>
          ) : state.kind === 'nutrition' ? (
            <>
              <p>Добавьте недавний продукт — итог изменится здесь и в разделе «Прогресс».</p>
              <div className="demo-cabinet-metrics">
                <Metric label="Калории" value={`${snapshot.cabinet.nutrition.calories} ккал`} />
                <Metric label="Приёмы пищи" value={snapshot.cabinet.nutrition.meals_logged} />
              </div>
              <AppLink className="ui-button" to={demoCabinetPath(scenario, 'nutrition')}>
                Открыть дневник
              </AppLink>
            </>
          ) : (
            <>
              <p>
                Откройте одного из подготовленных клиентов, посмотрите результат и оставьте
                комментарий.
              </p>
              <AppLink className="ui-button" to={demoCabinetPath(scenario, 'trainer')}>
                Открыть работу тренера
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

function PlanSection({
  scenario,
  snapshot,
}: {
  scenario: DemoScenario;
  snapshot: DemoSessionSnapshot;
}) {
  const today = dateInputValue(new Date());
  const program = snapshot.cabinet.program;
  return (
    <>
      <header className="demo-cabinet-title">
        <span className="eyebrow">План</span>
        <h1>Активная программа и расписание на неделю</h1>
        <p>
          Посмотрите, как подготовленный план связывает сегодняшнее действие с историей тренировок.
        </p>
      </header>
      <div className="demo-cabinet-focus-grid demo-ia-plan-grid">
        <Surface className="demo-ia-plan-summary">
          <Badge tone="success">Активна</Badge>
          <span className="demo-ia-kicker">Текущая программа</span>
          <h2>{program.name}</h2>
          <p>
            {program.sessions_per_week} тренировки в неделю · неделя {program.current_week} из{' '}
            {program.total_weeks}
          </p>
          <div className="demo-cabinet-schedule" aria-label="Расписание программы">
            {program.schedule.map((day) => (
              <div className={`demo-cabinet-schedule__row is-${day.status}`} key={day.day_label}>
                <strong>{day.day_label}</strong>
                <span>{day.workout_title}</span>
                <small>
                  {day.status === 'completed'
                    ? 'Готово'
                    : day.status === 'planned'
                      ? 'План'
                      : 'Отдых'}
                </small>
              </div>
            ))}
          </div>
          <AppLink className="ui-button" to={demoCabinetPath(scenario, 'today')}>
            Открыть сегодняшнюю тренировку
          </AppLink>
        </Surface>
        <Surface className="demo-ia-plan-management">
          <span className="demo-ia-kicker">Контекст программы</span>
          <h2>История уже собрана</h2>
          <p>
            За последние четыре недели видны тренировки, объём, подходы и регулярность. Управление
            программой открывается после входа.
          </p>
          <AppLink
            className="ui-button ui-button--secondary"
            to={demoCabinetPath(scenario, 'progress')}
          >
            Посмотреть историю
          </AppLink>
        </Surface>
      </div>
      <WeekStrip
        anchorDate={today}
        ariaLabel="Контекст недели в демо-плане"
        getDayMeta={(date) => scheduleDayMeta(snapshot, today, date)}
        legend={TRAINING_WEEK_LEGEND}
        mode="overview"
        title="Расписание недели"
        today={today}
      />
    </>
  );
}

function ProfileSection({ scenario }: { scenario: DemoScenario }) {
  const rows = [
    ['Личные данные и цели', 'Имя, параметры, часовой пояс'],
    ['Тренер', 'Приглашения и режим тренера'],
    ['Уведомления', 'Напоминания и время'],
    ['AI Coach', 'Доступность и личный контекст'],
    ['Интеграции', 'Точка входа готовится'],
    ['Приложение', 'Тема, PWA и runtime'],
    ['Аккаунт и безопасность', 'Вход, копия данных, аккаунт'],
  ];
  return (
    <>
      <header className="demo-cabinet-title">
        <span className="eyebrow">Профиль</span>
        <h1>Настройки по одной понятной группе</h1>
        <p>Демо показывает IA профиля; реальные изменения доступны только после входа.</p>
      </header>
      <Surface className="demo-ia-profile">
        <div className="demo-ia-profile__identity">
          <Badge>Демо-профиль</Badge>
          <h2>Подготовленный профиль</h2>
          <p>
            Цель, программа и история доступны только для просмотра в этой изолированной сессии.
          </p>
        </div>
        <div className="demo-ia-profile__rows" aria-label="Группы настроек профиля">
          {rows.map(([label, detail], index) => (
            <div className={`demo-ia-profile__row${index >= 4 ? ' is-reserved' : ''}`} key={label}>
              <strong>{label}</strong>
              <span>{detail}</span>
              {index >= 4 && <small>Скоро</small>}
            </div>
          ))}
        </div>
        <AppLink className="ui-button" to={loginPath(scenario, 'profile')}>
          Войти и открыть настройки
        </AppLink>
      </Surface>
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
  const state = snapshot.state;
  const isActionScenario = state.kind === 'nutrition';
  const canAdd = isActionScenario && !state.item_added;
  const canOpenReport = isActionScenario && state.item_added && state.screen === 'diary';
  return (
    <>
      <header className="demo-cabinet-title">
        <span className="eyebrow">Питание и прогресс</span>
        <h1>Дневной итог рядом с фактическими записями</h1>
        <p>Добавьте подготовленный продукт и проследите, как меняются дневной итог и показатели.</p>
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
        {canAdd && (
          <Button disabled={busy} fullWidth onClick={() => onAction('add_recent')}>
            {busy ? 'Добавляем…' : 'Добавить недавний продукт'}
          </Button>
        )}
        {canOpenReport && (
          <Button disabled={busy} fullWidth onClick={() => onAction('open_nutrition_report')}>
            {busy ? 'Открываем…' : 'Открыть итог по питанию'}
          </Button>
        )}
        {isActionScenario && state.screen === 'report' && (
          <div className="demo-cabinet-result" role="status">
            <strong>Итог обновлён</strong>
            <span>Запись учтена в текущей демо-сессии.</span>
          </div>
        )}
        {!isActionScenario && (
          <AppLink
            className="ui-button ui-button--secondary"
            to={demoCabinetPath(scenario, 'today')}
          >
            Вернуться к главному действию
          </AppLink>
        )}
        {nutrition.item_added && (
          <AppLink
            className="ui-button ui-button--secondary"
            to={demoCabinetPath(scenario, 'progress')}
          >
            Посмотреть показатели
          </AppLink>
        )}
      </Surface>
    </>
  );
}

function nutritionHistoryLabel(status: 'complete' | 'incomplete' | 'not_logged'): string {
  if (status === 'complete') return 'День заполнен';
  if (status === 'incomplete') return 'День заполнен частично';
  return 'Нет записи';
}

function ProgressSection({
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
  const progress = snapshot.cabinet.progress;
  const trainingState = snapshot.state.kind === 'self_training' ? snapshot.state : null;
  const needsProgressConfirmation = trainingState?.screen === 'summary';
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
          <Metric
            label="Регулярность"
            value={`${progress.adherence_percent}%`}
            hint="за 4 недели"
          />
        </div>
        {needsProgressConfirmation && (
          <Button disabled={busy} fullWidth onClick={() => onAction('open_progress')}>
            {busy ? 'Открываем…' : 'Подтвердить прогресс'}
          </Button>
        )}
        <div className="demo-cabinet-progress__nutrition">
          <QuantitativeProgress
            label="Дневной итог питания"
            maximum={100}
            unit="%"
            value={progress.nutrition_completion_percent}
          />
          <small>
            Заполнено дней: {progress.nutrition_days_logged} из {progress.nutrition_history.length}
          </small>
          <AppLink to={demoCabinetPath(scenario, 'nutrition')}>Открыть дневник</AppLink>
        </div>
      </Surface>
      <div className="demo-cabinet-history-grid">
        <Surface className="demo-cabinet-history" aria-labelledby="demoTrainingHistoryTitle">
          <div className="demo-cabinet-history__heading">
            <span className="demo-ia-kicker">Тренировки</span>
            <h2 id="demoTrainingHistoryTitle">Последние четыре недели</h2>
          </div>
          <ol aria-label="История тренировок">
            {progress.training_history.map((item) => (
              <li key={`${item.period_label}-${item.workout_title}`}>
                <span>{item.period_label}</span>
                <strong>{item.workout_title}</strong>
                <small>
                  {item.completed_sets} подхода · {item.volume_kg.toLocaleString('ru-RU')} кг
                </small>
              </li>
            ))}
          </ol>
        </Surface>
        <Surface className="demo-cabinet-history" aria-labelledby="demoVolumeHistoryTitle">
          <div className="demo-cabinet-history__heading">
            <span className="demo-ia-kicker">Объём</span>
            <h2 id="demoVolumeHistoryTitle">Динамика по занятиям</h2>
          </div>
          <ol className="demo-cabinet-volume-history" aria-label="Динамика объёма">
            {progress.volume_history.map((item) => (
              <li key={item.period_label}>
                <span>{item.period_label}</span>
                <strong>{item.volume_kg.toLocaleString('ru-RU')} кг</strong>
                <span className="demo-cabinet-volume-history__bar" aria-hidden="true">
                  <span
                    style={{ width: `${Math.max(12, Math.round((item.volume_kg / 7000) * 100))}%` }}
                  />
                </span>
              </li>
            ))}
          </ol>
        </Surface>
        <Surface className="demo-cabinet-history" aria-labelledby="demoNutritionHistoryTitle">
          <div className="demo-cabinet-history__heading">
            <span className="demo-ia-kicker">Питание</span>
            <h2 id="demoNutritionHistoryTitle">Дни без вымышленных нулей</h2>
          </div>
          <ul aria-label="История дней питания">
            {progress.nutrition_history.map((item) => (
              <li key={item.date_label}>
                <span>{item.date_label}</span>
                <strong>{nutritionHistoryLabel(item.status)}</strong>
                <small>
                  {item.calories === null
                    ? 'Нет подтверждённых значений'
                    : `${item.calories} ккал · ${item.protein_g} г белка`}
                </small>
              </li>
            ))}
          </ul>
        </Surface>
        <Surface className="demo-cabinet-history" aria-labelledby="demoMeasurementsTitle">
          <div className="demo-cabinet-history__heading">
            <span className="demo-ia-kicker">Замеры</span>
            <h2 id="demoMeasurementsTitle">Доступный контекст</h2>
          </div>
          <ul aria-label="Подготовленные замеры">
            {progress.measurements.map((item) => (
              <li key={`${item.label}-${item.date_label}`}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                <small>{item.date_label}</small>
              </li>
            ))}
          </ul>
        </Surface>
      </div>
      <DataConfidence
        kind="training"
        signal={{
          status: 'sufficient',
          counters: {
            working_set_count: progress.training_history.reduce(
              (total, item) => total + item.completed_sets,
              0,
            ),
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

function trainerBadgeTone(
  clientId: DemoTrainerState['clients'][number]['id'],
): 'success' | 'warning' | 'neutral' {
  if (clientId === 'alexey') return 'success';
  if (clientId === 'maria') return 'warning';
  return 'neutral';
}

function TrainerSection({
  busy,
  onComment,
  onSelectClient,
  snapshot,
}: {
  busy: boolean;
  onComment(comment: string, clientId: DemoTrainerState['selected_client_id']): void;
  onSelectClient(clientId: DemoTrainerState['selected_client_id']): void;
  snapshot: DemoSessionSnapshot;
}) {
  const trainer = snapshot.cabinet.trainer;
  const selected = trainer ? selectedTrainerClient(trainer) : undefined;
  const [commentDraft, setCommentDraft] = useState<{
    clientId: DemoTrainerState['selected_client_id'];
    value: string;
  } | null>(null);
  const comment =
    selected && commentDraft?.clientId === selected.id
      ? commentDraft.value
      : (selected?.comment ?? '');

  if (!trainer || !selected) return null;
  return (
    <>
      <header className="demo-cabinet-title">
        <span className="eyebrow">Работа тренера</span>
        <h1>Разбор результата клиента</h1>
        <p>Выберите подготовленное состояние и оставьте комментарий к конкретной тренировке.</p>
      </header>
      <Surface className="demo-cabinet-trainer-picker">
        <Field
          label="Демонстрационный клиент"
          labelFor="demoCabinetTrainerClient"
          hint="Все состояния вымышлены и существуют только в текущей демо-сессии."
        >
          <select
            className="ui-input"
            id="demoCabinetTrainerClient"
            value={trainer.selected_client_id}
            onChange={(event) =>
              onSelectClient(event.currentTarget.value as DemoTrainerState['selected_client_id'])
            }
          >
            {trainer.clients.map((client) => (
              <option key={client.id} value={client.id}>
                {client.name} · {client.status_label}
              </option>
            ))}
          </select>
        </Field>
      </Surface>
      <div className="demo-cabinet-focus-grid">
        <Surface className="demo-cabinet-trainer">
          <Badge tone={trainerBadgeTone(selected.id)}>{selected.status_label}</Badge>
          <span>{selected.name} · подготовленный клиент</span>
          <h2>{selected.workout_title}</h2>
          <p>{selected.context_label}</p>
          <dl>
            {selected.facts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        </Surface>
        <Surface className="demo-cabinet-comment">
          {selected.comment ? (
            <div className="demo-cabinet-comment__saved" role="status">
              <strong>Комментарий сохранён до конца демо-сессии</strong>
              <p>{selected.comment}</p>
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
                  onChange={(event) =>
                    setCommentDraft({ clientId: selected.id, value: event.currentTarget.value })
                  }
                  rows={5}
                  value={comment}
                />
              </Field>
              <Button
                disabled={busy || !comment.trim()}
                fullWidth
                onClick={() => onComment(comment, selected.id)}
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

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const next = await loadDemoSession(scenario, signal);
        if (!isCurrentScenario(scenario)) return;
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
    void Promise.resolve().then(() => load(controller.signal));
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    const normalized = demoCabinetPath(scenario, section);
    if (`${window.location.pathname}${search}` !== normalized) navigate(normalized, true);
  }, [navigate, scenario, search, section]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setVisitedSectionsByScenario((current) => {
        const visited = current[scenario];
        if (visited.has(section)) return current;
        return { ...current, [scenario]: new Set([...visited, section]) };
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [scenario, section]);

  const updateSnapshot = async (
    operation: () => Promise<DemoSessionSnapshot>,
    action?:
      | 'finish_workout'
      | 'add_recent'
      | 'save_comment'
      | 'open_progress'
      | 'open_nutrition_report'
      | 'select_client',
  ) => {
    const requestedScenario = scenario;
    setBusy(true);
    setError(null);
    try {
      const previousMeaningful = snapshot?.cabinet.meaningful_action_completed ?? false;
      const next = await operation();
      if (!isCurrentScenario(requestedScenario) || next.scenario !== requestedScenario) return;
      setSnapshot(next);
      if (!previousMeaningful && next.cabinet.meaningful_action_completed && action) {
        trackProductEvent(
          {
            name: 'demo_meaningful_action_completed',
            surface: productEventSurface(),
            scenario,
            action: action as 'finish_workout' | 'add_recent' | 'save_comment',
          },
          { dedupe: 'session', dedupeKey: scenario },
        );
      }
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

  const runAction = (
    action: string,
    comment?: string,
    clientId?: DemoTrainerState['selected_client_id'],
  ) => {
    const meaningfulAction =
      action === 'finish_workout' || action === 'add_recent' || action === 'save_comment'
        ? action
        : undefined;
    void updateSnapshot(() => {
      if (comment === undefined && clientId === undefined) return applyDemoAction(scenario, action);
      return applyDemoAction(scenario, action, comment, clientId);
    }, meaningfulAction);
  };

  const reset = () => {
    setRouteVisibility((current) => ({ ...current, [scenario]: true }));
    setDemoRouteVisible(scenario, true);
    setVisitedSectionsByScenario((current) => ({ ...current, [scenario]: new Set([section]) }));
    routeCompletedRef.current = false;
    void updateSnapshot(() => resetDemoSession(scenario));
  };

  const newSession = () => {
    const requestedScenario = scenario;
    clearDemoSession(scenario);
    setRouteVisibility((current) => ({ ...current, [scenario]: true }));
    setDemoRouteVisible(scenario, true);
    setVisitedSectionsByScenario((current) => ({ ...current, [scenario]: new Set([section]) }));
    routeCompletedRef.current = false;
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

  const selectScenario = (nextScenario: DemoScenario) => {
    if (nextScenario === scenario || busy || loading) return;
    trackProductEvent({
      name: 'demo_scenario_selected',
      surface: productEventSurface(),
      scenario: nextScenario,
    });
    setSnapshot(null);
    setError(null);
    setLoading(true);
    navigate(demoCabinetPath(nextScenario));
  };

  const visitedSections = useMemo(
    () => new Set([...(visitedSectionsByScenario[scenario] ?? new Set()), section]),
    [section, scenario, visitedSectionsByScenario],
  );
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
      navigate(demoCabinetPath(scenario, target.section));
      return;
    }
    if (target.kind === 'action') {
      runAction(target.action);
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
        ? `error:${scenario}:${error.status}`
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
    activeSection: section,
    brandTo: demoCabinetPath(scenario),
    destinations,
    displayName: 'Демо',
    exitTo: '/',
    menuTitle: 'Сценарии демо',
    minimalUtility: true,
    moreLinks: DEMO_SCENARIOS.map((item) => ({
      label: item.label,
      to: demoCabinetPath(item.value),
      onClick: () => {
        trackProductEvent({
          name: 'demo_scenario_selected',
          surface: productEventSurface(),
          scenario: item.value,
        });
      },
    })),
    onReset: reset,
    quickAddLinks: demoQuickAddLinks(scenario),
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
          <strong>Демо-режим · данные не сохраняются</strong>
          <label className="demo-cabinet-boundary__scenario">
            <span className="demo-cabinet-boundary__scenario-label">Сценарий</span>
            <span className="demo-cabinet-boundary__scenario-select">
              <select
                aria-label="Сценарий демо"
                disabled={busy || isLoading}
                value={scenario}
                onChange={(event) => selectScenario(event.currentTarget.value as DemoScenario)}
              >
                {DEMO_SCENARIOS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <div className="demo-cabinet-boundary__actions">
            <Button disabled={shellDemo.resetDisabled} onClick={reset} variant="secondary">
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
        ) : snapshot && route ? (
          <>
            <DemoRoute
              onContinue={onRouteContinue}
              onHide={hideRoute}
              onShow={showRoute}
              route={route}
              visible={routeVisibility[scenario]}
            />
            {section === 'today' && (
              <TodaySection
                busy={busy}
                onAction={runAction}
                scenario={scenario}
                snapshot={snapshot}
              />
            )}
            {section === 'plan' && <PlanSection scenario={scenario} snapshot={snapshot} />}
            {section === 'nutrition' && (
              <NutritionSection
                busy={busy}
                onAction={runAction}
                scenario={scenario}
                snapshot={snapshot}
              />
            )}
            {section === 'progress' && (
              <ProgressSection
                busy={busy}
                onAction={runAction}
                scenario={scenario}
                snapshot={snapshot}
              />
            )}
            {section === 'profile' && <ProfileSection scenario={scenario} />}
            {section === 'trainer' && (
              <TrainerSection
                key={`${snapshot.revision}-${snapshot.state.kind}`}
                busy={busy}
                onComment={(comment, clientId) => runAction('save_comment', comment, clientId)}
                onSelectClient={(clientId) => runAction('select_client', undefined, clientId)}
                snapshot={snapshot}
              />
            )}
            {route.complete && snapshot.cabinet.meaningful_action_completed && (
              <Conversion scenario={scenario} section={section} />
            )}
          </>
        ) : null}
      </div>
    </AppShell>
  );
}
