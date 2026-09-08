import { useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  AiCoachConsentResponse,
  AiCoachResponse,
  AiCoachStatus,
} from '../../shared/api/types';
import { AppLink } from '../../shared/navigation/router';
import {
  productEventSurface,
  trackProductEvent,
  type AiCoachEntryPoint,
  type AiCoachFailureClass,
  type AiCoachHelpfulness,
  type AiCoachMode,
} from '../../shared/analytics/productEvents';
import { Badge, Button, Card, LoadingState } from '../../shared/ui/common';
import './ai-coach.css';

export const AI_COACH_UI_EVAL_VERSION = 'ai-coach-ui-beta-v1';

type AiCoachJob =
  | 'app_help'
  | 'public_knowledge'
  | 'metric_explanation'
  | 'fitness_knowledge'
  | 'nutrition_knowledge'
  | 'progression_explanation';
type AiCoachPersonalTool =
  'get_progress_summary' | 'get_recent_training_summary' | 'get_nutrition_summary';
type AiCoachOutcome =
  | 'answer'
  | 'unavailable'
  | 'rate_limited'
  | 'safety_refusal'
  | 'insufficient_data'
  | 'invalid_output'
  | 'consent_required';
type AiCoachPeriod = 7 | 30 | 90;

type GenericPrompt = {
  id: string;
  label: string;
  message: string;
  job: AiCoachJob;
  context_id: string;
};

type PersonalPrompt = {
  id: string;
  label: string;
  message: string;
  tool: AiCoachPersonalTool;
};

type AiCoachRequest =
  | {
      mode: 'generic';
      job: AiCoachJob;
      context_id: string;
      message: string;
    }
  | {
      mode: 'personal';
      tool: AiCoachPersonalTool;
      period_days: AiCoachPeriod;
      message: string;
    };

const GENERIC_PROMPTS: readonly GenericPrompt[] = [
  {
    id: 'training',
    label: 'Разобраться с тренировкой',
    message:
      'Объясни простыми словами, как в YFC устроен план тренировки и что делать на экране «Сегодня».',
    job: 'app_help',
    context_id: '/training',
  },
  {
    id: 'nutrition',
    label: 'Понять дневник питания',
    message: 'Объясни, как в YFC вести дневник питания и как читать сохранённые ориентиры.',
    job: 'app_help',
    context_id: '/nutrition',
  },
  {
    id: 'progress',
    label: 'Прочитать прогресс',
    message:
      'Объясни, как читать раздел прогресса в YFC и почему одной записи недостаточно для вывода.',
    job: 'app_help',
    context_id: '/progress',
  },
];

const PERSONAL_PROMPTS: readonly PersonalPrompt[] = [
  {
    id: 'progress-summary',
    label: 'Мой прогресс',
    message:
      'Коротко объясни мою сводку прогресса за выбранный период и укажи, каких данных не хватает.',
    tool: 'get_progress_summary',
  },
  {
    id: 'training-summary',
    label: 'Мои тренировки',
    message: 'Коротко объясни мою сводку тренировок за выбранный период, не добавляя новых фактов.',
    tool: 'get_recent_training_summary',
  },
  {
    id: 'nutrition-summary',
    label: 'Моё питание',
    message: 'Коротко объясни мою сводку питания за выбранный период и обозначь её ограничения.',
    tool: 'get_nutrition_summary',
  },
];
const DEFAULT_GENERIC_PROMPT = GENERIC_PROMPTS[0]!;
const DEFAULT_PERSONAL_PROMPT = PERSONAL_PROMPTS[0]!;

const OUTCOME_COPY: Record<AiCoachOutcome, { title: string; text: string }> = {
  answer: {
    title: 'Ответ готов',
    text: 'Ответ сформирован только по разрешённому контексту и сопровождается его источниками.',
  },
  unavailable: {
    title: 'AI Coach сейчас недоступен',
    text: 'Основные функции приложения продолжают работать. Попробуйте позже.',
  },
  rate_limited: {
    title: 'Лимит AI Coach исчерпан',
    text: 'Новые запросы временно ограничены. Попробуйте позже.',
  },
  safety_refusal: {
    title: 'На этот запрос нельзя ответить в рамках beta',
    text: 'AI Coach не ставит диагнозы, не назначает лечение и не помогает с опасными схемами.',
  },
  insufficient_data: {
    title: 'Проверенных данных пока недостаточно',
    text: 'Откройте соответствующий раздел приложения, дополните данные и повторите запрос.',
  },
  invalid_output: {
    title: 'Ответ не прошёл проверку',
    text: 'Мы не показываем непроверенный результат. Попробуйте ещё раз позже.',
  },
  consent_required: {
    title: 'Нужно отдельное согласие',
    text: 'Персональная сводка не передаётся без явного согласия на этот режим.',
  },
};

const SAFE_FAILURE_COPY: Record<AiCoachFailureClass, string> = {
  network: 'Не удалось связаться с AI Coach. Проверьте соединение и повторите попытку.',
  timeout: 'Ответ занял слишком много времени. Попробуйте ещё раз.',
  validation: 'Запрос не прошёл проверку. Измените вопрос и повторите.',
  unknown: 'Не удалось получить проверенный ответ. Попробуйте ещё раз позже.',
};

export const aiCoachStatusQueryKey = ['ai-coach', 'status'] as const;
export const aiCoachConsentQueryKey = ['ai-coach', 'consent'] as const;

export function useAiCoachStatus(enabled = true) {
  return useQuery<AiCoachStatus>({
    queryKey: aiCoachStatusQueryKey,
    queryFn: () => api<AiCoachStatus>('/api/v1/ai-coach/status'),
    enabled,
    staleTime: 30_000,
    retry: false,
  });
}

function normalizeFailure(reason: unknown): AiCoachFailureClass {
  if (reason instanceof DOMException && reason.name === 'AbortError') return 'timeout';
  if (reason instanceof TypeError) return 'network';
  if (reason && typeof reason === 'object' && 'status' in reason) {
    const status = Number((reason as { status?: unknown }).status);
    if (status === 408 || status === 504) return 'timeout';
    if (status === 422) return 'validation';
  }
  return 'unknown';
}

export function safeCoachUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password || url.hash) return null;
    return url.toString();
  } catch {
    return null;
  }
}

function safeInlineNodes(text: string, allowedUrls: ReadonlySet<string>): ReactNode[] {
  const nodes: ReactNode[] = [];
  const linkPattern = /\[([^\]]{1,120})\]\((https:\/\/[^)\s]+)\)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  let index = 0;
  while ((match = linkPattern.exec(text)) !== null) {
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index));
    const label = match[1] ?? '';
    const url = safeCoachUrl(match[2] ?? '');
    if (url && allowedUrls.has(url)) {
      nodes.push(
        <a href={url} key={`link-${index}`} rel="noreferrer noopener" target="_blank">
          {label}
        </a>,
      );
    } else {
      nodes.push(label);
    }
    cursor = match.index + match[0].length;
    index += 1;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

export function SafeCoachAnswer({
  answer,
  citations,
}: {
  answer: string;
  citations: AiCoachResponse['citations'];
}) {
  const allowedUrls = useMemo(
    () =>
      new Set(
        citations
          .map((citation) => safeCoachUrl(citation.url))
          .filter((url): url is string => Boolean(url)),
      ),
    [citations],
  );
  const normalized = answer.replace(/\r\n?/g, '\n').slice(0, 1_600);
  const lines = normalized.split('\n');
  const blocks: ReactNode[] = [];
  let listItems: ReactNode[] = [];
  const flushList = () => {
    if (!listItems.length) return;
    blocks.push(<ul key={`list-${blocks.length}`}>{listItems}</ul>);
    listItems = [];
  };
  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      return;
    }
    const listMatch = /^[-*]\s+(.+)$/.exec(trimmed);
    if (listMatch) {
      listItems.push(
        <li key={`item-${index}`}>{safeInlineNodes(listMatch[1] ?? '', allowedUrls)}</li>,
      );
      return;
    }
    flushList();
    blocks.push(<p key={`paragraph-${index}`}>{safeInlineNodes(trimmed, allowedUrls)}</p>);
  });
  flushList();
  return <div className="ai-coach-answer__body">{blocks}</div>;
}

function ResponseState({
  mode,
  onFeedback,
  response,
}: {
  mode: AiCoachMode;
  onFeedback(value: AiCoachHelpfulness): void;
  response: AiCoachResponse;
}) {
  const copy = OUTCOME_COPY[response.outcome];
  const citations = response.citations.filter((citation) => safeCoachUrl(citation.url));
  return (
    <section
      aria-live="polite"
      className={`ai-coach-response ai-coach-response--${response.outcome}`}
      data-testid="ai-coach-response"
    >
      <div className="ai-coach-response__heading">
        <div>
          <Badge tone={response.outcome === 'answer' ? 'success' : 'warning'}>{copy.title}</Badge>
          <p>{copy.text}</p>
        </div>
        {response.request_id && <span className="ai-coach-response__request-mark">Проверено</span>}
      </div>
      {response.answer && response.outcome !== 'unavailable' && (
        <SafeCoachAnswer answer={response.answer} citations={citations} />
      )}
      {response.limitations.length > 0 && (
        <div className="ai-coach-response__limitations">
          <strong>Границы ответа</strong>
          <ul>
            {response.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </div>
      )}
      {citations.length > 0 && (
        <div className="ai-coach-response__sources">
          <strong>Источники</strong>
          <ul>
            {citations.map((citation) => {
              const url = safeCoachUrl(citation.url);
              if (!url) return null;
              return (
                <li key={`${citation.title}-${url}`}>
                  <a href={url} rel="noreferrer noopener" target="_blank">
                    {citation.title}
                  </a>
                  <small>{citation.publisher}</small>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      <div className="ai-coach-response__feedback" aria-label="Оценка ответа">
        <span>Ответ был полезен?</span>
        <button type="button" onClick={() => onFeedback('helpful')}>
          Да
        </button>
        <button type="button" onClick={() => onFeedback('not_helpful')}>
          Пока нет
        </button>
      </div>
      <span className="sr-only">
        Режим ответа: {mode === 'personal' ? 'личная сводка' : 'публичная помощь'}.
      </span>
    </section>
  );
}

function ConsentNotice({
  consent,
  onChange,
  pending,
  unavailable,
}: {
  consent: AiCoachConsentResponse | undefined;
  onChange(enabled: boolean): void;
  pending: boolean;
  unavailable: boolean;
}) {
  if (unavailable) {
    return (
      <section
        className="ai-coach-consent ai-coach-consent--unavailable"
        data-testid="ai-coach-personal-unavailable"
      >
        <Badge tone="warning">Персональный режим</Badge>
        <p>
          Персональные сводки пока недоступны в этом внутреннем окружении. Публичная помощь AI Coach
          остаётся отдельным режимом и не получает доступ к вашему профилю.
        </p>
      </section>
    );
  }
  if (consent?.status === 'granted') {
    return (
      <section className="ai-coach-consent" data-testid="ai-coach-consent-granted">
        <div>
          <Badge tone="success">Согласие включено</Badge>
          <p>
            AI Coach получает только ограниченную сводку за выбранный период. План, цели, калории и
            расписание не изменяются.
          </p>
          {consent.retention_notice && <small>{consent.retention_notice}</small>}
        </div>
        <Button
          disabled={pending}
          type="button"
          variant="secondary"
          onClick={() => onChange(false)}
        >
          {pending ? 'Сохраняем…' : 'Отозвать согласие'}
        </Button>
      </section>
    );
  }
  return (
    <section className="ai-coach-consent" data-testid="ai-coach-consent-required">
      <div>
        <Badge tone="warning">Отдельное согласие</Badge>
        <p>
          Передача ограниченной персональной сводки включается отдельно. Сырые записи дневника,
          заметки тренера и история чата не передаются и не сохраняются как память.
        </p>
        <ul>
          <li>
            Только готовая сводка прогресса, тренировок или питания без возможности что-либо менять.
          </li>
          <li>Период выбираете вы: 7, 30 или 90 дней.</li>
          <li>Согласие можно отозвать в любой момент.</li>
        </ul>
      </div>
      <Button disabled={pending} type="button" onClick={() => onChange(true)}>
        {pending ? 'Сохраняем…' : 'Разрешить сводку'}
      </Button>
    </section>
  );
}

export function AiCoachEntry({
  entryPoint,
}: {
  entryPoint: Exclude<AiCoachEntryPoint, 'profile'>;
}) {
  const status = useAiCoachStatus();
  if (!status.data?.ui_enabled) return null;
  return (
    <section className="ai-coach-entry" data-testid={`ai-coach-entry-${entryPoint}`}>
      <div>
        <span className="eyebrow">Внутренняя beta</span>
        <strong>Нужна короткая подсказка?</strong>
        <p>
          AI Coach объясняет опубликованные материалы и отдельно умеет читать ограниченные сводки.
        </p>
      </div>
      <AppLink
        className="button-link secondary-link"
        to="/app?section=profile#profile-ai-coach"
        onClick={() =>
          trackProductEvent({
            name: 'ai_coach_entry_opened',
            surface: productEventSurface(),
            entry_point: entryPoint,
          })
        }
      >
        Открыть AI Coach
      </AppLink>
    </section>
  );
}

export function AiCoachSettingsCard({
  defaultOpen = false,
  status: providedStatus,
}: {
  defaultOpen?: boolean;
  status?: AiCoachStatus;
}) {
  const statusQuery = useAiCoachStatus(!providedStatus);
  const status = providedStatus ?? statusQuery.data;
  if (!status?.ui_enabled) return null;
  return (
    <Card
      className="profile-settings-group ai-coach-settings-card"
      defaultOpen={defaultOpen}
      family="neutral"
      id="profile-ai-coach"
      title="AI Coach · внутренняя beta"
      description="Публичная помощь и отдельные сводки без долгосрочной памяти."
    >
      <AiCoachExperience status={status} entryPoint="profile" />
    </Card>
  );
}

export function AiCoachExperience({
  entryPoint,
  status: providedStatus,
}: {
  entryPoint: AiCoachEntryPoint;
  status?: AiCoachStatus;
}) {
  const statusQuery = useAiCoachStatus(!providedStatus);
  const status = providedStatus ?? statusQuery.data;
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<AiCoachMode>('generic');
  const [genericPromptId, setGenericPromptId] = useState(DEFAULT_GENERIC_PROMPT.id);
  const [personalPromptId, setPersonalPromptId] = useState(DEFAULT_PERSONAL_PROMPT.id);
  const [periodDays, setPeriodDays] = useState<AiCoachPeriod>(30);
  const [draft, setDraft] = useState('');
  const [response, setResponse] = useState<AiCoachResponse | null>(null);
  const [failure, setFailure] = useState<AiCoachFailureClass | null>(null);

  const consent = useQuery<AiCoachConsentResponse>({
    queryKey: aiCoachConsentQueryKey,
    queryFn: () => api<AiCoachConsentResponse>('/api/v1/ai-coach/consent'),
    enabled: status?.personal_available === true,
    staleTime: 30_000,
    retry: false,
  });
  const consentMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      api<AiCoachConsentResponse>('/api/v1/ai-coach/consent', {
        method: 'PUT',
        body: { enabled },
      }),
    onSuccess: (next) => {
      queryClient.setQueryData(aiCoachConsentQueryKey, next);
      trackProductEvent({
        name: 'ai_coach_consent_changed',
        surface: productEventSurface(),
        enabled: next.status === 'granted',
      });
    },
  });

  const selectedGenericPrompt =
    GENERIC_PROMPTS.find((prompt) => prompt.id === genericPromptId) ?? DEFAULT_GENERIC_PROMPT;
  const selectedPersonalPrompt =
    PERSONAL_PROMPTS.find((prompt) => prompt.id === personalPromptId) ?? DEFAULT_PERSONAL_PROMPT;
  const personalConsentGranted = consent.data?.status === 'granted';

  const requestMutation = useMutation({
    mutationFn: (request: AiCoachRequest) =>
      request.mode === 'generic'
        ? api<AiCoachResponse>('/api/v1/ai-coach/generate', {
            method: 'POST',
            body: {
              job: request.job,
              context_id: request.context_id,
              message: request.message,
            },
          })
        : api<AiCoachResponse>('/api/v1/ai-coach/personal/generate', {
            method: 'POST',
            body: {
              tool: request.tool,
              period_days: request.period_days,
              message: request.message,
            },
          }),
    onMutate: (request) => {
      setResponse(null);
      setFailure(null);
      trackProductEvent({
        name: 'ai_coach_request_started',
        surface: productEventSurface(),
        mode: request.mode,
      });
    },
    onSuccess: (next, request) => {
      setResponse(next);
      trackProductEvent({
        name: 'ai_coach_response_received',
        surface: productEventSurface(),
        mode: request.mode,
        outcome: next.outcome,
      });
    },
    onError: (reason, request) => {
      const failureClass = normalizeFailure(reason);
      setFailure(failureClass);
      trackProductEvent({
        name: 'ai_coach_request_failed',
        surface: productEventSurface(),
        mode: request.mode,
        failure: failureClass,
      });
    },
  });

  const reset = () => {
    setResponse(null);
    setFailure(null);
    setDraft('');
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = draft.trim();
    if (!message || requestMutation.isPending) return;
    if (mode === 'generic') {
      if (!status?.generic_available) {
        setResponse({
          outcome: 'unavailable',
          answer: null,
          citations: [],
          limitations: [
            'Публичная помощь AI Coach сейчас выключена для этого внутреннего окружения.',
          ],
          safety_category: 'clear',
          prompt_version: AI_COACH_UI_EVAL_VERSION,
          request_id: null,
        });
        return;
      }
      requestMutation.mutate({
        mode,
        job: selectedGenericPrompt.job,
        context_id: selectedGenericPrompt.context_id,
        message,
      });
      return;
    }
    if (!status?.personal_available) {
      setResponse({
        outcome: 'unavailable',
        answer: null,
        citations: [],
        limitations: [
          'Персональная сводка сейчас недоступна; публичная помощь остаётся отдельным режимом.',
        ],
        safety_category: 'clear',
        prompt_version: AI_COACH_UI_EVAL_VERSION,
        request_id: null,
      });
      return;
    }
    if (!personalConsentGranted) {
      setResponse({
        outcome: 'consent_required',
        answer: null,
        citations: [],
        limitations: [],
        safety_category: 'clear',
        prompt_version: AI_COACH_UI_EVAL_VERSION,
        request_id: null,
      });
      return;
    }
    requestMutation.mutate({
      mode,
      tool: selectedPersonalPrompt.tool,
      period_days: periodDays,
      message,
    });
  };

  const sendFeedback = (value: AiCoachHelpfulness) => {
    trackProductEvent({
      name: 'ai_coach_helpfulness_submitted',
      surface: productEventSurface(),
      value,
    });
  };

  if (!status?.ui_enabled) {
    return (
      <section className="ai-coach-unavailable" data-testid="ai-coach-ui-disabled">
        <p>AI Coach не включён для этой внутренней группы.</p>
      </section>
    );
  }

  return (
    <section className="ai-coach-experience" data-testid="ai-coach-experience">
      <header className="ai-coach-experience__intro">
        <div>
          <span className="eyebrow">Внутренняя проверка</span>
          <h3>Проверяем полезность маленькими шагами</h3>
          <p>
            Здесь нет долгосрочной памяти и автоматических изменений. Публичный режим работает по
            опубликованному материалу, а личный — только по одной готовой сводке за выбранный
            период.
          </p>
        </div>
        <Badge tone="warning">Не замена врачу или тренеру</Badge>
      </header>

      <div className="ai-coach-boundary">
        <strong>Что не передаётся</strong>
        <span>
          Сырые записи дневника, заметки тренера, идентификаторы аккаунта и история диалога.
        </span>
      </div>

      <div className="ai-coach-modes" aria-label="Режим AI Coach" role="group">
        <button
          aria-pressed={mode === 'generic'}
          className={mode === 'generic' ? 'is-active' : ''}
          type="button"
          onClick={() => {
            setMode('generic');
            setResponse(null);
            setFailure(null);
          }}
        >
          Публичная помощь
        </button>
        <button
          aria-pressed={mode === 'personal'}
          className={mode === 'personal' ? 'is-active' : ''}
          type="button"
          onClick={() => {
            setMode('personal');
            setResponse(null);
            setFailure(null);
          }}
        >
          Моя сводка
        </button>
      </div>

      {mode === 'personal' && (
        <ConsentNotice
          consent={consent.data}
          onChange={(enabled) => consentMutation.mutate(enabled)}
          pending={consentMutation.isPending}
          unavailable={!status.personal_available}
        />
      )}
      {consent.isError && mode === 'personal' && status.personal_available && (
        <p className="ai-coach-inline-error" role="alert">
          Не удалось проверить согласие. Публичная помощь остаётся доступной отдельно.
        </p>
      )}

      <div className="ai-coach-prompt-grid" aria-label="Быстрые вопросы">
        {(mode === 'generic' ? GENERIC_PROMPTS : PERSONAL_PROMPTS).map((prompt) => {
          const selected =
            mode === 'generic' ? prompt.id === genericPromptId : prompt.id === personalPromptId;
          return (
            <button
              className={selected ? 'is-selected' : ''}
              key={prompt.id}
              type="button"
              onClick={() => {
                if (mode === 'generic') setGenericPromptId(prompt.id);
                else setPersonalPromptId(prompt.id);
                setDraft(prompt.message);
                setResponse(null);
                setFailure(null);
              }}
            >
              {prompt.label}
            </button>
          );
        })}
      </div>

      {mode === 'personal' && (
        <label className="ai-coach-period">
          <span>Период сводки</span>
          <select
            value={periodDays}
            onChange={(event) => setPeriodDays(Number(event.target.value) as AiCoachPeriod)}
          >
            <option value={7}>7 дней</option>
            <option value={30}>30 дней</option>
            <option value={90}>90 дней</option>
          </select>
        </label>
      )}

      <form className="ai-coach-form" onSubmit={submit}>
        <label htmlFor="ai-coach-question">Ваш вопрос</label>
        <textarea
          id="ai-coach-question"
          maxLength={320}
          minLength={1}
          placeholder="Например: с чего начать чтение этого раздела?"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <div className="ai-coach-form__meta">
          <small>До 320 символов. Один вопрос без истории диалога.</small>
          <small>{draft.length}/320</small>
        </div>
        <div className="ai-coach-form__actions">
          <Button disabled={!draft.trim() || requestMutation.isPending} type="submit">
            {requestMutation.isPending ? 'Проверяем…' : 'Получить ответ'}
          </Button>
          <Button type="button" variant="secondary" onClick={reset}>
            Новый вопрос
          </Button>
        </div>
      </form>

      {!status.generic_available && mode === 'generic' && (
        <section
          className="ai-coach-state ai-coach-state--unavailable"
          data-testid="ai-coach-generic-unavailable"
        >
          <Badge tone="warning">Публичная помощь недоступна</Badge>
          <p>
            AI Coach выключен или временно не готов в этом внутреннем окружении. Остальные функции
            YFC работают.
          </p>
        </section>
      )}

      {failure && (
        <section
          className="ai-coach-state ai-coach-state--error"
          role="alert"
          data-testid="ai-coach-request-error"
        >
          <strong>Ответ не получен</strong>
          <p>{SAFE_FAILURE_COPY[failure]}</p>
          <button type="button" onClick={() => setFailure(null)}>
            Понятно
          </button>
        </section>
      )}
      {requestMutation.isPending && <LoadingState label="Проверяем разрешённый контекст…" />}
      {response && !requestMutation.isPending && (
        <ResponseState mode={mode} onFeedback={sendFeedback} response={response} />
      )}

      <footer className="ai-coach-experience__footer">
        <span>
          Это внутренний beta-экран. Автоматическая проверка не является отзывом реального
          пользователя.
        </span>
        <AppLink to="/app?section=today">Продолжить без AI</AppLink>
        {entryPoint !== 'profile' && (
          <AppLink to="/app?section=profile#profile-ai-coach">Открыть настройки AI Coach</AppLink>
        )}
      </footer>
    </section>
  );
}
