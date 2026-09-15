import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { api, apiFile } from '../../shared/api/client';
import type { NutritionReport, NutritionReportPeriod } from '../../shared/api/types';
import { dateInputValue, formatCalendarDate } from '../../shared/dateTime';
import { AppLink } from '../../shared/navigation/router';
import { queryKeys } from '../../shared/queryKeys';
import { DateInput } from '../../shared/ui/PickerInput';
import { QuantitativeProgress, TimeSeriesChart } from '../../shared/ui/DataViz';
import { Icon } from '../../shared/ui/Icon';
import { NUTRITION_WEEK_LEGEND, WeekStrip, type WeekStripDayMeta } from '../../shared/ui/WeekStrip';
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  SegmentedControl,
} from '../../shared/ui/common';

const reportPeriods = [
  { value: 'days_1', label: 'День' },
  { value: 'days_7', label: '7 дней' },
  { value: 'days_30', label: '30 дней' },
  { value: 'days_90', label: '90 дней' },
  { value: 'days_365', label: 'Год' },
  { value: 'current_week', label: 'Эта неделя' },
  { value: 'current_month', label: 'Этот месяц' },
  { value: 'previous_month', label: 'Прошлый месяц' },
  { value: 'custom', label: 'Свой период' },
] as const;

const reportPeriodSet = new Set<NutritionReportPeriod>(reportPeriods.map((option) => option.value));

type DailyPoint = NutritionReport['daily'][number];
type MetricSummary = NutritionReport['summary']['calories'];
type TargetComparison = NutritionReport['summary']['calorie_comparison'];

const statusLabels: Record<DailyPoint['status'], string> = {
  complete: 'Заполнен',
  incomplete: 'Не завершён',
  fasted: 'Без приёмов пищи',
  missing: 'Нет данных',
};

const targetSourceLabels: Record<NutritionReport['target_changes'][number]['source'], string> = {
  calculated: 'Расчётная цель',
  manual: 'Ручная цель',
  trainer: 'Цель тренера',
  adaptive: 'Принятая адаптация',
};

function initialReportState(): {
  period: NutritionReportPeriod;
  dateFrom: string;
  dateTo: string;
} {
  const params = new URLSearchParams(window.location.search);
  const candidate = params.get('nutrition_period') as NutritionReportPeriod | null;
  const period = candidate && reportPeriodSet.has(candidate) ? candidate : 'days_30';
  const dateFrom = params.get('nutrition_from') ?? '';
  const dateTo = params.get('nutrition_to') ?? '';
  if (period === 'custom' && (!dateFrom || !dateTo)) {
    return { period: 'days_30', dateFrom: '', dateTo: '' };
  }
  return { period, dateFrom, dateTo };
}

function reportPath(
  period: NutritionReportPeriod,
  dateFrom: string,
  dateTo: string,
  csv = false,
  clientId?: number,
): string {
  const params = new URLSearchParams({ period });
  if (period === 'custom') {
    params.set('date_from', dateFrom);
    params.set('date_to', dateTo);
  }
  const base =
    clientId == null
      ? '/api/v1/workouts/progress/nutrition-report'
      : `/api/v1/coach/clients/${clientId}/nutrition-report`;
  return `${base}${csv ? '.csv' : ''}?${params}`;
}

function syncReportUrl(period: NutritionReportPeriod, dateFrom: string, dateTo: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set('section', 'progress');
  url.searchParams.set('nutrition_period', period);
  if (period === 'custom') {
    url.searchParams.set('nutrition_from', dateFrom);
    url.searchParams.set('nutrition_to', dateTo);
  } else {
    url.searchParams.delete('nutrition_from');
    url.searchParams.delete('nutrition_to');
  }
  window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
}

function formatNumber(value: number | null | undefined, digits = 1): string {
  return value == null
    ? '—'
    : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(value);
}

function formatDate(value: string, withYear = false): string {
  return formatCalendarDate(value, {
    day: 'numeric',
    month: 'short',
    ...(withYear ? { year: 'numeric' } : {}),
  });
}

function periodLabel(report: NutritionReport): string {
  return `${formatDate(report.period_start, true)} — ${formatDate(report.period_end, true)}`;
}

function diaryLink(date: string): string {
  const returnTo = `${window.location.pathname}${window.location.search}#nutrition-period-report`;
  const params = new URLSearchParams({
    section: 'nutrition',
    date,
    return_to: returnTo,
  });
  return `/app?${params}`;
}

function weekMeta(
  point: DailyPoint | undefined,
  dayLink: ((date: string) => string) | null,
): WeekStripDayMeta {
  if (!point) {
    return { status: { key: 'upcoming', label: 'Вне выбранного периода' } };
  }
  const targetChange = point.target_changed ? ', цель изменилась' : '';
  const status = {
    complete: { key: 'completed' as const, label: `Заполнен${targetChange}` },
    incomplete: {
      key: 'in-progress' as const,
      pictogram: 'nutrition-incomplete' as const,
      label: `Не завершён${targetChange}`,
    },
    fasted: {
      key: 'completed' as const,
      pictogram: 'fasted' as const,
      label: `Отмечен день без приёмов пищи${targetChange}`,
    },
    missing: {
      key: 'neutral' as const,
      pictogram: 'missing' as const,
      label: `Нет данных${targetChange}`,
    },
  }[point.status];
  return {
    status,
    ...(dayLink
      ? { link: { label: 'Открыть дневник за этот день', to: dayLink(point.diary_date) } }
      : {}),
  };
}

function CoverageSummary({ report }: { report: NutritionReport }) {
  const { summary } = report;
  return (
    <div className="nutrition-report-coverage">
      <div>
        <span>Полнота дневника</span>
        <strong>
          Заполнено {summary.logged_days} из {summary.eligible_days} дней
        </strong>
        <p>Средние значения рассчитаны только по заполненным дням.</p>
      </div>
      <QuantitativeProgress
        label="Покрытие периода"
        maximum={100}
        unit="%"
        value={summary.coverage_percent}
      />
      <p className="nutrition-report-coverage__details">
        {summary.incomplete_days} не завершено · {summary.missing_days} без данных ·{' '}
        {summary.fasted_days} отмечено без приёмов пищи
      </p>
    </div>
  );
}

function MetricRow({
  comparison,
  label,
  metric,
  unit,
}: {
  comparison: TargetComparison;
  label: string;
  metric: MetricSummary;
  unit: string;
}) {
  const deviation = comparison.average_deviation;
  return (
    <div className="nutrition-report-metric">
      <dt>{label}</dt>
      <dd>
        <strong>
          {formatNumber(metric.average, 0)} <span>{unit}</span>
        </strong>
        <small>
          {metric.sample_days
            ? `минимум ${formatNumber(metric.minimum, 0)} · максимум ${formatNumber(metric.maximum, 0)} · по ${metric.sample_days} дн.`
            : 'Нет данных по показателю'}
        </small>
      </dd>
      <dd>
        <span>Ориентир в среднем</span>
        <strong>
          {formatNumber(comparison.average_target, 0)}{' '}
          {comparison.average_target == null ? '' : <span>{unit}</span>}
        </strong>
        <small>
          {comparison.evaluated_days
            ? `сравнено ${comparison.evaluated_days} дн.`
            : 'Нет сопоставимых дней'}
        </small>
      </dd>
      <dd>
        <span>Отклонение</span>
        <strong>
          {deviation != null && deviation > 0 ? '+' : ''}
          {formatNumber(deviation, 0)} {deviation == null ? '' : <span>{unit}</span>}
        </strong>
      </dd>
    </div>
  );
}

function ReportMetrics({ report }: { report: NutritionReport }) {
  const { summary } = report;
  return (
    <dl className="nutrition-report-metrics" aria-label="Средние КБЖУ и ориентиры">
      <MetricRow
        label="Калории"
        metric={summary.calories}
        comparison={summary.calorie_comparison}
        unit="ккал"
      />
      <MetricRow
        label="Белок"
        metric={summary.protein_g}
        comparison={summary.protein_comparison}
        unit="г"
      />
      <MetricRow label="Жиры" metric={summary.fat_g} comparison={summary.fat_comparison} unit="г" />
      <MetricRow
        label="Углеводы"
        metric={summary.carbs_g}
        comparison={summary.carbs_comparison}
        unit="г"
      />
    </dl>
  );
}

function NutritionChart({
  dayLink,
  report,
}: {
  dayLink: ((date: string) => string) | null;
  report: NutritionReport;
}) {
  return (
    <TimeSeriesChart
      ariaLabel={`Калории по дням за период ${periodLabel(report)}`}
      includeZero
      metric="Калории по дням"
      note="Точки — фактические значения завершённых дней; пропуски не соединяются, пунктир показывает ориентир."
      period={periodLabel(report)}
      points={report.daily.map((point) => ({
        href:
          dayLink && ['complete', 'fasted'].includes(point.status)
            ? dayLink(point.diary_date)
            : undefined,
        key: point.diary_date,
        label: formatDate(point.diary_date),
        status: statusLabels[point.status],
        target: point.target_calories,
        targetChanged: point.target_changed,
        value:
          ['complete', 'fasted'].includes(point.status) && point.calories != null
            ? point.calories
            : null,
      }))}
      targetLabel="Ориентир"
      unit="ккал"
    />
  );
}

function TargetChanges({ report }: { report: NutritionReport }) {
  if (!report.target_changes.length) return null;
  return (
    <div className="nutrition-report-targets">
      <h3>Изменения цели в периоде</h3>
      <ol>
        {report.target_changes.map((target) => (
          <li key={`${target.effective_from}-${target.source}`}>
            <time dateTime={target.effective_from}>{formatDate(target.effective_from, true)}</time>
            <strong>{targetSourceLabels[target.source]}</strong>
            <span>
              {target.calories} ккал · Б {target.protein_g} · Ж {target.fat_g} · У {target.carbs_g}{' '}
              г
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function DailyTable({
  dayLink,
  report,
}: {
  dayLink: ((date: string) => string) | null;
  report: NutritionReport;
}) {
  return (
    <details
      className="nutrition-report-days"
      open={report.daily.length <= 30 && report.summary.logged_days > 0}
    >
      <summary>Дни периода: {report.daily.length}</summary>
      <div className="nutrition-report-days__table-wrap">
        <table>
          <caption className="sr-only">
            Дневные КБЖУ, статус заполнения и действовавшая цель
          </caption>
          <thead>
            <tr>
              <th>Дата</th>
              <th>Статус</th>
              <th>Калории</th>
              <th>Б / Ж / У</th>
              <th>Цель</th>
              {dayLink && (
                <th>
                  <span className="sr-only">Действие</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {[...report.daily].reverse().map((point) => (
              <tr key={point.diary_date}>
                <td data-label="Дата">
                  <time dateTime={point.diary_date}>
                    {formatDate(point.diary_date, true)}
                    {point.is_current_day ? ' · сегодня' : ''}
                  </time>
                  {point.target_changed && <Badge>Новая цель</Badge>}
                </td>
                <td data-label="Статус">{statusLabels[point.status]}</td>
                <td data-label="Калории">
                  {point.calories == null ? '—' : `${formatNumber(point.calories, 0)} ккал`}
                </td>
                <td data-label="Б / Ж / У">
                  {point.protein_g == null
                    ? '—'
                    : `${formatNumber(point.protein_g, 0)} / ${formatNumber(point.fat_g, 0)} / ${formatNumber(point.carbs_g, 0)} г`}
                </td>
                <td data-label="Цель">
                  {point.target_calories == null ? 'Не задана' : `${point.target_calories} ккал`}
                </td>
                {dayLink && (
                  <td>
                    <AppLink
                      aria-label={`Открыть дневник за ${formatDate(point.diary_date, true)}`}
                      to={dayLink(point.diary_date)}
                    >
                      Открыть
                    </AppLink>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export type ControlledNutritionPeriod = {
  period: NutritionReportPeriod;
  dateFrom: string;
  dateTo: string;
};

export function NutritionPeriodReport({
  canExport = true,
  clientId,
  controlledPeriod,
  showSelector = true,
}: {
  canExport?: boolean;
  clientId?: number;
  controlledPeriod?: ControlledNutritionPeriod;
  showSelector?: boolean;
}) {
  const initial = useMemo(
    () =>
      clientId == null
        ? initialReportState()
        : { period: 'days_30' as const, dateFrom: '', dateTo: '' },
    [clientId],
  );
  const [period, setPeriod] = useState<NutritionReportPeriod>(initial.period);
  const [selectedPeriod, setSelectedPeriod] = useState<NutritionReportPeriod>(initial.period);
  const [dateFrom, setDateFrom] = useState(initial.dateFrom);
  const [dateTo, setDateTo] = useState(initial.dateTo);
  const [customError, setCustomError] = useState('');
  const [exportState, setExportState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');
  const dayLink = clientId == null ? diaryLink : null;
  const activePeriod = controlledPeriod?.period ?? period;
  const activeDateFrom = controlledPeriod?.dateFrom ?? dateFrom;
  const activeDateTo = controlledPeriod?.dateTo ?? dateTo;
  const visibleSelectedPeriod = controlledPeriod?.period ?? selectedPeriod;
  const visibleDateFrom = controlledPeriod?.dateFrom ?? dateFrom;
  const visibleDateTo = controlledPeriod?.dateTo ?? dateTo;
  const report = useQuery({
    queryKey: queryKeys.progress.nutritionReport(
      clientId ?? 'me',
      activePeriod,
      activeDateFrom,
      activeDateTo,
    ),
    queryFn: () =>
      api<NutritionReport>(reportPath(activePeriod, activeDateFrom, activeDateTo, false, clientId)),
    placeholderData: keepPreviousData,
  });
  const today = report.data
    ? dateInputValue(new Date(), report.data.timezone)
    : dateInputValue(new Date());

  function selectPeriod(value: string): void {
    const next = value as NutritionReportPeriod;
    setSelectedPeriod(next);
    setCustomError('');
    if (next === 'custom') {
      setDateFrom((current) => current || report.data?.period_start || today);
      setDateTo((current) => current || report.data?.period_end || today);
      return;
    }
    setPeriod(next);
    setDateFrom('');
    setDateTo('');
    if (clientId == null) syncReportUrl(next, '', '');
  }

  function applyCustomPeriod(): void {
    if (!dateFrom || !dateTo) {
      setCustomError('Укажите дату начала и окончания.');
      return;
    }
    const days =
      Math.floor(
        (Date.parse(`${dateTo}T00:00:00Z`) - Date.parse(`${dateFrom}T00:00:00Z`)) / 86_400_000,
      ) + 1;
    if (days < 1) {
      setCustomError('Дата окончания не может быть раньше даты начала.');
      return;
    }
    if (days > 366) {
      setCustomError('Период не может превышать 366 дней.');
      return;
    }
    if (dateTo > today) {
      setCustomError('Отчёт нельзя построить за будущие даты.');
      return;
    }
    setCustomError('');
    setPeriod('custom');
    if (clientId == null) syncReportUrl('custom', dateFrom, dateTo);
  }

  async function downloadCsv(): Promise<void> {
    setExportState('loading');
    try {
      const file = await apiFile(
        reportPath(activePeriod, activeDateFrom, activeDateTo, true, clientId),
      );
      const url = URL.createObjectURL(file.blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = file.filename ?? 'nutrition-report.csv';
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setExportState('done');
    } catch {
      setExportState('error');
    }
  }

  const pointsByDate = new Map(report.data?.daily.map((point) => [point.diary_date, point]));
  const showWeek = report.data && ['days_7', 'current_week'].includes(report.data.period);

  return (
    <section
      className="progress-section nutrition-period-report"
      id="nutrition-period-report"
      aria-labelledby="nutrition-period-report-title"
    >
      <header className="progress-section__head nutrition-period-report__head">
        <div>
          <span className="progress-section__eyebrow">Фактический дневник</span>
          <h2 id="nutrition-period-report-title">Отчёт по питанию</h2>
          <p>Полнота данных, КБЖУ и цели, которые действовали в каждый день периода.</p>
        </div>
        <Button
          disabled={!canExport || !report.data || exportState === 'loading'}
          onClick={() => void downloadCsv()}
          type="button"
          variant="secondary"
        >
          {exportState === 'loading' ? (
            'Готовим CSV…'
          ) : (
            <>
              <Icon name="download" size={16} /> Скачать CSV
            </>
          )}
        </Button>
      </header>
      {!canExport && (
        <p className="muted demo-capability-notice" role="status">
          Выгрузка отчёта доступна после входа.
        </p>
      )}

      {showSelector && (
        <>
          <div className="nutrition-period-report__selector">
            <SegmentedControl
              ariaLabel="Период отчёта по питанию"
              value={selectedPeriod}
              options={reportPeriods}
              onChange={selectPeriod}
            />
          </div>
          <p className="nutrition-period-report__selector-hint" aria-hidden="true">
            Ещё периоды — свайпните влево
          </p>
        </>
      )}
      {showSelector && visibleSelectedPeriod === 'custom' && (
        <div
          className="nutrition-period-report__custom"
          aria-describedby={customError ? 'nutrition-report-custom-error' : undefined}
        >
          <Field label="Начало периода" labelFor="nutrition-report-from">
            <DateInput
              id="nutrition-report-from"
              max={visibleDateTo || today}
              onChange={(event) => setDateFrom(event.target.value)}
              value={visibleDateFrom}
            />
          </Field>
          <Field label="Конец периода" labelFor="nutrition-report-to">
            <DateInput
              id="nutrition-report-to"
              max={today}
              min={visibleDateFrom}
              onChange={(event) => setDateTo(event.target.value)}
              value={visibleDateTo}
            />
          </Field>
          <Button onClick={applyCustomPeriod} type="button" variant="secondary">
            Показать период
          </Button>
          {customError && (
            <p className="ui-field__error" id="nutrition-report-custom-error" role="alert">
              {customError}
            </p>
          )}
        </div>
      )}

      {report.isLoading && !report.data ? (
        <LoadingState label="Собираем отчёт по питанию…" />
      ) : report.error && !report.data ? (
        <ErrorState message={(report.error as Error).message} retry={() => void report.refetch()} />
      ) : report.data ? (
        <>
          <div className="nutrition-period-report__period">
            <strong>{periodLabel(report.data)}</strong>
            <span>Часовой пояс: {report.data.timezone}</span>
            {report.isFetching && <span role="status">Обновляем данные…</span>}
          </div>
          {report.error && (
            <ErrorState
              message={(report.error as Error).message}
              retry={() => void report.refetch()}
            />
          )}
          <CoverageSummary report={report.data} />
          {report.data.hydration && (
            <section
              className="nutrition-hydration-report"
              aria-labelledby="hydration-report-title"
            >
              <div>
                <span className="progress-section__eyebrow">Фактические напитки</span>
                <h3 id="hydration-report-title">Гидратация</h3>
                <p>
                  В среднем <strong>{report.data.hydration.average_ml ?? 0} мл</strong> в записанный
                  день · покрытие {report.data.hydration.coverage_percent}%.
                </p>
              </div>
              <dl>
                <div>
                  <dt>Всего</dt>
                  <dd>{report.data.hydration.total_ml} мл</dd>
                </div>
                <div>
                  <dt>Дни с записями</dt>
                  <dd>
                    {report.data.hydration.logged_days} из {report.data.hydration.eligible_days}
                  </dd>
                </div>
                <div>
                  <dt>Ориентир достигнут</dt>
                  <dd>
                    {report.data.hydration.days_meeting_goal} из{' '}
                    {report.data.hydration.goal_evaluated_days}
                  </dd>
                </div>
                <div>
                  <dt>Изменение среднего</dt>
                  <dd>
                    {report.data.hydration.trend_ml == null
                      ? 'Недостаточно данных'
                      : `${report.data.hydration.trend_ml > 0 ? '+' : ''}${report.data.hydration.trend_ml} мл`}
                  </dd>
                </div>
              </dl>
              <p className="progress-note">
                Тренд описывает только внесённые объёмы и не является оценкой состояния гидратации.
              </p>
            </section>
          )}
          {showWeek && (
            <WeekStrip
              anchorDate={report.data.period_start}
              ariaLabel="Дни отчёта по питанию"
              getDayMeta={(date) => weekMeta(pointsByDate.get(date), dayLink)}
              legend={NUTRITION_WEEK_LEGEND}
              mode="overview"
              rangeStart={report.data.period_start}
              title="Дни отчёта"
              today={report.data.daily.find((point) => point.is_current_day)?.diary_date ?? ''}
            />
          )}
          {report.data.summary.logged_days === 0 ? (
            <div className="nutrition-period-report__empty">
              <EmptyState
                title="Нет заполненных дней за период"
                text="Неполные дни и отсутствие записей не превращаются в нулевые значения."
              />
              {clientId == null && (
                <AppLink className="button-link" to="/app?section=nutrition">
                  Открыть дневник питания
                </AppLink>
              )}
            </div>
          ) : (
            <>
              <ReportMetrics report={report.data} />
              <div className="nutrition-report-adherence" aria-label="Сравнение с целью">
                <p>
                  <strong>
                    {report.data.summary.days_within_calorie_tolerance} из{' '}
                    {report.data.summary.calorie_tolerance_evaluated_days}
                  </strong>
                  <span>дней в пределах ±10% ориентира калорий</span>
                </p>
                <p>
                  <strong>
                    {report.data.summary.days_meeting_protein_target} из{' '}
                    {report.data.summary.protein_target_evaluated_days}
                  </strong>
                  <span>дней с достигнутым ориентиром белка</span>
                </p>
              </div>
              <NutritionChart
                dayLink={dayLink}
                key={`${report.data.period_start}-${report.data.period_end}`}
                report={report.data}
              />
            </>
          )}
          <TargetChanges report={report.data} />
          <DailyTable dayLink={dayLink} report={report.data} />
          <p className="progress-note nutrition-period-report__methodology">
            Отчёт описывает только записи КБЖУ. Он не оценивает качество рациона, витамины, здоровье
            или причины изменения веса. Неполные дни видны в списке, но не входят в средние и
            сравнение с целью.
          </p>
        </>
      ) : null}
      <span aria-live="polite" className="sr-only">
        {exportState === 'done'
          ? 'CSV отчёт скачан.'
          : exportState === 'error'
            ? 'Не удалось скачать CSV отчёт.'
            : ''}
      </span>
    </section>
  );
}
