import { useEffect, useRef } from 'react';
import type { Workout } from '../../shared/api/types';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { PublicWebLink } from '../../shared/navigation/PublicWebLink';
import { Button, DisclosureIcon } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { weekTypeGenitive, weekTypeLabels } from './weekTypes';

type Guidance = NonNullable<Workout['exercises'][number]['progression_guidance']>;
type Session = Guidance['evidence']['sessions'][number];

const feedbackLabels: Record<NonNullable<Session['completion_feedback']>, string> = {
  easier_than_expected: 'легче ожидаемого',
  as_expected: 'нормально',
  harder_than_expected: 'тяжелее ожидаемого',
};

const ruleLabels: Record<NonNullable<Guidance['proposal']>['rule_kind'], string> = {
  legacy_progression_guidance: 'Общее правило прогрессии',
  fixed_prescription: 'Фиксированное назначение',
  double_progression: 'Двойная прогрессия',
  linear_load: 'Линейная прогрессия нагрузки',
  percentage_training_max: 'Процент тренировочного максимума',
  rir_rpe: 'Целевое усилие RIR/RPE',
  amrap_success_failure: 'Условие AMRAP',
  deload: 'Облегчённый блок',
};

function formatNumber(value: number): string {
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
}

function unitLabel(unit: Guidance['load_unit']): string {
  return unit === 'kg' ? 'кг' : 'lb';
}

function targetLabel(guidance: Guidance): string {
  const { target_reps_min: minimum, target_reps_max: maximum } = guidance.evidence;
  if (minimum == null || maximum == null) return 'Диапазон повторений не распознан';
  const reps = minimum === maximum ? String(minimum) : `${minimum}–${maximum}`;
  return `Цель: ${guidance.evidence.prescribed_sets} × ${reps}`;
}

function sessionLabel(session: Session): string {
  const date = new Date(`${session.scheduled_date}T12:00:00`).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
  });
  const reps =
    session.reps_min == null || session.reps_max == null
      ? 'повторы не записаны'
      : session.reps_min === session.reps_max
        ? `${session.reps_min} повторов`
        : `${session.reps_min}–${session.reps_max} повторов`;
  const load =
    session.load == null
      ? 'нагрузка неполная'
      : `${formatNumber(session.load)} ${unitLabel(session.load_unit)}`;
  return `${date} · ${load} · ${reps}`;
}

function latestSessionLabel(session: Session): string {
  if (session.load == null || session.reps_min == null || session.reps_max == null) {
    return sessionLabel(session);
  }
  const date = new Date(`${session.scheduled_date}T12:00:00`).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
  });
  const load = `${formatNumber(session.load)} ${unitLabel(session.load_unit)}`;
  const reps =
    session.reps_min === session.reps_max
      ? String(session.reps_min)
      : `${session.reps_min}–${session.reps_max}`;
  return `${load} × ${reps} · ${date}`;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function ruleSummary(guidance: Guidance): string | null {
  const proposal = guidance.proposal;
  if (!proposal || proposal.rule_kind === 'legacy_progression_guidance') return null;
  const rule = proposal.rule_snapshot;
  const repTarget = asRecord(rule.rep_target);
  const loadTarget = asRecord(rule.load_target);
  const effortTarget = asRecord(rule.effort_target);
  const increment = rule.increment_value;
  const incrementUnit = rule.increment_unit;
  const unit =
    incrementUnit === 'kg'
      ? 'кг'
      : incrementUnit === 'lb'
        ? 'lb'
        : incrementUnit === 'percent'
          ? '%'
          : null;
  const facts: string[] = [];

  if (
    repTarget?.kind === 'range' &&
    typeof repTarget.min_reps === 'number' &&
    typeof repTarget.max_reps === 'number'
  ) {
    facts.push(`диапазон ${repTarget.min_reps}–${repTarget.max_reps} повторений`);
  } else if (repTarget?.kind === 'exact' && typeof repTarget.value === 'number') {
    facts.push(`${repTarget.value} повторений`);
  } else if (repTarget?.kind === 'amrap') {
    facts.push(
      typeof repTarget.cap_reps === 'number'
        ? `AMRAP, не более ${repTarget.cap_reps} повторений`
        : 'AMRAP',
    );
  }

  if (loadTarget?.kind === 'user_selected') {
    facts.push('нагрузку выбирает пользователь');
  } else if (typeof loadTarget?.value === 'number') {
    if (loadTarget.kind === 'percent_training_max') {
      facts.push(`${formatNumber(loadTarget.value)}% от тренировочного максимума`);
    } else if (loadTarget.kind === 'percent_1rm') {
      facts.push(`${formatNumber(loadTarget.value)}% от 1ПМ`);
    } else if (loadTarget.kind === 'relative_to_top') {
      facts.push(`${formatNumber(loadTarget.value * 100)}% от верхнего подхода`);
    } else if (loadTarget.kind === 'relative_to_previous') {
      facts.push(`${formatNumber(loadTarget.value * 100)}% от предыдущего подхода`);
    } else if (loadTarget.kind === 'absolute') {
      facts.push(`нагрузка ${formatNumber(loadTarget.value)} кг`);
    }
  }

  if (
    (effortTarget?.kind === 'rir' || effortTarget?.kind === 'rpe') &&
    (typeof effortTarget.value === 'number' || typeof effortTarget.value === 'string')
  ) {
    facts.push(`цель ${effortTarget.kind.toUpperCase()} ${effortTarget.value}`);
  } else if (effortTarget?.kind === 'failure') {
    facts.push('до отказа');
  }

  if (typeof increment === 'number') {
    facts.push(
      unit
        ? `шаг ${formatNumber(increment)} ${unit}`
        : `шаг ${formatNumber(increment)}, единица не задана`,
    );
  }

  if (typeof rule.amrap_min_reps === 'number') {
    facts.push(`успех от ${rule.amrap_min_reps} повторений`);
  }
  const failureActions: Record<string, string> = {
    repeat: 'повторить нагрузку',
    reduce_load:
      typeof increment === 'number'
        ? `снизить на ${formatNumber(increment)}${unit ? ` ${unit}` : ', единица не задана'}`
        : 'снизить без заданной величины',
    deload: 'предложить облегчённый блок',
    manual_review: 'передать на проверку',
  };
  if (typeof rule.amrap_failure_action === 'string' && failureActions[rule.amrap_failure_action]) {
    facts.push(`при невыполнении: ${failureActions[rule.amrap_failure_action]}`);
  }

  if (rule.reset_on_failure === true) facts.push('сброс при отказе без заданной величины');
  if (typeof proposal.deload_volume_percent === 'number') {
    facts.push(`объём ${proposal.deload_volume_percent}%`);
  }
  if (typeof proposal.deload_intensity_percent === 'number') {
    facts.push(`интенсивность ${proposal.deload_intensity_percent}%`);
  }

  if (rule.scope === 'exercise') facts.push('уровень упражнения');
  else if (rule.scope === 'block' && typeof rule.block_number === 'number') {
    facts.push(`блок ${rule.block_number}`);
  } else if (rule.scope === 'program') facts.push('уровень программы');

  if (typeof rule.week_start === 'number' && typeof rule.week_end === 'number') {
    facts.push(
      rule.week_start === rule.week_end
        ? `неделя ${rule.week_start}`
        : `недели ${rule.week_start}–${rule.week_end}`,
    );
  } else if (typeof rule.week_start === 'number') {
    facts.push(`с недели ${rule.week_start}`);
  } else if (typeof rule.week_end === 'number') {
    facts.push(`по неделю ${rule.week_end}`);
  }

  const details = facts.join(' · ');
  return details
    ? `${ruleLabels[proposal.rule_kind]} · ${details}`
    : ruleLabels[proposal.rule_kind];
}

export function ProgressionGuidance({
  guidance,
  exerciseKey,
  applied = false,
  onApply,
  onDismiss,
}: {
  guidance: Guidance;
  exerciseKey: number;
  applied?: boolean;
  onApply?: () => void | Promise<unknown>;
  onDismiss: () => void;
}) {
  const applyStarted = useRef(false);
  const exactSuggestion = guidance.proposal?.proposed_weight ?? guidance.suggested_weight;
  const explanation = ruleSummary(guidance);
  const typed = guidance.ruleset_version === 'progression-guidance-v3';
  const weekType = guidance.evidence.week_type;
  const latestSession = guidance.evidence.sessions[0];
  const reasons = guidance.proposal?.reason_codes ?? guidance.evidence.reason_keys;
  const insufficientHistory = reasons.includes('insufficient_same_type_history');
  const isIncreasing = guidance.outcome === 'consider_progressing';
  const message =
    typed && isIncreasing && exactSuggestion != null
      ? `Можно рассмотреть увеличение до ${formatNumber(exactSuggestion)} ${unitLabel(guidance.load_unit)}`
      : guidance.message;
  const proposalVersions = (guidance.proposal?.target_set_updates ?? [])
    .map((update) => `${update.set_id}:${update.set_version}`)
    .join(',');

  useEffect(() => {
    applyStarted.current = false;
  }, [guidance.proposal?.proposal_id, proposalVersions]);

  useEffect(() => {
    trackProductEvent(
      { name: 'progression_suggestion_shown', surface: productEventSurface() },
      { dedupe: 'session', dedupeKey: `workout-exercise-${exerciseKey}` },
    );
  }, [exerciseKey]);

  return (
    <section
      aria-label="Рекомендация по следующей нагрузке"
      className={`progression-guidance is-${guidance.outcome}`}
    >
      <div className="progression-guidance__copy">
        <span>Следующая нагрузка{weekType ? ` · ${weekTypeLabels[weekType]} неделя` : ''}</span>
        <strong>{message}</strong>
        {typed && (
          <p>
            {latestSession
              ? `Прошлая сопоставимая: ${latestSessionLabel(latestSession)}`
              : insufficientHistory
                ? 'Сопоставимых тренировок пока нет.'
                : 'Сопоставимую историю для этой рекомендации не удалось подтвердить.'}
          </p>
        )}
        <p>{guidance.detail}</p>
        {weekType && insufficientHistory && (
          <p>
            Для рекомендации нужны полные сопоставимые тренировки {weekTypeGenitive[weekType]} типа.
          </p>
        )}
        {explanation && <p className="progression-guidance__rule">Правило: {explanation}</p>}
      </div>

      <details className="progression-guidance__details">
        <summary className="yfc-disclosure-summary">
          <span>Почему такой вес?</span>
          <DisclosureIcon />
        </summary>
        <div className="progression-guidance__evidence">
          <div className="progression-guidance__facts">
            <span>{targetLabel(guidance)}</span>
            <span>
              Сопоставимых тренировок: {guidance.evidence.comparable_session_count} из{' '}
              {guidance.evidence.required_session_count}
            </span>
            <span>
              Запас повторов записан в {guidance.evidence.rir_recorded_set_count} из{' '}
              {guidance.evidence.working_set_count} рабочих подходов
            </span>
          </div>
          {guidance.evidence.sessions.length > 0 ? (
            <ol className="progression-guidance__history" aria-label="Последние тренировки">
              {guidance.evidence.sessions.map((session) => (
                <li key={session.workout_id}>
                  <span>{sessionLabel(session)}</span>
                  <small>
                    {session.working_set_count} раб. подх.
                    {session.rir_recorded_set_count > 0
                      ? ` · запас записан: ${session.rir_values.join(', ')}`
                      : ' · без оценки запаса'}
                    {session.reached_failure ? ' · отмечен отказ' : ''}
                    {session.completion_feedback
                      ? ` · тренировка: ${feedbackLabels[session.completion_feedback]}`
                      : ''}
                  </small>
                </li>
              ))}
            </ol>
          ) : (
            <p className="progression-guidance__empty">
              Пока нет полных сопоставимых тренировок в этом контексте программы.
            </p>
          )}
          {typed && (
            <div className="progression-guidance__facts progression-guidance__provenance">
              {guidance.proposal?.source_evidence_ids.length ? (
                <span>Источники: {guidance.proposal.source_evidence_ids.join(' · ')}</span>
              ) : null}
              {reasons.length > 0 && <span>Причины: {reasons.join(' · ')}</span>}
              <span>Версия правила: {guidance.ruleset_version}</span>
            </div>
          )}
          <PublicWebLink
            className="contextual-help__link progression-guidance__source"
            path="/knowledge/training/progressive-overload"
          >
            Подробнее о прогрессии <Icon name="external-link" size={16} />
          </PublicWebLink>
        </div>
      </details>

      <div className="progression-guidance__actions">
        {exactSuggestion != null && onApply && (
          <Button
            type="button"
            variant="secondary"
            disabled={applied}
            onClick={() => {
              if (applyStarted.current || applied) return;
              applyStarted.current = true;
              try {
                const pending = onApply();
                if (pending) {
                  void pending.catch(() => {
                    applyStarted.current = false;
                  });
                }
              } catch (error) {
                applyStarted.current = false;
                throw error;
              }
            }}
          >
            {applied
              ? 'Вес подставлен'
              : `Применить ${formatNumber(exactSuggestion)} ${unitLabel(guidance.load_unit)}`}
          </Button>
        )}
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            trackProductEvent({
              name: 'progression_suggestion_dismissed',
              surface: productEventSurface(),
            });
            onDismiss();
          }}
        >
          Оставить текущую нагрузку
        </Button>
      </div>
    </section>
  );
}
