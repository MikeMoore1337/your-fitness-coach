import type { ExerciseHistory } from '../../shared/api/types';
import { AppLink } from '../../shared/navigation/router';
import { ErrorState, LoadingState } from '../../shared/ui/common';

const eventLabels: Record<ExerciseHistory['progression_events'][number]['event_kind'], string> = {
  confirm: 'Подтверждено',
  adjust: 'Скорректировано',
  reject: 'Отклонено',
};

const reasonLabels: Record<string, string> = {
  top_range_repeated: 'верх диапазона повторён',
  full_rir_coverage: 'RIR записан для всех подходов',
  conservative_without_rir: 'сохранено консервативное правило без полного RIR',
  below_range_two_sessions: 'две сессии ниже диапазона',
  need_one_more_stable_session: 'нужна ещё одна стабильная сессия',
  too_few_comparable_sessions: 'сопоставимых сессий пока мало',
  missing_configured_increment: 'в правиле не задан шаг нагрузки',
};

function formatLoad(value: number | null, unit = 'кг'): string {
  return value == null ? 'Нет данных' : `${value} ${unit}`;
}

function workoutLink(workoutId: number): string {
  return `/app?section=progress&workout_id=${workoutId}`;
}

function setLabel(
  set: ExerciseHistory['recent_sessions'][number]['sets'][number],
  loadUnit: string,
): string {
  const reps = set.reps == null ? 'повторы не записаны' : `${set.reps} повт.`;
  const load = set.load_kg == null ? 'внешний вес не записан' : `${set.load_kg} ${loadUnit}`;
  return `${reps} × ${load}${set.pr_eligible ? '' : ' · вспомогательный подход'}`;
}

function eventReason(event: ExerciseHistory['progression_events'][number]): string {
  const reasons = (event.reason_codes ?? []).map(
    (reason) => reasonLabels[reason] ?? 'сохранённая причина',
  );
  return reasons.length ? reasons.join(', ') : 'сохранённое правило программы';
}

export function ExerciseProgressPanel({
  data,
  error,
  isLoading,
}: {
  data: ExerciseHistory | undefined;
  error: Error | null;
  isLoading: boolean;
}) {
  const unit = data?.load_unit === 'kg' ? 'кг' : 'единицы нагрузки';
  const summary = isLoading
    ? 'Загружаем историю…'
    : error
      ? 'Историю пока не удалось загрузить'
      : data?.last_performed
        ? `Последний раз: ${data.last_performed.performed_on}`
        : 'Завершённых подходов пока нет';

  return (
    <section className="exercise-progress" aria-labelledby="exercise-progress-title">
      <details className="card-disclosure" open={Boolean(data?.last_performed)}>
        <summary>
          <span>
            <strong id="exercise-progress-title">Мой прогресс</strong>
            <small>{summary}</small>
          </span>
          <span className="disclosure-icon" aria-hidden="true">
            ›
          </span>
        </summary>
        <div className="exercise-progress__body">
          {isLoading && <LoadingState />}
          {error && <ErrorState message={error.message} />}
          {data && (
            <>
              <div className="exercise-progress__metrics" aria-label="Ключевые показатели">
                <div className="metric">
                  <span>Лучший авторитетный вес</span>
                  <strong>
                    {formatLoad(data.best_authoritative_load?.value_kg ?? null, unit)}
                  </strong>
                  <small>
                    {data.best_authoritative_load
                      ? data.best_authoritative_load.workout.performed_on
                      : 'Только завершённые рабочие подходы'}
                  </small>
                </div>
                <div className="metric">
                  <span>Оценочный 1ПМ</span>
                  <strong>{formatLoad(data.estimated_1rm?.value_kg ?? null, unit)}</strong>
                  <small>
                    {data.estimated_1rm ? 'Оценка по формуле Бжицки' : 'Недостаточно данных'}
                  </small>
                </div>
                <div className="metric">
                  <span>Последний раз</span>
                  <strong>{data.last_performed?.performed_on ?? 'Нет данных'}</strong>
                  {data.last_performed && (
                    <AppLink to={workoutLink(data.last_performed.workout_id)}>
                      Открыть тренировку
                    </AppLink>
                  )}
                </div>
              </div>

              <section aria-labelledby="exercise-progress-windows">
                <h3 id="exercise-progress-windows">Контекст 7 / 30 / 90 дней</h3>
                <div className="exercise-progress__windows">
                  {data.windows.map((window) => (
                    <article className="exercise-progress__window" key={window.days}>
                      <strong>{window.days} дней</strong>
                      <span>{window.performed_session_count} сессий</span>
                      <span>{window.authoritative_set_count} авторитетных подходов</span>
                      <small>
                        {window.best_authoritative_load_kg == null
                          ? 'Вес не записан'
                          : `Лучший вес: ${formatLoad(window.best_authoritative_load_kg, unit)}`}
                      </small>
                    </article>
                  ))}
                </div>
              </section>

              {!!data.rep_prs.length && (
                <section aria-labelledby="exercise-progress-prs">
                  <h3 id="exercise-progress-prs">PR по диапазонам повторений</h3>
                  <div className="exercise-progress__prs">
                    {data.rep_prs.map((pr) => (
                      <article className="exercise-progress__pr" key={pr.range_key}>
                        <strong>{pr.range_label}</strong>
                        <span>Лучший результат: {pr.best_reps} повт.</span>
                        <span>
                          {pr.best_load_kg == null
                            ? 'Внешний вес не записан'
                            : `Лучший вес: ${formatLoad(pr.best_load_kg, unit)}`}
                        </span>
                        <AppLink to={workoutLink(pr.best_reps_workout.workout_id)}>
                          {pr.best_reps_workout.performed_on}
                        </AppLink>
                      </article>
                    ))}
                  </div>
                </section>
              )}

              <section aria-labelledby="exercise-progress-recent">
                <h3 id="exercise-progress-recent">Последние рабочие подходы</h3>
                {data.recent_sessions.length ? (
                  <div className="exercise-progress__sessions">
                    {data.recent_sessions.map((session) => (
                      <article
                        className="exercise-progress__session"
                        key={session.workout.workout_id}
                      >
                        <div>
                          <AppLink to={workoutLink(session.workout.workout_id)}>
                            {session.workout.performed_on} · {session.workout.workout_title}
                          </AppLink>
                          <small>
                            {session.authoritative_set_count} авторитетных из{' '}
                            {session.completed_set_count} рабочих подходов
                          </small>
                        </div>
                        <ul>
                          {session.sets.map((set) => (
                            <li key={set.set_number}>{setLabel(set, unit)}</li>
                          ))}
                        </ul>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="muted">
                    После завершённой тренировки здесь появятся фактические подходы.
                  </p>
                )}
              </section>

              {!!data.progression.length && (
                <section aria-labelledby="exercise-progress-timeline">
                  <h3 id="exercise-progress-timeline">Прогрессия по фактическим сессиям</h3>
                  <ol className="exercise-progress__timeline">
                    {data.progression.map((point) => (
                      <li key={`${point.workout_id}-${point.performed_on}`}>
                        <AppLink to={workoutLink(point.workout_id)}>{point.performed_on}</AppLink>
                        <span>
                          {point.max_authoritative_load_kg == null
                            ? 'Вес не записан'
                            : formatLoad(point.max_authoritative_load_kg, unit)}
                          {point.max_reps == null ? '' : ` · до ${point.max_reps} повт.`}
                        </span>
                      </li>
                    ))}
                  </ol>
                  {data.history_truncated && (
                    <p className="muted">
                      Показана последняя часть истории; факты не дорисовываются.
                    </p>
                  )}
                </section>
              )}

              <section aria-labelledby="exercise-progress-events">
                <h3 id="exercise-progress-events">Связь с предложениями прогрессии</h3>
                {data.progression_events.length ? (
                  <ul className="exercise-progress__events">
                    {data.progression_events.map((event) => (
                      <li key={event.event_id}>
                        <strong>{eventLabels[event.event_kind]}</strong>
                        <span>
                          {event.created_at.slice(0, 10)} · {eventReason(event)}
                          {event.proposed_weight_kg != null &&
                            ` · Предложено: ${formatLoad(event.proposed_weight_kg, unit)}`}
                          {event.adjusted_weight_kg != null &&
                            ` · Скорректировано: ${formatLoad(event.adjusted_weight_kg, unit)}`}
                        </span>
                        {event.target_workout_id && (
                          <AppLink to={workoutLink(event.target_workout_id)}>
                            Открыть связанную тренировку
                          </AppLink>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Сохранённых подтверждений или корректировок пока нет.</p>
                )}
              </section>
            </>
          )}
        </div>
      </details>
    </section>
  );
}
