import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
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
} from '../../shared/ui/common';
import { NutritionPeriodReport, type ControlledNutritionPeriod } from './NutritionReport';
import { Icon } from '../../shared/ui/Icon';
import { CardioHistory } from '../cardio/CardioLogging';
import {
  nutritionPeriodForProgress,
  parseProgressSelection,
  progressApiQuery,
  progressPath,
  progressPeriodOptions,
  progressReportPath,
  progressSelectionKey,
  progressViewPath,
  parseProgressView,
  selectionDateRange,
  validateCustomProgressRange,
  type ProgressView,
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

function progressPercent(component: AdherenceComponent): string {
  return component.percent == null ? 'Мало данных' : `${formatNumber(component.percent)}%`;
}

function ProgressMetricCard({
  detail,
  label,
  to,
  value,
}: {
  detail: string;
  label: string;
  to: string;
  value: string;
}) {
  return (
    <AppLink className="progress-overview__metric" to={to}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
      <span className="progress-overview__metric-arrow" aria-hidden="true">
        <Icon name="arrow-right" size={16} />
      </span>
    </AppLink>
  );
}

function ProgressTrendRows({
  trends,
  selectedMetric,
}: {
  selectedMetric: BodyTrend['metric'] | null;
  trends: BodyTrend[];
}) {
  const compactTrends = trends.filter((trend) => trend.metric !== selectedMetric);
  if (!compactTrends.length) return null;
  return (
    <ul className="progress-overview__trend-list" aria-label="Другие замеры тела">
      {compactTrends.map((trend) => (
        <li key={trend.metric}>
          <span>{bodyMetricLabels[trend.metric]}</span>
          <strong>
            {formatNumber(trend.latest_value)} {bodyMetricUnits[trend.metric]}
          </strong>
          <small>{formatChange(trend.change, bodyMetricUnits[trend.metric])}</small>
        </li>
      ))}
    </ul>
  );
}

function ProgressTrendPanel({
  summary,
  detail = false,
  showConfidence = true,
}: {
  detail?: boolean;
  summary: ProgressSummary;
  showConfidence?: boolean;
}) {
  const trends = summary.body.trends;
  const defaultMetric =
    trends.find((trend) => trend.metric === 'weight_kg')?.metric ?? trends[0]?.metric ?? null;
  const [selectedMetric, setSelectedMetric] = useState<BodyTrend['metric'] | null>(defaultMetric);
  const selectedTrend = trends.find((trend) => trend.metric === selectedMetric) ?? trends[0];

  return (
    <section className={`progress-trend-panel${detail ? ' progress-trend-panel--detail' : ''}`}>
      <div className="progress-trend-panel__head">
        <div>
          <span className="progress-section__eyebrow">Динамика</span>
          <h3>{detail ? 'Один график для всех замеров' : 'Главная динамика'}</h3>
        </div>
        {selectedTrend && (
          <strong className="progress-trend-panel__value">
            {formatNumber(selectedTrend.latest_value)} {bodyMetricUnits[selectedTrend.metric]}
            <small>
              {formatChange(selectedTrend.change, bodyMetricUnits[selectedTrend.metric])}
            </small>
          </strong>
        )}
      </div>
      {trends.length ? (
        <>
          <div className="progress-trend-switcher" role="tablist" aria-label="Показатель графика">
            {trends.map((trend) => (
              <button
                aria-selected={selectedTrend?.metric === trend.metric}
                className={selectedTrend?.metric === trend.metric ? 'is-active' : ''}
                key={trend.metric}
                onClick={() => setSelectedMetric(trend.metric)}
                role="tab"
                type="button"
              >
                {bodyMetricLabels[trend.metric]}
              </button>
            ))}
          </div>
          {selectedTrend ? (
            <BodyChart trend={selectedTrend} />
          ) : (
            <EmptyState title="Мало данных" text="За выбранный период нет замеров тела." />
          )}
          <ProgressTrendRows selectedMetric={selectedTrend?.metric ?? null} trends={trends} />
          {showConfidence && (
            <DataConfidence
              className="data-confidence--compact"
              kind="weight"
              signal={summary.data_sufficiency.weight_trend}
            />
          )}
        </>
      ) : (
        <EmptyState
          title="Мало данных для динамики"
          text="Добавьте вес или окружность: первая запись сохранит факт, а повторные замеры покажут направление."
        />
      )}
    </section>
  );
}

function ProgressInsights({ summary }: { summary: ProgressSummary }) {
  const good: string[] = [];
  const attention: string[] = [];
  const { training, nutrition, cardio, body, adherence } = summary;
  const confirmedNutritionDays = nutrition.complete_days + nutrition.fasted_days;
  const weight = body.trends.find((trend) => trend.metric === 'weight_kg');

  if (training.completed_workouts > 0) {
    good.push(
      `Выполнено ${training.completed_workouts} из ${training.planned_workouts} тренировок`,
    );
  }
  if (training.new_personal_records > 0) {
    good.push(
      `${training.new_personal_records} ${plural(training.new_personal_records, 'новый рекорд', 'новых рекорда', 'новых рекордов')}`,
    );
  }
  if (confirmedNutritionDays > 0)
    good.push(`Питание подтверждено за ${confirmedNutritionDays} дней`);
  if (cardio.completed_sessions > 0) {
    good.push(`Кардио: ${cardio.completed_sessions} завершённых сессий`);
  }
  if (!good.length && adherence.overall_percent != null) {
    good.push(`Общий adherence: ${formatNumber(adherence.overall_percent)}%`);
  }

  if (training.planned_workouts > training.completed_workouts) {
    attention.push(
      `${training.planned_workouts - training.completed_workouts} тренировок ещё не завершено`,
    );
  }
  if (nutrition.visible && nutrition.unlogged_days > 0) {
    attention.push(`${nutrition.unlogged_days} дней питания без записей`);
  }
  if (!weight || summary.data_sufficiency.weight_trend.status !== 'sufficient') {
    attention.push('Для динамики веса пока мало повторных замеров');
  }
  if (!attention.length && cardio.planned_sessions > cardio.completed_sessions) {
    attention.push(
      `${cardio.planned_sessions - cardio.completed_sessions} кардио-сессий ещё не завершено`,
    );
  }

  return (
    <section className="progress-insights" aria-label="Короткие выводы">
      <div className="progress-insights__column progress-insights__column--good">
        <h3>Что идёт хорошо</h3>
        <ul>
          {(good.length ? good : ['Пока недостаточно фактов для вывода'])
            .slice(0, 3)
            .map((item) => (
              <li key={item}>{item}</li>
            ))}
        </ul>
      </div>
      <div className="progress-insights__column progress-insights__column--attention">
        <h3>Что требует внимания</h3>
        <ul>
          {(attention.length ? attention : ['За выбранный период явных отклонений нет'])
            .slice(0, 3)
            .map((item) => (
              <li key={item}>{item}</li>
            ))}
        </ul>
      </div>
    </section>
  );
}

function ProgressCategoryNav({ search, view }: { search: string; view: ProgressView }) {
  const categories: Array<{ detail: string; label: string; value: ProgressView }> = [
    { detail: 'Обзор периода', label: 'Обзор', value: 'overview' },
    { detail: 'Вес и окружности', label: 'Тело', value: 'body' },
    { detail: 'Нагрузка и PR', label: 'Тренировки', value: 'training' },
    { detail: 'Калории и БЖУ', label: 'Питание', value: 'nutrition' },
    { detail: 'Сессии и дистанция', label: 'Кардио', value: 'cardio' },
    { detail: 'Check-in и история', label: 'Самочувствие', value: 'wellbeing' },
    { detail: 'Исходные записи', label: 'История', value: 'history' },
  ];
  return (
    <nav className="progress-category-nav" aria-label="Разделы прогресса">
      {categories.map((category) => (
        <AppLink
          aria-current={view === category.value ? 'page' : undefined}
          className={view === category.value ? 'is-active' : undefined}
          key={category.value}
          to={progressViewPath(search, category.value)}
        >
          <strong>{category.label}</strong>
          <small>{category.detail}</small>
        </AppLink>
      ))}
    </nav>
  );
}

function SummaryOverview({ summary, search }: { search: string; summary: ProgressSummary }) {
  const weight = summary.body.trends.find((trend) => trend.metric === 'weight_kg');
  const confirmedNutritionDays = summary.nutrition.complete_days + summary.nutrition.fasted_days;
  const latestWeight = weight ? `${formatNumber(weight.latest_value)} кг` : 'Мало данных';
  return (
    <section
      className="progress-summary progress-overview semantic-card semantic-card--summary semantic-card--progress"
      data-card-variant="summary"
      data-semantic-family="progress"
      aria-labelledby="progress-overview-title"
    >
      <div className="progress-overview__heading">
        <div>
          <span className="progress-section__eyebrow">Сводка выбранного периода</span>
          <h2 id="progress-overview-title">Что изменилось</h2>
          <p>{periodDateLabel(summary.period_start, summary.period_end)}</p>
        </div>
        <Badge>{summary.period_days} дн.</Badge>
      </div>
      <div className="progress-overview__metrics" aria-label="Ключевые показатели">
        <ProgressMetricCard
          detail={weight ? formatChange(weight.change, 'кг') : 'Мало данных'}
          label="Тело"
          to={progressViewPath(search, 'body')}
          value={latestWeight}
        />
        <ProgressMetricCard
          detail={`${formatNumber(summary.training.frequency_per_week, 1)} в неделю · ${summary.training.new_personal_records} PR`}
          label="Тренировки"
          to={progressViewPath(search, 'training')}
          value={`${summary.training.completed_workouts} / ${summary.training.planned_workouts}`}
        />
        <ProgressMetricCard
          detail={
            summary.nutrition.visible
              ? `${confirmedNutritionDays} подтверждённых дней · ${progressPercent(summary.adherence.protein)} белок`
              : 'Недоступно для этой роли'
          }
          label="Питание"
          to={progressViewPath(search, 'nutrition')}
          value={
            !summary.nutrition.visible
              ? 'Недоступно'
              : summary.nutrition.average_calories == null
                ? 'Мало данных'
                : `${formatNumber(summary.nutrition.average_calories, 0)} ккал`
          }
        />
        <ProgressMetricCard
          detail={`${formatNumber(summary.cardio.duration_minutes, 0)} мин · ${progressPercent(summary.adherence.cardio)}`}
          label="Кардио"
          to={progressViewPath(search, 'cardio')}
          value={`${summary.cardio.completed_sessions} сессий`}
        />
      </div>
      <ProgressTrendPanel summary={summary} />
      <ProgressInsights summary={summary} />
      <details className="progress-overview__adherence">
        <summary>
          <span>
            <strong>Общий adherence</strong>
            <small>
              {summary.adherence.overall_percent == null ? (
                'Мало данных'
              ) : (
                <>
                  <strong>{formatNumber(summary.adherence.overall_percent)}%</strong> по доступным
                  компонентам
                </>
              )}
            </small>
          </span>
          <DisclosureIcon />
        </summary>
        <div>
          <ComplianceRow label="Тренировки" component={summary.adherence.workouts} />
          <ComplianceRow label="Калории" component={summary.adherence.calories} />
          <ComplianceRow label="Белок" component={summary.adherence.protein} />
          <ComplianceRow label="Кардио" component={summary.adherence.cardio} />
        </div>
      </details>
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
}: {
  isStale?: boolean;
  measurementDiary?: ReactNode;
  summary: ProgressSummary;
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
      <details className="progress-priority progress-priority--compact">
        <summary>
          <span>
            <small>Контекст планирования</small>
            <strong>
              {!body.priority
                ? 'Приоритет не выбран'
                : body.priority.mode === 'balanced'
                  ? 'Сбалансированное развитие'
                  : 'Выбранные мышечные группы'}
            </strong>
          </span>
          <DisclosureIcon />
        </summary>
        <div>
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
      </details>
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
          <ProgressTrendPanel detail showConfidence={false} summary={summary} />
          {body.trends.map((trend) => {
            const interpretation = trendInterpretationText(trend, body.guidance);
            return interpretation ? (
              <p className="progress-note" key={`${trend.metric}-interpretation`}>
                <strong>{bodyMetricLabels[trend.metric]}:</strong> {interpretation}
              </p>
            ) : null;
          })}
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

function ProgressDetailHeader({
  search,
  view,
}: {
  search: string;
  view: Exclude<ProgressView, 'overview'>;
}) {
  const labels: Record<Exclude<ProgressView, 'overview'>, string> = {
    body: 'Тело',
    training: 'Тренировки',
    nutrition: 'Питание',
    cardio: 'Кардио',
    wellbeing: 'Самочувствие',
    history: 'История тренировок',
  };
  return (
    <header className="progress-detail-header">
      <AppLink className="progress-detail-header__back" to={progressViewPath(search, 'overview')}>
        <Icon name="arrow-left" size={16} /> Обзор
      </AppLink>
      <div>
        <span className="progress-section__eyebrow">Детали выбранного периода</span>
        <p className="progress-detail-header__title">{labels[view]}</p>
      </div>
    </header>
  );
}

function useTrainingAnalytics(selection: ProgressSelection, enabled: boolean) {
  const selectionKey = progressSelectionKey(selection);
  return useQuery({
    queryKey: ['workout', 'training-analytics', selectionKey],
    queryFn: () =>
      api<TrainingAnalytics>(
        `/api/v1/workouts/progress/training-analytics${progressApiQuery(selection)}`,
      ),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function ProgressExperience({
  canExport = true,
  detailContent,
  focusMeasurements = false,
  measurementDiary,
  progressView,
  timeZone,
}: {
  detailContent?: ReactNode;
  canExport?: boolean;
  focusMeasurements?: boolean;
  measurementDiary?: ReactNode;
  progressView?: ProgressView;
  timeZone?: string | null;
} = {}) {
  const { navigate, search } = useNavigation();
  const view = progressView ?? parseProgressView(search, window.location.hash);
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
  const analytics = useTrainingAnalytics(selection, view === 'training');
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

  useEffect(() => {
    if (!focusMeasurements || !summary.data) return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById('measurement-diary')?.scrollIntoView({ block: 'start' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [focusMeasurements, summary.data]);

  return (
    <div className="progress-experience progress-experience--bento">
      <header className="progress-hero">
        <div className="progress-hero__copy">
          <span className="eyebrow">Факты за период</span>
          <h1>Прогресс</h1>
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
          {canExport ? (
            <AppLink className="button-link secondary-link" to={progressReportPath(selection)}>
              <Icon name="print" size={16} /> Скачать отчёт
            </AppLink>
          ) : (
            <button className="button-link secondary-link" disabled type="button">
              <Icon name="print" size={16} /> Скачать отчёт
            </button>
          )}
        </div>
      </header>

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
          {view === 'overview' ? (
            <>
              <SummaryOverview search={search} summary={summary.data} />
              <ProgressCategoryNav search={search} view={view} />
            </>
          ) : (
            <>
              <ProgressDetailHeader search={search} view={view} />
              <ProgressCategoryNav search={search} view={view} />
              <div className="progress-details" aria-label="Подробности прогресса">
                {view === 'training' && (
                  <TrainingSection analytics={analytics} summary={summary.data} />
                )}
                {view === 'cardio' && (
                  <CardioHistory
                    dateFrom={summary.data.period_start}
                    dateTo={summary.data.period_end}
                    summary={summary.data.cardio}
                    timeZone={resolvedTimeZone}
                  />
                )}
                {view === 'body' && (
                  <BodySection measurementDiary={measurementDiary} summary={summary.data} />
                )}
                {view === 'nutrition' && (
                  <>
                    <NutritionSection isStale={summary.isPlaceholderData} summary={summary.data} />
                    <div id="progress-reports">
                      <NutritionPeriodReport
                        canExport={canExport}
                        controlledPeriod={controlledNutritionPeriod}
                        showSelector={false}
                      />
                    </div>
                  </>
                )}
                {(view === 'wellbeing' || view === 'history') && detailContent}
                {(view === 'wellbeing' || view === 'history') && !detailContent && (
                  <EmptyState
                    title="Раздел пока недоступен"
                    text="Попробуйте открыть его ещё раз."
                  />
                )}
              </div>
            </>
          )}
        </>
      ) : null}

      {summary.error && view === 'training' && <TrainingSection analytics={analytics} />}
    </div>
  );
}
