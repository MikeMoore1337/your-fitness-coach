import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../shared/api/client';
import type { Client, CoachAssignedProgram, ProgramTemplate } from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Select,
} from '../../shared/ui/common';
import { ProgramImportPanel } from '../programs/ProgramImportPanel';
import { CoachProgramBulkOperations } from './CoachProgramBulkOperations';

type AssignmentOutcome = {
  clientId: number;
  clientName: string;
  status: 'assigned' | 'already_assigned' | 'failed';
  detail?: string;
};

function assignmentErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) {
    return 'У клиента уже есть активная программа. Существующее назначение сохранено.';
  }
  if (error instanceof ApiError && error.status === 404) {
    return 'Связь с клиентом или доступность шаблона изменилась. Обновите данные и повторите.';
  }
  if (error instanceof ApiError && error.status === 403) {
    return 'Этот шаблон нельзя назначить выбранному клиенту.';
  }
  return 'Не удалось назначить программу. Обновите данные и повторите.';
}

function clientName(client: Client): string {
  const name = client.full_name?.trim();
  const username = client.username?.trim();
  if (name && username) return `${name} · @${username}`;
  return name || (username ? `@${username}` : `Клиент ${client.id}`);
}

export function CoachProgramOperations({
  clients,
  programs,
}: {
  clients: Client[];
  programs: CoachAssignedProgram[];
}) {
  const { confirm, toast } = useFeedback();
  const queryClient = useQueryClient();
  const [templateId, setTemplateId] = useState('');
  const [selectedClientIds, setSelectedClientIds] = useState<number[]>([]);
  const [outcomes, setOutcomes] = useState<AssignmentOutcome[]>([]);
  const activeClients = useMemo(
    () => clients.filter((client) => client.status === 'active' && client.id != null),
    [clients],
  );
  const templates = useQuery({
    queryKey: ['templates'],
    queryFn: () => api<ProgramTemplate[]>('/api/v1/programs/templates/mine'),
  });
  const selectedTemplate = templates.data?.find((template) => String(template.id) === templateId);
  const selectedClients = activeClients.filter(
    (client) => client.id != null && selectedClientIds.includes(client.id),
  );
  const allClientsSelected =
    activeClients.length > 0 && selectedClients.length === activeClients.length;

  const assignment = useMutation({
    mutationFn: async (): Promise<AssignmentOutcome[]> => {
      if (!selectedTemplate || selectedClients.length === 0) {
        throw new Error('Выберите шаблон и одного или нескольких активных клиентов');
      }

      return Promise.all(
        selectedClients.map(async (client): Promise<AssignmentOutcome> => {
          const id = client.id;
          if (id == null) return { clientId: 0, clientName: clientName(client), status: 'failed' };
          const current = programs.find((program) => program.client_id === id && program.is_active);
          if (current?.template_id === selectedTemplate.id) {
            return { clientId: id, clientName: clientName(client), status: 'already_assigned' };
          }

          try {
            await api<void>(`/api/v1/coach/clients/${id}/templates/${selectedTemplate.id}/assign`, {
              method: 'POST',
              body: {
                duration_weeks: selectedTemplate.default_duration_weeks,
                replace_active: false,
              },
            });
            return { clientId: id, clientName: clientName(client), status: 'assigned' };
          } catch (error) {
            return {
              clientId: id,
              clientName: clientName(client),
              status: 'failed',
              detail: assignmentErrorMessage(error),
            };
          }
        }),
      );
    },
    onSuccess: async (result) => {
      setOutcomes(result);
      const failedIds = result
        .filter((item) => item.status === 'failed')
        .map((item) => item.clientId);
      setSelectedClientIds(failedIds);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['coach', 'programs'] }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.clientSummaries }),
      ]);
      const assignedCount = result.filter((item) => item.status === 'assigned').length;
      const failedCount = failedIds.length;
      if (failedCount) {
        toast(
          `Назначено: ${assignedCount}. Не выполнено: ${failedCount}; проверьте результат по клиентам.`,
          'error',
        );
      } else if (assignedCount) {
        toast(`Программа назначена ${assignedCount} клиентам`);
      } else {
        toast('У выбранных клиентов эта программа уже назначена');
      }
    },
    onError: (error) =>
      toast(error instanceof Error ? error.message : 'Не удалось назначить программу', 'error'),
  });

  const clone = useMutation({
    mutationFn: (sourceTemplateId: number) =>
      api<ProgramTemplate>(`/api/v1/programs/templates/${sourceTemplateId}/clone`, {
        method: 'POST',
      }),
    onSuccess: async (template) => {
      setTemplateId(String(template.id));
      queryClient.setQueryData<ProgramTemplate[]>(['templates'], (current) =>
        current ? [template, ...current] : [template],
      );
      await queryClient.invalidateQueries({ queryKey: ['templates'] });
      toast(`Создана копия «${template.title}»`);
    },
    onError: (error) =>
      toast(
        error instanceof ApiError && error.status === 403
          ? 'У вас нет доступа к исходному шаблону.'
          : error instanceof ApiError && error.status === 404
            ? 'Исходный шаблон уже недоступен. Обновите список.'
            : 'Не удалось создать копию шаблона. Повторите попытку.',
        'error',
      ),
  });

  const assignSelected = async () => {
    if (!selectedTemplate || selectedClients.length === 0) return;
    const clientList = selectedClients.map(clientName).join(', ');
    const approved = await confirm({
      title: 'Назначить один шаблон клиентам?',
      message:
        `«${selectedTemplate.title}» будет назначен отдельно: ${clientList}. ` +
        'У существующих программ не будут отменены будущие тренировки или история.',
      confirmText: `Назначить ${selectedClients.length}`,
    });
    if (approved) assignment.mutate();
  };

  const cloneSelectedTemplate = async () => {
    if (!selectedTemplate) return;
    const approved = await confirm({
      title: 'Создать копию шаблона?',
      message:
        `«${selectedTemplate.title}» будет скопирован в ваши шаблоны. ` +
        'Исходная программа и назначения клиентов не изменятся.',
      confirmText: 'Создать копию',
    });
    if (approved) clone.mutate(selectedTemplate.id);
  };

  const setAllClientsSelected = () => {
    setSelectedClientIds(
      allClientsSelected
        ? []
        : activeClients.flatMap((client) => (client.id == null ? [] : [client.id])),
    );
  };

  return (
    <Card
      className="coach-program-operations"
      title="Подготовить и назначить программу"
      description="Импортируйте исходную программу или выберите базовый шаблон. Каждое назначение и последующие правки хранят отдельную историю клиента."
    >
      <details className="coach-program-operations__import">
        <summary>Импортировать программу с источником</summary>
        <ProgramImportPanel
          onImported={() => void queryClient.invalidateQueries({ queryKey: ['templates'] })}
        />
      </details>

      {templates.isLoading ? (
        <LoadingState label="Загружаем базовые шаблоны…" />
      ) : templates.error ? (
        <ErrorState
          message="Не удалось загрузить шаблоны программ. Повторите попытку."
          retry={() => void templates.refetch()}
        />
      ) : templates.data?.length ? (
        <form
          className="coach-program-operations__form"
          onSubmit={(event) => {
            event.preventDefault();
            void assignSelected();
          }}
        >
          <Field label="Базовый шаблон" labelFor="coach-program-template">
            <Select
              id="coach-program-template"
              required
              value={templateId}
              onChange={(event) => {
                setTemplateId(event.target.value);
              }}
            >
              <option value="">Выберите шаблон</option>
              {templates.data.map((template) => (
                <option value={template.id} key={template.id}>
                  {template.title} · {template.default_duration_weeks} нед.
                </option>
              ))}
            </Select>
          </Field>

          {activeClients.length ? (
            <fieldset className="coach-program-operations__client-fieldset">
              <legend>Клиенты</legend>
              <Button
                type="button"
                variant="secondary"
                onClick={setAllClientsSelected}
                disabled={assignment.isPending}
              >
                {allClientsSelected ? 'Снять выбор' : 'Выбрать всех'}
              </Button>
              <div className="coach-program-operations__clients">
                {activeClients.map((client) => {
                  const id = client.id;
                  if (id == null) return null;
                  const current = programs.find(
                    (program) => program.client_id === id && program.is_active,
                  );
                  return (
                    <label className="coach-program-operations__client" key={id}>
                      <input
                        type="checkbox"
                        checked={selectedClientIds.includes(id)}
                        disabled={assignment.isPending}
                        onChange={(event) =>
                          setSelectedClientIds((currentIds) =>
                            event.target.checked
                              ? [...currentIds, id]
                              : currentIds.filter((currentId) => currentId !== id),
                          )
                        }
                      />
                      <span>
                        <strong>{clientName(client)}</strong>
                        <small>
                          {current ? `Сейчас: ${current.title}` : 'Без активной программы тренера'}
                        </small>
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ) : (
            <EmptyState
              title="Нет активных клиентов"
              text="После подтверждения связи с клиентом его можно будет добавить в назначение."
            />
          )}

          <p className="coach-program-operations__note">
            Шаблон остаётся неизменным. Новая программа создаётся для каждого выбранного клиента;
            активная программа автоматически не заменяется.
          </p>
          <Button
            type="submit"
            disabled={assignment.isPending || !selectedTemplate || selectedClients.length === 0}
          >
            {assignment.isPending
              ? 'Назначаем…'
              : `Назначить выбранным · ${selectedClients.length}`}
          </Button>
        </form>
      ) : (
        <EmptyState
          title="Базовых шаблонов пока нет"
          text="Импортируйте программу выше или создайте шаблон в разделе программ."
        />
      )}

      {selectedTemplate && (
        <Button
          type="button"
          variant="secondary"
          onClick={() => void cloneSelectedTemplate()}
          disabled={clone.isPending}
        >
          {clone.isPending ? 'Создаём копию…' : 'Создать копию выбранного шаблона'}
        </Button>
      )}

      {outcomes.length > 0 && (
        <ul className="coach-program-operations__results" aria-live="polite">
          {outcomes.map((item) => (
            <li
              key={`${item.clientId}-${item.status}`}
              className={item.status === 'failed' ? 'is-failed' : undefined}
            >
              <strong>{item.clientName}:</strong>{' '}
              {item.status === 'assigned'
                ? 'программа назначена'
                : item.status === 'already_assigned'
                  ? 'этот шаблон уже назначен'
                  : item.detail || 'назначение не выполнено'}
            </li>
          ))}
        </ul>
      )}
      <CoachProgramBulkOperations
        programs={programs}
        selectedClients={selectedClients}
        selectedTemplate={selectedTemplate}
      />
    </Card>
  );
}
