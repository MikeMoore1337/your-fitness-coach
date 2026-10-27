import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  AssignedCheckInTemplate,
  AssignedCheckInTemplateList,
  CheckInTemplateResponseItem,
} from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Button, Card, ErrorState, LoadingState } from '../../shared/ui/common';

function newIdempotencyKey(): string {
  return `check-in-response-${crypto.randomUUID()}`;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function AssignedCheckInTemplates({ readOnly = false }: { readOnly?: boolean }) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const [drafts, setDrafts] = useState<Record<number, Record<string, number>>>({});
  const assigned = useQuery<AssignedCheckInTemplateList>({
    queryKey: queryKeys.checkInTemplates.assigned,
    queryFn: () => api<AssignedCheckInTemplateList>('/api/v1/check-ins/templates/assigned'),
  });
  const submit = useMutation<
    CheckInTemplateResponseItem,
    Error,
    { assignmentId: number; values: Record<string, number> }
  >({
    mutationFn: ({ assignmentId, values }) =>
      api<CheckInTemplateResponseItem>(
        `/api/v1/check-ins/templates/assignments/${assignmentId}/responses`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': newIdempotencyKey() },
          body: { values },
        },
      ),
    onSuccess: async (_response, variables) => {
      setDrafts((current) => ({ ...current, [variables.assignmentId]: {} }));
      await queryClient.invalidateQueries({ queryKey: queryKeys.checkInTemplates.assigned });
      toast('Ответ на проверку сохранён');
    },
    onError: (reason) => toast(reason.message, 'error'),
  });
  const items = assigned.data?.items ?? [];
  const today = todayIso();

  if (assigned.isPending) return <LoadingState label="Проверяем задания тренера…" />;
  if (assigned.error) {
    return (
      <ErrorState
        message="Проверки тренера временно недоступны."
        retry={() => void assigned.refetch()}
      />
    );
  }
  if (!items.length) return null;

  return (
    <Card
      className="assigned-check-in-templates"
      collapsible={false}
      family="wellbeing"
      title="Проверки тренера"
      description="Дополнительные вопросы от тренера. Каждый ответ сохраняется в своей версии проверки."
    >
      <div className="assigned-check-in-templates__list">
        {items.map((item: AssignedCheckInTemplate) => {
          const values = drafts[item.assignment_id] ?? {};
          const fields = item.fields ?? [];
          const missingRequired = fields.some(
            (field) => field.required && values[field.key] == null,
          );
          const isDue = item.next_due_on <= today;
          return (
            <article className="assigned-check-in-template" key={item.assignment_id}>
              <header>
                <div>
                  <span className="eyebrow">
                    {item.next_due_on} · версия {item.version}
                  </span>
                  <h3>{item.name}</h3>
                </div>
                {!isDue && <span className="muted">Доступна с {item.next_due_on}</span>}
              </header>
              {item.description && <p className="muted">{item.description}</p>}
              <fieldset disabled={readOnly || !isDue || submit.isPending}>
                <div className="assigned-check-in-template__fields">
                  {fields.map((field) => (
                    <label className="field" key={field.key}>
                      <span>
                        {field.label}
                        {field.required ? ' · обязательно' : ' · по желанию'}
                      </span>
                      <select
                        aria-required={field.required}
                        className="ui-input"
                        onChange={(event) =>
                          setDrafts((current) => ({
                            ...current,
                            [item.assignment_id]: {
                              ...(current[item.assignment_id] ?? {}),
                              ...(event.target.value
                                ? { [field.key]: Number(event.target.value) }
                                : (() => {
                                    const next = { ...(current[item.assignment_id] ?? {}) };
                                    delete next[field.key];
                                    return next;
                                  })()),
                            },
                          }))
                        }
                        value={values[field.key] ?? ''}
                      >
                        <option value="">Выберите оценку</option>
                        {[1, 2, 3, 4, 5].map((score) => (
                          <option key={score} value={score}>
                            {score}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
                <Button
                  disabled={missingRequired || readOnly || !isDue || submit.isPending}
                  onClick={() => submit.mutate({ assignmentId: item.assignment_id, values })}
                  type="button"
                >
                  {submit.isPending ? 'Сохраняем…' : 'Отправить ответ'}
                </Button>
              </fieldset>
            </article>
          );
        })}
      </div>
    </Card>
  );
}
