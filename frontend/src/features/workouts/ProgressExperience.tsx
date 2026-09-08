import { useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { ApiSchemas, ProgressSummary, TrainingAnalytics } from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { AppLink, useNavigation } from '../../shared/navigation/router';
import { ContextualHelp } from '../../shared/ui/ContextualHelp';
import { DataConfidence } from '../../shared/ui/DataConfidence';
import { QuantitativeProgress, RankedBars, TimeSeriesChart } from '../../shared/ui/DataViz';
import { dateInputValue, detectedTimeZone, formatCalendarDate } from '../../shared/dateTime';
import {
  Badge,
  Button,
  DisclosureIcon,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  SegmentedControl,
  SemanticArtwork,
} from '../../shared/ui/common';
import { NutritionPeriodReport, type ControlledNutritionPeriod } from './NutritionReport';
import { Icon } from '../../shared/ui/Icon';
import { AiCoachEntry } from '../ai/AiCoachExperience';
import { CardioHistory } from '../cardio/CardioLogging';
import {
  nutritionPeriodForProgress,
  parseProgressSelection,
  progressApiQuery,
  progressPath,
  progressPeriodOptions,
  progressReportPath,
  progressSelectionKey,
  selectionDateRange,
  validateCustomProgressRange,
  type ProgressSelection,
} from './progressPeriods';

type BodyTrend = ProgressSummary['body']['trends'][number];
type AdherenceComponent = ProgressSummary['adherence']['workouts'];

const bodyMetricLabels: Record<BodyTrend['metric'], string> = {
  weight_kg: 'Вес',
  chest_cm: 'Грудь',
  waist_cm: 'Талия',
  hips_cm: 'Бёдра',
  biceps_cm: 'Окружность плеча',
  thigh_cm: 'Окружность бедра',
};

const bodyMetricUnits: Record<BodyTrend['metric'], string> = {
  weight_kg: 'кг',
  chest_cm: 'см',
  waist_cm: 'см',
  hips_cm: 'см',
  biceps_cm: 'см',
  thigh_cm: 'см',
};

function formatNumber(value: number, maximumFractionDigits = 1): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits }).format(value);
}

function formatDate(value: string, withYear = false): string {
  return formatCalendarDate(value, {
    day: 'numeric',
    month: 'short',
    ...(withYear ? { year: 'numeric' } : {}),
  });
}

function formatChange(change: number | null | undefined, unit: string): string {
  if (change == null) return 'Пока без динамики';
  const sign = change > 0 ? '+' : '';
  return `${sign}${formatNumber(change)} ${unit}`;
}

function trendInterpretationText(
  trend: BodyTrend,
  guidance: ProgressSummary['body']['guidance'],
): string | null {
  if (trend.interpretation_status === 'available') return null;
  if (trend.interpretation_status === 'single_point') {
    return 'Одна точка сохраняет факт, но ещё не показывает направление изменений.';
  }
  if (trend.interpretation_status === 'insufficient_points') {
    return `Нужно минимум ${guidance.minimum_points_for_interpretation} замера: разовое изменение не считаем трендом.`;
  }
  return `Точек достаточно, но период короче ${guidance.minimum_span_days_for_interpretation} дней — вывод пока преждевременный.`;
}

function plural(value: number, one: string, few: string, many: string): string {
  const absolute = Math.abs(value) % 100;
  const last = absolute % 10;
  if (absolute > 10 && absolute < 20) return many;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}

function SectionHeading({
  description,
  eyebrow,
  title,
  titleId,
  trailing,
}: {
  description: string;
  eyebrow: string;
  title: string;
  titleId: string;
  trailing?: ReactNode;
}) {
  return (
    <header className="progress-section__head">
      <div>
        <span className="progress-section__eyebrow">{eyebrow}</span>
        <h2 id={titleId}>{title}</h2>
        <p>{description}</p>
      </div>
      {trailing}
    </header>
  );
}

function periodDateLabel(start: string, end: string): string {
  return start === end
    ? formatDate(start, true)
    : `${formatDate(start, true)} — ${formatDate(end, true)}`;
}

function ProgressBentoMetric({
  detail,
  label,
  value,
}: {
  detail: string;
  label: string;
  value: string;
}) {
  return (
    <div className="progress-bento__metric">
      <dt>{label}</dt>
      <dd>{value}</dd>
      <small>{detail}</small>
    </div>
  );
}

function LatestMeasurementPoints({ summary }: { summary: ProgressSummary }) {
  const trend =
    summary.body.trends.find((item) => item.metric === 'weight_kg') ?? summary.body.trends[0];
  const points = trend?.points.slice(-4).reverse() ?? [];
  return (
    <article className="progress-bento__journal">
      <div className="progress-bento__journal-head">
        <div>
          <span className="progress-bento__eyebrow">Последние факты</span>
          <h3>Журнал замеров</h3>
        </div>
        <span className="progress-bento__journal-count">
          {points.length ? `${points.length} точек` : 'Нет точек'}
        </span>
      </div>
      {points.length ? (
        <ul aria-label="Последние замеры за выбранный период">
          {points.map((point) => (
            <li key={point.measured_on}>
              <span>{formatDate(point.measured_on, true)}</span>
              <strong>
                {formatNumber(point.value)} {bodyMetricUnits[trend?.metric ?? 'weight_kg']}
              </strong>
            </li>
          ))}
        </ul>
      ) : (
        <p className="progress-note">
          Добавьте фактический замер, чтобы увидеть первую точку истории. Одна точка ещё не образует
          тренд.
        </p>
      )}
    </article>
  );
}

function SummaryOverview({ summary }: { summary: ProgressSummary }) {
  const weight = summary.body.trends.find((trend) => trend.metric === 'weight_kg');
  const confirmedNutritionDays = summary.nutrition.complete_days + summary.nutrition.fasted_days;
  const latestWeight = weight ? `${formatNumber(weight.latest_value)} кг` : 'Нет данных';
  return (
    <section
      className="progress-summary progress-bento semantic-card semantic-card--summary semantic-card--progress"
      data-card-variant="summary"
      data-semantic-family="progress"
      aria-labelledby="progress-overview-title"
    >
      <div className="progress-bento__context">
        <div>
          <span className="progress-bento__eyebrow">Сводка выбранного периода</span>
          <h2 id="progress-overview-title">Прогресс по фактам</h2>
          <p>
            {periodDateLabel(summary.period_start, summary.period_end)}. Показаны только записи,
            попавшие в этот диапазон.
          </p>
        </div>
        <Badge>{summary.period_days} дн.</Badge>
      </div>
      <div className="progress-bento__grid">
        <article className="progress-bento__adherence">
          <span className="progress-bento__eyebrow">Ритм плана</span>
          <strong className="progress-summary__score">
            {summary.adherence.overall_percent == null
              ? 'Пока не оценить'
              : `${formatNumber(summary.adherence.overall_percent)}%`}
          </strong>
          <p>
            {summary.adherence.overall_percent == null
              ? 'Появится, когда за период будет что сравнивать с планом.'
              : 'Расчёт учитывает только доступные компоненты плана.'}
          </p>
        </article>
        <article className="progress-bento__trend">
          <div className="progress-bento__trend-head">
            <div>
              <span className="progress-bento__eyebrow">Главная динамика</span>
              <h3>{weight ? 'Вес' : 'Замеры тела'}</h3>
            </div>
            {weight && (
              <strong>
                {latestWeight}
                <small>{formatChange(weight.change, 'кг')}</small>
              </strong>
            )}
          </div>
          {weight ? (
            <>
              <BodyChart trend={weight} />
              <DataConfidence kind="weight" signal={summary.data_sufficiency.weight_trend} />
            </>
          ) : (
            <EmptyState
              title="Недостаточно точек для динамики"
              text="Добавьте замеры тела: первая запись сохранит факт, но не станет трендом сама по себе."
            />
          )}
        </article>
        <dl className="progress-bento__metrics" aria-label="Факты за выбранный период">
          <ProgressBentoMetric
            detail={`${summary.training.planned_workouts} запланировано`}
            label="Тренировки"
            value={`${summary.training.completed_workouts} из ${summary.training.planned_workouts}`}
          />
          <ProgressBentoMetric
            detail={
              summary.nutrition.visible
                ? `${summary.nutrition.incomplete_days} частичных, не входят в средние`
                : 'Доступ закрыт для этой роли'
            }
            label="Питание"
            value={summary.nutrition.visible ? `${confirmedNutritionDays} дней` : 'Недоступно'}
          />
          <ProgressBentoMetric
            detail={`${summary.cardio.duration_minutes} мин фактической длительности`}
            label="Кардио"
            value={`${summary.cardio.completed_sessions} сессий`}
          />
          <ProgressBentoMetric
            detail={weight ? `${weight.point_count} точек веса в периоде` : 'Нет фактических точек'}
            label="Замеры"
            value={latestWeight}
          />
        </dl>
        <LatestMeasurementPoints summary={summary} />
      </div>
    </section>
  );
}

function TrainingFacts({
  summary,
  analytics,
}: {
  summary?: ProgressSummary;
  analytics: TrainingAnalytics;
}) {
  return (
    <dl className="progress-fact-strip" aria-label="Итоги тренировок">
      <div>
        <dt>Рабочих подходов</dt>
        <dd>{analytics.completed_set_count}</dd>
      </div>
      <div>
        <dt>Частота</dt>
        <dd>
          {summary ? `${formatNumber(summary.training.frequency_per_week, 2)} в неделю` : '—'}
        </dd>
      </div>
      <div>
        <dt>Внешняя нагрузка</dt>
        <dd>
          {analytics.external_load_volume_kg == null
            ? 'Нет данных'
            : `${formatNumber(analytics.external_load_volume_kg, 0)} кг`}
        </dd>
      </div>
      <div>
        <dt>Повторов записано</dt>
        <dd>
          {analytics.reps_total == null ? 'Нет данных' : formatNumber(analytics.reps_total, 0)}
        </dd>
      </div>
    </dl>
  );
}

function SetValue({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <span>
      <small>{label}</small>
      <strong>{value ?? '—'}</strong>
    </span>
  );
}

function ExerciseHistory({ analytics }: { analytics: TrainingAnalytics }) {
  if (!analytics.exercises.length) {
    return (
      <EmptyState
        title="История упражнений пока пуста"
        text="Завершите тренировку и отметьте рабочие подходы — здесь появится фактическая динамика."
      />
    );
  }
  return (
    <div className="progress-exercises">
      {analytics.exercises.map((exercise) => (
        <details className="progress-exercise" key={exercise.exercise_id}>
          <summary>
            <span>
              <strong>{exercise.exercise_title}</strong>
              <small>
                {exercise.performed_session_count}{' '}
                {plural(exercise.performed_session_count, 'тренировка', 'тренировки', 'тренировок')}{' '}
                · {exercise.completed_set_count}{' '}
                {plural(
                  exercise.completed_set_count,
                  'рабочий подход',
                  'рабочих подхода',
                  'рабочих подходов',
                )}
              </small>
            </span>
            <span className="progress-exercise__best">
              {exercise.max_external_load_kg == null
                ? exercise.uses_bodyweight_equipment
                  ? 'Собственный вес'
                  : 'Вес не записан'
                : `до ${formatNumber(exercise.max_external_load_kg)} кг`}
            </span>
            <DisclosureIcon />
          </summary>
          <div className="progress-exercise__sessions">
            {exercise.sessions.map((session) => (
              <article className="progress-session" key={session.workout_exercise_id}>
                <header>
                  <div>
                    <strong>{formatDate(session.performed_on, true)}</strong>
                    <small>
                      {session.completed_set_count}{' '}
                      {plural(
                        session.completed_set_count,
                        'рабочий подход',
                        'рабочих подхода',
                        'рабочих подходов',
                      )}
                      {session.external_load_volume_kg == null
                        ? ''
                        : ` · ${formatNumber(session.external_load_volume_kg, 0)} кг внешней нагрузки`}
                    </small>
                  </div>
                  <Badge>Детали тренировки</Badge>
                </header>
                <div
                  className="progress-session__sets"
                  aria-label={`Подходы ${exercise.exercise_title}`}
                >
                  {session.sets.map((set) => (
                    <div className="progress-set" key={set.set_number}>
                      <b>{set.set_number}</b>
                      <SetValue
                        label="Вес"
                        value={
                          set.external_load_kg == null
                            ? '—'
                            : `${formatNumber(set.external_load_kg)} кг`
                        }
                      />
                      <SetValue label="Повторы" value={set.reps} />
                      <SetValue label="Повторы в запасе" value={set.rir} />
                    </div>
                  ))}
                </div>
              </article>
            ))}
            {exercise.history_truncated && (
              <p className="progress-note">
                Показаны последние {analytics.exercise_history_limit} тренировок упражнения.
              </p>
            )}
          </div>
        </details>
      ))}
    </div>
  );
}

function ExposureList({
  items,
  title,
}: {
  items: TrainingAnalytics['primary_muscle_exposure'];
  title: string;
}) {
  const visible = items.slice(0, 8);
  return (
    <div className="progress-exposure">
      <h3>{title}</h3>
      {!visible.length ? (
        <p className="progress-note">Нет структурированных данных по мышечным группам.</p>
      ) : (
        <RankedBars
          items={visible.map((item) => ({
            label: item.muscle_name,
            unit: 'подх.',
            value: item.completed_set_count,
          }))}
          label={title}
        />
      )}
    </div>
  );
}

function TrainingSection({
  analytics,
  summary,
}: {
  analytics: ReturnType<typeof useTrainingAnalytics>;
  summary?: ProgressSummary;
}) {
  return (
    <section
      className="progress-section"
      id="progress-training"
      aria-labelledby="progress-training-title"
    >
      <SectionHeading
        eyebrow="Нагрузка"
        title="Тренировки"
        titleId="progress-training-title"
        description="Фактические подходы, нагрузка и история упражнений — без расчётных коэффициентов."
        trailing={
          summary && (
            <Badge>
              {summary.training.new_personal_records}{' '}
              {plural(
                summary.training.new_personal_records,
                'новый рекорд',
                'новых рекорда',
                'новых рекордов',
              )}
            </Badge>
          )
        }
      />
      {analytics.isLoading ? (
        <LoadingState label="Собираем историю тренировок…" />
      ) : analytics.error ? (
        <ErrorState
          message={(analytics.error as Error).message}
          retry={() => void analytics.refetch()}
        />
      ) : analytics.data ? (
        <>
          <TrainingFacts analytics={analytics.data} summary={summary} />
          <DataConfidence
            isStale={analytics.isPlaceholderData}
            kind="training"
            signal={analytics.data.data_sufficiency.working_sets}
            action={<AppLink to="/app?section=today">Открыть тренировку</AppLink>}
          />
          <div className="progress-subsection">
            <div className="progress-subsection__head">
              <div>
                <h3>История упражнений</h3>
                <p>Раскройте упражнение, чтобы увидеть тренировки и записанные подходы.</p>
              </div>
              <a href="#progress-methodology">Как читать данные</a>
            </div>
            <ExerciseHistory analytics={analytics.data} />
          </div>
          <div className="progress-training-details">
            <ExposureList
              title="Основные мышечные группы"
              items={analytics.data.primary_muscle_exposure}
            />
            <ExposureList
              title="Дополнительные мышечные группы"
              items={analytics.data.secondary_muscle_exposure}
            />
          </div>
          <details className="progress-methodology" id="progress-methodology">
            <summary>Как читать тренировочные показатели</summary>
            <div>
              <p>
                Внешняя нагрузка учитывается только там, где записаны и вес, и повторы. Для
                упражнений с собственным весом она не описывает всю выполненную работу.
              </p>
              <p>
                Подход отдельно учитывается для каждой явно связанной основной и дополнительной
                мышечной группы. Эти значения не складываются в «эффективные подходы».
              </p>
              <p>
                Повторы в запасе необязательны и не используются для вывода об усталости или
                восстановлении.
              </p>
            </div>
          </details>
        </>
      ) : null}
    </section>
  );
}

function BodyChart({ trend }: { trend: BodyTrend }) {
  const unit = bodyMetricUnits[trend.metric];
  return (
    <TimeSeriesChart
      ariaLabel={`${bodyMetricLabels[trend.metric]}: ${trend.points
        .map((point) => `${formatDate(point.measured_on)} — ${formatNumber(point.value)} ${unit}`)
        .join(', ')}`}
      metric={bodyMetricLabels[trend.metric]}
      period={`${formatDate(trend.first_measured_on)} — ${formatDate(trend.latest_measured_on)}`}
      points={trend.points.map((point) => ({
        key: point.measured_on,
        label: formatDate(point.measured_on),
        value: point.value,
      }))}
      unit={unit}
      valueLabel="Замер"
    />
  );
}

function BodySection({
  isStale,
  measurementDiary,
  summary,
  weightChartInOverview = false,
}: {
  isStale?: boolean;
  measurementDiary?: ReactNode;
  summary: ProgressSummary;
  weightChartInOverview?: boolean;
}) {
  const { body } = summary;
  const priorityOptions = useQuery({
    queryKey: ['body-priority-options'],
    queryFn: () =>
      api<ApiSchemas['BodyPriorityOptionsResponse']>('/api/v1/me/profile/body-priority-options'),
    enabled: body.priority?.mode === 'muscle_groups',
    staleTime: Number.POSITIVE_INFINITY,
  });
  const priorityNames =
    body.priority?.mode === 'muscle_groups'
      ? (body.priority.muscle_group_ids ?? [])
          .map((id) => priorityOptions.data?.items.find((option) => option.id === id)?.name)
          .filter((name): name is string => Boolean(name))
      : [];
  const hasGuidance =
    body.guidance.consistency_tips.length > 0 || body.guidance.circumference_limitations.length > 0;
  return (
    <section className="progress-section" id="progress-body" aria-labelledby="progress-body-title">
      <SectionHeading
        eyebrow="Замеры"
        title="Замеры и приоритеты"
        titleId="progress-body-title"
        description="Фактические значения по датам и выбранный контекст развития — без идеальных пропорций и оценки тела."
        trailing={
          body.latest_measurement && (
            <Badge>Последний замер {formatDate(body.latest_measurement.measured_on)}</Badge>
          )
        }
      />
      <div
        className={`progress-priority${body.priority ? ' is-selected' : ' is-empty'}`}
        aria-label="Выбранный приоритет развития"
      >
        <div>
          <span>Приоритет развития</span>
          <strong>
            {!body.priority
              ? 'Не выбран'
              : body.priority.mode === 'balanced'
                ? 'Сбалансированное развитие'
                : 'Выбранные мышечные группы'}
          </strong>
        </div>
        {body.priority?.mode === 'muscle_groups' &&
          (priorityOptions.isLoading ? (
            <p role="status">Загружаем названия выбранных групп…</p>
          ) : priorityOptions.error ? (
            <p role="alert">
              Не удалось загрузить названия групп. Выбрано:{' '}
              {body.priority.muscle_group_ids?.length ?? 0}.
            </p>
          ) : (
            <ul>
              {priorityNames.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          ))}
        <p>
          {body.priority
            ? 'Это предпочтение для планирования. Оно не оценивает тело и не объясняет изменение окружностей.'
            : 'Можно оставить развитие без отдельного акцента или выбрать предпочтения в профиле.'}
        </p>
        <AppLink to="/app?section=profile#profile-fitness">
          {body.priority ? 'Изменить в профиле' : 'Выбрать в профиле'}
        </AppLink>
      </div>
      <div className="progress-body-flow">
        {measurementDiary && <div className="progress-body-diary">{measurementDiary}</div>}
        <div className="progress-body-trends" aria-label="Динамика замеров">
          <div className="progress-confidence-grid">
            <DataConfidence
              isStale={isStale}
              kind="weight"
              signal={summary.data_sufficiency.weight_trend}
              action={
                measurementDiary ? <a href="#measurement-diary">Добавить замер</a> : undefined
              }
            />
            <DataConfidence
              isStale={isStale}
              kind="anthropometry"
              signal={summary.data_sufficiency.anthropometry}
              action={
                measurementDiary &&
                summary.data_sufficiency.weight_trend.status === 'sufficient' ? (
                  <a href="#measurement-diary">Добавить замер</a>
                ) : undefined
              }
            />
          </div>
          {!body.trends.length ? (
            <EmptyState
              title="Замеров за этот период нет"
              text="Добавьте вес или окружности — первая точка начнёт историю, но ещё не станет трендом."
            />
          ) : (
            <>
              <div className="progress-body-grid">
                {body.trends.map((trend) => {
                  const unit = bodyMetricUnits[trend.metric];
                  const interpretation = trendInterpretationText(trend, body.guidance);
                  return (
                    <article
                      className={`progress-body-metric${trend.metric === 'weight_kg' ? ' progress-body-metric--data-insight' : ''}`}
                      key={trend.metric}
                    >
                      {trend.metric === 'weight_kg' && <SemanticArtwork variant="data-insight" />}
                      <header>
                        <div>
                          <span className="progress-body-metric__kind">
                            {trend.metric === 'weight_kg' ? 'Масса тела' : 'Окружность'}
                          </span>
                          <h3>{bodyMetricLabels[trend.metric]}</h3>
                          <p>
                            {trend.point_count === 1
                              ? `1 точка · ${formatDate(trend.latest_measured_on, true)}`
                              : `${trend.point_count} ${plural(trend.point_count, 'точка', 'точки', 'точек')} · ${trend.span_days} ${plural(trend.span_days, 'день', 'дня', 'дней')}`}
                          </p>
                        </div>
                        <div className="progress-body-metric__value">
                          <strong>
                            {formatNumber(trend.latest_value)} {unit}
                          </strong>
                          <span>{formatChange(trend.change, unit)}</span>
                        </div>
                      </header>
                      {weightChartInOverview && trend.metric === 'weight_kg' ? (
                        <p className="progress-note">
                          График веса вынесен в сводку выбранного периода.
                        </p>
                      ) : (
                        <BodyChart trend={trend} />
                      )}
                      {interpretation && <p className="progress-note">{interpretation}</p>}
                    </article>
                  );
                })}
              </div>
            </>
          )}
          {hasGuidance && (
            <details className="progress-body-guidance">
              <summary>Как сравнивать замеры</summary>
              <div>
                {body.guidance.consistency_tips.length > 0 && (
                  <ul>
                    {body.guidance.consistency_tips.map((tip) => (
                      <li key={tip}>{tip}</li>
                    ))}
                  </ul>
                )}
                {body.guidance.circumference_limitations.map((limitation) => (
                  <p key={limitation}>{limitation}</p>
                ))}
              </div>
            </details>
          )}
          <ContextualHelp articlePath="/knowledge/progress/how-to-read-progress">
            <p>
              Сравнивайте значения только с собственной историей. Окружность участка тела не
              показывает рост отдельной мышцы.
            </p>
          </ContextualHelp>
        </div>
      </div>
    </section>
  );
}

function NutritionSection({ isStale, summary }: { isStale?: boolean; summary: ProgressSummary }) {
  const { nutrition, adherence } = summary;
  return (
    <section
      className="progress-section"
      id="progress-nutrition"
      aria-labelledby="progress-nutrition-title"
    >
      <SectionHeading
        eyebrow="Средние значения"
        title="Питание"
        titleId="progress-nutrition-title"
        description="Средние значения по заполненным прошлым дням и сравнение с действующей целью."
      />
      {!nutrition.visible ? (
        <>
          <DataConfidence
            isStale={isStale}
            kind="nutrition"
            signal={summary.data_sufficiency.nutrition_coverage}
          />
          <EmptyState title="Данные питания недоступны" />
        </>
      ) : nutrition.complete_days + nutrition.fasted_days === 0 ? (
        <>
          <DataConfidence
            isStale={isStale}
            kind="nutrition"
            signal={summary.data_sufficiency.nutrition_coverage}
            action={<AppLink to="/app?section=nutrition">Заполнить дневник</AppLink>}
          />
          <EmptyState
            title="Нет подтверждённых дней питания"
            text={`${nutrition.incomplete_days} частичных и ${nutrition.unlogged_days} отсутствующих дней не входят в средние значения.`}
          />
        </>
      ) : (
        <>
          <div className="progress-nutrition-summary">
            <div>
              <span>В среднем за день</span>
              <strong>
                {nutrition.average_calories == null
                  ? '—'
                  : `${formatNumber(nutrition.average_calories, 0)} ккал`}
              </strong>
              <small>
                {nutrition.target_calories == null
                  ? 'Цель не задана'
                  : `цель ${formatNumber(nutrition.target_calories, 0)} ккал`}
              </small>
            </div>
            <div>
              <span>Белок в среднем</span>
              <strong>
                {nutrition.average_protein_g == null
                  ? '—'
                  : `${formatNumber(nutrition.average_protein_g, 0)} г`}
              </strong>
              <small>
                {nutrition.target_protein_g == null
                  ? 'Цель не задана'
                  : `цель ${formatNumber(nutrition.target_protein_g, 0)} г`}
              </small>
            </div>
            <div>
              <span>Подтверждено</span>
              <strong>{nutrition.complete_days + nutrition.fasted_days} дней</strong>
              <small>
                {nutrition.incomplete_days} частичных · {nutrition.unlogged_days} без записей
              </small>
            </div>
          </div>
          <div className="progress-nutrition-compliance">
            <ComplianceRow label="Калории в диапазоне цели" component={adherence.calories} />
            <ComplianceRow label="Цель по белку достигнута" component={adherence.protein} />
          </div>
          <DataConfidence
            isStale={isStale}
            kind="nutrition"
            signal={summary.data_sufficiency.nutrition_coverage}
            action={<AppLink to="/app?section=nutrition">Дополнить дневник</AppLink>}
          />
        </>
      )}
    </section>
  );
}

function componentStatus(component: AdherenceComponent): string {
  if (component.status === 'unsupported') return 'Пока нельзя оценить';
  if (component.status === 'not_applicable') return 'Нет цели или плана';
  if (component.status === 'insufficient_data') return 'Мало данных';
  return component.percent == null ? 'Мало данных' : `${formatNumber(component.percent)}%`;
}

function ComplianceRow({ label, component }: { label: string; component: AdherenceComponent }) {
  const percent = component.percent;
  return (
    <div className="progress-compliance">
      {percent != null && (
        <QuantitativeProgress label={label} maximum={100} unit="%" value={percent} />
      )}
      {percent == null && (
        <div>
          <span>{label}</span>
          <strong>{componentStatus(component)}</strong>
        </div>
      )}
      {component.status === 'available' && (
        <small>
          {component.achieved} из {component.evaluated} учтённых дней или тренировок
        </small>
      )}
    </div>
  );
}

function AdherenceSection({ summary }: { summary: ProgressSummary }) {
  const rows: Array<{ label: string; component: AdherenceComponent }> = [
    { label: 'Запланированные тренировки', component: summary.adherence.workouts },
    { label: 'Калории', component: summary.adherence.calories },
    { label: 'Белок', component: summary.adherence.protein },
    { label: 'Кардио', component: summary.adherence.cardio },
  ];
  return (
    <section
      className="progress-section progress-adherence"
      id="progress-adherence"
      aria-labelledby="progress-adherence-title"
    >
      <SectionHeading
        eyebrow="Ритм"
        title="Соблюдение плана"
        titleId="progress-adherence-title"
        description="Готовая серверная оценка: отсутствующие компоненты не превращаются в ноль."
        trailing={
          <strong className="progress-adherence__score">
            {summary.adherence.overall_percent == null
              ? '—'
              : `${formatNumber(summary.adherence.overall_percent)}%`}
          </strong>
        }
      />
      <div className="progress-adherence__rows">
        {rows.map((row) => (
          <ComplianceRow key={row.label} {...row} />
        ))}
      </div>
      <p className="progress-note">
        Текущий день питания не учитывается: его ещё можно дополнить. Кардио сравнивается с
        действовавшей недельной целью только по завершённым ручным записям.
      </p>
    </section>
  );
}

function ProgressPeriodControls({
  onSelectPreset,
  onApplyCustom,
  selection,
  timeZone,
  today,
}: {
  onApplyCustom: (selection: Extract<ProgressSelection, { kind: 'custom' }>) => void;
  onSelectPreset: (days: 7 | 30 | 90) => void;
  selection: ProgressSelection;
  timeZone: string;
  today: string;
}) {
  const initialRange = selectionDateRange(selection, today);
  const [customOpen, setCustomOpen] = useState(false);
  const [customDateFrom, setCustomDateFrom] = useState(initialRange.dateFrom);
  const [customDateTo, setCustomDateTo] = useState(initialRange.dateTo);
  const [customError, setCustomError] = useState('');
  const range = selectionDateRange(selection, today);
  const selectedValue = selection.kind === 'custom' ? 'custom' : String(selection.days);
  const onTabChange = (value: string) => {
    if (value === 'custom') {
      const nextRange = selectionDateRange(selection, today);
      setCustomDateFrom(nextRange.dateFrom);
      setCustomDateTo(nextRange.dateTo);
      setCustomError('');
      setCustomOpen(true);
      return;
    }
    setCustomOpen(false);
    setCustomError('');
    onSelectPreset(Number(value) as 7 | 30 | 90);
  };

  function applyCustom(): void {
    const error = validateCustomProgressRange(customDateFrom, customDateTo, today);
    if (error) {
      setCustomError(error);
      return;
    }
    setCustomError('');
    setCustomOpen(false);
    onApplyCustom({ kind: 'custom', dateFrom: customDateFrom, dateTo: customDateTo });
  }

  function cancelCustom(): void {
    setCustomError('');
    setCustomOpen(false);
    setCustomDateFrom(range.dateFrom);
    setCustomDateTo(range.dateTo);
  }

  return (
    <div className="progress-period-controls">
      <div className="progress-period-controls__tabs">
        <SegmentedControl
          ariaLabel="Период прогресса"
          options={progressPeriodOptions}
          value={selectedValue}
          onChange={onTabChange}
        />
      </div>
      <div className="progress-period-controls__meta" aria-live="polite">
        <strong>Период: {periodDateLabel(range.dateFrom, range.dateTo)}</strong>
        <span>Часовой пояс: {timeZone}</span>
      </div>
      {customOpen && (
        <form
          className="progress-period-controls__custom"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            applyCustom();
          }}
          aria-describedby={customError ? 'progress-custom-period-error' : undefined}
        >
          <Field label="Начало периода" labelFor="progress-period-from">
            <input
              aria-label="Начало периода"
              className="ui-input"
              id="progress-period-from"
              max={customDateTo || today}
              onChange={(event) => setCustomDateFrom(event.target.value)}
              type="date"
              value={customDateFrom}
            />
          </Field>
          <Field label="Конец периода" labelFor="progress-period-to">
            <input
              aria-label="Конец периода"
              className="ui-input"
              id="progress-period-to"
              max={today}
              min={customDateFrom}
              onChange={(event) => setCustomDateTo(event.target.value)}
              type="date"
              value={customDateTo}
            />
          </Field>
          <div className="progress-period-controls__custom-actions">
            <Button type="submit" variant="secondary">
              Показать период
            </Button>
            <Button onClick={cancelCustom} type="button" variant="ghost">
              Отмена
            </Button>
          </div>
          {customError && (
            <p className="ui-field__error" id="progress-custom-period-error" role="alert">
              {customError}
            </p>
          )}
        </form>
      )}
    </div>
  );
}

function useTrainingAnalytics(selection: ProgressSelection) {
  const selectionKey = progressSelectionKey(selection);
  return useQuery({
    queryKey: ['workout', 'training-analytics', selectionKey],
    queryFn: () =>
      api<TrainingAnalytics>(
        `/api/v1/workouts/progress/training-analytics${progressApiQuery(selection)}`,
      ),
    placeholderData: keepPreviousData,
  });
}

export function ProgressExperience({
  measurementDiary,
  timeZone,
}: { measurementDiary?: ReactNode; timeZone?: string | null } = {}) {
  const { navigate, search } = useNavigation();
  const selection = useMemo(() => parseProgressSelection(search), [search]);
  const resolvedTimeZone = timeZone ?? detectedTimeZone();
  const today = dateInputValue(new Date(), resolvedTimeZone);

  const selectionKey = progressSelectionKey(selection);
  const summary = useQuery({
    queryKey: queryKeys.progress.summary(selectionKey),
    queryFn: () =>
      api<ProgressSummary>(`/api/v1/workouts/progress/summary${progressApiQuery(selection)}`),
    placeholderData: keepPreviousData,
  });
  const analytics = useTrainingAnalytics(selection);
  const controlledNutritionPeriod = useMemo<ControlledNutritionPeriod>(
    () => nutritionPeriodForProgress(selection),
    [selection],
  );

  function navigateWithinProgress(to: string): void {
    const scrollX = window.scrollX;
    const scrollY = window.scrollY;
    navigate(to);
    window.scrollTo({ left: scrollX, top: scrollY, behavior: 'instant' });
  }

  function selectPreset(days: 7 | 30 | 90): void {
    navigateWithinProgress(progressPath(search, { kind: 'preset', days }));
  }

  function applyCustom(nextSelection: Extract<ProgressSelection, { kind: 'custom' }>): void {
    navigateWithinProgress(progressPath(search, nextSelection));
  }

  const summaryMatchesSelection = summary.data
    ? selection.kind === 'custom'
      ? summary.data.period_start === selection.dateFrom &&
        summary.data.period_end === selection.dateTo
      : summary.data.period_days === selection.days
    : false;
  const isSummaryUpdating = Boolean(summary.data && !summaryMatchesSelection);

  return (
    <div className="progress-experience progress-experience--bento">
      <header className="progress-hero">
        <div className="progress-hero__copy">
          <span className="eyebrow">Ваша динамика</span>
          <h1>Прогресс</h1>
          <p>Что изменилось в тренировках, теле и питании — только по фактическим данным.</p>
          <ContextualHelp articlePath="/knowledge/progress/how-to-read-progress">
            <p>
              Сначала смотрите на период и полноту данных. Одна точка не образует тренд, а
              пропущенная запись не равна нулевому результату.
            </p>
          </ContextualHelp>
        </div>
        <div className="progress-hero__actions">
          <ProgressPeriodControls
            key={selectionKey}
            onApplyCustom={applyCustom}
            onSelectPreset={selectPreset}
            selection={selection}
            timeZone={resolvedTimeZone}
            today={today}
          />
          <AppLink className="button-link secondary-link" to={progressReportPath(selection)}>
            <Icon name="print" size={16} /> Скачать отчёт
          </AppLink>
        </div>
      </header>

      <AiCoachEntry entryPoint="progress" />

      {summary.isLoading ? (
        <LoadingState label="Собираем динамику за период…" />
      ) : summary.error ? (
        <ErrorState
          message={(summary.error as Error).message}
          retry={() => void summary.refetch()}
        />
      ) : summary.data ? (
        <>
          {isSummaryUpdating && (
            <p className="progress-note" role="status">
              Обновляем динамику за период…
            </p>
          )}
          <SummaryOverview summary={summary.data} />
          <div className="progress-details" aria-label="Подробности прогресса">
            <TrainingSection analytics={analytics} summary={summary.data} />
            <CardioHistory
              dateFrom={summary.data.period_start}
              dateTo={summary.data.period_end}
              summary={summary.data.cardio}
              timeZone={resolvedTimeZone}
            />
            <BodySection
              measurementDiary={measurementDiary}
              summary={summary.data}
              weightChartInOverview
            />
            <NutritionSection summary={summary.data} />
            <NutritionPeriodReport
              controlledPeriod={controlledNutritionPeriod}
              showSelector={false}
            />
            <AdherenceSection summary={summary.data} />
          </div>
        </>
      ) : null}

      {summary.error && <TrainingSection analytics={analytics} />}
    </div>
  );
}
