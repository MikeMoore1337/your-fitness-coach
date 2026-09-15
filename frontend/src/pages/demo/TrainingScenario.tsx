import { clearAllDemoSessions, type DemoSelfTrainingState } from '../../features/demo/demoApi';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { AppLink } from '../../shared/navigation/router';
import { TaskProgress } from '../../shared/ui/DataViz';
import { Badge, Button, Metric } from '../../shared/ui/common';

function DemoLoginAction({ scenario }: { scenario: 'self_training' }) {
  return (
    <section className="demo-conversion" aria-labelledby={`demoConversion-${scenario}`}>
      <div>
        <span className="eyebrow">Основной сценарий завершён</span>
        <h3 id={`demoConversion-${scenario}`}>Готово. Вы посмотрели основной сценарий</h3>
        <p>Теперь можно начать со своими тренировками, питанием и прогрессом.</p>
      </div>
      <AppLink
        className="ui-button demo-login-action"
        to="/login?next=%2Fapp&from=demo"
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
