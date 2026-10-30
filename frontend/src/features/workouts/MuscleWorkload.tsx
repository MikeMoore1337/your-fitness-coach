import { useId, useState, type CSSProperties } from 'react';
import type { TrainingAnalytics } from '../../shared/api/types';
import { formatCalendarDate } from '../../shared/dateTime';
import { DisclosureIcon, EmptyState } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import './MuscleWorkload.css';

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

type MuscleGroup = TrainingAnalytics['muscle_group_workload'][number];

function MuscleGroupDetail({ group, days, id }: { group: MuscleGroup; days: number; id: string }) {
  return (
    <section className="muscle-distribution__detail" id={id} aria-labelledby={`${id}-title`}>
      <p className="muscle-distribution__eyebrow">Выбранная группа</p>
      <h4 id={`${id}-title`}>{group.muscle_name}</h4>
      <p className="muscle-distribution__detail-meta">
        {group.current
          ? `${group.current.completed_session_count} ${plural(group.current.completed_session_count, 'тренировка', 'тренировки', 'тренировок')} · ${formatNumber(group.current.frequency_per_week, 2)} в неделю`
          : 'Нет данных за текущий период'}
      </p>
      <div className="muscle-distribution__comparison">
        {(
          [
            [`Текущие ${days} дней`, group.current],
            [`Предыдущие ${days} дней`, group.previous],
          ] as const
        ).map(([label, period]) => (
          <div key={label}>
            <small>{label}</small>
            <strong>
              {period ? formatNumber(period.completed_set_count, 0) : 'Нет данных'}
              {period && <span> подх.</span>}
            </strong>
            {period && (
              <p>
                Основное: {period.primary_completed_set_count}
                <br />
                Вспомогательное: {period.secondary_completed_set_count}
              </p>
            )}
          </div>
        ))}
      </div>
      <p className="muscle-distribution__delta">
        {group.completed_set_count_change == null
          ? 'Нет данных для сравнения'
          : `Изменение: ${group.completed_set_count_change > 0 ? '+' : ''}${group.completed_set_count_change} ${plural(group.completed_set_count_change, 'подход', 'подхода', 'подходов')}`}
      </p>
      <h5>Упражнения-источники</h5>
      {group.contributing_exercises.length ? (
        group.contributing_exercises.map((exercise) => (
          <details className="muscle-distribution__source" key={exercise.exercise_id}>
            <summary className="yfc-disclosure-summary">
              <span>
                <strong>{exercise.exercise_title}</strong>
                <span className="muscle-distribution__source-role">
                  {exercise.contribution_roles
                    .map((role) =>
                      role === 'primary' ? 'Основное участие' : 'Вспомогательное участие',
                    )
                    .join(' · ')}
                </span>
                <span className="muscle-distribution__source-values">
                  {exercise.completed_set_count}{' '}
                  {plural(exercise.completed_set_count, 'подход', 'подхода', 'подходов')} ·{' '}
                  {exercise.performed_session_count}{' '}
                  {plural(
                    exercise.performed_session_count,
                    'тренировка',
                    'тренировки',
                    'тренировок',
                  )}
                </span>
                {exercise.history_truncated && (
                  <span className="muscle-distribution__source-role">Показана часть истории</span>
                )}
              </span>
              <DisclosureIcon />
            </summary>
            {exercise.sessions.length ? (
              <ul>
                {exercise.sessions.map((session) => (
                  <li key={session.workout_exercise_id}>
                    {formatDate(session.performed_on)} · {session.completed_set_count}{' '}
                    {plural(session.completed_set_count, 'подход', 'подхода', 'подходов')}
                  </li>
                ))}
              </ul>
            ) : (
              <p>Сессии не записаны.</p>
            )}
          </details>
        ))
      ) : (
        <p className="muscle-distribution__detail-meta">
          В текущем периоде нет записей с этой группой.
        </p>
      )}
      <p className="muscle-distribution__footnote">
        Роли взяты из каталога упражнений. Частота относится к тренировкам с учтёнными подходами
        этой группы.
      </p>
    </section>
  );
}

export function MuscleWorkloadDistribution({ analytics }: { analytics: TrainingAnalytics }) {
  const id = useId();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const workload = analytics.muscle_group_workload ?? [];
  const selected = workload.find((group) => group.muscle_id === selectedId) ?? workload[0];
  const scale = Math.max(
    1,
    ...workload.flatMap((group) =>
      group.current
        ? [group.current.primary_completed_set_count, group.current.secondary_completed_set_count]
        : [],
    ),
  );
  const unmapped = analytics.completed_sets_without_muscle_metadata ?? 0;
  return (
    <section className="muscle-distribution" aria-labelledby={`${id}-heading`}>
      <div className="muscle-distribution__heading">
        <div>
          <p className="muscle-distribution__eyebrow">По записям упражнений</p>
          <h3 id={`${id}-heading`}>Мышечные группы</h3>
        </div>
        <span className="muscle-distribution__unit">Единица: подходы</span>
      </div>
      <p className="muscle-distribution__intro">
        Один подход может участвовать в нескольких группах. Значения групп не складываются в общее
        число подходов.
      </p>
      {unmapped > 0 && (
        <div className="muscle-distribution__notice">
          <Icon name="info" size={20} />
          <div>
            <strong>Неполные сведения о мышцах</strong>
            {unmapped} {plural(unmapped, 'подход', 'подхода', 'подходов')} без мышечных связей. Они
            входят в общее число подходов, но не распределены по группам.
          </div>
        </div>
      )}
      {selected ? (
        <>
          <div className="muscle-distribution__legend" aria-label="Обозначения">
            <span>
              <i className="muscle-distribution__primary" aria-hidden="true" />
              Основное участие
            </span>
            <span>
              <i className="muscle-distribution__secondary" aria-hidden="true" />
              Вспомогательное
            </span>
          </div>
          <p className="muscle-distribution__caption">
            Группы по числу подходов. Обе полосы используют одну шкалу.
          </p>
          <div
            className="muscle-distribution__layout"
            style={{ '--muscle-group-count': workload.length } as CSSProperties}
          >
            {workload.map((group) => (
              <div className="muscle-distribution__row" key={group.muscle_id}>
                <div className="muscle-distribution__choice">
                  <button
                    type="button"
                    className="muscle-distribution__button"
                    data-yfc-choice="compact"
                    aria-pressed={group === selected}
                    aria-controls={`${id}-detail`}
                    onClick={() => setSelectedId(group.muscle_id)}
                  >
                    <span className="muscle-distribution__group-heading">
                      <span className="muscle-distribution__name">{group.muscle_name}</span>
                      <span className="muscle-distribution__total">
                        {group.current
                          ? `Всего ${group.current.completed_set_count}`
                          : 'Нет данных'}
                      </span>
                    </span>
                    {group.current ? (
                      (
                        [
                          ['Основное', group.current.primary_completed_set_count, 'primary'],
                          [
                            'Вспомогательное',
                            group.current.secondary_completed_set_count,
                            'secondary',
                          ],
                        ] as const
                      ).map(([label, value, role]) => (
                        <span className="muscle-distribution__role" key={role}>
                          <span>{label}</span>
                          <span className="muscle-distribution__track" aria-hidden="true">
                            {value > 0 && (
                              <i
                                className={`muscle-distribution__${role}`}
                                style={{ width: `${(value / scale) * 100}%` }}
                              />
                            )}
                          </span>
                          <b>{value}</b>
                        </span>
                      ))
                    ) : (
                      <span className="muscle-distribution__null">
                        Нет записей с этой группой за период
                      </span>
                    )}
                    <span className="muscle-distribution__row-meta">
                      <span>
                        {group.current
                          ? `${group.current.completed_session_count} ${plural(group.current.completed_session_count, 'тренировка', 'тренировки', 'тренировок')} · ${formatNumber(group.current.frequency_per_week, 2)} / нед.`
                          : group.previous
                            ? `Ранее: ${group.previous.completed_set_count} подх.`
                            : 'Нет данных'}
                      </span>
                      <span className="muscle-distribution__open-label">
                        {group === selected ? 'Выбрана' : 'Подробнее'}
                        {group !== selected && <Icon name="chevron-right" size={16} />}
                      </span>
                    </span>
                  </button>
                </div>
                {group === selected && (
                  <MuscleGroupDetail
                    group={group}
                    days={analytics.period_days}
                    id={`${id}-detail`}
                  />
                )}
              </div>
            ))}
          </div>
          <span className="sr-only" aria-live="polite" aria-atomic="true">
            Выбрана группа: {selected.muscle_name}
          </span>
        </>
      ) : (
        <EmptyState
          title={
            analytics.completed_set_count > 0
              ? 'Распределение пока недоступно'
              : 'Нет записанных подходов'
          }
          text={
            analytics.completed_set_count > 0
              ? 'Подходы записаны, но у упражнений нет сведений о мышцах. Отсутствие связей не означает, что мышцы не участвовали.'
              : 'За выбранный период нет записанных завершённых рабочих подходов. Здесь появятся группы и упражнения из вашего журнала.'
          }
        />
      )}
    </section>
  );
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
          <summary className="yfc-disclosure-summary">
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
                        <summary className="yfc-disclosure-summary">
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
