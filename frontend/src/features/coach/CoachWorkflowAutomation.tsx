import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { CoachWorkflowAutomation } from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { AppLink } from '../../shared/navigation/router';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Badge, Button, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';

type CoachWorkflowProposal = NonNullable<CoachWorkflowAutomation['proposals']>[number];

const eventLabels: Record<CoachWorkflowProposal['event_kind'], string> = {
  check_in_submitted: 'Новый недельный итог',
  missed_workout: 'Пропущенная тренировка',
  review_due: 'Просроченная проверка',
  program_revision_ready: 'Ревизия программы',
};

function outcomeLabel(proposal: CoachWorkflowProposal): {
  label: string;
  tone: 'neutral' | 'success' | 'warning';
} {
  if (proposal.outcome === 'created') return { label: 'Открыто', tone: 'warning' };
  if (proposal.outcome === 'already_processed') {
    return {
      label: proposal.task_state === 'completed' ? 'Подтверждено' : 'Открыто',
      tone: 'neutral',
    };
  }
  return { label: 'Черновик', tone: 'warning' };
}

export function CoachWorkflowAutomation() {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const preview = useQuery<CoachWorkflowAutomation>({
    queryKey: queryKeys.trainer.workflowAutomation,
    queryFn: () => api<CoachWorkflowAutomation>('/api/v1/coach/workflow-automation/preview'),
    staleTime: 15_000,
    retry: false,
  });
  const evaluate = useMutation({
    mutationFn: () =>
      api<CoachWorkflowAutomation>('/api/v1/coach/workflow-automation/evaluate', {
        method: 'POST',
      }),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.setQueryData(queryKeys.trainer.workflowAutomation, result),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.inbox }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.tasks }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.capacity }),
      ]);
      toast(
        result.tasks_created
          ? `Предложений создано: ${result.tasks_created}`
          : 'Новых предложений нет',
      );
    },
    onError: (error) =>
      toast(error instanceof Error ? error.message : 'Не удалось собрать предложения', 'error'),
  });

  const data = evaluate.data ?? preview.data;
  const proposals = data?.proposals ?? [];
  return (
    <section
      className="coach-workflow-automation"
      data-testid="coach-workflow-automation"
      aria-labelledby="coach-workflow-automation-title"
    >
      <header className="coach-workflow-automation__heading">
        <div>
          <span className="eyebrow">Правила рабочего списка</span>
          <h2 id="coach-workflow-automation-title">Предложения для тренера</h2>
          <p>
            События превращаются только в открытые задачи. Программа, сообщения и решения остаются
            под ручным контролем тренера.
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          disabled={evaluate.isPending}
          onClick={() => evaluate.mutate()}
        >
          {evaluate.isPending ? 'Собираем…' : 'Собрать предложения'}
        </Button>
      </header>

      {preview.isPending && !data ? (
        <LoadingState label="Проверяем события клиентов…" />
      ) : preview.error && !data ? (
        <ErrorState
          message="Предложения временно недоступны. Рабочий список продолжает работать."
          retry={() => void preview.refetch()}
        />
      ) : !proposals.length ? (
        <EmptyState
          title="Новых предложений нет"
          text="Правила не нашли нового события, требующего ручного решения."
        />
      ) : (
        <ul className="coach-workflow-automation__list">
          {proposals.map((proposal) => {
            const outcome = outcomeLabel(proposal);
            return (
              <li className="coach-workflow-automation__item" key={proposal.key}>
                <div className="coach-workflow-automation__copy">
                  <div className="coach-workflow-automation__meta">
                    <span className="eyebrow">{proposal.client_name}</span>
                    <span>{eventLabels[proposal.event_kind]}</span>
                    <Badge tone={outcome.tone}>{outcome.label}</Badge>
                  </div>
                  <strong>{proposal.title}</strong>
                  <p>{proposal.reason}</p>
                  {proposal.outcome !== 'already_processed' && (
                    <small>Черновик задачи требует подтверждения тренера.</small>
                  )}
                </div>
                {proposal.task_id && (
                  <AppLink className="button-link secondary-link" to="/coach?tab=tools&tool=tasks">
                    Открыть задачу
                  </AppLink>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
