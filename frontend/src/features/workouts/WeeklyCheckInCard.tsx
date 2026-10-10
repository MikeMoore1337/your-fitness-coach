import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  EnergyCalibration,
  ProgressWeeklyAction,
  WeeklyCheckInCurrent,
  WeeklyCheckInHistory,
  WeeklyCheckInSubmit,
  WeeklyPlanningAdjustment,
  WeeklyPlanningReview,
  WeeklyPlanningReviewConfirmResponse,
} from '../../shared/api/types';
import { formatCalendarDate } from '../../shared/dateTime';
import { invalidateNutritionSummaries } from '../../shared/queryKeys';
import { usePersistentState } from '../../shared/storage';
import { weeklyReviewDraftStorageKey } from '../../shared/userScopedStorage';
import { Badge, Card, DisclosureIcon, ErrorState, LoadingState } from '../../shared/ui/common';
import { DataConfidence } from '../../shared/ui/DataConfidence';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Icon } from '../../shared/ui/Icon';
import { AppLink } from '../../shared/navigation/router';
import {
  productEventSurface,
  trackCoreProductEvent,
  trackProductEvent,
} from '../../shared/analytics/productEvents';

const scoreOptions = [1, 2, 3, 4, 5] as const;

type ReviewStep = 'facts' | 'questions' | 'adjustment';
type ScoreField = 'training_load' | 'recovery' | 'hunger' | 'adherence_difficulty';

interface WeeklyReviewDraft {
  weekStart: string | null;
  step: ReviewStep;
  training_load: string;
  recovery: string;
  hunger: string;
  adherence_difficulty: string;
  note: string;
  selectedLowDays: string[];
  calibration: EnergyCalibration | null;
}

const emptyDraft: WeeklyReviewDraft = {
  weekStart: null,
  step: 'facts',
  training_load: '',
  recovery: '',
  hunger: '',
  adherence_difficulty: '',
  note: '',
  selectedLowDays: [],
  calibration: null,
};

const calibrationStatusLabels: Record<EnergyCalibration['status'], string> = {
  insufficient: 'Данных пока недостаточно',
  limited: 'Данные пока нестабильны',
  no_change: 'Изменение не требуется',
  pending: 'Есть предложение',
  accepted: 'Новая цель принята',
  rejected: 'Текущая цель сохранена',
  superseded: 'Предложение устарело',
};

const targetSourceLabels = {
  calculated: 'Расчёт',
  manual: 'Вручную',
  trainer: 'Тренер',
  adaptive: 'Адаптивная проверка',
} as const;

function formatPeriod(start: string, end: string): string {
  const format = (value: string) =>
    formatCalendarDate(value, {
      day: 'numeric',
      month: 'short',
    });
  return `${format(start)} — ${format(end)}`;
}

function formatDate(value: string): string {
  return formatCalendarDate(value, { day: 'numeric', month: 'long', year: 'numeric' });
}

function formatKcal(value: { energy_kcal: string | number } | null | undefined): string {
  return value ? `${Math.round(Number(value.energy_kcal))} ккал` : 'нет записей';
}

function planningAvailabilityLabel(value: WeeklyPlanningReview['availability']): string {
  switch (value) {
    case 'available':
      return 'Факты доступны';
    case 'no_plan':
      return 'Плана нет';
    case 'no_target':
      return 'Цель не задана';
    case 'no_data':
      return 'Пока нет данных';
  }
}

function planningRequestKey(weekStart: string, adjustments: WeeklyPlanningAdjustment[]): string {
  return `weekly-review-plan-${weekStart}-${adjustments.map((item) => item.source_date).join('-')}`;
}

function optionalScore(value: string): number | null {
  return value ? Number(value) : null;
}

function measurementCount(value: number): string {
  const lastTwo = Math.abs(value) % 100;
  const last = lastTwo % 10;
  const word =
    lastTwo > 10 && lastTwo < 20
      ? 'замеров'
      : last === 1
        ? 'замер'
        : last >= 2 && last <= 4
          ? 'замера'
          : 'замеров';
  return `${value} ${word}`;
}

function progressWeeklyActionHref(action: ProgressWeeklyAction): string | null {
  switch (action.target) {
    case 'today':
      return '/app?section=today';
    case 'nutrition':
      return '/app?section=nutrition';
    case 'body':
      return '/app?section=progress&progress_view=body';
    case 'progress':
      return '/app?section=progress';
    case 'weekly_review':
      return '/app?section=progress&progress_view=wellbeing';
  }
}

function questionFields(current: WeeklyCheckInCurrent): Array<{
  key: ScoreField;
  label: string;
  hint: string;
}> {
  const fields: Array<{ key: ScoreField; label: string; hint: string }> = [
    {
      key: 'recovery',
      label: 'Как вы восстанавливались на этой неделе?',
      hint: '1 — плохо, 5 — отлично',
    },
    {
      key: 'hunger',
      label: 'Насколько часто мешал голод?',
      hint: '1 — почти не мешал, 5 — мешал очень часто',
    },
  ];
  if (current.summary.training.completed_workouts > 0) {
    fields.push({
      key: 'training_load',
      label: 'Насколько тяжёлой ощущалась тренировочная неделя?',
      hint: '1 — легко, 5 — очень тяжело',
    });
  }
  if (
    current.summary.nutrition.current_target ||
    current.summary.nutrition.incomplete_days > 0 ||
    current.summary.training.planned_workouts > current.summary.training.completed_workouts
  ) {
    fields.push({
      key: 'adherence_difficulty',
      label: 'Насколько сложно было следовать плану?',
      hint: '1 — легко, 5 — очень сложно',
    });
  }
  return fields.slice(0, 4);
}

function macroLine(calibration: EnergyCalibration, proposed: boolean): string | null {
  const protein = proposed
    ? calibration.proposed_target_protein_g
    : calibration.current_target_protein_g;
  const fat = proposed ? calibration.proposed_target_fat_g : calibration.current_target_fat_g;
  const carbs = proposed ? calibration.proposed_target_carbs_g : calibration.current_target_carbs_g;
  if (protein == null || fat == null || carbs == null) return null;
  return `Б ${protein} г · Ж ${fat} г · У ${carbs} г`;
}

export function WeeklyCheckInCard({
  autoFocus = false,
  userId,
}: {
  autoFocus?: boolean;
  userId: number | 'anonymous';
}) {
  const queryClient = useQueryClient();
  const { toast, confirm } = useFeedback();
  const [draft, setDraft, clearDraft] = usePersistentState<WeeklyReviewDraft>(
    weeklyReviewDraftStorageKey(userId),
    emptyDraft,
  );
  const cardRef = useRef<HTMLDivElement>(null);
  const current = useQuery({
    queryKey: ['weekly-check-ins', 'current'],
    queryFn: () => api<WeeklyCheckInCurrent>('/api/v1/check-ins/weekly/current'),
  });
  const history = useQuery({
    queryKey: ['weekly-check-ins', 'history'],
    queryFn: () => api<WeeklyCheckInHistory>('/api/v1/check-ins/weekly?limit=4&offset=0'),
  });

  useEffect(() => {
    if (!current.data || current.data.week_start === draft.weekStart) return;
    setDraft({ ...emptyDraft, weekStart: current.data.week_start });
  }, [current.data, draft.weekStart, setDraft]);

  const submit = useMutation({
    mutationFn: (payload: WeeklyCheckInSubmit) =>
      api('/api/v1/check-ins/weekly', { method: 'POST', body: payload }),
    onSuccess: async (_result, payload) => {
      const surface = productEventSurface();
      if (payload.status === 'skipped') {
        trackProductEvent({ name: 'weekly_review_skipped', surface });
      } else {
        trackProductEvent({ name: 'check_in_logged', surface });
        trackCoreProductEvent(
          { name: 'weekly_review_completed', surface },
          'weekly_review_completed',
        );
      }
      clearDraft({ ...emptyDraft, weekStart: current.data?.week_start ?? null });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['weekly-check-ins'] }),
        queryClient.invalidateQueries({ queryKey: ['notifications'] }),
        invalidateNutritionSummaries(queryClient),
      ]);
      toast(payload.status === 'skipped' ? 'Недельный обзор пропущен' : 'Недельный обзор сохранён');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const preview = useMutation({
    mutationFn: () =>
      api<EnergyCalibration>('/api/v1/nutrition/energy-calibration/preview', {
        method: 'POST',
      }),
    onSuccess: (calibration) =>
      setDraft((value) => ({ ...value, step: 'adjustment', calibration })),
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const decision = useMutation({
    mutationFn: ({ id, value }: { id: number; value: 'accept' | 'reject' }) =>
      api<EnergyCalibration>(`/api/v1/nutrition/energy-calibration/${id}/decision`, {
        method: 'POST',
        body: { decision: value },
      }),
    onSuccess: async (calibration, variables) => {
      trackProductEvent({
        name:
          variables.value === 'accept'
            ? 'weekly_review_proposal_accepted'
            : 'weekly_review_proposal_rejected',
        surface: productEventSurface(),
      });
      setDraft((value) => ({ ...value, calibration }));
      if (calibration.status === 'accepted') await invalidateNutritionSummaries(queryClient);
      finishReview(calibration);
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const markIncomplete = useMutation({
    mutationFn: async (dates: string[]) => {
      await Promise.all(
        dates.map((diaryDate) =>
          api('/api/v1/nutrition/diary/status', {
            method: 'PUT',
            body: { diary_date: diaryDate, status: 'incomplete' },
          }),
        ),
      );
    },
    onSuccess: async () => {
      trackProductEvent({
        name: 'nutrition_incomplete_day_confirmed',
        surface: productEventSurface(),
      });
      setDraft((value) => ({ ...value, selectedLowDays: [], calibration: null }));
      await queryClient.invalidateQueries({ queryKey: ['weekly-check-ins', 'current'] });
      toast('Выбранные дни отмечены как неполные');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const planningConfirm = useMutation({
    mutationFn: (adjustments: WeeklyPlanningAdjustment[]) =>
      api<WeeklyPlanningReviewConfirmResponse>('/api/v1/check-ins/weekly/planning-review/confirm', {
        method: 'POST',
        headers: {
          'Idempotency-Key': planningRequestKey(current.data?.week_start ?? 'unknown', adjustments),
        },
        body: {
          week_start: current.data?.week_start,
          adjustments,
        },
      }),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['weekly-check-ins'] }),
        queryClient.invalidateQueries({ queryKey: ['nutrition', 'plans'] }),
      ]);
      toast(
        result.replayed
          ? 'Перенос уже был подтверждён'
          : 'Незавершённое добавлено в следующий план',
      );
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  function finishReview(calibration: EnergyCalibration | null = draft.calibration): void {
    submit.mutate({
      status: 'completed',
      training_load: optionalScore(draft.training_load),
      recovery: optionalScore(draft.recovery),
      hunger: optionalScore(draft.hunger),
      adherence_difficulty: optionalScore(draft.adherence_difficulty),
      note: draft.note.trim() || null,
      energy_calibration_id: calibration?.id ?? null,
    });
  }

  function openAdjustment(skipQuestions = false): void {
    const next = skipQuestions
      ? {
          ...draft,
          training_load: '',
          recovery: '',
          hunger: '',
          adherence_difficulty: '',
          note: '',
          step: 'adjustment' as const,
        }
      : { ...draft, step: 'adjustment' as const };
    setDraft(next);
    if (!next.calibration) preview.mutate();
  }

  useEffect(() => {
    if (
      !autoFocus ||
      current.isLoading ||
      !current.data ||
      draft.weekStart !== current.data.week_start ||
      document.activeElement !== document.body
    )
      return;
    cardRef.current?.focus({ preventScroll: true });
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    cardRef.current
      ?.closest('.card')
      ?.scrollIntoView?.({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  }, [autoFocus, current.data, current.isLoading, draft.weekStart]);

  if (current.isLoading) return <LoadingState label="Собираем итоги недели…" />;
  if (current.error) {
    return (
      <ErrorState message={(current.error as Error).message} retry={() => void current.refetch()} />
    );
  }
  if (!current.data) return null;
  if (draft.weekStart !== current.data.week_start) {
    return <LoadingState label="Восстанавливаем недельный обзор…" />;
  }

  const { summary, existing } = current.data;
  const progressAction = current.data.progress_action;
  const target = summary.nutrition.current_target;
  const planningReview = summary.nutrition.planning_review;
  const planningProposals = planningReview?.proposals ?? [];
  const repeatedPlanningMisses = planningReview?.repeated_miss_dates ?? [];
  const weightSignal = summary.data_sufficiency.weight_trend;
  const weightPoints = Number(weightSignal.counters.point_count ?? 0);
  const questions = questionFields(current.data);
  const calibration = draft.calibration;
  const suspiciousLowDays = summary.nutrition.suspicious_low_days ?? [];
  const isBusy =
    submit.isPending || preview.isPending || decision.isPending || planningConfirm.isPending;

  return (
    <Card
      className="weekly-review-card"
      title="Итоги недели"
      description={`${formatPeriod(summary.period_start, summary.period_end)} · ${current.data.timezone}`}
      collapsible={!autoFocus}
    >
      <div id="weekly-review" ref={cardRef} tabIndex={-1} className="weekly-review stack top-gap">
        {existing ? (
          <>
            <div className="weekly-review__complete">
              <Badge>{existing.status === 'skipped' ? 'Пропущено' : 'Готово'}</Badge>
              <div>
                <strong>
                  {existing.status === 'skipped' ? 'Обзор этой недели пропущен' : 'Обзор сохранён'}
                </strong>
                <p className="muted">
                  {existing.status === 'skipped'
                    ? 'Цель питания не менялась.'
                    : existing.summary.adaptive_energy?.decision === 'accepted'
                      ? 'Новая цель была явно подтверждена.'
                      : 'Автоматических изменений цели не было.'}
                </p>
              </div>
            </div>
            {progressAction && (
              <div className="weekly-review__complete" aria-live="polite">
                <Badge>
                  {progressAction.status === 'completed'
                    ? 'Шаг подтверждён'
                    : progressAction.status === 'unavailable'
                      ? 'Без отдельного шага'
                      : 'Следующий шаг'}
                </Badge>
                <div>
                  <strong>{progressAction.title}</strong>
                  <p className="muted">{progressAction.detail}</p>
                  {progressAction.status === 'available' &&
                    progressWeeklyActionHref(progressAction) && (
                      <AppLink
                        className="button-link secondary-link"
                        to={progressWeeklyActionHref(progressAction) ?? '/app?section=progress'}
                      >
                        Открыть действие
                      </AppLink>
                    )}
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            <ol className="weekly-review__steps" aria-label="Шаги недельного обзора">
              {[
                ['facts', 'Факты'],
                ['questions', 'Уточнения'],
                ['adjustment', 'Решение'],
              ].map(([step, label], index) => (
                <li key={step} aria-current={draft.step === step ? 'step' : undefined}>
                  <span aria-hidden="true">{index + 1}</span>
                  <strong>{label}</strong>
                </li>
              ))}
            </ol>

            {draft.step === 'facts' && (
              <section className="stack" aria-labelledby="weekly-facts-heading">
                <div>
                  <h3 id="weekly-facts-heading">Что известно приложению</h3>
                  <p className="muted">
                    Факты собраны на {formatDate(current.data.submitted_on)}. Отсутствующий день не
                    считается нулевым потреблением.
                  </p>
                </div>
                <div className="weekly-review__facts" aria-label="Ключевые факты недели">
                  <div>
                    <span>Тренировки</span>
                    <strong>
                      {summary.training.completed_workouts} из {summary.training.planned_workouts}
                    </strong>
                    <small>завершено по плану</small>
                  </div>
                  <div>
                    <span>Динамика массы</span>
                    <strong>{measurementCount(weightPoints)}</strong>
                    <small>за окно тренда</small>
                  </div>
                </div>
                <DataConfidence kind="weight" signal={weightSignal} />
                <dl className="weekly-review__coverage" aria-label="Полнота дневника питания">
                  <div>
                    <dt>Полных</dt>
                    <dd>{summary.nutrition.complete_days}</dd>
                  </div>
                  <div>
                    <dt>Неполных</dt>
                    <dd>{summary.nutrition.incomplete_days}</dd>
                  </div>
                  <div>
                    <dt>Без еды</dt>
                    <dd>{summary.nutrition.fasted_days}</dd>
                  </div>
                  <div>
                    <dt>Без записей</dt>
                    <dd>{summary.nutrition.unlogged_days}</dd>
                  </div>
                </dl>
                {planningReview && planningReview.availability !== 'no_data' && (
                  <section
                    className="weekly-review__planning"
                    aria-labelledby="weekly-planning-heading"
                  >
                    <div className="weekly-review__planning-heading">
                      <div>
                        <span className="eyebrow">План питания</span>
                        <h3 id="weekly-planning-heading">План и факт</h3>
                      </div>
                      <Badge>{planningAvailabilityLabel(planningReview.availability)}</Badge>
                    </div>
                    <p className="muted">
                      Плановые блюда и записи дневника показаны отдельно. Приложение не делает
                      выводов о здоровье и не изменяет дневник автоматически.
                    </p>
                    <dl className="weekly-review__planning-stats" aria-label="Сводка плана питания">
                      <div>
                        <dt>План</dt>
                        <dd>{formatKcal(planningReview.planned_total)}</dd>
                      </div>
                      <div>
                        <dt>Факт</dt>
                        <dd>{formatKcal(planningReview.consumed_total)}</dd>
                      </div>
                      <div>
                        <dt>Цель</dt>
                        <dd>{formatKcal(planningReview.target_total)}</dd>
                      </div>
                    </dl>
                    <div className="weekly-review__planning-days" aria-label="План и факт по дням">
                      {planningReview.days
                        .filter((day) => day.observed)
                        .map((day) => (
                          <div className="weekly-review__planning-day" key={day.diary_date}>
                            <strong>
                              {formatCalendarDate(day.diary_date, {
                                weekday: 'short',
                                day: 'numeric',
                                month: 'short',
                              })}
                            </strong>
                            <span>
                              План: {day.planned_items > 0 ? formatKcal(day.planned) : 'нет плана'}
                            </span>
                            <span>
                              Факт: {formatKcal(day.consumed)}
                              {day.target ? ` / ${formatKcal(day.target)}` : ''}
                            </span>
                            <small>
                              {day.plan_status === 'partial'
                                ? `Осталось позиций: ${day.pending_items}`
                                : day.plan_status === 'complete'
                                  ? 'План закрыт'
                                  : 'Без плана'}
                            </small>
                          </div>
                        ))}
                    </div>
                    {repeatedPlanningMisses.length > 0 && (
                      <p className="weekly-review__notice">
                        В нескольких днях остались незавершённые позиции. Это факт о плане, а не
                        оценка состояния или готовности.
                      </p>
                    )}
                    {planningProposals.length > 0 && (
                      <div className="weekly-review__planning-proposal">
                        <strong>Предпросмотр следующего плана</strong>
                        <p className="muted">
                          Можно перенести незавершённые позиции на те же дни следующей недели. До
                          подтверждения ничего не меняется.
                        </p>
                        <ul>
                          {planningProposals.map((proposal) => (
                            <li key={proposal.source_date}>
                              {formatDate(proposal.source_date)} →{' '}
                              {formatDate(proposal.target_date)} · {proposal.pending_item_count}{' '}
                              поз.
                            </li>
                          ))}
                        </ul>
                        <button
                          type="button"
                          className="weekly-review__primary"
                          disabled={isBusy}
                          onClick={() => void confirmPlanningPlan(planningReview)}
                        >
                          {planningConfirm.isPending
                            ? 'Добавляем в следующий план…'
                            : 'Подтвердить перенос'}
                        </button>
                      </div>
                    )}
                  </section>
                )}
                {target ? (
                  <div className="weekly-review__target">
                    <div>
                      <span className="eyebrow">Текущая цель</span>
                      <strong>{target.calories} ккал</strong>
                      <p>
                        Б {target.protein_g} г · Ж {target.fat_g} г · У {target.carbs_g} г
                      </p>
                    </div>
                    <Badge>
                      {targetSourceLabels[target.source]} · с {formatDate(target.effective_from)}
                    </Badge>
                  </div>
                ) : (
                  <p className="weekly-review__notice">Текущая цель КБЖУ ещё не задана.</p>
                )}

                {suspiciousLowDays.length > 0 && (
                  <fieldset className="weekly-review__partial">
                    <legend>Проверьте необычно низкие дни</legend>
                    <p className="muted">
                      В эти дни записано меньше половины действовавшей цели. Приложение ничего не
                      меняет само: отметьте только действительно неполные дни. Осознанный день без
                      еды остаётся отдельным статусом.
                    </p>
                    {suspiciousLowDays.map((day) => (
                      <label key={day.diary_date}>
                        <input
                          type="checkbox"
                          checked={draft.selectedLowDays.includes(day.diary_date)}
                          onChange={(event) =>
                            setDraft((value) => ({
                              ...value,
                              selectedLowDays: event.target.checked
                                ? [...value.selectedLowDays, day.diary_date]
                                : value.selectedLowDays.filter((value) => value !== day.diary_date),
                            }))
                          }
                        />
                        <span>
                          <strong>{formatDate(day.diary_date)}</strong>
                          {day.calories} из {day.target_calories} ккал
                        </span>
                      </label>
                    ))}
                    <button
                      type="button"
                      className="secondary"
                      disabled={!draft.selectedLowDays.length || markIncomplete.isPending}
                      onClick={() => markIncomplete.mutate(draft.selectedLowDays)}
                    >
                      {markIncomplete.isPending ? 'Сохраняем…' : 'Отметить выбранные как неполные'}
                    </button>
                  </fieldset>
                )}

                <div className="button-row weekly-review__actions">
                  <button
                    type="button"
                    className="weekly-review__primary"
                    onClick={() => {
                      trackProductEvent({
                        name: 'weekly_review_started',
                        surface: productEventSurface(),
                      });
                      setDraft((value) => ({ ...value, step: 'questions' }));
                    }}
                  >
                    Всё верно, продолжить
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => void skipEntireReview()}
                  >
                    Пропустить обзор
                  </button>
                </div>
              </section>
            )}

            {draft.step === 'questions' && (
              <section className="stack" aria-labelledby="weekly-questions-heading">
                <div>
                  <h3 id="weekly-questions-heading">Короткие уточнения</h3>
                  <p className="muted">
                    Каждый ответ необязателен. Он помогает понять контекст, но сам не меняет цель.
                  </p>
                </div>
                <div className="form-grid">
                  {questions.map((field) => (
                    <label className="field" key={field.key}>
                      <span>{field.label}</span>
                      <select
                        value={draft[field.key]}
                        onChange={(event) =>
                          setDraft((value) => ({ ...value, [field.key]: event.target.value }))
                        }
                      >
                        <option value="">Пропустить вопрос</option>
                        {scoreOptions.map((score) => (
                          <option key={score} value={score}>
                            {score}
                          </option>
                        ))}
                      </select>
                      <small>{field.hint}</small>
                    </label>
                  ))}
                </div>
                <label className="field">
                  <span>Заметка о неделе</span>
                  <textarea
                    value={draft.note}
                    maxLength={2000}
                    rows={3}
                    placeholder="Что повлияло на питание, тренировки или восстановление?"
                    onChange={(event) =>
                      setDraft((value) => ({ ...value, note: event.target.value }))
                    }
                  />
                  <small>
                    Черновик сохраняется только на этом устройстве и очищается при выходе.
                  </small>
                </label>
                <div className="button-row weekly-review__actions">
                  <button
                    type="button"
                    className="weekly-review__primary"
                    disabled={preview.isPending}
                    onClick={() => openAdjustment()}
                  >
                    {preview.isPending ? 'Проверяем данные…' : 'Перейти к решению'}
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    disabled={preview.isPending}
                    onClick={() => openAdjustment(true)}
                  >
                    Пропустить вопросы
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setDraft((value) => ({ ...value, step: 'facts' }))}
                  >
                    Назад
                  </button>
                </div>
              </section>
            )}

            {draft.step === 'adjustment' && (
              <section className="stack" aria-labelledby="weekly-adjustment-heading">
                <div>
                  <h3 id="weekly-adjustment-heading">Решение по цели</h3>
                  <p className="muted">
                    Проверка использует заполненный дневник и сглаженный тренд массы за 28 дней. Это
                    оценка, а не точный TDEE.
                  </p>
                </div>
                {preview.isPending ? (
                  <LoadingState label="Сопоставляем питание и динамику массы…" />
                ) : preview.isError && !calibration ? (
                  <div className="weekly-review__notice" role="alert">
                    <strong>Не удалось выполнить проверку.</strong>
                    <p>
                      Цель не менялась. Можно повторить запрос или завершить обзор без изменения.
                    </p>
                    <div className="button-row">
                      <button type="button" onClick={() => preview.mutate()}>
                        Повторить
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => finishReview(null)}
                      >
                        Завершить без изменения
                      </button>
                    </div>
                  </div>
                ) : calibration ? (
                  <div className="weekly-review__calibration" aria-live="polite">
                    <div className="weekly-review__calibration-heading">
                      <div>
                        <strong>{calibrationStatusLabels[calibration.status]}</strong>
                      </div>
                      <span>{formatPeriod(calibration.period_start, calibration.period_end)}</span>
                    </div>
                    <DataConfidence kind="calibration" signal={calibration.sufficiency} />
                    {calibration.estimated_expenditure_kcal != null && (
                      <p className="weekly-review__estimate">
                        Оценочный диапазон расхода:{' '}
                        <strong>
                          {calibration.estimate_low_kcal}–{calibration.estimate_high_kcal} ккал
                        </strong>
                      </p>
                    )}
                    <ul>
                      {calibration.rationale.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>

                    {calibration.proposed_target_calories != null && (
                      <div className="weekly-review__diff" aria-label="Изменение цели питания">
                        <div>
                          <span>Сейчас</span>
                          <strong>{calibration.current_target_calories} ккал</strong>
                          {macroLine(calibration, false) && (
                            <small>{macroLine(calibration, false)}</small>
                          )}
                        </div>
                        <Icon name="arrow-right" size={16} />
                        <div>
                          <span>Предложение</span>
                          <strong>{calibration.proposed_target_calories} ккал</strong>
                          {macroLine(calibration, true) && (
                            <small>{macroLine(calibration, true)}</small>
                          )}
                        </div>
                      </div>
                    )}

                    {calibration.status === 'pending' && calibration.id ? (
                      <div className="weekly-review__decision">
                        <p className="weekly-review__decision-note">
                          При принятии новая версия начнёт действовать{' '}
                          <strong>
                            {formatDate(
                              calibration.proposed_effective_from ?? current.data.submitted_on,
                            )}
                          </strong>
                          . До подтверждения ничего не изменится.
                        </p>
                        <button
                          type="button"
                          className="weekly-review__primary"
                          disabled={isBusy}
                          onClick={() => decision.mutate({ id: calibration.id!, value: 'accept' })}
                        >
                          {decision.isPending ? 'Применяем…' : 'Принять новую цель'}
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          disabled={isBusy}
                          onClick={() => decision.mutate({ id: calibration.id!, value: 'reject' })}
                        >
                          Оставить текущую цель
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          disabled={isBusy}
                          onClick={() => finishReview(calibration)}
                        >
                          Отложить решение
                        </button>
                      </div>
                    ) : (
                      <div className="button-row weekly-review__actions">
                        <button
                          type="button"
                          className="weekly-review__primary"
                          disabled={isBusy}
                          onClick={() => finishReview(calibration)}
                        >
                          {submit.isPending ? 'Сохраняем…' : 'Завершить обзор'}
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          disabled={isBusy}
                          onClick={() => setDraft((value) => ({ ...value, step: 'questions' }))}
                        >
                          Назад к вопросам
                        </button>
                      </div>
                    )}
                  </div>
                ) : null}
              </section>
            )}
          </>
        )}

        {history.data?.items.length ? (
          <details className="weekly-review__history">
            <summary>
              <span>Предыдущие недели</span>
              <DisclosureIcon />
            </summary>
            <div className="list-grid top-gap">
              {history.data.items.map((item) => (
                <div className="list-row" key={item.id}>
                  <div>
                    <strong>{formatPeriod(item.week_start, item.week_end)}</strong>
                    <p className="muted">
                      {item.summary.training.completed_workouts} из{' '}
                      {item.summary.training.planned_workouts} тренировок
                      {item.summary.adaptive_energy?.calibration.proposed_target_calories
                        ? ` · ${item.summary.adaptive_energy.calibration.current_target_calories} → ${item.summary.adaptive_energy.calibration.proposed_target_calories} ккал`
                        : ''}
                    </p>
                  </div>
                  <Badge>{item.status === 'skipped' ? 'Пропущено' : 'Готово'}</Badge>
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </div>
    </Card>
  );

  async function confirmPlanningPlan(review: WeeklyPlanningReview): Promise<void> {
    const adjustments: WeeklyPlanningAdjustment[] = (review.proposals ?? []).map(
      ({ source_date, target_date, source_revision, target_revision }) => ({
        source_date,
        target_date,
        source_revision,
        target_revision,
      }),
    );
    if (
      !(await confirm({
        title: 'Перенести незавершённое?',
        message:
          'Позиции будут добавлены в план следующей недели. Записи дневника останутся без изменений.',
        confirmText: 'Перенести',
      }))
    ) {
      return;
    }
    planningConfirm.mutate(adjustments);
  }

  async function skipEntireReview(): Promise<void> {
    if (
      await confirm({
        title: 'Пропустить недельный обзор?',
        message: 'Это необязательно. Цель питания останется без изменений.',
        confirmText: 'Пропустить',
      })
    ) {
      submit.mutate({ status: 'skipped' });
    }
  }
}
