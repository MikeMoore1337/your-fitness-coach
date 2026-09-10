import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { useOptionalAuth } from '../../app/AuthProvider';
import type {
  NutritionReportPeriod,
  ProgressReport,
  ReportHandoffView,
} from '../../shared/api/types';
import { api } from '../../shared/api/client';
import { downloadProgressReport } from '../../features/reports/downloadProgressReport';
import { ReportHandoffPanel } from '../../features/reports/ReportHandoffPanel';
import { AppLink, useNavigation } from '../../shared/navigation/router';
import { BrandLockup } from '../../shared/ui/BrandLogo';
import { DataConfidence } from '../../shared/ui/DataConfidence';
import { TimeSeriesChart } from '../../shared/ui/DataViz';
import { Icon } from '../../shared/ui/Icon';
import {
  Button,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  SegmentedControl,
} from '../../shared/ui/common';
import '../../styles/react.css';
import '../../styles/design-v2.css';

const periodOptions = [
  { value: 'days_7', label: '7 дней' },
  { value: 'days_30', label: '30 дней' },
  { value: 'days_90', label: '90 дней' },
  { value: 'current_month', label: 'Этот месяц' },
  { value: 'previous_month', label: 'Прошлый месяц' },
  { value: 'custom', label: 'Свой период' },
] as const;

const validPeriods = new Set<NutritionReportPeriod>(periodOptions.map((option) => option.value));
const datePattern = /^\d{4}-\d{2}-\d{2}$/;

type ReportSelection = {
  period: NutritionReportPeriod;
  dateFrom: string;
  dateTo: string;
};

function positiveClientId(search: string): number | null {
  const value = new URLSearchParams(search).get('client_id');
  if (!value || !/^\d+$/.test(value)) return null;
  const result = Number(value);
  return Number.isSafeInteger(result) && result > 0 ? result : null;
}

function positiveHandoffId(search: string): number | null {
  const value = new URLSearchParams(search).get('handoff_id');
  if (!value || !/^\d+$/.test(value)) return null;
  const result = Number(value);
  return Number.isSafeInteger(result) && result > 0 ? result : null;
}

function handoffReturnPath(search: string): string {
  return new URLSearchParams(search).get('return_to') ===
    '/app?section=profile#profile-notifications'
    ? '/app?section=profile#profile-notifications'
    : '/app?section=progress';
}

function initialSelection(search: string): ReportSelection {
  const params = new URLSearchParams(search);
  const candidate = params.get('period') as NutritionReportPeriod | null;
  const period = candidate && validPeriods.has(candidate) ? candidate : 'days_30';
  const dateFrom = params.get('date_from') ?? '';
  const dateTo = params.get('date_to') ?? '';
  return {
    period,
    dateFrom: datePattern.test(dateFrom) ? dateFrom : '',
    dateTo: datePattern.test(dateTo) ? dateTo : '',
  };
}

function reportPath(selection: ReportSelection, clientId: number | null): string {
  const params = new URLSearchParams({ period: selection.period });
  if (selection.period === 'custom') {
    params.set('date_from', selection.dateFrom);
    params.set('date_to', selection.dateTo);
  }
  const base = clientId
    ? `/api/v1/coach/clients/${clientId}/progress-report`
    : '/api/v1/workouts/progress/report';
  return `${base}?${params}`;
}

function reportDownloadLinkPath(selection: ReportSelection, clientId: number | null): string {
  const [base, query] = reportPath(selection, clientId).split('?');
  return `${base}/download-link?${query}`;
}

function pagePath(selection: ReportSelection, clientId: number | null): string {
  const params = new URLSearchParams({ period: selection.period });
  if (selection.period === 'custom') {
    params.set('date_from', selection.dateFrom);
    params.set('date_to', selection.dateTo);
  }
  if (clientId) params.set('client_id', String(clientId));
  return `/app/report?${params}`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  }).format(new Date(`${value}T12:00:00`));
}

function formatDateTime(value: string, timezone: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'long',
    timeStyle: 'short',
    timeZone: timezone,
  }).format(new Date(value));
}

function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value == null) return 'Нет данных';
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(value);
}

function percent(value: number | null | undefined): string {
  return value == null ? 'Пока не оценить' : `${formatNumber(value)}%`;
}

function goalLabel(value: string | null | undefined): string {
  return (
    {
      muscle_gain: 'Набор мышечной массы',
      weight_loss: 'Снижение массы',
      maintenance: 'Поддержание формы',
      strength: 'Развитие силы',
      endurance: 'Развитие выносливости',
    }[value ?? ''] ?? 'Не указана'
  );
}

function changeKindLabel(value: string): string {
  return (
    {
      assigned: 'Программа назначена',
      program_archived: 'Программа архивирована',
      plan_updated: 'План обновлён',
      block_created: 'Создан тренировочный блок',
      block_updated: 'Тренировочный блок обновлён',
      block_status_changed: 'Изменён статус тренировочного блока',
    }[value] ?? 'План изменён'
  );
}

function programStatusLabel(value: string): string {
  return (
    {
      active: 'активна',
      planned: 'запланирована',
      completed: 'завершена',
      archived: 'архивирована',
    }[value] ?? 'не определён'
  );
}

function nutritionTargetSourceLabel(value: string): string {
  return (
    {
      trainer: 'Тренер',
      manual: 'Пользователь',
      calculated: 'Расчёт приложения',
    }[value] ?? 'Не указан'
  );
}

function checkInValue(value: number | null | undefined): string {
  return value == null ? 'Не отвечено' : `${value} из 5`;
}

const wellbeingValueLabels: Record<'sleep' | 'mood', Record<number, string>> = {
  sleep: {
    1: 'Очень плохо',
    2: 'Плохо',
    3: 'Обычно',
    4: 'Хорошо',
    5: 'Отлично',
  },
  mood: {
    1: 'Очень тяжело',
    2: 'Тяжеловато',
    3: 'Обычно',
    4: 'Хорошо',
    5: 'Отлично',
  },
};

const wellbeingTrendLabels: Record<string, string> = {
  improving: 'В конце периода выше',
  declining: 'В конце периода ниже',
  stable: 'Без заметной разницы',
  insufficient_data: 'Пока мало точек',
};

function durationLabel(minutes: number | null | undefined): string {
  if (minutes == null) return 'Не заполнено';
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest} мин`;
  if (!rest) return `${hours} ч`;
  return `${hours} ч ${rest} мин`;
}

function DailyWellbeingReportSection({ report }: { report: ProgressReport }) {
  const wellbeing = report.wellbeing;
  if (!wellbeing) return null;
  const metrics = [
    ['sleep', 'Качество сна'],
    ['mood', 'Настроение'],
  ] as const;
  return (
    <section
      aria-labelledby="report-wellbeing-title"
      className="progress-report-section progress-report-section--wellbeing"
    >
      <header>
        <div>
          <span className="eyebrow">Самооценка</span>
          <h2 id="report-wellbeing-title">Сон и настроение</h2>
        </div>
        <AppLink
          className="button-link secondary-link report-screen-only"
          to={`/app?section=today&wellbeing=1&wellbeing_date=${wellbeing.period_end}`}
        >
          Добавить отметку
        </AppLink>
      </header>
      <dl className="progress-report-facts">
        <div>
          <dt>Покрытие</dt>
          <dd>
            {wellbeing.recorded_days} из {wellbeing.eligible_days} дней
          </dd>
        </div>
        <div>
          <dt>Процент периода</dt>
          <dd>{formatNumber(wellbeing.coverage_percent)}%</dd>
        </div>
      </dl>
      <div className="progress-report-wellbeing-grid">
        {metrics.map(([key, label]) => {
          const metric = wellbeing[key];
          const maxCount = Math.max(1, ...metric.distribution.map((item) => item.count));
          return (
            <article className="progress-report-wellbeing-metric" key={key}>
              <header>
                <div>
                  <h3>{label}</h3>
                  <p>{metric.recorded_days} отдельных отметок</p>
                </div>
                <span>{wellbeingTrendLabels[metric.trend]}</span>
              </header>
              <ul aria-label={`Распределение: ${label}`}>
                {metric.distribution.map((item) => (
                  <li key={item.value}>
                    <span>{wellbeingValueLabels[key][item.value]}</span>
                    <span className="progress-report-wellbeing-metric__bar" aria-hidden="true">
                      <i style={{ width: `${(item.count / maxCount) * 100}%` }} />
                    </span>
                    <strong>{item.count}</strong>
                  </li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>
      <details className="progress-report-wellbeing-days">
        <summary>Дни с фактическими отметками</summary>
        <div className="progress-report-wellbeing-days__table-wrap">
          <table>
            <caption>Записанные дни сна и настроения</caption>
            <thead>
              <tr>
                <th scope="col">Дата</th>
                <th scope="col">Сон</th>
                <th scope="col">Длительность</th>
                <th scope="col">Настроение</th>
              </tr>
            </thead>
            <tbody>
              {wellbeing.daily.map((item) => (
                <tr key={item.local_date}>
                  <th scope="row">{formatDate(item.local_date)}</th>
                  <td>
                    {item.sleep_quality == null
                      ? 'Не заполнено'
                      : wellbeingValueLabels.sleep[item.sleep_quality]}
                  </td>
                  <td>{durationLabel(item.sleep_duration_minutes)}</td>
                  <td>
                    {item.mood == null ? 'Не заполнено' : wellbeingValueLabels.mood[item.mood]}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <p className="progress-report-limit">
        Это субъективные фактические отметки. Пропуски не считаются нулевыми значениями, а заметки
        не включены в агрегаты, PDF и доступ тренера.
      </p>
    </section>
  );
}

const bodyMetricLabels: Record<string, string> = {
  biceps_cm: 'Плечо',
  chest_cm: 'Грудь',
  hips_cm: 'Бёдра',
  thigh_cm: 'Бедро',
  waist_cm: 'Талия',
};

function WeightChart({ report }: { report: ProgressReport }) {
  const trend = report.body.trends.find((item) => item.metric === 'weight_kg');
  if (!trend) {
    return (
      <EmptyState
        title="Нет замеров массы за период"
        text="Отсутствующие дни не интерполируются."
      />
    );
  }
  return (
    <TimeSeriesChart
      metric="Масса тела"
      period={`${formatDate(trend.first_measured_on)} — ${formatDate(trend.latest_measured_on)}`}
      points={trend.points.map((point) => ({
        key: point.measured_on,
        label: formatDate(point.measured_on),
        value: point.value,
      }))}
      print
      tableCaption="Таблица замеров массы"
      unit="кг"
      valueLabel="Замер"
    />
  );
}

function PrintPageHeader({
  report,
  continuation = false,
}: {
  report: ProgressReport;
  continuation?: boolean;
}) {
  return (
    <header
      className={`progress-report-print-header${continuation ? ' progress-report-print-header--continuation' : ''}`}
      aria-hidden="true"
    >
      <BrandLockup surface="light" />
      <span>
        Период: {formatDate(report.period_start)} — {formatDate(report.period_end)}
      </span>
    </header>
  );
}

function ReportContent({
  report,
  selectedExercises,
  controls,
}: {
  report: ProgressReport;
  selectedExercises: readonly string[];
  controls: ReactNode;
}) {
  const selected = report.training.exercises.filter((exercise) =>
    selectedExercises.includes(exercise.exercise_title),
  );
  const circumference = report.body.trends.filter((trend) => trend.metric !== 'weight_kg');
  const nutrition = report.nutrition.summary;
  const notCompleted = Math.max(
    0,
    report.training.planned_workouts -
      report.training.completed_workouts -
      report.training.skipped_workouts,
  );

  return (
    <div className="progress-report-document">
      <PrintPageHeader report={report} />
      <footer className="progress-report-print-footer" aria-hidden="true">
        <span>Сформировано {formatDateTime(report.generated_at, report.timezone)}</span>
        <span>Your Fitness Coach</span>
      </footer>

      <section className="progress-report-overview" aria-labelledby="report-overview-title">
        <div className="progress-report-overview__identity">
          <span className="eyebrow">Отчёт о прогрессе</span>
          <h1 id="report-overview-title">{report.subject.name}</h1>
          <p>
            {formatDate(report.period_start)} — {formatDate(report.period_end)} · {report.timezone}
          </p>
          <p>
            {report.subject.role === 'client' ? 'Клиент тренера' : 'Личный отчёт'} · Цель:{' '}
            {goalLabel(report.subject.goal)}
          </p>
        </div>
        <div className="progress-report-overview__adherence">
          <span>Соблюдение плана</span>
          <strong>{percent(report.adherence.overall_percent)}</strong>
          <small>Только по доступным компонентам расчёта</small>
        </div>
      </section>

      <section className="progress-report-confidence" aria-label="Полнота данных отчёта">
        <DataConfidence kind="training" signal={report.data_sufficiency.working_sets} />
        <DataConfidence kind="nutrition" signal={report.data_sufficiency.nutrition_coverage} />
        <DataConfidence kind="weight" signal={report.data_sufficiency.weight_trend} />
      </section>

      {controls}

      <section className="progress-report-section" aria-labelledby="report-training-title">
        <header>
          <span className="eyebrow">Тренировки</span>
          <h2 id="report-training-title">Факты за период</h2>
        </header>
        <dl className="progress-report-facts">
          <div>
            <dt>По плану</dt>
            <dd>{report.training.planned_workouts}</dd>
          </div>
          <div>
            <dt>Завершено</dt>
            <dd>{report.training.completed_workouts}</dd>
          </div>
          <div>
            <dt>Пропущено</dt>
            <dd>{report.training.skipped_workouts}</dd>
          </div>
          <div>
            <dt>Ещё не завершено</dt>
            <dd>{notCompleted}</dd>
          </div>
          <div>
            <dt>Частота</dt>
            <dd>{formatNumber(report.training.frequency_per_week, 2)} / нед.</dd>
          </div>
          <div>
            <dt>Рабочие подходы</dt>
            <dd>{report.training.completed_working_sets}</dd>
          </div>
          <div>
            <dt>Внешняя нагрузка</dt>
            <dd>{formatNumber(report.training.external_load_volume_kg, 0)} кг</dd>
          </div>
          <div>
            <dt>Новые личные рекорды</dt>
            <dd>{report.training.new_personal_records}</dd>
          </div>
        </dl>
        <p className="progress-report-limit">
          Объём внешней нагрузки — сумма веса × повторения только для завершённых рабочих подходов.
          Он не сравнивает технику, амплитуду, тренажёры и разные упражнения.
        </p>
        <div className="progress-report-print-page-section">
          <PrintPageHeader continuation report={report} />
          {report.program ? (
            <div className="progress-report-program">
              <h3>{report.program.title}</h3>
              <p>
                Старт {formatDate(report.program.start_date)} · {report.program.duration_weeks} нед.
                · статус: {programStatusLabel(report.program.status)}
              </p>
              {report.program.active_block && (
                <>
                  <p>
                    Текущий блок: <strong>{report.program.active_block.title}</strong>,{' '}
                    {formatDate(report.program.active_block.start_date)} —{' '}
                    {formatDate(report.program.active_block.end_date)}
                  </p>
                  <p className="progress-report-program__recommendation">
                    <strong>Рекомендация:</strong>
                    <span>{report.program.active_block.purpose}</span>
                  </p>
                </>
              )}
              {report.program.changes.length > 0 && (
                <ul>
                  {report.program.changes.map((change) => (
                    <li key={`${change.changed_on}-${change.change_kind}`}>
                      {formatDate(change.changed_on)} — {changeKindLabel(change.change_kind)}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <p className="progress-report-empty">Активной программы на дату формирования нет.</p>
          )}

          <div className="progress-report-exercises">
            <h3>Выбранная динамика упражнений</h3>
            {selected.length ? (
              selected.map((exercise) => {
                const chronological = [...exercise.sessions].sort((a, b) =>
                  a.performed_on.localeCompare(b.performed_on),
                );
                const first = chronological[0];
                const latest = chronological.at(-1);
                return (
                  <article key={exercise.exercise_title}>
                    <h4>{exercise.exercise_title}</h4>
                    <p>
                      {exercise.performed_session_count} сессий · {exercise.completed_set_count}{' '}
                      рабочих подходов · {formatDate(exercise.first_performed_on)} —{' '}
                      {formatDate(exercise.last_performed_on)}
                    </p>
                    <dl>
                      <div>
                        <dt>Макс. внешний вес</dt>
                        <dd>{formatNumber(exercise.max_external_load_kg)} кг</dd>
                      </div>
                      <div>
                        <dt>Объём за период</dt>
                        <dd>{formatNumber(exercise.external_load_volume_kg, 0)} кг</dd>
                      </div>
                      <div>
                        <dt>Первая сессия</dt>
                        <dd>{formatNumber(first?.external_load_volume_kg, 0)} кг</dd>
                      </div>
                      <div>
                        <dt>Последняя сессия</dt>
                        <dd>{formatNumber(latest?.external_load_volume_kg, 0)} кг</dd>
                      </div>
                    </dl>
                  </article>
                );
              })
            ) : (
              <p className="progress-report-empty">Упражнения для печати не выбраны.</p>
            )}
          </div>
          <div className="progress-report-cardio">
            <h3>Ручное кардио</h3>
            <p>
              {report.cardio.completed_sessions} завершено · {report.cardio.duration_minutes} мин ·{' '}
              {formatNumber(report.cardio.frequency_per_week, 2)} / нед.
              {report.cardio.distance_km == null
                ? ''
                : ` · ${formatNumber(report.cardio.distance_km)} км`}
            </p>
          </div>
        </div>
      </section>

      <div className="progress-report-print-page-section">
        <PrintPageHeader continuation report={report} />
        <section
          className="progress-report-section progress-report-section--body"
          aria-labelledby="report-body-title"
        >
          <header>
            <span className="eyebrow">Тело</span>
            <h2 id="report-body-title">Изменения только относительно себя</h2>
          </header>
          <WeightChart report={report} />
          <table>
            <caption>Окружности с точными датами крайних замеров</caption>
            <thead>
              <tr>
                <th scope="col">Замер</th>
                <th scope="col">Первый</th>
                <th scope="col">Последний</th>
                <th scope="col">Изменение</th>
              </tr>
            </thead>
            <tbody>
              {circumference.length ? (
                circumference.map((trend) => (
                  <tr key={trend.metric}>
                    <th scope="row">{bodyMetricLabels[trend.metric]}</th>
                    <td>
                      {formatNumber(trend.first_value)} см · {formatDate(trend.first_measured_on)}
                    </td>
                    <td>
                      {formatNumber(trend.latest_value)} см · {formatDate(trend.latest_measured_on)}
                    </td>
                    <td>
                      {trend.change == null
                        ? 'Недостаточно точек'
                        : `${formatNumber(trend.change)} см`}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4}>Нет замеров окружностей за период.</td>
                </tr>
              )}
            </tbody>
          </table>
          <p className="progress-report-limit">
            Окружности не показывают изменение отдельной мышцы и не используются для «идеальных»
            оценок тела.
          </p>
        </section>
      </div>

      <DailyWellbeingReportSection report={report} />

      <div className="progress-report-print-page-section">
        <PrintPageHeader continuation report={report} />
        <section
          className="progress-report-section progress-report-section--nutrition"
          aria-labelledby="report-nutrition-title"
        >
          <header>
            <span className="eyebrow">Питание</span>
            <h2 id="report-nutrition-title">Подтверждённые дни и действовавшие цели</h2>
          </header>
          <dl className="progress-report-facts">
            <div>
              <dt>Покрытие дневника</dt>
              <dd>
                {nutrition.logged_days} из {nutrition.eligible_days}
              </dd>
            </div>
            <div>
              <dt>Средние калории</dt>
              <dd>{formatNumber(nutrition.calories.average, 0)} ккал</dd>
            </div>
            <div>
              <dt>Белок</dt>
              <dd>{formatNumber(nutrition.protein_g.average)} г</dd>
            </div>
            <div>
              <dt>Жиры</dt>
              <dd>{formatNumber(nutrition.fat_g.average)} г</dd>
            </div>
            <div>
              <dt>Углеводы</dt>
              <dd>{formatNumber(nutrition.carbs_g.average)} г</dd>
            </div>
            <div>
              <dt>Калории по плану</dt>
              <dd>
                {nutrition.days_within_calorie_tolerance} из{' '}
                {nutrition.calorie_tolerance_evaluated_days}
              </dd>
            </div>
            <div>
              <dt>Белок по плану</dt>
              <dd>
                {nutrition.days_meeting_protein_target} из {nutrition.protein_target_evaluated_days}
              </dd>
            </div>
          </dl>
          {report.nutrition.target_changes.length > 0 ? (
            <table>
              <caption>Изменения цели за период</caption>
              <thead>
                <tr>
                  <th scope="col">Действует с</th>
                  <th scope="col">Источник</th>
                  <th scope="col">Ккал</th>
                  <th className="progress-report-macros-heading" scope="col">
                    Б / Ж / У
                  </th>
                </tr>
              </thead>
              <tbody>
                {report.nutrition.target_changes.map((target) => (
                  <tr key={`${target.effective_from}-${target.source}`}>
                    <td>{formatDate(target.effective_from)}</td>
                    <td>{nutritionTargetSourceLabel(target.source)}</td>
                    <td>{target.calories}</td>
                    <td>
                      {target.protein_g} / {target.fat_g} / {target.carbs_g} г
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="progress-report-empty">Изменений цели внутри периода нет.</p>
          )}
          <p className="progress-report-limit">
            Пропущенный или неполный день не считается нулевым рационом и не входит в средние и
            соблюдение плана.
          </p>
        </section>

        <section className="progress-report-section" aria-labelledby="report-checkins-title">
          <header>
            <span className="eyebrow">Самооценка</span>
            <h2 id="report-checkins-title">Еженедельные check-ins</h2>
          </header>
          {report.check_ins.length ? (
            report.check_ins.map((checkIn) => (
              <article
                className="progress-report-checkin"
                key={`${checkIn.week_start}-${checkIn.submitted_on}`}
              >
                <h3>
                  {formatDate(checkIn.week_start)} — {formatDate(checkIn.week_end)}
                </h3>
                <dl>
                  <div>
                    <dt>Нагрузка</dt>
                    <dd>{checkInValue(checkIn.training_load)}</dd>
                  </div>
                  <div>
                    <dt>Восстановление</dt>
                    <dd>{checkInValue(checkIn.recovery)}</dd>
                  </div>
                  <div>
                    <dt>Голод</dt>
                    <dd>{checkInValue(checkIn.hunger)}</dd>
                  </div>
                  <div>
                    <dt>Сложность соблюдения</dt>
                    <dd>{checkInValue(checkIn.adherence_difficulty)}</dd>
                  </div>
                </dl>
                {checkIn.note && <p>{checkIn.note}</p>}
              </article>
            ))
          ) : (
            <p className="progress-report-empty">За выбранный период check-ins не сохранены.</p>
          )}
          <p className="progress-report-limit">
            Это фактические ответы пользователя, а не медицинская оценка готовности или диагноз.
          </p>
        </section>

        <section className="progress-report-methodology" aria-labelledby="report-methodology-title">
          <h2 id="report-methodology-title">Как читать отчёт</h2>
          <p>
            Отчёт сформирован {formatDateTime(report.generated_at, report.timezone)}. Он не
            заполняет пропуски предположениями, не устанавливает причины изменений и не заменяет
            консультацию специалиста.
          </p>
        </section>
      </div>
    </div>
  );
}

export default function ProgressReportPage() {
  const { navigate, search } = useNavigation();
  const clientId = positiveClientId(search);
  const handoffId = positiveHandoffId(search);
  const auth = useOptionalAuth();
  const [draft, setDraft] = useState<ReportSelection>(() => initialSelection(search));
  const [applied, setApplied] = useState<ReportSelection>(() => initialSelection(search));
  const [exerciseSelections, setExerciseSelections] = useState<Record<string, string[]>>({});
  const [tmaDownload, setTmaDownload] = useState<{
    status: 'idle' | 'pending' | 'accepted' | 'cancelled' | 'fallback' | 'error';
    url?: string;
  }>({ status: 'idle' });
  const isTma = Boolean(window.Telegram?.WebApp?.initData);
  const customError = useMemo(() => {
    if (draft.period !== 'custom') return '';
    if (!datePattern.test(draft.dateFrom) || !datePattern.test(draft.dateTo)) {
      return 'Укажите обе даты.';
    }
    const start = new Date(`${draft.dateFrom}T12:00:00`);
    const end = new Date(`${draft.dateTo}T12:00:00`);
    if (end < start) return 'Дата окончания не может быть раньше начала.';
    const days = Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1;
    return days > 366 ? 'Период не может превышать 366 дней.' : '';
  }, [draft]);
  const handoffView = useQuery({
    queryKey: ['report-handoff', handoffId],
    queryFn: () => api<ReportHandoffView>(`/api/v1/report-handoffs/${handoffId}`),
    enabled: handoffId !== null,
  });
  const report = useQuery({
    queryKey: ['progress-report', clientId, applied],
    queryFn: () => api<ProgressReport>(reportPath(applied, clientId)),
    enabled:
      handoffId === null &&
      (applied.period !== 'custom' ||
        (!customError && Boolean(applied.dateFrom && applied.dateTo))),
    placeholderData: keepPreviousData,
  });
  const displayReport = handoffView.data?.report ?? report.data;
  const displayError = handoffId !== null ? handoffView.error : report.error;
  const displayLoading = handoffId !== null ? handoffView.isLoading : report.isLoading;
  const displayFetching = handoffId !== null ? handoffView.isFetching : report.isFetching;

  useEffect(() => {
    if (!displayReport) return;
    document.title = `progress-report-${displayReport.period_start}_${displayReport.period_end}`;
    return () => {
      document.title = 'Your Fitness Coach';
    };
  }, [displayReport]);

  const applySelection = (event?: FormEvent) => {
    event?.preventDefault();
    if (customError) return;
    setApplied(draft);
    navigate(pagePath(draft, clientId), true);
  };
  const selectPeriod = (value: string) => {
    const period = value as NutritionReportPeriod;
    const next = { ...draft, period };
    setDraft(next);
    if (period !== 'custom') {
      setApplied(next);
      navigate(pagePath(next, clientId), true);
    }
  };
  const printReport = async () => {
    if (handoffId !== null || !displayReport) return;
    if (isTma) {
      setTmaDownload({ status: 'pending' });
      try {
        const result = await downloadProgressReport(reportDownloadLinkPath(applied, clientId));
        setTmaDownload(result);
      } catch {
        setTmaDownload({ status: 'error' });
      }
      return;
    }
    window.print();
  };
  const returnPath =
    handoffId !== null
      ? handoffReturnPath(search)
      : clientId
        ? `/coach?client_id=${clientId}`
        : '/app?section=progress';
  const reportKey = displayReport
    ? `${displayReport.subject.name}:${displayReport.period_start}:${displayReport.period_end}`
    : '';
  const selectedExercises = displayReport
    ? (exerciseSelections[reportKey] ??
      displayReport.training.exercises.slice(0, 3).map((item) => item.exercise_title))
    : [];
  const controls = displayReport ? (
    <>
      {handoffId === null && (
        <section
          className="progress-report-controls report-screen-only"
          aria-labelledby="report-period-title"
        >
          <div>
            <span className="eyebrow">Период отчёта</span>
            <h2 id="report-period-title">Выберите фактическое окно</h2>
            <p>Период и субъект сохраняются в адресе отчёта при возврате из печати.</p>
          </div>
          <SegmentedControl
            ariaLabel="Период отчёта"
            onChange={selectPeriod}
            options={periodOptions}
            value={draft.period}
          />
          {draft.period === 'custom' && (
            <form className="progress-report-custom" onSubmit={applySelection}>
              <Field label="Начало" labelFor="report-date-from">
                <Input
                  id="report-date-from"
                  type="date"
                  value={draft.dateFrom}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, dateFrom: event.target.value }))
                  }
                />
              </Field>
              <Field error={customError || undefined} label="Окончание" labelFor="report-date-to">
                <Input
                  id="report-date-to"
                  type="date"
                  value={draft.dateTo}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, dateTo: event.target.value }))
                  }
                />
              </Field>
              <Button disabled={Boolean(customError)} type="submit" variant="secondary">
                Показать период
              </Button>
            </form>
          )}
        </section>
      )}

      {handoffId !== null && handoffView.data && (
        <section className="progress-report-handoff-banner report-screen-only" role="status">
          <div>
            <span className="eyebrow">Отчёт отправлен тренеру</span>
            <strong>
              {handoffView.data.handoff.trainer.full_name ||
                handoffView.data.handoff.trainer.username ||
                'Текущий тренер'}{' '}
              · живые данные
            </strong>
            <p>
              Статус:{' '}
              {handoffView.data.handoff.delivery_status === 'delivered'
                ? 'доставлено в центр уведомлений'
                : handoffView.data.handoff.delivery_status === 'pending'
                  ? 'ожидает обработки'
                  : 'не удалось доставить'}
              .
            </p>
            {handoffView.data.data_changed_since_send && (
              <p>Данные изменились после отправки; сейчас показаны актуальные факты.</p>
            )}
          </div>
        </section>
      )}

      {!['idle', 'pending'].includes(tmaDownload.status) && (
        <section className="progress-report-tma-fallback report-screen-only" role="status">
          <strong>
            {tmaDownload.status === 'accepted'
              ? 'Telegram открыл сохранение PDF.'
              : tmaDownload.status === 'cancelled'
                ? 'Сохранение PDF отменено.'
                : tmaDownload.status === 'fallback'
                  ? 'Откройте готовый PDF по ссылке.'
                  : 'Не удалось подготовить PDF.'}
          </strong>
          <p>Ссылка короткоживущая и содержит только этот отчёт.</p>
          {tmaDownload.url && tmaDownload.status !== 'accepted' && (
            <a href={tmaDownload.url} rel="noreferrer" target="_blank">
              Скачать PDF
            </a>
          )}
        </section>
      )}

      {handoffId === null && auth?.user?.trainer && !clientId && (
        <ReportHandoffPanel
          dateFrom={applied.dateFrom}
          dateTo={applied.dateTo}
          loading={displayFetching}
          period={applied.period}
          report={displayReport}
          trainer={auth.user.trainer}
        />
      )}

      {handoffId === null && displayReport.training.exercises.length > 0 && (
        <fieldset className="progress-report-exercise-picker report-screen-only">
          <legend>Упражнения в печатном отчёте</legend>
          <p>Выберите до четырёх. Значения показывают только записанные рабочие подходы.</p>
          {displayReport.training.exercises.slice(0, 8).map((exercise) => {
            const selected = selectedExercises.includes(exercise.exercise_title);
            return (
              <label key={exercise.exercise_title}>
                <input
                  checked={selected}
                  disabled={!selected && selectedExercises.length >= 4}
                  onChange={() =>
                    setExerciseSelections((current) => ({
                      ...current,
                      [reportKey]: selected
                        ? selectedExercises.filter((item) => item !== exercise.exercise_title)
                        : [...selectedExercises, exercise.exercise_title],
                    }))
                  }
                  type="checkbox"
                />
                <span>{exercise.exercise_title}</span>
              </label>
            );
          })}
        </fieldset>
      )}
    </>
  ) : null;

  return (
    <main className="progress-report-page">
      <div className="progress-report-toolbar report-screen-only">
        <AppLink className="progress-report-back" to={returnPath}>
          <Icon name="arrow-left" size={16} /> Назад
        </AppLink>
        <BrandLockup />
        <Button
          disabled={
            handoffId !== null ||
            !displayReport ||
            displayFetching ||
            tmaDownload.status === 'pending'
          }
          onClick={() => void printReport()}
          type="button"
        >
          <Icon name={isTma ? 'download' : 'print'} size={16} />{' '}
          {isTma
            ? tmaDownload.status === 'pending'
              ? 'Готовим PDF…'
              : 'Скачать PDF'
            : 'Печать / Сохранить как PDF'}
        </Button>
      </div>

      {displayLoading ? (
        <LoadingState label="Собираем фактический отчёт…" />
      ) : displayError ? (
        <ErrorState
          message={(displayError as Error).message}
          retry={() => void (handoffId !== null ? handoffView.refetch() : report.refetch())}
        />
      ) : displayReport ? (
        <>
          <ReportContent
            controls={controls}
            report={displayReport}
            selectedExercises={selectedExercises}
          />
          {handoffId === null && (
            <p className="progress-report-filename report-screen-only">
              Предлагаемое безопасное имя файла:{' '}
              <code>
                progress-report-{displayReport.period_start}_{displayReport.period_end}.pdf
              </code>
            </p>
          )}
        </>
      ) : null}
    </main>
  );
}
