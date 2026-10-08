import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  CheckInTemplateList,
  Client,
  CommunicationWorkflowDraft,
  CommunicationWorkflowTemplate,
  CommunicationWorkflowTemplateList,
  OnboardingWorkflowTemplate,
  OnboardingWorkflowTemplateList,
  ProgramTemplate,
} from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';
import { clientDisplayName } from './coachWorkspace';

type StepKey =
  | 'invite'
  | 'questionnaire'
  | 'goals'
  | 'equipment'
  | 'restrictions'
  | 'measurements'
  | 'program'
  | 'first_check_in'
  | 'agenda';

const stepChoices: ReadonlyArray<{ key: StepKey; label: string }> = [
  { key: 'invite', label: 'Приглашение' },
  { key: 'questionnaire', label: 'Анкета' },
  { key: 'goals', label: 'Цели' },
  { key: 'equipment', label: 'Оборудование' },
  { key: 'restrictions', label: 'Ограничения' },
  { key: 'measurements', label: 'Замеры' },
  { key: 'program', label: 'Программа' },
  { key: 'first_check_in', label: 'Первая проверка' },
  { key: 'agenda', label: 'Внутренняя повестка' },
];

function idempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

function toggleStep(steps: StepKey[], key: StepKey, checked: boolean): StepKey[] {
  return checked ? [...steps, key] : steps.filter((step) => step !== key);
}

function StepPicker({
  disabled,
  idPrefix,
  onChange,
  steps,
}: {
  disabled?: boolean;
  idPrefix: string;
  onChange: (steps: StepKey[]) => void;
  steps: StepKey[];
}) {
  return (
    <fieldset className="coach-workflow-templates__steps">
      <legend>Этапы подключения</legend>
      {stepChoices.map((choice) => (
        <label
          className={`coach-workflow-templates__step${
            steps.includes(choice.key) ? ' is-selected' : ''
          }`}
          htmlFor={`${idPrefix}-${choice.key}`}
          key={choice.key}
        >
          <input
            checked={steps.includes(choice.key)}
            disabled={disabled}
            id={`${idPrefix}-${choice.key}`}
            onChange={(event) => onChange(toggleStep(steps, choice.key, event.target.checked))}
            type="checkbox"
          />
          <span>{choice.label}</span>
        </label>
      ))}
    </fieldset>
  );
}

function ReferenceFields({
  checkInTemplates,
  checkInTemplateId,
  disabled,
  onCheckInTemplateChange,
  onProgramChange,
  programTemplateId,
  programTemplates,
  steps,
}: {
  checkInTemplates: CheckInTemplateList['items'];
  checkInTemplateId: number | null;
  disabled?: boolean;
  onCheckInTemplateChange: (value: number | null) => void;
  onProgramChange: (value: number | null) => void;
  programTemplateId: number | null;
  programTemplates: ProgramTemplate[];
  steps: StepKey[];
}) {
  return (
    <div className="coach-workflow-templates__references">
      {steps.includes('program') && (
        <label className="field">
          <span>Шаблон программы</span>
          <select
            className="ui-input"
            disabled={disabled}
            onChange={(event) =>
              onProgramChange(event.target.value ? Number(event.target.value) : null)
            }
            value={programTemplateId ?? ''}
          >
            <option value="">Выберите существующую программу</option>
            {programTemplates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.title}
              </option>
            ))}
          </select>
        </label>
      )}
      {steps.includes('first_check_in') && (
        <label className="field">
          <span>Шаблон первой проверки</span>
          <select
            className="ui-input"
            disabled={disabled}
            onChange={(event) =>
              onCheckInTemplateChange(event.target.value ? Number(event.target.value) : null)
            }
            value={checkInTemplateId ?? ''}
          >
            <option value="">Выберите существующую проверку</option>
            {(checkInTemplates ?? []).map((template) => (
              <option key={template.id} value={template.id}>
                {template.name}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}

function activeClientOptions(clients: Client[]): Client[] {
  return clients.filter((client) => client.status === 'active' && client.id != null);
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

export function CoachWorkflowTemplates({
  clients,
  canManage = true,
}: {
  clients: Client[];
  canManage?: boolean;
}) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const activeClients = useMemo(() => activeClientOptions(clients), [clients]);
  const [onboardingName, setOnboardingName] = useState('');
  const [onboardingDescription, setOnboardingDescription] = useState('');
  const [onboardingSteps, setOnboardingSteps] = useState<StepKey[]>([
    'invite',
    'goals',
    'equipment',
    'restrictions',
  ]);
  const [onboardingProgramId, setOnboardingProgramId] = useState<number | null>(null);
  const [onboardingCheckInId, setOnboardingCheckInId] = useState<number | null>(null);
  const [onboardingClientIds, setOnboardingClientIds] = useState<Record<number, string>>({});
  const [versioningOnboardingId, setVersioningOnboardingId] = useState<number | null>(null);
  const [versionSteps, setVersionSteps] = useState<StepKey[]>([]);
  const [versionProgramId, setVersionProgramId] = useState<number | null>(null);
  const [versionCheckInId, setVersionCheckInId] = useState<number | null>(null);
  const [communicationName, setCommunicationName] = useState('');
  const [communicationDescription, setCommunicationDescription] = useState('');
  const [communicationSubject, setCommunicationSubject] = useState('');
  const [communicationBody, setCommunicationBody] = useState('');
  const [communicationClientIds, setCommunicationClientIds] = useState<Record<number, string>>({});
  const [versioningCommunicationId, setVersioningCommunicationId] = useState<number | null>(null);
  const [versionSubject, setVersionSubject] = useState('');
  const [versionBody, setVersionBody] = useState('');
  const [selectedDraftId, setSelectedDraftId] = useState<number | null>(null);
  const [draftEdits, setDraftEdits] = useState<Record<number, { subject: string; body: string }>>(
    {},
  );

  const onboarding = useQuery<OnboardingWorkflowTemplateList>({
    queryKey: queryKeys.trainer.onboardingWorkflowTemplates,
    queryFn: () =>
      api<OnboardingWorkflowTemplateList>('/api/v1/coach/workflow-templates/onboarding'),
  });
  const communication = useQuery<CommunicationWorkflowTemplateList>({
    queryKey: queryKeys.trainer.communicationWorkflowTemplates,
    queryFn: () =>
      api<CommunicationWorkflowTemplateList>('/api/v1/coach/workflow-templates/communication'),
  });
  const programs = useQuery<ProgramTemplate[]>({
    queryKey: ['coach', 'program-templates'],
    queryFn: () => api<ProgramTemplate[]>('/api/v1/programs/templates/mine'),
  });
  const checkIns = useQuery<CheckInTemplateList>({
    queryKey: queryKeys.trainer.checkInTemplates,
    queryFn: () => api<CheckInTemplateList>('/api/v1/coach/check-in-templates'),
  });
  const draft = useQuery<CommunicationWorkflowDraft>({
    queryKey: queryKeys.trainer.communicationWorkflowDraft(selectedDraftId ?? 0),
    queryFn: () =>
      api<CommunicationWorkflowDraft>(`/api/v1/coach/communication-drafts/${selectedDraftId}`),
    enabled: selectedDraftId != null,
  });

  const selectedDraft = draft.data;
  const draftEdit = selectedDraft ? draftEdits[selectedDraft.id] : undefined;
  const currentDraftSubject = draftEdit?.subject ?? selectedDraft?.subject ?? '';
  const currentDraftBody = draftEdit?.body ?? selectedDraft?.body ?? '';

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.trainer.onboardingWorkflowTemplates }),
      queryClient.invalidateQueries({ queryKey: queryKeys.trainer.communicationWorkflowTemplates }),
    ]);
  };
  const createOnboarding = useMutation({
    mutationFn: () =>
      api<OnboardingWorkflowTemplate>('/api/v1/coach/workflow-templates/onboarding', {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey('onboarding-template') },
        body: {
          name: onboardingName,
          description: onboardingDescription || null,
          steps: onboardingSteps,
          program_template_id: onboardingProgramId,
          check_in_template_id: onboardingCheckInId,
        },
      }),
    onSuccess: async () => {
      setOnboardingName('');
      setOnboardingDescription('');
      await refresh();
      toast('План подключения создан');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const createOnboardingVersion = useMutation({
    mutationFn: ({ templateId }: { templateId: number }) =>
      api(`/api/v1/coach/workflow-templates/onboarding/${templateId}/versions`, {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey('onboarding-version') },
        body: {
          steps: versionSteps,
          program_template_id: versionProgramId,
          check_in_template_id: versionCheckInId,
        },
      }),
    onSuccess: async () => {
      setVersioningOnboardingId(null);
      await refresh();
      toast('Новая версия плана подключения сохранена');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const assignOnboarding = useMutation({
    mutationFn: ({
      templateId,
      clientId,
      version,
    }: {
      templateId: number;
      clientId: number;
      version: number;
    }) =>
      api(`/api/v1/coach/workflow-templates/onboarding/${templateId}/assignments`, {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey('onboarding-assignment') },
        body: { client_id: clientId, version },
      }),
    onSuccess: async () => {
      await refresh();
      toast('План подключения назначен клиенту');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const createCommunication = useMutation({
    mutationFn: () =>
      api<CommunicationWorkflowTemplate>('/api/v1/coach/workflow-templates/communication', {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey('communication-template') },
        body: {
          name: communicationName,
          description: communicationDescription || null,
          subject: communicationSubject,
          body: communicationBody,
        },
      }),
    onSuccess: async () => {
      setCommunicationName('');
      setCommunicationDescription('');
      setCommunicationSubject('');
      setCommunicationBody('');
      await refresh();
      toast('Шаблон сообщения создан');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const createCommunicationVersion = useMutation({
    mutationFn: ({ templateId }: { templateId: number }) =>
      api(`/api/v1/coach/workflow-templates/communication/${templateId}/versions`, {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey('communication-version') },
        body: { subject: versionSubject, body: versionBody },
      }),
    onSuccess: async () => {
      setVersioningCommunicationId(null);
      await refresh();
      toast('Новая версия шаблона сообщения сохранена');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const createDraft = useMutation({
    mutationFn: ({ templateId, clientId }: { templateId: number; clientId: number }) =>
      api<CommunicationWorkflowDraft>(
        `/api/v1/coach/workflow-templates/communication/${templateId}/drafts`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': idempotencyKey('communication-draft') },
          body: { client_id: clientId },
        },
      ),
    onSuccess: async (created) => {
      setSelectedDraftId(created.id);
      setDraftEdits((values) => ({
        ...values,
        [created.id]: { subject: created.subject, body: created.body },
      }));
      queryClient.setQueryData(queryKeys.trainer.communicationWorkflowDraft(created.id), created);
      await refresh();
      toast('Черновик сообщения создан');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const updateDraft = useMutation({
    mutationFn: () =>
      api<CommunicationWorkflowDraft>(`/api/v1/coach/communication-drafts/${selectedDraftId}`, {
        method: 'PATCH',
        body: { subject: currentDraftSubject, body: currentDraftBody },
      }),
    onSuccess: async (updated) => {
      setDraftEdits((values) => ({
        ...values,
        [updated.id]: { subject: updated.subject, body: updated.body },
      }));
      queryClient.setQueryData(queryKeys.trainer.communicationWorkflowDraft(updated.id), updated);
      await refresh();
      toast('Черновик сообщения сохранён');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });
  const confirmDraft = useMutation({
    mutationFn: () =>
      api<CommunicationWorkflowDraft>(
        `/api/v1/coach/communication-drafts/${selectedDraftId}/confirm`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': idempotencyKey('communication-confirmation') },
        },
      ),
    onSuccess: async (confirmed) => {
      queryClient.setQueryData(
        queryKeys.trainer.communicationWorkflowDraft(confirmed.id),
        confirmed,
      );
      await refresh();
      toast('Сообщение подтверждено и добавлено в уведомления клиента');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  if (onboarding.isPending || communication.isPending || programs.isPending || checkIns.isPending) {
    return <LoadingState label="Загружаем планы подключения и сообщения…" />;
  }
  if (onboarding.error || communication.error || programs.error || checkIns.error) {
    return (
      <ErrorState
        message="Не удалось загрузить планы подключения и сообщения."
        retry={() => {
          void onboarding.refetch();
          void communication.refetch();
          void programs.refetch();
          void checkIns.refetch();
        }}
      />
    );
  }

  const onboardingItems = onboarding.data?.items ?? [];
  const communicationItems = communication.data?.items ?? [];
  const programItems = programs.data ?? [];
  const checkInItems = checkIns.data?.items ?? [];

  return (
    <section className="coach-workflow-templates" data-testid="coach-workflow-templates">
      <Card
        className="coach-workflow-templates__intro"
        collapsible={false}
        title="Подключение клиентов и сообщения"
        description="Сохраняйте версии планов и готовьте сообщения. Профиль клиента не меняется автоматически, а сообщение попадает в уведомления только после явного подтверждения тренера."
        actions={!canManage && <Badge tone="neutral">Только просмотр</Badge>}
      >
        <div className="coach-workflow-templates__forms">
          <label className="field">
            <span>Название плана подключения</span>
            <input
              className="ui-input"
              disabled={!canManage}
              maxLength={128}
              onChange={(event) => setOnboardingName(event.target.value)}
              placeholder="Например, Первые две недели"
              value={onboardingName}
            />
          </label>
          <label className="field">
            <span>Описание</span>
            <input
              className="ui-input"
              disabled={!canManage}
              maxLength={500}
              onChange={(event) => setOnboardingDescription(event.target.value)}
              placeholder="Коротко о назначении плана"
              value={onboardingDescription}
            />
          </label>
          <StepPicker
            disabled={!canManage}
            idPrefix="onboarding-new-step"
            onChange={setOnboardingSteps}
            steps={onboardingSteps}
          />
          <ReferenceFields
            checkInTemplates={checkInItems}
            checkInTemplateId={onboardingCheckInId}
            disabled={!canManage}
            onCheckInTemplateChange={setOnboardingCheckInId}
            onProgramChange={setOnboardingProgramId}
            programTemplateId={onboardingProgramId}
            programTemplates={programItems}
            steps={onboardingSteps}
          />
          <Button
            disabled={
              !canManage ||
              !onboardingName.trim() ||
              !onboardingSteps.length ||
              createOnboarding.isPending
            }
            onClick={() => createOnboarding.mutate()}
            type="button"
          >
            {createOnboarding.isPending ? 'Сохраняем…' : 'Создать план подключения'}
          </Button>
        </div>
      </Card>

      <Card
        className="coach-workflow-templates__section"
        collapsible={false}
        title="Планы подключения"
        description="Назначение сохраняет выбранную версию и историю. Оно не меняет профиль, программу или проверки клиента без отдельного действия."
      >
        {onboardingItems.length === 0 ? (
          <EmptyState
            title="Планов подключения пока нет"
            text="Создайте первый повторяемый порядок шагов выше."
          />
        ) : (
          <div className="coach-workflow-templates__list">
            {onboardingItems.map((template) => {
              const current = template.current_version;
              const selectedClient = Number(onboardingClientIds[template.id] ?? 0);
              const isVersioning = versioningOnboardingId === template.id;
              return (
                <article className="coach-workflow-template" key={template.id}>
                  <div className="coach-workflow-template__header">
                    <div>
                      <h3>{template.name}</h3>
                      {template.description && <p className="muted">{template.description}</p>}
                    </div>
                    <Badge tone={template.is_active ? 'success' : 'neutral'}>
                      {template.is_active ? 'Активен' : 'Выключен'}
                    </Badge>
                  </div>
                  <p className="coach-workflow-template__meta">
                    Версия {current?.version ?? '—'} ·{' '}
                    {current?.steps
                      .map((step) => stepChoices.find((item) => item.key === step)?.label ?? step)
                      .join(', ') || 'Этапы не выбраны'}
                  </p>
                  {isVersioning && (
                    <div className="coach-workflow-template__editor">
                      <StepPicker
                        disabled={!canManage}
                        idPrefix={`onboarding-version-${template.id}-step`}
                        onChange={setVersionSteps}
                        steps={versionSteps}
                      />
                      <ReferenceFields
                        checkInTemplates={checkInItems}
                        checkInTemplateId={versionCheckInId}
                        disabled={!canManage}
                        onCheckInTemplateChange={setVersionCheckInId}
                        onProgramChange={setVersionProgramId}
                        programTemplateId={versionProgramId}
                        programTemplates={programItems}
                        steps={versionSteps}
                      />
                      <Button
                        disabled={
                          !canManage || !versionSteps.length || createOnboardingVersion.isPending
                        }
                        onClick={() => createOnboardingVersion.mutate({ templateId: template.id })}
                        type="button"
                      >
                        Сохранить новую версию
                      </Button>
                    </div>
                  )}
                  <div className="coach-workflow-template__actions">
                    <Button
                      disabled={!canManage || !current}
                      onClick={() => {
                        setVersioningOnboardingId(template.id);
                        setVersionSteps((current?.steps ?? []) as StepKey[]);
                        setVersionProgramId(current?.program_template_id ?? null);
                        setVersionCheckInId(current?.check_in_template_id ?? null);
                      }}
                      type="button"
                      variant="secondary"
                    >
                      Новая версия
                    </Button>
                  </div>
                  <div className="coach-workflow-template__assign">
                    <label className="field">
                      <span>Назначить клиенту</span>
                      <select
                        className="ui-input"
                        disabled={!canManage || !current || assignOnboarding.isPending}
                        onChange={(event) =>
                          setOnboardingClientIds((values) => ({
                            ...values,
                            [template.id]: event.target.value,
                          }))
                        }
                        value={onboardingClientIds[template.id] ?? ''}
                      >
                        <option value="">Выберите клиента</option>
                        {activeClients.map((client) => (
                          <option key={client.id} value={client.id ?? ''}>
                            {clientDisplayName(client)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <Button
                      disabled={
                        !canManage || !selectedClient || !current || assignOnboarding.isPending
                      }
                      onClick={() =>
                        assignOnboarding.mutate({
                          templateId: template.id,
                          clientId: selectedClient,
                          version: current?.version ?? 1,
                        })
                      }
                      type="button"
                      variant="secondary"
                    >
                      Назначить план
                    </Button>
                  </div>
                  <div className="coach-workflow-template__history">
                    <strong>История назначений</strong>
                    {(template.assignments ?? []).length === 0 ? (
                      <span className="muted">Назначений пока нет</span>
                    ) : (
                      <ul>
                        {(template.assignments ?? []).map((assignment) => (
                          <li key={assignment.id}>
                            {assignment.client_name} · версия {assignment.version} ·{' '}
                            {formatDate(assignment.created_at)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </Card>

      <Card
        className="coach-workflow-templates__section"
        collapsible={false}
        title="Шаблоны сообщений"
        description="Сообщение проходит путь «черновик → редактирование → явное подтверждение». До подтверждения уведомление клиенту не создаётся."
      >
        <div className="coach-workflow-templates__forms">
          <label className="field">
            <span>Название шаблона сообщения</span>
            <input
              className="ui-input"
              disabled={!canManage}
              maxLength={128}
              onChange={(event) => setCommunicationName(event.target.value)}
              placeholder="Например, После первой встречи"
              value={communicationName}
            />
          </label>
          <label className="field">
            <span>Описание</span>
            <input
              className="ui-input"
              disabled={!canManage}
              maxLength={500}
              onChange={(event) => setCommunicationDescription(event.target.value)}
              placeholder="Коротко о назначении сообщения"
              value={communicationDescription}
            />
          </label>
          <label className="field">
            <span>Тема сообщения</span>
            <input
              className="ui-input"
              disabled={!canManage}
              maxLength={128}
              onChange={(event) => setCommunicationSubject(event.target.value)}
              placeholder="Тема для клиента"
              value={communicationSubject}
            />
          </label>
          <label className="field coach-workflow-templates__wide-field">
            <span>Текст сообщения</span>
            <textarea
              className="ui-input"
              disabled={!canManage}
              maxLength={4000}
              onChange={(event) => setCommunicationBody(event.target.value)}
              placeholder="Подготовьте текст для дальнейшего редактирования"
              rows={4}
              value={communicationBody}
            />
          </label>
          <Button
            disabled={
              !canManage ||
              !communicationName.trim() ||
              !communicationSubject.trim() ||
              !communicationBody.trim() ||
              createCommunication.isPending
            }
            onClick={() => createCommunication.mutate()}
            type="button"
          >
            {createCommunication.isPending ? 'Сохраняем…' : 'Создать шаблон сообщения'}
          </Button>
        </div>
      </Card>

      <Card
        className="coach-workflow-templates__section"
        collapsible={false}
        title="Сообщения клиентов"
        description="Выберите клиента, создайте черновик, отредактируйте его и подтвердите отправку отдельной кнопкой."
      >
        {communicationItems.length === 0 ? (
          <EmptyState title="Шаблонов сообщений пока нет" text="Создайте первый шаблон выше." />
        ) : (
          <div className="coach-workflow-templates__list">
            {communicationItems.map((template) => {
              const current = template.current_version;
              const selectedClient = Number(communicationClientIds[template.id] ?? 0);
              const isVersioning = versioningCommunicationId === template.id;
              return (
                <article className="coach-workflow-template" key={template.id}>
                  <div className="coach-workflow-template__header">
                    <div>
                      <h3>{template.name}</h3>
                      {template.description && <p className="muted">{template.description}</p>}
                    </div>
                    <Badge tone={template.is_active ? 'success' : 'neutral'}>
                      {template.is_active ? 'Активен' : 'Выключен'}
                    </Badge>
                  </div>
                  <p className="coach-workflow-template__meta">
                    Версия {current?.version ?? '—'} · {current?.subject ?? 'Тема не задана'}
                  </p>
                  {current?.body && <p className="coach-workflow-template__body">{current.body}</p>}
                  {isVersioning && (
                    <div className="coach-workflow-template__editor">
                      <label className="field">
                        <span>Тема новой версии</span>
                        <input
                          className="ui-input"
                          disabled={!canManage}
                          onChange={(event) => setVersionSubject(event.target.value)}
                          value={versionSubject}
                        />
                      </label>
                      <label className="field">
                        <span>Текст новой версии</span>
                        <textarea
                          className="ui-input"
                          disabled={!canManage}
                          onChange={(event) => setVersionBody(event.target.value)}
                          rows={4}
                          value={versionBody}
                        />
                      </label>
                      <Button
                        disabled={
                          !canManage ||
                          !versionSubject.trim() ||
                          !versionBody.trim() ||
                          createCommunicationVersion.isPending
                        }
                        onClick={() =>
                          createCommunicationVersion.mutate({ templateId: template.id })
                        }
                        type="button"
                      >
                        Сохранить новую версию
                      </Button>
                    </div>
                  )}
                  <div className="coach-workflow-template__actions">
                    <Button
                      disabled={!canManage || !current}
                      onClick={() => {
                        setVersioningCommunicationId(template.id);
                        setVersionSubject(current?.subject ?? '');
                        setVersionBody(current?.body ?? '');
                      }}
                      type="button"
                      variant="secondary"
                    >
                      Новая версия
                    </Button>
                  </div>
                  <div className="coach-workflow-template__assign">
                    <label className="field">
                      <span>Создать черновик для клиента</span>
                      <select
                        className="ui-input"
                        disabled={!canManage || !current || createDraft.isPending}
                        onChange={(event) =>
                          setCommunicationClientIds((values) => ({
                            ...values,
                            [template.id]: event.target.value,
                          }))
                        }
                        value={communicationClientIds[template.id] ?? ''}
                      >
                        <option value="">Выберите клиента</option>
                        {activeClients.map((client) => (
                          <option key={client.id} value={client.id ?? ''}>
                            {clientDisplayName(client)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <Button
                      disabled={!canManage || !selectedClient || !current || createDraft.isPending}
                      onClick={() =>
                        createDraft.mutate({ templateId: template.id, clientId: selectedClient })
                      }
                      type="button"
                      variant="secondary"
                    >
                      Создать черновик
                    </Button>
                  </div>
                  <div className="coach-workflow-template__history">
                    <strong>Черновики</strong>
                    {(template.drafts ?? []).length === 0 ? (
                      <span className="muted">Черновиков пока нет</span>
                    ) : (
                      <ul>
                        {(template.drafts ?? []).map((item) => (
                          <li key={item.id}>
                            <span>
                              {item.client_name} · версия {item.version} ·{' '}
                              {formatDate(item.updated_at)}
                            </span>{' '}
                            <Badge tone={item.status === 'confirmed' ? 'success' : 'warning'}>
                              {item.status === 'confirmed' ? 'Подтверждено' : 'Черновик'}
                            </Badge>{' '}
                            <Button
                              onClick={() => setSelectedDraftId(item.id)}
                              type="button"
                              variant="ghost"
                            >
                              Открыть черновик
                            </Button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </Card>

      {selectedDraftId != null && (
        <Card
          className="coach-workflow-templates__section coach-workflow-templates__draft"
          collapsible={false}
          title={selectedDraft ? `Черновик для ${selectedDraft.client_name}` : 'Черновик сообщения'}
          description="Изменения сохраняются отдельно. Подтверждение добавляет одно уведомление в существующий внутренний поток клиента."
          actions={
            selectedDraft && (
              <Badge tone={selectedDraft.status === 'confirmed' ? 'success' : 'warning'}>
                {selectedDraft.status === 'confirmed' ? 'Подтверждено' : 'Черновик'}
              </Badge>
            )
          }
        >
          {draft.isPending ? (
            <LoadingState label="Загружаем черновик…" />
          ) : draft.error ? (
            <ErrorState
              message="Не удалось загрузить черновик сообщения."
              retry={() => void draft.refetch()}
            />
          ) : selectedDraft ? (
            <div className="coach-workflow-templates__draft-form">
              <label className="field">
                <span>Тема</span>
                <input
                  className="ui-input"
                  disabled={!canManage || selectedDraft.status === 'confirmed'}
                  onChange={(event) =>
                    setDraftEdits((values) => ({
                      ...values,
                      [selectedDraft.id]: {
                        subject: event.target.value,
                        body: currentDraftBody,
                      },
                    }))
                  }
                  value={currentDraftSubject}
                />
              </label>
              <label className="field">
                <span>Текст</span>
                <textarea
                  className="ui-input"
                  disabled={!canManage || selectedDraft.status === 'confirmed'}
                  onChange={(event) =>
                    setDraftEdits((values) => ({
                      ...values,
                      [selectedDraft.id]: {
                        subject: currentDraftSubject,
                        body: event.target.value,
                      },
                    }))
                  }
                  rows={6}
                  value={currentDraftBody}
                />
              </label>
              <div className="coach-workflow-template__actions">
                <Button
                  disabled={
                    !canManage ||
                    selectedDraft.status === 'confirmed' ||
                    !currentDraftSubject.trim() ||
                    !currentDraftBody.trim() ||
                    updateDraft.isPending
                  }
                  onClick={() => updateDraft.mutate()}
                  type="button"
                  variant="secondary"
                >
                  Сохранить изменения
                </Button>
                <Button
                  disabled={
                    !canManage || selectedDraft.status === 'confirmed' || confirmDraft.isPending
                  }
                  onClick={() => confirmDraft.mutate()}
                  type="button"
                >
                  {selectedDraft.status === 'confirmed'
                    ? 'Сообщение подтверждено'
                    : 'Подтвердить сообщение'}
                </Button>
              </div>
            </div>
          ) : null}
        </Card>
      )}
    </section>
  );
}
