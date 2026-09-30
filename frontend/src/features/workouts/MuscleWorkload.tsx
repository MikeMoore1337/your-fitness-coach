import type { TrainingAnalytics } from '../../shared/api/types';
import { formatCalendarDate } from '../../shared/dateTime';
import { DisclosureIcon, EmptyState } from '../../shared/ui/common';

function formatNumber(value: number, maximumFractionDigits = 1): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits }).format(value);
}

function formatDate(value: string): string {
  return formatCalendarDate(value, { day: 'numeric', month: 'short', year: 'numeric' });
}

function plural(value: number, one: string, few: string, many: string): string {
  const absolute = Math.abs(value) % 100;
  const last = absolute % 10;
  if (absolute > 10 && absolute < 20) return many;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}

function periodSummary(
  period: TrainingAnalytics['muscle_group_workload'][number]['current'],
): string {
  if (!period) return 'Нет данных за этот период';
  return `${period.completed_set_count} подх. · ${formatNumber(period.frequency_per_week, 2)} в неделю`;
}

function trendLabel(item: TrainingAnalytics['muscle_group_workload'][number]): string {
  if (item.trend === 'no_comparable_data') return 'Нет сравнения';
  if (item.trend === 'unchanged') return 'Без изменения';
  const change = item.completed_set_count_change ?? 0;
  return `${change > 0 ? '+' : ''}${change} подх.`;
}

function roleLabel(role: 'primary' | 'secondary'): string {
  return role === 'primary' ? 'основное' : 'дополнительное';
}

export function MuscleWorkloadList({ analytics }: { analytics: TrainingAnalytics }) {
  const workload = analytics.muscle_group_workload ?? [];
  if (!workload.length) {
    return (
      <EmptyState
        title="Распределение по мышцам пока не определено"
        text="Для этой истории нет завершённых подходов с каталогом мышечных связей."
      />
    );
  }
  return (
    <div className="progress-muscle-workload" aria-label="Нагрузка по мышечным группам">
      {workload.map((item) => (
        <details className="progress-exercise" key={item.muscle_id}>
          <summary>
            <span>
              <strong>{item.muscle_name}</strong>
              <small>{periodSummary(item.current)}</small>
            </span>
            <span className="progress-exercise__best">{trendLabel(item)}</span>
            <DisclosureIcon />
          </summary>
          <div className="progress-workload__body">
            <div className="progress-workload__comparison">
              <div>
                <small>Текущий период</small>
                <strong>{periodSummary(item.current)}</strong>
                {item.current && (
                  <span>
                    Основные: {item.current.primary_completed_set_count} · дополнительные:{' '}
                    {item.current.secondary_completed_set_count}
                  </span>
                )}
              </div>
              <div>
                <small>Предыдущий период</small>
                <strong>{periodSummary(item.previous)}</strong>
              </div>
            </div>
            {item.contributing_exercises.length ? (
              <div className="progress-workload__contributors">
                <strong>Упражнения и тренировки</strong>
                <ul>
                  {item.contributing_exercises.map((exercise) => (
                    <li key={exercise.exercise_id}>
                      <details className="progress-workload__exercise">
                        <summary>
                          <span>
                            {exercise.exercise_title} ·{' '}
                            {exercise.contribution_roles.map(roleLabel).join(', ')}
                          </span>
                          <DisclosureIcon />
                        </summary>
                        <div>
                          <small>
                            {exercise.completed_set_count} подх. ·{' '}
                            {exercise.performed_session_count}{' '}
                            {plural(
                              exercise.performed_session_count,
                              'тренировка',
                              'тренировки',
                              'тренировок',
                            )}
                            {exercise.history_truncated ? ' · показана не вся история' : ''}
                          </small>
                          {exercise.sessions.length ? (
                            <ul>
                              {exercise.sessions.map((session) => (
                                <li key={session.workout_exercise_id}>
                                  {formatDate(session.performed_on)} · {session.completed_set_count}{' '}
                                  {plural(
                                    session.completed_set_count,
                                    'подход',
                                    'подхода',
                                    'подходов',
                                  )}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <span>Сессии не записаны.</span>
                          )}
                        </div>
                      </details>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="progress-note">В текущем периоде нет упражнения для раскрытия.</p>
            )}
          </div>
        </details>
      ))}
    </div>
  );
}
