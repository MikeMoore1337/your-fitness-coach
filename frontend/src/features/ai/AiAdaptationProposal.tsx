import { useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import type { ApiSchemas, AiCoachConsentResponse } from '../../shared/api/types';
import { Button, Field } from '../../shared/ui/common';
import { useAiCoachStatus } from './AiCoachExperience';
import './ai-coach.css';

type AdaptationProposal = ApiSchemas['AdaptationProposal'];
type AdaptationResponse = ApiSchemas['AiCoachAdaptationProposalResponse'];
type ReviewResponse = ApiSchemas['AiCoachAdaptationReviewResponse'];
type GenerateRequest = ApiSchemas['AiCoachAdaptationGenerateRequest'];
type AdaptationState =
  | 'idle'
  | 'consent_checking'
  | 'generating'
  | 'ready'
  | 'confirm_pending'
  | 'confirmed'
  | 'rejected'
  | 'stale'
  | 'unavailable'
  | 'disabled'
  | 'consent_required'
  | 'unsupported'
  | 'invalid'
  | 'error';

const DEFAULT_MESSAGE =
  'Предложи безопасную адаптацию текущей программы с учётом ближайшей тренировки.';

const outcomeValues = new Set<string>([
  'answer',
  'unavailable',
  'rate_limited',
  'safety_refusal',
  'insufficient_data',
  'invalid_output',
  'consent_required',
]);

const relationshipLabels: Record<ApiSchemas['AiCoachDeterministicRelationship'], string> = {
  supports_deterministic_rule: 'Поддерживает детерминированное правило',
  supplements_no_rule: 'Дополняет программу там, где правила недостаточно',
  conflicts_with_deterministic_rule: 'Конфликтует с детерминированным правилом',
};

const proposalTypeLabels: Record<ApiSchemas['AiCoachAdaptationProposalType'], string> = {
  progression_explanation: 'Объяснение прогрессии',
  exercise_substitution: 'Замена упражнения',
  volume_or_frequency_adjustment: 'Изменение назначения',
  block_or_revision_edit: 'Изменение этапа или ревизии',
  adherence_performance_summary: 'Сводка выполнения',
};

const operationLabels: Record<AdaptationProposal['suggested_change']['operation'], string> = {
  replace_exercise: 'Предложена допустимая замена упражнения из каталога.',
  update_prescription: 'Предложено изменить назначение упражнения.',
  explanation_only: 'Только объяснение — программа не изменится.',
};

const scopeLabels: Record<AdaptationProposal['suggested_change']['effective_scope'], string> = {
  next_workout: 'Ближайшая тренировка',
  current_block: 'Текущий тренировочный блок',
  future_program: 'Будущая программа',
};

const evidenceLabels: Record<string, string> = {
  'evidence:progression': 'результаты прогрессии',
  'evidence:revision': 'текущая ревизия программы',
};

const relationshipValues = new Set(Object.keys(relationshipLabels));
const proposalTypeValues = new Set(Object.keys(proposalTypeLabels));
const operationValues = new Set(Object.keys(operationLabels));
const scopeValues = new Set(Object.keys(scopeLabels));

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function finiteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function nullableFiniteNumber(value: unknown): value is number | null | undefined {
  return value == null || finiteNumber(value);
}

function nullableString(value: unknown): value is string | null | undefined {
  return value == null || typeof value === 'string';
}

function isAdaptationResponse(value: unknown): value is AdaptationResponse {
  if (!isRecord(value) || typeof value.outcome !== 'string' || !outcomeValues.has(value.outcome)) {
    return false;
  }
  if (
    !stringList(value.limitations) ||
    typeof value.safety_category !== 'string' ||
    typeof value.prompt_version !== 'string' ||
    typeof value.schema_version !== 'string' ||
    typeof value.policy_version !== 'string'
  ) {
    return false;
  }
  if (value.outcome !== 'answer') return value.proposal == null && value.proposal_token == null;

  const proposal = value.proposal;
  const change = isRecord(proposal) ? proposal.suggested_change : null;
  return Boolean(
    isRecord(proposal) &&
    typeof value.proposal_token === 'string' &&
    value.proposal_token.length > 0 &&
    typeof proposal.proposal_id === 'string' &&
    proposal.proposal_id.length > 0 &&
    finiteNumber(proposal.target_program_id) &&
    finiteNumber(proposal.target_revision_id) &&
    finiteNumber(proposal.target_revision_number) &&
    nullableFiniteNumber(proposal.target_block_id) &&
    nullableFiniteNumber(proposal.target_exercise_id) &&
    typeof proposal.explanation === 'string' &&
    proposal.explanation.trim().length > 0 &&
    stringList(proposal.evidence_ids) &&
    stringList(proposal.limitations) &&
    proposal.requires_confirmation === true &&
    typeof proposal.deterministic_rule_relationship === 'string' &&
    relationshipValues.has(proposal.deterministic_rule_relationship) &&
    typeof proposal.proposal_type === 'string' &&
    proposalTypeValues.has(proposal.proposal_type) &&
    isRecord(change) &&
    typeof change.operation === 'string' &&
    operationValues.has(change.operation) &&
    typeof change.effective_scope === 'string' &&
    scopeValues.has(change.effective_scope) &&
    nullableString(change.replacement_candidate_ref) &&
    nullableFiniteNumber(change.prescribed_sets) &&
    nullableString(change.prescribed_reps) &&
    nullableFiniteNumber(change.rest_seconds),
  );
}

function isReviewResponse(
  value: unknown,
  proposalId: string,
  decision: 'confirm' | 'reject',
): value is ReviewResponse {
  return Boolean(
    isRecord(value) &&
    value.outcome === 'answer' &&
    value.proposal_id === proposalId &&
    value.decision === decision &&
    typeof value.applied === 'boolean' &&
    value.applied === (decision === 'confirm') &&
    typeof value.current_revision_number === 'number' &&
    Number.isFinite(value.current_revision_number) &&
    stringList(value.limitations),
  );
}

function changeDetails(proposal: AdaptationProposal): string[] {
  const change = proposal.suggested_change;
  const details: string[] = [operationLabels[change.operation]];
  if (change.operation === 'replace_exercise') {
    details.push('Вариант будет выбран только из проверенных кандидатов сервера.');
  }
  if (change.prescribed_sets != null) details.push(`Подходы: ${change.prescribed_sets}`);
  if (change.prescribed_reps) details.push(`Повторы: ${change.prescribed_reps}`);
  if (change.rest_seconds != null) details.push(`Отдых: ${change.rest_seconds} сек.`);
  details.push(`Область действия: ${scopeLabels[change.effective_scope]}`);
  return details;
}

function humanEvidence(proposal: AdaptationProposal): string[] {
  return proposal.evidence_ids
    .map((id) => evidenceLabels[id])
    .filter((label): label is string => Boolean(label));
}

function safeErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 0) return error.message;
  return 'Не удалось получить ответ. Проверьте соединение и попробуйте ещё раз.';
}

function stateCopy(state: AdaptationState): string {
  switch (state) {
    case 'unavailable':
      return 'AI-адаптация сейчас недоступна. Детерминированные функции программы продолжают работать.';
    case 'disabled':
      return 'AI-адаптация отключена. Основные функции программы доступны.';
    case 'consent_required':
      return 'Для персонального предложения сначала включите отдельное согласие на AI Coach.';
    case 'unsupported':
      return 'Для этого запроса безопасное предложение не сформировано. Программа не изменена.';
    case 'invalid':
      return 'Ответ не прошёл проверку формата. Программа не изменена.';
    case 'stale':
      return 'Программа уже изменилась. Сформируйте предложение заново на актуальной ревизии.';
    case 'confirmed':
      return 'Предложение подтверждено. Изменение передано в программу после серверной проверки.';
    case 'rejected':
      return 'Предложение отклонено. Текущая программа сохранена без изменений.';
    case 'error':
      return 'Не удалось завершить действие. Программа не изменена.';
    default:
      return '';
  }
}

function StateNotice({
  state,
  limitations,
  onRetry,
}: {
  state: AdaptationState;
  limitations: string[];
  onRetry?: () => void;
}) {
  const notice = stateCopy(state);
  if (!notice) return null;
  return (
    <div
      className={`ai-adaptation__notice ai-adaptation__notice--${state}`}
      role={state === 'error' || state === 'invalid' ? 'alert' : 'status'}
      aria-live="polite"
    >
      <p>{notice}</p>
      {limitations.length > 0 && (
        <ul>
          {limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      )}
      {state === 'consent_required' && (
        <a href="/app?section=profile#profile-ai-coach">Открыть настройки AI Coach</a>
      )}
      {onRetry && (
        <Button type="button" variant="secondary" onClick={onRetry}>
          {state === 'stale' ? 'Сформировать заново' : 'Попробовать снова'}
        </Button>
      )}
    </div>
  );
}

export function AiAdaptationProposal({
  enabled = true,
  programId,
  revisionNumber,
  targetWorkoutId,
  onApplied,
}: {
  enabled?: boolean;
  programId: number;
  revisionNumber: number;
  targetWorkoutId?: number | null;
  onApplied?: (currentRevisionNumber: number) => void;
}) {
  const status = useAiCoachStatus(enabled);
  const [panelOpen, setPanelOpen] = useState(false);
  const [message, setMessage] = useState(DEFAULT_MESSAGE);
  const [state, setState] = useState<AdaptationState>('idle');
  const [limitations, setLimitations] = useState<string[]>([]);
  const [proposal, setProposal] = useState<AdaptationProposal | null>(null);
  const [proposalToken, setProposalToken] = useState<string | null>(null);
  const generationStarted = useRef(false);
  const reviewStarted = useRef(false);
  const generateMutation = useMutation({
    mutationFn: (payload: GenerateRequest) =>
      api<AdaptationResponse>('/api/v1/ai-coach/adaptations/proposals', {
        method: 'POST',
        body: payload,
      }),
  });
  const reviewMutation = useMutation({
    mutationFn: ({
      decision,
      proposalId,
      token,
      expectedRevisionNumber,
    }: {
      decision: 'confirm' | 'reject';
      proposalId: string;
      token: string;
      expectedRevisionNumber: number;
    }) =>
      api<ReviewResponse>(
        `/api/v1/ai-coach/adaptations/proposals/${encodeURIComponent(proposalId)}/review`,
        {
          method: 'POST',
          body: {
            proposal_id: proposalId,
            proposal_token: token,
            expected_revision_number: expectedRevisionNumber,
            decision,
          },
        },
      ),
  });

  if (!enabled) return null;

  const reset = (open = false) => {
    setPanelOpen(open);
    setState('idle');
    setLimitations([]);
    setProposal(null);
    setProposalToken(null);
    generationStarted.current = false;
    reviewStarted.current = false;
  };

  const startGeneration = async () => {
    if (generationStarted.current || generateMutation.isPending) return;
    generationStarted.current = true;
    setState('consent_checking');
    setLimitations([]);
    try {
      const consentResponse = await api<AiCoachConsentResponse>('/api/v1/ai-coach/consent');
      if (consentResponse.status !== 'granted') {
        setState('consent_required');
        return;
      }

      setState('generating');
      const payload: GenerateRequest = {
        program_id: programId,
        expected_revision_number: revisionNumber,
        ...(targetWorkoutId != null ? { target_workout_id: targetWorkoutId } : {}),
        message: message.trim(),
        locale: 'ru',
      };
      const response = await generateMutation.mutateAsync(payload);
      if (!isAdaptationResponse(response)) {
        setState('invalid');
        return;
      }
      setLimitations(response.limitations);
      if (response.outcome !== 'answer') {
        setState(
          response.outcome === 'unavailable'
            ? 'unavailable'
            : response.outcome === 'consent_required'
              ? 'consent_required'
              : response.outcome === 'invalid_output'
                ? 'invalid'
                : response.outcome === 'insufficient_data' || response.outcome === 'safety_refusal'
                  ? 'unsupported'
                  : 'error',
        );
        return;
      }
      if (
        response.proposal?.target_program_id !== programId ||
        response.proposal.target_revision_number !== revisionNumber
      ) {
        setState('invalid');
        return;
      }
      if (!response.proposal || typeof response.proposal_token !== 'string') {
        setState('invalid');
        return;
      }
      setProposal(response.proposal);
      setProposalToken(response.proposal_token);
      setLimitations([...new Set([...response.limitations, ...response.proposal.limitations])]);
      setState('ready');
    } catch (error) {
      setState(error instanceof ApiError && error.status === 409 ? 'stale' : 'error');
      setLimitations([safeErrorMessage(error)]);
    } finally {
      generationStarted.current = false;
    }
  };

  const review = async (decision: 'confirm' | 'reject') => {
    if (!proposal || !proposalToken || reviewStarted.current) return;
    reviewStarted.current = true;
    setState('confirm_pending');
    setLimitations([]);
    try {
      const response = await reviewMutation.mutateAsync({
        decision,
        proposalId: proposal.proposal_id,
        token: proposalToken,
        expectedRevisionNumber: proposal.target_revision_number,
      });
      if (!isReviewResponse(response, proposal.proposal_id, decision)) {
        setState('invalid');
        return;
      }
      setLimitations(response.limitations);
      if (decision === 'confirm') {
        onApplied?.(response.current_revision_number);
        setState('confirmed');
      } else {
        setState('rejected');
      }
    } catch (error) {
      setState(error instanceof ApiError && error.status === 409 ? 'stale' : 'error');
      setLimitations([safeErrorMessage(error)]);
    } finally {
      reviewStarted.current = false;
    }
  };

  const statusUnavailable =
    status.isError ||
    (status.isSuccess && (!status.data?.ui_enabled || !status.data?.personal_available));
  if (status.isLoading || statusUnavailable) {
    const disabled = status.data?.ui_enabled === false;
    return (
      <section
        className={`ai-adaptation ai-adaptation--${disabled ? 'disabled' : 'unavailable'}`}
        data-state={disabled ? 'disabled' : 'unavailable'}
        data-testid="ai-adaptation"
      >
        <div className="ai-adaptation__copy">
          <span className="eyebrow">AI Coach · адаптация</span>
          <strong>
            {status.isLoading
              ? 'Проверяем доступ…'
              : stateCopy(disabled ? 'disabled' : 'unavailable')}
          </strong>
          {!status.isLoading && (
            <p>Можно продолжать использовать текущую программу и детерминированную прогрессию.</p>
          )}
        </div>
        <Button type="button" variant="secondary" disabled>
          {status.isLoading ? 'Проверяем доступ…' : 'AI-адаптация недоступна'}
        </Button>
      </section>
    );
  }

  if (!panelOpen && state === 'idle') {
    return (
      <section className="ai-adaptation" data-state="idle" data-testid="ai-adaptation">
        <div className="ai-adaptation__copy">
          <span className="eyebrow">AI Coach · адаптация</span>
          <strong>Проверяемое предложение для текущей программы</strong>
          <p>AI только предложит изменение. Программа не изменится без вашего подтверждения.</p>
        </div>
        <Button type="button" variant="secondary" onClick={() => setPanelOpen(true)}>
          Предложить адаптацию с AI
        </Button>
      </section>
    );
  }

  const reviewReady = state === 'ready' && proposal;
  const readableEvidence = reviewReady ? humanEvidence(proposal) : [];
  return (
    <section
      className={`ai-adaptation ai-adaptation--${state}`}
      data-state={state}
      data-testid="ai-adaptation"
    >
      <div className="ai-adaptation__header">
        <div className="ai-adaptation__copy">
          <span className="eyebrow">AI Coach · адаптация</span>
          <strong>Предложение для текущей программы</strong>
        </div>
        {state === 'idle' && (
          <span className="ai-adaptation__scope">Только после подтверждения</span>
        )}
      </div>

      {state === 'idle' && (
        <form
          className="ai-adaptation__form"
          onSubmit={(event) => {
            event.preventDefault();
            void startGeneration();
          }}
        >
          <Field
            label="Что учесть в предложении"
            labelFor={`ai-adaptation-message-${programId}`}
            hint="До 600 символов. Не добавляйте пароли, ссылки или данные других людей."
          >
            <textarea
              className="ui-input ai-adaptation__message"
              id={`ai-adaptation-message-${programId}`}
              maxLength={600}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              required
            />
          </Field>
          <div className="ai-adaptation__actions">
            <Button disabled={!message.trim()} type="submit">
              Сформировать предложение
            </Button>
            <Button type="button" variant="secondary" onClick={() => reset()}>
              Отменить
            </Button>
          </div>
        </form>
      )}

      {(state === 'consent_checking' || state === 'generating') && (
        <p className="ai-adaptation__progress" role="status" aria-live="polite">
          {state === 'consent_checking'
            ? 'Проверяем отдельное согласие…'
            : 'Формируем предложение…'}
        </p>
      )}

      {reviewReady && (
        <div className="ai-adaptation__review" aria-label="Проверка предложения AI">
          <div className="ai-adaptation__facts">
            <div>
              <span>Что меняется</span>
              <strong>{proposalTypeLabels[proposal.proposal_type]}</strong>
              <ul>
                {changeDetails(proposal).map((detail) => (
                  <li key={detail}>{detail}</li>
                ))}
              </ul>
            </div>
            <div>
              <span>Часть программы</span>
              <strong>
                {proposal.target_exercise_id != null
                  ? 'Упражнение ближайшей тренировки'
                  : proposal.target_block_id != null
                    ? 'Тренировочный блок'
                    : 'Текущая программа'}
              </strong>
              <small>Ревизия программы: v{proposal.target_revision_number}</small>
            </div>
            <div>
              <span>Связь с правилами</span>
              <strong>{relationshipLabels[proposal.deterministic_rule_relationship]}</strong>
              {readableEvidence.length > 0 && (
                <small>Основание: {readableEvidence.join(', ')}</small>
              )}
            </div>
          </div>
          <p className="ai-adaptation__explanation">{proposal.explanation}</p>
          <p className="ai-adaptation__confirmation">
            Требуется явное подтверждение. До него локальная программа не изменяется.
          </p>
          {limitations.length > 0 && (
            <ul className="ai-adaptation__limitations">
              {limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
          )}
          <div className="ai-adaptation__actions">
            <Button
              type="button"
              disabled={reviewMutation.isPending}
              onClick={() => void review('confirm')}
            >
              Подтвердить адаптацию
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={reviewMutation.isPending}
              onClick={() => void review('reject')}
            >
              Отклонить
            </Button>
          </div>
        </div>
      )}

      {state === 'confirm_pending' && (
        <p className="ai-adaptation__progress" role="status" aria-live="polite">
          Проверяем ревизию и сохраняем решение…
        </p>
      )}

      {!reviewReady &&
        state !== 'idle' &&
        state !== 'consent_checking' &&
        state !== 'generating' && (
          <StateNotice
            state={state}
            limitations={limitations}
            onRetry={
              state === 'error' ||
              state === 'invalid' ||
              state === 'stale' ||
              state === 'unsupported'
                ? () => reset(true)
                : undefined
            }
          />
        )}

      {(state === 'confirmed' || state === 'rejected') && (
        <Button type="button" variant="secondary" onClick={() => reset(true)}>
          Новое предложение
        </Button>
      )}
    </section>
  );
}
